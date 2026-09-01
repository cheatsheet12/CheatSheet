"""Value objects of the master data context.

Small on purpose. Most of what a `Cliente` is made of — `CUIT`, `CondicionIVA`, `Email`,
`Telefono` — is Shared Kernel vocabulary, because `identity` creates the first one of
each and `billing`, `payments` and `conversational` will read them next. What is left
here is what only this context defines: where a record came from.
"""

from __future__ import annotations

from enum import StrEnum


class OrigenDato(StrEnum):
    """DER enum `origen_dato`. Which door a master record came in through.

    **Assigned by the system and never editable** (HU-E4-01 RN-01). It is not a
    preference: ADR-006 and ADR-007 make decisions based on it — the company's
    spreadsheet is authoritative over what it owns, and what disappears from it is marked
    absent rather than deleted. A record whose origin could be edited would be a record
    that could be moved out from under those rules by hand.

    `PLANILLA` and `AGENTE` have no writer yet — epic 4 and epic 8 respectively. The
    enum is complete from the start anyway, because the column that stores it is, and a
    catalogue that grows one deploy at a time is a catalogue nobody can filter on.
    """

    PLANILLA = "PLANILLA"
    PANEL = "PANEL"
    AGENTE = "AGENTE"
