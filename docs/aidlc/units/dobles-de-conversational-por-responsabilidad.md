# Unidad: dobles-de-conversational-por-responsabilidad

**HUs**: — (refactor de tests; ver D4)   **Contexto dueño**: conversational   **Rama**: fix/conversational-dobles-por-responsabilidad

> **Gate 1 aprobado el 2026-10-09.** Refactor puro de tests: ningún cambio en `backend/src/`.
> Evidencia leída sobre `origin/develop` (`cc4fe5b`) y sobre
> `origin/feature/conversational-entregas-de-whatsapp-avisos` (`23c0880`).

## Qué hace

Parte `backend/tests/contexts/conversational/application/dobles.py` en módulos por
responsabilidad, para que ninguno pase las 400 líneas de `CLAUDE.md` §5. Ningún test cambia de
comportamiento; ningún doble cambia de interfaz.

**Fuera de esta unidad:**
- Cambiar cualquier doble (métodos, nombres, comportamiento).
- Los demás archivos de tests de más de 400 líneas (p. ej. `tests/contexts/scheduling/application/test_agenda.py`, TODO §22.42).
- Mover `escena.py` u `horario_fijo.py` (sólo se corrige la frase de `horario_fijo.py:1` que cita el tamaño de `dobles.py`).

## Hallazgos

| Dónde | Qué |
|---|---|
| `dobles.py` en `origin/develop` | **442 líneas**: ya pasa el límite hoy, no sólo en U7 |
| `dobles.py` en U6 (`plantillas-de-whatsapp-en-meta`) · U7 tramo 1 · tramo 2 · tramo 3 (`-avisos`) | 448 · 453 · 453 · **460** líneas. Cada rama lo toca (`sin_savepoint`, `para_actualizar` en `RepositorioMensajeEnMemoria.buscar_por_externo_id`, `MensajeriaEnMemoria.enviar_plantilla`) |
| Ramas locales de U8 (`scheduling-recordatorio-de-turno-modelo` / `-envio`) | Contienen la punta de `-avisos` y **no** modifican `dobles.py` (460) |
| Importadores en `-avisos` | **21 archivos**: 18 con import absoluto (`tests/api/…` ×6, `tests/contexts/conversational/…` ×6, `reporting` ×3, `scheduling` ×1, `integracion` ×2) y 3 con `from .dobles import` (`test_entregas.py:23`, `test_fallos_tipados_del_canal.py:28`, `test_id_del_envio.py:18`) |
| `horario_fijo.py:1` (`-avisos`) | El doble `HorarioFijo` ya se escribió aparte «porque `dobles.py` ya pasa de 400 líneas»: el límite ya condiciona dónde se ponen los dobles nuevos |
| `dobles.py:1-17` | El docstring del módulo documenta dos dobles (`AgendaEnMemoria` — D38 — e `InterpreteProgramado`); tiene que viajar con ellos |
| CI / hooks | El límite de 400 líneas **no** lo verifica ninguna herramienta (sólo `max-complexity = 10` en `pyproject.toml:57`): es norma, no gate |

## Diseño

Partición por responsabilidad (líneas de `-avisos`):

| Módulo nuevo | Contenido | Aprox. |
|---|---|---|
| `dobles_persistencia.py` | `sin_savepoint`, `RepositorioConversacionEnMemoria`, `RepositorioMensajeEnMemoria`, `RepositorioEscalamientoEnMemoria`, `RepositorioFAQEnMemoria`, `UsosDeFAQEnMemoria` (53-219) | ~190 |
| `dobles_modelos.py` | `InterpreteProgramado`, `TranscriptorProgramado`, `EmbeddingsEnMemoria` (221-261, 308-322) — lo que reemplaza al LLM y a la transcripción; lleva el párrafo del intérprete | ~85 |
| `dobles_colaboradores.py` | `MensajeriaEnMemoria`, `DirectorioEnMemoria`, `PublicadorEnMemoria` (263-306, 389-409) | ~80 |
| `dobles_agenda.py` | `SERVICIO_DE_PRUEBA`, `RECURSO_DE_PRUEBA`, `AgendaEnMemoria`, `un_horario`, `grilla_de` (325-441) — lleva el párrafo de D38 | ~125 |
| `dobles.py` | Fachada: docstring corto que apunta a los cuatro módulos y reexporta el mismo `__all__` (ver D1) | ~40 |

- Los nombres siguen el prefijo `dobles_` que ya usa el repo (`dobles_plantillas.py`,
  `dobles_de_reintento.py`).
