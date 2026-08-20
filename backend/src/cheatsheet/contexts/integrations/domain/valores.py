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
    """The four states an integration can be in.

    Three come from HU-E2-05 RN-02. `ATENCION` is the one that earns its place there: a
    service that answers but reports a problem is not the same as one that does not
    answer, and the acceptance criterion "una integración está degradada → la muestro en
    estado Atención con el detalle" is the reason the DER's `activa boolean` is not enough
    (gap H9).

    **`PENDIENTE` is the fourth, added by `conexion-whatsapp`** exactly as the previous
    unit announced it would be. Meta takes 24 to 72 hours to verify a number (HU-E2-03
    RN-02), and during that window the integration is neither connected nor failed: the
    credential is valid and stored, and there is simply no verdict yet. Collapsing it into
    `NO_CONECTADO` would show the Administrator an error for something that is working as
    designed — and would offer "Reconectar" for a request that is already in flight.

    Only WhatsApp reaches it today. ARCA and MercadoPago answer synchronously.
    """

    CONECTADO = "CONECTADO"
    PENDIENTE = "PENDIENTE"
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


#: The parameter keys this context defines for itself. Each provider's Anti-Corruption
#: Layer fills them from whatever its own vocabulary calls the same thing, and they are
#: declared here — not in each adapter — so the application layer can read them without
#: learning any provider's field names.
#:
#: `etiqueta`: a short human-readable name for what got connected, shown on the card under
#: the system's name. Meta calls it `verified_name` (HU-E2-03 RN-03).
CLAVE_ETIQUETA = "etiqueta"

#: `cuit`: the tax id the **provider** says the stored credential belongs to — for ARCA,
#: what the certificate's subject declares. Promoted from ARCA's adapter to the domain by
#: `padron-y-datos-fiscales`, which compares it with the CUIT the company entered by hand:
#: a difference means somebody loaded another taxpayer's certificate, and without this it
#: surfaces when the first document is issued in the wrong name.
CLAVE_CUIT = "cuit"

#: `credencial_vence_en`: cuando la credencial guardada deja de servir, en ISO-8601 UTC.
#: Escrita por `conexion-mercadopago`, cuyo OAuth devuelve un `expires_in` en segundos.
#:
#: Vive en el dominio y no en el `mapeo.py` del proveedor —a diferencia de `phone_number_id`
#: o `user_id`— porque **la capa de aplicacion la lee**: el barrido de renovacion decide con
#: ella si hay que llamar al proveedor, y un caso de uso que leyera una clave declarada en
#: `infrastructure/` estaria importando hacia adentro (R2).
#:
#: ARCA no la usa: el vencimiento de un certificado esta adentro del certificado, y leerlo de
#: aca seria copiar un dato que ya existe en su fuente.
CLAVE_VENCIMIENTO = "credencial_vence_en"

#: `code_verifier`: el secreto de un solo uso de PKCE (RFC 7636). Viaja por
#: `MaterialDeConexion.efimeros` y **no se guarda**: para cuando el codigo se canjeo, ya no
#: sirve para nada. Es vocabulario del estandar, no de un proveedor, asi que vive aca y no
#: en el `mapeo.py` de MercadoPago.
CLAVE_VERIFICADOR = "code_verifier"


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
