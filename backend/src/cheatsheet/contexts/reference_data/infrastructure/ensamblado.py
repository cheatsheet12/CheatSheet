"""Wiring of the fiscal catalogue onto one unit of work.

Only the repository. **The WSFEv1 client is not built here** any more: resolving the ARCA
credential means calling `integrations`, which rule R3 puts out of reach from a context's
`infrastructure/`. It is built in `api/arca.py`, the composition root, alongside the two
that `billing` uses — which is what the note this docstring replaces said would happen, and
it happened.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.reference_data.application.ports import PortRepositorioParametros
from cheatsheet.contexts.reference_data.infrastructure.repositories import (
    RepositorioParametrosPostgres,
)


@dataclass(frozen=True, slots=True)
class ParametrosFiscales:
    """The context's request-scoped adapters, bound to one transaction."""

    parametros: PortRepositorioParametros

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> ParametrosFiscales:
        return cls(parametros=RepositorioParametrosPostgres(unidad.sesion))
