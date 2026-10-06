"""Modelo de persistencia de `regla_de_negocio`.

La tabla del DER sin cambios. `configuracion` es un JSONB y lo que lo mantiene honesto vive
en el dominio (decisión D24): las clases de configuración validan al construirse, y leer una
fila mal formada **falla al leer** en vez de propagar un `KeyError` a la mitad de un barrido.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.contexts.business_config.domain.plantilla import (
    LARGO_MAXIMO_DETALLE,
    LARGO_MAXIMO_ID_EN_META,
    LARGO_MAXIMO_MOTIVO,
)
from cheatsheet.platform.database import Base

TABLA_REGLA = "regla_de_negocio"
TABLA_PLANTILLA = "plantilla_de_notificacion"


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


class PlantillaDeNotificacionORM(Base):
    """La tabla `plantilla_de_notificacion` del DER (HU-E11-02).

    `estado_aprobacion_meta` es `varchar` en el DER y acá tambien: lo que gobierna la decision
    es el enum del dominio, y guardar su `.value` deja la fila legible sin un tipo de
    PostgreSQL que haya que migrar cada vez que Meta agregue un estado.
    """

    __tablename__ = TABLA_PLANTILLA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    codigo: Mapped[str] = mapped_column(String(60), nullable=False)
    idioma: Mapped[str] = mapped_column(String(10), nullable=False)
    canal: Mapped[str] = mapped_column(String(20), nullable=False)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    estado_aprobacion_meta: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Lo que se sabe de la plantilla del otro lado (U6, migración 0035).
    nombre_en_meta: Mapped[str | None] = mapped_column(String(512), nullable=True)
    meta_plantilla_id: Mapped[str | None] = mapped_column(
        String(LARGO_MAXIMO_ID_EN_META), nullable=True
    )
    motivo_meta: Mapped[str | None] = mapped_column(String(LARGO_MAXIMO_MOTIVO), nullable=True)
    detalle_meta: Mapped[str | None] = mapped_column(String(LARGO_MAXIMO_DETALLE), nullable=True)
    categoria_en_meta: Mapped[str | None] = mapped_column(String(20), nullable=True)
    enviada_a_meta_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estado_meta_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # `ResolverPlantilla` busca por codigo dentro de la empresa, que es la consulta del
        # camino caliente: cada mensaje saliente pasa por ella.
        Index("ix_plantilla_empresa_codigo", "empresa_id", "codigo"),
        # Una plantilla de Meta es de una sola fila nuestra (el webhook la busca por este id).
        Index(
            "uq_plantilla_meta_id",
            "empresa_id",
            "meta_plantilla_id",
            unique=True,
            postgresql_where=text("meta_plantilla_id IS NOT NULL"),
        ),
    )
