"""Shared Kernel — the idempotency key every async task and webhook carries (ADR-009).

The key is `empresa + tipo + huella del payload`. Two deliveries of the same
MercadoPago webhook, or the same Celery task retried after a timeout that actually
succeeded, produce the same key — and the second one is a no-op instead of a second
`Cobro`.

The fingerprint is a SHA-256 of the canonical JSON form of the payload. Canonical
means sorted keys and no incidental whitespace: `{"a":1,"b":2}` and `{"b":2,"a":1}`
are the same delivery, and a hash that disagreed would defeat the whole mechanism.

SHA-256 here is a content fingerprint, not a security primitive. It is not hashing a
secret and it never protects one — passwords use Argon2id (ADR-011).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cheatsheet.shared.empresa import EmpresaId
from cheatsheet.shared.errors import EntradaInvalida


@dataclass(frozen=True, slots=True)
class ClaveDeIdempotencia:
    """A stable identity for one intended effect."""

    valor: str

    def __post_init__(self) -> None:
        if not self.valor.strip():
            raise EntradaInvalida("La clave de idempotencia no puede estar vacia")

    @classmethod
    def de(cls, *, empresa_id: EmpresaId, tipo: str, payload: Any) -> ClaveDeIdempotencia:
        """Build the key from the company, the kind of work and its payload.

        `payload` must be JSON-serialisable; anything reaching a task queue already is.
        """
        if not tipo.strip():
            raise EntradaInvalida("El tipo de la clave de idempotencia es obligatorio")
        huella = hashlib.sha256(_canonico(payload).encode("utf-8")).hexdigest()[:32]
        return cls(f"{empresa_id}:{tipo}:{huella}")

    def __str__(self) -> str:
        return self.valor


def _canonico(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as exc:
        raise EntradaInvalida(f"El payload no es serializable a JSON: {exc}") from exc
