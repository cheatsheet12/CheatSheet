# Unidad: cimientos-y-bitacora

**HUs**: HS-T5   **Contexto dueño**: observability   **Rama**: feature/infra-cimientos-y-bitacora

## Qué hace

Levanta el proceso donde vive todo lo demás y le da su primera tabla real. Al terminar, la API
responde `GET /health` contra una base migrada, cualquier contexto puede publicar un evento
auditable que queda persistido e inmutable en `registro_de_auditoria`, el aislamiento por
`tenant_id` está probado con RLS activa, hay un worker de Celery que ejecuta una tarea idempotente,
y el frontend tiene cascarón (layouts, BFF, cookie del JWT, sistema de diseño mínimo) donde montar
la primera pantalla.

No agrega **ninguna pantalla de negocio**: leer la bitácora es HU-E12-01, épico 10.

## Diseño

### Dominio (`contexts/observability/domain/`)

- **`RegistroDeAuditoria`** — agregado raíz, **inmutable por construcción**: atributos de solo
  lectura (`frozen`), sin métodos que muten estado y sin `update` en el repositorio. HS-T5 RN-03.
- Campos, uno por cada dato que exige HS-T5 RN-02: `id`, `tenant_id`, `modulo`, `operacion`,
  `entidad_afectada` (tipo + id), `iniciador`, `resultado`, `ocurrido_en`, `detalle`.
- **`Modulo`** — enum cerrado con los doce bounded contexts. Un módulo libre haría la bitácora
  infiltrable y no agrupable.
- **`Iniciador`** — value object: quién ejecutó. Tres formas — `USUARIO` (con `user_id`), `SISTEMA`
  (una tarea de Beat) y `AGENTE` (el canal conversacional). El épico 8 no tendrá que cambiar el
  agregado para caber.
- **`Resultado`** — enum `COMPLETADO` / `ERROR`. HS-T5 RN-04: se registra el fracaso igual que el
  éxito, así que el resultado es un campo, nunca la condición para escribir la fila.
- **`EventoDeDominio`** — clase base en `shared/`: `evento_id`, `ocurrido_en`, `tenant_id`. Es
  Shared Kernel porque los doce contextos van a emitir eventos; no pertenece a `observability`.

### Aplicación (`contexts/observability/application/`)

- **`RegistrarOperacion`** — único caso de uso. Entrada: un comando con los campos de RN-02.
  Salida: el `id` del registro. Garantiza que la fila se escribe una sola vez por evento
  (`evento_id` con índice único) y que nunca se modifica.
- **`ports.py`** — `PortRegistroDeAuditoria` con `agregar()` y `buscar_por_id()`. **No declara
  `actualizar` ni `eliminar`**: la inmutabilidad se expresa en el puerto, no en un comentario.

### Puertos y adaptadores

| Puerto | Adaptador | Dónde |
|---|---|---|
| `PortRegistroDeAuditoria` | Repositorio PostgreSQL (SQLAlchemy async + asyncpg) | `observability/infrastructure/` |
| `PortRelojDelSistema` | Reloj UTC real; en tests, uno fijo | `shared/` + `platform/` |

`shared/` declara el reloj porque la regla «la fecha se inyecta, nunca se lee del reloj adentro de
la lógica» (`backend/tests/README.md`) aplica a los doce contextos.

### Cómo publica un evento el resto del sistema

Este es el mecanismo que los nueve épicos siguientes van a usar, así que se decide acá y una vez:

- Cada contexto emite su evento de dominio a un **`PublicadorDeEventos`** declarado en `shared/`.
- `observability` registra un **suscriptor** en el composition root (`api/`) que traduce el evento a
  `RegistrarOperacion`. El emisor **no conoce a `observability`**: cumple R3 sin excepción, y la
  arista `all → observability` del Context Map queda implementada como OHS, no como import.
- La entrega es **síncrona y en la misma transacción** que la operación auditada. Es lo que hace que
  «se registra tanto la exitosa como la fallida» sea cierto: si la auditoría fuera asíncrona, una
  caída entre ambas perdería el registro, que es justamente el caso que hay que auditar. Cuando el
  volumen lo pida, se mueve a la cola de notificaciones — hoy no hay evidencia de que haga falta.

### Plataforma (`platform/`, `api/`, `workers/`)

- `platform/settings.py` — settings tipados desde el entorno (pydantic-settings). **Sin defaults
  para secretos**: si falta `DATABASE_URL`, el proceso no arranca.
