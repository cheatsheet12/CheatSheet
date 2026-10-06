"""tarea_asincrona — execution state and the DLQ (HS-T6).

The first table of epic 4, and it belongs to `observability` rather than to
`spreadsheet_sync`: the aggregate is cross-context. Every worker in the system writes
here, which is the same reason the audit log of migration 0001 lives where it lives.

**`DELETE` is not granted**, unlike the categories of migration 0010. HS-T6 RN-04 keeps
exhausted tasks so they can be analysed and eventually replayed, and a role that cannot
delete them cannot be talked into it by a cleanup job written in a hurry six months from
now. It is the same argument as the audit table, arrived at from a different rule.

**`estado` is a `varchar` with a CHECK, not a PostgreSQL enum.** The DER writes
`estado_tarea` as an enum and this migration deliberately departs from that: adding a
value to a PG enum is a migration that cannot run inside a transaction on older servers,
and this catalogue is the one most likely to grow — a `REINTENTANDO` or a `CANCELADA`
would each cost a fragile migration. A CHECK constraint gives the same closed set and is
altered like any other constraint. The application already treats it as a closed enum in
`domain/tarea_asincrona.py`, which is where the guarantee is read from.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
POLITICA_TAREA = """
CREATE POLICY aislamiento_por_empresa ON tarea_asincrona
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: The sweep's only query, and the only index this table needs. Partial on `FALLIDA`, so
#: it holds the handful of rows that are failing rather than every task ever run — which
#: on a spreadsheet import is the difference between kilobytes and gigabytes.
INDICE_FALLIDAS = """
CREATE INDEX ix_tarea_empresa_fallidas
    ON tarea_asincrona (empresa_id, created_at)
    WHERE estado = 'FALLIDA';
"""

#: **The sweep runs with no company, so RLS correctly shows it nothing.** Same shape and
#: same answer as migration 0005: a `SECURITY DEFINER` function that returns company ids
#: and nothing else — not the payload, not the type, not the failure reason. It is a hole
#: in the only multi-tenant barrier this system has, so what comes through it is useless on
#: its own, and the per-company task it feeds opens an ordinary session where RLS applies.
#:
#: This is the **fourth** such function in the system. The other three belong to
#: `integrations`; they are the only cross-company reads that exist and they are worth a
#: look in any security review.
FUNCION = """
CREATE OR REPLACE FUNCTION empresas_con_tareas_fallidas()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT t.empresa_id
    FROM tarea_asincrona t
    WHERE t.estado = 'FALLIDA'
$$;
"""

PERMISOS_FUNCION = (
    "REVOKE ALL ON FUNCTION empresas_con_tareas_fallidas() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_tareas_fallidas() TO cheatsheet_app",
)

#: No `DELETE`. See the module docstring.
RLS_Y_PERMISOS = (
    "ALTER TABLE tarea_asincrona ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE tarea_asincrona FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON tarea_asincrona TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "tarea_asincrona",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(120), nullable=False),
        # Uninstantiated, like migration 0003: the class itself is the type, and
        # calling it is an untyped call mypy rejects under --strict.
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("clave_idempotencia", sa.String(200), nullable=False),
        sa.Column("resultado", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'EN_CURSO', 'COMPLETADA', 'FALLIDA', 'DLQ')",
            name="ck_tarea_estado",
        ),
        sa.CheckConstraint("intentos >= 0", name="ck_tarea_intentos_no_negativos"),
        # One intended effect per company (ADR-009). Scoped to the company and not
        # global: two companies legitimately run the same work over the same payload,
        # and a global constraint would make the second one a duplicate of the first.
        sa.UniqueConstraint("empresa_id", "clave_idempotencia", name="uq_tarea_empresa_clave"),
    )
    op.execute(INDICE_FALLIDAS)
    op.execute(POLITICA_TAREA)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(FUNCION)
    for sentencia in PERMISOS_FUNCION:
        op.execute(sentencia)


def downgrade() -> None:
    # The function goes first: it depends on the table, and PostgreSQL would refuse the
    # drop otherwise.
    op.execute("DROP FUNCTION IF EXISTS empresas_con_tareas_fallidas()")
    # The policy, the index and the grants go with the table; dropping it is enough.
    op.drop_table("tarea_asincrona")
