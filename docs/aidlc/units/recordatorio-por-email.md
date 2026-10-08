# Unidad: recordatorio-por-email

**HUs**: HS-T3 (RN-02 «por el canal configurado», RN-04, RN-05)   **Contexto dueño**: payments (business_config para la plantilla editable; `platform/email.py` para el transporte)   **Rama**: feature/payments-recordatorio-por-email

> Origen: pregunta 1 del Gate 1 de [`canal-real-de-whatsapp`](canal-real-de-whatsapp.md) (U5,
> 2026-10-04) y decisión C2 (2026-10-06): la cadena de escalamiento admite pasos `EMAIL`, HS-T3 RN-02
> pide despachar «por el canal configurado», y U5 sólo construyó WhatsApp. El paso `EMAIL` se
> registró como **unidad propia, U11**, en payments y sobre `platform/email.py`, que puede ir en
> paralelo con U6–U8; el paso `PANEL` quedó para el centro de notificaciones del épico 10.
> Responsable Luciano.
>
> **Base de la rama:** la cabeza local del tramo ii de
> [`entregas-de-whatsapp`](entregas-de-whatsapp.md) (U7), todavía sin mergear a `develop`. Ver
> «Dependencias» más abajo: este plan asume interfaces del tramo ii, no sólo de U5.

**Encuadre (Paso 0).** Contexto dueño: `payments` (el adaptador de envío del recordatorio).
Capas: `infrastructure/` de payments (adaptador nuevo y ruteo por canal), un ajuste chico en
`application/` de payments (el mensaje listo y el contacto llevan el email), `platform/email.py`
(clasificación de fallas), `business_config` (una plantilla de fábrica más) y la raíz de composición
(`api/`, `workers/`). Integración externa: el servidor SMTP transaccional, **ya existente** como
transporte compartido (no hay proveedor nuevo ni SDK). Sin migraciones.

## Qué hace

Hoy un paso `EMAIL` de la cadena de recordatorios de cobro queda `FALLIDO` con motivo
`CANAL_NO_SOPORTADO` sin intentar nada. Con esta unidad, ese paso **manda un correo** al email del
cliente por el transporte SMTP compartido, con el mismo contenido que el recordatorio de WhatsApp
(nombre, concepto, monto, vencimiento y link de pago si está activo) y el nombre de la empresa que
cobra. El correo pasa por la misma máquina de estados del tramo ii de U7: se reserva y se confirma
antes de hablar con el servidor, una falla transitoria se reintenta entre barridos (1 h, 2 h), una
permanente o incierta queda `FALLIDO` con su motivo, y **nunca se reenvía lo que pudo haber salido**.
El paso `PANEL` sigue `FALLIDO` (`CANAL_NO_SOPORTADO`) hasta el épico 10.

## Lo que existe hoy (relevado sobre la rama, cabeza `4839248`, 2026-10-07)

> CodeGraph: el worktree no tenía índice propio; se inicializó con `gentle-ai codegraph init` y se
> usó `codegraph_explore` para el camino de envío. El resto se leyó de los archivos.

**El camino del recordatorio (U5 + U7 tramo ii):**

- `payments/application/ports_de_recordatorios.py:62-85` — `PortEnvioDeRecordatorio` en dos
  tiempos: `preparar(empresa_id, cobro, canal, paso) -> MensajeListo | ResultadoDeEnvio` (toda la E/S
  de base; sólo deja pasar lo que la base rechaza) y `mandar(mensaje) -> ResultadoDeEnvio` (sólo habla
  con el canal, **nunca levanta**).
- `ports_de_recordatorios.py:45-59` — `MensajeListo(cobro_id, paso, canal, telefono, texto |
  plantilla)`, con el teléfono, el texto y la plantilla fuera del `repr`. **`telefono: str` es
  obligatorio**: no hay lugar para un email.
- `ports_de_recordatorios.py:19-33` — `ResultadoDeEnvio(estado, externo_id, codigo, transitoria)`.
  `transitoria=True` es lo único que hace que `EnvioConReintento` programe otro intento.
- `payments/application/reintentos.py:133-151` (paso nuevo) y `:245-247` (fila existente) — los dos
  llaman a `preparar` con el `canal` **del paso o de la fila**: el ruteo por canal puede vivir
  enteramente en el adaptador, sin tocar el caso de uso.
- `payments/domain/recordatorio.py:25-40` — `LARGO_MAXIMO_ULTIMO_ERROR = 60`, `REINTENTOS_MAXIMOS =
  3`, `ESPERA_BASE = 1 h`, `VENTANA_DE_ENVIO = 30 min`, motivos `COBRO_CERRADO` e `INCIERTO`.
  `EstadoEntrega` (`:43-55`) ya dice que «ningún email» informa `LEIDO`.
- `payments/infrastructure/envio.py:57` — `CANAL_WHATSAPP = "WHATSAPP"`; `:146-167` —
  `EnvioPorWhatsApp.preparar` devuelve `FALLIDO`/`CANAL_NO_SOPORTADO` (log
  `recordatorio_canal_sin_adaptador`) para cualquier canal que no sea WhatsApp; `:169-195` arma el
  mensaje; `:197-217` lo manda. El archivo tiene 240 líneas.
- `payments/application/ports_envio.py:34-50` — `ContactoDeCobro(nombre, telefono)` y
  `PortContactoDeCliente` («`None` si el cliente no existe o no tiene un WhatsApp registrado»).
  `payments/infrastructure/clientes.py:31-45` — `ContactoViaMasterData` devuelve `None` si no hay
  `contacto_whatsapp`. El cliente **sí tiene** `contacto_email: Email | None`
  (`master_data/domain/cliente.py:47`), pero hoy no viaja.
