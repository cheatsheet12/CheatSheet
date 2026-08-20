# Unidad: conexion-mercadopago

**HUs**: HU-E2-02   **Contexto dueño**: `integrations`   **Rama**: `feature/integrations-conexion-mercadopago`

> La última unidad del épico 2. Cierra la única tarjeta de PAN-CFG-INT que todavía habla con
> `ConectorSimulado`, y con eso `infrastructure/simulados.py` deja de tener clientes reales.

## Qué hace

El Administrador aprieta «Conectar» en la tarjeta de MercadoPago y el navegador se va a MercadoPago
a autorizar. Vuelve al panel con un código, el sistema lo canjea por el par de tokens, **lee los
datos de la cuenta antes de dar nada por bueno** (RN-02) y recién ahí marca la integración como
Conectada, con el apodo de la cuenta en la tarjeta.

Los dos tokens quedan cifrados con el mismo AES-256-GCM que el resto (RN-01). Un barrido diario los
renueva antes de que venzan; si MercadoPago los rechaza —revocados desde su panel, o vencidos sin
que hubiera con qué renovarlos— la integración pasa a inactiva y el Administrador se entera por
email (RN-03).

## Diseño

### Dominio

**Ningún agregado nuevo y ningún estado nuevo.** `SistemaExterno.MERCADOPAGO` existe desde
`mecanismo-de-integraciones`, `ConfiguracionDeIntegracion` ya guarda credencial, ambiente, estado y
parámetros, y `EstadoDeConexion` no gana un quinto valor: MercadoPago contesta sincrónico, así que
usa `CONECTADO`, `ATENCION` y `NO_CONECTADO` tal como están.

Lo único que se agrega en `domain/valores.py` es **una clave de parámetro**:

```python
#: `credencial_vence_en`: cuándo deja de servir la credencial guardada, en ISO-8601 UTC.
CLAVE_VENCIMIENTO = "credencial_vence_en"
```

Va al dominio y no al `mapeo.py` del proveedor —a diferencia de `phone_number_id` o `user_id`—
porque **la capa de aplicación la lee**: el barrido de renovación decide con ella si hay que llamar
a MercadoPago, y un caso de uso que leyera una clave declarada dentro de `infrastructure/` estaría
importando hacia adentro (R2). Es el mismo criterio por el que `CLAVE_CUIT` subió al dominio en la
unidad anterior.

### Aplicación

Tres casos de uso nuevos. Los dos primeros son el flujo OAuth2 partido en sus dos mitades, que es
como el protocolo está hecho: entre una y otra el usuario se va del sistema.

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `IniciarAutorizacion` | `empresa_id`, `rol`, `sistema` | `AutorizacionIniciada(url, expira_en)` | Sólo Administrador. Genera `state` y `code_verifier` (PKCE S256), los guarda con TTL y devuelve la URL a la que mandar el navegador |
| `CompletarAutorizacion` | `empresa_id`, `rol`, `sistema`, `codigo`, `estado` | `VistaDeIntegracion` | **Consume el `state` una sola vez** y verifica que sea de esta empresa; después delega en `ConectarIntegracion`, que no cambia |
| `RenovarCredenciales` | `empresa_id` | `list[Desenlace]` | Renueva lo que esté por vencer y reporta sólo lo que cambió de estado |

**`ConectarIntegracion` no se toca.** El canje del código encaja en `MaterialDeConexion` sin
forzarlo: `contenido` son los bytes del código de autorización y `parametros` llevan el
`code_verifier` y la `redirect_uri` que MercadoPago exige repetir. El adaptador devuelve un
`ResultadoDeConexion` con la credencial a persistir —que **no** es lo que entró, exactamente el caso
que su docstring anticipaba— y con los parámetros que el proveedor informó de sí mismo.

**El `state` se valida en `application/` y no en el router.** Es una regla de negocio disfrazada de
detalle de protocolo: sin ella, cualquiera que consiga que un Administrador abra un link puede
enganchar *su* cuenta de MercadoPago a la empresa de otro, y a partir de ahí todos los cobros del
épico 6 caen en la cuenta equivocada. Un chequeo así no vive en el borde HTTP.

