# Unidad: entregas-de-whatsapp

**HUs**: HU-E8-04 (RN-04, RN-03), HS-T3 (RN-04, RN-05), HU-E6-02 (RN-01), HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04, HU-E9-01 (RN-04)   **Contexto dueño**: conversational (rama `statuses[]` y mensajes del sistema); payments y scheduling por la raíz de composición (ADR-0011)   **Rama**: feature/conversational-entregas-de-whatsapp

> Origen: plan de trabajo de la fase C (fuera del repo), decisiones G4c, G4f y unidad U7. Cierra el
> pendiente **#4** del épico 8 y el **#3** del épico 6 («el estado de entrega nunca se actualiza
> después del envío»). Responsable Luciano; revisa Cristian.
>
> **Depende de:** `canal-real-de-whatsapp` (U5) y `plantillas-de-whatsapp-en-meta` (U6)
> **mergeadas**, y el ADR-0011 aceptado. Interfaces que asume de U5 (revisada) y que se vuelven a
> comprobar apenas llegue a `develop`:
>
> - el canal clasifica cada falla en **transitoria** (5xx, 429, conexión rechazada o timeout de
>   conexión, tras sus 3 intentos con espera), **permanente** (4xx de Meta: 131047, 131026, 132001,
>   401…) o **incierta** (timeout de lectura: Meta pudo haberlo aceptado), y expone el `error.code`;
> - `EnvioPorWhatsApp` y `AvisoPorWhatsApp` nunca levantan;
> - el barrido de cobros procesa cada cobro en su propio savepoint (`begin_nested`).
>
> De U6 asume `ConsultarPlantillaParaEnviar` (devuelve también el `texto` resuelto) y
> `enviar_plantilla`.

## Qué hace

Cada mensaje que CheatSheet manda por WhatsApp pasa a tener su **estado de entrega real**
(enviado → entregado → leído, o fallido con su motivo), leído de los callbacks `statuses[]` de Meta:
los del agente y el operador, los recordatorios de cobro y — nuevo — los **avisos de turno**, que hoy no
quedan guardados en ningún lado y pasan a registrarse como mensaje del sistema en la conversación del
cliente (así también le dan contexto al agente cuando el cliente contesta). Un recordatorio de cobro
que falla por una causa **transitoria** se reintenta en los barridos siguientes, sobre la misma fila,
con un tope; nunca se reintenta un rechazo permanente ni un resultado incierto.

## Lo que existe hoy (relevado el 2026-10-04)

- `api/routers/whatsapp.py:114-118`: una notificación sin `messages` se contesta 200 y se descarta;
  `_mensajes_de` (`:179-208`) ignora `statuses` a propósito («anotado en los pendientes»).
- `conversational/domain/conversacion.py:148-162`: `Mensaje.marcar_entrega` **no retrocede**
  (`ENVIADO 0 < ENTREGADO 1 < LEIDO 2 < FALLIDO 3`). `RepositorioMensajePostgres.buscar_por_externo_id`
  existe (`repositories.py:141-144`). Índice único parcial `uq_mensaje_externo_id (empresa_id,
  externo_id)` (migración 0021).
- `OrigenDelMensaje.SISTEMA` existe (`conversacion.py:115`) y **nadie lo usa** en el backend; el
  frontend ya lo pinta como «Sistema» (`HiloDeConversacion.tsx:52`) y muestra `estado_entrega`
  (`:113-114`).
- `payments/domain/recordatorio.py:66-73`: `Recordatorio.marcar_entrega` acepta **cualquier orden**
  («lo último que el proveedor dijo es lo que vale»). La tabla `recordatorio` no tiene `externo_id`,
  ni `empresa_id` (RLS por el cobro padre, migración 0019 `aislamiento_por_cobro`). Índice único
  `uq_recordatorio_cobro_paso (cobro_id, paso)`.
