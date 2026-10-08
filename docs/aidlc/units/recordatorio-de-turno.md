# Unidad: recordatorio-de-turno

**HUs**: HU-E8-04 (RN-02, segundo criterio), HU-E11-01 (RN-01, RN-04, RN-05)   **Contexto dueño**: scheduling (barrido, fila por recordatorio y envío); business_config (regla tipada, consulta propia, endpoint y editor); conversational (un campo nuevo en el resultado de `NotificarAlCliente`)   **Rama**: feature/scheduling-recordatorio-de-turno

> Origen: plan de trabajo de la fase C (fuera del repo), decisión G4c y unidad U8. Cierra el
> pendiente **#7** del épico 8 y el **#11** del épico 7
> ([`../epicas/07-agenda-y-recursos/pendientes.md`](../epicas/07-agenda-y-recursos/pendientes.md)).
> Responsable Luciano; revisa Cristian, **y Paula y Emanuel la parte que toca sus módulos** (ver
> «Avisos al equipo»).
>
> **Re-presentación (08/10).** El plan aprobado el 04/10 se revalidó el 07/10 contra U6
> (`plantillas-de-whatsapp-en-meta`) y U7 (`entregas-de-whatsapp`) ya implementadas. Cambian el
> diseño del envío y aparece un cambio en `conversational`, así que **el Gate 1 se repite**. Las cuatro
> preguntas del 04/10 siguen valiendo (D-U8-1 a D-U8-4 conservan su lógica); las once decisiones de la
> revalidación están en «Decisiones aprobadas para este Gate 1».
>
> **Depende de:** U6 (`ConsultarPlantillaParaEnviar`, plantilla `recordatorio_de_turno` en Meta,
> migración 0036) y U7 (`NotificarAlCliente`, el envío en tres tiempos y `ConfirmacionDeLaUnidad`,
> migraciones 0037 y 0038), **mergeadas en `develop`** antes de los tramos 2 y 3. Interfaces leídas
> de `origin/feature/conversational-entregas-de-whatsapp-avisos` (`23c0880`, tramo iii, que trae
> también U6); se vuelven a comprobar contra `develop` cuando U7 entre.

## Qué hace

El cliente recibe por WhatsApp un **recordatorio de su turno** con la anticipación que la empresa
configura en PAN-CFG-RN (por defecto, 24 h antes). Lo dispara un barrido periódico de `scheduling`
que nunca manda dos veces el mismo recordatorio del mismo turno, no recuerda turnos cancelados,
recalcula los de un turno reprogramado, usa la plantilla aprobada `recordatorio_de_turno` y reintenta
solo las fallas transitorias. El recordatorio queda en la conversación del cliente como mensaje
`SISTEMA` con su estado de entrega, y si el cliente contesta, el agente retoma (HU-E8-04 RN-03).

## Lo que existe hoy (relevado el 2026-10-08)

En `develop` (`147ab1b`):

- `business_config/domain/regla.py` (266 líneas): `TipoRegla.AGENDA_DE_NOTIFICACION` existe sin clase
  de configuración; `resolver(reglas, tipo)` (`:225`) implementa RN-05; `ReglasVigentes` (`:240`) solo
  trae `escalamiento`.
- **Segunda regla tipada ya resuelta, el patrón a copiar (P6):** `HORARIO_DE_ATENCION` con dominio
  propio (`domain/horario_de_atencion.py`, `horario_de_atencion_json.py`), casos de uso propios en
  `application/atencion.py` (149 líneas: `ConfigurarHorarioDeAtencion`, `ConsultarAtencion` como Open
  Host Service, `configuracion_de_atencion_desde`), `PUT /reglas/horario-de-atencion` en
  `api/routers/reglas.py` (198 líneas) y frontend en `features/business_config` (`api/atencion.ts`,
  `components/HorarioDeAtencion.tsx`, `horarioDe(reglas)` exportado por `index.ts`), con su BFF
  `app/api/reglas/horario-de-atencion/route.ts`.
- `scheduling/domain/turno.py` (325): `ESTADOS_ABIERTOS = {RESERVADO, CONFIRMADO}` (`:109`),
  `reprogramar(franja, intervalo_posterior_min)` (`:241`) no recibe el momento; no hay columna que
  diga cuándo se fijó la franja actual. Índice `ix_turno_empresa_franja (empresa_id, franja_inicio)`.
- **Tamaños (P12):** `application/turnos.py` 521 líneas y `api/routers/agenda.py` 688 superan el
  tope de 400: **el código nuevo va a módulos nuevos**; en `turnos.py` solo se cambia la llamada a
  `reprogramar` (`:403`) para pasar el momento.
- `workers/beat.py`: ninguna entrada de scheduling; `barrer-cobros` va por `Cola.NOTIFICATIONS`.

En U7 (`origin/feature/conversational-entregas-de-whatsapp-avisos`):

- `conversational/application/notificaciones.py`: `NotificarAlCliente.ejecutar(*, empresa_id,
  cliente_id, telefono, envio: EnvioDeAviso, ahora) -> ResultadoDeNotificacion`. Manda y después
  guarda el `Mensaje` `SALIENTE`/`SISTEMA` en un savepoint propio (`aislar`). **Nunca levanta por el
  canal.** `ResultadoDeNotificacion(enviado, externo_id, falla, sin_registrar, causa)` **no dice si
  la falla es transitoria (P1)**: `motivo_de_falla_de` (`application/errors.py:137`) devuelve el código
  de Meta o una clase corta, no la clase de falla.
- `scheduling/infrastructure/avisos.py` (263): `CanalDeAvisos.notificar(...) -> ResultadoLocal`
  (`ResultadoLocal(enviado, falla, sin_registrar, causa)`, también sin `transitoria`),
  `PlantillasAprobadas.para(codigo, variables)`, `variables_de_aviso(datos)`. Lo respalda
  `api/avisos_de_turno.py` (`CanalDeAvisosViaConversacion`, `armar_canal_de_avisos`).
- **Envío en tres tiempos** (`payments/application/reintentos.py`, docstring): reservar + confirmar →
  mandar (sin escrituras sin confirmar ni locks) → registrar + confirmar. Piezas:
  `PortAislamiento.aislar()` y `PortTransaccion.confirmar()` (`payments/application/ports_envio.py:55`
  y `:70`), `ConfirmacionDeLaUnidad` (`payments/infrastructure/transaccion.py`, 56 líneas),
  `AislamientoConSavepoint` (`payments/infrastructure/aislamiento.py`, 38) y `DespachoNoPersistido`
  (`payments/application/errors.py:92`). Constantes del dominio de cobros: `REINTENTOS_MAXIMOS = 3`,
  `VENTANA_DE_ENVIO = 30 min` (`payments/domain/recordatorio.py`).
- Clasificación transitoria: `api/fallas_de_canal._traducir` marca transitoria **solo**
  `MensajeriaSaturada`; `EnvioIncierto` (timeout de lectura) nunca lo es.
- Sin canal: `api/mensajeria.armar_mensajeria` devuelve `SinCanal()`
  (`conversational/infrastructure/canal.py:174`), que **recién falla al enviar** (P5).
