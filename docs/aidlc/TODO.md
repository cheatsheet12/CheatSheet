# TODO — lo que falta para cerrar los épicos abiertos

> Estado al **2026-08-19**. Arranca siendo el TODO del épico 1; el épico 2 agrega su propia
> sección al final, con la misma regla.
>
> Todo lo que está acá **bloquea el cierre de un épico o queda declarado como deuda con dueño**.
> Lo que ya está hecho no se lista: para eso está el registro de cada unidad en [`units/`](units/).

---

# Épico 1 — Cimientos, identidad y bitácora

> Estado al **2026-08-18**. Las tres unidades están implementadas y verificadas en verde. Lo que
> queda es **configuración que no puedo tocar yo**, **integraciones que hoy corren simuladas**, y
> los dos gates finales.

## 1. Bloqueantes — sin esto el épico no cierra

### 1.1 Variables de entorno · ~~te toca a vos~~ **resuelto el 2026-08-18**

Decía que los dos `.env.example` estaban denegados por permisos y que había que pegarlos a mano. Ya
no: la unidad `mecanismo-de-integraciones` encontró la causa —una regla `Read(./.env.*)` demasiado
ancha, que atrapaba las plantillas versionadas junto con los archivos reales— y la corrigió por
enumeración. Los dos templates quedaron **reconciliados con lo que el código realmente lee**, y hay
una verificación que compara ambas listas.

Se deja escrito en lugar de borrarlo porque el épico 1 **se entregó con este punto de la Definition
of Done incumplido**, y eso es parte de su historia.

### 1.2 Los dos gates que faltan

| Gate | Qué falta |
|---|---|
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
| **CUIT no se valida contra el padrón de ARCA** | Decisión D1: la credencial fiscal recién existe en el épico 2. Hoy se valida formato y dígito verificador. Un CUIT bien formado pero inexistente entra al sistema | **Épico 2**, cuando HU-E2-01 deje la credencial cargada |
| **`CondicionIVA` se elige a mano** | Mismo motivo: el criterio de aceptación 1 de HU-E1-02 pide autocompletarla desde el padrón | **Épico 2** |
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

### 5.3 MercadoPago

Todavía no: su unidad no está hecha. Necesita una aplicación en modo sandbox.

## 6. Deuda declarada del épico 2

| Qué | Por qué queda afuera | Dueño |
|---|---|---|
| **Embedded Signup de Meta** reemplaza el formulario manual de tres campos | Exige una app de Meta **aprobada**, que no existe. El popup del SDK de Facebook es mucho mejor UX, pero no se puede construir ni demostrar hoy (decisión D-f) | Se cambia `FormularioDeWhatsApp.tsx` y `whatsapp/conector.py`, nada más |
| **El webhook de cambio de estado del número** | Es de plataforma: necesita endpoint público, validación de firma con `WHATSAPP_APP_SECRET` y app de Meta. Su endpoint es del épico 8 (decisión D-d) | Épico 8. El sondeo pasa a ser la red de seguridad |
| **La calidad de la línea sólo se ve cuando es `RED`** | Se registra siempre (RN-03) pero la pantalla la muestra únicamente como detalle del estado Atención. Mostrar `GREEN`/`YELLOW` en la tarjeta es diseño que el mockup no tiene | Cuando haya un mockup |
| **Un certificado de ARCA revocado antes de vencer no se detecta hasta la próxima renovación de ticket** | La verificación en vivo lee el `notAfter` local y no llama a WSAA, a propósito: llamar quemaría el ticket de 12 h en cada refresco de pantalla y chocaría con la regla del proveedor (decisión D-e) | Aparece igual, en el primer momento en que importa: cuando hay que emitir |
| **PyAfipWs sigue sin instalarse** | WSAA no lo necesita (ADR-0004). WSFEv1 es otra historia y es decisión del épico 5, donde ADR-012 sigue vigente | Épico 5 |

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

- **`empresas_con_integracion_de_arca()` es la segunda y última función `SECURITY DEFINER` de
  `integrations`.** Como la primera, devuelve `empresa_id` y nada más. Son las dos únicas lecturas
  entre empresas del sistema y merecen una mirada en cualquier revisión de seguridad.
- **Los tickets de acceso también dependen de `SECRETS_ENCRYPTION_KEY`.** Rotar esa clave ahora
  implica dos tablas, no una — aunque con los tickets alcanza con borrarlos: se vuelven a emitir
  solos cuando expiren.
- **La firma CMS es nuestra.** Son unas cuarenta líneas y están cubiertas por tests que verifican
  el DER de verdad, pero es código propio donde antes se esperaba una librería.
