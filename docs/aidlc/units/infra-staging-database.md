# Unidad: infra-staging-database

**HUs**: ninguna — trabajo de entorno   **Contexto dueño**: ninguno (`platform` + operaciones)
**Rama**: `feature/infra-staging-database`

> **Por qué esta unidad existe sin HU detrás, y por qué no está en `units.md`.**
> La escalada del workflow manda frenar ante «trabajo sin historia de usuario», salvo que sea una
> *unidad técnica declarada en el roadmap*. Esta no lo es, y aun así no es análisis: el entorno
> `staging` ya está **decidido** en [`docs/configuration-management.md`](../../configuration-management.md)
> §5 y §7 — existe, es compartido, es donde se demuestra, y provisionarlo es responsabilidad
> declarada del Arquitecto de Software. Esto **ejecuta** ese insumo; no lo re-decide.
> Por eso tampoco se agrega una fila a [`units.md`](../units.md): ese mapa ata unidades a épicos del
> roadmap por el nombre del épico, y `.claude/hooks/aidlc_next.py` lee esa correspondencia. Una fila
> con un épico inventado rompería el mapa. El plan vive acá porque es donde se buscan los planes.

---

## Qué hace

Deja existiendo y **verificada** la base de datos PostgreSQL de `staging` en Neon: extensiones
instaladas, los dos roles con la separación que el RLS necesita, las tres migraciones aplicadas, y
una prueba real de que una empresa no ve las filas de otra corriendo contra esa base y no contra un
contenedor local.

No levanta la aplicación en staging: eso necesita además Redis y un lugar donde corra el proceso.
Esta unidad deja la base lista y dice, con nombre y apellido, qué falta.

---

## Diseño

- **Dominio**: no aplica. No se crea ni se cambia ningún agregado.
- **Aplicación**: no aplica.
- **Puertos y adaptadores**: no aplica.
- **Otros contextos**: no aplica.
- **Frontend**: no aplica.

Se escribe **tooling de operaciones** (`backend/scripts/`) y **documentación**. Ni una línea
dentro de `contexts/`.

**Una excepción, agregada durante la implementación:** `platform/database.py` gana
`argumentos_de_conexion()`, que decide el TLS a partir del host. El plan original decía que no se
tocaba código de aplicación; conectarse a Neon con el certificado verificado resultó imposible desde
la URL. El detalle y el porqué están más abajo y en las Decisiones.

---

## La decisión de fondo, y la trampa que la hace no-trivial

Neon es PostgreSQL gestionado con separación de storage y compute. Lo que lo vuelve delicado para
**este** repositorio es una sola cosa:

> **Todo rol creado desde la consola, la API o el CLI de Neon recibe membresía en `neon_superuser`,
> y `neon_superuser` tiene `BYPASSRLS`.**

Si `cheatsheet_app` se crea desde la consola, hereda `BYPASSRLS`, **todas las políticas de
`aislamiento_por_empresa` dejan de dispararse**, y no pasa nada visible: la app funciona, los tests
locales siguen en verde contra el contenedor, y staging le sirve los datos de una empresa a otra. Es
exactamente el modo de falla que `platform/database.py` y la migración 0001 fueron escritas para
impedir, reintroducido por la vía del aprovisionamiento.

**Regla de esta unidad, entonces:** `cheatsheet_app` **se crea únicamente por SQL**. Los roles
creados con `CREATE ROLE` en Neon reciben solo privilegios básicos del esquema público, sin
`neon_superuser` y sin `BYPASSRLS`. Y no se confía en que eso salió bien: se verifica.

### Reparto de roles y endpoints

| Variable | Rol | Endpoint | Se usa para |
|---|---|---|---|
| `DATABASE_URL_MIGRATIONS` | `neondb_owner` (el que crea Neon con el proyecto; miembro de `neon_superuser`) | **directo** | `alembic upgrade head`, `CREATE EXTENSION`, dueño de las tablas |
| `DATABASE_URL` | `cheatsheet_app` (creado por SQL, no dueño de nada) | **directo** | la aplicación; sujeto a RLS |

**Endpoint directo, no el pooled (`-pooler`), en staging.** Dos razones: la documentación de Neon
pide conexión directa para migraciones, y el pooler es PgBouncer en modo transacción, cuya
interacción con los *prepared statements* de asyncpg es una clase de problema conocida que no vale
la pena estrenar en el entorno donde se hace la demo. Nada impide moverse al pooler después: sería
el host con `-pooler` más `prepared_statement_cache_size=0` en la URL. Se deja anotado, no se hace
ahora.

