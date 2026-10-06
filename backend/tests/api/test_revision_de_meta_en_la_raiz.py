"""La revisión de plantillas en el composition root (U6, ADR-0011 §4, casos 19 y 20).

`armar_revision_de_meta` arma el cliente de plantillas de **una empresa** a partir de su integración
y lo envuelve en `_RevisionViaMeta`, que traduce los errores tipados de `conversational` a los de
`business_config`. Todo corre sin red: la integración y el cifrado son dobles.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from cheatsheet.api import mensajeria as modulo
from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.api.mensajeria import _RevisionViaMeta, armar_revision_de_meta
from cheatsheet.contexts.business_config.application.errors import (
    MetaNoConectada,
    MetaNoDisponible,
    MetaRechazoLaPlantilla,
)
from cheatsheet.contexts.conversational.application.errors import (
    CanalNoConectado,
    EnvioIncierto,
    MensajeRechazado,
    MensajeriaSaturada,
)
from cheatsheet.contexts.conversational.infrastructure.plantillas_meta import (
    PlantillaEnMeta,
    PlantillasDeMeta,
    PlantillasSimuladas,
    RespuestaDePlantilla,
    SinCuentaDeMeta,
)
from cheatsheet.contexts.integrations.infrastructure.cifrado import CredencialIlegible
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
        return credencial


@dataclass
class _Piezas:
    integraciones: _Integraciones
    cifrado: _Cifrado = field(default_factory=_Cifrado)


def _con_integraciones(
    monkeypatch: pytest.MonkeyPatch, por_empresa: dict[UUID, _Configuracion]
) -> None:
    monkeypatch.setattr(
        Integraciones,
        "armar",
        staticmethod(lambda _sesion, _settings: _Piezas(_Integraciones(por_empresa))),
    )


def _unidad() -> UnidadDeTrabajo:
    return UnidadDeTrabajo(sesion=None, publicador=None, reloj=None)  # type: ignore[arg-type]


def _meta(entorno: Entorno) -> Settings:
    return replace(
        settings_de_prueba(entorno), entorno=entorno, whatsapp_adaptador=AdaptadorDeWhatsApp.META
    )


def _cliente_de(revision: object) -> object:
    assert isinstance(revision, _RevisionViaMeta)
    return revision._cliente


async def test_con_el_adaptador_simulado_aprueba_sin_leer_la_integracion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_debe_llamarse(_sesion: object, _settings: object) -> _Piezas:
        raise AssertionError("no se lee `integrations` con el adaptador simulado")

    monkeypatch.setattr(Integraciones, "armar", staticmethod(_no_debe_llamarse))

    revision = await armar_revision_de_meta(
        _unidad(), settings_de_prueba(), empresa_id=EmpresaId(uuid4())
    )

    assert isinstance(_cliente_de(revision), PlantillasSimuladas)
    respuesta = await revision.crear(nombre="x", idioma="es_AR", cuerpo="Hola.", ejemplos={})
    assert respuesta.estado == "APPROVED"


async def test_con_integracion_arma_el_cliente_con_el_token_y_la_waba_de_la_empresa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empresa = EmpresaId(uuid4())
    _con_integraciones(
        monkeypatch,
        {empresa: _Configuracion(b"fake-token-de-a", {modulo.CLAVE_WABA_ID: "waba-777"})},
    )

    revision = await armar_revision_de_meta(
        _unidad(), _meta(Entorno.PRODUCTION), empresa_id=empresa
    )

    cliente = _cliente_de(revision)
    assert isinstance(cliente, PlantillasDeMeta)
    assert cliente._token == "fake-token-de-a"
    assert cliente._waba_id == "waba-777"


async def test_cada_empresa_usa_su_propio_token_y_su_propia_waba(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a, b = EmpresaId(uuid4()), EmpresaId(uuid4())
    _con_integraciones(
        monkeypatch,
        {
            a: _Configuracion(b"fake-token-de-a", {modulo.CLAVE_WABA_ID: "waba-a"}),
            b: _Configuracion(b"fake-token-de-b", {modulo.CLAVE_WABA_ID: "waba-b"}),
        },
    )
    settings = _meta(Entorno.PRODUCTION)

    cliente_a = _cliente_de(await armar_revision_de_meta(_unidad(), settings, empresa_id=a))
    cliente_b = _cliente_de(await armar_revision_de_meta(_unidad(), settings, empresa_id=b))

    assert isinstance(cliente_a, PlantillasDeMeta)
    assert isinstance(cliente_b, PlantillasDeMeta)
    assert (cliente_a._waba_id, cliente_a._token) == ("waba-a", "fake-token-de-a")
    assert (cliente_b._waba_id, cliente_b._token) == ("waba-b", "fake-token-de-b")


async def test_en_produccion_sin_integracion_o_sin_waba_no_hay_cuenta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    con_integracion_sin_waba = EmpresaId(uuid4())
    _con_integraciones(
        monkeypatch, {con_integracion_sin_waba: _Configuracion(b"fake-token-for-tests")}
    )
    settings = _meta(Entorno.PRODUCTION)

    sin_integracion = await armar_revision_de_meta(
        _unidad(), settings, empresa_id=EmpresaId(uuid4())
    )
    sin_waba = await armar_revision_de_meta(
        _unidad(), settings, empresa_id=con_integracion_sin_waba
    )

    assert isinstance(_cliente_de(sin_integracion), SinCuentaDeMeta)
    assert isinstance(_cliente_de(sin_waba), SinCuentaDeMeta)
    with pytest.raises(MetaNoConectada):
        await sin_integracion.estados()


async def test_fuera_de_produccion_sin_integracion_sigue_siendo_el_simulado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _con_integraciones(monkeypatch, {})

    revision = await armar_revision_de_meta(
        _unidad(), _meta(Entorno.STAGING), empresa_id=EmpresaId(uuid4())
    )

    assert isinstance(_cliente_de(revision), PlantillasSimuladas)


@pytest.mark.parametrize("entorno", [Entorno.PRODUCTION, Entorno.STAGING])
async def test_una_credencial_ilegible_no_hay_cuenta_en_ningun_entorno(
    monkeypatch: pytest.MonkeyPatch, entorno: Entorno
) -> None:
    """Caso 20: aprobar plantillas sin poder hablar con Meta daría por hecho lo que no pasó."""
    empresa = EmpresaId(uuid4())
    _con_integraciones(monkeypatch, {empresa: _Configuracion(b"x", {modulo.CLAVE_WABA_ID: "w"})})

    def _ilegible(_self: object, _credencial: bytes) -> bytes:
        raise CredencialIlegible("La credencial no autentica")

    monkeypatch.setattr(_Cifrado, "descifrar", _ilegible)

    revision = await armar_revision_de_meta(_unidad(), _meta(entorno), empresa_id=empresa)

    assert isinstance(_cliente_de(revision), SinCuentaDeMeta)


async def test_las_simuladas_se_niegan_a_construirse_en_produccion() -> None:
    """Caso 19: con el adaptador `simulado` en producción no hay revisión posible."""
    produccion = replace(
        settings_de_prueba(Entorno.PRODUCTION),
        entorno=Entorno.PRODUCTION,
        whatsapp_adaptador=AdaptadorDeWhatsApp.SIMULADO,
    )

    with pytest.raises(RuntimeError):
        await armar_revision_de_meta(_unidad(), produccion, empresa_id=EmpresaId(uuid4()))


# --- La traducción de errores ---------------------------------------------------------------------------------


class _ClienteQueFalla:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def crear(
        self, *, nombre: str, idioma: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        del nombre, idioma, cuerpo, ejemplos
        raise self._error

    async def editar(
        self, *, meta_plantilla_id: str, cuerpo: str, ejemplos: Mapping[str, str]
    ) -> RespuestaDePlantilla:
        del meta_plantilla_id, cuerpo, ejemplos
        raise self._error

    async def estados(self) -> list[PlantillaEnMeta]:
        raise self._error


async def _crear(error: Exception) -> None:
    await _RevisionViaMeta(_ClienteQueFalla(error)).crear(
        nombre="x", idioma="es_AR", cuerpo="Hola.", ejemplos={}
    )


async def test_un_rechazo_de_meta_lleva_su_texto_y_si_el_nombre_estaba_en_uso() -> None:
    with pytest.raises(MetaRechazoLaPlantilla) as salida:
        await _crear(
            MensajeRechazado(
                "WhatsApp rechazó la plantilla",
                codigo=100,
                subcodigo=2388023,
                mensaje_para_el_usuario="Ya existe esa plantilla.",
            )
        )

    assert str(salida.value) == "Ya existe esa plantilla."
    assert salida.value.nombre_en_uso is True


async def test_un_rechazo_sin_texto_de_meta_usa_el_del_error_sin_inventar_datos() -> None:
    with pytest.raises(MetaRechazoLaPlantilla) as salida:
        await _crear(MensajeRechazado("WhatsApp rechazó la plantilla (HTTP 400, código 100)"))

    assert "código 100" in str(salida.value)
    assert salida.value.nombre_en_uso is False


@pytest.mark.parametrize(
    ("error", "incierto"),
    [(MensajeriaSaturada("x"), False), (EnvioIncierto("x"), True)],
)
async def test_saturada_e_incierta_son_meta_no_disponible(error: Exception, incierto: bool) -> None:
    with pytest.raises(MetaNoDisponible) as salida:
        await _crear(error)

    assert salida.value.incierto is incierto


async def test_canal_no_conectado_es_meta_no_conectada_en_las_tres_operaciones() -> None:
    revision = _RevisionViaMeta(_ClienteQueFalla(CanalNoConectado("sin cuenta")))

    with pytest.raises(MetaNoConectada):
        await revision.crear(nombre="x", idioma="es_AR", cuerpo="Hola.", ejemplos={})
    with pytest.raises(MetaNoConectada):
        await revision.editar(meta_plantilla_id="1", cuerpo="Hola.", ejemplos={})
    with pytest.raises(MetaNoConectada):
        await revision.estados()


async def test_los_estados_se_traducen_a_los_de_business_config() -> None:
    class _Cliente(_ClienteQueFalla):
        async def estados(self) -> list[PlantillaEnMeta]:
            return [
                PlantillaEnMeta(
                    meta_plantilla_id="1",
                    nombre="turno_confirmado",
                    idioma="es_AR",
                    estado="REJECTED",
                    categoria="UTILITY",
                    motivo="SCAM",
                    cuerpo="Hola.",
                )
            ]

    (una,) = await _RevisionViaMeta(_Cliente(RuntimeError())).estados()

    assert (una.meta_plantilla_id, una.nombre, una.estado, una.motivo) == (
        "1",
        "turno_confirmado",
        "REJECTED",
        "SCAM",
    )
