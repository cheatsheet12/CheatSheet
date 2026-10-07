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

## Revalidación contra develop + U6 (2026-10-07)

Hallazgos verificados contra el código por una revalidación de solo lectura.

**Ya resuelto por U5/U6 (fuera de alcance):**

- D-U7-5 (descriptor del SISTEMA) ya existe en `conversational/domain/datos_personales.py:36,71-78`:
  no hay cambio en `agente.py`; el caso 26 queda solo como test de regresión.
- `PortMensajeria.enviar_plantilla`, `ConsultarPlantillaParaEnviar` y `api/plantillas_salientes.py`
  existen. Las rutas `/webhooks/whatsapp` (app) y por empresa ya rutean plantillas por WABA con
  `empresas_de_la_cuenta_de_whatsapp`. `uq_integracion_waba` (0036) es único: hay 0 o 1 empresa por
  WABA. El agente usa `_NotificadorSilencioso`. El único llamador de `armar_avisador`/`armar_notificador`
  es `api/routers/agenda.py:579-649` (688 líneas: no debe crecer).

**Correcciones al plan:**

- La migración es la **0037** (`down_revision="0036"`) y su test es
  `tests/integracion/test_migracion_0037.py`.
- Citas movidas: `whatsapp.py` `_mensajes_de` ~274-303; `Mensaje.marcar_entrega`
  `conversacion.py:149-163`; `buscar_por_externo_id` `repositories.py:148-151`;
  `PortEnvioDeRecordatorio` en `payments/application/ports_de_recordatorios.py:17-25`; `_hilo_de`
  `agente.py:251-263`; el hilo del frontend es ahora `LineaDeTiempo.tsx`; el estado del cobro está en
  `DetalleDeCobro.tsx:375-392`.
- Las entradas de TODO de U7 son §22.35, §22.38, §22.39 y las nuevas de §22.53 (no §25).
- Archivos de test reales: `application/test_cobros_y_recordatorios.py` tiene 1000 líneas, así que
  los tests nuevos van en archivos nuevos; `test_cobros_postgres.py`;
  `scheduling/infrastructure/test_avisos.py`; se reutiliza `tests/api/montaje_webhook_plantillas.py`.

**Riesgos:**

- `routers/whatsapp.py` tiene 356 líneas: el ruteo de `statuses` va en `api/entregas.py` y el router
  solo lo llama.
- `hay_mensajes` (`whatsapp_notificaciones.py:80`) es verdadero también para payloads solo de
  `statuses`, y la ruta de la app loguea `whatsapp_mensajes_en_la_url_de_la_app`: hay que distinguir
  `messages[]` de `statuses[]`.
- La ruta por empresa debe verificar `entry[].id` (WABA) contra la empresa de la URL también para
  `statuses`.
- Archivos en el límite: `conversational/infrastructure/repositories.py` 400/400 (mover
  `RepositorioMensajePostgres` a su propio módulo), `atencion.py` 391, `conversational/application/ports.py`
  381, `payments/application/recordatorios.py` 285 (el reintento va en un `reintentos.py` aparte),
  `payments/infrastructure/repositories.py` 353, `cobros.py` 385.
- El hallazgo del ADR-0014 (E/S a Meta con la transacción abierta) no cambia y no se agrava.
- Verificar RLS en la búsqueda de `recordatorio` por `externo_id` en el caso PostgreSQL.

