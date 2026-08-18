"""The processing guarantees every async task inherits (ADR-009).

Two mechanisms, both deliberately free of Celery so they can be tested without a
broker — which is also why they are useful to the webhook endpoints, which need the
same guarantee and are not tasks at all.

**Idempotency.** At-least-once delivery is the only thing a queue can promise, so the
same task will run twice. `EjecutorIdempotente` makes the second run a no-op, keyed by
`ClaveDeIdempotencia`. The claim is a single atomic `SET NX` (see `platform/cache.py`)
because two workers can start the same task in the same millisecond.

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
from typing import TypeVar

from cheatsheet.platform.cache import RegistroDeIdempotencia
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.idempotencia import ClaveDeIdempotencia

logger = obtener_logger(__name__)

T = TypeVar("T")

MAX_INTENTOS_POR_DEFECTO = 5
ESPERA_BASE_SEGUNDOS = 2.0
ESPERA_MAXIMA_SEGUNDOS = 600.0


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
        self, clave: ClaveDeIdempotencia, accion: Callable[[], Awaitable[T]]
    ) -> T | None:
        """Run `accion`, or return None if this key was already handled.

        The key is claimed *before* the effect runs. Claiming afterwards would leave a
        window in which a crash between effect and claim lets the retry run it again —
        which for a `Cobro` means charging twice.
        """
        if not await self._registro.registrar_si_es_nueva(clave):
            logger.info("tarea_omitida_por_idempotencia", clave=clave.valor)
            return None
        return await accion()
