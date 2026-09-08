"""Persistence model for the audit log.

One column per field of the DER (`docs/aidlc/inputs/der.md`, BC10), plus `modulo` and
`evento_id`. Nothing is stored as a JSON blob: the audit panel of epic 10 (HU-E12-01)
filters by module, by result and by initiator, and a filter over a JSON field is a
sequential scan with extra steps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_AUDITORIA = "registro_de_auditoria"


class RegistroDeAuditoriaORM(Base):
    __tablename__ = TABLA_AUDITORIA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    evento_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, unique=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: Nullable by design: a null initiator is the statement that the system acted.
    usuario_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    modulo: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Quien lo puso en marcha (HS-T5 RN-02). Con `server_default` porque la columna llega en
    #: la migracion 0021 sobre una tabla que ya tiene filas: sin el default, el `ALTER` sobre
    #: una bitacora de produccion fallaria, y esa tabla es justamente la que no se puede
    #: reescribir (HS-T5 RN-03 le niega el UPDATE al rol de la aplicacion).
    iniciador: Mapped[str] = mapped_column(String(20), nullable=False, server_default="sistema")
    accion: Mapped[str] = mapped_column(String(120), nullable=False)
    entidad_afectada: Mapped[str] = mapped_column(String(200), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    direccion_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    #: Lo que la operación registró de sí misma (HU-E12-02 RN-01). Nulo en casi todas las
    #: filas, y la pantalla lo dice en vez de reconstruir algo que nadie escribió. Llega en la
    #: migración 0023, sin `server_default`: una columna nullable se agrega sin reescribir la
    #: tabla, que es lo que esta tabla no admite.
    detalle: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # `timezone=True` is not optional here. Without it SQLAlchemy maps to TIMESTAMP
    # WITHOUT TIME ZONE, the driver refuses the aware datetime the domain produces, and
    # any value that did get through would have silently lost its offset — which on a
    # tax document is the difference between one fiscal period and the next.
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # The panel always reads one company's log, newest first. Without this index
        # that is a scan over every company's history.
        Index("ix_auditoria_empresa_timestamp", "empresa_id", "timestamp"),
        Index("ix_auditoria_empresa_modulo", "empresa_id", "modulo"),
    )


TABLA_TAREA = "tarea_asincrona"


class TareaAsincronaORM(Base):
    """Execution state of one deferred unit of work (HS-T6).

    Unlike the audit row above, this one is updated in place: a task changes state on
    every attempt. It lives in the same context and the same migration chain, and shares
    nothing else with it.
    """

    __tablename__ = TABLA_TAREA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    tipo: Mapped[str] = mapped_column(String(120), nullable=False)
    #: JSONB rather than JSON so the column can be indexed if a later epic ever needs to
    #: look inside it. Nothing does today, and nothing should: see the aggregate on why
    #: the payload is not something to go copying around.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clave_idempotencia: Mapped[str] = mapped_column(String(200), nullable=False)
    resultado: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # The key identifies one intended effect within one company (ADR-009). Unique
        # per company and not globally: two companies legitimately run the same work on
        # the same payload, and a global constraint would make the second one a
        # duplicate of the first.
        UniqueConstraint("empresa_id", "clave_idempotencia", name="uq_tarea_empresa_clave"),
        # The sweep's only query: this company's failed tasks, oldest first. Partial, so
        # the index holds the handful of rows that are failing rather than every task
        # the system has ever run.
        Index(
            "ix_tarea_empresa_fallidas",
            "empresa_id",
            "created_at",
            postgresql_where=text("estado = 'FALLIDA'"),
        ),
    )


TABLA_NOTIFICACION = "notificacion"


class NotificacionORM(Base):
    """El centro de notificaciones (HU-E11-03).

    `destinatario_id` es lo que hace que esto sea una bandeja y no un tablón: dos operadores de
    la misma empresa comparten política de RLS y no comparten avisos.
    """

    __tablename__ = TABLA_NOTIFICACION

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    destinatario_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: La plantilla que la generó, si salió de una. Sin FK desde este ORM: la tabla vive en
    #: `conversational` y la migración es la que decide si la restricción existe (regla R3).
    plantilla_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), nullable=False)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    leida: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # La consulta de la pantalla, y la del globito: la bandeja de una persona, lo no leído
        # primero. Sin este índice son dos escaneos por carga del panel.
        Index("ix_notificacion_destinatario", "destinatario_id", "leida", "created_at"),
    )


TABLA_SOLICITUD = "solicitud_de_soporte"


class SolicitudDeSoporteORM(Base):
    __tablename__ = TABLA_SOLICITUD

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    asunto: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_solicitud_empresa_estado", "empresa_id", "estado"),)
