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
- ~~**La renovación de sesión es manual, y se nota.**~~ ✅ **Resuelta el 2026-10-05** por el commit
  `67f2db4`: `RenovadorDeSesion` renueva cada 10 minutos y al volver a la pestaña, y manda a `/` ante
  un 401. Se conserva el texto original porque explica por qué no fue un parche de QA.
  `/api/auth/refresh` existe y funciona, pero
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

⚠️ **`WHATSAPP_WEBHOOK_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN` no son estas.** Ésas son de plataforma, para los webhooks entrantes
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
| **El webhook de cambio de estado del número** | Es de plataforma: necesita endpoint público, validación de firma con `WHATSAPP_WEBHOOK_SECRET` y app de Meta. Su endpoint es del épico 8 (decisión D-d) | Épico 8. El sondeo pasa a ser la red de seguridad |
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
| 22.27 | En **staging de Render** (no en local): generar un cobro desde `/cobros/nuevo`, volver con «Atrás» y generar otro → dos cobros distintos; cortar la red tras enviar y reintentar (misma pantalla, sin tocar el formulario) → un solo cobro y un solo link; editar el monto tras un error y reenviar → el aviso «Esta clave ya se uso…» con el enlace al listado | `cobro-con-clave-de-idempotencia` |
| 22.28 | Los tests contra PostgreSQL de esta unidad (casos 9 a 15 del plan: mismo pedido y otro cuerpo por API, dos pedidos concurrentes, la misma clave en dos empresas, índice único y `PedidoEnCurso`, migración 0034) se saltearon en local (sin Docker): confirmar que pasan en la CI del PR | `cobro-con-clave-de-idempotencia` |
| 22.29 | **Aviso a Cristian (#97).** `billing` reutiliza `api/clave_de_pedido.py::exigir_clave_de_pedido`, el parámetro `cabeceras` de `reenviarAlBackend` (`app/api/usuarios/_proxy.ts`) y el contrato del ADR-0013 para `POST /comprobantes` y las notas de crédito | `cobro-con-clave-de-idempotencia` |
| 22.30 | Conseguir la app de Meta con número de prueba y cargar sus credenciales en staging (`integrations`, `WHATSAPP_ADAPTADOR=meta`) — responsable Cristian. **Sin esto no se puede verificar nada de 22.31–22.40**: el código de U5 queda probado sólo contra contratos grabados (`httpx.MockTransport`) | `canal-real-de-whatsapp` (U5–U8) |
| 22.31 | Un texto libre iniciado por la empresa **fuera de la ventana de 24 h** vuelve con `error.code` 131047, y **con qué status HTTP** (la documentación de Meta no lo dice). Si el código llega distinto, ajustar la tabla de `conversational/infrastructure/canal_errores.py` | `canal-real-de-whatsapp` |
| 22.32 | Formato del número argentino que acepta `to`: con o sin `+`, con o sin el `9` de celular (`549…` vs `54…`) contra lo que guarda `master_data`. Si falla, todos los envíos a celulares argentinos fallan y hay que normalizar en el adaptador | `canal-real-de-whatsapp` |
| 22.33 | Status HTTP con que llegan los códigos de throttling (4, 80007, 130429, 131056) y si traen `Retry-After`. La clasificación por código los cubre igual; si traen espera sugerida, evaluar usarla | `canal-real-de-whatsapp` |
| 22.34 | Un `ReadTimeout` provocado (proxy lento) no produce dos mensajes y deja el recordatorio `FALLIDO` | `canal-real-de-whatsapp` |
| 22.35 | `messages[0].id` del envío coincide con el `id` de `statuses[]` del callback | `entregas-de-whatsapp` (U7) |
| 22.36 | Forma del envío `type: template` (posicionales vs `parameter_name`, idioma `es_AR`) y respuesta ante plantilla no aprobada (132001) | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.37 | `GET /{waba_id}/message_templates` (con `rejected_reason` y `components` en `fields`) y el webhook `message_template_status_update`: ver también 22.45 (la app lo recibe en su URL) y 22.50 (el motivo en el `GET`) | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.38 | Un `failed` trae `errors[]` con código legible | `entregas-de-whatsapp` (U7) |
| 22.39 | Punta a punta en staging: registrar `/webhooks/whatsapp/{empresa}` con `WHATSAPP_WEBHOOK_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN` cargados en Render (pendiente #3 del épico 8). Sin el secreto, toda notificación se descarta con 200 (D49) | `canal-real-de-whatsapp` (config) / `entregas-de-whatsapp` |
| 22.40 | Cantidad de destinatarios que admite el número de prueba, para planificar la prueba con menos clientes si hace falta | `canal-real-de-whatsapp` (U5–U8) |
| 22.41 | Los tests contra PostgreSQL de `canal-real-de-whatsapp` (casos 2 y 3 del plan: `tests/integracion/test_barrido_de_recordatorios_postgres.py`, el barrido sin duplicados y el duplicado que ya no envenena la transacción) y `bash .claude/hooks/test_guards.sh` (caso 32; falta `jq` en la máquina de desarrollo) se saltearon en local: confirmar que pasan en la CI del PR | `canal-real-de-whatsapp` |
| ~~22.42~~ | ✅ **Resuelta por `router-de-agenda-por-responsabilidad`** (2026-10-09). `api/routers/agenda.py` (688 líneas) se partió en `agenda.py` (29), `agenda_forma.py` (252), `agenda_recursos.py` (218) y `agenda_turnos.py` (254), sin cambio de rutas ni de orden; la tabla de rutas queda fijada por `tests/api/test_rutas_de_agenda.py` | `router-de-agenda-por-responsabilidad` |
| 22.43 | Estado inmediato tras `POST /{template_id}` sobre una aprobada: ¿sigue `APPROVED` mientras revisa, o pasa a `PENDING`? y si se puede enviar mientras tanto. U6 la trata como `PENDIENTE` hasta que el webhook o la conciliación lo confirmen | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.44 | Código y forma del error de «nombre ya existe en ese idioma» al crear. U6 lo detecta por `error_subcode` 2388023 (`canal_errores.SUBCODIGOS_NOMBRE_EN_USO`, **sin verificar**): si es otro, el versionado del nombre no se dispara y la plantilla queda `SIN_ENVIAR` con el texto de Meta a la vista | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.45 | Que la app de Meta reciba `message_template_status_update` en su URL (`/webhooks/whatsapp`, campo suscripto en el panel de la app). Si no llega, solo funciona la conciliación: hasta `WHATSAPP_PLANTILLAS_MINUTOS` de demora, nada se rompe | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.46 | Que el número de prueba / WABA de desarrollo permita crear plantillas de utilidad, y cuánto tarda la revisión. Si no, la verificación real espera a una WABA productiva | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.47 | Valores de parámetro con salto de línea, tabulación o más de 4 espacios seguidos (¿132012?). U6 reemplaza saltos y tabulaciones por un espacio (`limpiar_valor`); si Meta los acepta, el saneo sobra pero no daña | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.48 | Que un link como valor de parámetro sea aceptable en una plantilla de UTILITY y no la recategorice a MARKETING. Si la recategoriza, la pantalla lo advierte (`categoria_en_meta`); habría que pasar el link a un botón URL (cambio de plantilla) | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.49 | Precio de plantillas de utilidad dentro de la ventana desde el 01/10/2026 (terceros dicen que pasa a cobrarse, igual que el texto). Ninguno en el diseño: plantilla y texto cuestan lo mismo dentro de la ventana en ambos escenarios | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.50 | Que `rejected_reason` venga en el `GET` del nodo con los valores documentados. Si no, la pantalla muestra «Rechazada» sin motivo traducido y `detalle_meta` sigue mostrando el texto | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.51 | Los tests contra PostgreSQL de `plantillas-de-whatsapp-en-meta` (`tests/integracion/test_migracion_0037.py`: backfill y funciones `SECURITY DEFINER`; `tests/integracion/test_plantillas_en_meta_postgres.py`: columnas, RLS, índice único y conciliación; y el `PUT /plantillas` de `test_api_conversacional.py`) y `bash .claude/hooks/test_guards.sh` se saltearon en local: confirmar que pasan en la CI del PR | `plantillas-de-whatsapp-en-meta` (U6) |
| ~~22.52~~ | ✅ ~~**Pregunta abierta Q1** (plan de U6): el monto sale «$ 1234.50» en el texto de fábrica de U5 y «1.234,50» como parámetro de la plantilla. Decidir un único formateador es-AR para los dos caminos (cambia `texto_de_recordatorio` y el caso 16 de U5; al hacerlo, alinear también « Gracias.» con `DE_FABRICA`)~~ **Saldada** (2026-10-07, decisión de Luciano en el Gate 2 de U6): un solo formateador es-AR, `formatear_es_ar` en `payments/domain/dinero.py`. El texto de fábrica (`texto_de_recordatorio`) ahora dice «$ 1.234,50» —igual que el parámetro de la plantilla— y termina en « Gracias.» como `DE_FABRICA`; cubierto en `test_envio.py` y `test_dinero.py` | `plantillas-de-whatsapp-en-meta` (U6) |
| 22.53 | **Override del webhook por WABA** (ADR-0011, punto 5): que el campo `messages` —con sus `statuses[]`— admita override por cuenta, que con override los estados lleguen a `/webhooks/whatsapp/{empresa}` y que sin él lleguen a la URL de la app (`/webhooks/whatsapp`). El código rutea por WABA en las dos URLs, así que la respuesta cambia la configuración (pendiente #3 del épico 8), no el código. No hay app de prueba para comprobarlo | `entregas-de-whatsapp` (U7, tramo 1) |
| 22.54 | Con la app de prueba: que el `id` de `statuses[]` sea el mismo `wamid` que devolvió el envío (ver 22.35), que un `failed` traiga `errors[0].code` (22.38), la frecuencia real de duplicados y desorden de `statuses[]`, y si un mensaje de plantilla ya aceptado puede recibir `failed` horas después y con qué código. **Y qué hace Meta con un `failed` que llega después de un `read` o un `delivered` del mismo `wamid`**: el diseño (D-U7-2) lo acepta y lo deja terminal (`FALLIDO` es el rango más alto: el mensaje pasa de «leído» a «fallido»); si Meta no lo manda nunca, la regla es inofensiva, y si lo manda, hay que decidir si la pantalla debe mostrarlo. Si el `wamid` no coincidiera, **todos** los estados caerían en el log `whatsapp_estado_sin_destinatario` (a propósito en `warning`) y los mensajes quedarían `ENVIADO` | `entregas-de-whatsapp` (U7, tramo 1) |
| 22.55 | Los tests contra PostgreSQL del tramo 1 de `entregas-de-whatsapp` (`tests/integracion/test_migracion_0038.py`: columnas, índice único parcial de `recordatorio.externo_id`, sin backfill; `test_entregas_de_recordatorio_postgres.py`: callback por `wamid` y RLS —un `wamid` de otra empresa no existe—; los dos casos nuevos de `test_conversacional_postgres.py` y `test_entregas_concurrentes_postgres.py`: dos callbacks del mismo `wamid` con dos transacciones solapadas, sin pisarse —`LEIDO` no se pisa con `ENTREGADO`, `FALLIDO` no se pisa— y `recordatorio_fallido` publicado una sola vez, sobre el `SELECT ... FOR UPDATE` y la política `aislamiento_por_cobro`) se saltearon en local (sin Docker): confirmar que pasan en la CI del PR | `entregas-de-whatsapp` (U7, tramo 1) |
| 22.56 | Del `failed` solo se guarda el `code` de `errors[0]` (como `motivo_de_falla` / `ultimo_error`), no el `title`: es texto de un tercero. Si hace falta mostrar el título de Meta para los códigos que la pantalla no traduce (tramo 3), habría que guardarlo acotado en una columna nueva | `entregas-de-whatsapp` (U7) |
| 22.57 | **Un `failed`/`delivered` que llega antes del commit del barrido se pierde** (hallazgo H1 del Gate 2 del tramo 1 de `entregas-de-whatsapp`). `workers/tasks_payments.py:74` abre **una** `unidad_de_trabajo` por empresa y `payments/application/recordatorios.py:230-252` inserta, manda a Meta y marca el envío dentro de ella, así que todo se confirma recién al final del barrido: un callback que llega antes del commit no encuentra la fila (`recordatorio.externo_id` todavía no existe para otra transacción), se contesta 200 con `whatsapp_estado_sin_destinatario` y **ese estado no se reaplica**. **Resuelto en el tramo ii** (reintento acotado): cada recordatorio se confirma **antes** de la E/S a Meta y se actualiza después con su `wamid`; la ventana que queda (milisegundos entre la respuesta de Meta y el commit del `wamid`) está en §22.60. Es la parte de recordatorios del hallazgo G5/ADR-0015 (E/S a Meta con la transacción abierta); la de los avisos de turno quedó sin resolver en el tramo iii (§22.64) | `entregas-de-whatsapp` (U7, tramo ii) |
| 22.58 | **Un `wamid` ENTRANTE (de `messages[]`) de más de 160 caracteres desborda su columna `varchar`** → error de base → 500 → Meta reintenta. Es un camino previo, desde U5 (hallazgo del Gate 2 del tramo 1 de `entregas-de-whatsapp`, fuera de U7): los `wamid` salientes y los de `statuses[]` ya pasan por `shared/externo_id.py` (`externo_id_o_ninguno`), el entrante no. **Resuelto en `wamid-entrante-largo`:** `_traducir` descarta en el borde el `wamid` vacío o de más de `LARGO_MAXIMO_EXTERNO_ID` (la constante, no `externo_id_o_ninguno`: un `None` en el entrante sería un mensaje sin idempotencia), con un log de largo y motivo, y la notificación contesta 200 | `wamid-entrante-largo` |
| 22.59 | Los tests contra PostgreSQL del tramo 2 de `entregas-de-whatsapp` (`tests/integracion/test_migracion_0039.py`: columnas, índice parcial `ix_recordatorio_reintento`, `intentos >= 0`, sin backfill; `test_reintento_de_recordatorios_postgres.py`: la fila está confirmada y vista por otra transacción cuando el barrido llama a Meta, el reintento es un `UPDATE` de la misma fila, dos barridos solapados mandan una vez —`SELECT ... FOR UPDATE`— y un envío perdido se resuelve `INCIERTO`; los casos reescritos de `test_barrido_de_recordatorios_postgres.py`, y los del Gate 2: un error real de PostgreSQL al preparar dentro del savepoint de la reserva no aborta la transacción —`SELECT 1 / 0`—, `empresas_con_recordatorios_en_espera()` devuelve la empresa cuyo único cobro se cerró con un reintento esperando, y la función de `test_migracion_0039.py` es `SECURITY DEFINER` con `EXECUTE` solo para la app) se saltearon en local (sin Docker): confirmar que pasan en la CI del PR. Verificar también que `ConfirmacionDeLaUnidad` (commit y nuevo `set_config`) deja la sesión con RLS activa para la empresa tras cada confirmación | `entregas-de-whatsapp` (U7, tramo ii) |
| 22.60 | **Ventana residual de H1.** Aun con la fila confirmada antes de Meta, el `wamid` se guarda recién cuando Meta contesta: un callback que llegara en esos milisegundos no lo encontraría (`whatsapp_estado_sin_destinatario`) y se perdería. Medir con la app de prueba cuánto tarda el primer `statuses[]` tras la respuesta del envío; si fuera una pérdida real, la salida es mandar un dato de correlación a Meta antes de la llamada (`biz_opaque_callback_data` con el id de la fila) y rutear por él, descartado hasta ahora en D-U7-1. Los recordatorios que quedan «en curso» (caída o resultado no guardado) se resuelven `INCIERTO` sin `wamid` y **sus `delivered`/`failed` posteriores no pueden coincidir nunca con una fila**: ese es el argumento más fuerte para adoptar el dato de correlación (argumento de la revisión del Gate 2, 2026-10-07) | `entregas-de-whatsapp` (U7, tramo ii) |
| 22.61 | **Clasificación transitoria contra Meta.** Que los códigos que hoy el canal trata como saturación (5xx, 429, throttling) sean los que Meta resuelve esperando, y que ningún 4xx permanente se clasifique como `MensajeriaSaturada` (se reintentaría 3 veces en ≈ 3 h). También si conviene una espera mayor para 131049 («healthy ecosystem»: Meta frena el mensaje por un día). Se decide con los códigos reales de la app de prueba | `entregas-de-whatsapp` (U7, tramo ii) |
| 22.62 | Los tests contra PostgreSQL del tramo 3 de `entregas-de-whatsapp` (`tests/integracion/test_avisos_de_turno_postgres.py`: el aviso queda en una conversación `ACTIVA` del cliente y un segundo se agrega al mismo hilo; un rechazo de Meta deja el mensaje `FALLIDO` con su motivo; un `wamid` repetido —viola `uq_mensaje_externo_id`— se deshace en el savepoint real sin abortar la transacción de la operación y el resultado trae `sin_registrar`; el aviso de una empresa no existe para otra) se saltearon en local (sin Docker): confirmar que pasan en la CI del PR | `entregas-de-whatsapp` (U7, tramo iii) |
| 22.63 | **Verificación en el navegador, en staging de Render** (no se levanta la app en local): (a) PAN-COB-02 con un recordatorio esperando reintento («Reintentando · intento n de 3 · próximo hh:mm»), uno `FALLIDO` con cada motivo traducido y uno descartado; (b) el hilo de una conversación con un aviso de turno enviado, entregado, leído y fallido (estado en castellano y motivo); (c) cancelar un turno desde el panel con un cliente sin conversación y comprobar que aparece un hilo nuevo con el aviso como «Sistema». También confirmar con la app de prueba que el `wamid` de un aviso por **plantilla** coincide con el `id` de su `statuses[]` (ver 22.54). `lucide-react` faltaba solo en el entorno local: con `npm ci` la suite de frontend corre completa (`tsc` limpio, Vitest 98/98 archivos, 1233 pruebas), así que lo único pendiente de este ítem es la verificación en el navegador | `entregas-de-whatsapp` (U7, tramo iii) |
| 22.64 | **Un `delivered`/`failed` de un aviso de turno que llega antes del commit del request del panel se pierde** (misma clase que 22.57, parte de los avisos de turno del hallazgo G5/ADR-0015). `AvisoPorWhatsApp` manda por Meta **dentro** de la transacción de cancelar/reprogramar/reservar y el mensaje del sistema se confirma recién al final del request: un callback que llegara antes no encuentra el `wamid` (`whatsapp_estado_sin_destinatario`) y el aviso queda `ENVIADO` para siempre. La salida es mandar el aviso **después** del commit (o confirmar el mensaje antes de la E/S, como hace el barrido de recordatorios): cambia el orden de la operación del panel, así que necesita su propia unidad y una decisión sobre qué pasa si el commit del turno falla después de que el aviso salió. Medir con la app de prueba cuánto tarda el primer `statuses[]` tras la respuesta del envío: si es mayor que la duración de un request del panel, la pérdida es teórica | `entregas-de-whatsapp` (U7, tramo iii) |
| 22.65 | **Verificación en el navegador, en staging de Render** (no se levanta la app en local): la pantalla de plantillas de notificación (`PlantillasDeNotificacion.tsx`) con el diseño en tarjetas de `develop` y el comportamiento de `plantillas-de-whatsapp-en-meta` reaplicado encima al sincronizar la cadena con `develop` el 2026-10-09: estado en Meta en el pie de la tarjeta, «Editar texto» deshabilitado con su motivo, «Enviar a revisión», el aviso de variables y la advertencia de la ventana de 24 h. Lint, tipos y vitest pasan; la disposición visual no se vio en un navegador | pendiente |
| 22.66 | Costo de la verificación de sesión por solicitud en staging (pregunta 1 de `revocacion-inmediata-de-sesion`): 200 llamadas a `GET /auth/empresa` con la compute de Neon despierta, con y sin la verificación, y anotar el p95 agregado por solicitud en el plan. En la base local la verificación completa da p95 2,16 ms | `revocacion-inmediata-de-sesion` |
| 22.67 | **Validación legal de los textos (HU-E1-08 RN-07).** La asesoría legal debe revisar y completar la Política de Privacidad `1.0` y los Términos `1.1` (responsable, CUIT, domicilio, contacto, jurisdicción: hoy `[a completar]`). Ambos se publican con `borrador = true` y la franja «Versión preliminar, pendiente de validación legal.». **No se publica en producción con `borrador = true`**: el texto validado sale como versión **nueva** (los publicados no se editan, un test de hashes lo hace cumplir) y todos la vuelven a aceptar | `terminos-y-privacidad` (tramo 1) |
| 22.68 | **`/terminos` y `/privacidad` en staging (Render), sin sesión y desde otro navegador**: responden 200 con versión, fecha de vigencia («10/10/2026») y la franja de borrador; el HTML no tiene `<script>` ni marcado salido del texto; los enlaces del pie del ingreso (modo ingresar y modo registrarse), de la barra lateral del panel (se oculta con la barra reducida) y del aviso de la página del contador abren la página correcta en otra pestaña | `terminos-y-privacidad` (tramo 1) |
| 22.69 | **Las páginas legales «nunca dan error» (HU-E1-03 RN-05).** Con ISR de una hora (`revalidarCadaSegundos: 3600`): visitar `/privacidad`, apagar el backend de staging, esperar la revalidación (o forzarla) y comprobar que Next sigue sirviendo la última copia buena y no una página de error. Vigilar también el caso del primer pedido tras un despliegue con el backend caído: ahí no hay copia previa y la página falla. Si importara, la salida es `generateStaticParams` + build con el backend arriba, o copiar los textos al frontend (descartado en la pregunta 1 del plan) | `terminos-y-privacidad` (tramo 1) |

**Archivos de más de 400 líneas (CLAUDE.md §5), vistos en `limites-e-intervalo-de-turnos`.** Ya superaban el límite antes de esa unidad y no se partieron (decisión P4): `scheduling/application/turnos.py` (~520), `api/routers/agenda.py` (~685), `RecursosReservables.tsx` (~640) y `tests/contexts/scheduling/application/test_agenda.py` (~1180). **El router ya se partió** (`router-de-agenda-por-responsabilidad`). Siguen sin unidad: `turnos.py` (extraer `Avisador` a `application/avisador.py`; U8 modifica `turnos.py`, conviene esperar), `RecursosReservables.tsx` y `test_agenda.py`.

Hallazgos de `router-de-agenda-por-responsabilidad` (sin unidad, sólo reportados; la unidad no cambia comportamiento):

- **Las fábricas de rutas pasan de 50 líneas.** `rutas_de_recursos` (61), `_rutas_de_configuracion` (67), `_rutas_de_excepciones` (47), `rutas_de_turnos` (114) y `_rutas_de_gestion` (85): el patrón de cierres por fábrica es el de todos los routers y la unidad lo conserva (decisión D2). Achicarlas es otra decisión, que alcanza a todos los routers.
- **`_actor` y `_exigir` están duplicados en al menos ocho routers** (`bitacora.py`, `categorias.py`, `clientes.py`, `conversaciones.py`, …); en la agenda viven ahora en `agenda_forma.py` como `actor` y `exigir`. Unificarlos en un módulo compartido de `api/` es una unidad aparte.
- **`scheduling/application/turnos.py` (~520 líneas) sigue sobre el límite**: la extracción de `Avisador` queda para después de U8, que lo modifica (`Avisador.recordatorio`, `franja_asignada_en`).

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

## 25. Hallazgos de `revocacion-inmediata-de-sesion`

Todos quedan **sin unidad** (registrados el 2026-10-09): se vieron al planificar y no se arreglaron,
porque ninguno es de HU-E1-05 ni de HU-E1-06.

- ~~**`renovarSesion` borra las dos cookies ante cualquier 5xx de `/auth/refresh`.**~~ ✅ **Resuelto el
  2026-10-09** por `renovacion-sin-borrar-sesion` (commit `22ac0ff`): sólo un 4xx cierra la sesión; un 5xx,
  un timeout o una red caída conservan las dos cookies. Se conserva el texto original por el contexto.
  Estaba en
  `frontend/src/app/api/auth/_sesion.ts` (bloque `catch`) y su comentario lo declara a propósito.
  Una caída breve de la base que coincida con una renovación saca al usuario al ingreso, aunque su
  sesión siga viva. No lo introduce la unidad (`/auth/refresh` es pública y no pasa por el
  verificador por solicitud), y cambiarlo es una decisión de contrato del BFF. Se resuelve en un
  `fix/identity-…` aparte (decisión 7 de la unidad).
- **`SesionInvalida` responde 409 y no 401** en `/auth/refresh` y `/auth/login` (`api/errors.py` no
  la mapea). El BFF ya lo traduce (`status < 500` → 401 y borra cookies), por eso no se ve. Cambiarlo
  afecta al BFF y a sus tests: es una decisión de contrato. Los tests de la unidad aseveran «4xx con
  `error == "SesionInvalida"`» y no el número, para no fijarlo.
- **Cada navegación del panel cuesta dos lecturas a la base**, cada una con su conexión del pool: la
  verificación del middleware y la propia `GET /auth/empresa`. Sigue valiendo la propuesta de §4 de
  un endpoint de «contexto de sesión» que devuelva empresa + usuario + rol de una vez.

## 26. Hallazgos de `recordatorio-de-turno`

- **Prioridad negativa al actualizar una regla de atención o de escalamiento responde 500.**
  La revisión del slice 1 encontró que `ConfigurarHorarioDeAtencion` (`atencion.py:89`) y el caso
  de uso de escalamiento (`reglas.py:95`) asignan `regla.prioridad = prioridad` sobre una regla
  existente sin pasar por la validación de `ReglaDeNegocio.__post_init__`, que solo corre al
  crear. Un `PUT` con `prioridad: -1` sobre una regla ya guardada llega al `CHECK` de la base y
  devuelve 500 en vez de 422. El camino de alta ya responde 422. El arreglo es el mismo que se
  aplicó a la agenda: usar `ReglaDeNegocio.cambiar_prioridad` (que valida) antes de reconfigurar,
  con su prueba de caso de uso. Sin unidad: no se tocó en `recordatorio-de-turno` para no
  ensanchar el alcance.
- **Las empresas sin integración de WhatsApp siguen en el fan-out del barrido de recordatorios.**
  `empresas_con_turnos_por_recordar` devuelve toda empresa con un turno abierto por recordar, tenga o no
  WhatsApp conectado, así que cada 15 minutos se encola una tarea `scheduling.recordar_empresa` que arma
  el canal, ve `SinCanal` y sale con `recordatorios_de_turno_sin_canal` (D-U8-13). No crea filas ni
  hilos, pero ocupa un worker y una conexión por empresa y corrida. Trabajo futuro, a elegir: excluirlas
  en la propia función `SECURITY DEFINER` (unir con la integración `WHATSAPP` conectada), o correr la
  pasada 1 en modo «solo resolver» (sin llamar a Meta) para esas empresas. Sin unidad: fuera del alcance
  del Gate 2 del tramo 3.
- **Las filas de recordatorio quedan sin resolver (en curso) mientras la empresa no tiene canal de
  WhatsApp o su agenda está mal formada.** La pasada 1 del barrido (la que resuelve ventanas vencidas
  como `INCIERTO` y retoma reintentos) no corre cuando no hay canal (`SinCanal`, D-U8-13) ni cuando la
  agenda es inválida (`recordatorios_de_turno_agenda_invalida`): el barrido sale antes. Una fila «en
  curso» o con reintento pendiente de esa empresa queda tal cual hasta que el canal o la agenda se
  arreglen. No se manda nada de más (es seguro), pero el estado queda desactualizado. Trabajo futuro:
  correr la pasada 1 en modo «solo resolver» (sin llamar a Meta) también en esos casos. Sin unidad.

## 27. Hallazgos de `terminos-y-privacidad`

Registrados el 2026-10-10; ninguno se arregla en esta unidad (CLAUDE.md §8).

- **`api/routers/auth.py` tiene 526 líneas** (límite 400, CLAUDE.md §5; ningún hook lo hace cumplir). La
  unidad lo toca en tres rutas (tramos 2 y 3), por eso lo nuevo vive en `api/routers/legal.py`. Partirlo
  (invitación y Google a su propio módulo) es un refactor con riesgo propio y merece su PR.
- **El enlace «¿Olvidaste tu contraseña?» (`FormularioDeIngreso.tsx`) apunta a `/recuperar`, que no tiene
  ruta** y responde 404, igual que `/terminos` hasta este tramo. Es de otra historia.

## 28. Hallazgos de la prueba con ARCA real (homologación)

Registrados el 2026-10-10, emitiendo desde el panel local contra ARCA homologación con el certificado
de plataforma (ADR-0014). Los que impedían obtener un CAE se arreglaron en
`fix/integrations-arca-real-en-homologacion` y `fix/billing-condicion-iva-del-receptor`; estos quedan
afuera (CLAUDE.md §8).

- **La sesión vence aunque el panel esté abierto.** `RenovadorDeSesion` renueva cada 10 minutos
  contados desde que se monta la página, no desde que se emitió el token de 15 minutos: una recarga a
  los 12 minutos de iniciar sesión deja vencer el token antes de la renovación siguiente, y la acción
  siguiente responde «Tu sesión venció». Arreglo probable: renovar según el vencimiento real del token
  (o al recibir un 401, y reintentar una vez).
- **`/api/auth/renovar` devuelve al inicio y no a la página pedida.** Al recargar
  `/facturacion/nueva?cliente=…` sin token de acceso, la renovación terminó en `/panel`. Revisar si el
  layout pasa la ruta y la query a `destinoSeguro()`.
- **Test inestable: `test_webhook_estados_robustez.py::test_un_payload_solo_de_estados_no_loguea_mensajes_en_la_url_de_la_app`.**
  Pasa solo y en `develop`; dentro de la suite completa falla a veces, según el orden. Probablemente
  estado de logging compartido entre tests.
- **El certificado de plataforma vence el 07/10/2028 y nada avisa.** El aviso de vencimiento era por
  empresa y se fue con el modelo 1. Hace falta un aviso a la plataforma (no a las empresas).
- **`billing/domain/comprobante.py` tiene 485 líneas** (límite 400, CLAUDE.md §5).
- **La Factura C (emisor Monotributo o Exento) no se probó contra ARCA real**: solo la A. La C no lleva
  `<Iva>`; conviene emitir una en homologación antes de abrir staging a empresas monotributistas.
- **La CUIT ficticia `30000000015` es compartida en homologación**: ARCA ya tenía Facturas A 1 y 2 de
  otro usuario. CheatSheet sincronizó y emitió la 3 (D18), así que no rompe nada, pero los números de
  staging no arrancan en 1.
