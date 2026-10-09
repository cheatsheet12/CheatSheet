"""Fixtures for the tests that need a real PostgreSQL.

Row-Level Security is a feature of the database engine. There is no fake for it: a
test against SQLite would pass while proving nothing, which is worse than no test at
all because it looks like coverage. So these tests connect to a real server.

**This does not break the rule that tests never touch the network.** That rule is
about external providers — ARCA, MercadoPago, WhatsApp, the LLM — which make suites
slow, flaky and dependent on somebody else's credentials. A container on localhost is
none of those things. ARCA and friends stay mocked, always.

They are skipped when the database is not configured, so `pytest` still passes on a
laptop with no Docker. CI always configures it, so the gate never quietly stops
checking — see the `tests` job in .github/workflows/ci.yml.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from cheatsheet.platform.database import crear_sessionmaker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

RAIZ_BACKEND = Path(__file__).resolve().parents[2]


def _url(nombre: str) -> str | None:
    return os.environ.get(nombre, "").strip() or None


requiere_base = pytest.mark.skipif(
    _url("DATABASE_URL") is None or _url("DATABASE_URL_MIGRATIONS") is None,
    reason=(
        "Necesita PostgreSQL. Levantalo con:\n"
        "  docker compose -f backend/docker-compose.yml up -d\n"
        "y exportá DATABASE_URL y DATABASE_URL_MIGRATIONS (ver backend/.env.example)."
    ),
)


@pytest.fixture(scope="session")
def esquema_migrado() -> None:
    """Bring the schema to head once per session, as the owner role.

    Running the real migrations rather than `metadata.create_all` is deliberate: it is
    the migration that creates the RLS policy and the grants, and those are precisely
    what these tests exist to check. `create_all` would build a table without them and
    every isolation test would pass for the wrong reason.
    """
    config = Config(str(RAIZ_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(RAIZ_BACKEND / "migrations"))
    command.upgrade(config, "head")


@pytest_asyncio.fixture
async def engine_aplicacion(esquema_migrado: None) -> AsyncIterator[AsyncEngine]:
    """Engine connected as `cheatsheet_app` — the role that RLS actually constrains."""
    url = _url("DATABASE_URL")
    assert url is not None  # guarded by requiere_base
    engine = create_async_engine(url, poolclass=None)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def engine_dueno(esquema_migrado: None) -> AsyncIterator[AsyncEngine]:
    """Engine connected as the owner. Used only to set up and inspect fixtures."""
    url = _url("DATABASE_URL_MIGRATIONS")
    assert url is not None
    engine = create_async_engine(url)
    yield engine
    await engine.dispose()


@pytest.fixture
def sesiones(engine_aplicacion: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return crear_sessionmaker(engine_aplicacion)


#: Children first: `invitacion` and `refresh_token` point at `usuario`, which points at
#: `empresa`. The cascades would handle it, but an explicit order does not depend on them.
#: Written as literal statements rather than interpolated table names — the same reason
#: the migrations are: a `f"DELETE FROM {x}"` is a SQL injection shape even when `x` is a
#: constant, and the linter is right to say so.
BORRADOS = (
    # `notificacion` y `solicitud_de_soporte` apuntan a `usuario` y a `empresa`, y la primera
    # además a `plantilla_de_notificacion`. Van primero, como el resto: de la hoja a la raíz.
    "DELETE FROM notificacion",
    "DELETE FROM solicitud_de_soporte",
    # `token_de_acceso_contable` antes que `paquete_contable`, y los dos antes que `empresa`.
    # `reporte` apunta además a `usuario`. El orden va de la hoja a la raíz, como el resto.
    "DELETE FROM token_de_acceso_contable",
    "DELETE FROM paquete_contable",
    "DELETE FROM reporte",
    "DELETE FROM configuracion_de_paquete",
    # `mensaje` y `escalamiento` antes que `conversacion`, y `conversacion` antes que
    # `cliente`: el orden va de la hoja a la raiz, como el resto de la lista. `faq_uso`
    # apunta a `mensaje` sin cascada (un uso no desaparece con su mensaje), así que va antes.
    "DELETE FROM faq_uso",
    "DELETE FROM mensaje",
    "DELETE FROM escalamiento",
    "DELETE FROM conversacion",
    "DELETE FROM faq",
    "DELETE FROM plantilla_de_notificacion",
    # `recordatorio_de_turno` apunta a `turno` y a `empresa`: antes que `turno`.
    "DELETE FROM recordatorio_de_turno",
    # `turno` antes que `cobro`: un turno apunta a la seña que lo reserva, y también al
    # cliente y al servicio. El orden va de la hoja a la raíz, como el resto de la lista.
    "DELETE FROM turno",
    "DELETE FROM servicio_de_recurso",
    "DELETE FROM excepcion_de_disponibilidad",
    "DELETE FROM patron_de_disponibilidad",
    "DELETE FROM recurso_reservable",
    # `recordatorio` y `cobro` antes que `comprobante`: un cobro apunta al comprobante que
    # salda, y el comprobante apunta al cliente. El orden va de la hoja a la raiz.
    "DELETE FROM recordatorio",
    # `reembolso` apunta a `cobro` sin cascada: un cobro con reembolsos no se borra solo.
    "DELETE FROM reembolso",
    "DELETE FROM cobro",
    "DELETE FROM regla_de_negocio",
    # `comprobante` primero: apunta a `cliente` y a `punto_de_venta` sin cascada, porque
    # un comprobante emitido no puede desaparecer porque alguien borre al cliente.
    "DELETE FROM item_de_comprobante",
    "DELETE FROM comprobante",
    "DELETE FROM punto_de_venta",
    "DELETE FROM registro_de_auditoria",
    "DELETE FROM ticket_de_acceso",
    "DELETE FROM ticket_de_plataforma",
    "DELETE FROM configuracion_de_integracion",
    "DELETE FROM respaldo_de_normalizacion",
    "DELETE FROM cliente_categoria",
    "DELETE FROM servicio_categoria",
    "DELETE FROM categoria_empresa",
    "DELETE FROM servicio",
    "DELETE FROM cliente",
    "DELETE FROM invitacion",
    "DELETE FROM refresh_token",
    "DELETE FROM usuario",
    "DELETE FROM empresa",
)


@pytest_asyncio.fixture(autouse=True)
async def base_limpia(engine_dueno: AsyncEngine) -> AsyncIterator[None]:
    """Empty the tables between tests, as the owner.

    The application role cannot do this to `registro_de_auditoria` — it holds no DELETE,
    which is the point of HS-T5 RN-03 — so the cleanup runs with the role that owns them.
    """
    yield
    async with engine_dueno.begin() as conexion:
        for sentencia in BORRADOS:
            await conexion.execute(text(sentencia))
