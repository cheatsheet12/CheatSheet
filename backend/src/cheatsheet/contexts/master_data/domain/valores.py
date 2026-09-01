"""Value objects of the master data context.

Small on purpose. Most of what a `Cliente` is made of — `CUIT`, `CondicionIVA`, `Email`,
`Telefono` — is Shared Kernel vocabulary, because `identity` creates the first one of
each and `billing`, `payments` and `conversational` will read them next. What is left
here is what only this context defines: where a record came from, and what a service
charges VAT at.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from cheatsheet.shared.errors import EntradaInvalida


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


class AlicuotaIVA(StrEnum):
    """The VAT rate of a service. Closed catalogue of three (HU-E4-02 RN-02).

    **The member's value is the rate itself, as a string**, and that is deliberate on two
    counts. The DER stores `servicio.alicuota_iva` as `decimal`, so persisting the number
    rather than a name keeps the column exactly as declared; and building the `Decimal`
    from `self.value` builds it from a string, which is the rule `code-standards` §2.5
    states and the one a float literal would break invisibly.

    **Why an enum here and not a row in `parametro_fiscal`.** That table is `reference_data`'s,
    it is versioned by date range, and it answers a question this screen never asks — *which
    rate was in force the day the document was issued*. That question belongs to issuance,
    which is epic 5. `reference_data` has no code yet, and the Context Map does not let
    `master_data` reach it. See this unit's plan for the full reasoning, including what
    epic 5 inherits: a `Comprobante` denormalises its own rate and validates *that* copy
    against the effective parameter — it does not read this one.
    """

    CERO = "0.00"
    REDUCIDA = "0.105"
    GENERAL = "0.21"

    @property
    def tasa(self) -> Decimal:
        """The rate as a number, for whoever has to multiply by it. Never this context."""
        return Decimal(self.value)

    @classmethod
    def desde_tasa(cls, tasa: Decimal) -> AlicuotaIVA:
        """Rebuild from the column.

        Compares numerically and not by string, because `NUMERIC(5, 4)` comes back as
        `Decimal("0.1050")` and `"0.1050" != "0.105"` while the two numbers are equal.
        """
        for miembro in cls:
            if miembro.tasa == tasa:
                return miembro
        raise EntradaInvalida(f"'{tasa}' no es una alicuota de IVA conocida")


class AmbitoDeCategoria(StrEnum):
    """What a category may classify (HU-E4-03 RN-01).

    **`AMBOS` is decision D9 of the epic 3 map.** The DER's `aplica_a` enum lists
    `CLIENTE · SERVICIO · FAQ · TURNO` and the story asks for «clientes, servicios o
    ambos», so the value the story needs is added and the two the DER has for later epics
    — FAQ in epic 8, TURNO in epic 7 — are simply not offered by this screen.

    **Named `AmbitoDeCategoria` and not `AplicaA`**: `aplica_a` is the column's name, and a
    column name makes a poor type name.
    """

    CLIENTE = "CLIENTE"
    SERVICIO = "SERVICIO"
    AMBOS = "AMBOS"
