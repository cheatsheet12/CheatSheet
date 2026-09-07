"""Cableado de `scheduling` sobre una unidad de trabajo.

Sólo los repositorios y el avisador local. **Los dos ACL sobre `master_data` no se arman
acá**: necesitan los repositorios de ese contexto, y la infraestructura de un contexto no
puede meter mano en la de otro (R3). Se arman en `api/agenda.py`, el composition root, que es
la única capa que puede cablear dos contextos — el mismo lugar donde `api/mercadopago.py` arma
el saldo de `billing` para `payments`.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.scheduling.application.ports import (
    PortRepositorioRecurso,
    PortRepositorioTurno,
)
from cheatsheet.contexts.scheduling.infrastructure.repositories import (
    RepositorioRecursoPostgres,
    RepositorioTurnoPostgres,
)


@dataclass(frozen=True, slots=True)
class Agenda:
    """Las piezas que necesita un request, atadas a una transacción."""

    recursos: PortRepositorioRecurso
    turnos: PortRepositorioTurno

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Agenda:
        return cls(
            recursos=RepositorioRecursoPostgres(unidad.sesion),
            turnos=RepositorioTurnoPostgres(unidad.sesion),
        )


__all__ = ["Agenda"]
