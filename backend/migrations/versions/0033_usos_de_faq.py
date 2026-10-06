"""Los usos de las FAQ como filas inmutables, y su línea de base (ADR-0012, unidad
`usos-de-faq-por-periodo`).

`faq.usos` era un entero sin fecha: no permitía hablar de «este mes», y el agente lo incrementaba
con una lectura-modificación-escritura de toda la fila (dos respuestas simultáneas perdían un
uso, y una respuesta que se cruzaba con una edición del administrador **le pisaba la edición**).

1. **`faq_uso`**: una fila por respuesta con FAQ que **salió** por WhatsApp. `mensaje_id` es único
   (un mensaje es a lo sumo un uso: el alta es idempotente) y `faq_id` es `ON DELETE SET NULL`,
   así que borrar una FAQ conserva sus filas y el total de la empresa no cambia hacia atrás.
2. **Solo inserción**, como `reembolso` (0027) y `registro_de_auditoria` (0001): RLS forzada con la
   política `aislamiento_por_empresa` y `GRANT SELECT, INSERT` únicamente. La acción `SET NULL` la
   ejecuta PostgreSQL con los permisos del dueño de la tabla (el rol de migraciones,
   `BYPASSRLS`, ADR-0005), no con los de la aplicación; lo verifica un test de integración.
3. **`faq.usos` pasa a `usos_anteriores`**: la línea de base congelada. Nadie la incrementa; suma
   al total y no a ningún mes. `editada_en` (última edición real del texto) y `seguimiento_desde`
   (desde cuándo hay eventos de esa FAQ) se agregan.

- **Backfill: no se inventa nada.** `usos_anteriores` conserva el contador viejo; `editada_en`
  queda `NULL` (`updated_at` también lo mueve el barrido de embeddings, así que no sirve);
  `seguimiento_desde` queda con el instante del despliegue para las FAQ existentes, y la escribe la
  aplicación para las nuevas (por eso el `DEFAULT` se quita después). `faq_uso` arranca vacía.
- **Reversible sin perder el total.** `downgrade` primero suma los eventos a la línea de base y
  después borra. Pérdida declarada: las fechas de los usos, y los usos de FAQ ya borradas.

Revision ID: 0033
Revises: 0032
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREAR_TABLA = """
CREATE TABLE faq_uso (
    id uuid PRIMARY KEY,
    empresa_id uuid NOT NULL REFERENCES empresa (id) ON DELETE CASCADE,
    faq_id uuid NULL REFERENCES faq (id) ON DELETE SET NULL,
    mensaje_id uuid NOT NULL REFERENCES mensaje (id),
    usado_en timestamptz NOT NULL,
    CONSTRAINT uq_faq_uso_mensaje UNIQUE (mensaje_id)
)
"""

#: `(empresa_id, faq_id, usado_en)` resuelve los conteos por FAQ con un recorrido de índice;
#: `(empresa_id, usado_en)` es el denominador de la participación (todas las FAQ, borradas
#: incluidas).
INDICES = """
CREATE INDEX ix_faq_uso_empresa_faq_usado ON faq_uso (empresa_id, faq_id, usado_en);
CREATE INDEX ix_faq_uso_empresa_usado ON faq_uso (empresa_id, usado_en)
"""

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON faq_uso
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
"""

#: Solo-inserción, como `reembolso` (0027): se revoca todo y se da lo mínimo.
RLS_Y_PERMISOS = (
    "ALTER TABLE faq_uso ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE faq_uso FORCE ROW LEVEL SECURITY",
    "REVOKE ALL ON faq_uso FROM cheatsheet_app",
    "GRANT SELECT, INSERT ON faq_uso TO cheatsheet_app",
)

#: `seguimiento_desde` nace con `DEFAULT now()` para completar las FAQ existentes y el default se
#: quita enseguida: de ahí en más lo escribe la aplicación.
AJUSTAR_FAQ = """
ALTER TABLE faq RENAME COLUMN usos TO usos_anteriores;
ALTER TABLE faq RENAME CONSTRAINT ck_faq_usos TO ck_faq_usos_anteriores;
ALTER TABLE faq ADD COLUMN editada_en timestamptz NULL;
ALTER TABLE faq ADD COLUMN seguimiento_desde timestamptz NOT NULL DEFAULT now();
ALTER TABLE faq ALTER COLUMN seguimiento_desde DROP DEFAULT
"""

#: Los eventos se pliegan a la línea de base **antes** de borrar la tabla.
PLEGAR_EVENTOS = """
UPDATE faq SET usos_anteriores = usos_anteriores
    + (SELECT count(*) FROM faq_uso u WHERE u.faq_id = faq.id)
"""

REVERTIR_FAQ = """
ALTER TABLE faq DROP COLUMN seguimiento_desde;
ALTER TABLE faq DROP COLUMN editada_en;
ALTER TABLE faq RENAME CONSTRAINT ck_faq_usos_anteriores TO ck_faq_usos;
ALTER TABLE faq RENAME COLUMN usos_anteriores TO usos
"""


def _ejecutar(sentencias: str) -> None:
    """Una sentencia por llamada: el driver asíncrono no acepta varias en una."""
    for sentencia in sentencias.split(";\n"):
        op.execute(sentencia.strip())


def upgrade() -> None:
    op.execute(CREAR_TABLA)
    _ejecutar(INDICES)
    op.execute(POLITICA)
    for sentencia in RLS_Y_PERMISOS:
        op.execute(sentencia)
    _ejecutar(AJUSTAR_FAQ)


def downgrade() -> None:
    op.execute(PLEGAR_EVENTOS)
    op.execute("DROP TABLE faq_uso")
    _ejecutar(REVERTIR_FAQ)
