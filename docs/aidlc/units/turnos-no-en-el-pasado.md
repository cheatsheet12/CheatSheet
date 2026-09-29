# Unidad: turnos-no-en-el-pasado

**HUs**: HU-E7-06, HU-E7-02, HU-E8-01 **Contexto dueño**: scheduling **Rama**: feature/scheduling-turnos-no-en-el-pasado

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D95 (`docs/aidlc/epicas/07-agenda-y-recursos/decisiones.md`). La rama sale de
> `feature/infra-ajustes-de-la-revision` (PR #45), que trae las historias modificadas; su PR apunta a
> esa rama y pasa a `develop` cuando el #45 se mergea.

## Qué hace

Hoy se puede reservar y reprogramar un turno en un instante que ya pasó: `ReservarTurno` y
`ReprogramarTurno` reciben `ahora` pero solo lo usan para `created_at` y la bitácora, y la grilla de
disponibilidad ofrece horarios de hoy que ya transcurrieron. Esta unidad cierra ese hueco para el
panel y para el agente, y agrega la única excepción que las historias admiten: el **Administrador**
puede registrar una atención ya realizada (carga a posteriori) o mover un turno a una franja ya
terminada (corrección a posteriori), sin avisarle nada al cliente y dejando la marca en la bitácora.

**Fuera de esta unidad** (van en `limites-e-intervalo-de-turnos`, D96): el rango de 5 a 480 minutos,
la duración tomada del servicio, el slot como paso de la grilla y el intervalo entre turnos.

## Las preguntas que D95 dejó para este Gate

### 1. Dos criterios de tiempo, y el turno en curso

| Caso | Regla | Comparación |
|---|---|---|
| Reserva o reprogramación normal (cualquier rol, panel o agente) | El inicio no puede haber pasado | `inicio >= ahora` (un inicio exactamente igual a `ahora` es válido) |
| Carga o corrección a posteriori (solo Administrador) | La franja completa tiene que haber terminado | `fin <= ahora`, el mismo "ya transcurrió" de D35 |

Un turno **en curso** (`inicio < ahora < fin`) no admite ninguna de las dos: ni es futuro ni terminó.
Se compara **el instante**, nunca `.date()`: la historia dice "contra el instante actual, no solo el
día". Los instantes son *aware*, así que la comparación no depende de `ZONA_DE_LA_AGENDA`.

### 2. ¿La carga a posteriori nace COMPLETADO o se crea y se transiciona?

**Nace COMPLETADO**, con un constructor de dominio `Turno.registrar_a_posteriori(..., ahora)` que
valida `franja.fin <= ahora` y deja el estado final en una sola operación.

Crear RESERVADO y transicionar con `marcar_completado` reusaría la máquina de estados, pero obliga a
dos escrituras, y la primera (un RESERVADO en una franja pasada) es justamente el estado que esta
unidad prohíbe. El constructor dedicado expresa la regla del negocio tal como la dice la historia: una
atención que ya ocurrió se registra como ocurrida.

### 3. ¿Cómo pide el Administrador la excepción?

**Con un indicador explícito `a_posteriori`** en la reserva y en la reprogramación. No se infiere del
inicio pasado: si se infiriera, un Administrador que se equivoca de fecha crearía sin querer un turno
COMPLETADO, sin aviso al cliente. Un inicio pasado **sin** el indicador se rechaza igual que para
cualquier rol. El indicador en manos de un Operador (o del agente) se rechaza con 422 y un motivo
claro, siguiendo la convención de `MOTIVO_SIN_PERMISO` (todas las reglas de negocio de la agenda
responden 422, no 403).

### 4. El solapamiento contra turnos COMPLETADO — **lleva migración**

La exclusión de la base (`0020_agenda.py`, `excl_turno_recurso_franja`) solo cubre los estados
`RESERVADO` y `CONFIRMADO`. Un turno COMPLETADO queda fuera, y eso tiene dos consecuencias:

- la carga a posteriori, que nace COMPLETADO, **no estaría protegida** contra el solapamiento que la
  historia exige rechazar;
- **ya hoy** se puede crear un turno encima de uno completado (hueco preexistente, conectado).

Un chequeo en Python no alcanza: pierde frente a dos pedidos concurrentes, y D95 dice que la exclusión
de la base sigue valiendo para la excepción.

**Resolución:** una migración nueva amplía la condición a `('RESERVADO', 'CONFIRMADO', 'COMPLETADO')`,
y `ocupados_en` pasa a contar también los COMPLETADO. **NO_SHOW queda afuera a propósito**: si el
cliente no vino, el recurso quedó libre de hecho, y el Administrador tiene que poder registrar a
posteriori la atención de otra persona en esa franja.

**Riesgo de la migración:** si en la base ya hay turnos COMPLETADO que se solapan (posible, porque el
bug permitía reservar en el pasado), crear la restricción falla. La migración primero **busca esos
conflictos y aborta con un mensaje que los lista**, en lugar de fallar con un error críptico de
PostgreSQL. Es reversible: el `downgrade` restaura la condición original.

### 5. Qué validaciones se omiten en la excepción

Se omite **solo la disponibilidad base** del recurso (`esta_disponible_en`), como dice la historia. Se
mantienen: servicio agendable y admitido por el recurso, recurso activo, y el solapamiento (ahora
garantizado por la base). Mantener "recurso activo" es la opción conservadora; si hiciera falta cargar
atenciones de un recurso ya desactivado, se decide aparte.

### 6. La corrección a posteriori conserva el estado

`turno.reprogramar` ya exige un turno abierto (RESERVADO o CONFIRMADO) y conserva su estado
(HU-E7-02 RN-02). Un turno movido al pasado **sigue** RESERVADO o CONFIRMADO; después se marca la
asistencia por el camino normal de HU-E7-03. No pasa a COMPLETADO solo.

### 7. La marca en la bitácora

Acciones propias, no un campo de detalle: `cargar_turno_a_posteriori` y `corregir_turno_a_posteriori`.
El filtro de la bitácora del épico 10 trabaja por acción, así que es lo que la hace visible. Las
acciones normales (`reservar_turno`, `reprogramar_turno`) no cambian.

### 8. El agente de WhatsApp

- `horarios_ofrecibles` pasa a filtrar los horarios que ya pasaron, con el reloj inyectado.
- **Bug encontrado:** `AgendaViaScheduling` usa `datetime.now()` real en tres lugares (`reservar`,
  `turnos_de`, `cancelar`). Se le inyecta el `Reloj` de la unidad de trabajo; sin eso, el re-chequeo
  "al confirmar" no es testeable.
- El re-chequeo al confirmar queda garantizado porque el agente reserva por el mismo `ReservarTurno`.
- **Límite:** el flujo conversacional todavía no llama a `reservar` (pendiente del épico 8). Esta
  unidad deja el contrato (`PortAgenda.reservar` puede levantar el nuevo error) y el filtro, pero **no
  agrega el diálogo** de "ese horario ya pasó, te ofrezco otros". Queda anotado en los pendientes del
  épico 8.

## Diseño

### Dominio — `contexts/scheduling/domain/turno.py`
- Mensajes nuevos: `MENSAJE_TURNO_EN_EL_PASADO` ("No se puede agendar un turno en un horario que ya
  pasó.") y `MENSAJE_REPROGRAMAR_AL_PASADO` ("No se puede reprogramar un turno a un horario que ya
  pasó.").
- `Franja.empieza_antes_de(ahora)` y el `ya_transcurrio(ahora)` existente: `ahora` siempre como
  parámetro, **nunca `datetime.now()` en el dominio**.
- `Turno.registrar_a_posteriori(...)`: nace COMPLETADO con canal PANEL; rechaza si la franja no terminó.

### Aplicación — `contexts/scheduling/application/`
- `errors.py`: `TurnoEnElPasado` (hija de `EntradaInvalida`, 422) y el motivo "solo el Administrador
  puede registrar o corregir a posteriori".
- `turnos.py`:
  - `ReservarTurno.ejecutar(..., a_posteriori=False)`: sin el indicador exige `inicio >= ahora`; con él,
    exige Administrador, omite la disponibilidad base, usa `registrar_a_posteriori`, **no llama al
    `Avisador`** y audita `cargar_turno_a_posteriori`.
  - `ReprogramarTurno.ejecutar(..., a_posteriori=False)`: la misma lógica; con el indicador, no llama a
    `Avisador.reprogramacion` y audita `corregir_turno_a_posteriori`.
  - `_validar_momento(...)` extraído, para no pasar la complejidad ciclomática de 10.
  - `_auditar` acepta la acción como parámetro.

### Puertos y adaptadores
- `infrastructure/repositories.py`: `ocupados_en` cuenta también los COMPLETADO.
- `conversational/infrastructure/acl.py`: `AgendaViaScheduling` recibe un `Reloj`; `horarios_ofrecibles`
  filtra pasados.
- `api/conversacional.py`: pasa `unidad.reloj` al construir `AgendaViaScheduling`.

### Otros contextos
`conversational` llega a `scheduling` por su `application`, como hoy (R3). No hay aristas nuevas.
`billing` no se toca: la carga a posteriori habilita la facturación por la regla existente
(`habilita_facturacion` = COMPLETADO).

### API — `api/routers/agenda.py`
- `TurnoEntrada` y `ReprogramacionEntrada`: campo `a_posteriori: bool = False`.
- `GET /turnos/disponibilidad`: deja de ofrecer los horarios que ya pasaron (usa `unidad.reloj`). La
  carga a posteriori no usa la grilla: el Administrador escribe fecha y hora.

### Frontend — `features/scheduling`
- `api/turno.ts`: el indicador en `TurnoNuevo` y en `reprogramarTurno`; los dos mensajes como constantes.
- `NuevoTurno.tsx`: el campo de fecha con `min` = hoy. Para el Administrador, una casilla "Registrar una
  atención ya realizada" que reemplaza la grilla por un campo de fecha y hora con `max` = ahora.
- `DetalleDeTurno.tsx`: el campo de reprogramación con `min` = ahora; para el Administrador, una casilla
  "Corrección a posteriori" que quita ese `min`.
- Páginas `agenda/nuevo/page.tsx` y `agenda/[turnoId]/page.tsx`: nueva prop
  `puedeRegistrarAPosteriori = claims.rol === "ADMINISTRADOR"`, con el mismo patrón que ya usa
  `agenda/recursos/page.tsx`.
- Los `min` y `max` son cortesía de interfaz: **el rechazo real lo hace el backend** (CLAUDE.md §5, sin
  lógica de negocio en el frontend).

## Infraestructura

### Migraciones
- `0024_turno_completado_ocupa_la_franja.py`: amplía `excl_turno_recurso_franja` a COMPLETADO.
  Antes de recrear la restricción, consulta los solapamientos existentes entre turnos que quedarían
  cubiertos y aborta listándolos si los hay. `downgrade` restaura la condición original. Reversible.
  Sin backfill.

### Trabajo asíncrono · Configuración · Integraciones externas
**No aplica.** Nada es diferido, no hay variables nuevas y no se agrega ninguna integración.

## Riesgos que obligan a tests
- [ ] Toca dinero — no aplica
- [ ] Comprobantes fiscales — no aplica (solo habilita facturar por la regla existente)
- [ ] Webhook — no aplica
- [x] Datos por empresa — la nueva restricción y `ocupados_en` siguen filtrando por `empresa_id` y RLS
- [ ] Salida de un LLM — no aplica (el agente solo recibe horarios filtrados)
- [ ] Datos personales a un LLM — no aplica

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/scheduling/domain/turno.py`
- [x] `backend/src/cheatsheet/contexts/scheduling/application/errors.py`
- [x] `backend/src/cheatsheet/contexts/scheduling/application/turnos.py`
- [x] `backend/src/cheatsheet/contexts/scheduling/infrastructure/repositories.py`
- [x] `backend/src/cheatsheet/contexts/conversational/infrastructure/acl.py`
- [x] `backend/src/cheatsheet/api/conversacional.py`
- [x] `backend/src/cheatsheet/api/routers/agenda.py`
- [x] `backend/migrations/versions/0024_turno_completado_ocupa_la_franja.py`
- [x] `backend/tests/contexts/scheduling/domain/test_turno.py`
- [x] `backend/tests/contexts/scheduling/application/test_agenda.py` (y `dobles.py` si hace falta)
- [x] `backend/tests/integracion/test_api_agenda.py`
- [x] `backend/tests/integracion/test_agenda_postgres.py`
- [x] Test nuevo de `AgendaViaScheduling` con reloj fijo

### Frontend
- [x] `frontend/src/features/scheduling/api/turno.ts`
- [x] `frontend/src/features/scheduling/components/NuevoTurno.tsx`
- [x] `frontend/src/features/scheduling/components/DetalleDeTurno.tsx`
- [x] `frontend/src/app/(panel)/agenda/nuevo/page.tsx`
- [x] `frontend/src/app/(panel)/agenda/[turnoId]/page.tsx`
- [x] `frontend/src/features/scheduling/api/__tests__/turno.test.ts`
- [x] `frontend/src/features/scheduling/components/__tests__/pantallas.test.tsx`

### Docs
- [ ] `docs/aidlc/units.md` (estado de la fila)
- [x] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (el diálogo de "ese horario ya pasó")

## Casos de prueba

Modo: **test primero**. Los casos 1 a 4 reproducen el bug y tienen que fallar antes de tocar el código
(CLAUDE.md §5: todo bug arreglado empieza con el test que lo reproduce).

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Reservar hoy a una hora anterior a la actual → `TurnoEnElPasado` con el mensaje de la historia | unit | pasa |
| 2 | Reservar hoy a una hora posterior a la actual → se crea | unit | pasa |
| 3 | Reprogramar a una hora ya transcurrida (Operador y Administrador sin indicador) → rechazado, el turno conserva su franja | unit | pasa |
| 4 | Reservar un turno en curso (`inicio < ahora < fin`) → rechazado, con y sin indicador | unit | pasa |
| 5 | `inicio == ahora` → se acepta | unit | pasa |
| 6 | Administrador con `a_posteriori` y franja terminada → turno COMPLETADO, canal PANEL, sin aviso, acción `cargar_turno_a_posteriori` | unit | pasa |
| 7 | Operador con `a_posteriori` → 422 con el motivo de solo Administrador | unit | pasa |
| 8 | Carga a posteriori fuera de la disponibilidad base → se acepta | unit | pasa |
| 9 | Corrección a posteriori del Administrador → el turno se mueve, conserva el estado, sin aviso, acción `corregir_turno_a_posteriori` | unit | pasa |
| 10 | `Turno.registrar_a_posteriori` con franja no terminada → rechazado | unit | pasa |
| 11 | Carga a posteriori solapada con un turno COMPLETADO → rechazada por la base | integración (PostgreSQL) | no corre localmente: requiere PostgreSQL |
| 12 | Turno nuevo sobre uno COMPLETADO → rechazado por la base; sobre uno NO_SHOW → aceptado | integración (PostgreSQL) | no corre localmente: requiere PostgreSQL |
| 13 | La migración aborta y lista los conflictos si hay COMPLETADO solapados | integración (PostgreSQL) | no corre localmente: requiere PostgreSQL |
| 14 | `GET /turnos/disponibilidad` de hoy no ofrece horarios pasados | integración (API) | no corre localmente: requiere PostgreSQL |
| 15 | `POST /turnos` en el pasado → 422 con el mensaje de la historia | integración (API) | no corre localmente: requiere PostgreSQL |
| 16 | `AgendaViaScheduling.horarios_ofrecibles` con reloj fijo no ofrece pasados; `reservar` usa el reloj inyectado | unit | pasa |
| 17 | Frontend: el Operador no ve la opción a posteriori; el Administrador sí | unit (frontend) | pasa |
| 18 | Frontend: el mensaje del backend se muestra tal cual en el `Alert` | unit (frontend) | pasa |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-29 | aprobado sin cambios |
| 2 · Verificación | 2026-09-29 | aprobado. ruff, mypy y pytest en verde (1331 pasan; 328 omitidos por requerir PostgreSQL o Redis). Frontend: lint, typecheck y test:coverage en verde (84,14 %). `format:check` falla solo por el checkout CRLF de Windows y pasa con `--end-of-line auto`. Los casos 11 a 15 los corre la CI |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- Carga a posteriori: nace COMPLETADO con un constructor de dominio, no se transiciona (§2).
- Excepción pedida con un indicador explícito, nunca inferida del inicio (§3).
- La exclusión de la base se amplía a COMPLETADO y NO_SHOW queda afuera (§4).
- En la excepción se mantiene "recurso activo" (§5).
- El diálogo del agente para horarios vencidos queda para el épico 8 (§8).
