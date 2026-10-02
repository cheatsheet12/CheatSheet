"""La duración de un servicio agendable queda entre 5 y 480 minutos (decisión D86).

Hasta ahora el panel aceptaba cualquier entero positivo: 99999 minutos son casi 70 días. La
unidad `duracion-de-servicios` fija el rango en el agregado `Servicio`, y esta migración lo
refuerza en la base con un `CHECK`, para que una escritura que no pase por el agregado (un
script, un contexto futuro, un `UPDATE` a mano) no pueda romper la regla.

**Por qué `NOT VALID`.** Pueden existir servicios ya fuera de rango. Con `NOT VALID` la
restricción protege **toda escritura nueva** sin fallar por las filas viejas y sin decidir por
el usuario qué valor les corresponde (no hay recorte automático a 480). La corrección es
manual: al editar el servicio desde el panel, el dominio exige un valor válido. Cuando el
informe de abajo dé cero, un `VALIDATE CONSTRAINT` en una migración posterior deja la
restricción completa.

**El informe.** La migración emite un `NOTICE` con la cantidad de servicios fuera de la regla
por empresa (sólo ids de empresa y un número: ningún dato personal). Corre con el rol de
migraciones, que tiene `BYPASSRLS` (ADR-0005), así que ve todas las empresas.

La expresión pide `IS NOT NULL` en la rama agendable a propósito: un `CHECK` deja pasar el
resultado `NULL`, y sin eso un agendable sin duración lo cumpliría.

Es reversible y no hace backfill: `downgrade` quita la restricción.

Revision ID: 0025
Revises: 0024
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOMBRE_RESTRICCION = "ck_servicio_duracion_en_rango"

#: La misma expresión que declara `ServicioORM`: si divergen, Alembic y el metadata también.
REGLA = (
    "(agendable AND duracion_estandar_min IS NOT NULL "
    "AND duracion_estandar_min BETWEEN 5 AND 480) "
    "OR (NOT agendable AND duracion_estandar_min IS NULL)"
)

AGREGAR_RESTRICCION = f"""
ALTER TABLE servicio ADD CONSTRAINT {NOMBRE_RESTRICCION}
CHECK ({REGLA}) NOT VALID
"""

QUITAR_RESTRICCION = f"ALTER TABLE servicio DROP CONSTRAINT {NOMBRE_RESTRICCION}"

#: `IS NOT TRUE` y no `NOT (...)`: con una duración `NULL` la regla evalúa a `NULL`, y
#: `NOT NULL` es `NULL`, que un `WHERE` descartaría en silencio. La regla se repite a mano
#: (y no se interpola) para que la consulta sea un literal; tiene que coincidir con `REGLA`.
INFORME = """
DO $informe$
DECLARE
    fila record;
BEGIN
    FOR fila IN
        SELECT empresa_id, count(*) AS cantidad
        FROM servicio
        WHERE ((agendable AND duracion_estandar_min IS NOT NULL
                AND duracion_estandar_min BETWEEN 5 AND 480)
               OR (NOT agendable AND duracion_estandar_min IS NULL)) IS NOT TRUE
        GROUP BY empresa_id
        ORDER BY empresa_id
    LOOP
        RAISE NOTICE 'duracion fuera de regla: empresa % tiene % servicio(s)',
            fila.empresa_id, fila.cantidad;
    END LOOP;
END
$informe$
"""


def upgrade() -> None:
    op.execute(AGREGAR_RESTRICCION)
    op.execute(INFORME)


def downgrade() -> None:
    op.execute(QUITAR_RESTRICCION)
