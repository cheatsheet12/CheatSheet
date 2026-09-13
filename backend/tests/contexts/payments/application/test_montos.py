"""Cómo entra la plata a `payments`, sin `async`.

En su propio módulo porque es sincrónico y el resto del paquete no: un
`pytestmark = pytest.mark.asyncio` a nivel de módulo marca también a los sincrónicos y pytest
avisa por cada uno.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from cheatsheet.contexts.payments.application.cobros import monto_desde
from cheatsheet.shared.errors import EntradaInvalida


def test_el_monto_llega_como_texto_y_se_vuelve_decimal() -> None:
    """Nunca pasa por `float`: está mal en el cuarto decimal, que es donde vive un centavo."""
    assert monto_desde("1234.56") == Decimal("1234.56")


def test_un_monto_que_no_es_numero_se_rechaza_en_vez_de_romper() -> None:
    with pytest.raises(EntradaInvalida):
        monto_desde("mil pesos")
