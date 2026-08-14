# Unidad: identidad-y-onboarding

**HUs**: HU-E1-01, HU-E1-02, HU-E1-03   **Contexto dueño**: identity
**Rama**: `feature/identity-cimientos-identidad-y-bitacora` — compartida por las tres unidades del
épico (ver `units.md` § Notas).

## Qué hace

Un visitante se registra con email y contraseña o con su cuenta de Google, acepta los términos,
carga los datos fiscales de su empresa y entra al panel. Desde ese momento existe una `Empresa` con
su `empresa_id`, existe un `Usuario` Administrador con sesión, y **cada una de esas operaciones
queda en la bitácora** que dejó la unidad anterior — que es la primera vez que el mecanismo de
HS-T5 se usa de verdad, y no contra un test.

Al terminar, el `EmpresaMiddleware` deja de leer un header de desarrollo y pasa a leer el JWT.

## El conflicto estructural que hay que resolver antes de codear

**HU-E1-01 crea la cuenta en el paso 1; el DER no admite una `Empresa` sin CUIT.**

- `usuario.empresa_id` es `NOT NULL`: no hay usuario sin empresa.
- `empresa.cuit` es `NOT NULL` **y único**: no hay empresa sin CUIT.
- Pero HU-E1-01 dice «el sistema crea la cuenta y me redirige al paso 2», y el CUIT recién se pide
  en el paso 2 (HU-E1-02).

O sea que el modelo, tal como está, **no permite que exista el estado intermedio que la historia
describe**. Es un conflicto entre dos insumos de Etapa 5, no un detalle de implementación, y no lo
resuelvo solo: las tres opciones están al final, en «Decisiones pendientes».

El resto del plan asume la **opción A** (columnas fiscales nullable hasta completar el onboarding).
Si elegís otra, cambian la migración y el agregado `Empresa`, no el resto.

## Diseño

### Dominio (`contexts/identity/domain/`)

- **`Empresa`** — agregado raíz. Datos del DER más los dos que HU-E1-02 RN-03 exige y el DER no
  tiene (hueco H7). Comportamiento real, no un contenedor de campos:
  - `completar_datos_fiscales(...)` — el paso 2. Es lo que hace verdadero `onboarding_completo`.
  - `aceptar_terminos(version, momento)` — registra versión y fecha (HU-E1-03 RN-01).
  - `debe_reaceptar_terminos(version_vigente)` — HU-E1-03 RN-03: si la versión cambió, el próximo
    ingreso vuelve a pedir aceptación.
  - `onboarding_completo` — propiedad derivada, no columna: es «tiene datos fiscales y términos
    aceptados». Un booleano guardado sería un segundo lugar donde la verdad puede desincronizarse.
- **`Usuario`** — agregado raíz: `empresa_id`, `email`, `nombre` (H1), `rol`, `activo`,
  `hash_de_contrasena` (H1, opcional: un usuario de Google no tiene), preferencias.
- **`CUIT`** — value object con **validación de dígito verificador** (D1: estructural en este
  épico, contra el padrón de ARCA en el 2). Es el único lugar del sistema que sabe cómo se valida
  un CUIT; `cliente.cuit` y `comprobante.receptor_cuit` lo van a reusar.
- **`Email`** — value object normalizado a minúsculas. La unicidad se compara sobre el normalizado,
  o `Ana@x.com` y `ana@x.com` son dos cuentas (HU-E1-01 RN-03).
- **`CondicionIVA`**, **`RolUsuario`** — enums del DER, textuales.
- **`TerminosAceptados`** — value object: versión + fecha, siempre juntos. Una fecha sin versión no
  prueba nada de lo que HU-E1-03 RN-01 quiere probar.
- **`HashDeContrasena`** — value object que envuelve el hash. Su `__str__` y su `__repr__`
  devuelven `***`: un hash de Argon2id en un log o en un traceback es material para un ataque
  offline, y esa es exactamente la clase de fuga que se cuela por un `logger.debug(usuario)`.

### Aplicación (`contexts/identity/application/`)

Un servicio por caso de uso:

| Caso de uso | Entrada | Qué garantiza |
|---|---|---|
| `RegistrarEmpresa` | email, contraseña, versión de términos | Crea `Empresa` + `Usuario` Administrador en **una** transacción y publica el evento auditable. Rechaza email repetido |
| `RegistrarConGoogle` | código de autorización OAuth2 | Igual, pero sin contraseña; toma email y nombre del perfil (HU-E1-01 RN-02: nada más) |
| `IniciarSesion` | email, contraseña | Devuelve el par de tokens y **a qué paso corresponde redirigir** |
| `CompletarDatosDeEmpresa` | datos fiscales | El paso 2. Valida CUIT y unicidad |
| `AceptarTerminos` | versión | Para la re-aceptación de RN-03 |
| `RefrescarSesion` | refresh token | Rota el token y **detecta reuso** (ADR-011) |
| `CerrarSesion` | refresh token | Revoca la familia de tokens |

