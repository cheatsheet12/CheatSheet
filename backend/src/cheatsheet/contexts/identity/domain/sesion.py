"""Refresh tokens, and the reuse detection that makes rotation worth anything (ADR-011).

The DER has no table for this (gap H3), and the design stage requires one: opaque
rotating refresh tokens with reuse detection.

**Why rotation alone is not enough.** If a stolen refresh token is rotated by the
attacker, the victim's next refresh presents a token that was already used. Revoking
only that token lets the attacker keep going — the two just take turns rotating, and
nobody notices. Revoking the whole **family** is what turns the victim's next request
into the alarm: one of them loses the session, and both are forced to sign in again.

The token itself is never stored. What is stored is its hash, so that a database dump is
not a set of live sessions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida


@dataclass(slots=True)
class RefreshToken:
    """One link in a rotation chain."""

    id: UUID
    #: All the tokens descended from one sign-in. Revocation works on this, not on `id`.
    familia_id: UUID
    empresa_id: EmpresaId
    usuario_id: UsuarioId
    hash_del_token: str
    expira_en: datetime
    usado_en: datetime | None = None
    revocado: bool = False

    def __post_init__(self) -> None:
        if not self.hash_del_token.strip():
            raise EntradaInvalida("El refresh token debe guardarse hasheado")
        if self.expira_en.tzinfo is None:
            raise EntradaInvalida("expira_en debe tener zona horaria (UTC)")

    @property
    def fue_usado(self) -> bool:
        return self.usado_en is not None

    def esta_vencido(self, ahora: datetime) -> bool:
        return ahora >= self.expira_en

    def es_utilizable(self, ahora: datetime) -> bool:
        return not self.revocado and not self.fue_usado and not self.esta_vencido(ahora)

    def marcar_usado(self, momento: datetime) -> None:
        self.usado_en = momento

    def revocar(self) -> None:
        self.revocado = True
