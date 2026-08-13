"""The FastAPI application: one process hosting twelve bounded contexts (ADR-001).

`create_app` is a factory rather than a module-level `app = FastAPI()` because a test
needs to build the application with its own settings and its own resources, and a
module-level instance would connect to whatever the environment happened to hold at
import time.

Routers are mounted here, one line per context, and that line is the only place a
context is exposed. Today there is one; by epic 10 there are twelve, and the shape of
this file does not change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.errors import registrar_manejadores
from cheatsheet.api.middleware.empresa import EmpresaMiddleware
from cheatsheet.api.routers import health
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import configurar_logging, obtener_logger

logger = obtener_logger(__name__)

TITULO = "CheatSheet API"
VERSION = "0.1.0"


def create_app(settings: Settings | None = None, recursos: Recursos | None = None) -> FastAPI:
    """Build the application.

    Both arguments exist for tests: passing `recursos` skips creating a real engine
    and a real Redis client, which is what lets an API test run without either.
    """
    settings = settings or Settings.desde_entorno()
    configurar_logging(settings)
    recursos = recursos or Recursos.crear(settings)

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
        logger.info("api_iniciada", entorno=settings.entorno.value)
        yield
        await recursos.cerrar()
        logger.info("api_detenida")

    app = FastAPI(
        title=TITULO,
        version=VERSION,
        lifespan=ciclo_de_vida,
        # The panel is served from another origin (Vercel), and its BFF is what talks
        # to this API — the browser never does. So no CORS middleware, on purpose.
        docs_url=None if settings.es_produccion else "/docs",
        redoc_url=None,
    )

    app.add_middleware(EmpresaMiddleware, settings=settings)
    registrar_manejadores(app)

    # One line per bounded context. `observability` exposes no HTTP surface yet: its
    # panel is HU-E12-01, epic 10.
    app.include_router(health.crear_router(recursos))

    return app
