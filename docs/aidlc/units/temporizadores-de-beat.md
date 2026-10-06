# Unidad: temporizadores-de-beat

**HUs**: HU-E2-01 (RN-04), HU-E2-02 (RN-03), HU-E10-04 (RN-01/RN-02), HS-T4 — las historias cuyas
tareas diarias hoy no corren   **Contexto dueño**: infra (`workers/`, transversal)
**Rama**: fix/infra-temporizadores-de-beat

> Origen: hallazgo **H-W2** (registrado en `docs/aidlc/units/navegacion-pendiente.md`, «Fuera de esta
> unidad»). Es un `fix/…` cortado de `develop`; el PR va a `develop` y no depende de ninguna otra
> unidad. Requiere **ADR-0014** aprobado antes de cerrar el Gate 1 (dependencia nueva y cambio de
> infraestructura del scheduler; ver «Escaladas» del workflow y `CLAUDE.md` §7).

Fila propuesta para `docs/aidlc/units.md`:

```markdown
| Conexión con los servicios externos | temporizadores-de-beat | infra (`workers/`, transversal) | HU-E2-01, HU-E2-02, HU-E10-04, HS-T4 | — | Luciano | fix/infra-temporizadores-de-beat | en curso |
```

(Épico 2 porque las dos primeras entradas diarias de Beat nacieron ahí — `beat.py:3-9`. Si se
prefiere no asociarlo a un épico, ver pregunta 7.)

## Qué hace

Hoy cada despliegue del worker en Render reinicia los temporizadores de Celery Beat, y las tareas de
intervalo largo (diarias, cada 6 h) no llegan a correr si hay un despliegue antes de que se cumpla el
intervalo. Después del fix: (1) las tareas «una vez por día calendario» corren a una **hora fija de
Argentina**, haya o no despliegues; (2) el estado del scheduler (última corrida de cada entrada) vive
**fuera del contenedor**, así un despliegue no lo borra y una corrida perdida se recupera al volver;
(3) dos Beat superpuestos durante el despliegue **no disparan dos veces** la misma entrada.

## Hallazgos

| Dónde | Qué |
|---|---|
| `render.yaml:151-159` | El worker arranca con `celery … worker -B -s /tmp/celerybeat-schedule`. El comentario lo justifica así: «/tmp is writable and ephemeral, which is right: the schedule is rebuilt from `workers/beat.py` at every start, so there is nothing worth keeping across one». **Esa premisa es la falla**: el archivo no guarda la *programación* (que sí está en el código) sino el **`last_run_at`** de cada entrada, que es justamente lo que hay que conservar. Mismo texto en `docs/staging-deployment.md:164-167` |
| `backend/src/cheatsheet/workers/beat.py:39-117` | Las diez entradas usan `timedelta`. Celery crea cada `ScheduleEntry` con `last_run_at = now` cuando no hay estado previo, así que una entrada de `timedelta(days=1)` corre **24 h después del arranque**, no 24 h después de su última corrida. (El hallazgo original citaba «`beat.py` línea 125»: el archivo tiene 124 líneas; lo de `/tmp` está en `render.yaml`, no en `beat.py`.) |
| `.github/workflows/ci.yml:411-490` | `deploy-staging` dispara el deploy hook del worker (`RENDER_DEPLOY_HOOK_WORKER`) en **cada push a `develop`** con CI verde. Con varios merges por día, el worker se redespliega varias veces por día |
| Entradas afectadas | `revisar-vencimientos-de-credenciales` (1 d), `renovar-credenciales-oauth` (1 d), `armar-paquetes-contables` (1 d), `sincronizar-parametros-fiscales` (`PARAMETROS_FISCALES_HORAS`, 24 h por defecto), `reindexar-faqs` (6 h). En menor medida `barrer-cobros` (1 h). Las de 5–30 min sobreviven en la práctica |
| Docs de Render (render.com/docs/deploys) | Los *background workers* tienen **zero-downtime deploy**: la instancia nueva arranca, y recién **60 s después** la vieja recibe `SIGTERM` (+30 s de gracia antes de `SIGKILL`). Durante ≥ 60 s **hay dos procesos con `-B`**. Contradice la premisa «es seguro porque hay una sola instancia» de `render.yaml:125-129` y ADR-0006 §5. Hoy no produce duplicados *por accidente*: el Beat nuevo no dispara nada hasta cumplir un intervalo completo. Con `crontab` o con estado persistente, sí los produciría |
| Docs de Render (render.com/docs/deploys) | Adjuntar un disco persistente **desactiva** el zero-downtime deploy del servicio |
| Docs de Render (render.com/docs/key-value) | La instancia **gratuita** de Key Value (nuestro `cheatsheet-redis`) **no persiste a disco**: un reinicio de Redis pierde todo. Ya es así hoy para la cola del broker y el registro de idempotencia |
| `backend/src/cheatsheet/workers/celery_app.py:44-45` | `timezone="UTC"`, `enable_utc=True`. Un `crontab` se interpretaría en UTC |
| `backend/src/cheatsheet/shared/zona_horaria.py` | `ZONA_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")` — la constante a usar |
| `workers/tasks_integrations.py:312-319` | `_dia()` nombra la corrida diaria con la fecha **UTC** (`dia-YYYY-MM-DD`): es la clave de idempotencia por empresa de vencimientos y renovación. Dos disparos el mismo día UTC son un solo efecto |
| `workers/tasks_reporting.py:52-62` | `barrer_paquetes` elige empresas por `reloj.ahora().day` (día **UTC**) y no tiene clave de idempotencia: un segundo disparo **rehace** el paquete del período (`del_periodo` + índice único, sin duplicar). Un día **sin** corrida hace que esa empresa **pierda el paquete del mes** (la consulta es «configurado para hoy», no «pendiente») |
| `workers/tasks_payments.py`, `contexts/payments/application/recordatorios.py:98` | Barrido de cobros idempotente por estado y por `paso` (D25) |
| `workers/tasks_conversational.py`, `tasks_reference_data.py` | Barridos por estado; un disparo de más es trabajo inútil (y, en parámetros, un ticket WSAA), no un efecto duplicado |
| `backend/pyproject.toml:40-41` | `celery[redis]==5.4.0`, `redis==5.2.0`. No hay scheduler persistente instalado ni driver PostgreSQL síncrono (solo `asyncpg`) |
| `.github/workflows/ci.yml:244-258` | El job de integración ya levanta `redis:7-alpine` local (`REDIS_URL=redis://localhost:6379/0`) |
| `backend/tests/workers/test_tasks_integrations.py:203-320`, `test_tasks_reporting.py:66` | Los tests actuales de Beat afirman `schedule.total_seconds() == 24*60*60` para entradas diarias: cambian con esta unidad |

