"""Adaptador PostgreSQL del repositorio de mensajes de `conversational`.

Salió de `repositories.py`, que llegó al tope de 400 líneas (`CLAUDE.md` §5). Las mismas
convenciones: mapeo a mano en los dos sentidos (R1) y `empresa_id` nunca en un `WHERE` porque RLS
ya acota.

**`buscar_por_externo_id` es la idempotencia del webhook de Meta** y también la forma de encontrar
el mensaje al que se refiere un callback de estado (`statuses[]`, U7).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.conversational.domain.conversacion import (
    DireccionMensaje,
    EstadoEntrega,
    Intencion,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.infrastructure.models import MensajeORM
from cheatsheet.shared.empresa import EmpresaId


class RepositorioMensajePostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, mensaje: Mensaje) -> None:
        self._sesion.add(_mensaje_a_fila(mensaje, MensajeORM()))
        await self._sesion.flush()

    async def guardar(self, mensaje: Mensaje) -> None:
        fila = await self._sesion.get(MensajeORM, mensaje.id)
        if fila is None:
            raise LookupError(f"El mensaje {mensaje.id} no existe para esta empresa")
        _mensaje_a_fila(mensaje, fila)
        await self._sesion.flush()

    async def buscar_por_externo_id(self, externo_id: str) -> Mensaje | None:
        sentencia = select(MensajeORM).where(MensajeORM.externo_id == externo_id)
        fila = (await self._sesion.execute(sentencia)).scalars().first()
        return _mensaje_a_dominio(fila) if fila is not None else None

    async def del_hilo(self, conversacion_id: UUID) -> list[Mensaje]:
        sentencia = (
            select(MensajeORM)
            .where(MensajeORM.conversacion_id == conversacion_id)
            .order_by(MensajeORM.momento)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_mensaje_a_dominio(fila) for fila in filas]


def _mensaje_a_dominio(fila: MensajeORM) -> Mensaje:
    return Mensaje(
        id=fila.id,
        conversacion_id=fila.conversacion_id,
        empresa_id=EmpresaId(fila.empresa_id),
        direccion=DireccionMensaje(fila.direccion),
        tipo_contenido=TipoContenido(fila.tipo_contenido),
        contenido=fila.contenido or "",
        momento=fila.momento,
        intencion=Intencion(fila.intencion) if fila.intencion else None,
        estado_entrega=EstadoEntrega(fila.estado_entrega) if fila.estado_entrega else None,
        origen=OrigenDelMensaje(fila.origen) if fila.origen else None,
        externo_id=fila.externo_id,
    )


def _mensaje_a_fila(mensaje: Mensaje, fila: MensajeORM) -> MensajeORM:
    fila.id = mensaje.id
    fila.conversacion_id = mensaje.conversacion_id
    fila.empresa_id = mensaje.empresa_id
    fila.direccion = mensaje.direccion.value
    fila.tipo_contenido = mensaje.tipo_contenido.value
    fila.contenido = mensaje.contenido
    fila.intencion = mensaje.intencion.value if mensaje.intencion else None
    fila.estado_entrega = mensaje.estado_entrega.value if mensaje.estado_entrega else None
    fila.origen = mensaje.origen.value if mensaje.origen else None
    fila.externo_id = mensaje.externo_id
    fila.momento = mensaje.momento
    return fila


__all__ = ["RepositorioMensajePostgres"]
