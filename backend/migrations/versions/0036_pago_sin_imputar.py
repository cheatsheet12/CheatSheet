"""Pagos aprobados que no se pudieron imputar: la tabla `pago_sin_imputar` (unidad
`pagos-sin-cobro-asociado`).

Hasta ahora un pago aprobado de MercadoPago sin cobro asociado se perdía en un log `info`. Esta
migración crea el registro donde queda, con su monto en `numeric(14, 2)` y el motivo:

- **`pago_sin_imputar`**: una fila **inmutable** por pago. **Solo `SELECT` e `INSERT`** para la
  aplicación, sin `UPDATE` ni `DELETE`, como `reembolso` (0027) y `registro_de_auditoria` (0001):
  es un hecho, no se edita. RLS forzada y política `aislamiento_por_empresa`.
- **`uq_pago_sin_imputar_payment (empresa_id, mp_payment_id)`**: la idempotencia (D20). Dos
  notificaciones simultáneas del mismo pago dejan una fila.
- **`ck_pago_sin_imputar_motivo`** cierra los tres motivos y **`ck_pago_sin_imputar_cobro`** ata
  el cobro al motivo: `cobro_id` es nulo si y solo si el motivo es `SIN_COBRO`.
- `cobro_id` apunta a `cobro` **sin** `ON DELETE CASCADE`: un cobro con pagos sin imputar no se
  borra solo. No se guardan datos del pagador.

**Sin backfill.** Los pagos perdidos antes de esta unidad no se pueden reconstruir desde nuestros
datos. **Reversible con pérdida declarada**: `downgrade` borra la tabla y con ella los registros de
pagos sin imputar (los eventos de bitácora y las notificaciones quedan).

**Número provisorio.** Es el siguiente libre sobre la cabeza de esta rama (`0035`); si `develop`
tomó el número al integrar, se renumera y se re-apunta `down_revision` a la cabeza de `develop`.

Revision ID: 0036
Revises: 0035
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escritas literalmente y no armadas desde una lista, por lo que dice la migración 0002: un SQL
# interpolado se le parece a un escáner exactamente a la inyección que no es.
CREAR_TABLA = """
CREATE TABLE pago_sin_imputar (
    id uuid PRIMARY KEY,
    empresa_id uuid NOT NULL REFERENCES empresa (id) ON DELETE CASCADE,
    mp_payment_id varchar(120) NOT NULL,
    referencia_externa varchar(256) NULL,
    cobro_id uuid NULL REFERENCES cobro (id),
    motivo varchar(20) NOT NULL,
    monto numeric(14, 2) NULL,
    fecha_aprobacion timestamptz NULL,
    recibido_en timestamptz NOT NULL,
    CONSTRAINT ck_pago_sin_imputar_motivo CHECK (
        motivo IN ('SIN_COBRO', 'COBRO_YA_PAGADO', 'MONTO_DISTINTO')
    ),
    CONSTRAINT ck_pago_sin_imputar_cobro CHECK ((motivo = 'SIN_COBRO') = (cobro_id IS NULL))
)
"""

INDICES = (
    "CREATE UNIQUE INDEX uq_pago_sin_imputar_payment ON pago_sin_imputar (empresa_id, mp_payment_id)",
    "CREATE INDEX ix_pago_sin_imputar_cobro ON pago_sin_imputar (cobro_id)",
)

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON pago_sin_imputar
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
"""

#: Solo-inserción, como `reembolso` (0027): se revoca todo y se da lo mínimo.
RLS_Y_PERMISOS = (
    "ALTER TABLE pago_sin_imputar ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE pago_sin_imputar FORCE ROW LEVEL SECURITY",
    "REVOKE ALL ON pago_sin_imputar FROM cheatsheet_app",
    "GRANT SELECT, INSERT ON pago_sin_imputar TO cheatsheet_app",
)


def upgrade() -> None:
    op.execute(CREAR_TABLA)
    for indice in INDICES:
        op.execute(indice)
    op.execute(POLITICA)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP TABLE pago_sin_imputar")
