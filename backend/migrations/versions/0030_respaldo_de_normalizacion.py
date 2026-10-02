"""El respaldo de la corrección de datos existentes (HU-E4-05 RN-09).

Una tabla nueva, `respaldo_de_normalizacion`: guarda el valor original de cada fila que una
corrida de la corrección cambió, para poder restaurarla. La historia lo exige («se hace un
respaldo restaurable de los valores originales antes de aplicar») y el DER es anterior, así
que no la tiene: se documenta como hueco en `der.md`.

**Inmutable.** `cheatsheet_app` recibe `SELECT` e `INSERT` y nada más. La restauración lee
esta tabla y nunca la modifica: una corrida restaurada es idempotente porque el `UPDATE` de
la restauración solo toca las filas cuyo nombre sigue siendo el que la corrida escribió.

**RLS como el resto.** `ENABLE` y `FORCE` con la política `aislamiento_por_empresa` escrita
literal (la misma razón de la migración 0002: SQL interpolado se lee como la inyección que no
es). La tabla lleva su propio `empresa_id`.

**Revisión.** Esta unidad nació sobre `0025` mientras otras unidades sumaban `0026` a `0028`. Al
integrarla en `develop`, `down_revision` se re-apuntó a `0028` para que quede una sola cabeza.

Es reversible y no hace backfill: `downgrade` borra la tabla.

Revision ID: 0030
Revises: 0028
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON respaldo_de_normalizacion
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: `SELECT, INSERT` y no más: el respaldo es inmutable. Ver el docstring del módulo.
RLS_Y_PERMISOS = (
    "ALTER TABLE respaldo_de_normalizacion ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE respaldo_de_normalizacion FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT ON respaldo_de_normalizacion TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "respaldo_de_normalizacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("corrida_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entidad", sa.String(20), nullable=False),
        sa.Column("entidad_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campo", sa.String(30), nullable=False, server_default="nombre"),
        sa.Column("valor_original", sa.String(200), nullable=False),
        sa.Column("valor_normalizado", sa.String(200), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entidad IN ('CLIENTE', 'SERVICIO', 'CATEGORIA')",
            name="ck_respaldo_de_normalizacion_entidad",
        ),
    )
    op.create_index(
        "ix_respaldo_de_normalizacion_corrida",
        "respaldo_de_normalizacion",
        ["empresa_id", "corrida_id"],
    )
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA)


def downgrade() -> None:
    op.drop_index("ix_respaldo_de_normalizacion_corrida", table_name="respaldo_de_normalizacion")
    op.drop_table("respaldo_de_normalizacion")
