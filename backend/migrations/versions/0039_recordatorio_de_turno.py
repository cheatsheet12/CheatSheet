"""Appointment reminders: when a slot was fixed, and one row per reminder (`recordatorio-de-turno`).

Revision ID: 0039
Revises: 0038

1. **`turno.franja_asignada_en`** (`timestamptz NOT NULL`): when the *current* slot was fixed, at
   booking or at the last reschedule. `updated_at` cannot say it (it also moves on confirmation).
   A reminder whose moment `inicio - anticipacion` is earlier than this was already late when the
   slot was fixed, and is not sent. Backfill: `created_at`. A turno moved before this migration
   keeps its creation date, which can only make a reminder *more* likely, never skip an old one.
2. **`recordatorio_de_turno`**: one row per `(turno, anticipacion, franja_inicio)`. The unique
   index is the idempotency guarantee (the same idea as `uq_recordatorio_cobro_paso` for payments);
   `resultado IS NULL` means in flight or waiting for a retry. `ENABLE` + `FORCE` row level
   security by `empresa_id`; **no `DELETE` grant**: the row is the proof that a reminder was
   already handled, and deleting an `OMITIDO` row would make the next sweep send it.
3. **Partial indexes**: `ix_recordatorio_de_turno_pendiente` (only rows without `resultado`, a
   handful) and `ix_turno_abierto_inicio` (only open turnos), so the cross-company fan-out reads
   neither the whole reminder table nor the whole `turno` table.
4. **`empresas_con_turnos_por_recordar(hasta)`**: `SECURITY DEFINER`, `SET search_path`, ids only.
   Companies with an open turno starting in `(now(), hasta]`, plus companies with an unresolved
   reminder (so one whose turno was cancelled meanwhile is still visited and discarded).

**Retention.** `OMITIDO` and `DESCARTADO` rows are kept while the turno exists (`ON DELETE
CASCADE`); there is no purge here. At most three rows per turno and slot, read only through the
unique key.

**Reversible.** `downgrade` drops the function, the indexes, the table and the column.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Written literally, not built from a list: see migration 0002.
CREAR_TABLA = """
CREATE TABLE recordatorio_de_turno (
    id uuid PRIMARY KEY,
    empresa_id uuid NOT NULL REFERENCES empresa (id) ON DELETE CASCADE,
    turno_id uuid NOT NULL REFERENCES turno (id) ON DELETE CASCADE,
    anticipacion_min integer NOT NULL,
    franja_inicio timestamptz NOT NULL,
    resultado varchar(12) NULL,
    intentos integer NOT NULL DEFAULT 0,
    proximo_intento_en timestamptz NULL,
    ultimo_error varchar(60) NULL,
    procesado_en timestamptz NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_recordatorio_de_turno_anticipacion
        CHECK (anticipacion_min BETWEEN 60 AND 10080),
    CONSTRAINT ck_recordatorio_de_turno_resultado
        CHECK (resultado IN ('ENVIADO', 'FALLIDO', 'OMITIDO', 'DESCARTADO')),
    CONSTRAINT ck_recordatorio_de_turno_intentos CHECK (intentos >= 0)
)
"""

INDICES = (
    "CREATE UNIQUE INDEX uq_recordatorio_de_turno "
    "ON recordatorio_de_turno (turno_id, anticipacion_min, franja_inicio)",
    "CREATE INDEX ix_recordatorio_de_turno_pendiente "
    "ON recordatorio_de_turno (proximo_intento_en) WHERE resultado IS NULL",
    "CREATE INDEX ix_turno_abierto_inicio ON turno (franja_inicio) "
    "WHERE estado IN ('RESERVADO', 'CONFIRMADO')",
)

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON recordatorio_de_turno
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
"""

#: No `DELETE`: see the module docstring, point 2.
RLS_Y_PERMISOS = (
    "ALTER TABLE recordatorio_de_turno ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE recordatorio_de_turno FORCE ROW LEVEL SECURITY",
    "REVOKE ALL ON recordatorio_de_turno FROM cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON recordatorio_de_turno TO cheatsheet_app",
)

#: Ids only, like the ones before it. See the module docstring, point 4.
FUNCION_EMPRESAS_CON_TURNOS_POR_RECORDAR = """
CREATE OR REPLACE FUNCTION empresas_con_turnos_por_recordar(hasta timestamptz)
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT t.empresa_id
    FROM turno t
    WHERE t.estado IN ('RESERVADO', 'CONFIRMADO')
      AND t.franja_inicio > now() AND t.franja_inicio <= hasta
    UNION
    SELECT r.empresa_id
    FROM recordatorio_de_turno r
    WHERE r.resultado IS NULL
$$;
"""

PERMISOS_FUNCION = (
    "REVOKE ALL ON FUNCTION empresas_con_turnos_por_recordar(timestamptz) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_turnos_por_recordar(timestamptz) TO cheatsheet_app",
)


def upgrade() -> None:
    op.execute("ALTER TABLE turno ADD COLUMN franja_asignada_en timestamptz NULL")
    op.execute("UPDATE turno SET franja_asignada_en = created_at")
    op.execute("ALTER TABLE turno ALTER COLUMN franja_asignada_en SET NOT NULL")
    op.execute(CREAR_TABLA)
    for sentencia in INDICES:
        op.execute(sentencia)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(POLITICA)
    op.execute(FUNCION_EMPRESAS_CON_TURNOS_POR_RECORDAR)
    for sentencia in PERMISOS_FUNCION:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_turnos_por_recordar(timestamptz)")
    op.execute("DROP INDEX IF EXISTS ix_turno_abierto_inicio")
    op.execute("DROP TABLE IF EXISTS recordatorio_de_turno")
    op.execute("ALTER TABLE turno DROP COLUMN IF EXISTS franja_asignada_en")
