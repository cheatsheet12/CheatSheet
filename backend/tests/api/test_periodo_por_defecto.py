"""El «mes en curso» se cuenta en hora argentina, no en UTC (HU-E10-01 RN-01 y RN-06).

El reloj del sistema devuelve UTC. Entre las 21:00 y las 24:00 del ultimo dia del mes (hora
argentina) ya es el mes siguiente en UTC, justo cuando alguien mira el cierre. Los cuatro
lugares que arman el periodo por defecto —tablero, previsualizacion, generar reporte y la ruta
del contador— usan este helper, asi que un test del helper cubre los cuatro.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from cheatsheet.api.reporteria import hoy_en_la_zona_del_reporte
from cheatsheet.contexts.reporting.application.tablero import periodo_por_defecto
from cheatsheet.contexts.reporting.domain.reporte import Periodo


def test_el_31_de_marzo_a_las_2330_hora_argentina_el_periodo_por_defecto_es_marzo() -> None:
    # 23:30 en Buenos Aires son las 02:30 del 1/4 en UTC.
    ahora = datetime(2026, 4, 1, 2, 30, tzinfo=UTC)

    assert ahora.date() == date(2026, 4, 1)  # lo que hacia el codigo anterior
    assert hoy_en_la_zona_del_reporte(ahora) == date(2026, 3, 31)
    assert periodo_por_defecto(hoy_en_la_zona_del_reporte(ahora)) == Periodo.del_mes(2026, 3)


def test_pasada_la_medianoche_argentina_ya_es_abril() -> None:
    ahora = datetime(2026, 4, 1, 3, 0, tzinfo=UTC)  # 00:00 del 1/4 en Buenos Aires

    assert hoy_en_la_zona_del_reporte(ahora) == date(2026, 4, 1)


def test_a_media_tarde_coincide_con_el_dia_utc() -> None:
    ahora = datetime(2026, 3, 17, 18, 0, tzinfo=UTC)

    assert hoy_en_la_zona_del_reporte(ahora) == date(2026, 3, 17)
