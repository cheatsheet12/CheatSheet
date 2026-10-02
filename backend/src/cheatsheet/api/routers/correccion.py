"""HTTP surface of the correction of existing data (HU-E4-05 RN-09, PAN-DM-01).

Four endpoints, all for the **Administrador**: the report (a dry-run that writes nothing),
the application, the list of runs and the restoration of one of them. The guard is the use
case, not this router: the role travels in the request and is handed to it, exactly as in
`clientes.py`.

The errors need no handler of their own. `CorreccionEnCurso` is an `InvarianteViolada` and
answers 409; `PermisoDenegado` answers 403; `CorridaNoEncontrada` is an `EntradaInvalida`
like `CategoriaNoEncontrada`, so it answers 422 with its message.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypeVar
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.master_data.application.correccion import (
    AplicarCorreccion,
    InformarCorreccion,
    InformeDeCorreccion,
    ListarCorridas,
    RestaurarCorreccion,
)
from cheatsheet.contexts.master_data.infrastructure.ensamblado import DatosMaestros
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request, status
from pydantic import BaseModel

_Salida = TypeVar("_Salida")


class EjemploSalida(BaseModel):
    antes: str
    despues: str


class InformeSalida(BaseModel):
    #: Keyed by `CLIENTE`, `SERVICIO`, `CATEGORIA`.
    a_corregir: dict[str, int]
    #: Keyed by `COLISION_DE_CATEGORIA`, `NOMBRE_INVALIDO`, `DURACION_FUERA_DE_REGLA`.
    omitidos: dict[str, int]
    ejemplos: dict[str, list[EjemploSalida]]


class CorreccionSalida(BaseModel):
    corrida_id: str
    conteos: dict[str, int]


class RestauracionSalida(BaseModel):
    restaurados: int
    conservados: int


class CorridaSalida(BaseModel):
    corrida_id: str
    creada_en: datetime
    cantidad: int


class ListadoDeCorridasSalida(BaseModel):
    corridas: list[CorridaSalida]


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _informe_a_salida(informe: InformeDeCorreccion) -> InformeSalida:
    return InformeSalida(
        a_corregir={entidad.value: n for entidad, n in informe.a_corregir.items()},
        omitidos={motivo.value: n for motivo, n in informe.omitidos.items()},
        ejemplos={
            entidad.value: [EjemploSalida(antes=e.antes, despues=e.despues) for e in ejemplos]
            for entidad, ejemplos in informe.ejemplos.items()
        },
    )


def _exigir(salida: _Salida | None) -> _Salida:
    if salida is None:  # pragma: no cover — the unit of work always yields once
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(prefix="/datos-maestros/correccion", tags=["master_data"])

    @router.get("/informe")
    async def informar(request: Request) -> InformeSalida:
        """The dry-run. Writes nothing; the examples show names only to this company's admin."""
        empresa_id, _, rol = _actor(request)
        salida: InformeSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            informe = await InformarCorreccion(correccion=piezas.correccion).ejecutar(
                empresa_id=empresa_id, rol=rol
            )
            salida = _informe_a_salida(informe)
        return _exigir(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def aplicar(request: Request) -> CorreccionSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: CorreccionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            resultado = await AplicarCorreccion(
                correccion=piezas.correccion, publicador=unidad.publicador, reloj=unidad.reloj
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                direccion_ip=_ip(request),
            )
            salida = CorreccionSalida(
                corrida_id=str(resultado.corrida_id), conteos=dict(resultado.conteos)
            )
        return _exigir(salida)

    @router.get("/corridas")
    async def listar(request: Request) -> ListadoDeCorridasSalida:
        empresa_id, _, rol = _actor(request)
        salida: ListadoDeCorridasSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            corridas = await ListarCorridas(correccion=piezas.correccion).ejecutar(
                empresa_id=empresa_id, rol=rol
            )
            salida = ListadoDeCorridasSalida(
                corridas=[
                    CorridaSalida(
                        corrida_id=str(c.corrida_id), creada_en=c.creada_en, cantidad=c.cantidad
                    )
                    for c in corridas
                ]
            )
        return _exigir(salida)

    @router.post("/{corrida_id}/restauracion")
    async def restaurar(corrida_id: UUID, request: Request) -> RestauracionSalida:
        empresa_id, usuario_id, rol = _actor(request)
        salida: RestauracionSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = DatosMaestros.armar(unidad)
            resultado = await RestaurarCorreccion(
                correccion=piezas.correccion, publicador=unidad.publicador, reloj=unidad.reloj
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                corrida_id=corrida_id,
                direccion_ip=_ip(request),
            )
            salida = RestauracionSalida(
                restaurados=resultado.restaurados, conservados=resultado.conservados
            )
        return _exigir(salida)

    return router