### Puertos y adaptadores

Tres puertos nuevos en `application/ports.py`, y ninguno menciona a MercadoPago:

```python
@dataclass(frozen=True, slots=True)
class PedidoDeAutorizacion:
    estado: str
    desafio: str          # code_challenge S256 — el verificador nunca sale de acá

class PortAutorizacionOAuth(Protocol):
    def url_de_autorizacion(self, pedido: PedidoDeAutorizacion) -> str: ...

@dataclass(frozen=True, slots=True)
class AutorizacionPendiente:
    empresa_id: EmpresaId
    sistema: SistemaExterno
    verificador: str

class PortMemoriaDeAutorizacion(Protocol):
    """Dónde vive el `state` entre que el navegador se va y vuelve."""
    async def guardar(self, estado: str, pendiente: AutorizacionPendiente, ttl: int) -> None: ...
    async def consumir(self, estado: str) -> AutorizacionPendiente | None: ...

class PortRenovacionDeCredencial(Protocol):
    async def renovar(self, credencial: bytes) -> ResultadoDeConexion: ...
```

`ParDeAdaptadores` gana dos ranuras opcionales más —`autorizacion` y `renovador`—, igual que ganó
`emisor` y `padron` para ARCA. Ningún sistema las usa todas: ARCA tiene emisor y padrón, MercadoPago
tiene autorización y renovador, WhatsApp no tiene ninguna.

Adaptadores, todos en `infrastructure/mercadopago/`:

| Archivo | Qué es |
|---|---|
| `cliente.py` | El HTTP contra MercadoPago: canje, renovación y `/users/me`. Timeout, 3 intentos con backoff, transporte inyectable — mismo molde que `whatsapp/cliente.py` |
| `mapeo.py` | El ACL: traduce la respuesta del proveedor a `ResultadoDeConexion`, empaqueta y desempaqueta el par de tokens, y decide qué error de MercadoPago es cuál de los nuestros |
| `conector.py` | `PortConectorDeIntegracion` + `PortRenovacionDeCredencial` |
| `autorizacion.py` | `PortAutorizacionOAuth`: arma la URL. Sin red |
| `simulado.py` | El de MercadoPago, con su propio flujo de dos pasos. Reemplaza a `ConectorSimulado`/`VerificadorSimulado` para este sistema |
| `verificador.py` | `PortVerificadorDeConexion`: un `GET /users/me`, que es lo que contesta si el token sigue vivo |

Y `infrastructure/autorizaciones.py`, fuera de la carpeta del proveedor porque no es de ningún
proveedor: `MemoriaDeAutorizacionRedis` sobre el Redis que `Recursos` ya tiene, con `SET NX EX` para
guardar y `GETDEL` para consumir —una sola operación, que es lo que hace que un `state` no pueda
usarse dos veces ni siquiera con dos pedidos simultáneos—, más una versión en memoria para los tests.

### La credencial de MercadoPago es el par de tokens, y eso evita una migración

`TicketEmitido` existe desde `conexion-arca` y su docstring dice, con todas las letras, que el
refresh token de MercadoPago iba a viajar por ahí. **No lo va a hacer, y conviene decir por qué en
lugar de dejar el comentario mintiendo.**

`TicketEmitido.servicio` es un `ServicioDeArca`. Meter ahí un token de MercadoPago obliga a
renombrar el enum, ampliar su catálogo, migrar la columna `servicio` de `ticket_de_acceso` y
reinterpretar una tabla cuyo docstring entero explica por qué existe: porque ARCA distingue una
credencial de dos años de una sesión de doce horas, y **se niega a emitir la segunda mientras la
primera viva**.

MercadoPago no tiene esa distinción. No hay credencial de larga vida por debajo: el par
`access_token` + `refresh_token` **es** la credencial, la empresa nunca escribió nada que se le
parezca, y renovar significa reemplazarla entera. Guardarla partida en dos tablas sería modelar una
diferencia que el proveedor no tiene.

