"""Shared Kernel — the root of the domain error hierarchy.

`api/errors.py` has to turn a broken invariant into an HTTP response without
importing any context's `domain/` (rule R3). It can only do that if every context
raises something it is allowed to know about, and this is that something.

Each context subclasses these in its own `domain/`. The API never catches
`Exception`: CLAUDE.md §5 forbids it and ruff (BLE) blocks it.
"""

from __future__ import annotations


class ErrorDeDominio(Exception):
    """A business rule was violated. Never the result of a bug or an outage."""


class InvarianteViolada(ErrorDeDominio):
    """An aggregate was asked to enter a state its own rules forbid.

    Example: removing the Administrador role from the last active Administrador
    (HU-E1-05 RN-02).
    """


class EntradaInvalida(ErrorDeDominio):
    """A value does not satisfy the domain's own definition of well-formed.

    Example: a CUIT whose check digit does not match. Distinct from a schema error:
    the shape was right, the meaning was not.
    """


class OperacionNoPermitida(ErrorDeDominio):
    """The actor may not perform this operation on this aggregate."""
