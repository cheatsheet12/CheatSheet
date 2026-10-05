"""`ProcesarMensajeEntrante` — el caso de uso más peligroso del sistema (HS-T2).

Acá entra texto que escribió un desconocido y sale una acción. Todo lo que sigue está escrito
para que esa frase sea segura.

**El orden importa y es el de HS-T2:**

1. **Idempotencia primero.** Meta reintenta, y reintenta seguido. Un mensaje ya procesado se
   descarta antes de gastar un token de LLM o de mover un turno.
2. **Transcribir, si vino audio.** Y si la transcripción es mala, escalar (HS-T7 RN-04) —
   interpretar una transcripción rota es adivinar dos veces seguidas.
3. **Registrar el mensaje entrante.** Antes de interpretarlo: si el modelo se cae, el mensaje
   igual quedó, y un operador puede leerlo.
4. **Interpretar.** El modelo devuelve una intención y una confianza, y **nada más**.
5. **Encaminar.** Por debajo del umbral, o agotados los intentos, se escala.

**Lo que el modelo no puede hacer** (decisión **D38**): reservar, cancelar, cobrar, ni mandar
un mensaje que él haya redactado sobre datos que él haya elegido. Las acciones son llamadas a
`PortAgenda`, que del otro lado son los casos de uso deterministas de `scheduling` con su
restricción de exclusión. Un prompt injection que logre convencer al modelo de que el cliente
quiere reservar produce, como mucho, que el agente ofrezca horarios reales de esa empresa.

**Si hay un escalamiento abierto, el agente no contesta** (HU-E9-01 RN-02). El mensaje se
registra igual —el operador lo tiene que ver— pero no se interpreta ni se responde.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.errors import MensajeYaProcesado
from cheatsheet.contexts.conversational.application.ports import (
    Lectura,
    MensajeEntrante,
    PortAgenda,
    PortDirectorio,
    PortEmbeddings,
    PortInterprete,
    PortMensajeria,
    PortRepositorioConversacion,
    PortRepositorioEscalamiento,
    PortRepositorioFAQ,
    PortRepositorioMensaje,
    PortTranscriptor,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    MENSAJE_DERIVACION,
    MENSAJE_OFRECER_ASESOR,
    Conversacion,
    DireccionMensaje,
    EstadoEntrega,
    Intencion,
    Mensaje,
    OrigenDelMensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    MOTIVO_BAJA_CONFIANZA,
    MOTIVO_PEDIDO_POR_EL_CLIENTE,
    MOTIVO_TRANSCRIPCION_POBRE,
    Escalamiento,
)
from cheatsheet.contexts.conversational.domain.faq import UMBRAL_DE_SIMILITUD
from cheatsheet.shared.auditoria import EventoAuditable, Iniciador, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import PublicadorDeEventos

#: Por debajo de esto, el agente no se cree lo que entendió (HS-T2 RN-03).
#:
#: 0.6 es más bajo que el umbral de las FAQ (0.75) y es deliberado: acá el error se paga con
#: un escalamiento —alguien lee el hilo y contesta— mientras que allá se paga con una respuesta
#: falsa dicha con seguridad. Los dos umbrales miden cosas distintas y no tienen por qué
#: coincidir.
UMBRAL_DE_CONFIANZA = 0.6

#: Debajo de esto, una transcripción no se interpreta: se escala (HS-T7 RN-04).
UMBRAL_DE_TRANSCRIPCION = 0.5

#: Cuántos horarios se ofrecen de una. Más de tres en un mensaje de WhatsApp es una lista que
#: nadie lee; el ejemplo de la historia ofrece dos.
HORARIOS_A_OFRECER = 3

#: Las palabras con las que alguien pide una persona (HU-E8-05 RN-01: «cuando el cliente la
#: solicita explícitamente»). Se comprueban **antes** de llamar al modelo: es la única
#: intención cuya interpretación no puede depender de un modelo que quizá no entienda.
PEDIDOS_DE_HUMANO = (
    "hablar con una persona",
    "hablar con alguien",
    "un humano",
    "una persona",
    "un asesor",
    "atencion humana",
    "atención humana",
)


@dataclass(frozen=True, slots=True)
class Respuesta:
    """Lo que el procesamiento produjo. Lo devuelve para que el webhook lo pueda afirmar."""

    conversacion_id: UUID
    intencion: Intencion
    escalado: bool
    texto_enviado: str | None


class ProcesarMensajeEntrante:
    """HS-T2. Ver el docstring del módulo antes de tocar nada de acá."""

    def __init__(
        self,
        *,
        conversaciones: PortRepositorioConversacion,
        mensajes: PortRepositorioMensaje,
        escalamientos: PortRepositorioEscalamiento,
        faqs: PortRepositorioFAQ,
        clientes: PortDirectorio,
        interprete: PortInterprete,
        transcriptor: PortTranscriptor,
        mensajeria: PortMensajeria,
        embeddings: PortEmbeddings,
        agenda: PortAgenda,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._conversaciones = conversaciones
        self._mensajes = mensajes
        self._escalamientos = escalamientos
        self._faqs = faqs
        self._clientes = clientes
        self._interprete = interprete
        self._transcriptor = transcriptor
        self._mensajeria = mensajeria
        self._embeddings = embeddings
        self._agenda = agenda
        self._publicador = publicador

    async def ejecutar(
        self, *, empresa_id: EmpresaId, entrante: MensajeEntrante, ahora: datetime
    ) -> Respuesta:
        # 1. Idempotencia, antes que nada. Ver el docstring del módulo.
        if await self._mensajes.buscar_por_externo_id(entrante.externo_id) is not None:
            raise MensajeYaProcesado(f"El mensaje {entrante.externo_id} ya fue procesado")

        cliente_id = await self._resolver_cliente(entrante)
        conversacion = await self._hilo_de(empresa_id, cliente_id, ahora)

        # 2. Transcribir si hace falta.
        texto, tipo, transcripcion_pobre = await self._texto_de(entrante)

        # 3. Registrar. **Antes** de interpretar: si el modelo se cae, el mensaje quedó.
        guardado = await self._guardar_entrante(
            empresa_id, conversacion, entrante, texto, tipo, ahora
        )
        conversacion.registrar_actividad(ahora)

        # Si un operador está atendiendo, el agente calla (HU-E9-01 RN-02).
        abierto = await self._escalamientos.abierto_de(conversacion.id)
        if abierto is not None:
            await self._conversaciones.guardar(conversacion)
            return Respuesta(
                conversacion.id, Intencion.DESCONOCIDA, escalado=True, texto_enviado=None
            )

        if transcripcion_pobre:
            return await self._escalar(
                empresa_id, conversacion, entrante.telefono, MOTIVO_TRANSCRIPCION_POBRE, ahora
            )

        # El pedido explícito de una persona no pasa por el modelo: ver `PEDIDOS_DE_HUMANO`.
        if _pide_una_persona(texto):
            return await self._escalar(
                empresa_id, conversacion, entrante.telefono, MOTIVO_PEDIDO_POR_EL_CLIENTE, ahora
            )

        # 4. Interpretar.
        historial = [uno.contenido for uno in await self._mensajes.del_hilo(conversacion.id)]
        lectura = await self._interprete.leer(texto, historial=historial[-6:])
        await self._auditar(empresa_id, conversacion, lectura, ahora)

        # 5. Encaminar.
        if lectura.confianza < UMBRAL_DE_CONFIANZA:
            await self._anotar_intencion(guardado, Intencion.DESCONOCIDA)
            conversacion.anotar_intento_fallido()
            if conversacion.agoto_los_intentos:
                return await self._escalar(
                    empresa_id, conversacion, entrante.telefono, MOTIVO_BAJA_CONFIANZA, ahora
                )
            await self._conversaciones.guardar(conversacion)
            texto_enviado = await self._responder(
                empresa_id, conversacion, entrante.telefono, MENSAJE_OFRECER_ASESOR, ahora
            )
            return Respuesta(conversacion.id, Intencion.DESCONOCIDA, False, texto_enviado)

        await self._anotar_intencion(guardado, lectura.intencion)
        conversacion.anotar_intento_entendido()
        await self._conversaciones.guardar(conversacion)
        salida = await self._encaminar(empresa_id, conversacion, entrante, lectura, texto, ahora)
        return Respuesta(conversacion.id, lectura.intencion, False, salida)

    # -- pasos ------------------------------------------------------------------------

    async def _resolver_cliente(self, entrante: MensajeEntrante) -> UUID:
        conocido = await self._clientes.cliente_de(entrante.telefono)
        if conocido is not None:
            return conocido[0]
        # Alguien que escribe por primera vez. No es un error: es el caso de uso del canal.
        return await self._clientes.alta_rapida(
            telefono=entrante.telefono, nombre=f"WhatsApp {entrante.telefono[-4:]}"
        )

    async def _hilo_de(
        self, empresa_id: EmpresaId, cliente_id: UUID, ahora: datetime
    ) -> Conversacion:
        abierta = await self._conversaciones.abierta_de(cliente_id)
        if abierta is not None:
            return abierta
        nueva = Conversacion(
            id=uuid4(), empresa_id=empresa_id, cliente_id=cliente_id, created_at=ahora
        )
        await self._conversaciones.agregar(nueva)
        return nueva

    async def _texto_de(self, entrante: MensajeEntrante) -> tuple[str, TipoContenido, bool]:
        """El texto a interpretar, su tipo original, y si la transcripción fue mala.

        El audio **no se devuelve ni se guarda** (HS-T7 RN-03): lo que sale de acá es texto.
        """
        if entrante.audio_id is None:
            return entrante.texto or "", TipoContenido.TEXTO, False
        transcripcion = await self._transcriptor.transcribir(entrante.audio_id)
        pobre = transcripcion.calidad < UMBRAL_DE_TRANSCRIPCION
        return transcripcion.texto, TipoContenido.AUDIO, pobre

    async def _guardar_entrante(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        entrante: MensajeEntrante,
        texto: str,
        tipo: TipoContenido,
        ahora: datetime,
    ) -> Mensaje:
        mensaje = Mensaje(
            id=uuid4(),
            conversacion_id=conversacion.id,
            empresa_id=empresa_id,
            direccion=DireccionMensaje.ENTRANTE,
            tipo_contenido=tipo,
            contenido=texto,
            momento=entrante.momento or ahora,
            externo_id=entrante.externo_id,
        )
        await self._mensajes.agregar(mensaje)
        return mensaje

    async def _anotar_intencion(self, mensaje: Mensaje, intencion: Intencion) -> None:
        """HS-T2 RN-02: el mensaje interpretado queda con la intención que el agente aplicó.

        Los caminos que no interpretan no pasan por acá y la dejan en `None` («no se clasificó»).
        """
        mensaje.intencion = intencion
        await self._mensajes.guardar(mensaje)

    async def _encaminar(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        entrante: MensajeEntrante,
        lectura: Lectura,
        texto: str,
        ahora: datetime,
    ) -> str | None:
        if lectura.intencion is Intencion.TURNO:
            return await self._ofrecer_horarios(empresa_id, conversacion, entrante, ahora)
        if lectura.intencion is Intencion.FAQ or lectura.intencion is Intencion.CONSULTA:
            return await self._responder_faq(empresa_id, conversacion, entrante, texto, ahora)
        # `PAGO` no tiene flujo automático en este épico: el cobro lo genera una persona
        # (HU-E6-03), así que lo honesto es derivar en vez de improvisar una respuesta.
        return await self._responder(
            empresa_id, conversacion, entrante.telefono, MENSAJE_OFRECER_ASESOR, ahora
        )

    async def _ofrecer_horarios(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        entrante: MensajeEntrante,
        ahora: datetime,
    ) -> str | None:
        """HU-E8-01 RN-01 y RN-02: **la disponibilidad real, no la que el modelo imagine.**

        Los horarios salen de `scheduling`, ya cruzados contra los turnos tomados. El agente no
        elige ninguno: los ofrece, y la reserva la confirma el motor determinista cuando el
        cliente responde.
        """
        manana = (ahora + timedelta(days=1)).date()
        horarios = await self._agenda.horarios_ofrecibles(dia=manana, limite=HORARIOS_A_OFRECER)
        if not horarios:
            return await self._responder(
                empresa_id,
                conversacion,
                entrante.telefono,
                "No tengo horarios disponibles para mañana. ¿Querés que te derive con un asesor?",
                ahora,
            )
        listado = " o ".join(uno.inicio.strftime("%H:%M") for uno in horarios)
        return await self._responder(
            empresa_id,
            conversacion,
            entrante.telefono,
            f"Tengo disponible mañana a las {listado}. ¿Cuál preferís?",
            ahora,
        )

    async def _responder_faq(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        entrante: MensajeEntrante,
        texto: str,
        ahora: datetime,
    ) -> str | None:
        """HU-E8-03. Por significado (RN-02), y con umbral (RN-03).

        **La respuesta es la que escribió la empresa, palabra por palabra.** El modelo no la
        reescribe ni la resume: una FAQ es lo que el negocio decidió contestar, y dejar que un
        modelo la parafrasee es dejar que cambie lo que la empresa dice.
        """
        vector = await self._embeddings.vectorizar(texto)
        candidatas = await self._faqs.buscar_por_significado(vector, limite=1)
        mejor = candidatas[0] if candidatas else None
        if mejor is None or not mejor.alcanza:
            # RN-03: ninguna FAQ alcanza, se ofrece derivar.
            return await self._responder(
                empresa_id, conversacion, entrante.telefono, MENSAJE_OFRECER_ASESOR, ahora
            )
        mejor.faq.registrar_uso()
        await self._faqs.guardar(mejor.faq)
        return await self._responder(
            empresa_id, conversacion, entrante.telefono, mejor.faq.respuesta, ahora
        )

    async def _escalar(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        telefono: str,
        motivo: str,
        ahora: datetime,
    ) -> Respuesta:
        """HU-E8-05. Se registra el motivo, se avisa al cliente, y el agente calla."""
        await self._escalamientos.agregar(
            Escalamiento(
                id=uuid4(),
                conversacion_id=conversacion.id,
                empresa_id=empresa_id,
                motivo=motivo,
                created_at=ahora,
                updated_at=ahora,
            )
        )
        conversacion.anotar_intento_entendido()
        await self._conversaciones.guardar(conversacion)
        texto = await self._responder(empresa_id, conversacion, telefono, MENSAJE_DERIVACION, ahora)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.CONVERSATIONAL,
                accion="escalar_conversacion",
                entidad_afectada=f"Conversacion:{conversacion.id}",
                resultado=Resultado.COMPLETADO,
                iniciador=Iniciador.IA,
            )
        )
        return Respuesta(conversacion.id, Intencion.DESCONOCIDA, escalado=True, texto_enviado=texto)

    async def _responder(
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

    async def _auditar(
        self,
        empresa_id: EmpresaId,
        conversacion: Conversacion,
        lectura: Lectura,
        ahora: datetime,
    ) -> None:
        """HS-T2 RN-05: **iniciador IA**.

        Es la marca que hace que el panel de auditoría del épico 10 pueda contestar «qué hizo
        el agente solo», que es la pregunta que alguien se hace la primera vez que un cliente
        se queja de algo que nadie recuerda haber hecho.
        """
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.CONVERSATIONAL,
                accion=f"interpretar_mensaje:{lectura.intencion.value}",
                entidad_afectada=f"Conversacion:{conversacion.id}",
                resultado=Resultado.COMPLETADO,
                iniciador=Iniciador.IA,
            )
        )


def _pide_una_persona(texto: str) -> bool:
    """HU-E8-05 RN-01, sin pasar por el modelo.

    Es una comprobación de subcadenas y es a propósito: la única intención que **no puede**
    depender de que un modelo la entienda es justamente la de alguien que ya se cansó del
    modelo.
    """
    normalizado = texto.lower()
    return any(frase in normalizado for frase in PEDIDOS_DE_HUMANO)


__all__ = [
    "HORARIOS_A_OFRECER",
    "UMBRAL_DE_CONFIANZA",
    "UMBRAL_DE_SIMILITUD",
    "UMBRAL_DE_TRANSCRIPCION",
    "ProcesarMensajeEntrante",
    "Respuesta",
]
