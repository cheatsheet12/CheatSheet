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
from cheatsheet.api.padron import armar_padron
from cheatsheet.contexts.identity.application.errors import (
    CredencialesInvalidas,
    InvitacionInvalida,
    OAuthFallido,
    SesionInvalida,
)
from cheatsheet.contexts.identity.application.invitaciones import AceptarInvitacion
from cheatsheet.contexts.identity.application.onboarding import CompletarDatosDeEmpresa
from cheatsheet.contexts.identity.application.padron import (
    ConsultarPadronDeCuit,
    EstadoDeConsulta,
)
from cheatsheet.contexts.identity.application.ports import PortProveedorOAuth
from cheatsheet.contexts.identity.application.registro import RegistrarConGoogle, RegistrarEmpresa
from cheatsheet.contexts.identity.application.sesiones import (
    CerrarSesion,
    IniciarSesion,
    RefrescarSesion,
    Sesion,
)
from cheatsheet.contexts.identity.domain.usuario import Usuario
from cheatsheet.contexts.identity.domain.valores import CUIT, CondicionIVA, Email
from cheatsheet.contexts.identity.infrastructure.ensamblado import Identidad, proveedor_google
from cheatsheet.contexts.identity.infrastructure.resolucion import (
    empresa_de_email,
    empresa_de_invitacion,
    empresa_de_refresh,
)
from cheatsheet.contexts.identity.infrastructure.seguridad import hashear_token_opaco
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
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


class AceptacionEntrada(BaseModel):
    token: str
    nombre: str
    contrasena: str = Field(min_length=LARGO_MINIMO_CONTRASENA)


class GoogleEntrada(BaseModel):
    """The authorization code Google handed to the browser, relayed by the BFF."""

    codigo: str


class DatosDeEmpresaEntrada(BaseModel):
    razon_social: str
    cuit: str
    condicion_iva: CondicionIVA
    nombre_responsable: str
    email_contacto: str


class EmpresaSalida(BaseModel):
    """What the panel reads before rendering, and what the edit screen loads into its form.

    It grew the four remaining fiscal fields when `padron-y-datos-fiscales` added a screen
    that edits them: a form cannot show what the API does not return. None of them is a
    secret — a CUIT and a razón social are printed on every document the company issues.
    """

    razon_social: str | None
    onboarding_completo: bool
    cuit: str | None = None
    condicion_iva: CondicionIVA | None = None
    nombre_responsable: str | None = None
    email_contacto: str | None = None


class ConsultaDePadronEntrada(BaseModel):
    cuit: str


class DatosDePadronSalida(BaseModel):
    razon_social: str | None
    condicion_iva: CondicionIVA | None
    activo: bool


class PadronSalida(BaseModel):
    """Three states, never two. See `identity/application/padron.py`.

    `NO_ENCONTRADO` blocks the form; `NO_DISPONIBLE` does not, and collapsing them into a
    boolean is exactly the mistake this unit exists to avoid.
    """

    estado: EstadoDeConsulta
    datos: DatosDePadronSalida | None = None
    motivo: str | None = None


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
    router.include_router(_rutas_de_invitacion(recursos))
    router.include_router(_rutas_autenticadas(recursos))
    router.include_router(_rutas_de_padron(recursos))
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


async def _salida_de(piezas: Identidad, empresa_id: EmpresaId, sesion: Sesion) -> SesionSalida:
    """The session plus whether the company still owes the onboarding.

    Read from the database rather than assumed: it used to be hardcoded `False`, which
    sent every returning user back to step 1.
    """
    empresa = await piezas.empresas.buscar_por_id(empresa_id)
    return _a_salida(sesion, empresa is not None and empresa.onboarding_completo)