## Opciones evaluadas

| Opción | Qué resuelve | Qué no resuelve / costo |
|---|---|---|
| **(a) `crontab` a hora fija** para las entradas diarias, sin otra cosa | Sin dependencia nueva. Un reinicio ya no corre el reloj: la próxima corrida es «la próxima 05:00», no «24 h desde el arranque». Fija la hora en Argentina y alinea el día calendario | Sigue sin estado: si el worker está caído o desplegándose **justo** a la hora del disparo, se pierde ese día (el Beat nuevo arranca con `last_run_at = now` y salta a mañana). Para `armar-paquetes-contables` un día perdido es **un mes perdido**. Y en el solapamiento de 60 s del deploy, si la hora cae adentro, **disparan los dos Beat**. No sirve sola para entradas de 6 h o configurables en horas |
| **(b1) Disco persistente de Render** para el archivo `celerybeat-schedule` | Cero código; ~USD 0,25/GB/mes. Conserva `last_run_at`. Como efecto lateral desactiva el zero-downtime deploy → no hay solapamiento | Acopla la corrección a una característica de Render (ADR-0006 es solo staging; producción no está decidida). Cada deploy del worker pasa a tener una ventana sin worker (las tareas esperan en Redis). El usuario no root (`uid 10001`) tiene que poder escribir el punto de montaje (a verificar). `shelve` puede quedar corrupto tras un `SIGKILL` y Celery lo recrea vacío. No da exclusión mutua si Beat se separa o el worker escala |
| **(b2) `celery-redbeat`** (scheduler con estado en Redis) | El estado vive en el Redis que ya es broker; sobrevive a cualquier deploy del worker. Trae **lock distribuido** (`redbeat_lock_key`, expira solo si el dueño muere): el Beat nuevo **espera** al viejo, así el solapamiento no duplica disparos. Recupera una corrida perdida al arrancar (una sola). Independiente de la plataforma; habilita sacar Beat a su propio servicio o escalar el worker sin riesgo. Apache-2.0, 2.4.2 (julio 2026), requiere `celery>=5.0`, `redis>=3.2` | **Dependencia nueva** (+ `tenacity` transitiva) → ADR. En staging, Redis gratuito no persiste: un reinicio de Redis pierde el estado (degrada al comportamiento de «primer arranque», que con `crontab` igual dispara a la hora fija). Las claves de RedBeat no tienen TTL: con una política de expulsión `allkeys-*` podrían expulsarse (la misma amenaza ya existe para el broker) |
| **(b3) Scheduler propio con estado en PostgreSQL** (subclase de `celery.beat.Scheduler`, tabla `ejecucion_programada`, lock por fila con vencimiento) | Durabilidad real (Neon). Sin dependencia nueva de terceros | Código propio sobre una API interna de Celery (`Scheduler`, `ScheduleEntry`) que no es contrato público: mantenimiento a cargo del equipo. No hay driver síncrono: cada `tick` tendría que puentear a `asyncpg` con un loop nuevo. Migración, grants al rol `cheatsheet_app`, tabla global sin RLS. El lock por *advisory lock* de sesión no sobrevive a un loop por llamada → hay que construir un arriendo. Estimado: 250–400 líneas con tests, contra ~40 de (b2) |
| **(c1) Beat como servicio aparte que se despliega menos** | — | No resuelve: el deploy de CI redespliega todo; además duplica la única línea paga (ADR-0006 lo rechazó) |
| **(c2) Render Cron Jobs** que encolan cada tarea | Temporización externa e inmune al deploy | Un servicio pago por entrada o un dispatcher propio; la programación sale del código a `render.yaml`; arranque de contenedor por disparo. Mismo acople a Render que (b1) |
| **(c3) Acortar intervalos** (correr «diarias» cada hora y dejar que la idempotencia por día absorba) | Sin dependencia | Es un parche: depende de que no haya deploys más seguidos que el intervalo, gasta 24× el trabajo, y `armar_paquete` no tiene clave por día (rehace el paquete cada hora del día configurado). Rechazada por la regla de soluciones definitivas |
| **(c4) Barridos «por pendiente» en vez de «por hoy»** (p. ej. paquetes: empresas con `dia <= hoy` sin paquete del período cerrado) | Hace a la tarea inmune a cualquier corrida perdida, no solo a las de deploy | Es cambio de dominio en `reporting` (y revisar otros contextos). Complementa, no reemplaza: sin estado del scheduler las diarias seguirían sin correr. Fuera de alcance (pregunta 5) |

