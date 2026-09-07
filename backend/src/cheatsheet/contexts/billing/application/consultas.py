"""HU-E5-01 and HU-E5-02 — reading what was issued.

**Every role reads, including Solo Lectura** (HU-E5-01 RN-04). What that role does not get
is the *actions*, and those live in `emision.py` behind their own check. Hiding a button is
a courtesy; refusing the use case is the guarantee, which is what PRU-09 taught.

There is no `empresa_id` filter anywhere here. RLS scopes every statement, and RN-01 says
the isolation is transparent — writing it again in a `WHERE` would suggest this layer is
what enforces it, and the day somebody forgot would be the day it was gone.
"""

from __future__ import annotations

from uuid import UUID

from cheatsheet.contexts.billing.application.errors import ComprobanteInexistente
from cheatsheet.contexts.billing.application.ports import (
    FiltrosDeComprobante,
    PortRepositorioComprobante,
)
from cheatsheet.contexts.billing.domain.comprobante import Comprobante

#: HU-E5-01, word for word, for the empty state of PAN-FAC-01.
MENSAJE_SIN_RESULTADOS = "No hay comprobantes para los filtros seleccionados."


class ListarComprobantes:
    """PAN-FAC-01. Ordered by issue date descending (RN-03)."""

    def __init__(self, comprobantes: PortRepositorioComprobante) -> None:
        self._comprobantes = comprobantes

    async def ejecutar(self, filtros: FiltrosDeComprobante | None = None) -> list[Comprobante]:
        return await self._comprobantes.listar(filtros or FiltrosDeComprobante())


class VerComprobante:
    """PAN-FAC-02. Raises rather than returning `None`.

    A caller that got `None` would have to decide what it means, and there is only one
    thing it can mean under RLS: not this company's, or never existed. Those are the same
    answer on purpose — distinguishing them would tell one company that another company's
    document id is real.
    """

    def __init__(self, comprobantes: PortRepositorioComprobante) -> None:
        self._comprobantes = comprobantes

    async def ejecutar(self, comprobante_id: UUID) -> Comprobante:
        comprobante = await self._comprobantes.buscar_por_id(comprobante_id)
        if comprobante is None:
            raise ComprobanteInexistente("El comprobante no existe")
        return comprobante


__all__ = ["MENSAJE_SIN_RESULTADOS", "ListarComprobantes", "VerComprobante"]
