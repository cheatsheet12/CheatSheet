"""Google Sheets, behind its own Anti-Corruption Layer (ADR-008).

The application sees `DocumentoVinculado` and `HojaDePlanilla`; a Google payload stops
here. Microsoft models the same idea with different words, and the day Excel Online is
implemented the difference has to end in this layer rather than reach a use case.

**The scope is `drive.file`, and that is RN-01 in one word.** It grants access to the
files the user picked through Google's own picker, and to nothing else in their Drive.
The alternative Google offers — `spreadsheets` — reads every spreadsheet the account can
open, which for a business owner is their accountant's files, their payroll and their
bank exports. The story says «permisos de lectura sobre el archivo específico
seleccionado, no sobre todo el Drive», and this constant is where that becomes true.

Timeout, bounded retries and failure handling on every call, as CLAUDE.md §5 requires and
as the three epic 2 adapters already do.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from cheatsheet.contexts.integrations.application.credenciales_oauth import CredencialOAuthRevocada
from cheatsheet.contexts.spreadsheet_sync.application.errors import (
    PermisosDePlanillaInsuficientes,
    ProveedorDePlanillaNoDisponible,
)
from cheatsheet.contexts.spreadsheet_sync.application.ports import (
    DocumentoVinculado,
    FilaLeida,
    HojaDePlanilla,
    PlanillaLeida,
    TokensDePlanilla,
)
from cheatsheet.contexts.spreadsheet_sync.domain.valores import MENSAJE_SIN_PERMISOS
from cheatsheet.platform.settings import Entorno
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)

URL_AUTORIZACION = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 — endpoint, not a secret
URL_HOJAS = "https://sheets.googleapis.com/v4/spreadsheets"

#: RN-01. Per-file access, never the whole Drive. See the module docstring.
ALCANCE = "https://www.googleapis.com/auth/drive.file"

TIMEOUT_SEGUNDOS = 15.0
MAX_INTENTOS = 3
ESPERA_BASE = 0.5
FILAS_POR_LOTE = 500
LIMITE_LECTURA_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ConfiguracionGoogleSheets:
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def esta_configurado(self) -> bool:
        return all((self.client_id, self.client_secret, self.redirect_uri))


class ProveedorGoogleSheets:
    """`PortProveedorDePlanilla` against the real Google APIs."""

    def __init__(self, configuracion: ConfiguracionGoogleSheets) -> None:
        if not configuracion.esta_configurado:
            raise RuntimeError(
                "Google Sheets no esta configurado: faltan GOOGLE_OAUTH_CLIENT_ID, "
                "GOOGLE_OAUTH_CLIENT_SECRET o GOOGLE_OAUTH_REDIRECT_URI"
            )
        self._config = configuracion

    def url_de_autorizacion(self, *, estado: str) -> str:
        parametros = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": ALCANCE,
            "state": estado,
            # Without this Google returns no refresh token on the second consent, and the
            # link silently stops working an hour later.
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{URL_AUTORIZACION}?{urlencode(parametros)}"

    async def canjear_codigo(self, codigo: str) -> TokensDePlanilla:
        datos = {
            "code": codigo,
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "redirect_uri": self._config.redirect_uri,
            "grant_type": "authorization_code",
        }
        respuesta = await self._pedir("POST", URL_TOKEN, data=datos)
        token = respuesta.get("access_token")
        renovacion = respuesta.get("refresh_token")
        if (
            not isinstance(token, str)
            or not token
            or not isinstance(renovacion, str)
            or not renovacion
        ):
            # A code that buys no token is a consent the user did not give -- an expired
            # code looks the same from here, and both mean no link is created (RN-01).
            raise PermisosDePlanillaInsuficientes(MENSAJE_SIN_PERMISOS)
        return TokensDePlanilla(acceso=token, renovacion=renovacion)

    async def renovar(self, credencial: bytes) -> str:
        """Exchange one encrypted-at-rest renewal credential for a short-lived access token."""
        try:
            respuesta = await self._pedir(
                "POST",
                URL_TOKEN,
                data={
                    "refresh_token": credencial.decode("utf-8"),
                    "client_id": self._config.client_id,
                    "client_secret": self._config.client_secret,
                    "grant_type": "refresh_token",
                },
            )
        except PermisosDePlanillaInsuficientes as exc:
            raise CredencialOAuthRevocada("Google revoco la autorizacion de Sheets") from exc
        acceso = respuesta.get("access_token")
        if not isinstance(acceso, str) or not acceso:
            raise CredencialOAuthRevocada("Google no devolvio un nuevo acceso a Sheets")
        return acceso

    async def describir_documento(self, *, token: str, identificador: str) -> DocumentoVinculado:
        respuesta = await self._pedir(
            "GET",
            f"{URL_HOJAS}/{identificador}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "properties.title,sheets.properties"},
        )
        hojas = tuple(
            HojaDePlanilla(
                nombre=str(hoja["properties"]["title"]),
                filas_estimadas=int(
                    hoja["properties"].get("gridProperties", {}).get("rowCount", 0)
                ),
            )
            for hoja in respuesta.get("sheets", [])
            if "properties" in hoja
        )
        if not hojas:
            raise ProveedorDePlanillaNoDisponible(
                "Google devolvio una planilla sin hojas: revisa que el documento exista"
            )
        return DocumentoVinculado(
            identificador_externo=identificador,
            nombre=str(respuesta.get("properties", {}).get("title", identificador)),
            hojas=hojas,
        )

    async def leer_hoja(
        self,
        *,
        token: str,
        identificador: str,
        hoja: str,
        max_filas: int | None = None,
    ) -> PlanillaLeida:
        """Read formatted cell text in bounded requests, preserving Google row numbers."""
        documento = await self.describir_documento(token=token, identificador=identificador)
        fuente = next((item for item in documento.hojas if item.nombre == hoja), None)
        if fuente is None:
            raise ProveedorDePlanillaNoDisponible("La hoja vinculada ya no existe en Google Sheets")
        hasta = fuente.filas_estimadas
        if max_filas is not None:
            hasta = min(hasta, max_filas)
        columnas: tuple[str, ...] = ()
        filas: list[FilaLeida] = []
        tamanio = 0
        nombre_rango = hoja.replace("'", "''")
        for inicio in range(1, hasta + 1, FILAS_POR_LOTE):
            fin = min(inicio + FILAS_POR_LOTE - 1, hasta)
            rango = quote(f"'{nombre_rango}'!{inicio}:{fin}", safe="")
            respuesta = await self._pedir(
                "GET",
                f"{URL_HOJAS}/{identificador}/values/{rango}",
                headers={"Authorization": f"Bearer {token}"},
                params={"valueRenderOption": "FORMATTED_VALUE"},
            )
            valores = respuesta.get("values", [])
            if not isinstance(valores, list):
                raise ProveedorDePlanillaNoDisponible("Google devolvio filas con formato invalido")
            for numero, celdas in enumerate(valores, start=inicio):
                if not isinstance(celdas, list):
                    raise ProveedorDePlanillaNoDisponible("Google devolvio una fila invalida")
                textos = tuple(str(valor).strip() for valor in celdas)
                tamanio += sum(len(valor.encode("utf-8")) for valor in textos)
                if tamanio > LIMITE_LECTURA_BYTES:
                    raise ProveedorDePlanillaNoDisponible(
                        "La planilla supera el limite de 25 MB para procesar"
                    )
                if numero == 1:
                    columnas = textos
                elif any(textos):
                    filas.append(
                        FilaLeida(
                            numero=numero,
                            celdas={
                                columna: textos[indice] if indice < len(textos) else ""
                                for indice, columna in enumerate(columnas)
                            },
                        )
                    )
        return PlanillaLeida(columnas=columnas, filas=tuple(filas))

    async def _pedir(self, metodo: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """One call, with the timeout and bounded retry CLAUDE.md §5 requires.

        A 4xx is not retried: Google has decided, and asking three times only delays the
        message the user is waiting for. Timeouts and 5xx are.
        """
        ultimo: Exception | None = None
        for intento in range(1, MAX_INTENTOS + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                    respuesta = await cliente.request(metodo, url, **kwargs)
                if respuesta.status_code in (401, 403):
                    raise PermisosDePlanillaInsuficientes(MENSAJE_SIN_PERMISOS)
                if url == URL_TOKEN and respuesta.status_code == 400:
                    raise PermisosDePlanillaInsuficientes(MENSAJE_SIN_PERMISOS)
                if 400 <= respuesta.status_code < 500 and respuesta.status_code != 429:
                    raise ProveedorDePlanillaNoDisponible(
                        f"Google rechazo la consulta con {respuesta.status_code}"
                    )
                respuesta.raise_for_status()
                cuerpo: dict[str, Any] = respuesta.json()
                return cuerpo
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                ultimo = exc
                if intento < MAX_INTENTOS:
                    await asyncio.sleep(ESPERA_BASE * (2 ** (intento - 1)))

        logger.warning("google_sheets_sin_respuesta", intentos=MAX_INTENTOS)
        raise ProveedorDePlanillaNoDisponible(
            "No pudimos comunicarnos con Google Sheets. Intentalo de nuevo en un momento."
        ) from ultimo


class ProveedorDePlanillaSimulado:
    """The stand-in. Walks the whole flow and opens no socket.

    **Rejected in production**, like the three epic 2 simulators: a company believing its
    spreadsheet is linked when nothing ever reached Google is a company whose catalogue
    will never fill and who will not know why.

    The authorisation code doubles as the document id, prefixed, so a test and a manual
    run through the panel exercise the same path the real callback takes.
    """

    PREFIJO = "simulado:"

    def __init__(
        self, entorno: Entorno = Entorno.LOCAL, *, callback: str = "/api/planillas/google/callback"
    ) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                "El proveedor de planillas simulado no es valido en produccion: "
                "ninguna planilla llegaria a vincularse de verdad."
            )
        self._callback = callback

    def url_de_autorizacion(self, *, estado: str) -> str:
        # Points back at our own callback, so the flow completes without leaving the app.
        return f"{self._callback}?state={estado}&code={self.PREFIJO}planilla-de-prueba"

    async def canjear_codigo(self, codigo: str) -> TokensDePlanilla:
        if not codigo.startswith(self.PREFIJO):
            raise PermisosDePlanillaInsuficientes(MENSAJE_SIN_PERMISOS)
        return TokensDePlanilla(
            acceso=f"token-{codigo.removeprefix(self.PREFIJO)}",
            renovacion="",
        )

    async def describir_documento(self, *, token: str, identificador: str) -> DocumentoVinculado:
        del token
        return DocumentoVinculado(
            identificador_externo=identificador,
            nombre="Planilla de prueba",
            hojas=(HojaDePlanilla(nombre="Clientes", filas_estimadas=120),),
        )

    async def leer_hoja(
        self,
        *,
        token: str,
        identificador: str,
        hoja: str,
        max_filas: int | None = None,
    ) -> PlanillaLeida:
        del token, identificador, hoja, max_filas
        return PlanillaLeida(
            columnas=("Nombre", "CUIT"),
            filas=(FilaLeida(numero=2, celdas={"Nombre": "Cliente de prueba", "CUIT": ""}),),
        )