- `api/mercadopago.py:164-177` — `armar_envio(unidad, *, canal)` devuelve un único
  `EnvioPorWhatsApp`. Su llamador es `workers/tasks_payments.py:97`, dentro de `barrer_empresa`
  (`:72-120`), que arma el canal de WhatsApp una vez por empresa (`:88`).
- `payments/domain/dinero.py:20-28` — `formatear_es_ar(monto: Decimal)`: dos decimales,
  `ROUND_HALF_UP`, punto de miles y coma decimal; nunca `float`.

**El transporte de correo compartido:**

- `platform/email.py` (159 líneas) — `TransporteDeEmail` (`:60-75`), `TransporteSMTP` sobre
  `aiosmtplib==3.0.2` (`backend/pyproject.toml:51`) con timeout explícito (`:94-113`),
  `TransporteDeConsola` que no abre socket (`:116-136`) y `crear_transporte(settings)` (`:151-159`).
  Su docstring (`:19-21`) ya anticipaba a `payments` como consumidor, y `docs/architecture.md` §7
  (`:164`) declara `PortNotificacionEmail` para `reporting` y `payments`: **el edge ya está previsto**.
- **Hallazgo 1 — todas las fallas son iguales.** `TransporteSMTP.enviar` convierte cualquier
  `aiosmtplib.SMTPException` u `OSError` en un único `ErrorDeEnvioDeEmail` (`:106-112`): no distingue
  «el servidor dijo que no, para siempre» (5yz) de «no conecté» o «se cortó esperando la respuesta
  al `DATA`». Sin esa distinción el reintento del tramo ii no puede decidir.
- **Hallazgo 2 — el transporte loguea la dirección.** `email_enviado` y `envio_de_email_fallido`
  (`:109-113`) y `email_no_enviado_modo_consola` (`:132-136`) registran `destinatario` y `asunto`.
  Para invitaciones y avisos internos es la dirección de un usuario; con esta unidad pasaría a ser la
  de **cada cliente final de cada empresa**, una vez por recordatorio. `CLAUDE.md` §5: nunca loguear
  datos personales (pregunta 3).
- Consumidores actuales del transporte: `identity/infrastructure/email_invitacion.py:35`,
  `integrations/infrastructure/email_integracion.py:25`, `reporting/infrastructure/avisos.py:27`.
  Los tres atrapan `ErrorDeEnvioDeEmail`; cualquier subclase nueva los deja intactos.
- `platform/settings.py:285-310` — `EMAIL_ADAPTADOR` (`consola` | `smtp`), obligatorio `smtp` en
  producción; `:547-551` y `:657-659` — `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USUARIO`,
  `SMTP_PASSWORD`, `SMTP_REMITENTE`, `SMTP_TLS`, `SMTP_TIMEOUT_SEGUNDOS` (10). **No hacen falta
  variables nuevas.** `render.yaml` no declara ninguna `EMAIL_*`/`SMTP_*`: staging corre en consola
  (`docs/staging-deployment.md:204`). El proveedor transaccional sigue sin elegirse a propósito
  (`TODO.md` §2.2).
- Patrón de correo de un contexto: `reporting/infrastructure/avisos.py:37-90` — `string.Template`
  sobre archivos versionados, parte de texto y parte HTML, adaptador de consola aparte.

**La plantilla (U6):**

- `business_config/domain/plantilla.py:89-96` — `VARIABLES_POR_CODIGO`; el código
  `recordatorio_de_cobro` admite `nombre`, `monto`, `concepto`, `link`, `vencimiento`. El archivo
  tiene **390/400 líneas**.
- `business_config/application/plantillas.py:53-85` — `DE_FABRICA`, **un canal por código**, todas
  `WHATSAPP`; se siembran por empresa la primera vez que se listan (`:96-130`).
  `ConsultarPlantillaParaEnviar` (`:155-180`) devuelve `None` para cualquier plantilla que no sea de
  WhatsApp (`:168`). La tabla busca por `(empresa_id, codigo)` (índice no único,
  `infrastructure/models.py:86`).
- PAN-CFG-NOT **ya soporta** plantillas de otro canal: `EstadoDePlantilla.tsx:39` no muestra estado
  de Meta si el canal no es WhatsApp, `faq.ts:172` traduce `NO_APLICA` a «No requiere aprobación», y
  `PlantillasDeNotificacion.tsx:70-73,99` muestra la columna de canal sola el día que haya dos. La
  conciliación con Meta filtra por canal (`business_config/application/conciliacion.py:102`).

**El nombre de la empresa:** `identity/application/empresa.py:34-56` publica
`ConsultarDatosFiscales` (con `razon_social`). Ya lo consumen `billing/infrastructure/emisor.py:15`
(import directo de la capa `application/`, permitido por R3) y la raíz `api/reporteria.py:95-105`
(`armar_nombre_de_empresa`, con un nombre provisorio si falta).

## Dependencias

- **Depende de U7 tramos i y ii mergeados** (no sólo de U5, que es lo que dice hoy `units.md`). Usa
  `preparar`/`mandar`, `MensajeListo`, `ResultadoDeEnvio.transitoria` y `EnvioConReintento`, que
  existen sólo en esa rama. Interfaces asumidas, a re-chequear apenas lleguen a `develop`:
  `PortEnvioDeRecordatorio` con las firmas de `ports_de_recordatorios.py:74-85`; `preparar` corre
  dentro del savepoint de la reserva y deja pasar `SQLAlchemyError`; `mandar` nunca levanta y sólo
  `transitoria=True` se reintenta (pregunta 6).
