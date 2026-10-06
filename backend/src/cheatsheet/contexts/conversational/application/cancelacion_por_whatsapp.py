"""Cancelar un turno por WhatsApp (HU-E8-02, issue #69).

**Cancelar es una acción irreversible para el cliente**, así que acá nada pasa sin un «sí»
explícito sobre un turno que se vuelve a comprobar:

1. `iniciar` busca los turnos futuros y abiertos del cliente por su número: ninguno → «No encuentro
   turnos reservados a su nombre.»; uno → pide confirmación; varios → pide cuál y después confirma
   (elegir es identificar; igual se confirma).
2. `continuar` lee la respuesta con el analizador determinista. Con un «sí», **re-verifica** que el
   turno siga entre los del cliente, cancela por el caso de uso de `scheduling` —el horario queda
   libre— y lo confirma por el mismo canal.

**El id que se cancela sale sólo del `Dialogo` que armó el sistema** (T4): ni el texto del cliente
ni lo que diga el modelo pueden cambiarlo. Un turno **con seña** no se cancela solo (Pregunta 3 del
Gate 1): el agente avisa y escala, porque la política de seña no existe tipada todavía.
"""

from __future__ import annotations

from cheatsheet.contexts.conversational.application.contexto import (
    ContextoDelMensaje,
    Desenlace,
    evento_del_agente,
)
from cheatsheet.contexts.conversational.application.errors import TurnoNoCancelable
from cheatsheet.contexts.conversational.application.ports import (
    PortAgenda,
    PortRepositorioConversacion,
)
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.domain.conversacion import MENSAJE_SIN_TURNOS
from cheatsheet.contexts.conversational.domain.dialogo import (
    Dialogo,
    OpcionDeTurno,
    PasoDelDialogo,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    MOTIVO_BAJA_CONFIANZA,
    MOTIVO_CANCELACION_CON_SENA,
)
from cheatsheet.contexts.conversational.domain.respuesta_del_cliente import (
    Ambigua,
    FueraDeRango,
    HoraNoOfrecida,
    RespuestaDelCliente,
    Unica,
    elegir,
)
from cheatsheet.contexts.conversational.domain.textos_de_turnos import (
    MENSAJE_NO_CANCELABLE,
    MENSAJE_NO_ENTENDI_LA_ELECCION,
    MENSAJE_TURNO_CON_SENA,
    MENSAJE_TURNO_SIGUE,
    cancelacion_confirmada,
    confirmar_cancelacion,
    listado_de_turnos,
)
from cheatsheet.shared.auditoria import Resultado
from cheatsheet.shared.events import PublicadorDeEventos

ACCION_DE_BITACORA = "cancelar_turno_por_whatsapp"


