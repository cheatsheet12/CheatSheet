"""The legal catalogue is checked once, at boot (HU-E1-08 RN-01).

If a document had no version in force today, every authenticated request would fail inside the
session check with a 500. That is a deployment mistake, so it stops the process from starting
instead of surfacing, one request at a time, as an outage.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast

import pytest
import structlog
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.platform.settings import ConfiguracionFaltante
from cheatsheet.shared.clock import RelojFijo
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import INSTANTE_CON_TEXTOS_VIGENTES, settings_de_prueba

#: Before the first published texts (2026-10-10), and after.
ANTES_DE_LOS_TEXTOS = datetime(2026, 8, 12, 15, 30, tzinfo=UTC)
CON_TEXTOS_VIGENTES = INSTANTE_CON_TEXTOS_VIGENTES


@pytest.fixture(autouse=True)
def _sin_logging_configurado_al_salir() -> Iterator[None]:
    """`create_app` configures structlog with `cache_logger_on_first_use`.

    This module sorts before the tests that capture other modules' logs with `capture_logs`, and
    a logger first used after that configuration can no longer be captured. Leave the process as
    this module found it.
    """
    yield
    structlog.reset_defaults()


def _recursos(instante: datetime) -> Recursos:
    return Recursos(
        settings=settings_de_prueba(),
        engine=cast(AsyncEngine, None),
        sesiones=cast("async_sessionmaker[AsyncSession]", None),
        redis=cast(Redis, None),
        reloj=RelojFijo(instante),
    )


def test_arrancar_sin_version_vigente_de_un_documento_falla_con_un_error_claro():
    with pytest.raises(ConfiguracionFaltante, match=r"PRIVACIDAD|TERMINOS"):
        create_app(settings_de_prueba(), _recursos(ANTES_DE_LOS_TEXTOS))


def test_arrancar_con_las_versiones_vigentes_arma_la_aplicacion():
    app = create_app(settings_de_prueba(), _recursos(CON_TEXTOS_VIGENTES))

    assert app.title == "CheatSheet API"
