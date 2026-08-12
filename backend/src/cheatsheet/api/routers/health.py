"""Healthcheck.

It reports on the two dependencies whose absence makes the process useless rather
than merely degraded: the database and Redis. It answers 503 when either is down, so
a load balancer takes the instance out instead of routing traffic into a wall.

It says nothing about versions, hostnames or connection strings. A healthcheck is
reachable without authentication, so everything it prints is public.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Literal

from cheatsheet.api.dependencies import Recursos
from cheatsheet.platform.cache import verificar_redis
from cheatsheet.platform.database import verificar_conexion
from cheatsheet.platform.telemetry import obtener_logger
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

logger = obtener_logger(__name__)

# What a dependency being down actually looks like. Listed explicitly rather than
# caught as `Exception`, so that a bug in our own probe surfaces as a 500 instead of
# being reported as "the database is down" and sending someone to the wrong place.
FALLAS_DE_DEPENDENCIA = (SQLAlchemyError, RedisError, OSError, TimeoutError)


class EstadoDeSalud(BaseModel):
    estado: Literal["ok", "degradado"]
    base_de_datos: bool
    redis: bool


async def _probar(prueba: Awaitable[bool], nombre: str) -> bool:
    try:
        return await prueba
    except FALLAS_DE_DEPENDENCIA as exc:
        logger.warning("dependencia_caida", dependencia=nombre, motivo=str(exc))
        return False


def crear_router(recursos: Recursos) -> APIRouter:
    """Build the health router bound to the process resources."""
    router = APIRouter(tags=["health"])

    @router.get("/health", response_model=EstadoDeSalud)
    async def health(response: Response) -> EstadoDeSalud:
        base = await _probar(verificar_conexion(recursos.engine), "base_de_datos")
        redis = await _probar(verificar_redis(recursos.redis), "redis")
        sano = base and redis
        if not sano:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return EstadoDeSalud(estado="ok" if sano else "degradado", base_de_datos=base, redis=redis)

    return router
