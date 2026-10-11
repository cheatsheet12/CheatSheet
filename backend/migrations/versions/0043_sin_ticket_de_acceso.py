"""Drop the per-company ARCA access tickets of model 1 (ADR-0014).

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-10

Since ADR-0014 every company is reached through the platform certificate, whose tickets live
in `ticket_de_plataforma` (migration 0036). `ticket_de_acceso` held the tickets minted with
each company's own certificate; nothing has written or read it since then, and the code that
did is gone. What it still holds are twelve-hour sessions of certificates no longer in use.

`empresas_con_integracion_de_arca()` was created by the same migration but stays: it reads
`configuracion_de_integracion`, and the daily ARCA sweep still uses it.

The downgrade recreates the table empty, as migration 0006 created it. The tickets it held
are not restored, and need not be: they expire in twelve hours and are minted on demand.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Migration 0006's isolation, written out again for the downgrade.
POLITICA = """
CREATE POLICY aislamiento_por_empresa ON ticket_de_acceso
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

RLS_Y_PERMISOS = (
    "ALTER TABLE ticket_de_acceso ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE ticket_de_acceso FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ticket_de_acceso TO cheatsheet_app",
)


def upgrade() -> None:
    op.drop_table("ticket_de_acceso")


def downgrade() -> None:
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
    op.create_unique_constraint(
        "uq_ticket_empresa_servicio", "ticket_de_acceso", ["empresa_id", "servicio"]
    )
    op.create_index("ix_ticket_empresa", "ticket_de_acceso", ["empresa_id"])
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA)
