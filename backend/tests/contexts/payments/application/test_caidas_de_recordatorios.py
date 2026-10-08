"""Las caídas del proceso durante un envío de recordatorio no reenvían nada (U7, tramo ii, D-U7-3).

Caso 4 y las ventanas de caída de `reintentos.py`: sin intentar, en curso dentro y fuera de su
ventana, resultado que la base no guarda y reserva que la base no confirma. En todos, lo que pudo
haber salido **no se manda otra vez**.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.domain.recordatorio import (
    INCIERTO,
    VENTANA_DE_ENVIO,
    EstadoEntrega,
    Recordatorio,
)
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from cheatsheet.shared.transaccion import DespachoNoPersistido

from tests.contexts.payments.application.dobles_de_reintento import (
    BARRIDO_1,
    RecordatoriosConBitacora,
    _con_un_cobro,
    _escenario,
    enviado,
)
from tests.contexts.payments.application.test_cobros_y_recordatorios import (
    TransaccionFalsa,
    _cobro,
)

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------ caso 4 y las caídas del proceso


async def test_una_fila_sin_intentar_no_traba_la_cadena_del_cobro() -> None:
    """Caso 4: una fila con `enviado_en` nulo y ningún intento empezado se manda; no queda trabada.

    Es seguro: si el intento nunca empezó, nada pudo haber salido.
    """
    escenario, cobro = await _con_un_cobro(enviado("wamid-3"))
    huerfana = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
    escenario.recordatorios.guardados.append(huerfana)

    await escenario.barrer(BARRIDO_1)

    fila = escenario.fila  # la misma fila, ningún `INSERT` nuevo
    assert escenario.envio.llamadas == 1
    assert fila.id == huerfana.id
    assert (fila.intentos, fila.externo_id) == (1, "wamid-3")
    assert fila.enviado_en == BARRIDO_1


async def test_un_envio_en_curso_dentro_de_su_ventana_no_se_toca() -> None:
    """Otro barrido lo está mandando: el nuestro ni lo reenvía ni lo da por perdido."""
    escenario, cobro = await _con_un_cobro(enviado())
    en_curso = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
    en_curso.iniciar_intento(BARRIDO_1)
    escenario.recordatorios.guardados.append(en_curso)

    await escenario.barrer(BARRIDO_1 + timedelta(minutes=5))

    assert escenario.envio.llamadas == 0
    assert escenario.fila.enviado_en is None
    assert escenario.fila.intentos == 1


async def test_un_envio_en_curso_con_la_ventana_vencida_se_resuelve_incierto_sin_reenviar() -> None:
    """El proceso murió a mitad del envío: Meta pudo haberlo aceptado. Nunca se reenvía."""
    escenario, cobro = await _con_un_cobro(enviado())
    perdida = Recordatorio(id=uuid4(), cobro_id=cobro.id, paso=1, canal="WHATSAPP")
    perdida.iniciar_intento(BARRIDO_1)
    escenario.recordatorios.guardados.append(perdida)

    resultado = await escenario.barrer(BARRIDO_1 + VENTANA_DE_ENVIO + timedelta(minutes=1))

    fila = escenario.fila
    assert escenario.envio.llamadas == 0
    assert (fila.estado_entrega, fila.ultimo_error) == (EstadoEntrega.FALLIDO, INCIERTO)
    assert fila.enviado_en is not None
    assert resultado.fallidos == 1
    resultados = [
        e.resultado
        for e in escenario.publicador.eventos
        if isinstance(e, EventoAuditable) and e.accion == "enviar_recordatorio"
    ]
    assert resultados == [Resultado.ERROR]


async def test_si_no_se_puede_guardar_el_resultado_la_fila_queda_en_curso_y_no_se_reenvia() -> None:
    """Meta aceptó y la base rechazó el resultado: la fila sigue «en curso» y se resuelve incierta
    cuando venza su ventana. Nunca se manda dos veces."""

    class SinGuardar(RecordatoriosConBitacora):
        async def guardar(self, recordatorio: Recordatorio) -> None:
            del recordatorio
            raise DespachoNoPersistido("la base rechazó el guardado")

    transaccion = TransaccionFalsa()
    escenario = _escenario(
        enviado("wamid-4"), recordatorios=SinGuardar(transaccion), transaccion=transaccion
    )
    await escenario.cobros.agregar(_cobro(vence_en_dias=0))

    primero = await escenario.barrer(BARRIDO_1)
    await escenario.barrer(BARRIDO_1 + timedelta(minutes=5))
    # Con la ventana vencida el resultado se resuelve incierto: guardarlo también falla, y aun así
    # no hay segundo envío.
    await escenario.barrer(BARRIDO_1 + timedelta(hours=2))

    assert escenario.envio.llamadas == 1
    assert (primero.procesados, primero.fallidos) == (0, 0)
    assert escenario.fila.enviado_en is None


async def test_si_no_se_puede_confirmar_la_fila_no_se_manda_nada() -> None:
    class ConfirmacionRota(TransaccionFalsa):
        async def confirmar(self) -> None:
            raise DespachoNoPersistido("la base rechazó el commit")

    escenario = _escenario(transaccion=ConfirmacionRota())
    await escenario.cobros.agregar(_cobro(vence_en_dias=0))

    resultado = await escenario.barrer(BARRIDO_1)

    # Sin la fila confirmada no hay E/S: nada pudo salir sin dejar registro.
    assert escenario.envio.llamadas == 0
    assert resultado.procesados == 0


async def test_el_log_de_una_reserva_que_la_base_rechaza_no_lleva_datos_personales() -> None:
    from structlog.testing import capture_logs

    class NoAgrega(RecordatoriosConBitacora):
        async def agregar(self, recordatorio: Recordatorio) -> None:
            del recordatorio
            raise DespachoNoPersistido("la base rechazó la fila de Ana Diaz")

    transaccion = TransaccionFalsa()
    escenario = _escenario(recordatorios=NoAgrega(transaccion), transaccion=transaccion)
    cobro = _cobro(vence_en_dias=0)
    await escenario.cobros.agregar(cobro)

    with capture_logs() as registros:
        await escenario.barrer(BARRIDO_1)

    eventos = [r for r in registros if r["event"] == "recordatorio_no_persistido"]
    assert len(eventos) == 1
    assert eventos[0]["cobro_id"] == str(cobro.id)
    assert escenario.envio.llamadas == 0
    assert "Ana Diaz" not in repr(registros)
