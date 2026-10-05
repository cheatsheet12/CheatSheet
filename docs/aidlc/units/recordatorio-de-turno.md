# Unidad: recordatorio-de-turno

**HUs**: HU-E8-04 (RN-02, segundo criterio), HU-E11-01 (RN-01, RN-04, RN-05)   **Contexto dueño**: scheduling (barrido y marca por turno); business_config (lectura tipada de la regla, endpoint y editor)   **Rama**: feature/scheduling-recordatorio-de-turno

> Origen: plan de trabajo de la fase C (fuera del repo), decisión G4c y unidad U8. Cierra el
> pendiente **#7** del épico 8 y el **#11** del épico 7
> ([`../epicas/07-agenda-y-recursos/pendientes.md`](../epicas/07-agenda-y-recursos/pendientes.md)).
> Responsable Luciano; revisa Cristian, **y Paula y Emanuel la parte que toca sus módulos** (ver
> «Avisos al equipo»).
>
> **Depende de:** `plantillas-de-whatsapp-en-meta` (U6: plantilla `recordatorio_de_turno` en Meta y
> `ConsultarPlantillaParaEnviar`) y `entregas-de-whatsapp` (U7: `NotificarAlCliente`, que manda y
> guarda el aviso como mensaje `SISTEMA` con su estado de entrega), las dos **mergeadas**; y por
> ellas U5 y el ADR-0011. Interfaces asumidas que se vuelven a comprobar al empezar: el resultado de
> `NotificarAlCliente` con la clase de falla (transitoria / permanente / incierta / sin canal) y el
> mecanismo de savepoint por ítem que U5 introduce en el barrido de cobros.

## Qué hace

El cliente recibe por WhatsApp un **recordatorio de su turno** con la anticipación que la empresa
configura en PAN-CFG-RN (por defecto, 24 h antes). Lo dispara un barrido periódico de `scheduling`,
que nunca manda dos veces el mismo recordatorio del mismo turno, no recuerda turnos cancelados,
recalcula los de un turno reprogramado y usa la plantilla aprobada `recordatorio_de_turno`. El
recordatorio queda en la conversación del cliente con su estado de entrega, y si el cliente contesta,
el agente retoma (HU-E8-04 RN-03).

## Lo que existe hoy (relevado el 2026-10-04)

- `business_config/domain/regla.py:49`: `TipoRegla.AGENDA_DE_NOTIFICACION` existe; **no hay clase de
  configuración** (solo `ConfiguracionDeEscalamiento`, `:82-146`) ni `interpretada_como_…`.
  `ReglasVigentes` (`:227-239`) solo trae `escalamiento`. `ConsultarReglasVigentes`
  (`application/reglas.py:166-190`) solo resuelve escalamiento. `ConfigurarEscalamiento` (`:53-119`)
  es el patrón de «reemplaza, no acumula» a copiar.
- `api/routers/reglas.py`: `GET /reglas`, `PUT /reglas/escalamiento`, `PUT /reglas/{id}/estado`.
- Frontend: `features/payments/api/regla.ts:39-43` ya tiene la etiqueta «Agenda de notificaciones»;
  el editor de escalamiento es `features/payments/components/ReglasDeNegocio.tsx` (258 líneas),
  compuesto en `app/(panel)/configuracion/reglas/page.tsx`. `features/business_config/` está vacío
  (solo `index.ts` con `export {}`).
- **Insumos:** el DER (`inputs/der.md:138-147, 578`) da `regla_de_negocio.configuracion jsonb` y el
  valor del enum, **sin parámetros**. HU-E8-04 RN-02: «Los recordatorios de turno y de cobro se
  despachan según las reglas de escalamiento configuradas (ver historias de sistema)» — **no hay
  historia de sistema para el de turno** (HS-T3 es solo de cobros). Ningún prototipo muestra la
  configuración. **Los parámetros son una decisión de producto → P1/P2.**
- `scheduling/domain/turno.py`: `Turno(franja, estado, created_at, updated_at…)`, `ESTADOS_ABIERTOS =
  {RESERVADO, CONFIRMADO}`, `reprogramar` conserva el estado y no recibe el momento. No hay columna
  que diga **cuándo se fijó la franja actual**.
