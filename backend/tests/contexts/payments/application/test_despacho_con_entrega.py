"""El barrido guarda el `wamid` y el motivo de lo que despacha (U7, casos 2 y 8 del lado del envío).

Sin el `wamid` guardado, ningún callback `statuses[]` encuentra su recordatorio; sin el motivo,
un `FALLIDO` en PAN-COB-02 no tiene explicación.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from cheatsheet.contexts.payments.application.ports_de_recordatorios import ResultadoDeEnvio
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    AHORA,
    EMPRESA,
    CadenaFalsa,
    RecordatoriosFalsos,
    _cobro,
    _despachar,
)
from tests.contexts.payments.application.test_confirmacion import CobrosFalsos

pytestmark = pytest.mark.asyncio


class EnvioQueDevuelve:
    def __init__(self, resultado: ResultadoDeEnvio | Exception) -> None:
        self._resultado = resultado

    async def enviar(
        self, *, empresa_id: EmpresaId, cobro: Cobro, canal: str, paso: int
    ) -> ResultadoDeEnvio:
        del empresa_id, cobro, canal, paso
        if isinstance(self._resultado, Exception):
            raise self._resultado
        return self._resultado


async def _barrer(resultado: ResultadoDeEnvio | Exception) -> tuple[RecordatoriosFalsos, UUID]:
    cobros, recordatorios = CobrosFalsos(), RecordatoriosFalsos()
    cobro = _cobro(vence_en_dias=0)
    await cobros.agregar(cobro)
    await _despachar(cobros, recordatorios, EnvioQueDevuelve(resultado), CadenaFalsa()).ejecutar(
        empresa_id=EMPRESA, ahora=AHORA + timedelta(days=4)
    )
    return recordatorios, cobro.id


async def test_el_wamid_que_devolvio_el_canal_queda_en_el_recordatorio() -> None:
    recordatorios, cobro_id = await _barrer(
        ResultadoDeEnvio(estado=EstadoEntrega.ENVIADO, externo_id="wamid-77")
    )

    (guardado,) = await recordatorios.de_cobro(cobro_id)
    assert guardado.externo_id == "wamid-77"
    assert guardado.estado_entrega is EstadoEntrega.ENVIADO
    assert guardado.ultimo_error is None


async def test_un_envio_fallido_guarda_el_codigo_que_informo_el_canal() -> None:
    recordatorios, cobro_id = await _barrer(
        ResultadoDeEnvio(estado=EstadoEntrega.FALLIDO, codigo="131026")
    )

    (guardado,) = await recordatorios.de_cobro(cobro_id)
    assert guardado.estado_entrega is EstadoEntrega.FALLIDO
    assert guardado.enviado_en is not None  # la cadena sigue: el paso se dio por hecho
    assert guardado.externo_id is None
    assert guardado.ultimo_error == "131026"


async def test_un_adaptador_que_levanta_deja_el_paso_fallido_con_motivo_error() -> None:
    recordatorios, cobro_id = await _barrer(RuntimeError("no debia levantar"))

    (guardado,) = await recordatorios.de_cobro(cobro_id)
    assert guardado.estado_entrega is EstadoEntrega.FALLIDO
    assert guardado.ultimo_error == "ERROR"
