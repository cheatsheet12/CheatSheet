"""Adaptador PostgreSQL de `PortRepositorioReglas`.

Las dos convenciones de siempre: el mapeo se escribe a mano en los dos sentidos para que el
dominio no cargue una dependencia de framework (R1), y `empresa_id` nunca llega a un `WHERE`
porque Row-Level Security ya acota la sentencia.

**No hay `eliminar`.** RN-04 pide desactivar, y una regla borrada deja la bitacora apuntando a
algo que ya no existe.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio, TipoRegla
from cheatsheet.contexts.business_config.infrastructure.models import ReglaDeNegocioORM
from cheatsheet.shared.empresa import EmpresaId


def _a_dominio(fila: ReglaDeNegocioORM) -> ReglaDeNegocio:
    return ReglaDeNegocio(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        tipo=TipoRegla(fila.tipo),
        configuracion=dict(fila.configuracion or {}),
        created_at=fila.created_at,
        prioridad=fila.prioridad,
        activa=fila.activa,
        updated_at=fila.updated_at,
    )


class RepositorioReglasPostgres:
    """Reglas de negocio, sobre PostgreSQL."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, regla: ReglaDeNegocio) -> None:
        self._sesion.add(
            ReglaDeNegocioORM(
                id=regla.id,
                empresa_id=regla.empresa_id,
                tipo=regla.tipo.value,
                configuracion=dict(regla.configuracion),
                prioridad=regla.prioridad,
                activa=regla.activa,
                created_at=regla.created_at,
                updated_at=regla.updated_at,
            )
        )
        await self._sesion.flush()

    async def guardar(self, regla: ReglaDeNegocio) -> None:
        fila = await self._sesion.get(ReglaDeNegocioORM, regla.id)
        if fila is None:
            raise LookupError(f"La regla {regla.id} no existe para esta empresa")
        fila.tipo = regla.tipo.value
        # Reasignado y no mutado en el lugar: SQLAlchemy no rastrea los cambios internos de
        # un JSONB, y una configuracion que falla en guardarse es una cadena de recordatorios
        # que sigue corriendo con la parametrizacion vieja.
        fila.configuracion = dict(regla.configuracion)
        fila.prioridad = regla.prioridad
        fila.activa = regla.activa
        fila.updated_at = regla.updated_at
        await self._sesion.flush()

    async def buscar_por_id(self, regla_id: UUID) -> ReglaDeNegocio | None:
        fila = await self._sesion.get(ReglaDeNegocioORM, regla_id)
        return _a_dominio(fila) if fila is not None else None

    async def listar(self, tipo: TipoRegla | None = None) -> list[ReglaDeNegocio]:
        sentencia = select(ReglaDeNegocioORM)
        if tipo is not None:
            sentencia = sentencia.where(ReglaDeNegocioORM.tipo == tipo.value)
        sentencia = sentencia.order_by(
            ReglaDeNegocioORM.prioridad.desc(), ReglaDeNegocioORM.created_at.desc()
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]


__all__ = ["RepositorioReglasPostgres"]