Dato a favor, que conviene saber: `sesion_de_empresa` usa `set_config(..., true)`, que es
**transaccional**, no de sesión. Es justo lo que el modo transacción de PgBouncer sí soporta. La
migración al pooler, el día que se haga, no rompe el aislamiento.

### El formato de la URL — donde esto se rompe la primera vez

La cadena que Neon da para copiar termina en `?sslmode=require&channel_binding=require`. El dialecto
`asyncpg` de SQLAlchemy **reenvía todo query param de la URL como kwarg a `asyncpg.connect()`**, y
asyncpg no acepta ni `sslmode` ni `channel_binding`: acepta `ssl`. Pegar la cadena de Neon tal cual
falla con `TypeError` antes de abrir el socket, tanto en la app como en Alembic (`env.py` usa el
mismo driver).

La forma correcta, y la única que se documenta — **sin query string, ninguno**:

```
postgresql+asyncpg://<rol>:<password>@<endpoint>.sa-east-1.aws.neon.tech/neondb
```

El TLS **no desaparece: se decide en código**. `argumentos_de_conexion()` en `platform/database.py`
le da a todo host que no sea local un `ssl.create_default_context()` —almacén de CA de la
plataforma, `check_hostname` prendido, `CERT_REQUIRED`— y a `localhost` nada.

Va ahí y no en la URL porque **las dos formas de escribirlo en la cadena son trampas**, y esto se
descubrió chocándose contra ellas el 2026-08-21, no razonándolo antes:

- `?ssl=verify-full` **no usa el almacén del sistema**. asyncpg imita a libpq: busca el CA en
  `~/.postgresql/root.crt` o en `PGSSLROOTCERT`, y si no está tira `ClientConfigurationError`. Anda
  en la máquina que alguien configuró y en ninguna otra.
- `?ssl=require` es peor: sin archivo de CA cae a `CERT_NONE` en silencio
  (`asyncpg/connect_utils.py`, rama `sslmode == SSLMode.require`). Cifra y nunca identifica al
  servidor — la falla que se ve igual que el éxito.

Un contexto verificado solo se le puede pasar a asyncpg como objeto, por `connect_args`, y un objeto
no entra en una URL. Si queda un parámetro de TLS en la cadena, `argumentos_de_conexion` **se niega
a construir la conexión** y lo nombra, en lugar de dejar que SQLAlchemy lo reenvíe y el `TypeError`
salga de adentro del driver.

---

## Infraestructura

- **Migraciones**: ninguna nueva. Se **aplican** las tres existentes (0001, 0002, 0003) contra Neon.
  Reversibles: sí, ya lo son. Backfill: no aplica, la base arranca vacía.
- **Trabajo asíncrono**: no aplica. Celery no se despliega en esta unidad (necesita Redis).
- **Configuración**: **ninguna variable nueva.** `DATABASE_URL` y `DATABASE_URL_MIGRATIONS` ya
  existen en `platform/settings.py` y en `backend/.env.example`. Cambia el **valor** en staging, no
  el contrato — así que no hay que tocar los `.env.example` (que además están denegados por permisos
  en mi entorno, ver [`TODO.md`](../TODO.md) §1.1). Los valores reales viajan por canal privado,
  `configuration-management.md` §4.3.
- **Integraciones externas**: Neon como proveedor de PostgreSQL gestionado para staging. No es una
  integración de la aplicación (no hay cliente, ni timeout, ni reintentos que escribir): es dónde
  vive el motor. Se registra en un ADR.

### Qué se crea en Neon (lo hacés vos por consola; yo te guío paso a paso)

1. Proyecto `CheatSheet - staging`, PostgreSQL **16** — el mismo motor mayor que el contenedor
   local y que CI. Con versiones distintas el SQL deja de ser comparable entre entornos.
2. Región **`sa-east-1` (São Paulo)**, la más cercana a Argentina que ofrece la consola.
3. **`Neon Auth` apagado.** Instala autenticación con sus propias tablas de usuarios y sesiones
   dentro de la base, y el contexto `identity` ya responde esa pregunta (ADR-011). Es el mismo
   motivo por el que se descartó Supabase.
4. La base y el rol dueño quedan con los nombres que pone Neon: **`neondb`** y **`neondb_owner`**.
   El onboarding no deja elegirlos, nada en el código tiene el nombre de la base hardcodeado, y lo
   que importa no es el nombre sino la separación de roles del paso siguiente.
5. Nada más. **`cheatsheet_app` no se crea desde la consola.** Ese es el punto entero.

---

## Archivos a tocar

