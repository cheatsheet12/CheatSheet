# TODO — lo que falta para cerrar los épicos abiertos

> Estado al **2026-08-24**. Arranca siendo el TODO del épico 1; el épico 2 agrega su propia
> sección al final, con la misma regla.
>
> **Los épicos 1 y 2 están cerrados en código y mergeados en `develop`.** Lo que queda acá de los
> dos es lo mismo en ambos casos: **credenciales reales** (§2 y §5) y **deuda declarada** (§3 y §6).
> Ninguna de las dos cosas se resuelve escribiendo código.
>
> Todo lo que está acá **bloquea el cierre de un épico o queda declarado como deuda con dueño**.
> Lo que ya está hecho no se lista: para eso está el registro de cada unidad en [`units/`](units/).

---

# Épico 1 — Cimientos, identidad y bitácora

> Estado al **2026-08-24**. Las tres unidades están implementadas, verificadas en verde y
> mergeadas. Lo que queda es **configuración que no puedo tocar yo** e **integraciones que hoy
> corren simuladas**.

## 1. ~~Bloqueantes — sin esto el épico no cierra~~ · **los dos resueltos**

### 1.1 Variables de entorno · ~~te toca a vos~~ **resuelto el 2026-08-18**

Decía que los dos `.env.example` estaban denegados por permisos y que había que pegarlos a mano. Ya
no: la unidad `mecanismo-de-integraciones` encontró la causa —una regla `Read(./.env.*)` demasiado
ancha, que atrapaba las plantillas versionadas junto con los archivos reales— y la corrigió por
enumeración. Los dos templates quedaron **reconciliados con lo que el código realmente lee**, y hay
una verificación que compara ambas listas.

Se deja escrito en lugar de borrarlo porque el épico 1 **se entregó con este punto de la Definition
of Done incumplido**, y eso es parte de su historia.

### 1.2 ~~Los dos gates que faltan~~ **cerrados el 2026-08-18**

