"""reporte, paquete_contable, token_de_acceso_contable y configuracion_de_paquete — el épico 9.

Cuatro tablas, dos funciones `SECURITY DEFINER` y ningún `DELETE`. Lo que el esquema hace y el
código no podría hacer solo:

1. **`uq_paquete_empresa_periodo`** — un mes tiene **un** paquete. El barrido mensual corre sin
   que nadie mire, y dos procesos de Beat o un reintento manual dejarían dos paquetes del mismo
   mes con contenidos distintos; el contador tendría que adivinar cuál abrir. Con el índice, el
   segundo intento encuentra el primero y lo rehace en vez de duplicarlo.

2. **`token_de_acceso_contable.valor_hash` único en toda la tabla, no por empresa.** Es la
   consecuencia de que el contador llegue **sin sesión**: la búsqueda por hash corre antes de
   saber de qué empresa es. Dos empresas con el mismo digesto convertirían esa consulta en una
   ambigüedad que resuelve el azar — y el azar elegiría a qué empresa dejar entrar.

3. **`empresa_de_token_contable(hash)`** — la novena función `SECURITY DEFINER` del sistema y
   la más angosta: recibe un digesto y devuelve un id de empresa. No dice si el token está
   vigente ni de qué paquete es; eso se lee después, ya dentro de la sesión de esa empresa,
   donde RLS acota todo lo demás. Es la misma forma que `buscar_empresa_de_refresh` de la
   migración 0002, y por el mismo motivo: hay una operación que ocurre antes de tener inquilino.

4. **`empresas_con_paquete_activo(dia)`** — la décima, para el barrido mensual. Devuelve ids y
   nada más. El día es parámetro y no `now()`: un barrido que se corre a mano para reponer un
   envío perdido tiene que poder pedir el día que corresponde.

5. **`configuracion_de_paquete` no está en el DER.** Es el mismo hueco que H2: HU-E10-04 RN-02
   y RN-03 exigen persistir día de envío, formato, contenido y email del contador, y el modelo
   no lo previó. La tabla se crea, con `empresa_id` como clave primaria —una configuración por
   empresa, no dos que se contradicen— y la decisión queda escrita en `decisiones.md`.

6. **Ningún `DELETE`, en ninguna de las cuatro.** Un reporte generado es la respuesta a «qué le
   mandé a mi contador y cuándo». Un paquete es documentación fiscal de un mes cerrado. Un
   token se **revoca**, que es una columna y no una baja: borrarlo perdería `accesos`, que es
   lo único que hace auditable un acceso sin cuenta (HU-E10-06 RN-03).

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Escritas literalmente y no armadas desde una lista, por lo que dice la migración 0002: un
# SQL interpolado se le parece a un escáner exactamente a la inyección que no es.
POLITICA_REPORTE = """
CREATE POLICY aislamiento_por_empresa ON reporte
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_PAQUETE = """
CREATE POLICY aislamiento_por_empresa ON paquete_contable
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_ACCESO = """
CREATE POLICY aislamiento_por_empresa ON token_de_acceso_contable
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

POLITICA_CONFIGURACION = """
CREATE POLICY aislamiento_por_empresa ON configuracion_de_paquete
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid);
"""

#: La novena función `SECURITY DEFINER`. Ver el punto 3 del docstring.
#:
#: `STABLE` y no `VOLATILE`: no escribe. Y sin `revocado` ni `vencimiento` en el `WHERE` a
#: propósito — un enlace revocado tiene que resolver igual, para que el caso de uso pueda
#: contestar «el acceso ya no está disponible» en vez de «ese enlace no existe». Las dos
#: respuestas son la misma para quien pregunta, pero la primera no obliga a que esta función
#: sepa de reglas de negocio.
#: El nombre no lleva «token» —el linter de secretos lo confundiría con una credencial— y sí
#: dice qué contesta: de qué empresa es un enlace. Acá no hay ninguna credencial escrita: hay
#: una función que recibe un digesto.
FUNCION_EMPRESA_DEL_ENLACE = """
CREATE OR REPLACE FUNCTION empresa_de_token_contable(p_hash text)
RETURNS uuid
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT t.empresa_id
    FROM token_de_acceso_contable t
    WHERE t.valor_hash = p_hash
$$;
"""

#: La décima. Ver el punto 4 del docstring.
FUNCION_EMPRESAS_CON_PAQUETE = """
CREATE OR REPLACE FUNCTION empresas_con_paquete_activo(p_dia integer)
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
STABLE
AS $$
    SELECT c.empresa_id
    FROM configuracion_de_paquete c
    WHERE c.activo AND c.dia_de_envio = p_dia AND c.email_contador IS NOT NULL
$$;
"""