**Cierre y tamaño:** el #73 se cierra recién tras U8 (lista U5, U6, U7 y U8). U7 cierra los pendientes
#4 (épico 8) y #3 (épico 6). Estimación: ~1.750 líneas de autoría, en 3 PR encadenados.

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
| `entry[].changes[].value.statuses[]` con `id` (wamid), `status`, `timestamp`, `recipient_id` siempre; `errors[]` «only included if failure to send or deliver message»; `conversation`/`pricing` solo en `sent` y uno de `delivered`/`read`; `biz_opaque_callback_data` si se mandó | Se leen `id`, `status`, `timestamp` y `errors[0].code`; el `title` **no** se lee ni se guarda (decisión (b): texto de un tercero, §22.56). Nada de `recipient_id` se guarda ni se loguea (es un teléfono) |
| `status` ∈ `sent`, `delivered`, `read`, `failed`, `played` | `played` (nota de voz reproducida) se ignora |
| «In some cases… the message is both delivered and read at the same time. In these cases, the 'delivered' webhook is not sent» | `LEIDO` sin `ENTREGADO` previo es legítimo: el orden permite saltar |
| La documentación **no** garantiza orden ni ausencia de duplicados | Idempotencia y piso monotónico obligatorios |
| El campo `messages` (que incluye `statuses`) **sí** admite override por WABA | Los callbacks llegan a `/webhooks/whatsapp/{empresa}` cuando la WABA tiene override, o a `/webhooks/whatsapp` (ruta de la app, U6) si no |
| Códigos en `errors[].code`: 131047 fuera de ventana, 131026 no es usuario de WhatsApp, 131049 «healthy ecosystem», 131050 baja de marketing, 132015/132016 plantilla pausada/deshabilitada ([error codes](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes)) | La pantalla traduce los conocidos y muestra el código crudo para el resto (el `title` de Meta no se guarda: decisión (b), §22.56) |

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
  Caso esperable: el `sent` llega antes de que haga commit la transacción que mandó el mensaje. Para un
  **mensaje** del agente o del operador no se pierde nada: ese estado (`ENVIADO`) ya lo escribió el
  propio envío, y los siguientes (`delivered`/`read`) llegan después. **Para un recordatorio de cobro
  la afirmación era falsa** (hallazgo H1 del Gate 2): el barrido (`workers/tasks_payments.py:74`) abre
  una unidad de trabajo por empresa y confirma recién al final, así que un `failed` o `delivered` que
  llega antes del commit no encuentra la fila, se contesta 200 y se pierde. El tramo ii confirma cada
  recordatorio **antes** de la E/S a Meta y lo actualiza después (con ello también resuelve la parte de
  recordatorios del hallazgo G5/ADR-0014); queda registrado en `TODO.md` §22.57.
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
| 1 | **RED** — Un callback `delivered` del `wamid` de un mensaje del agente no cambia nada (hoy se descarta). GREEN: `ENTREGADO` | integración (API) | hecho · tramo 1 |
| 2 | **RED** — Un callback `read` del `wamid` de un recordatorio de cobro no cambia nada (hoy no hay `externo_id`). GREEN: `LEIDO` en PAN-COB-02 | integración | hecho · tramo 1 |
| 3 | **RED** — Cancelar un turno no deja ningún registro del aviso (hoy). GREEN: un `Mensaje` `SALIENTE`/`SISTEMA` con el `wamid` en la conversación activa del cliente | integración | pendiente · tramo 3 |
| 4 | **RED** — Una fila de recordatorio con `enviado_en` nulo traba la cadena: el barrido siguiente no manda nada (hoy). GREEN: se reintenta y sale | caso de uso | pendiente · tramo 2 |
| 5 | El mismo `statuses[]` entregado dos veces → un solo cambio (en `recordatorio`, con un solo `recordatorio_fallido`, y en `mensaje`) | integración | hecho · tramo 1 |
| 6 | `read` y después `delivered` (fuera de orden) → queda `LEIDO`, en `mensaje` y en `recordatorio` | unit (dominio, tabla) | hecho · tramo 1 |
| 7 | `read` sin `delivered` previo → `LEIDO` | unit | hecho · tramo 1 |
| 8 | `failed` con `errors[0].code=131047` → `FALLIDO` + motivo; un `read` posterior no lo cambia | unit + integración | hecho · tramo 1 |
| 9 | `played` → ignorado sin error | unit | hecho · tramo 1 |
| 10 | Callback por `/webhooks/whatsapp/{A}` con el `wamid` de un recordatorio de B → nada cambia en B (RLS) | integración (multi-tenant, CI) | escrito · tramo 1 (corre en CI; en memoria, hecho) |
| 11 | `entry[].id` con la WABA de B en la URL de A → descartado con log | integración | hecho · tramo 1 |
| 12 | Callback por la ruta de la app → se rutea a la empresa de `entry[].id` | integración | hecho · tramo 1 |
| 13 | `wamid` desconocido → 200, log sin el wamid completo | integración | hecho · tramo 1 |
| 14 | Varios estados en una notificación: el segundo falla → el primero y el tercero (en `mensaje` y en `recordatorio`) quedaron aplicados, 200 y log solo con la clase de la excepción (H4) | integración | hecho · tramo 1 |
| 15 | Falla transitoria en el primer intento → fila sin `enviado_en`, `intentos=1`, `proximo_intento_en=+1h`; sin `INSERT` nuevo | caso de uso | pendiente · tramo 2 |
| 16 | Barrido antes de `proximo_intento_en` → no reintenta; después → `UPDATE` de la misma fila y sale con `wamid` | caso de uso | pendiente · tramo 2 |
| 17 | Tercer intento transitorio → `FALLIDO`, `enviado_en` puesto, y el barrido siguiente evalúa el paso 2 | caso de uso | pendiente · tramo 2 |
| 18 | Timeout de lectura → `FALLIDO` `INCIERTO` al primer intento, **nunca** reintentado | caso de uso | pendiente · tramo 2 |
| 19 | Rechazo permanente (400 131026) → `FALLIDO`, sin reintento | caso de uso | pendiente · tramo 2 |
| 20 | Cobro pagado mientras esperaba reintento → fila descartada (`COBRO_CERRADO`), ningún envío | caso de uso | pendiente · tramo 2 |
| 21 | Dos barridos solapados con una fila pendiente → un solo envío (savepoint + índice) | integración (CI) | pendiente · tramo 2 |
| 22 | El reintento de un cobro no voltea los demás del barrido (savepoint por ítem) | caso de uso | pendiente · tramo 2 |
| 23 | Aviso con el cliente sin conversación → se crea una `ACTIVA`; con conversación archivada → se crea otra; con una activa → se agrega ahí | unit | pendiente · tramo 3 |
| 24 | Aviso con Meta caído → `Mensaje` `FALLIDO` con motivo, turno cancelado, request OK | integración | pendiente · tramo 3 |
| 25a | Empresa sin WhatsApp conectado (producción) → ningún hilo ni mensaje creado, turno cancelado | unit | pendiente · tramo 3 |
| 25 | Falla al guardar el mensaje del sistema → el turno queda cancelado; log `aviso_de_turno_sin_registrar` | unit | pendiente · tramo 3 |
| 26 | Historial del intérprete: un `SISTEMA` se reemplaza por el descriptor; el texto con nombre no llega al intérprete | unit | pendiente · tramo 3 (solo regresión: el descriptor ya existe) |
| 27 | Respuesta del cliente a un aviso → el agente procesa en la misma conversación (RN-03) | integración | pendiente · tramo 3 |
| 28 | Ningún log de los módulos nuevos contiene `recipient_id`, teléfono ni texto del aviso | unit (captura de logs) | parcial · tramo 1 (webhook de estados; faltan los avisos, tramo 3) |
| 29 | Migración 0037: columnas e índice único **parcial** de `externo_id` (sin backfill, D1) | migración (CI) | escrito · tramo 1 (corre en CI) |
| 30 | PAN-COB-02: «Reintentando · intento n de 3», motivos traducidos; hilo con estado en castellano y motivo | unit (Vitest) | pendiente · tramo 3 |
| 31 | `guard_architecture --scan` y `test_guards.sh` pasan | gate | hecho · tramo 1 (`guard_architecture`; `test_guards.sh` pendiente: falta `jq`) |
| 32 | Dos callbacks del mismo `wamid` solapados (dos transacciones) no se pisan: `LEIDO` no se pisa con `ENTREGADO`, `FALLIDO` no se pisa, y `recordatorio_fallido` se publica una vez (H2) | integración (CI) | escrito · tramo 1 (corre en CI) |
| 33 | `wamid` vacío o más largo que la columna → se guarda `None`, el paso queda despachado y el log no lleva el id (H3) | unit | hecho · tramo 1 |
| 34 | Un estado venenoso no bloquea los mensajes del cliente (ruta por empresa); una falla transitoria de la base no corta los demás estados ni los mensajes y termina en 500 para que Meta reintente (H4) | integración (API) | hecho · tramo 1 |
| 35 | Clasificación de fallas: conexión, tiempo, deadlock y `SQLSTATE` 08/40/53/57 son transitorias; integridad, datos, sintaxis y errores nuestros no (H4) | unit | hecho · tramo 1 |

