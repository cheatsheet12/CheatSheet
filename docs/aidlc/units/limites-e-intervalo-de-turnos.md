# Unidad: limites-e-intervalo-de-turnos

**HUs**: HU-E7-04, HU-E7-06 (modificadas por ADR-0009) **Contexto dueño**: scheduling **Rama**: feature/scheduling-limites-e-intervalo-de-turnos

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D96 (`docs/aidlc/epicas/07-agenda-y-recursos/decisiones.md:230-260`). La rama sale de
> `feature/scheduling-turnos-no-en-el-pasado` (PR #46, sobre #45), de la que depende según el mapa: usa
> la carga y la corrección a posteriori de D95, que «no respetan el intervalo». Su PR apunta a esa rama y
> pasa a `develop` cuando la cadena llegue. Tamaño: M.

## Qué hace

Hoy la duración del slot de un recurso se usa como si fuera la duración del turno: la grilla corta la
franja en pasos del slot y solo marca «ocupado» un horario cuyo inicio coincide exactamente con el de un
turno. Un servicio de 45 minutos sobre un slot de 30 se ofrece en horarios en los que no entra, y no
existe un margen entre turnos. Esta unidad separa los tres conceptos de D96. El turno dura lo que dura el
servicio (5 a 480 minutos, sin carga manual). El slot (5 a 480 minutos, sin superar la franja) es solo
el paso de la grilla de inicios. Cada recurso tiene un intervalo entre turnos opcional (0 a 480 minutos,
0 por defecto), que la grilla, el panel, el agente y **la base** respetan. La carga y la corrección a
posteriori siguen sin respetarlo.

**Lo que las historias piden, textual** (`docs/aidlc/inputs/historias-de-usuario.md:1537-1665`):
- HU-E7-04 RN-01: «Cada franja del patrón define además la duración del slot: el paso de la grilla de
  horarios de inicio que se ofrecen. La duración del slot no es la duración del turno, que es la
  duracion_estandar_min del servicio (HU-E7-06 RN-08).»
- HU-E7-04 RN-05: «La duración del slot la elige la empresa, entre 5 y 480 minutos, y no puede superar la
  extensión de la franja.»
- HU-E7-04 RN-06: «Cada recurso tiene un intervalo entre turnos opcional, en minutos (0 por defecto,
  máximo 480), que se agrega después de cada turno.»
- HU-E7-04 RN-07: «Un turno nuevo o reprogramado debe empezar a partir del fin del turno anterior más el
  intervalo, y su fin más el intervalo no debe pisar el inicio del siguiente. El turno debe terminar
  dentro de la franja; el intervalo posterior al último turno de la franja puede exceder hora_fin. El
  agente solo ofrece inicios que cumplan lo anterior.»
- HU-E7-04 RN-08: «Cambiar el intervalo o la duración del slot aplica a reservas y reprogramaciones
  nuevas; no mueve turnos existentes.»
- HU-E7-06 RN-01: «… El solapamiento considera el intervalo entre turnos del recurso (HU-E7-04 RN-07),
  salvo en la carga a posteriori (RN-07).» RN-07: «… no exige que la franja esté dentro de la
  disponibilidad base ni respeta el intervalo entre turnos.»
- HU-E7-06 RN-08: «La duración del turno es la duración estándar del servicio elegido
  (duracion_estandar_min, entre 5 y 480 minutos, HU-E4-02 RN-05) y no se ingresa a mano.»
- HU-E7-02 RN-08 (la toca el mismo cambio): «La reprogramación conserva la duración, que debe seguir entre
  5 y 480 minutos, y considera el intervalo entre turnos del recurso en el chequeo de solapamiento
  (HU-E7-04 RN-07), salvo en la corrección a posteriori.»
- Criterios nuevos de HU-E7-04: «Ingreso una duración de slot de 4 o de 481 minutos → El sistema muestra
  “La duración del slot debe estar entre 5 y 480 minutos.”»; «Configuro un intervalo de 10 minutos y hay
  un turno de 09:00 a 09:30 → El siguiente turno puede empezar a las 09:40 o más tarde»; «No configuro
  intervalo → El intervalo es 0 y los turnos pueden ser contiguos»; «Ingreso un intervalo negativo → El
  sistema lo rechaza y no guarda».
- Criterio nuevo de HU-E7-06: «Elijo un servicio agendable de 45 minutos → El turno se crea con duración
  de 45 minutos y los inicios ofrecidos siguen el paso del slot del recurso».

**Lo que ya existe** (en esta rama):
- La duración por defecto ya sale del servicio (`scheduling/application/turnos.py:246`), pero **se puede
  pisar a mano**: `duracion_min` en `ReservarTurno.ejecutar` (`turnos.py:239`), en
  `ReprogramarTurno.ejecutar` (`turnos.py:374,382`) y en las entradas de la API
  (`api/routers/agenda.py:107,115`). El frontend no la manda (`features/scheduling/api/turno.ts:49-59`).
- El slot va de 5 a 1440 (`scheduling/domain/recurso.py:56-57`), con un mensaje que dice «La duración
  **del turno** debe estar entre…» (`recurso.py:116-120`), y nada impide un slot mayor que la franja. En
  la base solo hay `duracion_slot_min > 0` (`migrations/versions/0020_agenda.py:186`). El panel lo rotula
  «Minutos por turno» (`features/scheduling/components/RecursosReservables.tsx:454-456`).
- La grilla corta en pasos del slot y exige que **el slot** entre antes del cierre
  (`recurso.py:322-336`, `while actual + paso <= cierre`), sin mirar la duración del servicio.
- «Ocupado» es coincidencia exacta de inicios: `GET /turnos/disponibilidad`
  (`api/routers/agenda.py:528-540`) y el agente (`conversational/infrastructure/acl.py:94-97`). Las dos
  copias de la lógica están duplicadas.
- El tope del turno es 24 h en el dominio (`scheduling/domain/turno.py:39`, `Franja` en `:124`) y en la
  base (`0020_agenda.py:267`, `ck_turno_duracion`). `duracion-de-servicios` dejó ese tope a esta unidad
  explícitamente (`docs/aidlc/units/duracion-de-servicios.md:17-18`, en la otra cadena).
- No hay columna de intervalo en `recurso_reservable` (`scheduling/infrastructure/models.py:33-43`) ni
  en `turno` (`models.py:110-136`).
- La exclusión `excl_turno_recurso_franja` compara `franja_de_turno(franja_inicio, franja_duracion_min)`
  (`0020_agenda.py:99-120`), ampliada a COMPLETADO por `0024_turno_completado_ocupa_la_franja.py`.

**El hueco:** rango del slot y su tope por franja, rango 5–480 del turno, quitar la duración manual,
intervalo por recurso (dominio, base, API, panel), grilla por duración del servicio con ocupación por
solapamiento más intervalo, y la garantía de la base contra el doble booking **con** intervalo.

**Fuera de esta unidad:**
- El diálogo del agente cuando el horario elegido ya no está libre (épico 8, ya anotado por
  `turnos-no-en-el-pasado`). Acá el agente solo **ofrece** bien.
- El rango 5–480 del **servicio**: es de `duracion-de-servicios` (D86, migración 0025 en la otra cadena).
- Una duración de slot propia para la apertura especial: el DER no tiene la columna y la apertura sigue
  heredando la del patrón (`recurso.py:308-319`).
- Partir `turnos.py`, `agenda.py` o `RecursosReservables.tsx`, que ya superan las 400 líneas (ver P4).

## Las preguntas que D96 dejó para este Gate

### 1. ¿Cómo sigue garantizando la base el doble booking con intervalo? — **lleva migración**

D96 ofrece dos caminos: guardar en el turno el intervalo aplicado al reservar o pasar el chequeo al
dominio. El segundo pierde frente a dos reservas simultáneas, y D28 dice que esa garantía es de la base.
Se descarta. Queda decidir cómo se guarda el intervalo, porque la excepción a posteriori «no respeta el
intervalo» y una sola restricción no la puede expresar.

**Recomendación (A): columna `turno.intervalo_posterior_min` y dos restricciones.**
- `intervalo_posterior_min integer NULL`, entre 0 y 480. Al reservar o reprogramar en condiciones
  normales se copia el intervalo **actual** del recurso (eso cumple RN-08: cambiarlo no mueve turnos
  existentes). La carga y la corrección a posteriori lo dejan en `NULL`, que significa «sin intervalo».
- `excl_turno_recurso_franja` (la de 0024) **no cambia**: la franja real nunca se pisa, tampoco en la
  excepción.
- Una restricción nueva, `excl_turno_recurso_intervalo`, sobre
  `franja_de_turno(franja_inicio, franja_duracion_min + intervalo_posterior_min)`, con
  `WHERE estado IN ('RESERVADO','CONFIRMADO','COMPLETADO') AND intervalo_posterior_min IS NOT NULL`.
  Entre dos turnos normales, «A termina más su intervalo antes de que empiece B» es exactamente RN-07. Los
  turnos a posteriori quedan afuera: ni respetan el intervalo ajeno ni imponen el propio.
- Backfill: los turnos existentes quedan con 0. Con 0, la restricción nueva equivale a la vieja, así que
  crearla no puede fallar por datos existentes.

**Alternativa (B): una sola restricción** sobre `franja + COALESCE(intervalo, 0)`, con la carga a
posteriori guardando 0. Es más simple, pero el Administrador no podría registrar una atención pasada
dentro del intervalo posterior de un turno completado (09:30 después de un 09:00–09:30 con intervalo 10):
el rechazo contradiría HU-E7-06 RN-07. **No la recomiendo.**

**Lo que se paga con (A):** dos índices GiST sobre `turno` y un `NULL` con significado. D95 dijo «la
marca va en la bitácora y no hay columna nueva». Eso sigue valiendo para la **marca**: la bitácora
conserva sus acciones propias. La columna la pide D96 por otra razón, y el `NULL` solo dice qué intervalo
se aplicó.

### 2. ¿Dónde vive el rango 5–480 de la duración del turno?

Si se ajusta `Franja` (hoy 1–1440) y `ck_turno_duracion`, un turno viejo de, por ejemplo, 600 minutos
(posible: la duración manual existía) haría fallar la lectura de la agenda (`repositories.py:292`).
**Recomendación:** dejar `Franja` y `ck_turno_duracion` como tope estructural, y validar 5–480 en el
dominio (`validar_duracion_de_turno` en `turno.py`), llamado al **crear** (normal y a posteriori) y al
**reprogramar** (normal y corrección). Mensaje: «La duración del turno debe estar entre 5 y 480
minutos.». Con el servicio ya acotado por D86, el chequeo se dispara solo en reprogramaciones de turnos
viejos fuera de rango, que es justo lo que HU-E7-02 RN-08 pide rechazar. Alternativa: endurecer `Franja`
y la base con una migración que aborte listando los turnos fuera de rango. Bloquearía el despliegue por
historia que ya ocurrió, y no aporta nada sobre turnos nuevos.

### 3. Textos que las historias no escriben

Solo el del slot es literal. **Recomendación** (mismo estilo):
- Slot fuera de rango: «La duración del slot debe estar entre 5 y 480 minutos.» (literal, HU-E7-04).
- Slot mayor que la franja: «La duración del slot no puede superar la extensión de la franja.»
- Intervalo negativo o mayor que 480: «El intervalo entre turnos debe estar entre 0 y 480 minutos.»
- Turno fuera de rango: el de la pregunta 2.
- Choque por intervalo: el mismo «El horario seleccionado no está disponible.» de siempre. Para quien
  reserva, ocupado por un turno y ocupado por su margen son lo mismo, y el repositorio traduce las dos
  restricciones a `FranjaOcupada`.

### 4. Archivos que ya superan las 400 líneas

`application/turnos.py` (515), `api/routers/agenda.py` (674) y `RecursosReservables.tsx` (626) ya
superan el límite de CLAUDE.md §5. No encontré un chequeo automático en `pyproject.toml` ni en
`.claude/hooks/`. **Recomendación:** no partirlos en esta unidad (CLAUDE.md §8: no ampliar el alcance).
La lógica nueva va a archivos nuevos (`domain/grilla.py`, `application/disponibilidad.py`) y los
existentes crecen lo mínimo (estimado: `turnos.py` unas 10 líneas, `agenda.py` unas 15 netas porque la
grilla sale del router, `RecursosReservables.tsx` unas 20). El hallazgo se anota en `docs/aidlc/TODO.md`.
Alternativa: extraer `Avisador` (`turnos.py:98-167`) a `application/avisador.py` en un commit aparte de
esta misma rama. Es mecánico y deja `turnos.py` en unas 455 líneas, todavía arriba del límite.

## Diseño

### Dominio — `contexts/scheduling/domain/`
- `recurso.py`:
  - `DURACION_SLOT_MAXIMA_MIN = 480`; `MENSAJE_DURACION_SLOT` (literal) y `MENSAJE_SLOT_MAYOR_QUE_FRANJA`.
    `PatronDeDisponibilidad.__post_init__` valida 5–480 y que el slot no supere `hora_fin − hora_inicio`.
  - `RecursoReservable.intervalo_entre_turnos_min: int = 0`, validado 0–480 en `__post_init__` y en
    `definir_intervalo(minutos)`. `INTERVALO_MAXIMO_MIN = 480`, `MENSAJE_INTERVALO`.
  - `horarios_del_dia(fecha, duracion_min)`: los inicios siguen el paso del slot, y el último es el último
    **cuyo turno** (no el slot) termina dentro de la franja (RN-07: el intervalo puede pasarse de
    `hora_fin`). `_slots` recibe el paso y la duración por separado. La apertura especial sin patrón
    sigue ofreciendo su inicio, si el turno entra.
- `turno.py`:
  - `Turno.intervalo_posterior_min: int | None = 0`. `registrar_a_posteriori` lo deja en `None`.
    `reprogramar(franja, intervalo_posterior_min)` lo actualiza (la corrección pasa `None`).
  - `DURACION_TURNO_MINIMA_MIN = 5`, `DURACION_TURNO_MAXIMA_MIN = 480`, `validar_duracion_de_turno` (P2).
  - `Turno.bloquea(inicio, duracion_min, intervalo_min) -> bool`: el mismo criterio que las dos
    restricciones de la base. Siempre choca si se pisa la franja real. Si los dos llevan intervalo, también
    choca si se pisan los rangos extendidos con `[)`.
- `grilla.py` (**nuevo**, ~70 líneas): `horarios_ofrecidos(recurso, fecha, duracion_min, ocupados,
  ahora) -> tuple[HorarioOfrecido, ...]` con `inicio` y `ocupado`. Toma los inicios de
  `horarios_del_dia`, descarta los anteriores a `ahora` (D95) y marca ocupado cuando algún turno lo
  `bloquea` con el intervalo actual del recurso. Puro, sin reloj propio.

### Aplicación — `contexts/scheduling/application/`
- `disponibilidad.py` (**nuevo**): `VerHorariosDisponibles.ejecutar(recurso_id, servicio_id, fecha,
  ahora)`. Resuelve el recurso y el servicio agendable (`ServicioNoAdmitido` si no se presta ahí, como
  `ReservarTurno._resolver`), lee `ocupados_en` y llama a `grilla.horarios_ofrecidos` con
  `duracion_estandar_min`. Una sola implementación para el panel y para el agente.
- `turnos.py`:
  - `ReservarTurno.ejecutar` **pierde** `duracion_min`: la duración es siempre la del servicio. Valida el
    rango y pasa `recurso.intervalo_entre_turnos_min` al `Turno` (o `None` en la carga a posteriori).
  - `ReprogramarTurno.ejecutar` **pierde** `duracion_min` (conserva la del turno), valida el rango y pasa
    el intervalo actual del recurso (o `None` en la corrección).
- `recursos.py`: `ConfigurarDisponibilidad.ejecutar(..., intervalo_entre_turnos_min: int | None = None)`.
  `None` conserva el actual. Misma acción de bitácora, `configurar_disponibilidad`. `RegistrarRecurso`
  acepta el intervalo opcional (0 por defecto).

### Puertos y adaptadores
- `infrastructure/models.py`: `RecursoReservableORM.intervalo_entre_turnos_min` y
  `TurnoORM.intervalo_posterior_min`.
- `infrastructure/repositories.py`: mapear las dos columnas en los dos sentidos. `_flush_o_ocupado`
  traduce **las dos** restricciones a `FranjaOcupada` (`RESTRICCION_INTERVALO`). `ocupados_en` no cambia.
- `conversational/infrastructure/acl.py`: `horarios_ofrecibles` usa `VerHorariosDisponibles` con el
  servicio que ya elige (`sorted(recurso.servicios)[0]`) y deja de calcular la grilla por su cuenta.

### Otros contextos
`conversational → scheduling.application`, como hoy (R3). `master_data` se sigue leyendo por el puerto
`PortCatalogoDeServicios` existente. No hay aristas nuevas en el Context Map.

### API — `api/routers/agenda.py`
- `TurnoEntrada` y `ReprogramacionEntrada`: se quita `duracion_min`. Pydantic ignora el campo si un
  cliente viejo lo manda, así que la duración nunca se toma de la entrada.
- `GET /turnos/disponibilidad?recurso_id&fecha&servicio_id`: `servicio_id` pasa a ser **obligatorio** y
  el handler delega en `VerHorariosDisponibles`.
- `RecursoEntrada` y `DisponibilidadEntrada`: `intervalo_entre_turnos_min: int | None = None`.
  `RecursoSalida`: `intervalo_entre_turnos_min: int`.

### Frontend — `features/scheduling`
- `api/recurso.ts`: `Recurso.intervalo_entre_turnos_min` y el intervalo en `configurarDisponibilidad`.
- `RecursosReservables.tsx`: el campo del patrón se rotula «Duración del slot (min)», con la ayuda «Paso
  de la grilla de horarios. La duración del turno es la del servicio». En la tarjeta «Horario semanal» se
  agrega «Intervalo entre turnos (min)», con 0 por defecto. Los errores llegan del backend al `Alert`
  existente.
- `api/turno.ts`: `verDisponibilidad(recursoId, fecha, servicioId)`.
- `NuevoTurno.tsx`: busca los horarios cuando hay recurso, **servicio** y fecha (hoy no espera al
  servicio, `NuevoTurno.tsx:91-100,174,212`). Cambiar de servicio vuelve a buscar. Sin servicio, la grilla
  pide «Elegí el servicio para ver los horarios».
- Los `min` y rangos de los campos son cortesía: el rechazo real lo hace el backend.

## Infraestructura

### Migraciones
**Número: `0028_intervalo_entre_turnos.py`, con `down_revision = "0024"` en esta rama.** Esta rama
termina en 0024, pero la otra cadena (`C:\Dev\CheatSheet`, `feature/reporting-indicadores-de-cobranza`)
ya usa **0025** (`servicio_duracion_en_rango`), **0026** (`fecha_medio_y_operacion_de_pago`) y **0027**
(`reembolsos`), todas sobre 0024. Usar 0025 chocaría por número. Usar 0028 evita el choque de nombre,
pero **no** el de cadena: cuando las dos ramas lleguen a `develop`, Alembic va a ver dos cabezas (0027 y
0028, las dos hijas de 0024) y `alembic upgrade head` va a fallar. **Al rebasar sobre `develop` con la
otra cadena ya integrada, hay que cambiar `down_revision` a la cabeza vigente** (hoy "0027"). Es un
cambio de una línea, que se anota en el PR. Si otra unidad en vuelo (por ejemplo
`tipos-de-comprobante-por-receptor` o `nuevo-cobro-desde-su-panel`, que salen de 0025) toma 0028 antes,
se renumera al rebasar.

Contenido:
- `recurso_reservable.intervalo_entre_turnos_min integer NOT NULL DEFAULT 0`,
  `CHECK BETWEEN 0 AND 480`.
- `turno.intervalo_posterior_min integer NULL DEFAULT 0`,
  `CHECK (intervalo_posterior_min IS NULL OR intervalo_posterior_min BETWEEN 0 AND 480)`. Los existentes
  quedan en 0 (P1).
- `patron_de_disponibilidad`: `ck_patron_slot` pasa a `duracion_slot_min BETWEEN 5 AND 480 AND
  duracion_slot_min * interval '1 minute' <= hora_fin - hora_inicio`. **Antes** busca los patrones que
  la violan y aborta listando los ids, con el mismo criterio que 0024 y 0025: no hay recorte automático.
- `excl_turno_recurso_intervalo` (P1). No necesita chequeo previo: con todo en 0 equivale a la de 0024.
- Reversible: `downgrade` borra la restricción y las dos columnas, y restaura `duracion_slot_min > 0`.

### Trabajo asíncrono · Configuración · Integraciones externas
**No aplica.** Nada es diferido, no hay variables nuevas y no se agrega ninguna integración.

## Riesgos que obligan a tests
- [ ] Toca dinero: no aplica.
- [ ] Comprobantes fiscales: no aplica.
- [ ] Webhook: no aplica.
- [x] Datos por empresa: las columnas nuevas viven en tablas con RLS. La restricción nueva compara por
  `recurso_id`, que ya es de una sola empresa. Test de integración con dos empresas.
- [ ] Salida de un LLM: no aplica (el agente solo recibe horarios calculados).
- [ ] Datos personales a un LLM: no aplica.
- [x] **Doble booking** (riesgo dominante del contexto): la restricción nueva se prueba contra
  PostgreSQL, incluida la frontera exacta (09:40 entra, 09:39 no).

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/scheduling/domain/recurso.py`
- [ ] `backend/src/cheatsheet/contexts/scheduling/domain/turno.py`
- [ ] `backend/src/cheatsheet/contexts/scheduling/domain/grilla.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/scheduling/application/disponibilidad.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/scheduling/application/turnos.py`
- [ ] `backend/src/cheatsheet/contexts/scheduling/application/recursos.py`
- [ ] `backend/src/cheatsheet/contexts/scheduling/infrastructure/models.py`
- [ ] `backend/src/cheatsheet/contexts/scheduling/infrastructure/repositories.py`
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/acl.py`
- [ ] `backend/src/cheatsheet/api/routers/agenda.py`
- [ ] `backend/migrations/versions/0028_intervalo_entre_turnos.py`
- [ ] `backend/tests/contexts/scheduling/domain/test_recurso.py`, `test_turno.py`, `test_grilla.py` (nuevo)
- [ ] `backend/tests/contexts/scheduling/application/test_agenda.py` (y `dobles.py` si hace falta)
- [ ] `backend/tests/contexts/conversational/infrastructure/test_acl_agenda.py`
- [ ] `backend/tests/integracion/test_agenda_postgres.py`, `test_api_agenda.py`

### Frontend
- [ ] `frontend/src/features/scheduling/api/recurso.ts`, `api/turno.ts`
- [ ] `frontend/src/features/scheduling/components/RecursosReservables.tsx`, `NuevoTurno.tsx`
- [ ] `frontend/src/features/scheduling/api/__tests__/recurso.test.ts`, `turno.test.ts`
- [ ] `frontend/src/features/scheduling/components/__tests__/RecursosReservables.test.tsx`, `pantallas.test.tsx`

### Docs
- [ ] `docs/aidlc/units.md` (estado de la fila)
- [ ] `docs/aidlc/TODO.md`: el hallazgo de los archivos de más de 400 líneas (P4) y las verificaciones
  manuales de §22. **Ojo:** en esta rama `TODO.md` llega hasta §19, porque §20–§22 están en la otra
  cadena (`C:\Dev\CheatSheet\docs\aidlc\TODO.md:592-640`). Las filas se agregan a §22 al juntar las
  cadenas. Mientras tanto quedan en este plan, para no crear una §22 paralela que choque al mergear.

## Casos de prueba

Modo: **test primero**. Cada caso se escribe y se ve fallar (RED) antes del código que lo hace pasar.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Slot de 4 y de 481 → «La duración del slot debe estar entre 5 y 480 minutos.»; 5 y 480 se aceptan | unit | pendiente |
| 2 | Slot de 90 en una franja de 60 → rechazado con el mensaje de P3 | unit | pendiente |
| 3 | Intervalo −1 y 481 → rechazado; sin intervalo → 0 | unit | pendiente |
| 4 | `horarios_del_dia` con slot 30 y servicio 45 en 09:00–11:00: inicios 09:00, 09:30, 10:00 (10:30 no, el turno no entra) | unit | pendiente |
| 5 | Grilla con intervalo 10 y turno 09:00–09:30, slot 10, servicio 30: 09:30 ocupado, 09:40 libre (criterio de HU-E7-04) | unit | pendiente |
| 6 | Grilla: el turno nuevo más su intervalo no pisa el siguiente; un último turno cuyo intervalo pasa `hora_fin` se ofrece | unit | pendiente |
| 7 | Grilla: un turno a posteriori (`intervalo None`) solo bloquea su franja real | unit | pendiente |
| 8 | `ReservarTurno` ignora toda duración externa: el turno dura `duracion_estandar_min` (45) y guarda el intervalo actual del recurso | unit | pendiente |
| 9 | Carga a posteriori → `intervalo_posterior_min is None`; corrección a posteriori → `None` | unit | pendiente |
| 10 | Reprogramar un turno de 600 min → «La duración del turno debe estar entre 5 y 480 minutos.»; reprogramar normal copia el intervalo **actual** del recurso | unit | pendiente |
| 11 | `VerHorariosDisponibles` con servicio no asociado → `ServicioNoAdmitido` | unit | pendiente |
| 12 | `AgendaViaScheduling.horarios_ofrecibles` respeta duración del servicio e intervalo | unit | pendiente |
| 13 | Base: intervalo 10, turno 09:00–09:30 → 09:39 rechazado (`FranjaOcupada`), 09:40 aceptado; con intervalo 0, contiguo aceptado | integración (PostgreSQL) | pendiente; requiere PostgreSQL |
| 14 | Base: carga a posteriori a las 09:30 tras un 09:00–09:30 COMPLETADO con intervalo 10 → aceptada; solapando la franja real → rechazada | integración (PostgreSQL) | pendiente; requiere PostgreSQL |
| 15 | Base: cambiar el intervalo del recurso no altera `intervalo_posterior_min` de los turnos existentes (RN-08) | integración (PostgreSQL) | pendiente; requiere PostgreSQL |
| 16 | Migración: aborta listando patrones con slot fuera de rango o mayor que la franja; `downgrade` limpia | integración (PostgreSQL) | pendiente; requiere PostgreSQL |
| 17 | API: `PUT .../disponibilidad` con slot 481 o intervalo −1 → 422 con el texto; `GET /disponibilidad` sin `servicio_id` → 422 | integración (API) | pendiente; requiere PostgreSQL |
| 18 | API: `POST /turnos` con `duracion_min` en el cuerpo → el turno dura lo del servicio | integración (API) | pendiente; requiere PostgreSQL |
| 19 | Aislamiento: el intervalo de un recurso de la empresa A no afecta a la empresa B | integración (PostgreSQL) | pendiente; requiere PostgreSQL |
| 20 | Frontend: `RecursosReservables` manda el intervalo y muestra el error del backend; rótulo «Duración del slot» | unit (frontend) | pendiente |
| 21 | Frontend: `NuevoTurno` no busca sin servicio y vuelve a buscar al cambiarlo, con `servicio_id` en la consulta | unit (frontend) | pendiente |

## Verificaciones que no se pueden hacer acá

Van a `docs/aidlc/TODO.md` §22 (no hay ítems para §20 ni §21):
- 22.x: en el navegador (`run-local`), configurar un intervalo de 10 en un recurso, reservar 09:00 y ver
  que la grilla de PAN-AGE-02 marca 09:30 como no disponible y ofrece 09:40.
- 22.y: el formulario de recursos con el campo de intervalo y el rótulo nuevo del slot se ve bien en
  escritorio y en celular.
- 22.z: en Nuevo turno, cambiar de servicio recalcula la grilla sin dejar elegido un horario viejo.
- Los casos 13 a 19 se saltean en local sin Docker y se observan en la CI.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-01 | Aprobado por Luciano: P1 a P4 según la recomendación |
| 2 · Verificación | 2026-10-01 | Aprobado por Luciano con la evidencia de «Verificación (Gate 2)» |
| 3 · PR | 2026-10-01 | [#53](https://github.com/cheatsheet12/CheatSheet/pull/53), draft, apilado sobre #46 |

## Decisiones tomadas durante la unidad
- **P1**: columna `turno.intervalo_posterior_min` (NULL en la carga y la corrección a posteriori) y
  dos restricciones de exclusión: `excl_turno_recurso_franja` sin cambios y
  `excl_turno_recurso_intervalo` nueva. Migración `0028` (número reservado; `down_revision` se
  re-apunta al rebasar y se verifica `alembic heads` antes del PR).
- **P2**: el rango 5–480 del turno se valida en el dominio al crear y al reprogramar; `Franja` y
  `ck_turno_duracion` quedan en 1440 como tope estructural.
- **P3**: los textos propuestos en la pregunta 3.
- **P4**: no se parten `turnos.py`, `agenda.py` ni `RecursosReservables.tsx`; la lógica nueva va en
  archivos nuevos y el hallazgo se anota.

## Verificación (Gate 2) — evidencia, 2026-10-01

Commits: `b7020f4` (backend y migración `0028`), `0307642` (frontend), `4292f87` (docs).

| Comando | Resultado |
|---|---|
| `ruff format --check .` | 552 files already formatted |
| `ruff check .` | All checks passed |
| `mypy . --no-incremental` | Success: no issues found in 547 source files |
| `guard_architecture.py --scan .` | 647 files checked, architecture boundaries intact |
| `pytest --cov=backend/src` | 1386 passed, 341 skipped (PostgreSQL/Redis, sin Docker); cobertura local 74,04 % (el 80 % lo mide la CI) |
| `npm run lint` · `npm run typecheck` | sin errores |
| `vitest run --coverage` | 70 archivos, 817 tests en verde; 84,21 % de líneas |
| `prettier --check --end-of-line auto .` | All matched files use Prettier code style |
| `next build` | compila |

**Verificador independiente** (Sonnet, solo lectura, mutantes en el scratchpad): sin defectos altos ni
medios. Mató 17 mutantes y sobrevivió uno equivalente. Confirmó en el código:
- `Turno.bloquea` reproduce exactamente las dos restricciones de la base.
- El repositorio traduce las dos violaciones a `FranjaOcupada`, sin 500.
- La columna `intervalo_posterior_min` no tiene `DEFAULT`, así que el `NULL` de la carga a posteriori se
  conserva.
- `duracion_min` ya no entra por ningún camino: API, aplicación, agente ni frontend.
- La migración aborta antes de cualquier cambio si hay patrones fuera de rango, y su `downgrade` revierte
  todo en orden.

Los mensajes de los tres textos de P3 coinciden literalmente.

Notas que no se corrigen (bajas):
- **Turnos viejos con intervalo 0:** cambiar el intervalo de un recurso de 0 a 10 no afecta a los turnos
  existentes, que se reservaron con 0. Un turno nuevo puede quedar pegado a uno viejo. Es lo que pide
  RN-08 («no mueve turnos existentes»), no un defecto.
- **Turno de la noche anterior:** la grilla no lo ve si su intervalo pasa la medianoche; la base sí lo
  frena. Queda anotado en `TODO.md` §20.
- **Orden de los mensajes:** al reprogramar un turno cancelado de más de 480 minutos, sale el mensaje de
  duración antes que el de estado. Es cosmético.

**Lo que no se verificó:** todo lo que necesita PostgreSQL (casos 13 a 19): el comportamiento real de
las restricciones, la ida y vuelta de la `0028` y la traducción a 409. La migración tiene
`down_revision = "0024"`: al juntar las cadenas hay que re-apuntarlo y comprobar que `alembic heads`
dé una sola cabeza.

