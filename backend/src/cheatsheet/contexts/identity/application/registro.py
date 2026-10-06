"""Registration — step 1 of the onboarding (HU-E1-01, HU-E1-03).

Creates the `Empresa` and its first `Usuario` **in one transaction**. Half of that pair
is not a usable state: a company nobody can sign in to, or a user belonging to nothing.

The `EmpresaId` is generated here, before anything touches the database, and that is not
incidental — Row-Level Security scopes every statement to `app.current_empresa`, so the
identifier has to exist before the transaction opens in order to be announced. The
caller opens the unit of work with it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from cheatsheet.contexts.identity.application.errors import EmailYaRegistrado
from cheatsheet.contexts.identity.application.ports import (
    PortHashDeContrasena,
    PortRepositorioEmpresa,
    PortRepositorioUsuario,
)
from cheatsheet.contexts.identity.domain.empresa import Empresa
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    Email,
    RolUsuario,
    validar_contrasena_en_claro,
)
from cheatsheet.shared.auditoria import EventoAuditable, Modulo, Resultado
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.events import PublicadorDeEventos


@dataclass(frozen=True, slots=True)
class EmpresaRegistrada:
    empresa: Empresa
    usuario: Usuario


class RegistrarEmpresa:
    """Sign-up with email and password, plus the acceptance of the terms."""

    def __init__(
        self,
        *,
        empresas: PortRepositorioEmpresa,
        usuarios: PortRepositorioUsuario,
        hasher: PortHashDeContrasena,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._empresas = empresas
        self._usuarios = usuarios
        self._hasher = hasher
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        email: Email,
        contrasena: str,
        nombre: str,
        version_terminos: str,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> EmpresaRegistrada:
        validar_contrasena_en_claro(contrasena)
        if await self._usuarios.buscar_por_email(email) is not None:
            raise EmailYaRegistrado(f"Ya existe una cuenta con el email {email}")

        empresa = Empresa(id=empresa_id)
        # HU-E1-03 RN-02: acceptance is part of completing the registration, not a
        # later step. A company that exists without accepted terms would be a company
        # operating outside the contract it never signed.
        empresa.aceptar_terminos(version_terminos, ahora)

        usuario = Usuario(
            id=UsuarioId(uuid4()),
            empresa_id=empresa_id,
            email=email,
            nombre=nombre,
            # HU-E1-01: whoever registers the company administers it.
            rol=RolUsuario.ADMINISTRADOR,
            hash_de_contrasena=self._hasher.hashear(contrasena),
        )

        await self._empresas.agregar(empresa)
        await self._usuarios.agregar(usuario)
        await self._publicar(empresa_id, usuario, ahora, direccion_ip, "registrar_empresa")
        return EmpresaRegistrada(empresa=empresa, usuario=usuario)

    async def _publicar(
        self,
        empresa_id: EmpresaId,
        usuario: Usuario,
        ahora: datetime,
        direccion_ip: str | None,
        accion: str,
    ) -> None:
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.IDENTITY,
                accion=accion,
                entidad_afectada=f"Empresa:{empresa_id}",
                resultado=Resultado.COMPLETADO,
                usuario_id=usuario.id,
                direccion_ip=direccion_ip,
            )
        )


class RegistrarConGoogle:
    """Sign-up through OAuth2 (HU-E1-01 RN-02).

    The account has no password, and that is the accurate model: this person never chose
    one on this platform. Inventing a random hash so the column is filled would be
    inventing a credential.
    """

    def __init__(
        self,
        *,
        empresas: PortRepositorioEmpresa,
        usuarios: PortRepositorioUsuario,
        publicador: PublicadorDeEventos,
    ) -> None:
        self._empresas = empresas
        self._usuarios = usuarios
        self._publicador = publicador

    async def ejecutar(
        self,
        *,
        empresa_id: EmpresaId,
        email: Email,
        nombre: str,
        version_terminos: str,
        ahora: datetime,
        direccion_ip: str | None = None,
    ) -> EmpresaRegistrada:
        if await self._usuarios.buscar_por_email(email) is not None:
            raise EmailYaRegistrado(f"Ya existe una cuenta con el email {email}")

        empresa = Empresa(id=empresa_id)
        empresa.aceptar_terminos(version_terminos, ahora)
        usuario = Usuario(
            id=UsuarioId(uuid4()),
            empresa_id=empresa_id,
            email=email,
            nombre=nombre,
            rol=RolUsuario.ADMINISTRADOR,
            hash_de_contrasena=None,
        )

        await self._empresas.agregar(empresa)
        await self._usuarios.agregar(usuario)
        await self._publicador.publicar(
            EventoAuditable(
                evento_id=uuid4(),
                empresa_id=empresa_id,
                ocurrido_en=ahora,
                modulo=Modulo.IDENTITY,
                accion="registrar_empresa_con_google",
                entidad_afectada=f"Empresa:{empresa_id}",
                resultado=Resultado.COMPLETADO,
                usuario_id=usuario.id,
                direccion_ip=direccion_ip,
            )
        )
        return EmpresaRegistrada(empresa=empresa, usuario=usuario)
