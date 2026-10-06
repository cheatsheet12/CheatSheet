"""Persistence model for the fiscal catalogue.

The DER's `parametro_fiscal` (BC12), unchanged. **The absence of `empresa_id` is the
design**, not an omission: this is ARCA's catalogue and it is the same for every company.
It makes this the only business table in the system without a Row-Level Security policy, and
migration 0016 explains what protects it instead.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_PARAMETRO = "parametro_fiscal"


class ParametroFiscalORM(Base):
    __tablename__ = TABLA_PARAMETRO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Text, always. The rates are turned into `Decimal` from this string by whoever uses
    #: them, never through a float (`CLAUDE.md` §3.5) -- and the other five catalogues are
    #: labels, for which a numeric column would be a lie.
    valor: Mapped[str] = mapped_column(String(200), nullable=False)

    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    #: NULL means «still in force». The partial unique index of migration 0016 is what
    #: makes it impossible for two rows of the same entry to be NULL at once.
    fecha_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)

    #: Bookkeeping about when we learned this, not about when it applies. The aggregate
    #: does not carry it: `fecha_desde` is what the business reads.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # The query the issuing code runs on every document: this entry, on this date.
        Index("ix_parametro_tipo_codigo_desde", "tipo", "codigo", "fecha_desde"),
    )
