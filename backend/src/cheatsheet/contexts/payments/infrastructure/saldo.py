"""ACL sobre `billing`: el saldo de un comprobante, en el vocabulario de `payments`.

Cuatro operaciones y ninguna mas: cuanto falta, de quien es, descontá esto y devolvé esto. `payments` no ve el comprobante,
ni sus items, ni su CAE — pregunta lo unico que necesita para HU-E6-06.

**Lo que esta capa decide es que significa `None`.** `billing` puede no encontrar el
comprobante porque no existe o porque es de otra empresa; bajo RLS son la misma respuesta y
para el cobro las dos significan lo mismo: no hay contra que asociarlo.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from cheatsheet.contexts.billing.application.consultas import VerComprobante
from cheatsheet.contexts.billing.application.errors import ComprobanteInexistente
from cheatsheet.contexts.billing.application.ports import PortRepositorioComprobante


class SaldoViaBilling:
    """`PortSaldoDeComprobante`, respaldado por el repositorio publicado de `billing`."""

    def __init__(self, comprobantes: PortRepositorioComprobante) -> None:
        self._comprobantes = comprobantes

    async def saldo_pendiente(self, comprobante_id: UUID) -> Decimal | None:
        try:
            comprobante = await VerComprobante(self._comprobantes).ejecutar(comprobante_id)
        except ComprobanteInexistente:
            return None
        return comprobante.saldo_pendiente

    async def cliente_de(self, comprobante_id: UUID) -> UUID | None:
        """El cliente del comprobante. `None` cuando no existe o es de otra empresa."""
        try:
            comprobante = await VerComprobante(self._comprobantes).ejecutar(comprobante_id)
        except ComprobanteInexistente:
            return None
        return comprobante.cliente_id

    async def registrar_cobro(self, comprobante_id: UUID, monto: Decimal) -> None:
        """Reduce el saldo pendiente (HU-E6-06 RN-03). **Solo al aprobarse el cobro** (D26).

        Piso en cero y no negativo: dos cobros parciales que juntos superen el saldo son un
        error del que ya se defiende `GenerarCobro`, y si aun asi llegara hasta aca, un saldo
        negativo en un comprobante es peor que uno saldado — se lee como una deuda al reves.
        """
        comprobante = await VerComprobante(self._comprobantes).ejecutar(comprobante_id)
        restante = comprobante.saldo_pendiente - monto
        comprobante.saldo_pendiente = max(restante, Decimal("0.00"))
        await self._comprobantes.guardar(comprobante)

    async def registrar_reembolso(self, comprobante_id: UUID, monto: Decimal) -> None:
        """Devuelve saldo por un reembolso (`monto` > 0) o lo baja por su correccion (< 0).

        **Tope en el total del comprobante y piso en cero.** `registrar_cobro` recorta en cero,
        asi que el saldo puede haber quedado por debajo de lo que un cobro le resto: sumar sin
        tope podria dejarlo por encima de lo facturado, que es un saldo que miente. Con el tope no
        siempre vuelve exactamente a lo que era si antes se recorto (H11); se anota, no se
        corrige. No se emite ninguna nota de credito: solo se ajusta el saldo (RN-09, D89).
        """
        comprobante = await VerComprobante(self._comprobantes).ejecutar(comprobante_id)
        ajustado = comprobante.saldo_pendiente + monto
        comprobante.saldo_pendiente = min(max(ajustado, Decimal("0.00")), comprobante.total)
        await self._comprobantes.guardar(comprobante)


__all__ = ["SaldoViaBilling"]
