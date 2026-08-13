"""Foundation: extensions, the application role, and the audit log with RLS.

Revision ID: 0001
Revises:
Create Date: 2026-08-12

This is the first migration of the system, and it establishes three things every later
migration depends on.

**1. The extensions.** `pgvector` (semantic search over FAQs and intents, epic 8) and
`btree_gist` (the exclusion constraint that stops two `Turno` overlapping, epic 7).
They are installed now because installing an extension requires privileges the
application role will not have later.

**2. The application role.** `cheatsheet_app` is *not* the owner of these tables.
PostgreSQL exempts a table's owner from that table's RLS policies, so an application
connecting as the owner would bypass every isolation rule in the system while every
test still passed. This is the single most important line in the migration.

The role is created NOLOGIN if it does not already exist; provisioning
(`backend/scripts/init-db.sql` locally, the CI step, the deployment) grants LOGIN and a
password. That ordering works in both directions and keeps the credential out of the
repository.

**3. `registro_de_auditoria`** (HS-T5), whose columns are the DER's
(`docs/aidlc/inputs/der.md`, BC10) plus `modulo` (HS-T5 RN-02, gap H2) and `evento_id`
(ADR-009). The grants are what make RN-03 real: the application may `SELECT` and
`INSERT`, and holds no `UPDATE` or `DELETE`. Immutability that lives only in Python is
immutability until the first `psql` session.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROL_APLICACION = "cheatsheet_app"
TABLA = "registro_de_auditoria"

# Every statement below is a literal. SQL identifiers cannot be bound as parameters, so
# the alternative would be f-strings over constants — which reads to a scanner exactly
# like the injection it is not, and trains everyone to wave the warning away.
CREAR_ROL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cheatsheet_app') THEN
        CREATE ROLE cheatsheet_app NOLOGIN;
    END IF;
END
$$;
"""

# NULLIF + the missing_ok form of current_setting is what makes this fail closed: a
# session that never announced its company sees no rows at all, instead of erroring in
# a way somebody would be tempted to "fix" by disabling the policy.
POLITICA = """
CREATE POLICY aislamiento_por_empresa ON registro_de_auditoria
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

GRANT_USO_DEL_ESQUEMA = "GRANT USAGE ON SCHEMA public TO cheatsheet_app"
HABILITAR_RLS = "ALTER TABLE registro_de_auditoria ENABLE ROW LEVEL SECURITY"
# ENABLE alone still exempts the owner. FORCE is what closes that door, and it is the
# reason the isolation tests are worth anything.
FORZAR_RLS = "ALTER TABLE registro_de_auditoria FORCE ROW LEVEL SECURITY"
# HS-T5 RN-03, enforced by the engine: append and read, never modify or remove.
GRANT_APPEND_ONLY = "GRANT SELECT, INSERT ON registro_de_auditoria TO cheatsheet_app"
REVOCAR_TODO = "REVOKE ALL ON registro_de_auditoria FROM cheatsheet_app"
BORRAR_POLITICA = "DROP POLICY IF EXISTS aislamiento_por_empresa ON registro_de_auditoria"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(CREAR_ROL)
    op.execute(GRANT_USO_DEL_ESQUEMA)

    op.create_table(
        TABLA,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evento_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("empresa_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Nullable by design: a null initiator is the statement that the system acted.
        # No FK to `usuario` yet — that table arrives with the identity unit, and a
        # migration cannot reference what does not exist. Added there.
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("modulo", sa.String(40), nullable=False),
        sa.Column("accion", sa.String(120), nullable=False),
        sa.Column("entidad_afectada", sa.String(200), nullable=False),
        sa.Column("resultado", sa.String(20), nullable=False),
        # 45 characters: the longest IPv6 form, including an IPv4-mapped tail.
        sa.Column("direccion_ip", sa.String(45), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auditoria_empresa_timestamp", TABLA, ["empresa_id", "timestamp"])
    op.create_index("ix_auditoria_empresa_modulo", TABLA, ["empresa_id", "modulo"])

    op.execute(HABILITAR_RLS)
    op.execute(FORZAR_RLS)
    op.execute(POLITICA)
    op.execute(GRANT_APPEND_ONLY)


def downgrade() -> None:
    op.execute(REVOCAR_TODO)
    op.execute(BORRAR_POLITICA)
    op.drop_index("ix_auditoria_empresa_modulo", table_name=TABLA)
    op.drop_index("ix_auditoria_empresa_timestamp", table_name=TABLA)
    op.drop_table(TABLA)
    # The role and the extensions are not dropped: they are cluster-level objects that
    # other databases and later migrations may share. Reverting this migration must undo
    # *this* migration, not the server.
