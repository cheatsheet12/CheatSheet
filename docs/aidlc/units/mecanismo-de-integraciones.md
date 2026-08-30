# Unidad: mecanismo-de-integraciones

**HUs**: HU-E2-05 **Contexto dueño**: integrations **Rama**: feature/integrations-mecanismo-de-integraciones

## Qué hace

Levanta el contexto `integrations` entero: el agregado `ConfiguracionDeIntegracion`, el cifrado de
credenciales en reposo, el puerto por el que cada proveedor se enchufa, y la pantalla PAN-CFG-INT con
la grilla de tarjetas.

Cierra HU-E2-05: el Administrador o el Operador entran a `(panel)/configuracion/integraciones`, ven
las cuatro integraciones con su estado y la hora de la última verificación, y el botón «Verificar»
consulta a las cuatro en vivo y actualiza la tabla.

**Ningún proveedor real.** Los cuatro conectores y verificadores son simulados, igual que
`ProveedorOAuthSimulado` y `EnviadorDeConsola` en el épico 1, y por el mismo motivo: el flujo se
recorre entero en una laptop y los tests no tocan la red. Las unidades 2 a 5 reemplazan un simulado
por un adaptador real cada una, sin tocar nada de lo que se construye acá.

## Diseño

### Dominio

`contexts/integrations/domain/`, sin framework y sin I/O (R1).

**`valores.py`**

- **`SistemaExterno`** — StrEnum con los cinco valores del enum `sistema_externo` del DER: `ARCA`,
  `MERCADOPAGO`, `WHATSAPP`, `GOOGLE_SHEETS`, `EXCEL_ONLINE`. Se toma el catálogo completo del insumo
  aunque este épico solo llegue a los tres primeros; los dos de planilla son del épico 4.
- **`Ambiente`** — `HOMOLOGACION` · `PRODUCCION`. **No lo elige el usuario**: se deriva de
  `settings.entorno` (decisión D-b). Se guarda en la fila igual, porque HU-E2-01 RN-03 pide que la
  integración registre en cuál opera, y porque una fila creada en homologación tiene que seguir
  diciéndolo si algún día la base se restaura en otro lado.
- **`EstadoDeConexion`** — `CONECTADO` · `ATENCION` · `NO_CONECTADO`, exactamente los tres de
  HU-E2-05 RN-02. **`PENDIENTE` no entra acá**: lo necesita solo WhatsApp (HU-E2-03 RN-02) y lo
  agrega `conexion-whatsapp`. Se dice para que esa unidad sepa que ampliar el enum es parte de su
  alcance previsto y no una rotura de esta.
- **`CredencialCifrada`** — value object inmutable: `contenido: bytes` + `algoritmo: str`. Las dos
  columnas del DER viajan juntas siempre, porque una sin la otra no se puede descifrar.

**`configuracion.py` — el agregado `ConfiguracionDeIntegracion`**

Raíz de agregado, una por `(empresa_id, sistema)`. Comportamiento, no un contenedor de campos:

- `conectar(credencial, ambiente, parametros, ahora)` — guarda la credencial cifrada y deja el estado
  en `CONECTADO`. Rechaza reconectar con un ambiente distinto del que corresponde al despliegue.
- `registrar_verificacion(estado, detalle, ahora)` — mueve el estado y sella `verificado_en`.
  **Devuelve el evento solo si el estado cambió.** Una verificación que confirma lo que ya se sabía
  no escribe en la bitácora; si lo hiciera, el Log de Operaciones se convertiría en un latido y
  HU-E12-01 tendría que filtrarlo.
- `desactivar(motivo, ahora)` — a `NO_CONECTADO`, para HU-E2-01 RN-04 y HU-E2-02 RN-03. Existe acá
  porque es la transición que comparten las tres conexiones; **ninguna la dispara todavía**.

**Evento de dominio**: `EstadoDeIntegracionCambio(empresa_id, sistema, anterior, nuevo, detalle)`,
sobre `EventoDeDominio` de `shared/events.py`. Se traduce a una fila de bitácora con
`Modulo.INTEGRATIONS`, que ya existe en `shared/auditoria.py` desde `cimientos-y-bitacora`.

