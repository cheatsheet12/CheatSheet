"""Adaptador PostgreSQL de los pagos sin imputar: **solo se agrega**.

Sin `guardar` ni `eliminar`: la aplicación tiene `SELECT` e `INSERT` sobre `pago_sin_imputar` y
nada más (migración 0036), así que un método que actualizara una fila solo podría fallar.

`empresa_id` nunca va en un `WHERE`: RLS ya acota. El mapeo es a mano en los dos sentidos para
que el dominio no cargue una dependencia de framework (R1).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.payments.domain.pago_sin_imputar import MotivoSinImputar, PagoSinImputar
from cheatsheet.contexts.payments.infrastructure.models import PagoSinImputarORM
from cheatsheet.shared.empresa import EmpresaId

#: El nombre del índice único de la migración 0036, para traducir **solo** ese `IntegrityError`.
INDICE_DE_PAGO = "uq_pago_sin_imputar_payment"


def _a_dominio(fila: PagoSinImputarORM) -> PagoSinImputar:
    return PagoSinImputar(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        mp_payment_id=fila.mp_payment_id,
        motivo=MotivoSinImputar(fila.motivo),
        recibido_en=fila.recibido_en,
        referencia_externa=fila.referencia_externa,
        cobro_id=fila.cobro_id,
        monto=fila.monto,
        fecha_aprobacion=fila.fecha_aprobacion,
    )


class RepositorioPagoSinImputarPostgres:
    """`PortRepositorioPagoSinImputar`, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, pago: PagoSinImputar) -> bool:
        # **El `flush` va en su propio savepoint.** En PostgreSQL un `IntegrityError` aborta la
        # transacción entera: sin el savepoint, atrapar el duplicado dejaría inservible la sesión
        # y el webhook terminaría en 500 (MercadoPago reintentaría una notificación ya guardada).
        try:
            async with self._sesion.begin_nested():
                self._sesion.add(
                    PagoSinImputarORM(
                        id=pago.id,
                        empresa_id=pago.empresa_id,
                        mp_payment_id=pago.mp_payment_id,
                        referencia_externa=pago.referencia_externa,
                        cobro_id=pago.cobro_id,
                        motivo=pago.motivo.value,
                        monto=pago.monto,
                        fecha_aprobacion=pago.fecha_aprobacion,
                        recibido_en=pago.recibido_en,
                    )
                )
                await self._sesion.flush()
        except IntegrityError as exc:
            # Dos notificaciones simultáneas del mismo pago: la segunda pierde el índice único y
            # eso **no es un error**, es "ya registrado". Solo ese índice, por nombre: cualquier
            # otra violación (el `CHECK` del motivo, una FK) sigue siendo un error de verdad.
            if INDICE_DE_PAGO not in str(exc.orig):
                raise
            return False
        return True

    async def buscar_por_payment_id(self, payment_id: str) -> PagoSinImputar | None:
        sentencia = select(PagoSinImputarORM).where(PagoSinImputarORM.mp_payment_id == payment_id)
        fila = (await self._sesion.execute(sentencia)).scalar_one_or_none()
        return _a_dominio(fila) if fila is not None else None


__all__ = ["RepositorioPagoSinImputarPostgres"]
