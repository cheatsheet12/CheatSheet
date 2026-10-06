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

**`CUIT` joined it in epic 3, under the rule this docstring used to state.** It said the
value object stays in `identity` until a second context needs it, «never in
anticipation». `master_data` is that second context: `cliente.cuit` is validated by the
same rules as `empresa.cuit`, and HU-E4-01 RN-02 checks it against the same registry.
Two definitions of what a well-formed CUIT is would be two places for the check digit to
be wrong, in a system that puts that number on tax documents.

**This is not a general fiscal dumping ground.** A value object moves here when a second
context needs it, never in anticipation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from cheatsheet.shared.errors import EntradaInvalida

LARGO_CUIT = 11

#: The check-digit weights ARCA uses, in order.
MULTIPLICADORES = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

_NO_DIGITOS = re.compile(r"[^0-9]")


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


@dataclass(frozen=True, slots=True)
class CUIT:
    """An Argentine tax id, structurally valid.

    **Structural only, deliberately** (decision D1): format plus check digit. Whether
    the number actually exists in ARCA's registry is a separate question, asked by
    `integrations` when the company has a fiscal credential loaded — and answered
    differently depending on who asks: the onboarding blocks on an unknown CUIT, and so
    does the client form of HU-E4-01, but neither blocks when the registry could not be
    reached at all.

    The prefix (20/23/24/27 for people, 30/33/34 for companies) is **not** validated.
    The published lists disagree at the edges, and rejecting a real customer's CUIT is a
    worse failure than accepting one ARCA will reject later anyway.
    """

    valor: str

    def __post_init__(self) -> None:
        digitos = _NO_DIGITOS.sub("", self.valor)
        if len(digitos) != LARGO_CUIT:
            raise EntradaInvalida(f"Un CUIT tiene {LARGO_CUIT} digitos, no {len(digitos)}")
        if not _digito_verificador_valido(digitos):
            raise EntradaInvalida("El digito verificador del CUIT no es correcto")
        object.__setattr__(self, "valor", digitos)

    @property
    def formateado(self) -> str:
        """`30-71234567-8` — how a person reads it."""
        return f"{self.valor[:2]}-{self.valor[2:10]}-{self.valor[10]}"

    def __str__(self) -> str:
        return self.valor


def _digito_verificador_valido(digitos: str) -> bool:
    suma = sum(int(d) * m for d, m in zip(digitos[:10], MULTIPLICADORES, strict=True))
    resto = suma % 11
    esperado = 11 - resto
    if esperado == 11:
        esperado = 0
    elif esperado == 10:
        # 10 is never assigned as a check digit, so no CUIT can end in it.
        return False
    return esperado == int(digitos[10])