- `scheduling/domain/recurso.py:46`: `ZONA_DE_LA_AGENDA = America/Argentina/Buenos_Aires` (decisión
  D34, pendiente #3 del épico 7: una sola zona; Argentina no tiene horario de verano). Celery corre en
  UTC (`celery_app.py:40-41`); `franja_inicio` es `timestamptz`.
- `workers/beat.py`: **ninguna** entrada de scheduling. Las cinco colas (ADR-003) son
  `integrations_sync`, `spreadsheet_processing`, `incremental_sync`, `notifications`, `ai_nlp`; los
  barridos de mensajes salientes (`barrer-cobros`) van por `notifications`. No hay
  `workers/tasks_scheduling.py`.
- `PortNotificadorDeTurnos` tiene tres avisos y no devuelve nada; con U7 el adaptador recibe
  `CanalDeAvisos.notificar(...)` y `DatosDeAviso.cliente_id`.

## Diseño

### D-U8-1 · La regla tipada (business_config)

```json
{ "recordatorios": [ { "horas_antes": 24 } ] }
```

- `AnticipacionDeRecordatorio(horas_antes: int)` — entre 1 y 168 (una semana): un recordatorio con
  más de una semana deja de ser un recordatorio y uno con menos de una hora no llega a servir.
  Mensaje: «Las horas de anticipación deben estar entre 1 y 168.» (supuesto hasta P1).
- `ConfiguracionDeAgenda(recordatorios: tuple[AnticipacionDeRecordatorio, ...])` — de 1 a 3, sin
  repetidos, **ordenados de mayor a menor** anticipación; `como_json` / `desde_json` que **fallan al
  leer** una fila mal formada (mismo criterio D24 que el escalamiento). Sin canal: el recordatorio de
  turno sale por WhatsApp, que es lo que dice HU-E8-04, y no existe adaptador de email que justifique
  ofrecer otro.
- `AGENDA_POR_DEFECTO = (24 h)` (supuesto hasta P2). `ReglaDeNegocio.interpretada_como_agenda()`.
- `ReglasVigentes` gana `agenda` y `agenda_configurada`; `ConsultarReglasVigentes` resuelve los dos
  tipos (RN-05: prioridad, luego la más reciente). Una regla de agenda **desactivada** deja de regir de
  inmediato (RN-04) y vuelve el default — **salvo** que P2 decida «sin default»; en ese caso
  desactivar = no recordar.
- `ConfigurarAgendaDeNotificacion` (nuevo, en `application/reglas.py`): copia de
  `ConfigurarEscalamiento` — solo Administrador, reemplaza, reactiva al guardar, evento de bitácora
  `alta_regla_de_agenda` / `editar_regla_de_agenda`.
- `PUT /reglas/agenda` en `api/routers/reglas.py` (entrada `{recordatorios: [{horas_antes}],
  prioridad}`).

### D-U8-2 · Idempotencia por turno: tabla, no columna

**Decisión: tabla `recordatorio_de_turno`**, propiedad de scheduling, con índice único
`(turno_id, anticipacion_min, franja_inicio)`. Una columna `turno.recordatorio_enviado_en` no alcanza
por tres hechos:

1. La regla admite **varios** recordatorios por turno (P1): una columna marca uno solo.
2. **Reprogramar**: con la franja en la clave, el turno movido genera claves nuevas y sus
   recordatorios se recalculan **sin borrar ni resetear nada**; los de la franja vieja quedan como
   historia (lo que se mandó, se mandó). Con una columna habría que acordarse de ponerla en nulo en
   `reprogramar`, y el día que alguien lo olvide el turno movido no se recuerda.
3. El **reintento** de una falla transitoria necesita estado (intentos, próximo intento, último
   error), igual que el recordatorio de cobro de U7.

Es la misma idea que D25 en cobros: la unicidad la garantiza un índice, no una ventana de tiempo.

Columnas: `id`, `empresa_id` (RLS propia, como `turno`), `turno_id` (FK con `ON DELETE CASCADE`),
`anticipacion_min`, `franja_inicio`, `resultado` (`ENVIADO`, `FALLIDO`, `OMITIDO`, `DESCARTADO`, nulo
mientras espera reintento), `intentos`, `proximo_intento_en`, `ultimo_error`, `procesado_en`,
`created_at`. **El estado de entrega no se duplica acá:** vive en el `Mensaje` `SISTEMA` que guarda
U7 (un solo lugar por `wamid`).

### D-U8-3 · Cuándo corresponde un recordatorio

Para un turno abierto con inicio `I`, franja fijada en `F` y anticipación `h`, el momento es
`M = I − h`. Corresponde mandarlo en un barrido con `ahora` si:

- `M ≤ ahora < I` (llegó su momento y el turno no empezó);
- `M ≥ F` — **la franja ya estaba fijada en el momento del recordatorio**. Un turno reservado o
  reprogramado dentro de la ventana no recibe el recordatorio: el cliente acaba de recibir la
  confirmación o el aviso de reprogramación con la misma fecha y hora (supuesto hasta P3);
- no existe fila para `(turno, h, I)`.

Si **varias** anticipaciones corresponden a la vez (el worker estuvo caído), se manda **solo la más
cercana al turno** y las otras se registran `OMITIDO`: dos recordatorios del mismo turno en el mismo
minuto son peor que uno. Es la lección de D25 aplicada acá.

`F` necesita una columna nueva: **`turno.franja_asignada_en`** (`timestamptz NOT NULL`, backfill =
`created_at`). Se fija al reservar y en `Turno.reprogramar(franja, intervalo, ahora)` (gana el
parámetro). `updated_at` no sirve: cambia también al confirmar o al marcar asistencia, y un turno
confirmado dentro de la ventana perdería su recordatorio.

Todas las comparaciones son entre **instantes** (UTC); la zona solo interviene al **mostrar** fecha y
hora, que se formatean en `ZONA_DE_LA_AGENDA` (U6 ya lo hace en `avisos.py`). Ejemplo de test: turno
el 15/10/2026 a las 10:00 de Argentina = `13:00Z`; con 24 h, el recordatorio corresponde desde el
14/10 `13:00Z` y dice «15/10/2026» y «10:00».

### D-U8-4 · Cancelados, reprogramados y otros estados

| Situación | Efecto |
|---|---|
| Turno `CANCELADO`, `COMPLETADO`, `NO_SHOW` | No se selecciona. Una fila esperando reintento se marca `DESCARTADO` |
| Reprogramado | Claves nuevas para la franja nueva (D-U8-2); las pendientes de la franja vieja → `DESCARTADO`; si la reprogramación fue dentro de la ventana, `M < F` y no se recuerda (D-U8-3) |
| Carga a posteriori (nace `COMPLETADO`) | Nunca se recuerda |
| Cliente sin teléfono | Fila `OMITIDO`, `ultimo_error = SIN_TELEFONO` (no se reevalúa cada 15 min) |
| Empresa sin WhatsApp conectado (producción) | El barrido de esa empresa no corre: la raíz ve `SinCanal` y sale con log `recordatorios_de_turno_sin_canal`. No se crean filas ni hilos |
| Regla de agenda desactivada / sin default (P2) | No se recuerda; no se crean filas |

### D-U8-5 · Aplicación y puertos (scheduling)

- `scheduling/application/recordatorios.py` (nuevo): `EnviarRecordatoriosDeTurno.ejecutar(empresa_id,
  ahora) -> ResultadoDeBarrido`. Dos pasadas, **cada turno en su propio savepoint** (ADR-0011 punto 6,
  mismo mecanismo que U5 en cobros): 1) reintentos vencidos; 2) turnos abiertos con inicio en
  `(ahora, ahora + máxima anticipación]` → aplica D-U8-3 → `INSERT` de la fila (índice único: otro
  barrido llegó primero = «ya está») → `Avisador.recordatorio(turno)` → resultado → `UPDATE` de la
  fila → evento de bitácora `enviar_recordatorio_de_turno` (iniciador Sistema, `usuario_id=None`).
