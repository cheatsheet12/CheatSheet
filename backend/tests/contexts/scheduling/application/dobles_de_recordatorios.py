"""Dobles del barrido de recordatorios de turno (U8, tramo 3).

La pregunta central es **en qué orden** ocurren las cosas: la fila se confirma antes de hablar con el
canal y el resultado se confirma después. Todos los dobles escriben en la misma bitácora.

Los repositorios en memoria tienen **semántica de base**: guardan y leen copias, así que un `guardar`
que falla no deshace lo que el dominio ya mutó y el doble no miente justo en lo que se prueba.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cheatsheet.contexts.scheduling.application.envio_de_recordatorios import EnvioDeRecordatorios
from cheatsheet.contexts.scheduling.application.errors import (
    AgendaDeNotificacionInvalida,
    RecordatorioDeTurnoDuplicado,
)
from cheatsheet.contexts.scheduling.application.ports_de_recordatorios import (
    RecordatorioListo,
    ResultadoDelEnvio,
    SinTelefono,
)
from cheatsheet.contexts.scheduling.application.recordatorios import (
    EnviarRecordatoriosDeTurno,
    ResultadoDeBarrido,
)
from cheatsheet.contexts.scheduling.domain.recordatorio_de_turno import RecordatorioDeTurno
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Franja, Turno
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.events import EventoDeDominio
from cheatsheet.shared.transaccion import DespachoNoPersistido

H = 60  # minutos por hora

EMPRESA = EmpresaId(uuid4())
#: 15/10/2026 10:00 en la Argentina (UTC-3) = 13:00Z.
INICIO = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
RESERVADO_EL = INICIO - timedelta(days=10)
#: Un instante dentro de la ventana de 24 h del turno de `INICIO`.
VENTANA_DE_24H = INICIO - timedelta(hours=23)


class RelojDePrueba:
    def __init__(self, instante: datetime = VENTANA_DE_24H) -> None:
        self.instante = instante

    def ahora(self) -> datetime:
        return self.instante


class TransaccionFalsa:
    """`PortTransaccion`: cuenta los commits y sabe si hay algo sin confirmar."""

    def __init__(self) -> None:
        self.bitacora: list[str] = []
        self.confirmaciones = 0
        self.sin_confirmar = False
        self.fallar_la_confirmacion_numero: int | None = None

    def escribio(self, que: str) -> None:
        self.bitacora.append(que)
        self.sin_confirmar = True

    async def confirmar(self) -> None:
        if self.fallar_la_confirmacion_numero == self.confirmaciones + 1:
            self.confirmaciones += 1
            self.sin_confirmar = False
            raise DespachoNoPersistido("la base rechazó la confirmación")
        self.confirmaciones += 1
        self.sin_confirmar = False
        self.bitacora.append("confirmar")


class AislamientoFalso:
    """Un savepoint de mentira: lo que levanta `DespachoNoPersistido` cuenta como deshecho."""

    def __init__(self) -> None:
        self.deshechos = 0

    @asynccontextmanager
    async def aislar(self) -> AsyncIterator[None]:
        try:
            yield
        except DespachoNoPersistido:
            self.deshechos += 1
            raise


class PublicadorFalso:
    def __init__(self) -> None:
        self.eventos: list[EventoDeDominio] = []

    async def publicar(self, evento: EventoDeDominio) -> None:
        self.eventos.append(evento)


class RecordatoriosEnMemoria:
    """`PortRepositorioRecordatoriosDeTurno` con la clave única `(turno, anticipación, franja)`."""

    def __init__(self, transaccion: TransaccionFalsa) -> None:
        self.filas: dict[UUID, RecordatorioDeTurno] = {}
        self.transaccion = transaccion
        self.fallar_al_guardar: Callable[[RecordatorioDeTurno], bool] | None = None

    async def agregar(self, recordatorio: RecordatorioDeTurno) -> None:
        clave = (recordatorio.turno_id, recordatorio.anticipacion_min, recordatorio.franja_inicio)
        if any(
            (uno.turno_id, uno.anticipacion_min, uno.franja_inicio) == clave
            for uno in self.filas.values()
        ):
            raise RecordatorioDeTurnoDuplicado("ya existe")
        self.filas[recordatorio.id] = replace(recordatorio)
        self.transaccion.escribio("agregar")

    async def guardar(self, recordatorio: RecordatorioDeTurno) -> None:
        if self.fallar_al_guardar is not None and self.fallar_al_guardar(recordatorio):
            raise DespachoNoPersistido("la base rechazó el resultado")
        self.filas[recordatorio.id] = replace(recordatorio)
        self.transaccion.escribio("guardar")

    async def buscar_para_actualizar(self, recordatorio_id: UUID) -> RecordatorioDeTurno | None:
        uno = self.filas.get(recordatorio_id)
        return replace(uno) if uno is not None else None

    async def de_turnos(self, turno_ids: list[UUID]) -> list[RecordatorioDeTurno]:
        return [replace(uno) for uno in self.filas.values() if uno.turno_id in turno_ids]

    async def pendientes(self, hasta: datetime) -> list[RecordatorioDeTurno]:
        return [
            replace(uno)
            for uno in self.filas.values()
            if uno.resultado is None
            and uno.proximo_intento_en is not None
            and uno.proximo_intento_en <= hasta
        ]

    @property
    def unica(self) -> RecordatorioDeTurno:
        (fila,) = self.filas.values()
        return fila


class TurnosEnMemoria:
    """`PortTurnosPorRecordar`: relee el turno **de la base**, no el objeto ya cargado."""

    def __init__(self) -> None:
        self.turnos: dict[UUID, Turno] = {}
        self.releidos: list[UUID] = []

    def agregar(self, turno: Turno) -> None:
        self.turnos[turno.id] = turno

    async def abiertos_con_inicio_entre(self, desde: datetime, hasta: datetime) -> list[Turno]:
        return sorted(
            (
                replace(uno)
                for uno in self.turnos.values()
                if uno.esta_abierto and desde < uno.franja.inicio <= hasta
            ),
            key=lambda uno: uno.franja.inicio,
        )

    async def releer(self, turno_id: UUID) -> Turno | None:
        self.releidos.append(turno_id)
        uno = self.turnos.get(turno_id)
        return replace(uno) if uno is not None else None


class AgendaFalsa:
    def __init__(self, *horas: int, falla: Exception | None = None, apagada: bool = False) -> None:
        self.minutos = () if apagada else tuple(h * H for h in (horas or (24,)))
        self.falla = falla

    async def anticipaciones(self) -> tuple[int, ...]:
        if self.falla is not None:
            raise self.falla
        return self.minutos


class EnvioGuionado:
    """Devuelve, intento a intento, lo que se le indicó; anota si había algo sin confirmar."""

    def __init__(
        self,
        transaccion: TransaccionFalsa,
        *resultados: ResultadoDelEnvio | BaseException,
        sin_telefono: bool = False,
        al_enviar: Callable[[], None] | None = None,
    ) -> None:
        self._transaccion = transaccion
        self._resultados = list(resultados)
        self._sin_telefono = sin_telefono
        self._al_enviar = al_enviar
        self.preparados = 0
        self.enviados: list[tuple[UUID, int]] = []
        #: Verdadero si en algún envío había escrituras sin confirmar: lo que este diseño elimina.
        self.con_transaccion_abierta = False

    async def preparar(
        self, turno: Turno, anticipacion_min: int
    ) -> RecordatorioListo | SinTelefono:
        self.preparados += 1
        self._transaccion.bitacora.append("preparar")
        if self._sin_telefono:
            return SinTelefono()
        return RecordatorioListo(
            turno_id=turno.id,
            cliente_id=turno.cliente_id,
            anticipacion_min=anticipacion_min,
            telefono="5491112345678",
            texto="Hola Ana Diaz, te recordamos tu turno",
        )

    async def mandar(self, listo: RecordatorioListo) -> ResultadoDelEnvio:
        self._transaccion.bitacora.append("enviar")
        self.con_transaccion_abierta = (
            self.con_transaccion_abierta or self._transaccion.sin_confirmar
        )
        self.enviados.append((listo.turno_id, listo.anticipacion_min))
        if self._al_enviar is not None:
            self._al_enviar()
        resultado = self._resultados.pop(0) if self._resultados else enviado()
        if isinstance(resultado, BaseException):
            raise resultado
        return resultado


def enviado() -> ResultadoDelEnvio:
    return ResultadoDelEnvio(enviado=True)


def transitoria(codigo: str = "SATURADA") -> ResultadoDelEnvio:
    return ResultadoDelEnvio(enviado=False, falla=codigo, transitoria=True)


def permanente(codigo: str = "131047") -> ResultadoDelEnvio:
    return ResultadoDelEnvio(enviado=False, falla=codigo)


def incierto() -> ResultadoDelEnvio:
    return ResultadoDelEnvio(enviado=False, falla="INCIERTO")


def turno(**cambios: object) -> Turno:
    base: dict[str, object] = {
        "id": uuid4(),
        "empresa_id": EMPRESA,
        "cliente_id": uuid4(),
        "servicio_id": uuid4(),
        "recurso_id": uuid4(),
        "franja": Franja(inicio=INICIO, duracion_min=60),
        "created_at": RESERVADO_EL,
        "franja_asignada_en": RESERVADO_EL,
    }
    base.update(cambios)
    return Turno(**base)  # type: ignore[arg-type]


def cancelado(uno: Turno) -> Turno:
    return replace(uno, estado=EstadoTurno.CANCELADO)


@dataclass
class Escenario:
    barrido: EnviarRecordatoriosDeTurno
    turnos: TurnosEnMemoria
    recordatorios: RecordatoriosEnMemoria
    envio: EnvioGuionado
    transaccion: TransaccionFalsa
    aislamiento: AislamientoFalso
    publicador: PublicadorFalso
    reloj: RelojDePrueba

    @property
    def fila(self) -> RecordatorioDeTurno:
        return self.recordatorios.unica

    async def barrer(self, ahora: datetime | None = None) -> ResultadoDeBarrido:
        if ahora is not None:
            self.reloj.instante = ahora
        return await self.barrido.ejecutar(empresa_id=EMPRESA, ahora=self.reloj.ahora())


def escenario(
    *resultados: ResultadoDelEnvio | BaseException,
    agenda: AgendaFalsa | None = None,
    sin_telefono: bool = False,
    al_enviar: Callable[[], None] | None = None,
    reloj: RelojDePrueba | None = None,
) -> Escenario:
    transaccion = TransaccionFalsa()
    turnos = TurnosEnMemoria()
    recordatorios = RecordatoriosEnMemoria(transaccion)
    envio = EnvioGuionado(transaccion, *resultados, sin_telefono=sin_telefono, al_enviar=al_enviar)
    aislamiento = AislamientoFalso()
    publicador = PublicadorFalso()
    reloj = reloj or RelojDePrueba()
    barrido = EnviarRecordatoriosDeTurno(
        turnos=turnos,
        recordatorios=recordatorios,
        agenda=agenda or AgendaFalsa(),
        envio=EnvioDeRecordatorios(
            turnos=turnos,
            recordatorios=recordatorios,
            envio=envio,
            publicador=publicador,
            aislamiento=aislamiento,
            transaccion=transaccion,
            reloj=reloj,
        ),
    )
    return Escenario(
        barrido, turnos, recordatorios, envio, transaccion, aislamiento, publicador, reloj
    )


def agenda_invalida() -> AgendaDeNotificacionInvalida:
    return AgendaDeNotificacionInvalida("mal formada", regla_id=uuid4())
