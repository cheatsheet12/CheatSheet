"""Password hashing and token issuance (ADR-011).

**Argon2id, with explicit parameters.** The library's defaults change between versions,
and a silent downgrade of the work factor is exactly the kind of regression nobody
notices. Writing them down makes the cost a decision the repository owns.

**The access token is a JWT; the refresh token is not.** A JWT cannot be revoked by
itself, so it is not trusted for more than *who is asking*: on every request the
middleware asks the database whether that user still exists, is `ACTIVO` and which role
they hold now (`VerificarSesionVigente`). A deactivation or a role change therefore takes
effect on the next request, and the 15-minute lifetime only bounds how long a token can be
presented at all. A refresh token lives for days and must be revocable the instant a theft
is detected, so it is an opaque random string with a row behind it.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from cheatsheet.contexts.identity.application.ports import TokenEmitido
from cheatsheet.contexts.identity.domain.valores import HashDeContrasena
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

# OWASP's recommended Argon2id baseline: 19 MiB, 2 iterations, 1 degree of parallelism.
MEMORIA_KIB = 19 * 1024
ITERACIONES = 2
PARALELISMO = 1
LARGO_DEL_HASH = 32
LARGO_DE_SAL = 16

ALGORITMO_JWT = "HS256"
BYTES_DE_REFRESH = 32


def hashear_token_opaco(token: str) -> str:
    """The digest stored for a refresh token and for an invitation token.

    **SHA-256 is right here and Argon2 would be wrong.** Argon2's cost exists to slow down
    guessing a *human-chosen* password. These tokens are 256 random bits: there is nothing
    to guess, and paying 19 MiB per verification would only make the endpoints that verify
    them easy to overload.

    One function for both, so the two can never drift into different digests — the kind of
    difference that shows up as "some tokens stop working" long after the change.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class HasherArgon2:
    """Implements `PortHashDeContrasena`."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            memory_cost=MEMORIA_KIB,
            time_cost=ITERACIONES,
            parallelism=PARALELISMO,
            hash_len=LARGO_DEL_HASH,
            salt_len=LARGO_DE_SAL,
        )

    def hashear(self, contrasena: str) -> HashDeContrasena:
        return HashDeContrasena(self._hasher.hash(contrasena))

    def verificar(self, contrasena: str, hash_guardado: HashDeContrasena) -> bool:
        try:
            return self._hasher.verify(hash_guardado.valor, contrasena)
        except (VerifyMismatchError, InvalidHashError):
            # A wrong password and a corrupt hash are both "no" to the caller. Neither
            # is an exception the sign-in flow should have to know about.
            return False


class EmisorDeTokensJWT:
    """Implements `PortEmisorDeTokens`."""

    def __init__(self, *, secreto: str, vida_acceso: timedelta) -> None:
        if not secreto.strip():
            raise ValueError("JWT_SECRET no puede estar vacio")
        self._secreto = secreto
        self._vida_acceso = vida_acceso

    def emitir_acceso(
        self, *, usuario_id: UsuarioId, empresa_id: EmpresaId, rol: str, ahora: datetime
    ) -> TokenEmitido:
        expira = ahora + self._vida_acceso
        payload = {
            "sub": str(usuario_id),
            "empresa_id": str(empresa_id),
            "rol": rol,
            "iat": int(ahora.timestamp()),
            "exp": int(expira.timestamp()),
        }
        return TokenEmitido(
            valor=jwt.encode(payload, self._secreto, algorithm=ALGORITMO_JWT),
            expira_en=expira,
        )

    def emitir_refresh(self, ahora: datetime) -> TokenEmitido:
        """256 bits from the OS CSPRNG. `secrets`, never `random`."""
        return TokenEmitido(valor=secrets.token_urlsafe(BYTES_DE_REFRESH), expira_en=ahora)

    def hashear_refresh(self, token: str) -> str:
        return hashear_token_opaco(token)


def decodificar_acceso(token: str, secreto: str) -> dict[str, str]:
    """Verify and decode an access token. Raises `jwt.PyJWTError` when it is not valid."""
    datos = jwt.decode(token, secreto, algorithms=[ALGORITMO_JWT])
    return {clave: str(valor) for clave, valor in datos.items()}
