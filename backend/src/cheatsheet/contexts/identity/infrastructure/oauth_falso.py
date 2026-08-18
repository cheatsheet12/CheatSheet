"""A stand-in for Google, for environments that have no OAuth client.

**Why this exists at all.** Signing in with Google is one of the two ways HU-E1-01 lets
somebody create an account. Without credentials the endpoint could only refuse, so the
flow would be unreachable in local development and unverifiable in the test suite — and
"unverifiable" is how a path ships broken.

**What it is not.** It authenticates nobody. The authorization code *is* the email, and
anybody who can call the endpoint can claim any address. That is acceptable exactly where
it is allowed and nowhere else:

- `Settings.google_oauth_configurado` decides. When the real client id and secret are
  present, `proveedor_google` returns the real adapter and this class is never built.
- Selecting it in `produccion` raises. Not "logs a warning": raises, at startup, before
  the process can accept a request.

The authorization URL points back at the application's own callback, so the local flow
is a redirect the developer can follow instead of a page that says "not configured".
"""

from __future__ import annotations

from urllib.parse import urlencode

from cheatsheet.contexts.identity.application.errors import OAuthFallido
from cheatsheet.contexts.identity.application.ports import PerfilDeGoogle
from cheatsheet.contexts.identity.domain.valores import Email
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.errors import EntradaInvalida

#: The fake authorization code is `simulado:<email>`. The prefix is what keeps a real
#: Google code — which never looks like this — from being accepted by accident.
PREFIJO = "simulado:"


class ProveedorOAuthSimulado:
    """Implements `PortProveedorOAuth`. Development and tests only."""

    def __init__(self, *, url_base_de_la_app: str, entorno: Entorno) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El proveedor OAuth simulado no puede usarse en produccion. "
                "Configura GOOGLE_OAUTH_CLIENT_ID y GOOGLE_OAUTH_CLIENT_SECRET."
            )
        self._url_base = url_base_de_la_app.rstrip("/")

    def url_de_autorizacion(self, state: str) -> str:
        """Points at the app's own callback, so the redirect chain still works locally."""
        parametros = {"state": state, "code": f"{PREFIJO}dev@ejemplo.test", "simulado": "1"}
        return f"{self._url_base}/api/auth/google/callback?{urlencode(parametros)}"

    async def perfil_desde_codigo(self, codigo: str) -> PerfilDeGoogle:
        if not codigo.startswith(PREFIJO):
            raise OAuthFallido(
                f"El proveedor OAuth simulado espera un codigo con el formato '{PREFIJO}<email>'"
            )
        direccion = codigo.removeprefix(PREFIJO).strip()
        try:
            email = Email(direccion)
        except EntradaInvalida as exc:
            raise OAuthFallido(f"'{direccion}' no es un email valido") from exc
        # The name Google would have returned. Whoever signs in this way can change it.
        return PerfilDeGoogle(email=email, nombre=direccion.split("@")[0].replace(".", " ").title())
