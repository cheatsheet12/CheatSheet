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

Beat runs as **one** process. Replicating it duplicates every entry above — and now that
there is a real one, that warning has teeth: two schedulers mean two sweeps, two polls per
company and, at the moment Meta answers, two emails to every Administrator.

Entries that touch the database and repeat within a day are anchored to the wall clock
(`alineado`) instead of counting from Beat's boot, so they all fire at the same instants
and a serverless database wakes once per period. That includes the daily entries (00:00)
and the fiscal parameters sync, whose interval is validated at startup.

The schedule is built from `Settings` rather than hardcoded, because the poll interval is
a deployment decision (`WHATSAPP_SONDEO_MINUTOS`) and a constant here would mean a release
to change it.
"""

from __future__ import annotations

from typing import Any

from celery import Celery
from celery.schedules import crontab

from cheatsheet.platform.intervalos import MINUTOS_POR_HORA, campos_alineados
from cheatsheet.platform.settings import Settings
from cheatsheet.workers.celery_app import Cola

MINUTOS_POR_DIA = 24 * MINUTOS_POR_HORA


def alineado(minutos: int) -> crontab:
    """An interval anchored to the wall clock, so every task wakes the database together.

    See `platform/intervalos.py` for the rule and for why it never rounds.
    """
    minuto, hora = campos_alineados(minutos)
    return crontab(minute=minuto, hour=hora)


def programacion(settings: Settings) -> dict[str, dict[str, Any]]:
    """The periodic entries, resolved against configuration."""
    return {
        "sondear-integraciones-pendientes": {
            "task": "integrations.sondear_pendientes",
            "schedule": alineado(settings.whatsapp_sondeo_minutos),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        "revisar-vencimientos-de-credenciales": {
            "task": "integrations.revisar_vencimientos",
            "schedule": alineado(MINUTOS_POR_DIA),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        # Daily against a token that lasts about 180 days, and renewed a fortnight before
        # it expires: fourteen chances to survive an outage before anything breaks.
        "renovar-credenciales-oauth": {
            "task": "integrations.renovar_credenciales",
            "schedule": alineado(MINUTOS_POR_DIA),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        # HS-T6. On the notifications queue rather than a queue of its own: the sweep is
        # a short read plus a handful of updates, and ADR-003 fixed the queue count at
        # five. Frequent because a task sitting in FALLIDA is invisible to the operator
        # until it is retired, not because the work is urgent.
        # HU-E3-04. On the `incremental_sync` queue, which ADR-003 created for it. The
        # interval is configuration and not a constant, for the reason this module already
        # gives about the polling one.
        # HS-T4. The least frequent entry here on purpose: ARCA's catalogues move once
        # every several months, and asking more often is a call to learn nothing changed.
        "sincronizar-parametros-fiscales": {
            "task": "reference_data.sincronizar_parametros",
            "schedule": alineado(settings.parametros_fiscales_horas * 60),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        "sincronizar-planillas": {
            "task": "spreadsheet_sync.sincronizar_pendientes",
            "schedule": alineado(settings.sync_planillas_minutos),
            "options": {"queue": Cola.INCREMENTAL_SYNC.value},
        },
        # Decision D17: the retry that `billing.autorizar_comprobante` deliberately does
        # not have. Frequent, because what it settles is a document whose fate the company
        # does not know -- and infrequent enough not to race the task still awaiting ARCA,
        # which `VENTANA_DE_VUELO` is what actually guards.
        "reconciliar-comprobantes-en-vuelo": {
            "task": "billing.reconciliar_comprobantes",
            "schedule": alineado(settings.billing_reconciliacion_minutos),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        # HS-T3 y HU-E6-01 RN-03. Cada hora: una deuda no cambia de estado al minuto, y la
        # cadena de recordatorios cuenta en días. Más seguido sería preguntar lo mismo
        # sesenta veces para enterarse de que nada cambió.
        "barrer-cobros": {
            "task": "payments.barrer_cobros",
            "schedule": alineado(60),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
        # Las FAQ que quedaron sin vector. Cada seis horas: sólo hay algo que hacer cuando el
        # proveedor de embeddings estuvo caído o cuando alguien cambió de modelo, y ninguna de
        # las dos cosas pasa varias veces por día. Mientras tanto la FAQ se lee y se edita; lo
        # único que no puede es encontrarse por significado.
        "reindexar-faqs": {
            "task": "conversational.barrer_faqs",
            "schedule": alineado(360),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
        # HU-E10-04. **Diario y no mensual**: el día de envío lo elige cada empresa, así que
        # no hay un día del mes en el que corresponda correr — hay un día por empresa. La
        # corrida de un día sin empresas programadas es una consulta que devuelve cero filas.
        "armar-paquetes-contables": {
            "task": "reporting.barrer_paquetes",
            "schedule": alineado(MINUTOS_POR_DIA),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
        "barrer-tareas-agotadas": {
            "task": "observability.barrer_dlq",
            "schedule": alineado(settings.dlq_barrido_minutos),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
    }


def configurar_beat(app: Celery, settings: Settings) -> Celery:
    """Install the periodic schedule on a Celery application."""
    app.conf.beat_schedule = programacion(settings)
    app.conf.beat_max_loop_interval = 60
    return app