Así que los dos tokens viajan juntos en `ResultadoDeConexion.credencial`, empaquetados por
`mercadopago/mapeo.py` con la misma técnica que `wsaa.py` usa para el token y la firma. Una sola
fila, una sola clave de cifrado, ninguna migración de esa tabla — y `TicketEmitido` se queda como lo
que resultó ser: la sesión derivada que sólo ARCA tiene.

### Otros contextos

**Ninguno.** `integrations` sigue sin importar a nadie (ADR-0003). La notificación del RN-03 sale
por el mismo camino que ya existe: el caso de uso devuelve desenlaces, y la **tarea de Celery** —que
es composition root— resuelve los destinatarios llamando a `ListarUsuarios` de `identity`. Es
exactamente lo que `revisar_empresa` hace hoy para ARCA.

### Frontend

`features/integrations`, sin feature nueva:

- **`api/cliente.ts`** — dos funciones más: `iniciarAutorizacion(sistema)` y
  `canjearAutorizacion(sistema, codigo, estado)`. Las dos contra el BFF, como todo lo demás.
- **`components/GrillaDeIntegraciones.tsx`** — la rama `MERCADOPAGO` de `conectar()` deja de mandar
  `CREDENCIAL_SIMULADA` y pasa a `window.location.assign(url)`. Al volver, la grilla ve el `?code`
  en la URL, lo canjea, **y limpia la query con `history.replaceState`**: un F5 sobre una URL con un
  código ya usado devolvería un error de MercadoPago que no significa nada para quien lo lee.
- **`app/(panel)/configuracion/integraciones/page.tsx`** — le pasa a la grilla lo que venga en
  `searchParams`. La ruta no cambia: el retorno aterriza en la pantalla que el Administrador ya
  estaba mirando (decisión D-a).
- **BFF**: `app/api/integraciones/[sistema]/autorizacion/route.ts` y
  `.../autorizacion/canje/route.ts`, sobre el `_proxy.ts` que ya está.

## Infraestructura

### Migraciones

**Una, chica: `0007_empresas_con_mercadopago.py`.** Crea la función `SECURITY DEFINER`
`empresas_con_integracion_de_mercadopago()`, que el barrido diario necesita para saber a qué
empresas mandarle una tarea. Reversible (`DROP FUNCTION`), sin backfill, sin tocar ninguna tabla.

Es la **tercera** perforación de la barrera RLS del sistema, después de
`empresas_con_integracion_pendiente()` y `empresas_con_integracion_de_arca()` — cuyo comentario dice
«la segunda y la última». Deja de ser cierto y hay que corregirlo ahí y en el `TODO.md`. Se hace
igual que las otras dos: **una función por pregunta, sin argumentos**, devolviendo `empresa_id` y
nada más. Una función parametrizada por sistema sería un agujero cuya forma elige quien llama, que
es el motivo por el que la segunda no se hizo así.

### Trabajo asíncrono

| | |
|---|---|
| Tareas | `integrations.renovar_credenciales` (fan-out) y `integrations.renovar_empresa` (una empresa) |
| Worker | El mismo que ya corre las de este contexto |
| Schedule | Diario, junto al barrido de vencimientos de ARCA |
| Reintentos | La política que `workers/base.py` ya aplica |
| Idempotencia | `ClaveDeIdempotencia` por `(empresa, tarea, ventana diaria)`, igual que `revisar_empresa`. **Y una segunda línea de defensa:** renovar dos veces el mismo día no rompe nada porque la primera renovación deja la credencial lejos del margen, así que la segunda no encuentra nada por vencer |

**Par nuevo y no un `if` dentro de `revisar_empresa`.** Las dos tareas se parecen, pero preguntan
cosas distintas: la de ARCA lee una fecha que está dentro del certificado y **no llama a nadie**; la
de MercadoPago llama al proveedor y **reescribe la credencial**. Juntarlas pondría una escritura de
credencial dentro de una tarea que hoy es de sólo lectura.

### Configuración — `backend/.env.example`

