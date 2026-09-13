"""Entry point for the worker and scheduler processes.

    celery -A cheatsheet.workers.main:app worker -Q notifications -c 4
    celery -A cheatsheet.workers.main:app beat

Kept apart from `celery_app.py` so that importing the factory does not require a
configured environment. A test imports `crear_celery`; only a real worker imports
this module, and only a real worker should fail at import when `REDIS_URL` is absent.
"""

from __future__ import annotations

from celery import Celery

from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import configurar_logging
from cheatsheet.workers.beat import configurar_beat
from cheatsheet.workers.celery_app import crear_celery
from cheatsheet.workers.tasks_identity import registrar_en as registrar_identity
from cheatsheet.workers.tasks_integrations import registrar_en as registrar_integrations
from cheatsheet.workers.tasks_observability import registrar as registrar_observability
from cheatsheet.workers.tasks_spreadsheet import registrar as registrar_spreadsheet

settings = Settings.desde_entorno()
configurar_logging(settings)

app: Celery = configurar_beat(crear_celery(settings), settings)

# Tasks get `Settings`, not resources. The API can hold an engine for the life of the
# process because it serves every request on one event loop; a Celery worker runs each
# task in a fresh one, and a connection pool does not survive that. See
# `workers/ejecucion.py` — this is the defect QA found by sending two invitations.
registrar_identity(app, settings)
registrar_integrations(app, settings)
registrar_observability(app, settings)
registrar_spreadsheet(app, settings)
