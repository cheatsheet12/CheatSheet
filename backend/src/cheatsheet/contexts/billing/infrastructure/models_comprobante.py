"""Persistence models for `comprobante` and `item_de_comprobante`.

Single Table Inheritance (ADR-010): one table, a `tipo` discriminator, and the columns that
only some types use left nullable. `comprobante_origen_id` is the clearest case — only a
credit note has one — and what enforces it is the aggregate plus a conditional `CHECK`, not
a second table.

**The four amounts are `NUMERIC(14, 2)`.** Not `FLOAT`, which `CLAUDE.md` §3.5 forbids
outright, and not `NUMERIC` without a scale: an unscaled column would happily store the
third decimal that decision D15 rounds away, and the row would then disagree with the
document ARCA authorised.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_COMPROBANTE = "comprobante"
TABLA_ITEM = "item_de_comprobante"

#: 14 digits, 2 decimals. Room for a document of twelve figures, which is more than the
#: businesses this system serves will issue and cheap to allow.
MONTO = Numeric(14, 2)
#: The rate itself, four decimals: `0.1050` has to survive the round trip.
TASA = Numeric(5, 4)


class ComprobanteORM(Base):
    __tablename__ = TABLA_COMPROBANTE

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    punto_de_venta_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Absent while the document is a draft: a number reserved for something never sent is
    #: a hole in the numbering.
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True)

    receptor_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    receptor_cuit: Mapped[str] = mapped_column(String(11), nullable=False)
    receptor_condicion_iva: Mapped[str] = mapped_column(String(30), nullable=False)
    receptor_domicilio: Mapped[str | None] = mapped_column(String(300), nullable=True)
    #: Copied like the receptor's, and for the same reason: it is what made this type legal.
    emisor_condicion_iva: Mapped[str] = mapped_column(String(30), nullable=False)

    cae_codigo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cae_fecha_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    motivo_de_rechazo: Mapped[str | None] = mapped_column(String(500), nullable=True)

    subtotal: Mapped[Decimal] = mapped_column(MONTO, nullable=False)
    total_iva: Mapped[Decimal] = mapped_column(MONTO, nullable=False)
    total: Mapped[Decimal] = mapped_column(MONTO, nullable=False)
    saldo_pendiente: Mapped[Decimal] = mapped_column(MONTO, nullable=False)

    comprobante_origen_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_COMPROBANTE}.id"), nullable=True
    )
    #: Referenced by id and **without** a foreign key (DER hallazgo H4): `turno` belongs to
    #: another bounded context, and a join across that boundary is what R3 forbids.
    turno_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    fecha_emision: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # PAN-FAC-01 lists by issue date descending (RN-03), scoped to the company.
        Index("ix_comprobante_empresa_fecha", "empresa_id", "fecha_emision"),
        # The reconciliation sweep of D17 asks for exactly this: what is still in flight.
        Index("ix_comprobante_estado_fecha", "estado", "fecha_emision"),
    )


class ItemDeComprobanteORM(Base):
    __tablename__ = TABLA_ITEM

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    comprobante_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(f"{TABLA_COMPROBANTE}.id", ondelete="CASCADE"),
        nullable=False,
    )
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    cantidad: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(MONTO, nullable=False)
    alicuota_iva: Mapped[Decimal] = mapped_column(TASA, nullable=False)
    #: Stored as well as derivable. The aggregate computes it, and this column is what a
    #: report reads without rebuilding six hundred aggregates -- and what proves, years
    #: later, what the arithmetic was the day it was issued.
    subtotal: Mapped[Decimal] = mapped_column(MONTO, nullable=False)

    __table_args__ = (Index("ix_item_comprobante", "comprobante_id"),)