- **No depende** de U7 tramo iii ni de U8. Si el tramo iii (traducción de motivos en PAN-COB-02) llega
  antes que esta unidad, se suman ahí las etiquetas de los motivos nuevos; si llega después, el tramo
  iii los incluye. Es una tabla de textos, no una interfaz.
- **No depende de terceros para cerrarse**: todo se prueba con un transporte falso. Lo que sólo se
  verifica con un servidor SMTP real va a `TODO.md` (ver abajo).

## Contratos — SMTP (RFC 5321) y `aiosmtplib` 3.0.2

No hay proveedor ni API nuevos: el contrato es el protocolo SMTP, que el transporte ya habla.

> Fuentes primarias: RFC 5321 (<https://www.rfc-editor.org/rfc/rfc5321.html>), §4.2.1 (severidad de
> las respuestas), §4.5.3.2.6 (timeout de fin de `DATA`) y §6.1 (duplicados por respuesta perdida);
> el código instalado de `aiosmtplib` 3.0.2 (`aiosmtplib/errors.py:24-135`, `protocol.py:240-370`),
> leído del entorno virtual. Lo que no se verificó dice **«a confirmar»**.

| Hecho | Fuente | Consecuencia en el diseño |
|---|---|---|
| `4yz`: el comando no se aceptó, la acción **no ocurrió** y la condición es temporaria | RFC 5321 §4.2.1 | Transitoria → reintento entre barridos |
| `5yz`: el comando no se aceptó y la acción no ocurrió, en forma permanente | RFC 5321 §4.2.1 | Permanente → `FALLIDO`, sin reintento |
| Si la conexión se cae después del `.` final del `DATA` y antes de la respuesta, el cliente no sabe si el servidor aceptó el mensaje: reenviarlo puede duplicarlo | RFC 5321 §6.1 | Incierta → `FALLIDO`/`INCIERTO`, **nunca** se reenvía (la misma regla de U5/U7 para Meta) |
| El servidor puede tardar hasta **10 min** en contestar el fin de `DATA` | RFC 5321 §4.5.3.2.6 | Con `SMTP_TIMEOUT_SEGUNDOS=10` un relay lento produce `INCIERTO` (falso fallido, no duplicado). A medir con el proveedor real (TODO) |
| `SMTPConnectError` / `SMTPConnectTimeoutError`: no hubo conexión | `aiosmtplib/errors.py:41-57` | Nada salió → se puede reintentar **dentro** de la llamada |
| `SMTPServerDisconnected` / `SMTPReadTimeoutError`: se cortó o no contestó, en **cualquier** fase (no dice cuál) | `errors.py:34-63`, `protocol.py:249-254` | Como no se sabe si fue después del `DATA`, se trata como **incierta** siempre (conservador: puede dar un falso `FALLIDO`, nunca un duplicado) |
| `SMTPResponseException` y subclases (`SMTPDataError`, `SMTPSenderRefused`, `SMTPRecipientRefused`, `SMTPAuthenticationError`, `SMTPHeloError`) traen `code` | `errors.py:71-127` | Se clasifican por la primera cifra del código |
| `SMTPRecipientsRefused` trae la lista de rechazos de cada destinatario | `errors.py:130-135` | Un solo destinatario: se usa su código |
| `SMTPNotSupported` (p. ej. STARTTLS no ofrecido) | `errors.py:65-69` | Permanente (es configuración) |

**Ambientes.**

| Ambiente | `EMAIL_ADAPTADOR` | Qué pasa |
|---|---|---|
| Tests (CI y local) | — | Transporte falso o `aiosmtplib.send` reemplazado por un doble inyectado; **ninguna red ni espera real** |
| Local / staging hoy | `consola` (sin variable) | `TransporteDeConsola`: no abre socket; el recordatorio queda `ENVIADO` sin salir de la máquina, igual que WhatsApp `simulado` |
| Staging con proveedor (TODO) | `smtp` | Sale por el relay del proveedor elegido |
| Producción | `smtp` (obligatorio, `settings.py:305-310`) | `consola` está prohibido al arrancar |

## Diseño

### D-U11-1 · Un adaptador por canal y un ruteador delante

- `payments/infrastructure/envio_por_canal.py` (**nuevo**, ~60 líneas): `EnvioPorCanal` implementa
  `PortEnvioDeRecordatorio` y delega por canal: `preparar` elige el adaptador por el `canal` que
  recibe; `mandar` por `mensaje.canal`. Un canal sin adaptador (`PANEL`, o cualquier valor
  desconocido) → `FALLIDO`/`CANAL_NO_SOPORTADO` con el log de hoy. El caso de uso
  (`reintentos.py`, `recordatorios.py`) **no cambia**.
- `EnvioPorWhatsApp` conserva su chequeo de canal como defensa en profundidad; el log y el motivo
  siguen iguales.

### D-U11-2 · `EnvioPorEmail`

`payments/infrastructure/envio_por_email.py` (**nuevo**, ~170 líneas; `envio.py` no crece):

- **`preparar`** (toda la E/S de base, dentro del savepoint de la reserva): lee el contacto
  (`PortContactoDeCliente`), el nombre de la empresa (D-U11-4) y la plantilla editable si la hay
  (D-U11-5). Sin email → `FALLIDO`/`SIN_EMAIL` (log `recordatorio_sin_email`, sólo `cobro_id` y
  `paso`). Deja pasar `SQLAlchemyError`, igual que `EnvioPorWhatsApp.preparar` (`envio.py:158-162`).
  Devuelve un `MensajeListo` con `canal="EMAIL"`, `email`, `asunto` y `texto`.
