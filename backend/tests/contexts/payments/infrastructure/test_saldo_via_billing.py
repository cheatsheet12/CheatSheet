"""El contrato de `SaldoViaBilling`: de quien es el comprobante, que significa `None` y como se
mueve el saldo con un reembolso (tope en el total) y con su correccion (piso en cero).

Se arma con el caso de uso publicado de `billing` y un repositorio en memoria minimo. La barrera
de empresa de verdad (RLS) se prueba contra PostgreSQL en `tests/integracion/`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.billing.application.ports import FiltrosDeComprobante
from cheatsheet.contexts.billing.domain.comprobante import (
    AlicuotaIVA,
    Comprobante,
    ItemDeComprobante,
    Receptor,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import TipoComprobante
from cheatsheet.contexts.payments.infrastructure.saldo import SaldoViaBilling
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())


class ComprobantesEnMemoria:
    """El puerto completo, pero solo `buscar_por_id` tiene comportamiento: es lo que se lee."""

    def __init__(self, *comprobantes: Comprobante) -> None:
        self._por_id = {c.id: c for c in comprobantes}

    async def agregar(self, comprobante: Comprobante) -> None:
        self._por_id[comprobante.id] = comprobante

    async def guardar(self, comprobante: Comprobante) -> None:
        self._por_id[comprobante.id] = comprobante

    async def listar(self, filtros: FiltrosDeComprobante) -> list[Comprobante]:
        del filtros
        return list(self._por_id.values())

    async def notas_de(self, origen_id: UUID) -> list[Comprobante]:
        del origen_id
        return []

    async def en_vuelo(self, *, anteriores_a: datetime) -> list[Comprobante]:
        del anteriores_a
        return []

    async def buscar_por_id(self, comprobante_id: UUID) -> Comprobante | None:
        return self._por_id.get(comprobante_id)


def _comprobante(cliente_id: UUID) -> Comprobante:
    return Comprobante(
        id=uuid4(),
        empresa_id=EMPRESA,
        cliente_id=cliente_id,
        punto_de_venta_id=uuid4(),
        tipo=TipoComprobante.FACTURA_A,
        receptor=Receptor(
            nombre="Acme SA", cuit="30712345674", condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO
        ),
        emisor_condicion_iva=CondicionIVA.RESPONSABLE_INSCRIPTO,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_cliente_de_devuelve_el_cliente_del_comprobante() -> None:
    cliente = uuid4()
    comprobante = _comprobante(cliente)
    saldo = SaldoViaBilling(ComprobantesEnMemoria(comprobante))

    assert await saldo.cliente_de(comprobante.id) == cliente


async def test_cliente_de_devuelve_none_si_el_comprobante_no_existe() -> None:
    saldo = SaldoViaBilling(ComprobantesEnMemoria())

    assert await saldo.cliente_de(uuid4()) is None


def _con_saldo(saldo: str, *, total: str = "1000.00") -> Comprobante:
    comprobante = _comprobante(uuid4())
    comprobante.agregar_item(
        ItemDeComprobante(
            id=uuid4(),
            descripcion="Consulta",
            cantidad=Decimal("1"),
            precio_unitario=Decimal(total),
            alicuota_iva=AlicuotaIVA.CERO,
        )
    )
    comprobante.saldo_pendiente = Decimal(saldo)
    return comprobante


async def test_un_reembolso_sube_el_saldo_del_comprobante() -> None:
    """Caso 16."""
    comprobante = _con_saldo("600.00")
    saldo = SaldoViaBilling(ComprobantesEnMemoria(comprobante))

    await saldo.registrar_reembolso(comprobante.id, Decimal("250.00"))

    assert comprobante.saldo_pendiente == Decimal("850.00")


async def test_un_reembolso_nunca_deja_el_saldo_por_encima_del_total() -> None:
    """Tope en el total (H11): `registrar_cobro` recorta en cero, asi que sumar sin tope podria
    dejar un saldo mayor a lo facturado."""
    comprobante = _con_saldo("900.00")
    saldo = SaldoViaBilling(ComprobantesEnMemoria(comprobante))

    await saldo.registrar_reembolso(comprobante.id, Decimal("400.00"))

    assert comprobante.saldo_pendiente == Decimal("1000.00")


async def test_una_correccion_negativa_baja_el_saldo_con_piso_en_cero() -> None:
    comprobante = _con_saldo("100.00")
    saldo = SaldoViaBilling(ComprobantesEnMemoria(comprobante))

    await saldo.registrar_reembolso(comprobante.id, Decimal("-300.00"))

    assert comprobante.saldo_pendiente == Decimal("0.00")


async def test_registrar_un_reembolso_guarda_el_comprobante() -> None:
    comprobante = _con_saldo("600.00")
    comprobantes = ComprobantesEnMemoria(comprobante)
    saldo = SaldoViaBilling(comprobantes)

    await saldo.registrar_reembolso(comprobante.id, Decimal("100.00"))

    guardado = await comprobantes.buscar_por_id(comprobante.id)
    assert guardado is not None
    assert guardado.saldo_pendiente == Decimal("700.00")
