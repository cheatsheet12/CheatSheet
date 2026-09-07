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
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.shared.empresa import EmpresaId


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


__all__ = [
    "PortHabilitacionDeArca",
    "PortRepositorioPuntoDeVenta",
    "PuntoHabilitado",
    "TipoComprobante",
]
