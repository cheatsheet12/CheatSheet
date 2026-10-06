"""Ports of `reference_data`.

Two, and what each refuses is where the guarantees are.

`PortRepositorioParametros` has **no `eliminar`**. The table is the history of what ARCA's
catalogue said and when; deleting a row makes a document issued under it unexplainable.
Superseding a value is `cerrar`, which keeps both.

`PortCatalogosFiscales` is the Anti-Corruption Layer against WSFEv1 (ADR-0008). The
application sees `EntradaDeCatalogo` and never a SOAP body.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from cheatsheet.contexts.reference_data.domain.parametro import (
    ParametroFiscal,
    TipoCatalogoFiscal,
)
from cheatsheet.shared.empresa import EmpresaId


@dataclass(frozen=True, slots=True)
class EntradaDeCatalogo:
    """One catalogue row as ARCA hands it over, before it becomes a versioned parameter.

    No dates: WSFEv1's `FEParamGet*` answers with what is in force *now* and says nothing
    about since when. The validity range is ours to assign, from the day we saw it — which
    is why a sync that never ran leaves a gap the queries can see, rather than a wrong
    range nobody can.
    """

    tipo: TipoCatalogoFiscal
    codigo: str
    valor: str


class PortRepositorioParametros(Protocol):
    """Persistence of the fiscal catalogue. Append and close; never delete."""

    async def agregar(self, parametro: ParametroFiscal) -> None: ...

    async def cerrar(self, parametro: ParametroFiscal) -> None:
        """Persist a closed validity range. The row keeps its id (RN-02)."""
        ...

    async def vigentes(self, *, tipo: TipoCatalogoFiscal | None = None) -> list[ParametroFiscal]:
        """Everything with no `fecha_hasta`, optionally of one catalogue."""
        ...

    async def buscar_vigente_a(
        self, *, tipo: TipoCatalogoFiscal, codigo: str, fecha: date
    ) -> ParametroFiscal | None:
        """The version in force on `fecha` — never «today» (RN-03)."""
        ...


class PortCatalogosFiscales(Protocol):
    """WSFEv1's `FEParamGet*` operations, behind an ACL (ADR-0008).

    Takes the company whose ticket authenticates the call. **The catalogue that comes back
    is not the company's**: it is ARCA's, identical for everyone, and the company only
    supplies the credential that lets us ask. That asymmetry is why the sync can run for
    any one company and store the result for all of them.
    """

    async def obtener(self, *, empresa_id: EmpresaId) -> tuple[EntradaDeCatalogo, ...]:
        """Every catalogue, in one round of calls.

        Raises when ARCA cannot be reached, which HS-T4 RN-04 turns into «keep the last
        one and log the error» rather than an empty catalogue.
        """
        ...
