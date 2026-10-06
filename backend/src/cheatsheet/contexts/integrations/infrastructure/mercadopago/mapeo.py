"""MercadoPago's vocabulary in, ours out. Pure functions, no sockets.

Two things in here decide more than they look like they do.

**The credential is the pair of tokens.** `TicketEmitido` — the type `conexion-arca`
introduced for ARCA's access ticket — anticipated carrying MercadoPago's refresh token,
and it does not. Its `servicio` is a `ServicioDeArca`, so using it would mean renaming
that enum and migrating `ticket_de_acceso`, a table whose entire reason to exist is that
ARCA distinguishes a two-year credential from a twelve-hour session and refuses to mint
the second while the first lives. MercadoPago has no such distinction: there is no
long-lived credential underneath, the company never typed anything, and renewing replaces
the whole thing. So both tokens travel together in one encrypted blob, the same way WSAA's
token and sign do.

**`live_mode` is the only environment signal there is.** Unlike ARCA, MercadoPago has no
separate sandbox host: the same API serves everything and what changes is whose
application credentials are used and whether the account that authorized is a test one.
`Ambiente` still comes from `APP_ENV` — never from the request — and this is what catches
the two of them disagreeing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_ETIQUETA,
    CLAVE_VENCIMIENTO,
    EstadoDeConexion,
)

#: Parameter keys this adapter writes onto the aggregate. Ours, not MercadoPago's.
CLAVE_USUARIO = "usuario_externo"
CLAVE_CUENTA_REAL = "cuenta_real"

_SEPARADOR = "\n"

#: Read off a real answer: about 180 days. Used only when MercadoPago omits `expires_in`,
#: so that a missing field does not turn into "renew every day, forever".
DURACION_POR_DEFECTO = timedelta(days=180)


@dataclass(frozen=True, slots=True)
class TokensDeMercadoPago:
    """What the `/oauth/token` endpoint answers, in our words."""

    acceso: str
    refresco: str
    expira_en: datetime
    usuario: str | None


def empaquetar(acceso: str, refresco: str) -> bytes:
    """The two tokens together, because one without the other is a dead end.

    Same technique as WSAA's token and sign, for the same reason: a pair split across two
    places is a pair that eventually disagrees. Both are ASCII, so the newline separator
    cannot appear inside either.
    """
    return f"{acceso}{_SEPARADOR}{refresco}".encode()


def desempaquetar(credencial: bytes) -> tuple[str, str]:
    """Read back what `empaquetar` wrote. Raises when the stored blob is not a pair."""
    partes = credencial.decode("utf-8", errors="replace").split(_SEPARADOR)
    if len(partes) != 2 or not partes[0] or not partes[1]:
        raise ProveedorNoDisponible("La credencial guardada de MercadoPago no tiene los dos tokens")
    return partes[0], partes[1]


def leer_tokens(datos: dict[str, Any], ahora: datetime) -> TokensDeMercadoPago:
    """Turn the token payload into ours, or say clearly that it is unusable.

    A response without an `access_token` is not a rejection — MercadoPago answered 200 —
    but it is nothing we can store either, and failing here beats writing an empty
    credential that fails months later at the moment of charging.
    """
    acceso = _texto(datos.get("access_token"))
    refresco = _texto(datos.get("refresh_token"))
    if not acceso or not refresco:
        raise ProveedorNoDisponible("MercadoPago no devolvio el par de tokens completo")
    return TokensDeMercadoPago(
        acceso=acceso,
        refresco=refresco,
        expira_en=ahora + _duracion(datos.get("expires_in")),
        usuario=_texto(datos.get("user_id")),
    )


def parametros_de(
    tokens: TokensDeMercadoPago, cuenta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """What gets recorded on the row: who the account is and until when this works.

    Never a token. The account id is not a secret — it identifies the seller to
    MercadoPago and epic 6 needs it to build payment links — and the expiry is what the
    daily renewal reads.
    """
    parametros: dict[str, Any] = {CLAVE_VENCIMIENTO: tokens.expira_en.isoformat()}
    if tokens.usuario:
        parametros[CLAVE_USUARIO] = tokens.usuario
    if cuenta is not None:
        # Only when the account was read. A renewal does not read it and must not
        # overwrite what the connection recorded.
        parametros[CLAVE_CUENTA_REAL] = es_cuenta_real(cuenta)
        parametros.update(parametros_de_cuenta(cuenta))
    return parametros


#: The tag `/users/me` carries on every account created under "Cuentas de prueba".
ETIQUETA_DE_PRUEBA = "test_user"


def es_cuenta_real(cuenta: dict[str, Any]) -> bool:
    """Whether the account is a real one, read off `/users/me`.

    **Not `live_mode`.** That field says which credentials minted the token, and a test
    account authorizes with production credentials like any other: its token comes back
    `live_mode: true`. The account's own tags are what say it is a test one.
    """
    etiquetas = cuenta.get("tags")
    return not (isinstance(etiquetas, list) and ETIQUETA_DE_PRUEBA in etiquetas)


def parametros_de_cuenta(cuenta: dict[str, Any]) -> dict[str, Any]:
    """What `/users/me` contributes to the row. Shared with the live check."""
    etiqueta = _etiqueta(cuenta)
    return {CLAVE_ETIQUETA: etiqueta} if etiqueta else {}


def _etiqueta(cuenta: dict[str, Any]) -> str:
    """What the card shows under "MercadoPago": the nickname, and the email if there is one.

    The account id is deliberately not here. It identifies the seller to the provider and
    means nothing to a person reading a card.
    """
    apodo = _texto(cuenta.get("nickname")) or ""
    email = _texto(cuenta.get("email")) or ""
    if apodo and email:
        return f"{apodo} · {email}"
    return apodo or email


def estado_por_ambiente(
    cuenta_real: bool, es_produccion: bool
) -> tuple[EstadoDeConexion, str | None]:
    """Cross what the account says about itself with where this deployment is running.

    The asymmetry is on purpose. A **real** account in a deployment that is not production
    is the case that charges somebody's card from an environment meant for practising, so
    it is refused outright. A **test** account in production is the mirror image and is
    not refused: the risk there is money not collected, which is visible the first time
    somebody tries to pay, and refusing it would block a legitimate staging-to-production
    cutover.
    """
    if cuenta_real and not es_produccion:
        return (
            EstadoDeConexion.NO_CONECTADO,
            "La cuenta de MercadoPago es real y este entorno es de homologacion. "
            "Conecta una cuenta de prueba.",
        )
    if not cuenta_real and es_produccion:
        return (
            EstadoDeConexion.ATENCION,
            "La cuenta de MercadoPago es de prueba: los cobros no van a ser reales.",
        )
    return (EstadoDeConexion.CONECTADO, None)


def rechazo(estado: int, cuerpo: dict[str, Any]) -> ConexionRechazada:
    """Translate a 4xx from `/oauth/token` into the sentence somebody has to act on.

    `invalid_client` is singled out because it is **our** misconfiguration, not the
    Administrator's mistake: the application credentials in the environment are wrong, and
    a message about "the authorization" would send whoever reads it looking in the wrong
    place.
    """
    error = _texto(cuerpo.get("error")) or ""
    detalle = _texto(cuerpo.get("error_description")) or ""
    if error == "invalid_client":
        return ConexionRechazada(
            "MercadoPago rechazo las credenciales de la aplicacion. "
            "Revisá MERCADOPAGO_CLIENT_ID y MERCADOPAGO_CLIENT_SECRET del despliegue."
        )
    if error == "invalid_grant":
        return ConexionRechazada(
            "MercadoPago rechazo la autorizacion: el codigo ya fue usado o vencio. "
            "Volve a iniciar la conexion."
        )
    return ConexionRechazada(f"MercadoPago rechazo la operacion ({estado}): {detalle or error}")


def _duracion(crudo: object) -> timedelta:
    if isinstance(crudo, (int, float)) and crudo > 0:
        return timedelta(seconds=int(crudo))
    return DURACION_POR_DEFECTO


def _texto(valor: object) -> str | None:
    """MercadoPago answers `user_id` as a number and everything else as a string."""
    if isinstance(valor, str):
        return valor.strip() or None
    if isinstance(valor, int) and not isinstance(valor, bool):
        return str(valor)
    return None
