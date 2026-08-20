"""Shared Kernel — the Argentine fiscal vocabulary more than one context has to speak.

`CondicionIVA` was born in `identity/domain/valores.py`, which is where the DER enum
`condicion_iva` belongs and where the first one is chosen, during onboarding. It moved
here the moment a second context had to **produce** one.

**Why the move rather than an import.** `padron-y-datos-fiscales` reads ARCA's registry
and translates what it finds — a monotributista, a responsable inscripto — into this
vocabulary. That translation is ARCA's dialect coming in, so it belongs in the
Anti-Corruption Layer under `integrations/infrastructure/arca/`; and reaching into
`identity/domain/` from there breaks rule R3 and contradicts
[ADR-0003](../../../../docs/adr/0003-integrations-open-host-service.md), which declares
`integrations` an Open Host Service that imports from no context.

It is the same situation as `RolUsuario` (see `roles.py`) and it is resolved the same way.
`identity/domain/valores.py` re-exports it, so every existing import keeps working and
`identity` remains the context that *owns* the concept. R4 holds: this module imports
nothing from `contexts/`.

**This is not a general fiscal dumping ground.** `CUIT` stays in `identity` — it is
validated there and nobody else constructs one from the outside yet. A value object moves
here when a second context needs it, never in anticipation.
"""

from __future__ import annotations

from enum import StrEnum


class CondicionIVA(StrEnum):
    """DER enum `condicion_iva`. What a taxpayer is, for VAT purposes.

    Closed catalogue, and deliberately the four the DER names rather than the longer list
    ARCA publishes: these are the ones PAN-ONB-02 offers and the ones epic 5 will branch
    on when it decides which kind of `Comprobante` may be issued to whom.
    """

    RESPONSABLE_INSCRIPTO = "RESPONSABLE_INSCRIPTO"
    MONOTRIBUTO = "MONOTRIBUTO"
    EXENTO = "EXENTO"
    CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL"
