"""regla_de_negocio, cobro y recordatorio — el épico 6 entero en una migración.

Tres tablas juntas y no tres migraciones, porque **`cobro` no significa nada sin la regla que
despacha sus recordatorios ni sin la tabla que los registra**: separarlas daría tres pasos de
los que sólo el tercero deja el sistema en un estado usable, y una migración que hay que
aplicar en bloque es más honesta declarándolo.

Cuatro cosas del esquema hacen trabajo que el código no puede hacer solo:

1. **`uq_cobro_mp_payment_id`** — índice único parcial sobre `(empresa_id, mp_payment_id)`.
   Es la decisión **D20** hecha esquema: MercadoPago reintenta un webhook durante horas y
   manda la misma notificación varias veces por diseño. Una clave en Redis protege durante su
   TTL; esto protege siempre, sobrevive a un `FLUSHALL` y se verifica con una consulta. Es
   parcial porque un cobro sin pagar no tiene `mp_payment_id` y dos cobros sin pagar no son
   un duplicado.

2. **`uq_recordatorio_cobro_paso`** — un cobro no recibe dos veces el mismo paso de su cadena
   (HS-T3 RN-05, decisión **D25**). Lo mismo de antes: la idempotencia del barrido vive acá y
   no en una ventana de tiempo.

3. **`ck_cobro_monto`** — el monto es mayor a cero (HU-E6-03 RN-02), y `monto_reembolsado` no
   lo supera (HU-E6-05 RN-02). El agregado ya lo impone; esto es lo que un bug futuro no puede
   saltear.

4. **Sin `DELETE` en ninguna de las tres.** Un cobro aprobado es plata que entró y un
   recordatorio enviado es un mensaje que un cliente recibió: los dos se cancelan o se
   reembolsan, no se borran. Una regla se desactiva (HU-E11-01 RN-04).

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escritas literalmente y no armadas desde una lista, por lo que dice la migración 0002: un
# SQL interpolado se le parece a un escáner exactamente a la inyección que no es.
POLITICA_REGLA = """
CREATE POLICY aislamiento_por_empresa ON regla_de_negocio
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_COBRO = """
CREATE POLICY aislamiento_por_empresa ON cobro
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: `recordatorio` no tiene `empresa_id` propio -- el DER no se lo da, y agregarlo sería una
#: segunda copia del mismo hecho que puede separarse. Se acota por su padre, que RLS ya acota.
POLITICA_RECORDATORIO = """
CREATE POLICY aislamiento_por_cobro ON recordatorio
    USING (EXISTS (SELECT 1 FROM cobro c WHERE c.id = recordatorio.cobro_id))
    WITH CHECK (EXISTS (SELECT 1 FROM cobro c WHERE c.id = recordatorio.cobro_id));
"""

#: Decisión D20. Ver el docstring del módulo.
INDICE_PAGO = """
CREATE UNIQUE INDEX uq_cobro_mp_payment_id
    ON cobro (empresa_id, mp_payment_id)
    WHERE mp_payment_id IS NOT NULL;
"""

#: Decisión D25. Un cobro no recibe dos veces el mismo paso.
INDICE_PASO = """
CREATE UNIQUE INDEX uq_recordatorio_cobro_paso
    ON recordatorio (cobro_id, paso);
"""

#: HU-E6-05 RN-02, en el esquema. El agregado ya lo impone; esto es lo que un bug futuro no
#: puede saltear, y devolver más de lo que entró es dinero que sale de la cuenta de otro.
CHECK_REEMBOLSO = """
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_reembolso CHECK (
    monto_reembolsado IS NULL OR (monto_reembolsado > 0 AND monto_reembolsado <= monto)
);
"""

#: La séptima función `SECURITY DEFINER` del sistema, y la misma forma que las seis
#: anteriores: **devuelve ids de empresa y nada más**. Los dos barridos del épico -- el de
#: vencimientos (D23) y el de recordatorios (HS-T3) -- necesitan saber qué empresas tienen
#: algo pendiente antes de poder abrir una sesión por empresa, y esa pregunta no se puede
#: hacer desde adentro de RLS.
FUNCION_COBROS_ABIERTOS = """
CREATE OR REPLACE FUNCTION empresas_con_cobros_abiertos()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT c.empresa_id
    FROM cobro c
    WHERE c.estado IN ('PENDIENTE', 'VENCIDO')
