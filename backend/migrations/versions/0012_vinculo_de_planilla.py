"""vinculo_de_planilla — the three ways a spreadsheet enters the system (HU-E2-04).

The DER's table (BC5) plus four columns it does not have, each demanded by a rule:

- **`pausado` / `motivo_de_pausa`** — HU-E2-04 RN-04 and HU-E3-04 RN-03 both say the sync
  *pauses* when the structure changes. A pause that is not stored ends at the next worker
  restart, which turns a deliberate stop into an intermittent one.
- **`archivo_clave` / `archivo_nombre` / `archivo_tamano`** — decision D10's `ARCHIVO`
  provider. The DER has no column for an uploaded workbook because it has no such
  provider; `procesamiento_de_planilla.vinculo_id` being NOT NULL is what forces one.

**`DELETE` is granted here**, unlike `registro_de_auditoria` and `tarea_asincrona`.
Unlinking a spreadsheet is an ordinary Administrator operation and destroys nothing
ADR-007 protects: the `Cliente` and `Servicio` rows already ingested survive untouched,
keeping their `origen` and `presente_en_planilla`. What disappears is the connection, not
the history.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
POLITICA_VINCULO = """
CREATE POLICY aislamiento_por_empresa ON vinculo_de_planilla
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: PAN-ING-01 lists this company's links, newest first.
INDICE_LISTADO = """
CREATE INDEX ix_vinculo_empresa_created
    ON vinculo_de_planilla (empresa_id, created_at DESC);
"""

#: The incremental sweep of HU-E3-04 only ever asks for live, unpaused links. Partial,
#: because an uploaded file is never a candidate and most rows will be uploaded files.
INDICE_SINCRONIZABLES = """
CREATE INDEX ix_vinculo_sincronizables
    ON vinculo_de_planilla (empresa_id)
    WHERE pausado = false AND proveedor <> 'ARCHIVO';
"""

#: `DELETE` included. See the module docstring.
RLS_Y_PERMISOS = (
    "ALTER TABLE vinculo_de_planilla ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE vinculo_de_planilla FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON vinculo_de_planilla TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "vinculo_de_planilla",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Nullable: an `ARCHIVO` link has no stored credential, and neither does a
        # Google link until the OAuth token is persisted by `integrations`.
        sa.Column(
            "configuracion_integracion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("configuracion_de_integracion.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # The FK to `mapeo` arrives with the mapping unit, which creates that table.
        sa.Column("mapeo_vigente_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proveedor", sa.String(20), nullable=False),
        sa.Column("direccion", sa.String(20), nullable=False),
        sa.Column("identificador_externo", sa.String(200), nullable=True),
        sa.Column("hoja_empresa", sa.String(200), nullable=False),
        sa.Column("hoja_cheatsheet", sa.String(200), nullable=True),
        sa.Column("archivo_clave", sa.String(400), nullable=True),
        sa.Column("archivo_nombre", sa.String(300), nullable=True),
        sa.Column("archivo_tamano", sa.Integer(), nullable=True),
        sa.Column("ultima_lectura", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_escritura", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pausado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("motivo_de_pausa", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "proveedor IN ('GOOGLE_SHEETS', 'EXCEL_ONLINE', 'ARCHIVO')",
            name="ck_vinculo_proveedor",
        ),
        sa.CheckConstraint(
            "direccion IN ('SOLO_LECTURA', 'LECTURA_Y_ESCRITURA')", name="ck_vinculo_direccion"
        ),
        # The aggregate's central invariant, restated in the engine. Only Google Sheets
        # can be linked for writing -- Excel Online is read-only through this
        # integration, and an uploaded file has nowhere to write back to. The domain
        # enforces it too; this is what holds when somebody opens psql at 3 a.m.
        sa.CheckConstraint(
            "direccion = 'SOLO_LECTURA' OR proveedor = 'GOOGLE_SHEETS'",
            name="ck_vinculo_solo_google_escribe",
        ),
        # `ARCHIVO` needs its bytes; everything else needs the provider's document id.
        sa.CheckConstraint(
            "(proveedor = 'ARCHIVO' AND archivo_clave IS NOT NULL)"
            " OR (proveedor <> 'ARCHIVO' AND identificador_externo IS NOT NULL)",
            name="ck_vinculo_origen_completo",
        ),
    )
    op.execute(INDICE_LISTADO)
    op.execute(INDICE_SINCRONIZABLES)
    op.execute(POLITICA_VINCULO)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.drop_table("vinculo_de_planilla")
