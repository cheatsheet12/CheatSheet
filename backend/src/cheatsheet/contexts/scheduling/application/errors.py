"""Errores de `scheduling`.

Como en `payments`, casi todos derivan de `EntradaInvalida` porque `api/main.py` mapea ése a
**422 reenviando el texto**, y los textos de este épico los escriben las historias palabra por
palabra — «El horario seleccionado no está disponible.» tiene que llegar a la pantalla.

`FranjaOcupada` es la más importante del archivo y la única que puede nacer **de la base de
datos**: la restricción de exclusión de la migración 0020 es la que garantiza que no haya
doble booking (decisión **D28**), y el repositorio traduce su violación a esta excepción. Que
sea una sola clase para las dos fuentes —la comprobación previa y el rechazo del motor— es a
propósito: quien la atrapa no tiene por qué saber cuál de las dos ganó la carrera.
"""

from __future__ import annotations

from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


class TurnoInexistente(EntradaInvalida):
    """No es de esta empresa, o nunca existió. Bajo RLS son la misma respuesta, a propósito."""


class RecursoInexistente(EntradaInvalida):
    """Ídem, para un recurso reservable."""


class FranjaOcupada(EntradaInvalida):
    """HU-E7-02 RN-01 y HU-E7-06 RN-01: el horario ya está tomado.

    Puede venir de dos lados y significa lo mismo en los dos: de la comprobación que hace el
    caso de uso antes de intentar, o del `ExclusionViolation` que devuelve PostgreSQL cuando
    dos requests concurrentes pasaron esa comprobación a la vez. **El segundo es el que
    cuenta**; el primero existe para dar un mensaje sin gastar una transacción.
    """


class FueraDeHorario(EntradaInvalida):
    """El recurso no atiende en esa franja (HU-E7-04 RN-01).

    Distinto de `FranjaOcupada`: acá no hay nadie ocupando el horario, directamente el local
    está cerrado. Colapsarlas haría que alguien buscara el turno que le está pisando el suyo.
    """


class ServicioNoAdmitido(EntradaInvalida):
    """HU-E7-04 RN-02 y HU-E7-06 RN-03: ese servicio no se presta en ese recurso."""


class RecursoInactivo(EntradaInvalida):
    """HU-E7-04 RN-03: un recurso desactivado no acepta reservas nuevas.

    Los turnos ya reservados sobre él siguen existiendo — es justamente lo que la regla dice.
    """


class TurnoEnElPasado(EntradaInvalida):
    """D95: crear o reprogramar un turno a un instante que ya transcurrió (HU-E7-06 RN-06).

    Es un rechazo de entrada y no de estado: el turno no existe todavía, o sigue donde estaba.
    Los textos los escriben las historias y llegan a la pantalla tal cual.
    """


class TurnoNoModificable(InvarianteViolada):
    """El turno no está Reservado ni Confirmado, que es lo que HU-E7-02 exige para actuar."""


class ExcepcionDuplicada(EntradaInvalida):
    """HU-E7-05 RN-02. Ya hay una excepción para esa fecha en ese recurso."""


__all__ = [
    "ExcepcionDuplicada",
    "FranjaOcupada",
    "FueraDeHorario",
    "RecursoInactivo",
    "RecursoInexistente",
    "ServicioNoAdmitido",
    "TurnoEnElPasado",
    "TurnoInexistente",
    "TurnoNoModificable",
]
