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
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, text
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


TABLA_MAPEO = "mapeo"
TABLA_ENTRADA = "entrada_de_mapeo"


class MapeoORM(Base):
    """The DER's `mapeo` (BC5), unchanged."""

    __tablename__ = TABLA_MAPEO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    huella_encabezado: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # RN-02's reuse lookup, and the only query this table answers. Unique per company:
        # one structure has one current mapping, and two would mean the second is never
        # found. `nueva_version` bumps the version in place rather than inserting a row.
        Index("uq_mapeo_empresa_huella", "empresa_id", "huella_encabezado", unique=True),
    )


class EntradaDeMapeoORM(Base):
    """An internal entity of `Mapeo` (DER BC5), plus two columns the DER lacks.

    `ejemplo` and `corregida_a_mano` are not in the DER because it models the mapping and
    not its review. HU-E3-02 needs both: the sample is one of the four things the review
    screen shows per column, and the flag is what keeps a re-run of the model from undoing
    a correction somebody made on purpose.
    """

    __tablename__ = TABLA_ENTRADA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    mapeo_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: Denormalised from the parent so Row-Level Security can scope this table directly.
    #: The DER protects internal entities through their parent; a policy that had to join
    #: is a policy that is one missing index away from being the slowest thing here.
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    columna_origen: Mapped[str] = mapped_column(String(300), nullable=False)
    atributo_destino: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: `Numeric` and never a float: the score is compared against the RN-03 thresholds for
    #: equality, and 0.75 is not 0.75 in binary floating point.
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    ejemplo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    corregida_a_mano: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_entrada_mapeo", "mapeo_id"),)


TABLA_PROCESAMIENTO = "procesamiento_de_planilla"
TABLA_ERROR = "error_de_fila"


class ProcesamientoDePlanillaORM(Base):
    """The DER's `procesamiento_de_planilla` (BC5), plus `origen_id`.

    `origen_id` is HU-E3-06 RN-03: a reprocessing is «un nuevo procesamiento vinculado al
    original». Without the column the history reads as two unrelated imports, and the
    screen cannot say «reintento de la carga del martes».
    """

    __tablename__ = TABLA_PROCESAMIENTO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    vinculo_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    mapeo_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    origen_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    filas_totales: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duracion_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referencia_archivo: Mapped[str | None] = mapped_column(String(400), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # `Cargas recientes` reads this company's runs newest first, and PAN-ING-03 reads
        # one link's history. Both go through these two.
        Index("ix_procesamiento_empresa_created", "empresa_id", "created_at"),
        Index("ix_procesamiento_vinculo", "vinculo_id"),
    )


class ErrorDeFilaORM(Base):
    """An internal entity of the processing (DER BC5), with `empresa_id` denormalised.

    Same reasoning as `entrada_de_mapeo`: the DER protects internal entities through their
    parent, and a policy that has to join is one missing index away from being the slowest
    thing in the context. A failed import writes thousands of these.
    """

    __tablename__ = TABLA_ERROR

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    procesamiento_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

    numero_fila: Mapped[int] = mapped_column(Integer, nullable=False)
    motivo: Mapped[str] = mapped_column(String(300), nullable=False)

    __table_args__ = (
        # PAN-ING-03 lists a run's failures in the order the spreadsheet has them, which
        # is the order somebody scrolling their own file will look for.
        Index("ix_error_procesamiento_fila", "procesamiento_id", "numero_fila"),
    )
