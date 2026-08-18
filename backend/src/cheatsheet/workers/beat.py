"""Celery Beat — the periodic schedule.

**Empty on purpose, and that is worth stating.** The scheduler is infrastructure this
unit builds; the things it will schedule belong to later epics and arrive with them:

| Entry | Epic | Story |
| --- | --- | --- |
| Reminder chain dispatch | 6 | HS-T3 |
| Re-enqueue of `Comprobante` stuck in `VALIDADO` | 5 | HS-T4 |
| Incremental spreadsheet sync | 4 | HU-E3-04 |
| DLQ sweep for exhausted tasks | 4 | HS-T6 |
| Fiscal parameter refresh from ARCA | 5 | open question 8.8 |

Beat runs as **one** process. Replicating it duplicates every entry above, which on
the reminder chain means every customer receives each message twice.
"""

from __future__ import annotations

from typing import Any

from celery import Celery

PROGRAMACION: dict[str, dict[str, Any]] = {}


def configurar_beat(app: Celery) -> Celery:
    """Install the periodic schedule on a Celery application."""
    app.conf.beat_schedule = PROGRAMACION
    app.conf.beat_max_loop_interval = 60
    return app
