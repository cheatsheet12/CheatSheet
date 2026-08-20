"""Which companies have MercadoPago connected.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-20

One function and nothing else. `conexion-mercadopago` renews an access token that lasts
about 180 days, and the daily sweep that does it needs to know which companies to visit.
Beat runs with no company — `app.current_empresa` is unset and the RLS policy on
`configuracion_de_integracion` correctly shows it nothing — so this is the same shape as
the two functions that already exist, and it gets the same answer.

**Migration 0006 called its own function "the second and last".** It is not: this is the
third. What that comment was defending is still respected, and is why this is a separate
function rather than a parameter added to `empresas_con_integracion_de_arca` — a
`SECURITY DEFINER` function is a hole in the only multi-tenant barrier this system has,
and one whose shape the caller chooses is a wider hole. One question, no arguments,
company ids and nothing else: not the credential, not the tokens, not the expiry.

`SET search_path = public` so the body cannot be redirected at a schema an unprivileged
role controls, `STABLE` because it only reads, `EXECUTE` granted to `cheatsheet_app` and
revoked from `PUBLIC`.

**No backfill and no table change.** Nothing has ever connected MercadoPago.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FUNCION = """
CREATE OR REPLACE FUNCTION empresas_con_integracion_de_mercadopago()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT c.empresa_id
    FROM configuracion_de_integracion c
    WHERE c.sistema = 'MERCADOPAGO'
$$;
"""

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
PERMISOS = (
    "REVOKE ALL ON FUNCTION empresas_con_integracion_de_mercadopago() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_integracion_de_mercadopago() TO cheatsheet_app",
)


def upgrade() -> None:
    op.execute(FUNCION)
    for sentencia in PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_integracion_de_mercadopago()")
