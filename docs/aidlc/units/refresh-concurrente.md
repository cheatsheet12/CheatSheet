# Unidad: refresh-concurrente

**HUs**: HU-E1-01 (la detección de reuso de ADR-011 que esa historia entregó)   **Contexto dueño**: identity   **Rama**: fix/identity-refresh-concurrente

> Origen: pregunta P3 de [`revocacion-por-reuso`](revocacion-por-reuso.md), decidida como «unidad aparte
> con su propio test de concurrencia». Es un `fix/…` **apilado** sobre `fix/identity-revocacion-por-reuso`
> (cortado de `0a53e23`, PR #47, todavía sin mergear en `develop`): depende del arreglo «escribir y después
> levantar» de `_rotar_refresh`, porque la revocación que esta unidad agrega bajo concurrencia tiene que
> confirmarse igual que la de #47. Ver P4 para cómo corre la CI mientras #47 no se mergea.

## Qué hace

La rotación de refresh tokens (ADR-011) supone que **cada token se usa una sola vez**, pero esa garantía
solo vale si los requests llegan de a uno. Dos requests simultáneos con el mismo refresh leen los dos el
token «sin usar», rotan los dos y la familia queda con **dos hijos vivos**: el reuso nunca se detecta y el
ladrón y la víctima siguen rotando cada uno por su lado, para siempre. Esta unidad **serializa por familia**
todo lo que lee y después escribe tokens de una familia (refresh y logout), de modo que el segundo request
espere al primero y vea el token ya usado.

Comportamiento observable después del fix: de dos refresh simultáneos con el mismo token, **uno** rota
(200) y el otro responde el error de reuso de siempre (409 `ReusoDeRefreshDetectado`), y **toda la familia
queda revocada**, incluido el hijo que el primero acaba de emitir. Lo mismo vale si el reuso o el logout
llegan mientras otro request está rotando el token siguiente de la familia: ningún token emitido en esa
ventana sobrevive a la revocación. Los contratos HTTP no cambian.

**Fuera de esta unidad:**
- La carrera entre la desactivación de un usuario (`revocar_de_usuario`, HU-E1-06) y una rotación: el hijo
  que escapa no puede volver a refrescar porque `RefrescarSesion` rechaza al usuario inactivo
  (`sesiones.py:161-163`). Lo que queda vivo es el access token, y eso es de
  `revocacion-inmediata-de-sesion`.
- Coordinar refresh legítimos simultáneos en el navegador (varias pestañas): es del frontend y hoy no existe
  ningún refresh automático (ver P3).
- Cambiar `sesion_de_empresa` / `unidad_de_trabajo`, o el nivel de aislamiento (sigue READ COMMITTED).

## La historia

HU-E1-01 — «Registrar empresa e iniciar sesión». Descripción, textual:

> Como nuevo usuario, quiero registrarme en CheatSheet con email y contraseña o con mi cuenta de Google,
> para acceder a la plataforma y comenzar a configurar mi empresa.

Criterio de aceptación relacionado, textual: «Ingreso credenciales correctas en el login | El sistema inicia
sesión y me redirige al dashboard o al paso pendiente del onboarding».

**La historia no tiene ninguna regla de negocio sobre refresh ni reuso** (sus RN-01 a RN-04 tratan sobre la
contraseña, Google, el email duplicado y la redirección al onboarding). La regla viene de ADR-011, que vive
en los documentos de diseño de la Etapa 5 (`docs/adr/` no la tiene). Su resumen en el repo,
`docs/architecture.md:222-225`, textual:

> **Security (ADR-011).** OWASP ASVS Level 2. Argon2id for passwords, AES-256-GCM for integration secrets
> (key held outside the database), short-lived JWT access tokens in HttpOnly cookies issued by the BFF,
> opaque rotating refresh tokens with reuse detection, …

El dominio dice lo mismo en `domain/sesion.py` (docstring del módulo): revocar **la familia entera** es lo
que convierte el siguiente request de la víctima en la alarma.

## Lo que ya existe y el hueco

- `RefrescarSesion.ejecutar` (`application/sesiones.py:141-167`) **lee** el token (`buscar_por_hash`, 142),
  **verifica** `fue_usado` (148) y recién después **escribe** `usado_en` (`marcar_usado` + `guardar`,
  165-166) y emite el hijo (167). Entre la lectura y la escritura no hay ningún lock.
- #47 hizo que la revocación por reuso **se confirme** (`api/routers/auth.py:204-232`): eso sigue valiendo y
  esta unidad lo necesita.
- El hueco tiene tres formas, todas con la misma causa (lectura sin lock + `UPDATE` con snapshot propio en
  READ COMMITTED):
  1. **Mismo token, dos rotaciones.** A y B leen R0 sin usar; el `UPDATE` de B espera el lock de fila de A, A
     confirma, B sobrescribe `usado_en` y confirma: dos hijos vivos, nada detectado.
  2. **Reuso mientras se rota el hijo.** A rota R1 (tiene R1 tomado); B presenta R0 (ya usado), detecta reuso
     y `revocar_familia` espera a A; A confirma R2; el `UPDATE` de B revoca R0 y R1 pero **no ve R2** (no
     estaba en su snapshot). R2 sigue vivo: el reuso se detectó y se registró, pero no se aplicó.
  3. **Logout mientras se rota.** Lo mismo con `CerrarSesion` (`sesiones.py:183-188`): «cerré sesión» y el
     hijo recién emitido sobrevive.
- Ningún test cubre concurrencia en refresh. Los de #47 (`tests/integracion/test_api_sesiones.py`) son
  secuenciales.

## Hallazgos

| # | Dónde | Qué |
|---|---|---|
| H1 | `contexts/identity/application/sesiones.py:142-167` | Lectura sin lock → verificación `fue_usado` → escritura. Es la ventana del bug |
| H2 | `contexts/identity/infrastructure/repositories.py:329-343` | `buscar_por_hash` es un `select` simple, sin `with_for_update` |
| H3 | `contexts/identity/infrastructure/repositories.py:345-353` | `revocar_familia` es un `UPDATE … WHERE familia_id` con su propio snapshot: no alcanza a las filas que otra transacción confirma mientras él espera (formas 2 y 3) |
| H4 | `contexts/identity/infrastructure/repositories.py:320-327` | `guardar` usa `session.get` (identity map). Una **segunda** lectura ORM del mismo token en la misma sesión devolvería el objeto viejo salvo `populate_existing`: la lectura bajo lock tiene que ser la **primera** carga ORM del token |
| H5 | `contexts/identity/application/sesiones.py:183-188` | `CerrarSesion` usa el mismo `buscar_por_hash` + `revocar_familia` (forma 3) |
| H6 | `platform/database.py:~145-156`, `159-182` | Sin nivel de aislamiento explícito (READ COMMITTED), sin `lock_timeout` ni `statement_timeout`; `autoflush=False`. La transacción la abre `sesion_de_empresa` y la confirma después del `yield` |
| H7 | `api/routers/auth.py:204-232`, `267-274`, `278-293` | `_rotar_refresh` (#47) y las rutas `/refresh` y `/logout`; la empresa se resuelve antes, fuera de la transacción, con `buscar_empresa_de_refresh` (`migrations/versions/0003_…:49-60`, `SECURITY DEFINER`) |
| H8 | `migrations/versions/0002_identidad.py:160-178`, `52-56`, `115-117` | `refresh_token`: `hash_del_token` único, índice `ix_refresh_familia`, RLS por empresa, `SELECT, INSERT, UPDATE` a `cheatsheet_app`. No hace falta índice nuevo |
| H9 | `contexts/identity/infrastructure/repositories.py:111-123`; `contexts/billing/infrastructure/repositories.py:88-96` | Precedentes de lock en el repo: `bloquear` (`FOR UPDATE` sobre la empresa) y `tomar_para_emitir` (D14: esperar, no `nowait`). No hay advisory locks en `src/` |
| H10 | `frontend/src/app/api/auth/refresh/route.ts` | La ruta del BFF existe, pero nada en `frontend/src` la llama (solo sus tests): hoy no hay refresh automático ni pestañas que compitan |
| H11 | `.github/workflows/ci.yml:12-13`, `44-47` | La CI solo corre en PRs contra `develop`/`main`, y `fix/…` solo puede apuntar a `develop` |
| H12 | `tests/integracion/test_puntos_de_venta_postgres.py:65-96` | El precedente de test de concurrencia usa `asyncio.sleep(0.05)`: no es determinista. Acá hace falta un RED que falle siempre |
| H13 | `contexts/identity/infrastructure/repositories.py` | 368 líneas; el límite es 400 (`CLAUDE.md` §5) |

## Preguntas abiertas

1. **P1 — Mecanismo (necesita una persona).**

   | | Opción | Cierra | A favor | En contra |
   |---|---|---|---|---|
   | **A** | `SELECT … FOR UPDATE` sobre la fila del token | Forma 1 | Una línea, con precedente (D14) | No cierra las formas 2 y 3; el RED solo se ve contra PostgreSQL |
   | **B** | Escritura condicional `UPDATE … SET usado_en = :ahora WHERE id = :id AND usado_en IS NULL AND NOT revocado RETURNING id`; si no actualiza filas, se trata como reuso | Forma 1 | El invariante «se usa una vez» vive en la escritura; la rama «perdí la carrera» se prueba con fakes en local | No cierra las formas 2 y 3; una rotación que pierde contra un logout responde 409 de reuso en vez de `SesionInvalida` |
   | **C** | **Lock por familia**: `pg_advisory_xact_lock(<espacio>, hashtext(familia_id))` tomado por refresh y logout **antes** de leer el token, que se lee recién después | Formas 1, 2 y 3 | Un solo mecanismo para todo lo que lee y escribe una familia; un lock por transacción → sin ciclo de deadlock; se libera solo con commit o rollback; sin migración | Mecanismo nuevo en el repo (no hay advisory locks); el RED solo se ve contra PostgreSQL |

   Recomendación: **C**. A y B arreglan el síntoma de P3 y dejan abierta la forma 2, que es el mismo control
   (ADR-011: «revocar la familia entera») fallando bajo concurrencia. Lock por filas de la familia (`FOR
   UPDATE … ORDER BY id`) se descartó: los conjuntos de filas que toman dos transacciones difieren (el nieto
   recién insertado) y eso puede formar un ciclo con el `UPDATE` de la revocación.

2. **P2 — Alcance (necesita una persona).** ¿Entran las formas 2 (reuso durante una rotación) y 3 (logout
   durante una rotación)? Recomendación: **sí**. Con C son la misma llamada en `CerrarSesion` y dos tests más;
   dejarlas afuera significa abrir otra unidad para el mismo mecanismo.

3. **P3 — Ventana de gracia para refresh legítimos simultáneos (necesita una persona).** Con C, dos pestañas
   que refrescan a la vez con el mismo token **revocan su propia familia** y obligan a volver a iniciar sesión.
   Recomendación: **sin ventana**, ADR-011 estricto.
   (a) Hoy no hay refresh automático (H10).
   (b) El caso real de pestañas se da **en el navegador**: la pestaña B manda R0 después de que A ya recibió
   R1 y antes de que se actualice la cookie. Es un reuso secuencial que ningún lock en la base resuelve.
   (c) Una ventana de gracia es justo la ventana que aprovecha un ladrón, y cambiaría ADR-011.
   Se deja anotado como **requisito** para quien construya la renovación automática: un solo refresh a la vez
   entre pestañas (Web Locks API o `BroadcastChannel`).

4. **P4 — CI con el PR apilado (necesita una persona).** La CI solo corre en PRs contra `develop`/`main`, y
   `fix/…` solo puede apuntar a `develop` (H11): un PR contra `fix/identity-revocacion-por-reuso` no corre la
   CI. Recomendación:
   - Abrir un PR draft contra `develop`, con el commit que agrega solo los tests empujado primero, para que la
     CI muestre el RED contra PostgreSQL.
   - Avisar en la descripción: «apilado sobre #47; revisar solo desde `0a53e23`».
   - Mantenerlo en draft hasta que #47 se mergee. `develop` usa merge commits (`ba3f889`), así que el diff se
     achica solo y no hace falta rebasar.

   Alternativa: esperar el merge de #47, rebasar sobre `develop` y recién ahí abrir el PR (más limpio, pero
   sin evidencia de CI hasta entonces).

5. **P5 — `lock_timeout` (técnica).** Recomendación: **no** ponerlo. Mismo criterio que D14 (esperar es lento
   y correcto; fallar empuja el reintento al cliente, y en refresh un reintento con el mismo token es,
   justamente, un reuso). Quien tiene el lock lo suelta tras pocas sentencias (usuario, emisión, insert del
   hijo, empresa).

6. **P6 — Fila en `units.md`.** Tomar la fila existente: Responsable `Luciano`, Rama
   `fix/identity-refresh-concurrente`, Estado `en curso` (`en revisión` cuando se abra el PR).

## Diseño (con la recomendación C)

- **Dominio**: sin cambios. `RefreshToken` (`fue_usado`, `es_utilizable`, `marcar_usado`) ya expresa la regla.
- **Aplicación**:
  - `RefrescarSesion.ejecutar` y `CerrarSesion.ejecutar` cambian `buscar_por_hash` por un método nuevo del
    puerto, `tomar_con_familia_bloqueada(hash)`. Devuelve el token leído **después** de tener la familia
    bloqueada hasta el fin de la transacción, o `None` si no existe.
  - El resto del flujo no cambia: si el token ya fue usado, se revoca la familia y se levanta el error de
    reuso; el router (#47) confirma y relanza.
  - Lo que garantiza: mientras una transacción tiene la familia, ninguna otra lee ni escribe tokens de esa
    familia, y lo que lee ya incluye todo lo confirmado antes.
- **Puertos y adaptadores**:
  - `PortRepositorioRefreshToken` gana `tomar_con_familia_bloqueada`, con docstring que diga que el lock dura
    hasta el fin de la transacción y la dueña es la unidad de trabajo. `buscar_por_hash` queda (lo usan tests
    y lecturas sin escritura).
  - `RepositorioRefreshTokenPostgres.tomar_con_familia_bloqueada` hace tres pasos:
    1. `select(RefreshTokenORM.familia_id).where(hash == …)`. Columna, no entidad: no puebla el identity map
       (H4).
    2. Si no hay fila → `None`.
    3. `select(func.pg_advisory_xact_lock(ESPACIO_FAMILIA_REFRESH, func.hashtext(cast(familia_id, String))))`
       y después la carga ORM del token. Es la primera, así que se lee fresca.
  - `ESPACIO_FAMILIA_REFRESH`: constante entera con nombre, que reserva el espacio de locks del proyecto. Una
    colisión de `hashtext` solo serializa dos familias de más; no expone datos (el lock no lee la tabla y RLS
    no interviene).
  - Si el archivo pasa de 400 líneas (H13), `RepositorioRefreshTokenPostgres` se mueve a
    `infrastructure/refresh_tokens.py` y se reexporta desde `repositories.py`.
  - El fake `RepositorioRefreshEnMemoria` (`tests/contexts/identity/conftest.py:125-150`) implementa el
    método igual que `buscar_por_hash`.
- **Interacción con #47**: la revocación por reuso ocurre con la familia bloqueada y se confirma por
  `_rotar_refresh`. El lock se libera en ese mismo commit, así que el siguiente en la cola ya ve la familia
  revocada. Los rechazos `SesionInvalida` hacen rollback y también sueltan el lock.
- **Deadlocks**: cada transacción toma **un** lock de familia y nunca espera otro. `revocar_de_usuario`
  (HU-E1-06) no toma el lock y solo actualiza filas: no puede formar ciclo con un rotador, que solo espera por
  su propia fila o por el lock de familia.
- **Otros contextos · Frontend**: no aplica. El contrato HTTP no cambia; el requisito de P3 queda anotado para
  la unidad que agregue la renovación automática.

## Infraestructura

- **Migraciones**: **no aplica**. El advisory lock no necesita schema; los índices existentes
  (`hash_del_token` único, `ix_refresh_familia`) alcanzan. `pg_advisory_xact_lock` es ejecutable por `PUBLIC`
  por defecto; se verifica en CI con el rol `cheatsheet_app`.
- **Trabajo asíncrono · Configuración · Integraciones externas**: **no aplica**. Nota para staging: Neon se
  usa por el endpoint directo (`docs/staging-database.md:112`); de todos modos el lock es de transacción y
  también funcionaría detrás de PgBouncer en modo transacción.

## Riesgos que obligan a tests

- [ ] Toca dinero — no aplica
- [ ] Comprobantes fiscales — no aplica
- [ ] Webhook — no aplica
- [x] Datos por empresa (`empresa_id`): el lock no lee la tabla y no pasa por RLS. Se prueba que dos familias
      (y dos empresas) que rotan a la vez **no** se bloquean entre sí
- [ ] Salida de un LLM — no aplica
- [ ] Datos personales a un LLM — no aplica
- [x] **Seguridad de sesión (ADR-011)**: los RED son de integración contra PostgreSQL; los fakes no tienen ni
      transacción ni lock
- [x] **Concurrencia**: el test tiene que fallar **siempre** contra el código actual, no según la carga del
      runner (H12). Se coordina con un sondeo de `pg_locks`, no con `sleep`
- Riesgo operativo: un request retenido ocupa una conexión del pool mientras espera. Una ráfaga contra **una**
  familia se serializa; afecta solo a esa familia y la espera dura lo que tardan las pocas sentencias del que
  tiene el lock

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/identity/application/ports.py` (método nuevo del puerto)
- [ ] `backend/src/cheatsheet/contexts/identity/application/sesiones.py` (`RefrescarSesion`, `CerrarSesion`, docstring del módulo)
- [ ] `backend/src/cheatsheet/contexts/identity/infrastructure/repositories.py` (o `infrastructure/refresh_tokens.py` si se pasa de 400 líneas)
- [ ] `backend/tests/contexts/identity/conftest.py` (fake)
- [ ] `backend/tests/integracion/test_refresh_concurrente.py` (nuevo)
- [ ] `backend/tests/contexts/identity/infrastructure/test_candado_de_familia.py` (nuevo, local; crear `__init__.py` si la carpeta no existe)
- [ ] `backend/tests/contexts/identity/application/test_registro_y_sesiones.py` (casos con el fake)

### Docs
- [x] `docs/aidlc/units.md` (fila de la unidad: Luciano, rama, en curso)

Sin cambios en `api/routers/auth.py`, `api/dependencies.py`, migraciones ni frontend.

## Casos de prueba

Modo: **test primero**. El commit que agrega solo los tests va antes que el fix en la historia de la rama. Los
casos RED tienen que fallar contra el código actual **por el motivo correcto**: un segundo hijo vivo o un nieto
sin revocar, no un error de armado.

**Cómo se hace determinista (integración).**
- **A** es una rotación abierta a mano: `sesion_de_empresa` con los repositorios Postgres y `RefrescarSesion`,
  que **no** sale del `async with` hasta que el test lo indica.
- **B** es un request real (`httpx.ASGITransport`, como `test_api_sesiones.py`) lanzado con
  `asyncio.create_task`.
- El test sondea con `engine_dueno` hasta ver `SELECT count(*) FROM pg_locks WHERE NOT granted` ≥ 1, con tope
  de 5 s y mensaje explícito. Se usa `pg_locks` y no `pg_stat_activity`, que oculta columnas de otros roles.
  Recién ahí deja confirmar a A y espera a B.
- Contra el código actual, B queda bloqueado en el `UPDATE` de `guardar` (forma 1) o en `revocar_familia`
  (formas 2 y 3). Con el fix queda bloqueado en el advisory lock. En los dos casos hay un lock en espera, así
  que el test es determinista antes y después.
- La base se mira como dueño (`engine_dueno`), sin pasar por el código bajo prueba.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED**: A rota R0 (abierta); B refresca R0 por HTTP → B responde 409 `ReusoDeRefreshDetectado`; en la base, **todas** las filas de la familia quedan `revocado = true`, incluido el hijo de A; el hijo de A ya no refresca | integración (PostgreSQL) | pendiente |
| 2 | **RED**: A rota R1 (abierta); B reusa R0 por HTTP → 409; R2 (el hijo de A) queda revocado en la base y no refresca | integración (PostgreSQL) | pendiente |
| 3 | **RED**: A rota R1 (abierta); B hace logout con R1 por HTTP → 204; R2 queda revocado y no refresca | integración (PostgreSQL) | pendiente |
| 4 | Ráfaga: 5 refresh simultáneos de R0 (`asyncio.gather`) → a lo sumo un 200, ninguno 5xx (sin deadlock); si hubo más de una respuesta, la familia queda toda revocada | integración (PostgreSQL) | pendiente (no es el RED: depende del orden real) |
| 5 | Dos familias (mismo usuario con dos logins, y dos empresas) rotan a la vez y las dos responden 200: el lock es por familia | integración (PostgreSQL) | pendiente |
| 6 | Un refresh rechazado (`SesionInvalida`: vencido) suelta el lock: un refresh posterior de la misma familia termina sin esperar | integración (PostgreSQL) | pendiente |
| 7 | Los casos 1 a 7 de #47 (`test_api_sesiones.py`) siguen en verde sin cambios | integración | pendiente (CI) |
| 8 | El repositorio ejecuta, en orden, la búsqueda de `familia_id` (columna, no entidad), `pg_advisory_xact_lock` y recién después la carga ORM del token; con un hash desconocido no toma ningún lock. Se verifica con un doble de `AsyncSession` que registra las sentencias compiladas con el dialecto de PostgreSQL | unit (local) | pendiente. Es un test de especificación, no reproduce la carrera |
| 9 | `RefrescarSesion` y `CerrarSesion` usan `tomar_con_familia_bloqueada` (fake espía); los tests existentes de sesiones (`test_reusar_un_refresh_revoca_toda_la_familia` y demás) siguen en verde con el fake actualizado | unit (local) | pendiente |
| 10 | `tests/api/test_refresh_confirma_la_revocacion.py` (#47) sigue en verde | unit (local) | pendiente |

**Límite de la evidencia local.** No hay Docker acá, así que los RED (1 a 3) se observan recién en CI, sobre
el commit que agrega solo los tests (ver P4). Los casos 8 y 9 corren en local, pero prueban la forma del
mecanismo, no la carrera: el cierre del hallazgo son los casos 1 a 3 contra la base real.

## Gate 2 — verificación (además de los comandos del repositorio)

- **Verificador independiente (identity/auth)**: un subagente que **no escribió el fix** revisa el diff
  contra ADR-011 y responde:
  1. ¿Todo camino que lee y después escribe tokens de una familia toma el lock **antes** de leer?
  2. ¿La lectura bajo lock es la primera carga ORM del token (identity map)?
  3. ¿Hay algún camino con dos locks de familia en una transacción?
  4. ¿El contrato HTTP de `/refresh` y `/logout` es idéntico al anterior?
  5. ¿Queda algún otro escritor de `refresh_token` sin lock que pueda dejar escapar un hijo, aparte de
     `revocar_de_usuario`, que se dejó afuera con su justificación?
- **CI**: los casos 1 a 7 corren solo allí. **El Gate 2 no se cierra sin la CI en verde** sobre esos casos, y
  sin la corrida roja del commit que agrega solo los tests, con la salida real.
- Definition of Done (`CLAUDE.md` §7): sin secretos; sin configuración nueva; **sin ADR**: se cumple ADR-011,
  no se decide nada nuevo. Si P3 se resuelve **con** ventana de gracia, sí hace falta enmendar ADR-011 antes de
  codificar.

## Verificaciones que no se pueden hacer acá

- Correr los tests de integración: no hay Docker en esta máquina; corren en CI (P4).
- Confirmar que `cheatsheet_app` puede ejecutar `pg_advisory_xact_lock` en la base real (es `PUBLIC` por
  defecto; lo prueba el caso 1 en CI y, después del deploy, un refresh en `staging`).
- Medir la espera bajo carga real en Neon; no aplica hasta tener tráfico.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
-
