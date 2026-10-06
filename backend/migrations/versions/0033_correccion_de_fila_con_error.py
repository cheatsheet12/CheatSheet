"""Una fila con error se puede corregir en el sistema (unidad correccion-de-filas-con-error).

HU-E3-05 y HU-E3-06 se pensaron para corregir en la planilla de origen y reprocesar. Esta unidad
agrega corregir ahí mismo, desde el detalle de la carga. Para eso `error_de_fila` necesita saber
cuáles de sus errores ya se arreglaron: `corregida_en`, un `timestamptz` **nullable**.

**El error no se borra.** `0014` lo dejó escrito: un procesamiento es el registro de un import que
ya escribió en `master_data`, y «esta fila falló y se arregló el martes» es parte de ese registro.
Un error con `corregida_en` es historia y deja de contar como pendiente; los contadores del
procesamiento (`filas_error`, `filas_ok`) los mueve el dominio.

- **Sin backfill.** Todos los errores existentes quedan pendientes (`NULL`).
- **Sin política nueva.** La RLS y el `GRANT SELECT, INSERT, UPDATE` de `0014` ya cubren la columna.
- **Reversible.** `downgrade` borra la columna.

**Número reservado.** Se renumera al integrar en `develop` si otra unidad tomó 0033, y su
`down_revision` se re-apunta a la cabeza de `develop`, para que quede una sola cabeza.

Revision ID: 0033
Revises: 0032
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
# Re-apuntar al integrar en `develop`: ver «Número reservado» en el docstring.
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE error_de_fila ADD COLUMN corregida_en timestamptz NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE error_de_fila DROP COLUMN IF EXISTS corregida_en")
