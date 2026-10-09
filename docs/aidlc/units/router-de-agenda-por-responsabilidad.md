# Unidad: router-de-agenda-por-responsabilidad

**HUs**: HU-E7-01 … HU-E7-06 (sólo como referencia; ver D4)   **Contexto dueño**: scheduling   **Rama**: fix/scheduling-router-de-agenda-por-responsabilidad

> **Gate 1 aprobado el 2026-10-09.** Origen: TODO §22.42 (`docs/aidlc/TODO.md:667` en
> `origin/develop`) y la nota de la línea 669. Refactor sin cambio de comportamiento: misma
> superficie HTTP, mismos códigos, mismas formas. Evidencia leída sobre `origin/develop`
> (`cc4fe5b`).

## Qué hace

Parte `backend/src/cheatsheet/api/routers/agenda.py` (688 líneas, límite 400 de `CLAUDE.md` §5) en
módulos por responsabilidad. Ningún endpoint cambia de ruta, método, entrada, salida ni código de
estado.

**Fuera de esta unidad:**
- `scheduling/application/turnos.py` (~520) y la extracción de `Avisador` (nota de §22.42): U8
  modifica `turnos.py` (`Avisador.recordatorio`, `franja_asignada_en`).
- `RecursosReservables.tsx` (~640) y `tests/contexts/scheduling/application/test_agenda.py` (~1180).
- Unificar `_actor` / `_exigir`, hoy duplicados en al menos ocho routers (`bitacora.py:178,204`,
  `categorias.py:64`, `clientes.py:132`, `conversaciones.py:166,182`, …): se reporta, no se hace.
- Achicar cada fábrica de rutas a ≤ 50 líneas (ver D2).

## Hallazgos

| Dónde (`origin/develop`) | Qué |
|---|---|
| `api/routers/agenda.py` | **688 líneas** en todas las ramas vivas (develop, U6, U7 ×3) |
| `agenda.py:62-128` · `129-201` | Modelos de entrada (8) y de salida (9) |
| `agenda.py:203-298` | Conversiones (`_a_recurso`, `_a_turno`, `_patrones`, `_tipo_de_recurso`, `_excepcion`) y ayudantes (`_actor`, `_rango`, `_exigir`) |
| `agenda.py:300-305` | `crear_router`: incluye `/recursos` y `/turnos` |
| `agenda.py:307-486` | Recursos: `_rutas_de_recursos` (61 líneas) incluye `_rutas_de_configuracion` (67) y `_rutas_de_excepciones` (47) con prefijo `/{recurso_id}` (`365-366`) |
| `agenda.py:488-688` | Turnos: `_rutas_de_turnos` (114 líneas) incluye `_rutas_de_gestion` (85) con prefijo `/{turno_id}` (`600`) |
| `agenda.py:521` vs `557` | **`GET /turnos/disponibilidad` se registra antes que `GET /turnos/{turno_id}`.** Si se invierte el orden al mover, «disponibilidad» se toma como `turno_id` y contesta 422 |
| `api/main.py:23-24,105` | Único consumidor: `agenda.crear_router(recursos)` |
| `api/routers/tablero_salida.py:1-8` | Precedente: la forma HTTP del tablero salió de `reporteria.py` «porque ya pasaba de las 500 líneas» |
| `tests/integracion/test_api_agenda.py` | 30 tests de la API de agenda, **contra PostgreSQL**: en local se saltean, corren en la CI |
| Ramas sin mergear (remotas y locales, incl. U7 y U8) | **Ninguna modifica `api/routers/agenda.py`.** U7 y U8 tocan `api/agenda.py` (el armado), no el router; la firma de `armar_avisador` / `armar_catalogo` que usa el router no cambia para sus llamadores |

## Diseño

| Módulo | Contenido | Aprox. |
|---|---|---|
| `api/routers/agenda.py` | Docstring actual + `crear_router` (incluye los dos grupos). `main.py` no cambia | ~45 |
| `api/routers/agenda_forma.py` | Entradas, salidas, conversiones, `actor` y `exigir` — «la forma HTTP de la agenda», como `tablero_salida.py` | ~250 |
| `api/routers/agenda_recursos.py` | `rutas_de_recursos` + `_rutas_de_configuracion` + `_rutas_de_excepciones` (PAN-AGE-03, HU-E7-04/05) | ~220 |
| `api/routers/agenda_turnos.py` | `rutas_de_turnos` + `_rutas_de_gestion` + `_rango` (PAN-AGE-01/02, HU-E7-01/02/03/06) | ~250 |

- Los cuerpos de los endpoints se mueven sin cambios; sólo cambian los nombres de lo que pasa a
  cruzar módulos (sin `_`). El orden de registro de rutas se conserva tal cual.
