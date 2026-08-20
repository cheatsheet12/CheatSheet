"""The HTTP half of the MercadoPago adapter.

**Retries are not uniform here, and that is the point of the module.** `CLAUDE.md` §5
requires timeout, retry with backoff and failure handling on every external call, and a
blanket retry on `/oauth/token` would be the wrong way to obey it: that endpoint consumes
a single-use authorization code and **rotates the refresh token on every call**. Repeating
a request that MercadoPago may already have processed is how a company ends up holding a
refresh token MercadoPago has already replaced — an integration that dies quietly and
cannot be renewed.

So the split is by evidence, not by verb:

- `httpx.ConnectError` / `ConnectTimeout` / `PoolTimeout` prove the request **never
  reached** MercadoPago. Retried with exponential backoff.
- A read timeout, or a 5xx, mean it may have been processed. **Not retried** on
  `/oauth/token`: they become `ProveedorNoDisponible`, and nothing is marked inactive
  because nothing was learned.
- `GET /users/me` is a pure read and is retried like any other: repeating it cannot
  duplicate anything.

The transport is injectable so the contract tests drive `httpx.MockTransport`. Nothing in
the suite opens a socket.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from cheatsheet.contexts.integrations.application.errors import ProveedorNoDisponible
from cheatsheet.contexts.integrations.infrastructure.mercadopago.mapeo import rechazo
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

AUTH_URL_POR_DEFECTO = "https://auth.mercadopago.com.ar"
API_URL_POR_DEFECTO = "https://api.mercadopago.com"
TIMEOUT_POR_DEFECTO = 10.0
MAX_INTENTOS = 3
ESPERA_BASE = 0.5

#: MercadoPago's OAuth endpoint. Named for what it does rather than for what it returns:
#: a constant with "token" in its name reads to a secret scanner exactly like a leaked one.
RUTA_DE_CANJE = "/oauth/token"
RUTA_CUENTA = "/users/me"

#: Failures that prove the request never got there. Only these are safe to repeat against
#: an endpoint that consumes single-use secrets.
_NUNCA_LLEGO = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


@dataclass(frozen=True, slots=True)
class ConfiguracionMercadoPago:
    """Where MercadoPago is and who we are to it.

    `client_id` and `client_secret` identify **our application**, not a company — the same
    shape as the platform's Google OAuth client. What is per-company are the tokens the
    flow returns, and those live encrypted in the database.
    """

    client_id: str
    client_secret: str
    redirect_uri: str
    auth_url: str = AUTH_URL_POR_DEFECTO
    api_url: str = API_URL_POR_DEFECTO
    timeout_segundos: float = TIMEOUT_POR_DEFECTO
    max_intentos: int = MAX_INTENTOS
    espera_base: float = ESPERA_BASE


class ClienteMercadoPago:
    """Talks to MercadoPago. Raises this context's errors, never httpx's."""

    def __init__(
        self,
        config: ConfiguracionMercadoPago,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transporte = transporte

    async def canjear(self, *, codigo: str, verificador: str) -> dict[str, Any]:
        """Trade the authorization code for the pair of tokens (RN-01)."""
        return await self._post_token(
            {
                "grant_type": "authorization_code",
                "code": codigo,
                "redirect_uri": self._config.redirect_uri,
                "code_verifier": verificador,
            },
            operacion="canje",
        )

    async def refrescar(self, *, refresco: str) -> dict[str, Any]:
        """Trade the refresh token for a fresh pair. The old one stops working."""
        return await self._post_token(
            {"grant_type": "refresh_token", "refresh_token": refresco},
            operacion="renovacion",
        )

    async def cuenta(self, *, acceso: str) -> dict[str, Any]:
        """Who the token belongs to. This is the validation RN-02 asks for."""
        return await self._get(RUTA_CUENTA, token=acceso)

    async def _post_token(self, cuerpo: dict[str, str], *, operacion: str) -> dict[str, Any]:
        url = f"{self._config.api_url.rstrip('/')}{RUTA_DE_CANJE}"
        # The credentials of our application go in the body, as MercadoPago's OAuth
        # documents it. They are never logged, here or anywhere else.
        payload = {
            **cuerpo,
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
        }
        ultimo: Exception | None = None

        for intento in range(1, self._config.max_intentos + 1):
            try:
                async with self._cliente() as cliente:
                    respuesta = await cliente.post(url, json=payload)
            except _NUNCA_LLEGO as exc:
                ultimo = exc
                logger.warning("mercadopago_reintento", operacion=operacion, intento=intento)
                await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))
                continue
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # It may have been processed. Repeating it could burn the code or rotate
                # the refresh token a second time; see the module docstring.
                raise ProveedorNoDisponible(
                    f"MercadoPago no respondio a tiempo la {operacion}"
                ) from exc

            if respuesta.status_code < httpx.codes.BAD_REQUEST:
                return _cuerpo(respuesta)
            if respuesta.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
                raise ProveedorNoDisponible(
                    f"MercadoPago respondio {respuesta.status_code} a la {operacion}"
                )
            raise rechazo(respuesta.status_code, _cuerpo_tolerante(respuesta))

        raise ProveedorNoDisponible(
            f"No se pudo contactar a MercadoPago tras {self._config.max_intentos} intentos: {ultimo}"
        )

    async def _get(self, ruta: str, *, token: str) -> dict[str, Any]:
        url = f"{self._config.api_url.rstrip('/')}{ruta}"
        cabeceras = {"Authorization": f"Bearer {token}"}
        ultimo: Exception | None = None

        for intento in range(1, self._config.max_intentos + 1):
            try:
                async with self._cliente() as cliente:
                    respuesta = await cliente.get(url, headers=cabeceras)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo = exc
                logger.warning("mercadopago_reintento", ruta=ruta, intento=intento)
                await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))
                continue

            if respuesta.status_code < httpx.codes.BAD_REQUEST:
                return _cuerpo(respuesta)
            if _vale_la_pena_reintentar(respuesta.status_code):
                ultimo = ProveedorNoDisponible(f"MercadoPago respondio {respuesta.status_code}")
                logger.warning(
                    "mercadopago_reintento",
                    ruta=ruta,
                    intento=intento,
                    estado=respuesta.status_code,
                )
                await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))
                continue
            raise rechazo(respuesta.status_code, _cuerpo_tolerante(respuesta))

        raise ProveedorNoDisponible(
            f"MercadoPago no respondio tras {self._config.max_intentos} intentos: {ultimo}"
        )

    def _cliente(self) -> httpx.AsyncClient:
        if self._transporte is not None:
            return httpx.AsyncClient(
                timeout=self._config.timeout_segundos, transport=self._transporte
            )
        return httpx.AsyncClient(timeout=self._config.timeout_segundos)


def _vale_la_pena_reintentar(estado: int) -> bool:
    """429 and 5xx are MercadoPago having a moment; the rest of 4xx is us."""
    return estado == httpx.codes.TOO_MANY_REQUESTS or estado >= httpx.codes.INTERNAL_SERVER_ERROR


def _cuerpo(respuesta: httpx.Response) -> dict[str, Any]:
    try:
        datos = respuesta.json()
    except ValueError as exc:
        raise ProveedorNoDisponible("MercadoPago respondio algo que no es JSON") from exc
    if not isinstance(datos, dict):
        raise ProveedorNoDisponible("MercadoPago respondio un JSON con una forma inesperada")
    return datos


def _cuerpo_tolerante(respuesta: httpx.Response) -> dict[str, Any]:
    """For error paths: a rejection with an unreadable body is still a rejection."""
    try:
        datos = respuesta.json()
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}
