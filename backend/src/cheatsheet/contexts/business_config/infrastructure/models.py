"""Modelo de persistencia de `regla_de_negocio`.

La tabla del DER sin cambios. `configuracion` es un JSONB y lo que lo mantiene honesto vive
en el dominio (decisión D24): las clases de configuración validan al construirse, y leer una
fila mal formada **falla al leer** en vez de propagar un `KeyError` a la mitad de un barrido.
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

TABLA_REGLA = "regla_de_negocio"


class ReglaDeNegocioORM(Base):
    __tablename__ = TABLA_REGLA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    configuracion: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prioridad: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # La resolucion de RN-05 pide las de un tipo, ordenadas por prioridad.
        Index("ix_regla_empresa_tipo", "empresa_id", "tipo", "prioridad"),
    )
