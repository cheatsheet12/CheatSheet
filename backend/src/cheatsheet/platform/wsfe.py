"""What a WSFEv1 call needs in its `<Auth>`, and who can produce it.

Two contexts talk to WSFEv1 — `billing` issues documents and `reference_data` reads
catalogues — and both need the same credential. Rule R3 forbids either one importing the
other's `infrastructure/`, so the contract lives here, in `platform/`, which is where
`CLAUDE.md` §2 puts the infrastructure every layer shares.

It is the same move the previous unit made with `soap.py`, and for the same reason: the
alternative was two copies of one contract, which is two things that can drift.

**Only the contract lives here.** The implementation resolves a ticket through
`integrations`, which makes it a wiring of two contexts, and that belongs in the
composition root — `api/arca.py`. Nothing in `platform/` imports a bounded context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId


@dataclass(frozen=True, slots=True)
class CredencialDeWsfe:
    """The three values every WSFEv1 envelope carries in its `<Auth>` block.

    The token and the sign come from a WSAA ticket that lasts about twelve hours; the CUIT
    is the one extracted from the company's certificate when it connected. Carried together
    because a call with two of the three is a call ARCA refuses.
    """

    token: str
    sign: str
    cuit: str


class PortCredencialesDeWsfe(Protocol):
    """What the WSFEv1 adapters ask for, so they never learn about `integrations`.

    Asynchronous because resolving one may have to mint a ticket, which is a network call
    and a database write. An adapter that took a plain dict — which is what the first two
    units of this epic did while this piece was pending — cannot express that.
    """

    async def para(self, empresa_id: EmpresaId) -> CredencialDeWsfe:
        """Raises the caller's own "cannot reach ARCA" error when there is no usable
        credential. From the caller's point of view «the certificate is not loaded», «the
        ticket expired» and «WSAA is down» are one fact: we cannot ask ARCA right now."""
        ...

    async def numero_de_punto(self, empresa_id: EmpresaId, punto_id: UUID) -> int | None:
        """ARCA identifies a point of sale by its **number**, never by our UUID."""
        ...


__all__ = ["CredencialDeWsfe", "PortCredencialesDeWsfe"]
