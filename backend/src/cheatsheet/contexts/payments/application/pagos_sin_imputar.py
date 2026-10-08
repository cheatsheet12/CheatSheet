"""Registrar un pago aprobado que no se pudo imputar (unidad `pagos-sin-cobro-asociado`).

Antes, un pago sin cobro asociado quedaba en un log `info` y nada más: MercadoPago recibía 200,
no reintentaba y la plata no figuraba en ningún lado. Ahora cada uno es una fila y un evento de
bitácora con `Resultado.ERROR`, que `NotificarPorEventos` convierte en una notificación de
severidad alta: es la única forma de que alguien se entere hoy y no cuando concilie el extracto.

**No guarda ni loguea datos del pagador.** Solo ids (el de MercadoPago y los nuestros) y el
motivo.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.payments.application.ports import PagoRecibido
from cheatsheet.contexts.payments.application.ports_de_pagos import PortRepositorioPagoSinImputar
from cheatsheet.contexts.payments.domain.pago_sin_imputar import MotivoSinImputar, PagoSinImputar
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)


class RegistrarPagoSinImputar:
    """Guarda el pago y avisa. **Idempotente**: el índice único decide quién avisa."""

    def __init__(
        self, *, pagos: PortRepositorioPagoSinImputar, publicador: PublicadorDeEventos
    ) -> None:
        self._pagos = pagos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        pago: PagoRecibido,
        motivo: MotivoSinImputar,
        cobro_id: UUID | None,
        ahora: datetime,
    ) -> bool:
        """`True` si lo registró ahora; `False` si otra notificación ya lo había registrado.

        El evento sale **solo** cuando la fila se insertó: la notificación simultánea que pierde
        el índice único no duplica la alerta.
        """
        registrado = PagoSinImputar(
            id=uuid4(),
            empresa_id=empresa_id,
            mp_payment_id=pago.payment_id,
            motivo=motivo,
            recibido_en=ahora,
            referencia_externa=pago.referencia_externa,
            cobro_id=cobro_id,
            monto=pago.monto,
            fecha_aprobacion=pago.fecha_aprobacion,
        )
        if not await self._pagos.agregar(registrado):
            logger.info("pago_sin_imputar_repetido", payment_id=pago.payment_id)
            return False

        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                # Iniciador Sistema, como el resto de lo que hace el webhook (HS-T1 RN-05).
                usuario_id=None,
                modulo=Modulo.PAYMENTS,
                accion="pago_sin_imputar",
                entidad_afectada=f"PagoSinImputar:{registrado.id}",
                resultado=Resultado.ERROR,
            )
        )
        logger.warning(
            "pago_sin_imputar",
            payment_id=pago.payment_id,
            motivo=motivo.value,
            cobro_id=str(cobro_id) if cobro_id else None,
        )
        return True


__all__ = ["RegistrarPagoSinImputar"]
