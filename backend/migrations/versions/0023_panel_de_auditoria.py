"""notificacion, solicitud_de_soporte y registro_de_auditoria.detalle — el épico 10.

Dos tablas y una columna. Lo que el esquema hace y el código no podría hacer solo:

1. **`registro_de_auditoria.detalle jsonb`, nullable y sin `server_default`.** Es lo que
   HU-E12-02 RN-01 y RN-02 piden guardar —los datos de entrada y lo que contestó un servicio
   externo— y llega sobre una tabla que **ya tiene filas y no se puede reescribir**: HS-T5
   RN-03 le niega el `UPDATE` al rol de la aplicación, que es el punto de esa tabla. Una
   columna nullable se agrega sin tocar una sola fila; una con default no.

   Lo que el timeline de RN-01 necesita, en cambio, **no** es una columna: cada paso ya escribe
   su propia fila nombrando la misma `entidad_afectada`, así que el timeline se lee ordenando
   esas filas. Una segunda tabla de pasos sería escribir dos veces lo mismo y tener dos
   versiones de qué pasó, que es lo único que una bitácora no puede permitirse.

2. **`notificacion` lleva `destinatario_id`, y el índice va por ahí.** RLS acota a la empresa,
   y adentro de una empresa hay varias personas: la consulta que hace la pantalla es «lo mío,
   lo no leído primero», y sin ese índice son dos escaneos por carga del panel.

3. **`solicitud_de_soporte` no tiene `DELETE`, y `notificacion` tampoco.** Un pedido de ayuda
   borrado es un pedido que nadie puede demostrar que hizo; una notificación leída es la
   evidencia de que el sistema avisó. Lo que se hace con una notificación molesta es marcarla
   leída, que es lo que HU-E11-03 RN-03 pide.

4. **La FK de `notificacion.plantilla_id` se declara acá y no en el ORM.** La tabla
   `plantilla_de_notificacion` es de `conversational`, y el modelo de `observability` no la
   arrastra (regla R3): quien decide si la restricción existe es la migración.

Revision ID: 0023
Revises: 0022
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escritas literalmente y no armadas desde una lista, por lo que dice la migración 0002: un
# SQL interpolado se le parece a un escáner exactamente a la inyección que no es.
POLITICA_NOTIFICACION = """
CREATE POLICY aislamiento_por_empresa ON notificacion
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_SOLICITUD = """
CREATE POLICY aislamiento_por_empresa ON solicitud_de_soporte
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: La columna del detalle. Ver el punto 1 del docstring.
COLUMNA_DETALLE = "ALTER TABLE registro_de_auditoria ADD COLUMN detalle jsonb"

RLS_Y_PERMISOS = (
    "ALTER TABLE notificacion ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE notificacion FORCE ROW LEVEL SECURITY",
    "ALTER TABLE solicitud_de_soporte ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE solicitud_de_soporte FORCE ROW LEVEL SECURITY",
    # Sin `DELETE` en ninguna de las dos. Ver el punto 3 del docstring.
    "GRANT SELECT, INSERT, UPDATE ON notificacion TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON solicitud_de_soporte TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "notificacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "destinatario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # La FK vive acá y no en el ORM. Ver el punto 4 del docstring.
        sa.Column(
            "plantilla_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plantilla_de_notificacion.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("categoria", sa.String(30), nullable=False),
        sa.Column("severidad", sa.String(10), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("leida", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_notificacion_destinatario",
        "notificacion",
        ["destinatario_id", "leida", "created_at"],
    )

    op.create_table(
        "solicitud_de_soporte",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id"),
            nullable=False,
        ),
        sa.Column("asunto", sa.String(200), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("prioridad", sa.String(10), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_solicitud_empresa_estado", "solicitud_de_soporte", ["empresa_id", "estado"])

    op.execute(COLUMNA_DETALLE)
    op.execute(POLITICA_NOTIFICACION)
    op.execute(POLITICA_SOLICITUD)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("ALTER TABLE registro_de_auditoria DROP COLUMN IF EXISTS detalle")
    op.drop_table("solicitud_de_soporte")
    op.drop_table("notificacion")
