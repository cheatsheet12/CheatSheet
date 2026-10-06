"""Shared Kernel — how the system reaches a person.

`Email` was born in `identity/domain/valores.py`, where the first one is created: the
address someone signs up with. It moved here in epic 3 under the rule `fiscal.py` states
— a value object moves to the Shared Kernel when a **second** context needs it, never in
anticipation. `master_data` is that second context: `cliente.contacto_email` is an
address the system will write to, and it has to be normalised by the same rules or the
same person ends up in the catalogue twice.

`Telefono` is born here rather than moving, because there was nowhere for it to be born
before: `cliente.contacto_whatsapp` (HU-E4-01) is the first phone number this system
stores. `conversational` will be the second, in epic 8, when the agent answers one.

R4 holds: this module imports nothing from `contexts/`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cheatsheet.shared.errors import EntradaInvalida

#: E.164 allows at most 15 digits. The floor is deliberately low — an Argentine landline
#: written without its area code is eight — because this value object is not the
#: authority on whether a number is reachable.
LARGO_MINIMO_TELEFONO = 8
LARGO_MAXIMO_TELEFONO = 15

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NO_DIGITOS = re.compile(r"[^0-9]")


@dataclass(frozen=True, slots=True)
class Email:
    """Normalised to lowercase.

    HU-E1-01 RN-03 forbids two accounts with the same email. Comparing the raw strings
    would let `Ana@x.com` and `ana@x.com` through as two accounts, which is the same
    person and, sooner or later, the same support ticket.
    """

    valor: str

    def __post_init__(self) -> None:
        limpio = self.valor.strip().lower()
        if not _EMAIL.match(limpio):
            raise EntradaInvalida(f"'{self.valor}' no es un email valido")
        object.__setattr__(self, "valor", limpio)

    def __str__(self) -> str:
        return self.valor


@dataclass(frozen=True, slots=True)
class Telefono:
    """A phone number, kept as digits.

    **What it validates is length, and nothing else.** Not the country code, not the
    Argentine mobile `9`, not whether the line exists. The reason is the same one that
    keeps `CUIT` from checking its prefix: the published rules disagree at the edges, and
    refusing a real customer's number is a worse failure than storing one WhatsApp will
    later reject. WhatsApp is the authority on whether a number can be written to, and it
    answers in epic 8 — not in this form.

    Punctuation, spaces and a leading `+` are dropped on the way in, so `+54 9 11
    1234-5678` and `5491112345678` are the same number and compare equal.
    """

    valor: str

    def __post_init__(self) -> None:
        digitos = _NO_DIGITOS.sub("", self.valor)
        if not LARGO_MINIMO_TELEFONO <= len(digitos) <= LARGO_MAXIMO_TELEFONO:
            raise EntradaInvalida(
                f"Un telefono tiene entre {LARGO_MINIMO_TELEFONO} y "
                f"{LARGO_MAXIMO_TELEFONO} digitos, no {len(digitos)}"
            )
        object.__setattr__(self, "valor", digitos)

    def __str__(self) -> str:
        return self.valor
