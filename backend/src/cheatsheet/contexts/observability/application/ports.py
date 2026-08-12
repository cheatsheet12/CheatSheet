"""Ports of the observability context.

Note what is **not** here. There is no `actualizar` and no `eliminar`: HS-T5 RN-03
makes audit records immutable, and the cheapest place to enforce that is the shape of
the interface. A repository that cannot express deletion cannot be talked into it by
a future caller in a hurry.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.observability.domain.registro_de_auditoria import RegistroDeAuditoria


class PortRegistroDeAuditoria(Protocol):
    """Persistence of the audit log. Append and read; nothing else exists."""

    async def agregar(self, registro: RegistroDeAuditoria) -> None:
        """Persist a new record.

        Raises `RegistroDuplicado` when `evento_id` is already stored, so that a
        redelivery is a detectable condition rather than a second row.
        """
        ...

    async def buscar_por_evento(self, evento_id: UUID) -> RegistroDeAuditoria | None:
        """The record produced by an occurrence, if it was already registered."""
        ...

    async def buscar_por_id(self, registro_id: UUID) -> RegistroDeAuditoria | None: ...
