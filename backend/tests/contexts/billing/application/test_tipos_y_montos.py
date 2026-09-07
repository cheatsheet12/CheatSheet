"""Las dos piezas sincrónicas de la emisión: qué tipos se ofrecen y cómo entra la plata.

Están en su propio módulo porque no son `async` y el resto de `test_emision.py` sí: un
`pytestmark = pytest.mark.asyncio` a nivel de módulo marca también a los tests sincrónicos,
y pytest avisa por cada uno.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from cheatsheet.contexts.billing.application.emision import TiposDisponibles, item
from cheatsheet.contexts.billing.domain.comprobante import AlicuotaIVA
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.fiscal import CondicionIVA

RI = CondicionIVA.RESPONSABLE_INSCRIPTO


def test_la_pantalla_solo_ofrece_tipos_legales() -> None:
    """RN-01: el mensaje de error existe para el pedido que no vino de la pantalla."""
    ofrecidos = TiposDisponibles.ejecutar(emisor=RI, receptor=CondicionIVA.CONSUMIDOR_FINAL)

    assert TipoComprobante.FACTURA_B in ofrecidos
    assert TipoComprobante.FACTURA_A not in ofrecidos


def test_el_orden_de_los_tipos_es_estable() -> None:
    """Un `frozenset` no tiene orden, y una pantalla que reordena su combo entre requests
    es una pantalla en la que alguien elige mal por costumbre."""
    primero = TiposDisponibles.ejecutar(emisor=RI, receptor=RI)
    segundo = TiposDisponibles.ejecutar(emisor=RI, receptor=RI)

    assert primero == segundo


def test_un_consumidor_final_no_recibe_ningun_tipo() -> None:
    assert TiposDisponibles.ejecutar(emisor=CondicionIVA.CONSUMIDOR_FINAL, receptor=RI) == ()


def test_los_montos_llegan_como_texto_y_nunca_como_float() -> None:
    """`0.1 + 0.2` está mal en el cuarto decimal, que es donde vive un centavo."""
    creado = item(
        descripcion="Corte",
        cantidad="2",
        precio_unitario="1234.56",
        alicuota_iva=AlicuotaIVA.GENERAL,
    )

    assert creado.precio_unitario == Decimal("1234.56")
    assert creado.subtotal == Decimal("2469.12")


def test_un_monto_que_no_es_numero_se_rechaza_en_vez_de_romper() -> None:
    with pytest.raises(EntradaInvalida):
        item(
            descripcion="Corte",
            cantidad="dos",
            precio_unitario="1000",
            alicuota_iva=AlicuotaIVA.GENERAL,
        )
