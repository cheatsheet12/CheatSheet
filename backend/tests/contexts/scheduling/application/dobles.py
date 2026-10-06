"""Los dobles de `scheduling`, escritos a mano.

Como en el resto del sistema: implementaciones de verdad de los puertos y no `Mock`, porque un
`Mock` satisface cualquier interfaz, incluida una que ya no existe. El día que un puerto cambie
de forma, estos archivos fallan — que es el punto de tener un puerto.

**`RepositorioTurnoEnMemoria` no reproduce la restricción de exclusión**, y eso es deliberado.
Comprobar el solapamiento en Python haría que estos tests pasaran mientras la garantía real
—la de PostgreSQL— podría estar rota. La restricción se prueba contra el motor, en
`tests/integracion/test_agenda_postgres.py`, y se verifica al revés sacándola.

Lo que este doble sí hace es **poder fallar cuando se le pide**, para que los casos de uso
puedan probar qué hacen con un `FranjaOcupada` sin necesitar una base.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from cheatsheet.contexts.scheduling.application.errors import FranjaOcupada
from cheatsheet.contexts.scheduling.application.ports import (
    DatosDeAviso,
    FiltrosDeAgenda,
    ServicioAgendable,
)
from cheatsheet.contexts.scheduling.domain.recurso import ZONA_DE_LA_AGENDA, RecursoReservable
from cheatsheet.contexts.scheduling.domain.turno import (
    ESTADOS_QUE_OCUPAN_LA_FRANJA,
    MENSAJE_HORARIO_OCUPADO,
    Turno,
)


class RepositorioRecursoEnMemoria:
    def __init__(self, *recursos: RecursoReservable) -> None:
        self.recursos: dict[UUID, RecursoReservable] = {uno.id: uno for uno in recursos}

    async def agregar(self, recurso: RecursoReservable) -> None:
        self.recursos[recurso.id] = recurso

    async def guardar(self, recurso: RecursoReservable) -> None:
        self.recursos[recurso.id] = recurso

    async def buscar_por_id(self, recurso_id: UUID) -> RecursoReservable | None:
        return self.recursos.get(recurso_id)

    async def listar(self, solo_activos: bool = False) -> list[RecursoReservable]:
        todos = sorted(self.recursos.values(), key=lambda uno: uno.nombre)
        return [uno for uno in todos if uno.activo or not solo_activos]


class RepositorioTurnoEnMemoria:
    """Turnos en un dict. **No** comprueba solapamiento; ver el docstring del módulo."""

    def __init__(self, *turnos: Turno) -> None:
        self.turnos: dict[UUID, Turno] = {uno.id: uno for uno in turnos}
        #: Cuando está en `True`, el próximo `agregar` o `guardar` levanta `FranjaOcupada`.
        #: Es cómo se simula que el motor rechazó el solapamiento.
        self.ocupado = False

    async def agregar(self, turno: Turno) -> None:
        self._quizas_fallar()
        self.turnos[turno.id] = turno

    async def guardar(self, turno: Turno) -> None:
        self._quizas_fallar()
        self.turnos[turno.id] = turno

    async def buscar_por_id(self, turno_id: UUID) -> Turno | None:
        return self.turnos.get(turno_id)

    async def listar(self, filtros: FiltrosDeAgenda) -> list[Turno]:
        encontrados = [
            uno
            for uno in self.turnos.values()
            if (filtros.recurso_id is None or uno.recurso_id == filtros.recurso_id)
            and (filtros.desde is None or uno.franja.inicio >= filtros.desde)
            and (filtros.hasta is None or uno.franja.inicio < filtros.hasta)
            and (not filtros.estados or uno.estado in filtros.estados)
        ]
        return sorted(encontrados, key=lambda uno: uno.franja.inicio)

    async def ocupados_en(self, recurso_id: UUID, dia: date) -> list[Turno]:
        return [
            uno
            for uno in self.turnos.values()
            if uno.recurso_id == recurso_id
            and uno.franja.inicio.astimezone(ZONA_DE_LA_AGENDA).date() == dia
            and uno.estado in ESTADOS_QUE_OCUPAN_LA_FRANJA
        ]

    def _quizas_fallar(self) -> None:
        if self.ocupado:
            raise FranjaOcupada(MENSAJE_HORARIO_OCUPADO)


class CatalogoEnMemoria:
    def __init__(self, *servicios: ServicioAgendable) -> None:
        self.servicios = {uno.id: uno for uno in servicios}

    async def buscar_agendable(self, servicio_id: UUID) -> ServicioAgendable | None:
        return self.servicios.get(servicio_id)

    async def listar_agendables(self) -> list[ServicioAgendable]:
        return list(self.servicios.values())


class DirectorioEnMemoria:
    """Clientes con o sin teléfono. Sin número devuelve `None`, que es un camino previsto."""

    def __init__(self, contactos: dict[UUID, tuple[str, str]] | None = None) -> None:
        self.contactos = contactos or {}

    async def contacto_de(self, cliente_id: UUID) -> tuple[str, str] | None:
        return self.contactos.get(cliente_id)


class NotificadorEnMemoria:
    def __init__(self) -> None:
        self.avisos: list[tuple[str, DatosDeAviso]] = []

    async def avisar_reserva(self, datos: DatosDeAviso) -> None:
        self.avisos.append(("reserva", datos))

    async def avisar_cancelacion(self, datos: DatosDeAviso) -> None:
        self.avisos.append(("cancelacion", datos))

    async def avisar_reprogramacion(self, datos: DatosDeAviso) -> None:
        self.avisos.append(("reprogramacion", datos))


class PublicadorEnMemoria:
    """Guarda los eventos de auditoría para poder afirmar que la acción quedó registrada."""

    def __init__(self) -> None:
        self.eventos: list[object] = []

    async def publicar(self, evento: object) -> None:
        self.eventos.append(evento)

    @property
    def acciones(self) -> list[str]:
        return [getattr(uno, "accion", "") for uno in self.eventos]


__all__ = [
    "CatalogoEnMemoria",
    "DirectorioEnMemoria",
    "NotificadorEnMemoria",
    "PublicadorEnMemoria",
    "RepositorioRecursoEnMemoria",
    "RepositorioTurnoEnMemoria",
]
