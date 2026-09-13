"""How an access ticket travels once it leaves this context.

`TicketVigente.contenido` is `token` and `sign` in one blob, two lines. That format used to
live in `infrastructure/arca/wsaa.py`, next to the code that produces it, which was the
right place while `integrations` was its only reader.

It stopped being right when `billing` needed to read one: rule R3 forbids reaching into
another context's `infrastructure/`, and the Open Host Service's contract is exactly the
kind of thing that belongs in `application/` (ADR-0003). Moving it here rather than
duplicating it keeps the two halves of one format in one place, which is the property the
original docstring was defending.

`wsaa.py` re-exports both names, so its existing callers did not change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible

#: One blob, two lines.
SEPARADOR = "\n"


@dataclass(frozen=True, slots=True)
class TicketDeArca:
    """What `loginTicketResponse` carries: the two values every later call needs."""

    token: str
    sign: str
    expira_en: datetime


def empaquetar(ticket: TicketDeArca) -> bytes:
    """The token and the sign together, because every later call needs both.

    A pair split across two columns is a pair that eventually disagrees.
    """
    return f"{ticket.token}{SEPARADOR}{ticket.sign}".encode()


def desempaquetar(contenido: bytes) -> tuple[str, str]:
    """Read back what `empaquetar` wrote. Raises when the stored blob is not a pair."""
    partes = contenido.decode("utf-8", errors="replace").split(SEPARADOR)
    if len(partes) != 2 or not partes[0] or not partes[1]:
        raise ProveedorNoDisponible("El ticket de acceso guardado no tiene token y firma")
    return partes[0], partes[1]


__all__ = ["SEPARADOR", "TicketDeArca", "desempaquetar", "empaquetar"]
