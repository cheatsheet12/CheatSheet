"""Persistence models for billing.

`punto_de_venta` is the DER's, unchanged. The one thing worth reading twice is
`numerador_por_tipo`: it is a JSONB, and a JSONB read and written without a lock is exactly
the race that produces two documents with the same fiscal number. What prevents that is
`tomar_para_emitir` in the repository (decision D14), not anything in this file.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_PUNTO_DE_VENTA = "punto_de_venta"


class PuntoDeVentaORM(Base):
    __tablename__ = TABLA_PUNTO_DE_VENTA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: `{tipo: ultimo_numero}`. See the module docstring on why this needs a row lock.
    numerador_por_tipo: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # PAN-FAC-05 lists this company's points in fiscal order, which is the order they
        # appear on the documents.
        Index("ix_punto_empresa_numero", "empresa_id", "numero"),
    )
