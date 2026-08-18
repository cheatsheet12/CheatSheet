"""PostgreSQL adapters for the identity ports.

`buscar_por_email` is the odd one and deserves its explanation. Sign-in happens **before
there is a company**: the whole point of the lookup is to find out which one the person
belongs to. Row-Level Security scopes every statement to `app.current_empresa`, so a
normal query would return nothing and every login would fail.

The answer is not to grant the application `BYPASSRLS` — that would switch the barrier
off for everything, forever, to solve one query. It is a single `SECURITY DEFINER`
function created in migration 0002, `buscar_usuario_para_login`, which returns exactly
one user by email and nothing else. One narrow, named, auditable exception instead of a
blanket one.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.invitacion import Invitacion
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    CUIT,
    CondicionIVA,
    Email,
    EstadoUsuario,
    HashDeContrasena,
    PreferenciasDeNotificacion,
    RolUsuario,
    TerminosAceptados,
)
from cheatsheet.contexts.identity.infrastructure.models import (
    EmpresaORM,
    InvitacionORM,
    RefreshTokenORM,
    UsuarioORM,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId

CONSULTA_LOGIN = text("SELECT * FROM buscar_usuario_para_login(:email)")


def _empresa_a_dominio(fila: EmpresaORM) -> Empresa:
    terminos = None
    if fila.terminos_version and fila.terminos_fecha_aceptacion:
        terminos = TerminosAceptados(
            version=fila.terminos_version, fecha=fila.terminos_fecha_aceptacion
        )
    return Empresa(
        id=EmpresaId(fila.id),
        activa=fila.activa,
        razon_social=fila.razon_social,
        cuit=CUIT(fila.cuit) if fila.cuit else None,
        condicion_iva=CondicionIVA(fila.condicion_iva) if fila.condicion_iva else None,
        nombre_responsable=fila.nombre_responsable,
        email_contacto=Email(fila.email_contacto) if fila.email_contacto else None,
        terminos=terminos,
    )


def _volcar_empresa(empresa: Empresa, fila: EmpresaORM) -> None:
    fila.razon_social = empresa.razon_social
    fila.cuit = empresa.cuit.valor if empresa.cuit else None
    fila.condicion_iva = empresa.condicion_iva.value if empresa.condicion_iva else None
    fila.activa = empresa.activa
    fila.nombre_responsable = empresa.nombre_responsable
    fila.email_contacto = str(empresa.email_contacto) if empresa.email_contacto else None
    fila.terminos_version = empresa.terminos.version if empresa.terminos else None
    fila.terminos_fecha_aceptacion = empresa.terminos.fecha if empresa.terminos else None


class RepositorioEmpresaPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, empresa: Empresa) -> None:
        fila = EmpresaORM(id=empresa.id)
        _volcar_empresa(empresa, fila)
        self._sesion.add(fila)
        await self._sesion.flush()

    async def guardar(self, empresa: Empresa) -> None:
        fila = await self._sesion.get(EmpresaORM, empresa.id)
        if fila is None:
            await self.agregar(empresa)
            return
        _volcar_empresa(empresa, fila)
        await self._sesion.flush()

    async def buscar_por_id(self, empresa_id: EmpresaId) -> Empresa | None:
        fila = await self._sesion.get(EmpresaORM, empresa_id)
        return _empresa_a_dominio(fila) if fila is not None else None

    async def existe_cuit(self, cuit: str) -> bool:
        """Uniqueness is global, so this cannot go through the tenant-scoped table.

        The count runs inside the same `SECURITY DEFINER` boundary as the login lookup,
        for the same reason: the answer has to consider companies the caller cannot see.
        """
        resultado = await self._sesion.execute(
            text("SELECT existe_cuit_registrado(:cuit)"), {"cuit": cuit}
        )
        return bool(resultado.scalar())

    async def bloquear(self, empresa_id: EmpresaId) -> None:
        """`SELECT … FOR UPDATE` on the company row, to serialise the last-Administrator check.

        The company row is the lock rather than the user rows because the rule is about
        the company: the set of users being counted is exactly what a concurrent
        transaction might be changing, so locking the rows we can see would not stop it
        from changing one we cannot.

        The lock is released when the transaction ends, which the unit of work owns.
        """
        await self._sesion.execute(
            select(EmpresaORM.id).where(EmpresaORM.id == empresa_id).with_for_update()
        )


def _usuario_a_dominio(fila: UsuarioORM) -> Usuario:
    return Usuario(
        id=UsuarioId(fila.id),
        empresa_id=EmpresaId(fila.empresa_id),
        email=Email(fila.email),
        nombre=fila.nombre,
        rol=RolUsuario(fila.rol),
        estado=EstadoUsuario(fila.estado),
        hash_de_contrasena=(
            HashDeContrasena(fila.hash_de_contrasena) if fila.hash_de_contrasena else None
        ),
        pref_idioma=fila.pref_idioma,
        pref_zona_horaria=fila.pref_zona_horaria,
        pref_suscripciones=PreferenciasDeNotificacion.desde_json(fila.pref_suscripciones),
    )


class RepositorioUsuarioPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, usuario: Usuario) -> None:
        self._sesion.add(
            UsuarioORM(
                id=usuario.id,
                empresa_id=usuario.empresa_id,
                email=str(usuario.email),
                nombre=usuario.nombre,
                hash_de_contrasena=(
                    usuario.hash_de_contrasena.valor if usuario.hash_de_contrasena else None
                ),
                rol=usuario.rol.value,
                estado=usuario.estado.value,
                pref_idioma=usuario.pref_idioma,
                pref_zona_horaria=usuario.pref_zona_horaria,
                pref_suscripciones=usuario.pref_suscripciones.a_json(),
            )
        )
        await self._sesion.flush()

    async def guardar(self, usuario: Usuario) -> None:
        fila = await self._sesion.get(UsuarioORM, usuario.id)
        if fila is None:
            await self.agregar(usuario)
            return
        fila.nombre = usuario.nombre
        fila.rol = usuario.rol.value
        fila.estado = usuario.estado.value
        fila.pref_idioma = usuario.pref_idioma
        fila.pref_zona_horaria = usuario.pref_zona_horaria
        fila.pref_suscripciones = usuario.pref_suscripciones.a_json()
        fila.hash_de_contrasena = (
            usuario.hash_de_contrasena.valor if usuario.hash_de_contrasena else None
        )
        await self._sesion.flush()

    async def eliminar(self, usuario_id: UsuarioId) -> None:
        """Only for a revoked invitation — see `RevocarInvitacion` for why it is a delete."""
        fila = await self._sesion.get(UsuarioORM, usuario_id)
        if fila is not None:
            await self._sesion.delete(fila)
            await self._sesion.flush()

    async def buscar_por_id(self, usuario_id: UsuarioId) -> Usuario | None:
        fila = await self._sesion.get(UsuarioORM, usuario_id)
        return _usuario_a_dominio(fila) if fila is not None else None

    async def listar_de_empresa(self, empresa_id: EmpresaId) -> Sequence[Usuario]:
        """The `WHERE` is redundant under Row-Level Security and stays anyway.

        RLS is the barrier; this makes the intent readable and keeps the query correct if
        it is ever run as the owner role, as a migration or a fixture would.
        """
        consulta = (
            select(UsuarioORM)
            .where(UsuarioORM.empresa_id == empresa_id)
            .order_by(UsuarioORM.nombre)
        )
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_usuario_a_dominio(fila) for fila in filas]

    async def contar_administradores_activos(self, empresa_id: EmpresaId) -> int:
        """HU-E1-05 RN-02. `INVITADO` is not `ACTIVO`, so a pending admin never counts."""
        consulta = (
            select(func.count())
            .select_from(UsuarioORM)
            .where(UsuarioORM.empresa_id == empresa_id)
            .where(UsuarioORM.rol == RolUsuario.ADMINISTRADOR.value)
            .where(UsuarioORM.estado == EstadoUsuario.ACTIVO.value)
        )
        return int((await self._sesion.execute(consulta)).scalar_one())

    async def buscar_por_email(self, email: Email) -> Usuario | None:
        """Pre-tenant lookup — see the module docstring."""
        resultado = await self._sesion.execute(CONSULTA_LOGIN, {"email": str(email)})
        fila = resultado.mappings().one_or_none()
        if fila is None:
            return None
        return Usuario(
            id=UsuarioId(fila["id"]),
            empresa_id=EmpresaId(fila["empresa_id"]),
            email=Email(fila["email"]),
            nombre=fila["nombre"],
            rol=RolUsuario(fila["rol"]),
            estado=EstadoUsuario(fila["estado"]),
            hash_de_contrasena=(
                HashDeContrasena(fila["hash_de_contrasena"]) if fila["hash_de_contrasena"] else None
            ),
        )


def _invitacion_a_dominio(fila: InvitacionORM) -> Invitacion:
    return Invitacion(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        usuario_id=UsuarioId(fila.usuario_id),
        hash_del_token=fila.hash_del_token,
        expira_en=fila.expira_en,
        invitado_por=UsuarioId(fila.invitado_por),
        aceptada_en=fila.aceptada_en,
        revocada=fila.revocada,
    )


class RepositorioInvitacionPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, invitacion: Invitacion) -> None:
        self._sesion.add(
            InvitacionORM(
                id=invitacion.id,
                empresa_id=invitacion.empresa_id,
                usuario_id=invitacion.usuario_id,
                hash_del_token=invitacion.hash_del_token,
                expira_en=invitacion.expira_en,
                invitado_por=invitacion.invitado_por,
                aceptada_en=invitacion.aceptada_en,
                revocada=invitacion.revocada,
            )
        )
        await self._sesion.flush()

    async def guardar(self, invitacion: Invitacion) -> None:
        fila = await self._sesion.get(InvitacionORM, invitacion.id)
        if fila is None:
            await self.agregar(invitacion)
            return
        # `hash_del_token` and `expira_en` are here because resending replaces them; that
        # overwrite is what makes the previous link stop working.
        fila.hash_del_token = invitacion.hash_del_token
        fila.expira_en = invitacion.expira_en
        fila.aceptada_en = invitacion.aceptada_en
        fila.revocada = invitacion.revocada
        await self._sesion.flush()

    async def buscar_por_id(self, invitacion_id: UUID) -> Invitacion | None:
        fila = await self._sesion.get(InvitacionORM, invitacion_id)
        return _invitacion_a_dominio(fila) if fila is not None else None

    async def buscar_por_hash(self, hash_del_token: str) -> Invitacion | None:
        consulta = select(InvitacionORM).where(InvitacionORM.hash_del_token == hash_del_token)
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        return _invitacion_a_dominio(fila) if fila is not None else None

    async def listar_pendientes_de_empresa(self, empresa_id: EmpresaId) -> Sequence[Invitacion]:
        consulta = (
            select(InvitacionORM)
            .where(InvitacionORM.empresa_id == empresa_id)
            .where(InvitacionORM.aceptada_en.is_(None))
            .where(InvitacionORM.revocada.is_(False))
        )
        filas = (await self._sesion.execute(consulta)).scalars().all()
        return [_invitacion_a_dominio(fila) for fila in filas]


class RepositorioRefreshTokenPostgres:
    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, token: RefreshToken) -> None:
        self._sesion.add(
            RefreshTokenORM(
                id=token.id,
                familia_id=token.familia_id,
                empresa_id=token.empresa_id,
                usuario_id=token.usuario_id,
                hash_del_token=token.hash_del_token,
                expira_en=token.expira_en,
                usado_en=token.usado_en,
                revocado=token.revocado,
            )
        )
        await self._sesion.flush()

    async def guardar(self, token: RefreshToken) -> None:
        fila = await self._sesion.get(RefreshTokenORM, token.id)
        if fila is None:
            await self.agregar(token)
            return
        fila.usado_en = token.usado_en
        fila.revocado = token.revocado
        await self._sesion.flush()

    async def buscar_por_hash(self, hash_del_token: str) -> RefreshToken | None:
        consulta = select(RefreshTokenORM).where(RefreshTokenORM.hash_del_token == hash_del_token)
        fila = (await self._sesion.execute(consulta)).scalar_one_or_none()
        if fila is None:
            return None
        return RefreshToken(
            id=fila.id,
            familia_id=fila.familia_id,
            empresa_id=EmpresaId(fila.empresa_id),
            usuario_id=UsuarioId(fila.usuario_id),
            hash_del_token=fila.hash_del_token,
            expira_en=fila.expira_en,
            usado_en=fila.usado_en,
            revocado=fila.revocado,
        )

    async def revocar_familia(self, familia_id: UUID) -> int:
        resultado = await self._sesion.execute(
            update(RefreshTokenORM)
            .where(RefreshTokenORM.familia_id == familia_id)
            .where(RefreshTokenORM.revocado.is_(False))
            .values(revocado=True)
        )
        await self._sesion.flush()
        return int(resultado.rowcount or 0)

    async def revocar_de_usuario(self, usuario_id: UsuarioId) -> int:
        """Every live session of one user — HU-E1-06 RN-01.

        Families, not just the current one: someone signed in on a phone and a laptop has
        two, and deactivating them has to reach both.
        """
        resultado = await self._sesion.execute(
            update(RefreshTokenORM)
            .where(RefreshTokenORM.usuario_id == usuario_id)
            .where(RefreshTokenORM.revocado.is_(False))
            .values(revocado=True)
        )
        await self._sesion.flush()
        return int(resultado.rowcount or 0)
