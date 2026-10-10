"""El composition root del canal de WhatsApp (U5, ADR-0011 §2 y §3).

`armar_mensajeria` arma el canal de **una empresa** a partir de su integración; sin integración,
en producción devuelve `SinCanal` y no el simulado (que se niega a arrancar ahí y daría por
enviado lo que no salió). Todo corre sin red: la integración y el cifrado son dobles.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from cheatsheet.api import mensajeria as modulo
from cheatsheet.api.conversacional import _NotificadorSilencioso, armar_agenda
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.api.mercadopago import armar_envio
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaSimulada,
    SinCanal,
)
from cheatsheet.contexts.integrations.infrastructure.cifrado import CredencialIlegible
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.contexts.payments.infrastructure.envio import EnvioPorWhatsApp
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno
from cheatsheet.platform.settings import AdaptadorDeWhatsApp, Entorno, Settings
from cheatsheet.shared.empresa import EmpresaId

from tests.api.montaje_avisos_de_turno_reales import (
    Meta,
    canal_real,
    cancelar,
    escena_con_canal,
    unidad,
)
from tests.conftest import settings_de_prueba

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("hilos", "sin_plantillas_aprobadas"),
]


@dataclass
class _Configuracion:
    credencial: bytes
    parametros: dict[str, Any] = field(default_factory=dict)


class _Integraciones:
    def __init__(self, por_empresa: dict[UUID, _Configuracion]) -> None:
        self._por_empresa = por_empresa

    async def buscar(self, empresa_id: UUID, sistema: object) -> _Configuracion | None:
        del sistema
        return self._por_empresa.get(empresa_id)


class _Cifrado:
    def descifrar(self, credencial: bytes) -> bytes:
        return credencial  # el doble no cifra: el valor ya viene en claro


@dataclass
class _Piezas:
    integraciones: _Integraciones
    cifrado: _Cifrado = field(default_factory=_Cifrado)


class _CanalGrabador:
    """Reemplaza a `MensajeriaWhatsApp` para ver con qué configuración se armó."""

    def __init__(self, configuracion: ConfiguracionDeMensajeria) -> None:
        self.configuracion = configuracion

    async def enviar(self, *, telefono: str, texto: str) -> str:  # pragma: no cover
        del telefono, texto
        raise AssertionError("este doble no envía")

    async def enviar_plantilla(  # pragma: no cover
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        raise AssertionError("este doble no envía")


def _con_integraciones(
    monkeypatch: pytest.MonkeyPatch, por_empresa: dict[UUID, _Configuracion]
) -> None:
    monkeypatch.setattr(
        Integraciones,
        "armar",
        staticmethod(lambda _sesion, _settings: _Piezas(_Integraciones(por_empresa))),
    )
    monkeypatch.setattr(modulo, "MensajeriaWhatsApp", _CanalGrabador)


def _meta(entorno: Entorno) -> Settings:
    return replace(
        settings_de_prueba(entorno), entorno=entorno, whatsapp_adaptador=AdaptadorDeWhatsApp.META
    )


async def test_en_produccion_sin_integracion_devuelve_sin_canal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Caso 15.** Antes devolvía `MensajeriaSimulada`, que en producción levanta
    `RuntimeError`: cancelar un turno de una empresa sin WhatsApp daba 500."""
    _con_integraciones(monkeypatch, {})

    canal = await armar_mensajeria(
        unidad(), _meta(Entorno.PRODUCTION), empresa_id=EmpresaId(uuid4())
    )

    assert isinstance(canal, SinCanal)


async def test_en_produccion_sin_phone_number_id_devuelve_sin_canal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empresa = EmpresaId(uuid4())
    _con_integraciones(monkeypatch, {empresa: _Configuracion(b"fake-token-for-tests")})

    canal = await armar_mensajeria(unidad(), _meta(Entorno.PRODUCTION), empresa_id=empresa)

    assert isinstance(canal, SinCanal)


