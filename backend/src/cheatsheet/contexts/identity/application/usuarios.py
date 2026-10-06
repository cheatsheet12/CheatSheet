"""Administering the users of a company (HU-E1-05, HU-E1-06) and listing them (HU-E1-04).

**The "at least one active Administrator" invariant lives here, not in `Usuario`.** It is
a rule over the whole set of a company's users, and a single aggregate cannot hold a rule
about its siblings. The two operations that can break it — changing a role and
deactivating — are the two that check it, and they check it the same way.

**Listing is not restricted to Administrators, and that is deliberate.** HU-E1-05's third
acceptance criterion says an Operador who enters the Users section finds the role-change
action unavailable — which means the Operador is *in the section*, looking at the list.
So the read is open to any member of the company and only the mutations are guarded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from cheatsheet.contexts.identity.application.autorizacion import exigir_administrador
from cheatsheet.contexts.identity.application.errors import UltimoAdministradorActivo
from cheatsheet.contexts.identity.application.ports import (
    PortRepositorioEmpresa,
    PortRepositorioInvitacion,
    PortRepositorioRefreshToken,
    PortRepositorioUsuario,
)
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import RolUsuario
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.events import PublicadorDeEventos


@dataclass(frozen=True, slots=True)
class UsuarioListado:
    """One row of PAN-USR-01."""

    usuario: Usuario
    #: Present only while the invitation is pending — it is what the "resend" and
    #: "revoke" actions of RN-04 act on.
    invitacion_id: UUID | None


async def publicar_cambio(
    publicador: PublicadorDeEventos,
    *,
    empresa_id: EmpresaId,
    ejecutor_id: UsuarioId,
    accion: str,
    entidad: str,
    ahora: datetime,
    direccion_ip: str | None,
) -> None:
    """The audit entry every administrative change writes (HU-E1-05 RN-04).

    RN-04 asks for the affected user, the previous role, the new role, the executor and
    the timestamp. `usuario_id` carries the **executor** — the log answers "who did this"
    — and the affected user plus the transition go in `entidad_afectada`, which the DER
    models as one string.

    They are not folded into `accion` even though they would fit: epic 10 filters the
    audit panel by action (HU-E12-01), and a filter over a field that embeds two role
    names finds nothing.
    """
    await publicador.publicar(
        EventoAuditable(
            evento_id=uuid4(),
            empresa_id=empresa_id,
            ocurrido_en=ahora,
            modulo=Modulo.IDENTITY,
            accion=accion,
            entidad_afectada=entidad,
            resultado=Resultado.COMPLETADO,
            usuario_id=ejecutor_id,
            direccion_ip=direccion_ip,
        )
    )


class ListarUsuarios:
    """PAN-USR-01's list. Any member of the company may read it."""

    def __init__(
        self,
        *,
        usuarios: PortRepositorioUsuario,
        invitaciones: PortRepositorioInvitacion,
    ) -> None:
        self._usuarios = usuarios
        self._invitaciones = invitaciones

    async def ejecutar(self, *, empresa_id: EmpresaId) -> Sequence[UsuarioListado]:
        """Only this company's users. Row-Level Security is what makes that true, not a
        `WHERE` clause somebody could forget."""
        pendientes = {
            invitacion.usuario_id: invitacion.id
            for invitacion in await self._invitaciones.listar_pendientes_de_empresa(empresa_id)
        }
        return [
            UsuarioListado(usuario=usuario, invitacion_id=pendientes.get(usuario.id))
            for usuario in await self._usuarios.listar_de_empresa(empresa_id)
        ]


class GuardianDelUltimoAdministrador:
    """HU-E1-05 RN-02 and HU-E1-06 RN-03, in one place so they cannot drift apart.

    The lock comes **before** the count, and both come before the change. Counting first
    and locking later would leave the check-then-act race untouched: two administrators
    demoting each other at the same instant would both read "2" and both proceed.
    """

    def __init__(
        self, *, empresas: PortRepositorioEmpresa, usuarios: PortRepositorioUsuario
    ) -> None:
        self._empresas = empresas
        self._usuarios = usuarios

    async def exigir_que_sobreviva_uno(self, *, empresa_id: EmpresaId, afectado: Usuario) -> None:
        if not afectado.es_administrador_activo:
            # Whatever happens to this user, the count of active administrators does not
            # go down — including an invited administrator, who never counted.
            return
        if await self._usuarios.contar_administradores_activos(empresa_id) <= 1:
            raise UltimoAdministradorActivo(
                "La empresa debe conservar al menos un Administrador activo"
            )


