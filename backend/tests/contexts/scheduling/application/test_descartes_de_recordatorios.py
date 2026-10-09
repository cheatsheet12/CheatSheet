"""Los descartes y el registro del resultado bajo concurrencia (U8, tramo 3, Gate 2).

Lo que se fija acá:

1. **Un barrido lento no pisa a otro.** La fase 3 relee la fila bloqueada y escribe solo si sigue
   «en curso» con el mismo intento que este barrido reservó; si no, descarta su resultado (nunca
   reenvía).
2. **Un reintento lejano no sale después de uno cercano**: si ya hay una fila de una anticipación más
   cercana del mismo turno, la pendiente se descarta `ANTICIPACION_SUPERADA`.
3. **Una anticipación quitada de la agenda** descarta lo que esperaba reintento.
4. Todo descarte deja un log estructurado y el evento de bitácora, sin datos personales.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta

import pytest
import structlog
from cheatsheet.contexts.scheduling.application import (
    envio_de_recordatorios,
    registro_de_recordatorios,
)
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    AGENDA_APAGADA,
    ANTICIPACION_QUITADA,
    ANTICIPACION_SUPERADA,
    INCIERTO,
    VENTANA_DE_ENVIO,
    ResultadoDeRecordatorio,
)
from cheatsheet.shared.auditoria import EventoAuditable, Resultado
from structlog.testing import capture_logs

from tests.contexts.scheduling.application.dobles_de_recordatorios import (
    INICIO,
    VENTANA_DE_24H,
    AgendaFalsa,
    Escenario,
    escenario,
    transitoria,
    turno,
)
from tests.logs import logger_nuevo

pytestmark = pytest.mark.asyncio

QUINCE_MIN = timedelta(minutes=15)


@pytest.fixture(autouse=True)
def _logger(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Un logger nuevo y **sin filtro de nivel**: otro test pudo dejar la configuración en WARNING."""
    anterior = structlog.get_config()["wrapper_class"]
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(0))
    for modulo in (registro_de_recordatorios, envio_de_recordatorios):
        logger_nuevo(monkeypatch, modulo)
    yield
    structlog.configure(wrapper_class=anterior)


def _resolverla_otro_barrido(e: Escenario) -> None:
    """Otro barrido vio la ventana vencida y resolvió la fila `FALLIDO` `INCIERTO`."""
    fila = e.fila
    e.recordatorios.filas[fila.id] = replace(
        fila,
        resultado=ResultadoDeRecordatorio.FALLIDO,
        ultimo_error=INCIERTO,
        proximo_intento_en=None,
        procesado_en=VENTANA_DE_24H + VENTANA_DE_ENVIO,
    )


class TestElResultadoNoPisaAOtroBarrido:
    async def test_un_barrido_lento_no_pisa_el_incierto_de_otro(self) -> None:
        e = escenario()
        e.turnos.agregar(turno())
        e.envio._al_enviar = lambda: _resolverla_otro_barrido(e)

        with capture_logs() as logs:
            resultado = await e.barrer()

        assert not resultado.hubo_actividad
        assert e.fila.resultado is ResultadoDeRecordatorio.FALLIDO
        assert e.fila.ultimo_error == INCIERTO
        assert e.publicador.eventos == []
        assert [u["event"] for u in logs if "resultado_descartado" in u["event"]] == [
            "recordatorio_de_turno_resultado_descartado"
        ]
        assert len(e.envio.enviados) == 1

    async def test_un_barrido_lento_no_pisa_un_reintento_que_otro_ya_retomo(self) -> None:
        e = escenario()
        e.turnos.agregar(turno())

        def otro_la_retomo() -> None:
            fila = e.fila
            e.recordatorios.filas[fila.id] = replace(fila, intentos=fila.intentos + 1)

        e.envio._al_enviar = otro_la_retomo

        resultado = await e.barrer()

        assert not resultado.hubo_actividad
        assert e.fila.resultado is None
        assert e.fila.intentos == 2
        assert e.publicador.eventos == []


class TestUnReintentoLejanoNoSaleDespuesDeUnoCercano:
    async def _con_el_de_24h_esperando(self) -> Escenario:
        e = escenario(transitoria(), agenda=AgendaFalsa(24, 2))
        e.turnos.agregar(turno())
        await e.barrer(INICIO - timedelta(hours=2, minutes=10))  # 24 h falla y espera 15 min
        assert e.fila.esperando_reintento
        return e

    async def test_la_pendiente_de_24h_se_descarta_si_ya_hay_una_de_2h(self) -> None:
        e = await self._con_el_de_24h_esperando()
        # A las 2 h exactas la de 24 h todavía espera (hasta 1:55 h antes): sale la de 2 h.
        await e.barrer(INICIO - timedelta(hours=2))
        assert len(e.envio.enviados) == 2

        resultado = await e.barrer(INICIO - timedelta(hours=1, minutes=55))

        assert resultado.descartados == 1
        assert len(e.envio.enviados) == 2  # el reintento de 24 h no sale
        veinticuatro = next(f for f in e.recordatorios.filas.values() if f.anticipacion_min == 1440)
        assert veinticuatro.resultado is ResultadoDeRecordatorio.DESCARTADO
        assert veinticuatro.ultimo_error == ANTICIPACION_SUPERADA

    async def test_sin_una_fila_mas_cercana_el_reintento_sigue_su_curso(self) -> None:
        e = await self._con_el_de_24h_esperando()

        resultado = await e.barrer(INICIO - timedelta(hours=2, minutes=10) + QUINCE_MIN)

        assert resultado.enviados == 1
        assert len(e.envio.enviados) == 2


class TestUnaAnticipacionQuitadaDeLaAgenda:
    async def test_lo_que_esperaba_reintento_se_descarta(self) -> None:
        e = escenario(transitoria(), agenda=AgendaFalsa(24))
        e.turnos.agregar(turno())
        await e.barrer()
        assert e.fila.esperando_reintento
        e.barrido._agenda = AgendaFalsa(2)  # la empresa quitó las 24 h y dejó las 2 h

        resultado = await e.barrer(VENTANA_DE_24H + QUINCE_MIN)

        assert resultado.descartados == 1
        assert len(e.envio.enviados) == 1
        assert e.fila.resultado is ResultadoDeRecordatorio.DESCARTADO
        assert e.fila.ultimo_error == ANTICIPACION_QUITADA


class TestTodoDescarteSeRegistra:
    async def test_agenda_apagada_deja_log_y_evento_sin_datos_personales(self) -> None:
        e = escenario(transitoria(), agenda=AgendaFalsa(24))
        e.turnos.agregar(turno())
        await e.barrer()
        e.barrido._agenda = AgendaFalsa(apagada=True)

        with capture_logs() as logs:
            resultado = await e.barrer(VENTANA_DE_24H + QUINCE_MIN)

        assert resultado.descartados == 1
        assert e.fila.ultimo_error == AGENDA_APAGADA
        (registro,) = [u for u in logs if u["event"] == "recordatorio_de_turno_descartado"]
        assert registro["motivo"] == AGENDA_APAGADA
        assert registro["turno_id"] == str(e.fila.turno_id)
        assert registro["anticipacion_min"] == 24 * 60
        assert set(registro) <= {"event", "log_level", "turno_id", "anticipacion_min", "motivo"}
        (evento,) = e.publicador.eventos
        assert isinstance(evento, EventoAuditable)
        assert evento.resultado is Resultado.COMPLETADO
        assert evento.detalle == {"motivo": AGENDA_APAGADA}
        assert evento.entidad_afectada == f"Turno:{e.fila.turno_id}"
        assert evento.usuario_id is None
