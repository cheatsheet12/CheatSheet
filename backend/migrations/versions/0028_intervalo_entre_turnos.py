"""Intervalo entre turnos y slot acotado (decisión D96).

Separa tres conceptos que hasta hoy eran uno: la duración del **turno** (la del servicio), el
**slot** (el paso de la grilla de inicios) y el **intervalo entre turnos** (un margen opcional
que se agrega después de cada turno). Esta migración le da a la base lo que necesita para que
la garantía contra el doble booking siga siendo suya (D28) también con intervalo:

1. `recurso_reservable.intervalo_entre_turnos_min` — `NOT NULL DEFAULT 0`, entre 0 y 480
   (HU-E7-04 RN-06).
2. `turno.intervalo_posterior_min` — el intervalo que se aplicó al reservar o reprogramar. `NULL`
   significa «sin intervalo»: la carga y la corrección a posteriori no lo respetan ni lo imponen
   (HU-E7-06 RN-07). **Sin `DEFAULT` a propósito**: el ORM omite del `INSERT` un atributo en
   `None`, y un default de la base convertiría ese `NULL` en 0 sin que nadie lo note. Los
   turnos existentes se rellenan con 0 con un `UPDATE`.
3. `excl_turno_recurso_intervalo` — la exclusión sobre la franja **más** el intervalo, sólo
   entre turnos que llevan intervalo. `excl_turno_recurso_franja` (0020/0024) **no cambia**: la
   franja real nunca se pisa, tampoco en la excepción a posteriori. Con todo en 0 la nueva
   equivale a la vieja, así que crearla no puede fallar por datos existentes.
4. `ck_patron_slot` pasa de `duracion_slot_min > 0` a 5-480 minutos sin superar la extensión de
   la franja (HU-E7-04 RN-05). **Antes** busca los patrones que no cumplen y aborta listando
   los ids, como 0024: recortar un slot es una decisión del negocio y no de una migración.

**Número reservado.** Esta rama termina en 0024, pero la otra cadena de unidades ya usa 0025,
0026 y 0027 (todas hijas de 0024). Usar 0028 evita el choque de nombre, no el de cadena: al
rebasar sobre `develop` con esa cadena ya integrada hay que **re-apuntar `down_revision` a la
cabeza vigente** (hoy "0027") y verificar con `alembic heads` que queda una sola. Si otra unidad
toma 0028 antes, se renumera.

Es reversible: `downgrade` borra la exclusión, los checks y las dos columnas, y restaura
`duracion_slot_min > 0`.

Revision ID: 0028
Revises: 0024
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
# Re-apuntar al rebasar sobre `develop`: ver «Número reservado» en el docstring.
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Los patrones que el check nuevo rechazaría. Sin `empresa_id` en el filtro a propósito: la
#: migración corre con el rol de migraciones, que tiene `BYPASSRLS` (ADR-0005).
PATRONES_FUERA_DE_RANGO = """
SELECT id, duracion_slot_min
FROM patron_de_disponibilidad
WHERE duracion_slot_min NOT BETWEEN 5 AND 480
   OR duracion_slot_min * interval '1 minute' > hora_fin - hora_inicio
ORDER BY id
"""

#: Una sentencia por elemento: la migración corre sobre un motor asíncrono y asyncpg no acepta
#: varias sentencias en un mismo `execute`.
AGREGAR_COLUMNAS = (
    "ALTER TABLE recurso_reservable "
    "ADD COLUMN intervalo_entre_turnos_min integer NOT NULL DEFAULT 0",
    "ALTER TABLE recurso_reservable ADD CONSTRAINT ck_recurso_intervalo "
    "CHECK (intervalo_entre_turnos_min BETWEEN 0 AND 480)",
    "ALTER TABLE turno ADD COLUMN intervalo_posterior_min integer",
    "ALTER TABLE turno ADD CONSTRAINT ck_turno_intervalo "
    "CHECK (intervalo_posterior_min IS NULL OR intervalo_posterior_min BETWEEN 0 AND 480)",
)

#: Los turnos existentes quedan con intervalo 0 (D96, pregunta 1): con 0 la restricción nueva
#: equivale a la de 0024.
RELLENAR_TURNOS = "UPDATE turno SET intervalo_posterior_min = 0"

QUITAR_CHECK_DE_SLOT = "ALTER TABLE patron_de_disponibilidad DROP CONSTRAINT ck_patron_slot"
CHECK_DE_SLOT_ACOTADO = """
ALTER TABLE patron_de_disponibilidad ADD CONSTRAINT ck_patron_slot
CHECK (
    duracion_slot_min BETWEEN 5 AND 480
    AND duracion_slot_min * interval '1 minute' <= hora_fin - hora_inicio
);
"""
CHECK_DE_SLOT_ORIGINAL = """
ALTER TABLE patron_de_disponibilidad ADD CONSTRAINT ck_patron_slot
CHECK (duracion_slot_min > 0);
"""

#: Ver `EXCLUSION_SOLAPAMIENTO` en 0020 para el porqué de `[)` y de la función inmutable. La
#: duración extendida es `integer + integer`, inmutable como la función que la recibe.
EXCLUSION_CON_INTERVALO = """
ALTER TABLE turno ADD CONSTRAINT excl_turno_recurso_intervalo
EXCLUDE USING gist (
    recurso_id WITH =,
    franja_de_turno(franja_inicio, franja_duracion_min + intervalo_posterior_min) WITH &&
)
WHERE (
    estado IN ('RESERVADO', 'CONFIRMADO', 'COMPLETADO')
    AND intervalo_posterior_min IS NOT NULL
);
"""

QUITAR_TODO = (
    "ALTER TABLE turno DROP CONSTRAINT IF EXISTS excl_turno_recurso_intervalo",
    "ALTER TABLE turno DROP CONSTRAINT IF EXISTS ck_turno_intervalo",
    "ALTER TABLE turno DROP COLUMN IF EXISTS intervalo_posterior_min",
    "ALTER TABLE recurso_reservable DROP CONSTRAINT IF EXISTS ck_recurso_intervalo",
    "ALTER TABLE recurso_reservable DROP COLUMN IF EXISTS intervalo_entre_turnos_min",
)


class PatronesConSlotInvalido(RuntimeError):
    """Hay patrones con un slot fuera de 5-480 o mayor que su franja."""


def _exigir_patrones_validos() -> None:
    invalidos = op.get_bind().exec_driver_sql(PATRONES_FUERA_DE_RANGO).all()
    if not invalidos:
        return
    detalle = "; ".join(f"{uno} ({minutos} min)" for uno, minutos in invalidos)
    raise PatronesConSlotInvalido(
        "No se puede acotar ck_patron_slot: hay "
        f"{len(invalidos)} patron(es) de disponibilidad con un slot fuera de 5-480 minutos o "
        f"mayor que su franja (ids: {detalle}). "
        "Corregí el slot de cada uno y volvé a ejecutar la migración."
    )


def upgrade() -> None:
    _exigir_patrones_validos()
    for sentencia in AGREGAR_COLUMNAS:
        op.execute(sentencia)
    op.execute(RELLENAR_TURNOS)
    op.execute(QUITAR_CHECK_DE_SLOT)
    op.execute(CHECK_DE_SLOT_ACOTADO)
    op.execute(EXCLUSION_CON_INTERVALO)


def downgrade() -> None:
    for sentencia in QUITAR_TODO:
        op.execute(sentencia)
    op.execute(QUITAR_CHECK_DE_SLOT)
    op.execute(CHECK_DE_SLOT_ORIGINAL)
