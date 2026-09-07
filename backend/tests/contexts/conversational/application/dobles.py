"""Los dobles de `conversational`, escritos a mano.

Como en el resto del sistema: implementaciones de verdad de los puertos y no `Mock`, porque un
`Mock` satisface cualquier interfaz, incluida una que ya no existe.

**`AgendaEnMemoria` es el doble más importante del archivo**, y lo es por lo que *no* tiene:
ningún método que el intérprete pueda alcanzar. El agente sólo puede llamarlo a través del
puerto, y el puerto tiene cuatro operaciones — que es exactamente la decisión D38 hecha
superficie. Un doble con un `ejecutar(sql)` haría que los tests pasaran mientras la garantía
real no existe.

**`InterpreteProgramado` devuelve lo que se le diga**, incluida una confianza cualquiera. Es lo
que permite probar los dos caminos que importan: el de creerle y el de no creerle.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.ports import (
    HorarioOfrecible,
    Lectura,
    Transcripcion,
    TurnoDelCliente,
)
from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    EstadoConversacion,
    Intencion,
    Mensaje,
)
from cheatsheet.contexts.conversational.domain.escalamiento import (
    ESTADOS_SIN_AGENTE,
    Escalamiento,
)
from cheatsheet.contexts.conversational.domain.faq import FAQ, CoincidenciaDeFAQ


class RepositorioConversacionEnMemoria:
    def __init__(self, *hilos: Conversacion) -> None:
        self.hilos: dict[UUID, Conversacion] = {uno.id: uno for uno in hilos}

    async def agregar(self, conversacion: Conversacion) -> None:
        self.hilos[conversacion.id] = conversacion

    async def guardar(self, conversacion: Conversacion) -> None:
        self.hilos[conversacion.id] = conversacion

    async def buscar_por_id(self, conversacion_id: UUID) -> Conversacion | None:
        return self.hilos.get(conversacion_id)

    async def abierta_de(self, cliente_id: UUID) -> Conversacion | None:
        return next(
            (
                uno
                for uno in self.hilos.values()
                if uno.cliente_id == cliente_id and uno.estado is EstadoConversacion.ACTIVA
            ),
            None,
        )

    async def listar(self, *, solo_escaladas: bool = False) -> list[Conversacion]:
        del solo_escaladas
        return list(self.hilos.values())


class RepositorioMensajeEnMemoria:
    def __init__(self, *mensajes: Mensaje) -> None:
        self.mensajes: dict[UUID, Mensaje] = {uno.id: uno for uno in mensajes}

    async def agregar(self, mensaje: Mensaje) -> None:
        self.mensajes[mensaje.id] = mensaje

    async def guardar(self, mensaje: Mensaje) -> None:
        self.mensajes[mensaje.id] = mensaje

    async def buscar_por_externo_id(self, externo_id: str) -> Mensaje | None:
        return next((uno for uno in self.mensajes.values() if uno.externo_id == externo_id), None)

    async def del_hilo(self, conversacion_id: UUID) -> list[Mensaje]:
        del_hilo = [uno for uno in self.mensajes.values() if uno.conversacion_id == conversacion_id]
        return sorted(del_hilo, key=lambda uno: uno.momento)

    @property
    def salientes(self) -> list[Mensaje]:
        return [uno for uno in self.mensajes.values() if uno.origen is not None]


class RepositorioEscalamientoEnMemoria:
    def __init__(self, *escalamientos: Escalamiento) -> None:
        self.escalamientos: dict[UUID, Escalamiento] = {uno.id: uno for uno in escalamientos}

    async def agregar(self, escalamiento: Escalamiento) -> None:
        self.escalamientos[escalamiento.id] = escalamiento

    async def guardar(self, escalamiento: Escalamiento) -> None:
        self.escalamientos[escalamiento.id] = escalamiento

    async def buscar_por_id(self, escalamiento_id: UUID) -> Escalamiento | None:
        return self.escalamientos.get(escalamiento_id)

    async def abierto_de(self, conversacion_id: UUID) -> Escalamiento | None:
        return next(
            (
                uno
                for uno in self.escalamientos.values()
                if uno.conversacion_id == conversacion_id and uno.estado in ESTADOS_SIN_AGENTE
            ),
            None,
        )

    async def listar_abiertos(self) -> list[Escalamiento]:
        return [uno for uno in self.escalamientos.values() if uno.esta_abierto]


class RepositorioFAQEnMemoria:
    """FAQ en un dict, con una búsqueda que **no entiende significados**.

    Devuelve las coincidencias que se le programaron. Fingir una búsqueda semántica en Python
    haría que los tests de HU-E8-03 RN-02 pasaran probando la imitación y no la consulta, que
    corre contra PostgreSQL y se prueba en `tests/integracion/`.
    """

    def __init__(self, *faqs: FAQ) -> None:
        self.faqs: dict[UUID, FAQ] = {una.id: una for una in faqs}
        self.coincidencias: list[CoincidenciaDeFAQ] = []
        self.vectores: dict[UUID, list[float]] = {}

    async def agregar(self, faq: FAQ) -> None:
        self.faqs[faq.id] = faq

    async def guardar(self, faq: FAQ) -> None:
        self.faqs[faq.id] = faq

    async def guardar_vector(self, faq: FAQ, vector: Sequence[float]) -> None:
        self.faqs[faq.id] = faq
        self.vectores[faq.id] = list(vector)

    async def eliminar(self, faq_id: UUID) -> None:
        self.faqs.pop(faq_id, None)
        self.vectores.pop(faq_id, None)

    async def buscar_por_id(self, faq_id: UUID) -> FAQ | None:
        return self.faqs.get(faq_id)

    async def listar(self) -> list[FAQ]:
        return list(self.faqs.values())

    async def buscar_por_significado(
        self, vector: Sequence[float], *, limite: int = 3
    ) -> list[CoincidenciaDeFAQ]:
        del vector
        return self.coincidencias[:limite]

    async def pendientes_de_indexar(self) -> list[FAQ]:
        return [una for una in self.faqs.values() if una.embedding_obsoleto]


class InterpreteProgramado:
    """Devuelve la lectura que se le puso. Registra qué texto vio, para poder afirmarlo."""

    def __init__(self, lectura: Lectura | None = None) -> None:
        self.lectura = lectura or Lectura(intencion=Intencion.DESCONOCIDA, confianza=0.0)
        self.vistos: list[str] = []

    async def leer(self, texto: str, *, historial: Sequence[str] = ()) -> Lectura:
        del historial
        self.vistos.append(texto)
        return self.lectura


class TranscriptorProgramado:
    def __init__(self, texto: str = "quiero un turno", calidad: float = 0.9) -> None:
        self.texto = texto
        self.calidad = calidad
        self.pedidos: list[str] = []

    async def transcribir(self, audio_id: str) -> Transcripcion:
        self.pedidos.append(audio_id)
        return Transcripcion(texto=self.texto, calidad=self.calidad)


class MensajeriaEnMemoria:
    """Guarda lo que se mandó. `caida=True` simula un canal que no acepta nada."""

    def __init__(self, *, caida: bool = False) -> None:
        self.enviados: list[tuple[str, str]] = []
        self.caida = caida

    async def enviar(self, *, telefono: str, texto: str) -> str:
        if self.caida:
            raise RuntimeError("WhatsApp no responde")
        self.enviados.append((telefono, texto))
        return f"wamid-{len(self.enviados)}"

    @property
    def textos(self) -> list[str]:
        return [texto for _, texto in self.enviados]


class DirectorioEnMemoria:
    def __init__(self, conocidos: dict[str, tuple[UUID, str]] | None = None) -> None:
        self.conocidos = conocidos or {}
        self.altas: list[str] = []

    async def cliente_de(self, telefono: str) -> tuple[UUID, str] | None:
        return self.conocidos.get(telefono)

    async def alta_rapida(self, *, telefono: str, nombre: str) -> UUID:
        self.altas.append(telefono)
        nuevo = uuid4()
        self.conocidos[telefono] = (nuevo, nombre)
        return nuevo


class EmbeddingsEnMemoria:
    def __init__(self, *, cae: bool = False) -> None:
        self.cae = cae
        self.pedidos: list[str] = []

    @property
    def version(self) -> str:
        return "doble-v1"

    async def vectorizar(self, texto: str) -> list[float]:
        if self.cae:
            raise RuntimeError("el proveedor de embeddings no responde")
        self.pedidos.append(texto)
        return [0.1, 0.2, 0.3]


class AgendaEnMemoria:
    """`PortAgenda`. **Cuatro operaciones, y ninguna que el modelo pueda alcanzar.**

    Ver el docstring del módulo: la angostura de este doble es la decisión D38 hecha superficie
    de prueba.
    """

    def __init__(self, *horarios: HorarioOfrecible) -> None:
        self.horarios = list(horarios)
        self.turnos: list[TurnoDelCliente] = []
        self.reservados: list[HorarioOfrecible] = []
        self.cancelados: list[UUID] = []
        #: Cuando está en `True`, `reservar` levanta: es el motor rechazando el solapamiento.
        self.ocupado = False

    async def horarios_ofrecibles(self, *, dia: date, limite: int = 4) -> list[HorarioOfrecible]:
        del dia
        return self.horarios[:limite]

    async def reservar(self, *, cliente_id: UUID, horario: HorarioOfrecible) -> UUID:
        del cliente_id
        if self.ocupado:
            from cheatsheet.contexts.scheduling.application.errors import FranjaOcupada

            raise FranjaOcupada("El horario seleccionado no está disponible.")
        self.reservados.append(horario)
        return uuid4()

    async def turnos_de(self, cliente_id: UUID) -> list[TurnoDelCliente]:
        del cliente_id
        return self.turnos

    async def cancelar(self, turno_id: UUID) -> None:
        self.cancelados.append(turno_id)


class PublicadorEnMemoria:
    def __init__(self) -> None:
        self.eventos: list[object] = []

    async def publicar(self, evento: object) -> None:
        self.eventos.append(evento)

    @property
    def acciones(self) -> list[str]:
        return [getattr(uno, "accion", "") for uno in self.eventos]

    @property
    def iniciadores(self) -> list[str]:
        """Qué iniciador quedó en cada evento. **HS-T2 RN-05** se afirma con esto."""
        return [str(getattr(uno, "quien_inicio", "")) for uno in self.eventos]


def un_horario(inicio: datetime) -> HorarioOfrecible:
    return HorarioOfrecible(recurso_id=uuid4(), servicio_id=uuid4(), inicio=inicio)


__all__ = [
    "AgendaEnMemoria",
    "DirectorioEnMemoria",
    "EmbeddingsEnMemoria",
    "InterpreteProgramado",
    "MensajeriaEnMemoria",
    "PublicadorEnMemoria",
    "RepositorioConversacionEnMemoria",
    "RepositorioEscalamientoEnMemoria",
    "RepositorioFAQEnMemoria",
    "RepositorioMensajeEnMemoria",
    "TranscriptorProgramado",
    "un_horario",
]
