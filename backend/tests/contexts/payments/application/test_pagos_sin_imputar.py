"""HS-T1 — un pago se ata a su cobro por `external_reference`, y el que no se puede imputar queda
registrado (unidad `pagos-sin-cobro-asociado`).

Los dobles son los de `test_confirmacion.py`; el repositorio de pagos sin imputar es nuevo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from cheatsheet.contexts.payments.application.confirmacion import ConfirmarPago
from cheatsheet.contexts.payments.domain.cobro import Cobro, EstadoCobro, LinkDePago
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.payments.application.test_confirmacion import (
    CobrosFalsos,
    PasarelaFalsa,
    PublicadorFalso,
    SaldosFalsos,
)

pytestmark = pytest.mark.asyncio

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
EMPRESA = EmpresaId(uuid4())
LINK_VIGENTE = LinkDePago(preference_id="pref-vigente", url="https://mp.com/checkout/vigente")


def _cobro(*, link: LinkDePago | None = LINK_VIGENTE) -> Cobro:
    cobro = Cobro(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=uuid4(),
        monto=Decimal("1210.00"),
        descripcion="Consulta de octubre",
        vence_el=AHORA + timedelta(days=30),
        created_at=AHORA,
        comprobante_id=uuid4(),
    )
    if link is not None:
        cobro.asignar_link(link, AHORA)
    return cobro


async def test_un_pago_con_referencia_y_sin_preferencia_aprueba_el_cobro() -> None:
    """Caso 2. Es el pago real de Checkout Pro: trae `external_reference` y no `preference_id`."""
    cobros, saldos, publicador = CobrosFalsos(), SaldosFalsos(), PublicadorFalso()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia=None, referencia=str(cobro.id))

    resultado = await ConfirmarPago(
        cobros=cobros, pasarela=pasarela, saldos=saldos, publicador=publicador
    ).ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO
    assert cobro.mp_payment_id == "pago-1"
    assert len(saldos.descuentos) == 1
    assert publicador.eventos[0].accion == "confirmar_pago"  # type: ignore[attr-defined]


async def test_un_pago_por_el_link_viejo_se_imputa_al_cobro_de_la_referencia() -> None:
    """Regenerar el link cambia la preferencia de la fila; la referencia sigue siendo la misma."""
    cobros = CobrosFalsos()
    cobro = _cobro(link=LinkDePago(preference_id="pref-nueva", url="https://mp.com/n"))
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia="pref-vieja", referencia=str(cobro.id))

    resultado = await ConfirmarPago(
        cobros=cobros, pasarela=pasarela, saldos=SaldosFalsos(), publicador=PublicadorFalso()
    ).ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO


async def test_un_pago_con_la_preferencia_y_sin_referencia_se_sigue_encontrando() -> None:
    """Caso 3. Compatibilidad con el camino anterior."""
    cobros = CobrosFalsos()
    cobro = _cobro()
    await cobros.agregar(cobro)
    pasarela = PasarelaFalsa(preferencia="pref-vigente", referencia=None)

    resultado = await ConfirmarPago(
        cobros=cobros, pasarela=pasarela, saldos=SaldosFalsos(), publicador=PublicadorFalso()
    ).ejecutar(empresa_id=EMPRESA, payment_id="pago-1", ahora=AHORA)

    assert resultado.aprobado
    assert cobro.estado is EstadoCobro.APROBADO
