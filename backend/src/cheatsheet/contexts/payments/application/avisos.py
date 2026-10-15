"""`AvisarPagoConfirmado` — decirle al cliente que su pago llegó (HU-E8-04 RN-01).

Cuando el webhook de MercadoPago aprueba un cobro, el cliente recibe por WhatsApp una confirmación
inmediata. Este caso de uso toma el cobro ya aprobado, pide el contacto del cliente y se lo pasa al
puerto de aviso; **qué canal, qué plantilla y dónde queda registrado el mensaje** lo decide el
adaptador y la raíz de composición (ADR-0011), no `payments`.

**Nunca levanta.** El pago ya está guardado y confirmado cuando esto corre (el router lo dispara
después del commit): ningún fallo del aviso, ni del canal ni de la base, puede deshacerlo ni hacer
que MercadoPago reintente. Un fallo es un log con la clase de la excepción, nunca su texto ni el
teléfono (`CLAUDE.md` §5). El aviso **no se reintenta**: queda `FALLIDO` en el hilo del cliente.

**Sin teléfono no hay a quién escribirle.** Un cliente sin WhatsApp registrado no es un error.
"""

from __future__ import annotations

from cheatsheet.contexts.payments.application.ports_envio import (
    DatosDeAvisoDePago,
    PortAvisoDePago,
    PortContactoDeCliente,
)
from cheatsheet.contexts.payments.domain.cobro import Cobro
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)


class AvisarPagoConfirmado:
    """Avisa al cliente de un cobro aprobado. Idempotencia: la garantiza quien lo dispara."""

    def __init__(self, *, contactos: PortContactoDeCliente, aviso: PortAvisoDePago) -> None:
        self._contactos = contactos
        self._aviso = aviso

    async def ejecutar(self, *, cobro: Cobro) -> None:
        try:
            contacto = await self._contactos.contacto_de(cobro.cliente_id)
            if contacto is None:
                logger.info("aviso_de_pago_sin_telefono", cobro_id=str(cobro.id))
                return
            await self._aviso.avisar(
                DatosDeAvisoDePago(
                    cobro_id=cobro.id,
                    cliente_id=cobro.cliente_id,
                    nombre=contacto.nombre,
                    telefono=contacto.telefono,
                    concepto=cobro.descripcion,
                    monto=cobro.monto,
                )
            )
        except Exception as exc:  # noqa: BLE001 — ver el docstring del módulo
            # Acotado por el motivo: **nada del aviso puede voltear un pago ya confirmado**. El
            # puerto lo implementan adaptadores que levantan lo que su SDK levante. Solo la clase
            # de la excepción, nunca su texto: puede traer el número.
            logger.warning(
                "aviso_de_pago_fallido", cobro_id=str(cobro.id), causa=type(exc).__name__
            )


__all__ = ["AvisarPagoConfirmado"]
