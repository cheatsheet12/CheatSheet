"""Shared test fixtures.

The doubles here are hand-written rather than `unittest.mock` objects, and that is a
choice, not an omission: a `Mock` satisfies any interface, including one that no longer
exists. `RepositorioDeAuditoriaEnMemoria` implements `PortRegistroDeAuditoria` for real,
so the day the port changes, these tests fail — which is the whole point of having a
port.

Integration tests need a real PostgreSQL, because Row-Level Security is a feature of
the engine and cannot be faked. They live under `tests/integracion/` with their own
conftest, and skip themselves when the database is not configured.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.observability.application.errors import RegistroDuplicado
from cheatsheet.contexts.observability.application.ports import FiltrosDeBitacora
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.platform.settings import (
    DLQ_MAX_INTENTOS_POR_DEFECTO,
    MODELO_POR_DEFECTO,
    AdaptadorDeAlmacenamiento,
    AdaptadorDeArca,
    AdaptadorDeCatalogos,
    AdaptadorDeEmail,
    AdaptadorDeMercadoPago,
    AdaptadorDeModelo,
    AdaptadorDePlanilla,
    AdaptadorDeWhatsApp,
    Entorno,
    Settings,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId

INSTANTE_FIJO = datetime(2026, 8, 12, 15, 30, tzinfo=UTC)


class RepositorioDeAuditoriaEnMemoria:
    """A real implementation of `PortRegistroDeAuditoria`, backed by a dict.

    It reproduces the one behaviour the production adapter has that matters to the use
    case: a duplicate `evento_id` raises instead of overwriting.
    """

    def __init__(self) -> None:
        self.registros: dict[UUID, RegistroDeAuditoria] = {}

    async def agregar(self, registro: RegistroDeAuditoria) -> None:
        if any(r.evento_id == registro.evento_id for r in self.registros.values()):
            raise RegistroDuplicado(registro.evento_id)
        self.registros[registro.id] = registro

    async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
        return next((r for r in self.registros.values() if r.evento_id == evento_id), None)

    async def buscar_por_id(self, registro_id: UUID) -> RegistroDeAuditoria | None:
        return self.registros.get(registro_id)

    async def listar(self, filtros: FiltrosDeBitacora) -> list[RegistroDeAuditoria]:
        """Lo mínimo que hace falta para que este doble siga satisfaciendo el puerto.

        Sin filtrar: los tests que ejercitan los filtros usan el doble de
        `tests/contexts/observability`, que sí los reproduce, y los que ejercitan el SQL de
        verdad corren contra PostgreSQL. Un tercer lugar donde reproducir el `WHERE` sería un
        tercer lugar donde equivocarse.
        """
        ordenados = sorted(self.registros.values(), key=lambda uno: uno.timestamp, reverse=True)
        return ordenados[filtros.desplazamiento : filtros.desplazamiento + filtros.limite]

    async def listar_de_entidad(self, entidad: str) -> list[RegistroDeAuditoria]:
        de_la_entidad = [uno for uno in self.registros.values() if uno.entidad_afectada == entidad]
        return sorted(de_la_entidad, key=lambda uno: uno.timestamp)

    async def contar(self, filtros: FiltrosDeBitacora) -> int:
        del filtros
        return len(self.registros)


def settings_de_prueba(entorno: Entorno = Entorno.TEST) -> Settings:
    """A complete `Settings` with nothing real in it.

    Built here rather than in each test file: `Settings` grows a field every time a unit
    adds an integration, and a constructor repeated across files means every one of them
    breaks on that day. No credential is real and no host resolves.
    """
    return Settings(
        entorno=entorno,
        database_url="postgresql+asyncpg://x/y",
        database_url_migrations="postgresql+asyncpg://x/y",
        redis_url="redis://localhost:6380/0",
        celery_broker_url="redis://localhost:6380/0",
        celery_result_backend="redis://localhost:6380/0",
        log_level="WARNING",
        jwt_secret="fake-secret-for-tests",
        jwt_access_ttl_minutos=15,
        refresh_ttl_dias=30,
        terminos_version_vigente="1.0",
        # `CifradoAesGcm` validates the length at construction, so this has to decode to
        # exactly 32 bytes — a placeholder string would fail every test that builds
        # `Settings`. Encoded here rather than pasted as base64 on purpose: a literal
        # blob is high-entropy, and `gitleaks` is right to flag one in a source file even
        # when it protects nothing. Readable ASCII says what it is, like `jwt_secret`
        # above, and the scanner has nothing to report.
        secrets_encryption_key=base64.b64encode(b"fake-encryption-key-for-tests-32").decode(),
        integracion_timeout_segundos=1,
        # The simulator, and a host that does not resolve: if any test ever reached the
        # network it would fail loudly instead of quietly talking to Meta.
        whatsapp_adaptador=AdaptadorDeWhatsApp.SIMULADO,
        whatsapp_graph_url="https://graph.invalid",
        whatsapp_graph_version="v21.0",
        whatsapp_timeout_segundos=1,
        whatsapp_sondeo_minutos=30,
        whatsapp_plantillas_minutos=30,
        recordatorio_de_turno_minutos=15,
        # Un secreto de prueba, no vacio: con la cadena vacia **ninguna firma vale** (HS-T2),
        # asi que dejarlo en blanco haria que el test del camino feliz del webhook pasara por
        # el motivo equivocado.
        whatsapp_webhook_secret="secreto-de-whatsapp",
        whatsapp_webhook_verify_token="token-de-verificacion",
        whatsapp_sondeo_maximo_dias=7,
        # The simulator, and hosts that do not resolve: a test that ever reached the
        # network would fail loudly instead of quietly talking to ARCA.
        arca_adaptador=AdaptadorDeArca.SIMULADO,
        arca_wsaa_url_homologacion="https://wsaahomo.invalid/ws/services/LoginCms",
        arca_wsaa_url_produccion="https://wsaa.invalid/ws/services/LoginCms",
        arca_padron_url_homologacion="https://padronhomo.invalid/personaServiceA5",
        arca_padron_url_produccion="https://padron.invalid/personaServiceA5",
        arca_timeout_segundos=1,
        arca_margen_renovacion_minutos=30,
        arca_aviso_vencimiento_dias=30,
        # The simulator again, and a host that does not resolve. The application
        # credentials are placeholders: nothing in the suite exchanges a real code.
        mercadopago_adaptador=AdaptadorDeMercadoPago.SIMULADO,
        mercadopago_client_id="app-de-prueba",
        mercadopago_client_secret="secreto-de-prueba",
        mercadopago_redirect_uri="http://localhost:3000/configuracion/integraciones",
        mercadopago_auth_url="https://auth.mercadopago.invalid",
        mercadopago_api_url="https://api.mercadopago.invalid",
        mercadopago_timeout_segundos=1,
        mercadopago_margen_renovacion_dias=15,
        # Un secreto de prueba, no vacio: con la cadena vacia **ninguna firma vale** (HS-T1
        # RN-01), asi que dejarlo en blanco haria que el test del camino feliz del webhook
        # pasara por el motivo equivocado.
        mercadopago_webhook_secret="secreto-de-prueba",
        mercadopago_url_de_retorno="http://localhost:3000/cobros",
        mercadopago_url_de_notificaciones="http://localhost:8000",
        mercadopago_autorizacion_ttl_minutos=10,
        google_oauth_client_id="",
        google_oauth_client_secret="",
        google_oauth_redirect_uri="",
        app_base_url="http://localhost:3000",
        invitacion_ttl_dias=7,
        email_adaptador=AdaptadorDeEmail.CONSOLA,
        smtp_host="",
        smtp_port=587,
        smtp_usuario="",
        smtp_password="",
        smtp_remitente="no-reply@cheatsheet.test",
        smtp_tls=True,
        smtp_timeout_segundos=10,
        # HS-T6. The ceiling comes from the constant rather than a literal, so the
        # suite keeps testing whatever the default actually is.
        dlq_barrido_minutos=15,
        # spreadsheet_sync: the simulator and an unconfigured bucket. A test that
        # ever reached R2 would fail loudly instead of writing somebody's file.
        planilla_adaptador=AdaptadorDePlanilla.SIMULADO,
        almacenamiento_adaptador=AdaptadorDeAlmacenamiento.MEMORIA,
        almacenamiento_directorio="",
        r2_endpoint="",
        r2_bucket="",
        r2_access_key_id="",
        r2_secret_access_key="",
        # The simulator and no key: a test that ever reached the model would fail loudly
        # instead of quietly spending money and sending somebody's headers to a vendor.
        llm_adaptador=AdaptadorDeModelo.SIMULADO,
        anthropic_api_key="",
        llm_modelo=MODELO_POR_DEFECTO,
        llm_timeout_segundos=1.0,
        llm_max_tokens=1024,
        sync_planillas_minutos=60,
        # The simulator and hosts that do not resolve: a test that ever reached WSFEv1
        # would fail loudly instead of quietly asking ARCA for a catalogue.
        catalogos_fiscales_adaptador=AdaptadorDeCatalogos.SIMULADO,
        arca_wsfe_url_homologacion="https://wsfehomo.invalid/wsfev1/service.asmx",
        arca_wsfe_url_produccion="https://wsfe.invalid/wsfev1/service.asmx",
        parametros_fiscales_horas=24,
        dlq_max_intentos=DLQ_MAX_INTENTOS_POR_DEFECTO,
    )


@pytest.fixture
def settings() -> Settings:
    return settings_de_prueba()


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo(INSTANTE_FIJO)


@pytest.fixture
def empresa_id() -> EmpresaId:
    return EmpresaId(uuid4())


@pytest.fixture
def repositorio() -> RepositorioDeAuditoriaEnMemoria:
    return RepositorioDeAuditoriaEnMemoria()


@pytest.fixture
def evento_auditable(empresa_id: EmpresaId) -> EventoAuditable:
    return EventoAuditable(
        evento_id=uuid4(),
        empresa_id=empresa_id,
        ocurrido_en=INSTANTE_FIJO,
        modulo=Modulo.IDENTITY,
        accion="cambiar_rol_de_usuario",
        entidad_afectada=f"Usuario:{uuid4()}",
        resultado=Resultado.COMPLETADO,
    )
