"""Wiring of the billing context onto one unit of work.

The repository is request-scoped; the WSFEv1 client is process-scoped and cached, for the
reason every other context's assembly gives: it holds a connection pool.

**The credentials map is empty**, like `reference_data`'s. Resolving each company's ARCA
ticket through `integrations` is the piece `emision-de-comprobantes` needs and builds.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.billing.application.ports import (
    PortHabilitacionDeArca,
    PortRepositorioPuntoDeVenta,
)
from cheatsheet.contexts.billing.infrastructure.habilitacion import (
    HabilitacionEnArca,
    HabilitacionSimulada,
)
from cheatsheet.contexts.billing.infrastructure.repositories import (
    RepositorioPuntoDeVentaPostgres,
)
from cheatsheet.platform.settings import AdaptadorDeCatalogos, Settings


@dataclass(frozen=True, slots=True)
class Facturacion:
    """The context's request-scoped adapters, bound to one transaction."""

    puntos: PortRepositorioPuntoDeVenta

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Facturacion:
        return cls(puntos=RepositorioPuntoDeVentaPostgres(unidad.sesion))


@lru_cache(maxsize=1)
def habilitacion_de_arca(settings: Settings) -> PortHabilitacionDeArca:
    """`FEParamGetPtosVenta`, built once per process.

    Switched by the same setting as the fiscal catalogue: both are WSFEv1 reads, and having
    one simulated while the other is real would be a configuration nobody meant to make.
    """
    if settings.catalogos_fiscales_adaptador is AdaptadorDeCatalogos.WSFE:
        return HabilitacionEnArca(url=settings.arca_wsfe_url, credenciales={})
    return HabilitacionSimulada(settings.entorno)
