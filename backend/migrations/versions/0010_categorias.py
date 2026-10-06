"""Categories and the classification of clients and services.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-01

Three tables, and the one that closes epic 3.

**Decision D8 of the epic 3 units map, made schema.** The DER puts a `categoria_id uuid FK`
inside `cliente` and `servicio`; HU-E4-04 RN-02 says an element «puede tener más de una
categoría asignada», and a single foreign key cannot hold more than one. The column was
never created — not in 0008, not in 0009 — so there is nothing to migrate away from.

**Decision D9: the `AMBOS` scope.** Stored in `aplica_a` as a plain `String`, like every
other enum in this schema.

**The unique index is functional.** RN-02 forbids two categories with the same name and
scope in one company, and `lower(nombre)` is what makes «VIP» and «vip» the same name —
which is what anybody reading the list would assume.

---

**`DELETE` is granted here, and it is not granted in 0008 or 0009. Read this before
assuming it is an oversight.**

`cliente` and `servicio` are referenced by `comprobante`, `cobro` and `turno` **without a
declared foreign key** (DER gap H4), so a physical delete would leave tax documents
pointing at nothing — and ADR-007 says what leaves the spreadsheet is marked absent, never
removed. Neither story asks to delete one.

`categoria_empresa` is the opposite on all three counts. HU-E4-03 asks in as many words to
«crear, editar y **eliminar** categorías». The only rows that reference it are the two link
tables below — inside this same context, with a real foreign key. And RN-03 states what
must survive the delete: «los clientes o servicios que la tenían asignada quedan sin esa
clasificación, **sin afectar el resto de sus datos**», which is exactly `ON DELETE CASCADE`
on an association that carries no business data of its own.

---

**The link tables carry their own `empresa_id`.** The alternative was an RLS policy with an
`EXISTS` against the parent table, and it would be the only policy with a subquery in the
system. A barrier that reads identically in all fourteen tables is a barrier that gets
reviewed properly.

**What the foreign keys cannot do.** A foreign key is verified with the table owner's
permissions, so it *sees* rows RLS hides: nothing here stops a row linking a client of one
company to a category of another. What stops it is the application, which reads the
category through the repository before assigning — and that `SELECT` does go through the
policy, so a foreign category is simply not found. There is an integration test on exactly
that path.

**No backfill.** The three tables are new; `downgrade` drops them in dependency order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
POLITICA_CATEGORIA = """
CREATE POLICY aislamiento_por_empresa ON categoria_empresa
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_CLIENTE_CATEGORIA = """
CREATE POLICY aislamiento_por_empresa ON cliente_categoria
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_SERVICIO_CATEGORIA = """
CREATE POLICY aislamiento_por_empresa ON servicio_categoria
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

INDICE_UNICO = """
CREATE UNIQUE INDEX uq_categoria_empresa_nombre_ambito
    ON categoria_empresa (empresa_id, lower(nombre), aplica_a);
"""

#: `DELETE` included, unlike 0008 and 0009. See the module docstring.
RLS_Y_PERMISOS = (
    "ALTER TABLE categoria_empresa ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE categoria_empresa FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON categoria_empresa TO cheatsheet_app",
    "ALTER TABLE cliente_categoria ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE cliente_categoria FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON cliente_categoria TO cheatsheet_app",
    "ALTER TABLE servicio_categoria ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE servicio_categoria FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON servicio_categoria TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "categoria_empresa",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nombre", sa.String(60), nullable=False),
        sa.Column("aplica_a", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_categoria_empresa", "categoria_empresa", ["empresa_id"])
    op.execute(INDICE_UNICO)

    _crear_enlace("cliente_categoria", "cliente_id", "cliente")
    _crear_enlace("servicio_categoria", "servicio_id", "servicio")

    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA_CATEGORIA)
    op.execute(POLITICA_CLIENTE_CATEGORIA)
    op.execute(POLITICA_SERVICIO_CATEGORIA)


def _crear_enlace(tabla: str, columna: str, padre: str) -> None:
    """The two link tables are the same table twice, so they are built the same way.

    The composite primary key is what makes assignment idempotent in the database and not
    only in the use case: clicking twice cannot produce two rows.
    """
    op.create_table(
        tabla,
        sa.Column(
            columna,
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{padre}.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "categoria_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categoria_empresa.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("empresa_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    # The reverse direction: «which elements carry this category», which is what the
    # listing filter of HU-E4-04 asks and what the delete cascade walks.
    op.create_index(f"ix_{tabla}_categoria", tabla, ["categoria_id"])


def downgrade() -> None:
    op.drop_index("ix_servicio_categoria_categoria", table_name="servicio_categoria")
    op.drop_table("servicio_categoria")
    op.drop_index("ix_cliente_categoria_categoria", table_name="cliente_categoria")
    op.drop_table("cliente_categoria")
    op.execute("DROP INDEX IF EXISTS uq_categoria_empresa_nombre_ambito")
    op.drop_index("ix_categoria_empresa", table_name="categoria_empresa")
    op.drop_table("categoria_empresa")
