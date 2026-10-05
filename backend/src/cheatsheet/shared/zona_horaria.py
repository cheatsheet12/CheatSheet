"""Shared Kernel — la zona horaria de las personas que usan el sistema.

Todo instante del sistema es UTC (`shared/clock.py`). Pero un cliente que escribe «mañana a las
10» habla de la hora de Argentina, y el día calendario de ese cliente no es el de UTC: entre las
21:00 y las 24:00 locales ya es «mañana» en UTC. Quien necesite un día o una hora en el
vocabulario de la gente convierte con esta constante y no con una zona escrita a mano.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")

__all__ = ["ZONA_ARGENTINA"]