- `recordatorio.py:80-91`: `proximo_paso` cuenta **los despachados** (`enviado_en` no nulo): una fila
  sin `enviado_en` hace que el paso vuelva a calcularse, y el `INSERT` choca con el índice único →
  `RecordatorioDuplicado` → «ya despachado». **Una fila así hoy traba la cadena de ese cobro para
  siempre.**
- `recordatorios.py:175-190`: inserta la fila, manda, y marca `enviado_en` + estado. Con U5, un
  `FALLIDO` también lleva `enviado_en` (el paso se dio por hecho y la cadena sigue: P6 de U5).
- `PortEnvioDeRecordatorio.enviar(...) -> EstadoEntrega` (`ports.py:303-311`): no devuelve el `wamid`.
- `scheduling`: `Avisador` (`turnos.py:99-169`) arma `DatosDeAviso` **sin `cliente_id`**; el puerto
  `PortNotificadorDeTurnos` no devuelve nada (mejor esfuerzo).
- `conversational/application/agente.py:176-177`: el historial que va al intérprete son los
  `contenido` de **todos** los mensajes del hilo (`del_hilo`), los últimos seis.
- `ResponderComoOperador` (`atencion.py:173-248`) guarda el saliente con `externo_id` y
  `estado_entrega=ENVIADO`; el agente también.

## Contratos — Meta (callback de estado)

Fuente: *messages webhook reference — status*,
https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/status
(consultada el 2026-10-04) y *Webhook overrides*,
https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/override .

| Hecho | Consecuencia |
|---|---|
| `entry[].changes[].value.statuses[]` con `id` (wamid), `status`, `timestamp`, `recipient_id` siempre; `errors[]` «only included if failure to send or deliver message»; `conversation`/`pricing` solo en `sent` y uno de `delivered`/`read`; `biz_opaque_callback_data` si se mandó | Se leen `id`, `status`, `timestamp`, `errors[0].code` y `errors[0].title`. Nada de `recipient_id` se guarda ni se loguea (es un teléfono) |
| `status` ∈ `sent`, `delivered`, `read`, `failed`, `played` | `played` (nota de voz reproducida) se ignora |
| «In some cases… the message is both delivered and read at the same time. In these cases, the 'delivered' webhook is not sent» | `LEIDO` sin `ENTREGADO` previo es legítimo: el orden permite saltar |
| La documentación **no** garantiza orden ni ausencia de duplicados | Idempotencia y piso monotónico obligatorios |
| El campo `messages` (que incluye `statuses`) **sí** admite override por WABA | Los callbacks llegan a `/webhooks/whatsapp/{empresa}` cuando la WABA tiene override, o a `/webhooks/whatsapp` (ruta de la app, U6) si no |
| Códigos en `errors[].code`: 131047 fuera de ventana, 131026 no es usuario de WhatsApp, 131049 «healthy ecosystem», 131050 baja de marketing, 132015/132016 plantilla pausada/deshabilitada ([error codes](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes)) | La pantalla traduce los conocidos y muestra el `title` de Meta para el resto |

Sin verificar → `TODO.md` §25 (al final).

## Diseño

### D-U7-1 · Ruteo de un callback

`api/whatsapp_notificaciones.py` (creado en U6) gana `estados_de(crudo) -> list[EstadoEntrante]`
(defensivo, como `_mensajes_de`). `api/routers/whatsapp.py` ya no sale con 200 cuando no hay
`messages`: procesa también `statuses`.

- **Empresa:** en la ruta por empresa, la de la URL (mismo modelo de confianza que los mensajes
  entrantes), **y** se verifica que `entry[].id` sea la WABA de esa empresa (la consulta
  `empresa_de_la_cuenta_de_whatsapp` de U6); si es de otra, se descarta con log. En la ruta de la app,
  la empresa sale de `entry[].id`.
- **Una transacción por estado** (como `_procesar` por mensaje): si el segundo falla, el primero ya
  quedó.
