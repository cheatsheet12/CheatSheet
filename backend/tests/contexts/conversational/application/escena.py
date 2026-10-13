"""La escena que comparten los tests del agente: todo cableado de una vez.

Una conversación de WhatsApp es una **secuencia de mensajes** y lo que importa de cada uno es el
estado en que deja a la conversación, así que los tests de reserva y de cancelación necesitan los
mismos dobles, el mismo reloj y la misma agenda. Cada test arma una `Escena`, le manda mensajes
con `procesar` y afirma sobre lo que el cliente recibió (`textos`), sobre la agenda (`agenda`) y
sobre el diálogo pendiente (`dialogo`).

Por defecto el cliente es **desconocido** (el agente le da de alta, como en producción) y la
agenda tiene una grilla de 9:00 a 18:00 cada 30 minutos desde mañana, todos los días, para cada
servicio.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from cheatsheet.contexts.conversational.application.agente import ProcesarMensajeEntrante, Respuesta
from cheatsheet.contexts.conversational.application.ports import (
    Lectura,
    MensajeEntrante,
    ServicioOfrecible,
    Transcripcion,
)
from cheatsheet.contexts.conversational.domain.conversacion import Conversacion, Intencion
from cheatsheet.contexts.conversational.domain.dialogo import Dialogo
from cheatsheet.contexts.conversational.domain.escalamiento import Escalamiento
from cheatsheet.contexts.conversational.domain.pedido_de_turno import (
    AccionDeTurno,
    Cuando,
    PedidoDeTurno,
    ReferenciaDeDia,
)
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import HorarioOfrecible
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.conversational.application.dobles import (
    SERVICIO_DE_PRUEBA,
    AgendaEnMemoria,
    DirectorioEnMemoria,
    EmbeddingsEnMemoria,
    InterpreteProgramado,
    MensajeriaEnMemoria,
    PublicadorEnMemoria,
    RepositorioConversacionEnMemoria,
    RepositorioEscalamientoEnMemoria,
    RepositorioFAQEnMemoria,
    RepositorioMensajeEnMemoria,
    UsosDeFAQEnMemoria,
    grilla_de,
)
from tests.contexts.conversational.application.horario_fijo import HorarioFijo, siempre_abierto

EMPRESA = EmpresaId(uuid4())
#: Martes 8 de septiembre de 2026, las 12:00 en Argentina.
AHORA = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
TELEFONO = "5491112345678"
#: El primer día con horarios libres: miércoles 9 de septiembre.
MANANA = date(2026, 9, 9)


class _Transcriptor:
    """Un doble con calidad configurable: los dos caminos de HS-T7 pasan por ese número."""

    def __init__(self, calidad: float) -> None:
        self.calidad = calidad
        self.pedidos: list[str] = []

    async def transcribir(self, audio_id: str) -> Transcripcion:
        self.pedidos.append(audio_id)
        return Transcripcion(texto="quiero un turno", calidad=self.calidad)


class Escena:
    """Todo lo que el caso de uso necesita, cableado de una vez."""

    def __init__(
        self,
        *,
        lectura: Lectura | None = None,
        hilos: tuple[Conversacion, ...] = (),
        escalamientos: tuple[Escalamiento, ...] = (),
        servicios: Sequence[ServicioOfrecible] | None = None,
        libres: Sequence[HorarioOfrecible] | None = None,
        dias: int = 7,
        calidad_del_audio: float = 0.9,
        conocido: bool = False,
        horario: HorarioFijo | None = None,
        primer_dia: date = MANANA,
    ) -> None:
        self.ahora = AHORA
        self.cliente_id = uuid4()
        self.conversaciones = RepositorioConversacionEnMemoria(*hilos)
        self.mensajes = RepositorioMensajeEnMemoria()
        self.escalamientos = RepositorioEscalamientoEnMemoria(*escalamientos)
        self.faqs = RepositorioFAQEnMemoria()
        self.usos = UsosDeFAQEnMemoria()
        self.clientes = DirectorioEnMemoria()
        if conocido:
            self.clientes.conocidos[TELEFONO] = (self.cliente_id, "Ana")
        self.interprete = InterpreteProgramado(lectura)
        self.transcriptor = _Transcriptor(calidad_del_audio)
        self.mensajeria = MensajeriaEnMemoria()
        self.embeddings = EmbeddingsEnMemoria()
        elegidos = list(servicios) if servicios is not None else [SERVICIO_DE_PRUEBA]
        if libres is None:
            libres = [
                libre
                for servicio in elegidos
                for indice in range(dias)
                for libre in grilla_de(primer_dia + timedelta(days=indice), servicio_id=servicio.id)
            ]
        self.agenda = AgendaEnMemoria(*libres, servicios=elegidos)
        self.publicador = PublicadorEnMemoria()
        #: Sin horario configurado, «siempre abierto»: los tests del agente no se enteran.
        self.horario = horario or siempre_abierto()
        self._numero = 0

    @property
    def caso(self) -> ProcesarMensajeEntrante:
        return ProcesarMensajeEntrante(
            conversaciones=self.conversaciones,
            mensajes=self.mensajes,
            escalamientos=self.escalamientos,
            faqs=self.faqs,
            usos=self.usos,
            clientes=self.clientes,
            interprete=self.interprete,
            transcriptor=self.transcriptor,
            mensajeria=self.mensajeria,
            embeddings=self.embeddings,
            agenda=self.agenda,
            horario=self.horario,
            publicador=self.publicador,
        )

    async def procesar(
        self, texto: str, *, externo_id: str | None = None, audio: str | None = None
    ) -> Respuesta:
        self._numero += 1
        return await self.caso.ejecutar(
            empresa_id=EMPRESA,
            entrante=MensajeEntrante(
                externo_id=externo_id or f"wamid-{self._numero}",
                telefono=TELEFONO,
                texto=texto,
                audio_id=audio,
            ),
            ahora=self.ahora,
        )

    @property
    def hilo(self) -> Conversacion:
        return next(iter(self.conversaciones.hilos.values()))

    @property
    def dialogo(self) -> Dialogo | None:
        return self.hilo.dialogo

    def hay_dialogo(self) -> bool:
        """Para las precondiciones: no deja que mypy dé por hecho el estado de después."""
        return self.hilo.dialogo is not None

    @property
    def textos(self) -> list[str]:
        return self.mensajeria.textos

    @property
    def ultimo_texto(self) -> str:
        return self.mensajeria.textos[-1]


def leyendo(
    intencion: Intencion, confianza: float = 0.95, pedido: PedidoDeTurno | None = None
) -> Lectura:
    return Lectura(intencion=intencion, confianza=confianza, pedido_de_turno=pedido)


def pidiendo(
    accion: AccionDeTurno = AccionDeTurno.RESERVAR,
    *cuandos: Cuando,
    **resto: object,
) -> Lectura:
    """Una lectura de `TURNO` con un pedido, como la que devolvería el intérprete."""
    pedido = PedidoDeTurno(accion=accion, cuandos=cuandos, **resto)  # type: ignore[arg-type]
    return leyendo(Intencion.TURNO, pedido=pedido)


def para_manana() -> Cuando:
    return Cuando(ReferenciaDeDia.MANANA)
