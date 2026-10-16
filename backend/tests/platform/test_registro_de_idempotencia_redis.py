"""The Redis adapter translates store failures into the port's own exception (no network)."""

from __future__ import annotations

from typing import Any, cast

import pytest
from cheatsheet.platform.cache import (
    ErrorDeRegistroDeIdempotencia,
    RegistroDeIdempotenciaRedis,
)
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError


class _RedisQueNoResponde:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def delete(self, *claves: str) -> int:
        del claves
        raise self._error


def _registro(error: Exception) -> RegistroDeIdempotenciaRedis:
    return RegistroDeIdempotenciaRedis(cast(Redis, cast(Any, _RedisQueNoResponde(error))))


def _clave(empresa_id: EmpresaId) -> ClaveDeIdempotencia:
    return ClaveDeIdempotencia.de(empresa_id=empresa_id, tipo="prueba", payload={"a": 1})


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RedisConnectionError("caido"), OSError("sin red")])
async def test_liberar_traduce_los_errores_del_almacen(empresa_id: EmpresaId, error: Exception):
    with pytest.raises(ErrorDeRegistroDeIdempotencia) as capturado:
        await _registro(error).liberar(_clave(empresa_id))

    assert capturado.value.__cause__ is error
