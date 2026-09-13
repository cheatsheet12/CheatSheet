"""conversacion, mensaje, escalamiento, faq y plantilla_de_notificacion — el épico 8.

Cinco tablas y una columna. Cuatro cosas del esquema hacen trabajo que el código no puede
hacer solo:

1. **`uq_mensaje_externo_id`** — índice único parcial sobre `(empresa_id, externo_id)`. Es la
   idempotencia del webhook de Meta, la misma forma que la decisión **D20** del épico 6 le dio
   a MercadoPago. Meta reintenta una notificación durante horas y manda la misma varias veces
   por diseño; sin esto, cada reintento sería un mensaje más en el hilo, otra llamada al modelo
   y —en el peor caso— otro turno reservado. Es parcial porque un mensaje que escribimos
   nosotros antes de que Meta lo acepte no tiene id externo, y dos de ésos no son un duplicado.

2. **`faq.embedding_vector vector(1536)`** — la columna de `pgvector` que hace posible la
   búsqueda por significado de HU-E8-03 RN-02. La extensión se instaló en la migración 0001
   para este momento. **Sin índice `ivfflat` todavía**: ese índice necesita datos para elegir
   sus listas, y construirlo sobre una tabla vacía produce un plan peor que el escaneo
   secuencial. Con las decenas de FAQ que tiene una PyME, el escaneo es lo correcto; está
   anotado en los pendientes.

3. **`registro_de_auditoria.iniciador`** — la otra mitad del hueco H2 del DER. La migración
   0001 ya agregó `modulo` porque HS-T5 RN-02 lo exige; la misma regla nombra el iniciador, y
   HS-T2 RN-05 pide que lo del agente quede marcado como IA. Llega con `server_default` porque
   la tabla ya tiene filas y **no se puede reescribir**: HS-T5 RN-03 le niega el `UPDATE` al
   rol de la aplicación, que es justamente el punto de esa tabla.

4. **Sin `DELETE` en cuatro de las cinco.** Una conversación con un cliente es el registro de
   lo que se le dijo; un mensaje enviado es un mensaje que alguien recibió; un escalamiento
   cerrado es un caso atendido. **`faq` sí lo tiene**, y es la única baja real del sistema:
   HU-E9-04 RN-03 pide que una FAQ eliminada deje de estar disponible de inmediato, y no hay
   nada que auditar en una pregunta que ya no se hace.

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escritas literalmente y no armadas desde una lista, por lo que dice la migración 0002: un
# SQL interpolado se le parece a un escáner exactamente a la inyección que no es.
POLITICA_CONVERSACION = """
CREATE POLICY aislamiento_por_empresa ON conversacion
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_MENSAJE = """
CREATE POLICY aislamiento_por_empresa ON mensaje
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_ESCALAMIENTO = """
CREATE POLICY aislamiento_por_empresa ON escalamiento
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_FAQ = """
CREATE POLICY aislamiento_por_empresa ON faq
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_PLANTILLA = """
CREATE POLICY aislamiento_por_empresa ON plantilla_de_notificacion
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: La idempotencia del webhook de Meta. Ver el docstring del módulo.
INDICE_MENSAJE_EXTERNO = """
CREATE UNIQUE INDEX uq_mensaje_externo_id
    ON mensaje (empresa_id, externo_id)
    WHERE externo_id IS NOT NULL AND externo_id <> '';
"""

#: Un código de plantilla por empresa. Sin esto, `ListarPlantillas` podría sembrar dos veces la
#: misma si dos pestañas la abren a la vez, y `buscar_por_codigo` devolvería cualquiera de las
#: dos — que es la clase de bug que se manifiesta como «edité el texto y no cambió».
INDICE_PLANTILLA_CODIGO = """
CREATE UNIQUE INDEX uq_plantilla_empresa_codigo
    ON plantilla_de_notificacion (empresa_id, codigo);
"""

#: La columna `vector`. Fuera de `create_table` porque el tipo lo provee la extensión y
#: SQLAlchemy no lo conoce sin la dependencia de Python, que este repositorio no agregó.
COLUMNA_VECTOR = "ALTER TABLE faq ADD COLUMN embedding_vector vector(1536)"

#: La otra mitad del hueco H2. Ver el docstring del módulo.
COLUMNA_INICIADOR = (
    "ALTER TABLE registro_de_auditoria ADD COLUMN iniciador varchar(20) NOT NULL DEFAULT 'sistema'"
)

#: La octava función `SECURITY DEFINER` del sistema, y la misma forma que las siete
#: anteriores: **devuelve ids de empresa y nada más**. El barrido que reindexa las FAQ necesita
#: saber qué empresas tienen algo pendiente antes de poder abrir una sesión por empresa, y esa
#: pregunta no se puede hacer desde adentro de RLS.
FUNCION_FAQS_PENDIENTES = """
CREATE OR REPLACE FUNCTION empresas_con_faqs_pendientes()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT DISTINCT f.empresa_id
    FROM faq f
    WHERE f.embedding_obsoleto
$$;
"""

