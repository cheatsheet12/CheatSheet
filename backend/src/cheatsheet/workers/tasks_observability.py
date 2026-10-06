"""Retiring tasks that ran out of attempts (HS-T6), on a schedule.

Two tasks, and the split is the same one `tasks_integrations.py` already makes, for the
same reason: a cross-company sweep must not become a cross-company transaction.

- **`observability.barrer_dlq`** — the Beat entry. Asks which companies have something in
  `FALLIDA`, through a `SECURITY DEFINER` function that returns nothing but ids, and fans
  out one message per company. It touches no aggregate and opens no company session.
- **`observability.barrer_empresa`** — one company, one ordinary session, Row-Level
  Security applying exactly as it does for a request.

**Why a schedule and not the failing worker itself.** Deriving to the DLQ at the moment of
the last failure is one line shorter and wrong twice: the worker that just failed may be
the one whose process is dying, so the derivation would be the least likely work to
happen; and the retry ceiling belongs to the `PoliticaDeReintentos` of whoever runs the
task, which the failing worker does not necessarily know. Beat is slower and always runs.

**The sweep does not retry.** `autoretry_for` is absent on purpose, unlike the integration
sweeps: this task's whole job is to deal with things that failed, and a sweep that retries
itself into its own backlog is a shape worth not having. If a run fails, the next one in
`DLQ_BARRIDO_MINUTOS` picks up exactly the same rows — the query is by state, not by
cursor.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from celery import Celery
from kombu.exceptions import KombuError

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.observability.application.tareas import DerivarTareasAgotadasADLQ
from cheatsheet.contexts.observability.infrastructure.tareas_repository import (
    RepositorioTareaAsincrona,
    empresas_con_tareas_fallidas,
)
from cheatsheet.platform.database import sesion_sin_empresa
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.workers.celery_app import Cola, crear_celery
from cheatsheet.workers.ejecucion import ejecutar_tarea

logger = obtener_logger(__name__)

NOMBRE_BARRIDO = "observability.barrer_dlq"
NOMBRE_EMPRESA = "observability.barrer_empresa"


async def barrer_dlq(recursos: Recursos) -> int:
    """Fan out one message per company with failed tasks. Returns how many.

    Deliberately **not** idempotent, for the reason the integrations sweep gives: it reads
    and enqueues, enqueuing the same company twice is already harmless because the
    derivation itself is idempotent through the aggregate's state machine, and a key here
    would instead risk skipping a whole sweep after a redelivery.
    """
    async with sesion_sin_empresa(recursos.sesiones) as sesion:
        empresas = await empresas_con_tareas_fallidas(sesion)

    for empresa_id in empresas:
        _encolar_empresa(recursos.settings, empresa_id)
    logger.info("barrido_dlq_despachado", empresas=len(empresas))
    return len(empresas)


async def barrer_empresa(recursos: Recursos, empresa_id: EmpresaId) -> int:
    """Retire one company's exhausted tasks. Returns how many were derived.

    No idempotency key, and this is the one sweep that does not need one: `FALLIDA → DLQ`
    is a legal transition and `DLQ → DLQ` is not, so a redelivered message finds the rows
    already retired and moves nothing. The guarantee lives in the aggregate rather than in
    a claim in Redis, which is strictly better — it survives a Redis flush.
    """
    derivadas = 0
    async for unidad in unidad_de_trabajo(recursos, empresa_id):
        resultado = await DerivarTareasAgotadasADLQ(
            tareas=RepositorioTareaAsincrona(unidad.sesion),
            publicador=unidad.publicador,
            max_intentos=recursos.settings.dlq_max_intentos,
        ).ejecutar(ahora=unidad.reloj.ahora())
        derivadas = resultado.derivadas
        if resultado.quedan_reintentos:
            logger.info(
                "barrido_dlq_dejo_tareas_con_reintentos",
                empresa_id=str(empresa_id),
                pendientes=resultado.quedan_reintentos,
            )

    logger.info("barrido_dlq_empresa", empresa_id=str(empresa_id), derivadas=derivadas)
    return derivadas


def _encolar_empresa(settings: Settings, empresa_id: EmpresaId) -> None:
    """Enqueue one company's sweep. A broker hiccup must not abort the fan-out.

    Losing one company's message costs a delay of one `DLQ_BARRIDO_MINUTOS`; letting the
    exception escape would cost every company that came after it in the loop.
    """
    try:
        crear_celery(settings).send_task(
            NOMBRE_EMPRESA,
            kwargs={"empresa_id": str(empresa_id)},
            queue=Cola.NOTIFICATIONS.value,
        )
    except KombuError:
        logger.exception("no_se_pudo_encolar_barrido_dlq", empresa_id=str(empresa_id))


def barrer_dlq_sync(settings: Settings) -> Any:
    """Celery's bridge into the async world. One loop and one set of resources per run."""
    return ejecutar_tarea(settings, barrer_dlq)


def barrer_empresa_sync(settings: Settings, *, empresa_id: str) -> Any:
    identificador = EmpresaId(UUID(empresa_id))
    return ejecutar_tarea(settings, lambda recursos: barrer_empresa(recursos, identificador))


def registrar(app: Celery, settings: Settings) -> None:
    """Attach both tasks to a Celery application."""

    @app.task(name=NOMBRE_BARRIDO, queue=Cola.NOTIFICATIONS.value)  # type: ignore[misc]
    def _barrido() -> Any:
        return barrer_dlq_sync(settings)

    @app.task(name=NOMBRE_EMPRESA, queue=Cola.NOTIFICATIONS.value)  # type: ignore[misc]
    def _empresa(**kwargs: str) -> Any:
        return barrer_empresa_sync(settings, **kwargs)
