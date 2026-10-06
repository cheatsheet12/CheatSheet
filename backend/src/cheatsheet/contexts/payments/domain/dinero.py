"""El redondeo de plata de `payments`, en un solo lugar.

Vive aparte de `cobro.py` porque `Cobro` y `Reembolso` se necesitan mutuamente y el redondeo
no puede ser la razón de un import circular. `cobro.py` lo reexporta: quien ya importaba
`redondear` desde ahí sigue funcionando.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTAVOS = Decimal("0.01")


def redondear(monto: Decimal) -> Decimal:
    """Dos decimales, `ROUND_HALF_UP`. El único lugar donde este contexto redondea plata."""
    return monto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


__all__ = ["CENTAVOS", "redondear"]
