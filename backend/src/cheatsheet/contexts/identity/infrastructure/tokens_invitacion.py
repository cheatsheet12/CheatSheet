"""The invitation token (HU-E1-04 RN-02).

Same construction as the refresh token, and deliberately the same digest function: 256
bits from the OS CSPRNG via `secrets`, hashed with `hashear_token_opaco`. Two opaque
credentials stored the same way is one fewer thing that can quietly diverge.
"""

from __future__ import annotations

import secrets

from cheatsheet.contexts.identity.infrastructure.seguridad import hashear_token_opaco

BYTES_DE_TOKEN = 32


class TokenDeInvitacionAleatorio:
    """Implements `PortTokenDeInvitacion`."""

    def emitir(self) -> str:
        return secrets.token_urlsafe(BYTES_DE_TOKEN)

    def hashear(self, token: str) -> str:
        return hashear_token_opaco(token)
