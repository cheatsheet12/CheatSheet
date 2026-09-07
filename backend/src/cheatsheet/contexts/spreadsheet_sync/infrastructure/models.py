"""Persistence model for spreadsheet links.

The DER's `vinculo_de_planilla` (BC5), plus three columns it does not have and each of
which a rule demands:

- **`pausado` / `motivo_de_pausa`** — HU-E2-04 RN-04 and HU-E3-04 RN-03 both say the sync
  *pauses* on a structural change. A pause that is not stored is a pause that ends at the
  next worker restart.
- **`archivo_*`** — decision D10's `ARCHIVO` provider. The DER has no column for an
  uploaded file because it has no such provider.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_VINCULO = "vinculo_de_planilla"


class VinculoDePlanillaORM(Base):
    __tablename__ = TABLA_VINCULO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    configuracion_integracion_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    mapeo_vigente_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    proveedor: Mapped[str] = mapped_column(String(20), nullable=False)
    direccion: Mapped[str] = mapped_column(String(20), nullable=False)
    identificador_externo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    hoja_empresa: Mapped[str] = mapped_column(String(200), nullable=False)
    hoja_cheatsheet: Mapped[str | None] = mapped_column(String(200), nullable=True)

    archivo_clave: Mapped[str | None] = mapped_column(String(400), nullable=True)
    archivo_nombre: Mapped[str | None] = mapped_column(String(300), nullable=True)
    archivo_tamano: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ultima_lectura: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultima_escritura: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pausado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    motivo_de_pausa: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # PAN-ING-01 lists this company's links, newest first.
        Index("ix_vinculo_empresa_created", "empresa_id", "created_at"),
        # The incremental sweep of HU-E3-04 asks for live, unpaused links only. Partial,
        # because an uploaded file is never a candidate and there will be many of those.
        Index(
            "ix_vinculo_sincronizables",
            "empresa_id",
            postgresql_where=text("pausado = false AND proveedor <> 'ARCHIVO'"),
        ),
    )
