"""HTTP surface of PAN-CFG-INT (HU-E2-05).

`EmpresaMiddleware` has already verified the access token and put the company, the user
and the role on `request.state`. **The role is passed down to the use case rather than
checked here**, for the reason `identity/application/autorizacion.py` gives: the endpoint
is one caller among several, and the rule belongs next to the operation it guards.

**No credential ever comes back out.** The response carries the state, the environment and
the time of the last check — never the ciphertext, never the plaintext, and never a hint
of either. That is the same boundary ADR-0003 draws for decryption, restated at the HTTP
edge because this is where a careless field addition would leak it.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import TypeVar

from cheatsheet.api.dependencies import Recursos, UnidadDeTrabajo, unidad_de_trabajo
from cheatsheet.api.padron import armar_padron
from cheatsheet.contexts.identity.application.padron import RevalidarDatosFiscales
from cheatsheet.contexts.identity.infrastructure.ensamblado import Identidad
from cheatsheet.contexts.integrations.application.integraciones import (
    ConectarIntegracion,
    ListarIntegraciones,
    VerificarConexiones,
    VistaDeIntegracion,
)
from cheatsheet.contexts.integrations.application.oauth import (
    CompletarAutorizacion,
    IniciarAutorizacion,
)
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.ensamblado import (
    Integraciones,
    crear_memoria_de_autorizacion,
    registro_de_adaptadores,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request
from pydantic import BaseModel

_T = TypeVar("_T")


class ConexionEntrada(BaseModel):
    """What the connect endpoint receives.

    `contenido` is base64 because the three providers disagree about what a credential is
    — ARCA takes a binary certificate, MercadoPago an authorization code — and base64 is
    the one shape that carries all of them over JSON without the API having to know which.
    """

    contenido: str
    parametros: dict[str, str | int | float | bool] = {}


class IntegracionSalida(BaseModel):
    sistema: SistemaExterno
    estado: EstadoDeConexion
    detalle: str | None
    ambiente: Ambiente | None
    verificado_en: datetime | None
    configurada: bool
    #: The verified display name (HU-E2-03 RN-03). See `VistaDeIntegracion.etiqueta`.
    etiqueta: str | None = None
    #: Only on the connect response, and only for ARCA: what the taxpayer registry had to
    #: say about this company's fiscal data now that it can finally be asked. `None` is the
    #: ordinary answer — see `RevalidarDatosFiscales`.
    aviso_fiscal: str | None = None


class AutorizacionSalida(BaseModel):
    """Where to send the browser, and how long that link is good for."""

    url: str
    expira_en_segundos: int


class CanjeEntrada(BaseModel):
    """What comes back from the provider, forwarded by the screen that received it.

    Both values are opaque here. The `state` means nothing to this layer and everything to
    `CompletarAutorizacion`, which is where it is checked.
    """

    codigo: str
    estado: str


class ListadoSalida(BaseModel):
    integraciones: list[IntegracionSalida]
    #: HU-E2-05 RN-03: the consolidated screen shows when the check ran.
    verificado_en: datetime | None


def _salida(vistas: list[VistaDeIntegracion]) -> ListadoSalida:
    marcas = [v.verificado_en for v in vistas if v.verificado_en is not None]
    return ListadoSalida(
        integraciones=[
            IntegracionSalida(
                sistema=v.sistema,
                estado=v.estado,
                detalle=v.detalle,
                ambiente=v.ambiente,
                verificado_en=v.verificado_en,
                configurada=v.configurada,
                etiqueta=v.etiqueta,
            )
            for v in vistas
        ],
        verificado_en=max(marcas) if marcas else None,
    )


def _una(vista: VistaDeIntegracion, aviso: str | None = None) -> IntegracionSalida:
    return IntegracionSalida(
        sistema=vista.sistema,
        estado=vista.estado,
        detalle=vista.detalle,
        ambiente=vista.ambiente,
        verificado_en=vista.verificado_en,
        configurada=vista.configurada,
        etiqueta=vista.etiqueta,
        aviso_fiscal=aviso,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (
        request.state.empresa_id,
        request.state.usuario_id,
        RolUsuario(request.state.rol),
    )


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _decodificar(contenido: str) -> bytes:
    try:
        return base64.b64decode(contenido, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise EntradaInvalida("El contenido de la credencial debe ser base64 valido") from exc


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(prefix="/integraciones", tags=["integrations"])

    @router.get("")
    async def listar(request: Request) -> ListadoSalida:
        """The screen's initial read: last known state, no external calls."""
        empresa_id, _, rol = _actor(request)
        salida: ListadoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            vistas = await ListarIntegraciones(integraciones=piezas.integraciones).ejecutar(
                empresa_id=empresa_id, rol=rol
            )
            salida = _salida(vistas)
        return _exigir(salida)

    @router.post("/verificacion")
    async def verificar(request: Request) -> ListadoSalida:
        """HU-E2-05: check every configured integration live.

        Administrador **or** Operador — the story names both actors, and the use case is
        what enforces it.
        """
        empresa_id, usuario_id, rol = _actor(request)
        salida: ListadoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            vistas = await VerificarConexiones(
                integraciones=piezas.integraciones,
                cifrado=piezas.cifrado,
                adaptadores=piezas.adaptadores,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
                timeout_segundos=recursos.settings.integracion_timeout_segundos,
            ).ejecutar(
                empresa_id=empresa_id,
                rol=rol,
                usuario_id=usuario_id,
                direccion_ip=_ip(request),
            )
            salida = _salida(vistas)
        return _exigir(salida)

    @router.put("/{sistema}/conexion")
    async def conectar(
        request: Request, sistema: SistemaExterno, entrada: ConexionEntrada
    ) -> IntegracionSalida:
        """Administrador only. `PUT` because connecting twice is the same result once."""
        empresa_id, usuario_id, rol = _actor(request)
        vista: VistaDeIntegracion | None = None
        aviso: str | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            vista = await ConectarIntegracion(
                integraciones=piezas.integraciones,
                # ARCA mints an access ticket while validating and ARCA refuses to issue
                # another for twelve hours, so it has to be kept (ADR-0004).
                tickets=piezas.tickets,
                cifrado=piezas.cifrado,
                adaptadores=piezas.adaptadores,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
                es_produccion=recursos.settings.es_produccion,
            ).ejecutar(
                empresa_id=empresa_id,
                rol=rol,
                sistema=sistema,
                contenido=await _contenido(unidad, recursos, sistema, empresa_id, entrada),
                parametros=dict(entrada.parametros),
                usuario_id=usuario_id,
                direccion_ip=_ip(request),
            )
            aviso = await _revalidar_datos_fiscales(recursos, unidad, vista, request)
        return _una(_exigir(vista), aviso)

    router.include_router(_rutas_de_autorizacion(recursos))
    return router