def _rutas_de_sesion(recursos: Recursos) -> APIRouter:
    """The token lifecycle: obtain, rotate, revoke.

    **Every route here is pre-tenant**, and each one resolves the company *before* opening
    its transaction. Opening it with an invented `EmpresaId(uuid4())` — which is what this
    module used to do — makes Row-Level Security reject the write that follows, and in the
    case of sign-out reject it silently. See `infrastructure/resolucion.py`.
    """
    router = APIRouter()

    @router.post("/login")
    async def login(entrada: LoginEntrada) -> SesionSalida:
        email = Email(entrada.email)
        empresa_id = await empresa_de_email(recursos.sesiones, email)
        if empresa_id is None:
            # Same error as a wrong password: a different one here would turn the form
            # into an account enumerator.
            raise CredencialesInvalidas("Email o contrasena incorrectos")

        salida: SesionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            sesion = await IniciarSesion(
                usuarios=piezas.usuarios, hasher=piezas.hasher, emisor=piezas.emisor
            ).ejecutar(
                email=email,
                contrasena=entrada.contrasena,
                ahora=unidad.reloj.ahora(),
            )
            salida = await _salida_de(piezas, empresa_id, sesion)
        return _exigir(salida)

    @router.post("/refresh")
    async def refresh(entrada: RefreshEntrada) -> SesionSalida:
        empresa_id = await empresa_de_refresh(
            recursos.sesiones, hashear_token_opaco(entrada.refresh_token)
        )
        if empresa_id is None:
            raise SesionInvalida("El refresh token no existe")

        salida: SesionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            sesion = await RefrescarSesion(
                usuarios=piezas.usuarios,
                refrescos=piezas.refrescos,
                tokens=piezas.tokens,
                emisor=piezas.emisor,
            ).ejecutar(refresh_token=entrada.refresh_token, ahora=unidad.reloj.ahora())
            salida = await _salida_de(piezas, empresa_id, sesion)
        return _exigir(salida)

    # `response_class=Response`: a 204 carries no body, and FastAPI refuses to build a
    # response model for one.
    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
    async def logout(entrada: RefreshEntrada) -> Response:
        empresa_id = await empresa_de_refresh(
            recursos.sesiones, hashear_token_opaco(entrada.refresh_token)
        )
        # An unknown token is already signed out. Answering 204 rather than an error is
        # deliberate: sign-out must never leave a client stuck holding a session it
        # believes is open.
        if empresa_id is not None:
            async for unidad in unidad_de_trabajo(recursos, empresa_id):
                piezas = Identidad.armar(unidad, recursos.settings)
                await CerrarSesion(refrescos=piezas.refrescos, tokens=piezas.tokens).ejecutar(
                    refresh_token=entrada.refresh_token
                )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


def _rutas_de_invitacion(recursos: Recursos) -> APIRouter:
    """Accepting an invitation, and the Google authorization URL.

    Both are public and both are pre-tenant, so they sit apart from the token lifecycle
    rather than inside it — the session router was over the complexity limit.
    """
    router = APIRouter()

    @router.post("/invitaciones/aceptar", status_code=status.HTTP_201_CREATED)
    async def aceptar_invitacion(entrada: AceptacionEntrada, request: Request) -> SesionSalida:
        """HU-E1-04: the invited person sets a password and the account becomes real.

        Public by necessity — they have no session yet, which is the whole point.
        """
        empresa_id = await empresa_de_invitacion(
            recursos.sesiones, hashear_token_opaco(entrada.token)
        )
        if empresa_id is None:
            raise InvitacionInvalida("La invitacion no es valida o ya fue utilizada")

        salida: SesionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            sesion = await AceptarInvitacion(
                usuarios=piezas.usuarios,
                invitaciones=piezas.invitaciones,
                tokens=piezas.tokens_de_invitacion,
                hasher=piezas.hasher,
                emisor=piezas.emisor,
                publicador=unidad.publicador,
            ).ejecutar(
                token=entrada.token,
                nombre=entrada.nombre,
                contrasena=entrada.contrasena,
                ahora=unidad.reloj.ahora(),
                direccion_ip=_ip(request),
            )
            salida = await _salida_de(piezas, empresa_id, sesion)
        return _exigir(salida)

    @router.get("/google/url")
    async def url_de_google(state: str) -> dict[str, str]:
        return {"url": _proveedor(recursos).url_de_autorizacion(state)}

    @router.post("/google/callback", status_code=status.HTTP_201_CREATED)
    async def callback_de_google(entrada: GoogleEntrada, request: Request) -> SesionSalida:
        """Exchange the authorization code for a session (HU-E1-01 RN-02).

        **Sign-up and sign-in are the same endpoint here, on purpose.** Whoever comes back
        from Google does not know whether they have an account, and asking them to pick
        the right button before finding out would be a worse version of the account
        enumeration the sign-in form already avoids. An existing user gets a session; a
        new one gets a company first.
        """
        perfil = await _proveedor(recursos).perfil_desde_codigo(entrada.codigo)

        empresa_id = await empresa_de_email(recursos.sesiones, perfil.email)
        nueva = empresa_id is None
        if empresa_id is None:
            empresa_id = EmpresaId(uuid4())

        salida: SesionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            usuario = (
                (
                    await RegistrarConGoogle(
                        empresas=piezas.empresas,
                        usuarios=piezas.usuarios,
                        publicador=unidad.publicador,
                    ).ejecutar(
                        empresa_id=empresa_id,
                        email=perfil.email,
                        nombre=perfil.nombre,
                        version_terminos=recursos.settings.terminos_version_vigente,
                        ahora=unidad.reloj.ahora(),
                        direccion_ip=_ip(request),
                    )
                ).usuario
                if nueva
                else await _usuario_de_google(piezas, perfil.email)
            )
            sesion = await piezas.emisor.emitir(usuario, unidad.reloj.ahora())
            salida = await _salida_de(piezas, empresa_id, sesion)
        return _exigir(salida)

    return router


