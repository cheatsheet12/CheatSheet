"""comprobante and item_de_comprobante — the legal record (HU-E5-01, HU-E5-02, HU-E5-03).

The DER's two tables (BC6), unchanged, with Single Table Inheritance per ADR-010: one table,
a `tipo` discriminator, and the columns only some types use left nullable.

**No `DELETE` on either.** A document ARCA authorised is a legal record: it is reversed with
a credit note, which is another row, and removing it would orphan a CAE that still exists at
the AFIP. `item_de_comprobante` inherits the same rule -- deleting a line off an authorised
document would make our copy disagree with the one ARCA holds -- with one deliberate
exception the grant does allow, explained below.

**The unique index is on `(punto_de_venta_id, tipo, numero)`, not on `(empresa_id, numero)`.**
Numbering is per point of sale *and per type* (HU-E5-05 RN-02): factura A number 5 and
factura B number 5 coexist, and must. It is partial -- `WHERE numero IS NOT NULL` -- because
a draft has no number and two drafts are not a duplicate.

This index is the last line of defence for decision D14. The lock in `tomar_para_emitir` is
what makes the race impossible; this is what makes it impossible to be wrong about that
without the database noticing.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
POLITICA_COMPROBANTE = """
CREATE POLICY aislamiento_por_empresa ON comprobante
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: `item_de_comprobante` has no `empresa_id` of its own -- the DER does not give it one, and
#: adding one would be a second copy of the same fact that could drift. It is scoped through
#: its parent, which RLS already scopes.
POLITICA_ITEM = """
CREATE POLICY aislamiento_por_comprobante ON item_de_comprobante
    USING (EXISTS (
        SELECT 1 FROM comprobante c
        WHERE c.id = item_de_comprobante.comprobante_id
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM comprobante c
        WHERE c.id = item_de_comprobante.comprobante_id
    ));
"""

#: See the module docstring. Partial because a draft carries no number.
INDICE_NUMERO = """
CREATE UNIQUE INDEX uq_comprobante_punto_tipo_numero
    ON comprobante (punto_de_venta_id, tipo, numero)
    WHERE numero IS NOT NULL;
"""

#: A CAE only ever accompanies an authorised or reversed document. Written as a constraint
#: rather than trusted to the aggregate because it is the one fact a future bug could get
#: wrong in a way nobody notices until an inspection.
CHECK_CAE = """
ALTER TABLE comprobante ADD CONSTRAINT ck_comprobante_cae_con_estado CHECK (
    (cae_codigo IS NULL AND cae_fecha_vencimiento IS NULL)
    OR (cae_codigo IS NOT NULL AND cae_fecha_vencimiento IS NOT NULL
        AND estado IN ('AUTORIZADO', 'ANULADO'))
);
"""

#: A credit note has an origin; an invoice does not (HU-E5-04 RN-01). The conditional CHECK
#: is what ADR-010 says takes the place of a second table.
CHECK_ORIGEN = """
ALTER TABLE comprobante ADD CONSTRAINT ck_comprobante_origen_solo_nota CHECK (
    comprobante_origen_id IS NULL OR tipo LIKE 'NOTA_CREDITO%'
);
"""

#: The sixth `SECURITY DEFINER` function in the system, and the same shape as the five
#: before it: **it returns company ids and nothing else**. The reconciliation sweep of D17
#: has to know which companies have something in flight before it can open a per-company
#: session, and that question cannot be asked from inside RLS — a session scoped to one
#: company would answer only about that company, and the sweep would quietly settle one
#: tenant's documents forever.
#:
#: `STABLE`, no arguments, no way to ask about a particular company, and a fixed
#: `search_path`. A caller learns that some company has a document in flight; it learns
#: nothing about the document.
FUNCION_EN_VUELO = """
CREATE OR REPLACE FUNCTION empresas_con_comprobantes_en_vuelo()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT c.empresa_id
    FROM comprobante c
    WHERE c.estado = 'ENVIADO_A_ARCA'
$$;
"""

PERMISOS_FUNCION = (
    "REVOKE ALL ON FUNCTION empresas_con_comprobantes_en_vuelo() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_comprobantes_en_vuelo() TO cheatsheet_app",
)

#: No `DELETE` on `comprobante`. **`item_de_comprobante` does grant it**, and the reason is
#: narrow: the repository rewrites the lines when a draft is edited, and the aggregate
#: refuses to touch them once the document leaves `VALIDADO`. The database allows what the
#: domain has already made unreachable for an issued document.
RLS_Y_PERMISOS = (
    "ALTER TABLE comprobante ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE comprobante FORCE ROW LEVEL SECURITY",
    "ALTER TABLE item_de_comprobante ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE item_de_comprobante FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON comprobante TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON item_de_comprobante TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "comprobante",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cliente.id"),
            nullable=False,
        ),
        sa.Column(
            "punto_de_venta_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("punto_de_venta.id"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=True),
        sa.Column("receptor_nombre", sa.String(200), nullable=False),
        sa.Column("receptor_cuit", sa.String(11), nullable=False),
        sa.Column("receptor_condicion_iva", sa.String(30), nullable=False),
        sa.Column("receptor_domicilio", sa.String(300), nullable=True),
        sa.Column("emisor_condicion_iva", sa.String(30), nullable=False),
        sa.Column("cae_codigo", sa.String(20), nullable=True),
        sa.Column("cae_fecha_vencimiento", sa.Date(), nullable=True),
        sa.Column("motivo_de_rechazo", sa.String(500), nullable=True),
        # NUMERIC with an explicit scale, never FLOAT (CLAUDE.md §3.5). Without the scale
        # the column would store the third decimal that D15 rounds away, and the row would
        # disagree with the document ARCA authorised.
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_iva", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("saldo_pendiente", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "comprobante_origen_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comprobante.id"),
            nullable=True,
        ),
        # No foreign key on purpose (DER hallazgo H4): `turno` belongs to another bounded
        # context, and a join across that boundary is what rule R3 forbids.
        sa.Column("turno_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("fecha_emision", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("numero IS NULL OR numero > 0", name="ck_comprobante_numero"),
        sa.CheckConstraint("total >= 0 AND subtotal >= 0", name="ck_comprobante_montos"),
    )
    op.create_index("ix_comprobante_empresa_fecha", "comprobante", ["empresa_id", "fecha_emision"])
    op.create_index("ix_comprobante_estado_fecha", "comprobante", ["estado", "fecha_emision"])

    op.create_table(
        "item_de_comprobante",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "comprobante_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comprobante.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("cantidad", sa.Numeric(14, 4), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(14, 2), nullable=False),
        # Four decimals: `0.1050` has to survive the round trip.
        sa.Column("alicuota_iva", sa.Numeric(5, 4), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("cantidad > 0", name="ck_item_cantidad"),
        sa.CheckConstraint("precio_unitario > 0", name="ck_item_precio"),
    )
    op.create_index("ix_item_comprobante", "item_de_comprobante", ["comprobante_id"])

    op.execute(INDICE_NUMERO)
    op.execute(CHECK_CAE)
    op.execute(CHECK_ORIGEN)
    op.execute(POLITICA_COMPROBANTE)
    op.execute(POLITICA_ITEM)
    op.execute(FUNCION_EN_VUELO)
    for sentencia in (*RLS_Y_PERMISOS, *PERMISOS_FUNCION):
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_comprobantes_en_vuelo()")
    op.drop_table("item_de_comprobante")
    op.drop_table("comprobante")
