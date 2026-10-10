"""`EnviarRecordatoriosDeTurno` — el barrido (HU-E8-04, HU-E11-01; unidad `recordatorio-de-turno`).

Qué corresponde mandar y qué no, visto desde el barrido (casos 1, 9, 18 a 21, 36):

1. Un turno dentro de la ventana de su anticipación recibe **un** recordatorio, una sola vez.
2. Reprogramar genera uno nuevo para la franja nueva; cancelar, completar o marcar no-show, nunca.
3. Con varias anticipaciones vencidas a la vez sale solo la más cercana; las otras quedan `OMITIDO` con
   `ANTICIPACION_SUPERADA`.
4. Una regla de agenda malformada saltea esa empresa con un log sin datos personales; una apagada
   no manda nada.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from cheatsheet.contexts.scheduling.application import recordatorios
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import (
    ANTICIPACION_SUPERADA,
    SIN_TELEFONO,
    ResultadoDeRecordatorio,
)
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Franja
from cheatsheet.shared.errors import EntradaInvalida
from structlog.testing import capture_logs

from tests.contexts.scheduling.application.dobles_de_recordatorios import (
    EMPRESA,
    INICIO,
    VENTANA_DE_24H,
    AgendaFalsa,
    H,
    agenda_invalida,
    escenario,
    transitoria,
    turno,
)
from tests.logs import logger_nuevo

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _logger(monkeypatch: pytest.MonkeyPatch) -> None:
    logger_nuevo(monkeypatch, recordatorios)


class TestUnTurnoDentroDeLaVentana:
    async def test_recibe_un_recordatorio_y_queda_enviado(self) -> None:
        """**Caso 1.** Un turno a 23 h, con la regla por defecto, recibe el recordatorio."""
        e = escenario()
        e.turnos.agregar(turno())

        resultado = await e.barrer()

        assert resultado.enviados == 1
        assert len(e.envio.enviados) == 1
        assert e.fila.resultado is ResultadoDeRecordatorio.ENVIADO
        assert e.fila.anticipacion_min == 24 * H

    async def test_un_segundo_barrido_no_lo_repite(self) -> None:
        e = escenario()
        e.turnos.agregar(turno())
        await e.barrer()

        segundo = await e.barrer(VENTANA_DE_24H + timedelta(minutes=15))

        assert not segundo.hubo_actividad
        assert len(e.envio.enviados) == 1

    async def test_antes_de_su_momento_no_se_manda_nada(self) -> None:
        e = escenario()
        e.turnos.agregar(turno())

        resultado = await e.barrer(INICIO - timedelta(hours=25))

        assert not resultado.hubo_actividad
        assert e.envio.enviados == []
        assert e.recordatorios.filas == {}

    async def test_un_turno_ya_empezado_no_se_recuerda(self) -> None:
        """**Caso 20.**"""
        e = escenario()
        e.turnos.agregar(turno())

        resultado = await e.barrer(INICIO + timedelta(minutes=1))

        assert not resultado.hubo_actividad
        assert e.envio.enviados == []

    async def test_reservado_dentro_de_la_ventana_no_recibe_un_aviso_tardio(self) -> None:
        """**Caso 10 visto desde el barrido.** `M < F`: el momento ya había pasado al reservar."""
        e = escenario()
        e.turnos.agregar(turno(franja_asignada_en=INICIO - timedelta(hours=3)))

        resultado = await e.barrer(INICIO - timedelta(hours=2))

        assert not resultado.hubo_actividad
        assert e.envio.enviados == []

    @pytest.mark.parametrize(
        "estado", [EstadoTurno.CANCELADO, EstadoTurno.COMPLETADO, EstadoTurno.NO_SHOW]
    )
    async def test_un_turno_cerrado_nunca_se_recuerda(self, estado: EstadoTurno) -> None:
        """**Casos 19 y 20.**"""
        e = escenario()
        e.turnos.agregar(turno(estado=estado))

        resultado = await e.barrer()

        assert not resultado.hubo_actividad
        assert e.envio.enviados == []
        assert e.recordatorios.filas == {}


class TestReprogramar:
    async def test_reprogramado_recibe_un_recordatorio_para_la_franja_nueva(self) -> None:
        """**Caso 18.** El de la franja vieja no cuenta: la clave incluye la franja."""
        e = escenario()
        original = turno()
        e.turnos.agregar(original)
        await e.barrer()
        nueva_franja = Franja(inicio=INICIO + timedelta(days=2), duracion_min=60)
        e.turnos.agregar(replace(original, franja=nueva_franja, franja_asignada_en=VENTANA_DE_24H))

        resultado = await e.barrer(nueva_franja.inicio - timedelta(hours=23))

        assert resultado.enviados == 1
        assert len(e.recordatorios.filas) == 2
        assert {fila.franja_inicio for fila in e.recordatorios.filas.values()} == {
            INICIO,
            nueva_franja.inicio,
        }

    async def test_la_fila_que_esperaba_un_reintento_en_la_franja_vieja_se_descarta(self) -> None:
        """**Caso 18.** Pendiente de la franja vieja → `DESCARTADO` `FRANJA_CAMBIADA`."""
        e = escenario(transitoria())
        original = turno()
        e.turnos.agregar(original)
        await e.barrer()
        e.turnos.agregar(
            replace(
                original,
                franja=Franja(inicio=INICIO + timedelta(days=2), duracion_min=60),
                franja_asignada_en=VENTANA_DE_24H,
            )
        )

        resultado = await e.barrer(VENTANA_DE_24H + timedelta(minutes=16))

        assert resultado.descartados == 1
        (vieja,) = e.recordatorios.filas.values()
        assert vieja.resultado is ResultadoDeRecordatorio.DESCARTADO
        assert vieja.ultimo_error == "FRANJA_CAMBIADA"


class TestVariasAnticipaciones:
    async def test_con_el_worker_caido_sale_solo_la_mas_cercana(self) -> None:
        """**Caso 9.** Con 48 h y 24 h y el barrido detenido hasta faltar 20 h, solo la de 24 h."""
        e = escenario(agenda=AgendaFalsa(48, 24))
        uno = turno()
        e.turnos.agregar(uno)

        resultado = await e.barrer(INICIO - timedelta(hours=20))

        assert (resultado.enviados, resultado.omitidos) == (1, 1)
        assert e.envio.enviados == [(uno.id, 24 * H)]
        por_anticipacion = {f.anticipacion_min: f for f in e.recordatorios.filas.values()}
        assert por_anticipacion[48 * H].resultado is ResultadoDeRecordatorio.OMITIDO
        assert por_anticipacion[48 * H].ultimo_error == ANTICIPACION_SUPERADA
        assert por_anticipacion[24 * H].resultado is ResultadoDeRecordatorio.ENVIADO

    async def test_una_mas_cercana_en_espera_de_reintento_supera_a_la_vieja(self) -> None:
        """La fila de 12 h espera su reintento: el barrido no manda la de 24 h detrás (D-U8-3)."""
        e = escenario(transitoria(), agenda=AgendaFalsa(24, 12))
        e.turnos.agregar(turno())
        primero = await e.barrer(INICIO - timedelta(hours=11))
        assert primero.en_reintento == 1

        segundo = await e.barrer(INICIO - timedelta(hours=11) + timedelta(minutes=5))

        assert len(e.envio.enviados) == 1
        assert segundo.enviados == 0
        anticipaciones = {f.anticipacion_min: f for f in e.recordatorios.filas.values()}
        assert anticipaciones[24 * H].ultimo_error == ANTICIPACION_SUPERADA


class TestSinTelefono:
    async def test_la_fila_nace_omitida_y_no_se_reevalua(self) -> None:
        """**Caso 21.**"""
        e = escenario(sin_telefono=True)
        e.turnos.agregar(turno())

        primero = await e.barrer()
        segundo = await e.barrer(VENTANA_DE_24H + timedelta(minutes=15))

        assert primero.omitidos == 1
        assert not segundo.hubo_actividad
        assert e.fila.resultado is ResultadoDeRecordatorio.OMITIDO
        assert e.fila.ultimo_error == SIN_TELEFONO
        assert e.envio.enviados == []
        assert e.envio.preparados == 1


class TestLaAgenda:
    async def test_apagada_no_manda_nada(self) -> None:
        """Gate 1, pregunta 1: regla desactivada → agenda vacía → recordatorios apagados."""
        e = escenario(agenda=AgendaFalsa(apagada=True))
        e.turnos.agregar(turno())

        resultado = await e.barrer()

        assert not resultado.hubo_actividad
        assert e.envio.enviados == []
        assert e.recordatorios.filas == {}

    async def test_malformada_saltea_la_empresa_con_un_log_sin_datos_personales(self) -> None:
        """**Caso 36.** No levanta, no manda, y el log lleva solo `empresa_id` y `regla_id`."""
        falla = agenda_invalida()
        e = escenario(agenda=AgendaFalsa(falla=falla))
        e.turnos.agregar(turno())

        with capture_logs() as logs:
            resultado = await e.barrer()

        assert not resultado.hubo_actividad
        assert e.envio.enviados == []
        (registro,) = [
            uno for uno in logs if uno["event"] == "recordatorios_de_turno_agenda_invalida"
        ]
        assert registro["empresa_id"] == str(EMPRESA)
        assert registro["regla_id"] == str(falla.regla_id)
        assert set(registro) <= {"event", "log_level", "empresa_id", "regla_id"}

    async def test_una_falla_de_otra_clase_no_se_traga(self) -> None:
        """Solo la agenda malformada se saltea: un error de verdad sigue siendo un error."""
        e = escenario(agenda=AgendaFalsa(falla=RuntimeError("base caída")))

        with pytest.raises(RuntimeError):
            await e.barrer()

    async def test_un_error_de_entrada_comun_tampoco_se_traga(self) -> None:
        e = escenario(agenda=AgendaFalsa(falla=EntradaInvalida("otra cosa")))

        with pytest.raises(EntradaInvalida):
            await e.barrer()
