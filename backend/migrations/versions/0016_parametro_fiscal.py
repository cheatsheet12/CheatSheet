"""parametro_fiscal — ARCA's catalogue, versioned by validity (HS-T4).

**This is the first business table in the system with no `empresa_id` and no Row-Level
Security policy**, and both absences are the design rather than an oversight. The list of
document types, VAT rates and document codes is ARCA's, and it is identical for every
company in Argentina. A copy per tenant would be the same rows repeated, and a bug in the
sync would produce companies whose fiscal reality disagreed with each other's.

`docs/architecture.md` already says so: «of the 34 tables, 25 carry `empresa_id` and a
policy; the 7 internal entities are protected through their parent; `empresa` is the tenant
itself and **`parametro_fiscal` is ARCA's global catalogue**».

**What protects it instead of RLS is the grant.** `cheatsheet_app` gets `SELECT` and nothing
else. Whoever writes here is the migration and the Beat sync, which run as the owner. An
application role that could write would be an application role that could give one company
a different VAT rate from everybody else's, which is exactly the failure RLS prevents
elsewhere and that this table prevents by never being writable from a request.

**The partial unique index is the aggregate's invariant, in the engine.** Two rows for the
same `(tipo, codigo)` with `fecha_hasta IS NULL` are two versions in force at once, and the
issuing code would pick whichever the planner returned first. `WHERE fecha_hasta IS NULL`
is what makes that impossible while still allowing any number of closed historical rows.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The aggregate's invariant, enforced by the engine. See the module docstring.
INDICE_UNA_VIGENTE = """
CREATE UNIQUE INDEX uq_parametro_vigente
    ON parametro_fiscal (tipo, codigo)
    WHERE fecha_hasta IS NULL;
"""

#: The query the issuing code runs on every document: this entry, on this date.
INDICE_CONSULTA = """
CREATE INDEX ix_parametro_tipo_codigo_desde
    ON parametro_fiscal (tipo, codigo, fecha_desde);
"""

#: `SELECT` and nothing else. No RLS, because there is nothing to isolate. See the
#: module docstring for why that is safe here and would not be anywhere else.
PERMISOS = ("GRANT SELECT ON parametro_fiscal TO cheatsheet_app",)


def upgrade() -> None:
    op.create_table(
        "parametro_fiscal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("codigo", sa.String(40), nullable=False),
        # Text, always. The rates become `Decimal` from this string, never through a
        # float (CLAUDE.md 3.5), and the other five catalogues are labels.
        sa.Column("valor", sa.String(200), nullable=False),
        sa.Column("fecha_desde", sa.Date(), nullable=False),
        # NULL means still in force. The partial unique index above is what keeps two
        # rows of the same entry from being NULL at the same time.
        sa.Column("fecha_hasta", sa.Date(), nullable=True),
        # Server default: the domain aggregate does not carry it -- what matters to the
        # business is `fecha_desde`, and this is bookkeeping about when we learned it.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "tipo IN ('TIPO_COMPROBANTE', 'ALICUOTA_IVA', 'CONDICION_IVA',"
            " 'TIPO_DOCUMENTO', 'MONEDA', 'UNIDAD_MEDIDA')",
            name="ck_parametro_tipo",
        ),
        sa.CheckConstraint(
            "fecha_hasta IS NULL OR fecha_hasta >= fecha_desde", name="ck_parametro_vigencia"
        ),
    )
    op.execute(INDICE_UNA_VIGENTE)
    op.execute(INDICE_CONSULTA)
    for sentencia in PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.drop_table("parametro_fiscal")