`ports.py`: `PortRepositorioEmpresa`, `PortRepositorioUsuario`, `PortRepositorioRefreshToken`,
`PortHashDeContrasena`, `PortProveedorOAuth`, `PortEmisorDeTokens`.

### Puertos y adaptadores

| Puerto | Adaptador | Nota |
|---|---|---|
| `PortHashDeContrasena` | Argon2id (`argon2-cffi`) | ADR-011. Parámetros explícitos, no los del default |
| `PortProveedorOAuth` | Google OAuth2 | Credenciales **de la plataforma**, por variable de entorno |
| `PortEmisorDeTokens` | JWT corto (`PyJWT`) + refresh opaco | El refresh no es un JWT: tiene que poder revocarse |
| `PortRepositorio*` | PostgreSQL (SQLAlchemy async) | |

### Autenticación — cómo queda

- **Access token**: JWT de 15 minutos con `empresa_id`, `usuario_id` y `rol`. Va en la cookie
  HttpOnly que el cascarón del frontend ya sabe manejar.
- **Refresh token**: opaco y rotativo, guardado **hasheado** (si la base se filtra, los tokens no
  sirven). Cada uso lo revoca y emite otro.
- **Detección de reuso**: un refresh ya usado que vuelve a presentarse significa que alguien lo
  robó. La reacción es revocar **toda la familia**, no solo ese token — si no, el atacante y la
  víctima se turnan para rotar y nadie se entera.

### Otros contextos

Solo `identity → observability`, publicando `EventoAuditable`. Es la arista OHS que el Context Map
ya permite y que la unidad anterior dejó implementada: **ningún import cruzado**, R3 intacto. No
hace falta ADR.

### Frontend (`frontend/src/features/identity/`)

- `PAN-ONB-01` — registro, login, botón de Google y el checkbox de términos con enlace al texto
  (HU-E1-03 RN-04).
- `PAN-ONB-02` — datos fiscales, con el CUIT validado en vivo y `CondicionIVA` elegida a mano.
- Route handlers del BFF: `/api/auth/registro`, `/api/auth/login`, `/api/auth/google/callback`,
  `/api/auth/refresh`, `/api/auth/logout`. Son los que setean y borran la cookie; el token nunca
  toca el bundle del cliente.
- El layout `(panel)` deja de mirar solo si la cookie existe y pasa a exigir onboarding completo.

## Infraestructura

### Migración 0002

Tablas `empresa`, `usuario` y `refresh_token`, las tres con RLS por `empresa_id` salvo `empresa`,
que se aísla por su propio `id`. Además:

- **La FK que la migración 0001 dejó anotada**: `registro_de_auditoria.usuario_id → usuario.id`. No
  se pudo crear antes porque la tabla no existía; se crea acá.
- Índice único sobre `usuario.email` **por empresa** (HU-E1-04 RN-03) y único global sobre
  `empresa.cuit` (DER).
- `empresa` es la tabla del tenant: su política compara `id`, no `empresa_id`.

Reversible. Sin backfill: no hay datos.

### Configuración

