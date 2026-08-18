"""Value objects of the integrations context (DER, BC4)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from cheatsheet.shared.errors import EntradaInvalida

LARGO_MAXIMO_DETALLE = 300


class SistemaExterno(StrEnum):
    """DER enum `sistema_externo`. The whole catalogue, not just this epic's share.

    `GOOGLE_SHEETS` and `EXCEL_ONLINE` belong to HU-E2-04, which the roadmap moved to
    epic 4 because its acceptance criteria end in the mapping screen rather than in a
    connection. They are declared here anyway: the enum is an input from the DER, and a
    partial copy of it would have to be widened later by a unit that has no other reason
    to touch this file.

    Gap H8 (recorded by `identidad-y-onboarding`): the platform's own Google OAuth client
    is *not* one of these. These are per-company credentials; that one is the platform's.
    """

    ARCA = "ARCA"
    MERCADOPAGO = "MERCADOPAGO"
    WHATSAPP = "WHATSAPP"
    GOOGLE_SHEETS = "GOOGLE_SHEETS"
    EXCEL_ONLINE = "EXCEL_ONLINE"


#: What PAN-CFG-INT shows, in the order the prototype shows it. The spreadsheet card is
#: one card for two enum values because HU-E2-04 treats Sheets and Excel Online as one
#: choice; epic 4 decides which value a given company's link carries.
SISTEMAS_EN_PANTALLA: tuple[SistemaExterno, ...] = (
    SistemaExterno.ARCA,
    SistemaExterno.MERCADOPAGO,
    SistemaExterno.WHATSAPP,
    SistemaExterno.GOOGLE_SHEETS,
)


class Ambiente(StrEnum):
    """Which side of the external service the integration talks to (HU-E2-01 RN-03).

    **Not chosen by the Administrator.** It is derived from `APP_ENV` at connection time
    and then frozen on the row. A company that could pick this from a dropdown could sit
    in homologación believing it is invoicing — or, worse, issue a real irreversible
    document from a deployment meant for testing.

    It is still stored rather than recomputed on read, because a row created in
    homologación has to keep saying so if the database is ever restored somewhere else.
    """

    HOMOLOGACION = "HOMOLOGACION"
    PRODUCCION = "PRODUCCION"


class EstadoDeConexion(StrEnum):
    """The three states of HU-E2-05 RN-02, and only those three.

    `ATENCION` is the one that earns its place: a service that answers but reports a
    problem is not the same as one that does not answer, and the acceptance criterion
    "una integración está degradada → la muestro en estado Atención con el detalle" is
    the reason the DER's `activa boolean` is not enough (gap H9).

    **`PENDIENTE` is deliberately absent.** Only WhatsApp needs it — Meta takes 24 to 72
    hours to verify a number (HU-E2-03 RN-02) — and `conexion-whatsapp` adds it. Stated
    here so that unit reads this as planned scope rather than as something it broke.
    """

    CONECTADO = "CONECTADO"
    ATENCION = "ATENCION"
    NO_CONECTADO = "NO_CONECTADO"


@dataclass(frozen=True, slots=True)
class CredencialCifrada:
    """The credential as it lives at rest: ciphertext plus how to read it.

    The two DER columns travel together because one without the other is unreadable.
    `algoritmo` carries the key generation as well (`AES-256-GCM/v1`), which is what lets
    a rotation write `/v2` on new rows without having to guess what encrypted the old
    ones.

    This type never holds plaintext. Decryption returns bytes that are handed straight to
    the provider adapter and never stored on an aggregate.
    """

    contenido: bytes
    algoritmo: str

    def __post_init__(self) -> None:
        if not self.contenido:
            raise EntradaInvalida("Una credencial cifrada no puede estar vacia")
        if not self.algoritmo.strip():
            raise EntradaInvalida("Una credencial cifrada debe declarar su algoritmo")


def validar_detalle(detalle: str | None) -> str | None:
    """The human-readable reason behind a state, shown next to the Atención badge."""
    if detalle is None:
        return None
    limpio = detalle.strip()
    if not limpio:
        return None
    if len(limpio) > LARGO_MAXIMO_DETALLE:
        return limpio[:LARGO_MAXIMO_DETALLE]
    return limpio
