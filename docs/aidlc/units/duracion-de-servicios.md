# Unidad: duracion-de-servicios

**HUs**: HU-E4-02 (y el criterio de duración de HU-E3-03) **Contexto dueño**: master_data **Rama**: feature/master_data-duracion-de-servicios

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D86 (`docs/aidlc/units.md`). La rama sale de `feature/scheduling-turnos-no-en-el-pasado`
> (cadena de ramas sobre el PR #45).

## Qué hace

Hoy la duración estándar de un servicio agendable solo tiene que ser mayor que cero: el formulario
acepta 99999 minutos (casi 70 días), y `parseInt` además trunca en silencio "12.7" a 12 y "99999abc"
a 99999. Esta unidad fija el rango de negocio **entre 5 y 480 minutos** en el agregado `Servicio`, lo
refuerza con una restricción en la base y hace que la ingesta desde planillas lo respete.

**Fuera de esta unidad:**
- El tope de la duración del **turno** (`DURACION_MAXIMA_MIN` de scheduling, hoy 24 h) es de
  `limites-e-intervalo-de-turnos`. No se toca: el rango nuevo del catálogo cabe entero en ese tope.
- HU-E4-02 RN-06 (precio final en Factura C) es de `billing`, unidad `tipos-de-comprobante-por-receptor`.
- El cierre completo de HU-E3-03 es de `normalizacion-de-datos`. Acá se cubre solo su criterio de
  duración.

## Las preguntas que el mapa dejó para este Gate

### 1. El mensaje va sin tildes
La historia escribe «La duración debe estar entre 5 y 480 minutos.», pero el sistema tiene una
convención explícita (`servicio.py`: «Without accents, like every other message in this system») y el
mensaje de duración obligatoria ya la sigue. Se usa **«La duracion debe estar entre 5 y 480
minutos.»**, con la misma diferencia documentada que ya existe.

### 2. Qué mensaje recibe cada valor inválido
| Valor | Mensaje |
|---|---|
| Vacío (`None`) en un servicio agendable | «La duracion es obligatoria para servicios agendables.» (sin cambios) |
| 0, negativos, menos de 5 o más de 480 | «La duracion debe estar entre 5 y 480 minutos.» |
| Un booleano (`True` es un `int` en Python) | Se rechaza con el mensaje de rango |

Hoy 0 y los negativos dan "obligatoria", lo que es engañoso: el usuario escribió algo. Los
docstrings de `_duracion_valida` y `_duracion_pedida` se actualizan.

### 3. La ingesta hoy descarta la duración — **hallazgo**
`IngerirServicioDesdePlanilla` recibe `agendable` y `duracion_estandar_min` de la planilla, pero
**nunca los usa**: todo servicio que entra por planilla queda no agendable y sin duración. El criterio
de HU-E3-03 («una fila con duración fuera de 5 a 480 se marca con error y no aborta el resto») es
imposible de cumplir sin leerlos. La unidad agrega el parseo, con el mismo estilo de `_precio` y
`_alicuota`:

- `agendable`: «si», «sí», «true», «1», «x» → agendable; «no», «false», «0» o vacío → no agendable;
  cualquier otro texto → error de fila.
- `duracion_estandar_min`: entero; texto no numérico → error de fila (`ErrorDeDominio`, nunca un
  `ValueError` suelto que rompa el aislamiento por fila).
- El rango lo valida el agregado, como en el panel. `_procesar_fila` ya atrapa `ErrorDeDominio` por
  fila, así que **spreadsheet_sync no cambia**.

### 4. La restricción en la base, y los datos que ya existen
Pueden existir servicios fuera de rango (el panel aceptaba cualquier entero positivo). No se corrigen
en silencio (D86). La migración `0025`:

- agrega `CHECK ((agendable AND duracion_estandar_min BETWEEN 5 AND 480) OR (NOT agendable AND
  duracion_estandar_min IS NULL))` **con `NOT VALID`**: protege toda escritura nueva sin fallar por
  las filas viejas;
- informa cuántos servicios quedan fuera de la regla (`RAISE NOTICE` con la cantidad por empresa, sin
  datos personales).

**La corrección es manual**: al editar un servicio fuera de rango desde el panel, el dominio exige un
valor válido. Cuando el informe dé cero, un `VALIDATE CONSTRAINT` en una migración posterior deja la
restricción completa. No se decide un valor por el usuario (ni un recorte automático a 480).

El modelo de SQLAlchemy declara el mismo `CheckConstraint` para que el metadata y Alembic no diverjan.

## Diseño

### Dominio — `contexts/master_data/domain/servicio.py`
- `DURACION_MINIMA_MIN = 5` y `DURACION_MAXIMA_DEL_SERVICIO_MIN = 480`: nombres propios, para no
  confundirse con `DURACION_MAXIMA_MIN` de scheduling, que es otra regla.
- `MENSAJE_RANGO_DURACION` y la comprobación de rango en `_duracion_valida`. Un solo cambio cubre
  `registrar` y `volver_agendable`, es decir, panel, planilla y cualquier camino futuro.

### Aplicación — `contexts/master_data/application/`
- `servicios.py`: sin cambios de lógica; solo el docstring de `_duracion_pedida`.
- `ingesta.py`: helpers `_agendable` y `_duracion`, y `IngerirServicioDesdePlanilla` pasa ambos valores
  a `Servicio.registrar`.

### API — `api/routers/servicios.py`
Sin cambios. **No se agrega `Field(ge=5, le=480)`** al schema: daría un 422 de Pydantic con otro
formato y otro texto. La regla vive en el dominio y llega como `detalle`.

### Frontend — `features/master_data`
- `FormularioDeServicio.tsx`: el parseo pasa a ser estricto (solo dígitos). "12.7" o "99999abc" no
  se mandan: el formulario muestra «La duracion debe ser un numero entero de minutos.» en lugar de truncar. La ayuda dice «Entre 5 y 480
  minutos.». No se duplica la regla en el cliente.

### Otros contextos
Ninguno nuevo. scheduling ya lee `duracion_estandar_min` por su ACL y no cambia.

## Infraestructura

### Migraciones
- `0025_servicio_duracion_en_rango.py`: el `CHECK ... NOT VALID` y el informe. `downgrade` quita la
  restricción. Reversible y sin backfill.

### Trabajo asíncrono · Configuración · Integraciones externas
**No aplica.**

## Riesgos que obligan a tests
- [ ] Toca dinero — no aplica
- [ ] Comprobantes fiscales — no aplica
- [ ] Webhook — no aplica
- [x] Datos por empresa — la restricción se aplica por fila y RLS no cambia; el informe no expone datos
- [ ] Salida de un LLM — no aplica
- [ ] Datos personales a un LLM — no aplica

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/master_data/domain/servicio.py`
- [x] `backend/src/cheatsheet/contexts/master_data/application/servicios.py` (docstring)
- [x] `backend/src/cheatsheet/contexts/master_data/application/ingesta.py`
- [x] `backend/src/cheatsheet/contexts/master_data/infrastructure/models.py`
- [x] `backend/migrations/versions/0025_servicio_duracion_en_rango.py`
- [x] `backend/tests/contexts/master_data/domain/test_servicio.py`
- [x] `backend/tests/contexts/master_data/application/test_servicios.py`
- [x] `backend/tests/contexts/master_data/application/test_ingesta.py`
- [x] `backend/tests/integracion/test_api_servicios.py`
- [x] `backend/tests/integracion/test_servicios_postgres.py`

### Frontend
- [x] `frontend/src/features/master_data/components/FormularioDeServicio.tsx`
- [x] `frontend/src/features/master_data/api/servicio.ts` (sin cambio neto: `duracion_estandar_min` sigue siendo `number | null`)
- [x] `frontend/src/features/master_data/components/__tests__/FormularioDeServicio.test.tsx`

### Docs
- [ ] `docs/aidlc/units.md` (estado de la fila)

## Casos de prueba

Modo: **test primero**. Los casos marcados RED tienen que fallar antes de tocar el código.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: registrar un agendable con 4, 481 y 99999 → mensaje de rango | unit | RED observado, GREEN |
| 2 | RED: 0 y -30 → mensaje de rango, no "obligatoria" | unit | RED observado, GREEN |
| 3 | RED: `volver_agendable(600)` rechaza y el servicio no queda a medias | unit | RED observado, GREEN (además cerró un hueco: `volver_agendable` dejaba `agendable=True` al rechazar) |
| 4 | RED: un booleano como duración se rechaza | unit | RED observado, GREEN |
| 5 | 5 y 480 se aceptan; vacío en agendable sigue dando "obligatoria" | unit | GREEN |
| 6 | RED: `RegistrarServicio` y `EditarServicio` fuera de rango no guardan ni auditan | unit | RED observado, GREEN |
| 7 | RED: una fila de planilla agendable con 30 crea un servicio agendable de 30 minutos | unit | RED observado, GREEN |
| 8 | RED: fila con duración 481 o "abc", o agendable con texto desconocido → `ErrorDeDominio` | unit | RED observado, GREEN |
| 9 | Tres filas con la del medio inválida: esa fila queda con error y las otras dos se ingieren (HU-E3-03) | unit | GREEN |
| 10 | RED: POST con 4 y con 99999, y PUT con 481 → 422 con el `detalle` de rango; 5 y 480 → éxito | integración (API) | escrito; se omite localmente (sin Docker), corre en CI |
| 11 | INSERT directo fuera de rango, o no agendable con duración → viola la restricción | integración (PostgreSQL) | escrito; se omite localmente (sin Docker), corre en CI |
| 12 | RED: el formulario no convierte "12.7" en 12 ni "99999abc" en 99999 | unit (frontend) | RED observado, GREEN |
| 13 | El formulario muestra el error del backend y la ayuda menciona 5 y 480 | unit (frontend) | GREEN |
| 14 | RED: "12.7", "99999abc" y "12,5" muestran «La duracion debe ser un numero entero de minutos.» y no llaman a guardar; corregir el valor limpia el mensaje; 9999 no se valida en el cliente | unit (frontend) | RED observado (4 fallos), GREEN (17 tests del archivo) |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-29 | aprobado sin cambios |
| 2 · Verificación | 2026-09-30 | aprobado. ruff, mypy y pytest en verde (1361 pasan; 341 omitidos por requerir PostgreSQL o Redis); cobertura local 74,14 % contra 74,10 % antes de la unidad (el 80 % se mide en la CI, donde corren los de integración). Frontend: lint, typecheck y test:coverage en verde (819 tests, 84,16 %; `master_data` al 100 %). `format:check` falla solo por el checkout CRLF de Windows y pasa con `--end-of-line auto`. En la primera presentación se detectó el 422 genérico de Pydantic para «12.7» y se corrigió antes de aprobar. Los casos 10 y 11 (API y PostgreSQL) los corre la CI cuando la cadena llegue a `develop` |
| 3 · PR | 2026-09-30 | PR draft [#48](https://github.com/cheatsheet12/CheatSheet/pull/48) apilado sobre el #46; la CI corre cuando la cadena llegue a `develop` |

## Decisiones tomadas durante la unidad
- Mensaje sin tildes, por la convención del sistema (§1).
- 0 y negativos dan el mensaje de rango (§2).
- La ingesta pasa a leer `agendable` y la duración (§3).
- Restricción `NOT VALID` con informe y corrección manual, sin recortes automáticos (§4).
- El formulario valida solo el formato (entero) con mensaje propio; el rango lo decide el backend. Corrige el 422 genérico de Pydantic que mostraba "Unprocessable Entity" (Gate 2, 2026-09-30).
