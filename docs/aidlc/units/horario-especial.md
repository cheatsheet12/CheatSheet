# Unidad: horario-especial

**HUs**: HU-E7-05   **Contexto dueño**: scheduling   **Rama**: fix/scheduling-horario-especial

> Origen: issue #165, encontrado en la prueba manual de la Etapa 6 en staging (12/10/2026).
> Severidad **Mayor**: un criterio de aceptación no se puede cumplir desde el panel. Es un `fix/…`
> cortado de `develop` (`9676a1f`); el PR va a `develop`.

## Qué hace

En «Recursos › Configurar › Excepciones» el panel solo permite cargar un **día sin atención**. Esta
unidad agrega el segundo tipo que la historia pide y que el sistema ya soporta: el **horario
especial**, un día con un horario distinto del habitual (por ejemplo, abrir un sábado de 10:00 a
14:00).

Comportamiento observable después del fix:

- En «Excepciones» se elige el tipo: «Sin atención» o «Horario especial».
- «Horario especial» pide, además de la fecha, «Desde» y «Hasta», y se guarda con «Guardar horario
  especial». «Sin atención» sigue igual que hoy, con «Bloquear el día».
- La tabla de excepciones muestra el horario de un horario especial («10:00–14:00»).
- Una hora de inicio posterior a la de fin se rechaza con la frase de la historia, «La hora de inicio
  debe ser anterior a la hora de fin.», y no se manda nada.

**Fuera de esta unidad:**
- La duración del slot de una apertura especial: el DER no le da columna, y el sistema hereda la del
  patrón de ese día (pendiente 14 del épico 7). No cambia.
