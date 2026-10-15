"""The processing guarantees every async task inherits (ADR-009).

Two mechanisms, both deliberately free of Celery so they can be tested without a
broker — which is also why they are useful to the webhook endpoints, which need the
same guarantee and are not tasks at all.

**Idempotency.** At-least-once delivery is the only thing a queue can promise, so the
same task will run twice. `EjecutorIdempotente` makes the second run a no-op, keyed by
`ClaveDeIdempotencia`. The claim is a single atomic `SET NX` (see `platform/cache.py`)
because two workers can start the same task in the same millisecond.

The claim is taken *before* the effect, so a failed attempt would keep it and every
Celery retry would be skipped as "already done" (issue #216: a lost invitation).
Whether a failed attempt may be repeated depends on the effect, so each caller states it
with `AnteUnaFalla`: `LIBERAR` for an effect that is safe to repeat, `RETENER` for one
that may have half happened (a charge, a document). There is deliberately no default.
A worker that dies mid-effect never reaches the release: that case is a known debt
(docs/aidlc/TODO.md), not something this module pretends to cover.

**Backoff with jitter.** Retrying on a fixed schedule turns one outage into a
synchronised stampede when the provider comes back: every task waiting on ARCA fires
at the same second and knocks it over again. The jitter spreads them out.

The retry ceiling per task type is still open (docs/architecture.md §10). The default
here is conservative and each caller may override it.
"""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeVar

from redis.exceptions import RedisError

from cheatsheet.platform.cache import RegistroDeIdempotencia
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia

logger = obtener_logger(__name__)

T = TypeVar("T")

MAX_INTENTOS_POR_DEFECTO = 5
ESPERA_BASE_SEGUNDOS = 2.0
ESPERA_MAXIMA_SEGUNDOS = 600.0


class AnteUnaFalla(StrEnum):
    """What to do with the idempotency key when the effect raises."""

    #: Free the key so the retry runs the effect again. Only for effects that are safe to
    #: repeat after a failure: nothing observable happened, or repeating it is harmless.
    LIBERAR = "liberar"
    #: Keep the key: the retry is skipped. For effects that may have half happened.
    RETENER = "retener"


@dataclass(frozen=True, slots=True)
class PoliticaDeReintentos:
    """How many times to retry, and how long to wait between attempts."""

    max_intentos: int = MAX_INTENTOS_POR_DEFECTO
    espera_base: float = ESPERA_BASE_SEGUNDOS
    espera_maxima: float = ESPERA_MAXIMA_SEGUNDOS

    def espera_para(self, intento: int) -> float:
        """Seconds to wait before attempt `intento` (1-based), with full jitter.

        Full jitter — a uniform draw over the whole window rather than a fixed
        fraction — is what actually decorrelates retries. `random` is fine here: this
        is scheduling, not a secret, and `secrets` would buy nothing.
        """
        if intento < 1:
            raise ValueError("El numero de intento arranca en 1")
        techo = min(self.espera_base * (2 ** (intento - 1)), self.espera_maxima)
        return random.uniform(0.0, techo)  # noqa: S311 — scheduling jitter, not crypto

    def agoto_los_intentos(self, intento: int) -> bool:
        return intento >= self.max_intentos


class EjecutorIdempotente:
    """Runs an effect at most once per idempotency key."""

    def __init__(self, registro: RegistroDeIdempotencia) -> None:
        self._registro = registro

    async def ejecutar(
        self,
        clave: ClaveDeIdempotencia,
        accion: Callable[[], Awaitable[T]],
        *,
        ante_una_falla: AnteUnaFalla,
    ) -> T | None:
        """Run `accion`, or return None if this key was already handled.

        The key is claimed *before* the effect runs. Claiming afterwards would leave a
        window in which a crash between effect and claim lets the retry run it again —
        which for a `Cobro` means charging twice.

        If `accion` raises and `ante_una_falla` is `LIBERAR`, the key is freed and the
        original exception propagates, so the queue's retry can run the effect. A
        cancellation never frees it: the outcome is unknown.
        """
        if not await self._registro.registrar_si_es_nueva(clave):
            logger.info("tarea_omitida_por_idempotencia", clave=clave.valor)
            return None
        try:
            return await accion()
        except Exception:
            if ante_una_falla is AnteUnaFalla.LIBERAR:
                await self._liberar_sin_ocultar_el_error(clave)
            raise

    async def _liberar_sin_ocultar_el_error(self, clave: ClaveDeIdempotencia) -> None:
        """Free the key; if the registry itself is down, say so but keep the real error."""
        try:
            await self._registro.liberar(clave)
        except (RedisError, OSError) as error:
            logger.error(
                "liberacion_de_idempotencia_fallida",
                clave=clave.valor,
                causa=type(error).__name__,
            )
