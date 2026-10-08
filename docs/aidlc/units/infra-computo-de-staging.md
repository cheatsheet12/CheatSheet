# Unidad: infra-computo-de-staging

**HUs**: ninguna — trabajo de entorno   **Contexto dueño**: ninguno (`platform` + `workers` + `api`)
**Rama**: `fix/infra-computo-de-staging`

> **Por qué esta unidad existe sin HU detrás.** Es una unidad técnica de entorno, igual que
> [`infra-staging-database`](infra-staging-database.md) e
> [`infra-staging-deployment`](infra-staging-deployment.md): corrige cómo corre `staging`, que
> [`configuration-management.md`](../../configuration-management.md) §5 declara entorno compartido
> donde se valida y se demuestra. No agrega comportamiento de negocio.

---

## Qué hace

Hace que la base de `staging` en Neon **pueda dormirse**. Hoy el compute nunca se suspende y gasta
~6 CU-h por día (0,25 CU × 24 h) contra los 100 CU-h por proyecto y por mes del plan Free: el mes
se agota en ~17 días. Después de esta unidad, el compute despierta una vez por hora y vuelve a
dormir, por debajo de 1 CU-h por día.

---

## Diagnóstico (con evidencia, solo lectura)

Neon suspende el compute tras 5 minutos sin conexiones. Dos cosas lo mantenían despierto:

1. **Celery Beat, embebido en el worker de pago siempre encendido (`worker -B`).**
   `billing.reconciliar_comprobantes` corría cada **5 minutos fijos**
   (`backend/src/cheatsheet/workers/beat.py`): una consulta a la base cada 5 minutos, o sea que
   nunca pasan 5 minutos ociosos. Las demás tareas periódicas que tocan la base disparaban en
   instantes desalineados, porque un `timedelta` cuenta desde el arranque de Beat:
   `observability.barrer_dlq` (15 min), `integrations.sondear_pendientes` (30 min),
   `spreadsheet_sync.sincronizar_pendientes` (60 min), `payments.barrer_cobros` (1 h),
   `conversational.barrer_faqs` (6 h). Cada despertar suelto cuesta ≥ 5 minutos de compute.
2. **El health check de Render** (`healthCheckPath: /health`) ejecuta `SELECT 1` y un ping a Redis
   (`api/routers/health.py`) cada pocos segundos mientras la instancia gratuita de la API está
   despierta.

---

## Diseño aprobado (Gate 1 aprobado por Luciano el 2026-10-08)

- **A. Intervalo de reconciliación configurable.** `BILLING_RECONCILIACION_MINUTOS`, por defecto
  **5**: producción no cambia.
- **B. Alinear las tareas periódicas al reloj.** Las entradas que repiten dentro del día y tocan la
  base pasan de `timedelta` a `crontab` anclado al minuto 0 de la hora, para que **todas disparen
  en los mismos instantes** y Neon despierte una vez por período. Un helper puro,
  `platform/intervalos.py::campos_alineados`, aplica una regla determinista que **nunca redondea**:

  | Intervalo N (minutos) | Resultado |
  |---|---|
  | 1 ≤ N < 60 y N divide a 60 | cada N minutos (`*/N`) |
  | N múltiplo de 60, H = N/60 divide a 24 | minuto 0, cada H horas (`*/H`); 1440 → 00:00 |
  | cualquier otro valor (45, 90, 150, 0, negativos…) | `IntervaloNoAlineable` |

  Las cuatro variables `*_MINUTOS` se validan en `Settings.desde_entorno`: un valor que no se
  alinea **detiene el arranque** nombrando la variable, en lugar de cambiar en silencio cada
  cuánto corre un barrido de facturación. Alcanzadas: `WHATSAPP_SONDEO_MINUTOS`,
  `DLQ_BARRIDO_MINUTOS`, `SYNC_PLANILLAS_MINUTOS`, `BILLING_RECONCILIACION_MINUTOS`, más los
  literales de `barrer-cobros` (60) y `reindexar-faqs` (360). **No se tocan** las entradas diarias
  ni `PARAMETROS_FISCALES_HORAS` (ver ADR-0014 abajo).
- **C. `/health/live`.** Responde `200 {"estado": "ok"}` sin tocar PostgreSQL ni Redis, es público
  como `/health`. `/health` queda como comprobación completa (readiness) y la sigue usando el
  sondeo posterior al despliegue de CI. `render.yaml` pasa a `healthCheckPath: /health/live`.
- **D. Documentación.** `docs/staging-deployment.md` (§3 paso 7 y nueva §4 bis.4) y este plan.

### Relación con el ADR-0014 (propuesto, PR #101) y con la unidad `temporizadores-de-beat`

El ADR-0014 persiste el estado de Beat con RedBeat y mueve a `crontab` solo las **tres entradas
diarias**. Su punto 5 dice que las entradas de intervalo siguen con `timedelta`, «every shorter
entry (5 min to 1 h)». **Esta unidad contradice ese punto en parte**: convierte a `crontab` las
entradas de menos de un día que tocan la base. No es una contradicción de fondo:

- El ADR mantiene `timedelta` para conservar semántica de intervalo con estado persistido. Un
  `crontab` anclado al reloj no necesita `last_run_at` para saber cuándo toca, es compatible con
  RedBeat (que sabe programar `crontab`) y **no sufre** la pérdida de cuenta tras un deploy que el
  ADR describe.
