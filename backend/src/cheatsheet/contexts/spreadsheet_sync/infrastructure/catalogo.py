"""The adapter that carries a mapped row into `master_data` (HU-E3-03).

This file **is** the Context Map edge `spreadsheet_sync → master_data`, and it is the only
place in this context that names the other one. Rule R3 forbids reaching into
`master_data/domain` or its repositories; going through its application service is what
the edge means, and putting the call here rather than in a use case is what keeps
`spreadsheet_sync/application` from knowing that `master_data` exists at all.

**One row, one decision: customer or service.** The mapping already told us which
vocabulary the columns belong to, so the choice is the caller's and arrives as a flag. It
is not inferred from which fields are present — a row with `nombre` and nothing else would
be ambiguous, and guessing would put a customer in the service catalogue at row 12 000.
"""

from __future__ import annotations

from datetime import datetime

from cheatsheet.contexts.master_data.application.ingesta import (
    FilaDeCatalogo,
    IngerirClienteDesdePlanilla,
    IngerirServicioDesdePlanilla,
)
from cheatsheet.contexts.master_data.application.ports import (
    PortRepositorioCliente,
    PortRepositorioServicio,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import FilaParaIngerir
from cheatsheet.shared.empresa import EmpresaId


class IngestaEnMasterData:
    """`PortIngestaDeCatalogo` implemented against `master_data`'s application layer."""

    def __init__(
        self,
        *,
        clientes: PortRepositorioCliente,
        servicios: PortRepositorioServicio,
        para_servicios: bool = False,
    ) -> None:
        self._clientes = IngerirClienteDesdePlanilla(clientes)
        self._servicios = IngerirServicioDesdePlanilla(servicios)
        self._para_servicios = para_servicios

    async def ingerir(
        self, *, empresa_id: EmpresaId, fila: FilaParaIngerir, ahora: datetime
    ) -> None:
        datos = FilaDeCatalogo(
            nombre=fila.valores.get("nombre"),
            cuit=fila.valores.get("cuit"),
            condicion_iva=fila.valores.get("condicion_iva"),
            contacto_whatsapp=fila.valores.get("contacto_whatsapp"),
            contacto_email=fila.valores.get("contacto_email"),
            precio=fila.valores.get("precio"),
            alicuota_iva=fila.valores.get("alicuota_iva"),
            agendable=fila.valores.get("agendable"),
            duracion_estandar_min=fila.valores.get("duracion_estandar_min"),
        )
        if self._para_servicios:
            await self._servicios.ejecutar(empresa_id=empresa_id, fila=datos, ahora=ahora)
        else:
            await self._clientes.ejecutar(empresa_id=empresa_id, fila=datos, ahora=ahora)
