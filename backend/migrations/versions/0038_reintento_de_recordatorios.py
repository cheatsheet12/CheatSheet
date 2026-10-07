"""Bounded retry of reminder sends (unit `entregas-de-whatsapp`, slice 2).

Revision ID: 0038
Revises: 0037

Columns and an index only. **No backfill**: rows that already exist keep `intentos = 0` and no
`proximo_intento_en`, which the sweep reads as "no send ever started" for an unsent row and is
irrelevant for a sent one.

1. **`recordatorio.intentos`** (`integer NOT NULL DEFAULT 0`): how many send attempts *started*.
   It is counted when an attempt begins, not when it ends: if the worker dies mid-send the attempt
   is already on record, and the sweep resolves that row as uncertain instead of sending it again.
2. **`recordatorio.proximo_intento_en`** (`timestamptz`): while a send is in flight, when that send
   is declared lost; while a transient failure waits, when the retry is due. Null otherwise.
3. **`ix_recordatorio_reintento`**: partial index on that column, so the retry query reads only
   the handful of rows that wait instead of scanning a table that grows with every reminder.

**Reversible.** `downgrade` drops the index and the columns.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE recordatorio ADD COLUMN intentos integer NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE recordatorio ADD COLUMN proximo_intento_en timestamptz NULL")
    op.execute(
        "ALTER TABLE recordatorio ADD CONSTRAINT ck_recordatorio_intentos CHECK (intentos >= 0)"
    )
    op.execute(
        "CREATE INDEX ix_recordatorio_reintento ON recordatorio (proximo_intento_en) "
        "WHERE proximo_intento_en IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_recordatorio_reintento")
    op.execute("ALTER TABLE recordatorio DROP CONSTRAINT IF EXISTS ck_recordatorio_intentos")
    op.execute("ALTER TABLE recordatorio DROP COLUMN IF EXISTS proximo_intento_en")
    op.execute("ALTER TABLE recordatorio DROP COLUMN IF EXISTS intentos")
