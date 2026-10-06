# Unidad: canal-real-de-whatsapp

**HUs**: HS-T3, HU-E7-02, HU-E7-06, HU-E8-04 (parte de texto; cierran de punta a punta con U6–U8)   **Contexto dueño**: conversational (+ payments y scheduling, cableados por el composition root)   **Rama**: feature/conversational-canal-real-de-whatsapp

> Origen: [`../etapa-6/reparto.md`](../etapa-6/reparto.md) §2, «Unidades de código pendientes» —
> responsable Luciano, revisa Cristian. Es la **primera de cuatro unidades en secuencia** que forman
> el canal saliente de WhatsApp (decisiones G4a–G4h del 2026-10-04):
>
> | # | Unidad | Qué agrega | Depende de |
> |---|---|---|---|
> | **U5** | `canal-real-de-whatsapp` (esta) | Recordatorios de cobro y avisos de turno como **texto** por el cliente real; `SinCanal` en producción; H1 y H2; configuración y docs | ADR-0011 aceptado (2026-10-05) |
> | U6 | `plantillas-de-whatsapp-en-meta` | Envío de plantillas a Meta y lectura de su estado; mensajes `type: template` fuera de la ventana de 24 h (pendientes #9 y #13) | U5 |
> | U7 | `entregas-de-whatsapp` | Callbacks `statuses[]` para mensajes, recordatorios y avisos de turno; reintento acotado de transitorios (pendiente #4) | U5 (U6 para plantillas) |
> | U8 | `recordatorio-de-turno` | Regla `AGENDA_DE_NOTIFICACION` tipada, barrido de scheduling con Beat (pendiente #7) | U6 |
>
> Cierra el pendiente #11 del épico 8
> ([`../epicas/08-agente-de-whatsapp/pendientes.md`](../epicas/08-agente-de-whatsapp/pendientes.md)) y
> deja la configuración del #3. Requiere el
> [ADR-0011](../../adr/0011-outbound-whatsapp-channel-via-composition-root.md), **aceptado el
> 2026-10-05** (PR #62, merge `bd100e5`): su Decisión §2 y sus Consecuencias coinciden con este diseño.
> Revalidado contra develop el 2026-10-06 (ver «Revalidación contra develop»).

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
  despacha en **una sola transacción por empresa** (`workers/tasks_payments.py:62-110`) y
  `_despachar_uno` llama a `envio.enviar` sin `try` (`payments/application/recordatorios.py:185-187`).
  Si algo falla en el cobro K, la excepción sale del cuerpo del `async for` y la unidad de trabajo
  descarta todo (la trampa documentada en `api/dependencies.py:114-119`): las filas de los cobros
  anteriores desaparecen, sus mensajes ya salieron, y **el barrido de la hora siguiente los vuelve a
  mandar — un duplicado por hora**. El docstring de la clase (`recordatorios.py:102-104`) promete
  justo lo contrario.
- **H1b — un `RecordatorioDuplicado` envenena la transacción del barrido.**
  `RepositorioRecordatoriosPostgres.agregar` (`payments/infrastructure/repositories.py:285-306`, clase en `:279`)
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
| Render, documentación de configuración, `.env.example`, `TODO.md` §22.30–22.40 | Los textos configurables de PAN-CFG-NOT en los adaptadores (pendiente #13) — **U6** |

HS-T3 (RN-02 y RN-04), HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04 y HU-E8-04 quedan **cerradas de punta a
punta con U5–U8**, no con U5 sola (mensaje M6 al equipo). No es un recorte por tiempo: es el orden de
dependencias del canal.

**Fuera de alcance (anotado en la revalidación del 2026-10-06):** el ADR-0011 §6 (avisos y recordatorios
se registran como `Mensaje` `SISTEMA` en la conversación del cliente) lo hace U7; por eso
`AvisoPorWhatsApp` y `EnvioPorWhatsApp` reciben sólo el canal de texto y U7 ampliará su constructor. Los
callbacks de plantilla por `waba_id` (§5 del ADR) son de U6/U7.

## Lo que existe hoy (relevado sobre develop el 2026-10-04 y revalidado el 2026-10-06)

- `api/mercadopago.py:144-152` — `armar_envio(settings)` devuelve siempre `EnvioPorConsola` (import en
  `:49`). Lo usa únicamente el barrido `workers/tasks_payments.py:81` (`barrer_empresa`, `:62-110`).
- `api/agenda.py:61-69` — `armar_notificador(settings)` devuelve siempre `AvisoPorConsola`;
  `armar_avisador` (`:72-85`) lo usa, y lo llaman **sólo** `api/routers/agenda.py:582, 621, 645`.
  **El agente no lo llama** (PR #81): `armar_agenda(unidad, *, empresa_id, usuario_id)`
  (`api/conversacional.py:183-216`) arma su `Avisador` con `_NotificadorSilencioso` (mismo archivo,
  `~:152-181`), porque el agente confirma en la conversación y no manda un aviso aparte.
- `api/conversacional.py:103-137` — `armar_mensajeria` (async) elige entre `MensajeriaSimulada`
  (`WHATSAPP_ADAPTADOR=simulado`, empresa sin WhatsApp conectado, o sin `phone_number_id`) y `MensajeriaWhatsApp` con token y `phone_number_id` leídos de
  `integrations` por unidad de trabajo. La importan `api/routers/whatsapp.py:42` (usada en `:151`, una sola vez por request, para el
  agente) y `api/routers/conversaciones.py:24` (usada en `:288`). `armar_agenda` la llama **un solo**
  router, `api/routers/whatsapp.py:153`, y ya no recibe mensajería ni `settings`.
  `armar_plantillas` (`:230-`) está definida y **nadie la llama** (pendiente #13, va a U6).
- `contexts/conversational/infrastructure/canal.py:85-133` — `MensajeriaWhatsApp`: timeout
  explícito, `INTENTOS = 3` (`:43`), transporte `httpx` inyectable, sólo `type: text`. Ver H2.
- **No existe ningún test de `MensajeriaWhatsApp`**: no hay `tests/.../test_canal.py` (el plan
  anterior lo daba por existente). Sólo `MensajeriaSimulada` aparece en
  `tests/contexts/conversational/infrastructure/test_interprete.py:168-178`.
- **Hallazgo:** `MensajeriaSimulada(Entorno.PRODUCTION)` levanta `RuntimeError` (`canal.py:65-70`, intacto, 221 líneas).
  Como `armar_mensajeria` la devuelve para una empresa **sin WhatsApp conectado**, en producción
  cancelar un turno de esa empresa daría 500 apenas el aviso deje de ser la consola — lo contrario de
  lo que dice su propio docstring (`conversacional.py:103-114`).
- Quien ya atrapa los fallos del canal en `conversational`: `SalidaAlCliente.responder`, con un
  `except Exception` acotado y justificado (`application/salida.py:48-59`, `noqa: BLE001`; antes vivía
  en `agente.py`, PR #81; también lo usan `fuera_de_horario.py`, PR #84, y el agente) y el operador,
  que lo convierte en `MensajeriaNoDisponible` (`application/atencion.py:233-240`; ahora resuelve el
  teléfono por `PortDirectorio` y levanta `ClienteSinWhatsApp`). Las excepciones tipadas nuevas
  **heredan de `MensajeriaNoDisponible`** (`errors.py:55`), así que ninguno de los dos cambia.
  **`agente.py` está en 386/400 líneas (después de #99) y U5 no lo edita.**
- Firmas distintas, cada una correcta bajo R3: `PortEnvioDeRecordatorio.enviar(empresa_id, cobro,
  canal, paso) -> EstadoEntrega` (`payments/application/ports.py:303-311`) no trae teléfono ni texto;
  `PortNotificadorDeTurnos` (`scheduling/application/ports.py:145-158`) recibe `DatosDeAviso`
  (`:58-70`) con `telefono`.
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
- Context Map (`docs/architecture.md` §4): la fila de `conversational → payments/scheduling` **ya
  está** (`:91`, la agregó el PR del ADR-0011). Falta §7 (`:159`, tabla de puertos), que todavía lista
  `PortMensajeria` sólo para `conversational`: ese cambio **sí es de esta unidad**.
- `render.yaml` no declara **ninguna** variable `WHATSAPP_*` (ni API ni worker); el 2026-10-03
  `WHATSAPP_WEBHOOK_SECRET` se creó a mano en Render. `docs/staging-deployment.md` §3 (`:62`) y
  §4 bis.2 (`:135`) no las mencionan. `docs/configuration-management.md:122-124` todavía lista
  `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_ID`, que ya no existen (son por empresa, en `integrations`).
- `platform/settings.py:315-330` — `WHATSAPP_ADAPTADOR` obligatorio en producción y `simulado`
  prohibido ahí; `:555-564` — `WHATSAPP_GRAPH_URL`, `WHATSAPP_GRAPH_VERSION` (`v21.0`),
  `WHATSAPP_TIMEOUT_SEGUNDOS` (10), `WHATSAPP_SONDEO_MINUTOS` (30), `WHATSAPP_SONDEO_MAXIMO_DIAS` (7;
  las dos últimas, de `conexion-whatsapp`), `WHATSAPP_WEBHOOK_SECRET` (`:563`) y
  `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.
- `backend/.env.example` declara `WHATSAPP_ADAPTADOR`, `_GRAPH_URL`, `_GRAPH_VERSION`,
  `_TIMEOUT_SEGUNDOS`, `_SONDEO_MINUTOS` y `_SONDEO_MAXIMO_DIAS` (`:147-158`). El bloque «PLATFORM
  side — conversational. Forward-declared» (`~:279-288`) todavía trae `WHATSAPP_TOKEN` y
  `WHATSAPP_PHONE_ID` (no existen: son por empresa), `WHATSAPP_APP_SECRET` (el secreto real es
  `WHATSAPP_WEBHOOK_SECRET`, que no está declarado) y `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.

## Diseño

- **Dominio**: sin cambios. `EstadoEntrega` y `Recordatorio` ya tienen `ENVIADO` y `FALLIDO`;
  `DatosDeAviso` no cambia.
- **Aplicación**:
  - `payments/application/ports_envio.py` (**módulo nuevo**: `payments/application/ports.py` está en
    exactamente 400 líneas, el tope de CLAUDE.md §5, verificado el 2026-10-06 sobre develop, y **no
    crece**. Otra unidad lo reduce a 366 en una rama aún sin mergear: este plan no depende de ese
    margen. Re-exporta desde `ports.py` sólo si hace falta):
    - `PortContactoDeCliente.contacto_de(cliente_id) -> ContactoDeCobro | None` (nombre y teléfono).
      **Puerto aparte y no un método más en `PortClienteDeCobro`**, para no deshacer D92: el caso de
      uso de cobros sigue sin ver el contacto; sólo el adaptador de envío lo recibe. Mismo patrón que
      `scheduling`.
    - `PortAislamiento.aislar() -> AbstractAsyncContextManager[None]`: «lo que pase adentro se
      confirma o se deshace solo, sin tocar el resto de la transacción». Es la forma de pedir un
      savepoint sin que `application/` importe SQLAlchemy (R2).
  - `payments/application/errors.py`: `DespachoNoPersistido` — lo que el adaptador del aislamiento
    levanta cuando la base rechazó algo dentro del savepoint.
  - `DespacharRecordatorios` (`recordatorios.py:95-204`; docstring `:96-105`; archivo de 222 líneas), **arreglo de H1**:
    - Recibe `aislamiento: PortAislamiento`. Cada cobro de `ejecutar` corre en
      `async with self._aislamiento.aislar():` y un `DespachoNoPersistido` se registra
      (`recordatorio_no_persistido`, `cobro_id`, sin datos personales) y el bucle sigue: sólo se
      deshacen las filas de **ese** cobro.
    - `_despachar_uno` **protege el envío**: `enviar` va en `try`; ante cualquier excepción el estado
      es `FALLIDO` y la fila se guarda igual con `enviado_en`, para que el índice `(cobro_id, paso)`
      no lo deje salir de nuevo. Es un `except Exception` con `noqa: BLE001` justificado en el
      comentario, igual que `salida.py:53-58`: el puerto lo implementan adaptadores que podrían
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
      `CanalNoConectado` sin tocar la red. **Decisión C1 (2026-10-06):** así se cumple el ADR-0011 §3
      («reports the message as not sent»): `SinCanal` no puede devolver un id (el puerto devuelve
      `str`), así que levanta, y los consumidores (los adaptadores de payments y scheduling, que nunca
      levantan hacia arriba; el agente y el operador, que ya lo tratan como `MensajeriaNoDisponible`)
      registran el mensaje como **no enviado** en lugar de darlo por enviado.
    - Vigilar el tamaño: si `canal.py` pasa de ~380 líneas, extraer `SinCanal` y la tabla de códigos a
      un módulo hermano (p. ej. `canal_errores.py`); U6 agrega `enviar_plantilla` al mismo archivo.
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
  - `api/mensajeria.py` (nuevo): `armar_mensajeria` se muda acá desde `api/conversacional.py` (ADR-0011
    §2) para que `api/agenda.py`, `api/mercadopago.py` y `workers/` lo importen sin depender de
    `api/conversacional.py`, que ya importa `api/agenda.py` (`armar_catalogo`, `armar_directorio`). Con `meta` en producción y sin
    integración o sin `phone_number_id`, devuelve `SinCanal` en lugar de `MensajeriaSimulada`. Fuera
    de producción el comportamiento no cambia.
  - **El canal se arma una vez por unidad de trabajo** (ADR-0011 Decisión §2) y se pasa hacia
    adentro: `armar_envio(unidad, *, canal)` en `api/mercadopago.py`,
    `armar_notificador(canal)` y `armar_avisador(unidad, *, empresa_id, rol, canal)` en
    `api/agenda.py`. El único `await` es `armar_mensajeria`, en los llamadores:
    `workers/tasks_payments.py:81` y `api/routers/agenda.py:582/621/645`. **El agente queda fuera**:
    `armar_agenda` sigue con `_NotificadorSilencioso` (excepción deliberada: el agente nunca manda el
    aviso por `AvisoPorWhatsApp`, confirma en la conversación) y no se toca. En el webhook,
    `armar_mensajeria` ya se arma una sola vez (`routers/whatsapp.py:151`).
    *(El ADR-0011 aceptado ya dice que el builder del canal es `async` y que los de los adaptadores
    reciben el canal ya armado: coincide con este diseño.)*
  - `api/routers/whatsapp.py` y `api/routers/conversaciones.py` sólo cambian el import de
    `armar_mensajeria` (`:42` y `:24`) hacia `api/mensajeria.py`.
  - **`agente.py` (386/400 líneas) no se edita en U5.** Si algo lo exigiera, primero se extrae código
    a un módulo hermano, como hizo #81 con `salida.py` y `reserva_por_whatsapp.py`. Hoy el diseño no lo
    necesita; si U7 (mensajes `SISTEMA`) lo toca, es problema de U7.
  - **Tamaños**: `api/routers/agenda.py` (684), `api/routers/conversaciones.py` (486) y
    `platform/settings.py` (660) ya superan o rozan el tope; U5 agrega 1–3 líneas a los routers y
    nada a `settings.py`.
- **Otros contextos**: `payments` y `scheduling` reciben el canal de `conversational` **sólo por el
  composition root**; ningún import nuevo entre contextos (R1–R5 intactas, `guard_architecture`
  sin cambios). La fila del Context Map ya está en develop.
- **Frontend**: No aplica. PAN-COB-02 ya muestra `estado_entrega` de cada recordatorio.

### H3 — La hora de los avisos de turno sale en UTC

`scheduling/infrastructure/avisos.py` formatea `datos.inicio.strftime(FORMATO_FECHA)` (y
`inicio_anterior`) **sin convertir de zona**. Un turno leído de la base llega en UTC, así que, apenas
el aviso deje de ir a la consola, el cliente leería una hora tres horas corrida. Se corrige en esta
unidad, porque es la que hace reales los avisos: los textos convierten a `ZONA_DE_LA_AGENDA`
(`scheduling/domain/recurso.py:46`) antes de formatear. Caso 33.

## Infraestructura

- **Migraciones**: **ninguna en U5.** (U7 agrega `recordatorio.externo_id`; el número se toma libre al
  mergear: la cabeza de develop hoy es `0032`.)
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
  - `docs/staging-deployment.md` §3 (`:62`): dos filas (`WHATSAPP_WEBHOOK_SECRET` = el **App Secret** de la
    app de Meta, con el que firma `X-Hub-Signature-256`; `WHATSAPP_WEBHOOK_VERIFY_TOKEN` = el token que
    se escribe al registrar la URL) y la advertencia de que sin el secreto toda notificación se
    descarta con 200 (D49, pendiente #3). §4 bis.2 (`:135`): `WHATSAPP_ADAPTADOR` en el worker. `render.yaml` hoy no declara
    `WHATSAPP_SONDEO_MINUTOS` ni `WHATSAPP_SONDEO_MAXIMO_DIAS` (de `conexion-whatsapp`); no son de U5,
    pero se decide al editar si se declaran para no dejar la tabla de Render a medias.
  - `docs/configuration-management.md:122-124`: reemplazar `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID` por las
    variables reales y una línea que diga que el token y el número son por empresa (HU-E2-03).
  - `backend/.env.example`: **borrar** `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_ID`; **renombrar**
    `WHATSAPP_APP_SECRET` → `WHATSAPP_WEBHOOK_SECRET`; **dejar** `WHATSAPP_WEBHOOK_VERIFY_TOKEN`. La nota
    de Render y la de `docs/configuration-management.md` se alinean igual.
- **Integraciones externas**: Meta WhatsApp Cloud API, el mismo cliente. Timeout
  `WHATSAPP_TIMEOUT_SEGUNDOS`; 3 intentos con espera sobre transitorios; ninguno sobre permanentes ni
  sobre inciertos (tabla de Diseño).

## Contratos — Meta WhatsApp Cloud API

> Verificado el 2026-10-04 contra *Cloud API › Error codes*
> (`developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes`): títulos y recomendación de
> cada código de la tabla de Diseño, y la forma del error (`error.code`, `error.error_data.details`,
> `error.error_subcode` deprecado, `fbtrace_id`). La página recomienda **manejar los errores por
> `code` y no por status HTTP**, y **no dice con qué status HTTP llega cada código** → eso pasa a
> `TODO.md` §22.31. Lo que sigue sin verificar dice **«a confirmar»**.

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
| Staging con número de prueba (TODO §22.30) | `meta` | `MensajeriaWhatsApp` contra el número de prueba | Sólo llega a los destinatarios dados de alta en la app de prueba (cantidad: **a confirmar**) |
| Producción | `meta` (obligatorio, `settings.py:315-330`) | `MensajeriaWhatsApp`, o `SinCanal` si la empresa no conectó WhatsApp | `simulado` está prohibido |

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
en la **§22** (la §25 no existe: la última sección de develop es la §24, y la §22 recoge las
verificaciones manuales; **§22.23–22.29 ya están tomadas**, así que las filas de esta unidad son
**22.30 a 22.40**), con el formato de §20–22:

| # | Qué verificar | Unidad | Qué pasa si falla |
|---|---|---|---|
| 22.30 | Conseguir la app de Meta con número de prueba y cargar sus credenciales en staging (`integrations`, `WHATSAPP_ADAPTADOR=meta`) — responsable Cristian | U5–U8 | Nada de 22.30–22.40 se puede verificar; el código queda probado sólo contra contratos grabados |
| 22.31 | Un texto libre iniciado por la empresa fuera de la ventana de 24 h vuelve con `error.code` 131047 y **qué status HTTP** | U5 | Si el código llega distinto, se ajusta la tabla de clasificación |
| 22.32 | Formato del número argentino que acepta `to`: con o sin `+`, con o sin el `9` de celular (`549…` vs `54…`) contra lo que guarda `master_data` | U5 | Todos los envíos a celulares argentinos fallan: hay que normalizar en el adaptador |
| 22.33 | Status HTTP con que llegan los códigos de throttling (4, 80007, 130429, 131056) y si traen `Retry-After` | U5 | La clasificación por código los cubre igual; si traen espera sugerida, se evalúa usarla |
| 22.34 | Un `ReadTimeout` provocado (proxy lento) no produce dos mensajes y deja el recordatorio `FALLIDO` | U5 | Riesgo de duplicado no cubierto |
| 22.35 | `messages[0].id` del envío coincide con el `id` de `statuses[]` del callback | U7 | No se pueden atar los callbacks al mensaje |
| 22.36 | Forma del envío `type: template` (posicionales vs `parameter_name`, idioma `es_AR`), respuesta ante plantilla no aprobada (132001) | U6 | Ninguna plantilla sale |
| 22.37 | `GET /{waba_id}/message_templates` y webhook `message_template_status_update` | U6 | El estado de aprobación no se puede leer |
| 22.38 | Un `failed` trae `errors[]` con código legible | U7 | PAN-COB-02 muestra `FALLIDO` sin motivo |
| 22.39 | Punta a punta en staging: registrar `/webhooks/whatsapp/{empresa}` con `WHATSAPP_WEBHOOK_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN` cargados (pendiente #3) | U5 (config) / U7 | Toda notificación se descarta con 200 (D49) |
| 22.40 | Cantidad de destinatarios que admite el número de prueba | U5–U8 | Se planifica la prueba con menos clientes |

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

## Archivos a tocar

- [x] `backend/src/cheatsheet/api/mensajeria.py` (nuevo: `armar_mensajeria`, `SinCanal` en producción)
- [x] `backend/src/cheatsheet/api/conversacional.py` (sale `armar_mensajeria`; `armar_agenda` y `_NotificadorSilencioso` **no cambian**)
- [x] `backend/src/cheatsheet/api/mercadopago.py` (`armar_envio(unidad, *, canal)` → `EnvioPorWhatsApp`; `armar_contactos`)
- [x] `backend/src/cheatsheet/api/agenda.py` (`armar_notificador(canal)`, `armar_avisador(…, canal)` → `AvisoPorWhatsApp`)
- [x] `backend/src/cheatsheet/api/routers/agenda.py` (tres sitios: `await armar_mensajeria` y se pasa el canal)
- [x] `backend/src/cheatsheet/api/routers/whatsapp.py` (sólo el import de `armar_mensajeria`)
- [x] `backend/src/cheatsheet/api/routers/conversaciones.py` (import desde `api/mensajeria.py`)
- [x] `backend/src/cheatsheet/workers/tasks_payments.py` (canal por unidad de trabajo; docstring)
- [x] `backend/src/cheatsheet/contexts/payments/application/ports_envio.py` (nuevo: `PortContactoDeCliente`, `ContactoDeCobro`, `PortAislamiento`; `ports.py` está al tope de 400 líneas y no se toca)
- [x] `backend/src/cheatsheet/contexts/payments/application/errors.py` (`DespachoNoPersistido`)
- [x] `backend/src/cheatsheet/contexts/payments/application/recordatorios.py` (savepoint por cobro, envío protegido, docstring)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/aislamiento.py` (nuevo: `AislamientoConSavepoint`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/ensamblado.py` (`Cobros.aislamiento`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/repositories.py` (`agregar` con su savepoint — H1b)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/clientes.py` (`ContactoViaMasterData`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/envio.py` (`EnvioPorWhatsApp`, `CanalDeTexto`, texto; sale `EnvioPorConsola`)
- [x] `backend/src/cheatsheet/contexts/scheduling/infrastructure/avisos.py` (`AvisoPorWhatsApp`; sale `AvisoPorConsola`)
- [x] `backend/src/cheatsheet/contexts/conversational/infrastructure/canal.py` (H2: clasificación, espera inyectable, excepciones de httpx, log con código; `SinCanal`)
- [x] `backend/src/cheatsheet/contexts/conversational/application/errors.py` (`MensajeRechazado`, `MensajeriaSaturada`, `EnvioIncierto`, `CanalNoConectado`)
- [x] `backend/tests/contexts/conversational/infrastructure/test_canal.py` (nuevo)
- [x] `backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py` (H1 con fakes; `AislamientoFalso`)
- [x] `backend/tests/contexts/payments/infrastructure/test_envio.py` (nuevo)
- [x] `backend/tests/contexts/scheduling/infrastructure/test_avisos.py` (reescrito)
- [x] `backend/tests/api/test_canal_real_de_whatsapp.py` (nuevo: cableado del composition root; incluye el caso 34)
- [x] `backend/tests/integracion/test_barrido_de_recordatorios_postgres.py` (nuevo: H1 y H1b contra PostgreSQL, CI)
- [x] `render.yaml` (API: `WHATSAPP_WEBHOOK_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN` `sync: false`, `WHATSAPP_ADAPTADOR`; worker: `WHATSAPP_ADAPTADOR`)
- [x] `docs/staging-deployment.md` §3 y §4 bis.2
- [x] `docs/configuration-management.md` (bloque de variables de WhatsApp)
- [ ] `backend/.env.example` (borrar `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_ID`; `WHATSAPP_APP_SECRET` → `WHATSAPP_WEBHOOK_SECRET`) — **NO HECHO**: el directorio está bloqueado por los permisos del entorno de implementación; lo aplica el dueño (ver «Estado de la implementación»)
- [x] `docs/architecture.md` §7, `:159` (`PortMensajeria` consumido también por payments y scheduling vía composition root; la fila de §4 ya está hecha)
- [x] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#11 cerrado; #3 con la configuración de Render; #4, #7, #9, #13 apuntan a U7, U8, U6, U6)
- [x] `docs/aidlc/units.md` (fila de U5 y filas de U6, U7 y U8 con sus dependencias) — sin cambios: las filas de U5–U8 y U11 ya estaban
- [x] `docs/aidlc/TODO.md` (entradas 22.30–22.40 en §22)

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED (H1)** — Con un envío falso que levanta en el cobro 2 de 3, `DespacharRecordatorios.ejecutar` hoy propaga la excepción. GREEN: no levanta; cobros 1 y 3 `ENVIADO`, cobro 2 registrado `FALLIDO` con `enviado_en` | caso de uso (fakes) | hecho · RED observado (ImportError de colección) · `test_cobros_y_recordatorios.py` |
| 2 | **RED (H1, duplicado)** — PostgreSQL: dos `barrer_empresa` seguidos con un envío que falla en el cobro 2 la primera vez. Hoy el cobro 1 recibe **dos** envíos (la primera transacción se deshizo). GREEN: un envío por cobro; y con una falla de base forzada dentro del savepoint del cobro 2, las filas de 1 y 3 sobreviven | integración (CI) | hecho · escrito, **sólo CI** (PostgreSQL) · RED por ImportError de colección en local |
| 3 | **RED (H1b)** — PostgreSQL: con la fila del paso 1 del cobro A ya insertada, el barrido sigue, despacha el cobro B en la misma transacción y confirma | integración (CI) | hecho · escrito, **sólo CI** (PostgreSQL) |
| 4 | **RED (H2)** — `MockTransport` que levanta `httpx.ConnectError`: hoy sale la excepción de httpx cruda. GREEN: 3 intentos y `MensajeriaSaturada` (subclase de `MensajeriaNoDisponible`) | unit | hecho · RED observado (ImportError de colección) |
| 5 | **RED (H2)** — `httpx.ReadTimeout`: **un solo** `POST` y `EnvioIncierto`, sin reintento | unit | hecho · RED observado (ImportError de colección) |
| 6 | **RED (H2)** — 503, 503, 200: devuelve el `wamid`, y el `esperar` falso registró `[1.0, 2.0]`; ningún `sleep` real | unit | hecho · RED observado (ImportError de colección) |
| 7 | **RED (H2)** — 429 (y 400 con código 130429): hoy un solo `POST`. GREEN: se reintenta | unit | hecho · RED observado (ImportError de colección) |
| 8 | Códigos de throttling 4, 80007, 131056 y transitorios 131000, 131016 se reintentan (parametrizado) | unit | hecho · RED observado (ImportError de colección) |
| 9 | 131047, 131026, 132001, 190 y 401: **un solo** `POST`, `MensajeRechazado` con su `codigo` (parametrizado) | unit | hecho · RED observado (ImportError de colección) |
| 10 | 4xx con cuerpo ilegible → permanente, `codigo=None`; 5xx sin cuerpo → transitorio | unit | hecho · RED observado (ImportError de colección) |
| 11 | El log de un rechazo trae `estado`, `codigo` y `fbtrace_id`, y no trae teléfono, texto ni `error_data.details` | unit (captura de logs) | hecho · RED observado (ImportError de colección) |
| 12 | `SinCanal` levanta `CanalNoConectado` sin ningún `POST` | unit | hecho · RED observado (ImportError de colección) |
| 13 | **RED** — Un recordatorio de cobro hoy nunca llega a `MensajeriaWhatsApp`: con `WHATSAPP_ADAPTADOR=meta` y un canal sobre `MockTransport`, despachar el paso 1 de un cobro vencido no produce ningún `POST …/messages`. GREEN: un `POST` cuyo `to` es el teléfono del cliente | integración (composition root) | hecho · cubierto a nivel unidad con el canal real sobre `MockTransport` (`test_envio.py`); **no RED-observado** (el adaptador se escribió antes que el test) |
| 14 | **RED** — Cancelar un turno desde el panel no llega a la Cloud API (hoy `AvisoPorConsola`) | integración (composition root) | hecho · RED observado (ImportError de colección de `test_avisos.py`) · `tests/api/test_canal_real_de_whatsapp.py` |
| 15 | **RED** — En producción, cancelar el turno de una empresa sin WhatsApp conectado no levanta `RuntimeError` y el turno queda cancelado (`SinCanal`) | unit (composition root) | hecho · `tests/api/test_canal_real_de_whatsapp.py` (composition root y cancelación con `SinCanal`); no RED-observado |
| 16 | El texto del recordatorio lleva nombre, concepto, monto con dos decimales (`Decimal`, `ROUND_HALF_UP`) y el link activo del cobro | unit | hecho · **no RED-observado** |
| 17 | Cobro sin link (transferencia) → el texto no incluye la línea del link ni `None` | unit | hecho · **no RED-observado** |
| 18 | Cliente sin teléfono → `FALLIDO`, ningún `POST`, ninguna excepción | unit | hecho · **no RED-observado** |
| 19 | Paso con canal `EMAIL` o `PANEL` → `FALLIDO` sin llamar a Meta, log `recordatorio_canal_sin_adaptador` | unit | hecho · **no RED-observado** |
| 20 | Meta responde 400 → `FALLIDO`, un solo `POST`, y el barrido sigue con el cobro siguiente, que sí sale | unit + caso de uso | hecho · **no RED-observado** |
| 21 | Meta responde 503 tres veces → `FALLIDO` tras 3 `POST`; el paso queda registrado y el barrido siguiente **no** lo reenvía (D25) | caso de uso | hecho · **no RED-observado** |
| 22 | Timeout de lectura en el barrido → `FALLIDO` tras **un** `POST`; el barrido siguiente no lo reenvía | caso de uso | hecho · **no RED-observado** |
| 23 | `EnvioPorWhatsApp` y `AvisoPorWhatsApp` con un canal que levanta una excepción inesperada (`RuntimeError`) → `FALLIDO` / log, nunca levantan | unit | hecho · **no RED-observado** (payments); RED observado (scheduling) |
| 24 | Reserva, cancelación y reprogramación mandan su texto (la reprogramación con horario nuevo y anterior) al teléfono del cliente | unit | hecho · RED observado (ImportError de colección) |
| 25 | Meta en 500 durante una cancelación → el turno queda cancelado, la bitácora lo registra, el request responde OK | integración | hecho · sobre los dobles de `scheduling` y el canal real con `MockTransport` (no contra PostgreSQL) |
| 26 | La corrección a posteriori (HU-E7-02 RN-07) sigue sin mandar mensaje | regresión | hecho · ya cubierto por `test_agenda.py::TestCorreccionAPosteriori`; sin cambios |
| 27 | Ningún log de `EnvioPorWhatsApp` ni de `AvisoPorWhatsApp` contiene teléfono, nombre ni el texto | unit (captura de logs) | hecho · RED observado (scheduling); **no RED-observado** (payments) |
| 28 | Dos empresas en el mismo proceso: cada canal usa el token y el `phone_number_id` de su empresa | integración | hecho · a nivel `armar_mensajeria` con integraciones falsas (no contra PostgreSQL) |
| 29 | ~~El webhook arma la mensajería una vez y el agente y el avisador usan la misma instancia~~ | — | **eliminado** (2026-10-06): PR #81 ya hizo que `armar_agenda` use `_NotificadorSilencioso`, y el webhook ya arma la mensajería una sola vez |
| 30 | `MensajeriaSimulada` detrás del adaptador real: el recordatorio queda `ENVIADO` en staging, como hoy | unit | hecho · **no RED-observado** |
| 31 | Regresión: `SalidaAlCliente` (agente y `fuera_de_horario.py`) sigue guardando `FALLIDO` y el operador (`ResponderComoOperador`) sigue recibiendo `MensajeriaNoDisponible` (422) con las excepciones tipadas nuevas | regresión | hecho · `test_fallos_tipados_del_canal.py` (`SalidaAlCliente`); el operador captura `Exception`, sin cambio de código |
| 32 | `guard_architecture --scan` y `.claude/hooks/test_guards.sh` pasan: ningún import nuevo entre contextos | gate | parcial · `guard_architecture.py --scan` pasa (739 archivos); `test_guards.sh` **no corre local (falta `jq`)** → CI, TODO §22.41 |
| 33 | **RED** — Un turno a las `2026-10-15T13:30Z` produce avisos de reserva, cancelación y reprogramación con «15/10/2026 a las 10:30» (hora de Argentina), no «13:30» | unit | hecho · RED observado (la salida actual dice «13:30») |
| 34 | Regresión — una reserva o cancelación hecha por el agente sigue sin disparar un segundo mensaje (`_NotificadorSilencioso`; el agente nunca usa `AvisoPorWhatsApp`) | regresión (composition root) | hecho · `tests/api/test_canal_real_de_whatsapp.py` |

Los casos 2 y 3 necesitan PostgreSQL: sin Docker en esta máquina se saltean en local y se confirman en
la CI del PR. Gates de Gate 2: `ruff format --check . && ruff check . && mypy . && pytest`
(cobertura ≥ 80 %). Frontend: no se toca. El caso 29 queda «eliminado» y no se renumera: otros
pasajes citan los casos 1–5, 31 y 33.

## Estado de la implementación (2026-10-06)

Siete commits de trabajo en la rama (canal con clasificación y `SinCanal`; savepoint por cobro; `api/mensajeria.py`;
recordatorios por WhatsApp; avisos de turno por WhatsApp con hora local; configuración y documentación). Gates
locales: `ruff format --check`, `ruff check`, `mypy` (684 archivos) y `pytest` verdes; los tests contra PostgreSQL
y `test_guards.sh` quedan para la CI del PR (TODO §22.41).

**Desvíos respecto del plan (todos mecánicos):**

- Los puertos de envío de payments viven en `payments/application/ports_envio.py` como pidió el plan, pero
  `PortEnvioDeRecordatorio` ya estaba en `ports_de_recordatorios.py` (develop lo había extraído de `ports.py`): no se
  movió.
- La clasificación de errores de Meta salió a `conversational/infrastructure/canal_errores.py` desde el principio
  (el plan lo preveía sólo si `canal.py` pasaba de ~380 líneas; quedó en 292). Un código fuera de las dos tablas cae
  al status HTTP (5xx y 429 transitorios; el resto permanente).
- `CanalDeTexto` está declarado dos veces —en `payments/infrastructure/envio.py` y en
  `scheduling/infrastructure/avisos.py`—, a propósito (ADR-0011 §1: cada consumidor declara el suyo).
- `armar_envio(unidad, *, canal)` devuelve `PortEnvioDeRecordatorio`; `armar_avisador(unidad, *, empresa_id, rol, canal)`
  perdió el parámetro `settings`. El canal se arma en los llamadores (`workers/tasks_payments.py` y los tres sitios de
  `api/routers/agenda.py`).
- Se agregó la fila TODO §22.41 (confirmar en la CI los tests sólo-PostgreSQL y `test_guards.sh`).
- **`backend/.env.example` NO se tocó**: la ruta está denegada por los permisos del entorno donde se implementó. Falta
  borrar `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_ID`, renombrar `WHATSAPP_APP_SECRET` → `WHATSAPP_WEBHOOK_SECRET`
  (bloque «PLATFORM side — conversational», ~líneas 283–288) y corregir el comentario de la línea 18
  (`WHATSAPP_TOKEN/PHONE_ID/*_SECRET`).
- Variables a mano en Render (el dashboard es la fuente de verdad, `render.yaml` es descriptivo): en `cheatsheet-api`,
  agregar `WHATSAPP_ADAPTADOR=simulado` si no está; `WHATSAPP_WEBHOOK_SECRET` ya existe (creada el 2026-10-03);
  `WHATSAPP_WEBHOOK_VERIFY_TOKEN` hay que crearla cuando exista la app de Meta. En `cheatsheet-worker`, agregar
  `WHATSAPP_ADAPTADOR=simulado`. No hay variables renombradas ni borradas en Render.

## Preguntas del Gate 1 (con recomendación)

| # | Pregunta | Recomendación |
|---|---|---|
| 1 | La cadena de escalamiento admite pasos `EMAIL` y `PANEL` (`regla.py:51-61`) y HS-T3 RN-02 pide despachar «por el canal configurado». U5 sólo construye WhatsApp: un paso `EMAIL` o `PANEL` queda `FALLIDO` con log. ¿Se registra el recordatorio por email como **unidad propia** (payments, sobre `platform/email.py`, que ya existe) y el de panel en el centro de notificaciones del épico 10? | **Sí, unidad propia `recordatorio-por-email` (U11), que depende de U5 como dice `units.md` y puede ir en paralelo con U6–U8, y `PANEL` al épico 10**, anotadas en `units.md` y en los pendientes del épico. No depende de terceros, así que por el principio de solución definitiva no puede quedar sin plan; meterla en U5 mezclaría dos canales en una revisión que ya es grande. Mientras tanto el `FALLIDO` es honesto y visible en PAN-COB-02 |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | Aprobado por Luciano con las recomendaciones de las preguntas. **Cerrado el 2026-10-06**: el ADR-0011 fue aceptado el 2026-10-05 ([#62](https://github.com/cheatsheet12/CheatSheet/pull/62), merge `bd100e5`) y el plan se revalidó contra develop el 2026-10-06 (ver «Revalidación contra develop»); Luciano confirmó C1 y C2. Ya se puede escribir código |
| 2 · Verificación | | |
| 3 · PR | | |

> Condición del Gate 1 (ADR-0011 aceptado): cumplida el 2026-10-05.

## Decisiones tomadas durante la unidad

Decididas por el dueño del producto el 2026-10-04, antes del Gate 1 (ya no son preguntas):

- El canal completo se hace en cuatro unidades sucesivas (U5–U8); no hay partición por horas (G4a/b, G4h).
- Las plantillas se mandan a Meta por API y su estado se lee de Meta; con `simulado`, fuera de
  producción, se tratan como aprobadas (G4b, G4e) — U6.
- Callbacks de entrega y recordatorio de turno entran (G4c) — U7 y U8.
- Sin número de prueba se cierra con `httpx.MockTransport`; lo real va a `TODO.md` §22, entradas 22.30–22.40 (G4d).
- Un fallo de Meta deja `FALLIDO`; errores separados en transitorios y permanentes; H1 y H2 se
  arreglan acá; un timeout de lectura no se reintenta; el reintento entre barridos va en U7 (G4f).
- Si Meta está caída tras 3 intentos, el paso queda `FALLIDO` y la cadena sigue con el próximo paso
  (ex P6, aprobada).
- Gate 1 (2026-10-04): Pregunta 1 → sí: el recordatorio por email es una unidad propia, `recordatorio-por-email` (U11; payments, sobre `platform/email.py`), que depende de U5 (`units.md`) y no espera a `recordatorio-de-turno`; el paso `PANEL` va al centro de notificaciones del épico 10. Mientras tanto esos pasos quedan `FALLIDO`, visibles en PAN-COB-02.

Decididas por el dueño del producto el 2026-10-06, al revalidar el plan contra develop:

- **C1 — `SinCanal` levanta `CanalNoConectado`.** Así quien llama registra el mensaje como no enviado
  en lugar de darlo por enviado (ADR-0011 §3, «reports not sent»). Los adaptadores de payments y
  scheduling lo capturan y nunca levantan hacia arriba (recordatorio `FALLIDO` / log); el agente y el
  operador lo tratan como `MensajeriaNoDisponible`. Es una lectura del ADR, no un cambio de alcance.
- **C2 — `recordatorio-por-email` (U11) depende de U5**, como dice `units.md`, y no de U8. Puede ir en
  paralelo con U6–U8. Todavía no tiene plan ni rama: hay que escribirlo antes de empezarla.

## Revalidación contra develop (2026-10-06)

Develop avanzó 101 commits desde que se aprobó el Gate 1 (la rama sólo tiene este plan y las filas de
`units.md`; no hay código). Se contrastó cada cita y cada premisa del plan con develop (`292f3f6`) y con
el ADR-0011 aceptado. Resultado: **el Gate 1 aprobado sigue vigente**; todo cambio es mecánico o una
reducción de alcance.

| Qué cambió | Por qué | Tipo |
|---|---|---|
| El agente deja de ser llamador de `armar_notificador`; se quita el cambio de `armar_agenda(…, mensajeria)`, la reutilización de la mensajería del webhook y el caso 29 (eliminado); `_NotificadorSilencioso` se queda como excepción deliberada; se agrega el caso 34 | PR #81 ya hizo que `armar_agenda` use `_NotificadorSilencioso` y que el agente confirme en la conversación; `armar_notificador` sólo lo llama `api/routers/agenda.py` | Reducción de alcance |
| Los puertos nuevos de payments van a `payments/application/ports_envio.py` | `ports.py` está en 400/400 (tope de CLAUDE.md §5) | Estructura, sin cambio de comportamiento |
| El `except` amplio se cita en `application/salida.py:48-59` y `atencion.py:233-240`; el caso 31 apunta a `SalidaAlCliente`; se declara que U5 **no edita `agente.py`** (386/400) | El `except` se extrajo de `agente.py` (PR #81, #84) | Mecánico |
| La justificación de `api/mensajeria.py` pasa a «para que `agenda.py`, `mercadopago.py` y `workers/` no dependan de `conversacional.py`» | Con el diseño del plan no había ciclo que evitar; la mudanza sigue siendo la del ADR §2 | Mecánico |
| `.env.example`: borrar `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET` → `WHATSAPP_WEBHOOK_SECRET`, dejar `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | Ahora se pudo leer el archivo; el secreto real es `WHATSAPP_WEBHOOK_SECRET` (`settings.py:563`) | Mecánico |
| `docs/architecture.md`: sólo §7 (la fila de §4 ya está en `:91`) | La hizo el PR del ADR-0011 | Mecánico |
| El ADR-0011 está aceptado y su frase sobre los builders ya coincide con el diseño; se borran el riesgo residual y la condición de espera | Aceptado el 2026-10-05 (PR #62, `bd100e5`) | Mecánico |
| Sin migración en U5 (cabeza de develop: `0032`) | Otra unidad toma el número siguiente | Aclaración |
| Las entradas de TODO van a §22.30–22.40 | §25 no existe (la última sección es §24) y §22.23–22.29 están tomadas | Mecánico |
| `SinCanal` levanta `CanalNoConectado` (C1); U11 depende de U5 (C2) | Decisiones de Luciano del 2026-10-06 | Confirmación |
| Nota nueva en «Fuera de alcance»: el registro `SISTEMA` en la conversación (ADR-0011 §6) lo hace U7, que ampliará el constructor de `AvisoPorWhatsApp` y `EnvioPorWhatsApp`; los callbacks por `waba_id` (§5) son de U6/U7 | Decisiones agregadas al ADR después del plan | Sin código en U5 |
| Citas de archivo y línea actualizadas (`mercadopago.py`, `tasks_payments.py`, `conversacional.py`, `routers/*`, `settings.py`, `staging-deployment.md`, etc.) | Las líneas se movieron | Mecánico |

Los planes de U6, U7 y U8 (en sus ramas) asumen los nombres de este plan (`EnvioPorWhatsApp`,
`AvisoPorWhatsApp`, `SinCanal`, `CanalNoConectado`, `api/mensajeria.py`) y que U5 crea las entradas de
TODO: esas entradas son ahora §22.30–22.40, no §25; hay que propagarlo a esos planes al retomarlos.