- **`mandar`** (sin leer la base): compone el `EmailMessage` y lo entrega al transporte. Hasta **3
  intentos dentro de la llamada sólo si no hubo conexión** (`EmailSinConexion`, ver D-U11-3), con
  esperas `(1.0, 2.0)` s y `esperar` inyectable (los tests nunca duermen), el mismo esquema que el
  canal de WhatsApp. Resultado:

  | Falla del transporte | `ResultadoDeEnvio` | ¿Reintento entre barridos? |
  |---|---|---|
  | Ninguna | `ENVIADO`, `externo_id=None` | — |
  | `EmailSinConexion` tras 3 intentos | `FALLIDO`, `SMTP_SIN_CONEXION`, `transitoria=True` | Sí (1 h, 2 h) |
  | `EmailRechazadoTemporalmente` (4yz) | `FALLIDO`, `SMTP_4xx` con el código, `transitoria=True` | Sí |
  | `EmailRechazado` (5yz, STARTTLS no soportado) | `FALLIDO`, `SMTP_5xx` con el código | No |
  | `EnvioDeEmailIncierto` (desconexión o timeout de lectura) | `FALLIDO`, `INCIERTO` | **No** |
  | Cualquier otra excepción (incluido un encabezado inválido) | `FALLIDO`, `ERROR` | No |

  **Nunca levanta** (contrato del puerto); el `except` amplio final lleva `noqa: BLE001` con la misma
  justificación que `envio.py:201-204`. Sin plantilla de Meta ni `wamid`: `externo_id` queda `None`
  (no hay callbacks de entrega para el correo, D-U11-6).
- **Contenido.** Asunto: `Recordatorio de pago — {empresa}`. Cuerpo de texto: la plantilla editable
  resuelta o, si no hay, el texto de fábrica (mismo contenido que el de WhatsApp más el nombre de la
  empresa y el vencimiento). Parte HTML: **el mismo texto, escapado con `html.escape`**, con el link
  como `<a>` (escapado también); ningún valor del cliente o de la empresa entra al HTML sin escapar.
  Monto con `formatear_es_ar` (`Decimal`, `ROUND_HALF_UP`).
- **Remitente.** `From: "{empresa} vía CheatSheet" <dirección de SMTP_REMITENTE>`, armado con
  `email.utils.formataddr` sobre la dirección del remitente configurado. Sin `Reply-To` (la empresa
  no tiene un email de contacto en el DER; el correo invita a pagar por el link).
- **Encabezados seguros.** El nombre de la empresa y el asunto pasan por una limpieza de saltos de
  línea (el mismo criterio que `limpiar_valor`, `business_config/application/plantillas.py:136-138`)
  antes de entrar a un encabezado; si aun así `EmailMessage` rechaza un valor (`ValueError`), el
  resultado es `FALLIDO`/`ERROR`, nunca una excepción hacia el barrido.
- **`Message-ID` determinístico**: `<recordatorio.{cobro_id}.{paso}@{dominio del remitente}>`. No se
  guarda (se deriva de la fila) y no lleva datos personales; sirve para correlacionar un rebote
  futuro y para que un servidor que deduplica por `Message-ID` descarte un eventual duplicado.

### D-U11-3 · El transporte clasifica sus fallas (`platform/email.py`)

Subclases de `ErrorDeEnvioDeEmail` (los tres consumidores actuales no cambian), cada una con
`codigo: int | None` (el código SMTP, nunca el texto de la respuesta, que puede traer la dirección):

- `EmailSinConexion` — `SMTPConnectError`, `SMTPConnectTimeoutError`, `OSError` de conexión.
- `EmailRechazadoTemporalmente` — `SMTPResponseException` con código `4yz` (y `SMTPRecipientsRefused`
  con el `4yz` del único destinatario).
- `EmailRechazado` — código `5yz`, `SMTPNotSupported`, `SMTPRecipientsRefused` con `5yz`.
- `EnvioDeEmailIncierto` — `SMTPServerDisconnected`, `SMTPReadTimeoutError`, `SMTPTimeoutError` que
  no sea de conexión.

El orden de los `except` importa (`SMTPConnectTimeoutError` es a la vez `SMTPTimeoutError` y
`SMTPConnectError`; `SMTPConnectResponseError` es a la vez de conexión y de respuesta): se prueba con
una tabla. `aiosmtplib.send` se inyecta en el constructor de `TransporteSMTP` (por defecto el real)
para poder probar la clasificación sin red. El archivo pasa de 159 a ~230 líneas.

### D-U11-4 · El nombre de la empresa

`payments/infrastructure/empresa.py` (**nuevo**, ~35 líneas): `NombreViaIdentity` sobre
`ConsultarDatosFiscales` de `identity/application`, el mismo patrón que
`billing/infrastructure/emisor.py`. Puerto local en payments: `PortNombreDeEmpresa.nombre(empresa_id)
-> str` en `ports_envio.py`. Sin razón social → un nombre provisorio neutro («tu proveedor»), sin
levantar. Se lee **una vez por barrido** (cache en la instancia; el adaptador se arma por unidad de
trabajo, así que el nombre de la empresa A nunca llega a un correo de la B).

**No hace falta ADR**: es un import de la capa `application/` de `identity`, permitido por R3 y ya
usado por `billing` y por `reporting`; `identity` es upstream de todos en el Context Map (§4, `:81`).
El canal de correo para `payments` ya figura en `docs/architecture.md` §7 (`:164`).

### D-U11-5 · La plantilla editable del correo (pregunta 1)

Con la recomendación de la pregunta 1:

- `business_config/domain/plantilla.py`: `VARIABLES_POR_CODIGO` gana
  `"recordatorio_de_cobro_por_email"` con `nombre`, `monto`, `concepto`, `link`, `vencimiento` y
  `empresa` (+2 líneas: el archivo queda en 392/400 — si un cambio de U6/U7 lo empujara al tope,
  primero se extrae la tabla a un módulo hermano).
