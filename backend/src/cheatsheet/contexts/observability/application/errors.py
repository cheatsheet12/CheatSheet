"""Application-level conditions of the observability context."""

from __future__ import annotations

from uuid import UUID


class RegistroDuplicado(Exception):
    """The occurrence already has an audit record.

    Not a domain error: nothing about the business was violated. It is the expected
    outcome of an at-least-once delivery, and the caller's correct reaction is to do
    nothing and carry on.
    """

    def __init__(self, evento_id: UUID) -> None:
        super().__init__(f"El evento {evento_id} ya fue registrado")
        self.evento_id = evento_id
