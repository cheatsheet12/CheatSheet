# Unidad: indicadores-de-cobranza

**HUs**: HU-E10-01 (modificada por ADR-0009) **Contexto dueño**: reporting (con una lectura nueva en payments por su capa de aplicación) **Rama**: feature/reporting-indicadores-de-cobranza

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D98 (`docs/aidlc/epicas/09-reporteria-y-paquete-contable/decisiones.md:318-336`) y la
> definición de «cobrado» del [ADR-0010](../../adr/0010-payment-date-method-and-refunds.md) punto 6.
> La rama sale de `feature/payments-reembolsos-parciales-y-manuales` (cadena de ramas: PR #51 sobre #50
> sobre #49 sobre #48 sobre #45); su PR apunta a esa rama y pasa a `develop` cuando la cadena llegue.
> El mapa pide `fecha-de-pago`; esta unidad **también asume** la tabla `reembolso` y el «cobrado» neto
> de `reembolsos-parciales-y-manuales` (P7 de esa unidad). Si la cadena se reordena, eso es lo primero
> que hay que volver a revisar. Tamaño: M.

## Qué hace

Hoy el tablero de Reportes (PAN-REP-01) ya muestra «cobrado» por fecha de pago y neto de reembolsos,
porque reusa `MetricasDelPeriodo` (`reporting/infrastructure/acl.py:178-185`). Pero no tiene gráficos
de cobranza, no expone la tasa de cobro y considera «sin actividad» algunos períodos que sí tuvieron
cobros. Además, Inicio no muestra el resumen de cobros ni tiene selector de período: siempre muestra el
mes en curso (`frontend/src/app/(panel)/panel/page.tsx:69`). Esta unidad agrega a Reportes «cobrado por
semana» (neto, por fecha de pago y de devolución) y «cobros por estado» (lo creado en el período,
agrupado por su estado actual). También hace que Inicio muestre el resumen de cobros con el mismo
selector y las **mismas cifras** que Reportes, porque las dos pantallas leen la misma ruta.

**Lo que la historia pide, textual** (`docs/aidlc/inputs/historias-de-usuario.md:2047-2069`):
- RN-06: «La pantalla Inicio (código de pantalla a confirmar) muestra el resumen de cobros con el mismo
  selector de período que Reportes (por defecto, el mes en curso), usando la misma definición de métricas.»
- RN-07: «Reportes incluye visualizaciones de cobranza que siguen el período seleccionado: cobrado por
  semana y cobros por estado.»
- RN-08: «“Cobrado”, incluido el “total cobrado” de RN-02 y el “cobrado por semana”, se mide por fecha de
  pago, y los reembolsos restan en el período en que se devolvió el dinero (HU-E6-05 RN-11). “Cobros por
  estado” agrupa los cobros creados en el período por su estado actual y lo indica en el subtítulo del
  gráfico. La tasa de cobro se calcula solo sobre los cobros creados en el período, de modo que no puede
  superar el 100 % (HU-E6-01 RN-01).»
- Criterios nuevos: «Ingreso a Inicio → Veo el resumen de cobros del mes en curso con un selector de
  período»; «Cambio el período en Inicio → El resumen se actualiza con las mismas cifras que Reportes para
  ese período»; «Ingreso a Reportes → Veo “cobrado por semana” y “cobros por estado” además de
  facturación»; «Cambio el período → Ambos gráficos de cobranza se actualizan»; «Un cobro se pagó dentro
  del período pero se creó antes → Aparece en “cobrado” del período del pago»; «El período seleccionado
  solo tiene cobros y ningún comprobante → Veo las métricas de cobranza en lugar del mensaje de período sin
  actividad».

**Lo que ya existe y no se toca:** «total cobrado» por fecha de pago y neto
(`payments/infrastructure/repositories.py:180-222`, ADR-0010 punto 6), la variación contra el período
anterior (`reporting/application/tablero.py:33-50`, D52), el selector de Reportes (`Tablero.tsx:106-128`),
el acceso de Solo Lectura y del contador (RN-04, RN-05), y el criterio «un cobro pagado en el período
pero creado antes», que ya cumple `fecha-de-pago` (su caso 11). Acá solo se agrega una prueba de punta a
punta desde el tablero.

**Fuera de esta unidad:**
- El período por defecto de PAN-COB-01, que sale de `ahora.replace(day=1)` en UTC
  (`payments/application/cobros.py:118-123`), y las métricas de PAN-COB-01 en general (HU-E6-01). Es un
  hallazgo y se anota. RN-06 compara Inicio con Reportes, no con PAN-COB-01.
- Gráficos de cobranza dentro del resumen ejecutivo y del paquete contable (HU-E10-03/04 no los piden).
- El desglose «por medio de pago» que muestra el prototipo de reportes: ninguna historia lo pide.
- Que el listado de PAN-COB-01 filtre por fecha de pago (P5 de `fecha-de-pago`).
- Un índice sobre `cobro.fecha_pago` (ver «Riesgos»).

## Las preguntas que el mapa dejó para este Gate

### 1. ¿Qué código de pantalla lleva Inicio? (D98: «hay que asignar el código de pantalla de Inicio»)

La historia dice «código a confirmar», pero el código ya existe en los insumos: `prototipos.md:52` asigna
`dashboard.html` a **PAN-DSH-01**, y `frontend/src/app/(panel)/panel/page.tsx:2` ya se presenta como
«PAN-DSH-01 — el inicio del panel». **Recomendación: PAN-DSH-01.** Se anota en esta unidad y en la
nota de D98; la historia no se reescribe (los insumos son de solo lectura). Alternativa: un código nuevo
(`PAN-INI-01`). No lo recomiendo: rompe la trazabilidad con el prototipo.

### 2. ¿Cómo funciona el selector de período en Inicio, y qué parte de la pantalla lo sigue?

Hoy Inicio es un componente de servidor que pide `/reporteria/tablero` sin parámetros (`page.tsx:69`) y
muestra facturación, «Cobros pendientes», turnos y operaciones (`page.tsx:103-138`). No muestra «cobrado».
**Recomendación:**
- El período vive en la URL (`/panel?desde=AAAA-MM-DD&hasta=AAAA-MM-DD`). La página lo lee, lo manda a
  la misma ruta y **toda** la pantalla lo sigue: la línea del período, las tarjetas y el resumen.
- El selector es el mismo componente que usa Reportes. `SelectorDePeriodo` se extrae de
  `Tablero.tsx:106-128` y el feature lo exporta. En Inicio lo envuelve un cliente mínimo que hace
  `router.replace` de la URL.
- Se agrega un bloque «Cobros del período» (`ResumenDeCobros`): cobrado (con variación), pendiente, en
  mora y tasa de cobro, las cuatro cifras de PAN-COB-01. Reemplaza la tarjeta «Cobros pendientes», que
  quedaría repetida.

Así «mismas cifras que Reportes» vale por construcción: misma ruta, mismo período. Alternativa: un
componente de cliente que cambia solo el bloque de cobros. Deja dos períodos distintos en la misma
pantalla (cobros de marzo junto a facturación de septiembre). No lo recomiendo.

### 3. «Cobros por estado»: ¿monto o cantidad?

La historia no lo dice. **Recomendación: por monto, con la cantidad en el rótulo** («Pagado · $ 120.000 ·
8 cobros»). Con monto, las barras de Pendiente y En mora son exactamente las tarjetas «Pendiente» y «En
mora», y la suma de los tres estados pagados es el numerador de la tasa. El gráfico cuadra con el resto de
la pantalla, y `Distribucion` (`Graficos.tsx:162-208`) ya dibuja importes. El backend devuelve las dos
cosas, así que cambiar de opinión es solo de pantalla. Alternativa: solo cantidad. Se lee más fácil («8
pagados, 3 pendientes»), pero no se puede cruzar con ninguna otra cifra del tablero.

### 4. ¿Dónde se muestra la tasa de cobro?

RN-08 la define y el tablero hoy no la expone. **Recomendación:** en Inicio, como cuarta cifra del
resumen (pregunta 2). En Reportes, en el **subtítulo de «Cobros por estado»**: «Cobros creados en el
período, por su estado actual · tasa de cobro 72,50 %». Es la misma población (lo creado en el período),
y ponerla junto a «Cobrado», que se mide por fecha de pago, invita a leerla como cobrado ÷ algo.
Alternativa: una séptima tarjeta en Reportes. Rompe la grilla de seis que `Tablero.tsx:12-16` justifica.

### 5. El «mes en curso» se calcula en UTC — **hallazgo H1**

`api/routers/reporteria.py:309` (tablero), `:330` (previsualización) y `:388` (generar reporte) usan
`ahora().date()`, y `api/routers/contador.py:118` usa `ahora.date()`. El reloj devuelve UTC
(`shared/clock.py:22-31`). Entre las 21:00 y las 24:00 del último día del mes (hora argentina), el período
por defecto ya es **el mes siguiente**, justo en el momento en que alguien mira el cierre. En cambio, los
límites del período sí se cortan en hora argentina (`acl.py:62`, `ZONA_DEL_REPORTE`).
**Recomendación: corregirlo acá.** El default «mes en curso» es RN-01 y RN-06 de esta misma historia, y
el arreglo es convertir a `ZONA_DEL_REPORTE` antes de `.date()` en los cuatro lugares (un solo helper),
con un test de reloj fijo. Alternativa: anotarlo y dejarlo. En ese caso Inicio abriría en el mes
equivocado tres horas por mes.

## Diseño

- **Dominio**: sin cambios. `reporting` no tiene agregado para esto (D51: solo lee), y en `payments` no
  cambia nada del dominio.
- **Aplicación — payments** (módulo nuevo `payments/application/cobranza_del_periodo.py`. No va en
  `ports.py`, que tiene 400 líneas, ni en `cobros.py`, que tiene 415; mismo criterio que H8 de
  `reembolsos-parciales-y-manuales`):
  - `CobrosDeUnEstado(cantidad: int, monto: Decimal)` y
    `DetalleDeCobranza(cobrado_por_dia: dict[date, Decimal], por_estado: dict[EstadoCobro, CobrosDeUnEstado])`.
  - `PortConsultasDeCobranza(Protocol)`: `cobrado_por_dia(filtros, zona: tzinfo)` y `por_estado(filtros)`.
    Solo lectura.
  - `DetalleDeCobranzaDelPeriodo(consultas).ejecutar(*, filtros, zona) -> DetalleDeCobranza`. Garantiza
    que `filtros.estados` no interviene (igual que `metricas`) y devuelve `por_estado` en el orden de
    declaración de `EstadoCobro`, para que el gráfico tenga un orden estable sin que reporting nombre el
    enum.
  - **La misma definición que `metricas`**: `cobrado_por_dia` = Σ `monto` de `ESTADOS_PAGADOS` por día
    local de `fecha_pago` − Σ `reembolso.monto` por día local de `fecha_devolucion` (las correcciones,
    negativas, suman de vuelta; puede dar negativo). `por_estado` = cantidad y Σ `monto` de lo **creado**
    en el período, por `estado` actual, con los seis estados posibles (`CANCELADO` incluido). La suma de
    los días es `cobrado`; las filas `PENDIENTE`/`VENCIDO` son `pendiente`/`en_mora`; la suma de las tres
    pagadas es `cobrado_de_lo_creado`. Un test de PostgreSQL fija esas identidades.
- **Aplicación — reporting**:
  - `application/ports.py`: `TotalesDeCobranzas` gana `tasa_de_cobro: Decimal = Decimal("0.00")`. Hay un
    dataclass nuevo, `DetalleDeCobranzas(por_semana: dict[str, Decimal], por_estado: dict[str,
    CobrosPorEstado])`. `PortCobranzas.detalle(periodo)` se agrega y sigue siendo de solo lectura.
  - `application/tablero.py`: `Tablero` gana `tasa_de_cobro`, `cobrado_por_semana` y `cobros_por_estado`.
    `VerTablero` pide `detalle` **solo del período actual**: la variación es de las cifras del
    encabezado, no de los gráficos. `sin_actividad` (`tablero.py:74-79`) además exige
    `not cobros_por_estado and not cobrado_por_semana`, así que un período con cobros creados, o con un
    pago y un reembolso que se anulan en el neto, **no** es «sin actividad». `PrevisualizarReporte` no
    cambia.
- **Puertos y adaptadores**:
  - `payments/infrastructure/consultas_de_cobranza.py` (nuevo): `ConsultasDeCobranzaPostgres(sesion)`,
    con tres agregaciones **en la base** y en `Decimal`. Pagos por
    `date(timezone(:zona, fecha_pago))`, devoluciones por `date(timezone(:zona, fecha_devolucion))` sin
    join contra `cobro` (ADR-0010 punto 6), y creados por `estado` con `count(*)` y
    `coalesce(sum(monto), 0)`. Reusa `ESTADOS_PAGADOS` y el recorte por período de `repositories.py`
    (`_en_periodo` pasa de método estático a función del módulo, sin cambiar lo que hace). No va dentro
    de `RepositorioCobroPostgres` porque ese archivo tiene 363 líneas.
  - `reporting/infrastructure/acl.py`: `CobranzasViaPayments(cobros, consultas)`. `totales` pasa además
    `metricas.tasa_de_cobro`. `detalle` llama a `DetalleDeCobranzaDelPeriodo` con `_limites(periodo)` y
    `ZONA_DEL_REPORTE`, agrupa los días en semanas ISO con la **misma etiqueta** `2026-W09` que la
    facturación (un `_semana_del_dia(dia: date)` hermano de `_semana_de`, `acl.py:100-103`; las sumas son
    de `Decimal`) y lee los estados por atributo (`.value`), sin nombrar tipos de payments (R3).
  - `api/reporteria.py:59-60` (`armar_cobranzas`): se conecta el adaptador nuevo. Es la composition root,
    que ya importa `RepositorioCobroPostgres`.
- **Otros contextos**: solo `reporting → payments`, por `application/`, el mismo edge que ya usa
  `acl.py:43-44` y que el Context Map permite (`docs/architecture.md` §4). Sin ADR.
- **HTTP**: `GET /reporteria/tablero` suma `tasa_de_cobro: str`, `cobrado_por_semana: dict[str, str]` y
  `cobros_por_estado: dict[str, {cantidad: int, monto: str}]`. Los importes viajan como texto, como el
  resto (`routers/reporteria.py:112-117`). El cambio es aditivo, y la ruta del contador (`contador.py`) lo
  recibe sin cambios de comportamiento (son totales: nada identifica a un cliente, RN-04). `MetricaSalida`,
  `TableroSalida` y `tablero_salida` se mudan a `api/routers/tablero_salida.py` porque
  `routers/reporteria.py` tiene 590 líneas; `contador.py:38-44` actualiza su import. Si se acepta P5, el
  período por defecto se calcula en `ZONA_DEL_REPORTE` en `reporteria.py:309`, `:330`, `:388` y
  `contador.py:118`.
- **Frontend** (`features/reporting`; importa de otro feature solo por su `index.ts`, R5; precedente:
  `billing/components/ElegirCliente.tsx:23`):
  - `api/reporte.ts`: el tipo `Tablero` gana los tres campos.
  - `components/SelectorDePeriodo.tsx` (nuevo, exportado): los dos campos «Desde/Hasta» y el resumen del
    rango, sacados de `Tablero.tsx:106-128` sin cambiar su comportamiento.
  - `components/Tablero.tsx`: usa `SelectorDePeriodo` y suma dos paneles. «Cobrado por semana»
    («Lo cobrado en cada semana, por fecha de pago, menos lo devuelto») usa `BarrasPorSemana` con
    `etiquetaDeSemana`/`nombreDeSemana`. «Cobros por estado» (subtítulo de P3/P4) usa `Distribucion` con
    `ETIQUETAS_DE_ESTADO` de `@/features/payments` («Pagado», «En mora», …).
  - `components/Graficos.tsx`: `BarrasPorSemana` recibe la nota del dato único por prop (hoy dice
    «facturación» fijo, `Graficos.tsx:131`). Una semana **negativa** se dibuja con
    `rep-barras__barra--negativa` y el monto con signo (hoy `escalaDe` toma `abs`, `Graficos.tsx:51`, y la
    dibujaría igual que una positiva). `Distribucion` acepta un rótulo secundario (la cantidad) y su nota
    de dato único por prop (`Graficos.tsx:173`).
  - `components/ResumenDeCobros.tsx` (nuevo, exportado): cobrado con variación, pendiente, en mora y tasa,
    con `Cifra`.
  - `index.ts`: exporta `SelectorDePeriodo` y `ResumenDeCobros`.
  - `app/(panel)/panel/page.tsx` (PAN-DSH-01): lee `searchParams` y pasa `desde/hasta`. Agrega
    `SelectorDePeriodoEnUrl.tsx` (cliente, local a la ruta, como `iconos.tsx`) y `ResumenDeCobros`, y
    retira la tarjeta «Cobros pendientes» (P2).
  - `shared/pantallas-reportes.css`: la barra negativa.

## Infraestructura

- **Migraciones**: no aplica. No hay tablas ni columnas nuevas; las consultas usan lo que dejaron la 0026
  y la 0027. La **0028 queda libre**. `reembolso` ya tiene `ix_reembolso_empresa_fecha` (0027); `cobro`
  no tiene índice sobre `fecha_pago` ni `created_at`, igual que la métrica actual (ver «Riesgos»).
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica. Sin variables nuevas.
- **Integraciones externas**: no aplica. Ninguna llamada a MercadoPago.

## Riesgos que obligan a tests (marcar los que apliquen)
- [x] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → sumas por día en la base sobre `NUMERIC`; el
  agrupado a semana suma `Decimal` (nunca `float`); `0.10 + 0.20` en un mismo día da `0.30`; la tasa se
  sigue redondeando en `MetricasDeCobros.tasa_de_cobro` (`payments/application/ports.py:66-84`), sin
  recalcularla; el frontend no suma importes que se muestren
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [x] Agrega datos con `empresa_id` → no agrega filas, pero lee nuevas agregaciones: el cobrado por día y
  los cobros por estado de una empresa no suman los de otra (RLS)
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales a un LLM → no aplica; el tablero son totales (RN-04)

Riesgos que no son tests, dichos con todas las letras:
- **Dos consultas definen «cobrado»** (`metricas` y `cobrado_por_dia`). Si una cambia sin la otra, el
  encabezado y el gráfico dejan de cuadrar. Mitigación: comparten `ESTADOS_PAGADOS` y el recorte de
  período, y un test de PostgreSQL afirma `Σ cobrado_por_dia = metricas.cobrado` (y las otras identidades).
- **Borde de día**: el día se corta en hora argentina dentro de la base. Un pago del 31/3 a las 23:30
  (hora argentina, 02:30 UTC del 1/4) es del 31/3 y de la semana del 31/3, igual que en `_limites`.
- **Semanas recortadas**: la primera y la última semana del período pueden quedar parciales. Es lo mismo
  que ya pasa con la facturación por semana (RN-03).
- **Fechas históricas aproximadas**: los cobros anteriores a la 0026 tienen `fecha_pago` aproximada, y
  las devoluciones anteriores a la 0027, `updated_at`. Sus semanas pueden estar corridas. No se corrige.
- **Rendimiento**: el tablero pasa de 8 a 10 consultas (dos más solo para el período actual), sin índice
  sobre `cobro.fecha_pago`. Es aceptable con el volumen de una PyME y la métrica actual ya hace lo mismo.
  Si hace falta, el índice `(empresa_id, fecha_pago)` es una migración chica y aparte.
- **«Cobrado» negativo** en una semana o en el período se muestra con signo (P7 de reembolsos).

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/payments/application/cobranza_del_periodo.py` (nuevo: caso de uso, puerto y tipos)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/consultas_de_cobranza.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/repositories.py` (`_en_periodo` a función del módulo)
- [ ] `backend/src/cheatsheet/contexts/reporting/application/ports.py` (`tasa_de_cobro`, `DetalleDeCobranzas`, `PortCobranzas.detalle`)
- [ ] `backend/src/cheatsheet/contexts/reporting/application/tablero.py` (`Tablero`, `VerTablero`, `sin_actividad`)
- [ ] `backend/src/cheatsheet/contexts/reporting/infrastructure/acl.py` (`CobranzasViaPayments.detalle`, `_semana_del_dia`)
- [ ] `backend/src/cheatsheet/api/reporteria.py` (`armar_cobranzas`)
- [ ] `backend/src/cheatsheet/api/routers/tablero_salida.py` (nuevo) y `routers/reporteria.py` (mudanza; período por defecto, P5)
- [ ] `backend/src/cheatsheet/api/routers/contador.py` (import; período por defecto, P5)
- [ ] `backend/tests/contexts/payments/application/test_cobranza_del_periodo.py` (nuevo)
- [ ] `backend/tests/contexts/reporting/infrastructure/test_cobranzas_via_payments.py`
- [ ] `backend/tests/contexts/reporting/application/test_tablero.py` y `dobles.py` (`CobranzasFalsas.detalle`)
- [ ] `backend/tests/integracion/test_cobranza_del_periodo_postgres.py` (nuevo)
- [ ] `backend/tests/integracion/test_api_reporteria.py`

### Frontend
- [ ] `frontend/src/features/reporting/api/reporte.ts`
- [ ] `frontend/src/features/reporting/components/SelectorDePeriodo.tsx` (nuevo)
- [ ] `frontend/src/features/reporting/components/ResumenDeCobros.tsx` (nuevo)
- [ ] `frontend/src/features/reporting/components/Tablero.tsx`
- [ ] `frontend/src/features/reporting/components/Graficos.tsx`
- [ ] `frontend/src/features/reporting/index.ts`
- [ ] `frontend/src/app/(panel)/panel/page.tsx` y `SelectorDePeriodoEnUrl.tsx` (nuevo)
- [ ] `frontend/src/shared/pantallas-reportes.css`
- [ ] `frontend/src/features/reporting/api/__tests__/reporte.test.ts`
- [ ] `frontend/src/features/reporting/components/__tests__/pantallas.test.tsx`
- [ ] `frontend/src/app/(panel)/panel/__tests__/pagina.test.tsx` (nuevo; mismo patrón que `app/(panel)/cobros/__tests__/pagina.test.tsx`)

### Docs
- [ ] `docs/aidlc/epicas/09-reporteria-y-paquete-contable/decisiones.md` (D98: código PAN-DSH-01 y cómo se leyó)
- [ ] `docs/aidlc/TODO.md` §22 (verificaciones manuales de esta unidad) y el hallazgo del período de PAN-COB-01
- Sin ADR: el edge existe y el modelo es el de ADR-0010.

## Casos de prueba

Modo: **test primero**. Los casos RED tienen que fallar antes de tocar el código. Los de PostgreSQL se
escriben y, sin Docker local, **se saltean**: corren en la CI cuando la cadena llegue a `develop`. El
estado dice honestamente cuál se observó.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: `DetalleDeCobranzaDelPeriodo` pasa los filtros **sin** estados y la zona al puerto, y devuelve `por_estado` en el orden de `EstadoCobro` | unit (aplicación payments) | RED observado → verde |
| 2 | RED: `CobranzasViaPayments.totales` trae `tasa_de_cobro` de `MetricasDeCobros` sin recalcularla | unit (ACL) | RED observado → verde |
| 3 | RED: `detalle` agrupa días en semanas ISO con la etiqueta de la facturación: domingo y lunes en semanas distintas, 31/12 → `W53`/`W01` según corresponda, días negativos restan, suma `Decimal` exacta | unit (ACL) | RED observado → verde |
| 4 | RED: `detalle` usa `_limites(periodo)` y `ZONA_DEL_REPORTE`, y lee los estados por `.value` | unit (ACL) | RED observado → verde |
| 5 | RED: `VerTablero` expone `cobrado_por_semana`, `cobros_por_estado` y `tasa_de_cobro`, y pide `detalle` una sola vez (período actual) | unit (aplicación reporting) | RED observado → verde |
| 6 | RED: un período con solo cobros creados (sin comprobantes, turnos ni operaciones) **no** es `sin_actividad`; tampoco uno con un pago y un reembolso que netean cero; uno totalmente vacío sí lo es | unit (aplicación reporting) | RED observado → verde |
| 7 | RED (P5): con reloj fijo el 31/3 a las 23:30 hora argentina, el período por defecto es marzo (tablero, previsualización, generar reporte y contador) | unit/API | RED observado → verde |
| 8 | RED: `cobrado_por_dia`: un pago del 31/3 a las 23:30 hora argentina cae el 31/3; un reembolso resta el día de la devolución; una corrección suma; el día puede quedar negativo; `0.10 + 0.20 = 0.30` | integración (PostgreSQL) | escrito; se saltea sin Docker (CI) |
| 9 | RED: identidades con los mismos filtros: `Σ cobrado_por_dia = metricas.cobrado`; `por_estado[PENDIENTE].monto = pendiente`; `VENCIDO = en_mora`; `Σ` de los tres pagados `= cobrado_de_lo_creado` | integración (PostgreSQL) | escrito; se saltea sin Docker (CI) |
| 10 | RED: `por_estado` agrupa lo **creado** en el período por estado actual, con cantidad y monto: un cobro creado en febrero y pagado en marzo cuenta como «Pagado» en febrero y no aparece en marzo; `CANCELADO` incluido | integración (PostgreSQL) | escrito; se saltea sin Docker (CI) |
| 11 | RLS: el cobrado por día y los cobros por estado de una empresa no incluyen los de otra | integración (PostgreSQL) | escrito; se saltea sin Docker (CI) |
| 12 | `GET /reporteria/tablero` trae `tasa_de_cobro`, `cobrado_por_semana` y `cobros_por_estado`; un cobro pagado en marzo y creado en febrero suma en «cobrado» y en la semana de marzo; período con solo cobros → `sin_actividad` falso; Solo Lectura lee; la ruta del contador sigue respondiendo | integración (API) | escrito; se saltea sin Docker (CI) |
| 13 | RED: Reportes muestra «Cobrado por semana» y «Cobros por estado» con las etiquetas de payments, el subtítulo «por su estado actual» y la tasa | unit (frontend) | RED observado → verde |
| 14 | RED: cambiar el período actualiza los dos gráficos de cobranza | unit (frontend) | RED observado → verde |
| 15 | RED: una semana negativa lleva la clase negativa y el monto con signo; la nota del dato único habla de cobros, no de facturación | unit (frontend) | RED observado → verde |
| 16 | RED: Inicio muestra el resumen (cobrado con variación, pendiente, en mora, tasa) del mes en curso y el selector; con `?desde&hasta` pide `/reporteria/tablero` con ese período; ya no muestra la tarjeta «Cobros pendientes» | unit (frontend) | RED observado → verde |
| 17 | RED: el selector de Inicio escribe `desde/hasta` en la URL | unit (frontend) | RED observado → verde |
| 18 | `SelectorDePeriodo` extraído: el comportamiento de Reportes no cambia (los tests existentes siguen verdes) | unit (frontend) | verde (los tests de Reportes siguen pasando) |
| 19 | En el navegador (`run-local`): Inicio y Reportes con el mismo período muestran las mismas cifras de cobranza; una semana negativa se lee bien | manual | pendiente → `TODO.md` §22.2-22.4 y 22.7 |

## Verificaciones que no se pueden hacer acá

Van a `docs/aidlc/TODO.md` §22 (no dependen de MercadoPago ni de ARCA; no hay ítems para §20 ni §21):
- 22.x: en el navegador, Inicio y Reportes con el mismo período muestran las mismas cifras de cobranza, y
  el selector de Inicio conserva el período al recargar.
- 22.y: una semana con cobrado negativo y un período con un solo estado se ven legibles (color, signo,
  nota del dato único).
- 22.z: después de las 21:00 del último día del mes (hora argentina), Inicio y Reportes abren en el mes
  que termina (P5).
- Los casos 8 a 12 (PostgreSQL) se saltean en local sin Docker; se observan en la CI.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-30 | Aprobado por Luciano: P1 a P5 según la recomendación |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- **P1**: Inicio es **PAN-DSH-01** (`prototipos.md:52`). Se anota en la nota de D98.
- **P2**: el período de Inicio vive en la URL y toda la pantalla lo sigue; el bloque «Cobros del
  período» (cobrado con variación, pendiente, en mora, tasa) reemplaza la tarjeta «Cobros pendientes».
- **P3**: «Cobros por estado» se dibuja por monto, con la cantidad en el rótulo.
- **P4**: la tasa de cobro va como cuarta cifra del resumen de Inicio y en el subtítulo de «Cobros por
  estado» en Reportes.
- **P5**: el período por defecto se calcula en `ZONA_DEL_REPORTE` en los cuatro lugares
  (`reporteria.py:309`, `:330`, `:388` y `contador.py:118`), con un solo helper y test de reloj fijo.

## Verificación (Gate 2) — evidencia, 2026-09-30

Commits: `48e0ab5` (backend), `f1ca5ba` (docs), `3a285e5` (corrección del verificador), `5886042`
(frontend), `3574d69` (docs).

| Comando | Resultado |
|---|---|
| `ruff format --check .` | 584 files already formatted |
| `ruff check .` | All checks passed |
| `mypy . --no-incremental` | Success: no issues found in 579 source files |
| `guard_architecture.py --scan .` | 670 files checked, architecture boundaries intact |
| `pytest --cov=backend/src` | 1562 passed, 412 skipped (PostgreSQL/Redis, sin Docker); cobertura local 75,27 % (el 80 % lo mide la CI con PostgreSQL, igual que en las unidades anteriores) |
| `npm run lint` · `npm run typecheck` | sin errores |
| `vitest run --coverage` | 73 archivos, 883 tests en verde; 87,36 % de líneas |
| `prettier --check --end-of-line auto .` | All matched files use Prettier code style |
| `next build` | compila; `/panel` dinámico |
| `test_guards.sh` | no corre en esta máquina (falta `jq`); mismo resultado sin los cambios |

**Verificador independiente** (Sonnet, solo lectura, mutantes en el scratchpad): sin defectos altos ni
medios. 12 de 14 mutantes muertos por tests que corren en local. Los que sobrevivieron eran dos huecos de
test, y se cerraron en `3a285e5`:
- el orden de las semanas de cobrado (M11): ahora lo mata
  `test_las_semanas_salen_en_orden_aunque_los_dias_lleguen_desordenados`;
- la serialización de la tasa (M13), que la prueba de API no distinguía porque su caso sembrado da
  `0.00`: ahora está fijada por `tests/api/test_tablero_salida.py`, que no necesita base.

Hallazgos que no son de esta unidad, anotados en `TODO.md`: `periodo_cerrado` del paquete contable
también corta el mes en UTC (22.6); el período por defecto de PAN-COB-01, igual (22.5). Además, el
orden de la **facturación** por semana no lo fija ningún test (es anterior a esta unidad).

**Lo que no se verificó:** las consultas SQL nuevas no corrieron contra un PostgreSQL real (casos 8-12,
en la CI cuando la cadena llegue a `develop`); según el verificador, esos tests tampoco atraparían que
la devolución se corte en UTC, porque las devoluciones sembradas están a mediodía. Lo visual de Inicio y
Reportes queda en `TODO.md` §22.2-22.4 y 22.7.

**Desvíos menores del escritor de frontend:** la barra de una semana negativa se dibuja hacia arriba en
color de error con el monto con signo (el eje muestra magnitud); Inicio pasa a tres tarjetas
(`dsh-stats--tres`).
