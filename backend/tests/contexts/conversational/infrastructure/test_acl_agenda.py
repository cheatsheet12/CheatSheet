"""`AgendaViaScheduling` con un reloj fijo (HU-E8-01 RN-06, decisión D95).

Se fijan acá:

1. **El agente sólo ofrece horarios futuros.** `horarios_libres` descarta los que ya pasaron,
   con el reloj inyectado y no con el de la pared: sin eso el test dependería de qué hora es
   cuando corre.
2. **`reservar` usa el reloj inyectado.** El motor determinista rechaza un horario que se venció
   entre que se ofreció y que el cliente lo eligió (CA7).
3. **Los rechazos del motor se traducen al vocabulario del agente** y cada acción corre dentro
   del savepoint que le pasa el composition root (T9).
4. **Los servicios y los turnos del cliente** (T7, HU-E8-02): sólo lo agendable con un recurso
   activo, y sólo lo abierto y futuro del cliente, con la marca de seña.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, time
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from cheatsheet.contexts.conversational.application.errors import (
    HorarioEnElPasado,
    HorarioNoDisponible,
    TurnoNoCancelable,
)
from cheatsheet.contexts.conversational.domain.seleccion_de_horarios import HorarioOfrecible
from cheatsheet.contexts.conversational.infrastructure.acl import AgendaViaScheduling
from cheatsheet.contexts.scheduling.application.ports import ServicioAgendable
from cheatsheet.contexts.scheduling.application.turnos import Avisador
from cheatsheet.contexts.scheduling.domain.recurso import (
    ZONA_DE_LA_AGENDA,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno, Franja, Turno
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

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.asyncio

EMPRESA = EmpresaId(uuid4())
#: Martes 8 de septiembre de 2026.
MARTES = date(2026, 9, 8)
CORTE = ServicioAgendable(id=uuid4(), nombre="Corte", duracion_estandar_min=30)


def local(hora: int, minuto: int = 0, dia: date = MARTES) -> datetime:
    return datetime.combine(dia, time(hora, minuto), tzinfo=ZONA_DE_LA_AGENDA)


def un_recurso(
    servicios: frozenset[UUID], *, slot: int = 60, intervalo: int = 0, activo: bool = True
) -> RecursoReservable:
    return RecursoReservable(
        id=uuid4(),
        empresa_id=EMPRESA,
        nombre="Consultorio",
        tipo=TipoRecurso.ESPACIO,
        patrones=(
            PatronDeDisponibilidad(
                dia_semana=1, hora_inicio=time(9), hora_fin=time(18), duracion_slot_min=slot
            ),
        ),
        servicios=servicios,
        created_at=local(8),
        intervalo_entre_turnos_min=intervalo,
        activo=activo,
    )


class Savepoints:
    """Cuenta cuántos savepoints se abrieron, y cuántos terminaron por una excepción."""

    def __init__(self) -> None:
        self.abiertos = 0
        self.revertidos = 0

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[None]:
        self.abiertos += 1
        try:
            yield
        except Exception:
            self.revertidos += 1
            raise


class Escena:
    """La agenda del agente cableada con dobles y un reloj detenido a las 12 del martes."""

    def __init__(
        self,
        servicio: ServicioAgendable = CORTE,
        *,
        slot: int = 60,
        intervalo: int = 0,
        otros_servicios: tuple[ServicioAgendable, ...] = (),
    ) -> None:
        self.servicio = servicio
        self.recurso = un_recurso(frozenset({servicio.id}), slot=slot, intervalo=intervalo)
        self.turnos = RepositorioTurnoEnMemoria()
        self.recursos = RepositorioRecursoEnMemoria(self.recurso)
        self.catalogo = CatalogoEnMemoria(servicio, *otros_servicios)
        self.savepoints = Savepoints()
        self.agenda = AgendaViaScheduling(
            turnos=self.turnos,
            recursos=self.recursos,
            servicios=self.catalogo,
            avisador=Avisador(
                clientes=DirectorioEnMemoria(),
                servicios=self.catalogo,
                notificador=NotificadorEnMemoria(),
            ),
            publicador=PublicadorEnMemoria(),
            reloj=RelojFijo(local(12)),
            empresa_id=EMPRESA,
            usuario_id=None,
            aislar=self.savepoints,
        )

    def horario(self, inicio: datetime) -> HorarioOfrecible:
        return HorarioOfrecible(recurso_id=self.recurso.id, servicio_id=CORTE.id, inicio=inicio)

    def turno(
        self, cliente_id: UUID, inicio: datetime, *, estado: EstadoTurno = EstadoTurno.RESERVADO
    ) -> Turno:
        uno = Turno(
            id=uuid4(),
            empresa_id=EMPRESA,
            cliente_id=cliente_id,
            servicio_id=CORTE.id,
            recurso_id=self.recurso.id,
            franja=Franja(inicio=inicio, duracion_min=30),
            estado=estado,
        )
        self.turnos.turnos[uno.id] = uno
        return uno


class TestHorariosLibres:
    async def test_no_incluye_los_que_ya_pasaron(self) -> None:
        escena = Escena()

        libres = await escena.agenda.horarios_libres(servicio_id=CORTE.id, dia=MARTES)

        # De 9 a 18 hay nueve horarios; a las 12 quedan el de las 12 (igual a ahora) y los
        # seis siguientes hasta las 17.
        assert [uno.inicio for uno in libres] == [local(hora) for hora in range(12, 18)]

    async def test_devuelve_todos_sin_cortar_en_un_limite(self) -> None:
        """Antes se cortaba en los tres primeros: por eso sólo se ofrecían mañanas."""
        escena = Escena(slot=30)

        libres = await escena.agenda.horarios_libres(servicio_id=CORTE.id, dia=MARTES)

        assert len(libres) == 12  # de las 12:00 a las 17:30

    async def test_respeta_la_duracion_del_servicio(self) -> None:
        """Slot de 60 y servicio de 90: 17:00 no se ofrece, el turno terminaría 18:30."""
        largo = ServicioAgendable(id=uuid4(), nombre="Color", duracion_estandar_min=90)
        escena = Escena(largo)

        libres = await escena.agenda.horarios_libres(servicio_id=largo.id, dia=MARTES)

        assert [uno.inicio for uno in libres] == [local(hora) for hora in range(12, 17)]
        assert {uno.servicio_id for uno in libres} == {largo.id}

    async def test_respeta_el_intervalo_entre_turnos(self) -> None:
        """Intervalo 10 y un turno de 13:00 a 13:30: ni 12:30 ni 13:30 se ofrecen."""
        escena = Escena(slot=30, intervalo=10)
        existente = escena.turno(uuid4(), local(13))
        existente.intervalo_posterior_min = 10

        libres = await escena.agenda.horarios_libres(servicio_id=CORTE.id, dia=MARTES)

        # 12:00 termina 12:30 y su margen 12:40 no toca las 13:00. 12:30 llegaría a 13:10 y pisa
        # el inicio del turno; 13:30 cae dentro del margen del turno. 14:00 ya es libre.
        assert [uno.inicio for uno in libres][:4] == [
            local(12),
            local(14),
            local(14, 30),
            local(15),
        ]

    async def test_junta_los_recursos_que_prestan_el_servicio(self) -> None:
        escena = Escena()
        otro = un_recurso(frozenset({CORTE.id}))
        ajeno = un_recurso(frozenset({uuid4()}))
        for recurso in (otro, ajeno):
            await escena.recursos.agregar(recurso)

        libres = await escena.agenda.horarios_libres(servicio_id=CORTE.id, dia=MARTES)

        assert {uno.recurso_id for uno in libres} == {escena.recurso.id, otro.id}

    async def test_un_recurso_inactivo_no_ofrece_nada(self) -> None:
        escena = Escena()
        escena.recurso.desactivar()

        assert await escena.agenda.horarios_libres(servicio_id=CORTE.id, dia=MARTES) == []


class TestServiciosOfrecibles:
    async def test_solo_los_agendables_con_un_recurso_activo(self) -> None:
        sin_recurso = ServicioAgendable(id=uuid4(), nombre="Color", duracion_estandar_min=60)
        escena = Escena(otros_servicios=(sin_recurso,))

        ofrecibles = await escena.agenda.servicios_ofrecibles()

        assert [uno.nombre for uno in ofrecibles] == ["Corte"]

    async def test_un_recurso_inactivo_no_cuenta(self) -> None:
        escena = Escena()
        escena.recurso.desactivar()

        assert await escena.agenda.servicios_ofrecibles() == []

    async def test_vienen_ordenados_por_nombre(self) -> None:
        barba = ServicioAgendable(id=uuid4(), nombre="Barba", duracion_estandar_min=30)
        escena = Escena(otros_servicios=(barba,))
        await escena.recursos.agregar(un_recurso(frozenset({barba.id})))

        ofrecibles = await escena.agenda.servicios_ofrecibles()

        assert [uno.nombre for uno in ofrecibles] == ["Barba", "Corte"]


class TestReservar:
    async def test_un_horario_vencido_lo_rechaza_el_motor(self) -> None:
        escena = Escena()

        with pytest.raises(HorarioEnElPasado):
            await escena.agenda.reservar(cliente_id=uuid4(), horario=escena.horario(local(10)))

        assert escena.turnos.turnos == {}

    async def test_usa_el_reloj_inyectado(self) -> None:
        escena = Escena()

        turno_id = await escena.agenda.reservar(
            cliente_id=uuid4(), horario=escena.horario(local(15))
        )

        turno = escena.turnos.turnos[turno_id]
        assert turno.estado is EstadoTurno.RESERVADO
        assert turno.canal_reserva == "AGENTE"
        assert turno.created_at == local(12)

    async def test_corre_dentro_de_un_savepoint(self) -> None:
        escena = Escena()

        await escena.agenda.reservar(cliente_id=uuid4(), horario=escena.horario(local(15)))

        assert (escena.savepoints.abiertos, escena.savepoints.revertidos) == (1, 0)

    async def test_un_rechazo_del_motor_se_traduce_y_revierte_solo_ese_intento(self) -> None:
        """T9: `FranjaOcupada` (la exclusión de PostgreSQL) es `HorarioNoDisponible` para el agente."""
        escena = Escena()
        escena.turnos.ocupado = True

        with pytest.raises(HorarioNoDisponible):
            await escena.agenda.reservar(cliente_id=uuid4(), horario=escena.horario(local(15)))

        assert (escena.savepoints.abiertos, escena.savepoints.revertidos) == (1, 1)

    async def test_un_recurso_que_ya_no_presta_el_servicio_tambien_es_no_disponible(self) -> None:
        escena = Escena()
        ajeno = HorarioOfrecible(
            recurso_id=escena.recurso.id, servicio_id=uuid4(), inicio=local(15)
        )

        with pytest.raises(HorarioNoDisponible):
            await escena.agenda.reservar(cliente_id=uuid4(), horario=ajeno)

    async def test_fuera_del_horario_del_recurso_es_no_disponible(self) -> None:
        escena = Escena()

        with pytest.raises(HorarioNoDisponible):
            await escena.agenda.reservar(cliente_id=uuid4(), horario=escena.horario(local(20)))


class TestTurnosDelCliente:
    async def test_solo_los_abiertos_y_futuros_de_ese_cliente(self) -> None:
        escena = Escena()
        cliente, otro = uuid4(), uuid4()
        propio = escena.turno(cliente, local(15))
        escena.turno(cliente, local(10))  # ya pasó
        escena.turno(cliente, local(16), estado=EstadoTurno.CANCELADO)
        escena.turno(otro, local(15))

        turnos = await escena.agenda.turnos_de(cliente)

        assert [uno.id for uno in turnos] == [propio.id]
        assert turnos[0].servicio == "Corte"
        assert turnos[0].inicio == local(15)

    async def test_dice_si_el_turno_tiene_sena(self) -> None:
        escena = Escena()
        cliente = uuid4()
        con = escena.turno(cliente, local(15))
        con.asignar_cobro(uuid4())
        sin = escena.turno(cliente, local(16))

        turnos = {uno.id: uno for uno in await escena.agenda.turnos_de(cliente)}

        assert turnos[con.id].tiene_sena
        assert not turnos[sin.id].tiene_sena


class TestCancelar:
    async def test_cancela_y_deja_el_horario_libre(self) -> None:
        escena = Escena()
        turno = escena.turno(uuid4(), local(15))

        await escena.agenda.cancelar(turno.id)

        assert turno.estado is EstadoTurno.CANCELADO
        libres = await escena.agenda.horarios_libres(servicio_id=CORTE.id, dia=MARTES)
        assert local(15) in [uno.inicio for uno in libres]
        assert escena.savepoints.abiertos == 1

    async def test_un_turno_ya_cancelado_no_es_cancelable(self) -> None:
        escena = Escena()
        turno = escena.turno(uuid4(), local(15), estado=EstadoTurno.CANCELADO)

        with pytest.raises(TurnoNoCancelable):
            await escena.agenda.cancelar(turno.id)

    async def test_un_turno_inexistente_no_es_cancelable(self) -> None:
        with pytest.raises(TurnoNoCancelable):
            await Escena().agenda.cancelar(uuid4())