```bash
MERCADOPAGO_ADAPTADOR=simulado          # 'mercadopago' para el real; 'simulado' es rechazado en produccion
MERCADOPAGO_CLIENT_ID=
MERCADOPAGO_CLIENT_SECRET=              # secreto de plataforma, nunca por empresa
MERCADOPAGO_AUTH_URL=https://auth.mercadopago.com.ar
MERCADOPAGO_API_URL=https://api.mercadopago.com
MERCADOPAGO_REDIRECT_URI=               # por defecto {APP_BASE_URL}/configuracion/integraciones
MERCADOPAGO_TIMEOUT_SEGUNDOS=10
MERCADOPAGO_MARGEN_RENOVACION_DIAS=15
MERCADOPAGO_AUTORIZACION_TTL_MINUTOS=10
```

`CLIENT_ID` y `CLIENT_SECRET` son **de la plataforma, no de la empresa** — son las credenciales de
*nuestra* aplicación en MercadoPago, igual que el cliente OAuth de Google (gap H8). Lo que es por
empresa son los tokens que el flujo devuelve, y ésos van cifrados a la base como todo lo demás. El
frontend no gana ninguna variable: la URL de autorización la arma el backend.

### Integración externa — contratos

**MercadoPago no tiene dos hosts.** A diferencia de ARCA, no hay un dominio de homologación y otro
de producción: el mismo `api.mercadopago.com` atiende todo, y lo que cambia es de qué aplicación son
las credenciales y si la cuenta que autoriza es de prueba o real. Por eso `Ambiente` se sigue
derivando de `APP_ENV` (decisión D-b de `mecanismo-de-integraciones`) y `live_mode` es el cruce que
detecta el desajuste.

| Operación | Método y URL | Autenticación |
|---|---|---|
| Autorizar | `GET {AUTH_URL}/authorization?client_id&response_type=code&platform_id=mp&state&redirect_uri&code_challenge&code_challenge_method=S256` | Ninguna — la hace el navegador |
| Canjear el código | `POST {API_URL}/oauth/token` con `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier` | `client_id` + `client_secret` en el cuerpo |
| Renovar | `POST {API_URL}/oauth/token` con `grant_type=refresh_token`, `refresh_token` | idem |
| Validar la cuenta (RN-02) | `GET {API_URL}/users/me` | `Authorization: Bearer <access_token>` |

El canje devuelve `access_token`, `refresh_token`, `expires_in` (~180 días), `user_id`, `scope` y
`live_mode`. Timeout 10 s, 3 intentos con backoff exponencial, y **sólo se reintenta lo que se puede
reintentar**: un `POST /oauth/token` con `grant_type=authorization_code` **no se reintenta ante un
4xx** porque el código es de un solo uso — un segundo intento no falla distinto, sólo tarda más.

| Qué contesta MercadoPago | Qué significa | Qué lanzamos |
|---|---|---|
| 400 `invalid_grant` | Código usado, vencido (duran ~10 min) o `redirect_uri` distinta de la del paso 1 | `ConexionRechazada` → 422 |
| 400 `invalid_client` | `client_id`/`client_secret` mal configurados | `ConexionRechazada` con detalle propio: es error **nuestro** de despliegue, no del Administrador, y el mensaje lo dice |
| 401 en `/users/me` | El token ya no vale — revocado desde el panel de MercadoPago | RN-03: inactiva y notifica |
| 429 | Rate limit | Reintento con backoff |
| 5xx o timeout | MercadoPago no está | `ProveedorNoDisponible` — la tarjeta queda como estaba |

### `live_mode` — cuándo se rechaza la conexión

Decisión D-c. MercadoPago informa si la cuenta que autorizó es real o de prueba, y se cruza con el
ambiente del despliegue:

| Cuenta | Despliegue | Qué pasa |
|---|---|---|
| Real (`live_mode: true`) | Homologación | **Se rechaza.** Es el caso que cobra plata de verdad desde un entorno de pruebas |
| De prueba | Producción | Conecta en **Atención**, con el detalle. No hay riesgo de cobrar de más: el riesgo es no cobrar, y eso se ve |
| Coinciden | — | Conecta normal |

Es el mismo tipo de chequeo que el CUIT del certificado en la unidad anterior: sale casi gratis,
usa un dato que el proveedor ya nos dio, y ataja un error que si no aparece cuando alguien paga.

## Riesgos que obligan a tests

