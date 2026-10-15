# Unidad: reintentos-con-idempotencia

**Issue**: #216 (Mayor)   **HUs**: HU-E1-04 (donde se manifestó); corrige la garantía de ADR-009
**Contexto dueño**: transversal (`workers/` + `platform/`)   **Rama**: fix/infra-reintentos-con-idempotencia
**Revisa el PR**: Cristian, autor de `workers/base.py`, `platform/cache.py` y de las tareas afectadas (`reparto.md` §1, regla 3)

## Qué hace

Hace que el reintento de Celery de una tarea idempotente vuelva a ejecutar el efecto cuando el intento
anterior falló. Hoy la invitación que falla por SMTP se reintenta, el reintento se omite por
idempotencia, la tarea termina `succeeded: False` y el mail no sale hasta que alguien pulsa «Reenviar».

## Diagnóstico (verificado sobre `origin/develop` 07bcac1)

- `EjecutorIdempotente.ejecutar` (`workers/base.py:79-82`) reserva la clave con `registrar_si_es_nueva`
  **antes** del efecto y devuelve `await accion()` sin `try`: si el efecto lanza, la clave queda tomada.
- La reserva es `SET NX EX` de 7 días (`platform/cache.py:48-52`). El puerto (`cache.py:26-31`) no
  tiene forma de liberar.
- `identity.enviar_invitacion` (`tasks_identity.py:93`) se registra con
  `autoretry_for=(EnvioDeEmailFallido, OSError)` y 5 reintentos (`:178-182`): cada reintento encuentra
  la clave y devuelve `False`. Coincide con el log del issue.
- Mismo defecto en `sondear_empresa`, `revisar_empresa` y `renovar_empresa` (`tasks_integrations.py:137,
  182, 229`, `autoretry_for=(OSError,)` en `:335-399`), y latente en `registrar_latido` (`tasks.py:58`).
  Las cuatro son seguras de repetir: el cambio de estado se confirma en una transacción y la corrida
  repetida ya no encuentra nada que hacer.
- La redelivery tras la caída de un worker (`celery_app.py:49-50`, `acks_late` + `reject_on_worker_lost`)
  también se omite; no hay `task_time_limit` en la configuración.
- Ninguna tarea de dinero o de comprobantes usa el ejecutor (`tasks_payments`, `tasks_billing` no
  reintentan y su idempotencia vive en la base / ADR-0013).
- Los tests no lo ven: `test_base.py:13` y el caso 23 de `test_tasks_integrations.py` cubren solo el
  camino exitoso; el caso 29 (`test_tasks_identity.py`) solo verifica que el error suba. El adaptador
  Redis no tiene test propio.
- Desde el 13/10 no cambió nada de esto: #217 solo toca tests y #238 toca `integrations`/`api/arca.py`,
  no `workers/` ni `platform/cache.py`.

**Fuera de alcance**: la falla SMTP misma (SES en sandbox, es de entorno), el registro en dos estados
para la caída del worker, y los logs con `destinatario` en `email_invitacion.py:90,96,113`
(otro contexto; ver P5).

## Diseño

Reservar antes (protege la concurrencia, no cambia) y **liberar si el efecto lanza**, con la política
declarada por cada tarea:

- `platform/cache.py`: el puerto gana `liberar(clave) -> None`; Redis hace `DEL idem:<clave>`, memoria
  hace `discard`. Define `ErrorDeRegistroDeIdempotencia` junto al puerto; el adaptador Redis traduce
  `RedisError`/`OSError` de `liberar` a esa excepción (`raise ... from`), así el ejecutor no conoce Redis.
- `workers/base.py`: enum `AnteUnaFalla` (`LIBERAR` | `RETENER`) y argumento obligatorio en `ejecutar`.
  Con `LIBERAR`: `except Exception` → `liberar` → re-lanza la excepción original. Si `liberar` falla
  (`ErrorDeRegistroDeIdempotencia`), log `liberacion_de_idempotencia_fallida` y sube la original igual.
  `CancelledError` no libera (resultado desconocido). Con `RETENER`, comportamiento actual.
- Las cinco llamadas pasan `LIBERAR` con una línea de por qué. Se actualizan el docstring de `base.py`
  y el párrafo "Processing guarantees" de `docs/architecture.md`. No hace falta ADR: ADR-009 ya pide
  clave + reintentos; esto hace que convivan.
- Dominio, aplicación, migraciones, colas, Beat, variables y frontend: sin cambios.

## Riesgos que obligan a tests

