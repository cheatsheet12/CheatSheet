"""The in-process event publisher that wires the contexts together.

The monolith is modular, not distributed (ADR-001): an event does not need a broker
to reach a subscriber in the same process. What it does need is that the emitter
never learns who is listening — that is the whole point of the indirection, and the
reason `billing` can be extracted into its own service later without touching the
code that emits.

**Delivery is synchronous and inside the caller's transaction.** For the audit sink
that is deliberate (see `observability/infrastructure/subscriber.py`): an audit row
written in a different transaction than the operation it describes can survive
without it, or be lost while it survives. Both are worse than the coupling.

A subscriber that raises therefore fails the operation. That is correct for auditing
— HS-T5 makes the record a requirement, not a side effect — and it is why this
publisher does not swallow exceptions. When a future subscriber wants at-most-effort
delivery, it enqueues its own task and returns.
"""

from __future__ import annotations

from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.events import EventoDeDominio, SuscriptorDeEventos

logger = obtener_logger(__name__)


class PublicadorEnProceso:
    """Fans an event out to every subscriber registered at the composition root."""

    def __init__(self) -> None:
        self._suscriptores: list[SuscriptorDeEventos] = []

    def suscribir(self, suscriptor: SuscriptorDeEventos) -> None:
        self._suscriptores.append(suscriptor)

    async def publicar(self, evento: EventoDeDominio) -> None:
        for suscriptor in self._suscriptores:
            await suscriptor.manejar(evento)
        logger.debug(
            "evento_publicado",
            evento=type(evento).__name__,
            evento_id=str(evento.evento_id),
            suscriptores=len(self._suscriptores),
        )
