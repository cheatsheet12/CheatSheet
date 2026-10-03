# Unidad: canal-real-de-whatsapp

**HUs**: HS-T3, HU-E7-02, HU-E7-06, HU-E8-04 (y HU-E11-02 RN-03/RN-04 en la parte B)   **Contexto dueño**: conversational   **Rama**: feature/conversational-canal-real-de-whatsapp

> Origen: [`../etapa-6/reparto.md`](../etapa-6/reparto.md) §2, «Unidades de código pendientes» —
> responsable Luciano, revisa Cristian, presupuesto 10 h. Cierra el pendiente #11 del épico 8
> ([`../epicas/08-agente-de-whatsapp/pendientes.md`](../epicas/08-agente-de-whatsapp/pendientes.md)) y
> toca el #3, #4, #9 y #13. Requiere el [ADR-0011](../../adr/0011-outbound-whatsapp-channel-via-composition-root.md)
> (borrador, «Proposed»), que tiene que aprobarse antes de cerrar este Gate.
>
> **Todo lo marcado «supuesto hasta el Gate 1» depende de las preguntas del final.**

## Qué hace

Hoy ningún recordatorio de cobro ni aviso de turno sale por WhatsApp: los dos van a un log
(`EnvioPorConsola`, `AvisoPorConsola`) y los dos se niegan a arrancar en producción. Esta unidad los
reemplaza por adaptadores que mandan el mensaje por el cliente real de la Cloud API que ya existe en
`conversational` (`MensajeriaWhatsApp`), cableado en el composition root sin que ningún contexto
importe a otro. Un fallo de Meta nunca voltea la operación: el turno se cancela igual y el
recordatorio queda registrado como `FALLIDO`.

## Partición — supuesto hasta el Gate 1 (pregunta P1)

El trabajo completo pedido (adaptadores + plantillas de Meta + callbacks de entrega) se estima en
**≈ 19 h**, casi el doble de las 10 h del reparto. Se propone partirlo:

| Parte | Alcance | Estimación | Estado |
|---|---|---|---|
| **A — `canal-real-de-whatsapp`** (esta) | Adaptadores reales de `payments` y `scheduling` sobre `MensajeriaWhatsApp`, mensajes de texto, canal nulo en producción, configuración de Render y documentación | **≈ 8,5 h** | se planifica en detalle acá |
| **B — `plantillas-y-entregas-de-whatsapp`** | Mensajes `type: template` fuera de la ventana de 24 h, estado de aprobación de las plantillas, callbacks de entrega (`statuses`) para `mensaje` y `recordatorio` | **≈ 10,5 h** | se lista al final; fila nueva en `units.md` solo si el Gate aprueba la partición |

**Lo que A sola no cierra, dicho de frente:** fuera de la ventana de 24 h, Meta rechaza un texto
libre iniciado por la empresa (ver Contratos). Un recordatorio de cobro o una confirmación de turno
cargado desde el panel casi nunca cae dentro de esa ventana, así que con A sola **en producción esos
mensajes van a quedar `FALLIDO`** (registrado y visible en PAN-COB-02, no silencioso). HS-T3,
HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04 y HU-E8-04 quedan **cerradas de punta a punta recién con B**.
Hay que decírselo al equipo en la matriz.

## Lo que existe hoy (relevado en esta rama, 2026-10-03)

- `api/mercadopago.py:143-151` — `armar_envio(settings)` devuelve siempre `EnvioPorConsola`. Lo usa el
  barrido de cobros `workers/tasks_payments.py:81` (`barrer_empresa`).
- `api/agenda.py:61-69` — `armar_notificador(settings)` devuelve siempre `AvisoPorConsola`;
  `armar_avisador` (`:72-84`) lo usa, y lo llaman `api/routers/agenda.py:582, 621, 645` y el agente
  (`api/conversacional.py:174`, dentro de `armar_agenda`).