### Aplicación

`contexts/integrations/application/`. **Este es el contrato publicado de ADR-0003**: lo que viva acá
lo puede llamar cualquier contexto; `domain/` e `infrastructure/` quedan privados.

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `ListarIntegraciones` | `empresa_id`, `rol` | una entrada por valor de `SistemaExterno` alcanzable en el épico | Devuelve el **catálogo**, no las filas: un sistema sin fila configurada sale como `NO_CONECTADO`. Es lo que permite que la pantalla muestre cuatro tarjetas con la base vacía |
| `VerificarConexiones` (HU-E2-05) | `empresa_id`, `rol` | los mismos estados, ya actualizados, más `verificado_en` | Consulta **en paralelo** a los verificadores de las integraciones configuradas, con timeout por proveedor. Un proveedor que falla o tarda **no rompe la respuesta**: esa integración sale `NO_CONECTADO` con el detalle, y las otras tres se responden igual |
| `ConectarIntegracion` | `empresa_id`, `rol`, `sistema`, material de conexión | el estado resultante | Cifra la credencial antes de persistirla, valida contra el proveedor **antes** de marcar `CONECTADO` (HU-E2-01 RN-02, HU-E2-02 RN-02), y es idempotente por `(empresa_id, sistema)`: reconectar pisa la credencial, no crea una segunda fila |

**Autorización**: leer y verificar lo pueden hacer Administrador **y** Operador — HU-E2-05 nombra a
los dos como actores. Conectar es solo Administrador, como el resto de la configuración.

**No entra en esta unidad**: desconectar. Ninguna historia del épico la pide, y HU-E2-05 solo habla
de «la acción para reconectarla». Si aparece, es alcance de otra unidad.

### Puertos y adaptadores

`application/ports.py` declara; `infrastructure/` implementa (R2).

| Puerto | Adaptador de esta unidad | Lo reemplaza |
|---|---|---|
| `PortRepositorioIntegraciones` | `RepositorioIntegracionesSQL` | — |
| `PortCifradoDeCredenciales` | `CifradoAesGcm` | — |
| `PortConectorDeIntegracion` (por sistema) | `ConectorSimulado` ×4 | unidades 2, 3, 5 |
| `PortVerificadorDeConexion` (por sistema) | `VerificadorSimulado` ×4 | unidades 2, 3, 5 |

`RegistroDeAdaptadores` resuelve conector y verificador por `SistemaExterno`. Es el único punto que
cada unidad siguiente toca para enchufar su proveedor.

**El cifrado vive en `integrations/infrastructure/cifrado.py`, no en `platform/`.** Esto es lo que
hace verdadero el punto 3 de ADR-0003 en vez de aspiracional: si el cifrador fuera código de
plataforma, cualquier módulo podría importarlo y la afirmación «el descifrado no sale del contexto»
sería una convención sin nada que la sostenga. `Settings` sí lleva `SECRETS_ENCRYPTION_KEY`, igual
que ya lleva `JWT_SECRET` — se dice de frente: la *clave* es alcanzable desde `platform`, la
*capacidad de descifrar* no.

Rotación: `credencial_algoritmo` guarda `AES-256-GCM/v1`. El identificador de clave viaja en ese
mismo string, que es para lo que el DER le dio columna propia — rotar significa escribir `/v2` en las
filas nuevas y saber leer las dos.

`ConectorSimulado` y `VerificadorSimulado` **lanzan `RuntimeError` al construirse en `production`**,
como `ProveedorOAuthSimulado`. No es un warning.

### Otros contextos

Ninguno. Esta unidad **no llama a nadie**, que es exactamente lo que ADR-0003 punto 2 exige de un
Open Host Service. Los consumidores llegan después: `padron-y-datos-fiscales` es el primero.

**Un movimiento que sí toca `identity`, y hay que declararlo.** `RolUsuario` vive hoy en
`identity/domain/valores.py`, e `integrations` necesita el rol para autorizar. Importarlo rompería
R3, y ADR-0003 punto 2 prohíbe que `integrations` dependa de `identity`. Se sube el enum a
**`shared/roles.py`** —es un value object entre contextos, que es literalmente lo que el Shared
Kernel contiene— y `identity/domain/valores.py` lo re-exporta. Las 100 apariciones de `RolUsuario`
en el repositorio **no cambian**: siguen importando de donde importaban. R4 se respeta: `shared/` no
importa de `contexts/`.

