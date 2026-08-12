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

settings = Settings.desde_entorno()
configurar_logging(settings)

app: Celery = configurar_beat(crear_celery(settings))
