"""The invitation cycle (HU-E1-04): invite, resend, revoke, accept.

**The token in clear text exists exactly once, in memory, in the request that creates
it.** Only its hash is persisted, so from the moment the transaction commits there is no
way — not for us, not for anyone with the database — to recover the link. That is why
`InvitarUsuario` returns it: whoever calls has to hand it to the email task right there or
lose it. Anything else would mean storing a live credential.

**Accepting is a pre-tenant operation**, like signing in: the person has no session, and
the company is discovered *from the token*. See `api/dependencies.py` for how the
transaction gets opened with the right `empresa_id` — writing under the wrong one is
rejected by Row-Level Security, silently in the case of an `UPDATE`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from cheatsheet.contexts.identity.application.autorizacion import exigir_administrador
from cheatsheet.contexts.identity.application.errors import (
    EmailYaRegistrado,
    InvitacionInvalida,
)
from cheatsheet.contexts.identity.application.ports import (
    PortHashDeContrasena,
    PortRepositorioInvitacion,
    PortRepositorioUsuario,
    PortTokenDeInvitacion,
)
from cheatsheet.contexts.identity.application.sesiones import EmisorDeSesiones, Sesion
from cheatsheet.contexts.identity.application.usuarios import publicar_cambio
from cheatsheet.contexts.identity.domain.invitacion import Invitacion
from cheatsheet.contexts.identity.domain.usuario import NOMBRE_PENDIENTE, Usuario
from cheatsheet.contexts.identity.domain.valores import (
    Email,
    EstadoUsuario,
    RolUsuario,
    validar_contrasena_en_claro,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos


@dataclass(frozen=True, slots=True)
class InvitacionEmitida:
    """The caller gets the token **once**, to hand to the email task and forget."""

    invitacion: Invitacion
    usuario: Usuario
    token_en_claro: str


class InvitarUsuario:
    """HU-E1-04.

    Creates the `Usuario` in `INVITADO` and the `Invitacion` in one transaction. Half of
    that pair is not a usable state: a pending invitation pointing at nobody, or a user
    row that nothing can ever activate.
    """

    def __init__(
        self,
        *,
        usuarios: PortRepositorioUsuario,
        invitaciones: PortRepositorioInvitacion,
        tokens: PortTokenDeInvitacion,
        publicador: PublicadorDeEventos,
        vida_invitacion: timedelta,
    ) -> None:
        self._usuarios = usuarios
        self._invitaciones = invitaciones
        self._tokens = tokens
        self._publicador = publicador
        self._vida = vida_invitacion

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        ejecutor_id: UsuarioId,
        rol_del_ejecutor: RolUsuario,
        email: Email,
        rol: RolUsuario,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> InvitacionEmitida:
        exigir_administrador(rol_del_ejecutor)
        # RN-03 forbids two users with the same email *in the company*; the column is
        # unique platform-wide, so the check has to be global or the INSERT fails later
        # with a constraint error nobody can act on.
        if await self._usuarios.buscar_por_email(email) is not None:
            raise EmailYaRegistrado(f"Ya existe una cuenta con el email {email}")

        usuario = Usuario(
            id=UsuarioId(uuid4()),
            empresa_id=empresa_id,
            email=email,
            # They have not told us their name yet; they choose it when they accept.
            nombre=NOMBRE_PENDIENTE,
            rol=rol,
            estado=EstadoUsuario.INVITADO,
            hash_de_contrasena=None,
        )
        token = self._tokens.emitir()
        invitacion = Invitacion(
            id=uuid4(),
            empresa_id=empresa_id,
            usuario_id=usuario.id,
            hash_del_token=self._tokens.hashear(token),
            expira_en=ahora + self._vida,
            invitado_por=ejecutor_id,
        )

        await self._usuarios.agregar(usuario)
        await self._invitaciones.agregar(invitacion)
        await publicar_cambio(
            self._publicador,
            empresa_id=empresa_id,
            ejecutor_id=ejecutor_id,
            accion="invitar_usuario",
            entidad=f"Usuario:{usuario.id} rol {rol.value}",
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
        return InvitacionEmitida(invitacion=invitacion, usuario=usuario, token_en_claro=token)


class ReenviarInvitacion:
    """HU-E1-04 RN-04. Issues a new token and kills the old one."""

    def __init__(
        self,
        *,
        usuarios: PortRepositorioUsuario,
        invitaciones: PortRepositorioInvitacion,
        tokens: PortTokenDeInvitacion,
        publicador: PublicadorDeEventos,
        vida_invitacion: timedelta,
    ) -> None:
        self._usuarios = usuarios
        self._invitaciones = invitaciones
        self._tokens = tokens
        self._publicador = publicador
        self._vida = vida_invitacion

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        ejecutor_id: UsuarioId,
        rol_del_ejecutor: RolUsuario,
        invitacion_id: UUID,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> InvitacionEmitida:
        exigir_administrador(rol_del_ejecutor)
        invitacion = await _cargar_invitacion(self._invitaciones, invitacion_id)
        token = self._tokens.emitir()
        # Raises if it was already accepted or revoked — RN-04 allows this only while
        # the invitation is pending.
        invitacion.reemplazar_token(self._tokens.hashear(token), ahora + self._vida)
        await self._invitaciones.guardar(invitacion)

        usuario = await self._usuarios.buscar_por_id(invitacion.usuario_id)
        if usuario is None:  # pragma: no cover — the pair is created in one transaction
            raise EntradaInvalida("La invitacion no tiene usuario asociado")
        await publicar_cambio(
            self._publicador,
            empresa_id=empresa_id,
            ejecutor_id=ejecutor_id,
            accion="reenviar_invitacion",
            entidad=f"Usuario:{usuario.id}",
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
        return InvitacionEmitida(invitacion=invitacion, usuario=usuario, token_en_claro=token)


class RevocarInvitacion:
    """HU-E1-04 RN-04.

    **The user row is deleted, not deactivated.** Email is unique across the platform: a
    revoked invitation left as `INACTIVO` would hold that address hostage forever, and
    inviting the same person again would be impossible — which is the most common reason
    somebody revokes in the first place. Nobody who never accepted has any history to
    preserve, and the audit entry records the executor, not the invitee, so nothing is
    lost by removing the row.
    """

    def __init__(
        self,
        *,
        usuarios: PortRepositorioUsuario,
        invitaciones: PortRepositorioInvitacion,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._usuarios = usuarios
        self._invitaciones = invitaciones
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        ejecutor_id: UsuarioId,
        rol_del_ejecutor: RolUsuario,
        invitacion_id: UUID,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> None:
        exigir_administrador(rol_del_ejecutor)
        invitacion = await _cargar_invitacion(self._invitaciones, invitacion_id)
        invitacion.revocar()
        await self._invitaciones.guardar(invitacion)
        await self._usuarios.eliminar(invitacion.usuario_id)
        await publicar_cambio(
            self._publicador,
            empresa_id=empresa_id,
            ejecutor_id=ejecutor_id,
            accion="revocar_invitacion",
            entidad=f"Usuario:{invitacion.usuario_id}",
            ahora=ahora,
            direccion_ip=direccion_ip,
        )


class AceptarInvitacion:
    """HU-E1-04: the invited person chooses a password and the account becomes real.

    Runs with **no session**. Every rejection raises the same `InvitacionInvalida`, for
    the same reason sign-in has one error for three cases: whoever holds a token that is
    not theirs learns only that it does not work.
    """

    def __init__(
        self,
        *,
        usuarios: PortRepositorioUsuario,
        invitaciones: PortRepositorioInvitacion,
        tokens: PortTokenDeInvitacion,
        hasher: PortHashDeContrasena,
        emisor: EmisorDeSesiones,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._usuarios = usuarios
        self._invitaciones = invitaciones
        self._tokens = tokens
        self._hasher = hasher
        self._emisor = emisor
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        token: str,
        nombre: str,
        contrasena: str,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> Sesion:
        validar_contrasena_en_claro(contrasena)
        invitacion = await self._invitaciones.buscar_por_hash(self._tokens.hashear(token))
        if invitacion is None or not invitacion.es_utilizable(ahora):
            raise InvitacionInvalida("La invitacion no es valida o ya fue utilizada")

        usuario = await self._usuarios.buscar_por_id(invitacion.usuario_id)
        if usuario is None or usuario.estado is not EstadoUsuario.INVITADO:
            raise InvitacionInvalida("La invitacion no es valida o ya fue utilizada")

        usuario.aceptar_invitacion(
            nombre=nombre, hash_de_contrasena=self._hasher.hashear(contrasena)
        )
        invitacion.aceptar(ahora)
        await self._usuarios.guardar(usuario)
        await self._invitaciones.guardar(invitacion)
        # The executor is the invited person themself: this is the one action of the
        # cycle that nobody else can perform.
        await publicar_cambio(
            self._publicador,
            empresa_id=invitacion.empresa_id,
            ejecutor_id=usuario.id,
            accion="aceptar_invitacion",
            entidad=f"Usuario:{usuario.id} rol {usuario.rol.value}",
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
        return await self._emisor.emitir(usuario, ahora)


async def _cargar_invitacion(
    invitaciones: PortRepositorioInvitacion, invitacion_id: UUID
) -> Invitacion:
    invitacion = await invitaciones.buscar_por_id(invitacion_id)
    if invitacion is None:
        raise EntradaInvalida("La invitacion no existe en esta empresa")
    return invitacion