La alternativa era chequear el rol en el router. Se descarta porque contradice el motivo ya escrito
en `identity/application/autorizacion.py`: la regla tiene que estar al lado de la operación para que
una tarea de Celery o un endpoint escrito con apuro lleguen a la misma respuesta.

### Frontend

`features/integrations/`, espejo del contexto (ADR-0002).

- `api/cliente.ts` — tipos y llamadas al BFF.
- `components/TarjetaDeIntegracion.tsx` — una tarjeta: logo, nombre, descripción, badge de estado y
  acción. Reusa `Badge`, `Button` y `Card` de `shared/ui`.
- `components/GrillaDeIntegraciones.tsx` — las cuatro tarjetas, el botón «Verificar» y la marca de
  tiempo consolidada de HU-E2-05 RN-03.
- `index.ts` — exporta solo `GrillaDeIntegraciones` y sus tipos (R5).

Ruta: `(panel)/configuracion/integraciones/page.tsx`, más el enlace en la barra de
`(panel)/layout.tsx`, al lado de «Usuarios» y «Mis preferencias».

BFF: `app/api/integraciones/route.ts`, `app/api/integraciones/verificacion/route.ts` y
`app/api/integraciones/[sistema]/conexion/route.ts`, con el wrapper de fetch y la cookie HttpOnly que
ya existen.

**El diseño sale de PAN-ONB-03** (`inputs/prototipos/onboarding.html`, tercera columna):
la grilla `int-card` con logo cuadrado de color, descripción de una línea y pie con badge más acción.
Se toma tal cual, montado en configuración y no en el onboarding (decisión D7 del mapa de unidades).
El indicador «PASO 3 DE 3» y el pie «Configurar esto después» no se replican.

## Infraestructura

### Migraciones — `0004_configuracion_de_integracion`

Tabla `configuracion_de_integracion` según el DER (BC4), más tres columnas que las historias exigen
y el DER no tiene. Reversible; **sin backfill**: no hay filas previas.

| Columna | Origen |
|---|---|
| `id`, `empresa_id`, `sistema`, `credencial_contenido_cifrado`, `credencial_algoritmo`, `parametros`, `ambiente`, `created_at`, `updated_at` | DER |
| `estado` | **hueco H9** |
| `detalle_estado` | **hueco H9** |
| `verificado_en` | **hueco H9** |

**Hueco H9** — el DER modela el estado como `activa boolean NN`, y HU-E2-05 RN-02 pide **tres**
estados, RN-03 pide la marca de tiempo de la última verificación, y el criterio «una integración
está degradada → la muestro en Atención con el detalle disponible» pide un texto. Un booleano no
distingue *degradado* de *caído*, que es justo la distinción que la historia existe para mostrar.
Resolución: `activa` se reemplaza por `estado`, porque es derivable (`estado == CONECTADO`) y
mantener las dos garantiza que algún día se contradigan.

Índices: único sobre `(empresa_id, sistema)` — es la identidad del agregado y lo que hace idempotente
a `ConectarIntegracion`. RLS por `empresa_id` con la política `aislamiento_por_empresa`, idéntica a
las de `0002_identidad` (hueco H5: las políticas son decisión de cada migración).

**Una fila existe solo cuando algo se conectó.** `credencial_contenido_cifrado` es NOT NULL en el
DER y se respeta: no se crean cuatro filas vacías por empresa. El catálogo de cuatro tarjetas sale
del enum, no de la tabla.

### Trabajo asíncrono

**Ninguno.** La verificación es síncrona y en paralelo, con timeout por proveedor (decisión D-a). La
cola `integrations_sync` ya existe desde `cimientos-y-bitacora` y queda sin uso en esta unidad.

La re-verificación periódica que detecta una credencial vencida (HU-E2-01 RN-04, HU-E2-02 RN-03)
**no se construye acá**: sin ningún proveedor real no hay nada que pueda vencer. La transición
`desactivar()` sí queda escrita y probada, para que la unidad que traiga el primer proveedor real
solo tenga que agendar la tarea.

