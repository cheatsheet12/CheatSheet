"""The access tickets of the platform certificate (ADR-0014).

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-08

With web service delegation CheatSheet reaches ARCA through **one** certificate, acting for
every company that delegated «Facturación Electrónica» to it. WSAA issues one ticket per
certificate and service and refuses a second while the first is alive, so the ticket is the
platform's: one row per service.

**A gap in the DER, declared in ADR-0014.** The DER models what a company gives us; this is
not that.

**No `empresa_id`, and therefore no Row-Level Security.** The row holds no company's data —
only an encrypted token and sign of the platform — and every company is reached through it.
`verify_rls.py` checks the tables that carry `empresa_id`; this one deliberately does not.

`ticket_de_acceso` stays: the real adapter no longer writes it, and a later migration drops
it once nothing reads it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_de_plataforma",
        sa.Column("servicio", sa.String(30), primary_key=True),
        sa.Column("contenido_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("algoritmo", sa.String(40), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON ticket_de_plataforma TO cheatsheet_app")


def downgrade() -> None:
    op.drop_table("ticket_de_plataforma")