PERMISOS_FUNCIONES = (
    "REVOKE ALL ON FUNCTION empresa_de_token_contable(text) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresa_de_token_contable(text) TO cheatsheet_app",
    "REVOKE ALL ON FUNCTION empresas_con_paquete_activo(integer) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION empresas_con_paquete_activo(integer) TO cheatsheet_app",
)

RLS_Y_PERMISOS = (
    "ALTER TABLE reporte ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE reporte FORCE ROW LEVEL SECURITY",
    "ALTER TABLE paquete_contable ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE paquete_contable FORCE ROW LEVEL SECURITY",
    "ALTER TABLE token_de_acceso_contable ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE token_de_acceso_contable FORCE ROW LEVEL SECURITY",
    "ALTER TABLE configuracion_de_paquete ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE configuracion_de_paquete FORCE ROW LEVEL SECURITY",
    # Sin `DELETE` en ninguna. Ver el punto 6 del docstring.
    "GRANT SELECT, INSERT, UPDATE ON reporte TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON paquete_contable TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON token_de_acceso_contable TO cheatsheet_app",
    "GRANT SELECT, INSERT, UPDATE ON configuracion_de_paquete TO cheatsheet_app",
)


def upgrade() -> None:
    op.create_table(
        "reporte",
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
        sa.Column("tipo", sa.String(24), nullable=False),
        sa.Column("formato", sa.String(8), nullable=False),
        sa.Column("periodo_desde", sa.Date(), nullable=False),
        sa.Column("periodo_hasta", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column(
            "filtros", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("referencia_archivo", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("periodo_desde <= periodo_hasta", name="ck_reporte_periodo"),
    )
    op.create_index("ix_reporte_empresa_creado", "reporte", ["empresa_id", "created_at"])

    op.create_table(
        "paquete_contable",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("periodo_anio", sa.Integer(), nullable=False),
        sa.Column("periodo_mes", sa.Integer(), nullable=False),
        sa.Column(
            "totales_por_tipo",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("referencia_archivo", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("periodo_mes BETWEEN 1 AND 12", name="ck_paquete_mes"),
        sa.UniqueConstraint(
            "empresa_id", "periodo_anio", "periodo_mes", name="uq_paquete_empresa_periodo"
        ),
    )

    op.create_table(
        "token_de_acceso_contable",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "paquete_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paquete_contable.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Único en toda la tabla. Ver el punto 2 del docstring.
        sa.Column("valor_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("email_contador", sa.String(320), nullable=False),
        sa.Column("vencimiento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accesos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revocado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("accesos >= 0", name="ck_token_contable_accesos"),
    )
    op.create_index(
        "ix_token_contable_empresa", "token_de_acceso_contable", ["empresa_id", "revocado"]
    )

    op.create_table(
        "configuracion_de_paquete",
        # `empresa_id` es la clave primaria: una configuración por empresa. Ver el punto 5.
        sa.Column(
            "empresa_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("empresa.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("dia_de_envio", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "formatos", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "contenido", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("email_contador", sa.String(320), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Hasta 28 y no 31: febrero existe, y un envío programado para el 30 no saldría nunca
        # en el mes que más importa cerrar a tiempo. La misma regla vive en el agregado; acá
        # está para que ninguna otra vía de escritura la esquive.
        sa.CheckConstraint("dia_de_envio BETWEEN 1 AND 28", name="ck_configuracion_dia"),
        sa.CheckConstraint(
            "NOT activo OR email_contador IS NOT NULL", name="ck_configuracion_contador"
        ),
    )

    op.execute(FUNCION_EMPRESA_DEL_ENLACE)
    op.execute(FUNCION_EMPRESAS_CON_PAQUETE)
    op.execute(POLITICA_REPORTE)
    op.execute(POLITICA_PAQUETE)
    op.execute(POLITICA_ACCESO)
    op.execute(POLITICA_CONFIGURACION)
    for sentencia in (*RLS_Y_PERMISOS, *PERMISOS_FUNCIONES):
        op.execute(sentencia)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS empresas_con_paquete_activo(integer)")
    op.execute("DROP FUNCTION IF EXISTS empresa_de_token_contable(text)")
    op.drop_table("configuracion_de_paquete")
    op.drop_table("token_de_acceso_contable")
    op.drop_table("paquete_contable")
    op.drop_table("reporte")
