"""Adaptadores PostgreSQL de los dos repositorios de `scheduling`.

Las convenciones de siempre: mapeo a mano en los dos sentidos para que el dominio no cargue
una dependencia de framework (R1), y `empresa_id` nunca en un `WHERE` porque RLS ya acota.

**Acá vive la mitad más importante de la decisión D28.** `agregar` y `guardar` atrapan la
violación de la restricción de exclusión y la traducen a `FranjaOcupada`. Sin esa traducción,
un doble booking evitado por el motor llegaría a la pantalla como un 500 — el usuario vería
«error del sistema» donde la verdad es «ese horario ya está tomado», y volvería a intentar.

El nombre de la restricción se compara explícitamente: un `IntegrityError` puede venir de
cualquier otra cosa —una FK, el índice único de excepciones— y tragarse todos como «ocupado»
diría algo falso sobre la mitad de ellos.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cheatsheet.contexts.scheduling.application.errors import ExcepcionDuplicada, FranjaOcupada
from cheatsheet.contexts.scheduling.application.ports import FiltrosDeAgenda
from cheatsheet.contexts.scheduling.domain.recurso import (
    MENSAJE_EXCEPCION_DUPLICADA,
    ZONA_DE_LA_AGENDA,
    ExcepcionDeDisponibilidad,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoExcepcion,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import (
    ESTADOS_QUE_OCUPAN_LA_FRANJA,
    MENSAJE_HORARIO_OCUPADO,
    EstadoTurno,
    Franja,
    Turno,
)
from cheatsheet.contexts.scheduling.infrastructure.models import (
    ExcepcionDeDisponibilidadORM,
    PatronDeDisponibilidadORM,
    RecursoReservableORM,
    ServicioDeRecursoORM,
    TurnoORM,
)
from cheatsheet.shared.empresa import EmpresaId

#: Los nombres que pone la migración 0020. Se comparan tal cual contra el texto del
#: `IntegrityError` porque asyncpg no expone el nombre de la restricción de forma tipada.
RESTRICCION_SOLAPAMIENTO = "excl_turno_recurso_franja"
RESTRICCION_EXCEPCION = "uq_excepcion_recurso_fecha"


def _es(error: IntegrityError, restriccion: str) -> bool:
    return restriccion in str(error.orig)


class RepositorioRecursoPostgres:
    """Recursos reservables con su horario, sus excepciones y sus servicios.

    El recurso es un **agregado**: se lee y se escribe entero, incluidas las tres tablas hijas.
    Guardar reemplaza los hijos en lugar de reconciliarlos fila por fila — un horario semanal
    tiene siete filas en el peor caso, y una reconciliación fina cambiaría un `DELETE` barato
    por un montón de código que puede equivocarse.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, recurso: RecursoReservable) -> None:
        self._sesion.add(
            RecursoReservableORM(
                id=recurso.id,
                empresa_id=recurso.empresa_id,
                tipo=recurso.tipo.value,
                nombre=recurso.nombre,
                activo=recurso.activo,
                created_at=recurso.created_at or datetime.now(tz=ZONA_DE_LA_AGENDA),
            )
        )
        await self._sesion.flush()
        await self._reemplazar_hijos(recurso)

    async def guardar(self, recurso: RecursoReservable) -> None:
        fila = await self._sesion.get(RecursoReservableORM, recurso.id)
        if fila is None:
            raise LookupError(f"El recurso {recurso.id} no existe para esta empresa")
        fila.nombre = recurso.nombre
        fila.tipo = recurso.tipo.value
        fila.activo = recurso.activo
        await self._reemplazar_hijos(recurso)

    async def buscar_por_id(self, recurso_id: UUID) -> RecursoReservable | None:
        fila = await self._sesion.get(RecursoReservableORM, recurso_id)
        return await self._hidratar(fila) if fila is not None else None

    async def listar(self, solo_activos: bool = False) -> list[RecursoReservable]:
        sentencia = select(RecursoReservableORM).order_by(RecursoReservableORM.nombre)
        if solo_activos:
            sentencia = sentencia.where(RecursoReservableORM.activo.is_(True))
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [await self._hidratar(fila) for fila in filas]

    async def _hidratar(self, fila: RecursoReservableORM) -> RecursoReservable:
        patrones = (
            (
                await self._sesion.execute(
                    select(PatronDeDisponibilidadORM)
                    .where(PatronDeDisponibilidadORM.recurso_id == fila.id)
                    .order_by(
                        PatronDeDisponibilidadORM.dia_semana,
                        PatronDeDisponibilidadORM.hora_inicio,
                    )
                )
            )
            .scalars()
            .all()
        )
        excepciones = (
            (
                await self._sesion.execute(
                    select(ExcepcionDeDisponibilidadORM)
                    .where(ExcepcionDeDisponibilidadORM.recurso_id == fila.id)
                    .order_by(ExcepcionDeDisponibilidadORM.fecha)
                )
            )
            .scalars()
            .all()
        )
        servicios = (
            (
                await self._sesion.execute(
                    select(ServicioDeRecursoORM.servicio_id).where(
                        ServicioDeRecursoORM.recurso_id == fila.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return RecursoReservable(
            id=fila.id,
            empresa_id=EmpresaId(fila.empresa_id),
            nombre=fila.nombre,
            tipo=TipoRecurso(fila.tipo),
            activo=fila.activo,
            patrones=tuple(
                PatronDeDisponibilidad(
                    dia_semana=uno.dia_semana,
                    hora_inicio=uno.hora_inicio,
                    hora_fin=uno.hora_fin,
                    duracion_slot_min=uno.duracion_slot_min,
                )
                for uno in patrones
            ),
            excepciones=tuple(
                ExcepcionDeDisponibilidad(
                    fecha=una.fecha,
                    tipo=TipoExcepcion(una.tipo),
                    franja_inicio=una.franja_inicio,
                    franja_duracion_min=una.franja_duracion_min,
                )
                for una in excepciones
            ),
            servicios=frozenset(servicios),
            created_at=fila.created_at,
        )

    async def _reemplazar_hijos(self, recurso: RecursoReservable) -> None:
        for modelo in (
            PatronDeDisponibilidadORM,
            ExcepcionDeDisponibilidadORM,
            ServicioDeRecursoORM,
        ):
            await self._sesion.execute(delete(modelo).where(modelo.recurso_id == recurso.id))
        for patron in recurso.patrones:
            self._sesion.add(
                PatronDeDisponibilidadORM(
                    id=uuid4(),
                    recurso_id=recurso.id,
                    dia_semana=patron.dia_semana,
                    hora_inicio=patron.hora_inicio,
                    hora_fin=patron.hora_fin,
                    duracion_slot_min=patron.duracion_slot_min,
                )
            )
        for excepcion in recurso.excepciones:
            self._sesion.add(
                ExcepcionDeDisponibilidadORM(
                    id=uuid4(),
                    recurso_id=recurso.id,
                    fecha=excepcion.fecha,
                    tipo=excepcion.tipo.value,
                    franja_inicio=excepcion.franja_inicio,
                    franja_duracion_min=excepcion.franja_duracion_min,
                )
            )
        for servicio_id in sorted(recurso.servicios):
            self._sesion.add(ServicioDeRecursoORM(recurso_id=recurso.id, servicio_id=servicio_id))
        try:
            await self._sesion.flush()
        except IntegrityError as exc:
            if _es(exc, RESTRICCION_EXCEPCION):
                # HU-E7-05 RN-02, ganada por el índice y no por el `if` del agregado.
                raise ExcepcionDuplicada(MENSAJE_EXCEPCION_DUPLICADA) from exc
            raise


class RepositorioTurnoPostgres:
    """Turnos, sobre PostgreSQL. **Sin `eliminar`**: un turno se cancela.

    `agregar` y `guardar` son los dos únicos lugares del sistema donde se decide si una franja
    estaba libre, y los dos delegan la decisión en el motor.
    """

    def __init__(self, sesion: AsyncSession) -> None:
        self._sesion = sesion

    async def agregar(self, turno: Turno) -> None:
        self._sesion.add(_a_fila(turno, TurnoORM()))
        await self._flush_o_ocupado()

    async def guardar(self, turno: Turno) -> None:
        fila = await self._sesion.get(TurnoORM, turno.id)
        if fila is None:
            raise LookupError(f"El turno {turno.id} no existe para esta empresa")
        _a_fila(turno, fila)
        await self._flush_o_ocupado()

    async def buscar_por_id(self, turno_id: UUID) -> Turno | None:
        fila = await self._sesion.get(TurnoORM, turno_id)
        return _a_dominio(fila) if fila is not None else None

    async def listar(self, filtros: FiltrosDeAgenda) -> list[Turno]:
        sentencia = select(TurnoORM)
        if filtros.recurso_id is not None:
            sentencia = sentencia.where(TurnoORM.recurso_id == filtros.recurso_id)
        if filtros.desde is not None:
            sentencia = sentencia.where(TurnoORM.franja_inicio >= filtros.desde)
        if filtros.hasta is not None:
            sentencia = sentencia.where(TurnoORM.franja_inicio < filtros.hasta)
        if filtros.estados:
            sentencia = sentencia.where(
                TurnoORM.estado.in_([estado.value for estado in filtros.estados])
            )
        # La agenda se lee de arriba hacia abajo por hora: es como se mira un día.
        sentencia = sentencia.order_by(TurnoORM.franja_inicio.asc())
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def ocupados_en(self, recurso_id: UUID, dia: date) -> list[Turno]:
        """Los turnos que ocupan la franja de ese recurso ese día, en hora local de la agenda.

        Cuentan los abiertos y los **completados** (D95). Los cancelados y los no-show **no**:
        su franja quedó libre, y la restricción de exclusión tampoco los considera. Si acá
        contaran, la pantalla tacharía horarios que en realidad se pueden reservar.
        """
        inicio = datetime.combine(dia, time.min, tzinfo=ZONA_DE_LA_AGENDA)
        sentencia = (
            select(TurnoORM)
            .where(TurnoORM.recurso_id == recurso_id)
            .where(TurnoORM.franja_inicio >= inicio)
            .where(TurnoORM.franja_inicio < inicio + timedelta(days=1))
            .where(TurnoORM.estado.in_([estado.value for estado in ESTADOS_QUE_OCUPAN_LA_FRANJA]))
            .order_by(TurnoORM.franja_inicio)
        )
        filas = (await self._sesion.execute(sentencia)).scalars().all()
        return [_a_dominio(fila) for fila in filas]

    async def _flush_o_ocupado(self) -> None:
        try:
            await self._sesion.flush()
        except IntegrityError as exc:
            if _es(exc, RESTRICCION_SOLAPAMIENTO):
                # **Esta línea es la decisión D28 llegando a la pantalla.** El motor rechazó el
                # solapamiento; acá se convierte en la frase que las historias escribieron.
                raise FranjaOcupada(MENSAJE_HORARIO_OCUPADO) from exc
            raise


def _a_dominio(fila: TurnoORM) -> Turno:
    return Turno(
        id=fila.id,
        empresa_id=EmpresaId(fila.empresa_id),
        cliente_id=fila.cliente_id,
        servicio_id=fila.servicio_id,
        recurso_id=fila.recurso_id,
        franja=Franja(inicio=fila.franja_inicio, duracion_min=fila.franja_duracion_min),
        estado=EstadoTurno(fila.estado),
        canal_reserva=fila.canal_reserva,
        cobro_id=fila.cobro_id,
        created_at=fila.created_at,
        updated_at=fila.updated_at,
    )


def _a_fila(turno: Turno, fila: TurnoORM) -> TurnoORM:
    fila.id = turno.id
    fila.empresa_id = turno.empresa_id
    fila.cliente_id = turno.cliente_id
    fila.servicio_id = turno.servicio_id
    fila.recurso_id = turno.recurso_id
    fila.cobro_id = turno.cobro_id
    fila.franja_inicio = turno.franja.inicio
    fila.franja_duracion_min = turno.franja.duracion_min
    fila.estado = turno.estado.value
    fila.canal_reserva = turno.canal_reserva
    fila.created_at = turno.created_at or datetime.now(tz=ZONA_DE_LA_AGENDA)
    fila.updated_at = turno.updated_at or fila.created_at
    return fila


__all__ = ["RepositorioRecursoPostgres", "RepositorioTurnoPostgres"]
