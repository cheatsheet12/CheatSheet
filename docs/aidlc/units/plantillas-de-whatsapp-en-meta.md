# Unidad: plantillas-de-whatsapp-en-meta

**HUs**: HU-E11-02 (RN-03, RN-04), HU-E8-04 (RN-01, RN-02), HS-T3 (RN-02), HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04   **Contexto dueño**: business_config (agregado `PlantillaDeNotificacion`); el cliente de Meta vive en conversational y llega por la raíz de composición (ADR-0011)   **Rama**: feature/business_config-plantillas-de-whatsapp-en-meta

> Origen: plan de trabajo de la fase C (fuera del repo), decisiones G4a/b, G4e y unidad U6.
> Cierra los pendientes **#9** y **#13** del épico 8
> ([`../epicas/08-agente-de-whatsapp/pendientes.md`](../epicas/08-agente-de-whatsapp/pendientes.md)).
> Responsable Luciano; revisa Cristian (unidad del canal, `reparto.md`).
>
> **Depende de:** `canal-real-de-whatsapp` (U5) **mergeada** y el
> [ADR-0011](../../adr/0011-outbound-whatsapp-channel-via-composition-root.md) **aceptado**. Este
> plan asume la versión revisada de U5: `MensajeriaWhatsApp` con errores tipados (transitorio /
> permanente / incierto), espera entre intentos, un savepoint por cobro en el barrido y adaptadores
> `EnvioPorWhatsApp` / `AvisoPorWhatsApp` que nunca levantan. **Es lo primero que se vuelve a
> comprobar cuando U5 llegue a `develop`**: si los nombres de las excepciones o del resultado del
> envío cambian, se ajusta la tabla de casos 20–27 y nada más.

## Qué hace

Hoy las seis plantillas de WhatsApp de cada empresa existen solo en nuestra base: nadie se las manda
a Meta, su estado `PENDIENTE` es un valor sembrado que nunca cambia y ningún mensaje las usa. Esta
unidad las **envía a revisión de Meta** desde la cuenta de WhatsApp Business (WABA) de cada empresa,
**sincroniza su estado** (aprobada, rechazada con su motivo, pausada, deshabilitada) por webhook y por
una conciliación periódica, y hace que los recordatorios de cobro y los avisos de turno **salgan como
plantilla aprobada** — que es lo único que Meta acepta fuera de la ventana de 24 h. PAN-CFG-NOT
muestra el estado real, el motivo del rechazo y permite reenviar.

## Lo que existe hoy (relevado el 2026-10-04)

- `business_config/domain/plantilla.py`: `PlantillaDeNotificacion(codigo, canal, idioma, cuerpo,
  estado_aprobacion)`, `EstadoDeAprobacion` = `NO_APLICA | PENDIENTE | APROBADA | RECHAZADA`,
  `VARIABLES_POR_CODIGO` con seis códigos. `editar` **no toca el estado** «porque lo decide Meta»
  (`:112-122`). `puede_usarse` = canal ≠ WhatsApp o `APROBADA`.
- `business_config/application/plantillas.py`: **no hay alta ni baja**. `ListarPlantillas` siembra
  las seis faltantes con `DE_FABRICA` e `IDIOMA_POR_DEFECTO = "es_AR"`, en `PENDIENTE` (`:258-286`).
  `EditarPlantilla` (`:289-330`), `ResolverPlantilla` (`:333-351`, devuelve `None` si no es usable).
- Índice único `uq_plantilla_empresa_codigo (empresa_id, codigo)` (migración 0021): **una plantilla
  por código y por empresa**.
- **Hallazgo:** `DE_FABRICA["recordatorio_de_cobro"]` y `DE_FABRICA["cobro_generado"]` **terminan en
  `{{link}}`**. Meta rechaza una plantilla que empieza o termina con un parámetro (ver Contratos,
  fuente [T-REV]). Enviadas tal cual, las dos plantillas que más importan quedarían `RECHAZADA`.
- **Hallazgo:** las rutas de plantillas viven en `api/routers/conversaciones.py:446-486`, un archivo de
  **486 líneas** (el tope de `CLAUDE.md` §5 es 400). Las rutas nuevas no entran ahí: se mudan.
