"""Cuándo, cómo y con qué operación se pagó un cobro (ADR-0010, decisión D91).

Hasta ahora un cobro pagado sabía *cuándo lo procesó el sistema* (`pagado_en`), no *cuándo pagó
el cliente*, y no sabía por qué medio. Esta migración deja el modelo listo para las dos cosas:

- `pagado_en` **se renombra** a `fecha_pago` (una sola fuente de verdad: dos columnas para el
  mismo hecho es lo que el ADR quiere evitar). El código nuevo la llena con la fecha de
  aprobación de MercadoPago; migración y código salen en el mismo release.
- `fecha_pago_aproximada`: `true` cuando `fecha_pago` es una estimación. **Todas** las filas
  que ya tenían fecha quedan marcadas: su valor es «cuándo lo registramos», no «cuándo pagó».
  No se consulta a MercadoPago desde una migración (no hay red ni token por empresa, y una
  migración no puede depender de un tercero); completarlas es una tarea aparte, anotada.
- `medio_de_pago`: `LINK_MERCADOPAGO` o `TRANSFERENCIA`. Todo cobro existente es por link: hasta
  hoy no existe otro camino de pago, así que el `DEFAULT` no inventa nada.
- `numero_de_operacion`: nadie lo escribe todavía (lo hace `cobro-por-transferencia`). Un
  índice único por empresa sobre `COALESCE(numero_de_operacion, mp_payment_id)` hace que una
  operación tenga efecto una sola vez, llegue por link o por transferencia.

**Por qué `NOT VALID`** en `ck_cobro_fecha_de_pago` (un `APROBADO` o `REEMBOLSADO` debe tener
fecha). No debería haber filas que la violen, pero si las hay no se les inventa una fecha: la
restricción protege **toda escritura nueva** y la corrección queda manual. Se sigue el mismo
mecanismo de la migración 0025: un `NOTICE` por empresa con la cantidad de filas fuera de la
regla (sólo ids de empresa y un número: ningún dato personal, corre con el rol de migraciones,
que tiene `BYPASSRLS`, ADR-0005) y, cuando el informe dé cero, un `VALIDATE CONSTRAINT` en una
migración posterior.

RLS y permisos: no hay tabla nueva. La política `aislamiento_por_empresa` y el `GRANT SELECT,
INSERT, UPDATE` de la 0019 son de tabla y cubren las columnas nuevas. `ck_cobro_reembolso` no se
toca, ni la tabla `reembolso` ni `REEMBOLSADO_PARCIAL`: son de `reembolsos-parciales-y-manuales`.

Es reversible: `downgrade` quita índice y restricciones, borra las tres columnas nuevas y
devuelve `fecha_pago` a `pagado_en`. Pierde sólo lo derivado (el medio y la marca de aproximada).

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: La misma expresión que declara `CobroORM`: si divergen, Alembic y el metadata también.
REGLA_DE_FECHA = "estado NOT IN ('APROBADO', 'REEMBOLSADO') OR fecha_pago IS NOT NULL"
REGLA_DE_MEDIO = "medio_de_pago IN ('LINK_MERCADOPAGO', 'TRANSFERENCIA')"
REGLA_DE_APROXIMADA = "fecha_pago_aproximada = false OR fecha_pago IS NOT NULL"

AGREGAR_COLUMNAS = """
ALTER TABLE cobro RENAME COLUMN pagado_en TO fecha_pago;
ALTER TABLE cobro ADD COLUMN fecha_pago_aproximada boolean NOT NULL DEFAULT false;
ALTER TABLE cobro ADD COLUMN medio_de_pago varchar(30) NOT NULL DEFAULT 'LINK_MERCADOPAGO';
ALTER TABLE cobro ADD COLUMN numero_de_operacion varchar(120) NULL
"""

#: Nada más que esto: el `DEFAULT` ya dio `LINK_MERCADOPAGO` a las filas viejas, y a las que
#: no tenían fecha no se les inventa una.
BACKFILL = "UPDATE cobro SET fecha_pago_aproximada = true WHERE fecha_pago IS NOT NULL"

#: `IS NOT TRUE` y no `NOT (...)`: con una fecha `NULL` la regla evalúa a `NULL`, y `NOT NULL`
#: es `NULL`, que un `WHERE` descartaría en silencio. La regla se repite a mano (y no se
#: interpola) para que la consulta sea un literal; tiene que coincidir con `REGLA_DE_FECHA`.
INFORME = """
DO $informe$
DECLARE
    fila record;
BEGIN
    FOR fila IN
        SELECT empresa_id, count(*) AS cantidad
        FROM cobro
        WHERE (estado NOT IN ('APROBADO', 'REEMBOLSADO') OR fecha_pago IS NOT NULL) IS NOT TRUE
        GROUP BY empresa_id
        ORDER BY empresa_id
    LOOP
        RAISE NOTICE 'cobro pagado sin fecha de pago: empresa % tiene % cobro(s)',
            fila.empresa_id, fila.cantidad;
    END LOOP;
END
$informe$
"""

AGREGAR_RESTRICCIONES = f"""
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_fecha_de_pago CHECK ({REGLA_DE_FECHA}) NOT VALID;
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_medio_de_pago CHECK ({REGLA_DE_MEDIO});
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_fecha_aproximada CHECK ({REGLA_DE_APROXIMADA})
"""

#: Por empresa y no global: dos cuentas de MercadoPago pueden repetir un número. Parcial: un
#: cobro sin pagar no tiene ni operación ni pago, y `NULL` no es un duplicado. Las filas
#: existentes no pueden chocar: `numero_de_operacion` es `NULL` en todas, así que la expresión
#: vale `mp_payment_id`, que ya es único por empresa (D20).
CREAR_INDICE = """
CREATE UNIQUE INDEX uq_cobro_operacion
ON cobro (empresa_id, (COALESCE(numero_de_operacion, mp_payment_id)))
WHERE COALESCE(numero_de_operacion, mp_payment_id) IS NOT NULL
"""

QUITAR = """
DROP INDEX uq_cobro_operacion;
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_fecha_aproximada;
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_medio_de_pago;
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_fecha_de_pago;
ALTER TABLE cobro DROP COLUMN numero_de_operacion;
ALTER TABLE cobro DROP COLUMN medio_de_pago;
ALTER TABLE cobro DROP COLUMN fecha_pago_aproximada;
ALTER TABLE cobro RENAME COLUMN fecha_pago TO pagado_en
"""


def _ejecutar(sentencias: str) -> None:
    """Una sentencia por llamada: el driver asíncrono no acepta varias en una."""
    for sentencia in sentencias.split(";\n"):
        op.execute(sentencia.strip())


def upgrade() -> None:
    _ejecutar(AGREGAR_COLUMNAS)
    op.execute(BACKFILL)
    op.execute(INFORME)
    _ejecutar(AGREGAR_RESTRICCIONES)
    op.execute(CREAR_INDICE)


def downgrade() -> None:
    _ejecutar(QUITAR)
