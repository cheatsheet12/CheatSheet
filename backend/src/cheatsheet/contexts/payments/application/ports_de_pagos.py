"""Puertos de `payments` para los pagos sin imputar.

Salieron de `ports.py` (366 líneas, cerca del tope de 400 de `CLAUDE.md` §5): es un bloque
cohesivo que solo usa el registro de pagos sin imputar.
"""

from __future__ import annotations

from typing import Protocol

from cheatsheet.contexts.payments.domain.pago_sin_imputar import PagoSinImputar


class PortRepositorioPagoSinImputar(Protocol):
    """**Solo agrega y busca**: un pago sin imputar es un hecho, no se edita ni se borra.

    Sin `guardar` ni `eliminar` a propósito, como `PortRepositorioReembolso`: la aplicación solo
    tiene `SELECT` e `INSERT` sobre la tabla.
    """

    async def agregar(self, pago: PagoSinImputar) -> bool:
        """Registra el pago. `True` si lo insertó; `False` si ese `mp_payment_id` ya estaba.

        La unicidad es del índice `(empresa_id, mp_payment_id)` y no de una lectura previa: dos
        notificaciones simultáneas del mismo pago dejan **una** fila, y la que pierde recibe
        `False` en lugar de un error (que MercadoPago reintentaría).
        """
        ...

    async def buscar_por_payment_id(self, payment_id: str) -> PagoSinImputar | None:
        """El pago ya registrado, si lo hay: la primera línea de D20 para estos pagos."""
        ...


__all__ = ["PortRepositorioPagoSinImputar"]