- `platform/database.py` — engine async, `sessionmaker`, y el context manager que emite
  `SET LOCAL app.current_tenant` en cada transacción (ADR-002).
- `platform/telemetry.py` — logging estructurado JSON. `print()` está prohibido y lo bloquea ruff
  (T20).
- `api/main.py` — composition root: crea la app, arma las dependencias, registra el suscriptor de
  auditoría, monta el router de health. `api/errors.py` — manejador uniforme que traduce
  excepciones de dominio a respuestas HTTP sin filtrar internals.
- `api/middleware/tenant.py` — extrae el `tenant_id` del contexto autenticado y lo deja en el
  scope. Hoy no hay autenticación (es la unidad siguiente): lee un header solo habilitado fuera de
  producción, y el hueco queda marcado para `identidad-y-onboarding`.
- `workers/` — app de Celery, las cinco colas del ADR-003, Beat, y la tarea base con
  `ClaveDeIdempotencia` y reintentos con backoff exponencial + jitter (ADR-009). Se incluye **una**
  tarea de ejemplo (un no-op auditable) para que la infraestructura sea verificable; se borra cuando
  llegue la primera tarea real.

### Frontend (`frontend/src/`)

- `app/layout.tsx` raíz + `app/(public)/layout.tsx` y `app/(panel)/layout.tsx`.
- `lib/session.ts` — lectura y escritura de la cookie **HttpOnly, Secure, SameSite=Lax** del JWT.
  El token nunca llega al bundle del cliente (ADR-011).
- `lib/api.ts` — wrapper de `fetch` con timeout, manejo de error tipado y reenvío de la cookie.
- `app/api/health/route.ts` — primer route handler del BFF: prueba de extremo a extremo de que el
  navegador llega al backend sin ver su URL.
- `shared/` — tokens de diseño (color, tipografía, espaciado), `Button`, `Card`, `Alert`. Lo mínimo
  para que la primera pantalla sea una pantalla. Ningún `features/*` se toca en esta unidad.

## Infraestructura

### Migraciones

Alembic con `backend/migrations/env.py` apuntando al metadata de SQLAlchemy. Una sola migración:

- Extensiones `pgvector` y `btree_gist` (se instalan ahora, se usan en los épicos 4 y 7).
- Rol de aplicación **no propietario** de las tablas. Es un requisito técnico, no una preferencia:
  PostgreSQL **saltea RLS para el dueño de la tabla**, así que sin esto la política existiría y no
  se aplicaría nunca.
- Tabla `registro_de_auditoria` con `tenant_id`, `ENABLE ROW LEVEL SECURITY`, **`FORCE ROW LEVEL
  SECURITY`** y la política `USING (tenant_id = current_setting('app.current_tenant')::uuid)`.
- Sin `UPDATE` ni `DELETE` para el rol de aplicación sobre esa tabla: la inmutabilidad de HS-T5
  RN-03 se garantiza en la base, no solo en el agregado.
- Reversible (`downgrade` real). Sin backfill: no hay datos.

### Trabajo asíncrono

Celery + Beat, cinco colas (`integrations_sync`, `spreadsheet_processing`, `incremental_sync`,
`notifications`, `ai_nlp`). Tarea base con `ClaveDeIdempotencia` = empresa + tipo + huella del
payload; reintentos con backoff exponencial y jitter. **La DLQ no entra acá** (HS-T6, épico 4): al
agotar reintentos se registra el fallo en la bitácora y se deja el hueco marcado.

### Configuración

Variables nuevas en `backend/.env.example`: `DATABASE_URL`, `DATABASE_URL_MIGRATIONS`, `REDIS_URL`,
`APP_ENV`, `LOG_LEVEL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`. En `frontend/.env.example`:
`BACKEND_API_URL`, `SESSION_COOKIE_NAME`. Ningún valor real: solo la forma.

`backend/docker-compose.yml` con PostgreSQL 16 y Redis 7 para desarrollo local. Va dentro de
`backend/` y no en la raíz porque levanta las dependencias de **un** proceso (CLAUDE.md §2.3); el
frontend no las necesita.

### Integraciones externas

**No aplica.** Esta unidad no habla con ningún proveedor. La primera es ARCA, en el épico 2.

### Dependencias que se agregan

