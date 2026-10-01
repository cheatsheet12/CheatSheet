# Unidad: reporte-fallido-persistido

**HUs**: HU-E10-03   **Contexto dueño**: reporting   **Rama**: fix/reporting-reporte-fallido-persistido

> Origen: hallazgo de la unidad `revocacion-por-reuso` (PR #47, sin mergear), sección «Radio de
> impacto»: `reporting/application/generacion.py:139-146`, «que la fila quede en FALLIDO y no
> desaparezca». El bug existe desde `d2f5ded` (2026-09-07, `reporteria-y-paquete-contable`). Es un
> `fix/…` cortado de `develop` (`ba3f889`); el PR va a `develop` y no depende de #47.

## Qué hace

Cuando falla el armado o el guardado del archivo de un reporte, `GenerarReporte` marca la fila
`FALLIDO` y levanta `GeneracionFallida`, pero la transacción se descarta y **la fila desaparece**: el
historial no muestra nada y no queda evidencia del fallo, contra D65 y contra el docstring de
`GeneracionFallida`. Esta unidad hace que la fila `FALLIDO` **se confirme en la base** antes de
responder el error.

Comportamiento observable después del fix: un fallo de generación responde **el mismo error de hoy**
(422, `error = "GeneracionFallida"`), y el historial (`GET /reporteria/reportes`) muestra la fila con
estado `FALLIDO`, no descargable. Volver a pedir el reporte crea **otra** fila (D65).

**Fuera de esta unidad:**
- El paquete contable (`GenerarPaqueteContable`), con el mismo patrón pero sin estado `FALLIDO` (ver P2).
- El código HTTP de un fallo de almacenamiento (hoy 422 por heredar de `EntradaInvalida`; un 5xx sería
  más exacto, pero cambia el contrato y no es este bug).
- Un evento de auditoría con `Resultado.ERROR` para la generación fallida (hoy no se publica ninguno).
- Cambiar la semántica de `unidad_de_trabajo` / `sesion_de_empresa` (opción C, descartada en #47).

## La historia

> **HU-E10-03 — Generar y descargar un reporte en el formato deseado**
>
> Como administrador u operador, quiero generar y descargar un reporte en el formato que necesito,
> para analizar la información fuera de la plataforma o compartirla.
>
> * RN-02: La generación registra el tipo, formato, filtros y período, conforme a la entidad Reporte.
> * RN-03: El archivo generado queda disponible para descarga y referencia posterior.
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | Solicito generar un reporte en un formato | El sistema lo genera y lo deja disponible para descarga | PAN-REP-01 |
> | Consulto reportes generados antes | Veo el historial con su tipo, formato y período | PAN-REP-01 |

Decisiones del épico que gobiernan el fix: **D64** (la generación es síncrona; `EN_CURSO` existe
igual) y **D65** (un reporte `FALLIDO` no se reintenta sobre la misma fila: «el historial tiene filas
fallidas. Eso es el punto»). Estados del DER: `estado_reporte: PENDIENTE · EN_CURSO · LISTO · FALLIDO`.

## Lo que ya existe y el hueco

Existe todo lo de dominio y aplicación: `EstadoReporte`, `TRANSICIONES_LEGALES` sin salida desde
`FALLIDO`, `Reporte.fallar()`, el `guardar(FALLIDO)` en la rama de error de `GenerarReporte`, el test
unitario `test_un_fallo_del_almacenamiento_deja_la_fila_en_fallido` y el panel, que ya pinta `FALLIDO`
como error.

El hueco está en la frontera transaccional: la ruta deja escapar `GeneracionFallida` dentro del
cuerpo del `async for`, y eso descarta lo escrito. El test unitario pasa con el bug presente porque
los dobles en memoria no tienen transacción, y ningún test de integración provoca un fallo de
almacenamiento.

## Hallazgos

| Dónde | Qué |
|---|---|
| `contexts/reporting/application/generacion.py:128-130` | `agregar` + `empezar()` + `guardar` (fila en `EN_CURSO`) |
| `contexts/reporting/application/generacion.py:138-146` | ante cualquier fallo: `fallar()`, `guardar(FALLIDO)`, `raise GeneracionFallida` |
| `contexts/reporting/infrastructure/repositories.py:66-91` | `agregar` y `guardar` hacen `flush()`, nunca `commit()` |
| `platform/database.py:172-182` | `sesion_de_empresa` confirma **después** del `yield`; ante una excepción, rollback |
| `api/dependencies.py:109-119` | `unidad_de_trabajo` hace `yield` dentro de `sesion_de_empresa` |
| `api/routers/reporteria.py:364-391` | `POST /reporteria/reportes` llama a `GenerarReporte` dentro del `async for`, sin atrapar: el `raise` cae en el consumidor, el generador no se reanuda, no hay `commit()` y la fila se pierde |
| `contexts/reporting/application/errors.py:66-72` | el docstring de `GeneracionFallida` promete «la fila se conserva» |
| `api/errors.py:36` | `EntradaInvalida` → 422: el contrato que no debe cambiar |
| `tests/contexts/reporting/application/test_generacion.py:125-131` | el test de `FALLIDO` usa dobles sin transacción: verde con el bug |
| `workers/` (grep) | **ningún worker llama a `GenerarReporte`**: la generación es síncrona (D64, `generacion.py:12-16`). No hay reintentos de Celery ni DLQ en juego; el «reintento» es el usuario volviendo a pedir, que crea otra fila (D65) |
| `contexts/reporting/application/paquete.py:287-309` | mismo patrón en `GenerarPaqueteContable`: si el período es nuevo, la fila agregada en `:296` se pierde en el rollback; `PaqueteContable` no tiene estado (`domain/paquete.py:144-170`) |
| `api/routers/reporteria.py:424-460` y `workers/tasks_reporting.py:76-101` | los dos llamadores del paquete. El worker no reintenta (`:12-15`, `:144`); la excepción llega a Celery por `workers/ejecucion.py:50-57` como FAILURE; no pasa por la DLQ (que trabaja sobre `tarea_asincrona`). Como el barrido filtra por el día configurado (`:58-60`), el próximo intento es el mes siguiente y del fallo queda solo un `logger.warning` |
| `frontend/src/features/reporting/components/GeneradorDeReportes.tsx:111-122` | el historial se recarga solo si la generación sale bien; ya muestra `FALLIDO` (`:61`) |

## Preguntas

1. **P1 — Opción de fix.** (La confirma una persona en el Gate 1.)

   | | Opción | A favor | En contra |
   |---|---|---|---|
   | **A** | `GenerarReporte` devuelve el reporte fallido en vez de levantar; el router levanta después del bucle | sin excepciones para control de flujo | cambia el contrato del caso de uso y sus tests |
   | **B** | El router atrapa **solo** `GeneracionFallida` dentro del cuerpo, deja que el generador confirme y la relanza después del bucle | el mismo patrón de #47 (`_rotar_refresh`); el caso de uso y el contrato HTTP no cambian | es una convención que hay que recordar (#47 la documenta en `unidad_de_trabajo`) |
   | **C** | `unidad_de_trabajo` confirma ante ciertos errores | arregla la clase entera | rompe la atomicidad de todos los casos de uso; descartada en #47 |
   | **D** | Transacción aparte para marcar `FALLIDO` | sobrevive a cualquier rollback | dos transacciones para un caso que no tiene nada más que revertir |

   **Recomendación: B**, por consistencia con #47: la frontera de la transacción es del router (R2).

2. **P2 — El paquete contable.** **Necesita una persona.** No tiene estado `FALLIDO`, así que
   «persistir» la fila de un período nuevo sin archivo no marca el fallo: solo ocupa el índice único.
   El fallo del barrido mensual hoy no deja más rastro que un log, y no se reintenta hasta el mes
   siguiente. Darle rastro pide decidir un estado (o una bitácora) que el DER no tiene.
   **Recomendación:** no tocarlo acá; registrar en `units.md` una unidad pendiente
   `paquete-fallido-visible` (reporting, HU-E10-04).

3. **P3 — Refrescar el historial en el panel cuando la generación falla.** **Necesita una persona**
   (suma frontend). Sin esto, la fila `FALLIDO` aparece recién al recargar la página.
   **Recomendación:** sí; mover `listarReportes()` a un `finally` (o repetirlo en el `catch`) de
   `generar()` en `GeneradorDeReportes.tsx`, con su test en `pantallas.test.tsx`.

## Diseño

- **Dominio**: sin cambios.
- **Aplicación**: sin cambios de comportamiento. Una línea en el docstring de `GenerarReporte`:
  «levanta `GeneracionFallida` **después** de guardar `FALLIDO`; quien abre la transacción tiene que
  confirmarla antes de relanzar». Es el contrato para cualquier llamador futuro (por ejemplo, un
  worker si D64 deja de valer).
- **Puertos y adaptadores**: sin cambios.
- **API** (`api/routers/reporteria.py`): la ruta `generar` delega en una función privada de módulo
  `_generar_reporte(recursos, actor, entrada, desde, hasta) -> ReporteSalida`, por complejidad
  (`max-complexity = 10`) y para quedar en ≤ 50 líneas, igual que `_rotar_refresh` en #47:
  ```python
  salida: ReporteSalida | None = None
  fallo: GeneracionFallida | None = None
  async for unidad in unidad_de_trabajo(recursos, empresa_id):
      piezas = Reporteria.armar(unidad, recursos.settings)
      ahora = unidad.reloj.ahora()
      try:
          reporte = await GenerarReporte(...).ejecutar(...)
      except GeneracionFallida as error:
          # La fila ya quedó en FALLIDO: hay que confirmarla (D65). Levantar acá la borraría.
          fallo = error
      else:
          salida = _a_reporte(reporte)
  if fallo is not None:
      raise fallo
  return _exigir(salida)
  ```
  Solo se atrapa `GeneracionFallida`. `SinDatosEnElPeriodo`, el rechazo por rol, un formato inválido
  o un período inválido no escribieron nada y siguen descartando la transacción.
- **`api/dependencies.py`**: **no se toca**. #47 agrega en el docstring de `unidad_de_trabajo` la
  trampa y la convención; editarlo acá produciría un conflicto.
- **Otros contextos**: no aplica.
- **Frontend**: solo si P3 = sí; `features/reporting/components/GeneradorDeReportes.tsx`, sin cambios
  en `index.ts`.

## Infraestructura

- **Migraciones**: no aplica. La tabla `reporte` y el enum `estado_reporte` ya admiten `FALLIDO`.
- **Trabajo asíncrono**: no aplica. La generación es síncrona (D64) y ningún worker la ejecuta. Si
  algún día se encola, la tarea tiene que aplicar el mismo patrón y **no** reintentar sobre la misma
  fila (D65).
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica (el almacenamiento ya existe; los tests no lo tocan de verdad).

## Riesgos que obligan a tests

- [ ] Toca dinero: no aplica
- [ ] Comprobantes fiscales / CAE: no aplica
- [ ] Webhook: no aplica
- [ ] Datos con `empresa_id`: no aplica; no se agregan datos nuevos. La fila confirmada corre bajo la
      RLS de la empresa del request; el aislamiento de `reporte` ya lo cubre
      `test_reporteria_postgres.py::test_un_reporte_de_otra_empresa_no_se_ve`
- [ ] Salida de un LLM: no aplica
- [ ] Datos personales a un LLM: no aplica
- [x] **Atrapar de más**: confirmar ante un error que no escribió `FALLIDO` persistiría escrituras
      parciales; lo cubre el caso 3
- [x] **Conflicto con #47** en `docs/aidlc/units.md` (ver Registro); ningún archivo de código en común

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/api/routers/reporteria.py` (ruta `generar` → `_generar_reporte`)
- [ ] `backend/src/cheatsheet/contexts/reporting/application/generacion.py` (solo el docstring de `GenerarReporte`)
- [ ] `backend/tests/api/test_reporte_fallido_se_confirma.py` (nuevo, unitario local)
- [ ] `backend/tests/integracion/test_api_reporteria.py` (casos de integración nuevos)

### Frontend (solo si P3 = sí)
- [ ] `frontend/src/features/reporting/components/GeneradorDeReportes.tsx`
- [ ] `frontend/src/features/reporting/components/__tests__/pantallas.test.tsx`

### Docs
- [ ] `docs/aidlc/units.md` (fila de la unidad, ver Registro)
- [ ] `docs/aidlc/units/reporte-fallido-persistido.md` (este plan)

## Casos de prueba

Modo: **test primero** (`CLAUDE.md`: todo bug arreglado empieza con un test que lo reproduce). Los
casos RED tienen que fallar contra el código actual **por el motivo correcto** (la transacción no
confirmó / la fila no está), no por un error de armado del test. El commit del test va antes que el
del fix.

**Caso 1 (local).**
- **Armado**: `create_app` con `Recursos` de nulos.
- **Monkeypatch** sobre el módulo `cheatsheet.api.routers.reporteria`:
  - `unidad_de_trabajo` → doble que confirma después del `yield`, igual que
    `tests/api/test_refresh_confirma_la_revocacion.py` de #47.
  - `Reporteria.armar` → piezas con `RepositorioReportesEnMemoria` y `ArchivosEnMemoria(falla=True)`,
    de `tests/contexts/reporting/application/dobles.py`.
  - `armar_facturacion`, `armar_cobranzas` y `armar_bitacora` → `FacturacionFalsa` con filas,
    `CobranzasFalsas` y `BitacoraFalsa`.
- **Caso de uso**: `GenerarReporte` **real**.
- **Autenticación**: un JWT de rol `ADMINISTRADOR` emitido con
  `EmisorDeTokensJWT(secreto=settings.jwt_secret, …)`, para que `EmpresaMiddleware` llene
  `request.state`.
- **Sin red ni base.**

**Casos 4 y 5 (PostgreSQL).**
- **Armado**: el fixture `cliente_http` de `test_api_reporteria.py`.
- **Monkeypatch** de `cheatsheet.contexts.reporting.infrastructure.ensamblado.almacenamiento` con una
  función que devuelve un almacenamiento cuyo `guardar` levanta. `Reporteria.armar` lo resuelve en cada
  llamada, así que el `lru_cache` no interfiere.
- **Dónde corren**: se omiten localmente sin Docker (`requiere_base`) y corren en CI, porque este PR
  va a `develop`.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED**: con el almacenamiento fallando, `POST /reporteria/reportes` → el doble de la unidad de trabajo **confirmó**, la respuesta es 422 con `error = "GeneracionFallida"` y el repositorio en memoria tiene una fila `FALLIDO`. **Hoy falla en `assert estado.confirmo is True`** (queda `False`: la excepción escapa del cuerpo y el generador nunca llega a la línea de confirmación) | unit (local, sin Docker) | pendiente |
| 2 | Guardia del doble: un cuerpo que levanta **no** confirma (demuestra que el doble modela el bug y que el RED del 1 es real) | unit (local) | pendiente |
| 3 | No se atrapa de más: con `FacturacionFalsa` sin filas → 422 con `MENSAJE_SIN_DATOS` y **sin** confirmar; con rol `SOLO_LECTURA` → 422 y **sin** confirmar | unit (local) | pendiente |
| 4 | **RED**: con el almacenamiento fallando, `POST /reporteria/reportes` → 422 `GeneracionFallida`; `GET /reporteria/reportes` devuelve **una** fila con `estado = "FALLIDO"` y `descargable = false`. **Hoy falla porque el historial vuelve vacío** (`[]`): la fila se descartó en el rollback | integración (PostgreSQL) | pendiente; corre en CI |
| 5 | D65 de punta a punta: después del 4, con el almacenamiento restaurado, volver a pedir → 201; el historial tiene **dos** filas, una `FALLIDO` y una `LISTO` | integración (PostgreSQL) | pendiente; corre en CI |
| 6 | El camino feliz no cambia: `test_generar_y_descargar_un_reporte_de_operaciones` y `test_un_periodo_sin_datos_da_la_frase_de_la_historia` siguen verdes sin cambios | integración (existente) | pendiente; corre en CI |
| 7 | Los unitarios existentes de `test_generacion.py` siguen verdes sin cambios | unit (existente) | pendiente |
| 8 | (Solo si P3 = sí) un fallo al generar muestra el error **y** recarga el historial (`listarReportes` llamado tras el rechazo de `generarReporte`) | unit frontend (Vitest) | pendiente |

El 1 es la evidencia local del RED, y su límite es que el doble reproduce a mano el contrato de
`sesion_de_empresa` (por eso el 2). El 4, contra la base real, es el que cierra el hallazgo; su RED lo
confirma la primera corrida de CI sobre el commit del test solo.

## Verificaciones que no se pueden hacer acá

- Los casos 4 a 6 necesitan PostgreSQL. Sin Docker local se omiten: **el Gate 2 no se cierra sin la
  salida real del CI** en esos casos.
- El comportamiento contra R2 real (un error del SDK de verdad) no se prueba: los tests no tocan la
  red. El `except Exception` del caso de uso ya cubre lo que levante el SDK.
- El fallo en el panel de `staging` (P3) solo se puede ver allí, provocando un fallo de almacenamiento,
  y no es reproducible a pedido; queda cubierto por el caso 8.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

Fila de `units.md` en esta rama (épico existente «Reportería y paquete contable», inmediatamente
después de `reporteria-y-paquete-contable`). #47 agrega en la misma posición la misma unidad con
`— | — | pendiente`. Cuando se mergeen las dos ramas, git va a marcar un conflicto en ese bloque. Se
resuelve conservando la versión de esta rama (responsable, rama y estado más avanzados), sin duplicar
la fila.

## Decisiones tomadas durante la unidad
-