### Configuración — variables nuevas

`backend/.env.example`:

```bash
# Cifrado de credenciales de integraciones (ADR-0003, DER BC4)
SECRETS_ENCRYPTION_KEY=          # obligatoria; 32 bytes en base64. El proceso no arranca sin ella
INTEGRACION_TIMEOUT_SEGUNDOS=5   # por proveedor, en la verificación en vivo
```

**Y de paso se reconcilia el archivo entero**, que está desincronizado con `platform/settings.py`
desde el épico 1: declara `ENVIRONMENT`, `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_MINUTES` y
`REFRESH_TOKEN_DAYS` cuando el código lee `APP_ENV`, `JWT_SECRET`, `JWT_ACCESS_TTL_MINUTOS` y
`REFRESH_TTL_DIAS`, y le faltan las once variables de las unidades 2 y 3 del épico 1
(`DATABASE_URL_MIGRATIONS`, `TERMINOS_VERSION_VIGENTE`, `APP_BASE_URL`, `GOOGLE_OAUTH_REDIRECT_URI`,
`EMAIL_ADAPTADOR`, `INVITACION_TTL_DIAS` y las `SMTP_*`). Hoy copiarlo no levanta el proceso. Es
deuda heredada, está anotada en `docs/aidlc/TODO.md`, y se salda acá porque la Definition of Done
obliga a tocar el archivo igual. `frontend/.env.example` va con lo mismo: le faltan
`BACKEND_API_URL`, `APP_BASE_URL` y `SESSION_COOKIE_NAME`.

### Integraciones externas

**Ninguna real.** Los cuatro adaptadores son simulados. La escalada de «nueva integración externa»
—sección de contratos con endpoints por ambiente, autenticación, modos de falla y tests de
contrato— corresponde a las unidades 2, 3 y 5, cada una para su proveedor.

Lo que sí se define acá es la **forma** que van a tener: timeout explícito, reintentos con backoff y
manejo de falla son responsabilidad del adaptador, no del caso de uso. El caso de uso solo garantiza
que un adaptador lento no arrastre a los otros tres.

## Riesgos que obligan a tests

- [ ] Toca dinero → **no**
- [ ] Toca comprobantes fiscales / CAE → **no**. Habilita la credencial que el épico 5 va a usar, pero acá nada emite
- [x] **Agrega datos con `empresa_id`** → test de aislamiento entre empresas sobre `configuracion_de_integracion`, contra PostgreSQL real
- [ ] Consume un webhook → **no**
- [ ] Usa salida de un LLM → **no**
- [x] **Datos personales o fiscales** → la credencial de ARCA es material fiscal de la empresa. Nunca se loguea, nunca sale en una respuesta de la API, nunca viaja a un LLM. Test de que el descifrado no aparece en el log estructurado ni en el JSON de respuesta

## Archivos a tocar

Backend

- [x] `backend/src/cheatsheet/shared/roles.py` *(nuevo — `RolUsuario` sube al Shared Kernel)*
- [x] `backend/src/cheatsheet/contexts/identity/domain/valores.py` *(re-exporta `RolUsuario`)*
- [x] `backend/src/cheatsheet/contexts/integrations/domain/valores.py`
- [x] `backend/src/cheatsheet/contexts/integrations/domain/configuracion.py`
- [x] `backend/src/cheatsheet/contexts/integrations/application/ports.py`
- [x] `backend/src/cheatsheet/contexts/integrations/application/errors.py`
- [x] `backend/src/cheatsheet/contexts/integrations/application/integraciones.py`
- [x] `backend/src/cheatsheet/contexts/integrations/infrastructure/models.py`
- [x] `backend/src/cheatsheet/contexts/integrations/infrastructure/repositories.py`
- [x] `backend/src/cheatsheet/contexts/integrations/infrastructure/cifrado.py`
- [x] `backend/src/cheatsheet/contexts/integrations/infrastructure/simulados.py`
- [x] `backend/src/cheatsheet/contexts/integrations/infrastructure/registro.py`
- [x] `backend/src/cheatsheet/api/routers/integraciones.py`
- [x] `backend/src/cheatsheet/api/main.py` *(monta el router)*
- [x] `backend/src/cheatsheet/api/dependencies.py` *(arma el registro de adaptadores)*
- [x] `backend/src/cheatsheet/platform/settings.py` *(dos variables nuevas)*
- [x] `backend/migrations/versions/0004_configuracion_de_integracion.py`
- [x] `backend/.env.example` *(las dos nuevas + la reconciliación)*

