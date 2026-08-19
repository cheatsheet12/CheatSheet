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
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.platform.settings import (
    AdaptadorDeArca,
    AdaptadorDeEmail,
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
        whatsapp_sondeo_maximo_dias=7,
        # The simulator, and hosts that do not resolve: a test that ever reached the
        # network would fail loudly instead of quietly talking to ARCA.
        arca_adaptador=AdaptadorDeArca.SIMULADO,
        arca_wsaa_url_homologacion="https://wsaahomo.invalid/ws/services/LoginCms",
        arca_wsaa_url_produccion="https://wsaa.invalid/ws/services/LoginCms",
        arca_timeout_segundos=1,
        arca_margen_renovacion_minutos=30,
        arca_aviso_vencimiento_dias=30,
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
