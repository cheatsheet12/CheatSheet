"""Adaptadores PostgreSQL del centro de notificaciones y de las solicitudes de soporte.

Las convenciones de siempre: mapeo a mano en los dos sentidos para que el dominio no cargue una
dependencia de framework (R1), y `empresa_id` nunca en un `WHERE` porque RLS ya acota.

**`destinatario_id` sí va en el `WHERE`**, y no es una excepción a la regla anterior: RLS acota
a la empresa y adentro de una empresa hay varias personas. Una bandeja de entrada que muestre
los avisos de un compañero no es un problema de aislamiento entre inquilinos — es una pantalla
que no sirve.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.observability.domain.notificacion import Notificacion, Severidad
from cheatsheet.contexts.observability.domain.solicitud_de_soporte import (
    EstadoDeSolicitud,
    PrioridadDeSoporte,
    SolicitudDeSoporte,
)
from cheatsheet.contexts.observability.infrastructure.models import (
    NotificacionORM,
    SolicitudDeSoporteORM,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

#: Los estados que cuentan como «abierta» para RN-04 de HU-E9-03.
ESTADOS_ABIERTOS = (EstadoDeSolicitud.ABIERTA.value, EstadoDeSolicitud.EN_REVISION.value)


def _a_notificacion(fila: NotificacionORM) -> Notificacion:
    return Notificacion(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        destinatario_id=UsuarioId(fila.destinatario_id),
        categoria=fila.categoria,
        severidad=Severidad(fila.severidad),
        cuerpo=fila.cuerpo,
        plantilla_id=fila.plantilla_id,
        leida=fila.leida,
        created_at=fila.created_at,
    )


class RepositorioNotificacionesPostgres:
    """`PortRepositorioNotificaciones`. Sin `eliminar`: una notificación leída queda."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, notificacion: Notificacion) -> None:
        self._sesion.add(
            NotificacionORM(
                id=notificacion.id,
                empresa_id=notificacion.empresa_id,
                destinatario_id=notificacion.destinatario_id,
                plantilla_id=notificacion.plantilla_id,
                categoria=notificacion.categoria,
                severidad=notificacion.severidad.value,
                cuerpo=notificacion.cuerpo,
                leida=notificacion.leida,
                created_at=notificacion.created_at,
            )
        )
        await self._sesion.flush()

    async def guardar(self, notificacion: Notificacion) -> None:
        fila = await self._sesion.get(NotificacionORM, notificacion.id)
        if fila is None:
            raise LookupError(f"La notificación {notificacion.id} no existe para esta empresa")
        # Sólo `leida`: es lo único que cambia en la vida de una notificación. Un `guardar`
        # que reescribiera el cuerpo permitiría corregir un aviso después de que alguien lo
        # leyó, que es la clase de cosa que hace que un registro deje de servir de registro.
        fila.leida = notificacion.leida
        await self._sesion.flush()

    async def buscar_por_id(self, notificacion_id: UUID) -> Notificacion | None:
        fila = await self._sesion.get(NotificacionORM, notificacion_id)
        return _a_notificacion(fila) if fila is not None else None

    async def listar_de(
        self, destinatario_id: UsuarioId, *, solo_no_leidas: bool = False, limite: int = 50
    ) -> list[Notificacion]:
        consulta = select(NotificacionORM).where(NotificacionORM.destinatario_id == destinatario_id)
        if solo_no_leidas:
            consulta = consulta.where(NotificacionORM.leida.is_(False))
        consulta = consulta.order_by(NotificacionORM.created_at.desc()).limit(limite)
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_notificacion(fila) for fila in filas]

    async def contar_no_leidas(self, destinatario_id: UsuarioId) -> int:
        consulta = (
            select(func.count())
            .select_from(NotificacionORM)
            .where(
                NotificacionORM.destinatario_id == destinatario_id,
                NotificacionORM.leida.is_(False),
            )
        )
        return int((await self._sesion.execute(consulta)).scalar_one())


def _a_solicitud(fila: SolicitudDeSoporteORM) -> SolicitudDeSoporte:
    return SolicitudDeSoporte(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        usuario_id=UsuarioId(fila.usuario_id),
        asunto=fila.asunto,
        descripcion=fila.descripcion,
        prioridad=PrioridadDeSoporte(fila.prioridad),
        estado=EstadoDeSolicitud(fila.estado),
        created_at=fila.created_at,
        updated_at=fila.updated_at,
    )


class RepositorioSolicitudesPostgres:
    """`PortRepositorioSolicitudes`. Sin `eliminar`: un pedido de ayuda no se borra."""

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, solicitud: SolicitudDeSoporte) -> None:
        self._sesion.add(
            SolicitudDeSoporteORM(
                id=solicitud.id,
                empresa_id=solicitud.empresa_id,
                usuario_id=solicitud.usuario_id,
                asunto=solicitud.asunto,
                descripcion=solicitud.descripcion,
                prioridad=solicitud.prioridad.value,
                estado=solicitud.estado.value,
                created_at=solicitud.created_at,
                updated_at=solicitud.updated_at or solicitud.created_at,
            )
        )
        await self._sesion.flush()

    async def guardar(self, solicitud: SolicitudDeSoporte) -> None:
        fila = await self._sesion.get(SolicitudDeSoporteORM, solicitud.id)
        if fila is None:
            raise LookupError(f"La solicitud {solicitud.id} no existe para esta empresa")
        # El estado y su momento: es lo único que el equipo de soporte mueve. El asunto y la
        # descripción son lo que la empresa reportó, y eso no se reescribe.
        fila.estado = solicitud.estado.value
        # `or created_at`: la columna es NOT NULL y el agregado admite `None` mientras la
        # solicitud vive en memoria. Quien la guarda siempre pasó por `cambiar_estado`, que lo
        # completa; esto es el piso que hace que el tipo cierre sin un `assert` en producción.
        fila.updated_at = solicitud.updated_at or fila.created_at
        await self._sesion.flush()

    async def buscar_por_id(self, solicitud_id: UUID) -> SolicitudDeSoporte | None:
        fila = await self._sesion.get(SolicitudDeSoporteORM, solicitud_id)
        return _a_solicitud(fila) if fila is not None else None

    async def listar(
        self, *, solo_abiertas: bool = False, limite: int = 50
    ) -> list[SolicitudDeSoporte]:
        consulta = select(SolicitudDeSoporteORM)
        if solo_abiertas:
            consulta = consulta.where(SolicitudDeSoporteORM.estado.in_(ESTADOS_ABIERTOS))
        consulta = consulta.order_by(SolicitudDeSoporteORM.created_at.desc()).limit(limite)
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_a_solicitud(fila) for fila in filas]


__all__ = [
    "ESTADOS_ABIERTOS",
    "RepositorioNotificacionesPostgres",
    "RepositorioSolicitudesPostgres",
]