- `api/conversacional.py:182-204`: `armar_plantillas` y `_PlantillasViaConfiguracion` — definidos y
  **nunca llamados** (pendiente #13).
- PAN-CFG-NOT: `frontend/src/app/(panel)/configuracion/plantillas/page.tsx` +
  `features/conversational/components/PlantillasDeNotificacion.tsx` (341 líneas) +
  `features/conversational/api/faq.ts`. Muestra un badge por `puede_usarse` y un aviso «esperan la
  aprobación de Meta».
- `integrations` guarda `waba_id` y `phone_number_id` en `parametros` de la configuración de WhatsApp
  (`integrations/infrastructure/whatsapp/mapeo.py:23`). El token es por empresa (ADR-0003).
- El webhook (`api/routers/whatsapp.py`) solo lee `messages`; la firma es HMAC con **un único**
  `WHATSAPP_WEBHOOK_SECRET` (App Secret): es decir, **una sola app de Meta** para todas las empresas.
- No existe ninguna función `SECURITY DEFINER` que liste empresas con WhatsApp conectado ni que
  resuelva una empresa por su `waba_id` (sí las hay para ARCA, migración 0006, y MercadoPago, 0007).
- **Hallazgo (afecta a U5 y a esta unidad):** `scheduling/infrastructure/avisos.py` formatea
  `datos.inicio.strftime(...)` **sin convertir de zona**. Un turno leído de la base llega en UTC, así
  que la cancelación y la reprogramación dirían la hora UTC (tres horas más). La zona correcta ya
  existe: `ZONA_DE_LA_AGENDA` (`scheduling/domain/recurso.py:46`). Lo corrige U5 (H3, caso 33)
  en los textos de fábrica; acá los parámetros `fecha`/`hora` de las plantillas usan la misma conversión.

## Contratos — Meta (Business Management API y Cloud API)

Fuentes primarias consultadas el 2026-10-04 (developers.facebook.com):

| Ref | Documento | URL |
|---|---|---|
| [T-API] | Message templates (crear) | https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates |
| [T-LANG] | Supported languages | https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates/supported-languages |
| [T-FUND] | Template fundamentals (parámetros) | https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview.md |
| [T-MGMT] | Template management (editar, listar, borrar) | https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-management |
| [T-REV] | Template review | https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-review/ |
| [T-NODE] | Graph API — WhatsApp Business HSM | https://developers.facebook.com/docs/graph-api/reference/whats-app-business-hsm/ |
| [WH-TPL] | Webhook `message_template_status_update` | https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/message_template_status_update/ |
| [WH-OVR] | Webhook overrides | https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/override |
| [ERR] | Error codes | https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes |
| [PRICE] | Pricing | https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing |

**Lo verificado y lo que decide:**

| Hecho (fuente) | Consecuencia en el diseño |
|---|---|
| Crear: `POST /{waba_id}/message_templates` con `name`, `category` (`utility`), `language`, `parameter_format` (`named`/`positional`, default positional) y `components` [T-API] | Un cliente nuevo en `conversational` |
| `name`: hasta 512 caracteres, minúsculas, dígitos y guion bajo; **no es único**: puede repetirse en otro idioma [T-API] | Los seis `codigo` ya cumplen la forma |
| `es_AR` es un código válido («Spanish (ARG)») [T-LANG] | Se conserva `IDIOMA_POR_DEFECTO = "es_AR"` |
| Parámetros con nombre: «unique, single strings, composed of lowercase characters and underscores, wrapped in double curly brackets» [T-FUND]; ejemplos obligatorios en `body_text_named_params` (`param_name` + `example`) [T-API] | **Se usan parámetros con nombre**: `{{nombre}}` del dominio es literalmente el parámetro de Meta. No hay traducción a posicionales |
| Envío: `type: template`, `components[].parameters[]` con `parameter_name` [T-FUND] | `enviar_plantilla(..., parametros: Mapping[str, str])` |
| «The message template cannot start or end with a parameter»; parámetros con `#`, `$`, `%` o no secuenciales se rechazan [T-REV] | Regla nueva de dominio para el canal WhatsApp; se corrigen los dos textos de fábrica que terminan en `{{link}}` |
| Editar: `POST /{template_id}`; **solo** `APPROVED`, `REJECTED` o `PAUSED`; aprobada: **1 vez cada 24 h y hasta 10 en 30 días**; rechazada/pausada: sin límite; **nombre e idioma inmutables**, categoría de una aprobada inmutable; «the API replaces all components»; después de editar una aprobada o pausada «the API automatically re-approves the template unless it fails template review» [T-MGMT] | Editar una aprobada **reenvía** con el mismo nombre (no hace falta nombre nuevo). Editar una `PENDIENTE` se rechaza en casa. El límite de 24 h se controla antes de llamar |
| Borrar una aprobada bloquea el nombre **30 días** [T-MGMT] | Nunca borramos. Si Meta la elimina o deshabilita para siempre, se crea otra con **nombre versionado** → el nombre se guarda en una columna |
| Estados del nodo: `APPROVED, IN_APPEAL, PENDING, REJECTED, PENDING_DELETION, DELETED, DISABLED, PAUSED, LIMIT_EXCEEDED`; `rejected_reason`: `ABUSIVE_CONTENT, INVALID_FORMAT, NONE, PROMOTIONAL, TAG_CONTENT_MISMATCH, SCAM`; `category` [T-NODE] | Mapeo de estados (abajo) y columna de motivo |
| Listar: `GET /{waba_id}/message_templates` con `fields`, `limit`, filtro `status` y paginación por cursor [T-MGMT] | La conciliación lee una página por empresa (≤ 6 plantillas propias) y sigue `paging.next` |
| Webhook `message_template_status_update`: `object = whatsapp_business_account`, `entry[].id` = **WABA ID**, `value.event`, `message_template_id`, `message_template_name`, `message_template_language`, `reason`, `rejection_info{reason, recommendation}`, `other_info{title, description}`; eventos `APPROVED, ARCHIVED, UNARCHIVED, DELETED, DISABLED, FLAGGED, IN_APPEAL, LIMIT_EXCEEDED, LOCKED, PAUSED, PENDING, REINSTATED, PENDING_DELETION, REJECTED` [WH-TPL] | Rama nueva del webhook |
| **«Template webhooks (`message_template_status_update`…) and account-level webhooks do not support callback overrides»** [WH-OVR] | El estado de plantillas **no llega** a la URL por empresa `/webhooks/whatsapp/{empresa}`: llega a la URL de la app. Se rutea por `entry[].id` (WABA) y no por la URL; y por eso la conciliación periódica **no es opcional** |
| Revisión: «It can take up to 24 hours» [T-REV] | Frecuencia de la conciliación |
| `132001` plantilla inexistente o no aprobada, `132000` cantidad de parámetros, `132012` formato de parámetro, `132015` pausada, `132016` deshabilitada, `131047` fuera de ventana — todos 400, no reintentables [ERR] | Clasificados como permanentes (U5) |
| «Utility templates delivered within an open customer service window are free»; los mensajes de texto también son gratis dentro de la ventana [PRICE] | Mandar **siempre** la plantilla aprobada no cuesta más que el texto dentro de la ventana (ver Diseño, D-U6-6) |

**Sin verificar → `TODO.md` §25** (tabla al final): el estado inmediato tras editar una aprobada, si
el número de prueba admite crear plantillas, valores con salto de línea, el código de error de «nombre
ya existe», el cambio de precios anunciado por terceros para el 01/10/2026 y la suscripción de la app
al campo `message_template_status_update`.

## Diseño

### D-U6-1 · Nombre en Meta: columna, inicializada desde el código

**Decisión: columna `nombre_en_meta`, con valor inicial igual al `codigo`.** No alcanza la convención
sin columna, por dos hechos de la documentación:

1. Si Meta **elimina o deshabilita para siempre** una plantilla, la única salida es crear otra, y el
   nombre borrado queda bloqueado 30 días [T-MGMT]. La nueva se llama `<codigo>_v2`, `_v3`… y ese
   nombre hay que recordarlo para enviar.
2. La WABA es de la empresa: puede tener ya una plantilla creada a mano con el mismo nombre e idioma.
   Ante «nombre en uso» se prueba el siguiente sufijo, una sola vez por intento.

Editar una aprobada **no** necesita nombre nuevo: el `POST /{template_id}` conserva nombre e idioma.

### D-U6-2 · Campos nuevos del agregado

| Campo | Tipo | Por qué |
|---|---|---|
| `nombre_en_meta` | `varchar(512)` nulo | D-U6-1 |
| `meta_plantilla_id` | `varchar(64)` nulo | Lo exige editar (`POST /{template_id}`) y es la clave del webhook (`message_template_id`) |
| `motivo_meta` | `varchar(40)` nulo | `rejected_reason` / `reason` (código de Meta); la pantalla lo traduce |
| `detalle_meta` | `varchar(500)` nulo | `rejection_info.recommendation`, `other_info.description` o el `error_user_msg` de un envío refutado. Texto de Meta, sin datos personales |
| `categoria_en_meta` | `varchar(20)` nulo | Meta puede recategorizar una UTILITY como MARKETING; la pantalla lo advierte (los de marketing respetan bajas, error 131050) |
| `enviada_a_meta_en` | `timestamptz` nulo | El límite de 1 edición cada 24 h de una aprobada se controla en casa |
| `estado_meta_en` | `timestamptz` nulo | Momento del último estado aplicado (el `entry[].time` del webhook o el de la consulta). Descarta eventos viejos que llegan tarde |

**Categoría:** las seis son `UTILITY` (confirmaciones, avisos y recordatorios de una transacción
existente). Se manda como constante; no hay columna «categoría pedida».

`EstadoDeAprobacion` gana tres valores: `SIN_ENVIAR` (nunca aceptada por Meta o la última creación
fue refutada), `PAUSADA`, `DESHABILITADA`. `varchar(20)` alcanza. Mapeo desde Meta:

| Meta | Nuestro | `puede_usarse` |
|---|---|---|
| `APPROVED`, `REINSTATED`, `FLAGGED`, `LOCKED`, `UNARCHIVED`→(se relee) | `APROBADA` (FLAGGED con `detalle_meta`) | sí |
| `PENDING`, `IN_APPEAL` | `PENDIENTE` | no |
| `REJECTED`, `LIMIT_EXCEEDED` | `RECHAZADA` (+ motivo) | no |
| `PAUSED` | `PAUSADA` | no |
| `DISABLED` | `DESHABILITADA` | no |
| `DELETED`, `PENDING_DELETION`, `ARCHIVED` | `SIN_ENVIAR` (se borra `meta_plantilla_id`; la próxima creación versiona el nombre) | no |
| desconocido | sin cambio + log `plantilla_estado_meta_desconocido` | — |

### D-U6-3 · Reglas del dominio (business_config, sin red)

- `PlantillaDeNotificacion` nueva invariante **solo para canal WhatsApp**: el cuerpo no empieza ni
  termina con una variable (texto en castellano: «Meta no acepta una plantilla que empiece o termine
  con una variable.»). Se valida en `__post_init__` y en `editar`, con el mismo patrón que RN-02.
- `editar(cuerpo, momento)` — **decisión del docstring revisada:** sigue sin inventar un estado, pero
  ahora **exige** que la edición sea admisible ante Meta: rechaza si está `PENDIENTE` («La plantilla
  está en revisión de Meta. Vas a poder editarla cuando Meta responda.») y si está `APROBADA` con
  `enviada_a_meta_en` hace menos de 24 h (mensaje con la hora a partir de la cual se puede). El estado
  final lo escribe **solo** `aplicar_respuesta_de_meta(estado, motivo, detalle, momento)`. El
  docstring nuevo dice exactamente eso: «editar reenvía a Meta y el estado pasa a ser el que Meta
  conteste».
- `aplicar_respuesta_de_meta` ignora un estado con `momento` anterior a `estado_meta_en`.
- `registrar_envio_a_meta(meta_plantilla_id, nombre_en_meta, momento)`; `siguiente_nombre()` para el
  versionado.
- `ejemplos_de(codigo)`: un ejemplo ficticio por variable (`nombre="Ana"`, `servicio="Consulta
  general"`, `recurso="Sala 1"`, `fecha="15/10/2026"`, `hora="10:30"`, `fecha_anterior="14/10/2026"`,
  `hora_anterior="09:00"`, `monto="12.500,00"`, `concepto="Cuota de octubre"`,
  `vencimiento="10/10/2026"`, `link="https://pagos.example.com/c/abc123"`). Datos ficticios
  (`CLAUDE.md` §3).
- `DE_FABRICA`: `recordatorio_de_cobro` → «… Podés pagarlo acá: {{link}} Gracias.»;
  `cobro_generado` → «… por $ {{monto}}: {{link}} Gracias.». Texto exacto a confirmar en la revisión.

### D-U6-4 · Aplicación (business_config)

Puerto nuevo en `business_config/application/ports.py`:

```python
class PortRevisionDeMeta(Protocol):
    async def crear(self, *, nombre: str, idioma: str, cuerpo: str,
                    ejemplos: Mapping[str, str]) -> RespuestaDeMeta: ...
    async def editar(self, *, meta_plantilla_id: str, cuerpo: str,
                     ejemplos: Mapping[str, str]) -> RespuestaDeMeta: ...
    async def estados(self) -> list[EstadoEnMeta]: ...   # todas las de la WABA, paginado
```

`RespuestaDeMeta(meta_plantilla_id, estado, categoria)`; errores tipados de business_config:
`MetaRechazoLaPlantilla(detalle, nombre_en_uso: bool)` (4xx) y `MetaNoDisponible` (transitorio o
incierto). Son tipos **de este contexto**: el adaptador traduce los de `conversational`.

Casos de uso:

| Caso de uso | Entrada → salida | Garantiza |
|---|---|---|
| `EditarPlantilla` (cambia) | igual que hoy → plantilla | Para WhatsApp: valida en dominio, **llama a Meta dentro de la misma transacción** (crear si no hay `meta_plantilla_id` o está deshabilitada/borrada; editar si no), y solo si Meta acepta guarda cuerpo + respuesta. Si Meta refuta → `MetaRechazoLaPlantilla` y **no se guarda nada** (422 con el texto de Meta). Si Meta no responde → `MetaNoDisponible` y no se guarda (503, «reintentá»). Email/panel: igual que hoy |
| `EnviarPlantillaAMeta` (nuevo) | `plantilla_id` → plantilla | El «Enviar a revisión» de la pantalla para una `SIN_ENVIAR`/`RECHAZADA` sin editar el texto. Misma lógica que la rama WhatsApp de `EditarPlantilla` |
| `ActualizarEstadoDesdeMeta` (nuevo) | `meta_plantilla_id` o (`nombre`, `idioma`), estado, motivo, detalle, momento → `bool` | Idempotente; no retrocede por eventos viejos; sin rol (lo llama el webhook o el barrido, como `ConsultarReglasVigentes`) |
| `ConciliarPlantillasConMeta` (nuevo) | `empresa_id`, `ahora` → resumen | Siembra las faltantes (reusa `ListarPlantillas`), **envía las `SIN_ENVIAR` de fábrica** (P1), lee `estados()` y aplica cada una; detecta texto divergente (D-U6-5) |
| `ConsultarPlantillaParaEnviar` (nuevo, OHS) | `codigo`, `variables` → `PlantillaParaEnviar(nombre_en_meta, idioma, parametros, texto) \| None` | Solo si `APROBADA`. `parametros` = solo las variables que el cuerpo usa (Meta exige la cantidad exacta, 132000). `texto` = cuerpo resuelto, para guardarlo (U7) |
| `ResolverPlantilla` | sin cambios | — |

**Por qué Meta se llama dentro del caso de uso y no «después», en la raíz:** la respuesta de Meta
decide si la edición existe. Guardar primero y llamar después dejaría guardado un texto que Meta
refutó (o que no pudo recibir por el límite de 24 h), y la pantalla mostraría como vigente un cuerpo que
no es el que Meta tiene. El caso de uso no importa `conversational`: recibe `PortRevisionDeMeta`, y
quien le entrega un adaptador sobre el cliente de Meta es la raíz de composición (ADR-0011 punto 4).

### D-U6-5 · Timeout de lectura al editar (resultado incierto)

Si Meta aceptó la edición pero la respuesta no llegó, la transacción se revierte y en Meta queda un
texto que nosotros no guardamos. La conciliación compara el texto del componente `BODY` que devuelve
`estados()` con el cuerpo guardado; si difieren, deja `detalle_meta = "El texto en Meta no coincide
con el guardado: volvé a guardar la plantilla."` y la pantalla lo muestra. No se sobreescribe el cuerpo
local con el de Meta: el texto lo decide el administrador.

### D-U6-6 · Envío: plantilla siempre que esté aprobada; texto solo si no hay aprobada

Los adaptadores de U5 cambian así:

1. Piden `ConsultarPlantillaParaEnviar(codigo, variables)` (por un `Protocol` local, cableado en la
   raíz; la arista `business_config → payments, scheduling` ya existe en el Context Map).
2. Si hay aprobada → `canal.enviar_plantilla(telefono, nombre, idioma, parametros)`.
3. Si no → `canal.enviar(telefono, texto_de_fabrica)` (el texto **de fábrica**, no el editado: usar
   el cuerpo de una plantilla no aprobada por WhatsApp es justo lo que RN-04 prohíbe). Fuera de la
   ventana Meta contesta 131047 → permanente → `FALLIDO` con ese código (U5).

**Por qué no se calcula la ventana de 24 h:** el último mensaje entrante del cliente está en
`conversational.mensaje`, y consultarlo desde payments o scheduling sería una arista nueva que el
ADR-0011 no contempla. No hace falta: una plantilla de utilidad aprobada se acepta dentro y fuera de la
ventana, y dentro de la ventana es tan gratuita como un texto [PRICE]. Mandar siempre la aprobada es
más simple, nunca peor y no requiere arista. (Si el cambio de precios del 01/10/2026 que publican
terceros se confirma, plantilla de utilidad y texto dentro de la ventana pasan a costar lo mismo:
la conclusión se sostiene. TODO §25.)

El agente conversacional (`ProcesarMensajeEntrante`) **no cambia**: contesta siempre dentro de la
ventana, con texto.

Variables que arma cada adaptador (todas `str`):

| Código | Adaptador | Variables |
|---|---|---|
| `recordatorio_de_cobro` | `payments/infrastructure/envio.py` | nombre, concepto, monto (`Decimal` → `quantize(Decimal("0.01"), ROUND_HALF_UP)`, formato `12.500,00`), link (o «— (pagás por transferencia)» si no hay link: el parámetro no puede ir vacío), vencimiento |
| `turno_confirmado`, `turno_cancelado`, `turno_reprogramado`, `recordatorio_de_turno` | `scheduling/infrastructure/avisos.py` | nombre, servicio, recurso, fecha, hora, fecha_anterior, hora_anterior — **fecha/hora en `ZONA_DE_LA_AGENDA`** (corrige el hallazgo de zona) |
| `cobro_generado` | ninguno hoy (nadie lo manda) | — se registra en Meta igual: es un código del catálogo |

Saltos de línea o tabulaciones en un valor se reemplazan por un espacio (regla conocida de Meta, sin
verificar en la documentación consultada → TODO §25).

### D-U6-7 · Cliente de Meta (conversational/infrastructure)

- `canal.py`: `MensajeriaWhatsApp.enviar_plantilla(*, telefono, nombre, idioma, parametros) -> str`
  con el mismo manejo de errores tipados que `enviar` (U5). `MensajeriaSimulada.enviar_plantilla`
  devuelve `simulado-<uuid>`. `SinCanal.enviar_plantilla` levanta `CanalNoConectado`.
- `plantillas_meta.py` (nuevo, ≤ 250 líneas): `PlantillasDeMeta(token, waba_id, graph_url,
  graph_version, timeout, transporte)` con `crear`, `editar`, `estados` (paginado por
  `paging.cursors.after`, tope de 10 páginas). Reusa la clasificación de errores de `canal.py`
  (función compartida dentro del módulo de conversational, no copiada). `PlantillasSimuladas`
  (fuera de producción: responde `APPROVED` a todo, decisión G4e) y `SinCuentaDeMeta` (producción sin
  integración o sin `waba_id`: levanta `CanalNoConectado`).

### D-U6-8 · Raíz de composición (`api/`)

- `api/mensajeria.py` (de U5) gana `armar_revision_de_meta(unidad, settings, *, empresa_id)`: con
  `simulado` → `PlantillasSimuladas`; con `meta` → token y `waba_id` de `integrations`, o
  `SinCuentaDeMeta`. Lo envuelve `_RevisionViaMeta`, **en la raíz** (`api/mensajeria.py`), que
  satisface `PortRevisionDeMeta` y traduce los errores tipados de `conversational` a
  `MetaRechazoLaPlantilla` / `MetaNoDisponible` de `business_config`. Va en la raíz y no en
  `business_config/infrastructure/` porque traducir exige conocer las excepciones de los dos lados, y
  solo la raíz puede importar ambos sin una arista nueva (mismo patrón que
  `_PlantillasViaConfiguracion` en `api/conversacional.py`).
- `api/routers/plantillas.py` (nuevo): las dos rutas que hoy viven en `conversaciones.py` (GET, PUT)
  más `POST /plantillas/{id}/envio`. `conversaciones.py` baja de 486 a ≈ 440 líneas (sigue arriba del
  tope por motivos ajenos; se informa, no se arregla acá: `CLAUDE.md` §8).
- `api/mercadopago.armar_envio` y `api/agenda.armar_notificador` pasan también
  `PlantillasViaConfiguracion(ConsultarPlantillaParaEnviar(...))`. `armar_plantillas` /
  `_PlantillasViaConfiguracion` de `api/conversacional.py` se **eliminan** (código muerto, pendiente
  #13 cerrado por otra vía).

### D-U6-9 · Sincronización del estado: webhook + conciliación

**Las dos, y la conciliación es la columna vertebral.**

- **Webhook** (`message_template_status_update`): llega a la **URL de la app**, no a la de la empresa
  [WH-OVR]. Se agrega `POST/GET /webhooks/whatsapp` (sin empresa) como URL de la app; la ruta por
  empresa también acepta el campo (si una instalación tiene la URL de la app apuntando a una empresa,
  funciona igual). En ambos casos **se rutea por `entry[].id` (WABA)**: la raíz pregunta a
  `integrations` `empresa_de_la_cuenta_de_whatsapp(waba_id)` (función `SECURITY DEFINER` nueva) y abre
  la unidad de trabajo de esa empresa. La firma HMAC con el App Secret prueba el origen; la URL no
  decide nada. WABA desconocida → log + 200.
- **Conciliación** (Beat, cola `integrations_sync`, cada `WHATSAPP_PLANTILLAS_MINUTOS`, default 30):
  fan-out por `empresas_con_whatsapp_conectado()` (`SECURITY DEFINER` nueva), una tarea por empresa →
  `ConciliarPlantillasConMeta`. Una llamada `GET` por empresa por corrida.

**Por qué las dos:** el webhook de plantillas depende de una configuración de la app que no podemos
verificar sin la app de prueba (M3) y que no admite override por cuenta; si no llega, sin la
conciliación una plantilla quedaría `PENDIENTE` para siempre. La conciliación sola funcionaría, pero
con hasta 30 min de demora en mostrar un rechazo y sin enterarse de una `PAUSADA` entre corridas; el
webhook acorta eso cuando está. La conciliación además es quien **siembra y envía** las plantillas de
fábrica de una empresa que nunca entró a PAN-CFG-NOT (P1). 30 min: la revisión tarda hasta 24 h
[T-REV] y la consulta cuesta una llamada por empresa; el sondeo de verificación de número del épico 2
usa la misma escala (`WHATSAPP_SONDEO_MINUTOS`).

### D-U6-10 · Otros contextos y ADR

- `business_config` ← `conversational` (cliente de Meta): por la raíz, arista del ADR-0011.
- `payments`, `scheduling` ← `business_config` (`ConsultarPlantillaParaEnviar`): arista existente.
- `api` → `integrations` (dos funciones nuevas de lectura): la raíz ya lee `integrations`.
- **Pedido al ADR-0011 antes de aceptarse (PR #62):** el punto 5 dice que los callbacks llegan a
  `/webhooks/whatsapp/{empresa}`. Con [WH-OVR] eso es falso para el estado de plantillas. Agregar:
  «Template status updates do not support callback overrides: they arrive at the app-level URL
  `/webhooks/whatsapp` and are routed by WABA id through `integrations`, never by URL.» Si el ADR ya
  estuviera aceptado al implementar, es una enmienda por PR propio.

### D-U6-11 · Frontend (PAN-CFG-NOT)

- `features/conversational/api/faq.ts`: `Plantilla` gana `estado_aprobacion` con los 7 valores,
  `motivo_meta`, `detalle_meta`, `categoria_en_meta`, `editable_desde`; función
  `enviarARevision(id)`.
- `PlantillasDeNotificacion.tsx`: badge por estado (Aprobada / En revisión / Rechazada / Pausada /
  Deshabilitada / Sin enviar), motivo traducido (`ABUSIVE_CONTENT` → «Meta lo consideró abusivo»,
  `INVALID_FORMAT` → «Formato inválido: revisá variables y largo», `PROMOTIONAL` / `INCORRECT_CATEGORY`
  / `TAG_CONTENT_MISMATCH` → «Meta lo considera promocional: no corresponde a Utilidad», `SCAM` →
  «Meta lo consideró engañoso»), `detalle_meta` literal, botón «Enviar a revisión» (Sin enviar /
  Rechazada), edición deshabilitada con explicación en `PENDIENTE` o dentro de las 24 h, advertencia si
  `categoria_en_meta = MARKETING`. Si el componente pasa de 400 líneas, la tabla de estados se extrae a
  `EstadoDePlantilla.tsx`.
- Se queda en `features/conversational` (donde vive hoy). Mudarlo a `features/business_config` es
  correcto pero ajeno: se anota, no se hace (`CLAUDE.md` §8).
- BFF: `app/api/plantillas/[plantillaId]/envio/route.ts` (nuevo, `POST`).

## Infraestructura

- **Migraciones** (una, número libre al mergear, encadenada a la cabeza de `develop`; la 0031 está
  reservada):
  - `plantilla_de_notificacion`: las 7 columnas de D-U6-2; índice único parcial
    `uq_plantilla_meta_id (empresa_id, meta_plantilla_id) WHERE meta_plantilla_id IS NOT NULL`.
  - Backfill: `nombre_en_meta = codigo` donde `canal = 'WHATSAPP'`; `estado_aprobacion_meta =
    'SIN_ENVIAR'` donde `canal = 'WHATSAPP' AND estado_aprobacion_meta = 'PENDIENTE'` (nadie las mandó
    nunca: decir «pendiente» es falso); y el texto de fábrica nuevo de `recordatorio_de_cobro` y
    `cobro_generado` **solo** en las filas cuyo `cuerpo` es exactamente el de fábrica viejo (una editada
    por un administrador no se toca: la pantalla le mostrará el motivo).
  - `empresas_con_whatsapp_conectado()` y `empresa_de_la_cuenta_de_whatsapp(text)` `SECURITY DEFINER`,
    `REVOKE … FROM PUBLIC`, `GRANT EXECUTE … TO cheatsheet_app`, mismo formato que la 0007. La segunda
    devuelve **solo** `empresa_id`. Índice de expresión `(parametros->>'waba_id') WHERE sistema =
    'WHATSAPP'` si `parametros` es `jsonb` (se verifica en la 0004 al implementar).
  - Reversible: `downgrade` borra columnas, índices y funciones; el backfill de texto no se revierte
    (se documenta).
- **Trabajo asíncrono**: `workers/tasks_business_config.py` (nuevo) con
  `business_config.conciliar_plantillas` (fan-out) y `business_config.conciliar_empresa`, cola
  `integrations_sync`, sin `autoretry_for` (la corrida siguiente lee lo mismo: consultas por estado).
  Idempotente: aplicar el mismo estado dos veces no cambia nada; crear se protege con
  `meta_plantilla_id` (si la creación tuvo timeout, la siguiente corrida encuentra la plantilla por
  nombre en `estados()` antes de intentar crearla otra vez). Entrada en `workers/beat.py`; registro en
  `workers/main.py`.
- **Configuración**: `WHATSAPP_PLANTILLAS_MINUTOS` (default 30) en `platform/settings.py`,
  `backend/.env.example` y `render.yaml` (worker y beat). Ninguna credencial nueva.
- **Integraciones externas**: Meta Graph API, mismo timeout (`WHATSAPP_TIMEOUT_SEGUNDOS`) y política
  de U5: 3 intentos con espera sobre transitorios, ninguno sobre 4xx, **ninguno tras un timeout de
  lectura** al crear o editar (incierto: D-U6-5). Sandbox vs producción: `simulado` (local/staging
  hoy) aprueba todo; `meta` con el número de prueba (TODO §25); producción sin integración →
  `SinCuentaDeMeta`, la plantilla queda `SIN_ENVIAR` con `detalle_meta = "WhatsApp no está conectado"`.

## Riesgos que obligan a tests (marcar los que apliquen)

- [x] Toca dinero → el monto viaja como parámetro: test de formato `Decimal` con `ROUND_HALF_UP`.
- [ ] Toca comprobantes fiscales / CAE → No aplica.
- [x] Consume un webhook → mismo `message_template_status_update` dos veces = un efecto; un `PENDING`
      viejo que llega después de un `APPROVED` no retrocede.
- [x] Datos con `empresa_id` → el webhook de la WABA de la empresa A nunca toca plantillas de B, aunque
      llegue por la URL de B; la conciliación de A usa el token de A.
- [ ] Salida de un LLM → No aplica.
- [x] Datos personales → los ejemplos son ficticios; ningún log registra cuerpo, parámetros ni
      teléfono; `detalle_meta` solo guarda texto de Meta.
- [x] Red en tests → `httpx.MockTransport` y dobles; ningún test resuelve `graph.facebook.com`.
- [x] Una falla de Meta no deja estado inventado → refutación o timeout al editar = nada guardado.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/contexts/business_config/domain/plantilla.py` (estados, campos, invariante de bordes, `aplicar_respuesta_de_meta`, `ejemplos_de`, docstring de `editar`)
- [ ] `backend/src/cheatsheet/contexts/business_config/application/plantillas.py` (`EditarPlantilla` con Meta, `EnviarPlantillaAMeta`, `ActualizarEstadoDesdeMeta`, `ConsultarPlantillaParaEnviar`, `DE_FABRICA`; si pasa de 400 líneas, `application/revision_de_meta.py`)
- [ ] `backend/src/cheatsheet/contexts/business_config/application/conciliacion.py` (nuevo: `ConciliarPlantillasConMeta`)
- [ ] `backend/src/cheatsheet/contexts/business_config/application/ports.py` (`PortRevisionDeMeta`, `RespuestaDeMeta`, `EstadoEnMeta`)
- [ ] `backend/src/cheatsheet/contexts/business_config/application/errors.py` (`MetaRechazoLaPlantilla`, `MetaNoDisponible`, `PlantillaNoEditable`)
- [ ] `backend/src/cheatsheet/contexts/business_config/infrastructure/models.py` y `repositories.py` (columnas, `buscar_por_meta_id`, `buscar_por_nombre_en_meta`)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/canal.py` (`enviar_plantilla` en los tres canales)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/plantillas_meta.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/envio.py` (plantilla si aprobada; `PlantillasAprobadas` local)
- [ ] `backend/src/cheatsheet/contexts/scheduling/infrastructure/avisos.py` (ídem; fecha/hora en `ZONA_DE_LA_AGENDA`)
- [ ] `backend/src/cheatsheet/api/mensajeria.py` (`armar_revision_de_meta`, `_RevisionViaMeta`)
- [ ] `backend/src/cheatsheet/api/mercadopago.py`, `backend/src/cheatsheet/api/agenda.py` (plantillas a los adaptadores)
- [ ] `backend/src/cheatsheet/api/conversacional.py` (sale `armar_plantillas`)
- [ ] `backend/src/cheatsheet/api/routers/plantillas.py` (nuevo) · `api/routers/conversaciones.py` (salen las rutas) · `api/main.py` (router)
- [ ] `backend/src/cheatsheet/api/routers/whatsapp.py` (ruta de la app, rama de plantillas) y `api/whatsapp_notificaciones.py` (nuevo: parser defensivo de `changes[]` por `field`)
- [ ] `backend/src/cheatsheet/contexts/integrations/application/…` (consulta `EmpresaDeLaCuentaDeWhatsApp`, `EmpresasConWhatsApp`) y su repositorio
- [ ] `backend/src/cheatsheet/workers/tasks_business_config.py` (nuevo) · `workers/beat.py` · `workers/main.py`
- [ ] `backend/src/cheatsheet/platform/settings.py` · `backend/.env.example` · `render.yaml`
- [ ] `backend/migrations/versions/00NN_plantillas_en_meta.py` (número libre al mergear)
- [ ] `backend/tests/contexts/business_config/domain/test_plantilla.py`, `…/application/test_plantillas.py`, `…/application/test_conciliacion.py`
- [ ] `backend/tests/contexts/conversational/infrastructure/test_plantillas_meta.py`, `test_canal.py`
- [ ] `backend/tests/contexts/payments/infrastructure/test_envio.py`, `backend/tests/contexts/scheduling/infrastructure/test_avisos.py`
- [ ] `backend/tests/api/test_webhook_plantillas.py`, `backend/tests/api/test_rutas_de_plantillas.py`, `backend/tests/workers/test_conciliacion_de_plantillas.py`, `backend/tests/migrations/…` (backfill)
- [ ] `frontend/src/features/conversational/api/faq.ts`, `components/PlantillasDeNotificacion.tsx` (+ `EstadoDePlantilla.tsx` si hace falta) y sus tests
- [ ] `frontend/src/app/api/plantillas/[plantillaId]/envio/route.ts`
- [ ] `docs/staging-deployment.md` (URL de la app vs URL por empresa; campo `message_template_status_update`) · `docs/architecture.md` §7
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#9 y #13 cerrados) · `docs/aidlc/units.md` (fila) · `docs/aidlc/TODO.md` §25

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — Guardar una plantilla de WhatsApp en PAN-CFG-NOT no produce ningún `POST …/message_templates` (hoy solo actualiza la fila). GREEN: un `POST` con `name`, `language=es_AR`, `category=UTILITY`, `parameter_format=named` y `body_text_named_params` con un ejemplo por variable usada | integración (MockTransport) | pendiente |
| 2 | **RED** — Un recordatorio de cobro con la plantilla `APROBADA` sale como `type: text` (hoy). GREEN: `type: template`, `name = nombre_en_meta`, `language.code = es_AR`, un `parameter_name` por variable usada | unit (adaptador) | pendiente |
| 3 | **RED** — `DE_FABRICA` de `recordatorio_de_cobro` y `cobro_generado` terminan en variable: la invariante nueva los rechaza (falla hasta corregir el texto) | unit (dominio) | pendiente |
| 4 | Cuerpo de WhatsApp que empieza o termina con `{{variable}}` → `EntradaInvalida` con la frase; uno de email no se valida así | unit | pendiente |
| 5 | Editar una `PENDIENTE` → rechazo en casa, ninguna llamada a Meta | unit | pendiente |
| 6 | Editar una `APROBADA` enviada hace 3 h → rechazo con la hora; hace 25 h → `POST /{template_id}` con los componentes completos | unit + contrato | pendiente |
| 7 | Meta refuta la creación (400 con `error_user_msg`) → 422 con ese texto y **la fila no cambió** (cuerpo viejo en la base) | integración | pendiente |
| 8 | Timeout de lectura al editar → 503, nada guardado, **un solo** `POST`; la conciliación siguiente detecta texto divergente y deja el `detalle_meta` | integración | pendiente |
| 9 | «Nombre en uso» al crear → reintenta con `<codigo>_v2` una vez y guarda ese nombre | unit | pendiente |
| 10 | Plantilla `DESHABILITADA` o `DELETED` en Meta → `SIN_ENVIAR`; reenviarla crea con nombre versionado (nunca `POST /{id}`) | unit | pendiente |
| 11 | Webhook `APPROVED` por `entry[].id` = WABA de A → plantilla de A `APROBADA`, `puede_usarse` | integración (API) | pendiente |
| 12 | Webhook `REJECTED` con `reason=PROMOTIONAL` y `rejection_info.recommendation` → `RECHAZADA`, `motivo_meta`, `detalle_meta` | integración | pendiente |
| 13 | El mismo evento dos veces → un efecto; un `PENDING` con `entry[].time` anterior al `APPROVED` aplicado → se ignora | integración | pendiente |
| 14 | Evento con WABA de A que entra por `/webhooks/whatsapp/{B}` → actualiza A, nunca B; WABA desconocida → 200 sin efecto | integración (multi-tenant) | pendiente |
| 15 | Firma inválida en `/webhooks/whatsapp` → 200 sin efecto (D22); `GET` de verificación de la ruta de la app con `compare_digest` | integración | pendiente |
| 16 | Conciliación: empresa sin plantillas → siembra las seis, crea las de WhatsApp en Meta y aplica `estados()`; con paginación de 2 páginas | unit + contrato | pendiente |
| 17 | Conciliación con Meta en 503 → ninguna fila cambia, la tarea termina sin excepción; la siguiente corrida recupera | unit | pendiente |
| 18 | Mapeo completo de los 14 eventos y los 9 estados del nodo; uno desconocido no cambia nada y deja log | unit (tabla) | pendiente |
| 19 | `simulado` fuera de producción: guardar → `APROBADA` sin red; en producción `PlantillasSimuladas` se niega a construirse | unit | pendiente |
| 20 | Producción sin WhatsApp conectado → `SIN_ENVIAR` con «WhatsApp no está conectado», ninguna excepción | unit (raíz) | pendiente |
| 21 | Adaptador de cobros sin plantilla aprobada → texto **de fábrica** (no el cuerpo editado); Meta 131047 → `FALLIDO` con el código | unit | pendiente |
| 22 | Adaptador de turnos: los cuatro avisos usan su código; fecha/hora de un turno leído en UTC salen en hora de Argentina (`2026-10-15T13:30Z` → «15/10/2026», «10:30») | unit | pendiente |
| 23 | Solo se mandan los parámetros que el cuerpo usa (un cuerpo editado sin `{{recurso}}` no lo manda: 132000) | unit | pendiente |
| 24 | Monto `1234.5` → «1.234,50»; cobro sin link → parámetro no vacío | unit | pendiente |
| 25 | Valor con salto de línea → espacio | unit | pendiente |
| 26 | `enviar_plantilla`: 400 `132001` → permanente, un `POST`; 503 ×3 → transitorio tras 3 con espera; timeout de lectura → incierto, un `POST` | contrato | pendiente |
| 27 | Ningún log de los módulos nuevos contiene teléfono, cuerpo, parámetros ni token | unit (captura de logs) | pendiente |
| 28 | Backfill: `PENDIENTE` de WhatsApp → `SIN_ENVIAR`; texto de fábrica viejo → nuevo; uno editado queda igual | migración (CI) | pendiente |
| 29 | Las dos funciones `SECURITY DEFINER` devuelven solo `empresa_id` y `cheatsheet_app` puede ejecutarlas | migración (CI) | pendiente |
| 30 | PAN-CFG-NOT: badge por estado, motivo traducido, «Enviar a revisión» visible solo en Sin enviar/Rechazada y solo para Administrador, edición bloqueada con explicación en revisión / 24 h | unit (Vitest) | pendiente |
| 31 | `guard_architecture --scan` y `.claude/hooks/test_guards.sh`: ningún import de business_config, payments o scheduling hacia conversational | gate | pendiente |

Gates de Gate 2: `ruff format --check . && ruff check . && mypy . && pytest` (cobertura ≥ 80 %) y
`cd frontend && npm run format:check && npm run lint && npm run typecheck && npm run test:coverage`.
Los tests con PostgreSQL (28, 29, RLS de 14) se confirman en la CI (no hay Docker en esta máquina).

## Verificaciones no posibles sin la app de prueba de Meta → `TODO.md` §25

Numeración provisoria (sigue a las de U5; se renumera al mergear):

| # | Qué verificar | Unidad | Qué pasa si difiere |
|---|---|---|---|
| 25.9 | Estado inmediato tras `POST /{template_id}` sobre una aprobada (¿sigue `APPROVED` mientras revisa, o pasa a `PENDING`?) y si se puede enviar mientras tanto | `plantillas-de-whatsapp-en-meta` | Si pasa a `PENDING`, los envíos de ese lapso salen como texto de fábrica (y fallan fuera de ventana); se documenta en la pantalla |
| 25.10 | Código y forma del error de «nombre ya existe en ese idioma» al crear | ídem | El versionado de nombre no se dispara: la plantilla queda `SIN_ENVIAR` con el texto de Meta (visible), se ajusta la detección |
| 25.11 | Que la app reciba `message_template_status_update` en la URL de la app (campo suscripto en el panel de la app) | ídem | Solo funciona la conciliación: hasta 30 min de demora, nada se rompe |
| 25.12 | Que el número de prueba / WABA de desarrollo permita crear plantillas de utilidad y cuánto tarda la revisión | ídem | La verificación real espera a una WABA productiva |
| 25.13 | Valores con salto de línea, tabulación o más de 4 espacios seguidos (¿132012?) | ídem | Si Meta los acepta, el saneamiento sobra pero no daña |
| 25.14 | Que un link como valor de parámetro sea aceptable en una plantilla de UTILITY y no la recategorice a MARKETING | ídem | Recategorización: la pantalla lo advierte; habría que pasar el link a un botón URL (cambio de plantilla) |
| 25.15 | Precio de plantillas de utilidad dentro de la ventana desde el 01/10/2026 (terceros dicen que pasa a cobrarse, igual que el texto) | ídem | Ninguno en el diseño: plantilla y texto cuestan lo mismo dentro de la ventana en ambos escenarios |
| 25.16 | Que `rejected_reason` venga en el `GET` del nodo con los valores documentados | ídem | La pantalla muestra «Rechazada» sin motivo traducido; `detalle_meta` sigue mostrando el texto |

## Avisos al equipo

- **Cristian** (dueño de `conexion-whatsapp`, HU-E2-03, y revisor del canal): la URL de la app de
  Meta pasa a ser `/webhooks/whatsapp` y el campo `message_template_status_update` tiene que estar
  suscripto; la URL por empresa se fija por cuenta con `POST /{waba_id}/subscribed_apps` +
  `override_callback_uri` [WH-OVR]. Automatizar ese override al conectar WhatsApp es de
  `integrations` y **no** entra en esta unidad: se anota en el pendiente #3 del épico 8.
- **Equipo** (M6): con esta unidad las plantillas se envían solas a Meta al conectar WhatsApp (si se
  aprueba P1).

## Preguntas del Gate 1

1. **¿Las plantillas de fábrica se envían a Meta automáticamente cuando la empresa tiene WhatsApp
   conectado (la conciliación las siembra y las manda), o solo cuando un administrador aprieta
   «Enviar a revisión»?** Recomendación: **automático.** Es el mismo criterio que
   `ESCALAMIENTO_POR_DEFECTO`: una empresa que nunca entró a PAN-CFG-NOT tendría todos sus
   recordatorios `FALLIDO` fuera de la ventana sin enterarse. Los textos de fábrica son nuestros y
   neutros; el administrador puede editarlos después (y eso reenvía). El botón queda para reenviar una
   rechazada.
2. **Texto de cierre de las dos plantillas que terminan en `{{link}}`.** Recomendación: agregar
   « Gracias.» al final (« …acá: {{link}} Gracias.»). Es lo mínimo que cumple la regla de Meta sin
   cambiar el sentido; un link seguido de punto pegado podría romper el link en algunos clientes.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | Aprobado por Luciano con las recomendaciones de las preguntas. **Cierra cuando el equipo acepte el ADR-0011** ([#62](https://github.com/cheatsheet12/CheatSheet/pull/62)); hasta entonces no se escribe código |
| 2 · Verificación | | |
| 3 · PR | | |

> Bloqueado para cerrar el Gate 1 hasta que el ADR-0011 esté aceptado (con el agregado de D-U6-10) y
> U5 mergeada.

## Decisiones tomadas durante la unidad

- Gate 1 (2026-10-04): Pregunta 1 → automático: cuando la empresa tiene WhatsApp conectado, las plantillas de fábrica se siembran y se envían a Meta sin esperar a un administrador.
- Gate 1 (2026-10-04): Pregunta 2 → sí: los textos de fábrica de `recordatorio_de_cobro` y `cobro_generado` terminan en « Gracias.» para que no terminen en una variable; se corrigen las filas no editadas.
