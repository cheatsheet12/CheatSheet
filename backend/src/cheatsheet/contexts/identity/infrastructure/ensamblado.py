"""Wiring of the identity context onto one unit of work.

The composition root (`api/dependencies.py`) knows *that* contexts get assembled; this
knows *how* this one does. Keeping it here means adding a use case does not touch the
shared root, and the root does not grow a branch per context.

Everything below is request-scoped, for the same reason the audit subscriber is: the
repositories write through the session that the caller's transaction owns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from cheatsheet.api.dependencies import UnidadDeTrabajo
from cheatsheet.contexts.identity.application.ports import (
    PortEmisorDeTokens,
    PortHashDeContrasena,
    PortRepositorioEmpresa,
    PortRepositorioRefreshToken,
    PortRepositorioUsuario,
)
from cheatsheet.contexts.identity.application.sesiones import EmisorDeSesiones
from cheatsheet.contexts.identity.infrastructure.oauth_google import (
    ConfiguracionOAuthGoogle,
    ProveedorOAuthGoogle,
)
from cheatsheet.contexts.identity.infrastructure.repositories import (
    RepositorioEmpresaPostgres,
    RepositorioRefreshTokenPostgres,
    RepositorioUsuarioPostgres,
)
from cheatsheet.contexts.identity.infrastructure.seguridad import EmisorDeTokensJWT, HasherArgon2
from cheatsheet.platform.settings import Settings

#: Argon2 builds its parameter table on construction. One instance per process is plenty
#: and saves that work on every sign-in.
_HASHER = HasherArgon2()


@dataclass(frozen=True, slots=True)
class Identidad:
    """The identity context's adapters, bound to one transaction."""

    empresas: PortRepositorioEmpresa
    usuarios: PortRepositorioUsuario
    refrescos: PortRepositorioRefreshToken
    hasher: PortHashDeContrasena
    tokens: PortEmisorDeTokens
    emisor: EmisorDeSesiones

    @classmethod
    def armar(cls, unidad: UnidadDeTrabajo, settings: Settings) -> Identidad:
        tokens = EmisorDeTokensJWT(
            secreto=settings.jwt_secret,
            vida_acceso=timedelta(minutes=settings.jwt_access_ttl_minutos),
        )
        refrescos = RepositorioRefreshTokenPostgres(unidad.sesion)
        return cls(
            empresas=RepositorioEmpresaPostgres(unidad.sesion),
            usuarios=RepositorioUsuarioPostgres(unidad.sesion),
            refrescos=refrescos,
            hasher=_HASHER,
            tokens=tokens,
            emisor=EmisorDeSesiones(
                tokens=tokens,
                refrescos=refrescos,
                vida_refresh=timedelta(days=settings.refresh_ttl_dias),
            ),
        )


def proveedor_google(settings: Settings) -> ProveedorOAuthGoogle | None:
    """`None` when Google is not configured.

    The process still boots without it: a missing OAuth client should make one endpoint
    refuse, not stop the whole API from starting in an environment that does not use it.
    """
    if not settings.google_oauth_configurado:
        return None
    return ProveedorOAuthGoogle(
        ConfiguracionOAuthGoogle(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.google_oauth_redirect_uri,
        )
    )
