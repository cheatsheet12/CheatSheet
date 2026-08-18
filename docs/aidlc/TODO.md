# TODO — lo que falta para cerrar el épico 1

> Estado al **2026-08-18**. Todo lo que está acá **bloquea el cierre del épico o queda declarado
> como deuda con dueño**. Lo que ya está hecho no se lista: para eso está el registro de cada
> unidad en [`units/`](units/).
>
> Las tres unidades del épico están implementadas y verificadas en verde. Lo que queda es
> **configuración que no puedo tocar yo**, **integraciones que hoy corren simuladas**, y los dos
> gates finales.

---

## 1. Bloqueantes — sin esto el épico no cierra

### 1.1 Variables de entorno · **te toca a vos**

Los dos `.env.example` están **denegados por permisos en mi entorno**: no puedo leerlos ni
escribirlos. La Definition of Done (`CLAUDE.md` §7) pide que estén actualizados cuando se agrega
una integración, así que esto queda pendiente hasta que las pegues a mano.

**`backend/.env.example`** — las de las unidades 2 y 3:

```bash
# Sesiones (ADR-011)
JWT_SECRET=                      # obligatoria; el proceso no arranca sin ella
JWT_ACCESS_TTL_MINUTOS=15
REFRESH_TTL_DIAS=30
TERMINOS_VERSION_VIGENTE=1.0

# OAuth2 de Google (HU-E1-01 RN-02). Vacías fuera de produccion: se usa el simulado.
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REDIRECT_URI=

# Invitaciones (HU-E1-04)
APP_BASE_URL=http://localhost:3000
INVITACION_TTL_DIAS=7
EMAIL_ADAPTADOR=consola          # 'smtp' en produccion; 'consola' es rechazado ahi
SMTP_HOST=
SMTP_PORT=587
SMTP_USUARIO=
SMTP_PASSWORD=
SMTP_REMITENTE=CheatSheet <no-reply@localhost>
SMTP_TLS=true
SMTP_TIMEOUT_SEGUNDOS=10
```

**`frontend/.env.example`**:

```bash
APP_BASE_URL=http://localhost:3000   # a donde vuelve el callback de Google
```

Ninguna lleva un valor real. `EMAIL_ADAPTADOR` y `GOOGLE_OAUTH_*` tienen validación en
`platform/settings.py`: en `production` el proceso **no arranca** con el adaptador de consola, y el
proveedor OAuth simulado **lanza al construirse**.

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
