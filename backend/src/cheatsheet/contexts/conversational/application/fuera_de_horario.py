"""La política de fuera de horario del agente (HS-T2 RN-04, HU-E8-05 RN-04).

Dos políticas, a elección de la empresa (la opción (c) de I-09):

- **(a) `AGENTE_RESPONDE`, por defecto.** El agente sigue atendiendo como de día; lo único que
  cambia es el aviso de derivación, que agrega desde cuándo lo va a atender un asesor
  (`aviso_de_derivacion`, usado por `ProcesarMensajeEntrante._escalar`).
- **(b) `MENSAJE_FIJO`.** El agente **no contesta**: el mensaje queda registrado y el cliente recibe
  un único mensaje fijo por período de cierre (`atender_cerrado`). **El modelo no se llama**, ni
  los embeddings. La excepción es la respuesta a una oferta que el agente hizo antes de cerrar
  («el primero», «sí»): la lee el analizador determinista, se atiende y **termina con la oración de
  fuera de horario** (`SalidaConPosdata`), para que todo saliente del agente en el período informe
  el cierre y «ya avisado» (`ya_avisado`) sea cierto sin releer ningún texto.

Que el negocio esté abierto lo calcula `business_config`; el modelo ni se entera.
"""

from __future__ import annotations

from datetime import datetime

from cheatsheet.contexts.conversational.application.contexto import (
    ContextoDelMensaje,
    Desenlace,
    evento_del_agente,
)
from cheatsheet.contexts.conversational.application.ports import (
    PortAgenda,
    PortHorarioDeAtencion,
    PortMensajeria,
    PortRepositorioConversacion,
    PortRepositorioMensaje,
)
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.application.turnos_por_whatsapp import TurnosPorWhatsApp
from cheatsheet.contexts.conversational.domain.conversacion import (
    MENSAJE_DERIVACION,
    Conversacion,
    Intencion,
    Mensaje,
)
from cheatsheet.contexts.conversational.domain.fuera_de_horario import (
    AtencionDelNegocio,
    PoliticaFueraDeHorario,
    aviso_de_derivacion,
    mensaje_fuera_de_horario,
    posdata_fuera_de_horario,
    ya_avisado,
)
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

logger = obtener_logger(__name__)

ACCION_FUERA_DE_HORARIO = "responder_fuera_de_horario"


class SalidaConPosdata(SalidaAlCliente):
    """Agrega la oración de fuera de horario al **primer** saliente que manda, y lo guarda así.

    Es lo que permite seguir un diálogo de noche sin tocar los pasos de turnos: cada
    continuación manda un solo saliente por su `_decir`, así que la oración aparece una vez y
    queda en el hilo como saliente del agente.
    """

    def __init__(
        self, *, mensajes: PortRepositorioMensaje, mensajeria: PortMensajeria, posdata: str
    ) -> None:
        super().__init__(mensajes=mensajes, mensajeria=mensajeria)
        self._posdata = posdata
        self._agregada = False

    async def responder(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        telefono: str,
        texto: str,
        ahora: datetime,
    ) -> str | None:
        if not self._agregada:
            self._agregada = True
            texto = f"{texto}\n\n{self._posdata}"
        return await super().responder(empresa_id, conversacion, telefono, texto, ahora)


class AtencionFueraDeHorario:
    """Lo que el agente hace según el horario de atención. Ver el docstring del módulo."""

    def __init__(
        self,
        *,
        horario: PortHorarioDeAtencion,
        conversaciones: PortRepositorioConversacion,
        mensajes: PortRepositorioMensaje,
        mensajeria: PortMensajeria,
        agenda: PortAgenda,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._horario = horario
        self._conversaciones = conversaciones
        self._mensajes = mensajes
        self._mensajeria = mensajeria
        self._agenda = agenda
        self._publicador = publicador
        self._salida = SalidaAlCliente(mensajes=mensajes, mensajeria=mensajeria)
        self._consultado: tuple[datetime, AtencionDelNegocio] | None = None

    async def consultar(self, contexto: ContextoDelMensaje) -> AtencionDelNegocio:
        """Una consulta por mensaje: el `ahora` es el mismo en todo el procesamiento."""
        if self._consultado is None or self._consultado[0] != contexto.ahora:
            self._consultado = (contexto.ahora, await self._horario.consultar(contexto.ahora))
        return self._consultado[1]

    async def aviso_de_derivacion(self, contexto: ContextoDelMensaje) -> str:
        """HU-E8-05 RN-04. Abierto, el texto de siempre; cerrado, dice desde cuándo atienden."""
        atencion = await self.consultar(contexto)
        if atencion.abierto:
            return MENSAJE_DERIVACION
        return aviso_de_derivacion(atencion, contexto.ahora)

    async def atender_cerrado(
        self, contexto: ContextoDelMensaje, guardado: Mensaje, texto: str
    ) -> Desenlace | None:
        """Política (b) con el negocio cerrado. `None` si no aplica: el flujo sigue como siempre."""
        atencion = await self.consultar(contexto)
        if atencion.abierto or atencion.politica is not PoliticaFueraDeHorario.MENSAJE_FIJO:
            return None
        seguido = await self._seguir_el_dialogo(contexto, guardado, texto, atencion)
        if seguido is not None:
            return seguido
        return await self._avisar_una_vez(contexto, atencion)

    async def _seguir_el_dialogo(
        self,
        contexto: ContextoDelMensaje,
        guardado: Mensaje,
        texto: str,
        atencion: AtencionDelNegocio,
    ) -> Desenlace | None:
        """La respuesta a una oferta anterior al cierre: sin el modelo, con la oración al final.

        `PEDIR_CUANDO` es texto libre que necesita al intérprete: `continuar` devuelve `None` y
        el mensaje recibe el fijo. Un diálogo vencido se re-ofrece como de día, también con la
        oración.
        """
        if contexto.conversacion.dialogo is None:
            return None
        salida = SalidaConPosdata(
            mensajes=self._mensajes,
            mensajeria=self._mensajeria,
            posdata=posdata_fuera_de_horario(atencion, contexto.ahora),
        )
        turnos = TurnosPorWhatsApp(
            conversaciones=self._conversaciones,
            salida=salida,
            agenda=self._agenda,
            publicador=self._publicador,
        )
        desenlace = await turnos.continuar(contexto, texto)
        if desenlace is not None:
            guardado.intencion = Intencion.TURNO
            await self._mensajes.guardar(guardado)
        return desenlace

    async def _avisar_una_vez(
        self, contexto: ContextoDelMensaje, atencion: AtencionDelNegocio
    ) -> Desenlace:
        """El mensaje fijo si el agente no avisó en este período de cierre; si no, silencio (T9)."""
        conversacion = contexto.conversacion
        desde = atencion.cerrado_desde or contexto.ahora
        if ya_avisado(await self._mensajes.del_hilo(conversacion.id), desde):
            logger.info("fuera_de_horario_ya_avisado", conversacion=str(conversacion.id))
            return Desenlace(texto=None)
        enviado = await self._salida.responder(
            contexto.empresa_id,
            conversacion,
            contexto.telefono,
            mensaje_fuera_de_horario(atencion, contexto.ahora),
            contexto.ahora,
        )
        await self._publicador.publicar(
            evento_del_agente(
                contexto,
                accion=ACCION_FUERA_DE_HORARIO,
                entidad=f"Conversacion:{conversacion.id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return Desenlace(texto=enviado)


__all__ = ["ACCION_FUERA_DE_HORARIO", "AtencionFueraDeHorario", "SalidaConPosdata"]
