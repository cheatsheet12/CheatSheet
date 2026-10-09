"""Rutas de turnos: PAN-AGE-01 y PAN-AGE-02 (HU-E7-01, HU-E7-02, HU-E7-03 y HU-E7-06)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from cheatsheet.api.agenda import armar_avisador, armar_catalogo
from cheatsheet.api.dependencies import Recursos, unidad_de_trabajo
from cheatsheet.api.mensajeria import armar_mensajeria
from cheatsheet.api.routers.agenda_forma import (
    AsistenciaEntrada,
    DisponibilidadSalida,
    HorarioSalida,
    ListadoDeTurnos,
    ReprogramacionEntrada,
    TurnoEntrada,
    TurnoSalida,
    a_turno,
    actor,
    exigir,
)
from cheatsheet.contexts.scheduling.application.disponibilidad import VerHorariosDisponibles
from cheatsheet.contexts.scheduling.application.ports import FiltrosDeAgenda
from cheatsheet.contexts.scheduling.application.turnos import (
    CancelarTurno,
    RegistrarAsistencia,
    ReprogramarTurno,
    ReservarTurno,
    VerAgenda,
    VerTurno,
)
from cheatsheet.contexts.scheduling.domain.recurso import ZONA_DE_LA_AGENDA
from cheatsheet.contexts.scheduling.domain.turno import EstadoTurno
from cheatsheet.contexts.scheduling.infrastructure.ensamblado import Agenda
from fastapi import APIRouter, Query, Request, status


def _rango(desde: datetime | None, hasta: datetime | None, hoy: date) -> tuple[datetime, datetime]:
    """El rango pedido, o el día en curso (HU-E7-01 RN-01).

    El día se define en la zona de la agenda y no en UTC: un turno de las 22 de un martes es
    del martes para quien lo atiende, aunque en UTC ya sea miércoles.
    """
    if desde is not None and hasta is not None:
        return desde, hasta
    inicio = datetime.combine(hoy, time.min, tzinfo=ZONA_DE_LA_AGENDA)
    return desde or inicio, hasta or inicio + timedelta(days=1)


def rutas_de_turnos(recursos: Recursos) -> APIRouter:
    """PAN-AGE-01 y PAN-AGE-02. Todos leen; Administrador y Operador gestionan."""
    router = APIRouter()

    @router.get("")
    async def listar(
        request: Request,
        recurso_id: Annotated[UUID | None, Query()] = None,
        desde: Annotated[datetime | None, Query()] = None,
        hasta: Annotated[datetime | None, Query()] = None,
        estado: Annotated[str | None, Query()] = None,
    ) -> ListadoDeTurnos:
        """PAN-AGE-01 (HU-E7-01 RN-01). Sin rango explícito, el día en curso."""
        empresa_id, _, _ = actor(request)
        salida: ListadoDeTurnos | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            ahora = unidad.reloj.ahora()
            inicio, fin = _rango(desde, hasta, ahora.astimezone(ZONA_DE_LA_AGENDA).date())
            # Un estado desconocido se vuelve «sin filtro» y no un 422: el query string viene
            # de una URL que alguien pudo editar, y la respuesta honesta a un filtro que no
            # entendemos es la agenda sin filtrar.
            estados = (
                (EstadoTurno[estado],)
                if estado is not None and estado in EstadoTurno.__members__
                else ()
            )
            piezas = Agenda.armar(unidad)
            turnos = await VerAgenda(piezas.turnos).ejecutar(
                FiltrosDeAgenda(recurso_id=recurso_id, desde=inicio, hasta=fin, estados=estados)
            )
            salida = ListadoDeTurnos(turnos=[a_turno(uno, ahora) for uno in turnos])
        return exigir(salida)

    @router.get("/disponibilidad")
    async def disponibilidad(
        request: Request,
        recurso_id: Annotated[UUID, Query()],
        fecha: Annotated[date, Query()],
        servicio_id: Annotated[UUID, Query()],
    ) -> DisponibilidadSalida:
        """Los horarios que ese recurso ofrece ese día **para ese servicio**, con los ocupados.

        Lo que puebla el selector de PAN-AGE-02. La duración del turno es la del servicio, así
        que sin `servicio_id` no hay grilla (D96). Ver la advertencia de `DisponibilidadSalida`.
        """
        empresa_id, _, rol = actor(request)
        salida: DisponibilidadSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            horarios = await VerHorariosDisponibles(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                servicios=armar_catalogo(unidad, empresa_id=empresa_id, rol=rol),
            ).ejecutar(
                recurso_id=recurso_id,
                servicio_id=servicio_id,
                fecha=fecha,
                # Los que ya pasaron no se ofrecen (D95). La carga a posteriori no usa esta
                # grilla: el Administrador escribe la fecha y la hora.
                ahora=unidad.reloj.ahora(),
            )
            salida = DisponibilidadSalida(
                fecha=fecha,
                horarios=[
                    HorarioSalida(inicio=uno.inicio, ocupado=uno.ocupado) for uno in horarios
                ],
            )
        return exigir(salida)

    @router.get("/{turno_id}")
    async def ver(request: Request, turno_id: UUID) -> TurnoSalida:
        """PAN-AGE-02. Todos los roles leen (HU-E7-01 RN-03)."""
        empresa_id, _, _ = actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            turno = await VerTurno(piezas.turnos).ejecutar(turno_id)
            salida = a_turno(turno, unidad.reloj.ahora())
        return exigir(salida)

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def reservar(request: Request, entrada: TurnoEntrada) -> TurnoSalida:
        """HU-E7-06. **201**: cuando esto contesta, la franja quedó tomada de verdad.

        Si estaba ocupada, el repositorio levanta `FranjaOcupada` y la respuesta es un 422 con
        la frase que escribió la historia.
        """
        empresa_id, usuario_id, rol = actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            canal = await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa_id)
            turno = await ReservarTurno(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                servicios=armar_catalogo(unidad, empresa_id=empresa_id, rol=rol),
                avisador=armar_avisador(unidad, empresa_id=empresa_id, rol=rol, canal=canal),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                cliente_id=entrada.cliente_id,
                servicio_id=entrada.servicio_id,
                recurso_id=entrada.recurso_id,
                inicio=entrada.inicio,
                ahora=unidad.reloj.ahora(),
                a_posteriori=entrada.a_posteriori,
            )
            salida = a_turno(turno, unidad.reloj.ahora())
        return exigir(salida)

    router.include_router(_rutas_de_gestion(recursos), prefix="/{turno_id}")
    return router


def _rutas_de_gestion(recursos: Recursos) -> APIRouter:
    """Las tres acciones de HU-E7-02 y HU-E7-03, en su propio grupo por complejidad."""
    router = APIRouter()

    @router.post("/cancelacion")
    async def cancelar(request: Request, turno_id: UUID) -> TurnoSalida:
        """HU-E7-02. Sin cuerpo: cancelar un turno no pide motivo.

        Distinto de cancelar un cobro, que sí lo pide (HU-E6-04 RN-02). La diferencia es del
        negocio y no del diseño: ahí se está dando de baja una deuda y acá se está liberando
        una franja, y ninguna historia de este épico pide el motivo.
        """
        empresa_id, usuario_id, rol = actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            canal = await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa_id)
            turno = await CancelarTurno(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                avisador=armar_avisador(unidad, empresa_id=empresa_id, rol=rol, canal=canal),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                turno_id=turno_id,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_turno(turno, unidad.reloj.ahora())
        return exigir(salida)

    @router.post("/reprogramacion")
    async def reprogramar(
        request: Request, turno_id: UUID, entrada: ReprogramacionEntrada
    ) -> TurnoSalida:
        """HU-E7-02 RN-02: mueve la franja y **conserva el estado**."""
        empresa_id, usuario_id, rol = actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            canal = await armar_mensajeria(unidad, recursos.settings, empresa_id=empresa_id)
            turno = await ReprogramarTurno(
                turnos=piezas.turnos,
                recursos=piezas.recursos,
                avisador=armar_avisador(unidad, empresa_id=empresa_id, rol=rol, canal=canal),
                publicador=unidad.publicador,
            ).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                turno_id=turno_id,
                inicio=entrada.inicio,
                ahora=unidad.reloj.ahora(),
                a_posteriori=entrada.a_posteriori,
            )
            salida = a_turno(turno, unidad.reloj.ahora())
        return exigir(salida)

    @router.post("/asistencia")
    async def asistencia(
        request: Request, turno_id: UUID, entrada: AsistenciaEntrada
    ) -> TurnoSalida:
        """HU-E7-03. Una sola ruta para las dos marcas: son la misma decisión con dos valores.

        Dos rutas —una por resultado— habrían hecho que agregar un tercero fuera una ruta más
        en vez de un valor más, y el frontend tendría que elegir a cuál llamar en lugar de
        mandar lo que el usuario apretó.
        """
        empresa_id, usuario_id, rol = actor(request)
        salida: TurnoSalida | None = None
        async for unidad in unidad_de_trabajo(recursos, empresa_id):
            piezas = Agenda.armar(unidad)
            turno = await RegistrarAsistencia(piezas.turnos, unidad.publicador).ejecutar(
                empresa_id=empresa_id,
                usuario_id=usuario_id,
                rol=rol,
                turno_id=turno_id,
                asistio=entrada.asistio,
                ahora=unidad.reloj.ahora(),
            )
            salida = a_turno(turno, unidad.reloj.ahora())
        return exigir(salida)

    return router
