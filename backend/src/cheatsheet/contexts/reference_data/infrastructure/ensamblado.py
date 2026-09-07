"""Wiring of the fiscal catalogue onto one unit of work.

The repository is request-scoped like every other; the WSFEv1 client is process-scoped and
cached, because it holds a connection pool and the sweep would otherwise open one per run.

**The credentials map is empty for now**, and that is the piece this unit does not finish:
resolving each company's ARCA ticket means calling `integrations`' `ObtenerTicketDeAcceso`
from the composition root, which is where `emision-de-comprobantes` needs it too. It is
built there, once, rather than twice here and again in `billing`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.reference_data.application.ports import (
    PortCatalogosFiscales,
    PortRepositorioParametros,
)
from cheatsheet.contexts.reference_data.infrastructure.repositories import (
    RepositorioParametrosPostgres,
)
from cheatsheet.contexts.reference_data.infrastructure.wsfe_catalogos import (
    CatalogosDeWsfe,
    CatalogosSimulados,
)
from cheatsheet.platform.settings import AdaptadorDeCatalogos, Settings


@dataclass(frozen=True, slots=True)
class ParametrosFiscales:
    """The context's request-scoped adapters, bound to one transaction."""

    parametros: PortRepositorioParametros

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> ParametrosFiscales:
        return cls(parametros=RepositorioParametrosPostgres(unidad.sesion))


@lru_cache(maxsize=1)
def catalogos_fiscales(settings: Settings) -> PortCatalogosFiscales:
    """The WSFEv1 catalogue client, built once per process (ADR-0008)."""
    if settings.catalogos_fiscales_adaptador is AdaptadorDeCatalogos.WSFE:
        return CatalogosDeWsfe(url=settings.arca_wsfe_url, credenciales={})
    return CatalogosSimulados(settings.entorno)
