"""Reembolsos parciales y manuales: la tabla `reembolso` y el estado derivado (ADR-0010, D93).

Hasta ahora un cobro admitía **un** reembolso, guardado como un número (`monto_reembolsado`) sin
fecha, referencia, motivo ni autor, y un reembolso parcial figuraba igual `REEMBOLSADO`. Esta
migración entrega los puntos 4 y 5 del ADR-0010, y solo ahora porque hay código y tests detrás:

- **`reembolso`**: una fila **inmutable** por reembolso o por corrección (una corrección es una
  fila negativa que apunta a la que anula). **Solo `SELECT` e `INSERT`** para la aplicación: sin
  `UPDATE` ni `DELETE`, como `registro_de_auditoria` (migración 0001). RLS forzada y política
  `aislamiento_por_empresa`. `corrige_a` único (una fila se corrige una sola vez) y
  `(empresa_id, mp_refund_id)` único (una misma respuesta de MercadoPago, una sola fila).
- **`cobro.monto_reembolsado`** pasa a `NOT NULL DEFAULT 0` con `0 <= x <= monto` (el `CHECK`
  viejo prohibía el cero, que una corrección total necesita). Es el **acumulado**: se escribe en la
  misma transacción que cada fila, y quien lo escribe carga el cobro con `FOR UPDATE`.
- **El reembolso en vuelo** gana tres columnas (`reembolso_solicitado_monto`,
  `reembolso_clave_idempotencia`, `reembolso_mp_refund_id`) que viven **mientras** está en vuelo
  (D27: no es un estado). La clave de idempotencia se guarda para **reusarla** en cada reintento.
- **`ck_cobro_estado_de_reembolso`** ata el estado al acumulado: `REEMBOLSADO_PARCIAL` si
  `0 < acumulado < monto`, `REEMBOLSADO` si `acumulado = monto`.
- **`ck_cobro_fecha_de_pago`** se recrea `NOT VALID` incluyendo `REEMBOLSADO_PARCIAL`.
- `estado` es `varchar(20)` sin `CHECK` de valores: `REEMBOLSADO_PARCIAL` (19 caracteres) entra sin
  tocarla.

**Backfill, sin inventar datos.** Cada cobro `REEMBOLSADO` con `monto_reembolsado > 0` recibe **una
fila** con `monto = monto_reembolsado`, `origen = 'API_MERCADOPAGO'` (hasta hoy no había otro
camino), `fecha_devolucion = updated_at` (la única fecha que existe), `registrado_por = NULL` y
`motivo = 'Registrado antes de ADR-0010; fecha aproximada'`. Los que devolvieron solo una parte
pasan a `REEMBOLSADO_PARCIAL`. Un `REEMBOLSADO` **sin** monto no debería existir: no se le inventa
uno, se informa por `NOTICE` (ids de empresa y un número: ningún dato personal; corre con el rol
de migraciones, que tiene `BYPASSRLS`, ADR-0005) y su `CHECK` queda `NOT VALID`, el mismo
mecanismo que las migraciones 0025 y 0026. Cuando el informe da cero, la restricción se valida
sola.

**Reversible con pérdida declarada.** `downgrade` devuelve `REEMBOLSADO_PARCIAL` a `REEMBOLSADO`
(el comportamiento viejo: un parcial figuraba total), restaura el `CHECK` viejo (acumulado en cero
vuelve a `NULL`), borra las columnas en vuelo y **borra la tabla `reembolso`**: se pierde el
historial (fechas, referencias, motivos, correcciones). El acumulado queda en `cobro`.

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Las mismas expresiones que declara `CobroORM`: si divergen, Alembic y el metadata también.
REGLA_DE_FECHA = (
    "estado NOT IN ('APROBADO', 'REEMBOLSADO_PARCIAL', 'REEMBOLSADO') OR fecha_pago IS NOT NULL"
)
REGLA_DE_FECHA_ANTERIOR = "estado NOT IN ('APROBADO', 'REEMBOLSADO') OR fecha_pago IS NOT NULL"
REGLA_DE_ACUMULADO = "0 <= monto_reembolsado AND monto_reembolsado <= monto"
REGLA_DE_ACUMULADO_ANTERIOR = (
    "monto_reembolsado IS NULL OR (monto_reembolsado > 0 AND monto_reembolsado <= monto)"
)
REGLA_DE_REEMBOLSO_EN_VUELO = (
    "(reembolso_solicitado_en IS NULL) = (reembolso_solicitado_monto IS NULL) "
    "AND (reembolso_solicitado_en IS NULL) = (reembolso_clave_idempotencia IS NULL) "
    "AND (reembolso_mp_refund_id IS NULL OR reembolso_solicitado_en IS NOT NULL)"
)
REGLA_DE_ESTADO_DE_REEMBOLSO = (
    "((estado = 'REEMBOLSADO_PARCIAL') = (monto_reembolsado > 0 AND monto_reembolsado < monto)) "
    "AND ((estado = 'REEMBOLSADO') = (monto_reembolsado = monto))"
)

# Escritas literalmente y no armadas desde una lista, por lo que dice la migración 0002: un SQL
# interpolado se le parece a un escáner exactamente a la inyección que no es.
CREAR_TABLA = """
CREATE TABLE reembolso (
    id uuid PRIMARY KEY,
    empresa_id uuid NOT NULL REFERENCES empresa (id) ON DELETE CASCADE,
    cobro_id uuid NOT NULL REFERENCES cobro (id),
    monto numeric(14, 2) NOT NULL,
    fecha_devolucion timestamptz NOT NULL,
    origen varchar(20) NOT NULL,
    referencia varchar(120) NULL,
    motivo varchar(500) NULL,
    corrige_a uuid NULL REFERENCES reembolso (id),
    mp_refund_id varchar(120) NULL,
    registrado_por uuid NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT ck_reembolso_monto CHECK (monto <> 0),
    CONSTRAINT ck_reembolso_correccion CHECK ((monto < 0) = (corrige_a IS NOT NULL)),
    CONSTRAINT ck_reembolso_origen CHECK (origen IN ('API_MERCADOPAGO', 'MANUAL')),
    CONSTRAINT ck_reembolso_motivo_manual CHECK (
        origen <> 'MANUAL' OR (motivo IS NOT NULL AND length(btrim(motivo)) > 0)
    )
)
"""

#: `(empresa_id, fecha_devolucion)` es lo que la métrica de «cobrado» suma; `(cobro_id)` es el
#: historial. Los dos únicos parciales son las garantías: una fila se corrige una sola vez, y una
#: misma respuesta de MercadoPago no puede insertarse dos veces.
INDICES = """
CREATE INDEX ix_reembolso_empresa_fecha ON reembolso (empresa_id, fecha_devolucion);
CREATE INDEX ix_reembolso_cobro ON reembolso (cobro_id);
CREATE UNIQUE INDEX uq_reembolso_corrige_a ON reembolso (corrige_a) WHERE corrige_a IS NOT NULL;
CREATE UNIQUE INDEX uq_reembolso_mp_refund_id
    ON reembolso (empresa_id, mp_refund_id) WHERE mp_refund_id IS NOT NULL
