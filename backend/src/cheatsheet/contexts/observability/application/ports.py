"""Ports of the observability context.

Note what each port refuses to offer, because that is where the guarantees live.

`PortRegistroDeAuditoria` has no `actualizar` and no `eliminar`: HS-T5 RN-03 makes audit
records immutable, and the cheapest place to enforce that is the shape of the interface.
A repository that cannot express deletion cannot be talked into it by a future caller in
a hurry.

`PortRepositorioTareaAsincrona` does offer `actualizar` -- a task is execution state and
mutates on every attempt -- but still refuses `eliminar`, for its own reason: HS-T6 RN-04
keeps exhausted tasks for analysis and replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria
from cheatsheet.contexts.observability.domain.tarea_asincrona import TareaAsincrona
from cheatsheet.shared.auditoria import Modulo
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia


@dataclass(frozen=True, slots=True)
class FiltrosDeBitacora:
    """What a reader of the log may narrow it down by.

    Introduced by epic 9, which needs "how many operations happened in this period" for
    the dashboard, and reused by the audit panel of epic 10. Every field optional; absent
    means "do not filter by this".

    `limite` is not optional and is not unbounded: this table grows with every operation
    the system performs, and a read without a ceiling is the one query that takes the
    process down on the busiest company.
    """

    desde: datetime | None = None
    hasta: datetime | None = None
    modulos: tuple[Modulo, ...] = ()
    limite: int = 500


class PortRegistroDeAuditoria(Protocol):
    """Persistence of the audit log. Append and read; nothing else exists."""

    async def agregar(self, registro: RegistroDeAuditoria) -> None:
        """Persist a new record.

        Raises `RegistroDuplicado` when `evento_id` is already stored, so that a
        redelivery is a detectable condition rather than a second row.
        """
        ...

    async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
        """The record produced by an occurrence, if it was already registered."""
        ...

    async def buscar_por_id(self, registro_id: UUID) -> RegistroDeAuditoria | None: ...

    async def listar(self, filtros: FiltrosDeBitacora) -> list[RegistroDeAuditoria]:
        """The records matching the filters, most recent first.

        Reading is not writing: this addition keeps the port append-and-read, which is
        what HS-T5 RN-03 asks of it.
        """
        ...

    async def contar(self, filtros: FiltrosDeBitacora) -> int:
        """How many records match — **without** materialising them.

        A separate method rather than `len(await listar(...))` because the caller that
        needs the number is a dashboard metric over a whole month, and hydrating tens of
        thousands of aggregates to count them would be work done to be thrown away.
        `limite` is ignored here: a count is not a page.
        """
        ...


class PortRepositorioTareaAsincrona(Protocol):
    """Persistence of async task state.

    Unlike `PortRegistroDeAuditoria` above, this one **does** offer `actualizar`: a task
    is execution state and mutates on every attempt. What it still does not offer is
    `eliminar` — HS-T6 RN-04 wants exhausted tasks kept for analysis and eventual replay,
    and a repository that can delete them is one `cleanup` job away from losing exactly
    the rows somebody needed.
    """

    async def agregar(self, tarea: TareaAsincrona) -> None: ...

    async def actualizar(self, tarea: TareaAsincrona) -> None: ...

    async def buscar_por_id(self, tarea_id: UUID) -> TareaAsincrona | None: ...

    async def buscar_por_clave(self, clave: ClaveDeIdempotencia) -> TareaAsincrona | None:
        """The task a given intended effect already produced, if any."""
        ...

    async def listar_fallidas(self, *, limite: int) -> list[TareaAsincrona]:
        """Tasks sitting in `FALLIDA`, oldest first — the sweep's only query.

        Bounded on purpose: an incident that fails ten thousand tasks must not turn the
        sweep into the thing that runs out of memory. What the batch leaves behind, the
        next run picks up.
        """
        ...