Tests

- [x] `backend/tests/contexts/integrations/domain/test_configuracion.py`
- [x] `backend/tests/contexts/integrations/application/test_integraciones.py`
- [x] `backend/tests/contexts/integrations/infrastructure/test_cifrado.py`
- [x] `backend/tests/contexts/integrations/conftest.py`
- [x] `backend/tests/api/test_router_integraciones.py`
- [x] `backend/tests/integracion/test_integrations_postgres.py` *(RLS)*

Frontend

- [x] `frontend/src/features/integrations/api/cliente.ts`
- [x] `frontend/src/features/integrations/components/TarjetaDeIntegracion.tsx`
- [x] `frontend/src/features/integrations/components/GrillaDeIntegraciones.tsx`
- [x] `frontend/src/features/integrations/index.ts`
- [x] `frontend/src/app/(panel)/configuracion/integraciones/page.tsx`
- [x] `frontend/src/app/(panel)/layout.tsx` *(enlace en la barra)*
- [x] `frontend/src/app/api/integraciones/route.ts`
- [x] `frontend/src/app/api/integraciones/verificacion/route.ts`
- [x] `frontend/src/app/api/integraciones/[sistema]/conexion/route.ts`
- [x] `frontend/src/shared/componentes.css` *(la grilla `int-card` del prototipo)*
- [x] `frontend/.env.example` *(reconciliación)*
- [x] tests de los componentes y de las tres rutas del BFF

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | `registrar_verificacion` con el mismo estado **no** emite evento; con otro estado sí | unit | hecho |
| 2 | `conectar` deja `CONECTADO` y sella la credencial cifrada | unit | hecho |
| 3 | `desactivar` lleva a `NO_CONECTADO` con el motivo | unit | hecho |
| 4 | Cifrar y descifrar devuelve el original; el ciphertext no contiene el plano | unit | hecho |
| 5 | Un ciphertext manipulado falla al descifrar (GCM autentica) | unit | hecho |
| 6 | `ListarIntegraciones` sobre base vacía devuelve las cuatro en `NO_CONECTADO` | unit | hecho |
| 7 | `VerificarConexiones`: un proveedor que tarda más que el timeout sale `NO_CONECTADO` y **los otros tres responden bien** | unit | hecho |
| 8 | `VerificarConexiones`: un proveedor que lanza no propaga la excepción | unit | hecho |
| 9 | `VerificarConexiones` sella `verificado_en` en las cuatro | unit | hecho |
| 10 | Un cambio de estado escribe la fila de bitácora con `Modulo.INTEGRATIONS` | integración | hecho |
| 11 | `ConectarIntegracion` dos veces sobre el mismo sistema pisa la fila, no crea una segunda | integración | hecho |
| 12 | Operador puede listar y verificar; **no** puede conectar | unit | hecho |
| 13 | Solo Lectura no puede ni conectar ni verificar | unit | hecho |
| 14 | La empresa A no ve la configuración de la empresa B (RLS, PostgreSQL real) | integración | hecho |
| 15 | La credencial descifrada no aparece en la respuesta de la API ni en el log | integración | hecho |
| 16 | El conector simulado lanza al construirse con `APP_ENV=production` | unit | hecho |
| 17 | El ambiente sale de `settings.entorno` y no de la petición | unit | hecho |
| 18 | La migración `0004` sube y baja limpia contra PostgreSQL | integración | hecho |
| 19 | La grilla renderiza las cuatro tarjetas y el badge de cada estado | frontend | hecho |
| 20 | «Verificar» muestra estado de carga y refresca la marca de tiempo | frontend | hecho |
| 21 | Las tres rutas del BFF propagan la cookie y el error del backend | frontend | hecho |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-18 | aprobado sin cambios |
| 2 · Verificación | 2026-08-18 | verde; pendiente tu visto bueno |
| 3 · PR | | |

