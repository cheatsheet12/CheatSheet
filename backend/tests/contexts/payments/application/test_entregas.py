"""`RegistrarEntregaDeRecordatorio`: lo que Meta dice de un recordatorio de cobro (U7, caso 2).

El callback `statuses[]` encuentra el recordatorio por el `wamid` que se guardó al enviarlo, lo
mueve sin retroceder y es idempotente. El paso a `FALLIDO` deja un evento en la bitácora.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.application.entregas import RegistrarEntregaDeRecordatorio
from cheatsheet.contexts.payments.domain.recordatorio import EstadoEntrega, Recordatorio
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.payments.application.test_cobros_y_recordatorios import RecordatoriosFalsos
from tests.contexts.payments.application.test_confirmacion import PublicadorFalso

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


async def _con_un_recordatorio(
    externo_id: str | None = "wamid-1",
) -> tuple[RecordatoriosFalsos, Recordatorio, PublicadorFalso]:
    recordatorios = RecordatoriosFalsos()
    recordatorio = Recordatorio(id=uuid4(), cobro_id=uuid4(), paso=1, canal="WHATSAPP")
    recordatorio.marcar_enviado(AHORA, externo_id=externo_id)
    await recordatorios.agregar(recordatorio)
    return recordatorios, recordatorio, PublicadorFalso()


def _caso(
    recordatorios: RecordatoriosFalsos, publicador: PublicadorFalso
) -> RegistrarEntregaDeRecordatorio:
    return RegistrarEntregaDeRecordatorio(recordatorios=recordatorios, publicador=publicador)


async def test_un_read_del_wamid_de_un_recordatorio_lo_deja_leido() -> None:
    recordatorios, recordatorio, publicador = await _con_un_recordatorio()

    encontrado = await _caso(recordatorios, publicador).ejecutar(
        empresa_id=EMPRESA, externo_id="wamid-1", estado=EstadoEntrega.LEIDO, ahora=AHORA
    )

    assert encontrado is True
    assert recordatorio.estado_entrega is EstadoEntrega.LEIDO
    assert publicador.eventos == []  # un callback no deja bitácora (serían tres por mensaje)


async def test_un_wamid_desconocido_devuelve_falso() -> None:
    recordatorios, recordatorio, publicador = await _con_un_recordatorio()

    encontrado = await _caso(recordatorios, publicador).ejecutar(
        empresa_id=EMPRESA, externo_id="otro", estado=EstadoEntrega.LEIDO, ahora=AHORA
    )

    assert encontrado is False
    assert recordatorio.estado_entrega is EstadoEntrega.ENVIADO


async def test_delivered_despues_de_read_no_retrocede() -> None:
    recordatorios, recordatorio, publicador = await _con_un_recordatorio()
    caso = _caso(recordatorios, publicador)

    await caso.ejecutar(
        empresa_id=EMPRESA, externo_id="wamid-1", estado=EstadoEntrega.LEIDO, ahora=AHORA
    )
    await caso.ejecutar(
        empresa_id=EMPRESA, externo_id="wamid-1", estado=EstadoEntrega.ENTREGADO, ahora=AHORA
    )

    assert recordatorio.estado_entrega is EstadoEntrega.LEIDO


async def test_failed_guarda_el_codigo_y_publica_un_solo_evento_aunque_el_callback_se_repita() -> (
    None
):
    recordatorios, recordatorio, publicador = await _con_un_recordatorio()
    caso = _caso(recordatorios, publicador)

    for _ in range(2):
        await caso.ejecutar(
            empresa_id=EMPRESA,
            externo_id="wamid-1",
            estado=EstadoEntrega.FALLIDO,
            codigo_de_error="131047",
            ahora=AHORA,
        )
    await caso.ejecutar(
        empresa_id=EMPRESA, externo_id="wamid-1", estado=EstadoEntrega.LEIDO, ahora=AHORA
    )

    assert recordatorio.estado_entrega is EstadoEntrega.FALLIDO
    assert recordatorio.ultimo_error == "131047"
    (evento,) = publicador.eventos
    assert isinstance(evento, EventoAuditable)
    assert evento.accion == "recordatorio_fallido"
    assert evento.entidad_afectada == f"Cobro:{recordatorio.cobro_id}"
    assert evento.resultado is Resultado.ERROR
    assert evento.empresa_id == EMPRESA


async def test_el_callback_pide_el_recordatorio_bloqueado_para_no_pisar_a_otro_callback() -> None:
    """H2: dos callbacks del mismo `wamid` en paralelo se serializan en la base (ver el de mensajes)."""
    recordatorios, _, publicador = await _con_un_recordatorio()

    await _caso(recordatorios, publicador).ejecutar(
        empresa_id=EMPRESA, externo_id="wamid-1", estado=EstadoEntrega.ENTREGADO, ahora=AHORA
    )

    assert recordatorios.busquedas_por_externo_id == [True]
