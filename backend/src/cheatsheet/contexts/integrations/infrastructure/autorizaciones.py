"""Where an OAuth2 authorization in flight lives — the adapters of `PortMemoriaDeAutorizacion`.

Outside `mercadopago/` on purpose: nothing here is MercadoPago's. It stores a `state`, the
company that owns it and a PKCE verifier, for the ten minutes between the browser leaving
and coming back.

**Redis and not a table**, for the same reason the idempotency record lives there: these
entries are short-lived by nature and expire on their own. A table would need a row, a
migration and a job to sweep what nobody claimed.

`consumir` is a single `GETDEL`. That is what makes a `state` single-use under
concurrency: a read followed by a delete would let two callbacks arriving at the same
instant both find it, and connecting twice with the same `state` is precisely what the
check exists to stop.
"""

from __future__ import annotations

import json

from redis.asyncio import Redis

from cheatsheet.contexts.integrations.application.ports import AutorizacionPendiente
from cheatsheet.contexts.integrations.domain.valores import SistemaExterno
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import empresa_id_desde

logger = obtener_logger(__name__)

PREFIJO = "oauth:"


def _serializar(pendiente: AutorizacionPendiente) -> str:
    return json.dumps(
        {
            "empresa_id": str(pendiente.empresa_id),
            "sistema": pendiente.sistema.value,
            "verificador": pendiente.verificador,
        }
    )


def _deserializar(crudo: str) -> AutorizacionPendiente | None:
    """A stored entry we cannot read is treated as absent, not as an error.

    The caller's answer to `None` is already the right one — «volvé a iniciar la
    conexión» — and a malformed entry only ever means the format changed under a
    deployment, which resolves itself in ten minutes.
    """
    try:
        datos = json.loads(crudo)
        return AutorizacionPendiente(
            empresa_id=empresa_id_desde(datos["empresa_id"]),
            sistema=SistemaExterno(datos["sistema"]),
            verificador=datos["verificador"],
        )
    except (ValueError, KeyError, TypeError):
        logger.warning("autorizacion_ilegible")
        return None


class MemoriaDeAutorizacionRedis:
    """The production adapter."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def guardar(
        self, estado: str, pendiente: AutorizacionPendiente, ttl_segundos: int
    ) -> None:
        await self._redis.set(f"{PREFIJO}{estado}", _serializar(pendiente), ex=ttl_segundos)

    async def consumir(self, estado: str) -> AutorizacionPendiente | None:
        crudo = await self._redis.getdel(f"{PREFIJO}{estado}")
        if crudo is None:
            return None
        # `decode_responses=True` is set on the client, so this is already text.
        return _deserializar(crudo if isinstance(crudo, str) else crudo.decode("utf-8"))


class MemoriaDeAutorizacionEnMemoria:
    """In-process adapter for tests and for the local single-process runner.

    It ignores the TTL: nothing in a test lives long enough for ten minutes to matter, and
    expiry is Redis's job in the only place it has consequences.
    """

    def __init__(self) -> None:
        self._entradas: dict[str, AutorizacionPendiente] = {}

    async def guardar(
        self, estado: str, pendiente: AutorizacionPendiente, ttl_segundos: int
    ) -> None:
        del ttl_segundos
        self._entradas[estado] = pendiente

    async def consumir(self, estado: str) -> AutorizacionPendiente | None:
        return self._entradas.pop(estado, None)