- **Destinatario por `wamid`, siempre dentro de la empresa:** `api/entregas.py` (nuevo) prueba
  primero `conversational.RegistrarEstadoDeEntrega` (tabla `mensaje`), y si no lo encuentra
  `payments.RegistrarEntregaDeRecordatorio` (tabla `recordatorio`). Bajo RLS, un `wamid` de otra
  empresa simplemente no existe: nunca hay cruce de inquilinos.
- No encontrado en ninguno → log `whatsapp_estado_sin_destinatario` (sin el wamid completo) y 200.
  Caso esperable: el `sent` llega antes de que haga commit la transacción que mandó el mensaje. No se
  pierde nada: ese estado (`ENVIADO`) ya lo escribió el propio envío, y los siguientes
  (`delivered`/`read`) llegan después.
- **Alternativa descartada — `biz_opaque_callback_data`** con «payments:<id>» para rutear sin buscar
  en dos tablas: igual hace falta guardar el `wamid` (idempotencia, la respuesta del envío), es un dato
  más que mantener en tres adaptadores y no aporta nada que dos búsquedas por índice no den.

### D-U7-2 · Orden de los estados (payments) — monotónico, `FALLIDO` terminal

`Recordatorio.marcar_entrega` pasa a la **misma regla que `Mensaje`**: `ENVIADO < ENTREGADO < LEIDO
< FALLIDO`; un estado de rango menor o igual al actual se ignora.

- **Por qué monotónico:** Meta no garantiza el orden; con «lo último que llega vale», un `delivered`
  retrasado pisaría un `read` y PAN-COB-02 diría que el cliente no leyó lo que leyó. El docstring
  actual se apoya en «WhatsApp puede reportar LEIDO sin ENTREGADO» — eso sigue funcionando: el orden
  admite saltos, solo prohíbe retroceder.
- **Por qué `FALLIDO` terminal:** `failed` es el veredicto final de Meta sobre ese `wamid`; después no
  hay entrega posible del mismo mensaje. Y es la regla que `Mensaje` ya tiene, probada y mergeada: dos
  reglas distintas para el mismo flujo de callbacks de Meta, según en qué tabla caiga el `wamid`, es
  la clase de diferencia que nadie recuerda al leer la pantalla.
- El `EstadoEntrega` de payments sigue siendo su propio enum (R3); la tabla de orden se duplica en
  dos líneas, a propósito.

### D-U7-3 · Reintento acotado de fallas transitorias (payments)

**Máquina de estados de una fila de `recordatorio`** (columnas nuevas: `externo_id`, `intentos`,
`proximo_intento_en`, `ultimo_error`):

| Situación | `enviado_en` | `estado_entrega` | `proximo_intento_en` | `intentos` |
|---|---|---|---|---|
| Enviado (Meta aceptó) | momento | `ENVIADO` → callbacks | nulo | n |
| Falla transitoria, quedan intentos | **nulo** | nulo | `ahora + 2^(n-1) h` | n |
| Falla transitoria agotada (n = 3) | momento | `FALLIDO` | nulo | 3 |
| Falla permanente o incierta | momento | `FALLIDO` | nulo | n |
| Cobro cerrado mientras esperaba | nulo | nulo | nulo | n (`ultimo_error = COBRO_CERRADO`) |

- `REINTENTOS_MAXIMOS = 3` intentos en total entre barridos (además de los 3 dentro de cada llamada
  que ya hace el canal). Espera 1 h, 2 h: el barrido es horario, así que un recordatorio caído se
  resuelve en ≈ 3 h o queda `FALLIDO`. Más que eso convierte un «a los 3 días» en «a los 4».
- **Coexistencia con `(cobro_id, paso)`:** el reintento es un **`UPDATE` de la misma fila**, nunca un
  `INSERT`. `DespacharRecordatorios` hace dos pasadas por empresa, cada ítem en su savepoint (U5):
  1. `recordatorios.pendientes_de_reintento(ahora)` (las de `proximo_intento_en <= ahora`, de cobros
     abiertos) → reintenta;
  2. los cobros abiertos **sin** fila pendiente → paso nuevo como hoy.
