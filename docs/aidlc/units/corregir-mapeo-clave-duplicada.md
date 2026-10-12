# Unidad: corregir-mapeo-clave-duplicada

**HUs**: HU-E3-02   **Contexto dueño**: spreadsheet_sync
**Rama**: fix/spreadsheet_sync-corregir-mapeo-clave-duplicada

## Qué hace

Corrige un bug encontrado en la prueba manual de HU-E3-02 (Etapa 6, responsable Juan): corregir a
mano una columna de un mapeo ya existente (`PUT /planillas/mapeos/{id}/columnas`) tira 500 con
`IntegrityError: duplicate key value violates unique constraint "entrada_de_mapeo_pkey"`. Rompe el
segundo criterio de aceptación de la HU ("Corrijo manualmente una asignación → El sistema acepta
el cambio y actualiza la vista previa") en el único camino de ingesta que hoy funciona de punta a
punta (archivo subido), así que es más grave que cualquier otro hallazgo de hoy.

## Diseño

- **Dominio**: no cambia.
- **Aplicación**: no cambia. `CorregirMapeo.ejecutar` (`application/mapeos.py:216`) hace lo
  correcto: carga el mapeo, lo corrige en memoria, pide persistirlo.
- **Puertos y adaptadores** — la causa raíz:
  `RepositorioMapeoPostgres.actualizar` (`infrastructure/repositories.py:192`) borraba todas las
  entradas existentes (`DELETE FROM entrada_de_mapeo WHERE mapeo_id = ...`) y las volvía a crear
  con `_agregar_entradas`, usando los mismos `id` — una entrada no cambia de identidad al
  corregirse, `Mapeo.corregir` solo llama a `entrada_de(columna).asignar(atributo)` sobre la que ya
  existe.

  **Primer diagnóstico (descartado con un test):** se sospechó que el `delete()` de SQLAlchemy Core
  no sincronizaba el mapa de identidad de la sesión con lo que `buscar_por_id` ya había cargado. Un
  test de integración que repite exactamente esa secuencia (cargar, corregir, guardar, dos veces
  sobre el mismo mapeo) pasó **incluso sin ningún cambio**, así que esa no es la causa.

  **Causa real:** el patrón "borrar todo e insertar de nuevo con los mismos `id`" es frágil bajo
  dos escrituras casi simultáneas sobre el mismo mapeo — algo plausible dado que toda la sesión de
  prueba mostró un patrón de doble clic en la UI (el primer clic parece no registrar). Si dos
  correcciones se solapan, cada una puede borrar lo que la otra está por insertar, y la que pierde
  la carrera termina insertando un `id` que la otra ya confirmó — exactamente el
  `UniqueViolationError` sobre `entrada_de_mapeo_pkey` que se vio en producción. No se reprodujo la
  carrera exacta en un test automatizado (requeriría controlar el entrelazado de dos transacciones
  de Postgres), así que esta causa se infiere por descarte y por el patrón de uso observado, no se
  demostró en rojo.

  El fix reemplaza "borrar todo e insertar" por **`merge()`** (actualizar-si-existe) para cada
  entrada vigente, y solo `delete()` para las que de verdad dejaron de estar en el mapeo (un cambio
  de estructura real, RN-03 de HU-E3-04). `merge()` nunca intenta un `INSERT` de un `id` que podría
  ya existir — dos escrituras concurrentes sobre la misma entrada se serializan como dos `UPDATE`
  de fila en Postgres, no como un choque de clave primaria.
- **Otros contextos**: ninguno.
- **Frontend**: no cambia.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero
- [ ] Toca comprobantes fiscales / CAE
- [ ] Consume un webhook
- [ ] Agrega datos con `tenant_id`
- [ ] Usa salida de un LLM
- [ ] Datos personales o fiscales

Ninguno aplica directamente, pero el bug es de persistencia (clave duplicada), así que el caso de
prueba nuevo tiene que llegar hasta la base real — un test de unidad con un repositorio falso no lo
hubiera atrapado (el bug es específico de SQLAlchemy/Postgres). Va como test de integración.

## Archivos a tocar

- [x] backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/repositories.py
- [x] backend/tests/integracion/test_mapeos_postgres.py (nuevo caso)

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Corregir dos columnas distintas, una después de la otra, sobre un mapeo ya persistido, deja las dos asignaciones guardadas sin `IntegrityError` | integración | aprobado |
| 2 | Toda la suite existente de `spreadsheet_sync` (unit + integración) sigue en verde | unit + integración | aprobado |

No se agregó un test de la condición de carrera en sí (dos escrituras concurrentes): requeriría
controlar el entrelazado de dos transacciones de Postgres, frágil de simular de forma determinista.
Queda pendiente reverificar en caliente contra staging, donde se originó el reporte.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | aprobado |
| 2 · Verificación | 2026-10-12 | `ruff format --check .`, `ruff check .` y `mypy .` verdes (866/861 archivos). `pytest` **completo contra Postgres local real** (no el modo habitual que salta 654 por falta de base): 3924 passed, 0 failed, 2 warnings preexistentes sin relación (marca `asyncio` de más en un test sincrónico de `integrations`, ajeno a este cambio) |
| 3 · PR | 2026-10-12 | abierto: https://github.com/cheatsheet12/CheatSheet/pull/163 |

## Decisiones tomadas durante la unidad

- Encontrado durante la prueba manual de HU-E3-02 en staging — Juan priorizó arreglarlo antes de
  seguir con el hallazgo de la IA (menos grave: tiene un camino manual que funciona) y antes que
  HU-E3-04/07 (brecha de infraestructura más grande, fuera de alcance de hoy).
