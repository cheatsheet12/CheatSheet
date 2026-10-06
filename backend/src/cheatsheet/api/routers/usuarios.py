"""HTTP surface for administering users and personal preferences (HU-E1-04 … HU-E1-07).

Every route here needs a session; `EmpresaMiddleware` has already verified the access
token and put the company, the user and the role on `request.state`. **The role is passed
down to the use case rather than checked here**: the endpoint is one caller among
several, and the rule belongs next to the operation it guards (see
`application/autorizacion.py`).

**Inviting enqueues the email and never sends it inline.** An SMTP server that is slow
would otherwise make the request slow, and one that is down would make it fail — after
the invitation was already created. The task owns the retry; the endpoint owns the
transaction.
"""

from __future__ import annotations

from typing import TypeVar
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.identity.application.invitaciones import (
    InvitacionEmitida,
    InvitarUsuario,
    ReenviarInvitacion,
    RevocarInvitacion,
)
from cheatsheet.contexts.identity.application.preferencias import (
    ActualizarPreferencias,
    VerPreferencias,
)
from cheatsheet.contexts.identity.application.usuarios import (
    CambiarRolDeUsuario,
    DesactivarUsuario,
    ListarUsuarios,
    ReactivarUsuario,
)
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import (
    Email,
    PreferenciasDeNotificacion,
    RolUsuario,
)
from cheatsheet.contexts.identity.infrastructure.ensamblado import Identidad
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.workers.tasks_identity import encolar_invitacion
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

_T = TypeVar("_T")


class InvitacionEntrada(BaseModel):
    email: str
    rol: RolUsuario


class RolEntrada(BaseModel):
    rol: RolUsuario


class PreferenciasEntrada(BaseModel):
    pref_idioma: str | None = None
    pref_zona_horaria: str | None = None
    #: `{"FACTURACION": ["EMAIL"], …}`. Validated against the closed catalogue by
    #: `PreferenciasDeNotificacion.desde_json`, not by pydantic: the rule about which
    #: categories exist belongs to the domain.
    pref_suscripciones: dict[str, list[str]] | None = None


class UsuarioSalida(BaseModel):
    id: str
    email: str
    nombre: str
    rol: str
    estado: str
    invitacion_id: str | None = None


class PreferenciasSalida(BaseModel):
    pref_idioma: str
    pref_zona_horaria: str
    pref_suscripciones: dict[str, list[str]]


