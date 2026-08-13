"""Shared Kernel — the identifiers every bounded context speaks in.

`identity` is upstream of all twelve contexts (docs/architecture.md §4) and what flows
from it is exactly this: which company an operation belongs to, and which person
executed it.

**Why `EmpresaId` and not `EmpresaId`.** The DER
(`docs/aidlc/inputs/der.md`) names the isolation column `empresa_id` in all 25
company-scoped tables, and the ubiquitous language of this domain is Spanish
(CLAUDE.md §2.2). Carrying `EmpresaId` in the code and `empresa_id` in the database
would mean translating at every repository — the exact seam where a wrong mapping
hides. One word, everywhere.

They are `NewType`s over `UUID` rather than bare `UUID`s so that passing a
`UsuarioId` where an `EmpresaId` is expected is a type error and not a data leak
discovered in production.
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID

EmpresaId = NewType("EmpresaId", UUID)
UsuarioId = NewType("UsuarioId", UUID)


def empresa_id_desde(valor: str) -> EmpresaId:
    """Parse an `EmpresaId` coming from outside the system (header, token, task payload).

    Raises `ValueError` when the value is not a UUID — the caller decides whether that
    is a 400 or a rejected task, because the domain has no opinion about transports.
    """
    return EmpresaId(UUID(valor))


def usuario_id_desde(valor: str) -> UsuarioId:
    """Parse a `UsuarioId` coming from outside the system. See `empresa_id_desde`."""
    return UsuarioId(UUID(valor))
