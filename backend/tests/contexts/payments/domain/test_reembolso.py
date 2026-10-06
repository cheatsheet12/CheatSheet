"""`Reembolso`: una fila inmutable, con las invariantes que la base repite (ADR-0010, punto 4).

Cada invariante de acá tiene su `CHECK` gemelo en la migración 0027 y su prueba contra
PostgreSQL: el dominio es la primera línea y el esquema es lo que un bug futuro no saltea.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.payments.domain.reembolso import OrigenDeReembolso, Reembolso
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())


def _fila(
    monto: str = "100.00",
    *,
    origen: OrigenDeReembolso = OrigenDeReembolso.API_MERCADOPAGO,
    corrige_a: UUID | None = None,
    motivo: str | None = None,
    referencia: str | None = None,
) -> Reembolso:
    return Reembolso(
        id=uuid4(),
        empresa_id=EMPRESA,
        cobro_id=uuid4(),
        monto=Decimal(monto),
        fecha_devolucion=AHORA,
        origen=origen,
        created_at=AHORA,
        corrige_a=corrige_a,
        motivo=motivo,
        referencia=referencia,
    )


def test_el_monto_se_redondea_half_up_al_construir() -> None:
    assert _fila("100.005").monto == Decimal("100.01")


def test_un_monto_que_redondea_a_cero_se_rechaza() -> None:
    with pytest.raises(EntradaInvalida):
        _fila("0")
    with pytest.raises(EntradaInvalida):
        _fila("0.004")


def test_negativo_si_y_solo_si_es_una_correccion() -> None:
    original = uuid4()

    with pytest.raises(EntradaInvalida):
        _fila("-100.00")
    with pytest.raises(EntradaInvalida):
        _fila("100.00", corrige_a=original, origen=OrigenDeReembolso.MANUAL, motivo="Error")
    correccion = _fila(
        "-100.00", corrige_a=original, origen=OrigenDeReembolso.MANUAL, motivo="Error de carga"
    )

    assert correccion.es_correccion
    assert not _fila().es_correccion


def test_un_reembolso_manual_exige_motivo() -> None:
    for motivo in (None, "", "   "):
        with pytest.raises(EntradaInvalida):
            _fila(origen=OrigenDeReembolso.MANUAL, motivo=motivo)
    manual = _fila(origen=OrigenDeReembolso.MANUAL, motivo="  Devolucion  ")

    assert manual.motivo == "Devolucion"
    assert manual.es_manual


def test_un_reembolso_de_la_api_no_necesita_motivo() -> None:
    assert _fila().motivo is None


def test_los_textos_vacios_se_guardan_como_ausentes_y_los_largos_se_rechazan() -> None:
    assert _fila(referencia="   ").referencia is None
    with pytest.raises(EntradaInvalida):
        _fila(referencia="x" * 121)
    with pytest.raises(EntradaInvalida):
        _fila(origen=OrigenDeReembolso.MANUAL, motivo="x" * 501)


def test_la_fila_es_inmutable() -> None:
    fila = _fila()

    with pytest.raises(FrozenInstanceError):
        fila.monto = Decimal("1.00")  # type: ignore[misc]  # frozen on purpose: it is the assertion
