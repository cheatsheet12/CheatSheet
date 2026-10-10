"""Resolution of the current company and user, from the access token **and the database**.

The development header this module used to read is gone: the signed JWT issued by the
identity context is the only source of *who is claiming to ask*. It is no longer the source
of what that person may do. The token says who and which company, as of the moment it was
issued; whether that user still exists, is still `ACTIVO` and which role they hold **now**
is asked of the database on every request (HU-E1-05, HU-E1-06). `request.state` carries the
database's answer, never the token's.

Two outcomes are kept deliberately apart:

- the session is **revoked** (no such user, not `ACTIVO`, another company): 401, with exactly
  the body of a missing token, so a stolen token teaches its holder nothing;
- the check **could not run** (database down or slow): 503. Failing open would hand the
  window this check exists to close to anyone who can load the database, and answering 401
  would sign every user out of the panel during an outage.

Routes that exist *before* a session — sign-up, sign-in, the OAuth callback, the
healthcheck — are listed below and skip the check. Everything else needs a valid token
or it does not run.
"""

from __future__ import annotations

from typing import Protocol

import jwt
from cheatsheet.contexts.identity.application.errors import (
    SesionRevocada,
    VerificacionNoDisponible,
)
from cheatsheet.contexts.identity.application.verificacion_de_sesion import IdentidadVigente
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
        "/health/live",
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
        # HU-E1-03 RN-05, HU-E1-08 RN-06: the texts must be readable by someone who has not
        # signed up yet. Exact paths, never the `/legal/` prefix.
        "/legal/terminos",
        "/legal/privacidad",
        "/legal/vigentes",
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
#: The second entry is the accountant's link (HU-E10-06). It needs a prefix because the
#: credential is in the path: `/contador/<token>` and `/contador/<token>/paquetes/<id>`.
#: What authenticates the request is the token itself -- its SHA-256 digest is looked up in
#: `token_de_acceso_contable`, and `revocado` and `vencimiento` are checked inside the route
#: (`api/routers/contador.py`). Nothing else in the system answers without a session.
#:
#: A prefix set is more dangerous than an exact one, so it stays at two entries and the
#: docstring says why: anything added here is a route that answers to the open internet.
PREFIJOS_PUBLICOS: tuple[str, ...] = ("/webhooks/", "/contador/")


class VerificadorDeSesion(Protocol):
    """Turns a token's claims into the identity the database vouches for right now.

    Raises `SesionRevocada` when the user may no longer operate, and `VerificacionNoDisponible`
    when the check could not run (the database is down or slow). The adapter translates its
    own driver's errors, so this module knows nothing about any of them. Anything else is a
    bug, and a bug answers 500.
    """

    async def verificar(
        self, *, usuario_id: UsuarioId, empresa_id_del_token: EmpresaId
    ) -> IdentidadVigente: ...


def _sin_sesion() -> JSONResponse:
    """The one answer for "you are not signed in", whatever the reason.

    A missing, forged, expired or revoked credential is the same body on purpose: the
    difference is never told to the caller, only to the log.
    """
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": "NoAutenticado", "detalle": "Se requiere iniciar sesion."},
    )


def _servicio_no_disponible() -> JSONResponse:
    """The session was not found revoked; the system just cannot tell. Not a 401."""
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "ServicioNoDisponible",
            "detalle": "No pudimos verificar tu sesion. Reintenta en unos segundos.",
        },
    )


class EmpresaMiddleware(BaseHTTPMiddleware):
    """Puts the authenticated company, user and role on `request.state`, or refuses."""

    def __init__(self, app: object, settings: Settings, verificador: VerificadorDeSesion) -> None:
        super().__init__(app)  # type: ignore[arg-type]  # starlette types this as ASGIApp
        self._settings = settings
        self._verificador = verificador

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in RUTAS_PUBLICAS or request.url.path.startswith(PREFIJOS_PUBLICOS):
            return await call_next(request)

        reclamos = self._reclamos(request)
        if reclamos is None:
            return _sin_sesion()
        identidad = await self._verificar(request, *reclamos)
        if isinstance(identidad, Response):
            return identidad

        # The database's answer, not the token's. `rol` is stored as its string value
        # because that is what every router already reads.
        setattr(request.state, ATRIBUTO_EMPRESA, identidad.empresa_id)
        setattr(request.state, ATRIBUTO_USUARIO, identidad.usuario_id)
        setattr(request.state, ATRIBUTO_ROL, identidad.rol.value)
        # The verifier has already given its connection back: nothing is held while the
        # route runs.
        return await call_next(request)

    async def _verificar(
        self, request: Request, empresa_id: EmpresaId, usuario_id: UsuarioId
    ) -> IdentidadVigente | Response:
        try:
            return await self._verificador.verificar(
                usuario_id=usuario_id, empresa_id_del_token=empresa_id
            )
        except SesionRevocada as revocada:
            # The reason goes to the log and never into the response. No token, no email.
            logger.info("sesion_revocada", motivo=revocada.motivo.value, ruta=request.url.path)
            return _sin_sesion()
        except VerificacionNoDisponible as error:
            logger.error(
                "verificacion_de_sesion_no_disponible",
                tipo=type(error.causa).__name__,
                ruta=request.url.path,
                exc_info=error,
            )
            return _servicio_no_disponible()

    def _reclamos(self, request: Request) -> tuple[EmpresaId, UsuarioId] | None:
        """The signed claims that say who is asking. Their `rol` is deliberately not read."""
        cabecera = request.headers.get("Authorization", "")
        if not cabecera.startswith("Bearer "):
            return None
        try:
            datos = decodificar_acceso(
                cabecera.removeprefix("Bearer ").strip(), self._settings.jwt_secret
            )
            return empresa_id_desde(datos["empresa_id"]), usuario_id_desde(datos["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            # An expired, forged or malformed token is the same answer: no session. The
            # difference is never told to the caller, only to the log.
            logger.info("token_de_acceso_rechazado", ruta=request.url.path)
            return None
