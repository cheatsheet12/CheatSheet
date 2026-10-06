"""Cableado de `observability` sobre una unidad de trabajo.

Los tres repositorios que la superficie del panel necesita. **El ACL sobre `identity` no se
arma acá**: necesita el repositorio de ese contexto, y la infraestructura de uno no puede meter
mano en la de otro (R3). Se arma en `api/dependencies.py`, que es el composition root y el
único lugar que puede cablear dos contextos — el mismo sitio donde el suscriptor de auditoría
se engancha al publicador.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.observability.application.ports import (
    PortRegistroDeAuditoria,
    PortRepositorioNotificaciones,
    PortRepositorioSolicitudes,
)
from cheatsheet.contexts.observability.infrastructure.notificaciones_repository import (
    RepositorioNotificacionesPostgres,
    RepositorioSolicitudesPostgres,
)
from cheatsheet.contexts.observability.infrastructure.repository import (
    RepositorioDeAuditoriaPostgres,
)


@dataclass(frozen=True, slots=True)
class Observabilidad:
    """Las piezas que necesita un request, atadas a una transacción."""

    registros: PortRegistroDeAuditoria
    notificaciones: PortRepositorioNotificaciones
    solicitudes: PortRepositorioSolicitudes

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Observabilidad:
        return cls(
            registros=RepositorioDeAuditoriaPostgres(unidad.sesion),
            notificaciones=RepositorioNotificacionesPostgres(unidad.sesion),
            solicitudes=RepositorioSolicitudesPostgres(unidad.sesion),
        )


__all__ = ["Observabilidad"]
