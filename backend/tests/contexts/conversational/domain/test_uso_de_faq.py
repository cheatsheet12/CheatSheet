"""El uso de una FAQ: conteos, ventana de comparación y participación (ADR-0012)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from cheatsheet.contexts.conversational.domain.uso_de_faq import (
    ConteoDeUsos,
    MotivoSinComparacion,
    Participacion,
    VentanaDeComparacion,
    ventana_de_comparacion,
)

AHORA = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)


class TestVentanaDeComparacion:
    def test_sin_edicion_no_hay_con_que_comparar(self) -> None:
        resultado = ventana_de_comparacion(
            editada_en=None, seguimiento_desde=AHORA - timedelta(days=40), ahora=AHORA
        )

        assert resultado is MotivoSinComparacion.SIN_EDICIONES

    def test_editada_hace_menos_de_un_dia_es_reciente(self) -> None:
        resultado = ventana_de_comparacion(
            editada_en=AHORA - timedelta(hours=10),
            seguimiento_desde=AHORA - timedelta(days=40),
            ahora=AHORA,
        )

        assert resultado is MotivoSinComparacion.EDICION_RECIENTE

    def test_editada_en_el_primer_dia_seguido_no_tiene_historia_previa(self) -> None:
        seguimiento = AHORA - timedelta(days=10)

        resultado = ventana_de_comparacion(
            editada_en=seguimiento + timedelta(hours=6), seguimiento_desde=seguimiento, ahora=AHORA
        )

        assert resultado is MotivoSinComparacion.SIN_HISTORIA_PREVIA

    def test_la_ventana_es_la_menor_entre_treinta_dias_la_edicion_y_la_historia(self) -> None:
        casos = [
            (timedelta(days=10), timedelta(days=40), 10),  # manda el tiempo desde la edicion
            (timedelta(days=50), timedelta(days=90), 30),  # manda el maximo
            (timedelta(days=10), timedelta(days=13), 3),  # manda la historia previa
        ]
        for desde_la_edicion, desde_el_seguimiento, esperados in casos:
            editada = AHORA - desde_la_edicion
            resultado = ventana_de_comparacion(
                editada_en=editada, seguimiento_desde=AHORA - desde_el_seguimiento, ahora=AHORA
            )

            assert isinstance(resultado, VentanaDeComparacion)
            assert resultado.dias == esperados
            largo = timedelta(days=esperados)
            assert (resultado.antes.desde, resultado.antes.hasta) == (editada - largo, editada)
            assert (resultado.despues.desde, resultado.despues.hasta) == (editada, editada + largo)


class TestParticipacion:
    def test_porcentaje_con_un_decimal_y_half_up(self) -> None:
        assert Participacion(usos=1, total=3).porcentaje == Decimal("33.3")
        assert Participacion(usos=1, total=6).porcentaje == Decimal("16.7")
        assert Participacion(usos=0, total=5).porcentaje == Decimal("0.0")

    def test_sin_consultas_no_hay_porcentaje(self) -> None:
        assert Participacion(usos=0, total=0).porcentaje is None


class TestConteoDeUsos:
    def test_el_total_suma_la_linea_de_base(self) -> None:
        conteo = ConteoDeUsos(este_mes=3, mes_anterior=1, desde_el_seguimiento=3)

        assert conteo.total(usos_anteriores=47) == 50