- Reintento: solo **transitorio**, tope 3, espera 15 y 30 min, **y nunca después de `I`** (pasada la
  hora, `DESCARTADO`). Incierto (timeout de lectura) o permanente → `FALLIDO` sin reintento. Sin canal
  → no ocurre (D-U8-4).
- Puertos nuevos en `application/ports.py`: `PortRepositorioRecordatoriosDeTurno` (`agregar` que
  puede levantar `RecordatorioDeTurnoDuplicado`, `guardar`, `de_turnos(ids)`,
  `pendientes_de_reintento(ahora)`), `PortAgendaDeNotificacion.anticipaciones() ->
  tuple[int, ...]` (minutos; el ACL traduce desde `ReglasVigentes`, como `PasoDeCadena` en
  payments), y `PortRepositorioTurno.abiertos_entre(desde, hasta)`.
- `PortNotificadorDeTurnos.avisar_recordatorio(datos) -> ResultadoDeAviso(enviado, falla)` — el
  único de los cuatro que devuelve algo, porque es el único que se reintenta. `Avisador.recordatorio`.
- `AvisoPorWhatsApp.avisar_recordatorio`: código `recordatorio_de_turno`, variables `nombre, servicio,
  fecha, hora` (las de `VARIABLES_POR_CODIGO`), plantilla aprobada o texto de fábrica (U6), por
  `NotificarAlCliente` (U7).