- **Coexistencia con `proximo_paso`:** sin cambios en su fórmula (cuenta `enviado_en` no nulo). Una
  fila esperando reintento tiene `enviado_en` nulo, así que `proximo_paso` devuelve **su** paso; la
  pasada 2 la excluye explícitamente (`espera_reintento`), y si dos barridos se solapan el índice único
  sigue diciendo «ya existe». Al agotarse o salir, la fila gana `enviado_en` y la cadena avanza como
  siempre (P6 de U5: un `FALLIDO` no detiene la cadena).
- **Nunca se reintenta:** un rechazo permanente (4xx de Meta), un **timeout de lectura** (incierto:
  Meta pudo haberlo aceptado y la Cloud API no tiene clave de idempotencia — un duplicado es peor que
  un recordatorio que falta, ADR-0011 punto 6), ni un `failed` que llega por callback (es asíncrono,
  puede llegar horas después y reordenaría la cadena).
- **Filas trabadas de antes:** la migración pone `proximo_intento_en = now()` a las filas con
  `enviado_en IS NULL AND estado_entrega IS NULL` (las que hoy traban su cadena para siempre); el
  primer barrido las reintenta. En producción no hubo envíos reales, así que no hay riesgo de
  duplicar un mensaje que salió.
- Dominio: `Recordatorio` gana `marcar_enviado(ahora, externo_id)`, `programar_reintento(ahora,
  error)`, `fallar(ahora, error)`, `descartar(motivo)` y la propiedad `espera_reintento`.
- `PortEnvioDeRecordatorio.enviar` devuelve `ResultadoDeEnvio(estado, externo_id, falla:
  ClaseDeFalla | None, codigo: str | None)` — tipo de payments; `EnvioPorWhatsApp` traduce el
  resultado del canal.

### D-U7-4 · Avisos de turno guardados como mensaje del sistema

**Decisión del plan de trabajo:** el aviso se guarda como `Mensaje` saliente, `origen=SISTEMA`, en la
conversación del cliente. Diseño dentro de las reglas del ADR-0011:

- **conversational/application** — caso de uso nuevo `NotificarAlCliente` (en
  `application/notificaciones.py`): entrada `empresa_id, cliente_id, telefono, envio` (plantilla
  aprobada con `nombre/idioma/parametros/texto`, o texto de fábrica), `ahora`; hace
  1. el envío por su `PortMensajeria` (gana `enviar_plantilla`, de U6);
  2. busca `conversaciones.abierta_de(cliente_id)` o crea una `Conversacion` `ACTIVA` nueva (el
     mismo camino que ya usa el agente para un entrante, `agente.py:212-215`);
  3. guarda el `Mensaje(SALIENTE, SISTEMA, contenido=texto, externo_id=wamid, estado_entrega=ENVIADO)`,
     o `FALLIDO` con `motivo_de_falla` (código de Meta) si el envío falló;
  4. devuelve `ResultadoDeNotificacion(enviado, externo_id, falla)`. **Nunca levanta por el canal.**
  5. si el canal es `SinCanal` (empresa sin WhatsApp conectado en producción), **no** crea
     conversación ni mensaje: la empresa no usa el canal y llenarle la bandeja de hilos con avisos
     fallidos sería ruido. Devuelve `falla=SIN_CANAL` y registra el log de siempre.
- **scheduling/infrastructure/avisos.py** — `AvisoPorWhatsApp` deja de recibir el canal crudo y recibe
  un `Protocol` local `CanalDeAvisos.notificar(*, cliente_id, telefono, envio) -> ResultadoLocal`.
  `DatosDeAviso` gana `cliente_id` (es el puerto propio de scheduling; `Avisador._armar` ya lo tiene).
- **Raíz (`api/agenda.py`)** — construye `NotificarAlCliente` con los repositorios de
  `Conversaciones.armar(unidad)` y el canal de `armar_mensajeria`, y se lo pasa al adaptador. Ningún
  import entre contextos: scheduling ve su `Protocol`.
