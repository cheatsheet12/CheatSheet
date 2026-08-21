"""Where `identity` is handed its view of ARCA's registry.

The one place two contexts meet, and it is on purpose the composition root: `identity` may
call what `integrations` publishes (ADR-0003, Context Map §4), but neither context's
`infrastructure/` may reach into the other's — rule R3, enforced by
`guard_architecture.py`. So the assembly happens here, above both of them.

It lives in its own module rather than in `dependencies.py` because that one is imported by
each context's `ensamblado.py`; putting these imports there would close a cycle.
"""

from __future__ import annotations

from datetime import timedelta

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.identity.application.ports import PortPadron
from cheatsheet.contexts.identity.infrastructure.padron import PadronViaIntegraciones
from cheatsheet.contexts.integrations.application.padron import ConsultarPadron
from cheatsheet.contexts.integrations.application.tickets import ObtenerTicketDeAcceso
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
from cheatsheet.platform.settings import Settings


def armar_padron(unidad: UnidadDeTrabajo, settings: Settings) -> PortPadron:
    """Request-scoped, like everything that writes through the caller's transaction.

    The ticket use case is inside because the lookup may have to mint one, and minting one
    persists it: ARCA refuses a second ticket while the first is alive (ADR-0004), so that
    row has to be written in the same transaction as everything else the request does.
    """
    piezas = Integraciones.armar(unidad.sesion, settings)
    return PadronViaIntegraciones(
        ConsultarPadron(
            tickets=ObtenerTicketDeAcceso(
                integraciones=piezas.integraciones,
                tickets=piezas.tickets,
                cifrado=piezas.cifrado,
                adaptadores=piezas.adaptadores,
                reloj=unidad.reloj,
                margen=timedelta(minutes=settings.arca_margen_renovacion_minutos),
            ),
            integraciones=piezas.integraciones,
            adaptadores=piezas.adaptadores,
        )
    )
