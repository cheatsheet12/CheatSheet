"""`SalidaAlCliente` — mandar un mensaje y guardarlo.

Salió de `agente.py` tal cual (T13 del plan de la unidad): lo usan el agente y los pasos de turnos,
y que viva en el agente obligaba a que todos lo importaran de ahí.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.conversational.application.errors import motivo_de_falla_de
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
from cheatsheet.shared.externo_id import externo_id_o_ninguno


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
        """Manda el mensaje y lo guarda. Devuelve el texto si salió y `None` si no."""
        saliente = await self.enviar(empresa_id, conversacion, telefono, texto, ahora)
        return texto if saliente.estado_entrega is EstadoEntrega.ENVIADO else None

    async def enviar(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        telefono: str,
        texto: str,
        ahora: datetime,
    ) -> Mensaje:
        """Manda el mensaje, lo guarda y devuelve el saliente. **Un fallo de WhatsApp no voltea
        lo que ya pasó.**

        Un turno reservado sigue reservado aunque la confirmación no salga; lo contrario
        dejaría al negocio sin poder operar cuando Meta tiene un problema. Es la misma decisión
        D33 del épico 7. Quien necesite saber si salió (el uso de una FAQ) mira
        `estado_entrega` del `Mensaje` devuelto.
        """
        externo_id: str | None = None
        motivo: str | None = None
        estado = EstadoEntrega.FALLIDO
        try:
            externo_id = externo_id_o_ninguno(
                await self._mensajeria.enviar(telefono=telefono, texto=texto)
            )
            estado = EstadoEntrega.ENVIADO
        except Exception as fallo:  # noqa: BLE001 — ver abajo
            # `Exception` es lo que `CLAUDE.md` §5 prohíbe en general, y acá está acotado por
            # el motivo: **ningún fallo del canal puede revertir la operación**. El puerto lo
            # implementan adaptadores que pueden levantar lo que el SDK de turno levante, y
            # enumerarlos acá acoplaría este caso de uso a su infraestructura.
            estado = EstadoEntrega.FALLIDO
            motivo = motivo_de_falla_de(fallo)
        mensaje = Mensaje(
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
            motivo_de_falla=motivo,
        )
        await self._mensajes.agregar(mensaje)
        return mensaje


__all__ = ["SalidaAlCliente"]