$$;
"""

PERMISOS_FUNCION = (
    "REVOKE ALL ON FUNCTION empresas_con_cobros_abiertos() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_cobros_abiertos() TO cheatsheet_app",
)

#: Sin `DELETE`. Ver el docstring del módulo.
RLS_Y_PERMISOS = (
    "ALTER TABLE regla_de_negocio ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE regla_de_negocio FORCE ROW LEVEL SECURITY",
    "ALTER TABLE cobro ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE cobro FORCE ROW LEVEL SECURITY",
    "ALTER TABLE recordatorio ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE recordatorio FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON regla_de_negocio TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON cobro TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON recordatorio TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "regla_de_negocio",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", sa.String(40), nullable=False),
        # Sin instanciar, como la migración 0003: la clase misma es el tipo, y llamarla es
        # una llamada sin tipar que mypy rechaza bajo --strict.
        sa.Column("configuracion", postgresql.JSONB, nullable=False),
        sa.Column("prioridad", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("prioridad >= 0", name="ck_regla_prioridad"),
    )
    op.create_index(
        "ix_regla_empresa_tipo", "regla_de_negocio", ["empresa_id", "tipo", "prioridad"]
    )

    op.create_table(
        "cobro",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cliente.id"),
            nullable=False,
        ),
        sa.Column(
            "comprobante_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("comprobante.id"),
            nullable=True,
        ),
        # Sin FK a propósito (hallazgo H4 del DER): `turno` es de otro bounded context, y un
        # join que cruce esa frontera es lo que la regla R3 prohíbe. Lo escribe el épico 7.
        sa.Column("turno_id", postgresql.UUID(as_uuid=True), nullable=True),
        # NUMERIC con escala explícita, nunca FLOAT (CLAUDE.md §3.5).
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("monto_reembolsado", sa.Numeric(14, 2), nullable=True),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("mp_preference_id", sa.String(120), nullable=True),
        sa.Column("mp_payment_id", sa.String(120), nullable=True),
        sa.Column("mp_url_pago", sa.String(500), nullable=True),
        #: Cuándo vence sin pagar. Es lo que el barrido de D23 compara para pasar a VENCIDO,
        #: y lo que la cadena de recordatorios usa como día cero.
        sa.Column("vence_el", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pagado_en", sa.DateTime(timezone=True), nullable=True),
        #: Decisión D27: el reembolso en vuelo es este campo y no un estado del enum.
        sa.Column("reembolso_solicitado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_de_cancelacion", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("monto > 0", name="ck_cobro_monto"),
    )
    # PAN-COB-01 lista por estado y por antigüedad, acotado a la empresa.
    op.create_index("ix_cobro_empresa_estado", "cobro", ["empresa_id", "estado", "vence_el"])
    # Los dos barridos preguntan exactamente esto: qué está abierto y desde cuándo.
    op.create_index("ix_cobro_estado_vence", "cobro", ["estado", "vence_el"])
    # HU-E6-06: los cobros de un comprobante, para recalcular su saldo.
    op.create_index("ix_cobro_comprobante", "cobro", ["comprobante_id"])

    op.create_table(
        "recordatorio",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cobro_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cobro.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("paso", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(20), nullable=False),
        sa.Column("enviado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estado_entrega", sa.String(20), nullable=True),
        sa.CheckConstraint("paso >= 1", name="ck_recordatorio_paso"),
    )

    op.execute(INDICE_PAGO)
    op.execute(INDICE_PASO)
    op.execute(CHECK_REEMBOLSO)
    op.execute(POLITICA_REGLA)
    op.execute(POLITICA_COBRO)
    op.execute(POLITICA_RECORDATORIO)
    op.execute(FUNCION_COBROS_ABIERTOS)
    for sentencia in (*RLS_Y_PERMISOS, *PERMISOS_FUNCION):
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_cobros_abiertos()")
    op.drop_table("recordatorio")
    op.drop_table("cobro")
    op.drop_table("regla_de_negocio")
