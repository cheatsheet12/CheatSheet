"""La grilla de inicios que se ofrece, con la ocupación por solapamiento más intervalo (D96).

Antes «ocupado» era la coincidencia exacta de inicios, y un servicio de 45 minutos sobre un slot
de 30 se ofrecía en horarios en los que no entraba. Acá se fija lo que reemplaza eso:

- los inicios siguen el paso del slot y el turno (no el slot) tiene que entrar en la franja;
- un horario está ocupado si el turno nuevo, **con su intervalo**, pisa a otro turno o a su
  intervalo (HU-E7-04 RN-07);
- el intervalo posterior al último turno de la franja puede exceder `hora_fin`;
- un turno a posteriori (`intervalo None`) sólo bloquea su franja real.
"""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4

from cheatsheet.contexts.scheduling.domain.grilla import HorarioOfrecido, horarios_ofrecidos
from cheatsheet.contexts.scheduling.domain.recurso import (
    ZONA_DE_LA_AGENDA,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import Franja, Turno
from cheatsheet.shared.empresa import EmpresaId

#: Martes 8 de septiembre de 2026.
MARTES = date(2026, 9, 8)
ANTES = datetime(2026, 9, 1, 12, 0, tzinfo=ZONA_DE_LA_AGENDA)


def local(hora: int, minuto: int = 0) -> datetime:
    return datetime.combine(MARTES, time(hora, minuto), tzinfo=ZONA_DE_LA_AGENDA)


def un_recurso(
    *, desde: time = time(9), hasta: time = time(11), slot: int = 30, intervalo: int = 0
) -> RecursoReservable:
    return RecursoReservable(
        id=uuid4(),
        empresa_id=EmpresaId(uuid4()),
        nombre="Consultorio 1",
        tipo=TipoRecurso.ESPACIO,
        patrones=(
            PatronDeDisponibilidad(
                dia_semana=1, hora_inicio=desde, hora_fin=hasta, duracion_slot_min=slot
            ),
        ),
        intervalo_entre_turnos_min=intervalo,
    )


def un_turno(
    recurso: RecursoReservable,
    inicio: datetime,
    duracion: int,
    intervalo: int | None,
) -> Turno:
    return Turno(
        id=uuid4(),
        empresa_id=recurso.empresa_id,
        cliente_id=uuid4(),
        servicio_id=uuid4(),
        recurso_id=recurso.id,
        franja=Franja(inicio=inicio, duracion_min=duracion),
        intervalo_posterior_min=intervalo,
    )


def libres(grilla: tuple[HorarioOfrecido, ...]) -> list[datetime]:
    return [uno.inicio for uno in grilla if not uno.ocupado]


def ocupados(grilla: tuple[HorarioOfrecido, ...]) -> list[datetime]:
    return [uno.inicio for uno in grilla if uno.ocupado]


def test_sin_turnos_ofrece_los_inicios_donde_el_servicio_entra() -> None:
    # Slot 30, servicio 45, 09:00-11:00: 10:30 no entra.
    grilla = horarios_ofrecidos(un_recurso(), MARTES, 45, [], ANTES)

    assert [uno.inicio for uno in grilla] == [local(9), local(9, 30), local(10)]
    assert not any(uno.ocupado for uno in grilla)


def test_con_intervalo_el_horario_pegado_al_turno_esta_ocupado_y_el_del_margen_libre() -> None:
    """HU-E7-04: intervalo 10 y un turno de 09:00 a 09:30 → el siguiente puede ser a las 09:40."""
    recurso = un_recurso(slot=10, intervalo=10)
    existente = un_turno(recurso, local(9), 30, 10)

    grilla = horarios_ofrecidos(recurso, MARTES, 30, [existente], ANTES)

    assert local(9, 30) in ocupados(grilla)
    assert local(9, 39) not in [uno.inicio for uno in grilla]  # el paso es 10: 09:39 no existe
    assert local(9, 40) in libres(grilla)


def test_sin_intervalo_los_turnos_pueden_ser_contiguos() -> None:
    recurso = un_recurso(intervalo=0)
    existente = un_turno(recurso, local(9), 30, 0)

    grilla = horarios_ofrecidos(recurso, MARTES, 30, [existente], ANTES)

    assert local(9, 30) in libres(grilla)
    assert local(9) in ocupados(grilla)


def test_el_turno_nuevo_mas_su_intervalo_no_pisa_al_siguiente() -> None:
    recurso = un_recurso(slot=30, intervalo=10)
    siguiente = un_turno(recurso, local(10), 30, 10)

    grilla = horarios_ofrecidos(recurso, MARTES, 30, [siguiente], ANTES)

    # 09:30 terminaría 10:00 y su margen llegaría a las 10:10: pisa el inicio del siguiente.
    assert local(9, 30) in ocupados(grilla)
    assert local(9) in libres(grilla)


def test_el_intervalo_del_ultimo_turno_puede_pasarse_de_hora_fin() -> None:
    recurso = un_recurso(desde=time(9), hasta=time(10), slot=30, intervalo=10)

    grilla = horarios_ofrecidos(recurso, MARTES, 30, [], ANTES)

    # El turno de 09:30 termina a las 10:00, justo en hora_fin; su margen llega a 10:10.
    assert [uno.inicio for uno in grilla] == [local(9), local(9, 30)]


def test_un_turno_a_posteriori_solo_bloquea_su_franja_real() -> None:
    recurso = un_recurso(slot=10, intervalo=10)
    a_posteriori = un_turno(recurso, local(9), 30, None)

    grilla = horarios_ofrecidos(recurso, MARTES, 30, [a_posteriori], ANTES)

    assert local(9, 20) in ocupados(grilla)
    assert local(9, 30) in libres(grilla)


def test_descarta_los_horarios_que_ya_pasaron() -> None:
    """D95: un inicio igual a `ahora` todavía se ofrece."""
    grilla = horarios_ofrecidos(un_recurso(), MARTES, 30, [], local(9, 30))

    assert [uno.inicio for uno in grilla] == [local(9, 30), local(10), local(10, 30)]
