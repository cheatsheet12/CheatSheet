"""`excl_turno_recurso_franja` también cubre los turnos COMPLETADO (decisión D95).

La restricción de exclusión de la migración 0020 sólo cubría `RESERVADO` y `CONFIRMADO`, y eso
dejaba dos huecos que la unidad `turnos-no-en-el-pasado` cierra:

1. **La carga a posteriori nace `COMPLETADO`** (HU-E7-06 RN-07) y la historia exige rechazar
   el solapamiento con otros turnos reales del recurso. Un chequeo en Python pierde contra dos
   pedidos concurrentes; sólo el motor lo garantiza, como en el resto del épico (D28).
2. **Ya hoy** se podía crear un turno encima de una atención completada: un hueco preexistente
   que el bug de reservar en el pasado volvía alcanzable.

`NO_SHOW` **queda afuera a propósito**: si el cliente no vino, el recurso quedó libre de hecho,
y el Administrador tiene que poder registrar a posteriori la atención de otra persona en esa
franja. `CANCELADO` tampoco ocupa, como antes.

**Riesgo y cómo se maneja.** Si en la base ya hay turnos `COMPLETADO` que se solapan entre sí o
con uno abierto (posible: el bug permitía reservar en el pasado), crear la restricción falla
con un error críptico de PostgreSQL. Por eso la migración **primero busca esos conflictos y
aborta con un mensaje que lista los ids**, para que alguien los resuelva a mano antes de
reintentar. No hay backfill: decidir cuál de dos turnos pisados es el real no es una decisión
que una migración pueda tomar.

Es reversible: `downgrade` restaura la condición original de 0020.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Pares de turnos que la nueva condición pondría en conflicto: los dos ocupan la franja bajo
#: la condición ampliada, y al menos uno es `COMPLETADO` (entre dos abiertos ya rige la
#: restricción actual). Sin `empresa_id` en el filtro a propósito: la migración corre con el rol
#: de migraciones, que tiene `BYPASSRLS` (ADR-0005), y tiene que ver todas las empresas.
CONFLICTOS = """
SELECT a.id AS uno, b.id AS otro
FROM turno a
JOIN turno b
  ON a.recurso_id = b.recurso_id
 AND a.id < b.id
 AND franja_de_turno(a.franja_inicio, a.franja_duracion_min)
     && franja_de_turno(b.franja_inicio, b.franja_duracion_min)
WHERE a.estado IN ('RESERVADO', 'CONFIRMADO', 'COMPLETADO')
  AND b.estado IN ('RESERVADO', 'CONFIRMADO', 'COMPLETADO')
  AND (a.estado = 'COMPLETADO' OR b.estado = 'COMPLETADO')
ORDER BY a.id, b.id
"""

QUITAR_EXCLUSION = "ALTER TABLE turno DROP CONSTRAINT excl_turno_recurso_franja"

#: Ver `EXCLUSION_SOLAPAMIENTO` en 0020 para el porqué de `[)` y de la función inmutable.
EXCLUSION_CON_COMPLETADO = """
ALTER TABLE turno ADD CONSTRAINT excl_turno_recurso_franja
EXCLUDE USING gist (
    recurso_id WITH =,
    franja_de_turno(franja_inicio, franja_duracion_min) WITH &&
)
WHERE (estado IN ('RESERVADO', 'CONFIRMADO', 'COMPLETADO'));
"""

EXCLUSION_ORIGINAL = """
ALTER TABLE turno ADD CONSTRAINT excl_turno_recurso_franja
EXCLUDE USING gist (
    recurso_id WITH =,
    franja_de_turno(franja_inicio, franja_duracion_min) WITH &&
)
WHERE (estado IN ('RESERVADO', 'CONFIRMADO'));
"""


class TurnosSolapadosExistentes(RuntimeError):
    """Hay turnos completados que se pisan y la restricción ampliada no puede crearse."""


def _exigir_sin_conflictos() -> None:
    conflictos = op.get_bind().exec_driver_sql(CONFLICTOS).all()
    if not conflictos:
        return
    pares = "; ".join(f"{uno} con {otro}" for uno, otro in conflictos)
    raise TurnosSolapadosExistentes(
        "No se puede ampliar excl_turno_recurso_franja a COMPLETADO: hay "
        f"{len(conflictos)} par(es) de turnos solapados en el mismo recurso (ids: {pares}). "
        "Cancelá o corregí uno de cada par y volvé a ejecutar la migración."
    )


def upgrade() -> None:
    _exigir_sin_conflictos()
    op.execute(QUITAR_EXCLUSION)
    op.execute(EXCLUSION_CON_COMPLETADO)


def downgrade() -> None:
    op.execute(QUITAR_EXCLUSION)
    op.execute(EXCLUSION_ORIGINAL)
