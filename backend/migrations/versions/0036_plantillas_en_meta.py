"""WhatsApp templates in Meta (unit `plantillas-de-whatsapp-en-meta`).

Revision ID: 0036
Revises: 0035

Three things, all of one unit:

1. **Seven columns on `plantilla_de_notificacion`** that record what Meta knows about each
   template: its name there, its id, the rejection reason and detail, the category Meta
   assigned, when it was sent and when the last state was applied. A partial unique index on
   `(empresa_id, meta_plantilla_id)` keeps one Meta template to one row of ours.

2. **Backfill.** `nombre_en_meta = codigo` for WhatsApp rows. `PENDIENTE` becomes `SIN_ENVIAR`
   for WhatsApp rows: nobody ever sent them to Meta, so "pending" was false. And the two factory
   texts that ended in a variable (Meta rejects those) are replaced **only** in rows whose body
   is exactly the old factory text: one an administrator edited is left alone, and the screen
   will show Meta's reason.

3. **Two `SECURITY DEFINER` functions**, in the shape of 0005 and 0007, because Beat and the
   template webhook run with no company (`app.current_empresa` unset) and RLS shows them nothing:
   `empresas_con_whatsapp_conectado()` feeds the reconciliation fan-out, and
   `empresa_de_la_cuenta_de_whatsapp(text)` resolves the company that owns a WABA id. Both return
   **company ids and nothing else**. A **unique** partial expression index on `parametros->>'waba_id'`
   serves the second and keeps one WABA to one empresa.

**Reversible, with declared losses.** `downgrade` drops the functions, the indexes and the
columns, and maps the states the old code cannot read (`SIN_ENVIAR`, `PAUSADA`, `DESHABILITADA`)
back to `PENDIENTE`. The text backfill is **not** reverted: the new factory text is valid for
the old code too.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNAS = (
    "ALTER TABLE plantilla_de_notificacion ADD COLUMN nombre_en_meta varchar(512) NULL",
    "ALTER TABLE plantilla_de_notificacion ADD COLUMN meta_plantilla_id varchar(64) NULL",
    "ALTER TABLE plantilla_de_notificacion ADD COLUMN motivo_meta varchar(40) NULL",
    "ALTER TABLE plantilla_de_notificacion ADD COLUMN detalle_meta varchar(500) NULL",
    "ALTER TABLE plantilla_de_notificacion ADD COLUMN categoria_en_meta varchar(20) NULL",
    "ALTER TABLE plantilla_de_notificacion ADD COLUMN enviada_a_meta_en timestamptz NULL",
    "ALTER TABLE plantilla_de_notificacion ADD COLUMN estado_meta_en timestamptz NULL",
)

INDICE_META_ID = """
CREATE UNIQUE INDEX uq_plantilla_meta_id ON plantilla_de_notificacion (empresa_id, meta_plantilla_id)
    WHERE meta_plantilla_id IS NOT NULL
"""

# **Unique**: the webhook resolves the empresa from the WABA, so two empresas sharing one
# would let the second hijack or block the first one's template events. The write path turns
# the violation into a 409 (`CuentaDeWhatsAppEnUso`). Empty ids do not count as an account.
# If a database already holds two empresas on one WABA, the upgrade fails on purpose: the
# duplicate has to be resolved by a person, not silently picked by a migration.
INDICE_WABA = """
CREATE UNIQUE INDEX uq_integracion_waba ON configuracion_de_integracion ((parametros->>'waba_id'))
    WHERE sistema = 'WHATSAPP' AND COALESCE(parametros->>'waba_id', '') <> ''
"""

BACKFILL_NOMBRE = (
    "UPDATE plantilla_de_notificacion SET nombre_en_meta = codigo WHERE canal = 'WHATSAPP'"
)

BACKFILL_ESTADO = """
UPDATE plantilla_de_notificacion SET estado_aprobacion_meta = 'SIN_ENVIAR'
    WHERE canal = 'WHATSAPP' AND estado_aprobacion_meta = 'PENDIENTE'
