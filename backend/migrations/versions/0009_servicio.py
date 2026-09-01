"""The service catalogue.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-01

The second table of BC2, and **the first table in this system that stores money**.

**`precio NUMERIC(12, 2)`, never `FLOAT`.** `docs/code-standards.md` §2.5 is explicit and
this is where it starts being enforced by the schema rather than by review. Twelve integer
digits is a thousand million pesos; two decimals is what can be invoiced.

**`alicuota_iva NUMERIC(5, 4)`, and the scale is the point.** The three rates HU-E4-02
RN-02 allows are 0, 0.105 and 0.21, and `0.105` needs three decimals to survive. With
scale 2 PostgreSQL would round it to `0.11` on the way in — silently, correctly by its own
rules, and wrong on every reduced-rate line epic 5 ever issues.

**`categoria_id` is not here**, for the same reason it is not on `cliente`: decision D8 of
the epic 3 units map.

**No unique index.** Services have no uniqueness rule — two branches may both sell a
"Corte" — so there is nothing to constrain.

**No backfill.** The table is new; `downgrade` drops it whole.

**RLS like every other company-scoped table**, and `DELETE` deliberately not granted:
HU-E4-02 RN-04 says deactivating must not remove the documents and appointments that
reference the service, and `comprobante.servicio_id` and `turno.servicio_id` point here
without a declared foreign key (DER gap H4).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON servicio
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
RLS_Y_PERMISOS = (
    "ALTER TABLE servicio ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE servicio FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON servicio TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "servicio",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("precio", sa.Numeric(12, 2), nullable=False),
        sa.Column("alicuota_iva", sa.Numeric(5, 4), nullable=False),
        sa.Column("agendable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duracion_estandar_min", sa.Integer(), nullable=True),
        sa.Column("origen", sa.String(20), nullable=False),
        sa.Column("presente_en_planilla", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_servicio_empresa", "servicio", ["empresa_id"])

    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA)


def downgrade() -> None:
    op.drop_index("ix_servicio_empresa", table_name="servicio")
    op.drop_table("servicio")
