"""Modelos de persistencia de `scheduling`.

Las cuatro tablas del DER sin cambios de forma. Dos cosas valen leerse dos veces:

- **La franja es inicio más duración, no un rango.** Es lo que el DER dice y lo que se guarda.
  El rango que la restricción de exclusión compara se **calcula** en la restricción misma
  (migración 0020), y por eso no hay una columna `tstzrange`: guardar el rango además sería
  guardar el mismo hecho dos veces, con la posibilidad de que discrepen.

- **`turno` no tiene FK a `cobro` en este modelo**, aunque el DER la declare. `cobro` vive en
  otro bounded context y la migración es la que decide si la restricción existe; el ORM de
  este contexto no la declara para no arrastrar el modelo de `payments` (regla R3).
"""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_RECURSO = "recurso_reservable"
TABLA_PATRON = "patron_de_disponibilidad"
TABLA_EXCEPCION = "excepcion_de_disponibilidad"
TABLA_SERVICIO_DE_RECURSO = "servicio_de_recurso"
TABLA_TURNO = "turno"


class RecursoReservableORM(Base):
    __tablename__ = TABLA_RECURSO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    activo: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_recurso_empresa_activo", "empresa_id", "activo"),)


class PatronDeDisponibilidadORM(Base):
    """El horario semanal. Se reemplaza entero, así que no lleva `updated_at`.

    `dia_semana` es el de Python —lunes 0, domingo 6— y no el de PostgreSQL, que empieza el
    domingo. Elegido el de Python porque es el que el dominio usa, y traducir en el repositorio
    es exactamente el seam donde una traducción a medias corre la agenda un día.
    """

    __tablename__ = TABLA_PATRON

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    recurso_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_RECURSO}.id", ondelete="CASCADE"), nullable=False
    )
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)
    duracion_slot_min: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (Index("ix_patron_recurso", "recurso_id", "dia_semana"),)


class ExcepcionDeDisponibilidadORM(Base):
    """Un día que no se comporta como los demás.

    **`uq_excepcion_recurso_fecha` es HU-E7-05 RN-02.** «No permite configurar una excepción
    que contradiga otra existente para el mismo recurso y fecha» se cumple garantizando que
    haya a lo sumo una — y eso lo garantiza el índice, no el `if` del agregado, que pierde
    contra dos requests concurrentes.
    """

    __tablename__ = TABLA_EXCEPCION

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    recurso_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_RECURSO}.id", ondelete="CASCADE"), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(String(24), nullable=False)
    franja_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    franja_duracion_min: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("recurso_id", "fecha", name="uq_excepcion_recurso_fecha"),)


class ServicioDeRecursoORM(Base):
    """Qué servicios se prestan en qué recurso (HU-E7-04 RN-02).

    Una tabla de unión sin entidad propia: no tiene atributos más allá del par, y el DER la
    implica al decir que un recurso «puede asociarse a uno o más servicios». Sin FK a
    `servicio` **desde el ORM de este contexto** por lo mismo que `turno.cobro_id` — la
    migración decide; el modelo no arrastra `master_data`.
    """

    __tablename__ = TABLA_SERVICIO_DE_RECURSO

    recurso_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(f"{TABLA_RECURSO}.id", ondelete="CASCADE"),
        primary_key=True,
    )
    servicio_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)


class TurnoORM(Base):
    __tablename__ = TABLA_TURNO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    servicio_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    recurso_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_RECURSO}.id"), nullable=False
    )
    #: La seña de HU-E6-07. Sin FK acá: `cobro` es de `payments` (hallazgo H4 del DER).
    cobro_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    franja_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    franja_duracion_min: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    canal_reserva: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # La consulta de PAN-AGE-01: los turnos de un recurso en un rango.
        Index("ix_turno_empresa_franja", "empresa_id", "franja_inicio"),
        Index("ix_turno_recurso_franja", "recurso_id", "franja_inicio"),
        Index("ix_turno_cliente", "cliente_id"),
    )


__all__ = [
    "ExcepcionDeDisponibilidadORM",
    "PatronDeDisponibilidadORM",
    "RecursoReservableORM",
    "ServicioDeRecursoORM",
    "TurnoORM",
]
