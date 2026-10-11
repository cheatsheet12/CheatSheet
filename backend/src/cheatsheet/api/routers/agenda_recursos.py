"""Rutas de recursos reservables: PAN-AGE-03 (HU-E7-04 y HU-E7-05)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from cheatsheet.api.agenda import armar_catalogo
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.routers.agenda_forma import (
    DisponibilidadEntrada,
    EstadoEntrada,
    ExcepcionEntrada,
    ListadoDeRecursos,
    RecursoEntrada,
    RecursoSalida,
    ServicioSalida,
    ServiciosEntrada,
    a_recurso,
    actor,
    excepcion,
    exigir,
    patrones,
    tipo_de_recurso,
)
from cheatsheet.contexts.scheduling.application.recursos import (
    AsociarServicios,
    CambiarEstadoDeRecurso,
    ConfigurarDisponibilidad,
    ListarRecursos,
    QuitarExcepcion,
    RegistrarExcepcion,
    RegistrarRecurso,
)
from cheatsheet.contexts.scheduling.infrastructure.ensamblado import Agenda
from fastapi import APIRouter, Query, Request, status


def rutas_de_recursos(recursos: Recursos) -> APIRouter:
    """PAN-AGE-03 (HU-E7-04 y HU-E7-05). Todos leen; sólo el Administrador escribe."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request, solo_activos: Annotated[bool, Query()] = False
    ) -> ListadoDeRecursos:
        empresa_id, _, _ = actor(request)
        salida: ListadoDeRecursos | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            encontrados = await ListarRecursos(piezas.recursos).ejecutar(solo_activos=solo_activos)
            salida = ListadoDeRecursos(recursos=[a_recurso(uno) for uno in encontrados])
        return exigir(salida)

    @router.get("/servicios")
    async def servicios_agendables(request: Request) -> list[ServicioSalida]:
        """Los servicios que se pueden reservar, para poblar el selector de PAN-AGE-02.

        Vive bajo `/recursos` y no bajo `/servicios` a propósito: el catálogo completo es de
        `master_data` y ya tiene su ruta; esto es la vista que la agenda necesita, filtrada por
        una regla de este épico.
        """
        empresa_id, _, rol = actor(request)
        salida: list[ServicioSalida] = []
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            catalogo = armar_catalogo(unidad, empresa_id=empresa_id, rol=rol)
            salida = [
                ServicioSalida(
                    id=uno.id,
                    nombre=uno.nombre,
                    duracion_estandar_min=uno.duracion_estandar_min,
                )
                for uno in await catalogo.listar_agendables()
            ]
        return salida

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def registrar(request: Request, entrada: RecursoEntrada) -> RecursoSalida:
        empresa_id, usuario_id, rol = actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await RegistrarRecurso(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                nombre=entrada.nombre,
                tipo=tipo_de_recurso(entrada.tipo),
                patrones=patrones(entrada.patrones),
                servicios=frozenset(entrada.servicios),
                intervalo_entre_turnos_min=entrada.intervalo_entre_turnos_min or 0,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_recurso(recurso)
        return exigir(salida)

    router.include_router(_rutas_de_configuracion(recursos), prefix="/{recurso_id}")
    router.include_router(_rutas_de_excepciones(recursos), prefix="/{recurso_id}")
    return router


def _rutas_de_configuracion(recursos: Recursos) -> APIRouter:
    """Los tres `PUT` de HU-E7-04, en su propio grupo para no pasar del límite de complejidad.

    Los tres **reemplazan** en vez de acumular, que es lo que hace que configurar un recurso
    sea una operación y no una serie de parches con orden significativo.
    """
    router = APIRouter()

    @router.put("/disponibilidad")
    async def disponibilidad(
        request: Request, recurso_id: UUID, entrada: DisponibilidadEntrada
    ) -> RecursoSalida:
        """`PUT` y no `POST`: **reemplaza** el horario semanal (HU-E7-04 RN-01)."""
        empresa_id, usuario_id, rol = actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await ConfigurarDisponibilidad(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                patrones=patrones(entrada.patrones),
                intervalo_entre_turnos_min=entrada.intervalo_entre_turnos_min,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_recurso(recurso)
        return exigir(salida)

    @router.put("/servicios")
    async def asociar(
        request: Request, recurso_id: UUID, entrada: ServiciosEntrada
    ) -> RecursoSalida:
        empresa_id, usuario_id, rol = actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await AsociarServicios(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                servicios=frozenset(entrada.servicios),
                ahora=unidad.reloj.ahora(),
            )
            salida = a_recurso(recurso)
        return exigir(salida)

    @router.put("/estado")
    async def estado(request: Request, recurso_id: UUID, entrada: EstadoEntrada) -> RecursoSalida:
        """Activar o desactivar. Lo que la configuración tiene en lugar de un borrado."""
        empresa_id, usuario_id, rol = actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await CambiarEstadoDeRecurso(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                activo=entrada.activo,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_recurso(recurso)
        return exigir(salida)

    return router


def _rutas_de_excepciones(recursos: Recursos) -> APIRouter:
    """HU-E7-05, en su propio grupo para no pasar del límite de complejidad del archivo."""
    router = APIRouter()

    @router.post("/excepciones", status_code=status.HTTP_201_CREATED)
    async def agregar(
        request: Request, recurso_id: UUID, entrada: ExcepcionEntrada
    ) -> RecursoSalida:
        empresa_id, usuario_id, rol = actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await RegistrarExcepcion(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                excepcion=excepcion(entrada),
                ahora=unidad.reloj.ahora(),
            )
            salida = a_recurso(recurso)
        return exigir(salida)

    @router.delete("/excepciones/{fecha}")
    async def quitar(request: Request, recurso_id: UUID, fecha: date) -> RecursoSalida:
        """El único `DELETE` del épico, y no borra una entidad del negocio.

        Una excepción es una anotación sobre un calendario: sacarla es volver al horario
        habitual, no perder un registro. Corregir una es quitarla y volver a agregarla, lo que
        evita tener que decidir qué significa cambiarle el tipo.
        """
        empresa_id, usuario_id, rol = actor(request)
        salida: RecursoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            recurso = await QuitarExcepcion(piezas.recursos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                recurso_id=recurso_id,
                fecha=fecha,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_recurso(recurso)
        return exigir(salida)

    return router
