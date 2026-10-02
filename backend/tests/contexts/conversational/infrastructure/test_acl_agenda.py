"""`AgendaViaScheduling` con un reloj fijo (HU-E8-01 RN-06, decisión D95).

Dos cosas se fijan acá:

1. **El agente sólo ofrece horarios futuros.** `horarios_ofrecibles` descarta los que ya
   pasaron, con el reloj inyectado y no con el de la pared: sin eso el test dependería de qué
   hora es cuando corre.
2. **`reservar` usa el reloj inyectado.** Antes llamaba a `datetime.now()` real, y el
   re-chequeo «al confirmar» de la historia no se podía probar. Ahora el motor determinista
   rechaza un horario que se venció entre que se ofreció y que el cliente lo eligió.
"""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4

import pytest
from cheatsheet.contexts.conversational.application.ports import HorarioOfrecible
from cheatsheet.contexts.conversational.infrastructure.acl import AgendaViaScheduling
from cheatsheet.contexts.scheduling.application.errors import TurnoEnElPasado
from cheatsheet.contexts.scheduling.application.ports import ServicioAgendable
from cheatsheet.contexts.scheduling.application.turnos import Avisador
from cheatsheet.contexts.scheduling.domain.recurso import (
    ZONA_DE_LA_AGENDA,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.empresa import EmpresaId

from tests.contexts.scheduling.application.dobles import (
    CatalogoEnMemoria,
    DirectorioEnMemoria,
    NotificadorEnMemoria,
    PublicadorEnMemoria,
    RepositorioRecursoEnMemoria,
    RepositorioTurnoEnMemoria,
)

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
#: Martes 8 de septiembre de 2026.
MARTES = date(2026, 9, 8)
CORTE = ServicioAgendable(id=uuid4(), nombre="Corte", duracion_estandar_min=30)


def local(hora: int, minuto: int = 0) -> datetime:
    return datetime.combine(MARTES, time(hora, minuto), tzinfo=ZONA_DE_LA_AGENDA)


class Escena:
    """La agenda del agente cableada con dobles y un reloj detenido a las 12 del martes."""

    def __init__(self) -> None:
        self.recurso = RecursoReservable(
            id=uuid4(),
            empresa_id=EMPRESA,
            nombre="Consultorio 1",
            tipo=TipoRecurso.ESPACIO,
            patrones=(
                PatronDeDisponibilidad(
                    dia_semana=1, hora_inicio=time(9), hora_fin=time(18), duracion_slot_min=60
                ),
            ),
            servicios=frozenset({CORTE.id}),
            created_at=local(8),
        )
        self.turnos = RepositorioTurnoEnMemoria()
        catalogo = CatalogoEnMemoria(CORTE)
        self.agenda = AgendaViaScheduling(
            turnos=self.turnos,
            recursos=RepositorioRecursoEnMemoria(self.recurso),
            servicios=catalogo,
            avisador=Avisador(
                clientes=DirectorioEnMemoria(),
                servicios=catalogo,
                notificador=NotificadorEnMemoria(),
            ),
            publicador=PublicadorEnMemoria(),
            reloj=RelojFijo(local(12)),
            empresa_id=EMPRESA,
            usuario_id=None,
        )

    def horario(self, inicio: datetime) -> HorarioOfrecible:
        return HorarioOfrecible(recurso_id=self.recurso.id, servicio_id=CORTE.id, inicio=inicio)


async def test_horarios_ofrecibles_no_incluye_los_que_ya_pasaron() -> None:
    escena = Escena()

    ofrecidos = await escena.agenda.horarios_ofrecibles(dia=MARTES, limite=20)

    # De 9 a 18 hay nueve horarios; a las 12 quedan el de las 12 (igual a ahora) y los
    # seis siguientes hasta las 17.
    assert [uno.inicio for uno in ofrecidos] == [local(hora) for hora in range(12, 18)]


async def test_reservar_un_horario_vencido_lo_rechaza_el_motor() -> None:
    escena = Escena()

    with pytest.raises(TurnoEnElPasado):
        await escena.agenda.reservar(cliente_id=uuid4(), horario=escena.horario(local(10)))

    assert escena.turnos.turnos == {}


async def test_reservar_usa_el_reloj_inyectado() -> None:
    escena = Escena()

    turno_id = await escena.agenda.reservar(cliente_id=uuid4(), horario=escena.horario(local(15)))

    turno = escena.turnos.turnos[turno_id]
    assert turno.estado is EstadoTurno.RESERVADO
    assert turno.canal_reserva == "AGENTE"
    assert turno.created_at == local(12)
