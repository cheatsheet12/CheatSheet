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
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_CONVERSACION = "conversacion"
TABLA_MENSAJE = "mensaje"
TABLA_ESCALAMIENTO = "escalamiento"
TABLA_FAQ = "faq"


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
    #: HU-E9-04 RN-02. Un entero y no una tabla de eventos: la regla pide un número.
    usos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_faq_empresa_obsoleto", "empresa_id", "embedding_obsoleto"),)


__all__ = ["FAQORM", "ConversacionORM", "EscalamientoORM", "MensajeORM"]
