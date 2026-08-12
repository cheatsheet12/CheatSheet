"""Resolution of the current tenant.

**This is a placeholder with a deliberate expiry date.** The real source of
`tenant_id` is the authenticated JWT, and authentication is the next unit
(`identidad-y-onboarding`). Until it lands, the header below lets the rest of the
platform be built and tested end to end.

The dangerous version of this shortcut is one that survives into production, so it
cannot: outside `local` and `test` the header is ignored entirely and the request is
rejected. A tenant taken from a client-supplied header in production would let anyone
read anyone's data by editing a curl command.
"""

from __future__ import annotations

from cheatsheet.platform.settings import Entorno, Settings
from cheatsheet.shared.tenant import TenantId, tenant_id_desde
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

HEADER_TENANT = "X-Tenant-Id"
ATRIBUTO_TENANT = "tenant_id"

# Endpoints that exist before, or outside, any company.
RUTAS_SIN_TENANT = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class TenantMiddleware(BaseHTTPMiddleware):
    """Puts the current `TenantId` on `request.state`, or refuses the request."""

    def __init__(self, app: object, settings: Settings) -> None:
        super().__init__(app)  # type: ignore[arg-type]  # starlette types this as ASGIApp
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in RUTAS_SIN_TENANT:
            return await call_next(request)

        tenant = self._resolver(request)
        if tenant is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "SinTenant", "detalle": "La empresa no pudo determinarse."},
            )
        setattr(request.state, ATRIBUTO_TENANT, tenant)
        return await call_next(request)

    def _resolver(self, request: Request) -> TenantId | None:
        if self._settings.entorno not in (Entorno.LOCAL, Entorno.TEST):
            # Deployed environments: only the JWT may say who you are. It does not
            # exist yet, so nothing does — and refusing is the safe direction.
            return None
        crudo = request.headers.get(HEADER_TENANT, "").strip()
        if not crudo:
            return None
        try:
            return tenant_id_desde(crudo)
        except ValueError:
            return None