- [x] `backend/scripts/provision_app_role.py` — crea `cheatsheet_app` por SQL, le da LOGIN con la
      password leída del entorno (nunca literal en el repo ni en la línea de comandos) y `CONNECT`
      sobre la base, y **se niega a reportar éxito si el rol puede evadir RLS**. Hermano de
      `init-db.sql`, no reemplazo: aquel es para el contenedor descartable, este para una base real
      cuya password no vive acá.
- [x] `backend/scripts/verify_rls.py` — el verificador. Detalle abajo.
- [x] `docs/staging-database.md` — el runbook, en inglés: pasos de consola, SQL a correr, formato de
      las URLs, cómo verificar, y qué falta para que staging levante entero.
- [x] `docs/adr/0005-staging-database-neon.md` — la decisión y sus consecuencias.
- [x] `.github/workflows/ci.yml` — dos pasos que ejercitan el verificador contra el Postgres del job.
- [x] `backend/src/cheatsheet/platform/database.py` — `argumentos_de_conexion()`. **Fuera del plan
      original**, ver Decisiones.
- [x] `backend/migrations/env.py` — usa la misma función: Alembic cruza la misma red, con la
      credencial del dueño.
- [x] `backend/tests/platform/test_database_tls.py` — 8 casos sobre esa función.

### El verificador, que es el corazón de la unidad

`backend/scripts/verify_rls.py`, autónomo: **no importa nada de `cheatsheet.*`**, así que no cruza
ninguna frontera de R1–R5. Abre las dos conexiones —dueño y aplicación— y **sale con código distinto
de cero** si cualquiera de estas no se cumple.

Conecta con **SQLAlchemy y no con asyncpg pelado**, aunque asyncpg alcanzaría. La razón es que así
lee las URLs en el mismo formato exacto que usa la aplicación: una cadena de conexión que la app
rechazaría —la de Neon pegada tal cual, con `sslmode` y `channel_binding`— falla acá primero, que es
donde alguien la puede leer. Con asyncpg directo habría que traducir la URL, y esa traducción sería
un segundo lugar donde el formato puede divergir del real.

| # | Qué comprueba | Por qué |
|---|---|---|
| 1 | `cheatsheet_app` no tiene `rolsuper` ni `rolbypassrls` | La trampa de Neon, comprobada de frente |
| 2 | `cheatsheet_app` no es miembro de `neon_superuser` | La misma trampa por la otra puerta: se hereda |
| 3 | `cheatsheet_app` no es dueño de ninguna tabla de `public` | El dueño está exento de sus propias políticas |
| 4 | Toda tabla con `empresa_id` tiene RLS **y** `FORCE`, y al menos una política | `ENABLE` solo no alcanza |
| 5 | Sobre `registro_de_auditoria`: tiene `SELECT`/`INSERT`, **no** `UPDATE`/`DELETE` | HS-T5 RN-03: la bitácora es append-only en el motor |
| 6 | `vector` y `btree_gist` instaladas | Los épicos 7 y 8 dependen de ellas, y la app no podrá instalarlas después |
| 7 | `alembic_version` está en la última revisión | Que la base sea la que el código espera |
| 8 | **Sonda viva**: el dueño inserta dos filas de auditoría bajo dos `empresa_id` de descarte; la app, declarando una sola empresa, ve exactamente una; sin declarar empresa, ve cero. El dueño borra las dos | Los checks 1–7 miran metadatos. Este mira el comportamiento, que es lo que importa |

La sonda limpia lo que ensucia, y el borrado lo hace el **dueño** justamente porque la app no tiene
`DELETE` sobre esa tabla. Si el script muriera a la mitad quedarían dos filas huérfanas con UUIDs de
descarte: es un costo aceptable, y queda dicho.

**Se corre también en CI**, contra el contenedor del job `tests`. No es ceremonia: un verificador que
nadie ejecuta se pudre en silencio y da verde el día que dejó de comprobar algo — que es exactamente
por lo que el pipeline ya verifica que la regla R5 de ESLint sigue disparando.

---

## Riesgos que obligan a tests

- [ ] Toca dinero → no
- [ ] Toca comprobantes fiscales / CAE → no
- [ ] Consume un webhook → no
- [x] **Agrega datos con `empresa_id` → test de aislamiento entre empresas.** No agrega tablas, pero
      la unidad entera *es* el riesgo: un aprovisionamiento mal hecho apaga el aislamiento de las
      cuatro tablas que ya existen. El check 8 del verificador es ese test, y corre en CI.
