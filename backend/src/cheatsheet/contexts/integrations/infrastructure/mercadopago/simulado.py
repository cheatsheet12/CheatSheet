"""A stand-in for MercadoPago, for every environment without a sandbox application.

Same guard rails as the other three: it validates nothing against a real service, and
**constructing it in `production` raises** — a `RuntimeError` at build time, before the
process serves a request.

**It walks the whole OAuth2 dance, including the redirect.** `url_de_autorizacion` returns
the panel's own return URL with a fabricated code attached, so pressing "Conectar" on a
laptop leaves the app, comes back, and completes exactly as it would against MercadoPago —
`state` check, PKCE verifier, code exchange and all. A stand-in that skipped the round trip
would leave the one part of this unit most likely to break untested outside production.

Four codes are reserved so the awkward outcomes can be demonstrated without a real
account: a rejected authorization, a real account (which the environment cross-check must
refuse), and a token that will later be reported as revoked when the daily renewal runs.
"""

from __future__ import annotations

import secrets
from typing import Any

from cheatsheet.contexts.integrations.application.errors import ConexionRechazada
from cheatsheet.contexts.integrations.application.ports import (
    MaterialDeConexion,
    PedidoDeAutorizacion,
    ResultadoDeConexion,
    ResultadoDeVerificacion,
)
from cheatsheet.contexts.integrations.domain.valores import (
    CLAVE_VERIFICADOR,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.mercadopago.mapeo import (
    CLAVE_CUENTA_REAL,
    ETIQUETA_DE_PRUEBA,
    desempaquetar,
    empaquetar,
    es_cuenta_real,
    estado_por_ambiente,
    leer_tokens,
    parametros_de,
    parametros_de_cuenta,
)
from cheatsheet.platform.settings import Entorno
from cheatsheet.shared.clock import Reloj

#: Marks every fabricated token. One of these reaching MercadoPago would be rejected,
#: which is the right outcome and better than a blob that looks plausible.
PREFIJO_SIMULADO = "SIMULADO"

#: Reserved codes. They travel in the `code` query parameter of the fake redirect, so any
#: of them can be reached by hand from the browser's address bar.
CODIGO_RECHAZADO = f"{PREFIJO_SIMULADO}-rechazado"
CODIGO_CUENTA_REAL = f"{PREFIJO_SIMULADO}-real"
#: Connects normally and then fails the first renewal, so RN-03 — inactive plus a notice —
#: can be demonstrated without waiting six months.
CODIGO_REVOCABLE = f"{PREFIJO_SIMULADO}-revocable"

#: About 180 days, like the real one, so the renewal margin is exercised with a realistic
#: number instead of a token that expires immediately.
DURACION_SEGUNDOS = 180 * 24 * 60 * 60

_MARCA_REVOCABLE = "revocable"


class MercadoPagoSimulado:
    """Implements the four ports MercadoPago needs: authorize, connect, verify, renew."""

    def __init__(self, *, entorno: Entorno, reloj: Reloj, redirect_uri: str) -> None:
        if entorno is Entorno.PRODUCTION:
            raise RuntimeError(
                f"El adaptador simulado de {SistemaExterno.MERCADOPAGO.value} no puede usarse "
                f"en produccion. Configura las credenciales reales del proveedor."
            )
        self._reloj = reloj
        self._redirect_uri = redirect_uri
        self._es_produccion = False

    def url_de_autorizacion(self, pedido: PedidoDeAutorizacion) -> str:
        """Straight back to where we came from, with a code that this class will accept."""
        codigo = f"{PREFIJO_SIMULADO}-{secrets.token_urlsafe(8)}"
        separador = "&" if "?" in self._redirect_uri else "?"
        return f"{self._redirect_uri}{separador}code={codigo}&state={pedido.estado}"

    async def conectar(self, material: MaterialDeConexion) -> ResultadoDeConexion:
        codigo = material.contenido.decode("utf-8", errors="ignore").strip()
        if not codigo:
            raise ConexionRechazada("La autorizacion de MercadoPago volvio sin codigo")
        if not material.efimeros.get(CLAVE_VERIFICADOR, "").strip():
            raise ConexionRechazada("Esta autorizacion de MercadoPago no puede completarse")
        if codigo == CODIGO_RECHAZADO:
            raise ConexionRechazada(
                "MercadoPago rechazo la autorizacion: el codigo ya fue usado o vencio. "
                "Volve a iniciar la conexion."
            )

        tokens = leer_tokens(
            self._respuesta_de_token(revocable=codigo == CODIGO_REVOCABLE), self._reloj.ahora()
        )
        cuenta = self._cuenta(real=codigo == CODIGO_CUENTA_REAL)
        estado, detalle = estado_por_ambiente(es_cuenta_real(cuenta), self._es_produccion)
        if estado is EstadoDeConexion.NO_CONECTADO:
            raise ConexionRechazada(detalle or "La cuenta de MercadoPago no corresponde")
        return ResultadoDeConexion(
            credencial=empaquetar(tokens.acceso, tokens.refresco),
            estado=estado,
            detalle=detalle,
            parametros=parametros_de(tokens, cuenta),
        )

    async def verificar(
        self, credencial: bytes, parametros: dict[str, Any]
    ) -> ResultadoDeVerificacion:
        desempaquetar(credencial)
        estado, detalle = estado_por_ambiente(
            bool(parametros.get(CLAVE_CUENTA_REAL)), self._es_produccion
        )
        if estado is EstadoDeConexion.NO_CONECTADO:
            estado = EstadoDeConexion.ATENCION
        return ResultadoDeVerificacion(
            estado, detalle, parametros_de_cuenta(self._cuenta(real=False))
        )

    async def renovar(self, credencial: bytes) -> ResultadoDeConexion:
        _, refresco = desempaquetar(credencial)
        if _MARCA_REVOCABLE in refresco:
            raise ConexionRechazada(
                "MercadoPago rechazo la renovacion: el acceso fue revocado desde la cuenta. "
                "Volve a conectarla."
            )
        tokens = leer_tokens(self._respuesta_de_token(revocable=False), self._reloj.ahora())
        return ResultadoDeConexion(
            credencial=empaquetar(tokens.acceso, tokens.refresco),
            parametros=parametros_de(tokens),
        )

    def _respuesta_de_token(self, *, revocable: bool) -> dict[str, Any]:
        """The payload MercadoPago would answer, shaped exactly like the real one.

        Fabricated and then read back through the real `leer_tokens`, so the translation
        that decides what gets stored is the same code on a laptop and in production.
        """
        sufijo = _MARCA_REVOCABLE if revocable else secrets.token_urlsafe(6)
        return {
            "access_token": f"{PREFIJO_SIMULADO}-acceso-{secrets.token_urlsafe(6)}",
            "refresh_token": f"{PREFIJO_SIMULADO}-refresco-{sufijo}",
            "expires_in": DURACION_SEGUNDOS,
            "user_id": 123456789,
            # Always true, as MercadoPago answers for test accounts too: the account kind is
            # on `/users/me`, which is where the real adapter reads it.
            "live_mode": True,
            "scope": "offline_access read write",
        }

    def _cuenta(self, *, real: bool) -> dict[str, Any]:
        """What `/users/me` would answer. Fake data only — no real seller exists here."""
        return {
            "id": 123456789,
            "nickname": "VENDEDOR-SIMULADO",
            "email": "vendedor.simulado@example.invalid",
            "site_id": "MLA",
            "tags": ["normal"] if real else [ETIQUETA_DE_PRUEBA, "normal"],
        }
