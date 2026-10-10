"""El doble de la agenda de `conversational` y sus datos de prueba.

**`AgendaEnMemoria` es el doble más importante del archivo**, y lo es por lo que *no* tiene:
ningún método que el intérprete pueda alcanzar. El agente sólo puede llamarlo a través del
puerto, y el puerto tiene cinco operaciones — que es exactamente la decisión D38 hecha
superficie. Un doble con un `ejecutar(sql)` haría que los tests pasaran mientras la garantía
real no existe. Sus rechazos son **programables**: es cómo se prueba que el motor se adelantó
(CA4), que el horario ya pasó (CA7) o que el turno ya no se puede cancelar.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from cheatsheet.contexts.conversational.application.errors import (
    HorarioNoDisponible,
    TurnoNoCancelable,
)
from cheatsheet.contexts.conversational.application.ports import (
    ServicioOfrecible,
    TurnoDelCliente,
)
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import HorarioOfrecible
from cheatsheet.shared.zona_horaria import ZONA_ARGENTINA

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
    "grilla_de",
    "un_horario",
]
