# Unidad: webhook-concurrente

**HUs**: HS-T1, HU-E6-06 RN-03   **Contexto dueño**: payments   **Rama**: fix/payments-webhook-concurrente
**Issue**: #240 (Crítico: dinero)   **Revisa**: Paula (autora de Cobros, `reparto.md:34`; regla `reglas.md` §8.3)

> Evidencia leída sobre `origin/develop` (`07bcac1`). Rutas relativas a `backend/src/cheatsheet/`.

## Qué hace

Dos webhooks simultáneos del mismo `payment_id` dejan de aprobar dos veces el mismo cobro: el
primero aprueba y baja el saldo del comprobante; el segundo espera el bloqueo de la fila, ve el
cobro ya resuelto y termina en `ya_procesado`, sin tocar saldo ni bitácora. Lo mismo para un pago
sobre un cobro cancelado: un solo huérfano y una sola alerta.

## Hallazgos (la carrera, confirmada por lectura)

| Dónde | Qué |
|---|---|
| `payments/application/confirmacion.py:90` | `buscar_por_payment_id` sin bloqueo: las dos transacciones lo pasan porque ninguna commiteó |
| `confirmacion.py:95` | `consultar_pago` (HTTP a MercadoPago) ocurre **antes** de cargar el cobro |
| `confirmacion.py:119-125` | `_encontrar` carga con `buscar_por_id` o `buscar_por_preference_id` |
| `payments/infrastructure/repositories.py:128-130, 158-161` | `session.get` y `select` simples, **sin `FOR UPDATE`** |
| `confirmacion.py:138, 152-153` | Las dos ven el cobro abierto y lo aprueban; la segunda espera en el `flush` de `guardar` y reescribe la misma fila con el mismo `payment_id`, así que `uq_cobro_mp_payment_id` no salta |
| `payments/infrastructure/saldo.py:49-52` | `registrar_cobro` relee el comprobante (ya bajado por la primera) y vuelve a restar: $ 1000 → $ 200 |
| `confirmacion.py:130-136, 198-199` | Mismo defecto en el huérfano: el chequeo `mp_payment_id is not None` de `domain/cobro.py:225` mira la copia leída sin bloqueo, pasa en las dos y se publican dos `pago_sobre_cobro_cancelado` |
| `repositories.py:132-146` · `application/ports.py:159-166` | `buscar_para_actualizar` (`FOR UPDATE` + `populate_existing`) **ya existe en el puerto** y lo usan los reembolsos (`reembolsos_comunes.py:39`) |
| `tests/contexts/payments/application/test_confirmacion.py:78` | El doble en memoria ya implementa `buscar_para_actualizar`: no hay que tocar fakes |

No se fija nivel de aislamiento en `platform/` (no aparece `isolation` en `src`): es READ COMMITTED,
y con él `FOR UPDATE` devuelve la fila confirmada por la otra transacción tras la espera.

## Diseño

- **Dominio**: sin cambios.
- **Aplicación** (`ConfirmarPago`):
  1. `_encontrar` carga **siempre con bloqueo**: por `external_reference` →
     `buscar_para_actualizar(pago.cobro_id)` (manteniendo la comparación de empresa); por
     preferencia → `buscar_por_preference_id` para resolver el id y después
     `buscar_para_actualizar(cobro.id)`. El bloqueo se toma en `_encontrar`, antes de bifurcar,
     así cubre aprobación **y** huérfano.
  2. Primera línea de `_aprobar`, con el bloqueo tomado: si `cobro.mp_payment_id == pago.payment_id`
     → `ya_procesado` (cubre el APROBADO y el CANCELADO-con-huérfano). Después siguen el chequeo de
     CANCELADO y el de `esta_abierto` (`:138`), que ahora miran la fila fresca.
- **Puertos y adaptadores**: **sin cambios de puerto ni de adaptador** (ver D1).
- **Otros contextos / frontend**: no aplica.
- **El HTTP queda afuera del bloqueo**: `consultar_pago` (`:95`) sigue antes de `_encontrar`
  (`:102`). El bloqueo dura sólo trabajo de base (guardar, saldo, bitácora) hasta el commit de la
  unidad de trabajo del router (`api/routers/webhooks.py:89-95`). Un comentario lo deja escrito.

## Infraestructura

Migraciones: ninguna. Asíncrono, configuración, integraciones: sin cambios.

## Riesgos que obligan a tests

- [x] Toca dinero → el saldo baja exactamente una vez.
- [x] Consume un webhook → entrega duplicada **concurrente**: un evento, un efecto.
- **Orden de bloqueos**: cobro (`FOR UPDATE`) → comprobante (`UPDATE` de `guardar`) → inserción en
  bitácora. Los reembolsos usan el mismo orden (`reembolsos_comunes.py:39, 55-57`). No se ve un
  camino que bloquee comprobante y después cobro, así que no se introduce un ciclo de deadlock.
- **Duración del bloqueo**: ninguna llamada de red con la fila tomada (ver Diseño).

## Archivos a tocar

- [ ] `backend/src/cheatsheet/contexts/payments/application/confirmacion.py`
- [ ] `backend/tests/integracion/test_webhook_concurrente_postgres.py` (nuevo)
- [ ] `backend/tests/contexts/payments/application/test_confirmacion.py` (caso del `payment_id` ya atado tras el bloqueo)
- [ ] `docs/aidlc/units/webhook-concurrente.md`

