"""HTTP surface for the service catalogue (HU-E4-02, PAN-DM-02).

**The price crosses this boundary as a string, and that is the whole point of this
module's shape.** A JSON number is an IEEE-754 double: pydantic would happily turn
`19999.99` into a `Decimal` that carries the binary error it arrived with, and nothing
downstream could tell. Declaring the field as `str` makes a JSON number a 422 instead —
verified, not assumed: pydantic v2 refuses to coerce a number into a `str` field.

So the only conversion happens in `_precio`, from text, which is what
`docs/code-standards.md` §2.5 requires: «`Decimal` values are built from strings, never
from a float literal».

There is no `DELETE`, for the same reason there is none on `/clientes`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.master_data.application.servicios import (
    CambiarEstadoDeServicio,
    DatosDeServicio,
    EditarServicio,
    ListarServicios,
    RegistrarServicio,
)
from cheatsheet.contexts.master_data.domain.cliente import Pagina
from cheatsheet.contexts.master_data.domain.servicio import (
    MENSAJE_PRECIO,
    FiltrosDeServicio,
    Servicio,
)
from cheatsheet.contexts.master_data.domain.valores import AlicuotaIVA, OrigenDato
from cheatsheet.contexts.master_data.infrastructure.ensamblado import DatosMaestros
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, status
from pydantic import BaseModel


class ServicioEntrada(BaseModel):
    """`precio` is a string on purpose — see the module docstring."""

    nombre: str
    precio: str
    alicuota_iva: AlicuotaIVA
    agendable: bool = False
    duracion_estandar_min: int | None = None


class EstadoEntrada(BaseModel):
    activo: bool


class ServicioSalida(BaseModel):
    id: str
    nombre: str
    #: A string on the way out too. The panel displays it and never arithmetics on it.
    precio: str
    alicuota_iva: AlicuotaIVA
    agendable: bool
    duracion_estandar_min: int | None = None
    origen: OrigenDato
    activo: bool


class ListadoSalida(BaseModel):
    servicios: list[ServicioSalida]
    total: int


def _precio(valor: str) -> Decimal:
    """From text to `Decimal`, with a malformed number answered as the story words it.

    `Decimal("abc")` raises `InvalidOperation`, and so does `Decimal("")`. Both mean the
    same thing to whoever is filling in the form, and the acceptance criterion has one
    message for the price being wrong.
    """
    try:
        return Decimal(valor.strip())
    except (InvalidOperation, ValueError) as exc:
        raise EntradaInvalida(MENSAJE_PRECIO) from exc


def _a_salida(servicio: Servicio) -> ServicioSalida:
    return ServicioSalida(
        id=str(servicio.id),
        nombre=servicio.nombre,
        precio=str(servicio.precio),
        alicuota_iva=servicio.alicuota_iva,
        agendable=servicio.agendable,
        duracion_estandar_min=servicio.duracion_estandar_min,
        origen=servicio.origen,
        activo=servicio.activo,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _datos(entrada: ServicioEntrada) -> DatosDeServicio:
    return DatosDeServicio(
        nombre=entrada.nombre,
        precio=_precio(entrada.precio),
        alicuota_iva=entrada.alicuota_iva,
        agendable=entrada.agendable,
        duracion_estandar_min=entrada.duracion_estandar_min,
    )


def _exigir(salida: ServicioSalida | None) -> ServicioSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


def crear_router(recursos: Recursos) -> APIRouter:
    # Prefix on inclusion, for the reason the other routers state: the listing route has
    # no path of its own and FastAPI rejects an empty path without a prefix.
    router = APIRouter(tags=["master_data"])
    router.include_router(_rutas_de_catalogo(recursos), prefix="/servicios")
    return router


def _rutas_de_catalogo(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request,
        texto: str | None = None,
        agendable: bool | None = None,
        solo_activos: bool = False,
        limite: int = 50,
        desplazamiento: int = 0,
    ) -> ListadoSalida:
        empresa_id, _, rol = _actor(request)
        salida: ListadoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            listado = await ListarServicios(servicios=piezas.servicios).ejecutar(
                empresa_id=empresa_id,
                rol=rol,
                filtros=FiltrosDeServicio(
                    texto=texto, agendable=agendable, solo_activos=solo_activos
                ),
                pagina=Pagina(limite=limite, desplazamiento=desplazamiento),
            )
            salida = ListadoSalida(
                servicios=[_a_salida(servicio) for servicio in listado.servicios],
                total=listado.total,
            )
        if salida is None:  # pragma: no cover — the unit of work always yields once
            raise RuntimeError("La unidad de trabajo no produjo un resultado")
        return salida

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def registrar(entrada: ServicioEntrada, request: Request) -> ServicioSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: ServicioSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            servicio = await RegistrarServicio(
                servicios=piezas.servicios,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                datos=_datos(entrada),
                direccion_ip=_ip(request),
            )
            salida = _a_salida(servicio)
        return _exigir(salida)

    @router.put("/{servicio_id}")
    async def editar(
        servicio_id: UUID, entrada: ServicioEntrada, request: Request
    ) -> ServicioSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: ServicioSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            servicio = await EditarServicio(
                servicios=piezas.servicios,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                servicio_id=servicio_id,
                datos=_datos(entrada),
                direccion_ip=_ip(request),
            )
            salida = _a_salida(servicio)
        return _exigir(salida)

    @router.put("/{servicio_id}/estado")
    async def cambiar_estado(
        servicio_id: UUID, entrada: EstadoEntrada, request: Request
    ) -> ServicioSalida:
        """Deactivate or reactivate. This is what the catalogue has instead of a delete."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: ServicioSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            servicio = await CambiarEstadoDeServicio(
                servicios=piezas.servicios,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                servicio_id=servicio_id,
                activo=entrada.activo,
                direccion_ip=_ip(request),
            )
            salida = _a_salida(servicio)
        return _exigir(salida)

    return router