- **Transacción:** el aviso corre dentro de la transacción de la operación del panel (cancelar,
  reprogramar). La escritura del mensaje va en un **savepoint propio**: si fallara (por ejemplo, la
  base rechaza algo), el turno queda cancelado igual y el adaptador registra
  `aviso_de_turno_sin_registrar`. El envío por Meta ya ocurrió y no se repite.
- **Pedido al ADR-0011 antes de aceptarse:** la fila del Context Map dice «send a text or an approved
  template and get Meta's message id back». Agregar: «…and, for scheduling notices, record the
  outgoing message in the customer's conversation (owned by conversational)». Si ya estuviera
  aceptado, es una enmienda por PR propio.
- **Los recordatorios de cobro no se duplican en la conversación:** su estado vive en `recordatorio`
  (PAN-COB-02, HU-E6-02 RN-01) y guardarlo también como `Mensaje` daría dos estados para un mismo
  `wamid`, con el ruteo de D-U7-1 eligiendo uno. Si el cliente contesta un recordatorio de cobro, el
  agente ya abre o retoma la conversación (RN-03), como hoy.

### D-U7-5 · El mensaje del sistema y el modelo de lenguaje

El historial del intérprete (`agente.py:176`) mandaría al LLM el texto del aviso, que lleva el nombre
del cliente, el servicio y la fecha. `CLAUDE.md` §3.6 prohíbe mandar datos personales sin anonimizar.
**Decisión:** en el historial, un mensaje con `origen=SISTEMA` se reemplaza por el descriptor fijo
`"[Aviso automático del negocio sobre un turno]"`. Da el contexto que RN-03 necesita («sí, voy» tras
un aviso) sin un solo dato personal. El operador ve el texto completo en el panel.

### D-U7-6 · Casos de uso de los callbacks

| Contexto | Caso de uso | Entrada → salida | Garantiza |
|---|---|---|---|
| conversational | `RegistrarEstadoDeEntrega` (nuevo, `application/entregas.py`) | `externo_id, estado, codigo_de_error` → `bool` (encontrado) | `Mensaje.marcar_entrega`; si `FALLIDO`, `motivo_de_falla`; idempotente |
| payments | `RegistrarEntregaDeRecordatorio` (nuevo, `application/entregas.py`) | ídem → `bool` | `Recordatorio.marcar_entrega` monotónico; si `FALLIDO`, `ultimo_error`; idempotente |

Sin rol: los invoca el webhook (como `ActualizarEstadoDesdeMeta` en U6). Sin evento de bitácora por
callback (serían tres por mensaje); el cambio a `FALLIDO` de un recordatorio sí publica
`recordatorio_fallido` para la bitácora.

### D-U7-7 · Frontend

- PAN-COB-02 (`features/payments/components/DetalleDeCobro.tsx`): un recordatorio esperando
  reintento se ve «Reintentando · intento 2 de 3 · próximo hh:mm»; `FALLIDO` muestra el motivo
  traducido (131047 «Fuera de la ventana de 24 h y sin plantilla aprobada», 131026 «El número no usa
  WhatsApp», 131049 «Meta frenó el envío; se puede reintentar mañana», 132015/132016 «La plantilla
  está pausada / deshabilitada en Meta», `INCIERTO` «No sabemos si llegó: Meta no respondió»,
  `COBRO_CERRADO` «No se envió: el cobro se cerró»), y el código crudo para el resto. Backend:
  `api/routers/cobros.py` agrega `intentos`, `proximo_intento_en`, `ultimo_error` a la salida.
- Hilo de conversación (`HiloDeConversacion.tsx`): etiqueta de estado en castellano (hoy imprime el
  enum) y el motivo debajo de un `FALLIDO`. Ya distingue «Sistema».

## Infraestructura

