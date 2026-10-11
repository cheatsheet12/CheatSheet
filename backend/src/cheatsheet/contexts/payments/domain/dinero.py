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


def formatear_es_ar(monto: Decimal) -> str:
    """El monto como lo escribe un argentino: `12500` → `12.500,00`.

    Dos decimales con `ROUND_HALF_UP` (el mismo `redondear`), punto de miles y coma decimal. Es el
    valor que viaja como parámetro de la plantilla de Meta; nunca pasa por `float`.
    """
    entero, decimales = f"{redondear(monto):.2f}".split(".")
    con_miles = f"{int(entero):,}".replace(",", ".")
    return f"{con_miles},{decimales}"


__all__ = ["CENTAVOS", "formatear_es_ar", "redondear"]
