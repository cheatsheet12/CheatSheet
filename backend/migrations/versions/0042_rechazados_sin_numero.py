"""A rejected `Comprobante` holds no number (HU-E5-03).

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-10

ARCA records nothing under the number of a rejected document, so the point of sale hands
that number out again. Rejected rows kept it, and the next document drawing it collided on
`uq_comprobante_punto_tipo_numero`: the point of sale could never issue that type again.
Seen against ARCA homologación on 2026-10-10.

The aggregate now lets go of the number when it is rejected. This releases it from the rows
rejected before that. Data only; the downgrade cannot know which number each row held, and
none of them was ever a number ARCA recognised.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: `comprobante` FORCEs Row-Level Security, so even its owner would see no company's rows
#: and the UPDATE would match nothing -- silently -- wherever the migrating role does not
#: bypass RLS. Lifted for the one statement, inside the migration's transaction: if anything
#: fails, the FORCE is never lost.
LIBERAR_NUMEROS = (
    "ALTER TABLE comprobante NO FORCE ROW LEVEL SECURITY",
    "UPDATE comprobante SET numero = NULL WHERE estado = 'RECHAZADO'",
    "ALTER TABLE comprobante FORCE ROW LEVEL SECURITY",
)


def upgrade() -> None:
    for sentencia in LIBERAR_NUMEROS:
        op.execute(sentencia)


def downgrade() -> None:
    """Nothing to restore: the numbers released were never ARCA's."""
