"""Two consecutive task executions, against the real database and Redis.

**This is the QA defect, reproduced.** The first invitation email went out and the second
died with `got Future attached to a different loop`. The worker built its `Recursos` once
at import; every Celery execution calls `asyncio.run`, which opens a new event loop and
closes it at the end; the second execution then checked a connection out of a pool that
belonged to a loop that no longer existed.

It could not be caught anywhere else. The unit tests drive `enviar_invitacion` directly
inside one loop, and the API tests never touch Celery's synchronous bridge. Only running
the bridge **twice**, against real connections, shows it — which is exactly what this
does.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cheatsheet.platform.settings import Settings
from cheatsheet.workers.tasks_identity import enviar_invitacion_sync

from tests.conftest import settings_de_prueba
from tests.integracion.conftest import requiere_base

pytestmark = [requiere_base, pytest.mark.integration]

requiere_redis = pytest.mark.skipif(
    os.environ.get("REDIS_URL", "").strip() == "",
    reason="Necesita Redis: el registro de idempotencia vive ahí.",
)


def _settings() -> Settings:
    return replace(
        settings_de_prueba(),
        database_url=os.environ["DATABASE_URL"],
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6380/0"),
    )


def _enviar(settings: Settings) -> object:
    """One execution of exactly what Celery calls."""
    return enviar_invitacion_sync(
        settings,
        empresa_id=str(uuid4()),
        invitacion_id=str(uuid4()),
        destinatario="beto@empresa.com",
        invitado_por_id=str(uuid4()),
        token="un-token-de-invitacion-de-prueba",
        expira_en=(datetime.now(UTC) + timedelta(days=7)).isoformat(),
    )


@requiere_redis
@pytest.mark.parametrize("ejecucion", [1, 2, 3])
def test_la_tarea_corre_muchas_veces_en_el_mismo_proceso(
    esquema_migrado: None, ejecucion: int
) -> None:
    """Three executions in one process. Before the fix, only the first survived.

    Parametrised rather than looped so a failure names *which* execution broke — the
    difference between "the task is broken" and "the task is broken from the second one
    on", which is the whole diagnosis.
    """
    assert _enviar(_settings()) is True


@requiere_redis
def test_tres_ejecuciones_seguidas_dentro_de_un_solo_test(esquema_migrado: None) -> None:
    """The same thing without pytest between the calls, in case the runner is what resets
    something. It is not: the resources are what has to be per-execution."""
    settings = _settings()

    resultados = [_enviar(settings) for _ in range(3)]

    assert resultados == [True, True, True]
