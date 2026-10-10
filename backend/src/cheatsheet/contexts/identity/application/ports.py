"""Ports of the identity context."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.invitacion import Invitacion
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    Email,
    EstadoUsuario,
    HashDeContrasena,
    RolUsuario,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.fiscal import CondicionIVA


@dataclass(frozen=True, slots=True)
class DatosFiscalesDePadron:
    """What ARCA's registry says about a tax id, in this context's own words.

    A DTO of `identity`, not of `integrations`, even though the two currently look alike.
    That is the Anti-Corruption Layer being a layer: `infrastructure/padron.py` translates,
    and if ARCA — or whoever replaces it — starts answering something else, exactly one
    file changes.
    """

    razon_social: str | None
    condicion_iva: CondicionIVA | None
    #: `False` when the tax id exists but is deregistered. Worth telling the Administrator
    #: about; not a reason to refuse the data.
    activo: bool


class PortPadron(Protocol):
    """Asks ARCA's registry about one tax id, on behalf of one company.

    The only door between `identity` and `integrations`, and it is deliberately narrow:
    a CUIT goes in, a description comes back. No ticket, no credential, no knowledge that
    ARCA speaks SOAP.

    Three outcomes, and the implementation must keep them apart:

    - the data, when the registry knows the tax id;
    - `None`, when it does not — which blocks the Administrator (RN-01);
    - `PadronNoDisponible`, when it could not be asked — which must not.
    """

    async def consultar(
        self, *, empresa_id: EmpresaId, cuit: str
    ) -> DatosFiscalesDePadron | None: ...


class PadronNoDisponible(RuntimeError):
    """The registry could not be asked. Never means "that tax id does not exist"."""


class PortRepositorioEmpresa(Protocol):
    async def agregar(self, empresa: Empresa) -> None: ...
    async def guardar(self, empresa: Empresa) -> None: ...
    async def buscar_por_id(self, empresa_id: EmpresaId) -> Empresa | None: ...
    async def existe_cuit(self, cuit: str) -> bool: ...
    async def bloquear(self, empresa_id: EmpresaId) -> None:
        """Serialise the operations that can leave a company without an Administrator.

        Counting active administrators and then acting on the count is a check-then-act:
        two administrators demoting each other at the same moment both pass the count and
        the company ends up with none. This takes a row lock on the company first, so the
        second one waits and then reads a count that already includes the first one's
        change. It is the one place in the system where losing a race means being locked
        out of your own account.
        """
        ...


class PortRepositorioUsuario(Protocol):
    async def agregar(self, usuario: Usuario) -> None: ...
    async def guardar(self, usuario: Usuario) -> None: ...
    async def eliminar(self, usuario_id: UsuarioId) -> None:
        """Only ever used on a revoked invitation — see `RevocarInvitacion`."""
        ...

    async def buscar_por_id(self, usuario_id: UsuarioId) -> Usuario | None: ...
    async def buscar_por_email(self, email: Email) -> Usuario | None:
        """Global lookup, outside any company: sign-in happens before there is a tenant."""
        ...

    async def listar_de_empresa(self, empresa_id: EmpresaId) -> Sequence[Usuario]:
        """PAN-USR-01's list. Row-Level Security is what keeps it to one company."""
        ...

    async def contar_administradores_activos(self, empresa_id: EmpresaId) -> int:
        """HU-E1-05 RN-02. Counts `ADMINISTRADOR` **and** `ACTIVO`, never a pending invite."""
        ...


@dataclass(frozen=True, slots=True)
class EstadoActualDelUsuario:
    """The three columns that decide whether a session may operate, as the database has them now.

    Not a `Usuario`: the check runs on **every authenticated request**, and hydrating the
    aggregate would also read the preferences document it never looks at.
    """

    empresa_id: EmpresaId
    rol: RolUsuario
    estado: EstadoUsuario


class PortConsultaDeUsuarioVigente(Protocol):
    """Reads the current state of one user, for the per-request session check.

    A port of its own and not one more method of `PortRepositorioUsuario`: it is read-only,
    it is called far more often than anything else in the context, and it must stay a single
    cheap statement. Folding it into the repository would invite someone to make it hydrate
    the aggregate "for consistency".
    """

    async def estado_actual(self, usuario_id: UsuarioId) -> EstadoActualDelUsuario | None:
        """`None` when there is no such user **in the company the session is scoped to**."""
        ...


class PortRepositorioInvitacion(Protocol):
    async def agregar(self, invitacion: Invitacion) -> None: ...
    async def guardar(self, invitacion: Invitacion) -> None: ...
    async def buscar_por_id(self, invitacion_id: UUID) -> Invitacion | None: ...
    async def buscar_por_hash(self, hash_del_token: str) -> Invitacion | None: ...
    async def listar_pendientes_de_empresa(self, empresa_id: EmpresaId) -> Sequence[Invitacion]:
        """All at once, not one query per row: PAN-USR-01 needs an id on every pending row
        to offer "resend" and "revoke", and asking per user would be an N+1 on the one
        screen that lists users."""
        ...


class PortRepositorioRefreshToken(Protocol):
    async def agregar(self, token: RefreshToken) -> None: ...
    async def guardar(self, token: RefreshToken) -> None: ...
    async def buscar_por_hash(self, hash_del_token: str) -> RefreshToken | None: ...
    async def tomar_con_familia_bloqueada(self, hash_del_token: str) -> RefreshToken | None:
        """Lock the token's family, then return the token (`None` if it does not exist).

        The lock lasts until the end of the transaction, which the unit of work owns. While
        held, no other transaction rotates, revokes or signs out that family, and the token
        returned already reflects everything committed before the lock was granted.
        """
        ...

    async def revocar_familia(self, familia_id: UUID) -> int:
        """Revoke every token of a family. Returns how many were revoked."""
        ...

    async def revocar_de_usuario(self, usuario_id: UsuarioId) -> int:
        """Every live session of one user, for HU-E1-06 RN-01."""
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


class PortTokenDeInvitacion(Protocol):
    """Separate from `PortEmisorDeTokens` even though both make random strings.

    They answer different questions and change for different reasons: one is the session
    lifecycle of ADR-011, the other is a single-use link with a configurable expiry that
    travels by email. Folding them together would make a change to either affect both.
    """

    def emitir(self) -> str: ...
    def hashear(self, token: str) -> str: ...


@dataclass(frozen=True, slots=True)
class MensajeDeInvitacion:
    """Everything the email needs, with the token separated on purpose.

    The token is the credential. Keeping it as its own field — instead of letting each
    caller paste a URL together — is what lets the adapter build the link one way and
    lets the logging never print it.
    """

    destinatario: Email
    nombre_de_empresa: str
    invitado_por: str
    token: str
    expira_en: datetime


class PortEnvioDeEmail(Protocol):
    """Transactional email.

    `docs/architecture.md` §7 declares `PortNotificacionEmail` for `reporting` and
    `payments` and it was never implemented. This one is declared **here**, because that
    is what hexagonal asks for: a context declares the ports its own use cases need.
    Whether the adapter is worth extracting somewhere shared is a question for the second
    consumer — answering it now, with one, would be guessing the shape the second needs.
    """

    async def enviar_invitacion(self, mensaje: MensajeDeInvitacion) -> None:
        """Raises `EnvioDeEmailFallido`. The caller decides whether that is fatal."""
        ...
