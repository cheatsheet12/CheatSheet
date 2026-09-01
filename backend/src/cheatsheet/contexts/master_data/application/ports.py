"""The ports of the master data context: what its use cases need from the outside.

Three, and no more. A repository per aggregate, and a door to ARCA's registry — which
only `Cliente` needs, because a service has no tax id to look up.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.servicio import FiltrosDeServicio, Servicio
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA


@dataclass(frozen=True, slots=True)
class DatosFiscalesDePadron:
    """What ARCA's registry says about a tax id, in this context's own words.

    A DTO of `master_data`, and identical today to the one `identity` declares. That
    duplication is the Anti-Corruption Layer doing its job rather than an oversight:
    sharing the dataclass would mean one context importing another's `application/` for
    no reason the Context Map sanctions, and the two would then be unable to evolve
    apart — `master_data` will want the trade name a client invoices under long before
    `identity` has any use for it.
    """

    razon_social: str | None
    condicion_iva: CondicionIVA | None
    #: `False` when the tax id exists but is deregistered. Worth showing; not a reason to
    #: refuse the client.
    activo: bool


class PadronNoDisponible(RuntimeError):
    """The registry could not be asked. Never means "that tax id does not exist".

    Not an `ErrorDeDominio`: no business rule was broken, an external system was
    unreachable — or, most often in this context, was never connected in the first place.
    ARCA is optional (epic 2) and a company that has not configured it still has to be
    able to load its customers.
    """


class PortPadron(Protocol):
    """Asks ARCA's registry about one tax id, on behalf of one company.

    Three outcomes, and the implementation must keep them apart:

    - the data, when the registry knows the tax id;
    - `None`, when it does not — which blocks the save (HU-E4-01 RN-02);
    - `PadronNoDisponible`, when it could not be asked — which must not.
    """

    async def consultar(
        self, *, empresa_id: EmpresaId, cuit: str
    ) -> DatosFiscalesDePadron | None: ...


class PortRepositorioCliente(Protocol):
    """Persistence of `Cliente`, always inside one company.

    Nothing here takes an `empresa_id` except the queries that list or search, and that
    is not an oversight: every statement runs in a session with `app.current_empresa`
    set, and the RLS policy filters. Passing the company id to `buscar_por_id` as well
    would suggest the barrier is this port's responsibility, and the day somebody forgets
    to pass it would be the day the barrier is gone.
    """

    async def agregar(self, cliente: Cliente) -> None:
        """Raises `ClienteDuplicado` when the CUIT is already taken in this company."""
        ...

    async def guardar(self, cliente: Cliente) -> None:
        """Raises `ClienteDuplicado` for the same reason `agregar` does."""
        ...

    async def buscar_por_id(self, cliente_id: UUID) -> Cliente | None: ...

    async def buscar_por_cuit(self, cuit: str) -> Cliente | None:
        """Used to name the duplicate, never to prevent it — that is the index's job."""
        ...

    async def listar(
        self, *, empresa_id: EmpresaId, filtros: FiltrosDeCliente, pagina: Pagina
    ) -> tuple[Sequence[Cliente], int]:
        """One page and the total that matches the filters, in that order."""
        ...


class PortRepositorioServicio(Protocol):
    """Persistence of `Servicio`, always inside one company.

    Same arrangement as `PortRepositorioCliente`, and for the same reason: the company
    filter is the RLS policy, not a parameter somebody could forget to pass.

    **No `buscar_por_nombre`.** Services have no uniqueness rule — two branches may both
    sell a "Corte" — so there is nothing to look up before writing.
    """

    async def agregar(self, servicio: Servicio) -> None: ...

    async def guardar(self, servicio: Servicio) -> None: ...

    async def buscar_por_id(self, servicio_id: UUID) -> Servicio | None: ...

    async def listar(
        self, *, empresa_id: EmpresaId, filtros: FiltrosDeServicio, pagina: Pagina
    ) -> tuple[Sequence[Servicio], int]:
        """One page and the total that matches the filters, in that order."""
        ...
