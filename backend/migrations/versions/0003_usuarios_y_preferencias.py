"""Users, invitations and personal preferences.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-14

Three changes and two functions.

**`usuario.activo` becomes `usuario.estado`.** The DER models a boolean; PAN-USR-01 shows
three states, and the "at least one active Administrator" invariant must not count
somebody invited as Administrator who never accepted. Declared as an extension of the
DER's own gap H1. The `upgrade` maps `true → ACTIVO` and `false → INACTIVO`, which is
exact: nobody has been invited yet, so no row can belong in the third state.

**`usuario.pref_suscripciones`** is the column the DER declares and migration 0002 left
out, because HU-E1-07 landed in this unit. It arrives `NOT NULL` with every existing row
opted in, which is what `PreferenciasDeNotificacion.todas()` gives a new account.

**`invitacion`** gets the same treatment as every other table: RLS by `empresa_id`,
`FORCE ROW LEVEL SECURITY`, grants to the application role and nothing to `PUBLIC`.

**The two new `SECURITY DEFINER` functions** exist for the reason the first two did:
refreshing a session and accepting an invitation both happen *before* there is a company,
so the company has to be discovered from the credential. Each returns **one uuid** and
nothing else — not a row, not a token, not a user. That is narrower than the two from
0002, and it is all their callers need.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLITICA_INVITACION = """
CREATE POLICY aislamiento_por_empresa ON invitacion
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

# Returns the company and nothing else. Whoever calls it already holds the token hash;
# learning which company it belongs to tells them nothing they could not infer by using
# it, and it is what lets the caller open a correctly scoped transaction.
FUNCION_EMPRESA_DE_REFRESH = """
CREATE OR REPLACE FUNCTION buscar_empresa_de_refresh(p_hash varchar)
RETURNS uuid
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT r.empresa_id FROM refresh_token r WHERE r.hash_del_token = p_hash LIMIT 1;
$$;
"""

FUNCION_EMPRESA_DE_INVITACION = """
CREATE OR REPLACE FUNCTION buscar_empresa_de_invitacion(p_hash varchar)
RETURNS uuid
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT i.empresa_id FROM invitacion i WHERE i.hash_del_token = p_hash LIMIT 1;
$$;
"""

# `buscar_usuario_para_login` was declared in 0002 returning `activo boolean`, and this
# migration drops that column. A `SECURITY DEFINER` function is not recompiled when the
# table under it changes, so it keeps working until the first sign-in — at which point
# every login fails with "column u.activo does not exist". It is redefined here, in the
# migration that causes the change.
#
# Dropped and recreated rather than replaced: `CREATE OR REPLACE` cannot change the
# columns a function returns.
FUNCION_LOGIN_CON_ESTADO = """
CREATE FUNCTION buscar_usuario_para_login(p_email varchar)
RETURNS TABLE (
    id uuid,
    empresa_id uuid,
    email varchar,
    nombre varchar,
    hash_de_contrasena varchar,
    rol varchar,
    estado varchar
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT u.id, u.empresa_id, u.email, u.nombre, u.hash_de_contrasena, u.rol, u.estado
    FROM usuario u
    WHERE u.email = lower(p_email)
    LIMIT 1;
$$;
"""

#: The 0002 shape, restored by `downgrade` so the schema and the function agree again.
FUNCION_LOGIN_CON_ACTIVO = """
CREATE FUNCTION buscar_usuario_para_login(p_email varchar)
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

PERMISOS_FUNCIONES = (
    "REVOKE ALL ON FUNCTION buscar_empresa_de_refresh(varchar) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION buscar_empresa_de_invitacion(varchar) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION buscar_empresa_de_refresh(varchar) TO cheatsheet_app",
    "GRANT EXECUTE ON FUNCTION buscar_empresa_de_invitacion(varchar) TO cheatsheet_app",
    "REVOKE ALL ON FUNCTION buscar_usuario_para_login(varchar) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION buscar_usuario_para_login(varchar) TO cheatsheet_app",
)

RLS_Y_PERMISOS = (
    "ALTER TABLE invitacion ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE invitacion FORCE ROW LEVEL SECURITY",
    # DELETE is granted on `usuario` because revoking an invitation removes the row —
    # see `RevocarInvitacion` for why that is a delete and not a state change.
    "GRANT SELECT, INSERT, UPDATE, DELETE ON invitacion TO cheatsheet_app",
    "GRANT DELETE ON usuario TO cheatsheet_app",
)


def upgrade() -> None:
    op.add_column("usuario", sa.Column("estado", sa.String(20), nullable=True))
    op.execute("UPDATE usuario SET estado = CASE WHEN activo THEN 'ACTIVO' ELSE 'INACTIVO' END")
    op.alter_column("usuario", "estado", nullable=False)
    op.drop_column("usuario", "activo")

    op.add_column(
        "usuario",
        sa.Column("pref_suscripciones", postgresql.JSONB, nullable=True),
    )
    # Every existing account opted in everywhere, matching the default for a new one.
    op.execute(
        """
        UPDATE usuario SET pref_suscripciones = jsonb_build_object(
            'FACTURACION',    jsonb_build_array('EMAIL', 'PANEL'),
            'COBROS',         jsonb_build_array('EMAIL', 'PANEL'),
            'SINCRONIZACION', jsonb_build_array('EMAIL', 'PANEL'),
            'AGENDA',         jsonb_build_array('EMAIL', 'PANEL'),
            'SISTEMA',        jsonb_build_array('EMAIL', 'PANEL')
        )
        """
    )
    op.alter_column("usuario", "pref_suscripciones", nullable=False)

    op.create_table(
        "invitacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # CASCADE, because revoking deletes the user row and the invitation must not
        # outlive it as a dangling pointer.
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hash_del_token", sa.String(64), nullable=False, unique=True),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "invitado_por",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("aceptada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocada", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_invitacion_empresa", "invitacion", ["empresa_id"])

    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA_INVITACION)

    op.execute("DROP FUNCTION IF EXISTS buscar_usuario_para_login(varchar)")
    op.execute(FUNCION_LOGIN_CON_ESTADO)
    op.execute(FUNCION_EMPRESA_DE_REFRESH)
    op.execute(FUNCION_EMPRESA_DE_INVITACION)
    for permiso in PERMISOS_FUNCIONES:
        op.execute(permiso)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS buscar_empresa_de_refresh(varchar)")
    op.execute("DROP FUNCTION IF EXISTS buscar_empresa_de_invitacion(varchar)")
    op.drop_index("ix_invitacion_empresa", table_name="invitacion")
    op.drop_table("invitacion")
    op.execute("REVOKE DELETE ON usuario FROM cheatsheet_app")

    op.drop_column("usuario", "pref_suscripciones")
    op.add_column("usuario", sa.Column("activo", sa.Boolean(), nullable=True))
    # An invited user has no equivalent in a boolean world; `false` is the safe direction,
    # because it denies access rather than granting it.
    op.execute("UPDATE usuario SET activo = (estado = 'ACTIVO')")
    op.alter_column("usuario", "activo", nullable=False)
    op.drop_column("usuario", "estado")

    op.execute("DROP FUNCTION IF EXISTS buscar_usuario_para_login(varchar)")
    op.execute(FUNCION_LOGIN_CON_ACTIVO)
    op.execute("REVOKE ALL ON FUNCTION buscar_usuario_para_login(varchar) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION buscar_usuario_para_login(varchar) TO cheatsheet_app")
