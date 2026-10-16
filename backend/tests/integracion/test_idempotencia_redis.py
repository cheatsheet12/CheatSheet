"""The idempotency registry against a real Redis (issue #216, case 7).

The unit tests use the in-memory registry, which proves the executor's logic but not that
`SET NX EX` and `DEL` do what the Redis adapter says. This does, including the seven-day
TTL that bounds the key space.

Skipped without Redis (and without the database the rest of this folder needs), like
`test_tareas_en_loops_distintos.py`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from cheatsheet.platform.cache import (
    PREFIJO_IDEMPOTENCIA,
    TTL_IDEMPOTENCIA_SEGUNDOS,
    RegistroDeIdempotenciaRedis,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from redis.asyncio import Redis

from tests.integracion.conftest import requiere_base

pytestmark = [
    requiere_base,
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("REDIS_URL", "").strip() == "",
        reason="Necesita Redis: el registro de idempotencia vive ahí.",
    ),
]


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    cliente: Redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield cliente
    await cliente.aclose()


def _clave() -> ClaveDeIdempotencia:
    # A fresh company per test: the key is scoped by it, so nothing leaks between runs.
    return ClaveDeIdempotencia.de(empresa_id=EmpresaId(uuid4()), tipo="enviar", payload={"id": 1})


async def test_reservar_ocupa_la_clave_y_liberar_la_devuelve(redis: Redis) -> None:
    registro = RegistroDeIdempotenciaRedis(redis)
    clave = _clave()

    assert await registro.registrar_si_es_nueva(clave) is True
    assert await registro.registrar_si_es_nueva(clave) is False

    await registro.liberar(clave)

    assert await registro.registrar_si_es_nueva(clave) is True
    await registro.liberar(clave)


async def test_la_clave_vence_a_los_siete_dias(redis: Redis) -> None:
    registro = RegistroDeIdempotenciaRedis(redis)
    clave = _clave()

    await registro.registrar_si_es_nueva(clave)

    ttl = await redis.ttl(f"{PREFIJO_IDEMPOTENCIA}{clave.valor}")
    assert 0 < ttl <= TTL_IDEMPOTENCIA_SEGUNDOS == 7 * 24 * 60 * 60
    await registro.liberar(clave)


async def test_liberar_una_clave_inexistente_no_falla(redis: Redis) -> None:
    await RegistroDeIdempotenciaRedis(redis).liberar(_clave())