- [x] **Toca dinero — indirectamente, y por eso el test es de otra cosa.** Acá no hay ningún importe:
      no se suma, no se redondea y no aparece un `Decimal`. Lo que esta unidad decide es **a qué
      cuenta van a parar los cobros del épico 6**, así que los tests que lo cuidan son el del
      `state` de un solo uso, el de que el `state` es de la empresa que lo pidió, y el de `live_mode`
- [x] Agrega datos con `empresa_id` → test de aislamiento entre empresas, y el `state` de una
      empresa no sirve para otra
- [ ] Comprobantes fiscales / CAE → no aplica
- [ ] Webhook → no aplica. Los webhooks de pago son del épico 6
- [ ] Salida de un LLM → no aplica
- [x] **Secretos**: los dos tokens son credenciales completas. No se loguean, no vuelven por la API
      y no aparecen en ningún mensaje de error. El log de la renovación dice qué empresa y qué
      sistema, y nada más

## Archivos a tocar

**Backend — dominio y aplicación**
- [x] `contexts/integrations/domain/valores.py` — `CLAVE_VENCIMIENTO`
- [x] `contexts/integrations/application/ports.py` — los tres puertos y sus DTOs
- [x] `contexts/integrations/application/oauth.py` — `IniciarAutorizacion`, `CompletarAutorizacion`
- [x] `contexts/integrations/application/renovacion.py` — `RenovarCredenciales`
- [x] `contexts/integrations/application/errors.py` — `AutorizacionInvalida`

**Backend — infraestructura**
- [x] `contexts/integrations/infrastructure/mercadopago/{cliente,mapeo,conector,autorizacion,verificador,simulado}.py`
- [x] `contexts/integrations/infrastructure/autorizaciones.py`
- [x] `contexts/integrations/infrastructure/registro.py` — MERCADOPAGO deja de ser simulado genérico
- [x] `contexts/integrations/infrastructure/ensamblado.py` — la memoria de autorizaciones
- [x] `contexts/integrations/infrastructure/repositories.py` — `empresas_con_integracion_de_mercadopago`
- [x] `contexts/integrations/infrastructure/simulados.py` — el docstring: ya no le queda ningún cliente

**Backend — bordes**
- [x] `api/routers/integraciones.py` — las dos rutas nuevas
- [x] `workers/tasks_integrations.py` y `workers/beat.py` — el par de tareas y su schedule
- [x] `platform/settings.py` + `backend/.env.example` — las ocho variables
- [x] `migrations/versions/0007_empresas_con_mercadopago.py`

**Frontend**
- [x] `features/integrations/api/cliente.ts` e `index.ts`
- [x] `features/integrations/components/GrillaDeIntegraciones.tsx`
- [x] `app/(panel)/configuracion/integraciones/page.tsx`
- [x] `app/api/integraciones/[sistema]/autorizacion/route.ts` y `.../canje/route.ts`

**Tests**
- [x] `tests/contexts/integrations/infrastructure/test_mercadopago_contrato.py`
- [x] `tests/contexts/integrations/application/test_oauth.py`
- [x] `tests/contexts/integrations/application/test_renovacion.py`
- [x] `tests/integracion/test_api_mercadopago.py`
- [x] `frontend/src/features/integrations/components/__tests__/`

