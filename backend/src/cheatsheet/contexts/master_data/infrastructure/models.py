"""Persistence models of the master data context (DER, BC2).

Five tables: the three of the DER — `cliente`, `servicio`, `categoria_empresa` — plus the
two link tables that decision D8 of the epic 3 map put in place of the `categoria_id` the
DER draws on the first two. HU-E4-04 RN-02 lets one element carry several categories, and
a single foreign key cannot; the column was never created, so nothing had to be migrated.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
    #
    # The duration rule (HU-E4-02: 5 to 480 minutes for a bookable service, none otherwise)
    # is the same text as migration 0025, which adds it `NOT VALID` so rows written before
    # it are reported instead of blocking the upgrade. Declared here so the metadata and
    # Alembic agree. `IS NOT NULL` in the first branch is deliberate: a CHECK passes on
    # `NULL`, and without it a bookable service with no duration would satisfy the rule.
    __table_args__ = (
        Index("ix_servicio_empresa", "empresa_id"),
        CheckConstraint(
            "(agendable AND duracion_estandar_min IS NOT NULL "
            "AND duracion_estandar_min BETWEEN 5 AND 480) "
            "OR (NOT agendable AND duracion_estandar_min IS NULL)",
            name="ck_servicio_duracion_en_rango",
        ),
    )


TABLA_CATEGORIA = "categoria_empresa"
TABLA_CLIENTE_CATEGORIA = "cliente_categoria"
TABLA_SERVICIO_CATEGORIA = "servicio_categoria"

#: RN-02, enforced by the database. **Functional**, over `lower(nombre)`: «VIP» and «vip»
#: are the same name to anybody reading the list.
INDICE_CATEGORIA_UNICA = "uq_categoria_empresa_nombre_ambito"


class CategoriaEmpresaORM(Base):
    __tablename__ = TABLA_CATEGORIA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("empresa.id", ondelete="CASCADE"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(String(60), nullable=False)
    aplica_a: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_categoria_empresa", "empresa_id"),
        Index(
            INDICE_CATEGORIA_UNICA,
            "empresa_id",
            text("lower(nombre)"),
            "aplica_a",
            unique=True,
        ),
    )


class ClienteCategoriaORM(Base):
    """The N-to-N of decision D8, on the client side.

    **Carries its own `empresa_id`**, and that is a decision rather than denormalisation
    by accident: the alternative was an RLS policy with an `EXISTS` against the parent
    table, which would be the only policy with a subquery in the whole system. A barrier
    that reads the same everywhere is a barrier that gets reviewed properly.
    """

    __tablename__ = TABLA_CLIENTE_CATEGORIA

    cliente_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("cliente.id", ondelete="CASCADE"), primary_key=True
    )
    categoria_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("categoria_empresa.id", ondelete="CASCADE"),
        primary_key=True,
    )
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    __table_args__ = (Index("ix_cliente_categoria_categoria", "categoria_id"),)


class ServicioCategoriaORM(Base):
    """The same, on the service side. See `ClienteCategoriaORM` for the `empresa_id`."""

    __tablename__ = TABLA_SERVICIO_CATEGORIA

    servicio_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("servicio.id", ondelete="CASCADE"), primary_key=True
    )
    categoria_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("categoria_empresa.id", ondelete="CASCADE"),
        primary_key=True,
    )
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    __table_args__ = (Index("ix_servicio_categoria_categoria", "categoria_id"),)
