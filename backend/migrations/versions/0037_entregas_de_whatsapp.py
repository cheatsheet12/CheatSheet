"""WhatsApp delivery callbacks (unit `entregas-de-whatsapp`, slice 1).

Revision ID: 0037
Revises: 0036

Columns and indexes only. **No backfill**: a reminder row without `enviado_en` is not a "stuck"
row to be fixed after the fact (the sweep inserts, sends and marks the row sent inside a single
savepoint), and rewriting it could resend a reminder that did go out.

1. **`recordatorio.externo_id`** (`varchar(160)`): the `wamid` Meta returned when it accepted the
   message. It is how a `statuses[]` callback finds its reminder. The table has no `empresa_id`
   (RLS goes through the parent `cobro`, 0019), and a `wamid` is globally unique, so the partial
   unique index is on the id alone.
2. **`recordatorio.ultimo_error`** (`varchar(60)`): why the send failed, as a Meta error code or a
   short class (`INCIERTO`, `SIN_CANAL`...). Never free text from Meta.
3. **`mensaje.motivo_de_falla`** (`varchar(60)`): the same, for agent and operator messages.

**Reversible.** `downgrade` drops the index and the columns.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE recordatorio ADD COLUMN externo_id varchar(160) NULL")
    op.execute("ALTER TABLE recordatorio ADD COLUMN ultimo_error varchar(60) NULL")
    op.execute(
        "CREATE UNIQUE INDEX uq_recordatorio_externo_id ON recordatorio (externo_id) "
        "WHERE externo_id IS NOT NULL AND externo_id <> ''"
    )
    op.execute("ALTER TABLE mensaje ADD COLUMN motivo_de_falla varchar(60) NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE mensaje DROP COLUMN IF EXISTS motivo_de_falla")
    op.execute("DROP INDEX IF EXISTS uq_recordatorio_externo_id")
    op.execute("ALTER TABLE recordatorio DROP COLUMN IF EXISTS ultimo_error")
    op.execute("ALTER TABLE recordatorio DROP COLUMN IF EXISTS externo_id")
