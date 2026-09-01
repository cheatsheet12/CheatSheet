"""Wiring of the master data context onto one unit of work.

Small, and it will stay small: this context has one port that touches the database and
one that leaves the process, and the second one is assembled above both contexts in
`api/padron.py` — neither `master_data/infrastructure/` nor `integrations/infrastructure/`
may reach into the other (rule R3).

Request-scoped, like every other context's assembly: the repository writes through the
session the caller's transaction owns.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.master_data.application.ports import PortRepositorioCliente
from cheatsheet.contexts.master_data.infrastructure.repositories import RepositorioClientePostgres


@dataclass(frozen=True, slots=True)
class DatosMaestros:
    """The master data context's adapters, bound to one transaction."""

    clientes: PortRepositorioCliente

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> DatosMaestros:
        return cls(clientes=RepositorioClientePostgres(unidad.sesion))
