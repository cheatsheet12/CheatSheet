"""`RegistrarEstadoDeEntrega` — lo que Meta informa de un mensaje que mandamos (U7, HU-E8-04 RN-04).

Los callbacks `statuses[]` llegan por el webhook y se rutean por el `wamid` del mensaje. Este caso
de uso resuelve el lado de `conversational` (los mensajes del agente y del operador). Sin rol: lo
invoca el webhook, que ya validó la firma y resolvió la empresa.

**Idempotente y monótono**: lo decide `Mensaje.marcar_entrega`. Un callback repetido o fuera de
orden no cambia nada y no escribe. Sin evento de bitácora por callback: serían tres por mensaje.
"""

from __future__ import annotations

from cheatsheet.contexts.conversational.application.ports import PortRepositorioMensaje
from cheatsheet.contexts.conversational.domain.conversacion import EstadoEntrega


class RegistrarEstadoDeEntrega:
    def __init__(self, mensajes: PortRepositorioMensaje) -> None:
        self._mensajes = mensajes

    async def ejecutar(
        self,
        *,
        externo_id: str,
        estado: EstadoEntrega,
        codigo_de_error: str | None = None,
    ) -> bool:
        """Devuelve si el `wamid` es de un mensaje de esta empresa (no si cambió algo).

        `False` significa «no es mío»: el webhook prueba entonces con el otro contexto.
        """
        mensaje = await self._mensajes.buscar_por_externo_id(externo_id)
        if mensaje is None:
            return False
        if mensaje.marcar_entrega(estado, motivo=codigo_de_error):
            await self._mensajes.guardar(mensaje)
        return True


__all__ = ["RegistrarEstadoDeEntrega"]
