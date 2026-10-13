"""Periodic intervals anchored to the wall clock.

Neon suspends a project's compute after five idle minutes, and the free plan meters the
hours it is awake. A Celery `timedelta` schedule counts from Beat's boot, so every task
wakes the database at its own offset and it never gets to sleep. A `crontab` anchored at
minute 0 fires every task at the same instants, so the database wakes once per period.

The rule is deterministic and never rounds. An interval is accepted only when it tiles
the hour or the day exactly, because rounding 45 minutes to 30 or 60 would silently change
how often a billing sweep runs:

- N minutes, 1 <= N < 60 and N divides 60  -> every N minutes (`*/N`)
- N a multiple of 60, H = N / 60 divides 24  -> minute 0, every H hours (`*/H`)
- 1440 (one day)                             -> 00:00
- anything else                              -> `IntervaloNoAlineable`

Valid: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60, 120, 180, 240, 360, 480, 720, 1440.
"""

from __future__ import annotations

MINUTOS_POR_HORA = 60
HORAS_POR_DIA = 24


class IntervaloNoAlineable(ValueError):
    """The interval does not tile the hour or the day, so it cannot be anchored."""


def campos_alineados(minutos: int) -> tuple[str, str]:
    """Return the crontab `(minute, hour)` fields for an interval in minutes."""
    if minutos >= 1:
        if minutos < MINUTOS_POR_HORA and MINUTOS_POR_HORA % minutos == 0:
            return ("*" if minutos == 1 else f"*/{minutos}", "*")
        horas, resto = divmod(minutos, MINUTOS_POR_HORA)
        if resto == 0 and horas <= HORAS_POR_DIA and HORAS_POR_DIA % horas == 0:
            if horas == 1:
                return ("0", "*")
            return ("0", "0" if horas == HORAS_POR_DIA else f"*/{horas}")
    raise IntervaloNoAlineable(
        f"{minutos} minutes does not divide an hour or a day exactly; "
        "use 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60, 120, 180, 240, 360, 480, 720 or 1440"
    )