Gates: los mismos de U6 (backend y frontend). Los casos 10, 21, 29 y 32 corren con PostgreSQL en la CI.

**Tramos (PRs encadenados, D4):** (i) callbacks `statuses[]` + estado monótono + columnas + motivo de
falla; (ii) reintento acotado de fallas transitorias; (iii) avisos del SISTEMA + frontend. Cada
uno se apila sobre el anterior y se mergea a `develop` en ese orden.

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
| 2 · Verificación | 2026-10-07 | Tramo 1 aprobado por Luciano (correcciones H2 a H5 incluidas; H1 pasa al tramo ii). Hallazgo fuera de U7: un `wamid` entrante de más de 160 caracteres desborda su columna (`TODO.md` §22.58) |
| 3 · PR | | |

> Bloqueado para cerrar el Gate 1 hasta que el ADR-0011 esté aceptado (con el agregado de D-U7-4) y
> U5 y U6 mergeadas.

## Estado de la implementación

### Tramo 1 — callbacks de estado (2026-10-07)

**Hecho** (casos 1, 2, 5 a 9 y 11 a 14 con dobles; 10 y 29 escritos para la CI):

- `api/whatsapp_notificaciones.py`: `estados_de_entrega` (defensivo; solo `id`, `status` y `errors[0].code`
  de un `failed`; `played` y desconocidos se ignoran; un id demasiado largo se descarta, no se corta) y
  `hay_mensajes` ahora distingue `messages[]` de `statuses[]`.