Los dos se cerraron el mismo día: diste por buena la verificación de `usuarios-y-preferencias` —la
que traía el QA manual con 7 defectos encontrados y corregidos— y el épico entero entró a `develop`
en el PR [#5](https://github.com/cheatsheet12/CheatSheet/pull/5), con las ocho historias y en un solo
PR, por la decisión del 2026-08-13.

Queda escrito en lugar de borrarse por el mismo motivo que §1.1: el épico **se entregó con el punto
de los `.env.example` de la Definition of Done incumplido**, y la secuencia real es parte de su
historia.

Estado de la verificación con la que se cerró:

```
ruff format --check .   sin cambios
ruff check .            All checks passed!
mypy .                  Success: no issues found in 152 source files
guard_architecture      192 file(s) checked — architecture boundaries intact
pytest --cov            239 passed · cobertura 89.1%  (umbral 80%)
frontend lint/typecheck limpios
frontend vitest         181 passed · cobertura 91.3%
frontend build          compila, 21 rutas registradas
```

> Esas cifras son las del épico 1 y **no se actualizan**: son el registro de su cierre. La corrida
> vigente sobre `develop`, con los épicos 1 y 2 adentro, está al pie de este documento (§8).

---|---|
| **2 · Verificación** de `usuarios-y-preferencias` | Corrida y en verde, más un **QA manual en el navegador** que encontró y dejó corregidos 7 defectos (detalle en el plan de la unidad). Falta que **vos la des por buena**. |
| **3 · Pull Request** | El push de la rama y la apertura del PR. Por regla del repositorio **no los hago sin que los pidas**. Son 4 commits sobre `feature/identity-cimientos-identidad-y-bitacora`, que entra a `develop` con las ocho historias del épico. |

Estado de la verificación local, al día de hoy:

```
ruff format --check .   sin cambios
ruff check .            All checks passed!
mypy .                  Success: no issues found in 152 source files
guard_architecture      192 file(s) checked — architecture boundaries intact
pytest --cov            239 passed · cobertura 89.1%  (umbral 80%)
frontend lint/typecheck limpios
frontend vitest         181 passed · cobertura 91.3%
frontend build          compila, 21 rutas registradas
```

---

## 2. Integraciones que hoy corren **simuladas**

Las dos funcionan de punta a punta y están testeadas. Ninguna toca la red en los tests. Lo que
falta en ambas es **credenciales reales**, y eso es una tarea de despliegue, no de código.

### 2.1 Google OAuth2 — `ProveedorOAuthSimulado`

- **Hoy:** sin `GOOGLE_OAUTH_CLIENT_ID` y fuera de `production`, `proveedor_google()` devuelve el
  simulado. El código de autorización **es** el email, con el formato `simulado:<email>`, y la URL
  de autorización apunta al propio callback de la app. Alcanza para recorrer el flujo entero en
  local y para que el test de integración lo ejerza.
- **Falta:** crear el cliente OAuth en Google Cloud Console, cargar las tres variables y probar el
  flujo real una vez. El adaptador real (`ProveedorOAuthGoogle`) ya está escrito, con timeout,
  3 reintentos con backoff, scope `openid email profile` y verificación de `email_verified`.
- **Protección:** el simulado **lanza `RuntimeError` si se lo construye en `production`**. No es un
  warning. En producción sin credenciales el endpoint devuelve error y el resto de la API arranca
  igual.

### 2.2 Correo transaccional — `EnviadorDeConsola`

- **Hoy:** `EMAIL_ADAPTADOR=consola` escribe el link de invitación en el log estructurado y **no
  abre ningún socket**. El flujo de invitación se puede completar en local copiando ese link.
- **Falta:** elegir proveedor transaccional (SendGrid, Postmark, SES, el que sea — la decisión está
  deliberadamente abierta porque el adaptador habla SMTP y no el SDK de nadie), cargar las
  `SMTP_*` y poner `EMAIL_ADAPTADOR=smtp`.
- **Protección:** `Settings` rechaza `consola` en `production` al arrancar.

### 2.3 Worker de `notifications`

El envío se encola en la cola `notifications` (ADR-003). **Si no hay un worker consumiéndola, la
invitación se crea igual y el mail no sale** — que es el modo de falla elegido a propósito: el
Administrador ve la fila pendiente y puede reenviar. Para que salga de verdad hace falta levantar
el worker de esa cola:

```
celery -A cheatsheet.workers.main:app worker -Q notifications -c 4
```

---

## 3. Deuda declarada — con dueño, fuera de este épico

Ninguna de estas bloquea el cierre. Están acá para que nadie las descubra después.

| Deuda | Por qué | Dónde se salda |
|---|---|---|
| ~~**CUIT no se valida contra el padrón de ARCA**~~ | ✅ **Saldada a medias por `padron-y-datos-fiscales`** (2026-08-20). Con ARCA conectada, cada guardado consulta el padrón y un CUIT inexistente bloquea. **En el paso 2 del onboarding sigue sin validarse**, y no por pereza: ahí todavía no hay certificado con qué preguntar. Ver el plan de esa unidad, «El hueco que esta unidad no puede cerrar» | Lo que queda pide reordenar el onboarding o una credencial de plataforma, las dos descartadas |
| ~~**`CondicionIVA` se elige a mano**~~ | ✅ **Saldada** (2026-08-20). El padrón la completa cuando está vacía y propone reemplazo cuando difiere; el usuario puede corregirla, como pide RN-02 | — |
| **La interfaz no se traduce** | `pref_idioma` se guarda y gobierna el formato de fechas, horas y números; montar i18n para un catálogo de un solo idioma es infraestructura sin nadie del otro lado. El criterio «cambio mi idioma y la interfaz se actualiza» de HU-E1-07 **queda incumplido** | Cuando exista un segundo idioma. Nada de lo escrito lo impide |
| **No hay pantalla de bitácora** | El sumidero de HS-T5 está y audita todo; leerlo es otra historia | **Épico 10** (HU-E12-01, HU-E12-02) |
| **No hay DLQ** | HS-T6 | **Épico 4** |
| **PAN-USR-01 y PAN-USR-02 no tienen prototipo** (hueco P9) | La maquetación de Etapa 5 no las incluye. Se construyeron con el catálogo de componentes del PDF §1.3 y los tokens ya importados | Si aparece el prototipo, se ajustan |
| **El PDF y `styles.css` del prototipo difieren en 8 valores** (huecos P1–P8) | Se decidió que manda el PDF. Consecuencia: el panel **no se ve idéntico** al prototipo HTML y las capturas de entrega habría que regenerarlas | Decisión tomada el 2026-08-14, no se revisa |

---

## 4. Cosas chicas, para el próximo que pase

- **`GET /auth/empresa`** se agregó para que el layout del panel sepa si el onboarding está
  completo. Cuesta una llamada por navegación. Si el panel crece, conviene un endpoint de
  «contexto de sesión» que devuelva empresa + usuario + rol de una vez, en lugar de tres.
- **La renovación de sesión es manual, y se nota.** `/api/auth/refresh` existe y funciona, pero
  nadie lo llama solo: **el panel te saca a los 15 minutos** aunque tengas la cookie de refresh al
  lado. Apareció en el QA del 2026-08-18, en carne propia.
  **Por qué no lo arreglé ahí mismo:** el lugar natural es el middleware de Next, y ahí hay una
  carrera real — dos peticiones en paralelo rotarían el mismo token de un solo uso, y la detección
  de reuso revocaría **la familia entera**, que es peor que el problema. Necesita un candado o un
  único punto de renovación, y eso es una decisión de diseño, no un parche de QA.
- **`Button variante="destructivo"` confirma con `window.confirm`.** Funciona y está testeado, pero
  esta unidad agregó `Modal` al sistema de diseño y la confirmación debería usarlo. Cambiarlo toca
  todas las acciones destructivas del sistema: es alcance, no defecto.
- **La suite de integración borra la base local al terminar.** Correr `pytest` en medio de un QA
  manual se lleva puestos los datos de prueba. En CI es un contenedor descartable; en una laptop,
  conviene una segunda base o hacer el QA después de los tests.
- **El invariante del último Administrador se serializa con `SELECT … FOR UPDATE`** sobre la fila de
  `empresa`. Es correcto y está probado con dos operaciones concurrentes de verdad, pero es un
  candado por empresa: si alguna vez hay operaciones masivas sobre usuarios, ese es el cuello.

---

# Épico 2 — Conexión con los servicios externos

## 5. Credenciales reales · **te toca a vos**

Todo el épico corre contra adaptadores simulados, a propósito: el flujo se recorre entero en una
laptop y **ningún test toca la red**. Conseguir las credenciales es tarea de despliegue, y hasta que
existan, `staging` sigue simulado.

### 5.1 WhatsApp Business (unidad `conexion-whatsapp`, ya implementada)

Hacen falta tres cosas, y las tres salen de **Meta Business Manager**:

| Qué | Dónde |
|---|---|
| Token de un **usuario de sistema** con permisos sobre la cuenta | Business Settings → Users → System Users |
| `phone_number_id` del número a conectar | WhatsApp Manager → API Setup |
| `waba_id` de la cuenta de WhatsApp Business | El mismo lugar |

**No van a un `.env`.** El Administrador los pega en la pantalla de integraciones y quedan
**cifrados por empresa** en `configuracion_de_integracion`. Lo que sí va al `.env` de despliegue es
sólo esto:

```bash
WHATSAPP_ADAPTADOR=meta          # 'simulado' es rechazado al arrancar en produccion
WHATSAPP_GRAPH_VERSION=v21.0     # Meta deprecia una version por trimestre: revisala
```

⚠️ **`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_APP_SECRET` y
`WHATSAPP_WEBHOOK_VERIFY_TOKEN` no son estas.** Ésas son de plataforma, para los webhooks entrantes
del agente conversacional (épico 8). Confundirlas significaría que **todas las empresas mandan
mensajes desde el mismo número**.

Y el reloj que importa: **Meta tarda entre 24 y 72 horas** en verificar cada número (HU-E2-03
RN-02). Cuanto antes se cargue el primero, antes se puede demostrar el ciclo completo en `staging`.

### 5.2 ARCA (unidad `conexion-arca`, ya implementada)

Hace falta el **certificado fiscal de homologación** de cada empresa, que se obtiene en el sitio
de ARCA generando un CSR y descargando el `.crt`. Son dos archivos:

| Qué | De dónde sale |
|---|---|
| Certificado (`.crt` o `.pem`) | Lo emite ARCA a partir del CSR de la empresa |
| Clave privada (`.key`) | La genera la empresa junto con el CSR. **Sin contraseña** |

**Tampoco van a un `.env`.** El Administrador los sube en la pantalla de integraciones y quedan
cifrados por empresa. Lo que va al `.env` de despliegue es sólo:

```bash
ARCA_ADAPTADOR=arca              # 'simulado' es rechazado al arrancar en produccion
```

⚠️ **`AFIP_CERT_PATH` y `AFIP_KEY_PATH` fueron borradas del template.** Describían un certificado
**de plataforma que no existe ni debe existir**: la credencial es por empresa. Dejarlas invitaba a
montar un certificado compartido, que es el error que haría que una empresa emita comprobantes con
el CUIT de otra.

Y algo que conviene tener presente al probar contra ARCA de verdad: **el ticket de acceso dura 12
horas y ARCA se niega a emitir otro mientras el anterior siga vivo**. Por eso se guarda en la base
(ADR-0004). Si alguna vez hay que forzar uno nuevo, no alcanza con reiniciar: hay que borrar la
fila de `ticket_de_acceso` **y** esperar a que ARCA considere vencido el anterior.

**El mismo certificado tiene que estar autorizado para dos servicios**, y eso se hace una vez por
empresa en el sitio de ARCA, al asociar el certificado a un servicio (`padron-y-datos-fiscales`):

| Servicio | Para qué |
|---|---|
| `wsfe` | Emitir comprobantes — épico 5. Es contra el que se valida la conexión |
| `ws_sr_padron_a5` | Consultar el padrón de contribuyentes (HU-E1-02 RN-01) |

Un certificado autorizado sólo para `wsfe` conecta bien y después no puede consultar el padrón: la
pantalla dirá «no pudimos consultar el padrón de ARCA», que es correcto pero no explica la causa.
Si aparece eso con ARCA conectada y andando, **el primer lugar a mirar es la autorización del
servicio en ARCA**, no el código.

Las dos URLs del padrón tienen valor por defecto y no hace falta declararlas salvo que ARCA las
mueva: `ARCA_PADRON_URL_HOMOLOGACION` y `ARCA_PADRON_URL_PRODUCCION`.

### 5.3 MercadoPago (unidad `conexion-mercadopago`, ya implementada)

Hace falta **una aplicación creada en el panel de desarrolladores de MercadoPago**, y de
ahí salen dos valores que **sí van al `.env`** —a diferencia de ARCA y WhatsApp— porque
identifican a *nuestra* aplicación y no a una empresa:

```bash
MERCADOPAGO_ADAPTADOR=mercadopago    # 'simulado' es rechazado al arrancar en produccion
MERCADOPAGO_CLIENT_ID=...
MERCADOPAGO_CLIENT_SECRET=...
```

Lo que es por empresa son los **dos tokens** que devuelve el flujo OAuth2, y ésos quedan
cifrados en `configuracion_de_integracion`. Nunca en un `.env`.

⚠️ **`MP_ACCESS_TOKEN` fue borrada del template**, por el mismo motivo que `AFIP_CERT_PATH`:
describía un token de vendedor **de plataforma que no existe ni debe existir**. Dejarla
invitaba a que todas las empresas cobraran en la misma cuenta. `MP_WEBHOOK_SECRET` sí
queda: los webhooks de pago del épico 6 son de plataforma.

Y tres cosas que conviene saber antes de probar contra MercadoPago de verdad:

| Qué | Por qué importa |
|---|---|
| **La `redirect_uri` tiene que coincidir carácter por carácter** con la registrada en la aplicación | Si difiere, el canje falla con `invalid_grant`, que es el mismo error que da un código vencido. Por defecto sale de `APP_BASE_URL` |
| **No hay host de sandbox.** El mismo `api.mercadopago.com` atiende todo | Lo que separa una cuenta de prueba de una real es `live_mode`, y el sistema lo cruza contra `APP_ENV`: **una cuenta real en un despliegue de homologación se rechaza** |
| **Las cuentas de prueba se crean desde el panel** (usuarios de prueba vendedor y comprador) | Sin una, no se puede recorrer el flujo en `staging` |

## 6. Deuda declarada del épico 2

| Qué | Por qué queda afuera | Dueño |
|---|---|---|
| **Embedded Signup de Meta** reemplaza el formulario manual de tres campos | Exige una app de Meta **aprobada**, que no existe. El popup del SDK de Facebook es mucho mejor UX, pero no se puede construir ni demostrar hoy (decisión D-f) | Se cambia `FormularioDeWhatsApp.tsx` y `whatsapp/conector.py`, nada más |
| **El webhook de cambio de estado del número** | Es de plataforma: necesita endpoint público, validación de firma con `WHATSAPP_APP_SECRET` y app de Meta. Su endpoint es del épico 8 (decisión D-d) | Épico 8. El sondeo pasa a ser la red de seguridad |
| **La calidad de la línea sólo se ve cuando es `RED`** | Se registra siempre (RN-03) pero la pantalla la muestra únicamente como detalle del estado Atención. Mostrar `GREEN`/`YELLOW` en la tarjeta es diseño que el mockup no tiene | Cuando haya un mockup |
| **Un certificado de ARCA revocado antes de vencer no se detecta hasta la próxima renovación de ticket** | La verificación en vivo lee el `notAfter` local y no llama a WSAA, a propósito: llamar quemaría el ticket de 12 h en cada refresco de pantalla y chocaría con la regla del proveedor (decisión D-e) | Aparece igual, en el primer momento en que importa: cuando hay que emitir |
| **PyAfipWs sigue sin instalarse** | WSAA no lo necesita (ADR-0004). WSFEv1 es otra historia y es decisión del épico 5, donde ADR-012 sigue vigente | Épico 5 |
| **Un `state` de OAuth2 vive en Redis y no sobrevive a un flush** | Es un secreto de diez minutos: perderlo significa que el Administrador vuelve del proveedor y tiene que empezar de nuevo, no que algo se rompa. Una tabla costaría una migración y un barrido para el mismo resultado | Nadie: es la decisión |
| **La renovación de MercadoPago no se reintenta dentro del día** | Si el canje falla por red, la tarea termina sin cambiar nada y la del día siguiente vuelve a intentar. Con quince días de margen hay catorce intentos antes de que algo se rompa | Si alguna vez el margen baja, esto pasa a importar |
| **`MERCADOPAGO_REDIRECT_URI` no se valida contra la aplicación registrada** | No hay forma de preguntarle a MercadoPago cuál registró. Un desajuste se manifiesta como `invalid_grant` en el primer intento, con un mensaje que habla del código | Está escrito en §5.3 |

## 7. Cosas chicas del épico 2

- **`gitleaks` va a empezar a fallar cuando CI suba el pin.** La versión fijada es 8.21.2; desde
  ~8.30 el escáner decodifica base64 y rescanea, y con eso marca `.claude/hooks/test_guards.sh:34`,
  que **a propósito** codifica secretos falsos para probar que los guardas los bloquean. No lo toqué
  porque es preexistente y de otra unidad, pero conviene saberlo antes de que aparezca como sorpresa
  en un PR ajeno.
- **`empresas_con_integracion_pendiente()` es la única lectura entre empresas del sistema.** Está
  hecha tan angosta como se pudo —devuelve `empresa_id` y nada más—, pero es una perforación en la
  barrera RLS y merece una mirada en cualquier revisión de seguridad.
- **El sondeo corre para todas las empresas cada 30 minutos.** Hoy es un `SELECT DISTINCT` sobre un
  índice parcial y no cuesta nada. Si algún día hay miles de integraciones pendientes a la vez, el
  fan-out de una tarea por empresa es el punto a mirar.
- **Beat dejó de estar vacío.** La advertencia de `workers/beat.py` sobre no replicarlo ahora tiene
  consecuencias reales: dos schedulers son dos sondeos, y en el momento en que Meta contesta, dos
  mails a cada Administrador.

- **`integrations` tiene tres funciones `SECURITY DEFINER`**, no dos: `conexion-mercadopago` agregó
  `empresas_con_integracion_de_mercadopago()` para su barrido diario, y corrigió el comentario de la
  migración 0006 que decía «la segunda y última». Las tres devuelven `empresa_id` y nada más, y son
  las únicas lecturas entre empresas del sistema: merecen una mirada en cualquier revisión de
  seguridad. Cada una responde **una** pregunta y no toma argumentos — una función parametrizada
  sería un agujero cuya forma elige quien llama.
- **Los tickets de acceso también dependen de `SECRETS_ENCRYPTION_KEY`.** Rotar esa clave ahora
  implica dos tablas, no una — aunque con los tickets alcanza con borrarlos: se vuelven a emitir
  solos cuando expiren.
- **La firma CMS es nuestra.** Son unas cuarenta líneas y están cubiertas por tests que verifican
  el DER de verdad, pero es código propio donde antes se esperaba una librería.

---

# 8. La corrida vigente sobre `develop`

Verificación de los gates reales el **2026-08-24**, sobre `develop` con los épicos 1 y 2 adentro
(commit `80e5653`). No es el registro de ninguna unidad: es el estado del tronco.

```
ruff format --check .   243 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 238 source files
guard_architecture      257 file(s) checked — architecture boundaries intact
test_guards.sh          54 cases, all correct — the guards are active
pytest                  487 passed · 85 skipped · cobertura 80.72 %  (umbral 80)
frontend lint           No ESLint warnings or errors
frontend typecheck      sin errores
frontend test:coverage  230 passed · 88.01 % líneas
```

Dos cosas que hay que leer juntas, porque separadas engañan:

- **Los 85 saltados son los tests de integración**, y se saltaron porque Docker no estaba levantado.
  487 + 85 = 572, que es exactamente lo que reportó el Gate 2 de `conexion-mercadopago` con
  PostgreSQL y Redis arriba: no falta ningún test, faltaba la infraestructura para correrlos.
- **Por eso la cobertura da 80.72 % y no 89.35 %.** El umbral es 80. Corriendo sin los servicios el
  margen real es de **0.72 puntos**, no de nueve. No es un problema hoy —CI los levanta— pero quien
  corra `pytest --cov` en una laptop sin Docker está a un módulo nuevo sin tests de romper el gate,
  y el mensaje de error va a hablar de cobertura en lugar de hablar de Docker.

---

# Épico 3 — Catálogo de clientes y servicios

## 9. Hallazgos de `catalogo-de-clientes` que no son de esta unidad

Ninguno bloquea. Se anotan acá en lugar de arreglarse en la rama, por `CLAUDE.md` §8 («no amplíes
el alcance: si ves otro problema, reportalo»).

| Qué | Por qué importa | Dónde se salda |
|---|---|---|
| **`backend/migrations/env.py` no importa los modelos de `integrations`** | Sólo registra `identity` y `observability`. Su propio docstring dice que un modelo ausente es «una tabla que autogenerate propone borrar en silencio», y desde el épico 2 hay cuatro tablas de `integrations` en esa situación. Esta unidad agregó la línea de `master_data`; la de `integrations` es de otra rama | Una línea en `env.py`, en cualquier PR de `integrations` |
| **`npm run format:check` falla en 113 archivos por finales de línea** | El checkout tiene `core.autocrlf=true`, así que todo el repo está en disco con CRLF y Prettier espera LF. Falla en archivos que nadie tocó, así que el gate de formato del frontend **no discrimina** hoy en una laptop Windows. En CI (Linux) pasa | Un `.gitattributes` con `* text=auto eol=lf`, o `endOfLine: "auto"` en `.prettierrc.json`. Es decisión de equipo, no de una unidad |
| **`ruff format --check .` y `mypy .` desde la raíz levantan `tmp/` y `output/`** | Son dos directorios sin trackear del entorno local con scripts de PDF sin anotar. Hacen fallar los gates de la raíz sin que haya nada mal en el repositorio | Agregarlos a `.gitignore` y a los `exclude` de `pyproject.toml`, o borrarlos |
| **El frontend no tenía `node_modules`** | `npm ci` tarda unos minutos y hasta correrlo ningún gate del panel se puede ejecutar. No es un defecto; es que quien retome la rama lo va a necesitar | — |

## 10. Hallazgos de `categorias-y-clasificacion` que no son de esta unidad

| Qué | Por qué importa | Dónde se salda |
|---|---|---|
| **`ClienteDuplicado` no llega al navegador con su mensaje ni con el id del duplicado** | El backend hace lo correcto —`api/main.py` registra un manejador propio que agrega `cliente_existente_id`— pero **el BFF lo descarta**: `leerFalla` (`lib/api.ts`) sólo extrae `codigo` y `detalle`, y `respuestaDeError` (`app/api/auth/_sesion.ts`) reenvía `detalle` **sólo** para `EntradaInvalida`. Un `ClienteDuplicado` es un `InvarianteViolada`, así que la pantalla recibe `{error}` pelado: muestra «No se pudo completar la operacion» en vez del texto de la historia, y el botón «Ver el cliente existente» nunca aparece. **El criterio de aceptación «ofrece ver el duplicado» de HU-E4-01 no se cumple end to end.** El test de componente de #23 no lo vio porque mockea `crearCliente` para que lance `ErrorDeCatalogo` con id, salteándose la ruta HTTP real | Épico 3 lo esquiva: `CategoriaDuplicada` se declaró `EntradaInvalida` (422) justamente por esto. Arreglarlo para clientes es decidir si `respuestaDeError` amplía su lista blanca o si `ClienteDuplicado` pasa a 422. Es una decisión de equipo sobre la política del BFF, no de una unidad |
| **Un endpoint que devuelve 204 rompe la construcción de la app si se anota `-> None`** | Todos los módulos tienen `from __future__ import annotations`, así que FastAPI recibe la anotación como el string `"None"`, la resuelve a `NoneType` —una clase, y por lo tanto *truthy*— y afirma que un 204 no puede tener response model. **Falla al importar**, o sea que se cae la aplicación entera, no el endpoint. Pasó al escribir el `DELETE` de categorías: 6 fallas y 81 errores, ninguno en el archivo culpable | Ya resuelto acá con `response_model=None` y un comentario que explica por qué. Vale la pena saberlo antes de escribir el próximo 204 |
| **Ninguna `page.tsx` tenía test, y esta unidad hizo que eso bloqueara** | Las once páginas estaban en 0 %. Cada unidad que agrega una empuja la cobertura de funciones hacia abajo, y con la de categorías el umbral del 80 % se cruzó. Se escribió el **primer test de páginas del proyecto** (`app/(panel)/datos-maestros/__tests__/paginas.test.tsx`), que cubre las tres de Datos Maestros y prueba cosas reales: el redirect sin sesión y el mapeo de rol a `puedeEditar` | Las otras ocho siguen sin test. El mismo archivo sirve de patrón |

---

# Épico 4 — Sincronización de planillas

> Estado al **2026-09-07**. El épico está **en curso** sobre
> `feature/spreadsheet_sync-sincronizacion-de-planillas`, con las cinco unidades en una sola rama
> (decisión del mapa). Lo de acá abajo **no se resuelve escribiendo el código del épico**: son
> decisiones tuyas, credenciales, o cosas que arrastramos de épicos anteriores.

## 11. Bloqueantes de una unidad · **te tocan a vos**

### 11.1 Elegir el proveedor de LLM — bloquea `mapeo-asistido` (D11)

`docs/architecture.md` declara el puerto `PortModeloDeLenguaje` y le asigna dos contextos
(`spreadsheet_sync` y `conversational`), y reserva el worker 8 para sus llamadas. **Ningún documento
del repositorio elige un proveedor**, y los ADR van del 0001 al 0006 sin tocar el tema.

`mapeo-asistido` es el primer consumidor del sistema, pero la decisión **la hereda el épico 8
entero** —el agente de WhatsApp—, así que no es de una unidad: es un **ADR**, y hay que escribirlo
antes del Gate 1 de esa unidad.

Lo que el ADR tiene que cerrar:

| Qué | Por qué no se puede dejar abierto |
|---|---|
| Proveedor y modelo | Define el SDK, el formato de la respuesta y el costo por corrida |
| Dónde viven los prompts versionados | `CLAUDE.md` §5 los saca del medio de la lógica de negocio, sí o sí |
| El schema contra el que se valida cada respuesta | `CLAUDE.md` §5: la salida de un modelo es entrada no confiable, como un formulario |
| Timeout y límite de tokens | Obligatorios en toda llamada externa (`CLAUDE.md` §5) |
| Qué pasa cuando el modelo no contesta | Para el mapeo: degradar a «todas las columnas Sin asignar» y que el usuario mapee a mano. **Nunca** bloquear la ingesta |

**Credenciales:** además del ADR hace falta la API key del proveedor en el `.env` de despliegue. Como
con ARCA y MercadoPago, hasta que exista, `staging` corre contra un adaptador simulado.

### 11.2 Credenciales de Google para vincular planillas — bloquea la demo de `vinculo-de-planilla`

HU-E2-04 RN-01 pide OAuth2 con permiso de lectura **sobre el archivo elegido y no sobre todo el
Drive**, o sea el selector de archivos de Google, no un scope amplio. Hace falta:

| Qué | Dónde |
|---|---|
| Cliente OAuth2 con las APIs de Sheets y Drive habilitadas | Google Cloud Console |
| El scope acotado por archivo (`drive.file`) | En la configuración del cliente |

Es el **mismo proyecto de Google Cloud** que quedó pendiente en §2.1 para el login con Google del
épico 1. Si se crea uno, sirve para las dos cosas.

El código se puede construir y testear entero sin esto —ningún test toca la red—, pero la demo en
`staging` contra una planilla real no.

## 12. Decisiones ya tomadas en el mapa, para que nadie las redescubra

Las tres están argumentadas en [`units.md`](units.md), en el bloque del épico 4. Acá quedan
resumidas porque tienen consecuencias que se van a ver en el código:

| # | Decisión | La consecuencia que se va a ver |
|---|---|---|
| **D10** | `ARCHIVO` se agrega al enum `proveedor_planilla`, que el DER cerraba en Google Sheets y Excel Online | Queda un «vínculo» que no vincula nada. La sincronización incremental (HU-E3-04) y el write-back (HU-E3-07) **no aplican** a `ARCHIVO` y tienen que decirlo con una guarda explícita, igual que ya la tienen para `EXCEL_ONLINE` |
| **D11** | El proveedor de LLM escala a ADR | Ver §11.1 |
| **D12** | Al modelo se le mandan **solo los nombres de las columnas**, nunca filas de muestra | Un encabezado ambiguo (`Codigo`, `Tipo`, `Nro`) va a caer más seguido en confianza Baja, que es exactamente lo que HU-E3-01 RN-03 manda hacer con ella. Se prefiere un mapeo que pregunta más a uno que filtra datos de clientes |

## 13. Arrastrado de antes, todavía abierto

Nada de esto es del épico 4, pero sigue sin cerrarse y se cruza con él.

| Qué | Estado | Dónde se salda |
|---|---|---|
| **El épico 3 no está cerrado en el mapa** | El PR [#27](https://github.com/cheatsheet12/CheatSheet/pull/27) está **abierto y en verde desde el 2026-09-01**. Hasta que se mergee, `aidlc_next.py` sigue diciendo que el épico en curso es el 3 | Mergear el #27 |
| **Un commit del épico 2 nunca llegó a `develop`** | `1577d03`, en `feature/infra-staging-database`, hecho **seis minutos después** de que se mergeara el PR #14. Corrige el registro de la unidad: `develop` todavía afirma que la base de Neon quedó en la revisión `0003` y que «falta 0004→0007», cuando ese mismo día se migró y verificó sobre `0007` con las 8 comprobaciones en verde | Un `cherry-pick` a cualquier rama |
| **El fix de PRU-09 no tiene PR** | Commiteado como `35f9ae5` en `fix/identity-empresa-role-guard`. `CompletarDatosDeEmpresa` no miraba el rol, así que un Operador podía reescribir razón social, CUIT y condición de IVA. Verificado en verde, sin PR abierto | Gate 3 de esa rama, cuando lo pidas |
| **`migrations/env.py` no importa los modelos de `integrations`** | Cuatro tablas del épico 2 siguen sin registrar, o sea que autogenerate propone borrarlas en silencio. Detectado por `catalogo-de-clientes` (§9) y todavía sin dueño | Una línea en `env.py`. **Este épico agrega la de `observability` y `spreadsheet_sync`; la de `integrations` sigue huérfana** |
| **`npm run format:check` falla en 113 archivos por CRLF** | El gate de formato del frontend no discrimina en una laptop Windows. En CI (Linux) pasa | Un `.gitattributes` con `* text=auto eol=lf`. Es decisión de equipo |

## 14. Hallazgos de `vinculo-de-planilla` que no son de esta unidad

| Que | Por que importa | Donde se salda |
|---|---|---|
| **`Tabla` pierde su titulo cuando no hay filas** | El `titulo` se renderiza como `<caption>` dentro de `<table>`, y el camino vacio devuelve solo un `<p class="tabla__vacia">`. Un lector de pantalla recibe un parrafo suelto sin ninguna etiqueta que diga de que listado esta vacio. Afecta a **cinco pantallas** -usuarios, clientes, servicios, categorias e ingesta- y el estado vacio es justamente el primero que ve una empresa recien registrada | Tres lineas en `frontend/src/shared/ui/Tabla.tsx`. Es del sistema de diseno, no de una unidad |
| **`localhost` no resuelve a los contenedores en Windows** | Resuelve a IPv6 y `asyncpg` queda colgado hasta el timeout, con un `TimeoutError` que no nombra la causa. Con `127.0.0.1` funciona. `argumentos_de_conexion()` acepta los dos, asi que no es del codigo -- pero cuesta media hora la primera vez y no esta escrito en ningun lado | Una linea en `backend/.env.example` o en la skill `run-local` |
| **`ClienteDuplicado` sigue sin llegar al navegador** | `respuestaDeError` ahora reenvia el `detalle` de **todo 422**, lo que arregla las cuatro subclases de `spreadsheet_sync`. `ClienteDuplicado` es un `InvarianteViolada` y responde 409, asi que sigue perdiendo su mensaje y el boton «Ver el cliente existente» sigue sin aparecer | Decidir si pasa a 422. Es del epico 3 (seccion 10) |

## 15. Lo que el épico 4 deja abierto · **te toca a vos**

### 15.1 La lectura incremental no lee todavía — HU-E3-04 queda a medias

`sincronizar_empresa` hace la mitad del write-back y **no vuelve a leer la hoja viva**. Lo
que falta es el **token OAuth por empresa**: `escritura_de_planilla()` construye el
adaptador con un token vacío, porque resolver la credencial cifrada de cada empresa desde
`integrations` (ADR-0003) es la pieza que la unidad 5 no llegó a armar.

Se implementó primero la mitad con riesgo de bucle —los tres guardas anti-bucle de
ADR-007— y no la mitad que sólo lee, porque los guardas son los que conviene tener en
producción antes de que algo empiece a escribir por horario.

**Los dos criterios que quedan incumplidos**, dichos con precisión:

| Criterio de HU-E3-04 | Estado |
|---|---|
| «Se modifica una fila en la planilla vinculada → el sistema lo sincroniza en la siguiente corrida» | **incumplido** |
| «Se agregan filas nuevas → procesa sólo las nuevas» | **incumplido** |
| «Cambia la estructura de columnas → pausa y muestra el mensaje» | ✅ implementado y probado |
| «Una sincronización falla → se registra en la bitácora y se notifica» | ✅ el evento se publica |

Lo que hace falta para cerrarlos es lo mismo que ya está escrito en §11.2: el cliente
OAuth2 de Google. Con la credencial resuelta por empresa, el barrido que ya corre en Beat
pasa a leer además de escribir.

### 15.2 Credenciales que este épico necesita y no tiene

Las dos ya están en §11, y siguen siendo tuyas:

- **La API key de Anthropic** (§11.1). Sin ella el mapeo corre con el adaptador simulado,
  que empareja por parecido de texto: alcanza para recorrer el flujo en una laptop y
  produce un catálogo plausible y equivocado si alguien lo usara de verdad. `Settings` lo
  rechaza en `production`.
- **El cliente OAuth2 de Google con la API de Sheets habilitada** (§11.2). Sin él no hay
  vinculación real, ni lectura incremental, ni escritura de vuelta.

### 15.3 Deuda declarada del épico 4

| Qué | Por qué queda afuera | Dónde se salda |
|---|---|---|
| **Correr una carga inicial completa dos veces duplica todos los servicios** | `PortRepositorioServicio` no tiene `buscar_por_nombre` a propósito —dos sucursales venden el mismo «Corte»— así que la ingesta siempre crea. Ninguna historia pide evitarlo: el reproceso sólo vuelve sobre lo que falló y el sync incremental sólo lee lo que cambió | Es una decisión sobre identidad de servicio, y se toma con `master_data` el día que importe |
| **Una regresión en la calidad del mapeo es invisible para CI** | Ningún test llama al modelo real, y así tiene que ser. Quien ajuste el prompt necesita un juego de encabezados de verdad y una comparación manual | Declarado en ADR-0007. Es problema del épico 8 antes que de nadie |
| **El write-back sólo empuja clientes, no servicios** | `RegistrosDeMasterData` consulta `PortRepositorioCliente` y nada más. HU-E3-07 habla de «los registros gestionados desde el panel» sin distinguir, pero el catálogo de servicios no tiene todavía un consumidor que lo cree desde el panel con destino a la planilla | Una consulta más en `ListarClientesParaEscrituraDeVuelta`, cuando haga falta |
| **La escritura pisa la hoja entera en cada corrida** | `values.update` sobre `A1` reescribe desde arriba. Con hasta 500 registros por lote es correcto y simple; con más, la hoja quedaría truncada | Paginar la escritura, o pasar a `values.append`. Aparece el día que una empresa pase los 500 registros de origen PANEL |
| **`ProcesamientoDePlanilla` no tiene pantalla de historial por vínculo** | El endpoint acepta `vinculo_id` y el listado lo soporta; la pantalla muestra todas las cargas de la empresa | Un filtro en PAN-ING-01, si alguien lo pide |

---

# Épico 5 — Facturación electrónica

> Estado al **2026-09-07**. El mapa está escrito; las cuatro unidades arrancan sobre
> `feature/billing-facturacion-electronica`. **Este es el épico de mayor riesgo del
> sistema**: un CAE no se deshace, y lo único que revierte una factura es otra factura.

## 16. Bloqueantes · **te tocan a vos**

### 16.1 El certificado fiscal de homologación — sin esto no hay demo

Ya está descrito en §5.2 y sigue siendo lo mismo, pero ahora **bloquea el criterio central
del épico**: «se emite una factura contra ARCA en homologación y **se obtiene un CAE
real**». Sin certificado, todo el flujo corre contra el adaptador simulado y ese CAE no
existe.

Recordá lo que ya está anotado en §5.2 y que ahora importa de verdad:

| Qué | Por qué importa acá |
|---|---|
| El certificado tiene que estar autorizado para **`wsfe`** | Es el servicio de emisión. Un certificado autorizado sólo para `ws_sr_padron_a5` conecta y después no puede facturar |
| El **punto de venta tiene que estar habilitado en ARCA** | HU-E5-05 RN-03. Se habilita en el sitio de ARCA, por CUIT, y no se puede hacer desde el sistema |
| Los datos del emisor tienen que estar completos | Razón social, CUIT y condición de IVA de la empresa. Es el onboarding del épico 1, y ahora se factura con eso |

### 16.2 Aprobar el ADR-0008 — bloquea `emision-de-comprobantes`

[ADR-0008](../adr/0008-wsfev1-cliente-propio.md) **supersede al ADR-012 de Etapa 5**, que
había elegido PyAfipWs. La propuesta es un cliente SOAP propio sobre `httpx` y `defusedxml`,
por tres razones: PyAfipWs es GPL, no está tipado —y `mypy --strict` es obligatorio
justamente en el camino fiscal— y trae su propio manejo de tickets, que choca con ADR-0004.

**El contraargumento honesto está escrito en el ADR y conviene leerlo antes de aprobar:**
PyAfipWs sabe cosas de ARCA que nosotros vamos a aprender siendo rechazados. Estamos
cambiando experiencia acumulada ajena por una costura tipada y testeable. Es defendible
porque la superficie es chica —cuatro operaciones— pero **no es gratis**.

Es una decisión de arquitectura que revierte una de Etapa 5, así que la aprobás vos.

## 17. Riesgos del épico que conviene tener a la vista antes de empezar

| Riesgo | Por qué es distinto de todo lo anterior |
|---|---|
| **Un comprobante mal emitido es irreversible** | No hay `DELETE`, no hay rollback, no hay «lo arreglamos en el próximo deploy». Se arregla con una nota de crédito, que también va a ARCA y también queda |
| **Dos emisiones simultáneas con el mismo número** | ARCA rechaza la segunda —o autoriza las dos, que es peor y se arregla con la AFIP. Decisión D14: se serializa con `SELECT … FOR UPDATE` sobre el punto de venta |
| **Un CAE autorizado cuya respuesta se pierde** | El peor estado posible: ARCA lo emitió, nosotros no lo sabemos, y reintentar emite otro. **Ninguna historia lo cubre.** Es la pregunta que el Gate 1 de `emision-de-comprobantes` tiene que responder |
| **Un centavo de redondeo** | ARCA valida que los totales cierren contra la suma de ítems y rechaza con un código que no dice que faltó un centavo. Decisión D15: se redondea por ítem y los totales son sumas de valores ya redondeados |

## 18. Lo que este épico hereda y no vuelve a construir

Es el primer épico que se apoya casi enteramente en lo anterior, y conviene decirlo porque
significa que si algo de eso está flojo, se nota acá:

- **El ticket de acceso a ARCA** (ADR-0004, épico 2). Si el ticket falla, no se factura.
- **La consulta al padrón** (`padron-y-datos-fiscales`, épico 2), que HU-E5-03 RN-02 usa
  para validar el CUIT del receptor.
- **La DLQ** (HS-T6, épico 4), donde va a parar una emisión que agotó sus reintentos.
- **El catálogo de clientes** (épico 3), de donde sale el receptor.
- **La bitácora** (HS-T5, épico 1). Un comprobante emitido tiene que quedar registrado, y
  es de las operaciones donde más importa.

## 19. Lo que salió de la unidad `puntos-de-venta` (épico 5, unidad 2)

**Los adaptadores reales contra WSFEv1 estaban sin test, y uno tenía un bug.** Las dos
unidades del épico escribieron un cliente SOAP contra ARCA y probaron sólo el simulado. El
parser de la respuesta real quedó afuera, que es justo la pieza que se equivoca en silencio:
no tira excepción, devuelve vacío, y vacío se lee igual que «ARCA no te habilitó nada».

Al escribir el test aparecio esto en `billing/infrastructure/habilitacion.py`:

```python
bloqueado = (nodo.findtext("{*}Bloqueado") or "N").strip().upper() != "N"
```

Un `<Bloqueado></Bloqueado>` vacío es *falsy*, así que el default disparaba y «ARCA no nos
dijo» se leía como **no bloqueado** — la dirección insegura. Ya está arreglado (sólo un
`"N"` explícito habilita) y cubierto, y `CatalogosDeWsfe` de la unidad 1 recibió su test de
contrato en el mismo commit.

**Lo que queda como regla para el resto del épico:** todo adaptador contra ARCA se prueba
con `httpx.MockTransport` y sobres grabados, además de su simulado. El simulado prueba el
caso de uso; el transporte inyectado prueba el parser. Son dos cosas distintas y sólo una de
las dos toca XML que escribió otro.

**Un comentario viejo en `frontend/src/app/api/servicios/__tests__/rutas.test.ts`.** Dice
que `respuestaDeError` reenvía `detalle` sólo para `EntradaInvalida`; desde el épico 4 lo
reenvía en cualquier 422. El test pasa porque afirma sobre el comportamiento, no sobre el
comentario. Corregirlo es una línea, en el PR que toque ese archivo por otra razón.

**`habilitacion_de_arca()` sigue armándose con el mapa de credenciales vacío**, igual que
`catalogos_fiscales()`. Es la misma pieza pendiente —resolver el ticket de cada empresa
desde `integrations`— y se arma una sola vez en `emision-de-comprobantes`, que la necesita
sí o sí.

---

# Fase 2 — Verificaciones pendientes contra los sandbox

Lo que la fase 2 (ajustes de la revisión, ADR-0009) dejó **sin poder verificar** porque las
integraciones corren simuladas. Cuando el equipo tenga el sandbox de MercadoPago y el certificado
de homologación de ARCA (ola 0), se recorre esta lista **antes** de dar por cerradas las unidades
que dependen de ella. Cada unidad nueva suma acá lo que no pudo verificar.

## 20. MercadoPago (sandbox)

| # | Qué verificar | Unidad | Qué pasa si falla |
|---|---|---|---|
| 20.1 | El monto máximo que acepta una preferencia o link de pago, contra el tope propio `MONTO_MAXIMO_DE_COBRO` (100.000.000,00) | `nuevo-cobro-desde-su-panel` | Si el de MercadoPago es menor, manda el suyo: se baja la constante |
| 20.2 | Un pago aprobado trae siempre `date_approved`, en ISO 8601 y con zona horaria | `fecha-de-pago` | Si falta o viene sin zona, `fecha_pago` queda marcada aproximada; revisar la regla |
| 20.3 | Los valores reales de `payment_type_id` / `payment_method_id` | `fecha-de-pago` (ADR-0010) | El medio de pago es un conjunto cerrado; confirmar que nada se clasifica mal |
| 20.4 | Qué trae una **transferencia entrante**: identidad del pagador (DNI/CUIT), fecha y número de operación, y si se consulta con las credenciales del vendedor | `fecha-de-pago`, `cobro-por-transferencia` | Cualquier «no» cambia HU-E6-08 (ADR-0009) |
| 20.5 | La API acepta reembolsos **parciales** en un pago por link de Checkout Pro, varios sobre el mismo pago, y con qué respuesta (la referencia lista el error `4295` «parcial no soportado» para algunas transacciones) | `reembolsos-parciales-y-manuales` | Si un medio no admite parcial, se muestra el rechazo con el motivo; si ninguno, cambia HU-E6-05 |
| 20.6 | Montos con centavos llegan exactos: `crear_link` (`pasarela.py`) todavía envía `float(cobro.monto)`; el de reembolsar ya sale de `_numero_json` (P3 de `reembolsos-parciales-y-manuales`), que quien tome esto puede reusar | hallazgo sin unidad | Un centavo de diferencia entre el cobro y el pago |
| 20.7 | Dos notificaciones simultáneas del mismo pago: la segunda hoy puede devolver 500 | hallazgo sin unidad | MercadoPago reintenta; confirmar que no queda un pago sin imputar |
| 20.8 | Que el `date_approved` de un pago real cae dentro de la tolerancia de reloj de 5 minutos respecto de nuestra hora de confirmación y nunca es anterior a la creación del cobro | `fecha-de-pago` | Si un pago legítimo se descarta como implausible, queda marcado aproximado sin necesidad; ajustar `TOLERANCIA_DE_RELOJ` |
| 20.9 | Qué valores de `status` devuelve el `POST` de reembolso (la referencia solo muestra `approved`) y si un reembolso de tarjeta vuelve aprobado en el acto | `reembolsos-parciales-y-manuales` | Si nunca hay `in_process`, la rama «en proceso» queda solo para la falta de respuesta |
| 20.10 | **Crítico.** Reenviar el mismo `POST` con la misma `X-Idempotency-Key` devuelve el mismo reembolso y no crea otro; cuánto tiempo vale la clave | `reembolsos-parciales-y-manuales` | Si no deduplica, «Actualizar estado» sin id puede duplicar un reembolso: habría que consultar la lista de reembolsos del pago en vez de reenviar |
| 20.11 | `GET /v1/payments/{id}/refunds/{refund_id}` devuelve `status`, `amount` y `date_created` con zona horaria | `reembolsos-parciales-y-manuales` | Si la fecha falta, la devolución toma el momento de la confirmación |
| 20.12 | Si un reembolso dispara un webhook `payment.updated` o solo el tópico `topic_claims_integration_wh` | `reembolsos-parciales-y-manuales`, `reembolsos-en-vuelo` | Define si se puede confirmar por notificación además de por barrido, y detectar reembolsos hechos desde el panel de MercadoPago |
| 20.13 | `amount` con centavos (`0.10`, `1234.56`) se reembolsa exacto; mínimo por reembolso y máximo de parciales por pago | `reembolsos-parciales-y-manuales` | Un centavo de diferencia entre la fila y lo devuelto |
| 20.14 | El rechazo trae `message` legible (códigos `2063`, `2024`/`15016`, `4293`, `4295`) y rige el plazo de 180 días | `reembolsos-parciales-y-manuales` | Si no hay mensaje, la pantalla muestra solo el código |
| 20.15 | Qué código HTTP devuelve el `POST` de reembolso cuando **se reenvía la misma `X-Idempotency-Key` mientras el primero sigue en curso** (¿409?) y cuando hay límite de tasa (429). **Resuelto en el código (verificador independiente):** `pasarela.py` ya trata 401, 403, 408, 409, 425 y 429 al reembolsar como «no se pudo preguntar» (`PasarelaNoDisponible`): el reembolso queda en vuelo con su clave y el administrador ve «en proceso» y puede usar «Actualizar estado»; solo el resto de los 4xx es rechazo. **El sandbox debe confirmar** qué código devuelve realmente la clave repetida (¿409?) y el límite de tasa (¿429?), y si algún 4xx de negocio real cae en esa lista y nunca se resolvería solo | `reembolsos-parciales-y-manuales` | Si un 409 o un 429 no significan «no», un reintento legítimo se registraría como rechazado y la clave guardada se perdería: habría que tratarlos como «no se pudo preguntar» (`PasarelaNoDisponible`) y dejar el reembolso en vuelo |
| 20.16 | Qué `status` y `status_detail` tiene el **pago** después de un reembolso parcial y de uno total, y si `GET /v1/payments/{id}` trae el acumulado devuelto | `reembolsos-parciales-y-manuales`, `reembolsos-en-vuelo` | Es la alternativa para conciliar sin depender del id del reembolso, y para detectar devoluciones hechas desde el panel de MercadoPago (fuera de esta unidad) |

## 21. ARCA (homologación)

| # | Qué verificar | Unidad | Qué pasa si falla |
|---|---|---|---|
| 21.1 | Responsable Inscripto → receptor IVA No Alcanzado emite **Factura B** (confianza media) | `tipos-de-comprobante-por-receptor` | D90: se corrige la tabla con un release y no se emite ese tipo hasta entonces |
| 21.2 | `CondicionIVAReceptorId = 6` sirve para Monotributista Social y Promovido (13 y 16) | `tipos-de-comprobante-por-receptor` | Se agrega el código fino |
| 21.3 | Fecha real desde la que ARCA **rechaza** comprobantes sin `CondicionIVAReceptorId` (RG 5616/2024; hoy solo fuentes secundarias dicen 01/12/2026) | `tipos-de-comprobante-por-receptor` | Define el plazo de la sesión dedicada a esa unidad |
| 21.4 | Factura C sin arreglo `Iva` y con `ImpIVA` en 0 | `tipos-de-comprobante-por-receptor` | Rechazo de toda Factura C |
| 21.5 | Si una nota de crédito exige `CbtesAsoc` | `tipos-de-comprobante-por-receptor` | Rechazo de las notas de crédito |

## 22. Verificaciones manuales (no dependen del sandbox)

| # | Qué verificar | Unidad |
|---|---|---|
| 22.1 | En `/cobros/nuevo`, el concepto y el monto escritos no se pierden al elegir cliente (`router.replace`) | `nuevo-cobro-desde-su-panel` |
| 22.2 | En el navegador, Inicio (PAN-DSH-01) y Reportes con el mismo período muestran las mismas cifras de cobranza, y el selector de Inicio conserva el período al recargar | `indicadores-de-cobranza` |
| 22.3 | Una semana con cobrado negativo y un período con un solo estado de cobro se leen bien en Reportes (color, signo, nota del dato único) | `indicadores-de-cobranza` |
| 22.4 | Después de las 21:00 del último día del mes (hora argentina), Inicio y Reportes abren en el mes que termina, no en el siguiente | `indicadores-de-cobranza` |
| 22.5 | **Hallazgo sin unidad.** El período por defecto de PAN-COB-01 sale de `ahora.replace(day=1)` en UTC (`payments/application/cobros.py:118-123`): entre las 21:00 y las 24:00 del último día del mes ya muestra el mes siguiente. Reportes e Inicio ya lo calculan en hora argentina (`indicadores-de-cobranza`, P5). **Desde `usos-de-faq-por-periodo` (ADR-0012) la zona y el mes calendario argentino se pueden importar desde `payments`**: `shared/zona_horaria.py` publica `ZONA_ARGENTINA` y `MesCalendario` | hallazgo sin unidad |
| 22.6 | **Hallazgo sin unidad.** `periodo_cerrado(ahora)` (`reporting/application/paquete.py:116`) usa `ahora.date()` en UTC; lo llaman la generación del paquete contable (`api/routers/reporteria.py`) y la tarea programada (`workers/tasks_reporting.py:97`). Entre las 21:00 y las 24:00 del último día del mes (hora argentina) toma como «cerrado» el mes que todavía está en curso. Se arregla con `hoy_en_la_zona_del_reporte` (`indicadores-de-cobranza`, P5), o con `ZONA_ARGENTINA` del Shared Kernel (`usos-de-faq-por-periodo`) | hallazgo sin unidad |
| 22.7 | Inicio con tres tarjetas (`dsh-stats--tres`) y el resumen de cobros de cuatro cifras (`rep-kpis--cuatro`) se acomodan bien en escritorio, tablet y celular | `indicadores-de-cobranza` |
| 22.8 | Con un intervalo de 10 min en un recurso y un turno a las 09:00, la grilla de PAN-AGE-02 marca 09:30 como no disponible y ofrece 09:40 (`run-local`) | `limites-e-intervalo-de-turnos` |
| 22.9 | En el formulario de recursos, el campo «Intervalo entre turnos (min)» y el rótulo «Duración del slot (min)» con su ayuda se ven bien en escritorio y en celular | `limites-e-intervalo-de-turnos` |
| 22.10 | En Nuevo turno, cambiar de servicio recalcula la grilla sin dejar elegido un horario viejo, y sin servicio pide «Elegí el servicio para ver los horarios» | `limites-e-intervalo-de-turnos` |
| 22.11 | **Hallazgo sin unidad.** `ocupados_en` (`scheduling/infrastructure/repositories.py:267-273`) trae solo los turnos que **empiezan** ese día: un turno de la noche anterior cuya franja más su intervalo pasa la medianoche no aparece en la grilla, que puede ofrecer un horario que la base después rechaza con 409. No hay doble reserva (la restricción lo frena). Se arregla trayendo también los turnos del día anterior | hallazgo sin unidad |
| 22.12 | En staging, borrar una FAQ, eliminar una categoría, revocar una invitación, desvincular una planilla y quitar el acceso del contador ya no muestran «No se pudo completar» (cada responsable verifica su pantalla) | `borrado-sin-cuerpo` |
| 22.13 | Con `LLM_ADAPTADOR=anthropic` en staging, el intérprete devuelve `pedido_de_turno` sobre frases reales («el jueves que viene a la tarde», «no llego mañana»), la API acepta el esquema anidado con `pattern` y `maxItems` en `output_config.format`, y `max_tokens` alcanza | `reserva-y-cancelacion-por-whatsapp` |
| 22.14 | PRU-05 en staging con el servicio «Consulta general» y un recurso con disponibilidad cargados: «Quiero un turno para mañana» ofrece horarios; «Prefiero el primero» deja el turno `RESERVADO`, canal `AGENTE`, en la agenda; la bitácora filtrada por «Agente IA» muestra `reservar_turno_por_whatsapp`. Pasa de «Fallida» a «Re-ejecutada» (`reglas.md` §5.1) y se actualiza la nota 1 del borrador | `reserva-y-cancelacion-por-whatsapp` |
| 22.15 | Con WhatsApp real (depende de `canal-real-de-whatsapp` y del número de prueba, M3): el cliente recibe **un solo** mensaje por reserva o cancelación, el del agente, y no el aviso del panel además | `reserva-y-cancelacion-por-whatsapp` |
| ~~22.16~~ | ✅ **Confirmado el 2026-10-05.** Los tests contra PostgreSQL de esta unidad (casos 27 y 31 a 37 del plan: diálogo, RLS, savepoint, mensajes simultáneos, migración 0032, PRU-05) se saltearon en local (sin Docker) y pasaron en la CI de #81 (run 37316008291): 2514 tests, ninguno salteado, cobertura total 87,48 % | `reserva-y-cancelacion-por-whatsapp` |
| 22.17 | En staging, con «Estudio Ejemplo SRL»: cargar en PAN-WA-02 el horario del prototipo con un día cortado (09–13 y 16–20) y una fecha sin atención, con la política «mensaje fijo»; escribir en el hueco del mediodía y de noche y ver el mensaje fijo con «hoy a las 16:00» y con la fecha correcta; ver el entrante en PAN-WA-01 **quitando el filtro «sólo escaladas»** («Todas») y `responder_fuera_de_horario` en la bitácora; pasar a «el agente responde igual», pedir una persona y ver el aviso con la hora. Es la re-ejecución de I-09 (#71) | `politica-fuera-de-horario` |
| 22.18 | Con WhatsApp real (depende de `canal-real-de-whatsapp` y del número de prueba, M3): de noche, el cliente recibe **un solo** mensaje fijo por período de cierre y el siguiente mensaje de esa noche no recibe nada | `politica-fuera-de-horario` |
| 22.19 | En el navegador, la tarjeta «Horarios de atención» de PAN-WA-02 (renglón por día con varias franjas, «Hasta la medianoche», política y «Fechas sin atención») se ve bien en escritorio, tablet y celular, y el Operador la ve en modo lectura (el CSS `.hda-*` no se vio en un navegador) | `politica-fuera-de-horario` |
| 22.20 | Los tests contra PostgreSQL de esta unidad (casos 16, 17 y 37 del plan: RLS del horario, `PUT /reglas/horario-de-atencion` y el webhook con política (b)) se saltearon en local (sin Docker): confirmar que pasan en la CI del PR | `politica-fuera-de-horario` |
| 22.21 | ✅ **Verificado en staging el 2026-10-05 (Luciano).** En staging, ingresar al panel con **un** clic: el botón queda en «Ingresando…» y deshabilitado durante todo el `GET /panel?_rsc=…` (~4 s con la API lenta) y el panel abre sin segundo clic; en Network hay un solo `POST /api/auth/login`. Repetir con emisión (PAN-FAC), nota de crédito, nuevo cobro y nuevo turno: un solo `POST` por clic aunque se vuelva a hacer clic mientras carga | `navegacion-pendiente` |
| 22.22 | ✅ **Verificado en staging el 2026-10-05 (Luciano).** En staging, «Cerrar sesión» y luego «atrás» del navegador no muestra el panel desde la caché del router: con el orden `push` → `refresh` el `refresh` ya no se descarta (deducido del código instalado de Next 14.2.15, no observado en un navegador) | `navegacion-pendiente` |
| 22.23 | **Hallazgo sin unidad (ADR-0012).** Además de `shared/zona_horaria.py`, la zona argentina está declarada tres veces más: `reporting/infrastructure/acl.py:69` (`ZONA_DEL_REPORTE`), `scheduling/domain/recurso.py:46` (`ZONA_DE_LA_AGENDA`) e `identity/domain/usuario.py:30`. Pueden apuntar a la constante del Shared Kernel; `usos-de-faq-por-periodo` no lo hizo para no tocar dos contextos que funcionan sin ganar nada observable | hallazgo sin unidad |
| 22.24 | En **staging de Render** (no en local), con «Estudio Ejemplo SRL»: PAN-WA-02 muestra las columnas «Este mes», «Mes anterior» y «Total» y la barra «N usos este mes»; «Ver uso» abre la tarjeta con «Respondida N veces este mes» y la participación (o el motivo si no hay edición con la cual comparar); un usuario de Solo Lectura ve «Ver uso» y no ve «Editar» ni «Eliminar»; y la tarjeta y la tabla se ven bien en escritorio y en celular | `usos-de-faq-por-periodo` |
| 22.25 | Los tests contra PostgreSQL de esta unidad (casos 11 a 17 y 19 a 21 del plan: no pisar una edición, dos usos simultáneos, RLS y solo-inserción de `faq_uso`, `SET NULL` como dueño, frontera del mes en SQL, total con línea de base, migración 0033, webhook repetido y concurrente, API) se saltearon en local (sin Docker): confirmar que pasan en la CI del PR | `usos-de-faq-por-periodo` |
| 22.26 | Con WhatsApp real (depende de `canal-real-de-whatsapp` y del número de prueba, M3): una respuesta con FAQ enviada a un número de prueba suma un uso en «Este mes», y una que no sale (canal caído) no suma | `usos-de-faq-por-periodo` |

**Archivos de más de 400 líneas (CLAUDE.md §5), vistos en `limites-e-intervalo-de-turnos`.** Ya superaban el límite antes de esa unidad y no se partieron (decisión P4): `scheduling/application/turnos.py` (~520), `api/routers/agenda.py` (~685), `RecursosReservables.tsx` (~640) y `tests/contexts/scheduling/application/test_agenda.py` (~1180). Una unidad aparte puede extraer `Avisador` a `application/avisador.py` y partir el router en uno de recursos y uno de turnos.

## 23. Hallazgos y verificaciones de `correccion-de-datos-existentes`

Hallazgos **sin unidad** (se vieron al implementar y no se arreglaron):

- **Retención del respaldo.** `respaldo_de_normalizacion` guarda los nombres originales para
  siempre, con RLS como la tabla de origen. Cuánto tiempo se retienen es una decisión pendiente
  de datos personales.
- **`lower()` puede alargar un nombre.** `normalizacion.py` usa `caracter.lower()` sin la
  protección que tiene `_mayuscula`, y «İ» pasa a dos caracteres. La corrección omite esos
  nombres como `NOMBRE_INVALIDO`; el normalizador no se tocó.
- **Restaurar dos veces infla «conservados».** La segunda restauración informa como conservados
  los registros que ya se habían restaurado en la primera. No cambia ningún dato; solo el conteo.
- **La hoja propia conserva el formato viejo (P2).** La corrección no mueve `updated_at`, así que
  el write-back no envía los nombres corregidos hasta que el cliente se edite o haya un write-back
  completo.

Verificaciones pendientes (sin Docker ni navegador en local):

- Casos 12 a 22 del plan (PostgreSQL y API): se saltean en local y se observan en la CI.
- En el navegador, PAN-DM-01 como Administrador: informe, aplicar, ver la bitácora, restaurar; y
  que un Operador no vea la sección.
- En `staging`, con datos cargados antes de la normalización: que la hoja «CheatSheet (no
  editar)» no cambia después de aplicar, y que el `lower()` de PostgreSQL coincide con el de
  Python en la intercalación del entorno.

## 24. Hallazgos de `normalizacion-de-datos`

Todos quedan **sin unidad**: se vieron al implementar y no se arreglaron, porque ninguno es de
HU-E4-05.

- **Textos libres de otros contextos (P5).** RN-06 dice que FAQ, descripciones de cobro o de
  ítem y mensajes «solo reciben RN-01». Limpiarlos toca `conversational`, `payments` y
  `billing` y altera lo que el usuario escribió; `master_data` no tiene textos libres.
- **Un cliente de planilla sin CUIT se duplica en cada reproceso (P6).** La ingesta solo
  identifica por CUIT (`ingesta.py`), así que sin CUIT siempre crea. La identidad por
  `referencia_fila_planilla` (columna que nadie escribe) se decide junto con la lectura
  incremental de §15.1.
- **`categoria_empresa` no traduce su `IntegrityError`.** Con la búsqueda normalizada ya no
  se escapa por espacios o mayúsculas, pero la carrera de dos pestañas que crean el mismo nombre
  a la vez sigue llegando al índice y responde 500.
- **`ListarClientesParaEscrituraDeVuelta` no funciona.** Su `LIMITE` es 500 y `Pagina` solo
  admite hasta 200, así que cada llamada levanta `EntradaInvalida`. Ningún test del repo lo
  ejercitaba; los de esta unidad fijan el límite en 200 con `monkeypatch`. El arreglo es de una
  línea, pero es de la unidad del write-back.
