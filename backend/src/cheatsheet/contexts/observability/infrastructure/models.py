"""Persistence model for the audit log.

The value objects are flattened into columns rather than stored as one JSON blob.
The audit panel of epic 10 (HU-E12-01) filters by module, by result and by initiator,
and a filter over a JSON field is a sequential scan with extra steps.

`detalle` stays `JSONB` because it is the one part nobody queries by shape — it is
read by a human looking at one operation (HU-E12-02).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_AUDITORIA = "registro_de_auditoria"


class RegistroDeAuditoriaORM(Base):
    __tablename__ = TABLA_AUDITORIA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    evento_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, unique=True)
    tenant_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    modulo: Mapped[str] = mapped_column(String(40), nullable=False)
    operacion: Mapped[str] = mapped_column(String(120), nullable=False)
    entidad_tipo: Mapped[str] = mapped_column(String(80), nullable=False)
    entidad_identificador: Mapped[str] = mapped_column(String(120), nullable=False)

    iniciador_tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    iniciador_user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    iniciador_referencia: Mapped[str | None] = mapped_column(String(120), nullable=True)

    resultado: Mapped[str] = mapped_column(String(20), nullable=False)
    # `timezone=True` is not optional here. Without it SQLAlchemy maps to TIMESTAMP
    # WITHOUT TIME ZONE, the driver refuses the aware datetime the domain produces, and
    # any value that did get through would have silently lost its offset — which on a
    # tax document is the difference between one fiscal period and the next.
    ocurrido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detalle: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        # The panel always reads one company's log, newest first. Without this index
        # that is a scan over every company's history.
        Index("ix_auditoria_tenant_ocurrido", "tenant_id", "ocurrido_en"),
        Index("ix_auditoria_tenant_modulo", "tenant_id", "modulo"),
    )