## Recomendación — (a) + (b2)

**`crontab` a hora fija de Argentina para las entradas de semántica «una vez por día calendario»,
y `celery-redbeat` como scheduler para que el estado y la exclusión mutua vivan fuera del
contenedor.** Las dos piezas cubren huecos distintos:

- **RedBeat** resuelve H-W2 de raíz (el `last_run_at` sobrevive al deploy), recupera una corrida
  perdida (si el worker estaba caído a las 05:00, al volver dispara una vez) y convierte el
  solapamiento de 60 s del zero-downtime deploy en algo inocuo (el Beat nuevo espera el lock). Es la
  pieza que además corrige la premisa rota de ADR-0006 §5 («una sola instancia»).
- **`crontab`** es necesario porque, con estado persistente y `timedelta`, la hora de la corrida diaria
  quedaría anclada al primer arranque y derivaría con cada recuperación; una corrida a las 22:30 de
  Argentina es otro día en UTC, y `_dia()` y `barrer_paquetes` usan el día UTC. Una hora fija dentro
  de 00:00–20:59 ART (= mismo día calendario en UTC) mantiene coherentes las claves y la consulta.

Las entradas de **semántica de intervalo** (5 min, 15 min, 30 min, 1 h, 6 h y
`PARAMETROS_FISCALES_HORAS`) **siguen con `timedelta`**: con el estado persistido ya no se reinician,
y convertirlas cambiaría variables de configuración existentes sin necesidad.

Por qué no (b1): resuelve el síntoma en staging pero ata la corrección a un disco de Render y a
`shelve`, y no da exclusión mutua el día que Beat se separe o el worker escale. Por qué no (b3): la
misma garantía que (b2) a 6–10 veces el código, sobre API interna de Celery.

## Diseño

