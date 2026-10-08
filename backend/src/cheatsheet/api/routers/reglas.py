"""Superficie HTTP de las reglas de negocio (HU-E11-01, PAN-CFG-RN).

**No hay `DELETE`.** RN-04 pide desactivar, y una regla borrada deja la bitácora apuntando a
algo que ya no existe. Es `PUT /{id}/estado`, la misma forma que los puntos de venta y los
clientes.

**Sólo el Administrador escribe**, y el guarda vive en el caso de uso.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.contexts.business_config.application.atencion import (
    ConfigurarHorarioDeAtencion,
    configuracion_de_atencion_desde,
)
from cheatsheet.contexts.business_config.application.reglas import (
    CambiarEstadoDeRegla,
    ConfigurarEscalamiento,
    ListarReglas,
    configuracion_desde,
)
from cheatsheet.contexts.business_config.domain.regla import ReglaDeNegocio
from cheatsheet.contexts.business_config.infrastructure.ensamblado import (
    ConfiguracionDeNegocio,
)
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.roles import RolUsuario
from fastapi import APIRouter, Request
from pydantic import BaseModel


class PasoEntrada(BaseModel):
    dias: int
    canal: str


class EscalamientoEntrada(BaseModel):
    pasos: list[PasoEntrada]
    prioridad: int = 0


class FranjaEntrada(BaseModel):
    desde: str
    hasta: str


class DiaEntrada(BaseModel):
    dia: int
    franjas: list[FranjaEntrada]


class HorarioDeAtencionEntrada(BaseModel):
    dias: list[DiaEntrada]
    fechas_cerradas: list[str] = []
    politica: str = "AGENTE_RESPONDE"
    prioridad: int = 0


class EstadoEntrada(BaseModel):
    activa: bool


class ReglaSalida(BaseModel):
    id: UUID
    tipo: str
    #: El JSONB tal cual. La pantalla sabe leer el de su tipo, y devolverlo entero es lo que
    #: permite que un tipo nuevo no necesite tocar este archivo.
    configuracion: dict[str, object]
    prioridad: int
    activa: bool
    created_at: datetime
    updated_at: datetime | None


class ListadoSalida(BaseModel):
    reglas: list[ReglaSalida]


def _a_salida(regla: ReglaDeNegocio) -> ReglaSalida:
    return ReglaSalida(
        id=regla.id,
        tipo=regla.tipo.value,
        configuracion=dict(regla.configuracion),
        prioridad=regla.prioridad,
        activa=regla.activa,
        created_at=regla.created_at,
        updated_at=regla.updated_at,
    )


def _actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def crear_router(recursos: Recursos) -> APIRouter:
    router = APIRouter(tags=["business_config"])
    router.include_router(_rutas(recursos), prefix="/reglas")
    return router


def _rutas(recursos: Recursos) -> APIRouter:
    router = APIRouter()

    @router.get("")
    async def listar(request: Request) -> ListadoSalida:
        """PAN-CFG-RN. Todos los roles leen; sólo el Administrador ve las acciones."""
        empresa_id, _, _ = _actor(request)
        salida = ListadoSalida(reglas=[])
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = ConfiguracionDeNegocio.armar(unidad)
            reglas = await ListarReglas(piezas.reglas).ejecutar()
            salida = ListadoSalida(reglas=[_a_salida(uno) for uno in reglas])
        return salida

    @router.put("/escalamiento")
    async def configurar(request: Request, entrada: EscalamientoEntrada) -> ReglaSalida:
        """RN-02. `PUT` y no `POST` porque **reemplaza**: una empresa tiene una cadena de
        escalamiento, no un catálogo de cadenas."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: ReglaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = ConfiguracionDeNegocio.armar(unidad)
            regla = await ConfigurarEscalamiento(
                reglas=piezas.reglas, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                configuracion=configuracion_desde(
                    {"pasos": [paso.model_dump() for paso in entrada.pasos]}
                ),
                ahora=unidad.reloj.ahora(),
                prioridad=entrada.prioridad,
            )
            salida = _a_salida(regla)
        return _exigir(salida)

    @router.put("/horario-de-atencion")
    async def configurar_horario(
        request: Request, entrada: HorarioDeAtencionEntrada
    ) -> ReglaSalida:
        """HS-T2 RN-04. `PUT` porque **reemplaza**: una empresa tiene un horario de atención."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: ReglaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = ConfiguracionDeNegocio.armar(unidad)
            regla = await ConfigurarHorarioDeAtencion(
                reglas=piezas.reglas, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                configuracion=configuracion_de_atencion_desde(
                    {
                        "dias": [dia.model_dump() for dia in entrada.dias],
                        "fechas_cerradas": entrada.fechas_cerradas,
                        "politica": entrada.politica,
                    }
                ),
                ahora=unidad.reloj.ahora(),
                prioridad=entrada.prioridad,
            )
            salida = _a_salida(regla)
        return _exigir(salida)

    @router.put("/{regla_id}/estado")
    async def cambiar_estado(
        request: Request, regla_id: UUID, entrada: EstadoEntrada
    ) -> ReglaSalida:
        """RN-04. Desactivar deja de aplicar de inmediato, sin tocar lo ya procesado."""
        empresa_id, usuario_id, rol = _actor(request)
        salida: ReglaSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = ConfiguracionDeNegocio.armar(unidad)
            regla = await CambiarEstadoDeRegla(
                reglas=piezas.reglas, publicador=unidad.publicador
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                regla_id=regla_id,
                activa=entrada.activa,
                ahora=unidad.reloj.ahora(),
            )
            salida = _a_salida(regla)
        return _exigir(salida)

    return router


def _exigir(salida: ReglaSalida | None) -> ReglaSalida:
    if salida is None:  # pragma: no cover — la unidad de trabajo siempre rinde una vez
        raise RuntimeError("La unidad de trabajo no produjo un resultado")
    return salida