"""

POLITICA = """
CREATE POLICY aislamiento_por_empresa ON reembolso
    USING (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
    WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
"""

#: Solo-inserción, como `registro_de_auditoria` (0001): se revoca todo y se da lo mínimo.
RLS_Y_PERMISOS = (
    "ALTER TABLE reembolso ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE reembolso FORCE ROW LEVEL SECURITY",
    "REVOKE ALL ON reembolso FROM cheatsheet_app",
    "GRANT SELECT, INSERT ON reembolso TO cheatsheet_app",
)

#: El `CHECK` viejo prohíbe el cero: se saca **antes** de completar el `NULL` con cero. Y
#: `ck_cobro_fecha_de_pago` también, aunque se recree más abajo: una restricción `NOT VALID`
#: igual se evalúa en cada `UPDATE` de una fila, y un cobro pagado sin fecha (la anomalía que la
#: 0026 informa y no corrige) haría fallar la migración entera.
PREPARAR_COBRO = """
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_fecha_de_pago;
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_reembolso;
UPDATE cobro SET monto_reembolsado = 0 WHERE monto_reembolsado IS NULL;
ALTER TABLE cobro ALTER COLUMN monto_reembolsado SET DEFAULT 0;
ALTER TABLE cobro ALTER COLUMN monto_reembolsado SET NOT NULL;
ALTER TABLE cobro ADD COLUMN reembolso_solicitado_monto numeric(14, 2) NULL;
ALTER TABLE cobro ADD COLUMN reembolso_clave_idempotencia uuid NULL;
ALTER TABLE cobro ADD COLUMN reembolso_mp_refund_id varchar(120) NULL
"""

RESTRICCIONES = f"""
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_reembolso CHECK ({REGLA_DE_ACUMULADO});
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_fecha_de_pago CHECK ({REGLA_DE_FECHA}) NOT VALID;
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_reembolso_en_vuelo
    CHECK ({REGLA_DE_REEMBOLSO_EN_VUELO}) NOT VALID;
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_estado_de_reembolso
    CHECK ({REGLA_DE_ESTADO_DE_REEMBOLSO}) NOT VALID
"""

#: Una fila por cobro `REEMBOLSADO` con plata devuelta. Sin `NOW()` en la fecha de devolución: la
#: única fecha que hay es `updated_at`, y por eso el motivo dice que es aproximada.
BACKFILL_DE_FILAS = """
INSERT INTO reembolso (
    id, empresa_id, cobro_id, monto, fecha_devolucion, origen, referencia, motivo,
    corrige_a, mp_refund_id, registrado_por, created_at
)
SELECT
    gen_random_uuid(), c.empresa_id, c.id, c.monto_reembolsado, c.updated_at,
    'API_MERCADOPAGO', NULL, 'Registrado antes de ADR-0010; fecha aproximada',
    NULL, NULL, NULL, now()
FROM cobro c
WHERE c.estado = 'REEMBOLSADO' AND c.monto_reembolsado > 0
"""

#: Los que devolvieron solo una parte figuraban `REEMBOLSADO` (epic-6 `pendientes.md`, ítem 7).
BACKFILL_DE_ESTADO = """
UPDATE cobro SET estado = 'REEMBOLSADO_PARCIAL'
WHERE estado = 'REEMBOLSADO' AND monto_reembolsado > 0 AND monto_reembolsado < monto
"""

#: `IS NOT TRUE` y no `NOT (...)`: con una columna `NULL` la regla evalúa a `NULL`, y `NOT NULL` es
#: `NULL`, que un `WHERE` descartaría en silencio. Las reglas se repiten a mano (y no se
#: interpolan) para que la consulta sea un literal; tienen que coincidir con las constantes de
#: arriba. Cuando una da cero, su `CHECK` se valida: ya no es `NOT VALID`.
INFORME_Y_VALIDACION = """
DO $informe$
DECLARE
    fila record;
    fuera_del_acumulado integer := 0;
    en_vuelo_incompleto integer := 0;
BEGIN
    FOR fila IN
        SELECT empresa_id, count(*) AS cantidad
        FROM cobro
        WHERE (
            ((estado = 'REEMBOLSADO_PARCIAL')
                = (monto_reembolsado > 0 AND monto_reembolsado < monto))
            AND ((estado = 'REEMBOLSADO') = (monto_reembolsado = monto))
        ) IS NOT TRUE
        GROUP BY empresa_id
        ORDER BY empresa_id
    LOOP
        RAISE NOTICE 'cobro con estado que no concuerda con lo reembolsado: empresa % tiene % cobro(s)',
            fila.empresa_id, fila.cantidad;
        fuera_del_acumulado := fuera_del_acumulado + fila.cantidad;
    END LOOP;

    FOR fila IN
        SELECT empresa_id, count(*) AS cantidad
        FROM cobro
        WHERE (
            (reembolso_solicitado_en IS NULL) = (reembolso_solicitado_monto IS NULL)
            AND (reembolso_solicitado_en IS NULL) = (reembolso_clave_idempotencia IS NULL)
            AND (reembolso_mp_refund_id IS NULL OR reembolso_solicitado_en IS NOT NULL)
        ) IS NOT TRUE
        GROUP BY empresa_id
        ORDER BY empresa_id
    LOOP
        RAISE NOTICE 'reembolso en vuelo sin monto ni clave de idempotencia: empresa % tiene % cobro(s)',
            fila.empresa_id, fila.cantidad;
        en_vuelo_incompleto := en_vuelo_incompleto + fila.cantidad;
    END LOOP;

    IF fuera_del_acumulado = 0 THEN
        ALTER TABLE cobro VALIDATE CONSTRAINT ck_cobro_estado_de_reembolso;
    END IF;
    IF en_vuelo_incompleto = 0 THEN
        ALTER TABLE cobro VALIDATE CONSTRAINT ck_cobro_reembolso_en_vuelo;
    END IF;
END
$informe$
"""

#: **Con pérdida declarada**: un parcial vuelve a figurar `REEMBOLSADO` (el comportamiento viejo).
#: Las sentencias `UPDATE` son literales y las `ALTER` llevan las reglas interpoladas: mezclarlas
#: en un mismo texto interpolado es lo que un escáner de SQL lee como inyección.
BAJAR_ESTADO = "UPDATE cobro SET estado = 'REEMBOLSADO' WHERE estado = 'REEMBOLSADO_PARCIAL'"

BAJAR_RESTRICCIONES = """
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_estado_de_reembolso;
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_reembolso_en_vuelo;
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_reembolso;
ALTER TABLE cobro DROP CONSTRAINT ck_cobro_fecha_de_pago
"""

#: El acumulado en cero vuelve a `NULL` (el `CHECK` viejo prohíbe el cero), y para eso la columna
#: tiene que dejar de ser `NOT NULL` **antes**.
BAJAR_ACUMULADO = "UPDATE cobro SET monto_reembolsado = NULL WHERE monto_reembolsado = 0"

BAJAR_NULABLE = """
ALTER TABLE cobro ALTER COLUMN monto_reembolsado DROP NOT NULL;
ALTER TABLE cobro ALTER COLUMN monto_reembolsado DROP DEFAULT
"""

BAJAR_COLUMNAS = f"""
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_reembolso CHECK ({REGLA_DE_ACUMULADO_ANTERIOR});
ALTER TABLE cobro ADD CONSTRAINT ck_cobro_fecha_de_pago
    CHECK ({REGLA_DE_FECHA_ANTERIOR}) NOT VALID;
ALTER TABLE cobro DROP COLUMN reembolso_mp_refund_id;
ALTER TABLE cobro DROP COLUMN reembolso_clave_idempotencia;
ALTER TABLE cobro DROP COLUMN reembolso_solicitado_monto
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
    _ejecutar(PREPARAR_COBRO)
    op.execute(BACKFILL_DE_FILAS)
    op.execute(BACKFILL_DE_ESTADO)
    _ejecutar(RESTRICCIONES)
    op.execute(INFORME_Y_VALIDACION)


def downgrade() -> None:
    # Las restricciones primero: `ck_cobro_estado_de_reembolso` prohíbe el `REEMBOLSADO` de un
    # parcial que el `UPDATE` siguiente va a producir.
    _ejecutar(BAJAR_RESTRICCIONES)
    op.execute(BAJAR_ESTADO)
    _ejecutar(BAJAR_NULABLE)
    op.execute(BAJAR_ACUMULADO)
    _ejecutar(BAJAR_COLUMNAS)
    op.execute("DROP TABLE reembolso")
