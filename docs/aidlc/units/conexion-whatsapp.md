# Unidad: conexion-whatsapp

**HUs**: HU-E2-03   **Contexto dueño**: `integrations`   **Rama**: `feature/integrations-conexion-whatsapp`

Segunda unidad del épico 2. Depende de `mecanismo-de-integraciones`, **mergeada** en `develop`
(PR #8), así que no asume nada: el agregado, el cifrado, el registro de adaptadores y PAN-CFG-INT
ya existen y se leen del código, no de un supuesto.

---

## Qué hace

El Administrador conecta el número de WhatsApp Business de su empresa: pega el token y los
identificadores de Meta, el sistema los valida contra la Graph API y deja la integración en
**Pendiente** mientras Meta revisa el número (24–72 h). Una tarea de Beat consulta el resultado
periódicamente y, cuando llega, deja la integración **Conectada** con el display name verificado y
la calidad de la línea, o **No conectada** con el motivo. En los dos desenlaces asíncronos el
Administrador recibe un email, porque nadie mira una pantalla durante tres días.

Es la primera integración **real** del sistema: hasta acá todos los proveedores eran simulados.

---

## Diseño

### Dominio

| Qué | Cambio |
|---|---|
| `EstadoDeConexion` | **Se agrega `PENDIENTE`.** El cuarto y último estado. `valores.py` de la unidad 1 ya lo dejó anunciado — «`PENDIENTE` está deliberadamente ausente… `conexion-whatsapp` lo agrega» — así que esto es alcance planificado, no algo que se rompe |
| `ConfiguracionDeIntegracion.registrar(...)` | Classmethod nuevo, general: crea la fila **con el estado que el proveedor devolvió**. `conectar(...)` se reimplementa encima pasando `CONECTADO` y no cambia de firma, así que ningún test de la unidad 1 se toca |
| `.reconectar(...)` | Acepta el estado resultante, por lo mismo: reconectar WhatsApp vuelve a Pendiente, no a Conectado |
| `.registrar_intento_fallido(detalle, ahora)` | **La regla que evita el falso negativo.** Una verificación que no obtuvo veredicto —timeout, host caído— hoy deja la fila en `NO_CONECTADO`. Aplicado a una fila `PENDIENTE` eso es un error de datos: Meta no rechazó nada, se cayó la red. Este método sella `verificado_en` y el detalle, y **mantiene `PENDIENTE`**; para cualquier otro estado se comporta como hasta ahora |
| `.actualizar_parametros(nuevos)` | Fusiona lo que el proveedor informó (`display_name`, calidad) sobre `parametros`. RN-03 |
| `.esta_pendiente` | Propiedad, simétrica a `esta_conectada` |

**Ningún nombre de Meta entra al dominio.** `verified_name`, `quality_rating` y `name_status` son
vocabulario del proveedor y se quedan en la ACL de infraestructura (ADR-008). El agregado ve un
`dict` opaco.

### Aplicación

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `ConectarIntegracion` *(existente, se generaliza)* | igual + el resultado del conector | `VistaDeIntegracion` | El estado inicial lo decide el proveedor, no el caso de uso |
| `SondearIntegracionesPendientes` **(nuevo)** | `empresa_id` | `list[CambioDeEstado]` | Consulta cada fila `PENDIENTE` de una empresa, aplica el veredicto, audita sólo las transiciones reales y **devuelve** las que hubo. No notifica: eso lo hace quien lo llama |

Ampliación de los puertos, que es lo que absorbe la varianza entre proveedores:

```python
@dataclass(frozen=True, slots=True)
class ResultadoDeConexion:
    credencial: bytes
    estado: EstadoDeConexion = EstadoDeConexion.CONECTADO
    detalle: str | None = None
    parametros: dict[str, Any] = field(default_factory=dict)
```

`PortConectorDeIntegracion.conectar` pasa a devolver esto en lugar de `bytes`, y
`ResultadoDeVerificacion` gana el mismo campo `parametros`. **Es el cambio de contrato que esta
unidad hace sobre el OHS**, y es aditivo: ARCA y MercadoPago devolverán `CONECTADO` sin decir nada
más. Sin él, `ConectarIntegracion` tendría que preguntar «¿es WhatsApp?», que es exactamente el
`if` por proveedor que el registro de adaptadores existe para no tener.

### Puertos y adaptadores

| Puerto | Adaptador | Dónde |
|---|---|---|
| `PortConectorDeIntegracion` | `ConectorWhatsApp` — valida el token contra Graph API | `integrations/infrastructure/whatsapp/conector.py` |
| `PortVerificadorDeConexion` | `VerificadorWhatsApp` — relee el estado del número | `integrations/infrastructure/whatsapp/verificador.py` |
| *(los dos)* | `WhatsAppSimulado` — recorre el ciclo de vida sin red | `…/whatsapp/simulado.py` |
| `PortAvisoDeIntegracion` **(nuevo)** | `AvisoPorEmail` — plantilla + transporte de `platform/` | `integrations/infrastructure/email_integracion.py` |

`registro.py` deja de responder `WHATSAPP` con el par simulado genérico y pasa a resolverlo por
configuración: real o simulado de WhatsApp. **Es el único archivo de la unidad 1 que cambia de
comportamiento**, que era el punto de haberlo cortado ahí.

### Otros contextos

**Ninguno. Y eso costó una inversión deliberada — decisión D-c.**

HU-E2-03 pide avisarle al Administrador, y quiénes son los administradores es dato de `identity`.
Pero ADR-0003 declara `integrations` como Open Host Service y lista a `identity` entre sus
consumidores: una arista `integrations → identity` sería un ciclo y rompería el OHS —
`application/ports.py` lo dice con todas las letras («an Open Host Service that depended on its
clients would not be one»).

Se invierte: **el caso de uso recibe los destinatarios ya resueltos**. Quien los resuelve es la
tarea de Celery en `workers/`, que es composition root y sí puede tocar los dos contextos — el
mismo lugar y el mismo permiso con el que `tasks_identity.py` compone `identity` hoy. Los lee con
`ListarUsuarios`, que ya existe en `identity/application/usuarios.py`, filtrando por rol
`ADMINISTRADOR` y activo.

Lo que queda dentro de `integrations` es **cuándo** se avisa; lo que queda afuera es **a quién**.

### Frontend

`features/integrations` — la feature existe y se extiende, no se crea.

| Archivo | Cambio |
|---|---|
| `components/FormularioDeWhatsApp.tsx` | **Nuevo.** Los tres campos de Meta: token de System User, `phone_number_id`, `waba_id`. Reemplaza el `CREDENCIAL_SIMULADA` para este sistema |
| `components/GrillaDeIntegraciones.tsx` | Abre el formulario cuando el sistema es `WHATSAPP`; los otros tres siguen por el camino de la unidad 1 |
| `components/TarjetaDeIntegracion.tsx` | Estado `PENDIENTE` → badge `pendiente`, que **ya existe** en `shared/ui/Badge.tsx`; sin acción mientras Meta revisa |
| `api/cliente.ts` | `EstadoDeConexion` suma `"PENDIENTE"`; `conectarIntegracion` acepta `parametros` |

El `index.ts` **no cambia**: el formulario se compone dentro de la grilla, así que nada nuevo cruza
el borde de la feature (R5).

---

## Infraestructura

### Migraciones — `0005_sondeo_de_integraciones.py`

`estado` es `varchar(20)`, así que **`PENDIENTE` no necesita migración**. Lo que sí la necesita es
el barrido entre empresas:

```sql
CREATE OR REPLACE FUNCTION empresas_con_integracion_pendiente()
RETURNS TABLE (empresa_id uuid)
LANGUAGE sql SECURITY DEFINER SET search_path = public STABLE
AS $$ SELECT DISTINCT c.empresa_id FROM configuracion_de_integracion c
      WHERE c.estado = 'PENDIENTE' $$;
```

**Por qué una función y no un `SELECT`.** Beat corre sin empresa: `app.current_empresa` no está
seteado y la política RLS de la tabla, correctamente, no le muestra **nada**. Es el mismo problema
que el login —descubrir a qué empresa pertenece algo antes de saber la empresa— y se resuelve con
el mismo mecanismo que las migraciones 0002 y 0003 ya usan cuatro veces: `SECURITY DEFINER`,
`search_path` fijo, `GRANT EXECUTE` sólo a `cheatsheet_app`, `REVOKE` de `PUBLIC`.

**Devuelve el mínimo: sólo `empresa_id`.** Ni credencial, ni parámetros, ni estado. Una función que
esquiva RLS es una perforación en la única barrera multi-empresa del sistema; se la mantiene tan
angosta que lo que se filtre por ella no sirva para nada. La tarea por empresa que sale de acá abre
después una sesión con RLS normal.

Reversible: `downgrade` hace `DROP FUNCTION`. Sin backfill — no hay filas `PENDIENTE` todavía.

### Trabajo asíncrono

| | Despachador | Tarea por empresa |
|---|---|---|
| Nombre | `integrations.sondear_pendientes` | `integrations.sondear_empresa` |
| Cola | `integrations_sync` | `integrations_sync` |
| Disparo | Beat, **cada 30 min** | El despachador, una por empresa |
| Idempotencia | ninguna: es un `SELECT` y un fan-out | `ClaveDeIdempotencia` sobre `(empresa, tipo, ventana de 30 min)` |
| Reintentos | `PoliticaDeReintentos()` por defecto (5, backoff con jitter, ADR-009) | igual |

**30 minutos, no 5 y no 6 horas.** Meta tarda entre 24 y 72 horas (RN-02), así que sondear cada 5
minutos son ~860 llamadas por número para adelantar un resultado en minutos sobre una espera de
días; cada 6 horas se pierde media jornada de un desenlace que el Administrador está esperando. 30
min acota la demora a ~1 % de la espera y son 48 llamadas por número por día.

**El sondeo se rinde a los 7 días — decisión D-e.** Una fila `PENDIENTE` sin tope se sondea para
siempre: si Meta nunca contesta, esa empresa queda con una tarea eterna y el Administrador con una
pantalla que nunca cambia. Pasados 7 días —más del doble del techo de RN-02— la integración pasa a
`NO_CONECTADO` con «Meta no respondió la verificación en 7 días» y se notifica. Reconectar la vuelve
a poner en Pendiente y reinicia el reloj.

Beat hoy tiene `PROGRAMACION = {}`. **Esta es su primera entrada real**, y con eso empieza a valer
de verdad la advertencia que ya está escrita en `workers/beat.py`: Beat es singleton y replicarlo
duplica cada entrada.

### Configuración — `backend/.env.example`

```bash
WHATSAPP_ADAPTADOR=              # meta | simulado — 'simulado' es rechazado en produccion
WHATSAPP_GRAPH_URL=              # default https://graph.facebook.com
WHATSAPP_GRAPH_VERSION=          # default v21.0 — fijada por configuracion, nunca hardcodeada
WHATSAPP_TIMEOUT_SEGUNDOS=       # default 10
WHATSAPP_SONDEO_MINUTOS=         # default 30
WHATSAPP_SONDEO_MAXIMO_DIAS=     # default 7
```

`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN` ya
están declaradas en el template y **se dejan como están**: son de plataforma y las lee el épico 8
(webhooks entrantes del agente conversacional). Las de esta unidad son distintas por naturaleza —
el token de WhatsApp es **por empresa** y vive cifrado en `configuracion_de_integracion`, nunca en
un `.env`. Vale la pena decirlo porque las dos cosas se llaman «el token de WhatsApp» y confundirlas
significaría que todas las empresas mandan mensajes desde el mismo número.

---

## Contrato del proveedor — Meta WhatsApp Cloud API

*(Sección exigida por la escalada «nueva integración externa» del workflow.)*

### Endpoints

| Qué | Llamada |
|---|---|
| Validar credenciales y leer el estado del número | `GET {graph_url}/{version}/{phone_number_id}?fields=verified_name,code_verification_status,quality_rating,name_status,display_phone_number` |
| Confirmar que el número pertenece a la WABA declarada | `GET {graph_url}/{version}/{waba_id}/phone_numbers` |

Autenticación: `Authorization: Bearer <token de System User>` — el mismo token que se cifra y se
guarda. Las dos llamadas son de lectura: **esta unidad no escribe nada en Meta.**

**No hay ambiente sandbox.** Meta no expone uno: la separación es por número de prueba dentro de la
misma Graph API. Por eso `Ambiente` sigue derivándose de `APP_ENV` como decidió la unidad 1, y en
homologación se espera un número de prueba. Se dice acá porque es la primera integración del
sistema donde «homologación» no corresponde a un host distinto, y quien lea `ambiente` en la fila
podría suponer lo contrario.

### Traducción de estados — la ACL

`name_status` es lo que decide, y `whatsapp/mapeo.py` es una función pura sobre eso:

| Meta | Nuestro estado | Detalle mostrado |
|---|---|---|
| `APPROVED` | `CONECTADO` | — · se guardan `verified_name` y `quality_rating` (RN-03) |
| `PENDING_REVIEW` · `AVAILABLE_WITHOUT_REVIEW` | `PENDIENTE` | «Meta está revisando el nombre para mostrar» |
| `DECLINED` | `NO_CONECTADO` | «Meta rechazó el nombre para mostrar» |
| `EXPIRED` · `NONE` | `NO_CONECTADO` | «La verificación del número venció» |
| cualquier otro valor | `ATENCION` | «Meta informó un estado desconocido: …» |

La última fila importa: Meta agrega valores a este enum sin avisar, y un `KeyError` en una tarea de
Beat es una integración que se queda muda. `ATENCION` es visible y no destruye nada.

### Modos de falla

| Falla | Respuesta |
|---|---|
| HTTP 401 / 403 | `ConexionRechazada` — token inválido o sin permisos. Nada se guarda |
| HTTP 400 con `code: 100` | `ConexionRechazada` — `phone_number_id` inexistente |
| HTTP 429 | `ProveedorNoDisponible`. Reintento con backoff; en el sondeo, la fila queda `PENDIENTE` |
| HTTP 5xx / timeout / DNS | `ProveedorNoDisponible`. Idem |
| El número no pertenece a la WABA | `ConexionRechazada` — «El número no pertenece a la cuenta declarada» |

Timeout explícito de 10 s, reintentos con backoff y jitter en el cliente (`CLAUDE.md` §5).

### Cómo se prueba sin red

Tests de contrato sobre **fixtures grabadas** de las respuestas de Graph API —una por fila de la
tabla de estados y una por modo de falla— servidas por un transporte `httpx.MockTransport`. Ningún
test abre un socket (regla del workflow, paso 3).

---

## Riesgos que obligan a tests

- [ ] Toca dinero → **no aplica**
- [ ] Toca comprobantes fiscales / CAE → **no aplica**
- [ ] Consume un webhook → **no aplica.** Meta ofrece webhooks para esto; se sondea a propósito
      (D-d abajo). Los webhooks entrantes son del épico 8
- [x] **Agrega datos con `empresa_id`** → test de aislamiento: la empresa A no ve ni sondea la fila
      de la B, y la función `SECURITY DEFINER` no devuelve nada más que `empresa_id`
- [ ] Usa salida de un LLM → **no aplica**
- [x] **Datos personales** → el número de teléfono y el display name son datos de la empresa. No van
      a ningún LLM, no se loguean, y el token **nunca** sale del contexto ni aparece en un log

---

## Archivos a tocar

**Backend — dominio y aplicación**
- [x] `contexts/integrations/domain/valores.py` — `PENDIENTE` y `CLAVE_ETIQUETA`
- [x] `contexts/integrations/domain/configuracion.py` — `registrar`, `registrar_intento_fallido`,
      `actualizar_parametros`, `espera_vencida`, `esta_pendiente`, `pendiente_desde`
- [x] `contexts/integrations/application/ports.py` — `ResultadoDeConexion`, `parametros` en
      `ResultadoDeVerificacion`, `PortAvisoDeIntegracion`, `listar_pendientes`
- [x] `contexts/integrations/application/integraciones.py` — `SinVeredicto`,
      `verificar_con_timeout`, `aplicar_resultado`, `etiqueta` en la vista
- [x] `contexts/integrations/application/sondeo.py` — `SondearIntegracionesPendientes`
- [ ] ~~`contexts/integrations/application/errors.py` — `VerificacionVencida`~~ — **no hizo falta**:
      rendirse a los 7 días es una transición de estado, no una excepción. Nadie la atrapa

**Backend — infraestructura**
- [x] `contexts/integrations/infrastructure/whatsapp/{__init__,cliente,conector,verificador,mapeo,simulado}.py`
- [x] `contexts/integrations/infrastructure/email_integracion.py` + `plantillas/integracion_{conectada,desconectada}.{html,txt}`
- [x] `contexts/integrations/infrastructure/registro.py` — `desde_settings`, WhatsApp por configuración
- [x] `contexts/integrations/infrastructure/ensamblado.py` — `crear_aviso`
- [x] `contexts/integrations/infrastructure/repositories.py` — `listar_pendientes` y el barrido
- [x] `contexts/integrations/infrastructure/{models,simulados}.py`

**Backend — plataforma, workers, migración**
- [x] `platform/email.py` — **nuevo**: transporte SMTP + consola (D-b)
- [x] `contexts/identity/infrastructure/{email_invitacion,ensamblado}.py` — usan el transporte;
      **sin cambio de comportamiento**, y los 12 tests de identity pasan sin tocar sus asserts
- [x] `platform/settings.py` — `AdaptadorDeWhatsApp` y las seis variables
- [x] `workers/tasks_integrations.py` — despachador + tarea por empresa
- [x] `workers/{beat,main}.py` — la primera entrada de `PROGRAMACION`
- [x] `migrations/versions/0005_sondeo_de_integraciones.py`
- [x] `backend/.env.example`

**Backend — API**
- [x] `api/routers/integraciones.py` — `etiqueta` en la salida. **No estaba en el plan**: ver desvíos

**Frontend**
- [x] `features/integrations/components/FormularioDeWhatsApp.tsx` — **nuevo**
- [x] `features/integrations/components/{GrillaDeIntegraciones,TarjetaDeIntegracion}.tsx`
- [x] `features/integrations/api/cliente.ts`
- [x] `shared/componentes.css` — dos reglas del formulario, marcadas como sin contraparte en el mockup

**Tests**
- [x] `contexts/integrations/domain/test_configuracion.py` — 12 casos nuevos
- [x] `contexts/integrations/application/test_sondeo.py` — **nuevo**, 8 casos
- [x] `contexts/integrations/infrastructure/test_whatsapp_{mapeo,contrato,simulado}.py` — **nuevos**
- [x] `contexts/integrations/infrastructure/test_email_integracion.py` — **nuevo**
- [x] `integracion/test_whatsapp_ciclo_de_vida.py` — **nuevo**, 16 casos contra PostgreSQL y Redis
- [x] `workers/test_tasks_integrations.py` — **nuevo**
- [x] `tests/{conftest,contexts/integrations/conftest}.py` y los dobles existentes
- [x] `frontend/…/__tests__/GrillaDeIntegraciones.test.tsx` — 6 casos nuevos

**Docs**
- [x] `docs/aidlc/units.md` — fila propia
- [x] `docs/aidlc/TODO.md` — la deuda de despliegue del épico 2
- [ ] ~~`docs/architecture.md` §7~~ — **no hacía falta**: la fila de `PortNotificacionEmail` sigue
      diciendo la verdad. D-b movió el transporte, no el puerto, y el puerto sigue siendo de cada
      contexto. Editarla habría documentado algo que no pasó

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | `PENDIENTE` es un miembro válido y no rompe el mapeo de la pantalla | unit | ✅ |
| 2 | `registrar` crea la fila con el estado que devolvió el proveedor | unit | ✅ |
| 3 | `conectar` sigue creando en `CONECTADO` — la unidad 1 no se rompe | unit | ✅ |
| 4 | `registrar_intento_fallido` **mantiene `PENDIENTE`** y sella `verificado_en` | unit | ✅ |
| 5 | `registrar_intento_fallido` sobre `CONECTADO` sí baja a `NO_CONECTADO` | unit | ✅ |
| 6 | `actualizar_parametros` fusiona sin borrar lo que ya había | unit | ✅ |
| 7 | `name_status: APPROVED` → `CONECTADO` con `verified_name` y calidad | contrato | ✅ |
| 8 | `PENDING_REVIEW` → `PENDIENTE` | contrato | ✅ |
| 9 | `DECLINED` → `NO_CONECTADO` con el motivo | contrato | ✅ |
| 10 | `EXPIRED` → `NO_CONECTADO` | contrato | ✅ |
| 11 | Un `name_status` desconocido → `ATENCION`, sin excepción | contrato | ✅ |
| 12 | 401 → `ConexionRechazada`; no se reintenta ni se escribe nada | contrato | ✅ |
| 13 | 429 y 5xx → `ProveedorNoDisponible` tras agotar el backoff | contrato | ✅ |
| 14 | El número que no pertenece a la WABA se rechaza | contrato | ✅ |
| 15 | Timeout de 10 s: el valor configurado llega al cliente HTTP | contrato | ✅ |
| 16 | Conectar WhatsApp deja la fila `PENDIENTE` y audita la transición | integración | ✅ |
| 17 | El sondeo que aprueba: `CONECTADO`, audita **una** vez y avisa **una** vez | integración | ✅ |
| 18 | El sondeo que rechaza: `NO_CONECTADO` con motivo, audita y avisa | integración | ✅ |
| 19 | El sondeo que sigue pendiente: **no** audita y **no** avisa | integración | ✅ |
| 20 | A los 7 días sin respuesta: `NO_CONECTADO` y aviso | unit + integración | ✅ |
| 21 | Aislamiento: la empresa A no ve ni sondea la fila `PENDIENTE` de la B | integración | ✅ |
| 22 | `empresas_con_integracion_pendiente()` devuelve sólo `empresa_id` | integración | ✅ |
| 23 | Redelivery de la tarea: la idempotencia la vuelve no-op | unit + integración | ✅ |
| 24 | El token **no** aparece en ningún log ni en ninguna respuesta de la API | integración | ✅ |
| 25 | El adaptador simulado **lanza** al construirse en `production` | unit | ✅ |
| 26 | La invitación de `identity` sigue enviándose igual tras extraer el transporte | unit | ✅ |
| 27 | La tarjeta en `PENDIENTE` muestra el badge y **no** ofrece acción | frontend | ✅ |
| 28 | El formulario exige los tres campos y no los deja en el DOM tras enviar | frontend | ✅ |

**Casos agregados durante la implementación**, porque el código los pidió:

| Caso | Por qué |
|---|---|
| Una línea calificada `RED` por Meta es `ATENCION` aunque esté aprobada | Meta está por restringirla: eso *es* «degradada». `YELLOW` sigue conectada |
| Salir de `PENDIENTE` apaga el reloj, y volver a entrar lo reinicia | Sin esto, una espera vieja haría vencer una nueva a los pocos minutos |
| Reconectar deja el número en `PENDIENTE`, no en `CONECTADO` | Reconectar lo manda de nuevo a revisión: decir «Conectado» sería mentir 72 h |
| Un reintento que sale bien devuelve el cuerpo | El backoff tiene que servir de algo, no sólo agotarse |
| Una respuesta que no es JSON no explota como error de parseo | Un proxy corporativo devolviendo HTML es un modo de falla real |
| Verificar sin `phone_number_id` avisa en vez de explotar | Una fila así no responde ninguna pregunta; `ATENCION` lo dice y no rompe la tarea |
| Un `WHATSAPP_SONDEO_MINUTOS=0` no divide por cero | Un error de configuración no puede tumbar el worker |
| Un broker caído no rompe el barrido entero | Una empresa que no se pudo encolar se reintenta en 30 minutos |
| Sin destinatarios el aviso no se manda y no falla | Una empresa a medio onboardear puede no tener dirección confirmada todavía |
| El servidor de correo caído no deshace el cambio de estado | El cambio ya está auditado; reintentar el sondeo reescribiría la auditoría |
| El campo del token es `password` y sin autocompletado | Una credencial guardada por el navegador es una credencial sin auditoría |

**Total: 391 tests en el backend** (295 al empezar la unidad) **y 201 en el frontend** (195).

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-18 | aprobado sin cambios |
| 2 · Verificación | 2026-08-19 | **en verde** — salida real abajo |
| 3 · PR | | |

### Salida real del Gate 2

```
ruff format --check .   200 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 195 source files
pytest                  391 passed — cobertura 89.30% (umbral 80)
guard_architecture      227 file(s) checked — architecture boundaries intact
gitleaks 8.21.2         no leaks found
frontend format:check   All matched files use Prettier code style!
frontend lint           No ESLint warnings or errors
frontend typecheck      (sin salida: tsc --noEmit limpio)
frontend test:coverage  201 passed — 89.86% líneas
```

PostgreSQL y Redis estaban levantados, así que **no se saltó ningún test**: los 16 casos de
`test_whatsapp_ciclo_de_vida.py` corrieron contra la base real, incluidos los que dependen de RLS.

Cobertura de lo nuevo: `whatsapp/mapeo.py` 100%, `application/sondeo.py` 100%,
`whatsapp/{conector,simulado}.py` 100%, `whatsapp/cliente.py` 91%,
`workers/tasks_integrations.py` 90%, `platform/email.py` 80%.

### Desvíos del plan, dichos de frente

Cuatro. Ninguno cambia el alcance de la historia; los cuatro salieron de escribir el código.

1. **Se agregó la columna `pendiente_desde` — gap H10.** El plan decía que la migración sólo
   necesitaba la función `SECURITY DEFINER`, porque `estado` ya es `varchar`. Al escribir la regla
   de los 7 días quedó claro que **no había con qué medir la espera**: `verificado_en` se re-sella
   en cada sondeo, así que mide la última pregunta y no el tiempo esperado. Guardarlo en
   `parametros` habría sido meter estado del agregado en un campo que es material del proveedor.
   La migración agrega además un índice parcial sobre las filas pendientes.
2. **La vista y la API ganaron `etiqueta`.** RN-03 pide registrar el display name verificado, y el
   criterio de aceptación dice que la integración queda Conectada **con ese nombre** — o sea que
   tiene que verse. Se resolvió con una clave genérica que declara el dominio (`CLAVE_ETIQUETA`) y
   que la ACL de cada proveedor completa, en vez de exponer `parametros` entero: los IDs de Meta no
   le dicen nada a una persona y no tienen por qué cruzar la API.
3. **`ResultadoDeVerificacion` no alcanzaba para distinguir un rechazo de una caída de red**, así
   que apareció `SinVeredicto`. Es la pieza que hace posible la regla del caso 4; sin ella el
   agregado no puede saber si Meta dijo que no o si no llegamos a preguntar.
4. **`VerificacionVencida` no se escribió** y `docs/architecture.md` §7 no se tocó, por las razones
   anotadas en la lista de archivos.

## Decisiones tomadas durante la unidad

- **D-a — El puerto del conector devuelve un resultado, no `bytes`.** El estado inicial lo decide el
  proveedor. La alternativa era un `if sistema is WHATSAPP` en `ConectarIntegracion`, que es
  exactamente el condicional por proveedor que el registro de adaptadores existe para no tener.
- **D-b — El transporte SMTP se extrae a `platform/email.py`** (respuesta del usuario, 2026-08-18).
  El puerto sigue siendo de cada contexto, como pide hexagonal; lo que se comparte es el socket y el
  timeout. Es literalmente lo que el docstring de `PortEnvioDeEmail` en `identity` dejó anotado:
  «si vale la pena extraerlo lo decide el segundo consumidor». Esta unidad es ese segundo consumidor.
  **Descartado**: un adaptador SMTP propio en `integrations`, que dejaría dos implementaciones del
  mismo transporte para que `payments` herede el problema por triplicado en el épico 6.
- **D-c — `integrations` no llama a `identity`.** Los destinatarios entran como argumento; los
  resuelve la tarea en `workers/`, que es composition root. Evita el ciclo que rompería el OHS de
  ADR-0003.
- **D-d — Sondeo, no webhook.** Meta ofrece un webhook para el cambio de estado del número, y sería
  más inmediato. Se sonda igual por tres razones: recibir un webhook exige endpoint público,
  validación de firma con `WHATSAPP_APP_SECRET` y una app de Meta configurada —nada de lo cual
  existe todavía—; el webhook es **de plataforma**, así que su endpoint es del épico 8 y montarlo
  acá sería construir infraestructura de otro épico; y una espera de 24–72 h no gana nada medible
  con notificación instantánea. Cuando el épico 8 monte el endpoint, el sondeo pasa a ser la red de
  seguridad de un webhook perdido, que es donde conviene que esté.
- **D-e — El sondeo se rinde a los 7 días** y la integración pasa a `NO_CONECTADO` con el motivo.
  Más del doble del techo de RN-02. Sin tope, una fila que Meta nunca contesta se sondea para
  siempre.
- **D-f — Carga manual del token, con el hueco de Embedded Signup declarado** (respuesta del
  usuario, 2026-08-18). El flujo que Meta recomienda —popup del SDK de Facebook— exige una app de
  Meta aprobada, que no existe. El formulario de tres campos es lo único ejecutable y demostrable
  hoy; el punto exacto donde entra Embedded Signup queda escrito y en el `TODO.md` del épico.

## Deuda que esta unidad declara

- Conseguir el token de System User, el `phone_number_id` y el `waba_id` reales es **tarea de
  despliegue**, no de código → `TODO.md` del épico 2.
- Embedded Signup reemplaza el formulario manual cuando exista la app de Meta aprobada (D-f).
- El webhook de cambio de estado del número es del épico 8 (D-d).

