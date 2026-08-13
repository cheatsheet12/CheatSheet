"""Persistence model for the audit log.

One column per field of the DER (`docs/aidlc/inputs/der.md`, BC10), plus `modulo` and
`evento_id`. Nothing is stored as a JSON blob: the audit panel of epic 10 (HU-E12-01)
filters by module, by result and by initiator, and a filter over a JSON field is a
sequential scan with extra steps.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String
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
    accion: Mapped[str] = mapped_column(String(120), nullable=False)
    entidad_afectada: Mapped[str] = mapped_column(String(200), nullable=False)
    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    direccion_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

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
