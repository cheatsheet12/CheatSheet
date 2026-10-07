"""Reservar un turno por WhatsApp (HU-E8-01, issue #68).

El flujo tiene dos mitades:

1. **Ofrecer** (`iniciar`). Con lo que el cliente pidió —servicio, día, franja, hora— se consulta
   la disponibilidad **real** en `scheduling`, se eligen hasta cuatro horarios repartidos en el
   día (`elegir_horarios`) y se guardan en un `Dialogo` junto con su vencimiento. Si falta el
   servicio o el día, se pregunta.
2. **Elegir** (`continuar`). El cliente contesta y **un analizador determinista** —no el modelo—
   lo lee. Si eligió una opción que el sistema ofreció, reserva el motor de `scheduling`.

**Quién decide qué.** El modelo extrae el pedido y nada más (D38). Los ids que se reservan salen
**sólo** del `Dialogo` que armó el sistema: ni el texto ni el modelo pueden agregar un horario. Y
ni siquiera la elección es una salida de modelo: «el primero» lo lee `leer_respuesta`.

**Lo que el cliente nunca recibe es un silencio.** Si el motor rechaza el horario (CA4, CA7), el
agente lo dice y ofrece alternativas vigentes cerca del que se perdió; si el recurso de la opción
falla, antes de decir nada se prueba el siguiente que también la tenía libre (T6).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from uuid import UUID

from cheatsheet.contexts.conversational.application.contexto import (
    ContextoDelMensaje,
    Desenlace,
    evento_del_agente,
)
from cheatsheet.contexts.conversational.application.errors import (
    HorarioEnElPasado,
    HorarioNoDisponible,
)
from cheatsheet.contexts.conversational.application.ports import (
    PortAgenda,
    PortRepositorioConversacion,
    ServicioOfrecible,
)
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.domain.dialogo import (
    Dialogo,
    OpcionDeHorario,
    OpcionDeServicio,
    PasoDelDialogo,
)
from cheatsheet.contexts.conversational.domain.escalamiento import MOTIVO_BAJA_CONFIANZA
from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    PedidoDeTurno,
    coincidir_servicio,
    resolver_dias,
)
from cheatsheet.contexts.conversational.domain.respuesta_del_cliente import (
    Ambigua,
    FueraDeRango,
    HoraNoOfrecida,
    NoEsEleccion,
    RespuestaDelCliente,
    Unica,
    elegir,
)
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import (
    DIAS_DE_BUSQUEDA,
    HorarioOfrecible,
    elegir_horarios,
)
from cheatsheet.contexts.conversational.domain.textos_de_turnos import (
    MENSAJE_FECHA_PASADA,
    MENSAJE_HORARIO_OCUPADO,
    MENSAJE_HORARIO_PASADO,
    MENSAJE_NO_ENTENDI_LA_ELECCION,
    MENSAJE_OFERTA_VENCIDA,
    MENSAJE_PEDIR_CUANDO,
    MENSAJE_SIN_HORARIOS,
    MENSAJE_SIN_LO_PEDIDO,
    MENSAJE_SIN_SERVICIOS,
    oferta_de_horarios,
    oferta_de_un_horario,
    pregunta_de_servicio,
    reserva_confirmada,
)
from cheatsheet.shared.auditoria import Resultado
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

ACCION_DE_BITACORA = "reservar_turno_por_whatsapp"

#: Un pedido de reserva sin nada dicho: lo que se asume si el modelo no devolvió un pedido.
PEDIDO_VACIO = PedidoDeTurno(accion=AccionDeTurno.RESERVAR)


class ReservaPorWhatsApp:
    """HU-E8-01. Ver el docstring del módulo."""

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

    # -- ofrecer ----------------------------------------------------------------------

    async def iniciar(
        self,
        contexto: ContextoDelMensaje,
        pedido: PedidoDeTurno,
        *,
        servicio_id: UUID | None = None,
    ) -> Desenlace:
        """Arranca (o retoma) una reserva: resuelve el servicio, el día y ofrece horarios."""
        contexto.conversacion.anotar_intento_entendido()
        servicios = await self._agenda.servicios_ofrecibles()
        if not servicios:
            return await self._decir(contexto, MENSAJE_SIN_SERVICIOS, cerrar=True)
        elegido = _resolver_servicio(servicios, pedido, servicio_id)
        if elegido is None:
            return await self._preguntar_servicio(contexto, servicios, pedido)
        if pedido.sin_dia_ni_hora:
            return await self._pedir_cuando(contexto, elegido, pedido)
        return await self._ofrecer(contexto, elegido, pedido)

    async def _ofrecer(
        self,
        contexto: ContextoDelMensaje,
        servicio_id: UUID,
        pedido: PedidoDeTurno,
        *,
        fechas: list[date] | None = None,
        antes: str = "",
        excluir: datetime | None = None,
    ) -> Desenlace:
        """Consulta la disponibilidad, elige qué ofrecer y deja la oferta guardada."""
        if fechas is None:
            dias = resolver_dias(pedido, contexto.hoy, contexto.hora_local)
            fechas = list(dias.fechas)
            if dias.paso_alguna:
                antes = _juntar(MENSAJE_FECHA_PASADA, antes)
        por_dia = [await self._libres(servicio_id, fecha, excluir) for fecha in fechas]
        opciones = elegir_horarios(por_dia, momento=pedido.momento, hora=pedido.hora)
        if not opciones:
            opciones = await self._alternativas(contexto, servicio_id, fechas, excluir)
            if opciones and fechas:
                antes = _juntar(antes, MENSAJE_SIN_LO_PEDIDO)
        if not opciones:
            return await self._decir(contexto, _juntar(antes, MENSAJE_SIN_HORARIOS), cerrar=True)
        dialogo = Dialogo.nuevo(
            PasoDelDialogo.ELEGIR_HORARIO,
            contexto.ahora,
            opciones=tuple(opciones),
            servicio_id=servicio_id,
            pedido=pedido,
        )
        texto = (
            oferta_de_un_horario(opciones[0], antes=antes)
            if len(opciones) == 1
            else oferta_de_horarios(opciones, antes=antes)
        )
        return await self._decir(contexto, texto, abrir=dialogo)

    async def _libres(
        self, servicio_id: UUID, fecha: date, excluir: datetime | None
    ) -> list[HorarioOfrecible]:
        libres = await self._agenda.horarios_libres(servicio_id=servicio_id, dia=fecha)
        return [uno for uno in libres if uno.inicio != excluir]

    async def _alternativas(
        self,
        contexto: ContextoDelMensaje,
        servicio_id: UUID,
        fechas: list[date],
        excluir: datetime | None,
    ) -> list[OpcionDeHorario]:
        """«Alternativas cercanas» (CA3): el primer día de los próximos siete con algo libre."""
        desde = max(fechas) + timedelta(days=1) if fechas else contexto.hoy
        for corrimiento in range(DIAS_DE_BUSQUEDA):
            libres = await self._libres(servicio_id, desde + timedelta(days=corrimiento), excluir)
            opciones = elegir_horarios([libres])
            if opciones:
                return opciones
        return []

    async def _pedir_cuando(
        self, contexto: ContextoDelMensaje, servicio_id: UUID, pedido: PedidoDeTurno
    ) -> Desenlace:
        dialogo = Dialogo.nuevo(
            PasoDelDialogo.PEDIR_CUANDO, contexto.ahora, servicio_id=servicio_id, pedido=pedido
        )
        return await self._decir(contexto, MENSAJE_PEDIR_CUANDO, abrir=dialogo)

    async def _preguntar_servicio(
        self,
        contexto: ContextoDelMensaje,
        servicios: list[ServicioOfrecible],
        pedido: PedidoDeTurno,
    ) -> Desenlace:
        opciones = tuple(OpcionDeServicio(id=uno.id, nombre=uno.nombre) for uno in servicios)
        dialogo = Dialogo.nuevo(
            PasoDelDialogo.ELEGIR_SERVICIO, contexto.ahora, opciones=opciones, pedido=pedido
        )
        return await self._decir(contexto, pregunta_de_servicio(opciones), abrir=dialogo)

    # -- elegir -----------------------------------------------------------------------

    async def continuar(
        self, contexto: ContextoDelMensaje, dialogo: Dialogo, respuesta: RespuestaDelCliente
    ) -> Desenlace | None:
        """Lee la respuesta a una oferta. `None` si no es una respuesta: sigue el intérprete."""
        if dialogo.paso is PasoDelDialogo.ELEGIR_HORARIO:
            return await self._continuar_horario(contexto, dialogo, respuesta)
        if dialogo.paso is PasoDelDialogo.ELEGIR_SERVICIO:
            return await self._continuar_servicio(contexto, dialogo, respuesta)
        # `PEDIR_CUANDO` es texto libre: lo lee el intérprete y lo completa `TurnosPorWhatsApp`.
        return None

    async def _continuar_horario(
        self, contexto: ContextoDelMensaje, dialogo: Dialogo, respuesta: RespuestaDelCliente
    ) -> Desenlace | None:
        opciones = dialogo.horarios
        eleccion = elegir([uno.inicio for uno in opciones], respuesta)
        if isinstance(eleccion, NoEsEleccion) and respuesta.afirma and len(opciones) == 1:
            eleccion = Unica(0)  # «sí» a una oferta de una sola opción
        if isinstance(eleccion, Unica):
            contexto.conversacion.anotar_intento_entendido()
            if not dialogo.vigente(contexto.ahora):
                # T14: pasada la vigencia, una elección no reserva: se vuelve a consultar.
                return await self._reofrecer(contexto, dialogo)
            return await self._reservar(contexto, dialogo, opciones[eleccion.indice])
        if isinstance(eleccion, HoraNoOfrecida):
            contexto.conversacion.anotar_intento_entendido()
            pedido = replace(dialogo.pedido or PEDIDO_VACIO, hora=eleccion.hora, momento=None)
            return await self._ofrecer(
                contexto, opciones[0].servicio_id, pedido, fechas=_fechas_de(dialogo)
            )
        if isinstance(eleccion, Ambigua | FueraDeRango):
            return await self._repreguntar(contexto)
        if respuesta.niega:
            contexto.conversacion.anotar_intento_entendido()
            # Pide un día nuevo: lo que ya se había dicho del día y la hora no sirvió.
            pedido = replace(dialogo.pedido or PEDIDO_VACIO, cuandos=(), hora=None)
            return await self._pedir_cuando(contexto, opciones[0].servicio_id, pedido)
        return None

    async def _continuar_servicio(
        self, contexto: ContextoDelMensaje, dialogo: Dialogo, respuesta: RespuestaDelCliente
    ) -> Desenlace | None:
        eleccion = elegir(dialogo.inicios, respuesta)
        if isinstance(eleccion, Unica):
            return await self.iniciar(
                contexto,
                dialogo.pedido or PEDIDO_VACIO,
                servicio_id=dialogo.servicios[eleccion.indice].id,
            )
        if isinstance(eleccion, FueraDeRango | Ambigua):
            return await self._repreguntar(contexto)
        return None

    async def _reofrecer(self, contexto: ContextoDelMensaje, dialogo: Dialogo) -> Desenlace:
        """Vuelve a ofrecer los **mismos días** que se habían ofrecido, con lo que hay ahora."""
        fechas = [fecha for fecha in _fechas_de(dialogo) if fecha >= contexto.hoy]
        return await self._ofrecer(
            contexto,
            dialogo.horarios[0].servicio_id,
            dialogo.pedido or PEDIDO_VACIO,
            fechas=fechas,
            antes=MENSAJE_OFERTA_VENCIDA,
        )

    async def _repreguntar(self, contexto: ContextoDelMensaje) -> Desenlace:
        """No entendió cuál: repregunta, y a la tercera seguida escala (CA5)."""
        conversacion = contexto.conversacion
        conversacion.anotar_intento_fallido()
        if conversacion.agoto_los_intentos:
            conversacion.cerrar_dialogo()
            await self._conversaciones.guardar(conversacion)
            return Desenlace(texto=None, escalar_por=MOTIVO_BAJA_CONFIANZA)
        return await self._decir(contexto, MENSAJE_NO_ENTENDI_LA_ELECCION)

    # -- reservar ---------------------------------------------------------------------

    async def _reservar(
        self, contexto: ContextoDelMensaje, dialogo: Dialogo, opcion: OpcionDeHorario
    ) -> Desenlace:
        """RN-03: reserva el motor determinista, probando cada recurso que tenía el horario libre."""
        for recurso_id in opcion.recursos:
            horario = HorarioOfrecible(recurso_id, opcion.servicio_id, opcion.inicio)
            try:
                turno_id = await self._agenda.reservar(
                    cliente_id=contexto.cliente_id, horario=horario
                )
            except HorarioNoDisponible:
                continue
            except HorarioEnElPasado:
                return await self._rechazado(contexto, dialogo, opcion, MENSAJE_HORARIO_PASADO)
            return await self._reservado(contexto, opcion, turno_id)
        return await self._rechazado(contexto, dialogo, opcion, MENSAJE_HORARIO_OCUPADO)

    async def _reservado(
        self, contexto: ContextoDelMensaje, opcion: OpcionDeHorario, turno_id: UUID
    ) -> Desenlace:
        await self._publicador.publicar(
            evento_del_agente(
                contexto,
                accion=ACCION_DE_BITACORA,
                entidad=f"Turno:{turno_id}",
                resultado=Resultado.COMPLETADO,
            )
        )
        return await self._decir(contexto, reserva_confirmada(opcion.inicio), cerrar=True)

    async def _rechazado(
        self,
        contexto: ContextoDelMensaje,
        dialogo: Dialogo,
        opcion: OpcionDeHorario,
        motivo: str,
    ) -> Desenlace:
        """CA4 y CA7: lo dice, queda en la bitácora como error y ofrece lo vigente cerca."""
        await self._publicador.publicar(
            evento_del_agente(
                contexto,
                accion=ACCION_DE_BITACORA,
                entidad=f"Conversacion:{contexto.conversacion.id}",
                resultado=Resultado.ERROR,
            )
        )
        local = opcion.inicio.astimezone(ZONA_ARGENTINA)
        pedido = replace(dialogo.pedido or PEDIDO_VACIO, hora=local.time(), momento=None)
        return await self._ofrecer(
            contexto,
            opcion.servicio_id,
            pedido,
            fechas=[local.date()],
            antes=motivo,
            excluir=opcion.inicio,
        )

    # -- comunes ----------------------------------------------------------------------

    async def _decir(
        self,
        contexto: ContextoDelMensaje,
        texto: str,
        *,
        abrir: Dialogo | None = None,
        cerrar: bool = False,
    ) -> Desenlace:
        """Deja el diálogo como corresponde, lo guarda y le manda el texto al cliente.

        `abrir` deja una pregunta nueva; `cerrar` no deja nada pendiente; sin ninguno de los dos
        el diálogo que había sigue como estaba (una repregunta).
        """
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


def _resolver_servicio(
    servicios: list[ServicioOfrecible], pedido: PedidoDeTurno, previo: UUID | None
) -> UUID | None:
    """T7: el que el texto nombra; si no, el que ya se había resuelto; si no, el único."""
    nombrado = coincidir_servicio([uno.nombre for uno in servicios], pedido.servicio)
    if nombrado is not None:
        return servicios[nombrado].id
    if previo is not None and any(uno.id == previo for uno in servicios):
        return previo
    return servicios[0].id if len(servicios) == 1 else None


def _fechas_de(dialogo: Dialogo) -> list[date]:
    """Los días en que caen las opciones de un diálogo, sin repetir y en orden."""
    return sorted({uno.inicio.astimezone(ZONA_ARGENTINA).date() for uno in dialogo.horarios})


def _juntar(*partes: str) -> str:
    return "\n".join(parte for parte in partes if parte)
