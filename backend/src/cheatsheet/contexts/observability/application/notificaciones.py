"""El centro de notificaciones (HU-E11-03) y quién produce lo que muestra.

**Lo que se ve acá es lo que el sistema decidió que alguien tiene que mirar.** No es un feed
de todo lo que pasó —para eso está la bitácora— sino la lista corta de lo que pide atención:
una tarea que se agotó, una operación que falló, una integración que se cayó.

Tres decisiones:

- **Quién recibe qué sale de las preferencias del usuario** (RN-02), no de su rol. Alguien
  puede querer enterarse de las fallas de sincronización y no de las de facturación, y eso ya
  se configura desde el épico 1. `PortDestinatarios` es lo que lo pregunta.

- **Notificar no puede romper la operación que la produjo.** `NotificarPorEventos` corre como
  suscriptor del mismo publicador que la bitácora, y un fallo suyo se registra y se traga: un
  cobro confirmado no se deshace porque no se pudo escribir un aviso en el panel. Es la misma
  regla que D33 y D48, aplicada al canal más barato de todos.

- **Sólo se notifica lo que salió mal.** Un aviso por cada operación exitosa es un centro de
  notificaciones que nadie mira, y un centro que nadie mira es peor que ninguno: hace que la
  vez que sí importaba pase desapercibida entre doscientas que no.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from cheatsheet.contexts.observability.application.errors import NotificacionInexistente
from cheatsheet.contexts.observability.application.ports import (
    PortDestinatarios,
    PortRepositorioNotificaciones,
)
from cheatsheet.contexts.observability.domain.notificacion import Notificacion, Severidad
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import UsuarioId
from cheatsheet.shared.events import EventoDeDominio

logger = obtener_logger(__name__)

#: De qué módulo viene cada categoría de suscripción.
#:
#: Las categorías son las de `identity` (HU-E1-07) y los módulos son los de la bitácora: son
#: dos vocabularios distintos —uno de negocio, otro técnico— y esta tabla es la única
#: traducción entre ellos. Escrita una vez, acá, en vez de repartida en cada emisor.
CATEGORIA_DE: dict[Modulo, str] = {
    Modulo.BILLING: "FACTURACION",
    Modulo.PAYMENTS: "COBROS",
    Modulo.SPREADSHEET_SYNC: "SINCRONIZACION",
    Modulo.SCHEDULING: "AGENDA",
    Modulo.CONVERSATIONAL: "AGENDA",
    Modulo.INTEGRATIONS: "SISTEMA",
    Modulo.IDENTITY: "SISTEMA",
    Modulo.MASTER_DATA: "SISTEMA",
    Modulo.BUSINESS_CONFIG: "SISTEMA",
    Modulo.OBSERVABILITY: "SISTEMA",
    Modulo.REPORTING: "SISTEMA",
    Modulo.REFERENCE_DATA: "SISTEMA",
}


class ListarNotificaciones:
    """PAN-CFG-NOT (RN-01). Todos los roles leen **su propia** bandeja, incluida Solo Lectura.

    Que Solo Lectura pueda verlas no contradice RN-05: lo que ese rol no tiene son acciones de
    gestión, y marcar como leída una notificación propia no es gestión — es acuse de recibo.
    """

    def __init__(self, notificaciones: PortRepositorioNotificaciones) -> None:
        self._notificaciones = notificaciones

    async def ejecutar(
        self, *, destinatario_id: UsuarioId, solo_no_leidas: bool = False, limite: int = 50
    ) -> list[Notificacion]:
        return await self._notificaciones.listar_de(
            destinatario_id, solo_no_leidas=solo_no_leidas, limite=limite
        )


class ContarNoLeidas:
    """El número que el panel muestra sin abrir la pantalla."""

    def __init__(self, notificaciones: PortRepositorioNotificaciones) -> None:
        self._notificaciones = notificaciones

    async def ejecutar(self, destinatario_id: UsuarioId) -> int:
        return await self._notificaciones.contar_no_leidas(destinatario_id)


class MarcarComoLeida:
    """RN-03. **Sólo sobre la propia**: la bandeja de otro no se toca.

    El destinatario se compara acá y no se delega a RLS, porque RLS acota a la empresa y no a
    la persona: dos operadores de la misma empresa comparten política y no bandeja.
    """

    def __init__(self, notificaciones: PortRepositorioNotificaciones) -> None:
        self._notificaciones = notificaciones

    async def ejecutar(self, *, notificacion_id: UUID, destinatario_id: UsuarioId) -> Notificacion:
        notificacion = await self._notificaciones.buscar_por_id(notificacion_id)
        if notificacion is None or notificacion.destinatario_id != destinatario_id:
            # La misma respuesta para «no existe» y «no es tuya», por lo mismo que en el resto
            # del sistema: distinguirlas diría que el id de una notificación ajena es real.
            raise NotificacionInexistente("La notificación no existe")
        notificacion.marcar_leida()
        await self._notificaciones.guardar(notificacion)
        return notificacion


class NotificarPorEventos:
    """Suscriptor: convierte en notificaciones los eventos que salieron mal.

    Se engancha al mismo publicador que la bitácora, en el composition root, y por eso corre
    dentro de la transacción de la operación que lo produjo. Que **no la rompa** es
    responsabilidad de esta clase: ver el docstring del módulo.
    """

    def __init__(
        self,
        *,
        notificaciones: PortRepositorioNotificaciones,
        destinatarios: PortDestinatarios,
    ) -> None:
        self._notificaciones = notificaciones
        self._destinatarios = destinatarios

    async def manejar(self, evento: EventoDeDominio) -> None:
        if not isinstance(evento, EventoAuditable) or evento.resultado is not Resultado.ERROR:
            return
        try:
            await self._crear(evento)
        except Exception:  # noqa: BLE001 -- ver el docstring del módulo
            # Acotada por el motivo y no por el tipo: lo que no puede pasar es que un fallo
            # escribiendo un aviso deshaga la operación que el aviso describe. Se registra con
            # el evento para que el fallo no sea invisible.
            logger.warning("notificacion_no_creada", evento_id=str(evento.evento_id))

    async def _crear(self, evento: EventoAuditable) -> None:
        categoria = CATEGORIA_DE[evento.modulo]
        for destinatario_id in await self._destinatarios.suscriptos_a(categoria):
            await self._notificaciones.agregar(
                Notificacion(
                    id=uuid4(),
                    empresa_id=evento.empresa_id,
                    destinatario_id=destinatario_id,
                    categoria=categoria,
                    # Alta porque es un error: la severidad la decide quien notifica, y lo que
                    # falló en nombre de la empresa es lo que hay que mirar hoy.
                    severidad=Severidad.ALTA,
                    cuerpo=f"«{evento.accion}» falló sobre {evento.entidad_afectada}.",
                    created_at=evento.ocurrido_en,
                )
            )


__all__ = [
    "CATEGORIA_DE",
    "ContarNoLeidas",
    "ListarNotificaciones",
    "MarcarComoLeida",
    "NotificarPorEventos",
]
