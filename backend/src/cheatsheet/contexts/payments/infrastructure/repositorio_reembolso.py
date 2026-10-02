"""Adaptador PostgreSQL de los reembolsos: **solo se agrega** (ADR-0010, punto 4).

Sin `guardar` ni `eliminar`: la aplicacion tiene `SELECT` e `INSERT` sobre `reembolso` y nada
mas, asi que un metodo que actualizara una fila solo podria fallar. Un error se corrige con una
fila negativa que apunta a la anulada.

`empresa_id` nunca va en un `WHERE`: RLS ya acota. El mapeo es a mano en los dos sentidos para
que el dominio no cargue una dependencia de framework (R1).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.payments.domain.reembolso import OrigenDeReembolso, Reembolso
from cheatsheet.contexts.payments.infrastructure.models import ReembolsoORM
from cheatsheet.shared.empresa import EmpresaId, UsuarioId


def _a_dominio(fila: ReembolsoORM) -> Reembolso:
    return Reembolso(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        cobro_id=fila.cobro_id,
        monto=fila.monto,
        fecha_devolucion=fila.fecha_devolucion,
        origen=OrigenDeReembolso(fila.origen),
        created_at=fila.created_at,
        referencia=fila.referencia,
        motivo=fila.motivo,
        corrige_a=fila.corrige_a,
        mp_refund_id=fila.mp_refund_id,
        registrado_por=UsuarioId(fila.registrado_por) if fila.registrado_por else None,
    )


class RepositorioReembolsoPostgres:
    """`PortRepositorioReembolso`, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, reembolso: Reembolso) -> None:
        self._sesion.add(
            ReembolsoORM(
                id=reembolso.id,
                empresa_id=reembolso.empresa_id,
                cobro_id=reembolso.cobro_id,
                monto=reembolso.monto,
                fecha_devolucion=reembolso.fecha_devolucion,
                origen=reembolso.origen.value,
                referencia=reembolso.referencia,
                motivo=reembolso.motivo,
                corrige_a=reembolso.corrige_a,
                mp_refund_id=reembolso.mp_refund_id,
                registrado_por=reembolso.registrado_por,
                created_at=reembolso.created_at,
            )
        )
        await self._sesion.flush()

    async def de_cobro(self, cobro_id: UUID) -> list[Reembolso]:
        sentencia = (
            select(ReembolsoORM)
            .where(ReembolsoORM.cobro_id == cobro_id)
            .order_by(ReembolsoORM.created_at, ReembolsoORM.fecha_devolucion, ReembolsoORM.id)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def buscar_por_id(self, reembolso_id: UUID) -> Reembolso | None:
        fila = await self._sesion.get(ReembolsoORM, reembolso_id)
        return _a_dominio(fila) if fila is not None else None


__all__ = ["RepositorioReembolsoPostgres"]
