"""The customer catalogue.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-31

The first table of BC2, and the first one four other contexts will read: `billing` puts a
`Cliente` on a `Comprobante`, `payments` charges it, `scheduling` books it and
`conversational` talks to it.

**`categoria_id` is not here, and the DER has it.** Decision D8 of the epic 3 units map:
HU-E4-04 RN-02 lets one client carry several categories, and a single foreign key cannot
hold more than one. The link table arrives with `categorias-y-clasificacion`, and the
column is never created — so there is no data to migrate when it does.

**`cuit` is nullable, as the DER declares it**, against a reading of HU-E4-01 RN-02 that
assumes every client has one. HU-E8-01 registers clients from WhatsApp knowing nothing but
a phone number.

**The unique index is partial.** RN-03 forbids two clients of one company sharing a CUIT.
Without `WHERE cuit IS NOT NULL` the second client with no CUIT would collide with the
first — in PostgreSQL nulls do not collide in a unique index, but writing the predicate
says so on purpose and keeps the index off the rows it has no business in.

**No backfill.** The table is new; `downgrade` drops it whole.

**RLS, like every other company-scoped table.** `FORCE ROW LEVEL SECURITY` so the barrier
applies to the table owner too, grants to `cheatsheet_app` only, nothing to `PUBLIC`. No
`SECURITY DEFINER` function: unlike login, every query in this context happens inside a
session that already knows its company.

`DELETE` is deliberately **not** granted. `application/clientes.py` offers no delete —
ADR-007, and the fact that `comprobante`, `cobro` and `turno` reference this id without a
declared foreign key (DER gap H4). A grant nobody uses is a grant available on the day
somebody writes the statement by mistake.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON cliente
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
RLS_Y_PERMISOS = (
    "ALTER TABLE cliente ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE cliente FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON cliente TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "cliente",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("cuit", sa.String(11), nullable=True),
        sa.Column("condicion_iva", sa.String(30), nullable=True),
        sa.Column("contacto_whatsapp", sa.String(20), nullable=True),
        sa.Column("contacto_email", sa.String(320), nullable=True),
        sa.Column("origen", sa.String(20), nullable=False),
        sa.Column("presente_en_planilla", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("referencia_fila_planilla", sa.String(100), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cliente_empresa", "cliente", ["empresa_id"])
    op.create_index(
        "uq_cliente_empresa_cuit",
        "cliente",
        ["empresa_id", "cuit"],
        unique=True,
        postgresql_where=sa.text("cuit IS NOT NULL"),
    )

    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA)


def downgrade() -> None:
    op.drop_index("uq_cliente_empresa_cuit", table_name="cliente")
    op.drop_index("ix_cliente_empresa", table_name="cliente")
    op.drop_table("cliente")
