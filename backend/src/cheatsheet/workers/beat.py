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
        # U6. La conciliación de las plantillas de WhatsApp con Meta: la red de seguridad del
        # webhook de estado de plantillas, que no admite override por cuenta. Misma escala que el
        # sondeo de verificación de número, porque la revisión de Meta tarda hasta 24 h.
        "conciliar-plantillas-de-whatsapp": {
            "task": "business_config.conciliar_plantillas",
            "schedule": timedelta(minutes=max(settings.whatsapp_plantillas_minutos, 1)),
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
        # HU-E3-04. On the `incremental_sync` queue, which ADR-003 created for it. The
        # interval is configuration and not a constant, for the reason this module already
        # gives about the polling one.
        # HS-T4. The least frequent entry here on purpose: ARCA's catalogues move once
        # every several months, and asking more often is a call to learn nothing changed.
        "sincronizar-parametros-fiscales": {
            "task": "reference_data.sincronizar_parametros",
            "schedule": timedelta(hours=max(settings.parametros_fiscales_horas, 1)),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        "sincronizar-planillas": {
            "task": "spreadsheet_sync.sincronizar_pendientes",
            "schedule": timedelta(minutes=max(settings.sync_planillas_minutos, 1)),
            "options": {"queue": Cola.INCREMENTAL_SYNC.value},
        },
        # Decision D17: the retry that `billing.autorizar_comprobante` deliberately does
        # not have. Frequent, because what it settles is a document whose fate the company
        # does not know -- and infrequent enough not to race the task still awaiting ARCA,
        # which `VENTANA_DE_VUELO` is what actually guards.
        "reconciliar-comprobantes-en-vuelo": {
            "task": "billing.reconciliar_comprobantes",
            "schedule": timedelta(minutes=5),
            "options": {"queue": Cola.INTEGRATIONS_SYNC.value},
        },
        # HS-T3 y HU-E6-01 RN-03. Cada hora: una deuda no cambia de estado al minuto, y la
        # cadena de recordatorios cuenta en días. Más seguido sería preguntar lo mismo
        # sesenta veces para enterarse de que nada cambió.
        "barrer-cobros": {
            "task": "payments.barrer_cobros",
            "schedule": timedelta(hours=1),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
        # Las FAQ que quedaron sin vector. Cada seis horas: sólo hay algo que hacer cuando el
        # proveedor de embeddings estuvo caído o cuando alguien cambió de modelo, y ninguna de
        # las dos cosas pasa varias veces por día. Mientras tanto la FAQ se lee y se edita; lo
        # único que no puede es encontrarse por significado.
        "reindexar-faqs": {
            "task": "conversational.barrer_faqs",
            "schedule": timedelta(hours=6),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
        # HU-E10-04. **Diario y no mensual**: el día de envío lo elige cada empresa, así que
        # no hay un día del mes en el que corresponda correr — hay un día por empresa. La
        # corrida de un día sin empresas programadas es una consulta que devuelve cero filas.
        "armar-paquetes-contables": {
            "task": "reporting.barrer_paquetes",
            "schedule": timedelta(days=1),
            "options": {"queue": Cola.NOTIFICATIONS.value},
        },
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
