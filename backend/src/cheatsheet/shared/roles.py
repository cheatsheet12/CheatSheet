"""Shared Kernel — who is executing an operation.

`RolUsuario` was born in `identity/domain/valores.py`, which is where the DER enum
`rol_usuario` belongs and where the three roles are created. It moved here the moment a
second context needed to authorize.

**Why the move rather than an import.** `integrations` has to refuse a connection request
from an Operador (HU-E2-05 gives that role read access and nothing more). Reaching into
`identity/domain/` for the enum breaks rule R3, and depending on `identity` at all
contradicts [ADR-0003](../../../../docs/adr/0003-integrations-open-host-service.md), which
declares `integrations` an Open Host Service that imports from no context. A role is a
cross-context value object — the middleware puts it on the request, every context that
guards an operation reads it — and CLAUDE.md §2 says that is exactly what the Shared
Kernel holds.

`identity/domain/valores.py` re-exports it, so every existing import keeps working and
`identity` remains the context that *owns* the concept. R4 holds: this module imports
nothing from `contexts/`.
"""

from __future__ import annotations

from enum import StrEnum


class RolUsuario(StrEnum):
    """DER enum `rol_usuario`. Closed catalogue — HU-E1-04 RN-01: not configurable."""

    ADMINISTRADOR = "ADMINISTRADOR"
    OPERADOR = "OPERADOR"
    SOLO_LECTURA = "SOLO_LECTURA"