- Sin import circular: `agenda.py` importa a `agenda_recursos` y `agenda_turnos`; éstos sólo
  importan `agenda_forma`.
- Dependencias R1–R5: sin cambios (todo queda en `api/`).
- Dominio, aplicación, puertos, otros contextos, frontend: no aplica.

## Infraestructura

No aplica (sin migraciones, tareas, configuración ni integraciones).

## Dependencias y momento

**Puede empezar ya, cortada de `develop`.** Ninguna rama en curso toca el router. Al mergearse U7
o U8 después, el único punto de contacto es el import de `api/agenda.py`, que no cambia de nombre.

## Riesgos que obligan a tests

Ninguno de la lista aplica (no hay dinero, CAE, webhook, datos nuevos ni LLM). El riesgo es de
refactor: cambiar una ruta, su orden o una forma de respuesta sin que nada local lo detecte, porque
los tests de la API de agenda sólo corren contra PostgreSQL.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/api/routers/agenda.py`
- [ ] `backend/src/cheatsheet/api/routers/agenda_forma.py` · `agenda_recursos.py` · `agenda_turnos.py` (nuevos)
- [ ] `backend/tests/api/test_rutas_de_agenda.py` (nuevo, ver D3)
- [ ] `docs/aidlc/TODO.md` (§22.42 → resuelta; nota de la 669 actualizada) · `docs/aidlc/units.md` (fila)

## Casos de prueba (TDD: la caracterización se escribe y pasa **antes** de mover nada)

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Caracterización: la tabla (método, ruta, código de estado, modelo de respuesta) de todas las rutas de `crear_router` es la esperada — verde sobre el código actual | unit (sin base) | verificado en local |
| 2 | `GET /turnos/disponibilidad` está registrada antes que `GET /turnos/{turno_id}` | unit | verificado en local |
| 3 | Después de partir: 1 y 2 siguen verdes; `ruff`, `mypy --strict`, `pytest` limpios | suite | verificado en local |
| 4 | `tests/integracion/test_api_agenda.py` (30 casos) verde en la CI | integración (CI) | pendiente (CI) |
| 5 | Ningún módulo nuevo pasa las 400 líneas | revisión | verificado en local |

## Decisiones para el responsable

| # | Pregunta | Recomendación |
|---|---|---|
| D1 | ¿Módulos planos (`agenda_*.py`) o subpaquete `api/routers/agenda/`? | **Planos.** Sigue el precedente de `tablero_salida.py`, `main.py` no cambia y no se agrega un directorio |
| D2 | ¿Además del archivo, bajar cada fábrica de rutas a ≤ 50 líneas (hoy 61, 67, 47, 114 y 85)? | **No en esta unidad.** El patrón de cierres por fábrica es el de todos los routers; cambiarlo es otra decisión. Se registra en el TODO como hallazgo |
| D3 | ¿Agregar la prueba de caracterización de rutas, que corre sin base? | **Sí.** Es la única red local: los 30 tests de la API sólo corren en la CI |
| D4 | ¿Bajo qué épico se registra, siendo trabajo sin historia? | Épico «Agenda y recursos», con las HUs del router como referencia, igual que las unidades `fix/…` anteriores |
| D5 | ¿Empezar ya o esperar a U7/U8? | **Ya.** Ninguna rama en curso toca el archivo; esperar sólo agrega riesgo de que alguien lo toque |

## Tamaño estimado

Mediana en diff, baja en riesgo: ~690 líneas movidas, ~+70 netas (cabeceras, imports, test de
caracterización ~60). Dos commits: `test(scheduling): pin the agenda router's route table` y
`refactor(scheduling): split the agenda router by responsibility`.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-09 | aprobado con todas las decisiones (D1–D5) según la recomendación |
| 2 · Verificación | 2026-10-09 | aprobado por el responsable de la fase; revisión independiente sin bloqueantes. ruff, mypy y pytest en verde en local (2370 pasan, 525 omitidos por requerir PostgreSQL o Redis). La confirmación de los 30 casos de `test_api_agenda.py` queda para la CI del PR o para Docker local |
| 3 · PR | 2026-10-09 | PR a `develop`. GitHub Actions sin cuota hasta el 2026-11-01: verificado con el CI local (`backend/scripts/run_local_ci.py`), resumen en el PR |

## Decisiones tomadas durante la unidad

- Casos 1, 2, 3 y 5 verificados en local; el 4 corre en la CI. Archivos nuevos: 29, 252, 218 y 254 líneas.

---

**Gate 1 aprobado el 2026-10-09** por el responsable de la fase, con todas las decisiones según la recomendación.
