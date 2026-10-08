# Unidad: plantillas-de-whatsapp-en-meta

**HUs**: HU-E11-02 (RN-03, RN-04), HU-E8-04 (RN-01, RN-02), HS-T3 (RN-02), HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04   **Contexto dueño**: business_config (agregado `PlantillaDeNotificacion`); el cliente de Meta vive en conversational y llega por la raíz de composición (ADR-0011)   **Rama**: feature/business_config-plantillas-de-whatsapp-en-meta

> Origen: plan de trabajo de la fase C (fuera del repo), decisiones G4a/b, G4e y unidad U6.
> Cierra los pendientes **#9** y **#13** del épico 8
> ([`../epicas/08-agente-de-whatsapp/pendientes.md`](../epicas/08-agente-de-whatsapp/pendientes.md)).
> Responsable Luciano; revisa Cristian (unidad del canal, `reparto.md`).
>
> **Depende de:** `canal-real-de-whatsapp` (U5, mergeada en #104) y del
> [ADR-0011](../../adr/0011-outbound-whatsapp-channel-via-composition-root.md) (aceptado en #62).
> Revalidado contra develop `2b96b4a` el 2026-10-06: ver «Revalidación contra develop» más abajo.

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
  (`:112-123`). `puede_usarse` = canal ≠ WhatsApp o `APROBADA` (`:125`). El archivo tiene 161 líneas.
- `business_config/application/plantillas.py` (205 líneas): **no hay alta ni baja**. `DE_FABRICA :46`,
  `IDIOMA_POR_DEFECTO = "es_AR" :79`. `ListarPlantillas` (`:87-125`) siembra las seis faltantes en
  `PENDIENTE` (`:98-125`). `EditarPlantilla` (`:128-170`), `ResolverPlantilla` (`:172-191`, devuelve
  `None` si no es usable).
- Índice único `uq_plantilla_empresa_codigo (empresa_id, codigo)` (migración 0021): **una plantilla
  por código y por empresa**.
- **Hallazgo:** `DE_FABRICA["recordatorio_de_cobro"]` y `DE_FABRICA["cobro_generado"]` **terminan en
  `{{link}}`**. Meta rechaza una plantilla que empieza o termina con un parámetro (ver Contratos,
  fuente [T-REV]). Enviadas tal cual, las dos plantillas que más importan quedarían `RECHAZADA`.
- **Hallazgo:** las rutas de plantillas viven en `api/routers/conversaciones.py` (373 líneas hoy,
  bajo el tope de `CLAUDE.md` §5: `PlantillaEntrada :68`, `PlantillaSalida :108`, `ListadoDePlantillas
  :121`, `_a_plantilla :153`, `_rutas_de_plantillas :333-373`). U6 agrega campos a `PlantillaSalida`,
  la ruta `POST …/envio` y el mapeo de errores de Meta (≈ +50 líneas → ≈ 425 > 400): las rutas se
  mudan a un router propio.
- `api/conversacional.py:182-204` (215 líneas): `armar_plantillas` y `_PlantillasViaConfiguracion` —
  definidos y **nunca llamados** (pendiente #13). `PortPlantillas`
  (`conversational/application/ports.py:340`) solo la usa ese código.
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
- **Hallazgo H3 (corregido por U5, caso 33):** `scheduling/infrastructure/avisos.py` formateaba sin
  convertir de zona. `_fecha()` ya hace `astimezone(ZONA_DE_LA_AGENDA)` (`scheduling/domain/recurso.py:46`),
  pero devuelve **un solo string** `"%d/%m/%Y a las %H:%M"`: las plantillas necesitan `fecha` y `hora`
  separadas (y `fecha_anterior`/`hora_anterior`). Ver D-U6-6.
- `PortMensajeria` (`conversational/application/ports.py:265`) solo tiene `enviar`; `armar_mensajeria`
  devuelve ese puerto. La clasificación de errores de Meta vive en
  `conversational/infrastructure/canal_errores.py` (84 líneas) y el bucle de reintento está dentro de
  `MensajeriaWhatsApp.enviar/_intentar` (`canal.py`, 292 líneas).

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
| `132001` plantilla inexistente o no aprobada, `132000` cantidad de parámetros, `132012` formato de parámetro, `132015` pausada, `132016` deshabilitada, `131047` fuera de ventana — no reintentables [ERR]; el status HTTP exacto no está documentado (TODO 22.31/22.33) | U5 clasifica 131047 y 132001 en `CODIGOS_PERMANENTES`; U6 agrega 132000, 132012, 132015 y 132016 (hoy caen a permanentes solo por el fallback «4xx») |
| «Utility templates delivered within an open customer service window are free»; los mensajes de texto también son gratis dentro de la ventana [PRICE] | Mandar **siempre** la plantilla aprobada no cuesta más que el texto dentro de la ventana (ver Diseño, D-U6-6) |

**Sin verificar → `TODO.md` §22.43–22.50** (tabla al final; §22.36 y §22.37 ya cubren la forma del
envío `type: template` y el `GET message_templates` con el webhook): el estado inmediato tras editar una aprobada, si
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
| `detalle_meta` | `varchar(500)` nulo | `rejection_info.recommendation`, `other_info.description` o el `error_user_msg` de una creación/edición refutada. Texto de Meta sobre **nuestro** texto, sin datos personales |
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
  `DE_FABRICA` es el cuerpo que se **envía a Meta**; el texto de fábrica de respaldo de los adaptadores
  (D-U6-6) es una copia distinta que escribió U5: se alinean (incluido « Gracias.») con un test por
  código que compara `DE_FABRICA` resuelta con el texto del adaptador.

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
`MetaRechazoLaPlantilla(detalle, nombre_en_uso: bool)` (4xx), `MetaNoDisponible(incierto: bool)`
(transitorio, o incierto tras un timeout de lectura: D-U6-5 necesita distinguirlo) y `MetaNoConectada`
(sin integración o credencial ilegible → la plantilla queda `SIN_ENVIAR` con «WhatsApp no está
conectado»). Son tipos **de este contexto**: el adaptador traduce los de `conversational`:
`MensajeRechazado` → `MetaRechazoLaPlantilla`; `MensajeriaSaturada` → `MetaNoDisponible(incierto=False)`;
`EnvioIncierto` → `MetaNoDisponible(incierto=True)`; `CanalNoConectado` → `MetaNoConectada`.

Para no pasar de 400 líneas, `EditarPlantilla` con Meta y `EnviarPlantillaAMeta` viven en
`application/revision_de_meta.py` (decidido de entrada; `plantillas.py` queda con `Listar`, `Resolver`
y `ConsultarPlantillaParaEnviar`).

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

Los adaptadores de U5 (`EnvioPorWhatsApp(canal, contactos)`, `AvisoPorWhatsApp(canal)`) cambian así:

1. Ganan `plantillas: PlantillasAprobadas` (`Protocol` local a cada adaptador, cableado en la raíz;
   la arista `business_config → payments, scheduling` ya existe en el Context Map) y piden
   `ConsultarPlantillaParaEnviar(codigo, variables)`. Cada adaptador amplía su `CanalDeTexto` local
   (U5 los declaró dos veces a propósito) con `enviar_plantilla`. U7 amplía después los mismos
   constructores con el registro `SISTEMA`: el orden de parámetros se coordina con su plan.
2. Si hay aprobada → `canal.enviar_plantilla(telefono, nombre, idioma, parametros)`.
3. Si no → `canal.enviar(telefono, texto_de_fabrica)`. **El texto de fábrica de respaldo es el del
   adaptador** (`texto_de_recordatorio`, `texto_de_reserva/cancelacion/reprogramacion`), no el cuerpo
   editado (usar el cuerpo de una plantilla no aprobada por WhatsApp es justo lo que RN-04 prohíbe).
   Fuera de la ventana Meta contesta 131047 → permanente → `FALLIDO` (el código queda en el log del
   canal; persistirlo por fila es de U7).

**Por qué no se calcula la ventana de 24 h:** el último mensaje entrante del cliente está en
`conversational.mensaje`, y consultarlo desde payments o scheduling sería una arista nueva que el
ADR-0011 no contempla. No hace falta: una plantilla de utilidad aprobada se acepta dentro y fuera de la
ventana, y dentro de la ventana es tan gratuita como un texto [PRICE]. Mandar siempre la aprobada es
más simple, nunca peor y no requiere arista. (Si el cambio de precios del 01/10/2026 que publican
terceros se confirma, plantilla de utilidad y texto dentro de la ventana pasan a costar lo mismo:
la conclusión se sostiene. TODO §22.49.)

El agente conversacional (`ProcesarMensajeEntrante`) **no cambia**: contesta siempre dentro de la
ventana, con texto.

Variables que arma cada adaptador (todas `str`):

| Código | Adaptador | Variables |
|---|---|---|
| `recordatorio_de_cobro` | `payments/infrastructure/envio.py` | nombre, concepto, monto (`Decimal` → `quantize(Decimal("0.01"), ROUND_HALF_UP)`, formato `12.500,00`; ver «Pregunta abierta Q1»), link (o «— (pagás por transferencia)» si no hay link: el parámetro no puede ir vacío), vencimiento |
| `turno_confirmado`, `turno_cancelado`, `turno_reprogramado` | `scheduling/infrastructure/avisos.py` | nombre, servicio, recurso, fecha, hora, fecha_anterior, hora_anterior — separadas y en hora argentina: `avisos.py` gana `_dia(instante)` y `_hora(instante)` (misma conversión a `ZONA_DE_LA_AGENDA`) y `_fecha` los compone |
| `recordatorio_de_turno` | ninguno (es U8, scheduling con Beat) | se registra en Meta (catálogo) pero lo manda U8 |
| `cobro_generado` | ninguno hoy (nadie lo manda) | — se registra en Meta igual: es un código del catálogo |

`avisos.py` cablea **tres** códigos, no cuatro: `AvisoPorWhatsApp` solo tiene `avisar_reserva`,
`avisar_cancelacion` y `avisar_reprogramacion`.

Saltos de línea o tabulaciones en un valor se reemplazan por un espacio (regla conocida de Meta, sin
verificar en la documentación consultada → TODO §22.47).

### D-U6-7 · Cliente de Meta (conversational/infrastructure)

- `conversational/application/ports.py`: `PortMensajeria` gana `enviar_plantilla(*, telefono, nombre,
  idioma, parametros) -> str` (`armar_mensajeria` devuelve ese puerto y U7 cuenta con él); lo
  satisfacen `MensajeriaWhatsApp`, `MensajeriaSimulada` y `SinCanal`, y los dobles de tests de
  conversational que implementan el puerto.
- `canal.py`: `MensajeriaWhatsApp.enviar_plantilla` con el mismo manejo de errores tipados que `enviar`
  (U5). `MensajeriaSimulada.enviar_plantilla` devuelve `simulado-<uuid>`. `SinCanal.enviar_plantilla`
  levanta `CanalNoConectado`.
- `canal_errores.py` gana `CODIGOS_PERMANENTES` ∪ {132000, 132012, 132015, 132016} y
  `ErrorDeMeta.mensaje_para_el_usuario: str | None` (`error_user_msg`), **solo** poblado por el cliente
  de plantillas y que nunca va a un log (el log sigue con `estado`, `codigo`, `fbtrace_id`).
  `MensajeRechazado` de plantillas lo lleva en un campo propio. El bucle `INTENTOS`/`ESPERAS`/
  `_intentar` se extrae de `MensajeriaWhatsApp` a una función compartida en `canal_errores.py` (o
  `canal_http.py` si ese módulo pasa de ~200 líneas) que usan `enviar`, `enviar_plantilla` y
  `PlantillasDeMeta`; los tests existentes de `test_canal.py` quedan de red de seguridad.
- `plantillas_meta.py` (nuevo, ≤ 250 líneas): `PlantillasDeMeta(token, waba_id, graph_url,
  graph_version, timeout, transporte)` con `crear`, `editar`, `estados` (paginado por
  `paging.cursors.after`, tope de 10 páginas). Reusa `canal_errores.py` (no copia).
  `PlantillasSimuladas`
  (fuera de producción: responde `APPROVED` a todo, decisión G4e) y `SinCuentaDeMeta` (producción sin
  integración o sin `waba_id`: levanta `CanalNoConectado`).

### D-U6-8 · Raíz de composición (`api/`)

- `api/mensajeria.py` (de U5) gana `armar_revision_de_meta(unidad, settings, *, empresa_id)`: con
  `simulado` → `PlantillasSimuladas`; con `meta` → token y `waba_id` de `integrations`, o
  `SinCuentaDeMeta`. Misma regla que `_sin_conectar`: sin integración o sin `waba_id` →
  `PlantillasSimuladas` fuera de producción y `SinCuentaDeMeta` en producción; credencial ilegible
  (`CredencialIlegible`/`UnicodeDecodeError`) → `SinCuentaDeMeta` en todo entorno. El helper que lee y
  descifra el token (hoy inline en `armar_mensajeria`) se extrae a una función privada compartida
  (`_credencial_de(unidad, settings, empresa_id) -> (token, parametros) | None`) para no duplicar el
  `try/except`. `CLAVE_WABA_ID = "waba_id"` se escribe en `api/mensajeria.py` (no se importa de
  `mapeo.py`, R3). Lo envuelve `_RevisionViaMeta`, **en la raíz** (`api/mensajeria.py`), que
  satisface `PortRevisionDeMeta` y traduce los errores tipados de `conversational` a
  `MetaRechazoLaPlantilla` / `MetaNoDisponible` de `business_config`. Va en la raíz y no en
  `business_config/infrastructure/` porque traducir exige conocer las excepciones de los dos lados, y
  solo la raíz puede importar ambos sin una arista nueva (mismo patrón que
  `_PlantillasViaConfiguracion` en `api/conversacional.py`). El ADR-0011 §4 habla de
  `infrastructure/`; el puerto va en `application/ports.py` (R2) y su adaptador en la raíz: mismo
  efecto, ninguna arista nueva.
- `api/routers/plantillas.py` (nuevo): las dos rutas que hoy viven en `conversaciones.py` (GET, PUT)
  más `POST /plantillas/{id}/envio`, y con ellas `PlantillaEntrada`, `PlantillaSalida`,
  `ListadoDePlantillas` y `_a_plantilla`. `conversaciones.py` baja de 373 a ≈ 290 líneas; el router
  nuevo evita que pase de 400.
- `api/mercadopago.armar_envio(unidad, *, canal)` agrega el colaborador de plantillas.
  `api/agenda.armar_notificador(canal)` pasa a `armar_notificador(unidad, *, canal)` (hace falta la
  sesión para `ConsultarPlantillaParaEnviar`): se ajusta su llamador (`armar_avisador`) y
  `tests/api/test_canal_real_de_whatsapp.py`; los tres sitios de `api/routers/agenda.py` no cambian.
  `armar_agenda` del agente sigue con `_NotificadorSilencioso` y no se toca.
- `armar_plantillas` / `_PlantillasViaConfiguracion` de `api/conversacional.py` se **eliminan** (código
  muerto). `PortPlantillas` queda sin implementador y se borra también (se anota, no se amplía).

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
- **ADR-0011:** el §5 aceptado ya recoge que el estado de plantillas no admite override, llega a la
  URL de la app, se rutea por WABA vía `integrations` y la conciliación es la red de seguridad. Dice
  que esa afirmación «no se reverificó» y que la verifica el Gate 1 de `entregas-de-whatsapp`: U6 ya
  la verificó contra [WH-OVR] (2026-10-04). No hace falta enmienda ni PR de ADR; se avisa a U7 de que
  no tiene que reverificarlo.

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
  `categoria_en_meta = MARKETING`. Con tres estados nuevos, motivos traducidos, botón y bloqueo de edición
  el componente (341 líneas) pasa de 400: se extraen de entrada `EstadoDePlantilla.tsx` y
  `motivosDeMeta.ts` (tabla de traducción). `ETIQUETAS_DE_APROBACION` (`faq.ts:148`) pasa a 7 claves
  (el `Record` exhaustivo rompe typecheck si falta alguna) y se ajustan los tests que lo usan
  (`pantallas.test.tsx`, `pagina.test.tsx`).
- Se queda en `features/conversational` (donde vive hoy). Mudarlo a `features/business_config` es
  correcto pero ajeno: se anota, no se hace (`CLAUDE.md` §8).
- BFF: `app/api/plantillas/[plantillaId]/envio/route.ts` (nuevo, `POST`).

## Infraestructura

- **Migraciones** (una: **`0036_plantillas_en_meta.py`, `down_revision = "0035"`**; la 0031 sigue
  reservada para `tipos-de-comprobante-por-receptor`. Se renumera/re-apunta al integrar si la cabeza
  cambió, patrón de 0030/0032. La migración de U7 (`externo_id`) toma la 0037):
  - `plantilla_de_notificacion`: las 7 columnas de D-U6-2; índice único parcial
    `uq_plantilla_meta_id (empresa_id, meta_plantilla_id) WHERE meta_plantilla_id IS NOT NULL`.
  - Backfill: `nombre_en_meta = codigo` donde `canal = 'WHATSAPP'`; `estado_aprobacion_meta =
    'SIN_ENVIAR'` donde `canal = 'WHATSAPP' AND estado_aprobacion_meta = 'PENDIENTE'` (nadie las mandó
    nunca: decir «pendiente» es falso); y el texto de fábrica nuevo de `recordatorio_de_cobro` y
    `cobro_generado` **solo** en las filas cuyo `cuerpo` es exactamente el de fábrica viejo (una editada
    por un administrador no se toca: la pantalla le mostrará el motivo).
  - `empresas_con_whatsapp_conectado()` y `empresa_de_la_cuenta_de_whatsapp(text)` `SECURITY DEFINER`,
    `REVOKE … FROM PUBLIC`, `GRANT EXECUTE … TO cheatsheet_app`, mismo formato que la 0005 y la 0007.
    La segunda devuelve **solo** `empresa_id`. Se verifica que `empresas_con_whatsapp_conectado()` no
    duplique `empresas_con_integracion_pendiente()` (0005), que devuelve solo las «pendientes». Índice de expresión **único** `uq_integracion_waba` sobre `(parametros->>'waba_id') WHERE sistema =
    'WHATSAPP' AND COALESCE(parametros->>'waba_id', '') <> ''` (G4 del Gate 2: una WABA, una empresa).
  - Reversible: `downgrade` borra columnas, índices y funciones; el backfill de texto no se revierte
    (se documenta).
- **Trabajo asíncrono**: `workers/tasks_business_config.py` (nuevo) con
  `business_config.conciliar_plantillas` (fan-out) y `business_config.conciliar_empresa`, cola
  `integrations_sync`, sin `autoretry_for` (la corrida siguiente lee lo mismo: consultas por estado).
  Idempotente: aplicar el mismo estado dos veces no cambia nada; crear se protege con
  `meta_plantilla_id` (si la creación tuvo timeout, la siguiente corrida encuentra la plantilla por
  nombre en `estados()` antes de intentar crearla otra vez). Entrada en `workers/beat.py`; registro en
  `workers/main.py`. Modelo: `tasks_payments._encolar_empresa` (protege el reparto de un hipo del broker).
- **Configuración**: `WHATSAPP_PLANTILLAS_MINUTOS` (default 30) en `platform/settings.py` (660 líneas,
  ya supera 400 antes de U6: +3, se informa, no se parte acá, `CLAUDE.md` §8) y `backend/.env.example`
  (junto a `WHATSAPP_SONDEO_*`). `render.yaml`: servicio `cheatsheet-worker` (corre Beat embebido,
  `worker -B`; no hay servicio beat y la API no la necesita); el dashboard de Render es la fuente de
  verdad: avisar al dueño de crearla a mano si quiere un valor distinto de 30. Ninguna credencial nueva.
- **Integraciones externas**: Meta Graph API, mismo timeout (`WHATSAPP_TIMEOUT_SEGUNDOS`) y política
  de U5: 3 intentos con espera sobre transitorios, ninguno sobre 4xx, **ninguno tras un timeout de
  lectura** al crear o editar (incierto: D-U6-5). Sandbox vs producción: `simulado` (local/staging
  hoy) aprueba todo; `meta` con el número de prueba (TODO §22.46); producción sin integración →
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

- [x] `backend/src/cheatsheet/contexts/business_config/domain/plantilla.py` (estados, campos, invariante de bordes, `aplicar_respuesta_de_meta`, `ejemplos_de`, docstring de `editar`)
- [x] `backend/src/cheatsheet/contexts/business_config/application/plantillas.py` (`ConsultarPlantillaParaEnviar`, `ActualizarEstadoDesdeMeta`, `DE_FABRICA`) y `application/revision_de_meta.py` (nuevo: `EditarPlantilla` con Meta y `EnviarPlantillaAMeta`)
- [x] `backend/src/cheatsheet/contexts/business_config/application/conciliacion.py` (nuevo: `ConciliarPlantillasConMeta`)
- [x] `backend/src/cheatsheet/contexts/business_config/application/ports.py` (`PortRevisionDeMeta`, `RespuestaDeMeta`, `EstadoEnMeta`)
- [x] `backend/src/cheatsheet/contexts/business_config/application/errors.py` (`MetaRechazoLaPlantilla`, `MetaNoDisponible(incierto)`, `MetaNoConectada`, `PlantillaNoEditable`)
- [x] `backend/src/cheatsheet/contexts/business_config/infrastructure/models.py` y `repositories.py` (columnas, `buscar_por_meta_id`, `buscar_por_nombre_en_meta`)
- [x] `backend/src/cheatsheet/contexts/conversational/application/ports.py` (`PortMensajeria.enviar_plantilla`) y los dobles de tests de conversational que implementan `PortMensajeria`
- [x] `backend/src/cheatsheet/contexts/conversational/infrastructure/canal.py` (`enviar_plantilla` en los tres canales) y `canal_errores.py` (códigos 132000/132012/132015/132016, `mensaje_para_el_usuario`, bucle de reintento compartido)
- [x] `backend/src/cheatsheet/contexts/conversational/infrastructure/plantillas_meta.py` (nuevo)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/envio.py` (plantilla si aprobada; `PlantillasAprobadas` local; texto de fábrica alineado)
- [x] `backend/src/cheatsheet/contexts/scheduling/infrastructure/avisos.py` (ídem para los tres avisos; `_dia`/`_hora`)
- [x] `backend/src/cheatsheet/api/mensajeria.py` (`armar_revision_de_meta`, `_RevisionViaMeta`, `_credencial_de`)
- [x] `backend/src/cheatsheet/api/mercadopago.py`, `backend/src/cheatsheet/api/agenda.py` (`armar_notificador(unidad, *, canal)`; plantillas a los adaptadores) y `backend/tests/api/test_canal_real_de_whatsapp.py`
- [x] `backend/src/cheatsheet/api/conversacional.py` (sale `armar_plantillas`; `PortPlantillas` se borra)
- [x] `backend/src/cheatsheet/api/routers/plantillas.py` (nuevo) · `api/routers/conversaciones.py` (salen las rutas y sus modelos) · `api/main.py` (router)
- [x] `backend/src/cheatsheet/api/routers/whatsapp.py` (ruta de la app, rama de plantillas) y `api/whatsapp_notificaciones.py` (nuevo: parser defensivo de `changes[]` por `field`)
- [x] `backend/src/cheatsheet/contexts/integrations/application/…` (consulta `EmpresaDeLaCuentaDeWhatsApp`, `EmpresasConWhatsApp`) y su repositorio
- [x] `backend/src/cheatsheet/workers/tasks_business_config.py` (nuevo) · `workers/beat.py` · `workers/main.py`
- [x] `backend/src/cheatsheet/platform/settings.py` (+4 líneas, 664 en total) · `render.yaml` (sin cambio: se avisa)
- [ ] `backend/.env.example`: **lo aplica el dueño** (el archivo está protegido): `WHATSAPP_PLANTILLAS_MINUTOS=30` junto a `WHATSAPP_SONDEO_*`
- [x] `backend/migrations/versions/0036_plantillas_en_meta.py` (`down_revision = "0035"`)
- [x] `backend/tests/contexts/business_config/domain/test_plantilla.py`, `…/application/test_plantillas.py`, `…/application/test_revision_de_meta.py`, `…/application/test_conciliacion.py`
- [x] `backend/tests/contexts/conversational/infrastructure/test_plantillas_meta.py`, `test_canal_plantillas.py` (nuevo; `test_canal.py` ya tiene 319 líneas)
- [x] `backend/tests/contexts/payments/infrastructure/test_envio_con_plantilla.py`, `backend/tests/contexts/scheduling/infrastructure/test_avisos_con_plantilla.py` (nuevos: `test_envio.py` 346 y `test_avisos.py` 180 pasarían el tope)
- [x] `backend/tests/api/test_webhook_plantillas.py`, `backend/tests/api/test_rutas_de_plantillas.py`, `backend/tests/workers/test_conciliacion_de_plantillas.py`, `backend/tests/migrations/…` (backfill)
- [x] `frontend/src/features/conversational/api/faq.ts`, `components/PlantillasDeNotificacion.tsx`, `components/EstadoDePlantilla.tsx` y `motivosDeMeta.ts` (nuevos) y sus tests
- [x] `frontend/src/app/api/plantillas/[plantillaId]/envio/route.ts`
- [x] `docs/staging-deployment.md` (URL de la app vs URL por empresa; campo `message_template_status_update`; `WHATSAPP_PLANTILLAS_MINUTOS` en el worker) · `docs/architecture.md` §7 (fila `PortRevisionDeMeta`, consumidor `business_config`, adaptador en la raíz)
- [x] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (#9 cerrado; #13 cerrado con nota: cobros y turnos usan la plantilla aprobada, el agente sigue con su texto por diseño) · `docs/aidlc/units.md` (U6 «en progreso» con su rama; U5 «mergeada») · `docs/aidlc/TODO.md` §22.43–22.50

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — Guardar una plantilla de WhatsApp en PAN-CFG-NOT no produce ningún `POST …/message_templates` (hoy solo actualiza la fila). GREEN: un `POST` con `name`, `language=es_AR`, `category=UTILITY`, `parameter_format=named` y `body_text_named_params` con un ejemplo por variable usada | integración (MockTransport) | verde, RED observado (`test_revision_de_meta.py`, `test_rutas_de_plantillas.py`, `test_plantillas_meta.py`) |
| 2 | **RED** — Un recordatorio de cobro con la plantilla `APROBADA` sale como `type: text` (hoy). GREEN: `type: template`, `name = nombre_en_meta`, `language.code = es_AR`, un `parameter_name` por variable usada | unit (adaptador) | verde, RED observado (`test_envio_con_plantilla.py`) |
| 3 | **RED** — `DE_FABRICA` de `recordatorio_de_cobro` y `cobro_generado` terminan en variable: la invariante nueva los rechaza (falla hasta corregir el texto) | unit (dominio) | verde, RED observado (`test_plantillas.py` con el texto viejo) |
| 4 | Cuerpo de WhatsApp que empieza o termina con `{{variable}}` → `EntradaInvalida` con la frase; uno de email no se valida así | unit | verde, RED observado (`test_plantilla.py`) |
| 5 | Editar una `PENDIENTE` → rechazo en casa, ninguna llamada a Meta | unit | verde, RED observado (`test_revision_de_meta.py`, `test_plantilla.py`) |
| 6 | Editar una `APROBADA` enviada hace 3 h → rechazo con la hora; hace 25 h → `POST /{template_id}` con los componentes completos | unit + contrato | verde, RED observado (`test_revision_de_meta.py`, `test_plantilla.py`) |
| 7 | Meta refuta la creación (400 con `error_user_msg`) → 422 con ese texto y **la fila no cambió** (cuerpo viejo en la base) | integración | verde (`test_rutas_de_plantillas.py`, `test_revision_de_meta.py`); sin variante PostgreSQL: ningún efecto se escribe antes de Meta |
| 8 | Timeout de lectura al editar → 503, nada guardado, **un solo** `POST`; la conciliación siguiente detecta texto divergente y deja el `detalle_meta` | integración | verde (`test_rutas_de_plantillas.py`, `test_conciliacion.py`) |
| 9 | «Nombre en uso» al crear → reintenta con `<codigo>_v2` una vez y guarda ese nombre | unit | verde (`test_revision_de_meta.py`) |
| 10 | Plantilla `DESHABILITADA` o `DELETED` en Meta → `SIN_ENVIAR`; reenviarla crea con nombre versionado (nunca `POST /{id}`) | unit | verde (`test_revision_de_meta.py`); `DISABLED` queda `DESHABILITADA` (tabla de D-U6-2) y se recrea al editar |
| 11 | Webhook `APPROVED` por `entry[].id` = WABA de A → plantilla de A `APROBADA`, `puede_usarse` | integración (API) | verde, RED observado (`test_webhook_plantillas.py`) |
| 12 | Webhook `REJECTED` con `reason=PROMOTIONAL` y `rejection_info.recommendation` → `RECHAZADA`, `motivo_meta`, `detalle_meta` | integración | verde, RED observado (`test_webhook_plantillas.py`) |
| 13 | El mismo evento dos veces → un efecto; un `PENDING` con `entry[].time` anterior al `APPROVED` aplicado → se ignora | integración | verde, RED observado (`test_webhook_plantillas.py`, `test_consulta_y_estado.py`) |
| 14 | Evento con WABA de A que entra por `/webhooks/whatsapp/{B}` → actualiza A, nunca B; WABA desconocida → 200 sin efecto | integración (multi-tenant) | verde, RED observado (`test_webhook_plantillas.py`); RLS en PostgreSQL: CI (`test_plantillas_en_meta_postgres.py`) |
| 15 | Firma inválida en `/webhooks/whatsapp` → 200 sin efecto (D22); `GET` de verificación de la ruta de la app con `compare_digest` | integración | verde, RED observado (`test_webhook_plantillas.py`, `test_webhook_plantillas_robustez.py`) |
| 16 | Conciliación: empresa sin plantillas → siembra las seis, crea las de WhatsApp en Meta y aplica `estados()`; con paginación de 2 páginas | unit + contrato | verde, RED observado (`test_conciliacion.py`, `test_plantillas_meta.py` para las 2 páginas); PostgreSQL: CI |
| 17 | Conciliación con Meta en 503 → ninguna fila cambia, la tarea termina sin excepción; la siguiente corrida recupera | unit | verde, RED observado (`test_conciliacion.py`) |
| 18 | Mapeo completo de los 14 eventos y los 9 estados del nodo; uno desconocido no cambia nada y deja log | unit (tabla) | verde (`test_estados_de_meta.py`, `test_consulta_y_estado.py`, `test_conciliacion.py`); sin RED separado |
| 19 | `simulado` fuera de producción: guardar → `APROBADA` sin red; en producción `PlantillasSimuladas` se niega a construirse | unit | verde (`test_plantillas_meta.py`, `test_revision_de_meta_en_la_raiz.py`) |
| 20 | Producción sin WhatsApp conectado, o credencial ilegible en cualquier entorno → `SIN_ENVIAR` con «WhatsApp no está conectado» (`MetaNoConectada`), ninguna excepción | unit (raíz) | verde (`test_revision_de_meta_en_la_raiz.py`, `test_revision_de_meta.py`) |
| 21 | Adaptador de cobros sin plantilla aprobada → texto **de fábrica del adaptador** (no el cuerpo editado). (Meta 131047 → `FALLIDO` ya está cubierto por U5; el código queda en el log del canal) | unit | verde, RED observado (`test_envio_con_plantilla.py`) |
| 22 | Adaptador de turnos: los tres avisos usan su código; `fecha` y `hora` salen por separado y en hora argentina (`2026-10-15T13:30Z` → «15/10/2026», «10:30»; la conversión ya la prueba el caso 33 de U5) | unit | verde (`test_avisos_con_plantilla.py`); sin RED separado |
| 23 | Solo se mandan los parámetros que el cuerpo usa (un cuerpo editado sin `{{recurso}}` no lo manda: 132000) | unit | verde (`test_consulta_y_estado.py`, `test_plantillas_salientes.py`) |
| 24 | Monto `1234.5` → «1.234,50» (ver «Pregunta abierta Q1»); cobro sin link → parámetro no vacío | unit | verde (`test_envio_con_plantilla.py`); Q1 sigue abierta |
| 25 | Valor con salto de línea → espacio | unit | verde (`test_consulta_y_estado.py`): el saneo vive en `ConsultarPlantillaParaEnviar`, un solo lugar |
| 26 | `enviar_plantilla`: forma del `POST` (`type: template`, `parameter_name`); un caso por clase de error usando el bucle compartido (503 ×3, 132001, timeout incierto: ya probados en `test_canal.py`); 132000/132012/132015/132016 parametrizados como permanentes | contrato | verde, RED observado (`test_canal_plantillas.py`) |
| 27 | Ningún log de los módulos nuevos contiene teléfono, cuerpo, parámetros, token ni `error_user_msg` (patrón de captura de logs de U5) | unit (captura de logs) | verde (`test_canal_plantillas.py`, `test_plantillas_meta.py`, `test_envio_con_plantilla.py`) |
| 28 | Backfill: `PENDIENTE` de WhatsApp → `SIN_ENVIAR`; texto de fábrica viejo → nuevo; uno editado queda igual | migración (CI) | escrito (`test_migracion_0036.py`); **solo CI** (no hay Docker local) |
| 29 | Las dos funciones `SECURITY DEFINER` devuelven solo `empresa_id` y `cheatsheet_app` puede ejecutarlas | migración (CI) | escrito (`test_migracion_0036.py`, `test_plantillas_en_meta_postgres.py`); **solo CI** |
| 30 | PAN-CFG-NOT: badge por estado, motivo traducido, «Enviar a revisión» visible solo en Sin enviar/Rechazada y solo para Administrador, edición bloqueada con explicación en revisión / 24 h | unit (Vitest) | verde (`plantillas.test.tsx`, `motivosDeMeta.test.ts`, `clientes.test.ts`, `rutas.test.ts`); RED observado solo en estos tres últimos |
| 31 | `guard_architecture --scan` y `.claude/hooks/test_guards.sh`: ningún import de business_config, payments o scheduling hacia conversational | gate | `guard_architecture --scan` verde; `test_guards.sh` **solo CI** (falta `jq`) |

Gates de Gate 2: `ruff format --check . && ruff check . && mypy . && pytest` (cobertura ≥ 80 %) y
`cd frontend && npm run format:check && npm run lint && npm run typecheck && npm run test:coverage`.
Los tests con PostgreSQL (28, 29, RLS de 14) se confirman en la CI (no hay Docker en esta máquina).

## Verificaciones no posibles sin la app de prueba de Meta → `TODO.md` §22.43–22.50

Numeración definitiva en `TODO.md` §22 (sigue a las de U5, que llegan hasta 22.42). Los solapes con 22.37 (webhook y `GET message_templates`) y 22.30/22.40 (número de prueba) se referencian desde allí:

| # | Qué verificar | Unidad | Qué pasa si difiere |
|---|---|---|---|
| 22.43 | Estado inmediato tras `POST /{template_id}` sobre una aprobada (¿sigue `APPROVED` mientras revisa, o pasa a `PENDING`?) y si se puede enviar mientras tanto | `plantillas-de-whatsapp-en-meta` | Si pasa a `PENDING`, los envíos de ese lapso salen como texto de fábrica (y fallan fuera de ventana); se documenta en la pantalla |
| 22.44 | Código y forma del error de «nombre ya existe en ese idioma» al crear | ídem | El versionado de nombre no se dispara: la plantilla queda `SIN_ENVIAR` con el texto de Meta (visible), se ajusta la detección |
| 22.45 | Que la app reciba `message_template_status_update` en la URL de la app (campo suscripto en el panel de la app) | ídem | Solo funciona la conciliación: hasta 30 min de demora, nada se rompe |
| 22.46 | Que el número de prueba / WABA de desarrollo permita crear plantillas de utilidad y cuánto tarda la revisión | ídem | La verificación real espera a una WABA productiva |
| 22.47 | Valores con salto de línea, tabulación o más de 4 espacios seguidos (¿132012?) | ídem | Si Meta los acepta, el saneamiento sobra pero no daña |
| 22.48 | Que un link como valor de parámetro sea aceptable en una plantilla de UTILITY y no la recategorice a MARKETING | ídem | Recategorización: la pantalla lo advierte; habría que pasar el link a un botón URL (cambio de plantilla) |
| 22.49 | Precio de plantillas de utilidad dentro de la ventana desde el 01/10/2026 (terceros dicen que pasa a cobrarse, igual que el texto) | ídem | Ninguno en el diseño: plantilla y texto cuestan lo mismo dentro de la ventana en ambos escenarios |
| 22.50 | Que `rejected_reason` venga en el `GET` del nodo con los valores documentados | ídem | La pantalla muestra «Rechazada» sin motivo traducido; `detalle_meta` sigue mostrando el texto |

## Avisos al equipo

- **Cristian** (dueño de `conexion-whatsapp`, HU-E2-03, y revisor del canal): la URL de la app de
  Meta pasa a ser `/webhooks/whatsapp` y el campo `message_template_status_update` tiene que estar
  suscripto; la URL por empresa se fija por cuenta con `POST /{waba_id}/subscribed_apps` +
  `override_callback_uri` [WH-OVR]. Automatizar ese override al conectar WhatsApp es de
  `integrations` y **no** entra en esta unidad: se anota en el pendiente #3 del épico 8.
- **Luciano (dueño de Render)**: `WHATSAPP_PLANTILLAS_MINUTOS` (default 30) se carga a mano en el
  servicio `cheatsheet-worker` solo si quiere otro valor; el dashboard es la fuente de verdad.
- **U7 (`entregas-de-whatsapp`)**: mantener tal cual los cuatro nombres que le deja U6:
  `ConsultarPlantillaParaEnviar` (con `texto`), `api/whatsapp_notificaciones.py`,
  `empresa_de_la_cuenta_de_whatsapp` y `PortMensajeria.enviar_plantilla`. La migración 0036 es de U6 y
  la de U7 (`externo_id`) toma la 0037. U7 ya no tiene que reverificar la afirmación del ADR-0011 §5.
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

## Revalidación contra develop (2026-10-06)

Con U5 mergeada (#104) y el ADR-0011 aceptado (#62), se contrastó este plan con develop `2b96b4a`. **El
Gate 1 aprobado sigue vigente**: no cambia nada de lo que aprobó Luciano (Pregunta 1: envío automático;
Pregunta 2: « Gracias.» al final). Todas las correcciones ya están aplicadas arriba y son de tres clases:

- **Mecánicas**: citas de línea, número de migración (0036, `down_revision = "0035"`), `TODO.md` §25 →
  §22.43–22.50, `render.yaml` (un solo servicio `cheatsheet-worker`), `armar_notificador(unidad, *, canal)`,
  `CLAVE_WABA_ID` local (R3), `.env.example`, `docs/architecture.md` §7, `pendientes.md`, `units.md`.
  El «Pedido al ADR-0011» desaparece: el §5 aceptado ya cubre el webhook por WABA y U6 ya verificó la
  afirmación contra [WH-OVR].
- **Aclaraciones de diseño sin efecto de producto**: `PortMensajeria.enviar_plantilla`; bucle de reintento
  compartido en `canal_errores.py`; `mensaje_para_el_usuario` solo para plantillas; `MetaNoDisponible(incierto)`
  y `MetaNoConectada`; regla de `armar_revision_de_meta` ante integración ausente o credencial ilegible;
  texto de fábrica del adaptador alineado con `DE_FABRICA`; extracción de `revision_de_meta.py`,
  `EstadoDePlantilla.tsx` y `motivosDeMeta.ts` de entrada; archivos de test nuevos por el tope de 400.
- **Reducciones de alcance**: la zona horaria ya la corrigió U5 (solo se separan `fecha` y `hora`); son
  tres avisos de turno y no cuatro (el recordatorio es de U8); el caso 21 pierde «con el código» y los
  casos 22 y 26 se achican porque U5 ya los cubre.

## Pregunta abierta

**Q1 — Formato del monto en el mensaje de cobro.** El texto de fábrica de U5 (ya mergeado, caso 16)
muestra «$ 1234.50»; el parámetro de plantilla de esta unidad se manda como «1.234,50», tal como se
aprobó. El mismo recordatorio diría dos cosas según salga como plantilla o como texto. **No está
decidido y esta unidad no toca el texto ni el caso 16 de U5.** Recomendación: un solo formateador es-AR
(« $ 1.234,50») para ambos caminos; es el formato que lee un cliente argentino y el cambio es un
formateador más el test 16 de U5. Lo decide Luciano; si se acepta, se hace en un cambio aparte.

## Estado de la implementación (2026-10-06)

Rama `feature/business_config-plantillas-de-whatsapp-en-meta`, un commit por unidad de trabajo, cada uno
verde por sí solo (`ruff`, `mypy`, `pytest`):

| Commit | Qué entrega |
|---|---|
| `docs(business_config): revalidate…` | La revalidación de este plan contra develop; cierra el Gate 1 |
| `feat(conversational): send approved WhatsApp templates and share the Meta retry loop` | `PortMensajeria.enviar_plantilla`, `canal_http.py` (bucle compartido), códigos 132000/132012/132015/132016, `error_user_msg` solo para plantillas |
| `feat(conversational): add the Meta message templates client` | `plantillas_meta.py`: `PlantillasDeMeta`, `PlantillasSimuladas`, `SinCuentaDeMeta` |
| `feat(business_config): track WhatsApp template state from Meta and seed templates unsent` | Agregado (7 estados, 7 campos, bordes, edición admisible), migración 0036, `DE_FABRICA` corregido |
| `feat(business_config): send templates to Meta on edit, reconcile their state and expose it` | `revision_de_meta.py`, `conciliacion.py`, `ConsultarPlantillaParaEnviar`, `ActualizarEstadoDesdeMeta`, `_RevisionViaMeta`, `routers/plantillas.py` (503 / 422 con el texto de Meta) |
| `feat(payments): send approved WhatsApp templates for payment reminders and turn notices` | Adaptadores de cobros y turnos, `plantillas_salientes.py`, `armar_notificador(unidad, *, canal)` |
| `feat(business_config): reconcile WhatsApp templates with Meta from Beat` | `tasks_business_config.py`, Beat, `WHATSAPP_PLANTILLAS_MINUTOS`, consultas `SECURITY DEFINER` desde `integrations` |
| `feat(conversational): receive WhatsApp template status updates at the app webhook` | `POST/GET /webhooks/whatsapp`, `whatsapp_notificaciones.py`, ruteo por WABA |
| `test(business_config): cover WhatsApp template state against PostgreSQL` | Tests de PostgreSQL (solo CI) |
| `feat(frontend): show the Meta state of WhatsApp templates and send them to review` | PAN-CFG-NOT: estados, motivo traducido, «Enviar a revisión», bloqueo de edición, BFF `envio` |
| `test(business_config): keep the WhatsApp template tests under the file size limit` | Tests partidos por debajo de 400 líneas |
| `fix(business_config): renumber the templates migration to 0036 after merging develop` | Develop tomó la 0035 (`correccion_de_fila_con_error`): la nuestra pasa a 0036 con `down_revision = "0035"`; una sola cabeza |
| `fix(integrations): reject a WhatsApp business account already linked to another empresa` | G4: índice único `uq_integracion_waba`, `CuentaDeWhatsAppEnUso` (409) en el repositorio de integraciones |
| `fix(business_config): stop treating a template Meta no longer lists as approved` | G3: la aprobada que Meta ya no lista vuelve a `SIN_ENVIAR`; `estados()` o trae la lista entera o falla |

**Gates locales (actualizados el 2026-10-07, después de G3 y G4):** `ruff format --check`, `ruff check`, `mypy` (725 archivos) y `pytest` (2612 pasan, 541 se
saltean por falta de PostgreSQL/Redis) verdes; `guard_architecture --scan` verde; frontend `lint`,
`typecheck`, `format:check` y `test:coverage` (1040 tests) verdes. Gate 2 (verificación real) y Gate 3 (PR)
siguen sin llenar.

**Solo CI:** `test_migracion_0036.py` (incluye el índice único de la WABA), `test_waba_unica_postgres.py`, `test_plantillas_en_meta_postgres.py`, el `PUT /plantillas` de
`test_api_conversacional.py` (ahora con un cuerpo que no empieza con variable) y `test_guards.sh`.

**Para el dueño:** agregar `WHATSAPP_PLANTILLAS_MINUTOS=30` a `backend/.env.example` (junto a
`WHATSAPP_SONDEO_*`). `render.yaml` no cambia: el worker usa el default 30 y el dashboard de Render es la fuente
de verdad si se quiere otro valor. Registrar en la app de Meta la URL `/webhooks/whatsapp` y suscribir el campo
`message_template_status_update` (`TODO.md` §22.45); sin eso funciona igual, con la demora de la conciliación.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | Aprobado por Luciano con las recomendaciones de las preguntas. Condición cumplida el 2026-10-05 (ADR-0011 aceptado, [#62](https://github.com/cheatsheet12/CheatSheet/pull/62)); revalidado contra develop `2b96b4a` el 2026-10-06; **Gate 1 cerrado, ya se puede escribir código** |
| 2 · Verificación | 2026-10-07 | Aprobado por Luciano (G1), con G3 y G4 corregidos antes del PR |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Gate 1 (2026-10-04): Pregunta 1 → automático: cuando la empresa tiene WhatsApp conectado, las plantillas de fábrica se siembran y se envían a Meta sin esperar a un administrador.
- Gate 1 (2026-10-04): Pregunta 2 → sí: los textos de fábrica de `recordatorio_de_cobro` y `cobro_generado` terminan en « Gracias.» para que no terminen en una variable; se corrigen las filas no editadas.
- Implementación (2026-10-06): **el borde del texto se exige en `editar` y en `PlantillaDeNotificacion.nueva`, no en `__post_init__`.** Una fila editada antes de que Meta pidiera esta regla tiene que poder leerse: si el constructor levantara, listar las plantillas daría un error en vez de mostrarle al administrador el rechazo de Meta. Las variables sí se siguen validando siempre. No se creó `PlantillaNoEditable`: el dominio levanta `EntradaInvalida` con las frases del plan, que es lo que la API ya mapea a 422.
- Implementación: **el saneo de saltos de línea (caso 25) vive en `ConsultarPlantillaParaEnviar`** (`limpiar_valor`), no en cada adaptador: un solo lugar para los dos contextos que mandan.
- Implementación: **no se alineó el texto de fábrica de cobros con `DE_FABRICA`** (punto 16 de la revalidación). Hacerlo cambia el texto de U5 y su caso 16 (monto «$ 1234.50» y « Gracias.»), que es justo la **Pregunta abierta Q1**: se registra en `TODO.md` §22.52 para decidirla junto con ella. Los tres textos de turnos **ya coinciden** con `DE_FABRICA` y tienen un test que lo afirma (`test_plantillas_salientes.py`).
- Implementación: el 503 lo emite un manejador propio de `MetaNoDisponible` (`routers/plantillas.manejar_meta_no_disponible`), registrado en `main.py`; el BFF no reenvía el detalle de un 503, así que el cliente web muestra un texto fijo («No se guardó nada: volvé a intentarlo en un rato»).
- Implementación: `ActualizarEstadoDesdeMeta` no vincula una fila por **nombre e idioma** cuando el evento trae un id de Meta distinto del que la fila ya tiene (es otra plantilla de Meta con el mismo nombre); lo encontró el test de aislamiento por WABA.
- Implementación: la conciliación **no reintenta en cada corrida** una plantilla que Meta ya refutó (`SIN_ENVIAR` con el texto de Meta como detalle) ni una cuyo texto viejo termina en variable: esperan al administrador. Sí reintenta la que quedó `SIN_ENVIAR` por «WhatsApp no está conectado».
- Implementación: `EnviarPlantillaAMeta` acepta `SIN_ENVIAR` y `RECHAZADA`, como dice la pantalla; una `DESHABILITADA` se recrea al editar su texto (con nombre versionado). `plantillas_meta.py` quedó en 308 líneas (el plan estimaba ≤ 250; sigue bajo el tope de 400). `ResolverPlantilla` quedó sin llamadores (el plan la dejaba sin cambios); la revisión de la unidad pidió quitarla y se quitó (ver los hallazgos de revisión).
- Implementación: los mensajes entrantes (`messages`) que lleguen a la URL de la app se registran y se ignoran con 200: no hay empresa a quién atribuirlos desde esa URL.
- Hallazgo de revisión: **los textos que manda Meta llegaban sin medida a columnas acotadas** (`motivo_meta` varchar(40), `meta_plantilla_id` varchar(64)). Un desborde da un error de base, un 500 y los reintentos de Meta durante horas. Los límites se definen una sola vez en el dominio (`LARGO_MAXIMO_MOTIVO`, `LARGO_MAXIMO_ID_EN_META`, `LARGO_MAXIMO_DETALLE`) y el modelo los usa. El motivo, que es informativo, se recorta (en el agregado, que cubre el webhook y la conciliación, y también al leer el webhook). Un id más largo que su columna se ignora con un aviso estructurado (`plantilla_meta_id_demasiado_largo`) y nunca se recorta: un id truncado coincidiría con otra fila. Cubierto con tests de ambos caminos.
- Hallazgo de revisión: **se quitó `ResolverPlantilla`**, sin llamadores en el código ni en los tests desde que esta unidad retiró el único que tenía (U7 y U8 usan `ConsultarPlantillaParaEnviar`). Se actualizaron las referencias en `plantillas.py`, `ports.py` y `models.py`.
- Gate 2 (2026-10-07): **G3 → una aprobada que Meta ya no lista deja de estar aprobada.** Antes seguía `APROBADA` y el envío fallaba con Meta 132001 sin texto de respaldo. Ahora la conciliación la pasa a **`SIN_ENVIAR`** con el detalle «Meta ya no la tiene: volvé a enviarla a revisión.» y le saca el id de Meta. Se eligió `SIN_ENVIAR` y no `DESHABILITADA` porque es el estado al que ya lleva un `DELETED` de Meta (`ESTADOS_DEL_NODO`), el que el panel ya muestra como «Atención» con su detalle y uno de los dos desde los que «Enviar a revisión» está permitido (con `RECHAZADA`); `DESHABILITADA` quiere decir que Meta la deshabilitó, y acá Meta no dijo nada. Con `SIN_ENVIAR` `ConsultarPlantillaParaEnviar` devuelve `None` (no `puede_usarse`) y el adaptador manda su texto de fábrica. Tiene un detalle, así que **no se reenvía sola** en cada corrida (como una refutada): vuelve a revisión cuando el administrador lo decide. **Solo se aplica con la lista entera:** `PortRevisionDeMeta.estados_completos` es falso en el doble de desarrollo (que devuelve vacío porque no recuerda nada), y `PlantillasDeMeta.estados()` ahora levanta `EnvioIncierto` —en vez de devolver una parte— si quedan páginas sin leer (tope de 10), si la respuesta no trae una lista o si una fila con id es ilegible; la conciliación ya trata ese error como «Meta no disponible» y no toca nada.
- Gate 2 (2026-10-07): **G4 → una WABA pertenece a una sola empresa.** El índice de `parametros->>'waba_id'` de la migración 0036 pasó a ser **único** y parcial (`sistema = 'WHATSAPP'` y id no vacío). Sin eso, una segunda empresa podía registrar la WABA de otra y robarle o bloquearle el ruteo del webhook de plantillas, que resuelve la empresa por WABA. El repositorio de integraciones traduce solo la violación de ese índice (por nombre, como `uq_cobro_clave_idempotencia` en cobros) a `CuentaDeWhatsAppEnUso`, una `InvarianteViolada` que la API contesta **409** con «Esa cuenta de WhatsApp Business ya está vinculada a otra empresa. Verificá el ID de la cuenta que pegaste.» (no nombra a la otra empresa). Si una base ya tuviera dos empresas con la misma WABA, la migración falla a propósito: lo resuelve una persona.
- Gate 2 (2026-10-07): **G5 → hallazgo aparte, no se implementa en esta unidad.** La conciliación hace E/S contra Meta con una transacción de base abierta y la tarea de Beat no tiene límite de tiempo de Celery. Se resuelve con el ADR-0014 (#101), junto con el resto de los casos de E/S dentro de transacción.
- Gate 2 (2026-10-07): **G2 → un solo formateador de dinero es-AR** para el texto de U5 y el de la plantilla de U6. Aprobado; se hace como cambio aparte, después de esta unidad (es la Pregunta abierta Q1).
- Gate 2 (2026-10-07): **renumeración a 0036.** Develop incorporó `0035_correccion_de_fila_con_error` (PR #105) mientras esta rama tenía su propia 0035. La migración de plantillas pasa a `0036_plantillas_en_meta.py` con `down_revision = "0035"` (una sola cabeza), y su test a `test_migracion_0036.py`. La migración de U7 (`externo_id`) toma la 0037.
