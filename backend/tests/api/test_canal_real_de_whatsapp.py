"""El composition root del canal de WhatsApp (U5, ADR-0011 §2 y §3).

`armar_mensajeria` arma el canal de **una empresa** a partir de su integración; sin integración,
en producción devuelve `SinCanal` y no el simulado (que se niega a arrancar ahí y daría por
enviado lo que no salió). Todo corre sin red: la integración y el cifrado son dobles.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from cheatsheet.api import mensajeria as modulo
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.contexts.conversational.infrastructure.canal import (
    ConfiguracionDeMensajeria,
    MensajeriaSimulada,
    SinCanal,
)
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.platform.settings import AdaptadorDeWhatsApp, Entorno, Settings
from cheatsheet.shared.empresa import EmpresaId

from tests.conftest import settings_de_prueba

pytestmark = pytest.mark.asyncio


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


def _con_integraciones(
    monkeypatch: pytest.MonkeyPatch, por_empresa: dict[UUID, _Configuracion]
) -> None:
    monkeypatch.setattr(
        Integraciones,
        "armar",
        staticmethod(lambda _sesion, _settings: _Piezas(_Integraciones(por_empresa))),
    )
    monkeypatch.setattr(modulo, "MensajeriaWhatsApp", _CanalGrabador)


def _unidad() -> UnidadDeTrabajo:
    return UnidadDeTrabajo(sesion=None, publicador=None, reloj=None)  # type: ignore[arg-type]


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
        _unidad(), _meta(Entorno.PRODUCTION), empresa_id=EmpresaId(uuid4())
    )

    assert isinstance(canal, SinCanal)


async def test_en_produccion_sin_phone_number_id_devuelve_sin_canal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empresa = EmpresaId(uuid4())
    _con_integraciones(monkeypatch, {empresa: _Configuracion(b"fake-token-for-tests")})

    canal = await armar_mensajeria(_unidad(), _meta(Entorno.PRODUCTION), empresa_id=empresa)

    assert isinstance(canal, SinCanal)


async def test_fuera_de_produccion_sin_integracion_sigue_siendo_el_simulado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _con_integraciones(monkeypatch, {})

    canal = await armar_mensajeria(_unidad(), _meta(Entorno.STAGING), empresa_id=EmpresaId(uuid4()))

    assert isinstance(canal, MensajeriaSimulada)


async def test_con_el_adaptador_simulado_nunca_se_consulta_la_integracion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_debe_llamarse(_sesion: object, _settings: object) -> _Piezas:
        raise AssertionError("no se lee `integrations` con el adaptador simulado")

    monkeypatch.setattr(Integraciones, "armar", staticmethod(_no_debe_llamarse))

    canal = await armar_mensajeria(_unidad(), settings_de_prueba(), empresa_id=EmpresaId(uuid4()))

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

    canal_a = await armar_mensajeria(_unidad(), settings, empresa_id=a)
    canal_b = await armar_mensajeria(_unidad(), settings, empresa_id=b)

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
