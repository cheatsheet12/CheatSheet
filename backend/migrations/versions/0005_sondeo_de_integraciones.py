"""Asynchronous verification of an integration.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-18

Two things, both for HU-E2-03.

**`pendiente_desde` — gap H10.** Meta takes 24 to 72 hours to verify a phone number
(RN-02), so an integration can be in flight for days. Deciding when to stop waiting needs
to know when the wait started, and no existing column can say: `verificado_en` is
re-stamped by every poll, so it measures the last question rather than the wait. Nullable
because it is meaningless for every state other than `PENDIENTE`, and cleared when the
wait ends so a later pending period is never measured from an earlier one.

`estado` is already `varchar(20)`, so the new `PENDIENTE` value needs no migration at all.

**`empresas_con_integracion_pendiente()` — the sweep.** Beat runs with no company:
`app.current_empresa` is unset, and the RLS policy on `configuracion_de_integracion`
correctly shows it nothing. That is the same shape as sign-in — discovering which company
something belongs to before the company is known — and it gets the same answer migrations
0002 and 0003 already use four times.

**The function returns company ids and nothing else.** Not the credential, not the
parameters, not even the state. A `SECURITY DEFINER` function is a hole in the only
multi-tenant barrier this system has, so it is kept narrow enough that what comes through
it is useless on its own; the per-company task it feeds opens an ordinary session where
RLS applies normally. `SET search_path = public` so the body cannot be redirected at a
schema an unprivileged role controls, `STABLE` because it only reads, `EXECUTE` granted to
`cheatsheet_app` and revoked from `PUBLIC`.

**No backfill.** Nothing has ever been pending: the state did not exist until this
revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCION = """
CREATE OR REPLACE FUNCTION empresas_con_integracion_pendiente()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT c.empresa_id
    FROM configuracion_de_integracion c
    WHERE c.estado = 'PENDIENTE'
$$;
"""

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
PERMISOS = (
    "REVOKE ALL ON FUNCTION empresas_con_integracion_pendiente() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_integracion_pendiente() TO cheatsheet_app",
)

#: The poll asks one question, on a schedule, for every company that has something
#: pending. Without this the planner scans the whole table each time.
INDICE = "ix_integracion_pendientes"


def upgrade() -> None:
    op.add_column(
        "configuracion_de_integracion",
        sa.Column("pendiente_desde", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        INDICE,
        "configuracion_de_integracion",
        ["estado"],
        postgresql_where=sa.text("estado = 'PENDIENTE'"),
    )
    op.execute(FUNCION)
    for sentencia in PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_integracion_pendiente()")
    op.drop_index(INDICE, table_name="configuracion_de_integracion")
    op.drop_column("configuracion_de_integracion", "pendiente_desde")
