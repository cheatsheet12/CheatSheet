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
    PortEnvioDeEmail,
    PortHashDeContrasena,
    PortProveedorOAuth,
    PortRepositorioEmpresa,
    PortRepositorioInvitacion,
    PortRepositorioRefreshToken,
    PortRepositorioUsuario,
    PortTokenDeInvitacion,
)
from cheatsheet.contexts.identity.application.sesiones import EmisorDeSesiones
from cheatsheet.contexts.identity.infrastructure.email_invitacion import (
    ConfiguracionSMTP,
    EnviadorDeConsola,
    EnviadorSMTP,
)
from cheatsheet.contexts.identity.infrastructure.oauth_falso import ProveedorOAuthSimulado
from cheatsheet.contexts.identity.infrastructure.oauth_google import (
    ConfiguracionOAuthGoogle,
    ProveedorOAuthGoogle,
)
from cheatsheet.contexts.identity.infrastructure.repositories import (
    RepositorioEmpresaPostgres,
    RepositorioInvitacionPostgres,
    RepositorioRefreshTokenPostgres,
    RepositorioUsuarioPostgres,
)
from cheatsheet.contexts.identity.infrastructure.seguridad import EmisorDeTokensJWT, HasherArgon2
from cheatsheet.contexts.identity.infrastructure.tokens_invitacion import (
    TokenDeInvitacionAleatorio,
)
from cheatsheet.platform.settings import AdaptadorDeEmail, Entorno, Settings

#: Argon2 builds its parameter table on construction. One instance per process is plenty
#: and saves that work on every sign-in.
_HASHER = HasherArgon2()


@dataclass(frozen=True, slots=True)
class Identidad:
    """The identity context's adapters, bound to one transaction."""

    empresas: PortRepositorioEmpresa
    usuarios: PortRepositorioUsuario
    invitaciones: PortRepositorioInvitacion
    refrescos: PortRepositorioRefreshToken
    hasher: PortHashDeContrasena
    tokens: PortEmisorDeTokens
    tokens_de_invitacion: PortTokenDeInvitacion
    emisor: EmisorDeSesiones
    vida_invitacion: timedelta

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
            invitaciones=RepositorioInvitacionPostgres(unidad.sesion),
            refrescos=refrescos,
            hasher=_HASHER,
            tokens=tokens,
            tokens_de_invitacion=TokenDeInvitacionAleatorio(),
            emisor=EmisorDeSesiones(
                tokens=tokens,
                refrescos=refrescos,
                vida_refresh=timedelta(days=settings.refresh_ttl_dias),
            ),
            vida_invitacion=timedelta(days=settings.invitacion_ttl_dias),
        )


def crear_enviador(settings: Settings) -> PortEnvioDeEmail:
    """Pick the email adapter. Process-lifetime: it holds no transaction.

    `Settings` has already refused `consola` in production, so this does not have to
    second-guess the choice — a validation that lives in two places gets relaxed in one
    of them eventually.
    """
    if settings.email_adaptador is AdaptadorDeEmail.CONSOLA:
        return EnviadorDeConsola(settings.app_base_url)
    return EnviadorSMTP(
        ConfiguracionSMTP(
            host=settings.smtp_host,
            puerto=settings.smtp_port,
            usuario=settings.smtp_usuario,
            contrasena=settings.smtp_password,
            remitente=settings.smtp_remitente,
            usar_tls=settings.smtp_tls,
            timeout_segundos=settings.smtp_timeout_segundos,
            url_base_de_la_app=settings.app_base_url,
        )
    )


def proveedor_google(settings: Settings) -> PortProveedorOAuth | None:
    """The real adapter, the simulated one, or `None`.

    Outside production, an environment with no OAuth client gets `ProveedorOAuthSimulado`
    instead of a dead endpoint: HU-E1-01 RN-02 is one of the two ways to create an
    account, and a path nobody can exercise locally is a path that ships broken. The
    simulated provider refuses to be constructed in production, so this cannot silently
    become the way real accounts are created.

    `None` only happens in production without credentials, and there the endpoint
    refuses rather than the process failing to start: one missing integration should not
    stop an API that serves eleven other contexts.
    """
    if not settings.google_oauth_configurado:
        if settings.entorno is Entorno.PRODUCTION:
            return None
        return ProveedorOAuthSimulado(
            url_base_de_la_app=settings.app_base_url, entorno=settings.entorno
        )
    return ProveedorOAuthGoogle(
        ConfiguracionOAuthGoogle(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.google_oauth_redirect_uri,
        )
    )
