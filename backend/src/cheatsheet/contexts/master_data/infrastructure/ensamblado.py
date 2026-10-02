"""Wiring of the master data context onto one unit of work.

Small, and it will stay small: this context has one port per aggregate that touches the
database and one that leaves the process, and the second one is assembled above both
contexts in
`api/padron.py` — neither `master_data/infrastructure/` nor `integrations/infrastructure/`
may reach into the other (rule R3).

Request-scoped, like every other context's assembly: the repository writes through the
session the caller's transaction owns.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.master_data.application.ports import (
    PortClasificaciones,
    PortCorreccionDeNombres,
    PortRepositorioCategoria,
    PortRepositorioCliente,
    PortRepositorioServicio,
)
from cheatsheet.contexts.master_data.infrastructure.categorias import (
    ClasificacionesPostgres,
    RepositorioCategoriaPostgres,
)
from cheatsheet.contexts.master_data.infrastructure.correccion import CorreccionDeNombresPostgres
from cheatsheet.contexts.master_data.infrastructure.repositories import (
    RepositorioClientePostgres,
    RepositorioServicioPostgres,
)


@dataclass(frozen=True, slots=True)
class DatosMaestros:
    """The master data context's adapters, bound to one transaction."""

    clientes: PortRepositorioCliente
    servicios: PortRepositorioServicio
    categorias: PortRepositorioCategoria
    clasificaciones: PortClasificaciones
    correccion: PortCorreccionDeNombres

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> DatosMaestros:
        return cls(
            clientes=RepositorioClientePostgres(unidad.sesion),
            servicios=RepositorioServicioPostgres(unidad.sesion),
            categorias=RepositorioCategoriaPostgres(unidad.sesion),
            clasificaciones=ClasificacionesPostgres(unidad.sesion),
            correccion=CorreccionDeNombresPostgres(unidad.sesion),
        )
