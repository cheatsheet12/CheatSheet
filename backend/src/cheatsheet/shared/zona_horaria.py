"""Shared Kernel — la zona horaria de las personas que usan el sistema.

Todo instante del sistema es UTC (`shared/clock.py`). Pero un cliente que escribe «mañana a las
10» habla de la hora de Argentina, y el día calendario de ese cliente no es el de UTC: entre las
21:00 y las 24:00 locales ya es «mañana» en UTC. Quien necesite un día o una hora en el
vocabulario de la gente convierte con esta constante y no con una zona escrita a mano.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")

_UN_MICROSEGUNDO = timedelta(microseconds=1)


@dataclass(frozen=True, slots=True)
class MesCalendario:
    """Un mes calendario **de Argentina**, como el intervalo semiabierto `[inicio, fin)` en UTC.

    Un uso a las 23:30 del último día del mes es de ese mes aunque en UTC ya sea el siguiente
    (ADR-0012). Los límites salen como instantes con zona para compararlos contra `timestamptz`
    sin que la base tenga que conocer la zona.
    """

    inicio: datetime
    fin: datetime

    @classmethod
    def del_instante(cls, instante: datetime) -> MesCalendario:
        """El mes (en hora de Argentina) al que pertenece `instante`."""
        local = instante.astimezone(ZONA_ARGENTINA)
        return cls._de(local.year, local.month)

    def anterior(self) -> MesCalendario:
        """El mes calendario inmediatamente anterior (enero retrocede a diciembre del año previo)."""
        return MesCalendario.del_instante(
            self.inicio.astimezone(ZONA_ARGENTINA).replace(day=1) - _UN_MICROSEGUNDO
        )

    @classmethod
    def _de(cls, anio: int, mes: int) -> MesCalendario:
        siguiente = (anio + (mes == 12), mes % 12 + 1)
        return cls(
            inicio=datetime(anio, mes, 1, tzinfo=ZONA_ARGENTINA).astimezone(UTC),
            fin=datetime(siguiente[0], siguiente[1], 1, tzinfo=ZONA_ARGENTINA).astimezone(UTC),
        )


__all__ = ["ZONA_ARGENTINA", "MesCalendario"]
