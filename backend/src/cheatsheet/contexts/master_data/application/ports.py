"""The ports of the master data context: what its use cases need from the outside.

A repository per aggregate, a door to ARCA's registry — which only `Cliente` needs,
because a service has no tax id to look up — and one port for the classification links.

**`PortClasificaciones` is its own port and not two more methods on the client and service
repositories**, because the link belongs to neither aggregate. It is a relation between
two of them, and giving it to one would make that one the owner of something it does not
own.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.master_data.domain.categoria import CategoriaEmpresa
from cheatsheet.contexts.master_data.domain.cliente import Cliente, FiltrosDeCliente, Pagina
from cheatsheet.contexts.master_data.domain.servicio import FiltrosDeServicio, Servicio
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
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


class PortRepositorioCategoria(Protocol):
    """Persistence of `CategoriaEmpresa`, always inside one company.

    **This one has `eliminar`**, unlike the other two repositories of this context. RN-03
    of HU-E4-03 asks for it, and nothing outside `master_data` references a category: the
    only rows that point at it are the two link tables, with a real foreign key and
    `ON DELETE CASCADE`. See the unit plan for why the asymmetry is deliberate.
    """

    async def agregar(self, categoria: CategoriaEmpresa) -> None: ...

    async def guardar(self, categoria: CategoriaEmpresa) -> None: ...

    async def eliminar(self, categoria_id: UUID) -> None:
        """Removing one that is not there is not an error: the end state is the same."""
        ...

    async def buscar_por_id(self, categoria_id: UUID) -> CategoriaEmpresa | None: ...

    async def buscar_por_nombre_y_ambito(
        self, *, nombre: str, aplica_a: AmbitoDeCategoria
    ) -> CategoriaEmpresa | None:
        """Names the duplicate for RN-02's message. Compares case-insensitively."""
        ...

    async def listar(
        self, *, empresa_id: EmpresaId, aplica_a: AmbitoDeCategoria | None = None
    ) -> Sequence[CategoriaEmpresa]:
        """No paging: a company's own labels are a short list, and the screen shows it whole.

        `aplica_a` filters by *usability*, not by equality — asking for `CLIENTE` returns
        the `AMBOS` ones too, because those are assignable to a client. That is what the
        form's dropdown needs, and doing it here keeps HU-E4-04 RN-01 out of the UI.
        """
        ...


class PortClasificaciones(Protocol):
    """The links between elements and categories.

    Every operation is idempotent, in both directions: assigning twice leaves one row and
    removing something that was never there is not an error. HU-E4-04 RN-03 describes the
    assignment as immediate and without historical effects, and under that reading a
    repeated click is not a business failure.
    """

    async def asignar_a_cliente(self, *, cliente_id: UUID, categoria_id: UUID) -> None: ...

    async def quitar_de_cliente(self, *, cliente_id: UUID, categoria_id: UUID) -> None: ...

    async def categorias_de_cliente(self, cliente_id: UUID) -> Sequence[CategoriaEmpresa]: ...

    async def asignar_a_servicio(self, *, servicio_id: UUID, categoria_id: UUID) -> None: ...

    async def quitar_de_servicio(self, *, servicio_id: UUID, categoria_id: UUID) -> None: ...

    async def categorias_de_servicio(self, servicio_id: UUID) -> Sequence[CategoriaEmpresa]: ...
