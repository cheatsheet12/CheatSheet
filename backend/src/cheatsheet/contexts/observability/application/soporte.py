"""Las solicitudes de soporte (HU-E9-03).

Dos casos de uso y nada más: abrir una y consultar las propias. **El estado lo mueve el equipo
de CheatSheet**, no la empresa (RN-03), así que desde el panel no hay forma de cerrar un
ticket — y por eso este archivo no tiene un `CerrarSolicitud`.

**Sólo el Administrador abre** (el actor de la historia). Un operador que necesita ayuda se la
pide a su administrador, que es quien tiene el contexto de la cuenta y el vínculo comercial.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.observability.application.ports import PortRepositorioSolicitudes
from cheatsheet.contexts.observability.domain.solicitud_de_soporte import (
    PrioridadDeSoporte,
    SolicitudDeSoporte,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

MOTIVO_SOLO_ADMINISTRADOR = "Solo un Administrador puede abrir una solicitud de soporte"


class AbrirSolicitudDeSoporte:
    """HU-E9-03. Queda en estado abierto hasta que soporte la atienda.

    El texto de «el asunto y la descripción son obligatorios» lo levanta el **agregado**, no
    este caso de uso: es una invariante de la entidad, y ponerla acá dejaría la puerta abierta
    a construir una solicitud vacía desde cualquier otro lado.
    """

    def __init__(
        self, *, solicitudes: PortRepositorioSolicitudes, publicador: PublicadorDeEventos
    ) -> None:
        self._solicitudes = solicitudes
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        asunto: str,
        descripcion: str,
        prioridad: PrioridadDeSoporte,
        ahora: datetime,
    ) -> SolicitudDeSoporte:
        if rol is not RolUsuario.ADMINISTRADOR:
            raise EntradaInvalida(MOTIVO_SOLO_ADMINISTRADOR)

        solicitud = SolicitudDeSoporte(
            id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            asunto=asunto,
            descripcion=descripcion,
            prioridad=prioridad,
            created_at=ahora,
            updated_at=ahora,
        )
        await self._solicitudes.agregar(solicitud)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                ocurrido_en=ahora,
                modulo=Modulo.OBSERVABILITY,
                accion="abrir_solicitud_de_soporte",
                entidad_afectada=f"SolicitudDeSoporte:{solicitud.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return solicitud


class ListarSolicitudes:
    """RN-04: «el administrador puede consultar el estado de sus solicitudes abiertas».

    Lista las de la **empresa** y no las de la persona, que es lo que RLS acota y lo que la
    pantalla necesita: dos administradores de la misma empresa no tienen por qué abrir el mismo
    ticket dos veces porque cada uno ve sólo el suyo.
    """

    def __init__(self, solicitudes: PortRepositorioSolicitudes) -> None:
        self._solicitudes = solicitudes

    async def ejecutar(
        self, *, solo_abiertas: bool = False, limite: int = 50
    ) -> list[SolicitudDeSoporte]:
        return await self._solicitudes.listar(solo_abiertas=solo_abiertas, limite=limite)


__all__ = ["MOTIVO_SOLO_ADMINISTRADOR", "AbrirSolicitudDeSoporte", "ListarSolicitudes"]
