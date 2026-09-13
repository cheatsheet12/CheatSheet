"""`Conversacion` y `Mensaje` — el hilo de WhatsApp, sin nada que lo interprete.

Este contexto es Core por una razón que ninguno de los otros comparte: **acá adentro hay un
modelo de lenguaje**, y un modelo de lenguaje es entrada no confiable que además suena
convincente. Todo el diseño de este archivo sale de esa frase.

La regla que lo gobierna es la decisión **D38**: **el modelo clasifica, nunca actúa.** Lo que
el LLM produce es una intención y un número de confianza — dos datos, validados contra un
esquema cerrado. Reservar un turno lo hace el caso de uso determinista de `scheduling`, con
sus mismas validaciones y su misma restricción de exclusión. HU-E8-01 RN-03 lo pide con todas
las letras («un motor determinista que valida la disponibilidad en el momento de confirmar») y
`CLAUDE.md` §5 lo exige para todo el sistema.

Dos cosas más viven acá:

- **La intención es un dato del mensaje, no un estado de la conversación.** El DER le da la
  columna a `mensaje`, y tiene razón: un hilo puede empezar preguntando un precio y terminar
  reservando, y guardar «la intención del hilo» obligaría a decidir cuál de las dos gana.

- **«Escalada» no es un estado de la conversación** (HU-E9-01 RN-01, explícito). Los estados
  son `ACTIVA` y `ARCHIVADA` y nada más; que un hilo esté escalado se deriva de que exista un
  `Escalamiento` abierto. Por eso `Conversacion` no tiene un booleano de escalamiento: sería
  el mismo hecho guardado dos veces, y el día que discrepen el agente contestaría encima de un
  operador.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada

#: Cuántos intentos seguidos sin entender aguanta el agente antes de derivar.
#:
#: Es el «tras varios intentos» de HU-E8-01, quinto criterio, hecho número. Tres es lo que
#: hace que un malentendido no escale —la gente reformula— y que cinco vueltas de «no te
#: entendí» no sean una experiencia posible.
INTENTOS_ANTES_DE_ESCALAR = 3

#: Los textos del agente. Constantes y no literales sueltos: las historias los escriben como
#: «por ejemplo», así que no son literales fijos, pero sí tienen que estar en un solo lugar
#: para que cambiarlos sea un cambio y no una búsqueda.
MENSAJE_DERIVACION = "Lo derivo con un asesor que va a continuar la conversación."
MENSAJE_SIN_TURNOS = "No encuentro turnos reservados a su nombre."
MENSAJE_OFRECER_ASESOR = "No tengo esa respuesta. ¿Querés que te derive con un asesor?"


class EstadoConversacion(StrEnum):
    """El enum `estado_conversacion` del DER. **Dos valores, y no hay un tercero.**

    HU-E9-01 RN-01 es explícita: «los estados son únicamente ACTIVA y ARCHIVADA». Un
    `ESCALADA` acá sería el mismo hecho que el `Escalamiento` abierto, guardado dos veces.
    """

    ACTIVA = "ACTIVA"
    ARCHIVADA = "ARCHIVADA"


class DireccionMensaje(StrEnum):
    ENTRANTE = "ENTRANTE"
    SALIENTE = "SALIENTE"


class TipoContenido(StrEnum):
    """El enum `tipo_contenido_mensaje` del DER.

    `AUDIO` marca lo que **llegó** como nota de voz. Después de transcribir, el contenido que
    se guarda es el texto y el audio no se conserva (HS-T7 RN-03), pero el tipo se mantiene:
    saber que el cliente mandó un audio explica por qué una interpretación salió rara.
    """

    TEXTO = "TEXTO"
    AUDIO = "AUDIO"
    IMAGEN = "IMAGEN"


class EstadoEntrega(StrEnum):
    """El enum `estado_entrega` del DER, compartido con los recordatorios del épico 6."""

    ENVIADO = "ENVIADO"
    ENTREGADO = "ENTREGADO"
    LEIDO = "LEIDO"
    FALLIDO = "FALLIDO"


class Intencion(StrEnum):
    """Las cuatro clases de HS-T2 RN-02, más la que admite no saber.

    **`DESCONOCIDA` es un valor de primera clase y no un `None`.** Es lo que el agente
    responde cuando no entiende, y lo que dispara el escalamiento — un `None` invitaría a
    tratarlo como «todavía no clasificado», que es otra cosa.
    """

    TURNO = "TURNO"
    CONSULTA = "CONSULTA"
    PAGO = "PAGO"
    FAQ = "FAQ"
    DESCONOCIDA = "DESCONOCIDA"


class OrigenDelMensaje(StrEnum):
    """Quién escribió un mensaje saliente (HU-E9-01 RN-04).

    «Los mensajes enviados por el operador se distinguen visualmente de los del agente», dice
    la regla. Para distinguirlos hay que haberlos distinguido al guardarlos, y por eso esto
    existe: sin la marca, la pantalla tendría que adivinar por el momento del escalamiento.
    """

    AGENTE = "AGENTE"
    OPERADOR = "OPERADOR"
    SISTEMA = "SISTEMA"


@dataclass(slots=True)
class Mensaje:
    """Un mensaje del hilo, entrante o saliente.

    `contenido` es texto siempre — también para una nota de voz, donde lo que se guarda es la
    transcripción. **El audio original no se persiste** (HS-T7 RN-03): es un dato personal que
    el sistema no necesita después de leerlo, y guardarlo sería guardar la voz de alguien en
    un bucket por un beneficio que nadie pidió.
    """

    id: UUID
    conversacion_id: UUID
    empresa_id: EmpresaId
    direccion: DireccionMensaje
    tipo_contenido: TipoContenido
    contenido: str
    momento: datetime
    intencion: Intencion | None = None
    estado_entrega: EstadoEntrega | None = None
    origen: OrigenDelMensaje | None = None
    #: El id que le puso WhatsApp. Es la clave de idempotencia del webhook, igual que
    #: `mp_payment_id` lo es del de MercadoPago (decisión D20 del épico 6).
    externo_id: str | None = None

    def __post_init__(self) -> None:
        if self.direccion is DireccionMensaje.SALIENTE and self.origen is None:
            # Un saliente sin origen no se puede pintar distinto en el historial, que es lo
            # que HU-E9-01 RN-04 pide.
            raise EntradaInvalida("Un mensaje saliente necesita saber quién lo escribió")

    def marcar_entrega(self, estado: EstadoEntrega) -> None:
        """HU-E8-04 RN-04. Sólo avanza: un `LEIDO` no vuelve a `ENVIADO`.

        WhatsApp manda los callbacks por su cuenta y no garantiza el orden. Sin este piso, un
        `entregado` que llega tarde pisaría un `leído` que ya había llegado, y la pantalla
        diría que el cliente no leyó algo que leyó.
        """
        orden = {
            EstadoEntrega.ENVIADO: 0,
            EstadoEntrega.ENTREGADO: 1,
            EstadoEntrega.LEIDO: 2,
            EstadoEntrega.FALLIDO: 3,
        }
        if self.estado_entrega is None or orden[estado] > orden[self.estado_entrega]:
            self.estado_entrega = estado


@dataclass(slots=True)
class Conversacion:
    """El hilo de un cliente con la empresa.

    **`contador` cuenta intentos seguidos sin entender**, y `ventana_maximo` es el tope antes
    de derivar. El DER da las dos columnas sin decir qué cuentan; ésta es la lectura que hace
    trabajo para una regla que las historias sí escriben —«el agente no entiende mi caso tras
    varios intentos → se escala automáticamente»— en lugar de inventar un límite de mensajes
    que nadie pidió. Está anotado en las decisiones del épico.

    El contador **se reinicia con cada mensaje entendido**: alguien que preguntó algo raro y
    después preguntó bien no arrastra el error.
    """

    id: UUID
    empresa_id: EmpresaId
    cliente_id: UUID
    estado: EstadoConversacion = EstadoConversacion.ACTIVA
    contador: int = 0
    ventana_maximo: int = INTENTOS_ANTES_DE_ESCALAR
    ultimo_mensaje_en: datetime | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.ventana_maximo < 1:
            raise EntradaInvalida("El tope de intentos debe ser al menos 1")

    @property
    def esta_activa(self) -> bool:
        return self.estado is EstadoConversacion.ACTIVA

    def registrar_actividad(self, momento: datetime) -> None:
        self.ultimo_mensaje_en = momento

    def anotar_intento_fallido(self) -> None:
        self.contador += 1

    def anotar_intento_entendido(self) -> None:
        self.contador = 0

    @property
    def agoto_los_intentos(self) -> bool:
        """El «tras varios intentos» de HU-E8-01, hecho pregunta."""
        return self.contador >= self.ventana_maximo

    def archivar(self) -> None:
        """Cierra el hilo. **No se desarchiva**: un pedido nuevo abre una conversación nueva.

        Es la misma decisión que toma `Escalamiento` con su cierre, y por el mismo motivo:
        reabrir un hilo viejo mezcla dos casos que no tienen por qué tener nada que ver.
        """
        if self.estado is EstadoConversacion.ARCHIVADA:
            raise InvarianteViolada("La conversación ya está archivada")
        self.estado = EstadoConversacion.ARCHIVADA
