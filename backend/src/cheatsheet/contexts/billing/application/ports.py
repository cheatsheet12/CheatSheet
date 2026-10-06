"""Ports of `billing`.

What each one refuses is where the guarantees are.

`PortRepositorioPuntoDeVenta` offers `tomar_para_emitir`, which is not a read: it locks the
row (decision D14). A repository that only offered `buscar_por_id` would be a repository
whose callers race each other for a fiscal number.

**Nothing here has `eliminar`.** A point of sale that issued documents cannot be removed
without orphaning them, and a `Comprobante` with a CAE is a legal record. `desactivar` is
what HU-E5-05 RN-04 asks for and it is all that exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.billing.domain.comprobante import CAE, Comprobante, EstadoComprobante
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.fiscal import CondicionIVA


@dataclass(frozen=True, slots=True)
class PuntoHabilitado:
    """One point of sale as ARCA reports it (HU-E5-05 RN-03)."""

    numero: int
    #: ARCA reports points it knows about; a blocked one is reported and unusable.
    bloqueado: bool = False

    @property
    def puede_usarse(self) -> bool:
        return not self.bloqueado


class PortRepositorioPuntoDeVenta(Protocol):
    """Persistence of points of sale, always inside one company.

    No `empresa_id` parameter: every statement runs in a session with `app.current_empresa`
    set and the RLS policy filters. Passing it as well would suggest the barrier is this
    port's responsibility, and the day somebody forgot to pass it would be the day the
    barrier was gone.
    """

    async def agregar(self, punto: PuntoDeVenta) -> None:
        """Raises `PuntoDeVentaDuplicado` from the unique index, which is the only check
        that cannot lose a race with a second tab."""
        ...

    async def guardar(self, punto: PuntoDeVenta) -> None: ...

    async def buscar_por_id(self, punto_id: UUID) -> PuntoDeVenta | None: ...

    async def listar(self) -> list[PuntoDeVenta]: ...

    async def tomar_para_emitir(self, punto_id: UUID) -> PuntoDeVenta | None:
        """The same row as `buscar_por_id`, **locked until the transaction ends** (D14).

        This is what makes the numbering a sequence rather than a suggestion. Two
        simultaneous issues on the same point serialise here; without it they both read
        the same counter and draw the same number, which ARCA either rejects or -- worse --
        authorises twice.
        """
        ...


class PortHabilitacionDeArca(Protocol):
    """`FEParamGetPtosVenta`: which points of sale ARCA knows about (RN-03)."""

    async def puntos_habilitados(self, *, empresa_id: EmpresaId) -> tuple[PuntoHabilitado, ...]:
        """Raises `ArcaNoDisponible` when ARCA cannot be reached.

        The distinction matters to the caller: «ARCA says this point is not yours» blocks
        the activation for good, and «we could not ask» is worth trying again in a minute.
        """
        ...


# --------------------------------------------------------------------- comprobantes


@dataclass(frozen=True, slots=True)
class FiltrosDeComprobante:
    """HU-E5-01 RN-02. Every field optional; absent means "do not filter by this".

    Lives in the application layer and not in `domain/`, for the reason epic 4 learned the
    hard way when the architecture guard caught the same shape: a filter is a request from
    the outside, not a concept the aggregate knows about.
    """

    desde: date | None = None
    hasta: date | None = None
    tipos: tuple[TipoComprobante, ...] = ()
    estados: tuple[EstadoComprobante, ...] = ()


@dataclass(frozen=True, slots=True)
class DatosDelReceptor:
    """What the padrón answered about the receptor (HU-E5-03 RN-02).

    `condicion_iva` may be absent: ARCA's registry is uneven, and inventing one here would
    decide which type of document may be issued. The use case refuses instead.
    """

    cuit: str
    razon_social: str | None
    condicion_iva: CondicionIVA | None
    activo: bool


@dataclass(frozen=True, slots=True)
class RespuestaDeArca:
    """What `FECAESolicitar` answered, translated out of ARCA's vocabulary.

    **`autorizado=False` with a code means ARCA said no.** Not being able to reach ARCA is
    not represented here at all: that raises `ArcaNoDisponible`, and collapsing the two
    would turn an outage into a rejected document.
    """

    autorizado: bool
    cae: CAE | None = None
    codigo: str | None = None
    descripcion: str | None = None


class PortRepositorioComprobante(Protocol):
    """Persistence of documents, always inside one company (RLS, HU-E5-01 RN-01).

    **No `eliminar`.** A document with a CAE is a legal record; it is reversed with a
    credit note, never removed.
    """

    async def agregar(self, comprobante: Comprobante) -> None: ...

    async def guardar(self, comprobante: Comprobante) -> None: ...

    async def buscar_por_id(self, comprobante_id: UUID) -> Comprobante | None: ...

    async def listar(self, filtros: FiltrosDeComprobante) -> list[Comprobante]:
        """Ordered by `fecha_emision` descending (RN-03), with drafts last: they have no
        issue date, and sorting them by creation keeps them from floating to the top."""
        ...

    async def notas_de(self, origen_id: UUID) -> list[Comprobante]:
        """Every credit note issued against one document (HU-E5-04 RN-03, RN-05).

        All of them, in every state, because the caller decides what counts: only the
        authorised ones reverse anything (decision D19), and a filter here would hide the
        rejected and in-flight ones from a screen that has reason to show them.
        """
        ...

    async def en_vuelo(self, *, anteriores_a: datetime) -> list[Comprobante]:
        """Documents stuck in `ENVIADO_A_ARCA`, for the reconciliation of D17.

        Takes a cutoff so a document sent two seconds ago -- still legitimately in
        flight -- is not reconciled out from under the task that is awaiting it.
        """
        ...


class PortAutorizacionDeArca(Protocol):
    """WSFEv1's two operations that matter, behind an ACL (ADR-0008).

    The pair is not arbitrary: **`consultar` is what makes `solicitar` safe to retry**.
    A client that offered only `solicitar` would force its callers to choose between
    losing a document and issuing it twice (decision D17).
    """

    async def solicitar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca:
        """`FECAESolicitar`. Raises `ArcaNoDisponible` when the answer never came --
        which says nothing about whether ARCA authorised it."""
        ...

    async def ultimo_autorizado(
        self, *, empresa_id: EmpresaId, punto: PuntoDeVenta, tipo: TipoComprobante
    ) -> int:
        """`FECompUltimoAutorizado`. Zero when nothing has been authorised yet.

        **Decision D18.** WSFEv1 demands strictly correlative numbering and rejects
        anything else until the two counters agree, so ARCA -- not us -- is the authority
        on where the sequence is. Asked before every issue, inside the point of sale's
        lock.
        """
        ...

    async def consultar(
        self, *, empresa_id: EmpresaId, comprobante: Comprobante
    ) -> RespuestaDeArca | None:
        """`FECompConsultar`. `None` means ARCA has no record of this number.

        That is the answer decision D17 turns on: no record means it was never authorised
        and may be sent again; a record means it *was*, and sending again would issue a
        second document for one sale.
        """
        ...


class PortValidacionDeReceptor(Protocol):
    """The padrón lookup of HU-E5-03 RN-02, reached through `integrations`.

    Returns `None` when ARCA's registry does not know the tax id — «No se encontró el CUIT
    en el padrón de ARCA.» **Never** `None` for an outage: that raises, and the difference
    is what stops a bad afternoon at ARCA from blocking a legitimate sale with a message
    that blames the customer's CUIT.
    """

    async def validar(self, *, empresa_id: EmpresaId, cuit: str) -> DatosDelReceptor | None: ...


class PortDatosDelEmisor(Protocol):
    """The issuing company's own VAT condition, reached through `identity`.

    One method and one fact, because that is the only thing `billing` needs from the other
    context: it plus the receptor's condition decides which types are legal (RN-01, D16).
    Raises rather than returning `None` when the company has no condition loaded — for
    invoicing that is a hard stop, not a missing field.
    """

    async def condicion_iva(self, *, empresa_id: EmpresaId) -> CondicionIVA: ...


class PortColaDeEmision(Protocol):
    """Hands the authorisation off to a worker (HU-E5-03 RN-04).

    Takes only the id. The document is already persisted in `ENVIADO_A_ARCA` before this
    is called, so the worker reads the truth from the database rather than from a payload
    that may be stale by the time it runs.
    """

    async def encolar(self, *, empresa_id: EmpresaId, comprobante_id: UUID) -> None: ...


#: `EstadoComprobante` y `TipoComprobante` se reexportan a propósito, como `master_data` hizo
#: con `OrigenDato` en el épico 8: son tipos de **argumento** de `FiltrosDeComprobante`, y un
#: tipo de argumento que nadie de afuera puede nombrar es un argumento que nadie puede pasar.
#: Reexportarlos acá le permite a `reporting` filtrar por estado sin tocar este `domain/` (R3).
__all__ = [
    "DatosDelReceptor",
    "EstadoComprobante",
    "FiltrosDeComprobante",
    "PortAutorizacionDeArca",
    "PortColaDeEmision",
    "PortDatosDelEmisor",
    "PortHabilitacionDeArca",
    "PortRepositorioComprobante",
    "PortRepositorioPuntoDeVenta",
    "PortValidacionDeReceptor",
    "PuntoHabilitado",
    "RespuestaDeArca",
    "TipoComprobante",
]