- `api/entregas.py` (nuevo): ruteo por la WABA del `entry[].id` (ruta de la app: debe tener una sola
  dueña; ruta por empresa: debe ser la de la URL, si no se descarta con log), una transacción por
  estado, primero `mensaje` y después `recordatorio`. `routers/whatsapp.py` solo lo llama (362 líneas).
- `conversational`: `Mensaje.marcar_entrega(estado, motivo=)` devuelve si cambió (monótono, `FALLIDO`
  terminal), `Mensaje.motivo_de_falla`, `RegistrarEstadoDeEntrega`, `motivo_de_falla_de` (código de Meta
  o clase corta: `INCIERTO`, `SIN_CANAL`, `SATURADA`, `RECHAZADO`, `ERROR`) y `SalidaAlCliente` lo guarda
  cuando el envío del agente falla (D3).
- `payments`: `Recordatorio.marcar_entrega` monótono (D-U7-2), `externo_id` y `ultimo_error`,
  `ResultadoDeEnvio` (el puerto devuelve el `wamid` y el código), `RegistrarEntregaDeRecordatorio`
  (publica `recordatorio_fallido` una sola vez).
- Raíz (D2): `api/fallas_de_canal.py` (`CanalConFallasTraducidas`) traduce los errores tipados del canal a
  `payments.FallaDelCanal(codigo)`; `armar_envio` lo usa. **Para `scheduling` se hará en el tramo 3**, cuando
  los avisos se registren.
- Migración **0037**: `recordatorio.externo_id` + `ultimo_error` + índice único parcial, `mensaje.motivo_de_falla`.
  Sin backfill (D1).
- `mensaje`: `RepositorioMensajePostgres` pasó a `repositorio_mensaje.py` (el módulo estaba en 400/400).
- ADR-0011 (puntos 5 y 8) y `architecture.md` §4 enmendados (D5); pendientes en `TODO.md` §22.53 a §22.56.

**Decisiones del tramo 1**

- **Las columnas `intentos` y `proximo_intento_en` no están en la 0037**: nada del tramo 1 las usa. Las agrega
  el tramo 2 (migración 0038), así cada PR trae solo el esquema que ejerce.
- **Del `failed` se guarda solo el `code`**, no el `title` (texto de un tercero, §22.56). Sin código, el motivo
  queda vacío y la pantalla dirá «sin detalle».
- **Un `wamid` sin destinatario se loguea en `warning`** (sin el id): si el id del envío no coincidiera con el de
  `statuses[]` (§22.54), todos los estados caerían ahí y se vería.
- **Un envío del operador que falla no guarda mensaje** (levanta `MensajeriaNoDisponible`, como antes): D3 se
  cumple para el motivo que llega por callback.
