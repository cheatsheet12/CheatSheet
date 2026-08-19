"""Persistence model of the integrations context (DER BC4, plus gaps H9, H10 and H11)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Index, LargeBinary, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_CONFIGURACION = "configuracion_de_integracion"
TABLA_TICKET = "ticket_de_acceso"


class ConfiguracionDeIntegracionORM(Base):
    """One row per `(empresa_id, sistema)`, created only when something connects.

    **Gap H9.** The DER models the status as `activa boolean NOT NULL`. HU-E2-05 RN-02
    asks for three states, RN-03 for the timestamp of the last check, and the criterion
    "una integración está degradada → la muestro en Atención con el detalle disponible"
    for a reason string. A boolean cannot tell *degraded* from *down*, which is precisely
    the distinction the story exists to display.

    `activa` is **replaced** by `estado` rather than kept alongside it: it is derivable
    (`estado == CONECTADO`), and keeping both guarantees that one day they disagree.
    """

    __tablename__ = TABLA_CONFIGURACION
    __table_args__ = (
        # The identity of the aggregate, and what makes ConectarIntegracion idempotent:
        # reconnecting replaces the credential instead of accumulating rows.
        UniqueConstraint("empresa_id", "sistema", name="uq_integracion_empresa_sistema"),
        Index("ix_integracion_empresa", "empresa_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    sistema: Mapped[str] = mapped_column(String(30), nullable=False)
    # NOT NULL as the DER declares it. A company with nothing connected has no row here;
    # the four cards of PAN-CFG-INT come from the enum, not from this table.
    credencial_contenido_cifrado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    credencial_algoritmo: Mapped[str] = mapped_column(String(40), nullable=False)
    parametros: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ambiente: Mapped[str] = mapped_column(String(20), nullable=False)
    # Gap H9 — the three columns the DER does not have.
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    detalle_estado: Mapped[str | None] = mapped_column(String(300), nullable=True)
    verificado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Gap H10 — when the wait for an asynchronous provider started. `verificado_en` cannot
    # serve: every poll re-stamps it, so it measures the last question and not the wait.
    pendiente_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketDeAccesoORM(Base):
    """One live ARCA session per `(empresa_id, servicio)` — **gap H11**, ADR-0004.

    The DER models the credential and not the session derived from it, and the two cannot
    share a row: a ticket lasts twelve hours against a certificate's two years, and one
    company holds several at once because a ticket authenticates one ARCA service.

    Storing it at all is a correctness requirement rather than a cache: WSAA refuses to
    issue a second ticket while the first is alive, so a system that discards the one it
    was given cannot authenticate again until that one expires.

    `contenido_cifrado` holds the token and the sign, encrypted with the same AES-256-GCM
    adapter as the credentials. They are secrets in their own right — whoever holds them
    speaks to ARCA as the company for the rest of the twelve hours.
    """

    __tablename__ = TABLA_TICKET
    __table_args__ = (
        UniqueConstraint("empresa_id", "servicio", name="uq_ticket_empresa_servicio"),
        Index("ix_ticket_empresa", "empresa_id"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    servicio: Mapped[str] = mapped_column(String(30), nullable=False)
    contenido_cifrado: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    algoritmo: Mapped[str] = mapped_column(String(40), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