- **Migraciones** (una, número libre al mergear, encadenada a la cabeza de `develop`):
  - `recordatorio`: `externo_id varchar(160)`, `intentos integer NOT NULL DEFAULT 0`,
    `proximo_intento_en timestamptz`, `ultimo_error varchar(60)`; índice único parcial
    `uq_recordatorio_externo_id (externo_id) WHERE externo_id IS NOT NULL AND externo_id <> ''`
    (el `wamid` es único globalmente y la tabla no tiene `empresa_id`); índice parcial
    `ix_recordatorio_reintento (proximo_intento_en) WHERE proximo_intento_en IS NOT NULL`.
  - Backfill de filas trabadas (D-U7-3).
  - `mensaje`: `motivo_de_falla varchar(60)`.
  - Reversible (las columnas se borran; el backfill no se revierte y se documenta).
- **Trabajo asíncrono:** sin tareas nuevas. Los reintentos los toma el barrido horario existente
  (`payments.barrer_empresa`, cola `notifications`); su idempotencia sigue siendo el índice
  `(cobro_id, paso)` más el `UPDATE` de la misma fila.
- **Configuración:** No aplica.
- **Integraciones externas:** sin llamadas nuevas a Meta; solo se consumen callbacks firmados (HMAC
  existente).

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero → No aplica (no cambia montos).
- [ ] Comprobantes / CAE → No aplica.
- [x] Consume un webhook → el mismo `statuses[]` dos veces = un efecto; `delivered` después de `read`
      no retrocede; `failed` es terminal; duplicado de un `sent` sin destinatario no rompe.
- [x] Datos con `empresa_id` → un `wamid` de la empresa B que llega por la URL de A no modifica nada;
      una WABA ajena en `entry[].id` se descarta.
- [x] Salida de un LLM / datos personales a un LLM → el aviso del sistema entra al historial del
      intérprete como descriptor sin datos personales (D-U7-5).