- `business_config/application/plantillas.py`: `DE_FABRICA` gana el código con
  `CanalNotificacion.EMAIL` (nace `NO_APLICA`, no va a Meta). Caso de uso nuevo
  `ConsultarTextoDePlantilla(codigo, variables) -> str | None`: el cuerpo resuelto de una plantilla
  **que no es de WhatsApp**, o `None` (no existe, variables faltantes). Sin aprobación: RN-03/RN-04 de
  HU-E11-02 sólo aplican al canal que la requiere.
- `api/plantillas_salientes.py`: `armar_plantillas_de_email(unidad)` con su adaptador (`Protocol`
  local en payments, `TextosDeEmail.texto(codigo, variables)`).
- Frontend: **ningún cambio**; PAN-CFG-NOT ya muestra canal y «No requiere aprobación».

Si la respuesta es «no», D-U11-5 se cae entero: el cuerpo es un archivo versionado en
`payments/infrastructure/plantillas/` (como `reporting`) y la unidad baja ~150 líneas.

### D-U11-6 · Qué significa `ENVIADO` para un correo (pregunta 2)

`ENVIADO` = el servidor SMTP aceptó el mensaje (respuesta `250` al fin del `DATA`). El correo no
tiene callbacks como `statuses[]`: los rebotes llegan después, por correo, al buzón del remitente y
con formato de cada proveedor. Con la recomendación de la pregunta 2 la unidad **no** procesa
rebotes; queda en `TODO.md` atado a la elección del proveedor.

### D-U11-7 · Cambios chicos en `application/` de payments

- `MensajeListo` (`ports_de_recordatorios.py:45-59`): `telefono` pasa a `str | None = None`; se
  agregan `email: str | None` y `asunto: str | None` (fuera del `repr`). `__post_init__` exige el
  destino que corresponde al canal (`WHATSAPP` → teléfono; `EMAIL` → email y asunto). +~15 líneas.
- `ContactoDeCobro` (`ports_envio.py:34-39`): `telefono: str | None`, `email: str | None`.
  `PortContactoDeCliente` devuelve `None` sólo si el cliente no existe; cada adaptador decide con su
  propio campo (`SIN_TELEFONO` / `SIN_EMAIL`). `ContactoViaMasterData` lleva los dos.
  `EnvioPorWhatsApp._armar` cambia su chequeo de `contacto is None` a `contacto.telefono is None`.

### Raíz de composición

- `api/mercadopago.py`: `armar_envio(unidad, *, canal, transporte_de_email)` devuelve
  `EnvioPorCanal({WHATSAPP: EnvioPorWhatsApp(...), EMAIL: EnvioPorEmail(...)})`.
- `workers/tasks_payments.py`: `barrer_empresa` arma el transporte una vez por proceso con
  `crear_transporte(recursos.settings)` (no tiene transacción) y lo pasa. El docstring se actualiza.
- **Otros contextos**: `business_config` por su caso de uso publicado (C/S, ya permitido),
  `identity` por su servicio de aplicación (ver D-U11-4). Ningún import nuevo de `domain/` ni de
  `infrastructure/` ajenos; `guard_architecture` sin cambios.
- **Frontend**: No aplica (salvo las etiquetas de motivo si el tramo iii de U7 ya está, ver
  «Dependencias»). PAN-COB-02 ya muestra el canal de cada recordatorio y PAN-CFG-RN ya ofrece `EMAIL`
  (`frontend/src/features/payments/api/regla.ts:18`).

## Infraestructura

- **Migraciones**: **ninguna.** `recordatorio.canal`, `ultimo_error` (60 caracteres: los motivos
  nuevos miden ≤ 18), `intentos` y `proximo_intento_en` ya existen (0037/0038). Si al implementar
  apareciera una, toma el **número libre al mergear**.
- **Trabajo asíncrono**: el mismo barrido horario (`tasks_payments.barrer_empresa`, cola
  `notifications`, Beat). Idempotencia: el índice único `(cobro_id, paso)` y la máquina de estados del
  tramo ii. El peor caso de un envío (3 × `SMTP_TIMEOUT_SEGUNDOS` + 3 s ≈ 33 s) queda muy por debajo
  de `VENTANA_DE_ENVIO` (30 min).
- **Configuración**: **ninguna variable nueva.** El worker necesita las mismas `EMAIL_ADAPTADOR` y
  `SMTP_*` que la API. `.env.example` y el dashboard de Render están fuera del alcance del agente:
  quedan como **acciones del dueño** (abajo).
- **Integraciones externas**: el relay SMTP del proveedor transaccional (sin elegir, `TODO.md` §2.2).
  Timeout `SMTP_TIMEOUT_SEGUNDOS`; reintento con espera dentro de la llamada sólo sin conexión;
  reintento entre barridos para transitorias; nada para inciertas.

**Acciones del dueño (no las puede hacer el agente):**

1. `backend/.env.example`: verificar que `EMAIL_ADAPTADOR` y las siete `SMTP_*` estén declaradas con
   un comentario que diga que **también las lee el worker** (el barrido de recordatorios).
2. Render, servicio `cheatsheet-worker`: cuando se elija el proveedor, cargar `EMAIL_ADAPTADOR=smtp` y
   las `SMTP_*` iguales a las de `cheatsheet-api`. Hasta entonces, sin variable, el worker corre en
   consola (staging) y los recordatorios por email quedan `ENVIADO` sin salir.
3. `docs/staging-deployment.md` §4 bis.2: una línea con lo mismo (la unidad la agrega si el dueño lo
   aprueba en la pregunta 5).

