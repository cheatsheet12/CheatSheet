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
from cheatsheet.contexts.master_data.application.ports import PortPadron as PortPadronDeClientes
from cheatsheet.contexts.master_data.infrastructure.padron import (
    PadronViaIntegraciones as PadronDeClientesViaIntegraciones,
)
from cheatsheet.platform.settings import Settings


def _consultar_padron(unidad: UnidadDeTrabajo, settings: Settings) -> ConsultarPadron:
    """The published operation, built once and wrapped by each consumer's own layer.

    The ticket use case is inside because the lookup may have to mint one, and minting one
    persists it: ARCA refuses a second ticket while the first is alive (ADR-0004), so that
    row has to be written in the same transaction as everything else the request does.
    """
    piezas = Integraciones.armar(unidad.sesion, settings)
    return ConsultarPadron(
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


def armar_padron(unidad: UnidadDeTrabajo, settings: Settings) -> PortPadron:
    """The registry as `identity` sees it. Request-scoped, like the transaction it writes in."""
    return PadronViaIntegraciones(_consultar_padron(unidad, settings))


def armar_padron_de_clientes(unidad: UnidadDeTrabajo, settings: Settings) -> PortPadronDeClientes:
    """The same registry as `master_data` sees it (HU-E4-01 RN-02).

    Two functions and two anti-corruption layers over one operation, which is the shape
    ADR-0003 asks for: `integrations` publishes one contract and knows none of its
    consumers, and each consumer translates it into its own vocabulary. The alternative —
    `master_data` importing `identity`'s adapter — is an edge the Context Map does not
    have and rule R3 would block.
    """
    return PadronDeClientesViaIntegraciones(_consultar_padron(unidad, settings))
