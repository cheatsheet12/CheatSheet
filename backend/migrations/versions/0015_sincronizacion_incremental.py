"""The Beat sweep of the incremental sync needs to find companies (HU-E3-04).

Beat runs with no company set, so `app.current_empresa` is unset and the RLS policy on
`vinculo_de_planilla` correctly shows it nothing. Same shape and same answer as migrations
0005 and 0011: a `SECURITY DEFINER` function that returns company ids and nothing else,
feeding a per-company task that opens an ordinary session where RLS applies normally.

**This is the fifth such function in the system**, and the second outside `integrations`.
Between them they are the only cross-company reads that exist, and they are worth a look in
any security review. Each answers exactly one question and takes no arguments — a
parametrised one would be a hole whose shape the caller chooses.

**The filter is the same as the partial index of migration 0012.** A link is a candidate
when it is not paused, is not an uploaded file, and has a confirmed mapping: an `ARCHIVO`
is a snapshot with nothing new to offer, a paused link is waiting for a person (RN-03), and
one without a mapping has nothing to interpret rows with.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCION = """
CREATE OR REPLACE FUNCTION empresas_con_planilla_sincronizable()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT v.empresa_id
    FROM vinculo_de_planilla v
    WHERE v.pausado = false
      AND v.proveedor <> 'ARCHIVO'
      AND v.mapeo_vigente_id IS NOT NULL
$$;
"""

PERMISOS = (
    "REVOKE ALL ON FUNCTION empresas_con_planilla_sincronizable() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_planilla_sincronizable() TO cheatsheet_app",
)


def upgrade() -> None:
    op.execute(FUNCION)
    for sentencia in PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_planilla_sincronizable()")