- `src/`, dominio, aplicación, puertos, otros contextos y frontend: no aplica.

## Infraestructura

No aplica (sin migraciones, tareas, configuración ni integraciones).

## Dependencias y momento

- **Cortar de `develop` después del merge de U6 y U7.** Las cuatro ramas modifican `dobles.py`;
  partirlo antes las obliga a rebasar sobre un archivo que ya no existe en la misma forma.
- U8 no toca `dobles.py`; con la fachada (D1) sus imports siguen valiendo y no hay conflicto.

## Riesgos que obligan a tests

Ninguno de la lista aplica. El riesgo es de refactor: que un doble cambie al moverlo. Control:
la suite completa de `backend/tests` pasa igual antes y después, con el mismo número de tests.

## Archivos a tocar

- [x] `backend/tests/contexts/conversational/application/dobles.py` (queda como fachada)
- [x] `backend/tests/contexts/conversational/application/dobles_persistencia.py` · `dobles_modelos.py` · `dobles_colaboradores.py` · `dobles_agenda.py` (nuevos)
- [x] `backend/tests/contexts/conversational/application/horario_fijo.py` (docstring, línea 1)
- [x] Los 21 importadores: no se tocan (D1 = fachada)
- [x] `docs/aidlc/units.md` (fila)

## Casos de prueba

TDD no aplica en sentido estricto (no hay comportamiento nuevo). La red es la suite existente.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Antes de mover: `pytest backend/tests` verde y número de tests recolectados anotado (562 en `conversational`, 3450 en toda la suite) | suite | verde |
| 2 | Después: mismo número de tests, todos verdes; `mypy` y `ruff` limpios (562 y 3450; mismos ids salvo los uuid aleatorios de `test_webhook_estados`) | suite | verde |
| 3 | Ningún módulo `dobles*.py` pasa las 400 líneas (49 · 130 · 79 · 75 · 203) | revisión | verde |
| 4 | Los cuerpos de los dobles se copiaron sin cambios (mismas líneas del original, sólo cabeceras e imports nuevos) | revisión | verde |

## Decisiones para el responsable

| # | Pregunta | Recomendación |
|---|---|---|
| D1 | ¿`dobles.py` queda como fachada que reexporta, o se actualizan los 21 importadores y se borra? | **Fachada.** Cero conflictos con U8 y otras ramas en curso, y el diff queda en un solo directorio. Migrar imports es más limpio pero toca 21 archivos, varios de otros contextos |
| D2 | ¿Partición en cuatro módulos (persistencia / modelos / colaboradores / agenda) o en dos (repositorios / resto)? | **Cuatro.** Dos dejarían un «resto» de ~270 líneas sin una responsabilidad clara |
| D3 | ¿Esperar a U6+U7 o partir ya en `develop`? | **Esperar.** Hoy ya pasa el límite (442), pero no bloquea nada; partir antes fuerza cuatro rebases conflictivos |
| D4 | ¿Bajo qué épico y HU se registra en `units.md`, siendo trabajo sin historia? | Épico «Agente de WhatsApp y atención humana», HU `HS-T2` como referencia (los dobles prueban su caso de uso), igual que `ajustes-menores-del-agente` |

## Tamaño estimado

Chica en riesgo, mediana en diff: ~460 líneas movidas, ~+50 netas (cabeceras e imports). Un
commit `test(conversational): split the hand-written doubles by responsibility`.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-09 | Aprobado por Luciano con las recomendaciones D1–D4 |
| 2 · Verificación | 2026-10-09 | Aprobado por Luciano. Mismos 3450 tests recolectados antes y después; ruff, mypy, pytest y arquitectura en verde; ningún cambio en `backend/src/`. El CI local completo se corre en el Gate 3, cuando U7 entre a `develop` |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- D1: `dobles.py` queda como fachada que reexporta.
- D2: cuatro módulos (persistencia, modelos, colaboradores, agenda).
- D3: se parte sobre el código de U7 (rama apilada sobre el tramo iii); se mergea `develop` cuando U7 entre.
- D4: épico «Agente de WhatsApp y atención humana», HU `HS-T2` como referencia.
- La fachada agrega `sin_savepoint` a su `__all__`: los importadores ya lo usaban sin que estuviera listado, y reexportarlo sin listarlo haría fallar `ruff` (F401).
- No había entrada en `TODO.md` sobre el tamaño de `dobles.py`, así que no se marca nada como resuelto allí.