- [x] Toca dinero (indirecto): un test fija que `RETENER` sigue omitiendo el reintento, la garantía
      que necesitará un futuro `Cobro`.
- [ ] Comprobantes / CAE · [ ] Webhook · [ ] Datos con `empresa_id` · [ ] Salida de LLM · [ ] Datos personales

## Archivos a tocar (≈ 180-220 líneas, dos tercios tests)

- `backend/src/cheatsheet/platform/cache.py`, `workers/base.py`, `workers/tasks_identity.py`,
  `workers/tasks_integrations.py`, `workers/tasks.py`
- `backend/tests/workers/test_base.py`, `test_tasks_identity.py`, `test_tasks_integrations.py`
- `backend/tests/platform/test_registro_de_idempotencia_redis.py` (nuevo; sin red, Redis simulado)
- `backend/tests/integracion/test_idempotencia_redis.py` (nuevo; se saltea sin Redis, como
  `test_tareas_en_loops_distintos.py`)
- `docs/architecture.md`, `docs/aidlc/units.md` (fila) y este plan

## Casos de prueba (RED primero)

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | `test_tasks_identity.py::test_si_el_primer_envio_falla_el_reintento_manda_el_mail`: el primer envío lanza `EnvioDeEmailFallido`, el segundo envía → un mail y `True` (reproduce staging) | unit | rojo antes del fix |
| 2 | `test_base.py`: con `LIBERAR`, un efecto que lanza deja la clave libre y la segunda llamada ejecuta | unit | rojo antes del fix |
| 3 | `sondear_empresa`: un efecto que lanza `OSError` se re-ejecuta en la misma ventana | unit | rojo antes del fix |
| 4 | Con `RETENER`, un efecto que lanza deja la clave tomada y la segunda llamada devuelve `None` | unit | pendiente |
| 5 | Si `liberar` falla (`ErrorDeRegistroDeIdempotencia`), sube la excepción original y queda `liberacion_de_idempotencia_fallida`; el adaptador Redis traduce `RedisError`/`OSError` a esa excepción | unit | pendiente |
| 6 | Un efecto exitoso sigue sin repetirse (casos 30 y 23, `test_base.py:13`) | unit existente | verde antes y después |
| 7 | Redis real: reservar, ver ocupada, liberar, volver a reservar; TTL de 7 días | integración | pendiente |
| 8 | Staging: invitación a un mail no verificado en SES muestra un segundo `envio_de_email_fallido`, no `tarea_omitida_por_idempotencia` | manual | tras el deploy (`TODO.md` §22) |

## Verificación (Gate 2)

`ruff format --check .`, `ruff check .`, `mypy .`, `pytest` (con Redis para el caso 7),
`python .claude/hooks/guard_architecture.py --scan .`, y el CI local (`run_local_ci.py`) porque
GitHub Actions no tiene cuota hasta el 2026-11-01. Ojo: `backend/scripts/run_local_ci.py` no está
versionado en `develop`; correrlo desde donde se usó en los PRs anteriores.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-15 | Aprobado por Luciano con las decisiones 1–5 |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones del Gate 1 (2026-10-15)

- **1. `ante_una_falla` es obligatorio en cada llamada, sin valor por defecto.** Aprobado. Las cinco
  llamadas pasan `LIBERAR` (todas son seguras de repetir, ver Diagnóstico); una tarea futura con dinero
  tendrá que elegir a conciencia.
- **2. La caída del worker (registro en dos estados + `task_time_limit`) NO entra.** Aprobado. Se anota
  como deuda en `docs/aidlc/TODO.md`.
- **3. Rama `fix/infra-…` con contexto dueño transversal.** Aprobado.
- **4. `TODO.md` §2.2 (SES en sandbox) se actualiza en esta unidad**, en un commit `docs(infra)` aparte.
  Aprobado.
- **5. Los logs con `destinatario` en `email_invitacion.py` quedan FUERA de esta unidad.** Se tratan en
  un issue aparte; esta unidad no toca ese archivo.

### Política por llamada

| Tarea | Política | Por qué |
|---|---|---|
| `identity.enviar_invitacion` | `LIBERAR` | Si el envío lanzó, el mail no salió: repetirlo es el reintento buscado. |
| `integrations.sondear_empresa` | `LIBERAR` | El cambio de estado se confirma en una transacción; la corrida repetida no encuentra nada que hacer. |
| `integrations.revisar_empresa` | `LIBERAR` | Ídem. |
| `integrations.renovar_empresa` | `LIBERAR` | Ídem. |
| `observability.registrar_latido` | `LIBERAR` | Escribir un latido dos veces es inocuo. |
