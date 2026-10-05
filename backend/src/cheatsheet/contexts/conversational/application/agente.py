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
4. **Responder a lo que el agente ofreció.** Si hay un diálogo pendiente («elegí un horario»,
   «¿confirmás?») y el mensaje es la respuesta, lo lee un analizador **determinista** y se actúa
   **sin llamar al modelo** (`TurnosPorWhatsApp.continuar`).
5. **Interpretar.** El modelo devuelve una intención, una confianza y, si es un turno, qué quiere
   hacer y para cuándo — y **nada más**. Antes de salir, el texto y el historial pasan por
   `ocultar_datos_personales` (`CLAUDE.md` §3.6).
6. **Encaminar.** Por debajo del umbral, o agotados los intentos, se escala.

**Lo que el modelo no puede hacer** (decisión **D38**): reservar, cancelar, cobrar, ni mandar
un mensaje que él haya redactado sobre datos que él haya elegido. Las acciones son llamadas a
`PortAgenda`, que del otro lado son los casos de uso deterministas de `scheduling` con su
restricción de exclusión, y los ids que se reservan o cancelan salen del `Dialogo` que armó el
sistema. Un prompt injection que logre convencer al modelo de que el cliente quiere cancelar
produce, como mucho, una pregunta de confirmación sobre un turno de ese cliente.

