"""Los dobles de `conversational`, escritos a mano.

Como en el resto del sistema: implementaciones de verdad de los puertos y no `Mock`, porque un
`Mock` satisface cualquier interfaz, incluida una que ya no existe.

**`AgendaEnMemoria` es el doble más importante del archivo**, y lo es por lo que *no* tiene:
ningún método que el intérprete pueda alcanzar. El agente sólo puede llamarlo a través del
puerto, y el puerto tiene cinco operaciones — que es exactamente la decisión D38 hecha
superficie. Un doble con un `ejecutar(sql)` haría que los tests pasaran mientras la garantía
real no existe. Sus rechazos son **programables**: es cómo se prueba que el motor se adelantó
(CA4), que el horario ya pasó (CA7) o que el turno ya no se puede cancelar.

**`InterpreteProgramado` devuelve lo que se le diga**, incluida una confianza cualquiera. Es lo
que permite probar los dos caminos que importan: el de creerle y el de no creerle. Registra lo
que **recibió** —el texto y el historial— porque es lo que afirma que no se filtran datos
personales ni respuestas a una oferta.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.errors import (
    HorarioNoDisponible,
    TurnoNoCancelable,
)
from cheatsheet.contexts.conversational.application.ports import (
    Lectura,
    ServicioOfrecible,
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
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import HorarioOfrecible
from cheatsheet.contexts.conversational.domain.uso_de_faq import ConteoDeUsos, UsoDeFAQ
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA, MesCalendario


class RepositorioConversacionEnMemoria:
    def __init__(self, *hilos: Conversacion) -> None:
        self.hilos: dict[UUID, Conversacion] = {uno.id: uno for uno in hilos}
        #: Con qué `bloquear` se pidió el hilo cada vez: el agente lo pide bloqueado (T10).
        self.bloqueos: list[bool] = []

    async def agregar(self, conversacion: Conversacion) -> None:
        self.hilos[conversacion.id] = conversacion

    async def guardar(self, conversacion: Conversacion) -> None:
        self.hilos[conversacion.id] = conversacion

    async def buscar_por_id(self, conversacion_id: UUID) -> Conversacion | None:
        return self.hilos.get(conversacion_id)

    async def abierta_de(self, cliente_id: UUID, *, bloquear: bool = False) -> Conversacion | None:
        self.bloqueos.append(bloquear)
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
        #: Cuántas veces se pidió `guardar`: el agente no debe escribir la fila de la FAQ.
        self.guardados = 0

    async def agregar(self, faq: FAQ) -> None:
        self.faqs[faq.id] = faq

    async def guardar(self, faq: FAQ) -> None:
        self.guardados += 1
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


class UsosDeFAQEnMemoria:
    """Los usos de FAQ en una lista, con la misma idempotencia por mensaje que la tabla."""

    def __init__(self) -> None:
        self.usos: list[UsoDeFAQ] = []

    async def registrar(self, uso: UsoDeFAQ) -> None:
        if all(otro.mensaje_id != uso.mensaje_id for otro in self.usos):
            self.usos.append(uso)

    async def conteos(self, mes: MesCalendario) -> dict[UUID, ConteoDeUsos]:
        anterior = mes.anterior()
        por_faq: dict[UUID, list[UsoDeFAQ]] = {}
        for uso in self.usos:
            por_faq.setdefault(uso.faq_id, []).append(uso)
        return {
            faq_id: ConteoDeUsos(
                este_mes=sum(mes.inicio <= u.usado_en < mes.fin for u in usos),
                mes_anterior=sum(anterior.inicio <= u.usado_en < anterior.fin for u in usos),
                desde_el_seguimiento=len(usos),
            )
            for faq_id, usos in por_faq.items()
        }

    async def contar(self, *, desde: datetime, hasta: datetime, faq_id: UUID | None) -> int:
        return sum(
            desde <= uso.usado_en < hasta and (faq_id is None or uso.faq_id == faq_id)
            for uso in self.usos
        )


class InterpreteProgramado:
    """Devuelve la lectura que se le puso. Registra qué vio, para poder afirmarlo.

    Con `programar` se le da una secuencia: cada llamada consume la siguiente, y la última se
    repite. Es lo que permite probar una conversación de varios mensajes.
    """

    def __init__(self, lectura: Lectura | None = None) -> None:
        self.cola: list[Lectura] = [
            lectura or Lectura(intencion=Intencion.DESCONOCIDA, confianza=0.0)
        ]
        self.vistos: list[str] = []
        self.historiales: list[list[str]] = []

    @property
    def lectura(self) -> Lectura:
        return self.cola[0]

    @lectura.setter
    def lectura(self, valor: Lectura) -> None:
        self.cola = [valor]

    def programar(self, *lecturas: Lectura) -> None:
        self.cola = list(lecturas)

    async def leer(self, texto: str, *, historial: Sequence[str] = ()) -> Lectura:
        self.vistos.append(texto)
        self.historiales.append(list(historial))
        return self.cola.pop(0) if len(self.cola) > 1 else self.cola[0]


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

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        del telefono, nombre, idioma, parametros
        raise AssertionError("el agente y el operador contestan con texto, nunca con plantilla")

    @property
    def textos(self) -> list[str]:
        return [texto for _, texto in self.enviados]


class DirectorioEnMemoria:
    def __init__(self, conocidos: dict[str, tuple[UUID, str]] | None = None) -> None:
        self.conocidos = conocidos or {}
        self.altas: list[str] = []

    async def cliente_de(self, telefono: str) -> tuple[UUID, str] | None:
        return self.conocidos.get(telefono)

    async def telefono_de(self, cliente_id: UUID) -> str | None:
        return next(
            (telefono for telefono, (uno, _) in self.conocidos.items() if uno == cliente_id),
            None,
        )

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


#: El servicio que usan casi todos los tests, con un id fijo para poder compararlo.
SERVICIO_DE_PRUEBA = ServicioOfrecible(id=UUID(int=1), nombre="Consulta general")
RECURSO_DE_PRUEBA = UUID(int=2)


class AgendaEnMemoria:
    """`PortAgenda`. **Cinco operaciones, y ninguna que el modelo pueda alcanzar.**

    Ver el docstring del módulo: la angostura de este doble es la decisión D38 hecha superficie
    de prueba.
    """

    def __init__(
        self,
        *libres: HorarioOfrecible,
        servicios: Sequence[ServicioOfrecible] | None = None,
    ) -> None:
        self.libres = list(libres)
        self.servicios = list(servicios) if servicios is not None else [SERVICIO_DE_PRUEBA]
        self.turnos: list[TurnoDelCliente] = []
        self.reservados: list[HorarioOfrecible] = []
        self.cancelados: list[UUID] = []
        self.consultas: list[tuple[UUID, date]] = []
        self.tomados: set[datetime] = set()
        #: Cuando está en `True`, `reservar` rechaza todo: es el motor viendo el solapamiento.
        self.ocupado = False
        #: Un rechazo por recurso: es cómo se prueba que se prueba el siguiente recurso (T6).
        self.rechazos: dict[UUID, Exception] = {}
        #: Ids que `cancelar` rechaza, como un turno que se canceló desde el panel entretanto.
        self.no_cancelables: set[UUID] = set()

    async def servicios_ofrecibles(self) -> list[ServicioOfrecible]:
        return list(self.servicios)

    async def horarios_libres(self, *, servicio_id: UUID, dia: date) -> list[HorarioOfrecible]:
        self.consultas.append((servicio_id, dia))
        return [
            uno
            for uno in self.libres
            if uno.servicio_id == servicio_id
            and uno.inicio.astimezone(ZONA_ARGENTINA).date() == dia
            and uno.inicio not in self.tomados
        ]

    async def reservar(self, *, cliente_id: UUID, horario: HorarioOfrecible) -> UUID:
        del cliente_id
        if horario.recurso_id in self.rechazos:
            raise self.rechazos[horario.recurso_id]
        if self.ocupado:
            raise HorarioNoDisponible("El horario seleccionado no está disponible.")
        self.reservados.append(horario)
        self.tomados.add(horario.inicio)
        return uuid4()

    async def turnos_de(self, cliente_id: UUID) -> list[TurnoDelCliente]:
        del cliente_id
        return list(self.turnos)

    async def cancelar(self, turno_id: UUID) -> None:
        if turno_id in self.no_cancelables:
            raise TurnoNoCancelable("El turno ya no está abierto")
        self.cancelados.append(turno_id)
        self.turnos = [uno for uno in self.turnos if uno.id != turno_id]


class PublicadorEnMemoria:
    def __init__(self) -> None:
        self.eventos: list[object] = []

    async def publicar(self, evento: object) -> None:
        self.eventos.append(evento)

    def de_la_accion(self, accion: str) -> list[EventoAuditable]:
        """Los eventos auditables de esa acción, con su forma tipada."""
        return [
            uno for uno in self.eventos if isinstance(uno, EventoAuditable) and uno.accion == accion
        ]

    @property
    def acciones(self) -> list[str]:
        return [getattr(uno, "accion", "") for uno in self.eventos]

    @property
    def iniciadores(self) -> list[str]:
        """Qué iniciador quedó en cada evento. **HS-T2 RN-05** se afirma con esto."""
        return [str(getattr(uno, "quien_inicio", "")) for uno in self.eventos]


def un_horario(
    inicio: datetime,
    *,
    servicio_id: UUID = SERVICIO_DE_PRUEBA.id,
    recurso_id: UUID = RECURSO_DE_PRUEBA,
) -> HorarioOfrecible:
    return HorarioOfrecible(recurso_id=recurso_id, servicio_id=servicio_id, inicio=inicio)


def grilla_de(
    dia: date,
    *,
    desde: int = 9,
    hasta: int = 18,
    cada: int = 30,
    servicio_id: UUID = SERVICIO_DE_PRUEBA.id,
    recurso_id: UUID = RECURSO_DE_PRUEBA,
) -> list[HorarioOfrecible]:
    """Un inicio cada `cada` minutos de `desde` a `hasta` (exclusive), en hora argentina."""
    inicio = datetime.combine(dia, time(desde), tzinfo=ZONA_ARGENTINA)
    cantidad = (hasta - desde) * 60 // cada
    return [
        un_horario(
            inicio + timedelta(minutes=cada * indice),
            servicio_id=servicio_id,
            recurso_id=recurso_id,
        )
        for indice in range(cantidad)
    ]


__all__ = [
    "RECURSO_DE_PRUEBA",
    "SERVICIO_DE_PRUEBA",
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
    "UsosDeFAQEnMemoria",
    "grilla_de",
    "un_horario",
]
