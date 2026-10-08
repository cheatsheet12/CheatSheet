"""`PagoSinImputar`: un pago que entró y no se imputó a ninguna deuda (unidad
`pagos-sin-cobro-asociado`). Es un hecho registrado: sin estados ni transiciones."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.domain.pago_sin_imputar import (
    LARGO_MAXIMO_DE_REFERENCIA,
    MotivoSinImputar,
    PagoSinImputar,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def _pago(**campos: object) -> PagoSinImputar:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "mp_payment_id": "123456",
        "motivo": MotivoSinImputar.SIN_COBRO,
        "recibido_en": AHORA,
    }
    return PagoSinImputar(**{**base, **campos})  # type: ignore[arg-type]


def test_el_monto_se_redondea_half_up_desde_el_decimal() -> None:
    """Caso 10. `1210.005` redondea hacia arriba; nunca pasa por `float`."""
    assert _pago(monto=Decimal("1210.005")).monto == Decimal("1210.01")
    assert _pago(monto=Decimal("1210.004")).monto == Decimal("1210.00")


def test_sin_monto_queda_en_none() -> None:
    assert _pago().monto is None


@pytest.mark.parametrize(
    "motivo", [MotivoSinImputar.COBRO_YA_PAGADO, MotivoSinImputar.MONTO_DISTINTO]
)
def test_un_motivo_con_cobro_exige_el_cobro(motivo: MotivoSinImputar) -> None:
    with pytest.raises(EntradaInvalida):
        _pago(motivo=motivo)
    assert _pago(motivo=motivo, cobro_id=uuid4()).cobro_id is not None


def test_sin_cobro_no_puede_traer_cobro() -> None:
    with pytest.raises(EntradaInvalida):
        _pago(motivo=MotivoSinImputar.SIN_COBRO, cobro_id=uuid4())


def test_el_id_de_pago_no_puede_estar_vacio() -> None:
    with pytest.raises(EntradaInvalida):
        _pago(mp_payment_id="  ")


def test_la_referencia_se_limpia_y_se_acota_al_largo_de_la_columna() -> None:
    assert _pago(referencia_externa="  abc  ").referencia_externa == "abc"
    assert _pago(referencia_externa="   ").referencia_externa is None
    larga = _pago(referencia_externa="x" * (LARGO_MAXIMO_DE_REFERENCIA + 50)).referencia_externa
    assert larga is not None
    assert len(larga) == LARGO_MAXIMO_DE_REFERENCIA


def test_es_inmutable() -> None:
    pago = _pago()
    with pytest.raises(AttributeError):
        pago.monto = Decimal("1.00")  # type: ignore[misc]
