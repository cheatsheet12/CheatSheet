"""Celery: five specialised workers and one scheduler (ADR-003).

Five queues rather than one so that a burst of spreadsheet processing cannot delay
the issuance of a tax document, and a slow LLM call cannot starve payment reminders.
Each queue is consumed by its own worker deployment; routing decides which.

Beat is a **singleton and is never replicated** (docs/architecture.md §2). Two Beat
processes mean every scheduled task fires twice — which, on the reminder chain of
HS-T3, means sending every customer two messages.
"""

from __future__ import annotations

from enum import StrEnum

from celery import Celery
from celery.signals import setup_logging

from cheatsheet.platform.settings import Settings

#: Lets `conservar_el_logging_propio` connect its receiver once, however often it is called.
IDENTIFICADOR_DEL_LOGGING = "cheatsheet.workers.logging_propio"


class Cola(StrEnum):
    """The five queues. A task declares its queue; nothing runs on a default one."""

    INTEGRATIONS_SYNC = "integrations_sync"
    SPREADSHEET_PROCESSING = "spreadsheet_processing"
    INCREMENTAL_SYNC = "incremental_sync"
    NOTIFICATIONS = "notifications"
    AI_NLP = "ai_nlp"


def crear_celery(settings: Settings | None = None) -> Celery:
    settings = settings or Settings.desde_entorno()
    app = Celery(
        "cheatsheet", broker=settings.celery_broker_url, backend=settings.celery_result_backend
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # A task that vanished with its worker must come back. Late acknowledgement
        # plus rejection on worker loss is what makes that true; both are off by
        # default, and both are the difference between at-least-once and at-most-once.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        # Prefetching many tasks into one worker defeats the point of five queues.
        worker_prefetch_multiplier=1,
        task_default_queue=Cola.NOTIFICATIONS.value,
        task_track_started=True,
    )
    app.autodiscover_tasks(["cheatsheet.workers"])
    return app


def conservar_el_logging_propio() -> None:
    """Keep the pipeline `configurar_logging` installed when a worker starts.

    A booting worker reconfigures the root logger unless some receiver answers Celery's
    `setup_logging` signal: it sets the level of its `-l` option (WARNING when absent) and
    adds its own handler, and `worker_hijack_root_logger=False` does not prevent either.
    Every `logger.info` of every task disappeared that way. Answering the signal is how
    Celery documents opting out, and it leaves `LOG_LEVEL` in charge, as it is in the API.
    """
    setup_logging.connect(
        _logging_ya_configurado, weak=False, dispatch_uid=IDENTIFICADOR_DEL_LOGGING
    )


def _logging_ya_configurado(**_: object) -> None:
    """Nothing to do: `workers/main.py` ran `configurar_logging` before the worker started."""
