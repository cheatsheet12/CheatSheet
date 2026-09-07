"""PostgreSQL adapter for `PortRepositorioParametros`.

**No `empresa_id` filter anywhere, and no RLS to lean on either.** Every other repository
in this system relies on the policy; this table has none, because the catalogue is the same
for all tenants. That makes the absence deliberate rather than forgotten, and it is why the
application role holds `SELECT` and nothing else — see migration 0016.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.reference_data.domain.parametro import (
    ParametroFiscal,
    TipoCatalogoFiscal,
)
from cheatsheet.contexts.reference_data.infrastructure.models import ParametroFiscalORM


def _a_dominio(fila: ParametroFiscalORM) -> ParametroFiscal:
    return ParametroFiscal(
        id=fila.id,
        tipo=TipoCatalogoFiscal(fila.tipo),
        codigo=fila.codigo,
        valor=fila.valor,
        fecha_desde=fila.fecha_desde,
        fecha_hasta=fila.fecha_hasta,
    )


class RepositorioParametrosPostgres:
    """The fiscal catalogue, backed by PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, parametro: ParametroFiscal) -> None:
        self._sesion.add(
            ParametroFiscalORM(
                id=parametro.id,
                tipo=parametro.tipo.value,
                codigo=parametro.codigo,
                valor=parametro.valor,
                fecha_desde=parametro.fecha_desde,
                fecha_hasta=parametro.fecha_hasta,
            )
        )
        await self._sesion.flush()

    async def cerrar(self, parametro: ParametroFiscal) -> None:
        """Only `fecha_hasta` is written. The rest of a closed version is history."""
        fila = await self._sesion.get(ParametroFiscalORM, parametro.id)
        if fila is None:
            raise LookupError(f"El parametro fiscal {parametro.id} no existe")
        fila.fecha_hasta = parametro.fecha_hasta
        await self._sesion.flush()

    async def vigentes(self, *, tipo: TipoCatalogoFiscal | None = None) -> list[ParametroFiscal]:
        sentencia = select(ParametroFiscalORM).where(ParametroFiscalORM.fecha_hasta.is_(None))
        if tipo is not None:
            sentencia = sentencia.where(ParametroFiscalORM.tipo == tipo.value)
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def buscar_vigente_a(
        self, *, tipo: TipoCatalogoFiscal, codigo: str, fecha: date
    ) -> ParametroFiscal | None:
        sentencia = (
            select(ParametroFiscalORM)
            .where(ParametroFiscalORM.tipo == tipo.value)
            .where(ParametroFiscalORM.codigo == codigo)
            .where(ParametroFiscalORM.fecha_desde <= fecha)
            .where(
                (ParametroFiscalORM.fecha_hasta.is_(None))
                | (ParametroFiscalORM.fecha_hasta >= fecha)
            )
        )
        fila = (await self._sesion.execute(sentencia)).scalars().first()
        return _a_dominio(fila) if fila is not None else None
