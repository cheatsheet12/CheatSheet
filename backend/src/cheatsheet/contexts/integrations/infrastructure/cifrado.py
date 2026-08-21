"""AES-256-GCM for the credentials at rest (DER BC4, ADR-0003 point 3).

**Why this file is here and not in `platform/`.** ADR-0003 says decryption never leaves
the `integrations` context. A cipher in `platform/` would be importable by any module in
the system, and that sentence would rest on nobody happening to import it. Here, R3 stops
them: no other context may import `integrations/infrastructure/`, and the guard blocks the
write before the code exists.

What is *not* claimed: `SECRETS_ENCRYPTION_KEY` lives on `Settings`, like `JWT_SECRET`, so
the key material is reachable from `platform`. The property this placement buys is that
the *capability* — knowing the algorithm, the nonce layout and how to invoke them — has
exactly one home.

**Why GCM.** The credential must be tamper-evident, not merely unreadable. A truncated or
flipped ciphertext that decrypts to garbage and gets sent to ARCA as a certificate is a
failure mode with no error message; AEAD turns it into an exception at the point of read.
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cheatsheet.contexts.integrations.domain.valores import CredencialCifrada

#: Written into `credencial_algoritmo`. The generation suffix is not decoration: rotating
#: the key means writing `/v2` on new rows and keeping a reader for `/v1`, which is only
#: possible because the DER gave the algorithm its own column instead of assuming one.
ALGORITMO = "AES-256-GCM/v1"

LARGO_CLAVE = 32
LARGO_NONCE = 12


class ClaveDeCifradoInvalida(RuntimeError):
    """`SECRETS_ENCRYPTION_KEY` is not 32 bytes of base64. Raised at construction."""


class CredencialIlegible(RuntimeError):
    """The ciphertext does not authenticate, or its algorithm is unknown.

    Not an `ErrorDeDominio`: no business rule was broken. Either the row was tampered
    with, or it was encrypted with a key this process does not have.
    """


class CifradoAesGcm:
    """The adapter behind `PortCifradoDeCredenciales`.

    The nonce is random per encryption and stored as the first 12 bytes of the ciphertext.
    Storing it beside the payload rather than deriving it from the row is deliberate: a
    nonce derived from `(empresa_id, sistema)` would repeat on every reconnection, and a
    repeated nonce under the same key is what breaks GCM outright.
    """

    def __init__(self, clave_base64: str) -> None:
        try:
            clave = base64.b64decode(clave_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ClaveDeCifradoInvalida(
                "SECRETS_ENCRYPTION_KEY debe ser base64 valido de 32 bytes"
            ) from exc
        if len(clave) != LARGO_CLAVE:
            raise ClaveDeCifradoInvalida(
                f"SECRETS_ENCRYPTION_KEY debe decodificar a {LARGO_CLAVE} bytes, no {len(clave)}"
            )
        self._aead = AESGCM(clave)

    def cifrar(self, plano: bytes) -> CredencialCifrada:
        nonce = os.urandom(LARGO_NONCE)
        sellado = self._aead.encrypt(nonce, plano, None)
        return CredencialCifrada(contenido=nonce + sellado, algoritmo=ALGORITMO)

    def descifrar(self, credencial: CredencialCifrada) -> bytes:
        if credencial.algoritmo != ALGORITMO:
            raise CredencialIlegible(
                f"Algoritmo desconocido '{credencial.algoritmo}': esta version solo lee {ALGORITMO}"
            )
        if len(credencial.contenido) <= LARGO_NONCE:
            raise CredencialIlegible("La credencial cifrada es mas corta que su nonce")
        nonce, sellado = credencial.contenido[:LARGO_NONCE], credencial.contenido[LARGO_NONCE:]
        try:
            return self._aead.decrypt(nonce, sellado, None)
        except InvalidTag as exc:
            raise CredencialIlegible(
                "La credencial no autentica: fue alterada o cifrada con otra clave"
            ) from exc


def generar_clave() -> str:
    """A fresh key, base64-encoded, for filling in `SECRETS_ENCRYPTION_KEY`.

    Here rather than in a script so that the way keys are made and the way they are read
    cannot drift apart.
    """
    return base64.b64encode(os.urandom(LARGO_CLAVE)).decode()