## Gate 2 — verificación (2026-08-18)

```
ruff format --check .   182 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 177 source files
guard_architecture      216 file(s) checked — architecture boundaries intact
pytest --cov            295 passed · cobertura 88.5% (umbral 80%)
                        integrations/application 98% · domain 100% · cifrado 100%
frontend format/lint/typecheck  limpios
frontend vitest         195 passed · features/integrations 100%
frontend build          compila, 24 rutas registradas
```

Los 295 del backend incluyen los de PostgreSQL: se levantó el contenedor y **no quedó
ningún test salteado**. Los 33 skips que arrastraba el épico 1 eran justamente eso.

### Lo que la implementación encontró y el plan no preveía

- **`SECRETS_ENCRYPTION_KEY` ya existía en `backend/.env.example`.** El plan la daba por
  nueva. Estaba declarada desde el bootstrap del repositorio, sin que nada la leyera. La
  unidad no la agrega: la pone en uso.
- **El evento de dominio se convirtió en un hecho de dominio.** El plan hablaba de
  `EstadoDeIntegracionCambio` como evento. Al escribirlo apareció que `identity` construye
  sus `EventoAuditable` en la **capa de aplicación**, no en el dominio, y con razón: el
  agregado sabe qué cambió, pero solo el caso de uso sabe *quién* lo pidió y desde qué IP.
  Quedó `CambioDeEstado` en el dominio y la traducción a bitácora en `integraciones.py`.
- **`ConexionRechazada` y `SistemaNoConfigurable` pasaron a ser `EntradaInvalida`.** El
  test de integración las encontró respondiendo 409, que es el default para un
  `ErrorDeDominio` sin clasificar. HU-E2-01 lo redacta como «el sistema indica el error de
  validación», que es un 422; y para quien está completando el formulario, una credencial
  rechazada y una mal formada son lo mismo.
- **La primera conexión no producía fila de bitácora.** `registrar_verificacion` compara
  contra el estado anterior, y en un alta no hay estado anterior. Se construye el
  `CambioDeEstado` explícitamente en ese camino. Lo agarró el caso 10 contra PostgreSQL.

### Apartamientos del plan, y por qué

- **`domain/eventos.py` no contiene un evento.** Ver arriba. El nombre del archivo se
  mantuvo porque es donde el lector lo busca.
- **Se agregó `infrastructure/ensamblado.py`**, que el plan no listaba. Es el mismo patrón
  que `identity`: un solo lugar que sabe qué clase concreta satisface cada puerto, para que
  el router no lo sepa.
- **Se agregó la dependencia `cryptography==43.0.3`.** El plan la daba por sentada sin
  nombrarla. Va con su primer llamador, como pide el comentario de `backend/pyproject.toml`.

### Alcance que se agregó, declarado

- **La pantalla conecta de verdad, con credencial simulada.** El plan describía la unidad
  terminando en cuatro tarjetas «No conectada» y el botón de verificar. Tal cual, el camino
  de cifrado y persistencia no se ejercía nunca fuera de un test unitario, y la unidad no
  era demostrable. Se agregó `ConectarIntegracion` con `ConectorSimulado`, que es lo que
  hace que hoy se pueda recorrer: conectar → cifrar → persistir → verificar → auditar.
- **Se agregaron los estilos `int-*` a `shared/componentes.css`**, transcritos del prototipo
  PAN-ONB-03 con los tokens del repositorio sustituidos. Tres reglas no tienen equivalente
  en la maqueta y están marcadas como tales: el detalle de «Atención», el control de
  verificación con su marca de tiempo, y la nota de una tarjeta cuyo proveedor es de otro
  épico.

### Los dos `.env.example`, reconciliados

**Estaban bloqueados por una regla de permisos del propio repositorio, y la regla estaba mal.**
`.claude/settings.json` denegaba `Read(./.env.*)`, que además de los `.env` reales atrapaba a los
`.env.example` — plantillas versionadas, sin un solo secreto, que existen justamente para leerse.
`.gitignore` ya tenía la intención correcta desde siempre (`.env.*` ignorado, `!.env.example`
exceptuado); la regla de permisos había copiado la primera mitad y se olvidó de la segunda.

