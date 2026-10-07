"""Modelos de persistencia de `conversational`.

Las cuatro tablas del DER. Tres cosas valen leerse dos veces:

- **`faq.embedding_vector` es un `vector(1536)` de `pgvector`**, la extensión que la migración
  0001 instaló para este momento — pero **no está mapeado en este archivo**. Es lo que hace
  posible la búsqueda por significado de HU-E8-03 RN-02 sin traer las FAQ a Python; se escribe
  y se consulta con SQL explícito en `repositories.py`. Ver el comentario en `FAQORM`.

- **`mensaje.contenido` es texto siempre**, también para una nota de voz: lo que se guarda es
  la transcripción. **El audio no se persiste** (HS-T7 RN-03), y por eso no hay una columna
  que lo referencie — no la hay porque no debería poder haberla.

- **`mensaje.externo_id` es la clave de idempotencia del webhook de Meta.** No lo muestra
  ninguna pantalla y existe igual, igual que `mp_payment_id` en el épico 6. El índice único
  parcial de la migración 0021 es lo que lo convierte en una garantía.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_CONVERSACION = "conversacion"
TABLA_MENSAJE = "mensaje"
TABLA_ESCALAMIENTO = "escalamiento"
TABLA_FAQ = "faq"
TABLA_FAQ_USO = "faq_uso"


class ConversacionORM(Base):
    __tablename__ = TABLA_CONVERSACION

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    cliente_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Intentos seguidos sin entender. Ver el docstring de `Conversacion`.
    contador: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ventana_maximo: Mapped[int] = mapped_column(Integer, nullable=False)
    ultimo_mensaje_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Lo que el agente le ofreció al cliente y espera que conteste (T2): un solo diálogo pendiente
    #: por conversación, con su vencimiento adentro. El formato lo define `dialogo_json.py`; el DER
    #: no tiene esta columna y la decisión D99 explica por qué. `none_as_null`: sin diálogo es
    #: `NULL` de SQL y no el JSON `null`, que `IS NULL` no vería.
    #: El constructor de `JSONB` no está tipado en SQLAlchemy: de ahí el `ignore`, acotado a esa llamada.
    dialogo: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),  # type: ignore[no-untyped-call]
        nullable=True,
    )

    __table_args__ = (
        # Cómo un mensaje entrante encuentra su hilo: el activo de ese cliente.
        Index("ix_conversacion_cliente_estado", "cliente_id", "estado"),
        Index("ix_conversacion_empresa_actividad", "empresa_id", "ultimo_mensaje_en"),
    )


class MensajeORM(Base):
    __tablename__ = TABLA_MENSAJE

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    conversacion_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(f"{TABLA_CONVERSACION}.id", ondelete="CASCADE"),
        nullable=False,
    )
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    direccion: Mapped[str] = mapped_column(String(12), nullable=False)
    tipo_contenido: Mapped[str] = mapped_column(String(12), nullable=False)
    contenido: Mapped[str | None] = mapped_column(Text, nullable=True)
    intencion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    estado_entrega: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: Quién escribió un saliente (HU-E9-01 RN-04). Fuera del DER, como `modulo` en la
    #: bitácora: la regla pide distinguirlos y sin la columna no se puede.
    origen: Mapped[str | None] = mapped_column(String(12), nullable=True)
    #: La clave de idempotencia del webhook. Ver el docstring del módulo.
    externo_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: Por qué falló un saliente: el código de Meta o una clase corta (U7, migración 0037).
    motivo_de_falla: Mapped[str | None] = mapped_column(String(60), nullable=True)
    momento: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_mensaje_hilo_momento", "conversacion_id", "momento"),)


class EscalamientoORM(Base):
    __tablename__ = TABLA_ESCALAMIENTO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    conversacion_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(f"{TABLA_CONVERSACION}.id", ondelete="CASCADE"),
        nullable=False,
    )
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    usuario_asignado_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    motivo: Mapped[str] = mapped_column(String(300), nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # La consulta que decide si el agente contesta, y la bandeja del operador.
        Index("ix_escalamiento_hilo_estado", "conversacion_id", "estado"),
        Index("ix_escalamiento_empresa_estado", "empresa_id", "estado"),
    )


class FAQORM(Base):
    __tablename__ = TABLA_FAQ

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    categoria_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    pregunta: Mapped[str] = mapped_column(Text, nullable=False)
    respuesta: Mapped[str] = mapped_column(Text, nullable=False)
    #: **`embedding_vector` no está mapeado acá a propósito.** Es una columna `vector(1536)`
    #: de `pgvector`, y mapearla pediría la dependencia `pgvector` de Python para ahorrar unas
    #: veinte líneas. Se escribe y se busca con SQL explícito y un `::vector` en
    #: `repositories.py`, en un método cada cosa; el resto de la fila sí vive acá.
    #:
    #: La consecuencia práctica: un `SELECT` del ORM sobre esta tabla **no** trae el vector,
    #: que es lo que uno quiere en todos los listados menos en la búsqueda.
    embedding_modelo_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    embedding_obsoleto: Mapped[bool] = mapped_column(nullable=False, default=True)
    #: La línea de base de usos de antes del ADR-0012: congelada, solo la escribe el alta.
    #: Los usos nuevos son filas de `faq_uso`.
    usos_anteriores: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: La última edición del texto (no `updated_at`, que también mueve el barrido).
    editada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seguimiento_desde: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_faq_empresa_obsoleto", "empresa_id", "embedding_obsoleto"),)


class FAQUsoORM(Base):
    """Una respuesta con FAQ que salió (ADR-0012). Solo se inserta: ver la migración 0033."""

    __tablename__ = TABLA_FAQ_USO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    #: `NULL` cuando la FAQ se borró: la fila sigue contando para el total de la empresa.
    faq_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("faq.id", ondelete="SET NULL"), nullable=True
    )
    mensaje_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("mensaje.id"), nullable=False, unique=True
    )
    usado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_faq_uso_empresa_faq_usado", "empresa_id", "faq_id", "usado_en"),
        Index("ix_faq_uso_empresa_usado", "empresa_id", "usado_en"),
    )


__all__ = ["FAQORM", "ConversacionORM", "EscalamientoORM", "FAQUsoORM", "MensajeORM"]