PERMISOS_FUNCION = (
    "REVOKE ALL ON FUNCTION empresas_con_faqs_pendientes() FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_faqs_pendientes() TO cheatsheet_app",
)

RLS_Y_PERMISOS = (
    "ALTER TABLE conversacion ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE conversacion FORCE ROW LEVEL SECURITY",
    "ALTER TABLE mensaje ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE mensaje FORCE ROW LEVEL SECURITY",
    "ALTER TABLE escalamiento ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE escalamiento FORCE ROW LEVEL SECURITY",
    "ALTER TABLE faq ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE faq FORCE ROW LEVEL SECURITY",
    "ALTER TABLE plantilla_de_notificacion ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE plantilla_de_notificacion FORCE ROW LEVEL SECURITY",
    "GRANT SELECT, INSERT, UPDATE ON conversacion TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON mensaje TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON escalamiento TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON plantilla_de_notificacion TO cheatsheet_app",
    # `faq` es la única con DELETE. Ver el docstring del módulo.
    "GRANT SELECT, INSERT, UPDATE, DELETE ON faq TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "conversacion",
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
        sa.Column("estado", sa.String(20), nullable=False),
        # Intentos seguidos sin entender, y su tope. Ver `Conversacion`.
        sa.Column("contador", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ventana_maximo", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("ultimo_mensaje_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ventana_maximo >= 1", name="ck_conversacion_ventana"),
    )
    op.create_index("ix_conversacion_cliente_estado", "conversacion", ["cliente_id", "estado"])
    op.create_index(
        "ix_conversacion_empresa_actividad", "conversacion", ["empresa_id", "ultimo_mensaje_en"]
    )

    op.create_table(
        "mensaje",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversacion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversacion.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direccion", sa.String(12), nullable=False),
        sa.Column("tipo_contenido", sa.String(12), nullable=False),
        # Texto siempre, también para un audio: lo que se guarda es la transcripción, y el
        # audio no se persiste (HS-T7 RN-03). No hay columna que lo referencie.
        sa.Column("contenido", sa.Text(), nullable=True),
        sa.Column("intencion", sa.String(20), nullable=True),
        sa.Column("estado_entrega", sa.String(20), nullable=True),
        sa.Column("origen", sa.String(12), nullable=True),
        sa.Column("externo_id", sa.String(160), nullable=True),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mensaje_hilo_momento", "mensaje", ["conversacion_id", "momento"])

    op.create_table(
        "escalamiento",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversacion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversacion.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_asignado_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column("motivo", sa.String(300), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_escalamiento_hilo_estado", "escalamiento", ["conversacion_id", "estado"])
    op.create_index("ix_escalamiento_empresa_estado", "escalamiento", ["empresa_id", "estado"])

    op.create_table(
        "faq",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "categoria_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categoria_empresa.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pregunta", sa.Text(), nullable=False),
        sa.Column("respuesta", sa.Text(), nullable=False),
        sa.Column("embedding_modelo_version", sa.String(80), nullable=True),
        sa.Column(
            "embedding_obsoleto", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("usos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("usos >= 0", name="ck_faq_usos"),
    )
    op.create_index("ix_faq_empresa_obsoleto", "faq", ["empresa_id", "embedding_obsoleto"])
    op.execute(COLUMNA_VECTOR)

    op.create_table(
        "plantilla_de_notificacion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("codigo", sa.String(60), nullable=False),
        sa.Column("idioma", sa.String(10), nullable=False),
        sa.Column("canal", sa.String(20), nullable=False),
        sa.Column("cuerpo", sa.Text(), nullable=False),
        sa.Column("estado_aprobacion_meta", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_plantilla_empresa_codigo", "plantilla_de_notificacion", ["empresa_id", "codigo"]
    )

    op.execute(COLUMNA_INICIADOR)
    op.execute(FUNCION_FAQS_PENDIENTES)
    op.execute(INDICE_MENSAJE_EXTERNO)
    op.execute(INDICE_PLANTILLA_CODIGO)
    op.execute(POLITICA_CONVERSACION)
    op.execute(POLITICA_MENSAJE)
    op.execute(POLITICA_ESCALAMIENTO)
    op.execute(POLITICA_FAQ)
    op.execute(POLITICA_PLANTILLA)
    for sentencia in (*RLS_Y_PERMISOS, *PERMISOS_FUNCION):
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_faqs_pendientes()")
    op.execute("ALTER TABLE registro_de_auditoria DROP COLUMN IF EXISTS iniciador")
    op.drop_table("plantilla_de_notificacion")
    op.drop_table("faq")
    op.drop_table("escalamiento")
    op.drop_table("mensaje")
    op.drop_table("conversacion")