A `backend/pyproject.toml` (fijadas): `fastapi`, `uvicorn[standard]`, `pydantic-settings`,
`sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `celery[redis]`, `redis`, `structlog`. A
`requirements-dev.txt`: `pytest-asyncio`, `httpx`.

### CI — dos arreglos necesarios

Se descubrieron leyendo el pipeline, y sin ellos el Gate 2 sería falso:

1. El job `tests` instala `requirements-dev.txt` y un `requirements.txt` de raíz que **no existe ni
   puede existir** (el hook `guard_edit.py` lo prohíbe: las dependencias de aplicación van en
   `backend/`). Sin cambio, ninguna dependencia del backend se instala y todo test que importe
   `fastapi` falla. → pasa a `pip install -e backend/`.
2. El job `tests` no tiene base de datos. → se le agrega un `services: postgres:16` y las migraciones
   se aplican antes de correr `pytest`.

**Un Postgres local no viola «los tests nunca tocan la red».** Esa regla es sobre proveedores
externos — ARCA, MercadoPago, WhatsApp, el LLM —, que son los que hacen los tests lentos, flaky y
dependientes de credenciales. RLS **no se puede probar sin una base real**: es una característica del
motor. Probarlo contra SQLite sería un test que pasa siempre y no verifica nada.

## Riesgos que obligan a tests

- [x] Toca dinero → **no aplica** en esta unidad.
- [x] Toca comprobantes fiscales / CAE → **no aplica**.
- [x] Consume un webhook → **no aplica**.
- [x] **Agrega datos con `tenant_id`** → test de aislamiento entre tenants. Es la primera tabla del
      sistema: si RLS no funciona acá, no funciona en ninguna de las 27 que vienen.
- [x] Usa salida de un LLM → **no aplica**.
- [x] Datos personales o fiscales → la bitácora guarda `user_id`, nunca contenido personal en
      `detalle`. Se verifica en revisión, no hay test automático posible.

Riesgo propio de esta unidad, no listado en la plantilla: **la inmutabilidad** (HS-T5 RN-03) tiene
que probarse en los dos niveles — que el agregado no expone mutación y que la base rechaza el
`UPDATE`. Un solo nivel deja la garantía en el aire.

## Archivos a tocar

**Backend — plataforma**
- [x] `backend/pyproject.toml` (dependencias) · `requirements-dev.txt`
- [x] `backend/src/cheatsheet/platform/{settings,database,telemetry}.py`
- [x] `backend/src/cheatsheet/shared/{tenant,events,clock}.py`
- [x] `backend/src/cheatsheet/api/{main,errors,dependencies}.py` · `api/routers/health.py`
- [x] `backend/src/cheatsheet/api/middleware/tenant.py`
- [x] `backend/src/cheatsheet/workers/{celery_app,beat}.py` · `workers/base.py`
- [x] `backend/migrations/{env.py,alembic.ini,versions/0001_*.py}`
- [x] `backend/docker-compose.yml` · `backend/.env.example`

**Backend — observability**
- [x] `contexts/observability/domain/{registro_de_auditoria,modulo,iniciador,resultado}.py`
- [x] `contexts/observability/application/{registrar_operacion,ports}.py`
- [x] `contexts/observability/infrastructure/{repository,subscriber,models}.py`

**Backend — tests**
- [x] `backend/tests/conftest.py` (fixtures de base, factories, dobles, reloj fijo)
- [x] `backend/tests/contexts/observability/{domain,application,infrastructure}/`
- [x] `backend/tests/api/test_health.py` · `backend/tests/platform/test_tenant_isolation.py`

**Frontend**
- [x] `frontend/next.config.mjs` · `frontend/.env.example`
- [x] `frontend/src/app/layout.tsx` · `app/(public)/layout.tsx` · `app/(panel)/layout.tsx`
- [x] `frontend/src/app/api/health/route.ts`
- [x] `frontend/src/lib/{session,api}.ts` · `frontend/src/shared/**`
- [x] `frontend/src/**/__tests__/`

**Repositorio**
- [x] `.github/workflows/ci.yml` (los dos arreglos de arriba)

## Casos de prueba

Los 14 planificados, más los que aparecieron al escribir el código. **84 tests en total**
(47 de Python, 37 de TypeScript).

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | `RegistroDeAuditoria` no expone ninguna forma de mutar sus campos | unit | ✅ |
| 2 | Un evento con resultado `ERROR` se persiste igual que uno `COMPLETADO` (RN-04) | unit | ✅ |
| 3 | `RegistrarOperacion` captura los seis campos de RN-02 | unit | ✅ |
| 4 | Dos entregas del mismo `evento_id` producen **una** fila | integración | ✅ |
| 5 | Un `UPDATE` directo sobre `registro_de_auditoria` es rechazado por la base (RN-03) | integración | ✅ |
| 6 | Con `app.current_tenant` = A, no se ve ninguna fila del tenant B | integración | ✅ |
| 7 | Sin `app.current_tenant` seteado, la consulta no devuelve nada (falla cerrada) | integración | ✅ |
| 8 | Publicar un evento de dominio desde un contexto cualquiera deja su registro | unit | ✅ |
| 9 | `GET /health` responde 200 y reporta el estado de base y Redis | integración | ✅ |
| 10 | Una excepción de dominio se traduce a HTTP sin filtrar el stacktrace | integración | ✅ |
| 11 | La tarea base no repite efecto ante la misma `ClaveDeIdempotencia` | unit | ✅ |
| 12 | La migración `0001` aplica y revierte limpio | integración | ✅ |
| 13 | El wrapper de `fetch` propaga la cookie y corta por timeout | unit (vitest) | ✅ |
| 14 | El route handler de health no expone la URL del backend al cliente | unit (vitest) | ✅ |

Agregados durante la implementación, cada uno porque el código mostró un hueco:

| # | Caso | Por qué se agregó |
|---|---|---|
| 15 | Un `DELETE` de la aplicación es rechazado por la base | RN-03 tiene dos verbos, no uno |
| 16 | El rol de aplicación tiene exactamente `SELECT` e `INSERT` | Verifica el grant, no su efecto |
| 17 | La tabla tiene RLS `ENABLE` **y** `FORCE` | `ENABLE` solo deja al dueño exento: el modo de falla silencioso |
| 18 | `WITH CHECK`: declarar un tenant e insertar la fila de otro es rechazado | La política sin `WITH CHECK` filtra lecturas pero no escrituras |
| 19 | El `tenant_id` no sobrevive a la transacción | Una conexión del pool que arrastra el tenant anterior es la fuga clásica |
| 20 | La falla de un suscriptor propaga al emisor | Si se tragara la excepción habría operaciones sin registrar |
| 21 | Un evento **no** auditable pasa de largo | El mismo bus va a llevar `PagoConfirmado` |
| 22 | En producción el header `X-Tenant-Id` se ignora | El atajo de desarrollo no puede sobrevivir a un deploy |
| 23 | Un registro persistido se relee idéntico | El mapeo a mano en los dos sentidos es donde se esconden los bugs |
| 24 | Las doce features exponen su `index.ts` (R5) | ESLint solo ve el import profundo, nunca el barril faltante |
| 25 | La cookie de sesión es HttpOnly, SameSite=Lax y Secure en producción | Son propiedades de seguridad, no preferencias |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-12 | aprobado sin cambios |
| 2 · Verificación | 2026-08-12 | ver abajo — todos los gates locales en verde, con dos pendientes declarados |
| 3 · PR | | |

### Gate 2 — resultado real

```
ruff format --check .   111 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 106 source files
pytest --cov            47 passed · cobertura 89.60% (umbral 80%)
guard_architecture      112 file(s) checked — architecture boundaries intact
test_guards.sh          54 cases, all correct — the guards are active