def _rutas_de_autorizacion(recursos: Recursos) -> APIRouter:
    """The two halves of an OAuth2 connection (HU-E2-02 RN-01).

    Their own router for the reason `_rutas_de_padron` has one in `auth.py`: the factory
    above is at the complexity ceiling `CLAUDE.md` §5 sets, and a closure that keeps
    growing is the shape that eventually hides something.

    **Neither endpoint decides anything.** The first mints nothing it understands and the
    second forwards two opaque strings; what a `state` means, and whether this one may be
    spent, is `CompletarAutorizacion`'s business — a rule whose failure moves money does
    not belong at the HTTP edge.
    """
    router = APIRouter(tags=["integrations"])

    @router.post("/{sistema}/autorizacion")
    async def autorizar(request: Request, sistema: SistemaExterno) -> AutorizacionSalida:
        """Administrador only. Opens no transaction: nothing here touches the database."""
        empresa_id, _, rol = _actor(request)
        inicio = await IniciarAutorizacion(
            adaptadores=registro_de_adaptadores(recursos.settings),
            memoria=crear_memoria_de_autorizacion(recursos.redis),
            ttl_segundos=recursos.settings.mercadopago_autorizacion_ttl_minutos * 60,
        ).ejecutar(empresa_id=empresa_id, rol=rol, sistema=sistema)
        return AutorizacionSalida(url=inicio.url, expira_en_segundos=inicio.expira_en_segundos)

    @router.post("/{sistema}/autorizacion/canje")
    async def canjear(
        request: Request, sistema: SistemaExterno, entrada: CanjeEntrada
    ) -> IntegracionSalida:
        """Second half: the code comes back and becomes a stored credential."""
        empresa_id, usuario_id, rol = _actor(request)
        vista: VistaDeIntegracion | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            vista = await CompletarAutorizacion(
                memoria=crear_memoria_de_autorizacion(recursos.redis),
                conectar=ConectarIntegracion(
                    integraciones=piezas.integraciones,
                    tickets=piezas.tickets,
                    cifrado=piezas.cifrado,
                    adaptadores=piezas.adaptadores,
                    publicador=unidad.publicador,
                    reloj=unidad.reloj,
                    es_produccion=recursos.settings.es_produccion,
                ),
            ).ejecutar(
                empresa_id=empresa_id,
                rol=rol,
                sistema=sistema,
                codigo=entrada.codigo,
                estado=entrada.estado,
                usuario_id=usuario_id,
                direccion_ip=_ip(request),
            )
        return _una(_exigir(vista))

    return router


