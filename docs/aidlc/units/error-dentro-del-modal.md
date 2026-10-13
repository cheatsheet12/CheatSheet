# Unidad: error-dentro-del-modal

**HUs**: HU-E7-02, HU-E7-04, HU-E7-05   **Contexto dueño**: scheduling   **Rama**: fix/scheduling-error-dentro-del-modal

> Origen: issue #74 (transversal, abierto el 03/10/2026), visto también en la prueba manual de la
> Etapa 6 en Agenda (12/10/2026) y documentado en MAN-70. Severidad **Menor**. Esta unidad lo
> corrige **solo en los cuatro diálogos de la Agenda**; el resto de la app (#74) queda abierto.
> Es un `fix/…` cortado de `develop`; el PR va a `develop`.

## Qué hace

El error de una acción hecha dentro de un diálogo se pintaba arriba de la página, detrás del
diálogo que seguía abierto. Quien apretaba «Guardar horario» con un slot inválido no veía nada y
pensaba que se había guardado.

Comportamiento observable después del fix:

- **Configurar recurso** (horario, servicios y excepciones): el rechazo se muestra en el pie fijo
  del diálogo, arriba de «Listo». El diálogo es largo y el pie es lo único que se ve siempre.
- **Agregar recurso**, **Reprogramar turno** y **Cancelar turno**: el rechazo se muestra arriba
  del contenido del diálogo.
- **Cancelar turno** ya no cierra el diálogo antes de pedir: se cierra cuando el backend acepta, y
  si rechaza, el motivo queda a la vista dentro del diálogo.
- Abrir o cerrar un diálogo borra el error anterior.
- Con ningún diálogo abierto, el error se sigue mostrando en la página, como hasta ahora.

**Fuera de esta unidad:** los diálogos de los otros módulos (Configuración, Respuestas
frecuentes, Clientes, etc.), que son el resto de #74.

## La historia

> **HU-E7-04** — «La hora de inicio debe ser anterior a la hora de fin.», «La duración del slot
> debe estar entre 5 y 480 minutos.»; **HU-E7-05** — «Ya existe una excepción para esa fecha en
> este recurso.»; **HU-E7-02** — «El horario seleccionado no está disponible.». Son mensajes que
> la historia pide **mostrar**, y detrás del diálogo no se ven.

## Lo que ya existe y el hueco

| Dónde | Qué |
|---|---|
| `features/scheduling/components/RecursosReservables.tsx` | Un solo `error` para la pantalla, pintado arriba de la página; los diálogos «Agregar recurso» y «Configurar» no lo muestran |
| `features/scheduling/components/EditorDeRecurso.tsx` | Todas sus operaciones (horario, servicios, excepciones) corren por `onCorrer` del padre, que es quien guarda el error |
| `features/scheduling/components/DetalleDeTurno.tsx` | Un solo `error` pintado arriba de la página; «Cancelar turno» cerraba el diálogo antes de pedir para que el error se viera |

## Diseño

- **Dominio / Aplicación / Puertos**: no aplica.
- **Frontend**:
  - `RecursosReservables.tsx`: con un diálogo abierto, la alerta de la página no se pinta; la de
    «Agregar recurso» va dentro de su formulario y la de «Configurar» se le pasa al editor.
    Abrir y cerrar cada diálogo pasa por una función que borra el error.
  - `EditorDeRecurso.tsx`: nueva prop `error`, pintada en el pie fijo arriba de «Listo».
  - `DetalleDeTurno.tsx`: la misma regla para «Reprogramar turno» y «Cancelar turno»; cancelar
    cierra el diálogo al tener éxito, no antes de pedir.
  - `shared/pantallas-agente.css`: el pie del editor apila la alerta y la acción.

## Infraestructura

No aplica.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [ ] Datos con `empresa_id` → no aplica (solo presentación)
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales → no aplica

## Archivos a tocar
- [x] frontend/src/features/scheduling/components/RecursosReservables.tsx
- [x] frontend/src/features/scheduling/components/EditorDeRecurso.tsx
- [x] frontend/src/features/scheduling/components/DetalleDeTurno.tsx
- [x] frontend/src/shared/pantallas-agente.css
- [x] frontend/src/features/scheduling/components/__tests__/errores-en-los-modales.test.tsx (nuevo)
- [x] docs/aidlc/units.md (mi fila) · docs/aidlc/units/error-dentro-del-modal.md

## Casos de prueba

Se escriben **antes** del arreglo y tienen que fallar con el código actual (`CLAUDE.md` §5).

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Configurar: el rechazo de «Guardar horario» se lee dentro del diálogo, una sola vez | componente (vitest) | ✅ (falló antes del arreglo) |
| 2 | Configurar: al cerrar y volver a abrir no queda el error anterior | componente (vitest) | ✅ (falló antes del arreglo) |
| 3 | Agregar recurso: el rechazo se lee dentro del diálogo | componente (vitest) | ✅ (falló antes del arreglo) |
| 4 | Reprogramar turno: el rechazo se lee dentro del diálogo, que sigue abierto | componente (vitest) | ✅ (falló antes del arreglo) |
| 5 | Cancelar turno: el rechazo se lee dentro del diálogo, que sigue abierto | componente (vitest) | ✅ (falló antes del arreglo) |
| 6 | Cancelar turno: si el backend acepta, el diálogo se cierra | componente (vitest) | ✅ |
| 7 | Los tests existentes de PAN-AGE-02 y PAN-AGE-03 siguen verdes | regresión | ✅ (139 de agenda y scheduling) |
| 8 | Verificación manual en staging después del deploy: «Configurar» con slot 3 muestra el mensaje dentro del diálogo | manual | pendiente (después del deploy) |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-13 | aprobado por el usuario en el chat, con los cuatro diálogos de la Agenda |
| 2 · Verificación | 2026-10-13 | aprobado. Frontend: typecheck ✔, lint ✔, prettier ✔, 1482 tests ✔ (139 de agenda y scheduling). Sin cambios de backend |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- En «Configurar» el error va en el pie fijo y no arriba: el diálogo es largo, y arriba quedaría fuera de la vista al apretar «Guardar horario» o «Guardar servicios».
- «Cancelar turno» deja de cerrarse antes de pedir: esa era la forma de esquivar el problema, y con el error dentro del diálogo ya no hace falta.
- MAN-70 se actualiza junto con las demás correcciones de la Agenda cuando se verifiquen en staging, porque el manual describe lo que hace staging.
