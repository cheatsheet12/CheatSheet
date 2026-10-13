"""`EnvioPorWhatsApp` en dos tiempos: `preparar` lee, `mandar` solo habla con el canal (U7, S1).

La llamada a Meta no puede hacer E/S de base: un error ahí, después de reservar y fuera de todo
savepoint, abortaría la transacción de la empresa entera. Por eso la lectura del contacto y de la
plantilla vive en `preparar`, y `mandar` recibe un mensaje ya armado.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.ports_de_recordatorios import (
    MensajeListo,
    ResultadoDeEnvio,
)
from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro, FallaDelCanal
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.contexts.payments.infrastructure.envio import EnvioPorWhatsApp
from cheatsheet.shared.empresa import EmpresaId
from sqlalchemy.exc import OperationalError

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def _cobro() -> Cobro:
    return Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("10.00"),
        descripcion="Consulta",
        vence_el=AHORA,
        created_at=AHORA,
    )


class _Contactos:
    def __init__(self, contacto: ContactoDeCobro | None, falla: Exception | None = None) -> None:
        self._contacto = contacto
        self._falla = falla
        self.lecturas = 0

    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
        del cliente_id
        self.lecturas += 1
        if self._falla is not None:
            raise self._falla
        return self._contacto


class _Plantillas:
    def __init__(self) -> None:
        self.lecturas = 0

    async def para(self, codigo: str, variables: Mapping[str, str]) -> None:
        del codigo, variables
        self.lecturas += 1


class _Canal:
    def __init__(self, falla: Exception | None = None) -> None:
        self._falla = falla
        self.mandados: list[str] = []

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono
        if self._falla is not None:
            raise self._falla
        self.mandados.append(texto)
        return "wamid.OK"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        return "wamid.OK"


CONTACTO = ContactoDeCobro(nombre="Rosa Diaz", telefono="5491155550000")


def _envio(
    *,
    contactos: _Contactos | None = None,
    plantillas: _Plantillas | None = None,
    canal: _Canal | None = None,
) -> EnvioPorWhatsApp:
    return EnvioPorWhatsApp(
        canal or _Canal(), contactos or _Contactos(CONTACTO), plantillas or _Plantillas()
    )


async def _preparar(envio: EnvioPorWhatsApp, cobro: Cobro) -> MensajeListo | ResultadoDeEnvio:
    return await envio.preparar(empresa_id=EMPRESA, cobro=cobro, canal="WHATSAPP", paso=1)


async def test_preparar_lee_el_contacto_y_la_plantilla_y_no_manda_nada() -> None:
    contactos, plantillas, canal = _Contactos(CONTACTO), _Plantillas(), _Canal()
    cobro = _cobro()

    preparado = await _preparar(
        _envio(contactos=contactos, plantillas=plantillas, canal=canal), cobro
    )

    assert isinstance(preparado, MensajeListo)
    assert (preparado.cobro_id, preparado.paso, preparado.canal) == (cobro.id, 1, "WHATSAPP")
    assert preparado.telefono == CONTACTO.telefono
    assert (contactos.lecturas, plantillas.lecturas) == (1, 1)
    assert canal.mandados == []


async def test_mandar_no_lee_la_base() -> None:
    contactos, plantillas, canal = _Contactos(CONTACTO), _Plantillas(), _Canal()
    envio = _envio(contactos=contactos, plantillas=plantillas, canal=canal)
    preparado = await _preparar(envio, _cobro())
    assert isinstance(preparado, MensajeListo)
    lecturas = (contactos.lecturas, plantillas.lecturas)

    resultado = await envio.mandar(preparado)

    assert resultado == ResultadoDeEnvio(estado=EstadoEntrega.ENVIADO, externo_id="wamid.OK")
    assert (contactos.lecturas, plantillas.lecturas) == lecturas
    assert len(canal.mandados) == 1


async def test_mandar_traduce_la_falla_del_canal_sin_levantar() -> None:
    envio = _envio(canal=_Canal(FallaDelCanal("SATURADA", transitoria=True)))
    preparado = await _preparar(envio, _cobro())
    assert isinstance(preparado, MensajeListo)

    resultado = await envio.mandar(preparado)

    assert (resultado.estado, resultado.codigo, resultado.transitoria) == (
        EstadoEntrega.FALLIDO,
        "SATURADA",
        True,
    )


async def test_un_error_de_base_al_preparar_no_se_traga() -> None:
    """Tragarlo dejaría la transacción abortada: el savepoint de la reserva tiene que verlo."""
    falla = OperationalError("SELECT", {}, Exception("conexión perdida"))
    envio = _envio(contactos=_Contactos(CONTACTO, falla=falla))

    with pytest.raises(OperationalError):
        await _preparar(envio, _cobro())


async def test_cualquier_otro_error_al_preparar_es_un_envio_fallido() -> None:
    envio = _envio(contactos=_Contactos(CONTACTO, falla=RuntimeError("Rosa Diaz 5491155550000")))

    resultado = await _preparar(envio, _cobro())

    assert isinstance(resultado, ResultadoDeEnvio)
    assert (resultado.estado, resultado.codigo) == (EstadoEntrega.FALLIDO, "ERROR")


async def test_un_cobro_sin_contacto_se_resuelve_al_preparar_sin_llegar_al_canal() -> None:
    canal = _Canal()

    resultado = await _preparar(_envio(contactos=_Contactos(None), canal=canal), _cobro())

    assert isinstance(resultado, ResultadoDeEnvio)
    assert resultado.codigo == "SIN_TELEFONO"
    assert canal.mandados == []


async def test_el_mensaje_listo_no_muestra_datos_personales_en_su_repr() -> None:
    preparado = await _preparar(_envio(), _cobro())

    assert "5491155550000" not in repr(preparado)
    assert "Rosa" not in repr(preparado)
