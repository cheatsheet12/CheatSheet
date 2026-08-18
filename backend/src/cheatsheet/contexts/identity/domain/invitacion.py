"""`Invitacion` — the pending half of HU-E1-04.

An invitation is a credential with an expiry date. Whoever holds the token can create a
password for an account inside somebody's company, so it is treated exactly like the
refresh token in `sesion.py`: **opaque, random, stored hashed, single use, revocable.**

RN-02 makes acceptance the moment the account becomes real, and RN-04 says a pending
invitation can be resent or revoked. Both of those are transitions on this aggregate, and
both stop being legal once it has been accepted — which is why `esta_pendiente` exists
rather than each caller re-deriving it from three fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida, InvarianteViolada


@dataclass(slots=True)
class Invitacion:
    """One invitation to join a company."""

    id: UUID
    empresa_id: EmpresaId
    #: The `Usuario` row created in `INVITADO` state. They exist together or not at all.
    usuario_id: UsuarioId
    hash_del_token: str
    expira_en: datetime
    #: Who sent it — HU-E1-05 RN-04's "ejecutor", kept for the audit trail.
    invitado_por: UsuarioId
    aceptada_en: datetime | None = None
    revocada: bool = False

    def __post_init__(self) -> None:
        if not self.hash_del_token.strip():
            raise EntradaInvalida("El token de invitacion debe guardarse hasheado")
        if self.expira_en.tzinfo is None:
            raise EntradaInvalida("expira_en debe tener zona horaria (UTC)")

    @property
    def fue_aceptada(self) -> bool:
        return self.aceptada_en is not None

    @property
    def esta_pendiente(self) -> bool:
        """RN-04: resending and revoking are only legal while this is true."""
        return not self.fue_aceptada and not self.revocada

    def esta_vencida(self, ahora: datetime) -> bool:
        return ahora >= self.expira_en

    def es_utilizable(self, ahora: datetime) -> bool:
        return self.esta_pendiente and not self.esta_vencida(ahora)

    def aceptar(self, ahora: datetime) -> None:
        if not self.es_utilizable(ahora):
            raise InvarianteViolada("La invitacion no es valida")
        self.aceptada_en = ahora

    def revocar(self) -> None:
        """RN-04. Accepting already happened is not something revoking can undo.

        An accepted invitation is a person with a password who has been working; taking
        that away is deactivating a user (HU-E1-06), a different action with a different
        audit entry and a different rule about the last Administrator.
        """
        if self.fue_aceptada:
            raise InvarianteViolada("Una invitacion aceptada ya no se puede revocar")
        self.revocada = True

    def reemplazar_token(self, hash_nuevo: str, expira_en: datetime) -> None:
        """RN-04's resend.

        The previous token stops working, because this row is the only record of it and
        the hash is overwritten. Resending must not leave two live keys to the same door:
        an invitation forwarded to the wrong address is one of the reasons somebody
        resends in the first place.
        """
        if not self.esta_pendiente:
            raise InvarianteViolada("Solo se puede reenviar una invitacion pendiente")
        if not hash_nuevo.strip():
            raise EntradaInvalida("El token de invitacion debe guardarse hasheado")
        if expira_en.tzinfo is None:
            raise EntradaInvalida("expira_en debe tener zona horaria (UTC)")
        self.hash_del_token = hash_nuevo
        self.expira_en = expira_en
