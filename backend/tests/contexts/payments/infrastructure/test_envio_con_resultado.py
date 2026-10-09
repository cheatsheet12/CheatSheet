"""`EnvioPorWhatsApp` devuelve el `wamid` y el motivo del fallo (U7, ADR-0011 punto 8).

El `wamid` es lo que permite que un callback `statuses[]` encuentre su recordatorio; el motivo es
lo que PAN-COB-02 explica cuando un paso queda `FALLIDO`. El adaptador no importa a
`conversational` (R3): la clase del fallo le llega traducida en `FallaDelCanal`.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.application.ports_de_recordatorios import ResultadoDeEnvio
from cheatsheet.contexts.payments.application.ports_envio import ContactoDeCobro, FallaDelCanal
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.contexts.payments.infrastructure.envio import (
    CODIGO_RECORDATORIO,
    EnvioPorWhatsApp,
    PlantillaParaMandar,
)
from cheatsheet.shared.empresa import EmpresaId

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
CONTACTO = ContactoDeCobro(nombre="Rosa Diaz", telefono="5491155550000")


def _cobro() -> Cobro:
    return Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta",
        vence_el=AHORA,
        created_at=AHORA,
    )


class Contactos:
    def __init__(self, contacto: ContactoDeCobro | None = CONTACTO) -> None:
        self._contacto = contacto

    async def contacto_de(self, cliente_id: UUID) -> ContactoDeCobro | None:
        del cliente_id
        return self._contacto


class Canal:
    def __init__(self, *, falla: Exception | None = None) -> None:
        self._falla = falla

    async def enviar(self, *, telefono: str, texto: str) -> str:
        del telefono, texto
        if self._falla is not None:
            raise self._falla
        return "wamid.TEXTO"

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        return "wamid.PLANTILLA"


class _Plantilla:
    nombre_en_meta = "recordatorio_de_cobro"
    idioma = "es_AR"
    parametros: Mapping[str, str] = {"nombre": "Rosa"}


class SinPlantillas:
    async def para(self, codigo: str, variables: object) -> PlantillaParaMandar | None:
        del codigo, variables
        return None


class ConPlantilla:
    async def para(self, codigo: str, variables: object) -> PlantillaParaMandar | None:
        assert codigo == CODIGO_RECORDATORIO
        del variables
        return _Plantilla()


async def _enviar(envio: EnvioPorWhatsApp, canal: str = "WHATSAPP") -> ResultadoDeEnvio:
    return await envio.enviar(empresa_id=EMPRESA, cobro=_cobro(), canal=canal, paso=1)


async def test_un_texto_enviado_devuelve_el_wamid_del_canal() -> None:
    resultado = await _enviar(EnvioPorWhatsApp(Canal(), Contactos(), SinPlantillas()))

    assert resultado == ResultadoDeEnvio(estado=EstadoEntrega.ENVIADO, externo_id="wamid.TEXTO")


async def test_una_plantilla_enviada_devuelve_el_wamid_del_canal() -> None:
    resultado = await _enviar(EnvioPorWhatsApp(Canal(), Contactos(), ConPlantilla()))

    assert resultado.externo_id == "wamid.PLANTILLA"
    assert resultado.estado is EstadoEntrega.ENVIADO


async def test_la_falla_traducida_del_canal_deja_su_codigo() -> None:
    envio = EnvioPorWhatsApp(Canal(falla=FallaDelCanal("131047")), Contactos(), SinPlantillas())

    resultado = await _enviar(envio)

    assert resultado == ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="131047")


async def test_una_excepcion_cualquiera_deja_el_codigo_error_y_nunca_su_texto() -> None:
    envio = EnvioPorWhatsApp(
        Canal(falla=RuntimeError("fallo con 5491155550000")), Contactos(), SinPlantillas()
    )

    resultado = await _enviar(envio)

    assert resultado.estado is EstadoEntrega.FALLIDO
    assert resultado.codigo == "ERROR"
    assert "5491155550000" not in repr(resultado)


async def test_un_cliente_sin_telefono_deja_el_codigo_sin_telefono() -> None:
    resultado = await _enviar(EnvioPorWhatsApp(Canal(), Contactos(None), SinPlantillas()))

    assert resultado == ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="SIN_TELEFONO")


async def test_un_canal_sin_adaptador_deja_su_codigo() -> None:
    resultado = await _enviar(EnvioPorWhatsApp(Canal(), Contactos(), SinPlantillas()), "EMAIL")

    assert resultado == ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="CANAL_NO_SOPORTADO")
