"""Shared Kernel — time as an injected dependency.

`backend/tests/README.md` states the rule: date and time are injected, never read
from the clock inside business logic. A tax document issued at 23:58 on the last day
of a period belongs to that period, and a test must be able to stand there without
waiting for the calendar.

Every timestamp in this system is timezone-aware and in UTC. Naive datetimes are
rejected by ruff (DTZ) precisely because a naive timestamp on a `Comprobante` is a
fiscal bug waiting for the next DST change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Reloj(Protocol):
    """The port. Application services take one; they never call `datetime.now`."""

    def ahora(self) -> datetime:
        """Current instant, timezone-aware, in UTC."""
        ...


class RelojDelSistema:
    """The production adapter: the real clock."""

    def ahora(self) -> datetime:
        return datetime.now(UTC)


class RelojFijo:
    """A clock stopped at a given instant.

    It lives beside the real one rather than in the test tree because the workers and
    the migration smoke checks use it too, and a double that only tests can reach ends
    up reimplemented three times.
    """

    def __init__(self, instante: datetime) -> None:
        if instante.tzinfo is None:
            raise ValueError("RelojFijo requiere un instante con zona horaria (UTC)")
        self._instante = instante

    def ahora(self) -> datetime:
        return self._instante
