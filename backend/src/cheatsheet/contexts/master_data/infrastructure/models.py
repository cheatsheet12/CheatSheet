"""Persistence models of the master data context (DER, BC2).

Two tables. `categoria_empresa` arrives with the unit that owns it, and the
`categoria_id` the DER puts on both of these never does: decision D8 of the epic 3 map
replaces that column with link tables, because HU-E4-04 RN-02 lets one element carry
several categories and a single foreign key cannot.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_CLIENTE = "cliente"

#: RN-03, enforced by the database. **Partial**, because the CUIT is optional: several
#: clients without one are not duplicates of each other. Declared here as well as in the
#: migration so the schema the test fixtures build matches the one the database has.
INDICE_CUIT_UNICO = "uq_cliente_empresa_cuit"


class ClienteORM(Base):
    __tablename__ = TABLA_CLIENTE

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("empresa.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    # Nullable, as the DER declares it. HU-E8-01 registers clients from WhatsApp with
    # nothing but a phone number, and a mandatory CUIT would make the agent invent one.
    cuit: Mapped[str | None] = mapped_column(String(11), nullable=True)
    condicion_iva: Mapped[str | None] = mapped_column(String(30), nullable=True)
    contacto_whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contacto_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # ADR-006 and ADR-007 made columns. The panel always writes PANEL / False / NULL;
    # epic 4 is what fills the other combinations.
    origen: Mapped[str] = mapped_column(String(20), nullable=False)
    presente_en_planilla: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    referencia_fila_planilla: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_cliente_empresa", "empresa_id"),
        Index(
            INDICE_CUIT_UNICO,
            "empresa_id",
            "cuit",
            unique=True,
            postgresql_where=text("cuit IS NOT NULL"),
        ),
    )


TABLA_SERVICIO = "servicio"


class ServicioORM(Base):
    __tablename__ = TABLA_SERVICIO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("empresa.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    # `NUMERIC`, never `FLOAT` (code-standards §2.5). Twelve integer digits is a
    # thousand million pesos, which is headroom worth having with inflation.
    precio: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Scale 4 so `0.105` fits exactly. With scale 2 it would be stored as `0.11` and the
    # VAT of epic 5 would come out wrong on every reduced-rate line.
    alicuota_iva: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    agendable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duracion_estandar_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    origen: Mapped[str] = mapped_column(String(20), nullable=False)
    presente_en_planilla: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # No unique index: services have no uniqueness rule. Two branches may both sell a
    # "Corte", and no story says otherwise.
    __table_args__ = (Index("ix_servicio_empresa", "empresa_id"),)