"""

# The old factory texts end in `{{link}}`, which Meta rejects; the new ones end in " Gracias.".
# Matched by exact equality so an edited body is never touched.
TEXTO_VIEJO_RECORDATORIO = (
    "Hola {{nombre}}, te recordamos el pago de {{concepto}} por $ {{monto}}. "
    "Podés pagarlo acá: {{link}}"
)
TEXTO_NUEVO_RECORDATORIO = TEXTO_VIEJO_RECORDATORIO + " Gracias."
TEXTO_VIEJO_COBRO = (
    "Hola {{nombre}}, te dejamos el link para pagar {{concepto}} por $ {{monto}}: {{link}}"
)
TEXTO_NUEVO_COBRO = TEXTO_VIEJO_COBRO + " Gracias."

BACKFILL_TEXTO = """
UPDATE plantilla_de_notificacion SET cuerpo = :nuevo
    WHERE codigo = :codigo AND cuerpo = :viejo
"""

FUNCION_EMPRESAS = """
CREATE OR REPLACE FUNCTION empresas_con_whatsapp_conectado()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT c.empresa_id
    FROM configuracion_de_integracion c
    WHERE c.sistema = 'WHATSAPP'
      AND c.estado IN ('CONECTADO', 'ATENCION')
      AND COALESCE(c.parametros->>'waba_id', '') <> ''
$$;
"""

FUNCION_POR_WABA = """
CREATE OR REPLACE FUNCTION empresa_de_la_cuenta_de_whatsapp(p_waba_id text)
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT c.empresa_id
    FROM configuracion_de_integracion c
    WHERE c.sistema = 'WHATSAPP'
      AND c.parametros->>'waba_id' = p_waba_id
$$;
"""

# Written out literally rather than built from a list, for the reason migration 0002
# states: interpolated SQL reads to a scanner exactly like the injection it is not.
PERMISOS = (
    "REVOKE ALL ON FUNCTION empresas_con_whatsapp_conectado() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_whatsapp_conectado() TO cheatsheet_app",
    "REVOKE ALL ON FUNCTION empresa_de_la_cuenta_de_whatsapp(text) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresa_de_la_cuenta_de_whatsapp(text) TO cheatsheet_app",
)


BAJAS = (
    "ALTER TABLE plantilla_de_notificacion DROP COLUMN estado_meta_en",
    "ALTER TABLE plantilla_de_notificacion DROP COLUMN enviada_a_meta_en",
    "ALTER TABLE plantilla_de_notificacion DROP COLUMN categoria_en_meta",
    "ALTER TABLE plantilla_de_notificacion DROP COLUMN detalle_meta",
    "ALTER TABLE plantilla_de_notificacion DROP COLUMN motivo_meta",
    "ALTER TABLE plantilla_de_notificacion DROP COLUMN meta_plantilla_id",
    "ALTER TABLE plantilla_de_notificacion DROP COLUMN nombre_en_meta",
)


def upgrade() -> None:
    for sentencia in COLUMNAS:
        op.execute(sentencia)
    op.execute(INDICE_META_ID)
    op.execute(INDICE_WABA)
    op.execute(BACKFILL_NOMBRE)
    op.execute(BACKFILL_ESTADO)
    conexion = op.get_bind()
    for codigo, viejo, nuevo in (
        ("recordatorio_de_cobro", TEXTO_VIEJO_RECORDATORIO, TEXTO_NUEVO_RECORDATORIO),
        ("cobro_generado", TEXTO_VIEJO_COBRO, TEXTO_NUEVO_COBRO),
    ):
        conexion.execute(text(BACKFILL_TEXTO), {"codigo": codigo, "viejo": viejo, "nuevo": nuevo})
    op.execute(FUNCION_EMPRESAS)
    op.execute(FUNCION_POR_WABA)
    for sentencia in PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresa_de_la_cuenta_de_whatsapp(text)")
    op.execute("DROP FUNCTION IF EXISTS empresas_con_whatsapp_conectado()")
    op.execute("DROP INDEX IF EXISTS uq_integracion_waba")
    op.execute("DROP INDEX IF EXISTS uq_plantilla_meta_id")
    # The old code only knows PENDIENTE, APROBADA and RECHAZADA: it would fail reading the rest.
    op.execute(
        "UPDATE plantilla_de_notificacion SET estado_aprobacion_meta = 'PENDIENTE' "
        "WHERE estado_aprobacion_meta IN ('SIN_ENVIAR', 'PAUSADA', 'DESHABILITADA')"
    )
    for sentencia in BAJAS:
        op.execute(sentencia)
