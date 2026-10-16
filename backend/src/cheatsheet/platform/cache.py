"""Redis: Celery's broker, and the store that makes a retried task a no-op.

The idempotency record is the only thing here that guards a real effect, so it is
the only thing with an opinionated TTL. Seven days is longer than any retry window
in the system (ADR-009) and shorter than forever, which is what an unbounded key
space eventually costs.

`registrar_si_es_nueva` is a single `SET NX EX`, and that matters: two workers
picking up the same task at the same instant must not both see "not processed yet".
A read followed by a write would let them.

`liberar` exists for the one case where keeping the key is wrong: the effect raised, the
queue is going to retry, and the retry must be allowed to run it (see
`workers/base.py`, `AnteUnaFalla`).
"""

from __future__ import annotations

from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from cheatsheet.platform.settings import Settings
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia

PREFIJO_IDEMPOTENCIA = "idem:"
TTL_IDEMPOTENCIA_SEGUNDOS = 7 * 24 * 60 * 60


class ErrorDeRegistroDeIdempotencia(Exception):
    """The idempotency registry could not be reached or refused the operation.

    Adapters translate their store's errors into this one, so callers (`workers/base.py`)
    never have to know which store is behind the port.
    """


class RegistroDeIdempotencia(Protocol):
    """The port a task depends on to know whether its effect already happened."""

    async def registrar_si_es_nueva(self, clave: ClaveDeIdempotencia) -> bool:
        """True when this key was not seen before — i.e. the caller should proceed."""
        ...

    async def liberar(self, clave: ClaveDeIdempotencia) -> None:
        """Forget this key so the next attempt may claim it. Idempotent: a missing key is fine.

        Raises `ErrorDeRegistroDeIdempotencia` when the store cannot be reached.
        """
        ...


def crear_redis(settings: Settings) -> Redis:
    # `from_url` is annotated as returning Any; naming the type here is what keeps the
    # rest of the module honestly typed instead of silently degrading to Any.
    cliente: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return cliente


class RegistroDeIdempotenciaRedis:
    """The production adapter."""

    def __init__(self, redis: Redis, ttl_segundos: int = TTL_IDEMPOTENCIA_SEGUNDOS) -> None:
        self._redis = redis
        self._ttl = ttl_segundos

    async def registrar_si_es_nueva(self, clave: ClaveDeIdempotencia) -> bool:
        resultado = await self._redis.set(
            f"{PREFIJO_IDEMPOTENCIA}{clave.valor}", "1", nx=True, ex=self._ttl
        )
        return bool(resultado)

    async def liberar(self, clave: ClaveDeIdempotencia) -> None:
        try:
            await self._redis.delete(f"{PREFIJO_IDEMPOTENCIA}{clave.valor}")
        except (RedisError, OSError) as error:
            raise ErrorDeRegistroDeIdempotencia(type(error).__name__) from error


class RegistroDeIdempotenciaEnMemoria:
    """In-process adapter for tests and for the local single-process runner."""

    def __init__(self) -> None:
        self._vistas: set[str] = set()

    async def registrar_si_es_nueva(self, clave: ClaveDeIdempotencia) -> bool:
        if clave.valor in self._vistas:
            return False
        self._vistas.add(clave.valor)
        return True

    async def liberar(self, clave: ClaveDeIdempotencia) -> None:
        self._vistas.discard(clave.valor)


async def verificar_redis(redis: Redis) -> bool:
    """Liveness probe for the healthcheck."""
    await redis.ping()
    return True
