"""El formato de plata de `payments`: un solo formateador es-AR para el texto y la plantilla."""

from decimal import Decimal

import pytest
from cheatsheet.contexts.payments.domain.dinero import formatear_es_ar


@pytest.mark.parametrize(
    ("monto", "esperado"),
    [
        ("1234.5", "1.234,50"),
        ("0", "0,00"),
        ("1000000", "1.000.000,00"),
        ("0.005", "0,01"),
        ("2.675", "2,68"),
        ("999.995", "1.000,00"),
        ("-1234.5", "-1.234,50"),
        ("-0.001", "0,00"),
        ("12345678901.239", "12.345.678.901,24"),
    ],
)
def test_formatea_con_punto_de_miles_coma_decimal_y_dos_decimales(
    monto: str, esperado: str
) -> None:
    assert formatear_es_ar(Decimal(monto)) == esperado