Variables nuevas en `backend/.env.example`: `JWT_SECRET`, `JWT_ACCESS_TTL_MINUTOS`,
`REFRESH_TTL_DIAS`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`,
`GOOGLE_OAUTH_REDIRECT_URI`, `TERMINOS_VERSION_VIGENTE`. Ninguna con valor.

> ⚠️ Los `.env.example` **siguen sin poder editarse** desde este entorno (acceso denegado). Las
> variables quedan listadas acá y hay que agregarlas a mano, igual que las de la unidad anterior.

### Integraciones externas

**Google OAuth2** — la primera integración real del sistema. Timeout explícito, reintento con
backoff, manejo de falla y `state` firmado contra CSRF. **Los tests no la tocan**: se usa un doble
del puerto, como manda `backend/tests/README.md`.

Las credenciales son **de la plataforma**, no de cada empresa, así que **no** van en
`configuracion_de_integracion` ni agregan un valor al enum `sistema_externo` (hueco H8).

### Dependencias que se agregan

`argon2-cffi`, `pyjwt`, `httpx` (pasa de dev a runtime: la usa el adaptador de Google).

## Huecos del DER que esta unidad declara

| # | Hueco | Cómo se cubre |
|---|---|---|
| H1 | `usuario` sin `hash_de_contrasena` ni `nombre` | Se agregan. HU-E1-01 RN-01 y PAN-USR-01 los exigen |
| H3 | No hay tabla de refresh tokens | Se crea `refresh_token`. ADR-011 la exige |
| H7 | `empresa` sin `nombre_responsable` ni `email_contacto`, que HU-E1-02 RN-03 declara obligatorios. Además la historia dice «nombre comercial» y el DER dice `razon_social` | Se agregan las dos columnas. `razon_social` se usa como el nombre comercial: no hay evidencia de que el negocio distinga los dos |
| H8 | El enum `sistema_externo` no contempla OAuth de Google | No se toca: las credenciales son de plataforma, no de empresa |

Los cuatro quedan anotados para que el DER se actualice cuando quieras. **Ninguno se agregó en
silencio.**

## Riesgos que obligan a tests

- [ ] Toca dinero → no aplica
- [ ] Comprobantes fiscales / CAE → no aplica
- [ ] Webhook → no aplica
- [x] **Agrega datos con `empresa_id`** → test de aislamiento para `usuario` y `refresh_token`
- [ ] Salida de un LLM → no aplica
- [x] **Datos personales** → email y nombre. Nunca a un LLM; nunca en un log

Riesgos propios, que la plantilla no lista:

- [x] **La contraseña nunca se guarda ni se loguea en claro.** Test de que el hash no es reversible
      y de que `repr(usuario)` no filtra nada.
- [x] **Un CUIT con dígito verificador inválido no entra.** Test con casos reales de borde.
- [x] **Reuso de refresh token** → revoca la familia entera.
- [x] **El invariante del onboarding bloqueante** (HU-E1-02 RN-04): sin datos fiscales no se llega
      al panel, ni por la API ni por la ruta del frontend.

## Casos de prueba

| # | Caso | Tipo |
|---|---|---|
| 1 | Un email ya registrado es rechazado, sin revelar si existe en otra empresa | unit |
| 2 | `Ana@x.com` y `ana@x.com` son el mismo email | unit |
| 3 | Contraseña de menos de 8 caracteres es rechazada (RN-01) | unit |
| 4 | El hash de Argon2id no es reversible y no aparece en `repr` ni en logs | unit |
| 5 | CUIT con dígito verificador inválido es rechazado | unit |
| 6 | CUIT válido con y sin guiones se normaliza igual | unit |
| 7 | Aceptar términos guarda versión **y** fecha | unit |
| 8 | Si la versión vigente cambió, se pide re-aceptación (RN-03) | unit |
| 9 | Registrarse crea `Empresa` + `Usuario` Administrador en una transacción | integración |
| 10 | Si falla la creación del usuario, no queda una empresa huérfana | integración |
| 11 | Sin datos fiscales, la API no deja pasar al panel (RN-04) | integración |
| 12 | Login correcto devuelve access + refresh y redirige al paso pendiente | integración |
| 13 | Un refresh usado dos veces revoca toda la familia | integración |
| 14 | El refresh se guarda hasheado, no en claro | integración |
| 15 | El registro deja su fila en la bitácora, con `usuario_id` cargado | integración |
| 16 | Una empresa no ve los usuarios de otra (RLS) | integración |
| 17 | El adaptador de Google se usa mockeado; ningún test toca la red | contrato |
| 18 | La FK `registro_de_auditoria.usuario_id → usuario.id` existe tras 0002 | integración |
| 19 | PAN-ONB-01 bloquea el submit sin aceptar términos | unit (vitest) |
| 20 | El BFF nunca devuelve el token al cliente | unit (vitest) |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-13 | aprobado — opción A para el conflicto estructural |
| 1b · Prototipos | 2026-08-14 | los prototipos y la paleta se importaron **después** de aprobar el plan; la unidad se ajustó a ellos antes de escribir las pantallas |
| 2 · Verificación | 2026-08-14 | todos los gates en verde — ver abajo |
| 3 · PR | | al final del épico, junto con las otras dos unidades |

### Gate 2 — resultado real

```
ruff format --check .   136 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 131 source files
pytest --cov            140 passed · cobertura 84.24%
guard_architecture      144 files checked — boundaries intact
test_guards.sh          54 cases, all correct

