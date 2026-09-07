"""Resolution of the current company, from the authenticated access token.

The development header this module used to read is gone: the JWT issued by the identity
context is now the only source of `empresa_id`. That was the hole the previous unit left
open on purpose, and closing it is part of this one.

Routes that exist *before* a session — sign-up, sign-in, the OAuth callback, the
healthcheck — are listed below and skip the check. Everything else needs a valid token
or it does not run.
"""

from __future__ import annotations

import jwt
from cheatsheet.contexts.identity.infrastructure.seguridad import decodificar_acceso
from cheatsheet.platform.settings import Settings
from cheatsheet.platform.telemetry import obtener_logger
from cheatsheet.shared.empresa import EmpresaId, UsuarioId, empresa_id_desde, usuario_id_desde
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = obtener_logger(__name__)

ATRIBUTO_EMPRESA = "empresa_id"
ATRIBUTO_USUARIO = "usuario_id"
ATRIBUTO_ROL = "rol"

#: Reachable without a session. Everything not listed here requires one.
RUTAS_PUBLICAS = frozenset(
    {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/auth/registro",
        "/auth/registro/google",
        "/auth/login",
        "/auth/google/url",
        "/auth/google/callback",
        "/auth/refresh",
        "/auth/logout",
        # HU-E1-04: the invited person has no session — obtaining one is what accepting
        # gives them. The token in the body is the credential.
        "/auth/invitaciones/aceptar",
    }
)


#: Reachable without a session, matched by prefix instead of exactly.
#:
#: **One entry, and it needs a prefix because the company is in the path.** MercadoPago posts
#: to `/webhooks/mercadopago/<empresa>` with no session and no JWT -- it has neither. What
#: authenticates the request is the HMAC signature, checked inside the route (HS-T1 RN-01),
#: and the company comes from the URL because that is what was registered when the account
#: was connected.
#:
#: A prefix set is more dangerous than an exact one, so it stays at one entry and the
#: docstring says why: anything added here is a route that answers to the open internet.
PREFIJOS_PUBLICOS: tuple[str, ...] = ("/webhooks/",)


class EmpresaMiddleware(BaseHTTPMiddleware):
    """Puts the authenticated company and user on `request.state`, or refuses."""

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]  # starlette types this as ASGIApp
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in RUTAS_PUBLICAS or request.url.path.startswith(PREFIJOS_PUBLICOS):
            return await call_next(request)

        identidad = self._identidad(request)
        if identidad is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "NoAutenticado", "detalle": "Se requiere iniciar sesion."},
            )
        empresa_id, usuario_id, rol = identidad
        setattr(request.state, ATRIBUTO_EMPRESA, empresa_id)
        setattr(request.state, ATRIBUTO_USUARIO, usuario_id)
        setattr(request.state, ATRIBUTO_ROL, rol)
        return await call_next(request)

    def _identidad(self, request: Request) -> tuple[EmpresaId, UsuarioId, str] | None:
        cabecera = request.headers.get("Authorization", "")
        if not cabecera.startswith("Bearer "):
            return None
        try:
            datos = decodificar_acceso(
                cabecera.removeprefix("Bearer ").strip(), self._settings.jwt_secret
            )
            return (
                empresa_id_desde(datos["empresa_id"]),
                usuario_id_desde(datos["sub"]),
                datos["rol"],
            )
        except (jwt.PyJWTError, KeyError, ValueError):
            # An expired, forged or malformed token is the same answer: no session. The
            # difference is never told to the caller, only to the log.
            logger.info("token_de_acceso_rechazado", ruta=request.url.path)
            return None
