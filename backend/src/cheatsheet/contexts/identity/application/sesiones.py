"""Sign-in, refresh and sign-out (HU-E1-01, ADR-011).

The refresh chain is the part worth reading carefully. Every refresh **rotates**: the
presented token is marked used and a new one is issued. If a token that was already used
comes back, that is not a retry — the only way it happens is that two parties hold the
same token, which means one of them stole it. The reaction is to revoke the entire
family, so the legitimate user is forced to sign in again and the thief loses access
too. Revoking only the presented token would let both keep rotating forever.

Refresh and sign-out are serialized per family: both take the family lock before reading
the token, so a concurrent rotation, reuse or logout on the same family cannot interleave
with the check-then-write below.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from cheatsheet.contexts.identity.application.errors import (
    CredencialesInvalidas,
    ReusoDeRefreshDetectado,
    SesionInvalida,
)
from cheatsheet.contexts.identity.application.ports import (
    PortEmisorDeTokens,
    PortHashDeContrasena,
    PortRepositorioRefreshToken,
    PortRepositorioUsuario,
)
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import Email
from cheatsheet.platform.telemetry import obtener_logger

logger = obtener_logger(__name__)


@dataclass(frozen=True, slots=True)
class Sesion:
    """What the BFF turns into cookies."""

    access_token: str
    access_expira_en: datetime
    refresh_token: str
    refresh_expira_en: datetime
    usuario: Usuario


class EmisorDeSesiones:
    """Builds a session and persists the refresh link. Shared by sign-in and refresh."""

    def __init__(
        self,
        *,
        tokens: PortEmisorDeTokens,
        refrescos: PortRepositorioRefreshToken,
        vida_refresh: timedelta,
    ) -> None:
        self._tokens = tokens
        self._refrescos = refrescos
        self._vida_refresh = vida_refresh

    async def emitir(
        self, usuario: Usuario, ahora: datetime, familia_id: UUID | None = None
    ) -> Sesion:
        acceso = self._tokens.emitir_acceso(
            usuario_id=usuario.id,
            empresa_id=usuario.empresa_id,
            rol=usuario.rol.value,
            ahora=ahora,
        )
        refresh = self._tokens.emitir_refresh(ahora)
        await self._refrescos.agregar(
            RefreshToken(
                id=uuid4(),
                # A refresh keeps its family; a fresh sign-in starts a new one.
                familia_id=familia_id or uuid4(),
                empresa_id=usuario.empresa_id,
                usuario_id=usuario.id,
                # Only the hash is stored: a database dump must not be a set of live
                # sessions.
                hash_del_token=self._tokens.hashear_refresh(refresh.valor),
                expira_en=ahora + self._vida_refresh,
            )
        )
        return Sesion(
            access_token=acceso.valor,
            access_expira_en=acceso.expira_en,
            refresh_token=refresh.valor,
            refresh_expira_en=ahora + self._vida_refresh,
            usuario=usuario,
        )


class IniciarSesion:
    """Email and password.

    Every failure raises the same error. Telling apart "no such email" from "wrong
    password" turns the login form into an account enumerator, and the accounts here
    belong to companies with their tax data inside.
    """

    def __init__(
        self,
        *,
        usuarios: PortRepositorioUsuario,
        hasher: PortHashDeContrasena,
        emisor: EmisorDeSesiones,
    ) -> None:
        self._usuarios = usuarios
        self._hasher = hasher
        self._emisor = emisor

    async def ejecutar(self, *, email: Email, contrasena: str, ahora: datetime) -> Sesion:
        usuario = await self._usuarios.buscar_por_email(email)
        if usuario is None or usuario.hash_de_contrasena is None:
            raise CredencialesInvalidas("Email o contrasena incorrectos")
        if not self._hasher.verificar(contrasena, usuario.hash_de_contrasena):
            raise CredencialesInvalidas("Email o contrasena incorrectos")
        # HU-E1-06 RN-01: a deactivated user loses access immediately — including the
        # ability to obtain a new session.
        if not usuario.activo:
            raise CredencialesInvalidas("Email o contrasena incorrectos")
        return await self._emisor.emitir(usuario, ahora)


class RefrescarSesion:
    """Rotate the refresh token, or detect that it was stolen."""

    def __init__(
        self,
        *,
        usuarios: PortRepositorioUsuario,
        refrescos: PortRepositorioRefreshToken,
        tokens: PortEmisorDeTokens,
        emisor: EmisorDeSesiones,
    ) -> None:
        self._usuarios = usuarios
        self._refrescos = refrescos
        self._tokens = tokens
        self._emisor = emisor

    async def ejecutar(self, *, refresh_token: str, ahora: datetime) -> Sesion:
        guardado = await self._refrescos.tomar_con_familia_bloqueada(
            self._tokens.hashear_refresh(refresh_token)
        )
        if guardado is None:
            raise SesionInvalida("El refresh token no existe")

        if guardado.fue_usado:
            revocados = await self._refrescos.revocar_familia(guardado.familia_id)
            logger.warning(
                "reuso_de_refresh_detectado",
                familia_id=str(guardado.familia_id),
                usuario_id=str(guardado.usuario_id),
                tokens_revocados=revocados,
            )
            raise ReusoDeRefreshDetectado("El refresh token ya habia sido usado")

        if not guardado.es_utilizable(ahora):
            raise SesionInvalida("El refresh token esta vencido o revocado")

        usuario = await self._usuarios.buscar_por_id(guardado.usuario_id)
        if usuario is None or not usuario.activo:
            raise SesionInvalida("El usuario ya no puede operar")

        guardado.marcar_usado(ahora)
        await self._refrescos.guardar(guardado)
        return await self._emisor.emitir(usuario, ahora, guardado.familia_id)


class CerrarSesion:
    """Sign-out revokes the whole family, not just the presented token.

    Otherwise the sibling tokens of that sign-in stay alive, and "I logged out" would be
    false in exactly the situation where a user says it because they are worried.
    """

    def __init__(
        self, *, refrescos: PortRepositorioRefreshToken, tokens: PortEmisorDeTokens
    ) -> None:
        self._refrescos = refrescos
        self._tokens = tokens

    async def ejecutar(self, *, refresh_token: str) -> None:
        guardado = await self._refrescos.tomar_con_familia_bloqueada(
            self._tokens.hashear_refresh(refresh_token)
        )
        if guardado is not None:
            await self._refrescos.revocar_familia(guardado.familia_id)