- ACL `scheduling/infrastructure/agenda_de_notificacion.py`: `AgendaViaConfiguracion` sobre
  `ConsultarReglasVigentes` (arista `business_config → scheduling` existente; mismo patrón que
  `payments/infrastructure/cadena.py`). Cableado en `api/agenda.py`.

### D-U8-6 · Trabajo asíncrono

- `workers/tasks_scheduling.py` (nuevo): `scheduling.recordar_turnos` (fan-out) y
  `scheduling.recordar_empresa`, cola **`notifications`** (es mensajería saliente, como
  `barrer-cobros`; ADR-003 fija cinco colas y esta tarea no justifica otra), sin `autoretry_for` (la
  corrida siguiente vuelve a evaluar: consultas por estado, no por cursor).
- Fan-out por `empresas_con_turnos_por_recordar(hasta timestamptz)` — función `SECURITY DEFINER`
  nueva que devuelve **solo** `empresa_id` de empresas con turnos abiertos que empiezan entre `now()`
  y `hasta` (`hasta = ahora + 168 h`), o con filas de `recordatorio_de_turno` esperando reintento.
- Beat: entrada `recordar-turnos` cada **15 minutos** — el recordatorio se mide en horas, y 15 min de
  imprecisión sobre «24 h antes» no se nota; cada 5 serían 288 consultas por día para lo mismo. La
  entrada es configurable (`RECORDATORIO_DE_TURNO_MINUTOS`, default 15) por el mismo motivo que
  `WHATSAPP_SONDEO_MINUTOS`.

### D-U8-7 · Frontend (PAN-CFG-RN)

- `features/business_config/api/agenda.ts` (nuevo): tipos y `configurarAgenda(recordatorios,
  prioridad)` contra el BFF.
- `features/business_config/components/AgendaDeNotificacion.tsx` (nuevo): hasta 3 filas «N horas
  antes del turno», agregar/quitar, mensaje de validación de la historia, «Rige la de por defecto: 24 h
  antes» cuando no hay regla, solo Administrador edita.
- `features/business_config/index.ts` exporta el componente y sus tipos (R5).
- `app/(panel)/configuracion/reglas/page.tsx` lo compone **debajo** del editor de escalamiento
  (lee la regla del mismo `GET /reglas`).
- BFF `app/api/reglas/agenda/route.ts` (`PUT`, mismo `reenviarAlBackend`).
- El editor nuevo va en `features/business_config` (el dueño correcto) aunque el de escalamiento viva
  hoy en `features/payments`. Mudar ese es ajeno a esta unidad: se anota, no se hace.

## Infraestructura

- **Migraciones** (una, número libre al mergear, encadenada a la cabeza de `develop`):
  - `recordatorio_de_turno` con RLS (`ENABLE` + `FORCE`, política por `empresa_id` igual que `turno`),
    índice único `uq_recordatorio_de_turno (turno_id, anticipacion_min, franja_inicio)`, índice parcial
    `(proximo_intento_en) WHERE proximo_intento_en IS NOT NULL`, permisos a `cheatsheet_app`.
  - `turno.franja_asignada_en timestamptz NOT NULL` (agregar nula → `UPDATE … = created_at` → `SET
    NOT NULL`).
  - `empresas_con_turnos_por_recordar(timestamptz)` `SECURITY DEFINER`, `REVOKE … FROM PUBLIC`,
    `GRANT EXECUTE … TO cheatsheet_app`.
  - Reversible.