def _preferencias(usuario: Usuario) -> PreferenciasSalida:
    return PreferenciasSalida(
        pref_idioma=usuario.pref_idioma,
        pref_zona_horaria=usuario.pref_zona_horaria,
        pref_suscripciones=usuario.pref_suscripciones.a_json(),
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (
        request.state.empresa_id,
        request.state.usuario_id,
        RolUsuario(request.state.rol),
    )


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def crear_router(recursos: Recursos) -> APIRouter:
    # The prefix is applied on inclusion, not on the parent router: the listing route is
    # `GET /usuarios` with no path of its own, and FastAPI rejects an empty path only
    # when the router is included without a prefix.
    router = APIRouter(tags=["identity"])
    router.include_router(_rutas_de_preferencias(recursos), prefix="/usuarios")
    router.include_router(_rutas_de_invitacion(recursos), prefix="/usuarios")
    router.include_router(_rutas_de_administracion(recursos), prefix="/usuarios")
    return router


def _rutas_de_preferencias(recursos: Recursos) -> APIRouter:
    """HU-E1-07. Any role, and always about the caller themself.

    Mounted before the `/{usuario_id}` routes on purpose: `/usuarios/yo` would otherwise
    be matched as a user id and fail to parse as a UUID.
    """
    router = APIRouter()

    @router.get("/yo/preferencias")
    async def ver_preferencias(request: Request) -> PreferenciasSalida:
        empresa_id, usuario_id, _ = _actor(request)
        salida: PreferenciasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            usuario = await VerPreferencias(usuarios=piezas.usuarios).ejecutar(
                usuario_id=usuario_id
            )
            salida = _preferencias(usuario)
        return _exigir(salida)

    @router.put("/yo/preferencias")
    async def guardar_preferencias(
        entrada: PreferenciasEntrada, request: Request
    ) -> PreferenciasSalida:
        empresa_id, usuario_id, _ = _actor(request)
        suscripciones = (
            PreferenciasDeNotificacion.desde_json(entrada.pref_suscripciones)
            if entrada.pref_suscripciones is not None
            else None
        )
        salida: PreferenciasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            usuario = await ActualizarPreferencias(usuarios=piezas.usuarios).ejecutar(
                usuario_id=usuario_id,
                idioma=entrada.pref_idioma,
                zona_horaria=entrada.pref_zona_horaria,
                suscripciones=suscripciones,
            )
            salida = _preferencias(usuario)
        return _exigir(salida)

    return router


def _rutas_de_invitacion(recursos: Recursos) -> APIRouter:
    """HU-E1-04. Administrator only, enforced by the use case."""
    router = APIRouter()

    @router.post("/invitaciones", status_code=status.HTTP_201_CREATED)
    async def invitar(entrada: InvitacionEntrada, request: Request) -> UsuarioSalida:
        empresa_id, ejecutor_id, rol = _actor(request)
        emitida: InvitacionEmitida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            emitida = await InvitarUsuario(
                usuarios=piezas.usuarios,
                invitaciones=piezas.invitaciones,
                tokens=piezas.tokens_de_invitacion,
                publicador=unidad.publicador,
                vida_invitacion=piezas.vida_invitacion,
            ).ejecutar(
                empresa_id=empresa_id,
                ejecutor_id=ejecutor_id,
                rol_del_ejecutor=rol,
                email=Email(entrada.email),
                rol=entrada.rol,
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
        return await _entregar(recursos, empresa_id, ejecutor_id, emitida)

    @router.post("/invitaciones/{invitacion_id}/reenvio")
    async def reenviar(invitacion_id: UUID, request: Request) -> UsuarioSalida:
        empresa_id, ejecutor_id, rol = _actor(request)
        emitida: InvitacionEmitida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            emitida = await ReenviarInvitacion(
                usuarios=piezas.usuarios,
                invitaciones=piezas.invitaciones,
                tokens=piezas.tokens_de_invitacion,
                publicador=unidad.publicador,
                vida_invitacion=piezas.vida_invitacion,
            ).ejecutar(
                empresa_id=empresa_id,
                ejecutor_id=ejecutor_id,
                rol_del_ejecutor=rol,
                invitacion_id=invitacion_id,
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
        return await _entregar(recursos, empresa_id, ejecutor_id, emitida)

    @router.delete(
        "/invitaciones/{invitacion_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
    )
    async def revocar(invitacion_id: UUID, request: Request) -> Response:
        empresa_id, ejecutor_id, rol = _actor(request)
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            await RevocarInvitacion(
                usuarios=piezas.usuarios,
                invitaciones=piezas.invitaciones,
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                ejecutor_id=ejecutor_id,
                rol_del_ejecutor=rol,
                invitacion_id=invitacion_id,
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _rutas_de_administracion(recursos: Recursos) -> APIRouter:
    """HU-E1-04's list, plus HU-E1-05 and HU-E1-06."""
    router = APIRouter()

    @router.get("")
    async def listar(request: Request) -> list[UsuarioSalida]:
        """Readable by any role — HU-E1-05's third criterion puts an Operador on this
        screen, only without the role-change action."""
        empresa_id, _, _ = _actor(request)
        salida: list[UsuarioSalida] | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            filas = await ListarUsuarios(
                usuarios=piezas.usuarios, invitaciones=piezas.invitaciones
            ).ejecutar(empresa_id=empresa_id)
            salida = [
                UsuarioSalida(
                    id=str(fila.usuario.id),
                    email=str(fila.usuario.email),
                    nombre=fila.usuario.nombre,
                    rol=fila.usuario.rol.value,
                    estado=fila.usuario.estado.value,
                    invitacion_id=str(fila.invitacion_id) if fila.invitacion_id else None,
                )
                for fila in filas
            ]
        return _exigir(salida)

    @router.patch("/{usuario_id}/rol")
    async def cambiar_rol(usuario_id: UUID, entrada: RolEntrada, request: Request) -> UsuarioSalida:
        empresa_id, ejecutor_id, rol = _actor(request)
        salida: UsuarioSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            usuario = await CambiarRolDeUsuario(
                empresas=piezas.empresas,
                usuarios=piezas.usuarios,
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                ejecutor_id=ejecutor_id,
                rol_del_ejecutor=rol,
                usuario_id=UsuarioId(usuario_id),
                rol_nuevo=entrada.rol,
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
            salida = _a_salida(usuario)
        return _exigir(salida)

    @router.post("/{usuario_id}/desactivacion")
    async def desactivar(usuario_id: UUID, request: Request) -> UsuarioSalida:
        empresa_id, ejecutor_id, rol = _actor(request)
        salida: UsuarioSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            usuario = await DesactivarUsuario(
                empresas=piezas.empresas,
                usuarios=piezas.usuarios,
                refrescos=piezas.refrescos,
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                ejecutor_id=ejecutor_id,
                rol_del_ejecutor=rol,
                usuario_id=UsuarioId(usuario_id),
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
            salida = _a_salida(usuario)
        return _exigir(salida)

    @router.post("/{usuario_id}/reactivacion")
    async def reactivar(usuario_id: UUID, request: Request) -> UsuarioSalida:
        empresa_id, ejecutor_id, rol = _actor(request)
        salida: UsuarioSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            usuario = await ReactivarUsuario(
                usuarios=piezas.usuarios, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                ejecutor_id=ejecutor_id,
                rol_del_ejecutor=rol,
                usuario_id=UsuarioId(usuario_id),
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
            salida = _a_salida(usuario)
        return _exigir(salida)

    return router


def _a_salida(usuario: Usuario) -> UsuarioSalida:
    return UsuarioSalida(
        id=str(usuario.id),
        email=str(usuario.email),
        nombre=usuario.nombre,
        rol=usuario.rol.value,
        estado=usuario.estado.value,
    )


async def _entregar(
    recursos: Recursos,
    empresa_id: EmpresaId,
    ejecutor_id: UsuarioId,
    emitida: InvitacionEmitida | None,
) -> UsuarioSalida:
    """Hand the token to the email task, then forget it.

    This runs **after** the transaction committed, and that ordering is the point: an
    invitation whose email was enqueued and whose row then rolled back would be a live
    link to nothing.
    """
    emitida = _exigir(emitida)
    await encolar_invitacion(
        recursos,
        empresa_id=empresa_id,
        invitacion_id=emitida.invitacion.id,
        destinatario=str(emitida.usuario.email),
        invitado_por_id=ejecutor_id,
        token=emitida.token_en_claro,
        expira_en=emitida.invitacion.expira_en,
    )
    return UsuarioSalida(
        id=str(emitida.usuario.id),
        email=str(emitida.usuario.email),
        nombre=emitida.usuario.nombre,
        rol=emitida.usuario.rol.value,
        estado=emitida.usuario.estado.value,
        invitacion_id=str(emitida.invitacion.id),
    )


def _exigir(valor: _T | None) -> _T:
    if valor is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return valor
