# Unidad: canal-real-de-whatsapp

**HUs**: HS-T3, HU-E7-02, HU-E7-06, HU-E8-04 (parte de texto; cierran de punta a punta con U6–U8)   **Contexto dueño**: conversational (+ payments y scheduling, cableados por el composition root)   **Rama**: feature/conversational-canal-real-de-whatsapp

> Origen: [`../etapa-6/reparto.md`](../etapa-6/reparto.md) §2, «Unidades de código pendientes» —
> responsable Luciano, revisa Cristian. Es la **primera de cuatro unidades en secuencia** que forman
> el canal saliente de WhatsApp (decisiones G4a–G4h del 2026-10-04):
>
> | # | Unidad | Qué agrega | Depende de |
> |---|---|---|---|
> | **U5** | `canal-real-de-whatsapp` (esta) | Recordatorios de cobro y avisos de turno como **texto** por el cliente real; `SinCanal` en producción; H1 y H2; configuración y docs | ADR-0011 aceptado |
> | U6 | `plantillas-de-whatsapp-en-meta` | Envío de plantillas a Meta y lectura de su estado; mensajes `type: template` fuera de la ventana de 24 h (pendientes #9 y #13) | U5 |
> | U7 | `entregas-de-whatsapp` | Callbacks `statuses[]` para mensajes, recordatorios y avisos de turno; reintento acotado de transitorios (pendiente #4) | U5 (U6 para plantillas) |
> | U8 | `recordatorio-de-turno` | Regla `AGENDA_DE_NOTIFICACION` tipada, barrido de scheduling con Beat (pendiente #7) | U6 |
>
> Cierra el pendiente #11 del épico 8
> ([`../epicas/08-agente-de-whatsapp/pendientes.md`](../epicas/08-agente-de-whatsapp/pendientes.md)) y
> deja la configuración del #3. Requiere el
> [ADR-0011](../../adr/0011-outbound-whatsapp-channel-via-composition-root.md) (PR #62, «Proposed»):
> **este Gate 1 no puede cerrarse hasta que el equipo lo acepte.**

## Qué hace

Hoy ningún recordatorio de cobro ni aviso de turno sale por WhatsApp: los dos van a un log
(`EnvioPorConsola`, `AvisoPorConsola`) y los dos se niegan a arrancar en producción. Esta unidad los
reemplaza por adaptadores que mandan el mensaje como texto por el cliente real de la Cloud API que
ya existe en `conversational` (`MensajeriaWhatsApp`), cableado en el composition root sin que ningún
contexto importe a otro (ADR-0011). Un fallo de Meta nunca voltea la operación: el turno se cancela
igual y el recordatorio queda registrado como `FALLIDO`.

Además arregla dos defectos del camino de envío que, con un canal real, mandarían mensajes
duplicados o dejarían escapar errores crudos:

- **H1 — un fallo en el cobro K deshace los cobros 1..K-1 que ya salieron.** El barrido vence y
  despacha en **una sola transacción por empresa** (`workers/tasks_payments.py:62-94`) y
  `_despachar_uno` llama a `envio.enviar` sin `try` (`payments/application/recordatorios.py:185-187`).
  Si algo falla en el cobro K, la excepción sale del cuerpo del `async for` y la unidad de trabajo
  descarta todo (la trampa documentada en `api/dependencies.py:114-119`): las filas de los cobros
  anteriores desaparecen, sus mensajes ya salieron, y **el barrido de la hora siguiente los vuelve a
  mandar — un duplicado por hora**. El docstring de la clase (`recordatorios.py:102-104`) promete
  justo lo contrario.
- **H1b — un `RecordatorioDuplicado` envenena la transacción del barrido.**
  `RepositorioRecordatoriosPostgres.agregar` (`payments/infrastructure/repositories.py:285-306`)
  atrapa el `IntegrityError` del índice `(cobro_id, paso)` **sin savepoint**: en PostgreSQL la
  transacción queda abortada y SQLAlchemy exige `rollback`, así que el «no es un error, seguí»
  de `recordatorios.py:179-183` en la práctica tira el barrido entero. El test actual
  (`tests/integracion/test_cobros_postgres.py:236-260`) sólo afirma que la excepción sale, no que la
  sesión siga usable. Hallazgo por semántica de SQLAlchemy/PostgreSQL; el caso 3 lo confirma en CI.
  Entra acá porque el savepoint por cobro de H1 no puede atrapar ese error adentro sin resolverlo.
- **H2 — `MensajeriaWhatsApp.enviar` (`conversational/infrastructure/canal.py:103-133`)**: el `post`
  no tiene `try` (un `httpx.ConnectError` o `ReadTimeout` sale crudo, no como
  `MensajeriaNoDisponible`); no espera entre los 3 intentos aunque el docstring (`:88`) diga
  «backoff»; un 429 cae en la rama «4xx no se reintenta» (`:125-130`); y un timeout de lectura, si se
  reintentara, podría mandar el mismo mensaje dos veces.

### Lo que U5 cierra y lo que no, dicho de frente

| Cierra U5 | Lo cierra otra unidad |
|---|---|
| El recordatorio de cobro y los avisos de reserva, cancelación y reprogramación **llegan a la Cloud API** con el token y el número de la empresa | Fuera de la ventana de 24 h Meta sólo acepta plantillas aprobadas (error 131047, verificado). **Hasta U6, en producción, un recordatorio o un aviso iniciado por la empresa fuera de la ventana queda `FALLIDO`** — registrado y visible en PAN-COB-02, nunca silencioso |
| Un fallo del canal nunca voltea un turno ni un barrido, y nunca reenvía lo que ya salió (H1, H1b) | El estado de entrega real (`delivered`, `read`, `failed` asíncrono) — **U7** |
| Errores clasificados en transitorios (reintentados dentro de la llamada, con espera) y permanentes (no reintentados), con el código de Meta en el log (H2) | El reintento **entre barridos** de un transitorio agotado — **U7** (decisión G4f) |
| Producción sin WhatsApp conectado: `SinCanal`, el turno se cancela y el recordatorio queda `FALLIDO`; nunca un 500 | El recordatorio de turno — **U8** |
| Render, documentación de configuración, `.env.example`, `TODO.md` §25 | Los textos configurables de PAN-CFG-NOT en los adaptadores (pendiente #13) — **U6** |

HS-T3 (RN-02 y RN-04), HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04 y HU-E8-04 quedan **cerradas de punta a
punta con U5–U8**, no con U5 sola (mensaje M6 al equipo). No es un recorte por tiempo: es el orden de
dependencias del canal.

## Lo que existe hoy (relevado sobre develop, 2026-10-04)

- `api/mercadopago.py:143-151` — `armar_envio(settings)` devuelve siempre `EnvioPorConsola`. Lo usa
  únicamente el barrido `workers/tasks_payments.py:81` (`barrer_empresa`, `:62-94`).
- `api/agenda.py:61-69` — `armar_notificador(settings)` devuelve siempre `AvisoPorConsola`;
  `armar_avisador` (`:72-84`) lo usa, y lo llaman `api/routers/agenda.py:582, 621, 645` y el agente
  (`api/conversacional.py:174`, dentro de `armar_agenda`, `:157-179`).
- `api/conversacional.py:97-131` — `armar_mensajeria` (async) elige entre `MensajeriaSimulada`
  (`WHATSAPP_ADAPTADOR=simulado` `:108-109`, empresa sin WhatsApp conectado `:113-115`, o sin
  `phone_number_id` `:119-121`) y `MensajeriaWhatsApp` con token y `phone_number_id` leídos de
  `integrations` por unidad de trabajo. La importan `api/routers/whatsapp.py:41` (usada en `:150`) y
  `api/routers/conversaciones.py:23` (usada en `:287`). `armar_agenda` la llama **un solo** router:
  `api/routers/whatsapp.py:152`, en el mismo `_procesar` que ya armó la mensajería (`:150`).
  *(El plan anterior listaba también `conversaciones.py` como llamador de `armar_agenda`: no lo es.)*
  `armar_plantillas` (`:182-189`) está definida y **nadie la llama** (pendiente #13, va a U6).
- `contexts/conversational/infrastructure/canal.py:85-133` — `MensajeriaWhatsApp`: timeout
  explícito, `INTENTOS = 3` (`:43`), transporte `httpx` inyectable, sólo `type: text`. Ver H2.
- **No existe ningún test de `MensajeriaWhatsApp`**: no hay `tests/.../test_canal.py` (el plan
  anterior lo daba por existente). Sólo `MensajeriaSimulada` aparece en
  `tests/contexts/conversational/infrastructure/test_interprete.py:168-178`.
- **Hallazgo:** `MensajeriaSimulada(Entorno.PRODUCTION)` levanta `RuntimeError` (`canal.py:65-70`).
  Como `armar_mensajeria` la devuelve para una empresa **sin WhatsApp conectado**, en producción
  cancelar un turno de esa empresa daría 500 apenas el aviso deje de ser la consola — lo contrario de
  lo que dice su propio docstring (`conversacional.py:103-106`).
- Quien ya atrapa los fallos del canal en `conversational`: el agente con un `except Exception`
  acotado y justificado (`application/agente.py:384-394`, `noqa: BLE001`) y el operador, que lo
  convierte en `MensajeriaNoDisponible` (`application/atencion.py:220-227`). Las excepciones
  tipadas nuevas **heredan de `MensajeriaNoDisponible`**, así que ninguno de los dos cambia.
- Firmas distintas, cada una correcta bajo R3: `PortEnvioDeRecordatorio.enviar(empresa_id, cobro,
  canal, paso) -> EstadoEntrega` (`payments/application/ports.py:303-311`) no trae teléfono ni texto;
  `PortNotificadorDeTurnos` (`scheduling/application/ports.py:145-158`) recibe `DatosDeAviso`
  (`:57-70`) con `telefono`.
- `PortClienteDeCobro` (`payments/application/ports.py:344-357`) **no expone el contacto a
  propósito** (D92); su ACL es `ClienteViaMasterData` (`payments/infrastructure/clientes.py:19-27`).
  `scheduling` ya resolvió lo mismo con `PortDirectorioDeClientes.contacto_de`
  (`scheduling/application/ports.py:133-142`) y `ClientesViaMasterData.contacto_de`
  (`scheduling/infrastructure/catalogo.py:88-92`).
- `Avisador` (`scheduling/application/turnos.py:99-150`) promete que «ningún método levanta por no
  poder avisar», pero llama al notificador sin `try`: hoy lo cumple porque la consola no falla. El
  adaptador real tiene que sostener esa promesa **nunca levantando**.
- Savepoints ya usados en el repo: `observability/infrastructure/repository.py:73-84` y
  `master_data/infrastructure/correccion.py:215, 262` (`async with sesion.begin_nested()`). Ninguna
  capa `application/` tiene hoy un puerto transaccional.
- La cadena de escalamiento admite pasos `WHATSAPP`, `EMAIL` y `PANEL`
  (`business_config/domain/regla.py:51-61`); HS-T3 RN-02 dice «por el canal configurado».
- Context Map (`docs/architecture.md` §4, tabla en `:79-92`): no hay arista `conversational →
  payments/scheduling`. La agrega el PR del ADR-0011 al aceptarse, **no esta unidad**. §7
  (`:158`) lista `PortMensajeria` sólo para `conversational`.
- `render.yaml` no declara **ninguna** variable `WHATSAPP_*` (ni API ni worker); el 2026-10-03
  `WHATSAPP_WEBHOOK_SECRET` se creó a mano en Render. `docs/staging-deployment.md` §3 (`:62`) y
  §4 bis.2 (`:135`) no las mencionan. `docs/configuration-management.md:121-124` todavía lista
  `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_ID`, que ya no existen (son por empresa, en `integrations`).
- `platform/settings.py:313-333` — `WHATSAPP_ADAPTADOR` obligatorio en producción y `simulado`
  prohibido ahí; `:539-549` — `WHATSAPP_GRAPH_URL`, `WHATSAPP_GRAPH_VERSION` (`v21.0`),
  `WHATSAPP_TIMEOUT_SEGUNDOS` (10), `WHATSAPP_WEBHOOK_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
- `backend/.env.example` **no se pudo leer** en este relevamiento (permiso denegado). Se verifica al
  implementar que documente `WHATSAPP_ADAPTADOR`, `WHATSAPP_WEBHOOK_SECRET` y
  `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.

## Diseño

- **Dominio**: sin cambios. `EstadoEntrega` y `Recordatorio` ya tienen `ENVIADO` y `FALLIDO`;
  `DatosDeAviso` no cambia.
- **Aplicación**:
  - `payments/application/ports.py`:
    - `PortContactoDeCliente.contacto_de(cliente_id) -> ContactoDeCobro | None` (nombre y teléfono).
      **Puerto aparte y no un método más en `PortClienteDeCobro`**, para no deshacer D92: el caso de
      uso de cobros sigue sin ver el contacto; sólo el adaptador de envío lo recibe. Mismo patrón que
      `scheduling`.
    - `PortAislamiento.aislar() -> AbstractAsyncContextManager[None]`: «lo que pase adentro se
      confirma o se deshace solo, sin tocar el resto de la transacción». Es la forma de pedir un
      savepoint sin que `application/` importe SQLAlchemy (R2).
  - `payments/application/errors.py`: `DespachoNoPersistido` — lo que el adaptador del aislamiento
    levanta cuando la base rechazó algo dentro del savepoint.
  - `DespacharRecordatorios` (`recordatorios.py:95-204`), **arreglo de H1**:
    - Recibe `aislamiento: PortAislamiento`. Cada cobro de `ejecutar` corre en
      `async with self._aislamiento.aislar():` y un `DespachoNoPersistido` se registra
      (`recordatorio_no_persistido`, `cobro_id`, sin datos personales) y el bucle sigue: sólo se
      deshacen las filas de **ese** cobro.
    - `_despachar_uno` **protege el envío**: `enviar` va en `try`; ante cualquier excepción el estado
      es `FALLIDO` y la fila se guarda igual con `enviado_en`, para que el índice `(cobro_id, paso)`
      no lo deje salir de nuevo. Es un `except Exception` con `noqa: BLE001` justificado en el
      comentario, igual que `agente.py:388`: el puerto lo implementan adaptadores que podrían
      levantar cualquier cosa, y el contrato ya dice que no deben. Es defensa en profundidad; el
      adaptador real nunca levanta.
    - Se reescribe el docstring de la clase para que diga lo que el código hace: savepoint por
      cobro, envío protegido, y el único caso residual de reenvío (ver Riesgos).
    - Sin cambio de firma pública más allá del colaborador nuevo; su único llamador es
      `workers/tasks_payments.py:78-84`.
- **Puertos y adaptadores**:
  - `conversational/application/errors.py` — excepciones tipadas, todas subclases de
    `MensajeriaNoDisponible` (así `agente.py` y `atencion.py` no cambian) y con `codigo: int | None`
    (el `error.code` de Meta):
    - `MensajeRechazado` — permanente: Meta contestó y no lo va a aceptar aunque se reintente.
    - `MensajeriaSaturada` — transitorio agotado: 5xx, 429 o código de throttling después de los 3
      intentos, o sin conexión.
    - `EnvioIncierto` — el pedido pudo haber llegado y no se sabe (timeout de lectura, conexión
      cortada a mitad de respuesta). **No se reintenta.**
    - `CanalNoConectado` — la empresa no conectó WhatsApp (producción); no se tocó la red.
  - `conversational/infrastructure/canal.py`, **arreglo de H2** en `MensajeriaWhatsApp`:
    - Constructor con `esperar: Callable[[float], Awaitable[None]] = asyncio.sleep` inyectable: los
      tests pasan un registrador y **nunca esperan de verdad**.
    - Espera entre intentos: `ESPERAS = (1.0, 2.0)` segundos (exponencial, sin variable de entorno
      nueva). Peor caso en un request del panel: 3 × `WHATSAPP_TIMEOUT_SEGUNDOS` de conexión + 3 s.
    - Clasificación, **por `error.code` primero** (Meta pide manejar errores por código y no por
      status HTTP) y por status cuando el cuerpo no trae código:

      | Situación | Clase | ¿Se reintenta en la llamada? |
      |---|---|---|
      | `httpx.ConnectError`, `httpx.ConnectTimeout`, `httpx.PoolTimeout` (el pedido no salió) | transitorio | Sí |
      | 5xx sin código, 429 sin código | transitorio | Sí |
      | Código 4, 80007, 130429, 131056 (límites de tasa), 131000 (desconocido), 131016 (servicio no disponible) | transitorio | Sí |
      | `httpx.ReadTimeout`, `WriteTimeout`, `ReadError`, `RemoteProtocolError` (pudo haber llegado) | incierto | **No** → `EnvioIncierto` |
      | Código 131047 (fuera de ventana), 131026 (no entregable), 132001 (plantilla inexistente o no aprobada), 131048, 131049, 133010, 131042, 368 | permanente | No → `MensajeRechazado` |
      | Código 0, 3, 190 o status 401/403 (token o permisos) | permanente | No → `MensajeRechazado` |
      | Cualquier otro 4xx | permanente | No |

    - Log sin datos personales: `whatsapp_rechazo_el_mensaje` con `estado` (HTTP), `codigo`
      (`error.code`) y `fbtrace_id`; **nunca** `error.message` ni `error_data.details` (pueden traer el
      número) ni el teléfono ni el texto. Si el cuerpo no es JSON legible, `codigo=None`.
    - El cuerpo del bucle se parte en funciones chicas (`_intentar`, `_clasificar`) para respetar ≤ 50
      líneas y complejidad ≤ 10. `canal.py` pasa de 221 a ≈ 320 líneas, bajo el tope de 400.
    - `SinCanal`: el adaptador de producción para una empresa sin WhatsApp conectado; levanta
      `CanalNoConectado` sin tocar la red.
  - `payments/infrastructure/envio.py`: `EnvioPorWhatsApp(canal, contactos)` implementa
    `PortEnvioDeRecordatorio`. Arma el texto de fábrica de `recordatorio_de_cobro` (nombre, concepto
    —`Cobro.descripcion`—, monto con `Decimal` cuantizado a 2 decimales con `ROUND_HALF_UP`, link si
    el cobro tiene uno activo), llama a `canal.enviar(telefono=…, texto=…)` y devuelve `ENVIADO`.
    Devuelve `FALLIDO` sin llamar a Meta si el cliente no tiene teléfono o si el paso no es
    `WHATSAPP` (log `recordatorio_canal_sin_adaptador`, ver pregunta 1). **Nunca levanta**: cualquier
    excepción del canal → `FALLIDO` y log `recordatorio_fallido` con la clase de la excepción
    (`type(exc).__name__`). El `except` es amplio con `noqa: BLE001` justificado, **porque el
    adaptador no puede importar las excepciones de `conversational`** (R3 y ADR-0011 descarta la
    alternativa C); el código de Meta ya quedó en el log del canal. `canal` es un `Protocol` local del
    módulo (`CanalDeTexto`), no un import de `conversational`.
    *(Corrige el plan anterior, que decía «atrapa `MensajeriaNoDisponible`/`CanalNoConectado`»:
    eso exigiría el import que el ADR descarta.)*
  - `payments/infrastructure/clientes.py`: `ContactoViaMasterData.contacto_de` sobre
    `PortRepositorioCliente` de `master_data` (`payments → master_data` ya está permitido, C/S).
  - `payments/infrastructure/aislamiento.py` (nuevo): `AislamientoConSavepoint(sesion)` —
    `async with sesion.begin_nested(): yield`, y un `SQLAlchemyError` adentro sale como
    `DespachoNoPersistido`. `Cobros.armar` (`ensamblado.py:29-44`) gana el campo `aislamiento`.
  - `payments/infrastructure/repositories.py`, **arreglo de H1b**: `agregar` hace su `flush` dentro de
    su propio `begin_nested()` (mismo patrón que `observability/infrastructure/repository.py:78`),
    así el `RecordatorioDuplicado` deja la sesión usable. Savepoint anidado dentro del del cobro:
    PostgreSQL lo admite.
  - `scheduling/infrastructure/avisos.py`: `AvisoPorWhatsApp(canal)` implementa
    `PortNotificadorDeTurnos` reusando `texto_de_reserva/cancelacion/reprogramacion` (`:27-56`).
    **Nunca levanta**: cualquier excepción del canal → log `aviso_de_turno_fallido` (clase de aviso y
    clase de excepción, sin datos personales) y vuelve. Mismo `except` justificado y mismo
    `Protocol` local que en payments. La corrección a posteriori ya no llama al avisador
    (HU-E7-02 RN-07); no cambia.
  - `EnvioPorConsola` y `AvisoPorConsola` salen de `src/`: el doble de staging pasa a ser
    `MensajeriaSimulada` detrás del adaptador real. `tests/.../test_avisos.py` se reescribe contra
    `AvisoPorWhatsApp` con un canal falso.
- **Composition root** (`backend/src/cheatsheet/api/`):
  - `api/mensajeria.py` (nuevo): `armar_mensajeria` se muda acá desde `api/conversacional.py` para no
    crear el ciclo `conversacional → agenda → conversacional`. Con `meta` en producción y sin
    integración o sin `phone_number_id`, devuelve `SinCanal` en lugar de `MensajeriaSimulada`. Fuera
    de producción el comportamiento no cambia.
  - **El canal se arma una vez por unidad de trabajo** (ADR-0011 Decisión §2) y se pasa hacia
    adentro: `armar_envio(unidad, *, canal)` en `api/mercadopago.py`,
    `armar_notificador(canal)` y `armar_avisador(unidad, *, empresa_id, rol, canal)` en
    `api/agenda.py`, `armar_agenda(…, mensajeria)` en `api/conversacional.py`. El único `await` es
    `armar_mensajeria`, en los llamadores: `workers/tasks_payments.py:81`,
    `api/routers/agenda.py:582/621/645`, y `api/routers/whatsapp.py:150-152`, que **reusa** la
    mensajería que ya arma para el agente en lugar de leer la integración dos veces.
    *(Cambio respecto del plan anterior, que volvía `async` a cada builder y hacía que cada uno
    llamara a `armar_mensajeria` por su cuenta: en el webhook eso leía y descifraba la credencial dos
    veces en la misma transacción. El ADR-0011 dice en Consecuencias «three builders become async»;
    hay que alinear esa frase en el PR #62 antes de aceptarlo — ver Riesgos.)*
  - `api/routers/conversaciones.py:23` importa `armar_mensajeria` del módulo nuevo.
- **Otros contextos**: `payments` y `scheduling` reciben el canal de `conversational` **sólo por el
  composition root**; ningún import nuevo entre contextos (R1–R5 intactas, `guard_architecture`
  sin cambios). La fila del Context Map llega con el PR del ADR-0011.
- **Frontend**: No aplica. PAN-COB-02 ya muestra `estado_entrega` de cada recordatorio.

## Infraestructura

- **Migraciones**: No aplica. (U7 agrega `recordatorio.externo_id`; número libre al mergear.)
- **Trabajo asíncrono**: el barrido de cobros (`tasks_payments.barrer_empresa`, cola
  `notifications`, Beat) no cambia de forma: sigue siendo una transacción por empresa, ahora con un
  savepoint por cobro. La idempotencia sigue siendo el índice único `(cobro_id, paso)` (D25). **Los
  avisos de turno siguen saliendo dentro del request del panel**, como hoy el agente; mudarlos al
  worker es la alternativa D del ADR-0011, no esta unidad.
- **Configuración** (no hay variables nuevas; hay variables **no declaradas**):
  - `render.yaml`, servicio `cheatsheet-api`: `WHATSAPP_WEBHOOK_SECRET` y
    `WHATSAPP_WEBHOOK_VERIFY_TOKEN` con `sync: false`; `WHATSAPP_ADAPTADOR` con `value: simulado`
    (staging no tiene credenciales reales de Meta, `docs/staging-deployment.md` §8).
  - `render.yaml`, servicio `cheatsheet-worker`: `WHATSAPP_ADAPTADOR` con el mismo valor — el barrido
    de recordatorios corre en el worker y tiene que elegir el mismo canal que la API.
  - `docs/staging-deployment.md` §3: dos filas (`WHATSAPP_WEBHOOK_SECRET` = el **App Secret** de la
    app de Meta, con el que firma `X-Hub-Signature-256`; `WHATSAPP_WEBHOOK_VERIFY_TOKEN` = el token que
    se escribe al registrar la URL) y la advertencia de que sin el secreto toda notificación se
    descarta con 200 (D49, pendiente #3). §4 bis.2: `WHATSAPP_ADAPTADOR` en el worker.
  - `docs/configuration-management.md:121-124`: reemplazar `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID` por las
    variables reales y una línea que diga que el token y el número son por empresa (HU-E2-03).
  - `backend/.env.example`: verificar (no se pudo leer) y completar si falta.
- **Integraciones externas**: Meta WhatsApp Cloud API, el mismo cliente. Timeout
  `WHATSAPP_TIMEOUT_SEGUNDOS`; 3 intentos con espera sobre transitorios; ninguno sobre permanentes ni
  sobre inciertos (tabla de Diseño).

## Contratos — Meta WhatsApp Cloud API

> Verificado el 2026-10-04 contra *Cloud API › Error codes*
> (`developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes`): títulos y recomendación de
> cada código de la tabla de Diseño, y la forma del error (`error.code`, `error.error_data.details`,
> `error.error_subcode` deprecado, `fbtrace_id`). La página recomienda **manejar los errores por
> `code` y no por status HTTP**, y **no dice con qué status HTTP llega cada código** → eso pasa a
> `TODO.md` §25. Lo que sigue sin verificar dice **«a confirmar»**.

| Operación | Endpoint | Auth |
|---|---|---|
| Enviar texto | `POST {WHATSAPP_GRAPH_URL}/{WHATSAPP_GRAPH_VERSION}/{phone_number_id}/messages` con `{"messaging_product":"whatsapp","to":…,"type":"text","text":{"body":…}}` — ya implementado | `Authorization: Bearer <token de la empresa>` (de `integrations`) |
| Respuesta exitosa | `200` con `messages[0].id` (`wamid…`), que ya se guarda en `mensaje.externo_id` | — |
| Error | `{"error":{"code":…,"error_data":{"details":…},"fbtrace_id":…}}` — se loguean `code` y `fbtrace_id`, nunca `details` | — |

Plantillas, estado de plantillas y callbacks de entrega: contratos de U6 y U7.

**Ambientes.** Meta no tiene un host de sandbox aparte: el «sandbox» es un número de prueba de una app
de desarrollo contra el mismo `graph.facebook.com`.

| Ambiente | `WHATSAPP_ADAPTADOR` | Canal real | Qué pasa |
|---|---|---|---|
| Tests (CI y local) | — | `httpx.MockTransport` inyectado, `esperar` falso | **Nunca hay red ni esperas reales** |
| Local / staging hoy | `simulado` | `MensajeriaSimulada` | El mensaje queda en un log sin datos personales; el recordatorio se registra `ENVIADO` (igual que hoy) |
| Staging con número de prueba (TODO §25) | `meta` | `MensajeriaWhatsApp` contra el número de prueba | Sólo llega a los destinatarios dados de alta en la app de prueba (cantidad: **a confirmar**) |
| Producción | `meta` (obligatorio, `settings.py:316-332`) | `MensajeriaWhatsApp`, o `SinCanal` si la empresa no conectó WhatsApp | `simulado` está prohibido |

**Modos de falla y qué hace el sistema.**

| Falla | Respuesta de Meta | Recordatorio de cobro | Aviso de turno |
|---|---|---|---|
| Fuera de la ventana de 24 h con texto libre | `error.code` 131047 (verificado; status HTTP a confirmar) | `FALLIDO`, sin reintento, se loguea el código. **Se resuelve en U6** | Se loguea, el turno sigue |
| Número que no es de WhatsApp | 131026 | `FALLIDO` | Se loguea |
| Token vencido o revocado | 190 / 0 / 401 | `FALLIDO` (la desactivación de la integración es de HU-E2-03) | Se loguea |
| Límite de tasa | 4, 80007, 130429, 131056 o 429 | 3 intentos con espera; si se agotan, `FALLIDO` (reintento entre barridos: U7) | Ídem, se loguea |
| Meta caída o sin conexión | 5xx, 131000, 131016, `ConnectError` | 3 intentos con espera; si se agotan, `FALLIDO` | Se loguea |
| Timeout de lectura | — (resultado incierto) | `FALLIDO` **sin reintento**: Meta pudo aceptarlo y la Cloud API no ofrece clave de idempotencia; un duplicado es peor que un recordatorio que falta (ADR-0011 §6) | Se loguea |
| Empresa sin WhatsApp conectado (producción) | — (no se llama) | `FALLIDO` | Se omite, sin error |
| Cliente sin teléfono | — (no se llama) | `FALLIDO` | Se omite (HU-E7-02 RN-03 «si tiene número») |

## Lo que depende de terceros

Nada del código de U5 depende de Meta ni de otra persona: todo se prueba con `httpx.MockTransport` y
canales falsos (decisión G4d). Lo que **sólo** se puede verificar con un número de prueba real —la app
de Meta que tiene que crear Cristian (integraciones), mensaje M3— va a `docs/aidlc/TODO.md`, sección
nueva **§25. WhatsApp (sandbox)**, con el formato de §20–21:

| # | Qué verificar | Unidad | Qué pasa si falla |
|---|---|---|---|
| 25.1 | Conseguir la app de Meta con número de prueba y cargar sus credenciales en staging (`integrations`, `WHATSAPP_ADAPTADOR=meta`) — responsable Cristian | U5–U8 | Nada de §25 se puede verificar; el código queda probado sólo contra contratos grabados |
| 25.2 | Un texto libre iniciado por la empresa fuera de la ventana de 24 h vuelve con `error.code` 131047 y **qué status HTTP** | U5 | Si el código llega distinto, se ajusta la tabla de clasificación |
| 25.3 | Formato del número argentino que acepta `to`: con o sin `+`, con o sin el `9` de celular (`549…` vs `54…`) contra lo que guarda `master_data` | U5 | Todos los envíos a celulares argentinos fallan: hay que normalizar en el adaptador |
| 25.4 | Status HTTP con que llegan los códigos de throttling (4, 80007, 130429, 131056) y si traen `Retry-After` | U5 | La clasificación por código los cubre igual; si traen espera sugerida, se evalúa usarla |
| 25.5 | Un `ReadTimeout` provocado (proxy lento) no produce dos mensajes y deja el recordatorio `FALLIDO` | U5 | Riesgo de duplicado no cubierto |
| 25.6 | `messages[0].id` del envío coincide con el `id` de `statuses[]` del callback | U7 | No se pueden atar los callbacks al mensaje |
| 25.7 | Forma del envío `type: template` (posicionales vs `parameter_name`, idioma `es_AR`), respuesta ante plantilla no aprobada (132001) | U6 | Ninguna plantilla sale |
| 25.8 | `GET /{waba_id}/message_templates` y webhook `message_template_status_update` | U6 | El estado de aprobación no se puede leer |
| 25.9 | Un `failed` trae `errors[]` con código legible | U7 | PAN-COB-02 muestra `FALLIDO` sin motivo |
| 25.10 | Punta a punta en staging: registrar `/webhooks/whatsapp/{empresa}` con `WHATSAPP_WEBHOOK_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN` cargados (pendiente #3) | U5 (config) / U7 | Toda notificación se descarta con 200 (D49) |
| 25.11 | Cantidad de destinatarios que admite el número de prueba | U5–U8 | Se planifica la prueba con menos clientes |

U6–U8 agregan sus propias filas al planificarse; esta tabla deja reservadas las que ya se conocen.

## Riesgos que obligan a tests (marcar los que apliquen)

- [x] Toca dinero → el monto **se muestra** en el texto: test de formato con `Decimal` (`1234.5` →
      `1234.50`, `ROUND_HALF_UP`), nunca `float`.
- [ ] Toca comprobantes fiscales / CAE → No aplica.
- [ ] Consume un webhook → No aplica (U7).
- [x] Agrega datos con `empresa_id` → no agrega tablas, pero el canal se arma con la integración de la
      empresa de la unidad de trabajo: test de que la empresa A nunca usa el token de la B.
- [ ] Usa salida de un LLM → No aplica.
- [x] Datos personales → **ningún log de los adaptadores nuevos ni del canal registra teléfono,
      nombre, texto ni `error_data.details`** (captura de logs, como
      `test_registra_la_clase_de_aviso_y_no_el_telefono`).
- [x] **Red en tests** → todo test usa `httpx.MockTransport` o un canal falso, y `esperar` falso;
      ningún test resuelve `graph.facebook.com` ni duerme.
- [x] **Un fallo del canal no voltea la operación ni reenvía lo que ya salió** → H1, H1b y H2 con
      test RED primero.

**Riesgos residuales (documentados, no cubiertos por diseño):**

- Si la base falla **después** de que el mensaje del cobro K salió y **antes** de que su savepoint se
  libere, el savepoint de K se deshace y K se reenvía en el barrido siguiente. Afecta a un solo cobro,
  no a los anteriores; queda escrito en el docstring de `DespacharRecordatorios`.
- Si el `COMMIT` final de la transacción de la empresa falla (pérdida de conexión), se pierde todo lo
  de esa corrida y se reenvía. Es la consecuencia de la decisión G4f (savepoint por cobro dentro de la
  transacción de la empresa); un `COMMIT` que falla después de flushes válidos en READ COMMITTED sólo
  ocurre por caída de la conexión. No se cambia sin decisión del dueño.
- La frase de Consecuencias del ADR-0011 «three builders become async» deja de ser exacta con este
  diseño (sólo `armar_mensajeria` es async; el canal se pasa hacia adentro). Hay que corregirla en el
  PR #62 antes de que el equipo lo acepte, o el plan se adapta a la frase si el equipo la prefiere.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/api/mensajeria.py` (nuevo: `armar_mensajeria`, `SinCanal` en producción)
- [ ] `backend/src/cheatsheet/api/conversacional.py` (sale `armar_mensajeria`; `armar_agenda` recibe la mensajería)
- [ ] `backend/src/cheatsheet/api/mercadopago.py` (`armar_envio(unidad, *, canal)` → `EnvioPorWhatsApp`; `armar_contactos`)
- [ ] `backend/src/cheatsheet/api/agenda.py` (`armar_notificador(canal)`, `armar_avisador(…, canal)` → `AvisoPorWhatsApp`)
- [ ] `backend/src/cheatsheet/api/routers/agenda.py` (tres sitios: `await armar_mensajeria` y se pasa el canal)
- [ ] `backend/src/cheatsheet/api/routers/whatsapp.py` (reusa la mensajería en `armar_agenda`)
- [ ] `backend/src/cheatsheet/api/routers/conversaciones.py` (import desde `api/mensajeria.py`)
- [ ] `backend/src/cheatsheet/workers/tasks_payments.py` (canal por unidad de trabajo; docstring)
- [ ] `backend/src/cheatsheet/contexts/payments/application/ports.py` (`PortContactoDeCliente`, `ContactoDeCobro`, `PortAislamiento`)
- [ ] `backend/src/cheatsheet/contexts/payments/application/errors.py` (`DespachoNoPersistido`)
- [ ] `backend/src/cheatsheet/contexts/payments/application/recordatorios.py` (savepoint por cobro, envío protegido, docstring)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/aislamiento.py` (nuevo: `AislamientoConSavepoint`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/ensamblado.py` (`Cobros.aislamiento`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/repositories.py` (`agregar` con su savepoint — H1b)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/clientes.py` (`ContactoViaMasterData`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/envio.py` (`EnvioPorWhatsApp`, `CanalDeTexto`, texto; sale `EnvioPorConsola`)
- [ ] `backend/src/cheatsheet/contexts/scheduling/infrastructure/avisos.py` (`AvisoPorWhatsApp`; sale `AvisoPorConsola`)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/canal.py` (H2: clasificación, espera inyectable, excepciones de httpx, log con código; `SinCanal`)
- [ ] `backend/src/cheatsheet/contexts/conversational/application/errors.py` (`MensajeRechazado`, `MensajeriaSaturada`, `EnvioIncierto`, `CanalNoConectado`)
- [ ] `backend/tests/contexts/conversational/infrastructure/test_canal.py` (nuevo)
- [ ] `backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py` (H1 con fakes; `AislamientoFalso`)
- [ ] `backend/tests/contexts/payments/infrastructure/test_envio.py` (nuevo)
- [ ] `backend/tests/contexts/scheduling/infrastructure/test_avisos.py` (reescrito)
- [ ] `backend/tests/api/test_canal_real_de_whatsapp.py` (nuevo: cableado del composition root)
- [ ] `backend/tests/integracion/test_barrido_de_recordatorios_postgres.py` (nuevo: H1 y H1b contra PostgreSQL, CI)
- [ ] `render.yaml` (API: `WHATSAPP_WEBHOOK_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN` `sync: false`, `WHATSAPP_ADAPTADOR`; worker: `WHATSAPP_ADAPTADOR`)
- [ ] `docs/staging-deployment.md` §3 y §4 bis.2
- [ ] `docs/configuration-management.md` (bloque de variables de WhatsApp)
- [ ] `backend/.env.example` (verificar y completar)
- [ ] `docs/architecture.md` §7 (`PortMensajeria` consumido también por payments y scheduling vía composition root)
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#11 cerrado; #3 con la configuración de Render; #4, #7, #9, #13 apuntan a U7, U8, U6, U6)
- [ ] `docs/aidlc/units.md` (fila de U5 y filas de U6, U7 y U8 con sus dependencias)
- [ ] `docs/aidlc/TODO.md` (sección nueva §25)

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED (H1)** — Con un envío falso que levanta en el cobro 2 de 3, `DespacharRecordatorios.ejecutar` hoy propaga la excepción. GREEN: no levanta; cobros 1 y 3 `ENVIADO`, cobro 2 registrado `FALLIDO` con `enviado_en` | caso de uso (fakes) | pendiente |
| 2 | **RED (H1, duplicado)** — PostgreSQL: dos `barrer_empresa` seguidos con un envío que falla en el cobro 2 la primera vez. Hoy el cobro 1 recibe **dos** envíos (la primera transacción se deshizo). GREEN: un envío por cobro; y con una falla de base forzada dentro del savepoint del cobro 2, las filas de 1 y 3 sobreviven | integración (CI) | pendiente |
| 3 | **RED (H1b)** — PostgreSQL: con la fila del paso 1 del cobro A ya insertada, el barrido sigue, despacha el cobro B en la misma transacción y confirma | integración (CI) | pendiente |
| 4 | **RED (H2)** — `MockTransport` que levanta `httpx.ConnectError`: hoy sale la excepción de httpx cruda. GREEN: 3 intentos y `MensajeriaSaturada` (subclase de `MensajeriaNoDisponible`) | unit | pendiente |
| 5 | **RED (H2)** — `httpx.ReadTimeout`: **un solo** `POST` y `EnvioIncierto`, sin reintento | unit | pendiente |
| 6 | **RED (H2)** — 503, 503, 200: devuelve el `wamid`, y el `esperar` falso registró `[1.0, 2.0]`; ningún `sleep` real | unit | pendiente |
| 7 | **RED (H2)** — 429 (y 400 con código 130429): hoy un solo `POST`. GREEN: se reintenta | unit | pendiente |
| 8 | Códigos de throttling 4, 80007, 131056 y transitorios 131000, 131016 se reintentan (parametrizado) | unit | pendiente |
| 9 | 131047, 131026, 132001, 190 y 401: **un solo** `POST`, `MensajeRechazado` con su `codigo` (parametrizado) | unit | pendiente |
| 10 | 4xx con cuerpo ilegible → permanente, `codigo=None`; 5xx sin cuerpo → transitorio | unit | pendiente |
| 11 | El log de un rechazo trae `estado`, `codigo` y `fbtrace_id`, y no trae teléfono, texto ni `error_data.details` | unit (captura de logs) | pendiente |
| 12 | `SinCanal` levanta `CanalNoConectado` sin ningún `POST` | unit | pendiente |
| 13 | **RED** — Un recordatorio de cobro hoy nunca llega a `MensajeriaWhatsApp`: con `WHATSAPP_ADAPTADOR=meta` y un canal sobre `MockTransport`, despachar el paso 1 de un cobro vencido no produce ningún `POST …/messages`. GREEN: un `POST` cuyo `to` es el teléfono del cliente | integración (composition root) | pendiente |
| 14 | **RED** — Cancelar un turno desde el panel no llega a la Cloud API (hoy `AvisoPorConsola`) | integración (composition root) | pendiente |
| 15 | **RED** — En producción, cancelar el turno de una empresa sin WhatsApp conectado no levanta `RuntimeError` y el turno queda cancelado (`SinCanal`) | unit (composition root) | pendiente |
| 16 | El texto del recordatorio lleva nombre, concepto, monto con dos decimales (`Decimal`, `ROUND_HALF_UP`) y el link activo del cobro | unit | pendiente |
| 17 | Cobro sin link (transferencia) → el texto no incluye la línea del link ni `None` | unit | pendiente |
| 18 | Cliente sin teléfono → `FALLIDO`, ningún `POST`, ninguna excepción | unit | pendiente |
| 19 | Paso con canal `EMAIL` o `PANEL` → `FALLIDO` sin llamar a Meta, log `recordatorio_canal_sin_adaptador` | unit | pendiente |
| 20 | Meta responde 400 → `FALLIDO`, un solo `POST`, y el barrido sigue con el cobro siguiente, que sí sale | unit + caso de uso | pendiente |
| 21 | Meta responde 503 tres veces → `FALLIDO` tras 3 `POST`; el paso queda registrado y el barrido siguiente **no** lo reenvía (D25) | caso de uso | pendiente |
| 22 | Timeout de lectura en el barrido → `FALLIDO` tras **un** `POST`; el barrido siguiente no lo reenvía | caso de uso | pendiente |
| 23 | `EnvioPorWhatsApp` y `AvisoPorWhatsApp` con un canal que levanta una excepción inesperada (`RuntimeError`) → `FALLIDO` / log, nunca levantan | unit | pendiente |
| 24 | Reserva, cancelación y reprogramación mandan su texto (la reprogramación con horario nuevo y anterior) al teléfono del cliente | unit | pendiente |
| 25 | Meta en 500 durante una cancelación → el turno queda cancelado, la bitácora lo registra, el request responde OK | integración | pendiente |
| 26 | La corrección a posteriori (HU-E7-02 RN-07) sigue sin mandar mensaje | regresión | pendiente |
| 27 | Ningún log de `EnvioPorWhatsApp` ni de `AvisoPorWhatsApp` contiene teléfono, nombre ni el texto | unit (captura de logs) | pendiente |
| 28 | Dos empresas en el mismo proceso: cada canal usa el token y el `phone_number_id` de su empresa | integración | pendiente |
| 29 | El webhook arma la mensajería **una vez** y el agente y el avisador usan la misma instancia | unit (composition root) | pendiente |
| 30 | `MensajeriaSimulada` detrás del adaptador real: el recordatorio queda `ENVIADO` en staging, como hoy | unit | pendiente |
| 31 | Regresión: el agente sigue guardando `FALLIDO` y el operador sigue recibiendo `MensajeriaNoDisponible` (422) con las excepciones tipadas nuevas | regresión | pendiente |
| 32 | `guard_architecture --scan` y `.claude/hooks/test_guards.sh` pasan: ningún import nuevo entre contextos | gate | pendiente |

Los casos 2 y 3 necesitan PostgreSQL: sin Docker en esta máquina se saltean en local y se confirman en
la CI del PR. Gates de Gate 2: `ruff format --check . && ruff check . && mypy . && pytest`
(cobertura ≥ 80 %). Frontend: no se toca.

## Preguntas del Gate 1 (con recomendación)

| # | Pregunta | Recomendación |
|---|---|---|
| 1 | La cadena de escalamiento admite pasos `EMAIL` y `PANEL` (`regla.py:51-61`) y HS-T3 RN-02 pide despachar «por el canal configurado». U5 sólo construye WhatsApp: un paso `EMAIL` o `PANEL` queda `FALLIDO` con log. ¿Se registra el recordatorio por email como **unidad propia** (payments, sobre `platform/email.py`, que ya existe) y el de panel en el centro de notificaciones del épico 10? | **Sí, unidad propia `recordatorio-por-email` después de U8, y `PANEL` al épico 10**, anotadas en `units.md` y en los pendientes del épico. No depende de terceros, así que por el principio de solución definitiva no puede quedar sin plan; meterla en U5 mezclaría dos canales en una revisión que ya es grande. Mientras tanto el `FALLIDO` es honesto y visible en PAN-COB-02 |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

> El Gate 1 no puede cerrarse hasta que el equipo acepte el ADR-0011 (PR #62).

## Decisiones tomadas durante la unidad

Decididas por el dueño del producto el 2026-10-04, antes del Gate 1 (ya no son preguntas):

- El canal completo se hace en cuatro unidades sucesivas (U5–U8); no hay partición por horas (G4a/b, G4h).
- Las plantillas se mandan a Meta por API y su estado se lee de Meta; con `simulado`, fuera de
  producción, se tratan como aprobadas (G4b, G4e) — U6.
- Callbacks de entrega y recordatorio de turno entran (G4c) — U7 y U8.
- Sin número de prueba se cierra con `httpx.MockTransport`; lo real va a `TODO.md` §25 (G4d).
- Un fallo de Meta deja `FALLIDO`; errores separados en transitorios y permanentes; H1 y H2 se
  arreglan acá; un timeout de lectura no se reintenta; el reintento entre barridos va en U7 (G4f).
- Si Meta está caída tras 3 intentos, el paso queda `FALLIDO` y la cadena sigue con el próximo paso
  (ex P6, aprobada).
