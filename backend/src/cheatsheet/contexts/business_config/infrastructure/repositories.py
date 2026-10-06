"""Adaptadores PostgreSQL de `business_config`: reglas y plantillas.

Las dos convenciones de siempre: el mapeo se escribe a mano en los dos sentidos para que el
dominio no cargue una dependencia de framework (R1), y `empresa_id` nunca llega a un `WHERE`
porque Row-Level Security ya acota la sentencia.

**No hay `eliminar`.** RN-04 pide desactivar, y una regla borrada deja la bitacora apuntando a
algo que ya no existe.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.business_config.domain.plantilla import (
    EstadoDeAprobacion,
    PlantillaDeNotificacion,
)
from cheatsheet.contexts.business_config.domain.regla import (
    CanalNotificacion,
    ReglaDeNegocio,
    TipoRegla,
)
from cheatsheet.contexts.business_config.infrastructure.models import (
    PlantillaDeNotificacionORM,
    ReglaDeNegocioORM,
)
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


def _plantilla_a_dominio(fila: PlantillaDeNotificacionORM) -> PlantillaDeNotificacion:
    return PlantillaDeNotificacion(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        codigo=fila.codigo,
        canal=CanalNotificacion(fila.canal),
        idioma=fila.idioma,
        cuerpo=fila.cuerpo,
        estado_aprobacion=EstadoDeAprobacion(fila.estado_aprobacion_meta)
        if fila.estado_aprobacion_meta
        else EstadoDeAprobacion.NO_APLICA,
        created_at=fila.created_at,
        updated_at=fila.updated_at,
    )


def _plantilla_a_fila(
    plantilla: PlantillaDeNotificacion, fila: PlantillaDeNotificacionORM
) -> PlantillaDeNotificacionORM:
    fila.id = plantilla.id
    fila.empresa_id = plantilla.empresa_id
    fila.codigo = plantilla.codigo
    fila.canal = plantilla.canal.value
    fila.idioma = plantilla.idioma
    fila.cuerpo = plantilla.cuerpo
    fila.estado_aprobacion_meta = plantilla.estado_aprobacion.value
    fila.created_at = plantilla.created_at or plantilla.updated_at or datetime.now(tz=UTC)
    fila.updated_at = plantilla.updated_at
    return fila


class RepositorioPlantillasPostgres:
    """Plantillas de notificacion, sobre PostgreSQL. **Sin `eliminar`** — ver el puerto."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, plantilla: PlantillaDeNotificacion) -> None:
        self._sesion.add(_plantilla_a_fila(plantilla, PlantillaDeNotificacionORM()))
        await self._sesion.flush()

    async def guardar(self, plantilla: PlantillaDeNotificacion) -> None:
        fila = await self._sesion.get(PlantillaDeNotificacionORM, plantilla.id)
        if fila is None:
            raise LookupError(f"La plantilla {plantilla.id} no existe para esta empresa")
        _plantilla_a_fila(plantilla, fila)
        await self._sesion.flush()

    async def buscar_por_id(self, plantilla_id: UUID) -> PlantillaDeNotificacion | None:
        fila = await self._sesion.get(PlantillaDeNotificacionORM, plantilla_id)
        return _plantilla_a_dominio(fila) if fila is not None else None

    async def buscar_por_codigo(self, codigo: str) -> PlantillaDeNotificacion | None:
        sentencia = select(PlantillaDeNotificacionORM).where(
            PlantillaDeNotificacionORM.codigo == codigo
        )
        fila = (await self._sesion.execute(sentencia)).scalars().first()
        return _plantilla_a_dominio(fila) if fila is not None else None

    async def listar(self) -> list[PlantillaDeNotificacion]:
        sentencia = select(PlantillaDeNotificacionORM).order_by(PlantillaDeNotificacionORM.codigo)
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_plantilla_a_dominio(fila) for fila in filas]