## Riesgos que obligan a tests (marcar los que apliquen)

- [x] Toca dinero → el monto **se muestra**: test de formato con `Decimal` (`1234.5` → `1.234,50`,
      `ROUND_HALF_UP`), nunca `float`.
- [ ] Toca comprobantes fiscales / CAE → No aplica.
- [ ] Consume un webhook → No aplica (sin rebotes, D-U11-6).
- [x] Datos con `empresa_id` → no agrega tablas, pero el correo lleva el **nombre de la empresa**:
      test de que el adaptador armado para A nunca pone el nombre de B, y caso de RLS existente para
      la lectura de la plantilla.
- [ ] Usa salida de un LLM → No aplica.
- [x] Datos personales → **ningún log** de los módulos nuevos ni del transporte lleva email, nombre,
      asunto, texto ni la respuesta del servidor (captura de logs). El correo sale al proveedor SMTP,
      que es el destino del dato, no un LLM.
- [x] **Duplicados** → una falla incierta nunca se reintenta (ni dentro de la llamada ni entre
      barridos); test por cada clase de excepción de `aiosmtplib`.
- [x] **Inyección** → valores con `<script>`, `"` y saltos de línea en nombre, concepto y razón
      social: el HTML sale escapado y ningún encabezado se parte.
- [x] **Red en tests** → `aiosmtplib.send` inyectado y `esperar` falso; ningún test abre un socket ni
      duerme.

**Riesgos residuales (documentados, no cubiertos por diseño):**

- Un `SMTPServerDisconnected` **antes** del `DATA` (p. ej. en el `EHLO`) se trata como incierto y deja
  un falso `FALLIDO`/`INCIERTO`. Es el precio de no poder distinguir la fase con `aiosmtplib`; la
  alternativa (un cliente SMTP por fases) no se justifica para un recordatorio.
- Con un timeout de 10 s y un relay que tarde más en confirmar el `DATA`, el mensaje puede llegar y
  quedar `FALLIDO`/`INCIERTO` en PAN-COB-02. Se mide con el proveedor real (TODO).
