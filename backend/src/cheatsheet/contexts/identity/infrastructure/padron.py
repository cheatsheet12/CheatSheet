"""The Anti-Corruption Layer between `identity` and `integrations`.

**This is the only module in this context that imports another one**, and it imports only
its `application/` — which is what ADR-0003 publishes and what rule R3 allows. The Context
Map lists `identity` among the consumers of the `integrations` Open Host Service, so the
edge is one the architecture already permits; what it does not permit is that edge being
everywhere.

Hence a layer of a dozen lines. `CompletarDatosDeEmpresa`, `ConsultarPadronDeCuit` and
`RevalidarDatosFiscales` talk to `PortPadron` and know nothing about tickets, certificates,
SOAP or ARCA. If the registry is ever reached some other way, this file changes and they
do not.

It also translates the failure. `integrations` raises `ConsultaDePadronNoDisponible`, which
is *its* vocabulary; this context sees `PadronNoDisponible`, which is its own. Letting the
provider's exception travel would make every `except` clause upstream an import of another
context.
"""

from __future__ import annotations

from cheatsheet.contexts.identity.application.ports import (
    DatosFiscalesDePadron,
    PadronNoDisponible,
)
from cheatsheet.contexts.integrations.application.errors import ConsultaDePadronNoDisponible
from cheatsheet.contexts.integrations.application.padron import ConsultarPadron
from cheatsheet.shared.empresa import EmpresaId


class PadronViaIntegraciones:
    """Implements `PortPadron` by asking the integrations context."""

    def __init__(self, consulta: ConsultarPadron) -> None:
        self._consulta = consulta

    async def consultar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosFiscalesDePadron | None:
        try:
            datos = await self._consulta.ejecutar(empresa_id=empresa_id, cuit=cuit)
        except ConsultaDePadronNoDisponible as exc:
            raise PadronNoDisponible(str(exc)) from exc
        if datos is None:
            return None
        return DatosFiscalesDePadron(
            razon_social=datos.razon_social,
            condicion_iva=datos.condicion_iva,
            activo=datos.activo,
        )
