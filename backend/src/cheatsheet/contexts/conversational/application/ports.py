"""Puertos de `conversational`.

Donde cada uno se niega es donde están las garantías, y en este contexto **la garantía más
importante es lo que un puerto no tiene**.

`PortInterprete` devuelve una `Lectura`: una intención y una confianza. **No devuelve
acciones, ni herramientas, ni un turno reservado.** El modelo no puede reservar nada porque no
hay por dónde: reservar es `PortAgenda.reservar`, que es el caso de uso determinista de
`scheduling`, con sus validaciones y su restricción de exclusión. Es la decisión **D38**, y es
por lo que un prompt injection en este sistema puede como mucho hacer que el agente conteste
algo raro — no que agende, cobre o cancele.

`PortAgenda` es el ACL contra `scheduling`. Cinco operaciones, las que HU-E8-01 y HU-E8-02
necesitan, y ninguna más: `conversational` no ve el recurso, ni su patrón semanal, ni el estado
del turno.

`PortTranscriptor` devuelve texto **y una calidad**. La calidad existe porque HS-T7 RN-04 pide
derivar cuando la transcripción no alcanza: sin ese número, «no se entendió el audio» y «el
cliente dijo algo raro» serían indistinguibles.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.conversational.domain.conversacion import (
    Conversacion,
    Intencion,
    Mensaje,
)
from cheatsheet.contexts.conversational.domain.escalamiento import Escalamiento
from cheatsheet.contexts.conversational.domain.faq import FAQ, CoincidenciaDeFAQ
from cheatsheet.contexts.conversational.domain.fuera_de_horario import AtencionDelNegocio
from cheatsheet.contexts.conversational.domain.pedido_de_turno import PedidoDeTurno
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import HorarioOfrecible
from cheatsheet.contexts.conversational.domain.uso_de_faq import ConteoDeUsos, UsoDeFAQ
from cheatsheet.shared.zona_horaria import MesCalendario


@dataclass(frozen=True, slots=True)
class Lectura:
    """Lo que el modelo entendió. **Dos datos y nada más.**

    `confianza` va de 0 a 1. Por debajo del umbral del caso de uso, la conversación escala
    (HS-T2 RN-03) — y el modelo no tiene manera de subirla diciendo que está muy seguro,
    porque el número lo produce él pero la decisión la toma el código.
    """

    intencion: Intencion
    confianza: float
    #: Lo que el modelo cree que el cliente quiere agendar, en texto libre y **sin efecto**.
    #: Lo lee un humano en el panel; ninguna decisión del sistema depende de esto.
    resumen: str = ""
    #: Lo que el modelo extrajo de un pedido de turno: acción, días, franja, hora, servicio. Sigue
    #: sin ser una acción ni una herramienta: orienta la búsqueda de horarios y nada más. Los ids
    #: que se reservan o cancelan salen del `Dialogo` que armó el sistema, nunca de acá.
    pedido_de_turno: PedidoDeTurno | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confianza <= 1.0:
            raise ValueError("La confianza va de 0 a 1")


@dataclass(frozen=True, slots=True)
class Transcripcion:
    """Lo que se entendió de una nota de voz, y qué tan bien (HS-T7).

    El audio no viene acá y no va a ningún lado: se transcribe y se descarta (RN-03).
    """

    texto: str
    calidad: float


@dataclass(frozen=True, slots=True)
class TurnoDelCliente:
    """Un turno del cliente, en el vocabulario del agente.

    Sin el recurso ni el estado: para cancelar por WhatsApp hace falta saber cuál es cuál, y
    eso lo dicen el servicio y la hora.
    """

    id: UUID
    servicio: str
    inicio: datetime
    #: Si el turno tiene una seña (HU-E6-07). Cancelarlo depende de una política que el sistema
    #: todavía no tiene tipada (pendiente #6), así que el agente no lo cancela solo.
    tiene_sena: bool = False


@dataclass(frozen=True, slots=True)
class ServicioOfrecible:
    """Un servicio que el cliente puede pedir: agendable y con al menos un recurso activo."""

    id: UUID
    nombre: str


@dataclass(frozen=True, slots=True)
class MensajeEntrante:
    """Lo que el webhook de WhatsApp trae, traducido fuera de su vocabulario.

    `externo_id` es lo que hace idempotente el procesamiento, igual que `payment_id` en el
    webhook de MercadoPago (decisión D20). Meta reintenta, y reintenta seguido.
    """

    externo_id: str
    telefono: str
    texto: str | None
    #: El id del audio en la API de Meta. Se descarga, se transcribe y **no se guarda**.
    audio_id: str | None = None
    momento: datetime | None = None


class PortRepositorioConversacion(Protocol):
    """Persistencia de hilos, siempre dentro de una empresa (RLS).

    **Sin `eliminar`.** Una conversación con un cliente es el registro de lo que se le dijo:
    se archiva, no se borra.
    """

    async def agregar(self, conversacion: Conversacion) -> None: ...

    async def guardar(self, conversacion: Conversacion) -> None: ...

    async def buscar_por_id(self, conversacion_id: UUID) -> Conversacion | None: ...

    async def abierta_de(self, cliente_id: UUID, *, bloquear: bool = False) -> Conversacion | None:
        """El hilo activo de ese cliente, si lo hay. Cómo un mensaje encuentra su conversación.

        Con `bloquear=True` toma la fila (`SELECT … FOR UPDATE`): dos mensajes casi simultáneos
        del mismo cliente se procesan de a uno, y el segundo lee el diálogo ya consumido (T10).
        """
        ...

    async def listar(self, *, solo_escaladas: bool = False) -> list[Conversacion]: ...


class PortRepositorioMensaje(Protocol):
    async def agregar(self, mensaje: Mensaje) -> None: ...

    async def guardar(self, mensaje: Mensaje) -> None: ...

    async def buscar_por_externo_id(self, externo_id: str) -> Mensaje | None:
        """El mensaje que ya se procesó. **La idempotencia del webhook de Meta.**

        Devuelve `None` cuando nunca llegó. Que exista este método y no una clave en Redis es
        lo que hace que la protección sobreviva a un `FLUSHALL`, igual que en el épico 6.
        """
        ...

    async def del_hilo(self, conversacion_id: UUID) -> list[Mensaje]:
        """El historial completo, en orden. El «contexto previo» de HU-E8-05 RN-03."""
        ...


class PortRepositorioEscalamiento(Protocol):
    async def agregar(self, escalamiento: Escalamiento) -> None: ...

    async def guardar(self, escalamiento: Escalamiento) -> None: ...

    async def buscar_por_id(self, escalamiento_id: UUID) -> Escalamiento | None: ...

    async def abierto_de(self, conversacion_id: UUID) -> Escalamiento | None:
        """El escalamiento sin resolver del hilo, si lo hay.

        **Esto es lo que decide si el agente contesta.** No hay un flag en la conversación:
        HU-E9-01 RN-01 pide que la condición se derive de acá.
        """
        ...

    async def listar_abiertos(self) -> list[Escalamiento]: ...


class PortRepositorioFAQ(Protocol):
    """Las respuestas frecuentes, con su búsqueda por significado.

    **`eliminar` sí existe acá**, y es la excepción del sistema: HU-E9-04 RN-03 pide que una
    FAQ eliminada deje de estar disponible «de forma inmediata». Una FAQ no es un registro del
    negocio —no hay nada que auditar en una pregunta que ya no se hace—, así que borrarla no
    deja nada apuntando al vacío.
    """

    async def agregar(self, faq: FAQ) -> None: ...

    async def guardar(self, faq: FAQ) -> None: ...

    async def guardar_vector(self, faq: FAQ, vector: Sequence[float]) -> None:
        """Guarda la FAQ **y** su vector.

        Separado de `guardar` porque el vector no vive en el agregado: un `list[float]` de
        1536 posiciones dentro de `FAQ` sería un objeto de dominio que arrastra un detalle de
        cómo se busca, y que habría que cargar en cada listado para no usarlo nunca.
        """
        ...

    async def eliminar(self, faq_id: UUID) -> None: ...

    async def buscar_por_id(self, faq_id: UUID) -> FAQ | None: ...

    async def listar(self) -> list[FAQ]: ...

    async def buscar_por_significado(
        self, vector: Sequence[float], *, limite: int = 3
    ) -> list[CoincidenciaDeFAQ]:
        """Las FAQ más parecidas, **sin filtrar por umbral**.

        El umbral es una regla de negocio (`UMBRAL_DE_SIMILITUD`) y la aplica el caso de uso.
        Ponerlo en el `WHERE` haría que cambiarlo fuera cambiar una consulta, y que nadie
        pudiera ver qué tan cerca estuvo lo que se descartó.
        """
        ...

    async def pendientes_de_indexar(self) -> list[FAQ]: ...


class PortUsosDeFAQ(Protocol):
    """Los usos de las FAQ: una fila inmutable por respuesta enviada (ADR-0012).

    Es **solo de alta y consulta**: no hay `guardar` ni `eliminar`. Registrar un uso no toca la
    fila de la FAQ, que es lo que impide que el agente pise una edición del administrador.
    """

    async def registrar(self, uso: UsoDeFAQ) -> None:
        """Idempotente por `mensaje_id`: un mensaje es a lo sumo un uso."""
        ...

    async def conteos(self, mes: MesCalendario) -> dict[UUID, ConteoDeUsos]:
        """Los conteos de **todas** las FAQ con usos, en una sola consulta."""
        ...

    async def contar(self, *, desde: datetime, hasta: datetime, faq_id: UUID | None) -> int:
        """Usos en `[desde, hasta)`. `faq_id=None`: todas las respuestas con FAQ de la empresa,
        incluidas las de FAQ ya borradas."""
        ...


class PortEmbeddings(Protocol):
    """Convierte texto en un vector. Un solo método, y una versión que lo identifica."""

    @property
    def version(self) -> str:
        """Qué modelo produjo el vector. Se guarda con la FAQ (ver `faq.py`)."""
        ...

    async def vectorizar(self, texto: str) -> list[float]: ...


class PortInterprete(Protocol):
    """El modelo de lenguaje. **Clasifica; no actúa.** Ver el docstring del módulo."""

    async def leer(self, texto: str, *, historial: Sequence[str] = ()) -> Lectura: ...


class PortTranscriptor(Protocol):
    """HS-T7. Baja el audio, lo transcribe y **no lo guarda**."""

    async def transcribir(self, audio_id: str) -> Transcripcion: ...


class PortMensajeria(Protocol):
    """Por dónde sale un mensaje a WhatsApp.

    Devuelve el id que le puso Meta, para poder atar los callbacks de entrega (HU-E8-04 RN-04)
    al mensaje que se guardó.
    """

    async def enviar(self, *, telefono: str, texto: str) -> str: ...

    async def enviar_plantilla(
        self, *, telefono: str, nombre: str, idioma: str, parametros: Mapping[str, str]
    ) -> str:
        """Manda una plantilla **aprobada** por Meta: lo único que se acepta fuera de las 24 h.

        `parametros` va por nombre (`parameter_name`), y devuelve el id del mensaje igual que
        `enviar`.
        """
        ...


class PortDirectorio(Protocol):
    """ACL sobre `master_data`: quién es el número que escribió.

    Devuelve `None` cuando el número no corresponde a ningún cliente de la empresa. Ese caso
    **no es un error**: es alguien que escribe por primera vez, y el agente tiene que poder
    atenderlo.
    """

    async def cliente_de(self, telefono: str) -> tuple[UUID, str] | None: ...

    async def telefono_de(self, cliente_id: UUID) -> str | None:
        """El WhatsApp del cliente, o `None` si no existe o no tiene uno registrado.

        Es lo que usa la respuesta del operador: el destino sale del cliente dueño del hilo,
        nunca de lo que mande el request.
        """
        ...

    async def alta_rapida(self, *, telefono: str, nombre: str) -> UUID:
        """Crea el cliente mínimo para poder abrirle un hilo.

        HU-E7-06 ya admitía «el cliente existe o se crea en el momento»; acá pasa lo mismo por
        otro canal. Lo que se guarda es el teléfono y un nombre provisorio — nada que el
        cliente no haya dado al escribir.
        """
        ...


class PortAgenda(Protocol):
    """ACL sobre `scheduling`. Cinco operaciones y ninguna más.

    **Es la única puerta por la que el agente puede tocar la agenda**, y del otro lado están
    los casos de uso deterministas con su restricción de exclusión (decisión D28 del épico 7).
    Esa asimetría —el modelo propone, el motor dispone— es HU-E8-01 RN-03.
    """

    async def servicios_ofrecibles(self) -> list[ServicioOfrecible]:
        """Los servicios que se pueden reservar hoy: agendables y con un recurso activo."""
        ...

    async def horarios_libres(self, *, servicio_id: UUID, dia: date) -> list[HorarioOfrecible]:
        """**Todos** los inicios libres de ese día para ese servicio, en todos los recursos.

        No elige ni corta: elegir qué se ofrece es del dominio (`elegir_horarios`).
        """
        ...

    async def reservar(self, *, cliente_id: UUID, horario: HorarioOfrecible) -> UUID:
        """Reserva de verdad, o levanta si la franja se tomó. **El motor determinista.**

        Levanta `HorarioNoDisponible` (se ocupó, está fuera de horario, el recurso ya no sirve)
        o `HorarioEnElPasado`. Un rechazo revierte sólo este intento: lo que el agente hizo antes
        y lo que escriba después sigue en pie (T9).
        """
        ...

    async def turnos_de(self, cliente_id: UUID) -> list[TurnoDelCliente]:
        """Los turnos futuros y abiertos del cliente."""
        ...

    async def cancelar(self, turno_id: UUID) -> None:
        """Cancela. Levanta `TurnoNoCancelable` si ya no se puede (otro lo canceló antes)."""
        ...


class PortHorarioDeAtencion(Protocol):
    """ACL sobre `business_config`: lo único que este contexto sabe del horario de atención.

    Responde **una pregunta ya resuelta** —¿está abierto?, ¿con qué política?, ¿cuándo abre?—
    y no entrega ninguna regla ni franja: el cálculo es de `business_config`, escrito una vez,
    y el modelo no participa. Sin horario configurado responde «abierto».
    """

    async def consultar(self, ahora: datetime) -> AtencionDelNegocio: ...


__all__ = [
    "AtencionDelNegocio",
    "HorarioOfrecible",
    "Lectura",
    "MensajeEntrante",
    "PortAgenda",
    "PortDirectorio",
    "PortEmbeddings",
    "PortHorarioDeAtencion",
    "PortInterprete",
    "PortMensajeria",
    "PortRepositorioConversacion",
    "PortRepositorioEscalamiento",
    "PortRepositorioFAQ",
    "PortRepositorioMensaje",
    "PortTranscriptor",
    "PortUsosDeFAQ",
    "ServicioOfrecible",
    "Transcripcion",
    "TurnoDelCliente",
]
