"""Celery Beat — the periodic schedule.

**One entry so far**, added by `conexion-whatsapp`: the sweep that waits out Meta's number
verification (HU-E2-03 RN-02). It is the first thing in this system that has to happen
without anybody asking for it.

Everything else this scheduler will eventually carry belongs to later epics and arrives
with them:

| Entry | Epic | Story |
| --- | --- | --- |
| Reminder chain dispatch | 6 | HS-T3 |
| Re-enqueue of `Comprobante` stuck in `VALIDADO` | 5 | HS-T4 |
| Incremental spreadsheet sync | 4 | HU-E3-04 |
| DLQ sweep for exhausted tasks | 4 | HS-T6 |
| Fiscal parameter refresh from ARCA | 5 | open question 8.8 |

Beat runs as **one** process. Replicating it duplicates every entry above — and now that
there is a real one, that warning has teeth: two schedulers mean two sweeps, two polls per
company and, at the moment Meta answers, two emails to every Administrator.

The schedule is built from `Settings` rather than hardcoded, because the poll interval is
a deployment decision (`WHATSAPP_SONDEO_MINUTOS`) and a constant here would mean a release
to change it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from celery import Celery

from cheatsheet.platform.settings import Settings
from cheatsheet.workers.celery_app import Cola


def programacion(settings: Settings) -> dict[str, dict[str, Any]]:
    """The periodic entries, resolved against configuration."""
    return {
        "sondear-integraciones-pendientes": {
            "task": "integrations.sondear_pendientes",
            "schedule": timedelta(minutes=max(settings.whatsapp_sondeo_minutos, 1)),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        }
    }


def configurar_beat(app: Celery, settings: Settings) -> Celery:
    """Install the periodic schedule on a Celery application."""
    app.conf.beat_schedule = programacion(settings)
    app.conf.beat_max_loop_interval = 60
    return app