- El `EstadoEntrega` se traduce en la raíz por valor (`"LEIDO"`): cada contexto conserva su enum (R3).

**Correcciones del Gate 2 (2026-10-07)** — H2 a H5 (H1 va al tramo ii):

- **H2, bloqueo de la fila:** `buscar_por_externo_id(externo_id, *, para_actualizar=False)` en los dos
  puertos y repositorios; los casos de uso de los callbacks lo piden con `para_actualizar=True`
  (`SELECT ... FOR UPDATE`, compatible con `aislamiento_por_cobro`, que es `FOR ALL`). Dos callbacks del
  mismo `wamid` se serializan: un `delivered` retrasado no pisa un `read`, un `failed` no se pisa y
  `recordatorio_fallido` se publica una sola vez. Test de CI con dos transacciones solapadas
  (`tests/integracion/test_entregas_concurrentes_postgres.py`).
- **H3, `wamid` fuera de la columna:** `shared/externo_id.py` define `LARGO_MAXIMO_EXTERNO_ID` (160, también
  usado por los modelos y el parser) y `externo_id_o_ninguno`. `Recordatorio.marcar_enviado` guarda `None`
  si el id está vacío o no entra (el paso se da por despachado igual: sin eso el barrido lo reenviaría y el
  cliente recibiría el recordatorio dos veces); los mensajes salientes del agente y del operador siguen la
  misma regla. El canal devuelve `""` y loguea `whatsapp_id_de_mensaje_demasiado_largo` (largo, sin el id).
- **H4, un estado no tumba la notificación:** `aplicar_estados_de_entrega` aísla cada estado
  (`api/entregas.py`); ver «Decisiones» más abajo para las clases de excepción. En la ruta por empresa los
  mensajes entrantes se procesan aunque un estado falle. La unidad de trabajo se cierra con `aclosing`
  cuando el cuerpo levanta, para soltar la fila bloqueada de inmediato.
- **H5:** `pytestmark` asyncio solo en los tests async de `test_fallos_tipados_del_canal.py` (cero
  warnings propios); `test_webhook_estados.py` (475 líneas) partido en `test_webhook_estados.py`,
  `test_webhook_estados_robustez.py`, `test_clasificacion_de_fallas_de_estados.py` y el montaje
  `montaje_webhook_estados.py`; la 0037 verifica que el índice es parcial (`WHERE`); el caso 5 cubre también
  el lado `mensaje` y el 14 también el lado `recordatorio`.

**Evidencia RED (TDD):** observado en colección (`ImportError` del símbolo inexistente) antes de implementar en
cada bloque: dominio y casos de uso de `conversational`, dominio/casos de uso/adaptador de `payments`, el
envoltorio de la raíz, el parser y el webhook de estados. **No se observó RED** en: el refactor de
`repositorio_mensaje.py` (movimiento puro), `test_migracion_0037.py`, `test_entregas_de_recordatorio_postgres.py`
y los dos casos agregados a `test_conversacional_postgres.py` (necesitan PostgreSQL: solo corren en la CI).

**Correcciones del Gate 2:** RED observado (el test falla antes de implementar) en H3 (dominio, canal,
agente y operador), H2 (los casos de uso piden la fila bloqueada) y H4 (los tres casos nuevos del webhook).
**No se observó RED** en: `test_entregas_concurrentes_postgres.py` y la aserción de índice parcial de
`test_migracion_0037.py` (necesitan PostgreSQL: solo corren en la CI; §22.55) y en el movimiento de tests
de H5.

## Decisiones tomadas durante la unidad