- **Trabajo asíncrono**: D-U8-6.
- **Configuración**: `RECORDATORIO_DE_TURNO_MINUTOS` (default 15) en `platform/settings.py`,
  `backend/.env.example`, `render.yaml` (beat).
- **Integraciones externas**: ninguna nueva; usa el canal de U5–U7 (timeouts, reintentos y
  clasificación de fallas de U5).

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero → No aplica.
- [ ] Comprobantes / CAE → No aplica.
- [ ] Consume un webhook → No aplica directamente (el estado de entrega es de U7).
- [x] Datos con `empresa_id` → tabla nueva con RLS: test de aislamiento; el barrido de A no lee turnos
      de B.
- [ ] Salida de un LLM → No aplica (el historial del intérprete ya ve el descriptor de U7).
- [x] Datos personales → ningún log con nombre, teléfono ni texto.
- [x] Idempotencia de un barrido → dos corridas solapadas = un mensaje por (turno, anticipación,
      franja).
- [x] Zona horaria → borde de día en hora de Argentina vs UTC.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/contexts/business_config/domain/regla.py` (`AnticipacionDeRecordatorio`, `ConfiguracionDeAgenda`, `AGENDA_POR_DEFECTO`, `interpretada_como_agenda`, `ReglasVigentes.agenda`)
- [ ] `backend/src/cheatsheet/contexts/business_config/application/reglas.py` (`ConfigurarAgendaDeNotificacion`, `ConsultarReglasVigentes`, `configuracion_de_agenda_desde`)
- [ ] `backend/src/cheatsheet/api/routers/reglas.py` (`PUT /reglas/agenda`)
- [ ] `backend/src/cheatsheet/contexts/scheduling/domain/turno.py` (`franja_asignada_en`, `reprogramar(..., ahora)`) · `domain/recordatorio_de_turno.py` (nuevo: entidad y regla D-U8-3)
- [ ] `backend/src/cheatsheet/contexts/scheduling/application/recordatorios.py` (nuevo) · `application/ports.py` · `application/turnos.py` (`Avisador.recordatorio`, `franja_asignada_en` al reservar/reprogramar) · `application/errors.py`
- [ ] `backend/src/cheatsheet/contexts/scheduling/infrastructure/models.py`, `repositories.py`, `avisos.py`, `agenda_de_notificacion.py` (nuevo), `ensamblado.py`
- [ ] `backend/src/cheatsheet/api/agenda.py` (`armar_agenda_de_notificacion`, armado del barrido)
- [ ] `backend/src/cheatsheet/workers/tasks_scheduling.py` (nuevo) · `workers/beat.py` · `workers/main.py`
- [ ] `backend/src/cheatsheet/platform/settings.py` · `backend/.env.example` · `render.yaml`
- [ ] `backend/migrations/versions/00NN_recordatorio_de_turno.py`
- [ ] `backend/tests/contexts/business_config/domain/test_regla.py`, `…/application/test_reglas.py`, `backend/tests/api/test_reglas.py`
- [ ] `backend/tests/contexts/scheduling/domain/test_recordatorio_de_turno.py`, `test_turno.py`, `…/application/test_recordatorios.py`, `…/infrastructure/test_avisos.py`, `test_repositories.py`
- [ ] `backend/tests/workers/test_recordar_turnos.py`, `backend/tests/workers/test_beat.py`
- [ ] `frontend/src/features/business_config/api/agenda.ts`, `components/AgendaDeNotificacion.tsx`, `index.ts` y sus tests
- [ ] `frontend/src/app/(panel)/configuracion/reglas/page.tsx` · `frontend/src/app/api/reglas/agenda/route.ts`
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#7) · `docs/aidlc/epicas/07-agenda-y-recursos/pendientes.md` (#11) · `docs/aidlc/units.md`

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — Un turno que empieza en 23 h, con la regla por defecto, no recibe nada tras correr el barrido (hoy no existe). GREEN: un recordatorio con la plantilla `recordatorio_de_turno` y una fila `ENVIADO` | caso de uso | pendiente |
| 2 | **RED** — `ReglaDeNegocio(AGENDA_DE_NOTIFICACION).interpretada_como_agenda()` no existe. GREEN: devuelve la configuración tipada | unit | pendiente |
| 3 | Configuración: 0 recordatorios, 4, horas 0 o 169, repetidos → `EntradaInvalida` con la frase; se ordenan de mayor a menor | unit (tabla) | pendiente |
| 4 | Fila mal formada en la base → falla al leer, no a mitad del barrido (D24) | unit | pendiente |
| 5 | `PUT /reglas/agenda`: Administrador guarda y reemplaza; Operador → rechazo; bitácora con la acción | integración (API) | pendiente |
| 6 | Sin regla → default 24 h y `agenda_configurada=False`; regla desactivada → deja de regir de inmediato (RN-04) | unit | pendiente |
| 7 | Dos reglas de agenda → gana la de mayor prioridad (RN-05) | unit | pendiente |
| 8 | Dos barridos seguidos (y solapados) → un solo mensaje por (turno, anticipación, franja) | caso de uso + integración (CI) | pendiente |
| 9 | Con 48 h y 24 h y el worker caído hasta faltar 20 h → se manda solo el de 24 h; el de 48 h queda `OMITIDO` | caso de uso | pendiente |
| 10 | Turno reservado 3 h antes con regla de 24 h → no se recuerda (`M < F`) | caso de uso | pendiente |
| 11 | Turno confirmado dentro de la ventana → **sí** se recuerda (`updated_at` no interviene) | caso de uso | pendiente |
| 12 | Turno reprogramado a otra fecha → recordatorio nuevo para la franja nueva; una pendiente de la franja vieja → `DESCARTADO` | caso de uso | pendiente |
| 13 | Turno cancelado → nunca se recuerda; uno cancelado con reintento pendiente → `DESCARTADO` | caso de uso | pendiente |
| 14 | Turno a posteriori, completado o no-show → nunca | caso de uso | pendiente |
| 15 | Turno ya empezado → no se manda aunque el recordatorio no haya salido | caso de uso | pendiente |
| 16 | Cliente sin teléfono → fila `OMITIDO` `SIN_TELEFONO`, ningún envío, no se reevalúa | caso de uso | pendiente |
| 17 | Falla transitoria → reintento a los 15 y 30 min; agotado → `FALLIDO`; pasado el inicio → `DESCARTADO` | caso de uso | pendiente |
| 18 | Timeout de lectura → `FALLIDO` sin reintento; permanente → `FALLIDO` sin reintento | caso de uso | pendiente |
| 19 | Un turno que falla no voltea los demás del barrido (savepoint por turno) | caso de uso | pendiente |
| 20 | Zona: turno 15/10/2026 10:00 AR (`13:00Z`) → corresponde desde el 14/10 `13:00Z`, el texto dice «15/10/2026» y «10:00» | unit | pendiente |
| 21 | Turno a las 00:30 AR (03:30Z del mismo día UTC): el texto dice la fecha argentina correcta | unit | pendiente |
| 22 | Empresa sin WhatsApp conectado en producción → el barrido de esa empresa no corre, ninguna fila | unit (raíz) | pendiente |
| 23 | El recordatorio queda como mensaje `SISTEMA` en la conversación del cliente (U7) y la respuesta del cliente la toma el agente | integración | pendiente |
| 24 | RLS: barrido de A con turnos de B → no los ve; la tabla nueva aísla por `empresa_id` | integración (CI) | pendiente |
| 25 | `empresas_con_turnos_por_recordar` devuelve solo ids, incluye empresas con reintentos pendientes y respeta `hasta` | migración (CI) | pendiente |
| 26 | Backfill: `franja_asignada_en = created_at`; reservar y reprogramar la fijan | migración + unit | pendiente |
| 27 | Beat tiene `recordar-turnos` en la cola `notifications` con el intervalo de configuración | unit | pendiente |
| 28 | Ningún log del barrido contiene nombre, teléfono ni texto | unit (captura de logs) | pendiente |
| 29 | PAN-CFG-RN: el editor agrega hasta 3, valida con la frase, muestra el default, solo Administrador edita | unit (Vitest) | pendiente |
| 30 | `guard_architecture --scan` (R1–R5, incluida R5 en el frontend) y `test_guards.sh` pasan | gate | pendiente |

Gates: los mismos de U6. Los casos 8, 24, 25 y 26 corren con PostgreSQL en la CI.

## Verificaciones no posibles sin la app de prueba → `TODO.md` §25

| # | Qué verificar | Unidad | Qué pasa si difiere |
|---|---|---|---|
| 25.20 | Punta a punta en staging con `meta`: un turno a 24 h recibe la plantilla aprobada `recordatorio_de_turno` y el callback la marca entregada | `recordatorio-de-turno` | Se ajusta según 25.5/25.9 (U5/U6); el barrido no cambia |

## Avisos al equipo

- **Paula** (reglas de negocio, HU-E11-01; manual `manual/60-cobros.md`): PAN-CFG-RN gana un segundo
  editor (agenda de notificaciones) y `GET /reglas` empieza a devolver reglas de tipo
  `AGENDA_DE_NOTIFICACION`. Se le pide revisar en el PR `domain/regla.py`, `application/reglas.py`,
  `api/routers/reglas.py` y la pantalla, y reflejar el editor en su parte del manual y de la matriz.
- **Emanuel** (agenda, HU-E7-01 … HU-E7-06; manual `manual/70-agenda.md`): la tabla `turno` gana
  `franja_asignada_en`, `Turno.reprogramar` recibe el momento, hay una tabla nueva
  `recordatorio_de_turno` y un barrido cada 15 min. Se le pide revisar en el PR `domain/turno.py`,
  `application/turnos.py`, `application/recordatorios.py` y la migración, y contemplar en sus pruebas
  que reprogramar recalcula el recordatorio y cancelar lo anula.
- **Equipo** (M6): HU-E8-04 cierra entera recién con esta unidad.

## Preguntas del Gate 1

1. **¿Cuántos recordatorios por turno y con qué parámetro?** Recomendación: **hasta 3, cada uno
   expresado en horas antes del turno (1 a 168).** Uno solo cubre el caso típico (24 h), pero un
   consultorio suele querer «el día anterior y 2 h antes»; tres alcanza sin convertirse en acoso (el
   mismo criterio que `MAXIMO_DE_PASOS`). Horas y no días: «2 h antes» no se puede decir en días.
2. **¿Qué pasa si la empresa nunca configuró la regla?** Recomendación: **rige un default de un
   recordatorio 24 h antes**, y la pantalla lo dice. Es el mismo criterio que `ESCALAMIENTO_POR_DEFECTO`
   («una empresa que nunca entró a PAN-CFG-RN no puede quedarse sin recordatorios y sin enterarse»), y
   el criterio de HU-E8-04 espera el recordatorio. La alternativa —sin regla no se recuerda— deja la
   función apagada en toda empresa que no la descubra.
3. **Turno reservado o reprogramado cuando ya pasó el momento del recordatorio** (por ejemplo, se
   reserva hoy para mañana temprano con regla de 24 h): ¿se manda igual en el acto o se omite?
   Recomendación: **se omite**; el cliente acaba de recibir la confirmación o el aviso de
   reprogramación con la misma fecha y hora, y un segundo mensaje un minuto después es ruido. Si hay
   otro recordatorio más cercano configurado (2 h antes), ese sí sale.
4. **¿Hace falta un horario de silencio (no mandar recordatorios de noche)?** Recomendación: **no en
   esta unidad.** Con anticipaciones en horas el recordatorio sale a la misma hora del día que el turno
   menos `h`; con el default de 24 h sale a la hora del turno del día anterior, que es horario de
   atención. Solo un «2 h antes» de un turno de las 8 saldría a las 6. Si aparece el pedido, es una
   regla nueva de la agenda (y una enmienda de historia).

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | Aprobado por Luciano con las recomendaciones de las preguntas. **Cierra cuando el equipo acepte el ADR-0011** ([#62](https://github.com/cheatsheet12/CheatSheet/pull/62)); hasta entonces no se escribe código |
| 2 · Verificación | | |
| 3 · PR | | |

> Bloqueado para cerrar el Gate 1 hasta que el ADR-0011 esté aceptado y U5, U6 y U7 mergeadas.

## Decisiones tomadas durante la unidad

- Gate 1 (2026-10-04): Pregunta 1 → hasta 3 recordatorios por turno, cada uno en horas antes (1 a 168).
- Gate 1 (2026-10-04): Pregunta 2 → sin regla configurada rige un recordatorio por defecto 24 h antes.
- Gate 1 (2026-10-04): Pregunta 3 → se omite el recordatorio si el turno se reservó o se movió cuando su momento ya había pasado.
- Gate 1 (2026-10-04): Pregunta 4 → sin horario de silencio en esta unidad.
