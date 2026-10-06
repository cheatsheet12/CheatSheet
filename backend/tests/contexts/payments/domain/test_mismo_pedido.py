"""`Cobro.es_el_mismo_pedido`: cuándo una clave repetida es el mismo pedido (ADR-0013, punto 5).

Se compara contra los campos del cobro, que son inmutables después de crearlo. El monto se
compara **redondeado** (`ROUND_HALF_UP`) y nunca pasa por `float`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.shared.empresa import EmpresaId

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
CLIENTE = uuid4()


def _cobro(*, monto: str = "1210.01", comprobante_id: UUID | None = None) -> Cobro:
    return Cobro(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        cliente_id=CLIENTE,
        monto=Decimal(monto),
        descripcion="Consulta de septiembre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA,
        comprobante_id=comprobante_id,
        clave_idempotencia=uuid4(),
    )


def test_el_cobro_guarda_la_clave_y_los_viejos_no_la_tienen() -> None:
    assert _cobro().clave_idempotencia is not None
    sin_clave = Cobro(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        cliente_id=CLIENTE,
        monto=Decimal("1.00"),
        descripcion="Viejo",
        vence_el=AHORA,
        created_at=AHORA,
    )
    assert sin_clave.clave_idempotencia is None


def test_los_mismos_datos_son_el_mismo_pedido() -> None:
    assert _cobro().es_el_mismo_pedido(
        cliente_id=CLIENTE,
        monto=Decimal("1210.01"),
        descripcion="Consulta de septiembre",
        comprobante_id=None,
    )


def test_el_monto_se_compara_redondeado() -> None:
    cobro = _cobro()
    mismo = cobro.es_el_mismo_pedido(
        cliente_id=CLIENTE,
        monto=Decimal("1210.005"),
        descripcion="Consulta de septiembre",
        comprobante_id=None,
    )
    otro = cobro.es_el_mismo_pedido(
        cliente_id=CLIENTE,
        monto=Decimal("1210.02"),
        descripcion="Consulta de septiembre",
        comprobante_id=None,
    )
    assert mismo
    assert not otro


def test_cambia_el_cliente_el_concepto_o_el_comprobante_es_otro_pedido() -> None:
    comprobante = uuid4()
    cobro = _cobro(comprobante_id=comprobante)
    base = {
        "cliente_id": CLIENTE,
        "monto": Decimal("1210.01"),
        "descripcion": "Consulta de septiembre",
        "comprobante_id": comprobante,
    }
    assert cobro.es_el_mismo_pedido(**base)  # type: ignore[arg-type]
    for campo, otro in (
        ("cliente_id", uuid4()),
        ("descripcion", "Otra cosa"),
        ("comprobante_id", uuid4()),
        ("comprobante_id", None),
    ):
        assert not cobro.es_el_mismo_pedido(**{**base, campo: otro})  # type: ignore[arg-type]


def test_sin_comprobante_contra_un_comprobante_es_otro_pedido() -> None:
    assert not _cobro().es_el_mismo_pedido(
        cliente_id=CLIENTE,
        monto=Decimal("1210.01"),
        descripcion="Consulta de septiembre",
        comprobante_id=uuid4(),
    )