- `ENVIADO` no garantiza la bandeja de entrada (spam, rebote tardío). Ver D-U11-6.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/platform/email.py` (clasificación de fallas; `send` inyectable; logs sin dirección ni asunto — pregunta 3)
- [ ] `backend/src/cheatsheet/contexts/payments/application/ports_de_recordatorios.py` (`MensajeListo` con `email` y `asunto`)
- [ ] `backend/src/cheatsheet/contexts/payments/application/ports_envio.py` (`ContactoDeCobro` con `email`; `PortNombreDeEmpresa`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/clientes.py` (`ContactoViaMasterData` con el email)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/envio.py` (chequeo de teléfono; docstring: el email ya no «queda `FALLIDO`»)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/envio_por_email.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/envio_por_canal.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/empresa.py` (nuevo: `NombreViaIdentity`)
- [ ] `backend/src/cheatsheet/contexts/business_config/domain/plantilla.py` (código nuevo — pregunta 1)
- [ ] `backend/src/cheatsheet/contexts/business_config/application/plantillas.py` (`DE_FABRICA`, `ConsultarTextoDePlantilla` — pregunta 1)
- [ ] `backend/src/cheatsheet/api/plantillas_salientes.py` (`armar_plantillas_de_email` — pregunta 1)
- [ ] `backend/src/cheatsheet/api/mercadopago.py` (`armar_envio` con `EnvioPorCanal`)
- [ ] `backend/src/cheatsheet/workers/tasks_payments.py` (transporte de correo para el barrido)
- [ ] `backend/tests/platform/test_email_clasificacion.py` (nuevo)
- [ ] `backend/tests/contexts/payments/infrastructure/test_envio_por_email.py` (nuevo)
- [ ] `backend/tests/contexts/payments/infrastructure/test_envio_por_canal.py` (nuevo)
- [ ] `backend/tests/contexts/payments/application/test_recordatorio_por_email.py` (nuevo: el barrido con dobles; `test_cobros_y_recordatorios.py` tiene 1000 líneas y no crece)
- [ ] `backend/tests/contexts/business_config/application/test_plantilla_de_email.py` (nuevo — pregunta 1)
- [ ] `backend/tests/api/test_armar_envio_por_canal.py` (nuevo: cableado de la raíz)
- [ ] Tests existentes de `EnvioPorWhatsApp`, `ContactoViaMasterData` y los de invitación por email (`tests/contexts/identity/infrastructure/test_invitacion_email_y_token.py`): ajustar a las firmas nuevas, sin cambiar lo que afirman
- [ ] `docs/architecture.md` §7 (`:164`): `PortNotificacionEmail` en payments = `EnvioPorEmail` sobre `platform/email.py`
- [ ] `docs/aidlc/epicas/06-cobros-y-recordatorios/pendientes.md` (nota: el paso `EMAIL` sale desde U11)
- [ ] `docs/aidlc/TODO.md` (filas nuevas, abajo)
- [ ] `docs/aidlc/units.md` (sólo la fila de U11, al reclamarla tras el Gate 1)

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — Un cobro vencido con regla `[EMAIL a los 3 días]` y cliente con email: hoy queda `FALLIDO`/`CANAL_NO_SOPORTADO`. GREEN: sale un correo por el transporte y la fila queda `ENVIADO`, `externo_id` nulo | caso de uso (dobles) | pendiente |
| 2 | Cadena mixta `[WHATSAPP 3, EMAIL 7]`: el paso 1 sale por el canal de WhatsApp y el 2 por el transporte de correo | caso de uso | pendiente |
| 3 | Paso `PANEL` → `FALLIDO`/`CANAL_NO_SOPORTADO`, sin tocar ningún canal | unit (`EnvioPorCanal`) | pendiente |
| 4 | Cliente sin email → `FALLIDO`/`SIN_EMAIL`, sin llamar al transporte; cliente sin WhatsApp en un paso `EMAIL` → sale igual | unit | pendiente |
| 5 | Clasificación del transporte: tabla con cada excepción de `aiosmtplib` 3.0.2 (conexión, timeout de conexión, `SMTPConnectResponseError`, 421, 450, 451, 452, 535, 550, 553, `SMTPRecipientsRefused` con 4yz y con 5yz, `SMTPNotSupported`, desconexión, timeout de lectura) → su clase y su código | unit | pendiente |
| 6 | Sin conexión en el 1.º y 2.º intento, éxito en el 3.º → `ENVIADO`; esperas registradas `(1.0, 2.0)`, ninguna real | unit | pendiente |
| 7 | Sin conexión 3 veces → `FALLIDO`/`SMTP_SIN_CONEXION`, `transitoria`; el barrido programa el reintento a +1 h sobre la misma fila (`UPDATE`) | unit + caso de uso | pendiente |
| 8 | 4yz → `transitoria`, reintento programado; tras el 3.º intento entre barridos queda `FALLIDO` y la cadena sigue con el paso siguiente | caso de uso | pendiente |
| 9 | 5yz → `FALLIDO`/`SMTP_550`, **sin** reintento | caso de uso | pendiente |
| 10 | Desconexión o timeout de lectura → `FALLIDO`/`INCIERTO` al primer intento, **un solo** llamado al transporte y nunca reintentado | unit + caso de uso | pendiente |
| 11 | El adaptador nunca levanta: un transporte que levanta `RuntimeError` → `FALLIDO`/`ERROR` | unit | pendiente |
| 12 | Contenido: asunto con el nombre de la empresa; cuerpo con nombre, concepto, monto `1.234,50` (desde `Decimal("1234.5")`), vencimiento en hora argentina y link sólo si está activo | unit | pendiente |
| 13 | HTML escapado: `<script>` y `"` en nombre, concepto y razón social salen escapados en la parte HTML y literales en la de texto | unit | pendiente |
| 14 | Salto de línea en la razón social → el asunto y el `From` no se parten; un valor que `EmailMessage` rechace → `FALLIDO`/`ERROR` | unit | pendiente |
| 15 | `Message-ID` determinístico por `(cobro_id, paso)` y sin datos personales; `From` con el nombre de la empresa y la dirección de `SMTP_REMITENTE` | unit | pendiente |
| 16 | Plantilla editable de email existente → el cuerpo sale de ella; sin plantilla o con una variable faltante → texto de fábrica (pregunta 1) | unit + caso de uso | pendiente |
| 17 | `ConsultarTextoDePlantilla` ignora plantillas de WhatsApp y `ConsultarPlantillaParaEnviar` ignora la de email; `ListarPlantillas` siembra la de email con `NO_APLICA` y la conciliación con Meta no la toca (pregunta 1) | unit | pendiente |
| 18 | Aislamiento: el adaptador armado para la empresa A pone el nombre de A aunque luego se arme otro para B (dos unidades de trabajo) | unit (raíz) | pendiente |
| 19 | Logs: ningún evento de `platform/email.py`, `envio_por_email.py` ni `envio_por_canal.py` contiene el email, el nombre, el asunto, el texto ni el mensaje del servidor (captura de logs) | unit | pendiente |
| 20 | Los consumidores existentes (`identity`, `integrations`, `reporting`) siguen atrapando `ErrorDeEnvioDeEmail` con las subclases nuevas (regresión) | unit | pendiente |
| 21 | `armar_envio` cablea `EnvioPorCanal` con WhatsApp y email; `barrer_empresa` arma un solo transporte por proceso | unit (raíz/worker) | pendiente |
| 22 | `preparar` del email deja pasar un `SQLAlchemyError` al leer el contacto o el nombre (el savepoint de la reserva se deshace y no queda fila) | unit | pendiente |
| 23 | `ruff`, `mypy --strict`, `pytest`, `guard_architecture --scan` y `test_guards.sh` pasan | gate | pendiente |

TDD: **activado** por el flujo del repositorio (`CLAUDE.md` §5 «every fixed bug starts with a test»
y la práctica de U5–U7: RED observado antes de implementar); runner `pytest` desde la raíz.

## Verificaciones no posibles sin un servidor SMTP real → `TODO.md` §22

Las filas de §22 de esta rama terminan en **22.61**; esta unidad toma las siguientes libres **al
implementar** (hoy, 22.62 a 22.66) — se re-chequea al mergear porque otras ramas también agregan:

| # | Qué verificar | Unidad | Qué pasa si falla |
|---|---|---|---|
| 22.62 | Elegir el proveedor transaccional y cargar `EMAIL_ADAPTADOR=smtp` + `SMTP_*` en `cheatsheet-api` **y** `cheatsheet-worker` (ver §2.2) — responsable el dueño | U11 | Ningún recordatorio por email sale de verdad; quedan `ENVIADO` en consola |
| 22.63 | Con el proveedor: que un destinatario inexistente vuelva como `5yz` en el `RCPT` o como rebote posterior (y cuál de los dos) | U11 | Si rebota después, PAN-COB-02 muestra `ENVIADO` para un correo que no llegó (D-U11-6) |
| 22.64 | Cuánto tarda el relay en contestar el fin del `DATA` contra `SMTP_TIMEOUT_SEGUNDOS=10` (RFC 5321 §4.5.3.2.6 admite 10 min) | U11 | Falsos `FALLIDO`/`INCIERTO`; se sube el timeout del worker |
| 22.65 | Qué códigos `4yz` devuelve el proveedor ante límite de envío (rate limit) y si conviene una espera mayor que 1 h/2 h | U11 | Se ajusta la clasificación o la espera |
| 22.66 | Entregabilidad: SPF/DKIM/DMARC del dominio de `SMTP_REMITENTE` y que el `From` con el nombre de la empresa no caiga en spam | U11 | Los recordatorios llegan a spam |

