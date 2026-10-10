"""La forma HTTP de la agenda: entradas, salidas y conversiones (HU-E7-01 … HU-E7-06).

Sale de `agenda.py` como la del tablero salió de `reporteria.py` (ver `tablero_salida.py`): el
router pasaba de las 400 líneas de `CLAUDE.md` §5. Las rutas de recursos y de turnos importan
de acá; este módulo no importa ninguna.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TypeVar
from uuid import UUID

from cheatsheet.contexts.scheduling.domain.recurso import (
    ExcepcionDeDisponibilidad,
    PatronDeDisponibilidad,
    RecursoReservable,
    TipoExcepcion,
    TipoRecurso,
)
from cheatsheet.contexts.scheduling.domain.turno import Turno
from cheatsheet.shared.empresa import EmpresaId, UsuarioId
from cheatsheet.shared.errors import EntradaInvalida
from cheatsheet.shared.roles import RolUsuario
from fastapi import Request
from pydantic import BaseModel

_T = TypeVar("_T")


# -- entradas -------------------------------------------------------------------------


class PatronEntrada(BaseModel):
    dia_semana: int
    #: `"09:00"`. Se parsea acá porque `time` es lo que el dominio guarda: mandar minutos
    #: desde medianoche haría que la fila de la base ya no se pudiera leer a ojo.
    hora_inicio: time
    hora_fin: time
    duracion_slot_min: int


class RecursoEntrada(BaseModel):
    nombre: str
    tipo: str
    patrones: list[PatronEntrada] = []
    servicios: list[UUID] = []
    #: HU-E7-04 RN-06. `None`: 0 al registrar, y al configurar conserva el actual.
    intervalo_entre_turnos_min: int | None = None


class DisponibilidadEntrada(BaseModel):
    patrones: list[PatronEntrada]
    intervalo_entre_turnos_min: int | None = None


class ServiciosEntrada(BaseModel):
    servicios: list[UUID]


class EstadoEntrada(BaseModel):
    activo: bool


class ExcepcionEntrada(BaseModel):
    fecha: date
    tipo: str
    franja_inicio: datetime | None = None
    franja_duracion_min: int | None = None


class TurnoEntrada(BaseModel):
    cliente_id: UUID
    servicio_id: UUID
    recurso_id: UUID
    inicio: datetime
    #: La duración es siempre la del servicio (HU-E7-06 RN-08): si un cliente viejo manda
    #: `duracion_min`, Pydantic lo ignora y nunca llega al caso de uso.
    #: La carga a posteriori (HU-E7-06 RN-07): sólo el Administrador, y siempre explícita. Un
    #: inicio pasado sin este indicador se rechaza igual que para cualquier rol.
    a_posteriori: bool = False


class ReprogramacionEntrada(BaseModel):
    inicio: datetime
    #: La corrección a posteriori (HU-E7-02 RN-07). Ver `TurnoEntrada.a_posteriori`.
    a_posteriori: bool = False


class AsistenciaEntrada(BaseModel):
    asistio: bool


# -- salidas --------------------------------------------------------------------------


class PatronSalida(BaseModel):
    dia_semana: int
    hora_inicio: time
    hora_fin: time
    duracion_slot_min: int


class ExcepcionSalida(BaseModel):
    fecha: date
    tipo: str
    franja_inicio: datetime | None
    franja_duracion_min: int | None


class RecursoSalida(BaseModel):
    id: UUID
    nombre: str
    tipo: str
    activo: bool
    patrones: list[PatronSalida]
    excepciones: list[ExcepcionSalida]
    servicios: list[UUID]
    intervalo_entre_turnos_min: int


class ListadoDeRecursos(BaseModel):
    recursos: list[RecursoSalida]


class TurnoSalida(BaseModel):
    id: UUID
    cliente_id: UUID
    servicio_id: UUID
    recurso_id: UUID
    cobro_id: UUID | None
    inicio: datetime
    duracion_min: int
    fin: datetime
    estado: str
    canal_reserva: str
    #: HU-E7-03 RN-01: la pantalla ofrece marcar asistencia sólo si esto es `True`.
    ya_transcurrio: bool
    #: HU-E7-03 RN-02: un turno completado habilita emitir el comprobante del servicio.
    habilita_facturacion: bool


class ListadoDeTurnos(BaseModel):
    turnos: list[TurnoSalida]


class ServicioSalida(BaseModel):
    id: UUID
    nombre: str
    duracion_estandar_min: int


class HorarioSalida(BaseModel):
    inicio: datetime
    ocupado: bool


class DisponibilidadSalida(BaseModel):
    """Los horarios que el recurso ofrece ese día, con los que ya están tomados marcados.

    **`ocupado` es una ayuda, no una garantía.** Entre esta respuesta y el `POST` que reserva
    puede entrar otro turno; quien decide es la restricción de exclusión (decisión D28), y por
    eso reservar puede fallar aunque acá figurara libre.
    """

    fecha: date
    horarios: list[HorarioSalida]


def a_recurso(recurso: RecursoReservable) -> RecursoSalida:
    return RecursoSalida(
        id=recurso.id,
        nombre=recurso.nombre,
        tipo=recurso.tipo.value,
        activo=recurso.activo,
        patrones=[
            PatronSalida(
                dia_semana=uno.dia_semana,
                hora_inicio=uno.hora_inicio,
                hora_fin=uno.hora_fin,
                duracion_slot_min=uno.duracion_slot_min,
            )
            for uno in recurso.patrones
        ],
        excepciones=[
            ExcepcionSalida(
                fecha=una.fecha,
                tipo=una.tipo.value,
                franja_inicio=una.franja_inicio,
                franja_duracion_min=una.franja_duracion_min,
            )
            for una in recurso.excepciones
        ],
        servicios=sorted(recurso.servicios),
        intervalo_entre_turnos_min=recurso.intervalo_entre_turnos_min,
    )


def a_turno(turno: Turno, ahora: datetime) -> TurnoSalida:
    return TurnoSalida(
        id=turno.id,
        cliente_id=turno.cliente_id,
        servicio_id=turno.servicio_id,
        recurso_id=turno.recurso_id,
        cobro_id=turno.cobro_id,
        inicio=turno.franja.inicio,
        duracion_min=turno.franja.duracion_min,
        fin=turno.franja.fin,
        estado=turno.estado.value,
        canal_reserva=turno.canal_reserva,
        ya_transcurrio=turno.ya_transcurrio(ahora),
        habilita_facturacion=turno.habilita_facturacion,
    )


def patrones(entradas: list[PatronEntrada]) -> tuple[PatronDeDisponibilidad, ...]:
    return tuple(
        PatronDeDisponibilidad(
            dia_semana=uno.dia_semana,
            hora_inicio=uno.hora_inicio,
            hora_fin=uno.hora_fin,
            duracion_slot_min=uno.duracion_slot_min,
        )
        for uno in entradas
    )


def tipo_de_recurso(texto: str) -> TipoRecurso:
    if texto not in TipoRecurso.__members__:
        raise EntradaInvalida(f"«{texto}» no es un tipo de recurso valido")
    return TipoRecurso[texto]


def excepcion(entrada: ExcepcionEntrada) -> ExcepcionDeDisponibilidad:
    if entrada.tipo not in TipoExcepcion.__members__:
        raise EntradaInvalida(f"«{entrada.tipo}» no es un tipo de excepcion valido")
    return ExcepcionDeDisponibilidad(
        fecha=entrada.fecha,
        tipo=TipoExcepcion[entrada.tipo],
        franja_inicio=entrada.franja_inicio,
        franja_duracion_min=entrada.franja_duracion_min,
    )


def actor(request: Request) -> tuple[EmpresaId, UsuarioId, RolUsuario]:
    return (request.state.empresa_id, request.state.usuario_id, RolUsuario(request.state.rol))


def exigir(salida: _T | None) -> _T:
    if salida is None:  # pragma: no cover - la unidad de trabajo siempre entrega una vuelta
        raise RuntimeError("La unidad de trabajo no produjo una respuesta")
    return salida
