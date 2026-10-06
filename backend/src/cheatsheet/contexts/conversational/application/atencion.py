"""Los casos de uso del operador humano (HU-E9-01, HU-E9-02).

**Administrador y Operador atienden; Solo Lectura mira.** Los guardas viven acá y no sólo en
el router, por lo que enseñó PRU-09.

Lo que este archivo hace y conviene leer con atención:

- **Tomar el escalamiento es lo único que calla al agente.** No hay un flag «agente pausado»:
  mientras exista un escalamiento sin resolver, `ProcesarMensajeEntrante` no interpreta ese
  hilo. Un flag aparte sería el mismo hecho guardado dos veces, y el día que discreparan el
  agente contestaría encima de una persona.

- **Los mensajes del operador quedan marcados como suyos** (HU-E9-01 RN-04). Es lo que hace
  posible que la pantalla los distinga; sin la marca, tendría que adivinar por el momento del
  escalamiento.

- **Devolver el control reclasifica el hilo** (RN-05), y el operador puede corregir esa
  clasificación antes de devolverlo. Las dos cosas: la automática porque la regla la pide, y
  la manual porque la misma regla se la reserva a la persona.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.errors import (
    ClienteSinWhatsApp,
    ConversacionInexistente,
    EscalamientoInexistente,
    EscalamientoNoReabrible,
    MensajeriaNoDisponible,
)
from cheatsheet.contexts.conversational.application.ports import (
    PortDirectorio,
    PortInterprete,
    PortMensajeria,
    PortRepositorioConversacion,
    PortRepositorioEscalamiento,
    PortRepositorioMensaje,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    DireccionMensaje,
    EstadoEntrega,
    Intencion,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.escalamiento import Escalamiento
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.roles import RolUsuario

MOTIVO_SIN_PERMISO = "Solo un Administrador u Operador puede atender conversaciones"


def _exigir_gestor(rol: RolUsuario) -> None:
    if rol not in (RolUsuario.ADMINISTRADOR, RolUsuario.OPERADOR):
        raise EntradaInvalida(MOTIVO_SIN_PERMISO)


@dataclass(frozen=True, slots=True)
class VistaDeConversacion:
    """Un hilo con lo que la pantalla necesita para pintarlo.

    El escalamiento viene al lado y no adentro de `Conversacion`: la conversación no sabe que
    está escalada, y ése es justamente el punto de HU-E9-01 RN-01.
    """

    conversacion: Conversacion
    escalamiento: Escalamiento | None
    mensajes: tuple[Mensaje, ...] = ()
    nombre_del_cliente: str | None = None

    @property
    def esta_escalada(self) -> bool:
        return self.escalamiento is not None and self.escalamiento.esta_abierto


class ListarConversaciones:
    """PAN-WA-01. Todos los roles leen.

    `solo_escaladas` es lo que la pantalla usa por defecto: la bandeja de un operador son las
    que esperan a alguien, no todas las que hubo.
    """

    def __init__(
        self,
        conversaciones: PortRepositorioConversacion,
        escalamientos: PortRepositorioEscalamiento,
    ) -> None:
        self._conversaciones = conversaciones
        self._escalamientos = escalamientos

    async def ejecutar(self, *, solo_escaladas: bool = False) -> list[VistaDeConversacion]:
        hilos = await self._conversaciones.listar(solo_escaladas=solo_escaladas)
        vistas: list[VistaDeConversacion] = []
        for hilo in hilos:
            vistas.append(
                VistaDeConversacion(
                    conversacion=hilo,
                    escalamiento=await self._escalamientos.abierto_de(hilo.id),
                )
            )
        return vistas


class VerConversacion:
    """PAN-WA-01, el hilo abierto. **El contexto previo de HU-E8-05 RN-03.**

    Trae los mensajes completos: es lo que evita que el cliente tenga que repetir todo, que es
    la promesa textual de la historia.
    """

    def __init__(
        self,
        conversaciones: PortRepositorioConversacion,
        mensajes: PortRepositorioMensaje,
        escalamientos: PortRepositorioEscalamiento,
    ) -> None:
        self._conversaciones = conversaciones
        self._mensajes = mensajes
        self._escalamientos = escalamientos

    async def ejecutar(self, conversacion_id: UUID) -> VistaDeConversacion:
        conversacion = await self._conversaciones.buscar_por_id(conversacion_id)
        if conversacion is None:
            raise ConversacionInexistente("La conversación no existe")
        return VistaDeConversacion(
            conversacion=conversacion,
            escalamiento=await self._escalamientos.abierto_de(conversacion_id),
            mensajes=tuple(await self._mensajes.del_hilo(conversacion_id)),
        )


class TomarEscalamiento:
    """HU-E9-01 RN-02 y RN-06.

    A partir de acá el agente no contesta ese hilo, y queda registrado quién lo tomó y cuándo.
    """

    def __init__(
        self, escalamientos: PortRepositorioEscalamiento, publicador: PublicadorDeEventos
    ) -> None:
        self._escalamientos = escalamientos
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        escalamiento_id: UUID,
        ahora: datetime,
    ) -> Escalamiento:
        _exigir_gestor(rol)
        escalamiento = await _buscar(self._escalamientos, escalamiento_id)
        try:
            escalamiento.tomar(usuario_id, ahora)
        except InvarianteViolada as exc:
            raise EscalamientoNoReabrible(str(exc)) from exc
        await self._escalamientos.guardar(escalamiento)
        await _auditar(
            self._publicador, empresa_id, usuario_id, escalamiento, "tomar_escalamiento", ahora
        )
        return escalamiento


class ResponderComoOperador:
    """HU-E9-01, tercer criterio: el mensaje sale por WhatsApp y se distingue del agente.

    **Requiere el escalamiento tomado.** Un operador escribiendo sobre un hilo que el agente
    todavía atiende produce dos interlocutores en la misma conversación, que es exactamente la
    experiencia que RN-02 evita.

    **El destino no lo elige quien escribe.** Sale del cliente dueño del hilo
    (`conversacion.cliente_id`), resuelto en `master_data` por el directorio. Si el operador
    pudiera mandar el número, cualquier gestor podría escribirle a cualquiera desde la cuenta
    de WhatsApp Business verificada de la empresa.
    """

    def __init__(
        self,
        *,
        conversaciones: PortRepositorioConversacion,
        mensajes: PortRepositorioMensaje,
        escalamientos: PortRepositorioEscalamiento,
        directorio: PortDirectorio,
        mensajeria: PortMensajeria,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._conversaciones = conversaciones
        self._mensajes = mensajes
        self._escalamientos = escalamientos
        self._directorio = directorio
        self._mensajeria = mensajeria
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        conversacion_id: UUID,
        texto: str,
        ahora: datetime,
    ) -> Mensaje:
        _exigir_gestor(rol)
        if not texto.strip():
            raise EntradaInvalida("El mensaje no puede estar vacío")
        conversacion = await self._conversaciones.buscar_por_id(conversacion_id)
        if conversacion is None:
            raise ConversacionInexistente("La conversación no existe")
        abierto = await self._escalamientos.abierto_de(conversacion_id)
        if abierto is None:
            # Sin escalamiento tomado, el agente sigue contestando ese hilo. Ver el docstring.
            raise EntradaInvalida(
                "Para escribirle al cliente hay que tomar el escalamiento primero"
            )
        telefono = await self._directorio.telefono_de(conversacion.cliente_id)
        if telefono is None:
            raise ClienteSinWhatsApp(
                "El cliente de esta conversación no tiene un WhatsApp registrado"
            )

        externo_id: str | None = None
        try:
            externo_id = await self._mensajeria.enviar(telefono=telefono, texto=texto)
        except Exception as exc:
            # A diferencia del agente, acá **sí** se levanta: un operador que apretó «Enviar»
            # tiene que enterarse de que el mensaje no salió. El agente puede seguir sin su
            # confirmación; una persona esperando una respuesta, no.
            raise MensajeriaNoDisponible("WhatsApp no aceptó el mensaje") from exc

        mensaje = Mensaje(
            id=uuid4(),
            conversacion_id=conversacion_id,
            empresa_id=empresa_id,
            direccion=DireccionMensaje.SALIENTE,
            tipo_contenido=TipoContenido.TEXTO,
            contenido=texto,
            momento=ahora,
            # RN-04: lo que hace que la pantalla los pueda distinguir.
            origen=OrigenDelMensaje.OPERADOR,
            estado_entrega=EstadoEntrega.ENVIADO,
            externo_id=externo_id,
        )
        await self._mensajes.agregar(mensaje)
        conversacion.registrar_actividad(ahora)
        await self._conversaciones.guardar(conversacion)
        await _auditar(
            self._publicador, empresa_id, usuario_id, abierto, "responder_como_operador", ahora
        )
        return mensaje


class CerrarEscalamiento:
    """HU-E9-02. Resuelve, y opcionalmente devuelve el hilo al agente.

    **Devolver al agente reclasifica** (RN-05): se relee el último mensaje del cliente y se
    actualiza la intención del hilo. El operador puede mandar una clasificación explícita, y
    entonces ésa gana — la regla se la reserva.

    **Si no se devuelve al agente, la conversación se archiva.** «Darla por finalizada» es eso:
    un hilo resuelto que no espera nada. Dejarla activa sin escalamiento haría que el agente
    volviera a contestar sobre un caso que alguien dio por cerrado.
    """

    def __init__(
        self,
        *,
        conversaciones: PortRepositorioConversacion,
        mensajes: PortRepositorioMensaje,
        escalamientos: PortRepositorioEscalamiento,
        interprete: PortInterprete,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._conversaciones = conversaciones
        self._mensajes = mensajes
        self._escalamientos = escalamientos
        self._interprete = interprete
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        usuario_id: UsuarioId,
        rol: RolUsuario,
        escalamiento_id: UUID,
        devolver_al_agente: bool,
        ahora: datetime,
        clasificacion: Intencion | None = None,
    ) -> Escalamiento:
        _exigir_gestor(rol)
        escalamiento = await _buscar(self._escalamientos, escalamiento_id)
        try:
            escalamiento.resolver(ahora)
        except InvarianteViolada as exc:
            # HU-E9-02, tercer criterio: hay que **decirlo**, no sólo negarlo.
            raise EscalamientoNoReabrible(
                "Un escalamiento cerrado no se reabre. Un nuevo pedido del cliente genera uno "
                "nuevo."
            ) from exc
        await self._escalamientos.guardar(escalamiento)

        conversacion = await self._conversaciones.buscar_por_id(escalamiento.conversacion_id)
        if conversacion is not None:
            if devolver_al_agente:
                await self._reclasificar(conversacion, clasificacion)
            else:
                conversacion.archivar()
            await self._conversaciones.guardar(conversacion)

        await _auditar(
            self._publicador, empresa_id, usuario_id, escalamiento, "cerrar_escalamiento", ahora
        )
        return escalamiento

    async def _reclasificar(
        self, conversacion: Conversacion, clasificacion: Intencion | None
    ) -> None:
        """RN-05. El agente reevalúa, salvo que el operador ya lo haya decidido.

        La clasificación se guarda en el **último mensaje entrante**, que es donde el DER pone
        `intencion`: no hay «intención del hilo», y guardarla en la conversación sería un dato
        nuevo que el esquema no tiene.
        """
        conversacion.anotar_intento_entendido()
        entrantes = [
            uno
            for uno in await self._mensajes.del_hilo(conversacion.id)
            if uno.direccion is DireccionMensaje.ENTRANTE
        ]
        if not entrantes:
            return
        ultimo = entrantes[-1]
        if clasificacion is not None:
            ultimo.intencion = clasificacion
        else:
            lectura = await self._interprete.leer(ultimo.contenido)
            ultimo.intencion = lectura.intencion
        await self._mensajes.guardar(ultimo)


async def _buscar(
    escalamientos: PortRepositorioEscalamiento, escalamiento_id: UUID
) -> Escalamiento:
    escalamiento = await escalamientos.buscar_por_id(escalamiento_id)
    if escalamiento is None:
        raise EscalamientoInexistente("El escalamiento no existe")
    return escalamiento


async def _auditar(
    publicador: PublicadorDeEventos,
    empresa_id: EmpresaId,
    usuario_id: UsuarioId,
    escalamiento: Escalamiento,
    accion: str,
    ahora: datetime,
) -> None:
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario_id,
            ocurrido_en=ahora,
            modulo=Modulo.CONVERSATIONAL,
            accion=accion,
            entidad_afectada=f"Escalamiento:{escalamiento.id}",
            resultado=Resultado.COMPLETADO,
        )
    )


__all__ = [
    "CerrarEscalamiento",
    "ListarConversaciones",
    "ResponderComoOperador",
    "TomarEscalamiento",
    "VerConversacion",
    "VistaDeConversacion",
]