- [ ] Usa salida de un LLM → no
- [x] **Datos personales o fiscales**: staging lleva datos de prueba controlados por el Analista de
      QA (`configuration-management.md` §5). **Ningún dato real de una empresa piloto entra acá.**

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | `verify_rls.py` da verde contra el Postgres de CI | integración (CI) | **pendiente** — corre en el PR |
| 2 | `verify_rls.py` da rojo si `cheatsheet_app` recibe `BYPASSRLS` | integración (CI) | **pendiente** — corre en el PR |
| 3 | `verify_rls.py` da verde contra la base de Neon | manual, una vez | **OK 2026-08-21**, las 8 |
| 4 | `alembic upgrade head` aplica 0001→0003 sobre Neon sin error | manual, una vez | **OK 2026-08-21** |
| 5 | La app conecta a Neon con TLS verificado (healthcheck en verde) | manual, una vez | **parcial** — ver abajo |
| 6 | `argumentos_de_conexion()`: TLS por host, timeout, y rechazo de parámetros en la URL | unit | **OK**, 9 casos |

**El caso 5, dicho con precisión:** la conexión con TLS verificado quedó probada — los dos scripts y
Alembic conectaron a Neon con `ssl.create_default_context()` y sin ningún parámetro de TLS en la
URL. Lo que **no** se probó es el healthcheck del proceso FastAPI, porque el proceso no arranca sin
`REDIS_URL` y Redis quedó fuera de alcance. Queda como pendiente de la unidad que provisione Redis,
no de esta.

El caso 2 es el que impide que el verificador se vuelva decorativo: se le da `BYPASSRLS` al rol, se
comprueba que el script falla, y se lo revoca. Mismo patrón que el fixture de R5 en el job de
frontend.

---

## Lo que esta unidad NO deja funcionando

Dicho de frente, para que nadie lo descubra durante la demo:

- **Redis.** `Settings.desde_entorno` exige `REDIS_URL`: sin él el proceso **no arranca**. Fuera de
  alcance por decisión tuya. Staging no levanta hasta que exista.
- **Dónde corren el backend y el frontend de staging.** Esta unidad deja la base, no el cómputo.
- **Los workers de Celery**, y por lo tanto el email de invitación ([`TODO.md`](../TODO.md) §2.3).
- **Aplicar migraciones automáticamente.** En staging se corren a mano, desde una máquina con
  `DATABASE_URL_MIGRATIONS` en el entorno. Automatizarlo es un workflow de despliegue, y lo
  descartaste del alcance.
- **Las credenciales.** No entran al repositorio en ninguna forma. Viajan por canal privado.

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-21 | **aprobado** |
| 2 · Verificación | 2026-08-21 | **en verde**, incluida la base real de Neon. Detalle abajo |
| 3 · PR | | |

---

## Decisiones tomadas durante la unidad

- ¿Cómo se provisiona Neon? → **Por consola, guiado**; el SQL lo aporta el repositorio (2026-08-21).
- ¿Qué queda versionado? → **Provisión + verificación + ADR**, sin workflow de despliegue (2026-08-21).
- ¿Redis? → **Fuera de alcance**, declarado como bloqueante de staging (2026-08-21).
- ¿La conexión lleva timeout explícito? → **Sí, 10 s**, en `argumentos_de_conexion()` (2026-08-21).
  Faltaba, y era una violación de `CLAUDE.md` §5: sin timeout el llamador no distingue «la base
  está lenta» de «la base no está», y espera el default de asyncpg. No son 2 segundos porque Neon
  despierta el compute suspendido en la primera conexión.
- ¿Cómo se configura el TLS contra Neon? → **En código, no en la URL** (2026-08-21). El plan decía
  `?ssl=verify-full` en la cadena de conexión; contra Neon eso falla, porque asyncpg pide un archivo
  de CA que no existe en Windows, y el fallback obvio (`require`) deja de validar el certificado sin
  avisar. Se agregó `argumentos_de_conexion()` a `platform/database.py`, usada por la app, por
  Alembic y por los dos scripts. **Es la única parte de esta unidad que toca código de aplicación**,
  contra lo que decía el plan, y se decidió con el usuario. Tiene tests propios en
  `backend/tests/platform/test_database_tls.py`.
- ¿La provisión en `.sql` para `psql` o en Python? → **Python** (2026-08-21). Se planificó como
  `provision-neon.sql`, pero `psql` no está instalado en la máquina del responsable y el paso
  siguiente —`alembic upgrade head`— ya exige el entorno de Python igual. Pedir un cliente de
  PostgreSQL para un solo comando agrega una dependencia que no compra nada. Efecto lateral bueno:
  la password se lee del entorno y no de la línea de comandos, así que no queda en el historial
  del shell.
- ¿Pooler o endpoint directo? → **Directo**, por las migraciones y por no estrenar PgBouncer +
  asyncpg en el entorno de la demo. Queda documentado cómo migrar al pooler (2026-08-21).
