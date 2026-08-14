"""HTTP surface of the identity context (HU-E1-01, HU-E1-02, HU-E1-03).

The endpoints return tokens in the body and set no cookies: the BFF in `frontend/` turns
them into an HttpOnly cookie. Keeping that in one place means the browser never sees a
token, and this API stays usable by something that is not a browser.

`empresa_id` is generated **before** the transaction opens, because Row-Level Security
scopes every statement to `app.current_empresa` and the identifier has to exist in order
to announce it.
"""

from __future__ import annotations

from uuid import uuid4

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.identity.application.errors import OAuthFallido
from cheatsheet.contexts.identity.application.onboarding import CompletarDatosDeEmpresa
from cheatsheet.contexts.identity.application.registro import RegistrarEmpresa
from cheatsheet.contexts.identity.application.sesiones import (
    CerrarSesion,
    IniciarSesion,
    RefrescarSesion,
    Sesion,
)
from cheatsheet.contexts.identity.domain.valores import CUIT, CondicionIVA, Email
from cheatsheet.contexts.identity.infrastructure.ensamblado import Identidad, proveedor_google
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

LARGO_MINIMO_CONTRASENA = 8


class RegistroEntrada(BaseModel):
    email: str
    contrasena: str = Field(min_length=LARGO_MINIMO_CONTRASENA)
    nombre: str


class LoginEntrada(BaseModel):
    email: str
    contrasena: str


class RefreshEntrada(BaseModel):
    refresh_token: str


class DatosDeEmpresaEntrada(BaseModel):
    razon_social: str
    cuit: str
    condicion_iva: CondicionIVA
    nombre_responsable: str
    email_contacto: str


class SesionSalida(BaseModel):
    access_token: str
    refresh_token: str
    empresa_id: str
    usuario_id: str
    onboarding_completo: bool


def _a_salida(sesion: Sesion, onboarding_completo: bool) -> SesionSalida:
    return SesionSalida(
        access_token=sesion.access_token,
        refresh_token=sesion.refresh_token,
        empresa_id=str(sesion.usuario.empresa_id),
        usuario_id=str(sesion.usuario.id),
        onboarding_completo=onboarding_completo,
    )


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def crear_router(recursos: Recursos) -> APIRouter:
    """The whole auth surface: the routes reachable without a session, and the one that is not."""
    router = APIRouter(prefix="/auth", tags=["identity"])
    router.include_router(_rutas_de_alta(recursos))
    router.include_router(_rutas_de_sesion(recursos))
    router.include_router(_rutas_autenticadas(recursos))
    return router


def _rutas_de_alta(recursos: Recursos) -> APIRouter:
    """Creating an account. No session exists yet."""
    router = APIRouter()

    @router.post("/registro", status_code=status.HTTP_201_CREATED)
    async def registro(entrada: RegistroEntrada, request: Request) -> SesionSalida:
        empresa_id = EmpresaId(uuid4())
        salida: SesionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            registrada = await RegistrarEmpresa(
                empresas=piezas.empresas,
                usuarios=piezas.usuarios,
                hasher=piezas.hasher,
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                email=Email(entrada.email),
                contrasena=entrada.contrasena,
                nombre=entrada.nombre,
                version_terminos=recursos.settings.terminos_version_vigente,
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
            sesion = await piezas.emisor.emitir(registrada.usuario, unidad.reloj.ahora())
            salida = _a_salida(sesion, registrada.empresa.onboarding_completo)
        return _exigir(salida)

    return router


def _rutas_de_sesion(recursos: Recursos) -> APIRouter:
    """The token lifecycle: obtain, rotate, revoke."""
    router = APIRouter()

    @router.post("/login")
    async def login(entrada: LoginEntrada) -> SesionSalida:
        # Sign-in happens before there is a company: the lookup goes through the
        # SECURITY DEFINER function, so the transaction can be opened with any id.
        salida: SesionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, EmpresaId(uuid4())):
            piezas = Identidad.armar(unidad, recursos.settings)
            sesion = await IniciarSesion(
                usuarios=piezas.usuarios, hasher=piezas.hasher, emisor=piezas.emisor
            ).ejecutar(
                email=Email(entrada.email),
                contrasena=entrada.contrasena,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(sesion, onboarding_completo=False)
        return _exigir(salida)

    @router.post("/refresh")
    async def refresh(entrada: RefreshEntrada) -> SesionSalida:
        salida: SesionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, EmpresaId(uuid4())):
            piezas = Identidad.armar(unidad, recursos.settings)
            sesion = await RefrescarSesion(
                usuarios=piezas.usuarios,
                refrescos=piezas.refrescos,
                tokens=piezas.tokens,
                emisor=piezas.emisor,
            ).ejecutar(refresh_token=entrada.refresh_token, ahora=unidad.reloj.ahora())
            salida = _a_salida(sesion, onboarding_completo=False)
        return _exigir(salida)

    # `response_class=Response`: a 204 carries no body, and FastAPI refuses to build a
    # response model for one.
    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    async def logout(entrada: RefreshEntrada) -> Response:
        async for unidad in unidad_de_trabajo(recursos, EmpresaId(uuid4())):
            piezas = Identidad.armar(unidad, recursos.settings)
            await CerrarSesion(refrescos=piezas.refrescos, tokens=piezas.tokens).ejecutar(
                refresh_token=entrada.refresh_token
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/google/url")
    async def url_de_google(state: str) -> dict[str, str]:
        proveedor = proveedor_google(recursos.settings)
        if proveedor is None:
            raise OAuthFallido("Google OAuth no esta configurado en este entorno")
        return {"url": proveedor.url_de_autorizacion(state)}

    return router


def _rutas_autenticadas(recursos: Recursos) -> APIRouter:
    """Needs a valid access token; `EmpresaMiddleware` has already resolved the company."""
    router = APIRouter()

    @router.put("/empresa")
    async def completar_empresa(
        entrada: DatosDeEmpresaEntrada, request: Request
    ) -> dict[str, bool]:
        empresa_id: EmpresaId = request.state.empresa_id
        usuario_id: UsuarioId = request.state.usuario_id
        resultado: dict[str, bool] | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            empresa = await CompletarDatosDeEmpresa(
                empresas=piezas.empresas, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                razon_social=entrada.razon_social,
                cuit=CUIT(entrada.cuit),
                condicion_iva=entrada.condicion_iva,
                nombre_responsable=entrada.nombre_responsable,
                email_contacto=Email(entrada.email_contacto),
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
            resultado = {"onboarding_completo": empresa.onboarding_completo}
        if resultado is None:  # pragma: no cover — the unit of work always yields once
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return resultado

    return router


def _exigir(salida: SesionSalida | None) -> SesionSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo una sesion")
    return salida
