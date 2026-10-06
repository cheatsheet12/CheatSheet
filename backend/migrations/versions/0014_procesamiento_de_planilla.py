"""procesamiento_de_planilla and error_de_fila — running a sheet into the catalogue.

HU-E3-03, HU-E3-05 and HU-E3-06. The DER's two tables (BC5), plus:

- **`origen_id`** — HU-E3-06 RN-03 wants a reprocessing to be «un nuevo procesamiento
  vinculado al original». Without the column the history is two unrelated imports.
- **`empresa_id` on `error_de_fila`** — denormalised so RLS scopes the table directly,
  for the reason migration 0013 gives about `entrada_de_mapeo`. A failed import writes
  thousands of these rows and every read of them would otherwise be a join.

**`estado` carries a fourth value the DER does not have: `CON_ERRORES`.** The DER closes
the enum at `EN_CURSO`, `COMPLETADO` and `FALLIDO`; HU-E3-03's third acceptance criterion
describes a run that finished, filled the catalogue, and left some rows behind — «Con
errores», which is not `FALLIDO`. Collapsing the two would make «se procesaron 39.999 de
40.000» look like a failed import to everyone reading the screen.

**No `DELETE` on either table.** A processing is the record of an import that already
wrote into `master_data`; HU-E3-05 exists so somebody can read it afterwards. Deleting one
leaves rows in the catalogue whose provenance nothing explains.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
POLITICA_PROCESAMIENTO = """
CREATE POLICY aislamiento_por_empresa ON procesamiento_de_planilla
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_ERROR = """
CREATE POLICY aislamiento_por_empresa ON error_de_fila
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

RLS_Y_PERMISOS = (
    "ALTER TABLE procesamiento_de_planilla ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE procesamiento_de_planilla FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON procesamiento_de_planilla TO cheatsheet_app",
    "ALTER TABLE error_de_fila ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE error_de_fila FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON error_de_fila TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "procesamiento_de_planilla",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vinculo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vinculo_de_planilla.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mapeo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mapeo.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # RESTRICT above and here: the mapping and the original run are how anybody
        # explains, later, why a row in the catalogue says what it says.
        sa.Column(
            "origen_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("procesamiento_de_planilla.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("filas_totales", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("filas_ok", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("filas_error", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("duracion_ms", sa.Integer(), nullable=True),
        sa.Column("referencia_archivo", sa.String(400), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "estado IN ('EN_CURSO', 'COMPLETADO', 'CON_ERRORES', 'FALLIDO')",
            name="ck_procesamiento_estado",
        ),
        # The three counters are maintained together by the aggregate; this is what says
        # so to anybody reading the schema, and what catches a repository that forgets.
        sa.CheckConstraint(
            "filas_ok >= 0 AND filas_error >= 0 AND filas_totales = filas_ok + filas_error",
            name="ck_procesamiento_contadores",
        ),
    )
    op.create_index(
        "ix_procesamiento_empresa_created",
        "procesamiento_de_planilla",
        ["empresa_id", "created_at"],
    )
    op.create_index("ix_procesamiento_vinculo", "procesamiento_de_planilla", ["vinculo_id"])

    op.create_table(
        "error_de_fila",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "procesamiento_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("procesamiento_de_planilla.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("numero_fila", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(300), nullable=False),
        sa.CheckConstraint("numero_fila >= 1", name="ck_error_numero_fila"),
    )
    op.create_index(
        "ix_error_procesamiento_fila", "error_de_fila", ["procesamiento_id", "numero_fila"]
    )

    op.execute(POLITICA_PROCESAMIENTO)
    op.execute(POLITICA_ERROR)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.drop_table("error_de_fila")
    op.drop_table("procesamiento_de_planilla")
