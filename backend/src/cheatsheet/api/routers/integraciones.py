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

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.integrations.application.integraciones import (
    ConectarIntegracion,
    ListarIntegraciones,
    VerificarConexiones,
    VistaDeIntegracion,
)
from cheatsheet.contexts.integrations.domain.valores import (
    Ambiente,
    EstadoDeConexion,
    SistemaExterno,
)
from cheatsheet.contexts.integrations.infrastructure.ensamblado import Integraciones
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
            )
            for v in vistas
        ],
        verificado_en=max(marcas) if marcas else None,
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
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Integraciones.armar(unidad.sesion, recursos.settings)
            vista = await ConectarIntegracion(
                integraciones=piezas.integraciones,
                cifrado=piezas.cifrado,
                adaptadores=piezas.adaptadores,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
                es_produccion=recursos.settings.es_produccion,
            ).ejecutar(
                empresa_id=empresa_id,
                rol=rol,
                sistema=sistema,
                contenido=_decodificar(entrada.contenido),
                parametros=dict(entrada.parametros),
                usuario_id=usuario_id,
                direccion_ip=_ip(request),
            )
        vista_final = _exigir(vista)
        return IntegracionSalida(
            sistema=vista_final.sistema,
            estado=vista_final.estado,
            detalle=vista_final.detalle,
            ambiente=vista_final.ambiente,
            verificado_en=vista_final.verificado_en,
            configurada=vista_final.configurada,
        )

    return router


def _exigir(valor: _T | None) -> _T:
    """The unit of work is an async generator; mypy cannot see that it yields once."""
    if valor is None:  # pragma: no cover — unreachable while the generator yields
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return valor