class CancelacionPorWhatsApp:
    """HU-E8-02. Ver el docstring del módulo."""

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
        self._agenda = agenda
        self._publicador = publicador

    async def iniciar(self, contexto: ContextoDelMensaje) -> Desenlace:
        """Busca los turnos del cliente y pregunta lo que haga falta para identificar uno."""
        contexto.conversacion.anotar_intento_entendido()
        turnos = sorted(await self._agenda.turnos_de(contexto.cliente_id), key=lambda t: t.inicio)
        opciones = tuple(
            OpcionDeTurno(
                turno_id=uno.id, servicio=uno.servicio, inicio=uno.inicio, tiene_sena=uno.tiene_sena
            )
            for uno in turnos
        )
        if not opciones:
            return await self._decir(contexto, MENSAJE_SIN_TURNOS, cerrar=True)
        if len(opciones) == 1:
            return await self._confirmar(contexto, opciones[0])
        dialogo = Dialogo.nuevo(
            PasoDelDialogo.ELEGIR_TURNO_A_CANCELAR, contexto.ahora, opciones=opciones
        )
        return await self._decir(contexto, listado_de_turnos(opciones), abrir=dialogo)

    async def continuar(
        self, contexto: ContextoDelMensaje, dialogo: Dialogo, respuesta: RespuestaDelCliente
    ) -> Desenlace | None:
        """Lee la respuesta. `None` si no es una respuesta: sigue el camino del intérprete."""
        if dialogo.paso is PasoDelDialogo.CONFIRMAR_CANCELACION:
            return await self._continuar_confirmacion(contexto, dialogo, respuesta)
        if dialogo.paso is PasoDelDialogo.ELEGIR_TURNO_A_CANCELAR:
            return await self._continuar_eleccion(contexto, dialogo, respuesta)
        return None

    async def _continuar_confirmacion(
        self, contexto: ContextoDelMensaje, dialogo: Dialogo, respuesta: RespuestaDelCliente
    ) -> Desenlace | None:
        if respuesta.afirma:
            if not dialogo.vigente(contexto.ahora):
                # T14: un «sí» horas después puede confirmar algo que ya no estaba en mente.
                return await self.iniciar(contexto)
            contexto.conversacion.anotar_intento_entendido()
            return await self._cancelar(contexto, dialogo.turnos[0])
        if respuesta.niega:
            return await self._dejar_en_pie(contexto)
        return None

    async def _continuar_eleccion(
        self, contexto: ContextoDelMensaje, dialogo: Dialogo, respuesta: RespuestaDelCliente
    ) -> Desenlace | None:
        eleccion = elegir(dialogo.inicios, respuesta)
        if isinstance(eleccion, Unica):
            if not dialogo.vigente(contexto.ahora):
                return await self.iniciar(contexto)
            contexto.conversacion.anotar_intento_entendido()
            return await self._confirmar(contexto, dialogo.turnos[eleccion.indice])
        if isinstance(eleccion, Ambigua | FueraDeRango | HoraNoOfrecida):
            return await self._repreguntar(contexto)
        if respuesta.niega:
            return await self._dejar_en_pie(contexto)
        return None

    async def _confirmar(self, contexto: ContextoDelMensaje, turno: OpcionDeTurno) -> Desenlace:
        """Pide el «sí», o deriva si el turno tiene seña (Pregunta 3)."""
        if turno.tiene_sena:
            return await self._con_sena(contexto)
        dialogo = Dialogo.nuevo(
            PasoDelDialogo.CONFIRMAR_CANCELACION, contexto.ahora, opciones=(turno,)
        )
        return await self._decir(contexto, confirmar_cancelacion(turno), abrir=dialogo)

    async def _con_sena(self, contexto: ContextoDelMensaje) -> Desenlace:
        desenlace = await self._decir(contexto, MENSAJE_TURNO_CON_SENA, cerrar=True)
        return Desenlace(texto=desenlace.texto, escalar_por=MOTIVO_CANCELACION_CON_SENA)

    async def _cancelar(self, contexto: ContextoDelMensaje, turno: OpcionDeTurno) -> Desenlace:
        """HU-E8-02 CA4. Re-verifica el turno, cancela, libera y confirma."""
        vigentes = {uno.id: uno for uno in await self._agenda.turnos_de(contexto.cliente_id)}
        actual = vigentes.get(turno.turno_id)
        if actual is None:
            return await self._no_cancelable(contexto, turno)
        if actual.tiene_sena:
            return await self._con_sena(contexto)
        try:
            await self._agenda.cancelar(turno.turno_id)
        except TurnoNoCancelable:
            return await self._no_cancelable(contexto, turno)
        await self._publicador.publicar(
            evento_del_agente(
                contexto,
                accion=ACCION_DE_BITACORA,
                entidad=f"Turno:{turno.turno_id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return await self._decir(contexto, cancelacion_confirmada(turno), cerrar=True)

    async def _no_cancelable(self, contexto: ContextoDelMensaje, turno: OpcionDeTurno) -> Desenlace:
        """Otro lo canceló o lo completó entretanto: se lo dice, queda en la bitácora y no rompe."""
        await self._publicador.publicar(
            evento_del_agente(
                contexto,
                accion=ACCION_DE_BITACORA,
                entidad=f"Conversacion:{contexto.conversacion.id}",
                resultado=Resultado.ERROR,
            )
        )
        del turno
        return await self._decir(contexto, MENSAJE_NO_CANCELABLE, cerrar=True)

    async def _dejar_en_pie(self, contexto: ContextoDelMensaje) -> Desenlace:
        contexto.conversacion.anotar_intento_entendido()
        return await self._decir(contexto, MENSAJE_TURNO_SIGUE, cerrar=True)

    async def _repreguntar(self, contexto: ContextoDelMensaje) -> Desenlace:
        conversacion = contexto.conversacion
        conversacion.anotar_intento_fallido()
        if conversacion.agoto_los_intentos:
            conversacion.cerrar_dialogo()
            await self._conversaciones.guardar(conversacion)
            return Desenlace(texto=None, escalar_por=MOTIVO_BAJA_CONFIANZA)
        return await self._decir(contexto, MENSAJE_NO_ENTENDI_LA_ELECCION)

    async def _decir(
        self,
        contexto: ContextoDelMensaje,
        texto: str,
        *,
        abrir: Dialogo | None = None,
        cerrar: bool = False,
    ) -> Desenlace:
        if abrir is not None:
            contexto.conversacion.abrir_dialogo(abrir)
        elif cerrar:
            contexto.conversacion.cerrar_dialogo()
        await self._conversaciones.guardar(contexto.conversacion)
        enviado = await self._salida.responder(
            contexto.empresa_id,
            contexto.conversacion,
            contexto.telefono,
            texto,
            contexto.ahora,
        )
        return Desenlace(texto=enviado)


__all__ = ["CancelacionPorWhatsApp"]