- [x] Datos personales en logs → ni `recipient_id`, ni teléfono, ni texto del aviso.
- [x] Red en tests → callbacks como JSON fijo; el canal con `MockTransport` o doble.
- [x] Reintento → un timeout de lectura nunca se reintenta; un permanente tampoco; tope de 3.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/api/whatsapp_notificaciones.py` (`estados_de`)
- [ ] `backend/src/cheatsheet/api/routers/whatsapp.py` (procesa `statuses` en las dos rutas, verificación de WABA)
- [ ] `backend/src/cheatsheet/api/entregas.py` (nuevo: ruteo por `wamid`)
- [ ] `backend/src/cheatsheet/api/agenda.py` (`NotificarAlCliente` al adaptador de avisos)
- [ ] `backend/src/cheatsheet/contexts/conversational/domain/conversacion.py` (`Mensaje.motivo_de_falla`)
- [ ] `backend/src/cheatsheet/contexts/conversational/application/entregas.py` (nuevo) · `application/notificaciones.py` (nuevo) · `application/agente.py` (descriptor en el historial) · `application/ports.py` (`enviar_plantilla` en `PortMensajeria` si U6 no lo agregó)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/models.py`, `repositories.py`
- [ ] `backend/src/cheatsheet/contexts/payments/domain/recordatorio.py` (orden, reintento)
- [ ] `backend/src/cheatsheet/contexts/payments/application/recordatorios.py` (dos pasadas) · `application/entregas.py` (nuevo) · `application/ports.py` (`ResultadoDeEnvio`, `pendientes_de_reintento`, `buscar_por_externo_id`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/envio.py`, `models.py`, `repositories.py`
- [ ] `backend/src/cheatsheet/api/routers/cobros.py` (campos de reintento en la salida)
- [ ] `backend/src/cheatsheet/contexts/scheduling/application/ports.py` (`DatosDeAviso.cliente_id`) · `application/turnos.py` (`Avisador._armar`) · `infrastructure/avisos.py` (`CanalDeAvisos`)
- [ ] `backend/migrations/versions/00NN_entregas_de_whatsapp.py`
- [ ] `backend/tests/api/test_webhook_estados.py` (nuevo) · `backend/tests/contexts/payments/domain/test_recordatorio.py` · `…/application/test_recordatorios.py` · `…/application/test_entregas.py` · `backend/tests/contexts/conversational/application/test_entregas.py`, `test_notificaciones.py`, `test_agente.py` · `backend/tests/contexts/scheduling/infrastructure/test_avisos.py`
- [ ] `frontend/src/features/payments/components/DetalleDeCobro.tsx` y su API/tests · `frontend/src/features/conversational/components/HiloDeConversacion.tsx` y sus tests
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#4) · `docs/aidlc/epicas/06-…/pendientes.md` (#3) · `docs/aidlc/units.md` · `docs/aidlc/TODO.md` §25

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — Un callback `delivered` del `wamid` de un mensaje del agente no cambia nada (hoy se descarta). GREEN: `ENTREGADO` | integración (API) | pendiente |
| 2 | **RED** — Un callback `read` del `wamid` de un recordatorio de cobro no cambia nada (hoy no hay `externo_id`). GREEN: `LEIDO` en PAN-COB-02 | integración | pendiente |
| 3 | **RED** — Cancelar un turno no deja ningún registro del aviso (hoy). GREEN: un `Mensaje` `SALIENTE`/`SISTEMA` con el `wamid` en la conversación activa del cliente | integración | pendiente |
| 4 | **RED** — Una fila de recordatorio con `enviado_en` nulo traba la cadena: el barrido siguiente no manda nada (hoy). GREEN: se reintenta y sale | caso de uso | pendiente |
| 5 | El mismo `statuses[]` entregado dos veces → un solo cambio | integración | pendiente |
| 6 | `read` y después `delivered` (fuera de orden) → queda `LEIDO`, en `mensaje` y en `recordatorio` | unit (dominio, tabla) | pendiente |
| 7 | `read` sin `delivered` previo → `LEIDO` | unit | pendiente |
| 8 | `failed` con `errors[0].code=131047` → `FALLIDO` + motivo; un `read` posterior no lo cambia | unit + integración | pendiente |
| 9 | `played` → ignorado sin error | unit | pendiente |
| 10 | Callback por `/webhooks/whatsapp/{A}` con el `wamid` de un recordatorio de B → nada cambia en B (RLS) | integración (multi-tenant, CI) | pendiente |
| 11 | `entry[].id` con la WABA de B en la URL de A → descartado con log | integración | pendiente |
| 12 | Callback por la ruta de la app → se rutea a la empresa de `entry[].id` | integración | pendiente |
| 13 | `wamid` desconocido → 200, log sin el wamid completo | integración | pendiente |
| 14 | Varios estados en una notificación: el segundo falla → el primero quedó aplicado | integración | pendiente |
| 15 | Falla transitoria en el primer intento → fila sin `enviado_en`, `intentos=1`, `proximo_intento_en=+1h`; sin `INSERT` nuevo | caso de uso | pendiente |
| 16 | Barrido antes de `proximo_intento_en` → no reintenta; después → `UPDATE` de la misma fila y sale con `wamid` | caso de uso | pendiente |
| 17 | Tercer intento transitorio → `FALLIDO`, `enviado_en` puesto, y el barrido siguiente evalúa el paso 2 | caso de uso | pendiente |
| 18 | Timeout de lectura → `FALLIDO` `INCIERTO` al primer intento, **nunca** reintentado | caso de uso | pendiente |
| 19 | Rechazo permanente (400 131026) → `FALLIDO`, sin reintento | caso de uso | pendiente |
| 20 | Cobro pagado mientras esperaba reintento → fila descartada (`COBRO_CERRADO`), ningún envío | caso de uso | pendiente |
| 21 | Dos barridos solapados con una fila pendiente → un solo envío (savepoint + índice) | integración (CI) | pendiente |
| 22 | El reintento de un cobro no voltea los demás del barrido (savepoint por ítem) | caso de uso | pendiente |
| 23 | Aviso con el cliente sin conversación → se crea una `ACTIVA`; con conversación archivada → se crea otra; con una activa → se agrega ahí | unit | pendiente |
| 24 | Aviso con Meta caído → `Mensaje` `FALLIDO` con motivo, turno cancelado, request OK | integración | pendiente |
| 25a | Empresa sin WhatsApp conectado (producción) → ningún hilo ni mensaje creado, turno cancelado | unit | pendiente |
| 25 | Falla al guardar el mensaje del sistema → el turno queda cancelado; log `aviso_de_turno_sin_registrar` | unit | pendiente |
| 26 | Historial del intérprete: un `SISTEMA` se reemplaza por el descriptor; el texto con nombre no llega al intérprete | unit | pendiente |
| 27 | Respuesta del cliente a un aviso → el agente procesa en la misma conversación (RN-03) | integración | pendiente |
| 28 | Ningún log de los módulos nuevos contiene `recipient_id`, teléfono ni texto del aviso | unit (captura de logs) | pendiente |
| 29 | Migración: índice único de `externo_id`, backfill de filas trabadas | migración (CI) | pendiente |
| 30 | PAN-COB-02: «Reintentando · intento n de 3», motivos traducidos; hilo con estado en castellano y motivo | unit (Vitest) | pendiente |
| 31 | `guard_architecture --scan` y `test_guards.sh` pasan | gate | pendiente |

Gates: los mismos de U6 (backend y frontend). Los casos 10, 21 y 29 corren con PostgreSQL en la CI.

## Verificaciones no posibles sin la app de prueba → `TODO.md` §25

| # | Qué verificar | Unidad | Qué pasa si difiere |
|---|---|---|---|
| 25.4 | (de U5) `messages[0].id` de la respuesta del envío coincide con `statuses[].id` | `entregas-de-whatsapp` | Ningún callback encuentra su mensaje: los estados quedan en `ENVIADO` |
| 25.7 | (de U5) Un `failed` trae `errors[]` con `code` y `title` | ídem | El motivo se muestra como «sin detalle» |
| 25.17 | Frecuencia real de duplicados y desorden de `statuses[]` | ídem | Ninguno en el diseño (es monotónico e idempotente) |
| 25.18 | Que con override por WABA los `statuses` lleguen a `/webhooks/whatsapp/{empresa}` y sin override a la URL de la app | ídem | Se ajusta la configuración (pendiente #3), no el código |
| 25.19 | Si un mensaje de plantilla aceptado puede recibir `failed` horas después (TTL) y con qué código | ídem | El recordatorio pasa a `FALLIDO` tarde; la pantalla lo muestra |

## Preguntas del Gate 1

1. **¿Los avisos de turno que fallan por una causa transitoria también se reintentan?** Recomendación:
   **no.** Son avisos de una acción puntual del panel (cancelación, reprogramación, confirmación); un
   aviso de cancelación que llega tres horas tarde puede llegar después de la hora del turno, y
   reintentarlo exige guardar la plantilla y sus parámetros por mensaje y un barrido nuevo en
   conversational. La falla queda **visible** en el hilo, con su motivo, para que el operador
   contacte al cliente. El recordatorio de turno (U8) sí reintenta, porque ya es un barrido.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | Aprobado por Luciano con las recomendaciones de las preguntas. **Cierra cuando el equipo acepte el ADR-0011** ([#62](https://github.com/cheatsheet12/CheatSheet/pull/62)); hasta entonces no se escribe código |
| 2 · Verificación | | |
| 3 · PR | | |

> Bloqueado para cerrar el Gate 1 hasta que el ADR-0011 esté aceptado (con el agregado de D-U7-4) y
> U5 y U6 mergeadas.

## Decisiones tomadas durante la unidad

- Gate 1 (2026-10-04): Pregunta 1 → no: los avisos de turno con falla transitoria no se reintentan; la falla queda visible en el hilo con su motivo.