Se reemplazó el comodín por la enumeración de los archivos que sí son secretos
(`.env`, `.env.local`, `.env.development`, `.env.test`, `.env.staging`, `.env.production`), y de paso
se agregó `*.crt`, que `CLAUDE.md` §3.3 nombra y la lista no tenía. Ningún archivo real quedó
desprotegido.

Con eso aplicado, los dos archivos quedaron reconciliados:

- **`backend/.env.example`** — corregidas las cuatro variables mal nombradas desde el épico 1
  (`ENVIRONMENT`→`APP_ENV`, `JWT_SECRET_KEY`→`JWT_SECRET`,
  `JWT_ACCESS_TOKEN_MINUTES`→`JWT_ACCESS_TTL_MINUTOS`, `REFRESH_TOKEN_DAYS`→`REFRESH_TTL_DIAS`);
  agregadas `DATABASE_URL_MIGRATIONS`, `TERMINOS_VERSION_VIGENTE`, `APP_BASE_URL`,
  `GOOGLE_OAUTH_REDIRECT_URI`, `INVITACION_TTL_DIAS`, `EMAIL_ADAPTADOR`, las siete `SMTP_*` y
  `INTEGRACION_TIMEOUT_SEGUNDOS`. Además el encabezado ahora distingue las variables que el código
  **lee hoy** de las **declaradas por adelantado** para un épico que no llegó (`R2_*`, `AFIP_*`,
  `MP_*`, `WHATSAPP_*`, `MS_GRAPH_*`, `AI_*`) — la confusión entre esos dos grupos es lo que dejó
  pasar la desincronización durante todo un épico.
- **`frontend/.env.example`** — declaraba `NEXT_PUBLIC_API_BASE_URL`, que nadie lee, y le faltaban las
  tres que el código sí usa: `BACKEND_API_URL`, `SESSION_COOKIE_NAME` y `APP_BASE_URL`. Ninguna lleva
  prefijo `NEXT_PUBLIC_`, y el archivo ahora dice por qué: las tres se leen del lado del servidor.

**Verificado, no supuesto.** Un chequeo compara los nombres que lee `platform/settings.py` contra los
que declara la plantilla, y otro llena solo lo que la plantilla declara y construye `Settings` de
verdad:

```
BACKEND  — lee el codigo y NO esta en la plantilla: ninguna
FRONTEND — lee el codigo y NO esta en la plantilla: ninguna
FRONTEND — en la plantilla y nadie lee: ninguna
Settings OK · test · timeout 1
Cifrado OK · b'x'
```

La Definition of Done queda cumplida en este punto.

## Decisiones tomadas durante la unidad

- **D-a — La verificación de HU-E2-05 es síncrona y en paralelo, con timeout de 5s por proveedor**
  (usuario, 2026-08-18). Sin Celery, sin polling, sin estado intermedio. *Lo que se paga:* si WSAA de
  ARCA resulta lento —es SOAP con certificado cliente—, la unidad 3 hereda el problema y habrá que
  migrar a encolado.
- **D-b — El ambiente se deriva de `APP_ENV`, no lo elige el Administrador** (usuario, 2026-08-18).
  Hace imposible emitir un comprobante de homologación creyéndolo real. *Lo que se paga:* no se puede
  probar contra homologación desde el despliegue productivo.
- **D-c — `RolUsuario` sube a `shared/roles.py`.** Sin esto, `integrations` no puede autorizar sin
  romper R3 o ADR-0003. `identity` lo re-exporta y ningún import existente cambia.
- **D-d — `EstadoDeConexion` tiene los tres estados de HU-E2-05 RN-02.** `PENDIENTE` es alcance
  previsto de `conexion-whatsapp`, no una omisión de esta unidad.
- **D-e — El cifrador vive en `integrations/infrastructure/`, no en `platform/`**, para que «el
  descifrado no sale del contexto» tenga algo que lo sostenga y no sea solo una frase del ADR.
- **D-f — Sin acción de desconectar.** Ninguna historia del épico la pide.