async def _revalidar_datos_fiscales(
    recursos: Recursos,
    unidad: UnidadDeTrabajo,
    vista: VistaDeIntegracion,
    request: Request,
) -> str | None:
    """The moment ARCA is connected is the first moment the padrón can be asked at all.

    So it is asked here, once, and the answer rides back on the response the Administrator
    is already looking at. This is the composition root calling two contexts, which is the
    one place that is allowed to — `integrations` learns nothing about `identity`.

    Anything other than a successful ARCA connection leaves this alone: there is nothing
    to check against a credential the provider refused.
    """
    if vista.sistema is not SistemaExterno.ARCA or vista.estado is not EstadoDeConexion.CONECTADO:
        return None
    empresa_id, usuario_id, _ = _actor(request)
    piezas = Identidad.armar(unidad, recursos.settings)
    aviso = await RevalidarDatosFiscales(
        empresas=piezas.empresas,
        padron=armar_padron(unidad, recursos.settings),
        publicador=unidad.publicador,
    ).ejecutar(
        empresa_id=empresa_id,
        ahora=unidad.reloj.ahora(),
        cuit_declarado=vista.cuit_declarado,
        usuario_id=usuario_id,
        direccion_ip=_ip(request),
    )
    return aviso.motivo if aviso is not None else None


async def _contenido(
    unidad: UnidadDeTrabajo,
    recursos: Recursos,
    sistema: SistemaExterno,
    empresa_id: EmpresaId,
    entrada: ConexionEntrada,
) -> bytes:
    """What the connector validates. **For ARCA it is never what the request sent.**

    Under ADR-0014 connecting ARCA verifies that the company delegated the web service to
    CheatSheet, and the CUIT decides on whose behalf documents will be issued. So it comes
    from the company's own data in `identity` — unique across companies — and the body is
    ignored. Taking it from the request would let any Administrator point the platform
    certificate at another company's CUIT.
    """
    if sistema is not SistemaExterno.ARCA:
        return _decodificar(entrada.contenido)
    empresa = await Identidad.armar(unidad, recursos.settings).empresas.buscar_por_id(empresa_id)
    cuit = empresa.cuit if empresa is not None else None
    return str(cuit.valor if cuit is not None else "").encode()


def _exigir(valor: _T | None) -> _T:
    """The unit of work is an async generator; mypy cannot see that it yields once."""
    if valor is None:  # pragma: no cover — unreachable while the generator yields
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return valor