- Las entradas diarias y `PARAMETROS_FISCALES_HORAS` quedan intactas, así que ninguna otra decisión
  de la unidad `temporizadores-de-beat` (horas ART, `timezone`, RedBeat) se pisa. Si esa unidad
  cambia la `timezone` de Celery a Argentina (UTC−3, sin horario de verano), los instantes de esta
  unidad se corren 3 h pero **siguen alineados entre sí**, que es lo único que importa acá.
- **Acción para la otra unidad:** al implementar el ADR-0014, ajustar su punto 5 (o sumar una
  nota) para reflejar que las entradas sub-diarias que tocan la base están ancladas con
  `alineado()`. Esta unidad no edita el ADR.

---

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: ver B. Ninguna tarea cambia; cambia solo *cuándo* dispara su entrada de
  Beat.
- **Configuración**: una variable nueva, `BILLING_RECONCILIACION_MINUTOS` (default 5), en
  `backend/.env.example`. Las otras tres ya existían.
- **Integraciones externas**: no aplica.

### Efecto esperado

De ~6 CU-h/día (compute siempre encendido) a **< 1 CU-h/día**: con los valores de abajo el compute
despierta ~1 vez por hora (el barrido de cobros, minuto 0), ~5–6 minutos cada vez, unos
24 × 0,25 × (6/60) ≈ 0,6 CU-h/día, con el health check ya sin tocar la base.

### Acciones del dueño (Render, no versionables)

1. En el worker, setear: `BILLING_RECONCILIACION_MINUTOS=60`, `DLQ_BARRIDO_MINUTOS=120`,
   `WHATSAPP_SONDEO_MINUTOS=120`, `SYNC_PLANILLAS_MINUTOS=240`.
2. En la API, cambiar **Health Check Path** a `/health/live` en el panel de Render (el panel es la
   fuente de verdad, no `render.yaml`).
3. Agregar `BILLING_RECONCILIACION_MINUTOS` a `backend/.env.example` (el archivo está protegido
   para el agente).

---

## Riesgos y compensaciones

| Riesgo | Mitigación |
|---|---|
| Reconciliación más lenta en staging (hasta 1 h para un comprobante con respuesta de ARCA perdida) | Solo staging; producción conserva 5 min. D17 sigue protegiendo el caso con `VENTANA_DE_VUELO` |
| Barrido de la DLQ más lento (hasta 2 h) | Es visibilidad, no urgencia (HS-T6) |
| Verificación de WhatsApp notada hasta 2 h tarde | Meta mide la espera en días (HU-E2-03 RN-02) |
| Sincronización de planillas cada 4 h en vez de 1 h | Demostración en staging |
| Una variable mal escrita (45) | Falla al arrancar nombrando la variable, con test |
| `/health/live` no detecta una base caída | A propósito: liveness no es readiness. `/health` sigue detectándola y CI lo sondea tras cada deploy |
| Todas las tareas disparan a la vez | Colas y `-c 2` ya acotan la concurrencia; son consultas cortas |

## Riesgos que obligan a tests

- [ ] Toca dinero: no
- [x] Toca comprobantes fiscales / CAE: solo la **frecuencia** de la reconciliación; test de que el
  intervalo configurado llega a Beat
- [ ] Consume un webhook: no
- [ ] Datos con `empresa_id`: no
- [ ] Salida de un LLM: no
- [ ] Datos personales o fiscales: no

## Archivos a tocar

- [x] `backend/src/cheatsheet/platform/intervalos.py` (nuevo)
- [x] `backend/src/cheatsheet/platform/settings.py` (campo, validación)
- [x] `backend/src/cheatsheet/workers/beat.py`
- [x] `backend/src/cheatsheet/api/routers/health.py`, `api/middleware/empresa.py`
- [x] `backend/tests/platform/test_intervalos.py`, `tests/workers/test_tasks_integrations.py`,
  `tests/api/test_health.py`, `tests/conftest.py`
- [x] `render.yaml`, `docs/staging-deployment.md`
- [ ] `backend/.env.example` (a cargo del dueño)

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Intervalos que dividen la hora o el día se anclan al minuto 0 | unit | hecho |
| 2 | Intervalos que no se alinean (0, 7, 45, 90, 1500…) se rechazan | unit | hecho |
| 3 | Cada una de las cuatro variables mal configuradas detiene el arranque | unit | hecho |
| 4 | Beat usa `BILLING_RECONCILIACION_MINUTOS` | unit | hecho |
| 5 | Las entradas que tocan la base comparten el minuto 0 | unit | hecho |
| 6 | `/health/live` da 200 sin tocar base ni Redis, sin empresa | unit (ASGI) | hecho |
| 7 | `/health` sigue dando 503 con dependencias caídas | unit (ASGI) | hecho |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-08 | **aprobado** |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- ¿Se alinean las entradas diarias y `PARAMETROS_FISCALES_HORAS`? → **No** (2026-10-08): son
  territorio de la unidad `temporizadores-de-beat` / ADR-0014 y despiertan la base una vez al día.
- ¿Redondear un intervalo que no divide la hora? → **No, se rechaza** (2026-10-08): redondear
  cambia en silencio la frecuencia de un barrido de facturación o de cobros.
- ¿`/health` pasa a ser liveness? → **No**: se agrega `/health/live` y `/health` queda como
  readiness, porque CI lo usa para saber que el despliegue quedó sano.
