"""ARCA access tickets, and the sweep that finds the companies holding them.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-19

**Gap H11 — a table the DER does not have.** The DER models the *credential*: what a
company gave us so we can act on its behalf. ARCA adds a short-lived session derived from
it, and the two cannot share a row: a ticket lasts about twelve hours against a
certificate's two years, and a ticket authenticates one ARCA service, so a company holds
several at once while it has exactly one certificate.

Storing it is a correctness requirement rather than a cache. WSAA **refuses to issue a
second ticket while the first is alive**, answering "El CEE ya posee un TA valido". A
system that discards the ticket it was handed cannot authenticate again until that ticket
expires — up to twelve hours during which the company cannot invoice. The full reasoning,
and the alternatives that were ruled out, are in ADR-0004.

**The content is encrypted**, with the same AES-256-GCM adapter and the same algorithm
marker as the credentials themselves. A token and its sign are secrets in their own right:
whoever holds them speaks to ARCA as that company for the rest of the ticket's life.

**`empresas_con_integracion_de_arca()`** is the second and last `SECURITY DEFINER`
function of this context, and it exists for the same reason as the first: Beat runs with
no company, so `app.current_empresa` is unset and the RLS policies correctly show it
nothing. It gets its own function rather than a parameter on the existing one — a function
that steps around Row-Level Security is a hole in the only multi-tenant barrier this
system has, and one whose shape the caller chooses is a wider hole. It returns company ids
and nothing else.

**No backfill.** Nothing has ever connected ARCA; the table is new.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON ticket_de_acceso
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

FUNCION = """
CREATE OR REPLACE FUNCTION empresas_con_integracion_de_arca()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT c.empresa_id
    FROM configuracion_de_integracion c
    WHERE c.sistema = 'ARCA'
$$;
"""

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
RLS_Y_PERMISOS = (
    "ALTER TABLE ticket_de_acceso ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ticket_de_acceso FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ticket_de_acceso TO cheatsheet_app",
    "REVOKE ALL ON FUNCTION empresas_con_integracion_de_arca() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_integracion_de_arca() TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "ticket_de_acceso",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("servicio", sa.String(30), nullable=False),
        sa.Column("contenido_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("algoritmo", sa.String(40), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
    )
    # One ticket per company and service, which is the rule WSAA enforces on its side.
    op.create_unique_constraint(
        "uq_ticket_empresa_servicio", "ticket_de_acceso", ["empresa_id", "servicio"]
    )
    op.create_index("ix_ticket_empresa", "ticket_de_acceso", ["empresa_id"])

    op.execute(FUNCION)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_integracion_de_arca()")
    op.drop_index("ix_ticket_empresa", table_name="ticket_de_acceso")
    op.drop_constraint("uq_ticket_empresa_servicio", "ticket_de_acceso", type_="unique")
    op.drop_table("ticket_de_acceso")
