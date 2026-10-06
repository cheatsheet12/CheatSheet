"""Google OAuth2 — the first real external integration of the system (HU-E1-01 RN-02).

Behind its own Anti-Corruption Layer (ADR-008): the application sees `PerfilDeGoogle`
and never a Google payload. Every call has an explicit timeout and a bounded retry —
CLAUDE.md §5 requires both, and a sign-up flow hanging on somebody else's outage is the
concrete reason why.

**The credentials belong to the platform, not to each company.** They are one OAuth
client for CheatSheet as a whole, so they come from the environment and not from
`configuracion_de_integracion`, which models per-company credentials. That is why the
`sistema_externo` enum of the DER has no entry for this (gap H8) and should not get one.

Scope is `openid email profile` and nothing else: RN-02 says CheatSheet asks for the
email and the name, and does not reach any other part of the account.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from cheatsheet.contexts.identity.application.errors import OAuthFallido
from cheatsheet.contexts.identity.application.ports import PerfilDeGoogle
from cheatsheet.contexts.identity.domain.valores import Email
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.errors import EntradaInvalida

logger = obtener_logger(__name__)

URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 — endpoint, not a secret
URL_PERFIL = "https://openidconnect.googleapis.com/v1/userinfo"
ALCANCE = "openid email profile"

TIMEOUT_SEGUNDOS = 10.0
MAX_INTENTOS = 3
ESPERA_BASE = 0.5


@dataclass(frozen=True, slots=True)
class ConfiguracionOAuthGoogle:
    client_id: str
    client_secret: str
    redirect_uri: str


class ProveedorOAuthGoogle:
    """Implements `PortProveedorOAuth`."""

    def __init__(self, configuracion: ConfiguracionOAuthGoogle) -> None:
        self._config = configuracion

    def url_de_autorizacion(self, state: str) -> str:
        """`state` is the CSRF defence: it comes back and must match what was sent."""
        parametros = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": ALCANCE,
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{URL_AUTORIZACION}?{urlencode(parametros)}"

    async def perfil_desde_codigo(self, codigo: str) -> PerfilDeGoogle:
        datos = await self._con_reintentos(
            lambda cliente: cliente.post(
                URL_TOKEN,
                data={
                    "code": codigo,
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "redirect_uri": self._config.redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        )
        access_token = datos.get("access_token")
        if not access_token:
            raise OAuthFallido("Google no devolvio un access token")

        perfil = await self._con_reintentos(
            lambda cliente: cliente.get(
                URL_PERFIL, headers={"Authorization": f"Bearer {access_token}"}
            )
        )
        return self._a_perfil(perfil)

    @staticmethod
    def _a_perfil(datos: dict[str, object]) -> PerfilDeGoogle:
        correo = datos.get("email")
        nombre = datos.get("name") or correo
        if not isinstance(correo, str) or not isinstance(nombre, str):
            raise OAuthFallido("El perfil de Google no trae email")
        # Google says whether it verified the address. An unverified one would let
        # somebody claim an account by asserting an email they do not control.
        if datos.get("email_verified") is False:
            raise OAuthFallido("El email de Google no esta verificado")
        try:
            return PerfilDeGoogle(email=Email(correo), nombre=nombre)
        except EntradaInvalida as exc:
            raise OAuthFallido(f"Google devolvio un email invalido: {exc}") from exc

    async def _con_reintentos(
        self, llamada: object
    ) -> dict[str, object]:  # pragma: no cover — exercised through a fake in tests
        ultimo: Exception | None = None
        for intento in range(1, MAX_INTENTOS + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                    respuesta = await llamada(cliente)  # type: ignore[operator]
                    respuesta.raise_for_status()
                    cuerpo: dict[str, object] = respuesta.json()
                    return cuerpo
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo = exc
                logger.warning("google_oauth_reintento", intento=intento, motivo=str(exc))
                await asyncio.sleep(ESPERA_BASE * (2 ** (intento - 1)))
            except httpx.HTTPStatusError as exc:
                # A 4xx is our request being wrong; retrying would only repeat it.
                raise OAuthFallido(f"Google respondio {exc.response.status_code}") from exc
        raise OAuthFallido(f"Google no respondio tras {MAX_INTENTOS} intentos: {ultimo}")