**Documentación**
- [x] `docs/architecture.md` §7 — los tres puertos nuevos
- [x] `docs/aidlc/TODO.md` — §5.3 con lo que hace falta para credenciales reales, y §7 corregida

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | La URL de autorización lleva `client_id`, `redirect_uri`, `state` y `code_challenge` con `S256` | contrato | ✅ |
| 2 | Un Operador no puede iniciar la autorización | unit | ✅ |
| 3 | El `state` se consume **una sola vez**: el segundo canje con el mismo `state` es rechazado | unit + integración | ✅ |
| 4 | Un `state` de la empresa A no sirve para la empresa B | unit + integración | ✅ |
| 5 | Un `state` vencido o inexistente es rechazado sin llamar a MercadoPago | unit | ✅ |
| 6 | El canje manda `code_verifier` y la **misma** `redirect_uri` del paso 1 | contrato | ✅ |
| 7 | El canje exitoso guarda los dos tokens cifrados y ninguno vuelve por la API | integración | ✅ |
| 8 | RN-02: sin `GET /users/me` en verde la integración no se marca Conectada | contrato | ✅ |
| 9 | El apodo de la cuenta llega a la tarjeta como `etiqueta` | contrato | ✅ |
| 10 | `invalid_grant` → `ConexionRechazada` (422) y la integración queda como estaba | contrato + integración | ✅ |
| 11 | `invalid_client` → mensaje que dice que es configuración nuestra | contrato | ✅ |
| 12 | Un 4xx en el canje **no** se reintenta; un 5xx **tampoco** (ver desvío D4) | contrato | ✅ |
| 13 | Cuenta real en despliegue de homologación → se rechaza la conexión | contrato | ✅ |
| 14 | Cuenta de prueba en producción → conecta en Atención con el detalle | contrato | ✅ |
| 15 | Reconectar reemplaza la credencial y no crea una segunda fila | integración | ✅ |
| 16 | La renovación diaria no llama a MercadoPago si falta más que el margen | unit | ✅ |
| 17 | Renovada la credencial, se reescribe cifrada y `credencial_vence_en` avanza | unit | ✅ |
| 18 | RN-03: rechazo al renovar → inactiva, evento de bitácora y desenlace para el aviso | unit | ✅ |
| 19 | MercadoPago caído al renovar **no** desconecta nada | unit | ✅ |
| 20 | Un 401 en la verificación en vivo pasa la integración a **No conectada** (desvío D5) | contrato | ✅ |
| 21 | La tarea es idempotente: dos corridas el mismo día producen un solo efecto | unit | ✅ |
| 22 | El adaptador simulado se niega a construirse en `production` | unit | ✅ |
| 23 | Ningún test abre un socket | contrato | ✅ |
| 24 | La grilla manda el navegador a MercadoPago y al volver canjea el código | frontend | ✅ |
| 25 | Al volver con `?error=access_denied` se explica que no se autorizó, sin error técnico | frontend | ✅ |
| 26 | Después de canjear, la query queda limpia (un F5 no reenvía el código) | frontend | ✅ |
| 27 | El `state` vive en Redis de verdad y se consume entre dos pedidos HTTP distintos | integración | ✅ |
| 28 | La función `SECURITY DEFINER` nueva devuelve la empresa conectada y nada más | integración | ✅ |
| 29 | Una entrada ilegible en la memoria de autorizaciones se trata como ausente | unit | ✅ |
| 30 | Sin `expires_in` se asume la duración habitual en lugar de renovar todos los días | contrato | ✅ |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-20 | **aprobado** sin cambios, con las tres preguntas contestadas (D-a, D-b, D-c) |
| 2 · Verificación | 2026-08-20 | ver abajo |
| 3 · PR | | |

## Verificación — Gate 2 (2026-08-20)

```
ruff format --check .   243 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 238 source files
guard_architecture      257 file(s) checked — architecture boundaries intact
test_guards.sh          54 cases, all correct — the guards are active
pytest                  572 passed · cobertura 89.35 % (umbral 80)
frontend format:check   All matched files use Prettier code style!
frontend lint           No ESLint warnings or errors
frontend typecheck      sin errores
frontend test:coverage  230 passed · 88.01 % líneas
```

Corrida con PostgreSQL y Redis levantados, así que los tests de integración —RLS, el índice
único y el `state` viviendo en Redis de verdad— se ejecutaron en lugar de saltearse.

## Desvíos del plan

Ocho, y ninguno cambia el alcance. Se escriben porque el plan quedó desactualizado respecto
del código en estos puntos.

**D1 — `MaterialDeConexion` gana un campo, `efimeros`.** El plan pasaba el `code_verifier`
por `parametros`, y eso lo habría **persistido**: `ConectarIntegracion` mezcla los
parámetros del pedido con los del proveedor y los escribe en la fila. Un secreto de un solo
uso guardado para siempre en una columna JSONB. `efimeros` es una bolsa aparte que el caso
de uso nunca mezcla. Toca el contrato publicado, y es genérico: PKCE es un estándar, no un
proveedor.

