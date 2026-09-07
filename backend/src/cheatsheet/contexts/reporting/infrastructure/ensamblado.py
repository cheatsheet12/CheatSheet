"""Cableado de `reporting` sobre una unidad de trabajo.

Los tres repositorios, el almacenamiento y el generador de enlaces. **Los cuatro ACL no se
arman acá**: necesitan los repositorios de `billing`, `payments`, `scheduling` y
`observability`, y la infraestructura de un contexto no puede meter mano en la de otro (R3).
Se arman en `api/reporteria.py`, el composition root, que es la única capa que puede cablear
dos contextos — el mismo lugar donde `api/agenda.py` arma el catálogo de servicios y
`api/mercadopago.py` el saldo de un comprobante.
"""

from __future__ import annotations

from dataclasses import dataclass

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.reporting.application.ports import (
    PortArchivos,
    PortRepositorioPaquetes,
    PortRepositorioReportes,
    PortRepositorioTokens,
    PortTokenDeAcceso,
)
from cheatsheet.contexts.reporting.infrastructure.acceso import EnlaceContableAleatorio
from cheatsheet.contexts.reporting.infrastructure.archivos import ArchivosDeReporteria
from cheatsheet.contexts.reporting.infrastructure.repositories import (
    RepositorioPaquetePostgres,
    RepositorioReportePostgres,
    RepositorioTokenContablePostgres,
)
from cheatsheet.platform.almacenamiento import almacenamiento
from cheatsheet.platform.settings import Settings


@dataclass(frozen=True, slots=True)
class Reporteria:
    """Las piezas que necesita un request, atadas a una transacción.

    El almacenamiento entra acá aunque viva a nivel de proceso: quien lo construye es
    `platform/almacenamiento.py`, que lo cachea, y pasarlo por este objeto evita que cada
    router tenga que acordarse de envolverlo en su adaptador.
    """

    reportes: PortRepositorioReportes
    paquetes: PortRepositorioPaquetes
    tokens: PortRepositorioTokens
    archivos: PortArchivos
    enlaces: PortTokenDeAcceso

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo, settings: Settings) -> Reporteria:
        return cls(
            reportes=RepositorioReportePostgres(unidad.sesion),
            paquetes=RepositorioPaquetePostgres(unidad.sesion),
            tokens=RepositorioTokenContablePostgres(unidad.sesion),
            archivos=ArchivosDeReporteria(almacenamiento(settings)),
            enlaces=EnlaceContableAleatorio(),
        )


__all__ = ["Reporteria"]
