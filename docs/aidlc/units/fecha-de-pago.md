# Unidad: fecha-de-pago

**HUs**: HU-E6-01, HU-E6-02 **Contexto dueño**: payments (con una lectura en reporting que hereda la métrica) **Rama**: feature/payments-fecha-de-pago

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D91 (`docs/aidlc/epicas/06-cobros-y-recordatorios/decisiones.md`). La rama sale de
> `feature/payments-nuevo-cobro-desde-su-panel` (cadena de ramas: PR #49 sobre #48 sobre #45); su PR
> apunta a esa rama y pasa a `develop` cuando la cadena llegue. Tamaño: M. Es la primera unidad de la
> cadena `fecha-de-pago → reembolsos-parciales-y-manuales → cobro-por-transferencia →
> comprobante-por-whatsapp`; `indicadores-de-cobranza` (reporting, D98) también depende de ella.
> Escribe el **ADR-0010** ([borrador](../../adr/0010-payment-date-method-and-refunds.md)), que las
> otras tres unidades de payments consumen sin reescribirlo.

## Qué hace

Hoy un cobro pagado sabe *cuándo lo procesó el sistema* (`pagado_en`), no *cuándo pagó el cliente*, y
el encabezado de PAN-COB-01 mide «cobrado» por fecha de **creación**: un cobro creado en febrero y
pagado en marzo no suma en marzo. Esta unidad hace que el cobro guarde **cuándo se pagó** (la fecha de
aprobación que informa MercadoPago), **por qué medio** y, para las transferencias que llegan después,
**qué operación**; que PAN-COB-02 muestre medio, fecha y número de operación (solo transferencia); y
que «cobrado» del encabezado se mida por fecha de pago con la tasa de cobro calculada solo sobre lo
creado en el período (D91), sin poder pasar del 100 %. Los cobros que ya existen conservan lo que hoy
saben y quedan marcados como fecha aproximada: no se inventa nada.

**Fuera de esta unidad:**
- Reembolsos parciales, la tabla `reembolso`, el estado `REEMBOLSADO_PARCIAL`, el registro manual y que
  el reembolso reste «cobrado» en el período de la devolución (HU-E6-05, D93): unidad
  `reembolsos-parciales-y-manuales`. Acá el ADR fija el modelo y esta unidad no lo migra.
- Registrar y verificar una transferencia, la regla de identidad del pagador, «Reintentar verificación»
  (HU-E6-08, D94): unidad `cobro-por-transferencia`. Acá la columna `numero_de_operacion` y su índice
  único quedan listos y **nada la escribe**.
- El recibo por WhatsApp (HU-E8-06): unidad `comprobante-por-whatsapp`.
- «Cobrado por semana», «cobros por estado» y el resumen de Inicio (HU-E10-01, D98): unidad
  `indicadores-de-cobranza`. Reporting hereda la nueva definición de «cobrado» porque reusa
  `MetricasDelPeriodo` (ver «Otros contextos»), y nada más.
- Completar la fecha de los cobros ya pagados consultando a MercadoPago (ver pregunta 2).
- Persistir cualquier dato del pagador (HU-E8-06/HU-E6-08 RN-07: nunca).
- El `float(cobro.monto)` de `pasarela.py:85` (crear link) y el `float(monto)` de `pasarela.py:162`
  (reembolsar) — hallazgo anotado, no se toca; el segundo es de la unidad de reembolsos.
- Que el listado de PAN-COB-01 filtre por fecha de pago (pregunta 5).

## Las preguntas que el mapa dejó para este Gate

### 1. ¿`fecha_pago` es una columna nueva o `pagado_en` renombrada? — **hallazgo H1**

D91 dice «`cobro` no tiene fecha de pago. Se agrega `fecha_pago`», y el DER no la trae. Pero **el código
ya tiene `pagado_en`**: columna en la migración 0019, campo del agregado (`domain/cobro.py:141`),
del ORM, del repositorio, de la salida HTTP (`api/routers/cobros.py:81`), del tipo del frontend y de
`DetalleDeCobro`, que la muestra como «Pagado». Lo que no tiene es la fecha correcta: `Cobro.aprobar`
la fija en `ahora` (el instante en que el webhook se procesó, `routers/webhooks.py:95`), no la fecha de
aprobación de MercadoPago. Un webhook reintentado horas después mueve el pago de período.

**Recomendación: renombrar `pagado_en` → `fecha_pago` (una sola fuente) y cambiar cómo se llena.**
El nombre de la historia, del DER enmendado y de D91 es `fecha_pago`; dos columnas para el mismo hecho
es lo que el ADR quiere evitar. Se paga un cambio que toca ~10 sitios (ORM, repositorio, dominio,
salida HTTP, reporting `acl.py:198`, tipos y pantalla del frontend, sus tests) y un campo HTTP
renombrado; el único consumidor es el panel, que se despliega junto con la API. Alternativa: agregar
`fecha_pago` y dejar `pagado_en` muerta: cero riesgo de despliegue, pero queda una columna engañosa.

### 2. ¿Qué reciben los cobros ya pagados, y cómo se marca la aproximación?

Hoy `pagado_en` está lleno en todo cobro `APROBADO` y `REEMBOLSADO` (solo `aprobar` lo escribe; el pago
huérfano de un `CANCELADO` **no** lo escribe). Su valor es real pero es «cuándo lo registramos», no
«cuándo pagó». D91 pide completarlo desde MercadoPago si se puede y, si no, marcarlo aproximado, y deja
abierto cómo.

**Recomendación:** columna `fecha_pago_aproximada boolean NOT NULL DEFAULT false`. La migración pone
`true` en **todas** las filas que ya tenían fecha, y `false` en el resto. **Sin llamada a MercadoPago
dentro de la migración** (no hay red ni tokens por empresa en una migración, y una migración no puede
depender de un tercero). Un cobro `APROBADO` o `REEMBOLSADO` sin fecha —que no debería existir— se deja
en `NULL`, se informa por `NOTICE` con la cantidad por empresa (mismo mecanismo que la migración 0025) y
la restricción se agrega `NOT VALID`; la corrección es manual, no inventada. Qué recibe cada fila:

| Fila existente | `fecha_pago` | `fecha_pago_aproximada` | `medio_de_pago` | `numero_de_operacion` |
|---|---|---|---|---|
| `APROBADO` / `REEMBOLSADO` | la de `pagado_en` | `true` | `LINK_MERCADOPAGO` | `NULL` |
| `PENDIENTE` / `VENCIDO` | `NULL` | `false` | `LINK_MERCADOPAGO` (valor por defecto) | `NULL` |
| `CANCELADO` (con o sin pago huérfano) | `NULL` | `false` | `LINK_MERCADOPAGO` | `NULL` |

`LINK_MERCADOPAGO` para todo cobro existente **no es un dato inventado**: hasta hoy no existe otro
camino de pago (D91: «mientras no exista, todo cobro es por link»). Alternativa descartada: reconsultar a
MercadoPago cada `mp_payment_id` con una tarea; es útil solo si hay producción con datos, y el sistema
está en staging. Se deja como pendiente anotado, no como código.

### 3. ¿Qué migra esta unidad y qué queda para la de reembolsos?

El mapa dice que la migración de `cobro` trae `fecha_pago`, `medio_de_pago`, `numero_de_operacion` **y
los campos de reembolso**. **Recomendación: 0026 lleva solo lo que esta unidad usa** —fecha, aproximada,
medio y número de operación con su índice— y el modelo de reembolsos (tabla `reembolso`, estado
`REEMBOLSADO_PARCIAL`) lo decide el ADR-0010 y lo migra la unidad `reembolsos-parciales-y-manuales`
(0027). Razón: una tabla nueva necesita RLS, grants sin `UPDATE`/`DELETE` y sus tests, y nada de esta
unidad la escribe ni la lee; sería esquema muerto y sin prueba. Lo que se paga: dos migraciones para un
mismo modelo. Si el Gate prefiere todo en 0026, la unidad deja de ser M (tabla + RLS + estado en dominio,
frontend y filtros) y hay que partirla; no lo recomiendo.

### 4. ¿Cómo se define exactamente el encabezado de PAN-COB-01? — **hallazgo H2**

Hoy `metricas` (`repositories.py:134`) suma **todo por `created_at`** y «cobrado» es solo `APROBADO`;
un reembolso total saca al cobro de «cobrado» del período de su **creación**, lo contrario de D91/RN-11.
**Recomendación**, sin pisar la unidad de reembolsos:

- **Cobrado** = suma de `monto` de cobros `APROBADO` cuya `fecha_pago` cae en `[desde, hasta]`.
- **Pendiente** y **en mora** = como hoy: cobros creados en el período, en ese estado (D91: «mantienen su
  base actual»).
- **Tasa de cobro** = cobrado *de lo creado en el período* ÷ (eso + pendiente + en mora): es exactamente
  la fórmula actual (todo por `created_at`), ahora con nombre propio para que no se confunda con el
  «cobrado» del encabezado. Un pago posterior al cierre de un período cuenta en la tasa de ese período
  (cohorte «al día de hoy»). Nunca supera 100 % porque numerador ⊆ denominador.
- Los `REEMBOLSADO` **siguen fuera** de «cobrado» hasta que la unidad de reembolsos los reste por fecha de
  devolución. Se documenta como limitación conocida y un test la fija (caso 12): un cobro pagado en
  febrero y reembolsado en marzo hoy no suma en ningún mes; la unidad 5 lo corrige.

`MetricasDeCobros` gana un campo (`cobrado_de_lo_creado`) y `tasa_de_cobro` deja de derivarse de
`cobrado`. La respuesta HTTP no cambia de forma (`cobrado`, `pendiente`, `en_mora`, `tasa_de_cobro`).
Alternativa: contar en la tasa solo los pagos hasta `hasta`: reproduce períodos cerrados pero deja de
contar como pendiente un cobro que hoy está pagado, y el denominador se achica. No la recomiendo.

### 5. El listado sigue filtrando por fecha de creación — **hallazgo H3**

`listar` usa `created_at` para `desde/hasta`. Con «cobrado» por fecha de pago, el encabezado de marzo
suma el cobro de febrero pagado en marzo y la tabla, filtrada por `Pagado`, no lo muestra: encabezado y
tabla dejan de coincidir. Las historias no piden cambiar el listado (RN-01 habla del encabezado).
**Recomendación: no cambiarlo en esta unidad**, y dejar dicho en pantalla qué mide cada número: el
mosaico «Cobrado» lleva la leyenda «por fecha de pago» y la tabla sigue siendo «cobros creados en el
período». Alternativa: filtrar el listado por `fecha_pago` cuando el estado elegido es `Pagado`; es
una decisión de producto que conviene tomar con las historias abiertas.

### 6. ¿El «medio de pago» es el de MercadoPago (tarjeta, dinero en cuenta) o el de la historia?

Las historias lo definen como `LINK_MERCADOPAGO` o `TRANSFERENCIA` (HU-E6-08 RN-01) y la pantalla dice
«medio de pago». MercadoPago informa además `payment_type_id` (tarjeta, etc.); la lista completa de sus
valores **no pude verificarla** (la referencia oficial solo muestra `credit_card` como ejemplo).
**Recomendación: solo los dos valores propios**, `NOT NULL` con `CHECK`, y el vocabulario de MercadoPago
se queda en el ACL (`pasarela.py`). Mostrar «Tarjeta de crédito» sería otra historia y otra verificación.

### 7. ¿Una transferencia y un link pueden repetir el mismo número de operación?

HU-E6-08 RN-03: «la unicidad también cubre los pagos recibidos por link (`mp_payment_id`)», y el
identificador de una operación de MercadoPago y el de un pago están en el mismo espacio de números. Un
índice único solo sobre `numero_de_operacion` no cubre un link contra una transferencia.
**Recomendación:** un índice único por empresa sobre `COALESCE(numero_de_operacion, mp_payment_id)`
(parcial, no nulo), además del `uq_cobro_mp_payment_id` existente (D20). La misma operación sobre el
mismo cobro es una sola fila y no choca; sobre otro cobro, la base lo rechaza. Los cobros por link dejan
`numero_de_operacion` en `NULL` (la pantalla lo muestra solo para transferencias, HU-E6-02 RN-05). Lo que
se paga: un índice sobre expresión, que el ORM debe declarar igual para que Alembic no lo vea distinto
(mismo cuidado que la 0025). Alternativa: llenar `numero_de_operacion` también en los links; duplica el
dato.

### 8. ¿Una corrección de un reembolso puede bajar el estado? — **hallazgo H4 (para el ADR)**

D93 dice que `REEMBOLSADO_PARCIAL` es «un estado estable del que solo se avanza»; HU-E6-05 RN-08 dice que
un error se corrige con un registro nuevo visible. Registrar 1000 en vez de 100 y corregirlo obliga a
volver de `REEMBOLSADO` a `REEMBOLSADO_PARCIAL`. Las dos cosas no caben juntas. **Recomendación (ya
escrita en el ADR-0010, punto 5):** el estado es función del acumulado, así que una corrección puede
bajarlo; «solo se avanza» vale para reembolsos, no para correcciones. Se decide acá porque el ADR se
aprueba antes de cerrar este Gate y la unidad de reembolsos lo consume; esta unidad no escribe código
de eso.

### 9. La pantalla llama «Operación» a la referencia del cobro

`DetalleDeCobro.tsx` muestra «Operación» con `referenciaDeCobro(cobro.id)` (un código derivado del id
del cobro). Con `numero_de_operacion` en pantalla, dos cosas distintas se llamarían igual.
**Recomendación: renombrar esa etiqueta a «Referencia» dentro de esta unidad** (una línea y su test).

## Diseño

- **Dominio** (`payments/domain/cobro.py`):
  - `MedioDePago(StrEnum)`: `LINK_MERCADOPAGO`, `TRANSFERENCIA`.
  - `Cobro`: `pagado_en` pasa a `fecha_pago`; campos nuevos `fecha_pago_aproximada: bool = False`,
    `medio_de_pago: MedioDePago = LINK_MERCADOPAGO`, `numero_de_operacion: str | None = None`.
  - `aprobar(payment_id, ahora, fecha_pago=None)`: la fecha informada se usa **solo si es plausible**
    (con zona horaria, no posterior a `ahora` más 5 minutos de tolerancia de reloj, no anterior a
    `created_at`); si falta o no lo es, `fecha_pago = ahora` y `fecha_pago_aproximada = True`. Se escribe
    una sola vez, en la transición a `APROBADO`; `APROBADO → APROBADO` sigue ausente de la tabla, así
    que un webhook repetido no la toca. `registrar_pago_huerfano` no escribe fecha ni medio.
  - Sin `REEMBOLSADO_PARCIAL`: es de la unidad de reembolsos.
- **Aplicación**: no hay caso de uso nuevo.
  - `PagoRecibido` (ports.py) gana `fecha_aprobacion: datetime | None = None`.
  - `ConfirmarPago._aprobar` pasa `pago.fecha_aprobacion` a `aprobar`; el resto (idempotencia D20,
    saldo D26, bitácora) queda igual. El evento auditable **no** se cambia.
  - `MetricasDeCobros`: campos `cobrado` (por fecha de pago), `pendiente`, `en_mora`,
    `cobrado_de_lo_creado`; `tasa_de_cobro` se calcula con el último. `MetricasDelPeriodo` no cambia de
    firma.
- **Puertos y adaptadores**: sin puerto nuevo.
  - `infrastructure/pasarela.py`: `consultar_pago` traduce `date_approved` (ISO 8601, puede ser `null`;
    fuente: referencia oficial de MercadoPago citada en el ADR) con `datetime.fromisoformat`; sin
    zona horaria, vacío o ilegible → `None` (no se rompe el webhook por un formato). `PasarelaSimulada`
    devuelve la hora actual en UTC para que una demo local no muestre «aproximada».
  - `infrastructure/repositories.py`: `_a_dominio`/`_a_fila` con los campos nuevos; `metricas` con dos
    agregaciones sumadas **en la base**, en `Decimal`, sin pasar por `float`.
  - `infrastructure/models.py`: columnas, `CHECK` e índice declarados igual que la migración.
- **Otros contextos**: solo lectura desde `reporting`, por un edge que el Context Map ya permite
  (`reporting → payments`, `docs/architecture.md` §4) y que hoy pasa por `reporting/infrastructure/acl.py`
  con `MetricasDelPeriodo`. `CobranzasViaPayments.totales` hereda «cobrado» por fecha de pago **sin
  cambiar una línea** (el tablero de reportería cambia de significado, que es lo que D98 quiere); `filas`
  cambia `pagado_en` → `fecha_pago`. No hace falta ADR por edge; el ADR-0010 es por el modelo.
- **Frontend** (`features/payments`, sin importar otro feature, R5):
  - `api/cobro.ts`: `pagado_en` → `fecha_pago`; `fecha_pago_aproximada`, `medio_de_pago`
    (`"LINK_MERCADOPAGO" | "TRANSFERENCIA"`), `numero_de_operacion: string | null`; etiquetas
    «Link de MercadoPago» y «Transferencia».
  - `components/DetalleDeCobro.tsx`: filas «Medio de pago», «Fecha de pago» (con «(aproximada)» cuando
    corresponde y «—» si no se pagó) y «N.º de operación» **solo** si el medio es `TRANSFERENCIA`; la
    etiqueta «Operación» pasa a «Referencia» (pregunta 9). Sin acciones nuevas; Solo Lectura ve lo mismo.
  - `components/ListadoDeCobros.tsx`: leyenda «por fecha de pago» en el mosaico «Cobrado» (pregunta 5).
  - `index.ts`: sin cambios en lo que exporta. Rutas: sin cambios.

## Infraestructura

- **Migraciones**: `backend/migrations/versions/0026_fecha_medio_y_operacion_de_pago.py`
  (`down_revision = "0025"`).
  1. `ALTER TABLE cobro RENAME COLUMN pagado_en TO fecha_pago`.
  2. `fecha_pago_aproximada boolean NOT NULL DEFAULT false`; `medio_de_pago varchar(30) NOT NULL DEFAULT
     'LINK_MERCADOPAGO'` con `CHECK (medio_de_pago IN ('LINK_MERCADOPAGO','TRANSFERENCIA'))`;
     `numero_de_operacion varchar(120) NULL`.
  3. Backfill: `UPDATE cobro SET fecha_pago_aproximada = true WHERE fecha_pago IS NOT NULL`. Nada más;
     el `DEFAULT` da `LINK_MERCADOPAGO` a las filas viejas (ver pregunta 2).
  4. `CHECK ck_cobro_fecha_de_pago`: `estado NOT IN ('APROBADO','REEMBOLSADO') OR fecha_pago IS NOT NULL`,
     **`NOT VALID`**, con `NOTICE` por empresa de las filas que lo violan, y
     `CHECK (fecha_pago_aproximada = false OR fecha_pago IS NOT NULL)`. Se usa el mismo mecanismo que la
     0025; el `VALIDATE` queda para una migración posterior cuando el informe dé cero.
  5. `CREATE UNIQUE INDEX uq_cobro_operacion ON cobro (empresa_id, (COALESCE(numero_de_operacion,
     mp_payment_id))) WHERE COALESCE(numero_de_operacion, mp_payment_id) IS NOT NULL`.
  - **Reversible**: `downgrade` quita índice y restricciones, borra las tres columnas nuevas y
    devuelve `fecha_pago` → `pagado_en`. Pierde solo lo derivado (medio y marca de aproximada).
  - RLS y grants: no hay tabla nueva; la política `aislamiento_por_empresa` y `GRANT SELECT, INSERT,
    UPDATE` de la 0019 cubren las columnas nuevas. `empresas_con_cobros_abiertos()` no referencia
    `pagado_en`. El `CHECK ck_cobro_reembolso` no se toca.
  - El despliegue es una sola instancia y el renombrado es incompatible con el código viejo: migración y
    código salen en el mismo release (lo hace la CI de staging, ADR-0006).
- **Trabajo asíncrono**: no aplica. Ninguna tarea nueva; los barridos de vencimiento y recordatorios no
  leen la fecha de pago.
- **Configuración**: no aplica. Sin variables nuevas ni cambios en `.env.example`.
- **Integraciones externas**: no se agrega ninguna llamada. `consultar_pago` ya existe, con su timeout,
  reintentos con backoff y aplanado de fallas (`_pedir`); solo se lee un campo más de la misma
  respuesta. Sandbox vs producción: no hay diferencia conocida en `date_approved`; **no verificado** en
  sandbox (ver «Riesgos»).

## Riesgos que obligan a tests (marcar los que apliquen)
- [x] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → las agregaciones de «cobrado» y tasa se
  suman en la base sobre `NUMERIC` y viajan como `Decimal`; caso con `0.10 + 0.20` que no da
  `0.30000000000000004` y caso de redondeo de la tasa (`ROUND_HALF_UP` a dos decimales, ya en
  `MetricasDeCobros.tasa_de_cobro`, sin cambiar)
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [x] Consume un webhook → un mismo evento, un solo efecto: el webhook repetido **no cambia**
  `fecha_pago`, ni con el mismo `payment_id` (primera línea, D20) ni con otro sobre un cobro ya cerrado
  (segunda línea); y `date_approved` ilegible no rompe el webhook (200 con fecha aproximada)
- [x] Agrega datos con `empresa_id` → aislamiento entre empresas: el índice único es por empresa (mismo
  número en dos empresas convive) y «cobrado» de una empresa no suma pagos de otra (RLS)
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales a un LLM → no aplica; ni el pagador ni su identificación se persisten

Riesgos que no son tests, dichos con todas las letras:
- **Una fecha equivocada mueve plata de período.** Por eso la fecha de MercadoPago solo se acepta si es
  plausible y, si no, se marca aproximada en lugar de guardarla como cierta.
- **No está verificado** que `date_approved` venga siempre poblado en un pago `approved` ni su zona
  horaria exacta en Argentina (la referencia solo muestra un ejemplo en UTC); el código lo trata como
  opcional y exige zona horaria. A comprobar en sandbox al implementar, y anotar el resultado acá.
- **Filas existentes**: quedan aproximadas; la tasa y el «cobrado» de los meses históricos usan esa
  fecha. Cualquier `APROBADO` sin fecha se informa y no se completa.
- **Renombrado de columna**: si la migración corre sin el código nuevo (o al revés), el cobro falla.
  Mitigación: mismo release; el test de migración sube y baja.
- **Idempotencia preexistente, no tocada**: dos webhooks simultáneos del mismo pago pueden chocar en el
  índice único y devolver 500 en el segundo (MercadoPago reintenta y ahí se resuelve por
  `buscar_por_payment_id`). No se cambia; se anota.

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/payments/domain/cobro.py` (`MedioDePago`, `fecha_pago`, `aprobar`)
- [x] `backend/src/cheatsheet/contexts/payments/application/ports.py` (`PagoRecibido`, `MetricasDeCobros`)
- [x] `backend/src/cheatsheet/contexts/payments/application/confirmacion.py`
- [x] `backend/src/cheatsheet/contexts/payments/application/cobros.py` (solo el docstring de `MetricasDelPeriodo`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/pasarela.py` (`date_approved`, simulada)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/models.py`
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/repositories.py` (`metricas`, mapeos)
- [x] `backend/migrations/versions/0026_fecha_medio_y_operacion_de_pago.py` (nuevo)
- [x] `backend/src/cheatsheet/api/routers/cobros.py` (`CobroSalida`)
- [x] `backend/src/cheatsheet/contexts/reporting/infrastructure/acl.py` (`filas`: `fecha_pago`)
- [x] `backend/tests/contexts/payments/domain/test_cobro.py`
- [x] `backend/tests/contexts/payments/application/test_confirmacion.py` (`CobrosFalsos.metricas`, `PasarelaFalsa`)
- [ ] `backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py` (sin cambios: usa `CobrosFalsos` de `test_confirmacion.py`)
- [x] `backend/tests/contexts/payments/application/test_metricas.py` (nuevo: `tasa_de_cobro` y `cobrado_de_lo_creado`)
- [x] `backend/tests/contexts/payments/infrastructure/test_pasarela_contrato.py`
- [x] `backend/tests/integracion/test_cobros_postgres.py`
- [x] `backend/tests/integracion/test_migracion_0026.py` (nuevo: backfill, sube/baja/sube y NOTICE)
- [x] `backend/tests/integracion/test_api_cobros_fecha_de_pago.py` (nuevo, caso 20)
- [x] `backend/tests/contexts/reporting/infrastructure/test_cobranzas_via_payments.py` (nuevo, caso 22)

### Frontend
- [x] `frontend/src/features/payments/api/cobro.ts`
- [x] `frontend/src/features/payments/components/DetalleDeCobro.tsx`
- [x] `frontend/src/features/payments/components/ListadoDeCobros.tsx`
- [x] `frontend/src/features/payments/api/__tests__/cobro.test.ts`
- [x] `frontend/src/features/payments/components/__tests__/pantallas.test.tsx`
- [x] `frontend/src/app/(panel)/cobros/__tests__/pagina.test.tsx`

### Docs
- [x] `docs/adr/0010-payment-date-method-and-refunds.md` (el borrador adjunto, en `Proposed`; pasa a `Accepted` al aprobarse el PR)
- [x] `docs/adr/README.md` (una fila en el índice)
- [ ] `docs/aidlc/units.md` (fila de la unidad: `Responsable`, `Rama`, estado) — no se toca en esta pasada

## Casos de prueba

Modo: **test primero**. Los casos marcados RED tienen que fallar antes de tocar el código. Los de
integración (PostgreSQL) se escriben y corren en CI si el entorno local no tiene base; el estado dice
honestamente cuál se observó.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: `aprobar` con la fecha de MercadoPago → `fecha_pago` es esa fecha, `fecha_pago_aproximada` es `False`, `medio_de_pago` es `LINK_MERCADOPAGO` | unit (dominio) | RED observado (ImportError de `MedioDePago` al recolectar) → verde |
| 2 | RED: `aprobar` sin fecha → `fecha_pago = ahora` y `fecha_pago_aproximada = True` | unit (dominio) | RED observado (ídem) → verde |
| 3 | RED: fecha sin zona horaria, en el futuro (más de 5 min) o anterior a `created_at` → se ignora, `fecha_pago = ahora`, aproximada | unit (dominio) | RED observado (ídem; tres variantes parametrizadas, más la tolerancia de 5 min inclusiva) → verde |
| 4 | RED: aprobar dos veces sigue rechazado y la segunda no toca `fecha_pago` | unit (dominio) | RED observado (ídem) → verde |
| 5 | RED: `registrar_pago_huerfano` no escribe `fecha_pago` (y el cobro sigue `CANCELADO`) | unit (dominio) | RED observado (ídem) → verde |
| 6 | RED: `consultar_pago` traduce `date_approved` con offset (`-04:00`) y con `Z` a la misma hora UTC correcta; `null`, ausente o basura → `None` | unit (contrato del adaptador, `MockTransport`) | RED observado (falló la conversión a UTC y el doble) → verde |
| 7 | RED: `ConfirmarPago` con un pago que trae fecha → el cobro guarda esa fecha | unit (aplicación) | RED observado (`fecha_pago` no se propagaba) → verde |
| 8 | Webhook duplicado (mismo `payment_id`) → un solo efecto, `fecha_pago` intacta; otro `payment_id` sobre un cobro ya aprobado → `ya_procesado` y `fecha_pago` intacta | unit (aplicación) | verde (los dos caminos de idempotencia, con la fecha intacta); no era RED: el dominio ya no reescribe la fecha |
| 9 | Un `date_approved` ilegible no rompe el webhook: se aprueba con fecha aproximada | unit (aplicación) | verde (`None` de un `date_approved` ilegible y fecha futura); no era RED: el comportamiento por defecto ya aproximaba |
| 10 | RED: `tasa_de_cobro` se calcula con `cobrado_de_lo_creado`, no con `cobrado`; con `cobrado` (por fecha de pago) mayor que lo creado en el período la tasa no pasa de 100 %; período vacío → `0.00` | unit | RED observado (`MetricasDeCobros` sin `cobrado_de_lo_creado`; 6 tests) → verde |
| 11 | RED: cobro creado en febrero y pagado en marzo → mirando marzo suma en «cobrado» y mirando febrero no; su tasa de febrero lo incluye | integración (PostgreSQL) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 12 | Limitación fijada: un cobro `REEMBOLSADO` no suma en «cobrado» de ningún período (lo cambia la unidad de reembolsos) | integración (PostgreSQL) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 13 | «Pendiente» y «en mora» siguen midiéndose por `created_at`; el filtro de estado del listado no altera las métricas | integración (PostgreSQL) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 14 | Los importes de las métricas son `Decimal` de punta a punta: `0.10 + 0.20` da `0.30`, nunca un `float` | unit + integración | unit verde; integración escrita, **no corrida** (sin PostgreSQL local) |
| 15 | RED: el mismo número como `numero_de_operacion` de un cobro y `mp_payment_id` de otro **de la misma empresa** → el índice único rechaza; en **otra empresa** convive | integración (PostgreSQL) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 16 | RED: `medio_de_pago` fuera de los dos valores, y un `APROBADO` nuevo sin `fecha_pago`, son rechazados por la base | integración (PostgreSQL) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 17 | RED: migración sobre datos viejos: `APROBADO`/`REEMBOLSADO` conservan la fecha y quedan aproximados; `PENDIENTE`/`CANCELADO` sin fecha y sin marca; todos `LINK_MERCADOPAGO`; `numero_de_operacion` en `NULL` | integración (PostgreSQL, migración) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 18 | La migración sube, baja y vuelve a subir; al bajar `fecha_pago` vuelve a llamarse `pagado_en` con sus valores | integración (migración) | escrito, **no corrido** (sin PostgreSQL local); corre en CI. SQL de subida y bajada revisado con `alembic ... --sql` |
| 19 | Un `APROBADO` viejo sin fecha se informa por `NOTICE` y la migración no falla ni lo completa | integración (migración) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 20 | `GET /cobros/{id}` de un cobro pagado devuelve `fecha_pago`, `fecha_pago_aproximada`, `medio_de_pago` y `numero_de_operacion = null`; los tres roles leen | integración (API) | escrito, **no corrido** (sin PostgreSQL local); corre en CI. Solo Administrador por HTTP: la ruta de lectura no consulta el rol |
| 21 | «Cobrado» de una empresa no suma pagos de otra (RLS) | integración (PostgreSQL) | escrito, **no corrido** (sin PostgreSQL local); corre en CI |
| 22 | Reporting: `CobranzasViaPayments.totales` refleja el nuevo «cobrado» y `filas` usa `fecha_pago` | unit (aplicación/ACL) | verde; no fue RED (se escribió después del cambio de `acl.py`) |
| 23 | RED: `DetalleDeCobro` de un cobro pagado por link muestra «Link de MercadoPago» y la fecha, sin «N.º de operación» | unit (frontend) | RED observado (16 fallas del bloque) → verde |
| 24 | RED: con `fecha_pago_aproximada` muestra «(aproximada)»; un cobro sin pagar muestra «—» | unit (frontend) | RED observado → verde |
| 25 | RED: con `medio_de_pago = TRANSFERENCIA` y número de operación, el detalle muestra ese número | unit (frontend) | RED observado → verde |
| 26 | La etiqueta que antes decía «Operación» dice «Referencia» | unit (frontend) | RED observado → verde |
| 27 | El mosaico «Cobrado» lleva la leyenda «por fecha de pago» | unit (frontend) | RED observado → verde |
| 28 | `PasarelaSimulada.consultar_pago` devuelve una fecha real (no aproximada) | unit | RED observado (`fecha_aprobacion` era `None`) → verde |
| 29 | En el navegador (`run-local`, con la pasarela simulada): generar un cobro, simular el webhook, ver medio y fecha en el detalle y el encabezado del período | manual | pendiente, para quien revise |
| 30 | En sandbox de MercadoPago: un pago `approved` real trae `date_approved` con zona horaria y coincide con el detalle | manual (sandbox) | pendiente; anotado como no verificado en `TODO.md` §20.2 y §20.8 |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-30 | aprobado junto con ADR-0010; las nueve preguntas según la recomendación |
| 2 · Verificación | | Incluye un **verificador independiente** (agente distinto del que implementó, con conocimiento de `payments`): revisa el diff contra este plan y las historias, corre las verificaciones y reporta huecos de prueba, sobre todo en dinero, webhook y migración |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- P1: `pagado_en` se renombra a `fecha_pago` (una sola fuente de verdad; migración y código en el mismo release).
- P2: los cobros ya pagados conservan la fecha de `pagado_en`, marcada `fecha_pago_aproximada = true`; la migración no consulta a MercadoPago.
- P3: la migración 0026 lleva solo lo que usa esta unidad; la tabla `reembolso` y `REEMBOLSADO_PARCIAL` van en `reembolsos-parciales-y-manuales`.
- P4: «Cobrado» se mide por `fecha_pago` en el período; pendiente y en mora siguen por fecha de creación; la tasa de cobranza es la fórmula de cohorte, sin superar el 100 %.
- P5: el listado sigue filtrando por fecha de creación, con la aclaración «por fecha de pago» en la tarjeta de Cobrado.
- P6: `medio_de_pago` es un conjunto cerrado de dos valores: `LINK_MERCADOPAGO` y `TRANSFERENCIA`.
- P7: el índice único por empresa cubre el número de operación de link y de transferencia juntos.
- P8: una corrección puede bajar el estado de reembolso (estado derivado del acumulado; ADR-0010).
- P9: la etiqueta «Operación» pasa a «Referencia».
- Lo que no se pudo verificar contra MercadoPago quedó en `docs/aidlc/TODO.md` §20 (20.2 a 20.4), para recorrerlo cuando esté el sandbox.
