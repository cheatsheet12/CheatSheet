"""HTTP surface for the points of sale (HU-E5-05, PAN-FAC-05).

`EmpresaMiddleware` has already put the company, the user and the role on `request.state`.
The role is passed down to the use case rather than checked here, for the reason the other
routers state and PRU-09 proved.

**There is no `DELETE`.** A point of sale that issued documents cannot be removed without
orphaning them, and those documents carry a CAE. Taking one out of circulation is
`PUT /puntos-de-venta/{id}/estado`, which is what RN-04 asks for.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cheatsheet.api.arca import armar_habilitacion
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.billing.application.puntos_de_venta import (
    CambiarEstadoDePuntoDeVenta,
    DatosDePuntoDeVenta,
    ListarPuntosDeVenta,
    RegistrarPuntoDeVenta,
)
from cheatsheet.contexts.billing.domain.punto_de_venta import PuntoDeVenta, TipoComprobante
from cheatsheet.contexts.billing.infrastructure.ensamblado import Facturacion
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, status
from pydantic import BaseModel


class PuntoDeVentaEntrada(BaseModel):
    numero: int
    descripcion: str | None = None


class EstadoEntrada(BaseModel):
    activo: bool


class PuntoDeVentaSalida(BaseModel):
    id: UUID
    numero: int
    descripcion: str | None
    activo: bool
    #: `{tipo: ultimo_numero}`. Shown so an Administrator can see where the numbering is
    #: without opening a document — which is the first thing anybody asks when ARCA
    #: rejects one for a number out of sequence.
    numerador_por_tipo: dict[str, int]
    created_at: datetime


class ListadoSalida(BaseModel):
    puntos: list[PuntoDeVentaSalida]


def _a_salida(punto: PuntoDeVenta) -> PuntoDeVentaSalida:
    return PuntoDeVentaSalida(
        id=punto.id,
        numero=punto.numero,
        descripcion=punto.descripcion,
        activo=punto.activo,
        numerador_por_tipo={
            tipo.value: punto.ultimo_numero(tipo)
            for tipo in TipoComprobante
            if punto.ultimo_numero(tipo)
        },
        created_at=punto.created_at,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["billing"])
    router.include_router(_rutas(recursos), prefix="/puntos-de-venta")
    return router


def _rutas(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.get("")
    async def listar(request: Request) -> ListadoSalida:
        """PAN-FAC-05. Every role reads."""
        empresa_id, _, _ = _actor(request)
        salida = ListadoSalida(puntos=[])
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            puntos = await ListarPuntosDeVenta(piezas.puntos).ejecutar()
            salida = ListadoSalida(puntos=[_a_salida(p) for p in puntos])
        return salida

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def registrar(request: Request, entrada: PuntoDeVentaEntrada) -> PuntoDeVentaSalida:
        """RN-03: verified against ARCA before the point can be used."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: PuntoDeVentaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            punto = await RegistrarPuntoDeVenta(
                puntos=piezas.puntos,
                habilitacion=armar_habilitacion(unidad, recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                datos=DatosDePuntoDeVenta(numero=entrada.numero, descripcion=entrada.descripcion),
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(punto)
        return _exigir(salida)

    @router.put("/{punto_id}/estado")
    async def cambiar_estado(
        request: Request, punto_id: UUID, entrada: EstadoEntrada
    ) -> PuntoDeVentaSalida:
        """RN-04. Reactivating re-checks ARCA; deactivating keeps the counters."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: PuntoDeVentaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Facturacion.armar(unidad)
            punto = await CambiarEstadoDePuntoDeVenta(
                puntos=piezas.puntos,
                habilitacion=armar_habilitacion(unidad, recursos.settings),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                punto_id=punto_id,
                activo=entrada.activo,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(punto)
        return _exigir(salida)

    return router


def _exigir(salida: PuntoDeVentaSalida | None) -> PuntoDeVentaSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida
