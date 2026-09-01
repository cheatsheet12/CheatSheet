"""The Anti-Corruption Layer between `master_data` and `integrations`.

**This is the only module in this context that imports another one**, and it imports only
its `application/` — which is what [ADR-0003](../../../../../docs/adr/0003-integrations-open-host-service.md)
publishes and what rule R3 allows. `integrations` is an Open Host Service that any context
may call; `master_data` is the sixth consumer, and epic 3 is what added it to the row in
`docs/architecture.md` §4.

Hence a layer of a dozen lines, identical in shape to the one `identity` wrote for the
same purpose. Duplicated rather than shared, deliberately: sharing it would mean one
context importing another's adapter, which is exactly the edge the layer exists to keep
from spreading.

It also translates the failure. `integrations` raises `ConsultaDePadronNoDisponible`,
which is *its* vocabulary; this context sees `PadronNoDisponible`, which is its own.
Letting the provider's exception travel would turn every `except` upstream into an import
of another context.
"""

from __future__ import annotations

from cheatsheet.contexts.integrations.application.errors import ConsultaDePadronNoDisponible
from cheatsheet.contexts.integrations.application.padron import ConsultarPadron
from cheatsheet.contexts.master_data.application.ports import (
    DatosFiscalesDePadron,
    PadronNoDisponible,
)
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
