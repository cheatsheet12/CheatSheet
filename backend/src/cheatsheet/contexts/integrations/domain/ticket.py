"""The `TicketDeAcceso` aggregate — gap H11, decided by ADR-0004.

**Why an entity the DER does not have.** The DER models the *credential*: what a company
gave us so we can act on its behalf. ARCA adds a second thing on top of it — a short-lived
session derived from that credential — and the two cannot share a row, for three reasons
that are facts about the provider rather than modelling taste:

- a ticket lasts about 12 hours and the credential lasts about two years;
- a ticket is per **service** (invoicing, padrón), so one company holds several at once
  while it has exactly one certificate;
- WSAA **refuses to issue a second ticket while the first is alive**, which makes storing
  it a correctness requirement: a system that throws its ticket away cannot authenticate
  again until the old one expires.

The full reasoning, and the alternatives that were ruled out, live in
[ADR-0004](../../../../../../docs/adr/0004-arca-wsaa-access-tickets.md).

This module knows nothing about ARCA's wire format. A ticket is an opaque blob with a
name and an expiry; what is inside it is the Anti-Corruption Layer's business.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from cheatsheet.contexts.integrations.domain.valores import CredencialCifrada
from cheatsheet.shared.empresa import EmpresaId

#: Default head start before expiry at which a ticket is renewed rather than reused.
#: Not zero, because a ticket that expires between the check and the call ARCA makes with
#: it fails halfway through an operation instead of before it starts.
MARGEN_DE_RENOVACION = timedelta(minutes=30)


class ServicioDeArca(StrEnum):
    """Which ARCA service a ticket authenticates against.

    A closed catalogue rather than a free string, and the reason is the unique index:
    tickets are keyed by `(empresa_id, servicio)`, so a typo would not fail — it would
    quietly mint a second ticket, and ARCA would refuse it because the first is still
    alive.

    `PADRON_A5` is here before its unit needs it (`padron-y-datos-fiscales`, next) because
    the value is part of the storage key, and a catalogue widened later by a unit that has
    no other reason to touch this file is worse than one written once.
    """

    WSFE = "wsfe"
    PADRON_A5 = "ws_sr_padron_a5"


@dataclass(eq=False)
class TicketDeAcceso:
    """One live session with one ARCA service, for one company."""

    id: UUID
    empresa_id: EmpresaId
    servicio: ServicioDeArca
    contenido: CredencialCifrada
    expira_en: datetime

    def vigente(self, ahora: datetime) -> bool:
        """Whether ARCA would still accept it. Says nothing about whether to reuse it."""
        return ahora < self.expira_en

    def hay_que_renovar(self, ahora: datetime, margen: timedelta = MARGEN_DE_RENOVACION) -> bool:
        """Whether to mint a new one instead of handing this one out.

        Separate from `vigente` on purpose: inside the margin a ticket is still valid — so
        a failed renewal can fall back to it — but it is close enough to expiry that an
        operation started now might outlive it.
        """
        return ahora >= self.expira_en - margen

    def reemplazar(self, contenido: CredencialCifrada, expira_en: datetime) -> None:
        """Overwrite in place. One row per `(empresa, servicio)`, as the index states."""
        self.contenido = contenido
        self.expira_en = expira_en


@dataclass(eq=False)
class TicketDePlataforma:
    """One live session of **the platform certificate** with one ARCA service (ADR-0014).

    Not per company: with web service delegation every company is reached through the
    same certificate, and WSAA issues one ticket per certificate and service. A ticket
    kept per company would make the second company to connect fail for twelve hours.
    """

    servicio: ServicioDeArca
    contenido: CredencialCifrada
    expira_en: datetime

    def vigente(self, ahora: datetime) -> bool:
        """Whether ARCA would still accept it."""
        return ahora < self.expira_en

    def hay_que_renovar(self, ahora: datetime, margen: timedelta = MARGEN_DE_RENOVACION) -> bool:
        """Whether to mint a new one instead of handing this one out (see `TicketDeAcceso`)."""
        return ahora >= self.expira_en - margen

    def reemplazar(self, contenido: CredencialCifrada, expira_en: datetime) -> None:
        self.contenido = contenido
        self.expira_en = expira_en
