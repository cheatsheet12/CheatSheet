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

from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.sesion import RefreshToken
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    CUIT,
    CondicionIVA,
    Email,
    HashDeContrasena,
    RolUsuario,
    TerminosAceptados,
)
from cheatsheet.contexts.identity.infrastructure.models import (
    EmpresaORM,
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


def _usuario_a_dominio(fila: UsuarioORM) -> Usuario:
    return Usuario(
        id=UsuarioId(fila.id),
        empresa_id=EmpresaId(fila.empresa_id),
        email=Email(fila.email),
        nombre=fila.nombre,
        rol=RolUsuario(fila.rol),
        activo=fila.activo,
        hash_de_contrasena=(
            HashDeContrasena(fila.hash_de_contrasena) if fila.hash_de_contrasena else None
        ),
        pref_idioma=fila.pref_idioma,
        pref_zona_horaria=fila.pref_zona_horaria,
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
                activo=usuario.activo,
                pref_idioma=usuario.pref_idioma,
                pref_zona_horaria=usuario.pref_zona_horaria,
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
        fila.activo = usuario.activo
        fila.pref_idioma = usuario.pref_idioma
        fila.pref_zona_horaria = usuario.pref_zona_horaria
        fila.hash_de_contrasena = (
            usuario.hash_de_contrasena.valor if usuario.hash_de_contrasena else None
        )
        await self._sesion.flush()

    async def buscar_por_id(self, usuario_id: UsuarioId) -> Usuario | None:
        fila = await self._sesion.get(UsuarioORM, usuario_id)
        return _usuario_a_dominio(fila) if fila is not None else None

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
            activo=fila["activo"],
            hash_de_contrasena=(
                HashDeContrasena(fila["hash_de_contrasena"]) if fila["hash_de_contrasena"] else None
            ),
        )


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
