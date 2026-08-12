"""Shared Kernel — the identifiers every bounded context speaks in.

`identity` is upstream of all twelve contexts (docs/architecture.md §4) and what
flows from it is exactly this: which company an operation belongs to, and which
person executed it. They are `NewType`s over `UUID` rather than bare `UUID`s so
that passing a `UserId` where a `TenantId` is expected is a type error and not a
data leak discovered in production.
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID

TenantId = NewType("TenantId", UUID)
UserId = NewType("UserId", UUID)


def tenant_id_desde(valor: str) -> TenantId:
    """Parse a `TenantId` coming from outside the system (header, token, task payload).

    Raises `ValueError` when the value is not a UUID — the caller decides whether that
    is a 400 or a rejected task, because the domain has no opinion about transports.
    """
    return TenantId(UUID(valor))


def user_id_desde(valor: str) -> UserId:
    """Parse a `UserId` coming from outside the system. See `tenant_id_desde`."""
    return UserId(UUID(valor))