async def test_una_credencial_ilegible_en_produccion_cae_a_sin_canal_y_no_levanta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hallazgo de revisión: `descifrar` levantaba `CredencialIlegible` fuera de
    `armar_mensajeria`; reservar, cancelar y reprogramar daban 500 y el barrido de cobros
    abortaba la empresa entera. Ahora cae a `SinCanal` y quien llama registra `FALLIDO`."""
    from structlog.testing import capture_logs

    empresa = EmpresaId(uuid4())
    _con_integraciones(
        monkeypatch, {empresa: _Configuracion(b"x", {modulo.CLAVE_PHONE_NUMBER_ID: "111"})}
    )

    def _ilegible(_self: object, _credencial: bytes) -> bytes:
        raise CredencialIlegible("La credencial no autentica: token-secreto-123")

    monkeypatch.setattr(_Cifrado, "descifrar", _ilegible)

    with capture_logs() as registros:
        canal = await armar_mensajeria(unidad(), _meta(Entorno.PRODUCTION), empresa_id=empresa)

    assert isinstance(canal, SinCanal)
    aviso = [r for r in registros if r["event"] == "whatsapp_credencial_ilegible"]
    assert len(aviso) == 1
    assert aviso[0]["empresa_id"] == str(empresa)
    assert aviso[0]["causa"] == "CredencialIlegible"
    assert "token-secreto-123" not in repr(registros)


async def test_una_credencial_que_no_es_utf8_cae_a_sin_canal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empresa = EmpresaId(uuid4())
    _con_integraciones(
        monkeypatch, {empresa: _Configuracion(b"\xff\xfe", {modulo.CLAVE_PHONE_NUMBER_ID: "111"})}
    )

    canal = await armar_mensajeria(unidad(), _meta(Entorno.PRODUCTION), empresa_id=empresa)

    assert isinstance(canal, SinCanal)


async def test_fuera_de_produccion_sin_integracion_sigue_siendo_el_simulado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _con_integraciones(monkeypatch, {})

    canal = await armar_mensajeria(unidad(), _meta(Entorno.STAGING), empresa_id=EmpresaId(uuid4()))

    assert isinstance(canal, MensajeriaSimulada)


async def test_con_el_adaptador_simulado_nunca_se_consulta_la_integracion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_debe_llamarse(_sesion: object, _settings: object) -> _Piezas:
        raise AssertionError("no se lee `integrations` con el adaptador simulado")

    monkeypatch.setattr(Integraciones, "armar", staticmethod(_no_debe_llamarse))

    canal = await armar_mensajeria(unidad(), settings_de_prueba(), empresa_id=EmpresaId(uuid4()))

    assert isinstance(canal, MensajeriaSimulada)


async def test_cada_empresa_usa_su_propio_token_y_su_propio_numero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Caso 28.** La empresa A nunca usa el token de la B."""
    a, b = EmpresaId(uuid4()), EmpresaId(uuid4())
    _con_integraciones(
        monkeypatch,
        {
            a: _Configuracion(b"fake-token-de-a", {modulo.CLAVE_PHONE_NUMBER_ID: "111"}),
            b: _Configuracion(b"fake-token-de-b", {modulo.CLAVE_PHONE_NUMBER_ID: "222"}),
        },
    )
    settings = _meta(Entorno.PRODUCTION)

    canal_a = await armar_mensajeria(unidad(), settings, empresa_id=a)
    canal_b = await armar_mensajeria(unidad(), settings, empresa_id=b)

    assert isinstance(canal_a, _CanalGrabador)
    assert isinstance(canal_b, _CanalGrabador)
    assert (canal_a.configuracion.token, canal_a.configuracion.phone_number_id) == (
        "fake-token-de-a",
        "111",
    )
    assert (canal_b.configuracion.token, canal_b.configuracion.phone_number_id) == (
        "fake-token-de-b",
        "222",
    )


# --- armar_envio: el recordatorio sale por el canal que le pasan (U5, caso 13) -------------


async def test_armar_envio_cablea_el_canal_recibido_con_el_contacto_del_cliente() -> None:
    canal = MensajeriaSimulada(Entorno.STAGING)

    envio = armar_envio(unidad(), canal=canal)

    assert isinstance(envio, EnvioPorWhatsApp)


# --- avisos de turno por el canal real (U5, casos 14, 15, 25 y 34) ----------------------------


async def test_cancelar_un_turno_desde_el_panel_llega_a_la_cloud_api() -> None:
    """**Caso 14.** Antes el aviso iba a `AvisoPorConsola` y nunca salía."""
    meta = Meta(httpx.Response(200, json={"messages": [{"id": "wamid.OK"}]}))
    escena, turno = escena_con_canal(canal_real(meta))

    cancelado = await cancelar(escena, turno)

    assert cancelado.estado is EstadoTurno.CANCELADO
    assert len(meta.pedidos) == 1
    cuerpo = json.loads(meta.pedidos[0].read())
    assert cuerpo["to"] == "5491112345678"
    assert "fue cancelado" in cuerpo["text"]["body"]


async def test_meta_en_500_durante_una_cancelacion_deja_el_turno_cancelado_y_la_bitacora() -> None:
    """**Caso 25.** Un fallo del canal no voltea la operación."""
    meta = Meta(httpx.Response(500))
    escena, turno = escena_con_canal(canal_real(meta))

    cancelado = await cancelar(escena, turno)

    assert cancelado.estado is EstadoTurno.CANCELADO
    assert len(meta.pedidos) == 3  # los tres intentos con espera, y después el aviso se loguea
    assert "cancelar_turno" in escena.publicador.acciones


async def test_cancelar_en_produccion_sin_whatsapp_conectado_no_levanta_y_cancela() -> None:
    """**Caso 15.** Antes de `SinCanal`, el simulado levantaba `RuntimeError` en producción."""
    escena, turno = escena_con_canal(SinCanal())

    cancelado = await cancelar(escena, turno)

    assert cancelado.estado is EstadoTurno.CANCELADO
    assert "cancelar_turno" in escena.publicador.acciones


async def test_el_agente_sigue_sin_mandar_un_segundo_aviso() -> None:
    """**Caso 34.** `armar_agenda` arma su `Avisador` con el notificador silencioso, no con
    `AvisoPorWhatsApp`: el agente confirma en la conversación."""
    unidad = UnidadDeTrabajo(
        sesion=SimpleNamespace(begin_nested=lambda: None),  # type: ignore[arg-type]
        publicador=None,  # type: ignore[arg-type]
        reloj=None,  # type: ignore[arg-type]
    )
    agenda = armar_agenda(unidad, empresa_id=EmpresaId(uuid4()), usuario_id=None)

    notificador = vars(vars(agenda)["_avisador"])["_notificador"]

    assert isinstance(notificador, _NotificadorSilencioso)
