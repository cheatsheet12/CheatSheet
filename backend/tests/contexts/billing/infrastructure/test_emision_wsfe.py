"""`FECAESolicitar` tal como sale hacia ARCA (HU-E5-03).

Visto contra ARCA homologación el 10/10/2026: sin `CondicionIVAReceptorId` ARCA rechaza
todo comprobante con el error 10246 (RG 5616). El mismo pedido con el campo obtuvo CAE.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.billing.application.emision import item
from cheatsheet.contexts.billing.domain.comprobante import AlicuotaIVA, Comprobante, Receptor
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.contexts.billing.infrastructure.wsfe_emision import _cuerpo_de_solicitud
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA


def _comprobante(receptor: CondicionIVA) -> Comprobante:
    comprobante = Comprobante(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        cliente_id=uuid4(),
        punto_de_venta_id=uuid4(),
        tipo=TipoComprobante.FACTURA_B,
        receptor=Receptor(nombre="Cliente Ficticio", cuit="20222222223", condicion_iva=receptor),
        emisor_condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
        created_at=datetime(2026, 10, 10, tzinfo=UTC),
    )
    comprobante.agregar_item(
        item(
            descripcion="Asesoramiento",
            cantidad="1",
            precio_unitario="1000.00",
            alicuota_iva=AlicuotaIVA.GENERAL,
        )
    )
    comprobante.numero = 2
    return comprobante


@pytest.mark.parametrize(
    ("condicion", "codigo"),
    [
        (CondicionIVA.RESPONSABLE_INSCRIPTO, 1),
        (CondicionIVA.EXENTO, 4),
        (CondicionIVA.CONSUMIDOR_FINAL, 5),
        (CondicionIVA.MONOTRIBUTO, 6),
    ],
)
def test_la_condicion_de_iva_del_receptor_viaja_con_el_codigo_de_arca(
    condicion: CondicionIVA, codigo: int
) -> None:
    cuerpo = _cuerpo_de_solicitud(_comprobante(condicion), 1, date(2026, 10, 10))

    assert re.search(rf"<ar:CondicionIVAReceptorId>{codigo}</ar:CondicionIVAReceptorId>", cuerpo)


def test_cada_condicion_tiene_su_codigo() -> None:
    """Una condición nueva en el catálogo no puede salir hacia ARCA sin código."""
    for condicion in CondicionIVA:
        _cuerpo_de_solicitud(_comprobante(condicion), 1, date(2026, 10, 10))
