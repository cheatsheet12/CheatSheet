"""`TareaAsincrona` — the aggregate behind HS-T6.

**Why this exists at all.** `workers/base.py` already computes the retry ceiling:
`PoliticaDeReintentos.agoto_los_intentos()` has been there since epic 1 and **nobody
calls it**. A task that fails every time therefore retries forever, which is the exact
shape of HS-T6 RN-03's failure — one poisoned row starving a queue everybody else is
waiting on. The policy knows *when* to stop; this aggregate is *what happens then*.

**It is not `RegistroDeAuditoria`, and the difference is the point.** The audit log is
immutable business history: it happened, and that is all it will ever do. This is
execution state, and it mutates on every attempt. Storing them together would break the
immutability that HS-T5 enforces at three levels. The relationship runs the other way:
exhausting the retries **publishes** an auditable event (RN-04), which is one line of
the log and does not replace this row.

**The DLQ is a state, not a sixth queue.** ADR-003 fixed five queues at one worker
deployment each; a sixth would cost a process forever. RN-03 only asks that a dead task
stop blocking the others, and a terminal state already gives that — the task stops being
re-enqueued and the worker moves on. A table also beats a queue for RN-04, which wants
the failures analysed and eventually replayed: a row answers SQL, a message in a queue
does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia

#: Truncation limit for `resultado`. A traceback is not a business fact, and the column
#: is read by a human deciding whether to replay — not by a debugger.
MAX_LONGITUD_RESULTADO = 2000


class EstadoTarea(StrEnum):
    """The five states of the DER's `estado_tarea`, and no others."""

    PENDIENTE = "PENDIENTE"
    EN_CURSO = "EN_CURSO"
    COMPLETADA = "COMPLETADA"
    FALLIDA = "FALLIDA"
    DLQ = "DLQ"


#: The whole state machine, written once so that both the aggregate and its tests read
#: the same table. Anything not in here is illegal by construction rather than by an
#: `if` somebody can forget to write.
TRANSICIONES_LEGALES: dict[EstadoTarea, frozenset[EstadoTarea]] = {
    EstadoTarea.PENDIENTE: frozenset({EstadoTarea.EN_CURSO}),
    # A failure returns to PENDIENTE only through a new attempt, which is what
    # `marcar_en_curso` does; FALLIDA is where a task waits between attempts.
    EstadoTarea.EN_CURSO: frozenset({EstadoTarea.COMPLETADA, EstadoTarea.FALLIDA}),
    EstadoTarea.FALLIDA: frozenset({EstadoTarea.EN_CURSO, EstadoTarea.DLQ}),
    EstadoTarea.COMPLETADA: frozenset(),
    EstadoTarea.DLQ: frozenset(),
}


@dataclass(slots=True, kw_only=True)
class TareaAsincrona:
    """One unit of deferred work, and the record of how it went.

    Mutable on purpose — see the module docstring. Every transition goes through a
    method that validates it; there is no way to set `estado` directly that does not
    read as the mistake it would be.
    """

    id: UUID
    empresa_id: EmpresaId
    #: The task's name, e.g. `spreadsheet_sync.procesar_planilla`. Free text rather than
    #: an enum: the catalogue grows with every epic, and a closed one here would mean a
    #: migration each time a worker learns a new job.
    tipo: str
    #: What the task needs to run. **May carry personal or fiscal data** — a spreadsheet
    #: row holds a CUIT and a phone number. It never leaves the system and it is never
    #: sent to an LLM (CLAUDE.md §3.6); that is also why `resultado` stores the reason a
    #: task failed and not the payload that made it fail.
    payload: dict[str, Any] = field(default_factory=dict)
    clave_idempotencia: ClaveDeIdempotencia
    estado: EstadoTarea = EstadoTarea.PENDIENTE
    intentos: int = 0
    resultado: str | None = None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.tipo.strip():
            raise EntradaInvalida("El tipo de la tarea no puede estar vacio")
        if self.intentos < 0:
            raise EntradaInvalida("Los intentos no pueden ser negativos")
        for momento, nombre in ((self.created_at, "created_at"), (self.updated_at, "updated_at")):
            if momento.tzinfo is None:
                raise EntradaInvalida(f"{nombre} debe tener zona horaria (UTC)")

    @property
    def es_terminal(self) -> bool:
        """True once nothing more will happen to this task."""
        return not TRANSICIONES_LEGALES[self.estado]

    @property
    def fue_derivada(self) -> bool:
        return self.estado is EstadoTarea.DLQ

    def marcar_en_curso(self, *, ahora: datetime) -> None:
        """Claim the task for an attempt. Counts the attempt, RN-01 counts them here.

        The increment lives with the transition and not with the failure: a worker that
        dies mid-task never reports anything, and if the attempt were counted on failure
        that crash would be free. Counting on start makes a crash cost an attempt, which
        is the conservative direction — the task reaches the DLQ instead of looping.
        """
        self._exigir_transicion(EstadoTarea.EN_CURSO)
        self.estado = EstadoTarea.EN_CURSO
        self.intentos += 1
        self.updated_at = ahora

    def marcar_completada(self, *, ahora: datetime) -> None:
        self._exigir_transicion(EstadoTarea.COMPLETADA)
        self.estado = EstadoTarea.COMPLETADA
        self.resultado = None
        self.updated_at = ahora

    def marcar_fallida(self, *, motivo: str, ahora: datetime) -> None:
        """Record a failed attempt. The task stays retryable until the sweep says otherwise."""
        self._exigir_transicion(EstadoTarea.FALLIDA)
        self.estado = EstadoTarea.FALLIDA
        self.resultado = self._recortar(motivo)
        self.updated_at = ahora

    def derivar_a_dlq(self, *, motivo: str | None = None, ahora: datetime) -> None:
        """RN-02: the retries are gone, so the task stops being work and becomes evidence."""
        self._exigir_transicion(EstadoTarea.DLQ)
        self.estado = EstadoTarea.DLQ
        if motivo is not None:
            self.resultado = self._recortar(motivo)
        self.updated_at = ahora

    def agoto_los_intentos(self, *, max_intentos: int) -> bool:
        """Whether this task has spent its budget.

        The ceiling is a parameter and not an attribute of the task: it belongs to the
        `PoliticaDeReintentos` of whoever runs it (`workers/base.py`), and a task type
        that deserves more attempts should not have to be migrated to get them.
        """
        if max_intentos < 1:
            raise EntradaInvalida("El maximo de intentos arranca en 1")
        return self.intentos >= max_intentos

    def _exigir_transicion(self, destino: EstadoTarea) -> None:
        if destino not in TRANSICIONES_LEGALES[self.estado]:
            raise InvarianteViolada(
                f"Una tarea {self.estado.value} no puede pasar a {destino.value}"
            )

    @staticmethod
    def _recortar(motivo: str) -> str:
        limpio = motivo.strip()
        if not limpio:
            raise EntradaInvalida("El motivo del fallo no puede estar vacio")
        return limpio[:MAX_LONGITUD_RESULTADO]
