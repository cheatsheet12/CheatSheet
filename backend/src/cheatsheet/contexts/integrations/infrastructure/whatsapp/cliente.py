"""The HTTP half of the WhatsApp adapter: two GETs, a timeout and a bounded retry.

Both calls are reads. **This unit writes nothing into Meta** — registering a number is
done by the Administrator in Meta Business Manager, and we only ask what state it is in.
That is worth stating because it is what makes retrying safe: a repeated GET cannot
duplicate anything.

The transport is injectable so the contract tests can drive `httpx.MockTransport` instead
of monkeypatching a module-level function. Nothing in the suite opens a socket.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from cheatsheet.contexts.integrations.application.errors import (
    ConexionRechazada,
    ProveedorNoDisponible,
)
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

URL_BASE_POR_DEFECTO = "https://graph.facebook.com"
VERSION_POR_DEFECTO = "v21.0"
TIMEOUT_POR_DEFECTO = 10.0
MAX_INTENTOS = 3
ESPERA_BASE = 0.5

#: Fields asked for explicitly. Graph API returns a minimal object otherwise, and a
#: default that changes underneath us is a silent loss of RN-03's data.
CAMPOS_DEL_NUMERO = (
    "verified_name,code_verification_status,quality_rating,name_status,display_phone_number"
)

#: Meta's error code for "this object does not exist / you cannot see it".
CODIGO_OBJETO_INEXISTENTE = 100


@dataclass(frozen=True, slots=True)
class ConfiguracionWhatsApp:
    url_base: str = URL_BASE_POR_DEFECTO
    version: str = VERSION_POR_DEFECTO
    timeout_segundos: float = TIMEOUT_POR_DEFECTO
    max_intentos: int = MAX_INTENTOS
    espera_base: float = ESPERA_BASE


class ClienteGraph:
    """Talks to Graph API. Raises this context's errors, never httpx's."""

    def __init__(
        self,
        config: ConfiguracionWhatsApp,
        transporte: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transporte = transporte

    async def numero(self, *, token: str, phone_number_id: str) -> dict[str, Any]:
        """The state of one phone number. This is what decides everything downstream."""
        return await self._get(
            f"/{phone_number_id}", token=token, params={"fields": CAMPOS_DEL_NUMERO}
        )

    async def numeros_de_la_cuenta(self, *, token: str, waba_id: str) -> list[dict[str, Any]]:
        """The numbers of one WhatsApp Business Account.

        Used for one check only: that the number the Administrator declared actually
        belongs to the account they declared. Without it, a token with access to several
        accounts could be pointed at somebody else's number by a typo.
        """
        cuerpo = await self._get(f"/{waba_id}/phone_numbers", token=token, params={})
        datos = cuerpo.get("data")
        return [item for item in datos if isinstance(item, dict)] if isinstance(datos, list) else []

    async def _get(self, ruta: str, *, token: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self._config.url_base.rstrip('/')}/{self._config.version}{ruta}"
        cabeceras = {"Authorization": f"Bearer {token}"}
        ultimo: Exception | None = None

        for intento in range(1, self._config.max_intentos + 1):
            try:
                async with self._cliente() as cliente:
                    respuesta = await cliente.get(url, headers=cabeceras, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                ultimo = exc
                # The token is in the headers, never in what gets logged.
                logger.warning("whatsapp_reintento", ruta=ruta, intento=intento, motivo=str(exc))
                await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))
                continue

            if respuesta.status_code < httpx.codes.BAD_REQUEST:
                return _cuerpo(respuesta)
            if _vale_la_pena_reintentar(respuesta.status_code):
                ultimo = ProveedorNoDisponible(f"Meta respondio {respuesta.status_code}")
                logger.warning(
                    "whatsapp_reintento", ruta=ruta, intento=intento, estado=respuesta.status_code
                )
                await asyncio.sleep(self._config.espera_base * (2 ** (intento - 1)))
                continue
            # Any other 4xx is our request being wrong; repeating it changes nothing.
            raise _rechazo(respuesta)

        raise ProveedorNoDisponible(
            f"Meta no respondio tras {self._config.max_intentos} intentos: {ultimo}"
        )

    def _cliente(self) -> httpx.AsyncClient:
        if self._transporte is not None:
            return httpx.AsyncClient(
                timeout=self._config.timeout_segundos, transport=self._transporte
            )
        return httpx.AsyncClient(timeout=self._config.timeout_segundos)


def _vale_la_pena_reintentar(estado: int) -> bool:
    """429 and 5xx are Meta having a moment; everything else in 4xx is us."""
    return estado == httpx.codes.TOO_MANY_REQUESTS or estado >= httpx.codes.INTERNAL_SERVER_ERROR


def _cuerpo(respuesta: httpx.Response) -> dict[str, Any]:
    try:
        datos = respuesta.json()
    except ValueError as exc:
        raise ProveedorNoDisponible("Meta respondio algo que no es JSON") from exc
    if not isinstance(datos, dict):
        raise ProveedorNoDisponible("Meta respondio un JSON con una forma inesperada")
    return datos


def _rechazo(respuesta: httpx.Response) -> ConexionRechazada:
    """Translate a 4xx into the sentence the Administrator sees on the card."""
    detalle = ""
    codigo: object = None
    try:
        error = respuesta.json().get("error", {})
    except ValueError:
        error = {}
    if isinstance(error, dict):
        mensaje = error.get("message")
        detalle = mensaje if isinstance(mensaje, str) else ""
        codigo = error.get("code")

    if respuesta.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
        return ConexionRechazada(
            "Meta rechazo el token: es invalido o no tiene permisos sobre este numero"
        )
    if codigo == CODIGO_OBJETO_INEXISTENTE:
        return ConexionRechazada(
            "Meta no encontro el identificador del numero o de la cuenta declarada"
        )
    return ConexionRechazada(f"Meta rechazo la consulta ({respuesta.status_code}): {detalle}")