def _proveedor(recursos: Recursos) -> PortProveedorOAuth:
    proveedor = proveedor_google(recursos.settings)
    if proveedor is None:
        raise OAuthFallido("Google OAuth no esta configurado en este entorno")
    return proveedor


async def _usuario_de_google(piezas: Identidad, email: Email) -> Usuario:
    """The returning user. A deactivated account does not get a session back."""
    usuario = await piezas.usuarios.buscar_por_email(email)
    if usuario is None:  # pragma: no cover — the company was just resolved from this email
        raise OAuthFallido("La cuenta de Google no corresponde a ningun usuario")
    usuario.exigir_activo()
    return usuario


def _rutas_autenticadas(recursos: Recursos) -> APIRouter:
    """Needs a valid access token; `EmpresaMiddleware` has already resolved the company."""
    router = APIRouter()

    @router.get("/empresa")
    async def ver_empresa(request: Request) -> EmpresaSalida:
        """What the panel needs before rendering: does this company still owe the onboarding.

        It exists because the alternative was putting `onboarding_completo` in the access
        token, where it would be stale for fifteen minutes — long enough to bounce someone
        back to a form they just finished.
        """
        empresa_id: EmpresaId = request.state.empresa_id
        salida: EmpresaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Identidad.armar(unidad, recursos.settings)
            empresa = await piezas.empresas.buscar_por_id(empresa_id)
            if empresa is None:  # pragma: no cover — the token was issued for it
                raise EntradaInvalida("La empresa no existe")
            salida = EmpresaSalida(
                razon_social=empresa.razon_social,
                onboarding_completo=empresa.onboarding_completo,
                cuit=empresa.cuit.valor if empresa.cuit else None,
                condicion_iva=empresa.condicion_iva,
                nombre_responsable=empresa.nombre_responsable,
                email_contacto=str(empresa.email_contacto) if empresa.email_contacto else None,
            )
        if salida is None:  # pragma: no cover — the unit of work always yields once
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return salida

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
                empresas=piezas.empresas,
                publicador=unidad.publicador,
                # RN-01 bites from here on, but only for a company that has already
                # connected ARCA: without a certificate the registry cannot be asked, and
                # `CompletarDatosDeEmpresa` treats that as "carry on", not as a rejection.
                padron=armar_padron(unidad, recursos.settings),
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


def _rutas_de_padron(recursos: Recursos) -> APIRouter:
    """Its own factory so the authenticated block stays under the complexity ceiling."""
    router = APIRouter()

    @router.post("/empresa/padron")
    async def consultar_padron(entrada: ConsultaDePadronEntrada, request: Request) -> PadronSalida:
        """HU-E1-02 RN-01 and RN-02, behind the «Validar contra ARCA» button.

        A `POST` on a read because the CUIT is somebody's tax id: in a query string it
        would end up in access logs and in browser history. Nothing is written.
        """
        empresa_id: EmpresaId = request.state.empresa_id
        rol = RolUsuario(request.state.rol)
        salida: PadronSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            vista = await ConsultarPadronDeCuit(
                padron=armar_padron(unidad, recursos.settings)
            ).ejecutar(empresa_id=empresa_id, cuit=entrada.cuit, rol=rol)
            salida = PadronSalida(
                estado=vista.estado,
                datos=(
                    DatosDePadronSalida(
                        razon_social=vista.datos.razon_social,
                        condicion_iva=vista.datos.condicion_iva,
                        activo=vista.datos.activo,
                    )
                    if vista.datos is not None
                    else None
                ),
                motivo=vista.motivo,
            )
        if salida is None:  # pragma: no cover — the unit of work always yields once
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return salida

    return router


def _exigir(salida: SesionSalida | None) -> SesionSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo una sesion")
    return salida
