"""`MesCalendario`: el mes en hora de Argentina, y sus límites como instantes UTC."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA, MesCalendario

ART = timezone(timedelta(hours=-3))


class TestMesCalendario:
    def test_el_ultimo_tramo_del_mes_argentino_no_pasa_al_mes_siguiente(self) -> None:
        """31/10 23:30 en Argentina es 01/11 02:30 UTC, pero sigue siendo octubre."""
        mes = MesCalendario.del_instante(datetime(2026, 10, 31, 23, 30, tzinfo=ART))

        assert mes.inicio == datetime(2026, 10, 1, 3, 0, tzinfo=UTC)
        assert mes.fin == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)

        mismo_en_utc = MesCalendario.del_instante(datetime(2026, 11, 1, 2, 30, tzinfo=UTC))
        assert mismo_en_utc == mes

    def test_el_borde_exacto_pertenece_al_mes_que_empieza(self) -> None:
        noviembre = MesCalendario.del_instante(datetime(2026, 11, 1, 0, 0, tzinfo=ART))
        octubre = MesCalendario.del_instante(datetime(2026, 10, 31, 23, 59, 59, 999999, tzinfo=ART))

        assert noviembre.inicio == datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
        assert octubre.fin == noviembre.inicio

    def test_el_mes_anterior_de_enero_es_diciembre_del_anio_anterior(self) -> None:
        enero = MesCalendario.del_instante(datetime(2027, 1, 15, 12, 0, tzinfo=ART))

        diciembre = enero.anterior()

        assert diciembre.inicio == datetime(2026, 12, 1, 3, 0, tzinfo=UTC)
        assert diciembre.fin == enero.inicio

    def test_los_limites_son_instantes_con_zona(self) -> None:
        mes = MesCalendario.del_instante(datetime(2026, 3, 10, 12, 0, tzinfo=UTC))

        assert mes.inicio.tzinfo is not None and mes.fin.tzinfo is not None
        assert mes.inicio.astimezone(ZONA_ARGENTINA).day == 1
