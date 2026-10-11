"""HU-E5-03 RN-13: la leyenda de la Factura A a un Monotributista."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cheatsheet.contexts.billing.domain.comprobante import Comprobante, Receptor
from cheatsheet.contexts.billing.domain.leyendas import LEYENDA_MONOTRIBUTO, leyenda_de
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA


def _comprobante(tipo: TipoComprobante, receptor: CondicionIVA) -> Comprobante:
    return Comprobante(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        cliente_id=uuid4(),
        punto_de_venta_id=uuid4(),
        tipo=tipo,
        receptor=Receptor(nombre="Cliente Ficticio", cuit="20222222223", condicion_iva=receptor),
        emisor_condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
        created_at=datetime(2026, 10, 10, tzinfo=UTC),
    )


@pytest.mark.parametrize("tipo", [TipoComprobante.FACTURA_A, TipoComprobante.NOTA_CREDITO_A])
def test_la_a_a_un_monotributista_lleva_la_leyenda(tipo: TipoComprobante) -> None:
    assert leyenda_de(_comprobante(tipo, CondicionIVA.MONOTRIBUTO)) == LEYENDA_MONOTRIBUTO
    assert "27.618" in LEYENDA_MONOTRIBUTO


def test_la_a_a_un_inscripto_no_lleva_leyenda() -> None:
    comprobante = _comprobante(TipoComprobante.FACTURA_A, CondicionIVA.RESPONSABLE_INSCRIPTO)

    assert leyenda_de(comprobante) is None


def test_la_b_no_lleva_leyenda() -> None:
    comprobante = _comprobante(TipoComprobante.FACTURA_B, CondicionIVA.CONSUMIDOR_FINAL)

    assert leyenda_de(comprobante) is None