- **Dominio**: No aplica (no cambia ningún agregado).
- **Aplicación**: No aplica. Las tareas y sus casos de uso no cambian.
- **Puertos y adaptadores**: No aplica en sentido hexagonal: el scheduler es infraestructura de
  `workers/` (composition root). Cambios:
  - `workers/celery_app.py`: `timezone=ZONA_ARGENTINA.key` (`"America/Argentina/Buenos_Aires"`),
    **manteniendo `enable_utc=True`**: los mensajes y ETA siguen en UTC; solo cambia el marco en que
    se leen los `crontab`. Se verifica que nada más lea `app.conf.timezone` (hoy nadie: `rg` sobre
    `backend/src`).
  - `workers/beat.py`:
    - `revisar-vencimientos-de-credenciales` → `crontab(hour=5, minute=0)`;
      `renovar-credenciales-oauth` → `crontab(hour=5, minute=15)`;
      `armar-paquetes-contables` → `crontab(hour=6, minute=0)` (horas a confirmar, pregunta 2). Las
      horas como constantes con nombre y docstring de por qué (madrugada, sin deploys humanos,
      dentro de la ventana en la que el día ART = día UTC).
    - `configurar_beat`: `beat_scheduler = "redbeat.RedBeatScheduler"`,
      `redbeat_redis_url = settings.redis_url` (mismo Redis que el broker),
      `redbeat_key_prefix = "cheatsheet:beat"`, `redbeat_lock_timeout` explícito
      (5 × `beat_max_loop_interval` = 300 s: si el dueño muere sin liberar, el siguiente espera como
      mucho 5 min).
    - Docstring del módulo: reemplazar «Beat runs as one process…» por la garantía nueva (lock) y por
      qué hay dos semánticas (`crontab` vs `timedelta`).
- **Otros contextos**: No aplica (ningún edge nuevo del Context Map).
- **Frontend**: No aplica.

## Infraestructura

- **Migraciones**: No aplica.
- **Trabajo asíncrono**: cambia el *scheduler*, no las tareas. Idempotencia ante un disparo doble
  residual (p. ej. Redis reiniciado justo a la hora): vencimientos y renovación por clave
  `dia-<fecha>` por empresa; cobros por `paso` (D25); FAQ, DLQ, planillas y reconciliación por
  estado; paquetes, por rehacer el del período (sin duplicar); parámetros, upsert por vigencia (cuesta
  un ticket). Ninguna tarea necesita cambio.
- **Configuración**: sin variables nuevas (RedBeat usa `REDIS_URL`). `render.yaml` y
  `docs/staging-deployment.md`: el `startCommand` pierde `-s /tmp/celerybeat-schedule` (con RedBeat
  no hay archivo); se reescriben los comentarios que afirman que no hay nada que conservar y que el
  solapamiento no existe. El cambio de `startCommand` se aplica **a mano en la consola de Render**
  (el dashboard es la fuente de verdad, `render.yaml:13-28`). Ningún `.env.example` cambia.
- **Integraciones externas**: No aplica (Redis no es un proveedor externo nuevo; ya está en
  `.env.example`).
- **Dependencia**: `celery-redbeat==2.4.2` fijada en `backend/pyproject.toml` con comentario
  (motivo y ADR), siguiendo la convención del archivo. Antes de fijarla: confirmar compatibilidad con
  `celery==5.4.0` y `redis==5.2.0` instalando en el venv y corriendo la suite.

### ADR-0014 — borrador de esquema (en inglés, `docs/adr/0013-persistent-beat-scheduler-redbeat.md`)

- **Title**: Keep Celery Beat state in Redis with RedBeat, and schedule calendar-daily entries with crontab.
- **Context**: H-W2; `last_run_at` lost on every deploy (`/tmp`); deploy on every merge to `develop`;
  Render zero-downtime overlap of ≥ 60 s means two `-B` schedulers, contradicting ADR-0006 §5;
  daily sweeps (credential expiry, OAuth renewal, accounting package, ARCA catalogue) silently never run.
- **Decision**: `redbeat.RedBeatScheduler` against the existing Redis, with its distributed lock;
  `crontab` in `America/Argentina/Buenos_Aires` for calendar-daily entries, `timedelta` for interval
  entries; Celery `timezone` set to `ZONA_ARGENTINA`, `enable_utc` unchanged.
- **Alternatives considered**: crontab alone; Render persistent disk; own PostgreSQL scheduler;
  Render Cron Jobs; shorter intervals. (Tabla de arriba, traducida.)
- **Consequences**: new dependency (+ `tenacity`); schedule state as durable as Redis — on the free
  Key Value tier, lost on a Redis restart (same as the broker queue); a production Redis must persist
  and use a non-evicting policy; Beat may now be split out or the worker scaled without duplicate
  firing; ADR-0006 §5's "one instance" premise is replaced by the lock.
