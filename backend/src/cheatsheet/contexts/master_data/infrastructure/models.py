"""Persistence models of the master data context (DER, BC2).

One table for now. `servicio` and `categoria_empresa` arrive with the units that own
them, and `cliente.categoria_id` never does: decision D8 of the epic 3 map replaces that
column with a link table, because HU-E4-04 RN-02 lets one client carry several
categories and a single foreign key cannot.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
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
