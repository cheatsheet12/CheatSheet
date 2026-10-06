"""`SalidaAlCliente` — mandar un mensaje y guardarlo.

Salió de `agente.py` tal cual (T13 del plan de la unidad): lo usan el agente y los pasos de turnos,
y que viva en el agente obligaba a que todos lo importaran de ahí.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.conversational.application.ports import (
    PortMensajeria,
    PortRepositorioMensaje,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    DireccionMensaje,
    EstadoEntrega,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.shared.empresa import EmpresaId


class SalidaAlCliente:
    """Por dónde sale lo que el agente le dice al cliente, y cómo queda guardado."""

    def __init__(self, *, mensajes: PortRepositorioMensaje, mensajeria: PortMensajeria) -> None:
        self._mensajes = mensajes
        self._mensajeria = mensajeria

    async def responder(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        telefono: str,
        texto: str,
        ahora: datetime,
    ) -> str | None:
        """Manda el mensaje y lo guarda. **Un fallo de WhatsApp no voltea lo que ya pasó.**

        Un turno reservado sigue reservado aunque la confirmación no salga; lo contrario
        dejaría al negocio sin poder operar cuando Meta tiene un problema. Es la misma decisión
        D33 del épico 7.
        """
        externo_id: str | None = None
        estado = EstadoEntrega.FALLIDO
        try:
            externo_id = await self._mensajeria.enviar(telefono=telefono, texto=texto)
            estado = EstadoEntrega.ENVIADO
        except Exception as fallo:  # noqa: BLE001 — ver abajo
            # `Exception` es lo que `CLAUDE.md` §5 prohíbe en general, y acá está acotado por
            # el motivo: **ningún fallo del canal puede revertir la operación**. El puerto lo
            # implementan adaptadores que pueden levantar lo que el SDK de turno levante, y
            # enumerarlos acá acoplaría este caso de uso a su infraestructura.
            estado = EstadoEntrega.FALLIDO
            del fallo
        await self._mensajes.agregar(
            Mensaje(
                id=uuid4(),
                conversacion_id=conversacion.id,
                empresa_id=empresa_id,
                direccion=DireccionMensaje.SALIENTE,
                tipo_contenido=TipoContenido.TEXTO,
                contenido=texto,
                momento=ahora,
                origen=OrigenDelMensaje.AGENTE,
                estado_entrega=estado,
                externo_id=externo_id,
            )
        )
        return texto if estado is EstadoEntrega.ENVIADO else None


__all__ = ["SalidaAlCliente"]