- **Impact on repository rules**: none of R1–R5; no new root directory.
- **References**: ADR-0006, `render.yaml`, `docs/staging-deployment.md` §4 bis.3, Render docs (deploys,
  disks, key-value), RedBeat docs.

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero → No aplica
- [ ] Toca comprobantes fiscales / CAE → No aplica (la reconciliación no cambia de programación)
- [ ] Consume un webhook → No aplica
- [ ] Agrega datos con `empresa_id` → No aplica (las claves de RedBeat son globales, sin datos de empresa)
- [ ] Usa salida de un LLM → No aplica
- [ ] Datos personales o fiscales → No aplica
- [x] **Disparo duplicado de tareas programadas** (no está en la plantilla; es el riesgo propio de esta
  unidad) → test de exclusión mutua de dos schedulers y de no-redisparo tras reinicio

## Archivos a tocar

- [ ] `backend/pyproject.toml` — `celery-redbeat==2.4.2` con comentario
- [ ] `backend/src/cheatsheet/workers/celery_app.py` — `timezone` = `ZONA_ARGENTINA`
- [ ] `backend/src/cheatsheet/workers/beat.py` — `crontab` en las tres diarias, configuración de RedBeat, docstrings
- [ ] `backend/tests/workers/test_beat.py` (nuevo) — tests de programación y de scheduler
- [ ] `backend/tests/workers/test_tasks_integrations.py` — ajustar `test_beat_programa_la_revision_de_vencimientos_una_vez_por_dia` y el de parámetros (que compara contra `timedelta` de todas las entradas)
- [ ] `backend/tests/workers/test_tasks_reporting.py` — ajustar la aserción de la entrada de paquetes
- [ ] `backend/tests/integracion/test_beat_redbeat.py` (nuevo) — contra el Redis local del job de integración
- [ ] `render.yaml` — `startCommand` sin `-s /tmp/…`, comentarios
- [ ] `docs/staging-deployment.md` — §4 bis.3 y tabla del worker
- [ ] `docs/architecture.md` — fila 9 (Scheduler): RedBeat + lock
- [ ] `docs/adr/0013-persistent-beat-scheduler-redbeat.md` (nuevo) y referencia desde ADR-0006
- [ ] `docs/aidlc/units.md` — fila de la unidad
- [ ] `docs/aidlc/TODO.md` — verificaciones en staging (ver abajo)

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** Las tres entradas diarias son `crontab` con la hora de Argentina acordada (hoy fallan: son `timedelta`) | unit | pendiente |
| 2 | La app de Celery tiene `timezone == "America/Argentina/Buenos_Aires"` y `enable_utc` sigue en `True` | unit | pendiente |
| 3 | **RED** Reinicio a media jornada: `last_run_at` = hoy 05:00 ART, `now` = hoy 14:00 ART → `is_due` falso y el próximo disparo es mañana 05:00 ART (con `nowfun` fijo, sin reloj real) | unit | pendiente |
| 4 | Corrida perdida: `last_run_at` = ayer 05:00 ART, `now` = hoy 05:03 ART → `is_due` verdadero (recuperación de un solo disparo) | unit | pendiente |
| 5 | 05:00 ART es el mismo día calendario en UTC (el disparo de paquetes y `_dia()` ven el mismo día que la empresa) | unit | pendiente |
| 6 | `configurar_beat` instala `beat_scheduler == "redbeat.RedBeatScheduler"`, la URL de Redis de `Settings`, el prefijo y el `redbeat_lock_timeout` | unit | pendiente |
| 7 | Las entradas de intervalo conservan su `timedelta` y su variable (`WHATSAPP_SONDEO_MINUTOS`, `DLQ_BARRIDO_MINUTOS`, `SYNC_PLANILLAS_MINUTOS`, `PARAMETROS_FISCALES_HORAS`) | unit | pendiente |
| 8 | Lista exhaustiva de entradas (`test_todas_las_entradas_de_beat_conviven`) sigue verde con 10 | regresión | pendiente |
| 9 | Con Redis local: un `last_run_at` guardado por un scheduler sobrevive a crear un scheduler nuevo (simula el deploy) | integración | pendiente |
| 10 | Con Redis local: un segundo scheduler **no** obtiene el lock mientras el primero lo tiene, y lo obtiene cuando el primero cierra | integración | pendiente |
| 11 | Ningún test toca la red: el de integración usa solo el Redis del servicio de CI (`localhost`) | — | pendiente |

## Verificaciones que no se pueden hacer acá (→ `docs/aidlc/TODO.md`)

