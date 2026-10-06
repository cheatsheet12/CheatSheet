"""`TurnosPorWhatsApp` — la fachada que el agente usa para todo lo que sea un turno.

El agente (`ProcesarMensajeEntrante`) ya tiene demasiado que decidir. Esta fachada le deja dos
llamadas y nada más (T13 del plan de la unidad):

- **`continuar`** — antes de interpretar: si hay un diálogo pendiente y el mensaje **es una
  respuesta** («el primero», «sí», «a las 10:30»), se resuelve acá, sin llamar al modelo.
- **`atender`** — después de interpretar: la intención `TURNO` se reparte por la acción que el
  modelo extrajo —reservar, cancelar o reprogramar—, que nunca es una acción que el modelo ejecute.

`reprogramar` no tiene historia detrás: el agente ofrece un asesor, como con `PAGO`.
"""

from __future__ import annotations

from cheatsheet.contexts.conversational.application.cancelacion_por_whatsapp import (
    CancelacionPorWhatsApp,
)
from cheatsheet.contexts.conversational.application.contexto import (
    ContextoDelMensaje,
    Desenlace,
)
from cheatsheet.contexts.conversational.application.ports import (
    Lectura,
    PortAgenda,
    PortRepositorioConversacion,
)
from cheatsheet.contexts.conversational.application.reserva_por_whatsapp import (
    PEDIDO_VACIO,
    ReservaPorWhatsApp,
)
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.domain.conversacion import MENSAJE_OFRECER_ASESOR
from cheatsheet.contexts.conversational.domain.dialogo import Dialogo, PasoDelDialogo
from cheatsheet.contexts.conversational.domain.pedido_de_turno import AccionDeTurno
from cheatsheet.contexts.conversational.domain.respuesta_del_cliente import leer_respuesta
from cheatsheet.shared.events import PublicadorDeEventos

#: Los pasos en los que la respuesta del cliente es texto libre que lee el intérprete (T8).
_PASOS_QUE_ESPERAN_UN_PEDIDO = frozenset(
    {PasoDelDialogo.PEDIR_CUANDO, PasoDelDialogo.ELEGIR_SERVICIO}
)


class TurnosPorWhatsApp:
    """Reservar, cancelar y reprogramar por WhatsApp (HU-E8-01 y HU-E8-02)."""

    def __init__(
        self,
        *,
        conversaciones: PortRepositorioConversacion,
        salida: SalidaAlCliente,
        agenda: PortAgenda,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._conversaciones = conversaciones
        self._salida = salida
        self._reserva = ReservaPorWhatsApp(
            conversaciones=conversaciones, salida=salida, agenda=agenda, publicador=publicador
        )
        self._cancelacion = CancelacionPorWhatsApp(
            conversaciones=conversaciones, salida=salida, agenda=agenda, publicador=publicador
        )

    async def continuar(self, contexto: ContextoDelMensaje, texto: str) -> Desenlace | None:
        """Resuelve el mensaje si es la respuesta a un diálogo pendiente; si no, `None`.

        **Sin llamar al modelo** (T3): lo lee `leer_respuesta`, una lista cerrada. Si no resuelve
        sin ambigüedad, el mensaje sigue el camino normal: el cliente pudo cambiar de tema.
        """
        dialogo = contexto.conversacion.dialogo
        if dialogo is None:
            return None
        respuesta = leer_respuesta(texto)
        if dialogo.paso in (PasoDelDialogo.ELEGIR_HORARIO, PasoDelDialogo.ELEGIR_SERVICIO):
            return await self._reserva.continuar(contexto, dialogo, respuesta)
        return await self._cancelacion.continuar(contexto, dialogo, respuesta)

    def completa_un_pedido_en_curso(self, contexto: ContextoDelMensaje, lectura: Lectura) -> bool:
        """T8: «el jueves a la tarde» completa la reserva que pidió el día, aunque venga floja.

        Sólo eso: la lectura no se vuelve más confiable para nada más, y no hace nada por sí
        sola. Es la decisión de seguir un diálogo que **el sistema** abrió y sigue vigente.
        """
        dialogo = contexto.conversacion.dialogo
        pedido = lectura.pedido_de_turno
        return (
            dialogo is not None
            and dialogo.paso in _PASOS_QUE_ESPERAN_UN_PEDIDO
            and dialogo.vigente(contexto.ahora)
            and pedido is not None
            and pedido.accion is AccionDeTurno.RESERVAR
            and (pedido.dice_algo_del_cuando or pedido.servicio is not None)
        )

    async def atender(self, contexto: ContextoDelMensaje, lectura: Lectura) -> Desenlace:
        """La intención `TURNO`, repartida por la acción que el modelo extrajo."""
        pedido = lectura.pedido_de_turno or PEDIDO_VACIO
        if pedido.accion is AccionDeTurno.REPROGRAMAR:
            return await self._a_un_asesor(contexto)
        if pedido.accion is AccionDeTurno.CANCELAR:
            return await self._cancelacion.iniciar(contexto)
        previo = _pendiente_de_completar(contexto)
        if previo is None or previo.pedido is None:
            return await self._reserva.iniciar(contexto, pedido)
        return await self._reserva.iniciar(
            contexto, pedido.completar_con(previo.pedido), servicio_id=previo.servicio_id
        )

    async def _a_un_asesor(self, contexto: ContextoDelMensaje) -> Desenlace:
        """Reprogramar no tiene historia: se ofrece una persona y no se toca la agenda."""
        contexto.conversacion.cerrar_dialogo()
        await self._conversaciones.guardar(contexto.conversacion)
        enviado = await self._salida.responder(
            contexto.empresa_id,
            contexto.conversacion,
            contexto.telefono,
            MENSAJE_OFRECER_ASESOR,
            contexto.ahora,
        )
        return Desenlace(texto=enviado)


def _pendiente_de_completar(contexto: ContextoDelMensaje) -> Dialogo | None:
    """El diálogo vigente que está esperando el resto de un pedido de reserva, si lo hay."""
    dialogo = contexto.conversacion.dialogo
    if (
        dialogo is not None
        and dialogo.paso in _PASOS_QUE_ESPERAN_UN_PEDIDO
        and dialogo.vigente(contexto.ahora)
    ):
        return dialogo
    return None


__all__ = ["TurnosPorWhatsApp"]