## Estimación y entrega

- Autoría estimada (adiciones + borrados, sin generados): producción ~430 líneas (transporte ~70,
  `EnvioPorEmail` ~170, ruteador ~60, nombre ~35, `application/` ~25, plantilla editable ~45, raíz y
  worker ~25), tests ~650, docs ~60 → **~1.150 líneas**.
- Supera el presupuesto de ~400 por PR: **dos PRs encadenados** (pregunta 4):
  1. **Tramo i — el transporte clasifica y calla** (~300): `platform/email.py` (D-U11-3 y logs sin
     datos personales), casos 5, 19 (parte transporte) y 20. Independiente de U7: puede ir a
     `develop` antes que el tramo ii de U7.
  2. **Tramo ii — el recordatorio por email** (~850): todo lo demás, apilado sobre el tramo i y sobre
     U7 tramo ii mergeado.

## Preguntas del Gate 1

Se contestan en bloque («1 sí, 2 sí, …»).

| # | Pregunta | Recomendación |
|---|---|---|
| 1 | ¿El cuerpo del correo es **editable en PAN-CFG-NOT**, como el de WhatsApp (código nuevo `recordatorio_de_cobro_por_email`, canal `EMAIL`, sin aprobación de Meta), o es un texto fijo versionado en el código, como la invitación y el correo al contador? | **Sí, editable.** HU-E11-02 dice «personalizar los mensajes que el sistema envía a clientes», y un administrador que editó el recordatorio de WhatsApp esperaría poder editar el de email. El frontend ya soporta plantillas de otro canal (no hay código de pantalla) y en el backend son ~45 líneas más sus tests. El asunto queda fijo con el nombre de la empresa. Dejarlo fijo «por ahora» sería una solución temporal que no depende de terceros |
| 2 | ¿Alcanza con que `ENVIADO` signifique «el servidor SMTP aceptó el correo», sin procesar rebotes, que llegan después y con el formato de cada proveedor? | **Sí.** Procesar rebotes depende del proveedor, que todavía no está elegido (`TODO.md` §2.2): es lo único que se difiere y depende de un tercero. Queda en §22.63 con el `Message-ID` determinístico ya puesto para correlacionarlos el día que se haga |
| 3 | `platform/email.py` loguea hoy la **dirección y el asunto** de cada correo (`:109-113`, `:132-136`). Con esta unidad serían las direcciones de los clientes finales. ¿Se saca la dirección y el asunto de esos logs en esta unidad, aunque el transporte lo usen también `identity`, `integrations` y `reporting`? | **Sí, en el tramo i.** Es el mismo archivo que hay que tocar para clasificar las fallas, y esta unidad es la que multiplica el dato personal en el log. Cada contexto sigue logueando sus ids. El `destinatario` que `reporting/infrastructure/avisos.py:85` loguea por su cuenta **no** se toca (otro contexto): se anota como hallazgo en `TODO.md` §22 |
| 4 | ¿Se entrega en **dos PRs encadenados** (i: transporte; ii: recordatorio por email) en lugar de uno de ~1.150 líneas? | **Sí.** El tramo i no depende de U7 y se puede revisar y mergear solo; el ii queda en ~850, en línea con los tramos de U7 |
| 5 | ¿La unidad agrega a `docs/staging-deployment.md` la línea que dice que el worker necesita `EMAIL_ADAPTADOR` y `SMTP_*`, y deja como acción del dueño `.env.example` y Render? | **Sí.** El agente no puede editar `.env.example` ni el dashboard de Render; la doc de despliegue es lo que evita que el día que se cargue el proveedor en la API alguien se olvide del worker |
| 6 | La unidad depende en los hechos de **U7 tramos i y ii** (puerto en dos tiempos, `transitoria`), no sólo de U5. ¿Se actualiza la columna «Depende de» de U11 en `units.md` a `canal-real-de-whatsapp, entregas-de-whatsapp (tramo ii)` al reclamarla? | **Sí.** El mapa tiene que decir la verdad: el tramo ii de U11 no se puede mergear antes que el de U7. El tramo i sí, y eso también queda escrito en esta fila |

## Traspaso (2026-10-07)

HS-T3 pertenece al módulo de cobros (`docs/aidlc/etapa-6/reparto.md` §1); el reparto asigna al canal
conversacional solo el canal real de WhatsApp para recordatorios y avisos. Esta unidad se libera para
quien tenga el módulo de cobros, con el **borrador del plan** en esta rama: el relevamiento, el diseño
y las 6 preguntas con su recomendación. **El Gate 1 no se presentó**: lo presenta y lo aprueba quien
la tome, que puede cambiar cualquier decisión.

Antes de empezar: el tramo ii depende de `entregas-de-whatsapp` tramos i y ii (puerto en dos tiempos y
`FallaDelCanal.transitoria`), todavía sin mergear; el tramo i no depende de nada y puede ir antes.
Hallazgos que valen aunque la unidad no se haga ya: `platform/email.py` loguea la dirección y el
asunto de cada correo (pregunta 3) y `reporting/infrastructure/avisos.py:85` loguea el destinatario.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- (vacío hasta el Gate 1)