frontend format:check   All matched files use Prettier code style!
frontend lint           No ESLint warnings or errors
frontend typecheck      sin errores
frontend test:coverage  99 passed · 89.01% líneas / 90.86% ramas
```

La comprobación que CI hace del R5 —crear un import cruzado entre features y verificar que
lint lo rechace— se corrió a mano y **sigue disparando**.

### Ajustes por los prototipos (2026-08-14)

Los prototipos llegaron con el plan ya aprobado y el backend ya escrito. Lo que cambiaron:

- **El sistema de diseño que había era inventado y se descartó entero.** `tokens.css` se
  reescribió con los valores del PDF y los componentes se rehicieron contra el catálogo del §1.3.
- **Decisión: ante la discrepancia entre el PDF y `styles.css`, gana el PDF** (8 valores, huecos
  P1–P8 de `prototipos.md`). Consecuencia asumida: el panel **no** se ve igual que el prototipo
  HTML, y las capturas de entrega quedan desactualizadas.
- **DM Sans y JetBrains Mono vía `next/font`**, que las auto-hospeda en el build. Sin request a
  Google en runtime. El build necesita red una vez; CI no corre `next build`, así que solo afecta
  a un deploy.
- **Dos diferencias deliberadas respecto del prototipo en PAN-ONB-02**, ambas trazables a
  decisiones previas: no hay autocompletado desde ARCA (D1 lo mandó al épico 2, y el mensaje de
  éxito dice lo que es cierto en vez de «datos verificados contra ARCA»), y se piden **nombre del
  responsable y email de contacto**, que HU-E1-02 RN-03 exige y el prototipo no muestra (hueco H7).
- **El checkbox de términos aparece solo al registrarse.** Las anotaciones lo listan entre los
  campos obligatorios de la pantalla, pero HU-E1-03 RN-02 lo ata a *completar el registro*: pedir
  re-aceptar el contrato en cada ingreso sería ruido.

### Falso positivo del R5 encontrado y resuelto sin tocar la regla

La regla de ESLint que implementa R5 no distingue «los internos de **otra** feature» —lo único que
R5 prohíbe— de «mis propios internos», que R5 permite explícitamente. Disparaba sobre el barril de
la propia feature, que por definición tiene que importar lo que exporta.

Se resolvió **sin debilitar la regla**: dentro de una feature los imports son relativos
(`./components/…`), y el alias `@/features/<name>/…` queda significando una sola cosa —alguien
metiendo mano desde afuera—, que es exactamente lo que debe fallar.

## Decisiones pendientes — bloquean el inicio

**¿Cómo existe una cuenta entre el paso 1 y el paso 2?** (ver arriba)

- **Opción A — columnas fiscales nullable hasta completar el onboarding.** `empresa.razon_social`,
  `cuit` y `condicion_iva` pasan a nullable; `onboarding_completo` se deriva de que estén cargadas.
  La cuenta existe desde el paso 1, como dice la historia, y el usuario puede volver mañana a
  terminar. **Cuesta:** tres `NOT NULL` menos que el DER, y que toda lectura de `empresa.cuit`
  tenga que contemplar el nulo.
- **Opción B — nada se persiste hasta el paso 2.** El DER queda intacto. Lo del paso 1 vive en un
  registro efímero. **Cuesta:** «el sistema crea la cuenta» del criterio de aceptación deja de ser
  cierto, y quien abandona en el paso 2 pierde todo y vuelve a empezar.
- **Opción C — empresa provisoria con CUIT placeholder.** No la recomiendo y la dejo escrita para
  que quede descartada por escrito: `cuit` es único, así que habría que inventar un valor único por
  registro, y un CUIT falso en una tabla fiscal es exactamente la clase de dato que después alguien
  factura.

## Decisiones tomadas durante la unidad

- **Conflicto estructural → opción A**: `razon_social`, `cuit` y `condicion_iva` son nullable hasta
  completar el onboarding. La cuenta existe desde el paso 1, como dice HU-E1-01.
- **Sign-up y sign-in ocurren antes de que exista empresa**, y RLS no puede expresarlo. En vez de
  `BYPASSRLS` —apagar la barrera en todos lados para resolver dos consultas— la migración 0002
  agrega dos funciones `SECURITY DEFINER` acotadas: `buscar_usuario_para_login` devuelve un usuario
  por email, `existe_cuit_registrado` devuelve un booleano.
- **El email es único en toda la plataforma, no por empresa.** El login es solo por email, así que
  dos usuarios compartiéndolo harían la autenticación ambigua.
- **Ante la discrepancia PDF vs `styles.css`, gana el PDF** (ver arriba).
- **DM Sans y JetBrains Mono con `next/font`**, auto-hospedadas.