**Si hay un escalamiento abierto, el agente no contesta** (HU-E9-01 RN-02). El mensaje se
registra igual —el operador lo tiene que ver— pero no se interpreta ni se responde.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.contexto import (
    ContextoDelMensaje,
    Desenlace,
    evento_del_agente,
)
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
from cheatsheet.contexts.conversational.application.salida import SalidaAlCliente
from cheatsheet.contexts.conversational.application.turnos_por_whatsapp import TurnosPorWhatsApp
from cheatsheet.contexts.conversational.domain.conversacion import (
    MENSAJE_DERIVACION,
    MENSAJE_OFRECER_ASESOR,
    Conversacion,
    DireccionMensaje,
    Intencion,
    Mensaje,
    TipoContenido,
)
from cheatsheet.contexts.conversational.domain.datos_personales import (
    historial_para_el_interprete,
    ocultar_datos_personales,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    MOTIVO_BAJA_CONFIANZA,
    MOTIVO_PEDIDO_POR_EL_CLIENTE,
    MOTIVO_TRANSCRIPCION_POBRE,
    Escalamiento,
)
from cheatsheet.contexts.conversational.domain.faq import UMBRAL_DE_SIMILITUD
from cheatsheet.contexts.conversational.domain.pedido_de_persona import pide_una_persona
from cheatsheet.shared.auditoria import Resultado
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
        self._embeddings = embeddings
        self._publicador = publicador
        self._salida = SalidaAlCliente(mensajes=mensajes, mensajeria=mensajeria)
        self._turnos = TurnosPorWhatsApp(
            conversaciones=conversaciones, salida=self._salida, agenda=agenda, publicador=publicador
        )

    async def ejecutar(
        self, *, empresa_id: EmpresaId, entrante: MensajeEntrante, ahora: datetime
    ) -> Respuesta:
        # 1. Idempotencia, antes que nada. Ver el docstring del módulo.
        if await self._mensajes.buscar_por_externo_id(entrante.externo_id) is not None:
            raise MensajeYaProcesado(f"El mensaje {entrante.externo_id} ya fue procesado")

        cliente_id = await self._resolver_cliente(entrante)
        conversacion = await self._hilo_de(empresa_id, cliente_id, ahora)
        contexto = ContextoDelMensaje(
            empresa_id, conversacion, cliente_id, entrante.telefono, ahora
        )

        # 2. Transcribir si hace falta.
        texto, tipo, transcripcion_pobre = await self._texto_de(entrante)

        # 3. Registrar. **Antes** de interpretar: si el modelo se cae, el mensaje quedó.
        guardado = await self._guardar_entrante(
            empresa_id, conversacion, entrante, texto, tipo, ahora
        )
        conversacion.registrar_actividad(ahora)

        # Si un operador está atendiendo, el agente calla (HU-E9-01 RN-02).
        if await self._escalamientos.abierto_de(conversacion.id) is not None:
            await self._conversaciones.guardar(conversacion)
            return Respuesta(
                conversacion.id, Intencion.DESCONOCIDA, escalado=True, texto_enviado=None
            )

        if transcripcion_pobre:
            return await self._escalar(contexto, MOTIVO_TRANSCRIPCION_POBRE)

        # El pedido explícito de una persona no pasa por el modelo: ver `pide_una_persona`.
        if pide_una_persona(texto):
            return await self._escalar(contexto, MOTIVO_PEDIDO_POR_EL_CLIENTE)

        # 4. Una respuesta a lo que el agente ofreció se lee sin el modelo (T3).
        desenlace = await self._turnos.continuar(contexto, texto)
        if desenlace is not None:
            await self._anotar_intencion(guardado, Intencion.TURNO)
            return await self._terminar(contexto, desenlace)

        # 5. Interpretar: con los datos personales ocultos (`CLAUDE.md` §3.6).
        historial = historial_para_el_interprete(await self._mensajes.del_hilo(conversacion.id))
        lectura = await self._interprete.leer(ocultar_datos_personales(texto), historial=historial)
        await self._auditar(contexto, lectura)
        if self._turnos.completa_un_pedido_en_curso(contexto, lectura):
            # T8: «el jueves a la tarde» completa la reserva que pidió el día, aunque venga floja.
            confianza = max(lectura.confianza, UMBRAL_DE_CONFIANZA)
            lectura = replace(lectura, intencion=Intencion.TURNO, confianza=confianza)

        # 6. Encaminar.
        if lectura.confianza < UMBRAL_DE_CONFIANZA:
            await self._anotar_intencion(guardado, Intencion.DESCONOCIDA)
            conversacion.anotar_intento_fallido()
            if conversacion.agoto_los_intentos:
                return await self._escalar(contexto, MOTIVO_BAJA_CONFIANZA)
            await self._conversaciones.guardar(conversacion)
            texto_enviado = await self._decir(contexto, MENSAJE_OFRECER_ASESOR)
            return Respuesta(conversacion.id, Intencion.DESCONOCIDA, False, texto_enviado)

        await self._anotar_intencion(guardado, lectura.intencion)
        conversacion.anotar_intento_entendido()
        if lectura.intencion is not Intencion.TURNO:
            conversacion.cerrar_dialogo()  # cambió de tema: la oferta pendiente ya no vale
        await self._conversaciones.guardar(conversacion)
        return await self._encaminar(contexto, lectura, texto)

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
        # Bloqueado (T10): dos mensajes casi simultáneos del mismo cliente se procesan de a uno,
        # y el segundo lee el diálogo ya consumido. Sin esto, «1» y «2» podrían reservar dos turnos.
        abierta = await self._conversaciones.abierta_de(cliente_id, bloquear=True)
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
        self, contexto: ContextoDelMensaje, lectura: Lectura, texto: str
    ) -> Respuesta:
        if lectura.intencion is Intencion.TURNO:
            return await self._terminar(contexto, await self._turnos.atender(contexto, lectura))
        if lectura.intencion is Intencion.FAQ or lectura.intencion is Intencion.CONSULTA:
            salida = await self._responder_faq(contexto, texto)
        else:
            # `PAGO` no tiene flujo automático en este épico: el cobro lo genera una persona
            # (HU-E6-03), así que lo honesto es derivar en vez de improvisar una respuesta.
            salida = await self._decir(contexto, MENSAJE_OFRECER_ASESOR)
        return Respuesta(contexto.conversacion.id, lectura.intencion, False, salida)

    async def _terminar(self, contexto: ContextoDelMensaje, desenlace: Desenlace) -> Respuesta:
        """Cierra un turno: si el paso pide una persona, se escala; si no, ya contestó."""
        if desenlace.escalar_por is not None:
            return await self._escalar(contexto, desenlace.escalar_por)
        return Respuesta(contexto.conversacion.id, Intencion.TURNO, False, desenlace.texto)

    async def _responder_faq(self, contexto: ContextoDelMensaje, texto: str) -> str | None:
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
            return await self._decir(contexto, MENSAJE_OFRECER_ASESOR)
        mejor.faq.registrar_uso()
        await self._faqs.guardar(mejor.faq)
        return await self._decir(contexto, mejor.faq.respuesta)

    async def _escalar(self, contexto: ContextoDelMensaje, motivo: str) -> Respuesta:
        """HU-E8-05. Se registra el motivo, se avisa al cliente, y el agente calla."""
        conversacion, ahora = contexto.conversacion, contexto.ahora
        await self._escalamientos.agregar(
            Escalamiento(
                id=uuid4(),
                conversacion_id=conversacion.id,
                empresa_id=contexto.empresa_id,
                motivo=motivo,
                created_at=ahora,
                updated_at=ahora,
            )
        )
        conversacion.anotar_intento_entendido()
        conversacion.cerrar_dialogo()  # escalar deja sin efecto lo que se había ofrecido
        await self._conversaciones.guardar(conversacion)
        texto = await self._decir(contexto, MENSAJE_DERIVACION)
        await self._publicar(contexto, "escalar_conversacion")
        return Respuesta(conversacion.id, Intencion.DESCONOCIDA, escalado=True, texto_enviado=texto)

    async def _decir(self, contexto: ContextoDelMensaje, texto: str) -> str | None:
        return await self._salida.responder(
            contexto.empresa_id,
            contexto.conversacion,
            contexto.telefono,
            texto,
            contexto.ahora,
        )

    async def _auditar(self, contexto: ContextoDelMensaje, lectura: Lectura) -> None:
        """HS-T2 RN-05: **iniciador IA**.

        Es la marca que hace que el panel de auditoría del épico 10 pueda contestar «qué hizo
        el agente solo», que es la pregunta que alguien se hace la primera vez que un cliente
        se queja de algo que nadie recuerda haber hecho.
        """
        await self._publicar(contexto, f"interpretar_mensaje:{lectura.intencion.value}")

    async def _publicar(self, contexto: ContextoDelMensaje, accion: str) -> None:
        entidad = f"Conversacion:{contexto.conversacion.id}"
        await self._publicador.publicar(
            evento_del_agente(
                contexto, accion=accion, entidad=entidad, resultado=Resultado.COMPLETADO
            )
        )


__all__ = [
    "UMBRAL_DE_CONFIANZA",
    "UMBRAL_DE_SIMILITUD",
    "UMBRAL_DE_TRANSCRIPCION",
    "ProcesarMensajeEntrante",
    "Respuesta",
]