- Que los errores del editor aparezcan detrás del modal (#74, transversal).
- La fecha ISO de la tabla (#166): el código la deja cruda a propósito («es la clave por la que se
  borra»); es decisión de diseño, no se toca.

## La historia

> **HU-E7-05 — Registrar excepciones de disponibilidad**
>
> * RN-01: Una excepción define un día específico sin atención o con horario distinto al habitual.
> * RN-02: No se permite una excepción que contradiga otra existente para el mismo recurso y fecha.
> * RN-03: Las excepciones tienen prioridad sobre la disponibilidad base.
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | Agrego una excepción de día sin atención | El agente no ofrece ese día al reservar | PAN-AGE-03 |
> | Agrego una excepción de horario especial | El agente ofrece el horario de la excepción en lugar del habitual | PAN-AGE-03 |
> | Intento agregar una excepción que contradice otra existente | «Ya existe una excepción para esa fecha en este recurso.» | PAN-AGE-03 |

## Lo que ya existe y el hueco

| Dónde | Qué |
|---|---|
| `backend/.../scheduling/domain/recurso.py:150-176` | `ExcepcionDeDisponibilidad` con `APERTURA_ESPECIAL`: exige `franja_inicio` y `franja_duracion_min` positivos, y que el inicio caiga en la fecha (en la zona de la agenda) |
| `backend/.../api/routers/agenda_forma.py:65-69` | `ExcepcionEntrada`: `franja_inicio` es un `datetime` completo (`2026-10-17T10:00:00-03:00`) |
| `frontend/.../scheduling/api/recurso.ts:191-210` | `registrarExcepcion` ya acepta `tipo`, `franja_inicio` y `franja_duracion_min` |
| `frontend/.../scheduling/api/recurso.ts:81-84` | `ETIQUETAS_DE_EXCEPCION`: «Sin atención» y «Horario especial» ya existen |
| `frontend/.../scheduling/components/EditorDeRecurso.tsx:287-311` | **El hueco**: el formulario manda siempre `tipo: "BLOQUEO"` |

Verificado en staging (12/10/2026): una apertura cargada por la API se guarda y la disponibilidad la
respeta (sábado 17/10 de 10:00 a 14:00 ofrece 10:00 … 13:15). Solo falta el formulario.

## Diseño

- **Dominio**: no aplica.
- **Aplicación**: no aplica.
- **API**: no aplica.
- **Frontend** (`EditorDeRecurso.tsx`, tarjeta «Excepciones»):
  - Un selector «Tipo de excepción» con las dos etiquetas existentes.
  - Para «Horario especial», dos campos de hora «Desde» y «Hasta», como los de las franjas del
    horario semanal. Se mandan `franja_inicio = "<fecha>T<desde>:00-03:00"` (el mismo desfase que
    usa la agenda) y `franja_duracion_min = minutos entre Desde y Hasta`.
  - Si «Desde» no es anterior a «Hasta», se muestra `MENSAJE_HORARIO_INVERTIDO` y el botón queda
    deshabilitado.
  - La tabla agrega una columna «Horario»: «10:00–14:00» para un horario especial, «—» para un día
    sin atención.
  - El cálculo de la franja va en una función pura junto al resto de `api/recurso.ts`, para
    probarla sin el formulario.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [ ] Datos con `empresa_id` → no cambia el aislamiento
- [ ] Usa salida de un LLM → no aplica
- [x] **Zona horaria**: la franja se manda con el desfase de la agenda (`-03:00`), no en UTC ni en la
      zona del navegador; si no, el backend rechazaría «El horario de la apertura no cae en la fecha
      indicada» para un horario nocturno.

## Archivos a tocar
- [x] frontend/src/features/scheduling/components/EditorDeRecurso.tsx
- [x] frontend/src/features/scheduling/components/recursosDatos.ts (`franjaDeApertura`, `horarioDeExcepcion`: funciones puras; van junto a los demás helpers de la tarjeta y no en `api/`, porque usan el desfase de `calendario.ts`)
- [x] frontend/src/features/scheduling/components/FormularioDeExcepcion.tsx (nuevo: el formulario sale del editor, que tenía 321 líneas)
- [x] frontend/src/features/scheduling/components/calendario.ts (exporta `DESFASE`)
- [x] frontend/src/features/scheduling/components/__tests__/RecursosReservables.test.tsx
- [x] docs/aidlc/units.md (mi fila) · docs/aidlc/units/horario-especial.md

## Casos de prueba

El primero se escribe **antes** del arreglo y tiene que fallar con el código actual.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Elegir «Horario especial», fecha 17/10, 10:00 a 14:00 y guardar manda `APERTURA_ESPECIAL`, `franja_inicio = 2026-10-17T10:00:00-03:00`, `franja_duracion_min = 240` (reproduce #165) | componente (vitest) | ✅ (falló antes del arreglo) |
| 2 | «Desde» posterior a «Hasta» muestra «La hora de inicio debe ser anterior a la hora de fin.» y no manda nada | componente (vitest) | ✅ |
| 3 | La tabla muestra «10:00–14:00» para un horario especial y «—» para un día sin atención | componente (vitest) | ✅ |
| 4 | La función de la franja calcula inicio con `-03:00` y la duración en minutos, también para un horario nocturno | unit (vitest) | ✅ (falló antes del arreglo) |
| 5 | «Bloquear el día» sigue mandando `BLOQUEO` sin franja (test existente) | regresión | ✅ (cambió solo la etiqueta del selector de fecha: «Fecha de la excepción») |
| 6 | Verificación manual en staging después del merge: cargar un sábado de 10:00 a 14:00 y ver esos horarios en Nuevo turno | manual | pendiente (después del merge) |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-13 | aprobado sin cambios |
| 2 · Verificación | 2026-10-13 | Frontend: Prettier ✔, lint ✔, typecheck ✔, 1433 tests ✔, cobertura 90,88 %. Backend sin cambios |
| 3 · PR | 2026-10-13 | PR #204 a `develop`. CI bloqueado por la facturación de Actions de la organización |

## Decisiones tomadas durante la unidad
- El selector de fecha pasa de «Día sin atención» a «Fecha de la excepción», porque ahora sirve para los dos tipos; las horas se rotulan «Hora de apertura» y «Hora de cierre» para no repetir «Desde» / «Hasta» de las franjas en el mismo diálogo. El capítulo MAN-70 se actualiza en su PR (#183).
- Solo frontend: el dominio, la API y el cliente ya soportan la apertura especial; falta el formulario.
- La fecha ISO de la tabla (#166) no se cambia: es deliberada según el código.
