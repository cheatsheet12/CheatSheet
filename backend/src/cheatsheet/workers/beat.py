"""Celery Beat — the periodic schedule.

**Two entries**, both from epic 2 and both about something that has to happen without
anybody asking for it:

- every 30 minutes, the sweep that waits out Meta's number verification (HU-E2-03 RN-02);
- once a day, the sweep that watches a fiscal certificate's expiry date (HU-E2-01 RN-04).
  Daily rather than half-hourly because a `notAfter` moves once every two years — and it
  costs no call to ARCA, because the date is inside the certificate we already hold.

Everything else this scheduler will eventually carry belongs to later epics and arrives
with them:

| Entry | Epic | Story |
| --- | --- | --- |
| Reminder chain dispatch | 6 | HS-T3 |
| Re-enqueue of `Comprobante` stuck in `VALIDADO` | 5 | HS-T4 |
| Incremental spreadsheet sync | 4 | HU-E3-04 |
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
        },
        "revisar-vencimientos-de-credenciales": {
            "task": "integrations.revisar_vencimientos",
            "schedule": timedelta(days=1),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        # Daily against a token that lasts about 180 days, and renewed a fortnight before
        # it expires: fourteen chances to survive an outage before anything breaks.
        "renovar-credenciales-oauth": {
            "task": "integrations.renovar_credenciales",
            "schedule": timedelta(days=1),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        # HS-T6. On the notifications queue rather than a queue of its own: the sweep is
        # a short read plus a handful of updates, and ADR-003 fixed the queue count at
        # five. Frequent because a task sitting in FALLIDA is invisible to the operator
        # until it is retired, not because the work is urgent.
        "barrer-tareas-agotadas": {
            "task": "observability.barrer_dlq",
            "schedule": timedelta(minutes=max(settings.dlq_barrido_minutos, 1)),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
    }


def configurar_beat(app: Celery, settings: Settings) -> Celery:
    """Install the periodic schedule on a Celery application."""
    app.conf.beat_schedule = programacion(settings)
    app.conf.beat_max_loop_interval = 60
    return app
