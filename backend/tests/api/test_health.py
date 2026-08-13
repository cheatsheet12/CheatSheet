"""The healthcheck, the error handler and the tenant middleware.

Driven through the real ASGI app with `httpx.ASGITransport`, so routing, middleware
and exception handlers are exercised — in process, without opening a socket.
"""

from __future__ import annotations

from typing import cast

import httpx
import pytest
from cheatsheet.api.dependencies import Recursos
from cheatsheet.api.main import create_app
from cheatsheet.api.middleware.empresa import HEADER_EMPRESA
from cheatsheet.platform.settings import Entorno, Settings
from cheatsheet.shared.clock import RelojFijo
from cheatsheet.shared.errors import InvarianteViolada
from fastapi import APIRouter, FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.conftest import INSTANTE_FIJO


def _settings(entorno: Entorno = Entorno.TEST) -> Settings:
    return Settings(
        entorno=entorno,
        database_url="postgresql+asyncpg://x/y",
        database_url_migrations="postgresql+asyncpg://x/y",
        redis_url="redis://localhost:6380/0",
        celery_broker_url="redis://localhost:6380/0",
        celery_result_backend="redis://localhost:6380/0",
        log_level="WARNING",
    )


def _recursos(settings: Settings) -> Recursos:
    """Resources whose engine and Redis are never actually used.

    The probes are patched in every test below, so nothing dereferences these. Passing
    them as None keeps the test honest about what it is *not* checking, instead of a
    mock that would happily answer any call.
    """
    return Recursos(
        settings=settings,
        engine=cast(AsyncEngine, None),
        sesiones=cast("async_sessionmaker[AsyncSession]", None),
        redis=cast(Redis, None),
        reloj=RelojFijo(INSTANTE_FIJO),
    )


def _cliente(app: FastAPI) -> httpx.AsyncClient:
    """Drive the app in process: no socket, no lifespan, no network."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def parchar_sondas(monkeypatch: pytest.MonkeyPatch):
    def aplicar(base_ok: bool, redis_ok: bool) -> None:
        async def sonda_base(_engine: object) -> bool:
            if not base_ok:
                raise OSError("conexion rechazada")
            return True

        async def sonda_redis(_redis: object) -> bool:
            if not redis_ok:
                raise OSError("conexion rechazada")
            return True

        monkeypatch.setattr("cheatsheet.api.routers.health.verificar_conexion", sonda_base)
        monkeypatch.setattr("cheatsheet.api.routers.health.verificar_redis", sonda_redis)

    return aplicar


@pytest.mark.asyncio
async def test_health_responde_ok_con_las_dependencias_arriba(parchar_sondas):
    parchar_sondas(base_ok=True, redis_ok=True)
    app = create_app(_settings(), _recursos(_settings()))

    async with _cliente(app) as cliente:
        respuesta = await cliente.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"estado": "ok", "base_de_datos": True, "redis": True}


@pytest.mark.asyncio
async def test_health_responde_503_si_la_base_esta_caida(parchar_sondas):
    """503 and not 200: a load balancer must take the instance out of rotation."""
    parchar_sondas(base_ok=False, redis_ok=True)
    app = create_app(_settings(), _recursos(_settings()))

    async with _cliente(app) as cliente:
        respuesta = await cliente.get("/health")

    assert respuesta.status_code == 503
    assert respuesta.json()["estado"] == "degradado"
    assert respuesta.json()["base_de_datos"] is False


@pytest.mark.asyncio
async def test_health_no_exige_empresa(parchar_sondas):
    """It is reachable before any company exists, and without authentication."""
    parchar_sondas(base_ok=True, redis_ok=True)
    app = create_app(_settings(), _recursos(_settings()))

    async with _cliente(app) as cliente:
        respuesta = await cliente.get("/health")

    assert respuesta.status_code == 200


@pytest.mark.asyncio
async def test_una_ruta_de_negocio_sin_empresa_es_rechazada(parchar_sondas):
    parchar_sondas(base_ok=True, redis_ok=True)
    settings = _settings()
    app = create_app(settings, _recursos(settings))
    app.include_router(_router_de_prueba())

    async with _cliente(app) as cliente:
        respuesta = await cliente.get("/prueba/eco")

    assert respuesta.status_code == 401


@pytest.mark.asyncio
async def test_en_produccion_el_header_de_empresa_es_ignorado(parchar_sondas):
    """The development shortcut must not survive a deploy. This is what proves it."""
    parchar_sondas(base_ok=True, redis_ok=True)
    settings = _settings(Entorno.PRODUCTION)
    app = create_app(settings, _recursos(settings))
    app.include_router(_router_de_prueba())

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(
            "/prueba/eco", headers={HEADER_EMPRESA: "3f1c2b8e-0000-4000-8000-000000000001"}
        )

    assert respuesta.status_code == 401


@pytest.mark.asyncio
async def test_un_error_de_dominio_se_traduce_sin_filtrar_internals(parchar_sondas):
    parchar_sondas(base_ok=True, redis_ok=True)
    settings = _settings()
    app = create_app(settings, _recursos(settings))
    app.include_router(_router_de_prueba())

    async with _cliente(app) as cliente:
        respuesta = await cliente.get(
            "/prueba/romper", headers={HEADER_EMPRESA: "3f1c2b8e-0000-4000-8000-000000000001"}
        )

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["error"] == "InvarianteViolada"
    assert "Traceback" not in str(cuerpo)


def _router_de_prueba() -> APIRouter:
    router = APIRouter(prefix="/prueba")

    @router.get("/eco")
    async def eco() -> dict[str, str]:
        return {"eco": "ok"}

    @router.get("/romper")
    async def romper() -> dict[str, str]:
        raise InvarianteViolada("Debe existir al menos un Administrador activo")

    return router
