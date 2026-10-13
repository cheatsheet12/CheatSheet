"""El rango de la agenda con una sola fecha es ese día, no «desde hoy» (#85, HU-E7-01 RN-01).

`_rango` completaba la punta que faltaba con el día en curso: solo «desde» = 14/10 daba el rango
invertido `[14/10, mañana)` y la agenda quedaba vacía; solo «hasta» arrancaba en hoy. Ahora la
punta que falta se completa a partir de la que llegó (Gate 1, opción A: una sola fecha es ese
día completo), y una fecha sin zona se lee en la zona de la agenda, no en UTC.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from cheatsheet.api.routers.agenda_turnos import _rango
from cheatsheet.contexts.scheduling.domain.recurso import ZONA_DE_LA_AGENDA

HOY = date(2026, 10, 12)


def _local(dia: int, hora: int = 0) -> datetime:
    return datetime(2026, 10, dia, hora, tzinfo=ZONA_DE_LA_AGENDA)


def test_solo_desde_es_ese_dia_completo_y_no_un_rango_invertido() -> None:
    inicio, fin = _rango(_local(14), None, HOY)

    assert (inicio, fin) == (_local(14), _local(15))
    assert inicio < fin


def test_solo_hasta_es_el_dia_que_termina_ahi_y_no_arranca_en_hoy() -> None:
    inicio, fin = _rango(None, _local(15), HOY)

    assert (inicio, fin) == (_local(14), _local(15))


def test_una_fecha_sin_zona_se_lee_en_la_zona_de_la_agenda() -> None:
    # Lo que FastAPI arma con `?desde=2026-10-14`: medianoche sin zona.
    sin_zona = datetime.fromisoformat("2026-10-14T00:00:00")
    assert sin_zona.tzinfo is None
    inicio, fin = _rango(sin_zona, None, HOY)

    assert (inicio, fin) == (_local(14), _local(15))
    # Un turno a las 22:00 del 14 en Buenos Aires ya es el 15 en UTC, y entra igual (D34).
    turno_nocturno = _local(14, 22)
    assert turno_nocturno.astimezone(UTC).date() == date(2026, 10, 15)
    assert inicio <= turno_nocturno < fin


def test_sin_fechas_sigue_siendo_el_dia_en_curso() -> None:
    assert _rango(None, None, HOY) == (_local(12), _local(13))


def test_con_las_dos_fechas_se_usan_tal_cual() -> None:
    desde = datetime(2026, 10, 12, 3, tzinfo=UTC)
    hasta = desde + timedelta(days=7)

    assert _rango(desde, hasta, HOY) == (desde, hasta)
