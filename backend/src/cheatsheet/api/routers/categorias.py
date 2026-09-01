"""HTTP surface for categories and classification (HU-E4-03, HU-E4-04, PAN-DM-03).

**This is the only router in the system with a `DELETE`**, and the reason is in migration
0010: a category is referenced by nothing outside `master_data`, and HU-E4-03 asks for the
operation in as many words. `/clientes` and `/servicios` deliberately have none.

The classification endpoints live here rather than under `/clientes/{id}/categorias`
because the operation belongs to neither element: it is a link, and `ClasificarCliente`
reads both sides before writing it. Keeping them together also keeps the scope rule —
HU-E4-04 RN-01 — in one file.
"""

from __future__ import annotations

from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.master_data.application.categorias import (
    ClasificarCliente,
    ClasificarServicio,
    EditarCategoria,
    EliminarCategoria,
    ListarCategorias,
    RegistrarCategoria,
    VerClasificacion,
)
from cheatsheet.contexts.master_data.domain.categoria import CategoriaEmpresa
from cheatsheet.contexts.master_data.domain.valores import AmbitoDeCategoria
from cheatsheet.contexts.master_data.infrastructure.ensamblado import DatosMaestros
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, status
from pydantic import BaseModel


class CategoriaEntrada(BaseModel):
    nombre: str
    aplica_a: AmbitoDeCategoria


class ClasificacionEntrada(BaseModel):
    categoria_id: UUID
    #: `True` assigns, `False` removes. One endpoint and not two, because the screen has
    #: one control — a checkbox per category — and it toggles.
    asignar: bool


class CategoriaSalida(BaseModel):
    id: str
    nombre: str
    aplica_a: AmbitoDeCategoria


class ListadoDeCategoriasSalida(BaseModel):
    categorias: list[CategoriaSalida]


def _a_salida(categoria: CategoriaEmpresa) -> CategoriaSalida:
    return CategoriaSalida(
        id=str(categoria.id), nombre=categoria.nombre, aplica_a=categoria.aplica_a
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _exigir(salida: CategoriaSalida | None) -> CategoriaSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


def _exigir_listado(salida: ListadoDeCategoriasSalida | None) -> ListadoDeCategoriasSalida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["master_data"])
    router.include_router(_rutas_de_categorias(recursos), prefix="/categorias")
    router.include_router(_rutas_de_clasificacion(recursos))
    return router


