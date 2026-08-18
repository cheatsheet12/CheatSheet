"""Identity: empresa, usuario, refresh_token, and the pre-tenant lookups.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13

Three tables and two functions.

**`empresa` isolates by its own `id`, not by `empresa_id`** — it *is* the tenant. Its
fiscal columns are nullable, against the DER's NOT NULL, because HU-E1-01 creates the
account at step 1 and the CUIT only arrives at step 2 (decision A of the unit plan).

**The two `SECURITY DEFINER` functions exist because sign-up and sign-in happen before
there is a company.** Looking a user up by email is how the system finds out which
company they belong to, and checking whether a CUIT is taken has to see companies the
caller cannot. Both are impossible under RLS, and the alternative — granting the
application `BYPASSRLS` — would switch the barrier off for everything, forever, to solve
two queries.

So instead: two functions, each returning the minimum, each owned by the migration role
and executable by the application. `buscar_usuario_para_login` returns one user by email
and nothing else; `existe_cuit_registrado` returns a boolean and never a row. They are
narrow enough to read in ten seconds and named so they show up in any audit.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# `empresa` compares its own id: it is the tenant, not something that belongs to one.
POLITICA_EMPRESA = """
CREATE POLICY aislamiento_por_empresa ON empresa
    USING (id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_USUARIO = """
CREATE POLICY aislamiento_por_empresa ON usuario
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_REFRESH = """
CREATE POLICY aislamiento_por_empresa ON refresh_token
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

# Returns one user, by email, and only the columns authentication needs. No listing, no
# wildcard, no way to enumerate.
FUNCION_LOGIN = """
CREATE OR REPLACE FUNCTION buscar_usuario_para_login(p_email varchar)
RETURNS TABLE (
    id uuid,
    empresa_id uuid,
    email varchar,
    nombre varchar,
    hash_de_contrasena varchar,
    rol varchar,
    activo boolean
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT u.id, u.empresa_id, u.email, u.nombre, u.hash_de_contrasena, u.rol, u.activo
    FROM usuario u
    WHERE u.email = lower(p_email)
    LIMIT 1;
$$;
"""

FUNCION_CUIT = """
CREATE OR REPLACE FUNCTION existe_cuit_registrado(p_cuit varchar)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT EXISTS (SELECT 1 FROM empresa e WHERE e.cuit = p_cuit);
$$;
"""

# EXECUTE to the application role only; PUBLIC is revoked so the functions are not an
# open door for any future role.
PERMISOS_FUNCIONES = (
    # One statement per call: asyncpg does not accept several in a single execute.
    "REVOKE ALL ON FUNCTION buscar_usuario_para_login(varchar) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION existe_cuit_registrado(varchar) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION buscar_usuario_para_login(varchar) TO cheatsheet_app",
    "GRANT EXECUTE ON FUNCTION existe_cuit_registrado(varchar) TO cheatsheet_app",
)

# Written out literally rather than built with an f-string over a list of names. SQL
# cannot be bound as parameters, so interpolation would read to a scanner exactly like
# the injection it is not — and train everyone to wave that warning away.
RLS_Y_PERMISOS = (
    "ALTER TABLE empresa ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE empresa FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON empresa TO cheatsheet_app",
    "ALTER TABLE usuario ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE usuario FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON usuario TO cheatsheet_app",
    "ALTER TABLE refresh_token ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE refresh_token FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON refresh_token TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "empresa",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("razon_social", sa.String(200), nullable=True),
        sa.Column("cuit", sa.String(11), nullable=True, unique=True),
        sa.Column("condicion_iva", sa.String(30), nullable=True),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("nombre_responsable", sa.String(200), nullable=True),
        sa.Column("email_contacto", sa.String(320), nullable=True),
        sa.Column("terminos_version", sa.String(20), nullable=True),
        sa.Column("terminos_fecha_aceptacion", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "usuario",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # Unique platform-wide: sign-in is by email alone, so two users sharing one
        # would make authentication ambiguous.
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("nombre", sa.String(200), nullable=False),
        # Null for accounts created through Google: that person chose no password here.
        sa.Column("hash_de_contrasena", sa.String(255), nullable=True),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pref_idioma", sa.String(10), nullable=False),
        sa.Column("pref_zona_horaria", sa.String(60), nullable=False),
    )
    op.create_index("ix_usuario_empresa", "usuario", ["empresa_id"])

    op.create_table(
        "refresh_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("familia_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hash_del_token", sa.String(64), nullable=False, unique=True),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocado", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_refresh_familia", "refresh_token", ["familia_id"])

    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA_EMPRESA)
    op.execute(POLITICA_USUARIO)
    op.execute(POLITICA_REFRESH)

    op.execute(FUNCION_LOGIN)
    op.execute(FUNCION_CUIT)
    for permiso in PERMISOS_FUNCIONES:
        op.execute(permiso)

    # The foreign key migration 0001 could not create, because `usuario` did not exist.
    op.create_foreign_key(
        "fk_auditoria_usuario",
        "registro_de_auditoria",
        "usuario",
        ["usuario_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_auditoria_usuario", "registro_de_auditoria", type_="foreignkey")
    op.execute("DROP FUNCTION IF EXISTS buscar_usuario_para_login(varchar)")
    op.execute("DROP FUNCTION IF EXISTS existe_cuit_registrado(varchar)")
    op.drop_index("ix_refresh_familia", table_name="refresh_token")
    op.drop_table("refresh_token")
    op.drop_index("ix_usuario_empresa", table_name="usuario")
    op.drop_table("usuario")
    op.drop_table("empresa")
