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
from cheatsheet.api.routers import (
    agenda,
    auth,
    bitacora,
    categorias,
    clientes,
    cobros,
    comprobantes,
    contador,
    conversaciones,
    health,
    integraciones,
    planillas,
    puntos_de_venta,
    reglas,
    reporteria,
    servicios,
    usuarios,
    webhooks,
    whatsapp,
)
from cheatsheet.contexts.master_data.application.errors import ClienteDuplicado
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
    # More specific than the generic domain handler, and registered after it so it
    # wins: the uniform `{error, detalle}` body has nowhere to put the id of the
    # client that already holds the CUIT, and HU-E4-01 asks the screen to offer it.
    app.add_exception_handler(ClienteDuplicado, clientes.manejar_duplicado)

    # One line per bounded context. `observability` exposes no HTTP surface yet: its
    # panel is HU-E12-01, epic 10.
    app.include_router(health.crear_router(recursos))
    app.include_router(auth.crear_router(recursos))
    app.include_router(usuarios.crear_router(recursos))
    app.include_router(integraciones.crear_router(recursos))
    app.include_router(clientes.crear_router(recursos))
    app.include_router(servicios.crear_router(recursos))
    app.include_router(categorias.crear_router(recursos))
    app.include_router(planillas.crear_router(recursos))
    app.include_router(puntos_de_venta.crear_router(recursos))
    app.include_router(comprobantes.crear_router(recursos))
    app.include_router(cobros.crear_router(recursos))
    app.include_router(agenda.crear_router(recursos))
    app.include_router(reglas.crear_router(recursos))
    app.include_router(conversaciones.crear_router(recursos))
    app.include_router(webhooks.crear_router(recursos))
    app.include_router(whatsapp.crear_router(recursos))
    app.include_router(reporteria.crear_router(recursos))
    app.include_router(bitacora.crear_router(recursos))
    # La única ruta pública del épico 9. Va última y con su propio módulo: ver `contador.py`.
    app.include_router(contador.crear_router(recursos))

    return app
