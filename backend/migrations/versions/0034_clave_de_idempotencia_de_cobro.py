"""La clave de idempotencia del pedido de un cobro (ADR-0013, unidad
`cobro-con-clave-de-idempotencia`).

`POST /cobros` crea un cobro y pide una preferencia a MercadoPago: repetirlo (reintento de red,
504 del BFF, dos pestañas) producía dos cobros y dos links pagables para la misma deuda. El cliente
manda ahora una clave (`X-Idempotency-Key`, un UUID) y el backend la guarda con el cobro.

- **`cobro.clave_idempotencia uuid NULL`**, sin default y **sin backfill**: los cobros existentes
  quedan en `NULL`, no se les inventa una clave.
- **Índice único parcial** `uq_cobro_clave_idempotencia ON cobro (empresa_id, clave_idempotencia)
  WHERE clave_idempotencia IS NOT NULL`: la misma clave en dos empresas son dos pedidos
  independientes. La política RLS que ya tiene la tabla cubre la columna nueva.
- **Reversible con pérdida declarada**: `downgrade` borra el índice y la columna, y con ellos las
  claves (un reintento posterior con una clave vieja crearía otro cobro).

Revision ID: 0034
Revises: 0033
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AGREGAR_COLUMNA = "ALTER TABLE cobro ADD COLUMN clave_idempotencia uuid NULL"

CREAR_INDICE = """
CREATE UNIQUE INDEX uq_cobro_clave_idempotencia ON cobro (empresa_id, clave_idempotencia)
    WHERE clave_idempotencia IS NOT NULL
"""


def upgrade() -> None:
    op.execute(AGREGAR_COLUMNA)
    op.execute(CREAR_INDICE)


def downgrade() -> None:
    op.execute("DROP INDEX uq_cobro_clave_idempotencia")
    op.execute("ALTER TABLE cobro DROP COLUMN clave_idempotencia")
