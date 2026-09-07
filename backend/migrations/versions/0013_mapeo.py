"""mapeo and entrada_de_mapeo — what the columns of a spreadsheet mean (HU-E3-01/02).

The DER's two tables (BC5), plus two columns on the entries that it does not have and one
denormalisation:

- **`ejemplo` and `corregida_a_mano`** — the DER models the mapping, not its review.
  HU-E3-02 needs both: the sample value is one of the four things the review screen shows
  per column, and the flag is what stops a re-run of the model from undoing a correction
  somebody made on purpose.
- **`empresa_id` on `entrada_de_mapeo`** — the DER protects internal entities through
  their parent. Here the parent is one join away from every read, and a policy that has to
  join is one missing index away from being the slowest thing in the context. The column
  is denormalised so RLS scopes the table directly, like every other table in the system.

**No `DELETE` on `mapeo`.** It is the record of how every already-ingested row was
interpreted; deleting one turns the history of a processing into columns nobody can read
back. Superseding a mapping is `nueva_version`, which keeps both. `entrada_de_mapeo` does
get `DELETE`, because correcting a mapping rewrites its entries.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
POLITICA_MAPEO = """
CREATE POLICY aislamiento_por_empresa ON mapeo
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_ENTRADA = """
CREATE POLICY aislamiento_por_empresa ON entrada_de_mapeo
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: RN-02's reuse lookup, and the only query `mapeo` answers. Unique per company: one
#: structure has one current mapping, and a second would never be found.
INDICE_HUELLA = """
CREATE UNIQUE INDEX uq_mapeo_empresa_huella
    ON mapeo (empresa_id, huella_encabezado);
"""

RLS_Y_PERMISOS = (
    "ALTER TABLE mapeo ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE mapeo FORCE ROW LEVEL SECURITY",
    # No DELETE. See the module docstring.
    "GRANT SELECT, INSERT, UPDATE ON mapeo TO cheatsheet_app",
    "ALTER TABLE entrada_de_mapeo ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE entrada_de_mapeo FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON entrada_de_mapeo TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "mapeo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("huella_encabezado", sa.String(64), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("estado IN ('BORRADOR', 'VALIDADO')", name="ck_mapeo_estado"),
        sa.CheckConstraint("version >= 1", name="ck_mapeo_version"),
    )
    op.create_table(
        "entrada_de_mapeo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "mapeo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mapeo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("columna_origen", sa.String(300), nullable=False),
        # Nullable: this is the `Sin asignar` of RN-03, and it is a real answer.
        sa.Column("atributo_destino", sa.String(80), nullable=True),
        # NUMERIC and never a float: the score is compared against the RN-03 thresholds
        # for equality, and 0.75 is not 0.75 in binary floating point.
        sa.Column("score", sa.Numeric(5, 4), nullable=False),
        sa.Column("ejemplo", sa.String(500), nullable=True),
        sa.Column(
            "corregida_a_mano", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_entrada_score"),
        # One column of a spreadsheet maps once. Two rows for `Nombre` would make which
        # one wins depend on the order the repository happened to read them in.
        sa.UniqueConstraint("mapeo_id", "columna_origen", name="uq_entrada_mapeo_columna"),
    )
    op.create_index("ix_entrada_mapeo", "entrada_de_mapeo", ["mapeo_id"])

    # The FK that migration 0012 could not declare, because `mapeo` did not exist yet.
    op.create_foreign_key(
        "fk_vinculo_mapeo_vigente",
        "vinculo_de_planilla",
        "mapeo",
        ["mapeo_vigente_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(INDICE_HUELLA)
    op.execute(POLITICA_MAPEO)
    op.execute(POLITICA_ENTRADA)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.drop_constraint("fk_vinculo_mapeo_vigente", "vinculo_de_planilla", type_="foreignkey")
    op.drop_table("entrada_de_mapeo")
    op.drop_table("mapeo")
