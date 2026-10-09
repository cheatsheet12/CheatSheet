"""Modelos de persistencia de `payments`.

Las dos tablas del DER, más `reembolso` (ADR-0010, migración 0027). Tres cosas valen
leerse dos veces:

- **`mp_payment_id` no lo muestra ninguna pantalla y existe igual.** Es la clave de
  idempotencia del webhook (decisión D20), y el índice único parcial de la migración 0019 es
  lo que la convierte en una garantía en vez de una intención.
- **Los montos son `NUMERIC(14, 2)`.** Ni `FLOAT`, que `CLAUDE.md` §3.5 prohíbe de plano, ni
  `NUMERIC` sin escala: una columna sin escala guardaría el tercer decimal que el agregado
  redondea, y la fila terminaría diciendo algo distinto de lo que MercadoPago cobró.
- **`reembolso` es solo-inserción** (`SELECT` e `INSERT` para la aplicación). Un error se
  corrige con una fila negativa que apunta a la anulada, nunca editando.
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
from cheatsheet.shared.externo_id import LARGO_MAXIMO_EXTERNO_ID

TABLA_COBRO = "cobro"
TABLA_RECORDATORIO = "recordatorio"
TABLA_REEMBOLSO = "reembolso"

MONTO = Numeric(14, 2)

#: Las mismas expresiones que la migración 0027: si divergen, Alembic y el metadata también.
REGLA_DE_FECHA = (
    "estado NOT IN ('APROBADO', 'REEMBOLSADO_PARCIAL', 'REEMBOLSADO') OR fecha_pago IS NOT NULL"
)
REGLA_DE_ACUMULADO = "0 <= monto_reembolsado AND monto_reembolsado <= monto"
#: Las tres columnas de la solicitud en vuelo, todas o ninguna; el id de MercadoPago puede faltar
#: pero no existir sin solicitud.
REGLA_DE_REEMBOLSO_EN_VUELO = (
    "(reembolso_solicitado_en IS NULL) = (reembolso_solicitado_monto IS NULL) "
    "AND (reembolso_solicitado_en IS NULL) = (reembolso_clave_idempotencia IS NULL) "
    "AND (reembolso_mp_refund_id IS NULL OR reembolso_solicitado_en IS NOT NULL)"
)
#: El estado sale del acumulado: parcial si `0 < acumulado < monto`, total si `acumulado = monto`.
REGLA_DE_ESTADO_DE_REEMBOLSO = (
    "((estado = 'REEMBOLSADO_PARCIAL') = (monto_reembolsado > 0 AND monto_reembolsado < monto)) "
    "AND ((estado = 'REEMBOLSADO') = (monto_reembolsado = monto))"
)


class CobroORM(Base):
    __tablename__ = TABLA_COBRO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    comprobante_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    #: Sin FK (hallazgo H4 del DER): `turno` es de otro bounded context.
    turno_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    monto: Mapped[Decimal] = mapped_column(MONTO, nullable=False)
    #: El acumulado de `reembolso`: se escribe **junto con** cada fila (ADR-0010, punto 4).
    monto_reembolsado: Mapped[Decimal] = mapped_column(MONTO, nullable=False, server_default="0")
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
    #: El reembolso en vuelo (D27: no es un estado). Las cuatro columnas viven solo mientras dura;
    #: el id de MercadoPago es la única que puede faltar.
    reembolso_solicitado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reembolso_solicitado_monto: Mapped[Decimal | None] = mapped_column(MONTO, nullable=True)
    reembolso_clave_idempotencia: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    reembolso_mp_refund_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    motivo_de_cancelacion: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: La clave del pedido que el cliente mandó al generar el cobro (ADR-0013, migración 0034).
    #: `NULL` en los cobros anteriores: no se les inventó una.
    clave_idempotencia: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

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
        # La misma expresión que la migración 0034. La clave es única por empresa: la misma clave
        # en dos empresas son dos pedidos independientes.
        Index(
            "uq_cobro_clave_idempotencia",
            "empresa_id",
            "clave_idempotencia",
            unique=True,
            postgresql_where=text("clave_idempotencia IS NOT NULL"),
        ),
        CheckConstraint(
            "medio_de_pago IN ('LINK_MERCADOPAGO', 'TRANSFERENCIA')",
            name="ck_cobro_medio_de_pago",
        ),
        CheckConstraint(REGLA_DE_FECHA, name="ck_cobro_fecha_de_pago"),
        CheckConstraint(REGLA_DE_ACUMULADO, name="ck_cobro_reembolso"),
        CheckConstraint(REGLA_DE_REEMBOLSO_EN_VUELO, name="ck_cobro_reembolso_en_vuelo"),
        CheckConstraint(REGLA_DE_ESTADO_DE_REEMBOLSO, name="ck_cobro_estado_de_reembolso"),
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
    #: El `wamid` con el que Meta aceptó el mensaje: así un callback `statuses[]` encuentra su
    #: recordatorio (U7, migración 0038). Único en todo el sistema, no solo por empresa.
    externo_id: Mapped[str | None] = mapped_column(String(LARGO_MAXIMO_EXTERNO_ID), nullable=True)
    #: Por qué falló el envío: un código de Meta o una clase corta (`INCIERTO`, `SIN_CANAL`...).
    ultimo_error: Mapped[str | None] = mapped_column(String(60), nullable=True)


class ReembolsoORM(Base):
    """Una fila por reembolso o corrección. **Solo `SELECT` e `INSERT`** (ADR-0010, punto 4)."""

    __tablename__ = TABLA_REEMBOLSO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: Sin `ON DELETE CASCADE`: un cobro con reembolsos no se borra.
    cobro_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_COBRO}.id"), nullable=False
    )
    #: Distinto de cero; negativo si y solo si es una corrección.
    monto: Mapped[Decimal] = mapped_column(MONTO, nullable=False)
    fecha_devolucion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origen: Mapped[str] = mapped_column(String(20), nullable=False)
    #: La del administrador (número de operación o comprobante bancario). Texto libre: no único.
    referencia: Mapped[str | None] = mapped_column(String(120), nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: La fila que esta anula. El índice único parcial hace que una fila se corrija una sola vez.
    corrige_a: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey(f"{TABLA_REEMBOLSO}.id"), nullable=True
    )
    #: La clave de idempotencia de la confirmación: una misma respuesta de MercadoPago, una fila.
    mp_refund_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: `NULL` cuando confirma el sistema. Sin FK: `usuario` es de otro contexto.
    registrado_por: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # La métrica de «cobrado» resta por fecha de devolución, acotada a la empresa.
        Index("ix_reembolso_empresa_fecha", "empresa_id", "fecha_devolucion"),
        Index("ix_reembolso_cobro", "cobro_id"),
        Index(
            "uq_reembolso_corrige_a",
            "corrige_a",
            unique=True,
            postgresql_where=text("corrige_a IS NOT NULL"),
        ),
        Index(
            "uq_reembolso_mp_refund_id",
            "empresa_id",
            "mp_refund_id",
            unique=True,
            postgresql_where=text("mp_refund_id IS NOT NULL"),
        ),
        CheckConstraint("monto <> 0", name="ck_reembolso_monto"),
        CheckConstraint("(monto < 0) = (corrige_a IS NOT NULL)", name="ck_reembolso_correccion"),
        CheckConstraint("origen IN ('API_MERCADOPAGO', 'MANUAL')", name="ck_reembolso_origen"),
        CheckConstraint(
            "origen <> 'MANUAL' OR (motivo IS NOT NULL AND length(btrim(motivo)) > 0)",
            name="ck_reembolso_motivo_manual",
        ),
    )