class CambiarRolDeUsuario:
    """HU-E1-05."""

    def __init__(
        self,
        *,
        empresas: PortRepositorioEmpresa,
        usuarios: PortRepositorioUsuario,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._empresas = empresas
        self._usuarios = usuarios
        self._guardian = GuardianDelUltimoAdministrador(empresas=empresas, usuarios=usuarios)
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        ejecutor_id: UsuarioId,
        rol_del_ejecutor: RolUsuario,
        usuario_id: UsuarioId,
        rol_nuevo: RolUsuario,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> Usuario:
        exigir_administrador(rol_del_ejecutor)
        await self._empresas.bloquear(empresa_id)
        usuario = await _cargar(self._usuarios, usuario_id)
        rol_anterior = usuario.rol
        if rol_anterior is rol_nuevo:
            return usuario
        if rol_nuevo is not RolUsuario.ADMINISTRADOR:
            await self._guardian.exigir_que_sobreviva_uno(empresa_id=empresa_id, afectado=usuario)

        usuario.cambiar_rol(rol_nuevo)
        await self._usuarios.guardar(usuario)
        await publicar_cambio(
            self._publicador,
            empresa_id=empresa_id,
            ejecutor_id=ejecutor_id,
            accion="cambiar_rol_de_usuario",
            entidad=f"Usuario:{usuario_id} rol {rol_anterior.value}->{rol_nuevo.value}",
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
        return usuario


class DesactivarUsuario:
    """HU-E1-06.

    **Revoking the refresh tokens is what makes RN-01 true.** Without it, "loses access
    immediately" would mean "loses access when the access token expires", and the person
    just removed would keep operating for the rest of its lifetime. Doing better than
    minutes would mean checking the database on every request, which is the cost a short
    JWT exists to avoid.
    """

    def __init__(
        self,
        *,
        empresas: PortRepositorioEmpresa,
        usuarios: PortRepositorioUsuario,
        refrescos: PortRepositorioRefreshToken,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._empresas = empresas
        self._usuarios = usuarios
        self._refrescos = refrescos
        self._guardian = GuardianDelUltimoAdministrador(empresas=empresas, usuarios=usuarios)
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        ejecutor_id: UsuarioId,
        rol_del_ejecutor: RolUsuario,
        usuario_id: UsuarioId,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> Usuario:
        exigir_administrador(rol_del_ejecutor)
        await self._empresas.bloquear(empresa_id)
        usuario = await _cargar(self._usuarios, usuario_id)
        await self._guardian.exigir_que_sobreviva_uno(empresa_id=empresa_id, afectado=usuario)

        usuario.desactivar()
        await self._usuarios.guardar(usuario)
        sesiones = await self._refrescos.revocar_de_usuario(usuario_id)
        await publicar_cambio(
            self._publicador,
            empresa_id=empresa_id,
            ejecutor_id=ejecutor_id,
            accion="desactivar_usuario",
            entidad=f"Usuario:{usuario_id} sesiones revocadas: {sesiones}",
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
        return usuario


class ReactivarUsuario:
    """HU-E1-06 RN-04: back with the role they had.

    No lock and no invariant check: reactivating can only ever add an administrator, never
    remove the last one.
    """

    def __init__(
        self, *, usuarios: PortRepositorioUsuario, publicador: PublicadorDeEventos
    ) -> None:
        self._usuarios = usuarios
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        ejecutor_id: UsuarioId,
        rol_del_ejecutor: RolUsuario,
        usuario_id: UsuarioId,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> Usuario:
        exigir_administrador(rol_del_ejecutor)
        usuario = await _cargar(self._usuarios, usuario_id)
        usuario.reactivar()
        await self._usuarios.guardar(usuario)
        await publicar_cambio(
            self._publicador,
            empresa_id=empresa_id,
            ejecutor_id=ejecutor_id,
            accion="reactivar_usuario",
            entidad=f"Usuario:{usuario_id} rol {usuario.rol.value}",
            ahora=ahora,
            direccion_ip=direccion_ip,
        )
        return usuario


async def _cargar(usuarios: PortRepositorioUsuario, usuario_id: UsuarioId) -> Usuario:
    """A user of another company reads as "does not exist", because under Row-Level
    Security that is literally what the repository sees."""
    usuario = await usuarios.buscar_por_id(usuario_id)
    if usuario is None:
        raise EntradaInvalida("El usuario no existe en esta empresa")
    return usuario
