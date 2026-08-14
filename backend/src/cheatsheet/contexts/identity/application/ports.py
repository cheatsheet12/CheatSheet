"""Ports of the identity context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import Email, HashDeContrasena
from cheatsheet.shared.empresa import EmpresaId, UsuarioId


class PortRepositorioEmpresa(Protocol):
    async def agregar(self, empresa: Empresa) -> None: ...
    async def guardar(self, empresa: Empresa) -> None: ...
    async def buscar_por_id(self, empresa_id: EmpresaId) -> Empresa | None: ...
    async def existe_cuit(self, cuit: str) -> bool: ...


class PortRepositorioUsuario(Protocol):
    async def agregar(self, usuario: Usuario) -> None: ...
    async def guardar(self, usuario: Usuario) -> None: ...
    async def buscar_por_id(self, usuario_id: UsuarioId) -> Usuario | None: ...
    async def buscar_por_email(self, email: Email) -> Usuario | None:
        """Global lookup, outside any company: sign-in happens before there is a tenant."""
        ...


class PortRepositorioRefreshToken(Protocol):
    async def agregar(self, token: RefreshToken) -> None: ...
    async def guardar(self, token: RefreshToken) -> None: ...
    async def buscar_por_hash(self, hash_del_token: str) -> RefreshToken | None: ...
    async def revocar_familia(self, familia_id: UUID) -> int:
        """Revoke every token of a family. Returns how many were revoked."""
        ...


class PortHashDeContrasena(Protocol):
    """Argon2id (ADR-011). Behind a port so a test never pays its cost."""

    def hashear(self, contrasena: str) -> HashDeContrasena: ...
    def verificar(self, contrasena: str, hash_guardado: HashDeContrasena) -> bool: ...


@dataclass(frozen=True, slots=True)
class PerfilDeGoogle:
    """The only two fields HU-E1-01 RN-02 allows asking Google for."""

    email: Email
    nombre: str


class PortProveedorOAuth(Protocol):
    def url_de_autorizacion(self, state: str) -> str: ...

    async def perfil_desde_codigo(self, codigo: str) -> PerfilDeGoogle:
        """Exchange the authorization code for the profile. Raises `OAuthFallido`."""
        ...


@dataclass(frozen=True, slots=True)
class TokenEmitido:
    valor: str
    expira_en: datetime


class PortEmisorDeTokens(Protocol):
    def emitir_acceso(
        self, *, usuario_id: UsuarioId, empresa_id: EmpresaId, rol: str, ahora: datetime
    ) -> TokenEmitido: ...

    def emitir_refresh(self, ahora: datetime) -> TokenEmitido:
        """A random opaque string. Not a JWT: a refresh token must be revocable."""
        ...

    def hashear_refresh(self, token: str) -> str: ...