Estimado: ~25 líneas de producción, ~150-200 de tests.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** `test_dos_webhooks_concurrentes_del_mismo_pago_bajan_el_saldo_una_sola_vez`: comprobante $ 1000, cobro $ 400; A procesa y queda abierto, B arranca, se espera en `pg_locks` hasta ver a alguien bloqueado, A commitea. Saldo $ 600, una sola `confirmar_pago`, uno `recien` y el otro `ya_procesado`. En `develop` falla con $ 200 y dos eventos | integración (PostgreSQL real) | pendiente |
| 2 | Lo mismo, encontrando el cobro por `preference_id` (parametrizado) | integración | pendiente |
| 3 | `test_dos_webhooks_concurrentes_sobre_un_cobro_cancelado_registran_un_solo_huerfano` | integración | pendiente |
| 4 | Con el bloqueo tomado, un cobro con ese `payment_id` devuelve `ya_procesado` sin saldo ni evento | unit | pendiente |

Patrón determinista de `tests/integracion/test_entregas_concurrentes_postgres.py:84-113` (A abierto a
mano, B como tarea, sondeo de `pg_locks`, sin `sleep` para provocar el solapamiento). Pasarela falsa
que devuelve el pago aprobado; saldo real (`SaldoViaBilling` sobre el repositorio de `billing` en
Postgres). Las tablas tocadas (`cobro`, `comprobante`, `item_de_comprobante`,
`registro_de_auditoria`) ya están en `BORRADOS` (`tests/integracion/conftest.py:125-166`).

## Verificación (Gate 2)

`ruff format --check .` · `ruff check .` · `mypy .` · `pytest` · CI local completa. Actions no
tiene cuota hasta el 2026-11-01: la CI de referencia es la local.

## Dependencia con otra unidad

`feature/payments-aviso-de-cobro-confirmado` (rama **local**, no está en `origin`) se rebasa sobre
este arreglo. Su `ResultadoDeConfirmacion.recien_aprobado` (`aprobado and not ya_procesado and not
huerfano`) sólo es cierto para el ganador **gracias a este arreglo**: hoy saldría cierto en los dos y
se mandarían dos avisos. Su docstring dice que el ganador es «la transacción que ganó el índice único
de `payment_id`», lo que es falso (el índice no salta, ver Hallazgos): corregirlo al rebasar.

## Hallazgos fuera de alcance (ya reportados como issues, no se arreglan acá)

1. **`CancelarCobro` contra la aprobación** (`application/cobros.py:249, 266`): lee sin bloqueo,
   llama a MercadoPago y `guardar` reescribe la fila entera (`infrastructure/mapeo_de_cobro.py:62, 65`).
   Si el webhook aprueba en el medio, la cancelación puede pisar APROBADO con CANCELADO y borrar el
   `mp_payment_id` con el saldo ya bajado. Crítico. Issue #241.
2. **Barrido de vencimiento** (`application/recordatorios.py:77-84`): lista sin bloqueo y guarda
   VENCIDO; misma ventana contra una aprobación concurrente. Issue #242.
3. **Saldo sin bloqueo del comprobante** (`saldo.py:49-52, 63-66`): dos cobros **distintos** del
   mismo comprobante (o un cobro y un reembolso) aprobados a la vez leen el mismo saldo y uno pisa al
   otro (actualización perdida: el saldo queda **alto**). El bloqueo del cobro no lo cubre. Issue #243
   (toca la ACL sobre `billing`).
4. Un segundo pago **distinto** sobre un cobro cancelado que ya tiene huérfano: `cobro.py:225`
   levanta `InvarianteViolada` → 500 y MercadoPago reintenta. Preexistente; no se cambia.

## Decisiones para el responsable (resueltas en el Gate 1)

| # | Pregunta | Resolución |
|---|---|---|
| D1 | ¿Puerto nuevo (`buscar_por_preference_id_para_actualizar`) o dos pasos? | **Dos pasos** con `buscar_para_actualizar` (buscar, después bloquear por id). Sin método nuevo en el puerto |
| D2 | ¿El chequeo de `payment_id` tras el bloqueo va en la aplicación o en el dominio? | **Aplicación**: devuelve `ya_procesado`, no un error |
| D3 | ¿Contar los eventos en `registro_de_auditoria` o con un publicador falso? | **En la tabla** `registro_de_auditoria` (se confirma al escribir el test que el publicador de la sesión escribe ahí) |
| D4 | Hallazgos 1-3 | Ya reportados como issues **#241** (CancelarCobro), **#242** (barrido de vencimiento) y **#243** (actualización perdida en `SaldoViaBilling`); no se arreglan en esta unidad |
| D5 | Unidad apilada `aviso-de-cobro-confirmado` | Se rebasa sobre este arreglo; nada que hacer acá |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-15 | Aprobado por Luciano con las decisiones 1–5 |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- D1–D5 según la tabla de decisiones: dos pasos sin puerto nuevo, chequeo en la aplicación, conteo en `registro_de_auditoria`, hallazgos fuera de alcance en #241-#243.
