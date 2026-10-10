"""Acceptances of the terms and the privacy policy: the `aceptacion_legal` table (HU-E1-03, HU-E1-08).

Until now the only trace of accepting the terms was two columns of `empresa`
(`terminos_version`, `terminos_fecha_aceptacion`), overwritten by every acceptance, and nothing
at all for the privacy policy. This migration adds the evidence:

- **`aceptacion_legal`**: one **immutable** row per acceptance. `documento` is `TERMINOS` or
  `PRIVACIDAD`. **Only `SELECT` and `INSERT`** for the application: no `UPDATE` and no `DELETE`,
  like `registro_de_auditoria` (0001) and `reembolso` (0027). Both foreign keys are `RESTRICT`
  for the same reason: evidence does not disappear because somebody deleted what it points at.
- **RLS forced** with the usual `aislamiento_por_empresa` policy. The table carries
  `empresa_id` even though a privacy acceptance belongs to a user: each user belongs to one
  company, every read happens in a session scoped to it, and a table of identity without the
  barrier would be the only one.
- **Two partial unique indexes** are the guarantees: a user accepts a given version of the
  privacy policy once, and a company accepts a given version of the terms once.
- **`ck_aceptacion_legal_usuario`**: `usuario_id` may be empty only for `TERMINOS`, and only
  because of the backfill below.
- **No IP address** (decision D83): the audit log keeps it, this table does not.

**Backfill, without inventing data.** Each company with accepted terms gets one `TERMINOS` row
with that version and that date. It is attributed to the user of the `registrar_empresa` /
`registrar_empresa_con_google` event of `registro_de_auditoria` (`entidad_afectada =
'Empresa:<id>'`), the one who registered it; if there is no such event (or the event names no user),
`usuario_id` stays `NULL`, which says "unknown" instead of guessing. **No `PRIVACIDAD`
row is created**: nobody has accepted a policy that did not exist. `empresa` is not touched.
The migration role bypasses RLS (ADR-0005), which is what lets this read every company.

**Reversible with a declared loss.** `downgrade` drops the table and the history with it; the
`empresa` columns keep the last acceptance of the terms.

Revision ID: 0041
Revises: 0040
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Literal statements, not built from lists: see migration 0002 on interpolated SQL.
CREAR_TABLA = """
CREATE TABLE aceptacion_legal (
    id uuid PRIMARY KEY,
    empresa_id uuid NOT NULL REFERENCES empresa (id) ON DELETE RESTRICT,
    usuario_id uuid NULL REFERENCES usuario (id) ON DELETE RESTRICT,
    documento varchar(20) NOT NULL,
    version varchar(20) NOT NULL,
    fecha_aceptacion timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_aceptacion_legal_documento CHECK (documento IN ('TERMINOS', 'PRIVACIDAD')),
    CONSTRAINT ck_aceptacion_legal_usuario CHECK (usuario_id IS NOT NULL OR documento = 'TERMINOS')
)
"""

INDICES = """
CREATE INDEX ix_aceptacion_legal_empresa ON aceptacion_legal (empresa_id);
CREATE UNIQUE INDEX uq_aceptacion_legal_privacidad
    ON aceptacion_legal (usuario_id, version) WHERE documento = 'PRIVACIDAD';
CREATE UNIQUE INDEX uq_aceptacion_legal_terminos
    ON aceptacion_legal (empresa_id, version) WHERE documento = 'TERMINOS'
"""

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON aceptacion_legal
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
"""

#: Insert-only, like `registro_de_auditoria` (0001): everything is revoked, the minimum granted.
RLS_Y_PERMISOS = (
    "ALTER TABLE aceptacion_legal ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE aceptacion_legal FORCE ROW LEVEL SECURITY",
    "REVOKE ALL ON aceptacion_legal FROM cheatsheet_app",
    "GRANT SELECT, INSERT ON aceptacion_legal TO cheatsheet_app",
)

#: The earliest registration event of the company names who registered it. The join with
#: `usuario` (same company) keeps the attribution honest: the user must belong to that company.
BACKFILL_DE_TERMINOS = """
INSERT INTO aceptacion_legal (
    id, empresa_id, usuario_id, documento, version, fecha_aceptacion, created_at
)
SELECT
    gen_random_uuid(),
    e.id,
    (
        SELECT u.id
        FROM registro_de_auditoria a
        JOIN usuario u ON u.id = a.usuario_id AND u.empresa_id = e.id
        WHERE a.entidad_afectada = 'Empresa:' || e.id::text
          AND a.accion IN ('registrar_empresa', 'registrar_empresa_con_google')
        ORDER BY a."timestamp"
        LIMIT 1
    ),
    'TERMINOS',
    e.terminos_version,
    e.terminos_fecha_aceptacion,
    now()
FROM empresa e
WHERE e.terminos_version IS NOT NULL AND e.terminos_fecha_aceptacion IS NOT NULL
"""


def _ejecutar(sentencias: str) -> None:
    """One statement per call: the async driver does not take several in one."""
    for sentencia in sentencias.split(";\n"):
        op.execute(sentencia.strip())


def upgrade() -> None:
    op.execute(CREAR_TABLA)
    _ejecutar(INDICES)
    op.execute(POLITICA)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    op.execute(BACKFILL_DE_TERMINOS)


def downgrade() -> None:
    op.execute("DROP TABLE aceptacion_legal")
