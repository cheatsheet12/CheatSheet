"""Persistence models of the identity context (DER, BC1, plus gaps H1, H3 and H7)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from cheatsheet.platform.database import Base

TABLA_EMPRESA = "empresa"
TABLA_USUARIO = "usuario"
TABLA_REFRESH = "refresh_token"
TABLA_INVITACION = "invitacion"
TABLA_ACEPTACION_LEGAL = "aceptacion_legal"


class EmpresaORM(Base):
    __tablename__ = TABLA_EMPRESA

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    # Nullable until the onboarding completes (decision A of this unit). The DER marks
    # the three NOT NULL, which leaves no room for the state HU-E1-01 creates at step 1.
    razon_social: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cuit: Mapped[str | None] = mapped_column(String(11), nullable=True, unique=True)
    condicion_iva: Mapped[str | None] = mapped_column(String(30), nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Gap H7: HU-E1-02 RN-03 requires both and the DER has neither.
    nombre_responsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email_contacto: Mapped[str | None] = mapped_column(String(320), nullable=True)
    terminos_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    terminos_fecha_aceptacion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UsuarioORM(Base):
    __tablename__ = TABLA_USUARIO

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Unique across the platform, not per company: sign-in is by email alone, so two
    # users sharing one would make authentication ambiguous.
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    # Gap H1 — the DER has neither.
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    hash_de_contrasena: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)
    # Three states where the DER has `activo boolean` — extension of gap H1, see
    # `EstadoUsuario`. PAN-USR-01 shows three, and the last-Administrator invariant must
    # not count somebody who was invited and never accepted.
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    pref_idioma: Mapped[str] = mapped_column(String(10), nullable=False)
    pref_zona_horaria: Mapped[str] = mapped_column(String(60), nullable=False)
    # The DER declares this column and no schema; `PreferenciasDeNotificacion` is the
    # schema, and it is validated on the way back in.
    pref_suscripciones: Mapped[dict[str, list[str]]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (Index("ix_usuario_empresa", "empresa_id"),)


class RefreshTokenORM(Base):
    """Gap H3: the DER has no table, and ADR-011 requires rotation with reuse detection."""

    __tablename__ = TABLA_REFRESH

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    familia_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # The token itself is never stored, so a database dump is not a set of live sessions.
    hash_del_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_refresh_familia", "familia_id"),)


class InvitacionORM(Base):
    """Gap H1: the DER models no pending-invitation state, and HU-E1-04 RN-02 needs one."""

    __tablename__ = TABLA_INVITACION

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Same treatment as the refresh token: whoever holds this string can set a password
    # inside somebody's company, so only its digest is stored.
    hash_del_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invitado_por: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    aceptada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (Index("ix_invitacion_empresa", "empresa_id"),)


class AceptacionLegalORM(Base):
    """One acceptance of one version of one legal document (HU-E1-08 RN-02).

    Insert-only for the application role (migration 0041): evidence is never edited. The
    foreign keys are declared in the migration, as for the rest of this context.
    """

    __tablename__ = TABLA_ACEPTACION_LEGAL

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    # Empty only for the terms of a company registered before this table existed and whose
    # registration event could not be found (migration 0041).
    usuario_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    documento: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_aceptacion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "documento IN ('TERMINOS', 'PRIVACIDAD')", name="ck_aceptacion_legal_documento"
        ),
        CheckConstraint(
            "usuario_id IS NOT NULL OR documento = 'TERMINOS'", name="ck_aceptacion_legal_usuario"
        ),
        Index("ix_aceptacion_legal_empresa", "empresa_id"),
        Index(
            "uq_aceptacion_legal_privacidad",
            "usuario_id",
            "version",
            unique=True,
            postgresql_where=text("documento = 'PRIVACIDAD'"),
        ),
        Index(
            "uq_aceptacion_legal_terminos",
            "empresa_id",
            "version",
            unique=True,
            postgresql_where=text("documento = 'TERMINOS'"),
        ),
    )