frontend format:check   All matched files use Prettier code style!
frontend lint           No ESLint warnings or errors
frontend typecheck      tsc --noEmit sin errores
frontend test:coverage  37 passed · 92.52% líneas / 87.80% ramas (umbral 80%)
```

Los 12 tests de integración corrieron contra PostgreSQL 16 real
(`docker compose -f backend/docker-compose.yml up -d`), no salteados.

**Dos cosas que NO pude verificar y no voy a dar por buenas:**

1. `gitleaks` no está instalado en la máquina local. Los valores `test-only-…` de
   `docker-compose.yml`, `init-db.sql` y el workflow son placeholders de contenedores
   descartables, pero la verificación queda a cargo del job `secret-scan` de CI.
2. `backend/.env.example` y `frontend/.env.example` **no pudieron editarse**: el
   entorno de trabajo tiene denegado el acceso a esos archivos. Las variables nuevas
   están listadas abajo y hay que agregarlas a mano antes del PR.

## Decisiones tomadas durante la unidad

- **D1 (mapa)** → validación estructural del CUIT en el épico 1; padrón de ARCA en el épico 2. No
  afecta a esta unidad, sí a la siguiente.
- **Granularidad** → el usuario pidió unidades gruesas: menos análisis, más ejecución. De ahí que
  las seis unidades técnicas del roadmap §5 y HS-T5 vayan en un solo Gate.
- **Auditoría síncrona y en la misma transacción** → decidido acá, aplica a los nueve épicos
  siguientes. Justificación arriba.
- **Postgres real en los tests** → decidido acá. RLS no es verificable de otra forma.

## Desvíos respecto del plan aprobado

Cuatro, todos descubiertos al escribir el código y ninguno que cambie el alcance.

1. **`Modulo`, `Iniciador`, `Resultado`, `EntidadAfectada` y `EventoAuditable` viven en `shared/`,
   no en `observability/domain/`.** El plan los ponía en el dominio del contexto. Escribirlo lo
   desmintió: la regla R3 prohíbe que `billing/domain` importe `observability/domain`, así que con
   los enums ahí **ningún contexto podría emitir un evento auditable** — el hook bloquearía la
   escritura. Son value objects entre contextos (`Modulo` es literalmente la lista de los doce), que
   es exactamente lo que CLAUDE.md §2 dice que guarda el Shared Kernel. El agregado se quedó donde
   estaba.
2. **`Settings` no usa pydantic-settings.** Un dataclass congelado leyendo `os.environ` cumple lo
   mismo —tipado, sin defaults para secretos, falla al arrancar— y deja `platform/` sin depender de
   un framework de validación. Menos piezas en el piso sobre el que se para todo lo demás.
3. **El suscriptor de auditoría se arma por request, no una vez al arrancar.** El plan decía
   "registrar el suscriptor en el composition root". El composition root lo hace
   (`api/dependencies.py::construir_publicador`), pero **por unidad de trabajo**: el registro de
   auditoría tiene que caer en la misma transacción que la operación, y un publicador global le
   daría a cada request un suscriptor escribiendo en la sesión de otro.
4. **`docker-compose` publica 5433 y 6380, no 5432 y 6379.** Un desarrollador con PostgreSQL nativo
   ya ocupa el 5432, y la falla es fea: `localhost` resuelve al servidor nativo, que contesta y
   después dice que el rol no existe — se lee como un bug de aprovisionamiento y no como un choque
   de puertos. En CI los puertos son los estándar porque ahí no hay con qué chocar.

## Hallazgos de configuración del repositorio

Cinco defectos preexistentes que este trabajo destapó. Los tres primeros hacían que un gate
reportara verde sin haber verificado nada, que es peor que fallar.

| # | Qué estaba mal | Consecuencia | Arreglo |
|---|---|---|---|
| 1 | El paquete `cheatsheet` no publicaba `py.typed` | mypy trataba nuestro propio código como librería sin tipos: **cada import del backend degradaba a `Any`** y `--strict` no verificaba nada | `backend/src/cheatsheet/py.typed` + `artifacts` en el pyproject del backend |
| 2 | `[[tool.mypy.overrides]] module = ["tests.*"]` no aplicaba, y le faltaba `disallow_incomplete_defs` | Los tests fallaban el gate de tipos por no anotar `-> None` | Ambos nombres de módulo declarados, y las dos flags |
| 3 | `per-file-ignores` de ruff apuntaba a `tests/**`, pero la suite vive en `backend/tests/**` | El patrón no matcheaba nunca; pasó inadvertido mientras todos los archivos se llamaban `test_*.py` | `**/tests/**/*.py` |
| 4 | El job `typecheck` de CI no instalaba el paquete backend | `import fastapi` sin resolver → mypy habría fallado en cada módulo | `pip install -e backend/` |
| 5 | El job `tests` de CI instalaba un `requirements.txt` de raíz que no existe **y que el hook `guard_edit.py` prohíbe crear**, y no tenía base de datos | Ninguna dependencia del backend instalada; los tests de integración se habrían salteado en silencio | `pip install -e backend/`, servicios `postgres:16` y `redis:7`, migraciones antes de correr, y un paso que **falla si los tests de integración se saltearon** |

## Pendiente antes del PR — acción del usuario

Los dos `.env.example` no pude editarlos (acceso denegado en este entorno). Hay que agregar, sin
valores:

```bash
# backend/.env.example
APP_ENV=
DATABASE_URL=
DATABASE_URL_MIGRATIONS=
REDIS_URL=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
LOG_LEVEL=
```

```bash
# frontend/.env.example
BACKEND_API_URL=
SESSION_COOKIE_NAME=
```

Para desarrollo local, con `docker compose -f backend/docker-compose.yml up -d`:

```bash
DATABASE_URL=postgresql+asyncpg://cheatsheet_app:test-only-local-container@localhost:5433/cheatsheet
DATABASE_URL_MIGRATIONS=postgresql+asyncpg://cheatsheet_owner:test-only-local-container@localhost:5433/cheatsheet
REDIS_URL=redis://localhost:6380/0
```
