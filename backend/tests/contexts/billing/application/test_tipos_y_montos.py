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
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
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


def test_el_tipo_de_la_nota_lo_determina_la_letra_del_original() -> None:
    """HU-E5-04 RN-02, en el dominio: A anula A, B anula B, C anula C.

    Lo determina el sistema y no lo elige el usuario, porque ofrecer las otras dos sería
    ofrecer un documento que ARCA rechaza.
    """
    esperados: dict[TipoComprobante, TipoComprobante] = {
        TipoComprobante.FACTURA_A: TipoComprobante.NOTA_CREDITO_A,
        TipoComprobante.FACTURA_B: TipoComprobante.NOTA_CREDITO_B,
        TipoComprobante.FACTURA_C: TipoComprobante.NOTA_CREDITO_C,
    }
    for factura, nota in esperados.items():
        assert factura.nota_de_credito is nota


def test_una_nota_de_credito_no_tiene_nota_de_credito() -> None:
    """Anular una anulación no es una operación: se emite una factura nueva."""
    with pytest.raises(InvarianteViolada):
        _ = TipoComprobante.NOTA_CREDITO_A.nota_de_credito
