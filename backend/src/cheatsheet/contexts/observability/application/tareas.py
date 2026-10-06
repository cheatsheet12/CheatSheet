"""The use cases of HS-T6 — the lifecycle of a `TareaAsincrona` and its DLQ.

Three services, one per moment a task is observed: it starts, it ends, and — for the
ones that ended badly too many times — the sweep that retires them.

**Why the sweep is a separate service and not part of reporting a failure.** Deriving to
the DLQ at the moment of the last failure is tempting and one line shorter. It is also
wrong twice: the worker that just failed may be the one whose process is dying, so the
derivation would be the work least likely to happen; and the retry ceiling belongs to the
`PoliticaDeReintentos` of whoever runs the task, which the failing worker does not
necessarily know. Beat sweeping on a schedule is slower and always happens (RN-02).

**Why the sweep is idempotent for free.** `FALLIDA → DLQ` is a legal transition and
`DLQ → DLQ` is not, so a second run over the same rows moves nothing. That is the
aggregate's state machine doing the work, not a flag in this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.observability.application.ports import PortRepositorioTareaAsincrona
from cheatsheet.contexts.observability.domain.tarea_asincrona import EstadoTarea, TareaAsincrona
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import InvarianteViolada
from cheatsheet.shared.events import PublicadorDeEventos
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia

#: How many failed tasks one sweep retires. See `listar_fallidas` for why it is bounded.
TAMANO_DE_LOTE_POR_DEFECTO = 200

#: The action recorded in the audit log when a task is retired (RN-04). A closed constant
#: rather than a literal at the call site, because epic 10 filters the panel by it.
ACCION_DERIVACION_A_DLQ = "TareaAsincronaDerivadaADLQ"


class RegistrarIntentoDeTarea:
    """Claims a task for one attempt, creating it the first time.

    Creation and claim are the same call because the alternative — an endpoint that
    registers the task and a worker that later claims it — leaves a window where a task
    exists in `PENDIENTE` and no worker ever picks it up, which looks exactly like a
    task that is running.
    """

    def __init__(self, tareas: PortRepositorioTareaAsincrona) -> None:
        self._tareas = tareas

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        tipo: str,
        clave: ClaveDeIdempotencia,
        ahora: datetime,
        payload: dict[str, object] | None = None,
    ) -> TareaAsincrona:
        tarea = await self._tareas.buscar_por_clave(clave)
        if tarea is None:
            tarea = TareaAsincrona(
                id=uuid4(),
                empresa_id=empresa_id,
                tipo=tipo,
                payload=dict(payload or {}),
                clave_idempotencia=clave,
                created_at=ahora,
                updated_at=ahora,
            )
            tarea.marcar_en_curso(ahora=ahora)
            await self._tareas.agregar(tarea)
            return tarea

        # A task that already finished must not be resurrected by a redelivery: that is
        # what the idempotency key is for (ADR-009). Raising here rather than returning
        # quietly keeps a genuine bug -- two different effects colliding on one key --
        # from looking like a normal retry.
        if tarea.es_terminal:
            raise InvarianteViolada(
                f"La tarea {tarea.id} ya esta en estado {tarea.estado.value} y no admite otro intento"
            )

        tarea.marcar_en_curso(ahora=ahora)
        await self._tareas.actualizar(tarea)
        return tarea


class RegistrarResultadoDeTarea:
    """Closes one attempt, well or badly.

    It does **not** decide whether the task is finished for good — that is the sweep's
    call, for the reasons in the module docstring. A task that fails its last attempt
    still lands in `FALLIDA` here and is retired later.
    """

    def __init__(self, tareas: PortRepositorioTareaAsincrona) -> None:
        self._tareas = tareas

    async def completar(self, *, tarea_id: UUID, ahora: datetime) -> TareaAsincrona:
        tarea = await self._exigir(tarea_id)
        tarea.marcar_completada(ahora=ahora)
        await self._tareas.actualizar(tarea)
        return tarea

    async def fallar(self, *, tarea_id: UUID, motivo: str, ahora: datetime) -> TareaAsincrona:
        tarea = await self._exigir(tarea_id)
        tarea.marcar_fallida(motivo=motivo, ahora=ahora)
        await self._tareas.actualizar(tarea)
        return tarea

    async def _exigir(self, tarea_id: UUID) -> TareaAsincrona:
        tarea = await self._tareas.buscar_por_id(tarea_id)
        if tarea is None:
            raise InvarianteViolada(f"La tarea {tarea_id} no existe")
        return tarea


@dataclass(frozen=True, slots=True)
class ResultadoDelBarrido:
    """What one sweep did. Read by tests and by whoever is looking at an incident."""

    revisadas: int
    derivadas: int

    @property
    def quedan_reintentos(self) -> int:
        """Failed tasks the sweep left alone because they still have attempts left."""
        return self.revisadas - self.derivadas


class DerivarTareasAgotadasADLQ:
    """RN-02 — the Beat sweep that retires tasks which ran out of attempts.

    One task failing to be retired does not stop the batch (RN-03). That is the whole
    point of the story: the dead must not block the living, and a sweep that aborts on
    the first surprise is itself a way for one bad row to stop the rest.
    """

    def __init__(
        self,
        *,
        tareas: PortRepositorioTareaAsincrona,
        publicador: PublicadorDeEventos,
        max_intentos: int,
    ) -> None:
        self._tareas = tareas
        self._publicador = publicador
        self._max_intentos = max_intentos

    async def ejecutar(
        self, *, ahora: datetime, limite: int = TAMANO_DE_LOTE_POR_DEFECTO
    ) -> ResultadoDelBarrido:
        candidatas = await self._tareas.listar_fallidas(limite=limite)
        derivadas = 0

        for tarea in candidatas:
            if not tarea.agoto_los_intentos(max_intentos=self._max_intentos):
                continue
            await self._derivar(tarea, ahora=ahora)
            derivadas += 1

        return ResultadoDelBarrido(revisadas=len(candidatas), derivadas=derivadas)

    async def _derivar(self, tarea: TareaAsincrona, *, ahora: datetime) -> None:
        tarea.derivar_a_dlq(ahora=ahora)
        await self._tareas.actualizar(tarea)

        # RN-04: the derivation is the event worth analysing later. `usuario_id` stays
        # None because nobody asked for this -- the scheduler did.
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=tarea.empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.OBSERVABILITY,
                accion=ACCION_DERIVACION_A_DLQ,
                # The task's id, not its payload: the payload may carry a CUIT or a
                # phone number, and the audit log is not where those go to be copied.
                entidad_afectada=f"TareaAsincrona:{tarea.id}",
                resultado=Resultado.ERROR,
            )
        )


__all__ = [
    "ACCION_DERIVACION_A_DLQ",
    "TAMANO_DE_LOTE_POR_DEFECTO",
    "DerivarTareasAgotadasADLQ",
    "EstadoTarea",
    "RegistrarIntentoDeTarea",
    "RegistrarResultadoDeTarea",
    "ResultadoDelBarrido",
]