- `api/conversacional.py:97-131` — `armar_mensajeria` (async) elige entre `MensajeriaSimulada`
  (`WHATSAPP_ADAPTADOR=simulado`, o empresa sin WhatsApp conectado, o sin `phone_number_id`) y
  `MensajeriaWhatsApp` con token y `phone_number_id` leídos de `integrations` por unidad de trabajo.
  `armar_plantillas` (`:182`) está definida y **nadie la llama** (pendiente #13).
- `contexts/conversational/infrastructure/canal.py:85-126` — `MensajeriaWhatsApp`: timeout explícito,
  3 intentos, no reintenta un 4xx, transporte `httpx` inyectable; solo manda `type: text`.
- **Hallazgo:** `MensajeriaSimulada(Entorno.PRODUCTION)` levanta `RuntimeError` (`canal.py:65-70`).
  Como `armar_mensajeria` la devuelve para una empresa **sin WhatsApp conectado**, en producción
  cancelar un turno de esa empresa daría 500 apenas el aviso deje de ser la consola. Lo contrario de
  lo que dice su propio docstring.
- Firmas distintas, cada una correcta bajo R3: `PortEnvioDeRecordatorio.enviar(empresa_id, cobro,
  canal, paso) -> EstadoEntrega` (`payments/application/ports.py:303-311`) no trae teléfono ni texto;
  `PortNotificadorDeTurnos` recibe `DatosDeAviso` con `telefono` (`scheduling/application/ports.py:58-65`).
- `PortClienteDeCobro` (`payments/application/ports.py:344-357`) **no expone el contacto a
  propósito** (D92). `scheduling` ya tiene `PortDirectorioDeClientes.contacto_de` con su ACL
  `ClientesViaMasterData.contacto_de` (`scheduling/infrastructure/catalogo.py:88-92`).
- **Hallazgo:** `DespacharRecordatorios._despachar_uno` (`payments/application/recordatorios.py:175-189`)
  inserta la fila del paso y **después** llama a `envio.enviar` sin `try`. Si el adaptador levantara,
  la excepción voltearía la transacción del barrido entero; y si la fila quedara sin `enviado_en`, el
  índice único `(cobro_id, paso)` la haría «ya despachada» para siempre. Por eso el adaptador real
  **nunca levanta**: devuelve `FALLIDO`.
- No hay arista `conversational → payments/scheduling` en el Context Map (`docs/architecture.md:79-92`).
- `render.yaml` no declara **ninguna** variable `WHATSAPP_*`, ni en la API ni en el worker. El
  2026-10-03 `WHATSAPP_WEBHOOK_SECRET` tuvo que crearse a mano en Render. `docs/staging-deployment.md`
  §3 tampoco la menciona, y `docs/configuration-management.md:122-124` todavía lista
  `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID`, que ya no existen (el token y el número son por empresa, en
  `integrations`).
- `backend/.env.example` **no pudo leerse en este relevamiento** (permiso denegado). Se verifica al
  implementar que documente `WHATSAPP_ADAPTADOR`, `WHATSAPP_WEBHOOK_SECRET` y
  `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.

## Diseño (parte A)

- **Dominio**: sin cambios. `EstadoEntrega` y `Recordatorio` ya tienen lo necesario (`ENVIADO`,
  `FALLIDO`). `DatosDeAviso` no cambia.
- **Aplicación**:
  - `payments/application/ports.py` gana `PortContactoDeCliente.contacto_de(cliente_id) ->
    ContactoDeCobro | None` (nombre y teléfono). **Puerto aparte y no un método más en
    `PortClienteDeCobro`**, para no deshacer D92: el caso de uso de cobros sigue sin ver el contacto;
    solo el adaptador de envío lo recibe. Mismo patrón que `scheduling`.
  - `DespacharRecordatorios` no cambia de firma. Su comportamiento ya cubre `FALLIDO`.
- **Puertos y adaptadores**:
  - `payments/infrastructure/envio.py`: `EnvioPorWhatsApp(canal, contactos)` implementa
    `PortEnvioDeRecordatorio`. Arma el texto de fábrica de `recordatorio_de_cobro` (nombre, concepto,
    monto con `Decimal` cuantizado a 2 decimales con `ROUND_HALF_UP`, link si el cobro lo tiene),
    llama a `canal.enviar(telefono=…, texto=…)` y devuelve `ENVIADO`. Devuelve `FALLIDO` sin llamar a
    Meta si el cliente no tiene teléfono o si el paso no es `WHATSAPP` (no hay adaptador de email);
    devuelve `FALLIDO` si el canal levanta `MensajeriaNoDisponible` o `CanalNoConectado`. **Nunca
    levanta.** `canal` es un `Protocol` local del módulo (`CanalDeTexto`), no un import de
    `conversational` (ADR-0011).
  - `scheduling/infrastructure/avisos.py`: `AvisoPorWhatsApp(canal)` implementa
    `PortNotificadorDeTurnos` reusando `texto_de_reserva/cancelacion/reprogramacion`. Atrapa
    `MensajeriaNoDisponible`/`CanalNoConectado`, registra `aviso_de_turno_fallido` (clase de aviso, sin
    datos personales) y vuelve. La corrección a posteriori ya no llama al avisador (RN-07); no cambia.
  - `conversational/infrastructure/canal.py`: `CanalNoConectado` (excepción) y `SinCanal` — el
    adaptador de producción para una empresa sin WhatsApp conectado: levanta `CanalNoConectado` sin
    tocar la red. `MensajeriaWhatsApp` agrega al log de un 4xx el **código de error de Meta** del cuerpo
    (`error.code`), sin teléfono ni texto: es lo que permite distinguir en staging «fuera de ventana»
    de «número inválido».
  - `EnvioPorConsola` y `AvisoPorConsola` salen de `src/`: el doble de staging pasa a ser
    `MensajeriaSimulada` detrás del adaptador real. `tests/.../test_avisos.py` se reescribe contra
    `AvisoPorWhatsApp` con un canal falso.
- **Composition root** (`backend/src/cheatsheet/api/`):
  - `api/mensajeria.py` (nuevo): `armar_mensajeria` se muda acá desde `api/conversacional.py` para no
    crear el ciclo `conversacional → agenda → conversacional`. En producción, sin integración o sin
    `phone_number_id`, devuelve `SinCanal` en lugar de `MensajeriaSimulada`.
  - `api/mercadopago.armar_envio(unidad, settings, *, empresa_id)` y
    `api/agenda.armar_notificador/armar_avisador` pasan a `async` y reciben el canal de
    `armar_mensajeria`. Se actualizan sus llamadores: `workers/tasks_payments.py:81`,
    `api/routers/agenda.py:582/621/645`, `api/conversacional.armar_agenda` y sus llamadores en
    `api/routers/whatsapp.py` y `api/routers/conversaciones.py`.
- **Otros contextos**: `payments` y `scheduling` reciben el canal de `conversational` **solo por el
  composition root**; ningún import nuevo entre contextos (R1–R5 intactas). Es una arista que el
  Context Map **no** tiene → **ADR-0011** agrega la fila `conversational → payments, scheduling`.
  `payments → master_data` (contacto del cliente) ya está permitido (C/S).
- **Frontend**: No aplica. PAN-COB-02 ya muestra `estado_entrega` de cada recordatorio.

## Infraestructura

- **Migraciones**: No aplica en A. (B agrega `recordatorio.externo_id`.)
- **Trabajo asíncrono**: el barrido de cobros (`tasks_payments.barrer_empresa`, cola
  `notifications`, Beat) no cambia de forma; ahora su envío llega a Meta. La idempotencia sigue siendo
  el índice único `(cobro_id, paso)` (D25). **Los avisos de turno siguen saliendo dentro del request
  del panel**, como hoy el agente: peor caso 3 intentos × `WHATSAPP_TIMEOUT_SEGUNDOS` (10 s) con la
  transacción abierta. Se acepta en A (ver Riesgos); mudarlo al worker de integraciones es la
  alternativa D del ADR-0011.
- **Configuración** (no hay variables nuevas; hay variables **no declaradas**):
  - `render.yaml`, servicio `cheatsheet-api`: `WHATSAPP_WEBHOOK_SECRET` y
    `WHATSAPP_WEBHOOK_VERIFY_TOKEN` con `sync: false`; `WHATSAPP_ADAPTADOR` con `value: simulado`
    (staging no tiene credenciales reales de Meta, `docs/staging-deployment.md` §8).
  - `render.yaml`, servicio `cheatsheet-worker`: `WHATSAPP_ADAPTADOR` con el mismo valor — el
    barrido de recordatorios corre en el worker y tiene que elegir el mismo canal que la API.
  - `docs/staging-deployment.md` §3: dos filas en la tabla (`WHATSAPP_WEBHOOK_SECRET` = el **App
    Secret** de la app de Meta, con el que firma `X-Hub-Signature-256`; `WHATSAPP_WEBHOOK_VERIFY_TOKEN`
    = el token que se escribe al registrar la URL) y la advertencia de que sin el secreto toda
    notificación se descarta con 200 (D49, pendiente #3). §4 bis.2: `WHATSAPP_ADAPTADOR` en el worker.
  - `docs/configuration-management.md:122-124`: reemplazar `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID` por las
    variables reales y una línea que diga que el token y el número son por empresa (HU-E2-03).
  - `backend/.env.example`: verificar (no se pudo leer) y completar si falta.
- **Integraciones externas**: Meta WhatsApp Cloud API, el mismo cliente. Timeout
  `WHATSAPP_TIMEOUT_SEGUNDOS`, 3 intentos sobre 5xx/timeout, ninguno sobre 4xx. Sandbox vs producción:
  ver Contratos.

## Contratos — Meta WhatsApp Cloud API

> Sin acceso web en este relevamiento: lo que sigue sale de la documentación pública de Meta tal como
> se conoce y del código que ya funciona. Lo que no está verificado dice **«a confirmar en la
> documentación de Meta»** y pasa a `TODO.md` §25. Referencias: *Cloud API › Messages reference*
> (`developers.facebook.com/docs/whatsapp/cloud-api/reference/messages`), *Send message templates*
> (`…/cloud-api/guides/send-message-templates`), *Webhooks › messages*
> (`…/cloud-api/webhooks/components`), *Business Management API › Message templates*
> (`…/business-management-api/message-templates`).

| Operación | Endpoint | Auth | Parte |
|---|---|---|---|
| Enviar texto | `POST {WHATSAPP_GRAPH_URL}/{WHATSAPP_GRAPH_VERSION}/{phone_number_id}/messages` con `{"messaging_product":"whatsapp","to":…,"type":"text","text":{"body":…}}` — ya implementado | `Authorization: Bearer <token de la empresa>` (de `integrations`) | A |
| Enviar plantilla | Mismo endpoint, `"type":"template","template":{"name":…,"language":{"code":"es_AR"},"components":[{"type":"body","parameters":[{"type":"text","text":…}]}]}`. Parámetros **posicionales** (`{{1}}`, `{{2}}`…) en el orden en que se registró la plantilla. Parámetros con nombre (`parameter_name`): **a confirmar en la documentación de Meta**. `es_AR` como código de idioma: **a confirmar** | Ídem | B |
| Respuesta exitosa | `200` con `messages[0].id` (`wamid…`), que ya se guarda en `mensaje.externo_id` | — | A |
| Estado de plantillas | `GET /{version}/{waba_id}/message_templates` → `data[].name`, `language`, `status` (`APPROVED`, `PENDING`, `REJECTED`, …). Valores exactos y paginación: **a confirmar**. El `waba_id` ya se guarda en `integrations` (`CLAVE_WABA_ID`) | Ídem | B |
| Callback de entrega | Mismo webhook `POST /webhooks/whatsapp/{empresa}`, `entry[].changes[].value.statuses[]` con `id` (wamid), `status` (`sent`/`delivered`/`read`/`failed`), `timestamp`, `recipient_id`, `errors[]` en `failed`. Forma de `errors[]`: **a confirmar** | Firma HMAC-SHA256 con el App Secret (`X-Hub-Signature-256`) — ya implementada | B |

**Ambientes.** Meta no tiene un host de sandbox aparte: el «sandbox» es un número de prueba de una app
de desarrollo contra el mismo `graph.facebook.com`.

| Ambiente | `WHATSAPP_ADAPTADOR` | Canal real | Qué pasa |
|---|---|---|---|
| Tests (CI y local) | — | `httpx.MockTransport` inyectado | **Nunca hay red** |
| Local / staging hoy | `simulado` | `MensajeriaSimulada` | El mensaje queda en un log sin datos personales; el recordatorio se registra `ENVIADO` (igual que hoy) |
| Staging con sandbox (TODO §25) | `meta` | `MensajeriaWhatsApp` contra el número de prueba | Solo llega a los destinatarios dados de alta en la app de prueba (cantidad: **a confirmar**) |
| Producción | `meta` (obligatorio, `settings.py:328`) | `MensajeriaWhatsApp`, o `SinCanal` si la empresa no conectó WhatsApp | `simulado` está prohibido |

**Modos de falla y qué hace el sistema.**

| Falla | Respuesta de Meta | Recordatorio de cobro | Aviso de turno |
|---|---|---|---|
| Fuera de la ventana de 24 h con texto libre | 4xx; código de error **a confirmar** (se cita 131047, «re-engagement message») | `FALLIDO`, sin reintento, se loguea el código | Se loguea, el turno sigue |
| Número inválido / no es de WhatsApp | 4xx | `FALLIDO` | Se loguea |
| Token vencido o revocado | 401 | `FALLIDO` (la desactivación de la integración es de HU-E2-03, no de acá) | Se loguea |
| Límite de tasa | 429 (4xx: hoy **no** se reintenta) | `FALLIDO` | Se loguea |
| Meta caída / timeout | 5xx o timeout × 3 | `FALLIDO` (pregunta P6) | Se loguea |
| Empresa sin WhatsApp conectado (producción) | — (no se llama) | `FALLIDO` | Se omite, sin error |
| Cliente sin teléfono | — (no se llama) | `FALLIDO` | Se omite (HU-E7-02 RN-03 «si tiene número») |

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero → el monto **se muestra** en el texto: test de formato con `Decimal` (`1234.5` →
      dos decimales, `ROUND_HALF_UP`), nunca `float`.
- [ ] Toca comprobantes fiscales / CAE → No aplica.
- [ ] Consume un webhook → **No aplica en A** (A no lee callbacks). **Obligatorio en B:** un mismo
      `statuses[]` entregado dos veces produce un solo efecto, y un `delivered` que llega después de
      `read` no retrocede el estado (`Mensaje.marcar_entrega` ya no retrocede; `Recordatorio.marcar_entrega`
      sí acepta cualquier orden y hay que decidir cuál vale).
- [ ] Agrega datos con `empresa_id` → No agrega tablas en A. El canal se arma con la integración de la
      empresa de la unidad de trabajo: test de que la empresa A nunca usa el token de la B.
- [ ] Usa salida de un LLM → No aplica.
- [ ] Datos personales → **ningún log de los adaptadores nuevos registra teléfono, nombre ni el
      texto del mensaje** (test con captura de logs, como `test_registra_la_clase_de_aviso_y_no_el_telefono`).
      No se envía nada a un LLM.
- [ ] **Red en tests** → todo test usa `httpx.MockTransport` o un canal falso; ningún test resuelve
      `graph.facebook.com`.
- [ ] **Un fallo del canal no voltea la operación** → test de cancelación de turno con Meta en 500 y de
      barrido con un cobro cuyo envío falla seguido de otro que sale.

## Archivos a tocar (parte A)

- [ ] `backend/src/cheatsheet/api/mensajeria.py` (nuevo: `armar_mensajeria`, `SinCanal` en producción)
- [ ] `backend/src/cheatsheet/api/conversacional.py` (importa de `mensajeria.py`; `armar_agenda` async)
- [ ] `backend/src/cheatsheet/api/mercadopago.py` (`armar_envio` async → `EnvioPorWhatsApp`; `armar_contactos`)
- [ ] `backend/src/cheatsheet/api/agenda.py` (`armar_notificador`/`armar_avisador` async → `AvisoPorWhatsApp`)
- [ ] `backend/src/cheatsheet/api/routers/agenda.py` (tres `await armar_avisador`)
- [ ] `backend/src/cheatsheet/api/routers/whatsapp.py`, `backend/src/cheatsheet/api/routers/conversaciones.py` (`await armar_agenda`)
- [ ] `backend/src/cheatsheet/workers/tasks_payments.py` (`await armar_envio(unidad, …)`)
- [ ] `backend/src/cheatsheet/contexts/payments/application/ports.py` (`PortContactoDeCliente`, `ContactoDeCobro`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/clientes.py` (`contacto_de` sobre `master_data`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/envio.py` (`EnvioPorWhatsApp`, `CanalDeTexto`, texto; sale `EnvioPorConsola`)
- [ ] `backend/src/cheatsheet/contexts/scheduling/infrastructure/avisos.py` (`AvisoPorWhatsApp`; sale `AvisoPorConsola`)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/canal.py` (`SinCanal`, código de error de Meta en el log)
- [ ] `backend/src/cheatsheet/contexts/conversational/application/errors.py` (`CanalNoConectado`)
- [ ] `backend/tests/contexts/payments/infrastructure/test_envio.py` (nuevo)
- [ ] `backend/tests/contexts/scheduling/infrastructure/test_avisos.py` (reescrito)
- [ ] `backend/tests/contexts/conversational/infrastructure/test_canal.py` (`SinCanal`, código de error)
- [ ] `backend/tests/api/test_canal_real_de_whatsapp.py` (nuevo: cableado del composition root)
- [ ] `render.yaml` (API: `WHATSAPP_WEBHOOK_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN` `sync: false`, `WHATSAPP_ADAPTADOR`; worker: `WHATSAPP_ADAPTADOR`)
- [ ] `docs/staging-deployment.md` §3 y §4 bis.2
- [ ] `docs/configuration-management.md` (bloque de variables de WhatsApp)
- [ ] `backend/.env.example` (verificar y completar)
- [ ] `docs/adr/0011-outbound-whatsapp-channel-via-composition-root.md` (de «Proposed» a «Accepted» al aprobarse) y `docs/adr/README.md` (índice)
- [ ] `docs/architecture.md` §4 (fila del ADR-0011) y §7 (`PortMensajeria` consumido también por payments y scheduling vía composition root)
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#11 cerrado; #3 con la configuración de Render)
- [ ] `docs/aidlc/units.md` (fila de esta unidad; fila de B si se aprueba P1)
- [ ] `docs/aidlc/TODO.md` — sección nueva **§25. WhatsApp (sandbox)**, con el formato de §20–21:

| # | Qué verificar | Unidad | Qué pasa si falla |
|---|---|---|---|
| 25.1 | Un texto libre iniciado por la empresa fuera de la ventana de 24 h se rechaza, con qué HTTP y qué `error.code` (¿131047?) | `canal-real-de-whatsapp` | Si Meta lo acepta, B pierde urgencia; si el código es otro, se ajusta el log |
| 25.2 | Formato del número argentino que acepta `to`: con o sin `+`, y con o sin el `9` de celular (`549…` vs `54…`) contra lo que guarda `master_data` | `canal-real-de-whatsapp` | Todos los envíos a celulares argentinos fallan: hay que normalizar en el adaptador |
| 25.3 | Qué responde un 429 y si conviene reintentarlo con espera en lugar de tratarlo como rechazo | `canal-real-de-whatsapp` | Un pico de recordatorios queda `FALLIDO` en lugar de salir más tarde |
| 25.4 | El cuerpo de `messages[0].id` del envío real coincide con el `id` de `statuses[]` del callback | `plantillas-y-entregas-de-whatsapp` | No se pueden atar los callbacks al mensaje |
| 25.5 | Forma del envío `type: template`: posicionales vs `parameter_name`, código de idioma `es_AR`, respuesta ante plantilla no aprobada | `plantillas-y-entregas-de-whatsapp` | Ninguna plantilla sale |
| 25.6 | `GET /{waba_id}/message_templates`: valores de `status`, paginación, y si llega el webhook `message_template_status_update` | `plantillas-y-entregas-de-whatsapp` | El estado de aprobación no se puede leer y todo sale como texto |
| 25.7 | Un `failed` trae `errors[]` con código y título legibles | `plantillas-y-entregas-de-whatsapp` | PAN-COB-02 muestra `FALLIDO` sin motivo |
| 25.8 | Punta a punta en staging: registrar `/webhooks/whatsapp/{empresa}` en la app de Meta con `WHATSAPP_WEBHOOK_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN` cargados (pendiente #3) | ambas | Toda notificación se descarta con 200 (D49) |

## Casos de prueba (parte A)

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — Un recordatorio de cobro hoy nunca llega a `MensajeriaWhatsApp`: con `WHATSAPP_ADAPTADOR=meta` y un canal `MensajeriaWhatsApp` sobre `MockTransport`, despachar el paso 1 de un cobro vencido no produce ningún `POST …/messages` (hoy `armar_envio` arma `EnvioPorConsola`). Pasa a GREEN con un `POST` cuyo `to` es el teléfono del cliente | integración (composition root) | pendiente |
| 2 | **RED** — Cancelar un turno desde el panel no llega a la Cloud API (hoy `armar_notificador` arma `AvisoPorConsola`) | integración (composition root) | pendiente |
| 3 | **RED** — En producción, cancelar el turno de una empresa sin WhatsApp conectado no levanta `RuntimeError` (hoy `MensajeriaSimulada(PRODUCTION)` levanta) y el turno queda cancelado | unit (composition root) | pendiente |
| 4 | El texto del recordatorio lleva nombre, concepto, monto con dos decimales (`Decimal`, `ROUND_HALF_UP`) y el link del cobro | unit | pendiente |
| 5 | Cobro sin link (transferencia) → el texto no incluye la línea del link ni `None` | unit | pendiente |
| 6 | Cliente sin teléfono → `FALLIDO`, ningún `POST`, ninguna excepción | unit | pendiente |
| 7 | Paso de la cadena con canal `EMAIL` → `FALLIDO` sin llamar a Meta, log `recordatorio_canal_sin_adaptador` | unit | pendiente |
| 8 | Meta responde 400 → `FALLIDO`, **un solo** `POST`, y el barrido sigue con el cobro siguiente, que sí sale | unit + caso de uso | pendiente |
| 9 | Meta responde 503 tres veces → `FALLIDO` tras 3 `POST`; el paso queda registrado y el barrido siguiente **no** lo reenvía (D25) | caso de uso | pendiente |
| 10 | Reserva, cancelación y reprogramación mandan su texto (la reprogramación con horario nuevo y anterior) al teléfono del cliente | unit | pendiente |
| 11 | Meta en 500 durante una cancelación → el turno queda cancelado, la bitácora lo registra, el request responde OK | integración | pendiente |
| 12 | La corrección a posteriori (HU-E7-02 RN-07) sigue sin mandar mensaje | regresión | pendiente |
| 13 | Ningún log de `EnvioPorWhatsApp`, `AvisoPorWhatsApp` ni del 4xx de `MensajeriaWhatsApp` contiene teléfono, nombre ni el texto | unit (captura de logs) | pendiente |
| 14 | El 4xx de Meta registra `error.code` del cuerpo (y nada si el cuerpo es ilegible) | unit | pendiente |
| 15 | Dos empresas en el mismo proceso: cada canal usa el token y el `phone_number_id` de su empresa | integración | pendiente |
| 16 | `MensajeriaSimulada` detrás del adaptador real: el recordatorio queda `ENVIADO` en staging, como hoy | unit | pendiente |
| 17 | `guard_architecture --scan` y `.claude/hooks/test_guards.sh` pasan: ningún import nuevo entre contextos | gate | pendiente |

Gates de Gate 2: `ruff format --check . && ruff check . && mypy . && pytest` (cobertura ≥ 80 %).
Frontend: no se toca.

## Parte B — `plantillas-y-entregas-de-whatsapp` (listada, no planificada)

Depende de A. ≈ 10,5 h. Responsable a definir con el equipo (excede el presupuesto de Luciano).

1. `MensajeriaWhatsApp.enviar_plantilla(telefono, nombre, idioma, parametros)` con el contrato de
   arriba y sus tests de contrato (`MockTransport`).
2. Mapa por código (`turno_confirmado`, `turno_cancelado`, `turno_reprogramado`,
   `recordatorio_de_cobro`, `cobro_generado`, `recordatorio_de_turno`) → nombre de plantilla en Meta y
   orden de los parámetros. Los adaptadores mandan **plantilla si está `APROBADA`**, texto si no
   (HU-E11-02 RN-04; pendiente #13: conectar `armar_plantillas`).
3. Estado de aprobación (pregunta P5): lectura de `GET /{waba_id}/message_templates` con
   `WHATSAPP_ADAPTADOR=meta`; con `simulado`, fuera de producción, las plantillas se tratan como
   `APROBADA`. Cierra el pendiente #9 en su parte de «recibir su estado».
4. Callbacks de entrega (pendiente #4): rama `statuses[]` en `api/routers/whatsapp.py`; caso de uso
   en `conversational` sobre `Mensaje.marcar_entrega`; caso de uso en `payments` sobre
   `Recordatorio.marcar_entrega` con migración `recordatorio.externo_id` (índice único) y
   `PortEnvioDeRecordatorio` devolviendo también el `wamid`. Test de entrega duplicada.
5. Decisión abierta para B: los avisos de turno no se guardan en ninguna tabla, así que no tienen
   dónde registrar su estado de entrega (HU-E8-04 RN-04).

**Fuera de las dos partes:** el recordatorio de turno (pendiente #7: regla `AGENDA_DE_NOTIFICACION` +
barrido nuevo). Por eso **HU-E8-04 no cierra entera**: su RN-02 en la parte «recordatorios de turno»
queda pendiente. Hay que avisarlo al equipo.

## Preguntas del Gate 1 (con recomendación)

| # | Pregunta | Recomendación |
|---|---|---|
| P1 | ¿Partir en A (adaptadores + texto, ≈ 8,5 h) y B (plantillas + callbacks, ≈ 10,5 h), y planificar solo A? | **Sí.** El total duplica el presupuesto. Aviso explícito: con A sola, en producción, los mensajes fuera de la ventana de 24 h quedan `FALLIDO` |
| P2 (D5) | ¿Se incluye el envío de plantillas (`type: template`) para los mensajes iniciados por la empresa? | **Sí, en B.** Sin plantillas, recordatorios y confirmaciones del panel no llegan fuera de la ventana |
| P3 (D6) | ¿Se incluyen los callbacks de entrega (pendiente #4)? ¿Y el recordatorio de turno (pendiente #7)? | **Callbacks sí, en B. Recordatorio de turno no** (regla + barrido nuevos). Decirle al equipo que HU-E8-04 no cierra entera |
| P4 (P8) | Sin sandbox de Meta antes del Gate 2, ¿se cierra con HTTP simulado? | **Sí:** `httpx.MockTransport` en todos los tests y lo que necesita sandbox va a `TODO.md` §25 «WhatsApp (sandbox)» |
| P5 | ¿Cómo pasa una plantilla a `APROBADA` sin Meta? | **Lo más chico:** con `meta`, se lee de la lista de plantillas de Meta; con `simulado` y fuera de producción, un adaptador simulado las da por aprobadas. Nunca la carga a mano un administrador (sería inventar la respuesta del proveedor, pendiente #9) |
| P6 | Si Meta está caída (5xx/timeout tras 3 intentos), ¿el paso del recordatorio queda `FALLIDO` y la cadena sigue con el próximo paso? | **Sí.** Es visible en PAN-COB-02 y no reescribe D25. La alternativa —dejar el paso sin `enviado_en` para reintentarlo— choca con el índice único `(cobro_id, paso)`, que hoy lo dejaría trabado para siempre |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- (vacío hasta el Gate 1)
