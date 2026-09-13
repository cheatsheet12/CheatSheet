"""punto_de_venta — the fiscal numbering a company invoices from (HU-E5-05).

The DER's table (BC6), unchanged. The first table of `billing`, and the one whose column
carries the most risk in the system: `numerador_por_tipo` holds the last number used per
document type, and two documents with the same number is a fiscal inconsistency fixed with
the AFIP rather than with an `UPDATE`.

**What protects it is not in this file.** JSONB has no built-in serialisation, and the
uniqueness of a fiscal number is not something a column type can promise. Decision D14
puts it in `SELECT … FOR UPDATE` on this row, in `tomar_para_emitir` — the same mechanism
migration 0003 used for «always at least one Administrador». The schema's contribution is
the unique index on `(empresa_id, numero)`, which is a different guarantee: it stops two
*points* sharing a number, not two documents.

**`DELETE` is not granted.** A point of sale that issued documents cannot be removed
without orphaning them, and those documents carry a CAE. HU-E5-05 RN-04 asks for
deactivation, which keeps everything, and that is all the story needs.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
POLITICA_PUNTO = """
CREATE POLICY aislamiento_por_empresa ON punto_de_venta
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: HU-E5-05: «Ya existe un punto de venta con ese numero.» Enforced by the index and not by
#: a read-then-write, which loses to a second tab.
INDICE_UNICO = """
CREATE UNIQUE INDEX uq_punto_empresa_numero
    ON punto_de_venta (empresa_id, numero);
"""

#: No `DELETE`. See the module docstring.
RLS_Y_PERMISOS = (
    "ALTER TABLE punto_de_venta ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE punto_de_venta FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON punto_de_venta TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "punto_de_venta",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("descripcion", sa.String(200), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Uninstantiated, like migration 0003: the class itself is the type, and calling
        # it is an untyped call mypy rejects under --strict.
        sa.Column(
            "numerador_por_tipo",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # ARCA numbers points from 1 to 99 999. Zero is not a point of sale, and the
        # ceiling is the field width in WSFEv1's request.
        sa.CheckConstraint("numero >= 1 AND numero <= 99999", name="ck_punto_numero"),
    )
    op.execute(INDICE_UNICO)
    op.execute(POLITICA_PUNTO)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.drop_table("punto_de_venta")
