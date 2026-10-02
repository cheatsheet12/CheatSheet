"""Modelos de persistencia de `payments`.

Las dos tablas del DER. Dos cosas valen leerse dos veces:

- **`mp_payment_id` no lo muestra ninguna pantalla y existe igual.** Es la clave de
  idempotencia del webhook (decisión D20), y el índice único parcial de la migración 0019 es
  lo que la convierte en una garantía en vez de una intención.
- **Los montos son `NUMERIC(14, 2)`.** Ni `FLOAT`, que `CLAUDE.md` §3.5 prohíbe de plano, ni
  `NUMERIC` sin escala: una columna sin escala guardaría el tercer decimal que el agregado
  redondea, y la fila terminaría diciendo algo distinto de lo que MercadoPago cobró.
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
    false,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_COBRO = "cobro"
TABLA_RECORDATORIO = "recordatorio"

MONTO = Numeric(14, 2)


class CobroORM(Base):
    __tablename__ = TABLA_COBRO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    comprobante_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    #: Sin FK (hallazgo H4 del DER): `turno` es de otro bounded context.
    turno_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    monto: Mapped[Decimal] = mapped_column(MONTO, nullable=False)
    monto_reembolsado: Mapped[Decimal | None] = mapped_column(MONTO, nullable=True)
    descripcion: Mapped[str] = mapped_column(String(300), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)

    mp_preference_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: La clave de idempotencia del webhook. Ver el docstring del modulo.
    mp_payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mp_url_pago: Mapped[str | None] = mapped_column(String(500), nullable=True)

    vence_el: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Cuándo pagó el cliente (D91, ADR-0010). Era `pagado_en` hasta la migración 0026.
    fecha_pago: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fecha_pago_aproximada: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    medio_de_pago: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="LINK_MERCADOPAGO"
    )
    #: Solo lo escribe una transferencia verificada (unidad `cobro-por-transferencia`).
    numero_de_operacion: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reembolso_solicitado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    motivo_de_cancelacion: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_cobro_empresa_estado", "empresa_id", "estado", "vence_el"),
        Index("ix_cobro_estado_vence", "estado", "vence_el"),
        Index("ix_cobro_comprobante", "comprobante_id"),
        # Las mismas expresiones que la migración 0026: si divergen, Alembic y el metadata
        # también. Una operación (link o transferencia) tiene efecto una sola vez por empresa.
        Index(
            "uq_cobro_operacion",
            "empresa_id",
            text("(COALESCE(numero_de_operacion, mp_payment_id))"),
            unique=True,
            postgresql_where=text("COALESCE(numero_de_operacion, mp_payment_id) IS NOT NULL"),
        ),
        CheckConstraint(
            "medio_de_pago IN ('LINK_MERCADOPAGO', 'TRANSFERENCIA')",
            name="ck_cobro_medio_de_pago",
        ),
        CheckConstraint(
            "estado NOT IN ('APROBADO', 'REEMBOLSADO') OR fecha_pago IS NOT NULL",
            name="ck_cobro_fecha_de_pago",
        ),
        CheckConstraint(
            "fecha_pago_aproximada = false OR fecha_pago IS NOT NULL",
            name="ck_cobro_fecha_aproximada",
        ),
    )


class RecordatorioORM(Base):
    __tablename__ = TABLA_RECORDATORIO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    cobro_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_COBRO}.id", ondelete="CASCADE"), nullable=False
    )
    #: Lo que hace verificable la cadena de HS-T3: el recordatorio N sale una sola vez. El
    #: indice unico `(cobro_id, paso)` de la migracion 0019 es lo que lo garantiza (D25).
    paso: Mapped[int] = mapped_column(Integer, nullable=False)
    canal: Mapped[str] = mapped_column(String(20), nullable=False)
    enviado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estado_entrega: Mapped[str | None] = mapped_column(String(20), nullable=True)
