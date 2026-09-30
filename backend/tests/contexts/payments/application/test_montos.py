"""Cómo entra la plata a `payments`, sin `async`.

En su propio módulo porque es sincrónico y el resto del paquete no: un
`pytestmark = pytest.mark.asyncio` a nivel de módulo marca también a los sincrónicos y pytest
avisa por cada uno.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.application.cobros import (
    MENSAJE_MONTO_DEMASIADO_GRANDE,
    MONTO_MAXIMO_DE_COBRO,
    monto_desde,
)
from cheatsheet.contexts.payments.domain.cobro import MENSAJE_MONTO_NO_POSITIVO, Cobro
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida

AHORA = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def test_el_monto_llega_como_texto_y_se_vuelve_decimal() -> None:
    """Nunca pasa por `float`: está mal en el cuarto decimal, que es donde vive un centavo."""
    assert monto_desde("1234.56") == Decimal("1234.56")


def test_un_monto_que_no_es_numero_se_rechaza_en_vez_de_romper() -> None:
    with pytest.raises(EntradaInvalida):
        monto_desde("mil pesos")


@pytest.mark.parametrize("texto", ["NaN", "nan", "sNaN", "Infinity", "-Infinity", "inf"])
def test_un_monto_no_finito_se_rechaza_como_no_positivo_y_no_como_500(texto: str) -> None:
    """`Decimal("NaN") <= 0` levanta `InvalidOperation`: sin esto, el POST contesta 500."""
    with pytest.raises(EntradaInvalida) as exc:
        monto_desde(texto)

    assert str(exc.value) == MENSAJE_MONTO_NO_POSITIVO


def test_el_tope_de_un_cobro_es_de_negocio_y_no_la_capacidad_de_la_columna() -> None:
    assert Decimal("100000000.00") == MONTO_MAXIMO_DE_COBRO


def test_el_monto_justo_en_el_tope_se_acepta() -> None:
    assert monto_desde("100000000.00") == MONTO_MAXIMO_DE_COBRO


@pytest.mark.parametrize("texto", ["100000000.01", "999999999999.99", "1e30"])
def test_un_monto_sobre_el_tope_se_rechaza(texto: str) -> None:
    with pytest.raises(EntradaInvalida) as exc:
        monto_desde(texto)

    assert str(exc.value) == MENSAJE_MONTO_DEMASIADO_GRANDE


def test_un_monto_con_medio_centavo_se_redondea_half_up_y_no_pasa_por_float() -> None:
    """`1210.005` en binario es `1210.00499999...`: por `float` el cobro quedaria en `1210.00`."""
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        cliente_id=uuid4(),
        monto=monto_desde("1210.005"),
        descripcion="Consulta",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA,
    )

    assert cobro.monto == Decimal("1210.01")
