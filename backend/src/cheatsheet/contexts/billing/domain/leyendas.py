"""What the printed document has to say besides its numbers (HU-E5-03 RN-13).

A function of the document rather than a stored column: the legend follows from the type
and the receptor's VAT condition, both frozen at issue time, so storing it would only add a
second place for the two to disagree.
"""

from __future__ import annotations

from cheatsheet.contexts.billing.domain.comprobante import Comprobante
from cheatsheet.shared.fiscal import CondicionIVA

#: RN-13, word for word: a Factura A to a Monotributista discriminates VAT that the receptor
#: can only compute under the regime of Ley 27.618.
LEYENDA_MONOTRIBUTO = (
    "El crédito fiscal discriminado en el presente comprobante, sólo podrá ser computado a "
    "efectos del Régimen de Sostenimiento e Inclusión Fiscal para Pequeños Contribuyentes "
    "de la Ley Nº 27.618"
)


def leyenda_de(comprobante: Comprobante) -> str | None:
    """The legend the document must carry, or `None` when it needs none."""
    if (
        comprobante.tipo.letra == "A"
        and comprobante.receptor.condicion_iva is CondicionIVA.MONOTRIBUTO
    ):
        return LEYENDA_MONOTRIBUTO
    return None


__all__ = ["LEYENDA_MONOTRIBUTO", "leyenda_de"]
