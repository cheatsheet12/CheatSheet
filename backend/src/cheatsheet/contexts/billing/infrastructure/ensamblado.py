"""Wiring of the billing context onto one unit of work.

Only the repositories. **The WSFEv1 clients are not built here**, and that is a change from
what the two previous units of this epic did: resolving a company's ARCA credential means
calling `integrations`, and a context's `infrastructure/` may not reach into another's
(R3). They are built in `api/arca.py`, the composition root, which is the one layer allowed
to wire two contexts together — the same place `api/padron.py` already assembles the
registry lookup.

That is also what let the empty `credenciales={}` disappear: it was empty because there was
nowhere legal to fill it from, here.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.billing.application.ports import (
    PortRepositorioComprobante,
    PortRepositorioPuntoDeVenta,
)
from cheatsheet.contexts.billing.infrastructure.pdf import PdfDeComprobante
from cheatsheet.contexts.billing.infrastructure.repositories import (
    RepositorioPuntoDeVentaPostgres,
)
from cheatsheet.contexts.billing.infrastructure.repositorio_comprobante import (
    RepositorioComprobantePostgres,
)
from cheatsheet.platform.almacenamiento import almacenamiento
from cheatsheet.platform.settings import Settings


@dataclass(frozen=True, slots=True)
class Facturacion:
    """The context's request-scoped adapters, bound to one transaction."""

    puntos: PortRepositorioPuntoDeVenta
    comprobantes: PortRepositorioComprobante

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo) -> Facturacion:
        return cls(
            puntos=RepositorioPuntoDeVentaPostgres(unidad.sesion),
            comprobantes=RepositorioComprobantePostgres(unidad.sesion),
        )


@lru_cache(maxsize=1)
def pdf_de_comprobantes(settings: Settings) -> PdfDeComprobante:
    """The PDF renderer and its cache, built once per process.

    Cached here and **not** in `api/arca.py`, which builds its clients per request: this one
    has no credential bound to a transaction, and the R2 client does hold a connection pool.

    The store is the same `platform/almacenamiento.py` `spreadsheet_sync` uses -- one
    adapter, two consumers, each with its own port (R3).
    """
    return PdfDeComprobante(almacenamiento(settings))