- En `staging`: tras un deploy del worker, los logs muestran que el Beat nuevo espera el lock y lo toma
  después del `SIGTERM` del viejo; al día siguiente las tres diarias corrieron a la hora fijada aunque
  hubo deploys en el medio.
- En la consola de Render: aplicar el `startCommand` nuevo; confirmar la `maxmemory-policy` de
  `cheatsheet-redis` (pregunta 4).

## Fuera de esta unidad (hallazgos para registrar)

- **Paquete contable perdido**: `barrer_paquetes` elige por «día configurado == hoy»; un día sin corrida
  (worker caído todo el día) hace perder el paquete del mes, con o sin este fix (pregunta 5).
- **Día UTC vs día de Argentina** en `barrer_paquetes` (`reloj.ahora().day`) y `_dia()`: con la hora
  fija elegida no se manifiesta, pero una recuperación tardía (después de las 21:00 ART) usaría el día
  siguiente. Fix propio de `reporting`/`integrations`.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-06 | Aprobado por Luciano con las recomendaciones de las siete preguntas. Cierra cuando se acepte el ADR-0014; hasta entonces no se escribe código |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Gate 1 (2026-10-06): Pregunta 1 → RedBeat sobre el Redis existente, con ADR-0014.
- Gate 1 (2026-10-06): Pregunta 2 → vencimientos 05:00, renovación OAuth 05:15 y paquetes contables 06:00, hora de Argentina (`crontab`).
- Gate 1 (2026-10-06): Pregunta 3 → `sincronizar-parametros-fiscales` y `reindexar-faqs` siguen con intervalo.
- Gate 1 (2026-10-06): Pregunta 4 → se acepta Redis sin persistencia en staging; el ADR exige Redis persistente con `noeviction` en producción.
- Gate 1 (2026-10-06): Pregunta 5 → el paquete perdido por un día sin corrida queda fuera de esta unidad, como corrección propia de reporting.
- Gate 1 (2026-10-06): Pregunta 6 → el ADR-0006 no se edita; se le agrega «Amended by ADR-0014».
- Gate 1 (2026-10-06): Pregunta 7 → la fila va en el épico «Conexión con los servicios externos».
- Numeración: ADR-0014, porque el ADR-0013 lo toma `cobro-con-clave-de-idempotencia`, que se mergea antes.

## Preguntas para el Gate 1

1. **Opción de persistencia.** ¿RedBeat (b2), disco de Render (b1) o scheduler propio en PostgreSQL
   (b3)? Recomendación: **RedBeat**, con ADR-0014; es la única que además da exclusión mutua portable
   con ~40 líneas, y reusa el Redis que ya es broker.
2. **Horas de las diarias.** Recomendación: vencimientos **05:00**, renovación OAuth **05:15**, paquetes
   contables **06:00** (hora de Argentina): fuera del horario en que alguien mergea, dentro de la ventana
   en la que el día ART coincide con el UTC, y escalonadas para no competir por el worker de `-c 2`.
3. **`sincronizar-parametros-fiscales` y `reindexar-faqs`.** ¿Pasarlas también a `crontab`?
   Recomendación: **no**; son de semántica de intervalo, con estado persistido ya no se reinician, y
   parámetros tiene una variable (`PARAMETROS_FISCALES_HORAS`) que pasaría a no significar nada.
4. **Redis gratuito sin persistencia.** En staging un reinicio de Redis pierde el estado de Beat (como ya
   pierde la cola). Recomendación: aceptarlo para staging, dejar escrito en el ADR que producción
   requiere Redis con persistencia y política `noeviction`, y verificar hoy la política de
   `cheatsheet-redis` en la consola.
5. **Paquete perdido por un día sin corrida** (hallazgo de arriba). Recomendación: **fuera de esta
   unidad**, como `fix/reporting-…` propio que cambie la consulta a «pendiente del período»; este fix
   elimina la causa frecuente (deploys) pero no la rara (caída de un día entero).
6. **ADR-0006.** El solapamiento de deploys rompe su premisa «una sola instancia». Recomendación: no
   editar el cuerpo de ADR-0006; agregarle una línea «Amended by ADR-0014» y explicar en ADR-0014.
7. **Épico de la fila en `units.md`.** Recomendación: «Conexión con los servicios externos», porque las
   primeras entradas diarias de Beat son suyas (HU-E2-01, HU-E2-02); alternativa: el épico de
   `dlq-y-tareas-asincronas` («Sincronización de planillas»).
