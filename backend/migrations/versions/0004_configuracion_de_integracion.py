"""External integration configuration.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-18

The first table of BC4, and the first credential this system stores.

**Gap H9.** The DER models the status as `activa boolean NOT NULL`. HU-E2-05 RN-02 asks
for three states, RN-03 for the timestamp of the last live check, and the criterion "una
integración está degradada → la muestro en Atención con el detalle disponible" for a
reason string. A boolean cannot separate *degraded* from *down*, which is the distinction
the story exists to display. `estado`, `detalle_estado` and `verificado_en` replace
`activa` rather than joining it: `activa` is derivable, and keeping both guarantees they
eventually disagree.

**No backfill.** The table is new and nothing has ever been connected, so `upgrade` has no
rows to convert and `downgrade` drops the table whole.

**`credencial_contenido_cifrado` stays NOT NULL, as the DER declares it.** A company with
nothing connected has no row here. PAN-CFG-INT shows four cards because the enum has four
entries on screen, not because four empty rows exist per company — which also means the
ciphertext column never holds a placeholder nobody can decrypt.

**RLS, like every other company-scoped table.** `FORCE ROW LEVEL SECURITY` so the barrier
applies to the table owner too, grants to `cheatsheet_app` only, nothing to `PUBLIC`. No
`SECURITY DEFINER` function is needed here: unlike login, every query in this context
happens inside a session that already knows its company.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON configuracion_de_integracion
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
RLS_Y_PERMISOS = (
    "ALTER TABLE configuracion_de_integracion ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE configuracion_de_integracion FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON configuracion_de_integracion TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "configuracion_de_integracion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sistema", sa.String(30), nullable=False),
        sa.Column("credencial_contenido_cifrado", sa.LargeBinary(), nullable=False),
        sa.Column("credencial_algoritmo", sa.String(40), nullable=False),
        sa.Column(
            "parametros",
            postgresql.JSONB(),  # type: ignore[no-untyped-call]  # untyped in the stubs
            nullable=False,
            server_default="{}",
        ),
        sa.Column("ambiente", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("detalle_estado", sa.String(300), nullable=True),
        sa.Column("verificado_en", sa.DateTime(timezone=True), nullable=True),
    )
    # The identity of the aggregate, and what makes ConectarIntegracion idempotent in the
    # database rather than only in the use case.
    op.create_unique_constraint(
        "uq_integracion_empresa_sistema",
        "configuracion_de_integracion",
        ["empresa_id", "sistema"],
    )
    op.create_index("ix_integracion_empresa", "configuracion_de_integracion", ["empresa_id"])

    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA)


def downgrade() -> None:
    op.drop_index("ix_integracion_empresa", table_name="configuracion_de_integracion")
    op.drop_constraint(
        "uq_integracion_empresa_sistema", "configuracion_de_integracion", type_="unique"
    )
    op.drop_table("configuracion_de_integracion")
