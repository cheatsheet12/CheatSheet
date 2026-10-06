"""The adapter that turns published events into audit records.

This is the *only* place in the system where the audit sink is attached to the rest.
Nine epics' worth of contexts will emit `EventoAuditable` without ever naming
`observability`, and the wiring happens once, in the composition root.

Events that are not auditable pass through untouched. That is not defensiveness: the
same publisher will carry `PagoConfirmado` to `billing` and `TurnoReservado` to the
notification worker, and this subscriber has no opinion about them.
"""

from __future__ import annotations

from cheatsheet.contexts.observability.application.registrar_operacion import RegistrarOperacion
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.auditoria import EventoAuditable
from cheatsheet.shared.events import EventoDeDominio

logger = obtener_logger(__name__)


class SuscriptorDeAuditoria:
    """Implements `SuscriptorDeEventos` for `EventoAuditable`."""

    def __init__(self, registrar: RegistrarOperacion) -> None:
        self._registrar = registrar

    async def manejar(self, evento: EventoDeDominio) -> None:
        if not isinstance(evento, EventoAuditable):
            return
        resultado = await self._registrar.ejecutar(evento)
        if not resultado.fue_creado:
            logger.info(
                "auditoria_evento_redelivered",
                evento_id=str(evento.evento_id),
                registro_id=str(resultado.registro_id),
            )