def _rutas_de_categorias(recursos: Recursos) -> APIRouter:
    """PAN-DM-03: the CRUD of HU-E4-03."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request, aplica_a: AmbitoDeCategoria | None = None
    ) -> ListadoDeCategoriasSalida:
        """`aplica_a` filters by usability, not equality — asking for `CLIENTE` also
        returns the `AMBOS` ones, which is what the client form's dropdown needs.
        """
        empresa_id, _, rol = _actor(request)
        salida: ListadoDeCategoriasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            encontradas = await ListarCategorias(categorias=piezas.categorias).ejecutar(
                empresa_id=empresa_id, rol=rol, aplica_a=aplica_a
            )
            salida = ListadoDeCategoriasSalida(
                categorias=[_a_salida(categoria) for categoria in encontradas]
            )
        return _exigir_listado(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def registrar(entrada: CategoriaEntrada, request: Request) -> CategoriaSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: CategoriaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            categoria = await RegistrarCategoria(
                categorias=piezas.categorias, publicador=unidad.publicador, reloj=unidad.reloj
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                nombre=entrada.nombre,
                aplica_a=entrada.aplica_a,
                direccion_ip=_ip(request),
            )
            salida = _a_salida(categoria)
        return _exigir(salida)

    @router.put("/{categoria_id}")
    async def editar(
        categoria_id: UUID, entrada: CategoriaEntrada, request: Request
    ) -> CategoriaSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: CategoriaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            categoria = await EditarCategoria(
                categorias=piezas.categorias, publicador=unidad.publicador, reloj=unidad.reloj
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                categoria_id=categoria_id,
                nombre=entrada.nombre,
                aplica_a=entrada.aplica_a,
                direccion_ip=_ip(request),
            )
            salida = _a_salida(categoria)
        return _exigir(salida)

    # `response_model=None` is not decoration. This module has `from __future__ import
    # annotations`, like every other, so `-> None` reaches FastAPI as the string "None" and
    # is resolved to `NoneType` — a class, and therefore truthy — which makes FastAPI
    # believe a 204 has a response model and assert at import time. The whole application
    # then fails to build, which is exactly what happened the first time this ran: 6
    # failures and 81 errors, none of them in this file.
    @router.delete("/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
    async def eliminar(categoria_id: UUID, request: Request) -> None:
        """RN-03: the classified elements lose the label and keep everything else.

        The only `DELETE` the API exposes. See migration 0010 for why this table gets one
        and `cliente` and `servicio` do not.
        """
        empresa_id, usuario_id, rol = _actor(request)
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            await EliminarCategoria(
                categorias=piezas.categorias, publicador=unidad.publicador, reloj=unidad.reloj
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                categoria_id=categoria_id,
                direccion_ip=_ip(request),
            )

    return router


def _rutas_de_clasificacion(recursos: Recursos) -> APIRouter:
    """HU-E4-04, on both elements. One endpoint each, toggling with `asignar`."""
    router = APIRouter()

    @router.get("/clientes/{cliente_id}/categorias")
    async def ver_de_cliente(cliente_id: UUID, request: Request) -> ListadoDeCategoriasSalida:
        """What the element already carries, so the checkboxes open already ticked."""
        empresa_id, _, rol = _actor(request)
        salida: ListadoDeCategoriasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            categorias = await VerClasificacion(clasificaciones=piezas.clasificaciones).de_cliente(
                cliente_id=cliente_id, rol=rol
            )
            salida = ListadoDeCategoriasSalida(
                categorias=[_a_salida(categoria) for categoria in categorias]
            )
        return _exigir_listado(salida)

    @router.get("/servicios/{servicio_id}/categorias")
    async def ver_de_servicio(servicio_id: UUID, request: Request) -> ListadoDeCategoriasSalida:
        empresa_id, _, rol = _actor(request)
        salida: ListadoDeCategoriasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            categorias = await VerClasificacion(clasificaciones=piezas.clasificaciones).de_servicio(
                servicio_id=servicio_id, rol=rol
            )
            salida = ListadoDeCategoriasSalida(
                categorias=[_a_salida(categoria) for categoria in categorias]
            )
        return _exigir_listado(salida)

    @router.put("/clientes/{cliente_id}/categorias")
    async def clasificar_cliente(
        cliente_id: UUID, entrada: ClasificacionEntrada, request: Request
    ) -> ListadoDeCategoriasSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: ListadoDeCategoriasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            categorias = await ClasificarCliente(
                clientes=piezas.clientes,
                categorias=piezas.categorias,
                clasificaciones=piezas.clasificaciones,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                cliente_id=cliente_id,
                categoria_id=entrada.categoria_id,
                asignar=entrada.asignar,
                direccion_ip=_ip(request),
            )
            salida = ListadoDeCategoriasSalida(
                categorias=[_a_salida(categoria) for categoria in categorias]
            )
        return _exigir_listado(salida)

    @router.put("/servicios/{servicio_id}/categorias")
    async def clasificar_servicio(
        servicio_id: UUID, entrada: ClasificacionEntrada, request: Request
    ) -> ListadoDeCategoriasSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: ListadoDeCategoriasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            categorias = await ClasificarServicio(
                servicios=piezas.servicios,
                categorias=piezas.categorias,
                clasificaciones=piezas.clasificaciones,
                publicador=unidad.publicador,
                reloj=unidad.reloj,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                servicio_id=servicio_id,
                categoria_id=entrada.categoria_id,
                asignar=entrada.asignar,
                direccion_ip=_ip(request),
            )
            salida = ListadoDeCategoriasSalida(
                categorias=[_a_salida(categoria) for categoria in categorias]
            )
        return _exigir_listado(salida)

    return router