**D2 — `CLAVE_VERIFICADOR` también subió al dominio.** Misma razón que `CLAVE_VENCIMIENTO`:
la escribe la capa de aplicación, así que declararla en `infrastructure/` sería importar
hacia adentro (R2).

**D3 — `infrastructure/simulados.py` se borró, no se le arregló el docstring.** El plan
decía «actualizar el docstring: ya no le queda ningún cliente». Al no quedarle ninguno, lo
que quedaba era código muerto con un test propio. Se fue el módulo y su test — que es lo que
su propio docstring venía anunciando desde `mecanismo-de-integraciones`: «cada unidad borra
su par de `registro.py`».

**D4 — El reintento no es uniforme, y es el hallazgo de la unidad.** El plan decía «3
intentos con backoff» y «no se reintenta ante un 4xx». Al escribir el cliente apareció algo
más filoso: **`/oauth/token` rota el refresh token en cada llamada**, así que repetir un
pedido que MercadoPago quizá ya procesó deja a la empresa con un token que el proveedor ya
reemplazó — una integración que muere en silencio y no se puede renovar. El corte quedó por
**evidencia y no por verbo**: sólo se repite lo que prueba que el pedido **nunca llegó**
(`ConnectError`, `ConnectTimeout`, `PoolTimeout`). Un read timeout o un 5xx contra ese
endpoint se reportan como proveedor no disponible, sin reintentar. `GET /users/me` sí se
reintenta como cualquier lectura.

**D5 — Un 401 en la verificación deja la integración en No conectada, no en Atención.** El
caso 20 del plan decía Atención. RN-03 dice «marca la integración como **inactiva**», y la
tarjeta tiene que ofrecer Reconectar: Atención habría dicho «anda con un detalle» sobre algo
que no anda.

**D6 — `_exigir_administrador` pasó a ser público.** `CompletarAutorizacion` chequea el rol
**antes** de consumir el `state`: si no, un pedido que nunca iba a permitirse quema un token
de un solo uso y obliga al Administrador a empezar de cero. Hay un test para eso.

**D7 — `test_api_integraciones.py` hubo que reescribirlo.** Sus cuatro tests conectaban
MERCADOPAGO con una credencial de relleno, porque era el último sistema con adaptador
genérico. Ahora recorren el OAuth2 real. Dos de ellos **pasaban en vacío** después del
cambio —afirmaban que nada se filtraba sobre una conexión que había fallado—, así que ahora
verifican primero que la conexión funcionó.

**D8 — Dos tests del frontend se mudaron al formulario de ARCA.** Los del `aviso_fiscal` de
`padron-y-datos-fiscales` apretaban «Conectar» en MercadoPago por ser el único de un click.
Ahora pasan por donde el aviso realmente ocurre. Costó un detalle: jsdom no implementa
`Blob.prototype.text`, que es lo que ese formulario usa, así que el test lo resuelve **por
instancia** en vez de parchear el prototipo — un polyfill global escondería que el navegador
real hace otra cosa.

## Decisiones tomadas durante la unidad

- **D-a — El retorno de MercadoPago aterriza en el panel, en la misma pantalla.** `redirect_uri` es
  `{APP_BASE_URL}/configuracion/integraciones`; la pantalla lee `?code&state` y llama al BFF, que es
  quien tiene la cookie de sesión. No agrega ruta nueva ni obliga a exponer el backend a internet.
- **D-b — La renovación es automática, en el barrido diario.** Guardar el refresh token y no usarlo
  sería dejar caer la integración a los 180 días con un aviso. El barrido diario ya existe para ARCA
  y esto es un par de tareas más con la misma forma.
- **D-c — Una cuenta real en un despliegue que no es producción se rechaza.** El caso inverso
  —cuenta de prueba en producción— conecta en Atención: ahí el riesgo es no cobrar, y se ve.
- **D-d — El refresh token no viaja como `TicketEmitido`.** La credencial de MercadoPago es el par
  de tokens; ver la sección de diseño. Evita renombrar `ServicioDeArca` y migrar `ticket_de_acceso`.