- Identidad fija del agente: `api/conversacional.py:150` arma el catálogo con
  `rol=RolUsuario.OPERADOR` (P4: el barrido no tiene actor y el ACL de servicios exige un rol).
- Plantilla: `VARIABLES_POR_CODIGO["recordatorio_de_turno"] = {nombre, servicio, fecha, hora}`
  (`business_config/domain/plantilla.py:95`); `ConsultarPlantillaParaEnviar`
  (`business_config/application/plantillas.py:155`).
- **Migraciones (P7):** `develop` llega a **0035**; U6 agrega **0036** (`plantillas_en_meta`) y U7
  **0037** (`entregas_de_whatsapp`) y **0038** (`reintento_de_recordatorios`). La de U8 es **0039**.
- **Funciones `SECURITY DEFINER` (P8):** con U6 y U7 hay **17** distintas
  (`empresas_con_recordatorios_en_espera` de 0038 es la última); la de U8 es la **18.ª** y la 12.ª de
  la familia `empresas_con_*`. El «novena» del informe no se sostiene: los docstrings del repo ya
  numeran de forma inconsistente (0022 dice «novena», 0038 dice «octava»). El código nuevo no lleva
  ordinal.
- **G5 (P9):** el ADR-0014 (#101) trata solo de Beat persistente (RedBeat + crontab). **No resuelve
  G5** (E/S a Meta con la transacción abierta). Las referencias «G5/ADR-0014» de U6, U7 y
  `TODO.md` §22.57/§22.64 están mal; corregirlas es de esas unidades, no de esta (se avisa, no se toca).

## Decisiones aprobadas para este Gate 1

Las once decisiones de la revalidación del 07/10, **aprobadas por Luciano el 2026-10-08 tal como se
recomendaron**. Numeración: la decisión *n* del informe es **D-U8-(7+n)**.

| Id | Decisión |
|---|---|
| **D-U8-8** | **Reintento acotado.** Solo falla transitoria, 3 intentos, esperas de 15 y 30 min, nunca después de la hora del turno. Incierto o permanente → `FALLIDO` sin reenvío |
| **D-U8-9** | **Queda como mensaje `SISTEMA` en el hilo**, vía `NotificarAlCliente` |
| **D-U8-10** | **Envío en tres tiempos de U7** (reservar + confirmar → mandar → registrar + confirmar). U8 no agrava G5 y no depende de #101 |
| **D-U8-11** | **Extracción (ajustada en el Gate 1 del 08/10):** a `shared/` los dos `Protocol` (`PortAislamiento`, `PortTransaccion`) y el tipo de error; a `platform/`, juntos, `ConfirmacionDeLaUnidad` y `AislamientoConSavepoint` (~120 líneas movidas). El orquestador queda por contexto |
| **D-U8-12** | **Rol en el worker:** ACL de scheduling sobre master_data con identidad de sistema fija `OPERADOR`, como el agente |
| **D-U8-13** | **Empresa sin WhatsApp:** chequeo de `SinCanal` en la raíz del barrido, antes de crear filas; log `recordatorios_de_turno_sin_canal` |
| **D-U8-14** | **Regla:** seguir `atencion.py` con consulta propia `ConsultarAgendaDeNotificacion`; no inflar `ReglasVigentes`. Default 24 h |
| **D-U8-15** | **Migración 0039**, encadenada cuando U6 y U7 estén en `develop` |
| **D-U8-16** | **Beat cada 15 min, configurable**; test de dos barridos solapados con PostgreSQL |
| **D-U8-17** | **Filas `OMITIDO`/`DESCARTADO` se mantienen**, con retención e índices parciales explícitos (ver Migración) |
| **D-U8-18** | **Ventana de 24 h de Meta:** sin plantilla aprobada el recordatorio falla siempre (131047) fuera de la ventana: se avisa en el PR y PAN-CFG-NOT muestra la advertencia |

**Premisas del plan del 04/10 que cambiaron:** P1 (falta `transitoria`), P3 (el orden INSERT → Meta →
UPDATE es el defecto H1 de U7, §22.57), P4 (el barrido no tiene actor), P5 (`SinCanal` falla tarde),
P6 (patrón `atencion.py`), P7/P8 (0039; ordinal corregido arriba), P9 (ADR-0014 no resuelve G5) y P12
(módulos nuevos). Siguen valiendo: plantilla `recordatorio_de_turno` y sus variables,
`variables_de_aviso`, la lógica D-U8-3/D-U8-4 y el descriptor del SISTEMA para el intérprete.

## Diseño

### D-U8-1 · La regla tipada (business_config), con el patrón de `atencion.py` (D-U8-14)

```json
{ "recordatorios": [ { "horas_antes": 24 } ] }
```

- **Dominio** — `business_config/domain/agenda_de_notificacion.py` (nuevo, ~120):
  `AnticipacionDeRecordatorio(horas_antes: int)` entre 1 y 168 («Las horas de anticipación deben estar
  entre 1 y 168.»); `ConfiguracionDeAgenda(recordatorios: tuple[...])` de 1 a 3, sin repetidos,
  ordenados de mayor a menor; `como_json` / `desde_json` que **fallan al leer** una fila mal formada
  (D24); `AGENDA_POR_DEFECTO = (24 h)`. En `regla.py`, solo `interpretada_como_agenda()` (como
  `interpretada_como_atencion`). `ReglasVigentes` **no cambia**.
- **Aplicación** — `business_config/application/agenda.py` (nuevo, ~130), espejo de `atencion.py`:
  - `ConfigurarAgendaDeNotificacion`: solo Administrador (`_exigir_administrador`), reemplaza, reactiva
    al guardar, bitácora `alta_regla_de_agenda` / `editar_regla_de_agenda`.
  - `ConsultarAgendaDeNotificacion.ejecutar(*, empresa_id) -> AgendaVigente(anticipaciones_min:
    tuple[int, ...], configurada: bool)` — Open Host Service sin chequeo de rol (quien llama es otro
    contexto). Sin regla → `AGENDA_POR_DEFECTO`, `configurada=False`; varias → `resolver` (RN-05). Regla
    desactivada → ver **Pregunta abierta 1**.
- **API** — `PUT /reglas/agenda` en `api/routers/reglas.py` (~+30; entrada `{recordatorios:
  [{horas_antes}], prioridad}`). `GET /reglas` ya devuelve todas las reglas.

### D-U8-2 · Idempotencia por turno: tabla `recordatorio_de_turno`, no columna

Sin cambios de fondo: índice único `(turno_id, anticipacion_min, franja_inicio)`. Una columna en
`turno` no alcanza porque la regla admite hasta 3 recordatorios, porque reprogramar genera claves
nuevas sin resetear nada, y porque el reintento necesita estado. Es la idea de D25 en cobros: la
unicidad la garantiza un índice. **El estado de entrega no se duplica:** vive en el `Mensaje`
`SISTEMA` de U7 (un solo lugar por `wamid`).

Estados de una fila (`resultado` + columnas de intento, mismo modelo que `payments/domain/recordatorio.py`):

| Situación | `resultado` | `ultimo_error` | `proximo_intento_en` |
|---|---|---|---|
| Envío en curso (reservada y confirmada, Meta todavía no contestó) | `NULL` | `NULL` | reserva + `VENTANA_DE_ENVIO` (30 min) |
| Esperando reintento tras falla transitoria | `NULL` | código | reloj + 15 min · 2^(intentos−1) |
| Salió | `ENVIADO` | `NULL` | `NULL` |
| Falla permanente, incierta o reintentos agotados | `FALLIDO` | código / `INCIERTO` | `NULL` |
| No corresponde mandarla (otra anticipación más cercana, sin teléfono) | `OMITIDO` | `ANTICIPACION_SUPERADA` / `SIN_TELEFONO` | `NULL` |
| Turno cancelado, movido o ya empezado mientras esperaba | `DESCARTADO` | `TURNO_CERRADO` / `FRANJA_CAMBIADA` / `TURNO_EMPEZADO` | `NULL` |

### D-U8-3 · Cuándo corresponde un recordatorio (sin cambios)

Para un turno abierto con inicio `I`, franja fijada en `F` y anticipación `h`, `M = I − h`. Corresponde
si `M ≤ ahora < I`, `M ≥ F` (la franja ya estaba fijada; Pregunta 3 del 04/10) y no hay fila para
`(turno, h, I)`. Si varias corresponden a la vez (worker caído), sale **solo la más cercana al turno** y
las otras quedan `OMITIDO`.

`F` = **`turno.franja_asignada_en`** (`timestamptz NOT NULL`, backfill `created_at`), fijada al reservar y
en `Turno.reprogramar(franja, intervalo, ahora)`. `updated_at` no sirve (cambia al confirmar).

Comparaciones entre instantes UTC; la zona solo interviene al mostrar (`ZONA_DE_LA_AGENDA`, como
`avisos._dia` / `_hora`). Ejemplo: turno 15/10/2026 10:00 AR = `13:00Z`; con 24 h corresponde desde el
14/10 `13:00Z` y el texto dice «15/10/2026» y «10:00».

La regla vive en `scheduling/domain/recordatorio_de_turno.py` (nuevo, ~180): la entidad
`RecordatorioDeTurno` con `iniciar_intento`, `registrar_falla(..., transitoria)`, `marcar_enviado`,
`fallar`, `omitir`, `descartar` y `envio_en_curso`; y la función pura `que_corresponde(turno,
anticipaciones, existentes, ahora) -> PlanDeRecordatorio` (qué mandar, qué omitir).

### D-U8-4 · Cancelados, reprogramados y otros estados

| Situación | Efecto |
|---|---|
| Turno `CANCELADO`, `COMPLETADO`, `NO_SHOW` | No se selecciona. Una fila esperando reintento → `DESCARTADO` (`TURNO_CERRADO`) |
| Reprogramado | Claves nuevas para la franja nueva; pendientes de la franja vieja → `DESCARTADO` (`FRANJA_CAMBIADA`); si fue dentro de la ventana, `M < F` y no se recuerda |
| Carga a posteriori (nace `COMPLETADO`) | Nunca se recuerda |
| Cliente sin teléfono | Fila `OMITIDO` `SIN_TELEFONO` (no se reevalúa cada 15 min) |
| Empresa sin WhatsApp conectado (producción) | La raíz ve `SinCanal` y sale con log `recordatorios_de_turno_sin_canal` (D-U8-13). Ninguna fila, ningún hilo |
| Turno que empieza antes del próximo reintento | `DESCARTADO` (`TURNO_EMPEZADO`): nunca después de `I` (D-U8-8) |

### D-U8-5 · Aplicación y puertos (scheduling)

**Puertos** — `scheduling/application/ports_de_recordatorios.py` (nuevo, ~120; `ports.py` queda como está):

- `PortRepositorioRecordatoriosDeTurno`: `agregar` (puede levantar `RecordatorioDeTurnoDuplicado`),
  `guardar`, `de_turnos(ids)`, `pendientes(hasta)` (filas con `resultado IS NULL` y
  `proximo_intento_en ≤ hasta`).
- `PortTurnosPorRecordar.abiertos_con_inicio_entre(desde, hasta) -> list[Turno]` (lo implementa el
  repositorio de turnos; sobre `ix_turno_empresa_franja`).
- `PortAgendaDeNotificacion.anticipaciones() -> tuple[int, ...]` (minutos; vacía si la agenda no rige).
- `PortEnvioDeRecordatorioDeTurno` en dos tiempos, como `PortEnvioDeRecordatorio` de payments:
  `preparar(turno, anticipacion_min) -> RecordatorioListo | SinTelefono` (lee contacto, servicio y
  plantilla; corre dentro del savepoint de la reserva) y `mandar(listo) -> ResultadoDeRecordatorio
  (enviado, falla, transitoria)` (solo habla con el canal; **nunca levanta**). `RecordatorioListo`
  deja teléfono y texto fuera del `repr`.
- `PortAislamiento` y `PortTransaccion` **se importan de `shared/`** (D-U8-11).

**Caso de uso** — `scheduling/application/recordatorios.py` (nuevo, ~300) y
`scheduling/application/envio_de_recordatorios.py` (nuevo, ~200; los tres tiempos):

`EnviarRecordatoriosDeTurno.ejecutar(*, empresa_id, ahora) -> ResultadoDeBarrido(enviados, fallidos,
en_reintento, omitidos, descartados)`. El `ahora` decide *qué* le toca a la corrida; toda fecha que se
**escribe** sale del reloj real (S2 de U7).

1. **Pasada 1 — pendientes vencidos** (`pendientes(reloj)`): una fila **en curso** cuya ventana venció
   → `FALLIDO` `INCIERTO`, **sin reenviar** (pudo haber salido). Una fila **esperando reintento**: si el
   turno ya no está abierto, cambió de franja o el reloj alcanzó `I` → `DESCARTADO`; si no, tres tiempos
   sobre **la misma fila** (`UPDATE`, nunca `INSERT`).
2. **Pasada 2 — nuevos**: turnos abiertos con inicio en `(ahora, ahora + máxima anticipación]`, menos
   los tocados en la pasada 1 (un recordatorio por turno por barrido) → `que_corresponde` → filas
   `OMITIDO` para las superadas → tres tiempos para la elegida.

**Los tres tiempos por ítem (D-U8-10):**

1. **Reservar**: en `aislamiento.aislar()`: `preparar` → `INSERT` (o `UPDATE` del reintento) con
   `iniciar_intento(reloj)` → `transaccion.confirmar()`. `RecordatorioDeTurnoDuplicado` = otro barrido
   llegó primero → se sigue con el siguiente. `SinTelefono` → la fila nace `OMITIDO` y no se manda.
2. **Mandar**: se relee el turno (si se canceló o se movió mientras tanto, se registra `DESCARTADO` sin
   mandar) y `envio.mandar(listo)`. **Sin escrituras sin confirmar ni locks** durante la llamada a Meta:
   la transacción abierta es la vacía que deja `confirmar()` al volver a declarar la empresa (N1 de U7).
   `NotificarAlCliente` guarda el mensaje `SISTEMA` **después** de la respuesta de Meta, en su savepoint.
3. **Registrar**: en `aislar()`: `marcar_enviado` / `registrar_falla(transitoria=...)` (reintento si
   quedan intentos y la espera cae antes de `I`; si no, `FALLIDO` o `DESCARTADO`) / `fallar` → evento
   de bitácora `enviar_recordatorio_de_turno` (iniciador Sistema, `usuario_id=None`, sin datos
   personales) → `confirmar()`. Esta confirmación es la que hace visible el mensaje `SISTEMA` para los
   callbacks.

`DespachoNoPersistido` en cualquiera de los tiempos: se loguea la clase y se sigue con el siguiente
ítem; solo se deshace ese ítem. Ventanas de caída: iguales a las de `reintentos.py` (la fila en curso
se resuelve `INCIERTO` al vencer su ventana; nunca un duplicado).

**Reintento (D-U8-8)** — constantes en el dominio de scheduling: `REINTENTOS_MAXIMOS = 3`,
`ESPERA_BASE = 15 min` (esperas de 15 y 30), `VENTANA_DE_ENVIO = 30 min`. Transitoria solo si el canal
lo dice (`MensajeriaSaturada`). Incierto, permanente (incluido 131047) o error propio → `FALLIDO`.

**Cambio en conversational (P1)** — `ResultadoDeNotificacion` gana `transitoria: bool = False`, que
`NotificarAlCliente` llena con `isinstance(fallo, MensajeriaSaturada)` (el mismo criterio que
`api/fallas_de_canal._traducir`); `ResultadoLocal` de scheduling gana el mismo campo y
`CanalDeAvisosViaConversacion` lo copia. Los avisos de turno de U7 lo ignoran (no se reintentan, D6 de U7).

**Errores** — `RecordatorioDeTurnoDuplicado` en `scheduling/application/errors.py` (82 líneas).

**Regla de agenda malformada (hallazgo de la revisión del tramo 1).** `interpretada_como_agenda()`
levanta `EntradaInvalida` si la fila guardada está mal formada. El barrido (tramos 2 y 3) debe
atraparla **por empresa**: registrar un log (`recordatorios_de_turno_agenda_invalida`, solo con
`empresa_id` y `regla_id`, sin datos personales) y saltear esa empresa, de modo que una fila
corrupta nunca aborte el barrido completo ni se convierta en un 422 desde un worker.

### D-U8-6 · Adaptadores y raíz de composición

- `scheduling/infrastructure/recordatorio_por_whatsapp.py` (nuevo, ~150): `RecordatorioPorWhatsApp`
  implementa `PortEnvioDeRecordatorioDeTurno` reusando de `avisos.py` `CanalDeAvisos`,
  `PlantillasAprobadas`, `variables_de_aviso` y `_dia`/`_hora` (se publican si hace falta). Código
  `recordatorio_de_turno`; plantilla aprobada o texto de fábrica (U6). `avisos.py` no crece.
- `scheduling/infrastructure/repositorio_de_recordatorios.py` (nuevo, ~150) y el modelo
  `RecordatorioDeTurnoModel` en `models.py` (150 → ~185). `abiertos_con_inicio_entre` en
  `repositories.py` (325 → ~345). Función `empresas_con_turnos_por_recordar(sesion, hasta)` en el
  repositorio nuevo.
- `scheduling/infrastructure/agenda_de_notificacion.py` (nuevo, ~50): `AgendaViaConfiguracion` sobre
  `ConsultarAgendaDeNotificacion` (arista `business_config → scheduling` del Context Map; mismo patrón
  que `payments/infrastructure/cadena.py`).
- `api/recordatorios_de_turno.py` (nuevo, ~110): arma el caso de uso para una unidad de trabajo — el
  catálogo con **`rol=RolUsuario.OPERADOR`** (D-U8-12, como `api/conversacional.py:150`), el directorio,
  `armar_canal_de_avisos` + `armar_plantillas_aprobadas`, `AislamientoConSavepoint` y
  `ConfirmacionDeLaUnidad` (ver Pregunta abierta 2 sobre dónde viven).
- `workers/tasks_scheduling.py` (nuevo, ~130), con la forma de `tasks_payments.py`:
  - `scheduling.recordar_turnos` (fan-out) por `empresas_con_turnos_por_recordar(hasta = ahora + 168 h)`.
  - `scheduling.recordar_empresa`: abre la unidad de trabajo, `canal = await armar_mensajeria(...)`;
    **si el canal es `SinCanal` → log `recordatorios_de_turno_sin_canal` y sale** (D-U8-13); si no,
    `EnviarRecordatoriosDeTurno`. Cola **`notifications`**, sin `autoretry_for` (la corrida siguiente
    reevalúa por estado, no por cursor). Registro en `workers/main.py`.
- **Beat (D-U8-16)**: entrada `recordar-turnos` cada `RECORDATORIO_DE_TURNO_MINUTOS` (default 15,
  `max(…, 1)` como `whatsapp_sondeo_minutos`), cola `notifications`.

### D-U8-11 en detalle · Extracción a `shared/` (~120 líneas movidas)

| Pieza | Hoy (U7) | Va a |
|---|---|---|
| `PortAislamiento`, `PortTransaccion` | `payments/application/ports_envio.py:55-92` | `shared/transaccion.py` |
| `DespachoNoPersistido` | `payments/application/errors.py:92` | `shared/transaccion.py` (`payments` lo reexporta: sin cambios en sus llamadores) |
| `ConfirmacionDeLaUnidad` + `AislamientoConSavepoint` | `payments/infrastructure/transaccion.py` y `aislamiento.py` | `platform/` (juntos; aprobado 08/10) |

Los orquestadores quedan por contexto (`payments/application/reintentos.py` y el nuevo de scheduling).
Los tests de payments no cambian salvo imports y tienen que seguir verdes.

### D-U8-7 · Frontend

**PAN-CFG-RN (editor de la regla, tramo 1):**

- `features/business_config/api/agenda.ts` (nuevo): tipos, `agendaDe(reglas)` (como `horarioDe`) y
  `configurarAgenda(recordatorios, prioridad)` contra el BFF.
- `features/business_config/components/AgendaDeNotificacion.tsx` (nuevo): hasta 3 filas «N horas antes
  del turno», agregar/quitar, mensaje de validación, «Rige la de por defecto: 24 h antes» sin regla,
  solo Administrador edita.
- `features/business_config/index.ts` exporta componente y tipos (R5).
- `app/(panel)/configuracion/reglas/page.tsx` lo compone **debajo** de `ReglasDeNegocio` (mismo
  `GET /reglas`). BFF `app/api/reglas/agenda/route.ts` (`PUT`).

**PAN-CFG-NOT · Plantillas (advertencia, tramo 3, D-U8-18):**

- `features/conversational/components/AdvertenciaDeRecordatorio.tsx` (nuevo; `PlantillasDeNotificacion.tsx`
  ya tiene 393 líneas): si `recordatorio_de_turno` no está aprobada en Meta (el estado que el listado ya
  trae desde U6), avisa que los recordatorios no llegan a clientes fuera de la ventana de 24 h. Se
  compone en `app/(panel)/configuracion/plantillas/page.tsx`.

## Infraestructura

### Migración 0039 (`0039_recordatorio_de_turno.py`, `down_revision = "0038"`)

1. **`turno.franja_asignada_en timestamptz`**: agregar nula → `UPDATE turno SET franja_asignada_en =
   created_at` → `SET NOT NULL`.
2. **Tabla `recordatorio_de_turno`**: `id uuid PK`, `empresa_id uuid NOT NULL` (FK a empresa),
   `turno_id uuid NOT NULL REFERENCES turno ON DELETE CASCADE`, `anticipacion_min integer NOT NULL
   CHECK (60..10080)`, `franja_inicio timestamptz NOT NULL`, `resultado varchar(12) NULL CHECK (IN
   ('ENVIADO','FALLIDO','OMITIDO','DESCARTADO'))`, `intentos integer NOT NULL DEFAULT 0 CHECK (>= 0)`,
   `proximo_intento_en timestamptz NULL`, `ultimo_error varchar(60) NULL`, `procesado_en timestamptz
   NULL`, `created_at timestamptz NOT NULL`.
3. **RLS**: `ENABLE` + `FORCE`, política por `empresa_id = current_setting('app.current_empresa')`
   igual que `turno`; `GRANT SELECT, INSERT, UPDATE` a `cheatsheet_app` (sin `DELETE`: la fila es la
   prueba de idempotencia).
4. **Índices**:
   - `uq_recordatorio_de_turno (turno_id, anticipacion_min, franja_inicio)` único — la idempotencia;
     también sirve a `de_turnos(ids)`.
   - `ix_recordatorio_de_turno_pendiente (proximo_intento_en) WHERE resultado IS NULL` — **parcial**:
     solo las filas en curso o esperando reintento (un puñado), que es lo que leen la pasada 1 y la
     función de fan-out. Las `ENVIADO`/`FALLIDO`/`OMITIDO`/`DESCARTADO` no entran.
   - `ix_turno_abierto_inicio ON turno (franja_inicio) WHERE estado IN ('RESERVADO','CONFIRMADO')` —
     **parcial**, para que el fan-out entre empresas no recorra toda la tabla `turno`.
5. **`empresas_con_turnos_por_recordar(hasta timestamptz)`** `SECURITY DEFINER`, `SET search_path =
   public`, `STABLE`: `empresa_id` de turnos abiertos con `franja_inicio` en `(now(), hasta]` **unión**
   empresas con filas `resultado IS NULL`. Solo ids. `REVOKE ALL … FROM PUBLIC`, `GRANT EXECUTE … TO
   cheatsheet_app`.
6. **Reversible**: `downgrade` quita función, índices, tabla y columna.

**Retención de `OMITIDO`/`DESCARTADO` (D-U8-17).** Se conservan mientras exista el turno (`ON DELETE
CASCADE`) y no hay purga en esta unidad: borrar una fila `OMITIDO` haría que el barrido siguiente la
recreara y **mandara** ese recordatorio. El volumen está acotado por diseño (a lo sumo 3 filas por
turno y franja) y ninguna consulta del barrido las recorre: las lee solo por la clave única. Una purga
futura, si hiciera falta, solo podría tocar filas con `franja_inicio < now()`.

### Trabajo asíncrono, configuración e integraciones

- Asíncrono: D-U8-6.
- Configuración: `RECORDATORIO_DE_TURNO_MINUTOS` (default 15) en `platform/settings.py` y
  `backend/.env.example`. `render.yaml` no cambia (rige el default).
- Integraciones externas: **ninguna nueva**; el canal de U5–U7 (timeouts, reintentos internos y
  clasificación de fallas).

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero → No aplica.
- [ ] Comprobantes / CAE → No aplica.
- [ ] Consume un webhook → No aplica directamente (el estado de entrega es de U7); sí la carrera
      callback/commit, que el envío en tres tiempos reduce (caso 33).
- [x] Datos con `empresa_id` → tabla nueva con RLS: aislamiento; el barrido de A no lee turnos de B.
- [ ] Salida de un LLM → No aplica.
- [x] Datos personales → ningún log con nombre, teléfono ni texto; `repr` sin teléfono.
- [x] Idempotencia de un barrido → dos corridas solapadas = un mensaje por (turno, anticipación, franja).
- [x] Zona horaria → borde de día en hora de Argentina vs UTC.
- [x] G5 → la llamada a Meta corre sin escrituras sin confirmar ni locks.

## Tramos (3 PR encadenados, ~2.600–3.000 líneas)

| Tramo | Rama | Contenido | Tamaño | Depende de |
|---|---|---|---|---|
| **1 · Regla de agenda** | `feature/scheduling-recordatorio-de-turno` (esta) | Este plan; D-U8-1 (dominio, `agenda.py`, `PUT /reglas/agenda`); frontend PAN-CFG-RN y su BFF; tests | ~700–900 | `develop`. **Puede salir antes que U7** |
| **2 · Modelo de scheduling** | `feature/scheduling-recordatorio-de-turno-modelo` | Migración 0039; `franja_asignada_en` en dominio, modelo y `reprogramar(…, ahora)`; `domain/recordatorio_de_turno.py`; `ports_de_recordatorios.py`; repositorio y modelo nuevos; `abiertos_con_inicio_entre`; tests de dominio, migración y RLS | ~900–1.000 | Tramo 1. Su migración revisa `0038`: **se mergea después de U7** |
| **3 · Barrido y envío** | `feature/scheduling-recordatorio-de-turno-barrido` | Extracción a `shared/`; `transitoria` en conversational; caso de uso en tres tiempos; adaptadores; `api/recordatorios_de_turno.py`; worker, Beat, settings; advertencia PAN-CFG-NOT; tests de caso de uso e integración; pendientes #7 y #11 | ~1.100 | Tramo 2 y **U7 mergeada** |

**Orden de merge del épico:** U6 → U7 (i, ii, iii) → U8 (1 → 2 → 3). El tramo 1 puede adelantarse a U7.

**Decisión (Luciano, 2026-10-08): el tramo 2 va apilado sobre la pila de U7.** La migración 0039
encadena después de la 0038, que solo existe en `feature/conversational-entregas-de-whatsapp-avisos`
(U6 + U7 i/ii/iii, migraciones 0036 a 0038). Por eso `feature/scheduling-recordatorio-de-turno-modelo`
incorpora esa rama con un merge (`--no-ff`), igual que U7 se apiló sobre U6. **El PR del tramo 2 se
abre después de que U6 y U7 estén mergeadas en `develop`** (orden U6 → U7 → U8); si U7 cambia su
numeración antes de entrar, se re-encadena la 0039 (D-U8-15).
ADR-0014 no bloquea.

## Archivos a tocar

Tramo 1
- [x] `backend/src/cheatsheet/contexts/business_config/domain/agenda_de_notificacion.py` (nuevo) · `domain/regla.py` (`interpretada_como_agenda`)
- [x] `backend/src/cheatsheet/contexts/business_config/application/agenda.py` (nuevo)
- [x] `backend/src/cheatsheet/api/routers/reglas.py` (`PUT /reglas/agenda`) y el armado del caso de uso donde se arma el de atención
- [x] `backend/tests/contexts/business_config/domain/test_agenda_de_notificacion.py` · `…/application/test_agenda.py` · `backend/tests/integracion/test_agenda_de_notificacion_postgres.py` (en vez de `tests/api/`: es la convención de los demás tests de API de reglas)
- [x] `frontend/src/features/business_config/api/agenda.ts` · `components/AgendaDeNotificacion.tsx` · `index.ts` y sus tests
- [x] `frontend/src/app/(panel)/configuracion/reglas/page.tsx` · `frontend/src/app/api/reglas/agenda/route.ts`
- [ ] `docs/aidlc/units.md` (sin cambios: la unidad ya figura «en curso»)

Tramo 2
- [x] `backend/migrations/versions/0039_recordatorio_de_turno.py`
- [x] `backend/src/cheatsheet/contexts/scheduling/domain/turno.py` · `domain/recordatorio_de_turno.py` (nuevo)
- [x] `backend/src/cheatsheet/contexts/scheduling/application/ports_de_recordatorios.py` (nuevo) · `application/errors.py` · `application/turnos.py` (la llamada a `reprogramar` y `franja_asignada_en` al reservar)
- [x] `backend/src/cheatsheet/contexts/scheduling/infrastructure/models.py` · `repositories.py` · `repositorio_de_recordatorios.py` (nuevo)
- [x] `backend/tests/contexts/scheduling/domain/test_recordatorio_de_turno.py` · `test_turno.py` · `backend/tests/integracion/test_migracion_0039.py` · `test_recordatorios_de_turno_postgres.py` · `tests/integracion/conftest.py` (`BORRADOS`)

Tramo 3
- [ ] `backend/src/cheatsheet/shared/transaccion.py` (nuevo) · `payments/application/ports_envio.py` · `payments/application/errors.py` · `payments/infrastructure/transaccion.py` · `workers/tasks_payments.py` (imports)
- [ ] `backend/src/cheatsheet/contexts/conversational/application/notificaciones.py` (`transitoria`) · `api/avisos_de_turno.py` · `scheduling/infrastructure/avisos.py` (`ResultadoLocal.transitoria`)
- [ ] `backend/src/cheatsheet/contexts/scheduling/application/recordatorios.py` · `envio_de_recordatorios.py` (nuevos)
- [ ] `backend/src/cheatsheet/contexts/scheduling/infrastructure/recordatorio_por_whatsapp.py` · `agenda_de_notificacion.py` (nuevos) · `ensamblado.py`
- [ ] `backend/src/cheatsheet/api/recordatorios_de_turno.py` (nuevo)
- [ ] `backend/src/cheatsheet/workers/tasks_scheduling.py` (nuevo) · `workers/beat.py` · `workers/main.py`
- [ ] `backend/src/cheatsheet/platform/settings.py` · `backend/.env.example`
- [ ] `backend/tests/contexts/scheduling/application/test_recordatorios.py` · `test_envio_de_recordatorios.py` · `…/infrastructure/test_recordatorio_por_whatsapp.py` · `backend/tests/contexts/conversational/application/test_notificaciones.py` · `backend/tests/workers/test_recordar_turnos.py` · `test_beat.py` · `backend/tests/integracion/test_barrido_de_turnos_postgres.py`
- [ ] `frontend/src/features/conversational/components/AdvertenciaDeRecordatorio.tsx` y su test · `frontend/src/app/(panel)/configuracion/plantillas/page.tsx`
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#7) · `docs/aidlc/epicas/07-agenda-y-recursos/pendientes.md` (#11) · `docs/aidlc/TODO.md` §22 · `docs/aidlc/units.md`

## Casos de prueba

| # | Caso | Tipo | Tramo | Estado |
|---|---|---|---|---|
| 1 | **RED** — Un turno que empieza en 23 h, con la regla por defecto, no recibe nada tras el barrido (hoy no existe). GREEN: un recordatorio con la plantilla `recordatorio_de_turno`, fila `ENVIADO` | caso de uso | 3 | pendiente |
| 2 | **RED** — `interpretada_como_agenda()` no existe. GREEN: devuelve la configuración tipada | unit | 1 | hecho |
| 3 | Configuración: 0 recordatorios, 4, horas 0 o 169, repetidos → `EntradaInvalida` con la frase; se ordenan de mayor a menor | unit (tabla) | 1 | hecho |
| 4 | Fila mal formada en la base → falla al leer (D24) | unit | 1 | hecho |
| 5 | `PUT /reglas/agenda`: Administrador guarda y reemplaza; Operador → rechazo; bitácora | integración (API) | 1 | escrito (corre en la CI) |
| 6 | `ConsultarAgendaDeNotificacion`: sin regla → 24 h y `configurada=False`; regla desactivada → agenda vacía (recordatorios apagados) | unit | 1 | hecho |
| 7 | Dos reglas de agenda → gana la de mayor prioridad (RN-05) | unit | 1 | hecho |
| 8 | PAN-CFG-RN: agrega hasta 3, valida con la frase, muestra el default, solo Administrador edita | unit (Vitest) | 1 | hecho |
| 9 | `que_corresponde`: con 48 h y 24 h y el worker caído hasta faltar 20 h → solo la de 24 h; la de 48 h `OMITIDO` | unit | 2 | hecho |
| 10 | Turno reservado 3 h antes con regla de 24 h → no se recuerda (`M < F`) | unit | 2 | hecho |
| 11 | Turno confirmado dentro de la ventana → **sí** se recuerda | unit | 2 | hecho |
| 12 | Zona: 15/10/2026 10:00 AR (`13:00Z`) corresponde desde el 14/10 `13:00Z`; turno a las 00:30 AR muestra la fecha argentina | unit | 2/3 | hecho |
| 13 | Entidad: `registrar_falla` transitoria espera 15 y 30 min; la tercera agota → `FALLIDO`; espera que cae después de `I` → `DESCARTADO` | unit | 2 | hecho |
| 14 | Migración 0039: backfill `franja_asignada_en = created_at`, `NOT NULL`, upgrade/downgrade limpios | migración (CI) | 2 | escrito (corre en la CI) |
| 15 | RLS: la tabla aísla por `empresa_id`; sin empresa declarada no se ve nada | integración (CI) | 2 | escrito (corre en la CI) |
| 16 | `empresas_con_turnos_por_recordar`: solo ids, respeta `hasta`, incluye empresas con filas pendientes, excluye turnos cerrados | migración (CI) | 2 | escrito (corre en la CI) |
| 17 | Índice único: un segundo `INSERT` de la misma clave → `RecordatorioDeTurnoDuplicado` | integración (CI) | 2 | escrito (corre en la CI) |
| 18 | Reprogramado → recordatorio nuevo para la franja nueva; pendiente de la vieja → `DESCARTADO` | caso de uso | 3 | pendiente |
| 19 | Cancelado → nunca; cancelado con reintento pendiente → `DESCARTADO`; cancelado entre reservar y mandar → `DESCARTADO` sin llamar al canal | caso de uso | 3 | pendiente |
| 20 | A posteriori, completado o no-show → nunca; turno ya empezado → no se manda | caso de uso | 3 | pendiente |
| 21 | Cliente sin teléfono → `OMITIDO` `SIN_TELEFONO`, ningún envío, no se reevalúa | caso de uso | 3 | pendiente |
| 22 | Falla transitoria → reintento a los 15 y 30 min sobre la misma fila; agotado → `FALLIDO` | caso de uso | 3 | pendiente |
| 23 | Incierto (timeout de lectura) y permanente (131047) → `FALLIDO` sin reintento | caso de uso | 3 | pendiente |
| 24 | Fila en curso con ventana vencida (caída entre tiempos) → `FALLIDO` `INCIERTO`, **nunca** se reenvía | caso de uso | 3 | pendiente |
| 25 | Tres tiempos: el canal falso registra que, al llamarlo, no hay escrituras sin confirmar (la fila ya está confirmada y visible desde otra sesión) | integración (CI) | 3 | pendiente |
| 26 | `DespachoNoPersistido` en un turno no voltea los demás del barrido | caso de uso | 3 | pendiente |
| 27 | Empresa con `SinCanal` → la raíz sale con `recordatorios_de_turno_sin_canal`, ninguna fila | unit (raíz) | 3 | pendiente |
| 28 | `NotificarAlCliente`: `MensajeriaSaturada` → `transitoria=True`; `EnvioIncierto`, `MensajeRechazado` → `False`; el adaptador de scheduling lo propaga | unit | 3 | pendiente |
| 29 | El recordatorio queda como mensaje `SISTEMA` en el hilo del cliente y un callback posterior al commit lo encuentra por `wamid` | integración (CI) | 3 | pendiente |
| 30 | **Dos barridos solapados** de la misma empresa sobre PostgreSQL (dos sesiones concurrentes) → un solo envío y una sola fila por (turno, anticipación, franja) | integración (CI) | 3 | pendiente |
| 31 | Beat: `recordar-turnos` en `notifications` con el intervalo de configuración | unit | 3 | pendiente |
| 32 | Ningún log del barrido contiene nombre, teléfono ni texto | unit (captura de logs) | 3 | pendiente |
| 33 | Extracción a `shared/`: la suite de payments (recordatorios, reintentos, integración) pasa sin cambios de comportamiento | regresión | 3 | pendiente |
| 34 | PAN-CFG-NOT: la advertencia aparece si `recordatorio_de_turno` no está aprobada y no aparece si lo está | unit (Vitest) | 3 | pendiente |
| 35 | `guard_architecture --scan` (R1–R5) y `test_guards.sh` pasan | gate | 1/2/3 | tramo 1: scan verde; `test_guards.sh` falla igual en la base (27/54, entorno Windows) |
| 36 | Una empresa con la regla de agenda malformada (`interpretada_como_agenda()` levanta `EntradaInvalida`) se saltea con el log `recordatorios_de_turno_agenda_invalida`; las demás empresas del mismo barrido se procesan y el barrido no levanta | caso de uso | 3 | pendiente |

Gates: `ruff format --check . && ruff check . && mypy . && pytest` y, en frontend, `npm run format:check
&& npm run lint && npm run typecheck && npm run test:coverage`. Los casos 14–17, 25, 29 y 30 corren con
PostgreSQL en la CI.

## Verificaciones no posibles sin la app de prueba → `TODO.md` §22

| # | Qué verificar | Qué pasa si difiere |
|---|---|---|
| 22.65 (provisorio; se renumera al mergear después de U7) | Punta a punta en staging con `meta`: un turno a 24 h recibe la plantilla aprobada `recordatorio_de_turno` y el callback la marca entregada en el hilo | Se ajusta según las verificaciones de U5/U6; el barrido no cambia |

## Riesgos

- **131047 sin plantilla aprobada (D-U8-18).** Fuera de la ventana de 24 h Meta solo acepta
  plantillas: si `recordatorio_de_turno` no está aprobada, el recordatorio queda `FALLIDO` (permanente,
  sin reintento) para casi todos los clientes, porque un recordatorio de 24 h casi nunca cae dentro de
  la ventana. Mitigación: advertencia en PAN-CFG-NOT y nota explícita en el PR.
- **G5 no lo resuelve el ADR-0014.** U8 no lo agrava: la llamada a Meta corre sin escrituras sin
  confirmar ni locks (D-U8-10). Queda la **ventana residual** de §22.60 (milisegundos entre la respuesta
  de Meta y el commit del tiempo 3, en los que un callback no encuentra el `wamid`); es la misma que la
  de los recordatorios de cobro y se mide con la app de prueba.
- **Encadenamiento de migraciones.** 0039 revisa 0038; si U7 cambia su numeración antes de mergear, se
  re-encadena (D-U8-15).

## Avisos al equipo

- **Paula** (reglas de negocio, HU-E11-01; manual `manual/60-cobros.md`): PAN-CFG-RN gana el editor de
  agenda y `GET /reglas` devuelve reglas `AGENDA_DE_NOTIFICACION`. Revisar `domain/agenda_de_notificacion.py`,
  `application/agenda.py`, `api/routers/reglas.py` y la pantalla; reflejar el editor en el manual y la matriz.
- **Emanuel** (agenda, HU-E7-01 … HU-E7-06; manual `manual/70-agenda.md`): `turno` gana
  `franja_asignada_en`, `Turno.reprogramar` recibe el momento, hay tabla `recordatorio_de_turno` y un
  barrido cada 15 min. Revisar `domain/turno.py`, `domain/recordatorio_de_turno.py`,
  `application/recordatorios.py` y la migración; contemplar en sus pruebas que reprogramar recalcula y
  cancelar anula.
- **Quien revise payments**: el tramo 3 mueve a `shared/` los dos puertos, `DespachoNoPersistido` y
  `ConfirmacionDeLaUnidad`; solo cambian imports.
- **Equipo** (M6): HU-E8-04 cierra entera recién con esta unidad.
- **Dueño de la cuenta de Meta (acción previa al tramo 3 en staging):** la plantilla
  `recordatorio_de_turno` tiene que estar **aprobada** en Meta.

## Preguntas abiertas para el Gate 1 (resueltas el 08/10)

1. **Regla de agenda desactivada.** → **Aprobado: los recordatorios se APAGAN** (sin vuelta silenciosa
   al default de 24 h). Desactivar la regla es una decisión explícita del negocio de no avisar, y cada
   mensaje de plantilla de Meta tiene costo. Sin regla configurada sigue rigiendo el default de 24 h
   (`configurada=False`); con regla desactivada, `ConsultarAgendaDeNotificacion` devuelve una agenda
   vacía.
2. **Dónde viven las piezas compartidas del envío en tres tiempos.** → **Aprobado:** los dos `Protocol`
   (`PortAislamiento`, `PortTransaccion`) y el tipo de error (`DespachoNoPersistido`) van a `shared/`
   (sin framework, R4); `ConfirmacionDeLaUnidad` y `AislamientoConSavepoint` van **juntos** a
   `platform/` (que ya es dueño de la sesión de base de datos), de modo que ningún contexto los
   duplica y R3/R4 se cumplen. **Ajusta D-U8-11**, que tal como se aprobó no podía cumplirse.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | Aprobado por Luciano con las recomendaciones de las preguntas 1–4 |
| 1 · Plan (re-presentación) | 2026-10-08 | **Aprobado por Luciano el 08/10.** Revalidación contra U6 y U7 del 07/10; once decisiones (D-U8-8 a D-U8-18) y las dos preguntas abiertas resueltas (ver «Decisiones tomadas durante la unidad») |
| 1 · Revisión del tramo 1 | 2026-10-08 | Correcciones aprobadas por Luciano: prioridad negativa al actualizar la agenda (422), nombre accesible de cada «Quitar», casos de PostgreSQL para prioridad, reactivación y 422, y la nota del caso 36 para el barrido |
| 2 · Verificación del tramo 1 | 2026-10-08 | **Aprobado por Luciano el 08/10.** El tramo 2 se apila en `feature/scheduling-recordatorio-de-turno-modelo` |
| 3 · PR | | |

## Progreso

**Tramo 1 · Regla de agenda (implementado, sin push).**

- Backend: `domain/agenda_de_notificacion.py`, `interpretada_como_agenda()` en `regla.py`,
  `application/agenda.py` (`ConfigurarAgendaDeNotificacion`, `ConsultarAgendaDeNotificacion`,
  `AgendaVigente`) y `PUT /reglas/agenda`. Regla desactivada = agenda vacía (recordatorios apagados);
  sin ninguna regla = 24 h con `configurada=False`.
- Frontend: `api/agenda.ts`, `AgendaDeNotificacion.tsx`, BFF `app/api/reglas/agenda/route.ts`,
  compuesto debajo de `ReglasDeNegocio` en PAN-CFG-RN.
- Desvíos del plan: las rutas `horario-de-atencion` y `agenda` se movieron a un segundo router
  (`_rutas_de_reglas_tipadas`) porque `_rutas` superaba la complejidad 10; el test de API vive en
  `tests/integracion/` (como el del horario) y no en `tests/api/`. `units.md` no cambia.

**Correcciones de la revisión del tramo 1 (08/10).**

- `ReglaDeNegocio.cambiar_prioridad` valida con la misma regla que la construcción;
  `ConfigurarAgendaDeNotificacion` la usa al actualizar, antes de tocar la regla, así que `PUT
  /reglas/agenda` con prioridad negativa responde 422 también sobre una regla existente (antes, 500).
  El mismo defecto en `atencion.py` y en escalamiento queda registrado en `TODO.md` §25.
- Cada botón «Quitar» de la agenda tiene `aria-label` «Quitar recordatorio N».
- Tres casos nuevos en `test_agenda_de_notificacion_postgres.py` (se saltean sin base, corren en la CI).
- Caso 36 y la nota de D-U8-5 sobre la regla malformada, para los tramos 2 y 3.

**Gate 2 del tramo 1 (08/10).** Aprobado por Luciano. Se abre el tramo 2 sobre `ab4cd5d`.

**Tramo 2 · Modelo de scheduling (implementado, sin push).**

- Base: merge de la pila de U7 (`origin/feature/conversational-entregas-de-whatsapp-avisos`) en la rama
  del tramo; sin conflictos. Suite verde tras el merge, antes de escribir código del tramo.
- Migración `0039_recordatorio_de_turno.py` (`down_revision = "0038"`): `turno.franja_asignada_en`
  con backfill `created_at` y `NOT NULL`; tabla `recordatorio_de_turno` con RLS forzada, sin `DELETE`
  para la app, índice único `uq_recordatorio_de_turno` y los parciales `ix_recordatorio_de_turno_pendiente`
  e `ix_turno_abierto_inicio`; función `SECURITY DEFINER` `empresas_con_turnos_por_recordar(hasta)`.
- Dominio: `Turno.franja_asignada_en` (se fija al reservar, en la carga a posteriori y en
  `reprogramar(franja, intervalo, ahora)`); `domain/recordatorio_de_turno.py` con la entidad, las
  constantes del reintento y la función pura `que_corresponde`.
- Aplicación: `ports_de_recordatorios.py` (cuatro puertos y `RecordatorioListo`, `SinTelefono`,
  `ResultadoDelEnvio`) y `RecordatorioDeTurnoDuplicado`.
- Infraestructura: `RecordatorioDeTurnoORM`, `repositorio_de_recordatorios.py` (con
  `empresas_con_turnos_por_recordar`), `abiertos_con_inicio_entre` en el repositorio de turnos.
- Pruebas: dominio y aplicación (casos 9 a 13) pasan; `test_migracion_0039.py` y
  `test_recordatorios_de_turno_postgres.py` (casos 14 a 17 y el aislamiento) se saltean sin base y
  corren en la CI. La tabla se agregó a `BORRADOS`.
- Desvíos del plan: el resultado del canal se llama `ResultadoDelEnvio` (el nombre
  `ResultadoDeRecordatorio` es el enum de la columna); los modelos se llaman `...ORM` como los demás de
  scheduling; `PortTurnosPorRecordar` suma `buscar_por_id`, que el barrido necesita para releer el turno.

## Decisiones tomadas durante la unidad

- Gate 1 (2026-10-04): Pregunta 1 → hasta 3 recordatorios por turno, cada uno en horas antes (1 a 168).
- Gate 1 (2026-10-04): Pregunta 2 → sin regla configurada rige un recordatorio por defecto 24 h antes.
- Gate 1 (2026-10-04): Pregunta 3 → se omite el recordatorio si el turno se reservó o se movió cuando su momento ya había pasado.
- Gate 1 (2026-10-04): Pregunta 4 → sin horario de silencio en esta unidad.
- Tramo 2 (2026-10-08): Luciano decidió apilar el tramo 2 sobre la pila de U7 (merge de la rama de U7 en la rama del tramo); su PR se abre después de U6 y U7 (orden U6 → U7 → U8).
- Revalidación (2026-10-08): las once decisiones del informe del 07/10 aprobadas tal como se recomendaron → D-U8-8 a D-U8-18.
- Gate 1 (2026-10-08): Pregunta abierta 1 → regla de agenda desactivada = recordatorios apagados, sin vuelta al default de 24 h (desactivar es una decisión explícita de no avisar y cada mensaje de plantilla cuesta).
- Gate 1 (2026-10-08): Pregunta abierta 2 → `shared/` recibe los dos `Protocol` y el tipo de error (sin framework, R4); `ConfirmacionDeLaUnidad` y `AislamientoConSavepoint` van juntos a `platform/`. Ajusta D-U8-11.