- Gate 1 (2026-10-04): Pregunta 1 → no: los avisos de turno con falla transitoria no se reintentan; la falla queda visible en el hilo con su motivo.
- Gate 1 revalidado y aprobado por Luciano (2026-10-07):
  - **D1** — Se elimina el backfill de «filas trabadas»: la premisa es falsa (`recordatorios.py:221-249`
    inserta, envía y marca enviado en un solo savepoint) y un backfill podría reenviar un recordatorio
    que sí salió. La migración 0037 trae solo columnas e índices. El caso 29 se actualiza.
  - **D2** — Las clases de falla se traducen en la raíz de composición: wrappers en `api/` (patrón
    `_RevisionViaMeta`, `api/mensajeria.py:196-244`) que capturan los errores tipados de conversational
    (`MensajeriaSaturada`, `MensajeRechazado`, `EnvioIncierto`, `CanalNoConectado`, con `.codigo`,
    `conversational/application/errors.py:63-109`) y levantan excepciones locales de payments/scheduling
    declaradas en su módulo de puertos. R3 intacta.
  - **D3** — `motivo_de_falla` también para los mensajes del agente y del operador (misma columna, mismo
    código).
  - **D4** — Tres PR encadenados, cada uno apilado sobre el anterior y mergeados a `develop` en orden:
    (i) callbacks de estado + estado monotónico + columnas + motivo de falla; (ii) reintento acotado de
    fallas transitorias; (iii) avisos del SISTEMA + frontend. Los límites de cada slice se registran en
    este plan.
  - **D5** — Las dos enmiendas de una línea al ADR-0011 se hacen dentro de U7 (slice i): punto 5 (U7
    verifica contra Meta que el override por WABA aplica a `messages`; queda como pendiente en el TODO
    porque no hay sandbox) y punto 8 (el Context Map incluye registrar el mensaje en la conversación).
  - **D6** — Los avisos de turno no se reintentan (la pregunta 1 del Gate 1 se mantiene).
- Gate 2 del tramo 1 (2026-10-07, Luciano):
  - **H1 (no se implementa en el tramo i; va al tramo ii)** — el barrido (`workers/tasks_payments.py:74`,
    una `unidad_de_trabajo` por empresa; `recordatorios.py:230-252`) confirma recién al final, así que un
    `failed`/`delivered` que llega antes del commit no encuentra la fila, recibe 200 y se pierde: la
    afirmación «no se pierde nada» de D-U7-1 era falsa para los recordatorios. El tramo ii confirma cada
    recordatorio antes de la E/S a Meta y lo actualiza después (resuelve también la parte de recordatorios
    del hallazgo G5/ADR-0014). Pendiente en `TODO.md` §22.57.
  - **H2** — la búsqueda de los callbacks bloquea la fila (`SELECT ... FOR UPDATE`) y hay un test de CI con
    dos transacciones.
  - **H3** — un `wamid` vacío o más largo que la columna se guarda como `None`, nunca cortado; el paso se da
    por despachado igual; log estructurado sin el id.
  - **H4** — cada estado se aplica aislado. Un estado que falla por algo suyo se registra con la clase de su
    excepción (nunca `wamid`, teléfono ni texto) y se sigue; solo una falla **transitoria** de la base se
    vuelve a levantar, al final, para que Meta reintente. Clases transitorias (`es_falla_transitoria`):
    `OperationalError`, `InterfaceError`, el `TimeoutError` del pool de SQLAlchemy, `ConnectionError` y
    `TimeoutError` del sistema (red, tiempo agotado), y cualquier `DBAPIError` cuyo `SQLSTATE` sea de clase
    08 (conexión), 40 (deadlock o serialización), 53 (recursos) o 57 (reinicio o cancelación), porque el
    controlador asíncrono no siempre lo traduce a `OperationalError`. No lo son `IntegrityError`,
    `DataError`, `ProgrammingError` ni un error de nuestro código: reintentar el mismo estado fallaría igual,
    para siempre. El único `except Exception` (con `# noqa: BLE001` y su justificación, como en
    `recordatorios.py`) está en el borde del aislamiento y decide con esa función, no con un `pass`.
  - **H5** — ver «Correcciones del Gate 2» arriba.
  - **Un `failed` que llega después de `read`/`delivered` se acepta y es terminal** (D-U7-2): se verifica
    contra Meta en `TODO.md` §22.54.
  - **(a)** `intentos` y `proximo_intento_en` van a la migración **0038** en el tramo ii (`down_revision =
    "0037"`, su propio test de migración en la CI, sin backfill).
  - **(b)** Del `failed` se guarda solo `errors[0].code`, nunca el `title` (texto de un tercero); §22.56 es la
    salida si hace falta mostrarlo.
  - **(c)** El `wamid` sin destinatario se sigue registrando en nivel `warning`.
