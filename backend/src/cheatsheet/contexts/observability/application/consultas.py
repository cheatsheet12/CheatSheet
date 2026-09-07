"""Reading the audit log (HS-T5, and the metric epic 9 needs).

The log is written by a subscriber that nobody calls directly; this is the other half —
the part that answers questions about it. Two of them, and no more:

- **how many operations happened in a period**, which is one of the four dashboard
  metrics of HU-E10-01 RN-02, and
- **which ones**, which is what an exportable "log de operaciones" is made of
  (HU-E10-04 RN-03) and what the audit panel of epic 10 will paginate.

Both are reads. Nothing here can write, and the port they use still has no `actualizar`
and no `eliminar`: HS-T5 RN-03 makes these records immutable, and reading them does not
change that.

No `empresa_id` filter appears anywhere: Row-Level Security already scopes the statement,
and a second copy of that rule in the application layer is a copy that can drift.
"""

from __future__ import annotations

from cheatsheet.contexts.observability.application.ports import (
    FiltrosDeBitacora,
    PortRegistroDeAuditoria,
)
from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria


class ListarOperaciones:
    """The records of a period, most recent first."""

    def __init__(self, registros: PortRegistroDeAuditoria) -> None:
        self._registros = registros

    async def ejecutar(self, filtros: FiltrosDeBitacora | None = None) -> list[RegistroDeAuditoria]:
        return await self._registros.listar(filtros or FiltrosDeBitacora())


class ContarOperaciones:
    """How many, without bringing them back.

    Separate from `ListarOperaciones` because the caller is a headline number over a whole
    month: hydrating every aggregate to take its length would be work done to be discarded.
    """

    def __init__(self, registros: PortRegistroDeAuditoria) -> None:
        self._registros = registros

    async def ejecutar(self, filtros: FiltrosDeBitacora | None = None) -> int:
        return await self._registros.contar(filtros or FiltrosDeBitacora())


__all__ = ["ContarOperaciones", "ListarOperaciones"]
