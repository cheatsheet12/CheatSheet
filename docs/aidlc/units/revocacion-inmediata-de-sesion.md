# Unidad: revocacion-inmediata-de-sesion

**HUs**: HU-E1-05, HU-E1-06   **Contexto dueño**: identity   **Rama**: feature/identity-revocacion-inmediata-de-sesion

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D84 (`docs/aidlc/units.md`). La rama sale de `develop`.
>
> **Estado al 2026-10-09: pendiente, Gate 1 listo para presentar.** El plan quedó escrito el
> 2026-09-29, se actualizó a `develop` el 2026-10-02 (hallazgo 3, pregunta 6 y caso 25) y **se revalidó
> contra `develop` en `cc4fe5b` el 2026-10-09**: `identity/`, `platform/database.py`, `api/main.py`,
> `api/errors.py`, `api/dependencies.py` y `api/middleware/empresa.py` no cambiaron; `api/routers/auth.py`
> solo sumó la delegación de ARCA en `PUT /auth/empresa`; la última migración es la 0036 y la unidad no
> agrega ninguna. La revalidación corrigió el hallazgo 5 (un segundo archivo de tests), la pregunta 2
> (arranque en frío de Neon), el umbral de costo de la pregunta 1, la sección de frontend (dos
> comentarios, no código) y «Fuera de esta unidad» (la renovación automática del panel ya existe).
> Al abrir el Gate 1 hay que resolver **la pregunta 1 (decisión C1)**: cumplir D84 (consultar el
> usuario en la base en cada solicitud, sin caché, con 503 si la base no responde) o mantener la
> ventana de 15 minutos del JWT y documentarla como desvío de D84. La recomendación es cumplir D84.
>
> **Toca autenticación.** El Gate 2 de esta unidad incluye un **verificador independiente** (un agente
> distinto del que implementa, sin el contexto de la implementación), además de las verificaciones
> habituales. Ver «Verificación de esta unidad».

## Qué hace

Hoy el middleware acepta el rol y la identidad que dice el token de acceso (JWT de 15 minutos) sin
consultar la base: si un Administrador desactiva a alguien o le cambia el rol, el token viejo sigue
valiendo hasta que vence. Esta unidad hace que **cada solicitud autenticada se evalúe contra el estado
actual del usuario** (existe, está `ACTIVO`, rol vigente, misma empresa que el token). La siguiente
solicitud de un usuario desactivado da 401, y la de un usuario con el rol cambiado se evalúa con el rol
nuevo. La renovación de sesión de un usuario desactivado ya se rechaza y sus refresh tokens ya se
revocan: la unidad lo deja probado de punta a punta.

## Encuadre (Paso 0)

- **Contexto dueño**: `identity`. El middleware vive en `api/` (raíz de composición) y no decide nada:
  llama a un caso de uso de `identity`.
- **Capas**: aplicación (caso de uso + puerto) e infraestructura (adaptador PostgreSQL) de `identity`,
  más `api/middleware` y el armado en `create_app`. El dominio no cambia; en el frontend solo se corrige
  un comentario (ver «Frontend»).
- **Sin integraciones externas ni migraciones.** Redis no participa (ver pregunta 1).

### Hallazgos — el código contradice a las historias o a sí mismo

1. **HALLAZGO — el criterio central no se cumple hoy.** `api/middleware/empresa.py::_identidad` toma
   `sub`, `empresa_id` y `rol` del JWT y no consulta la base. Los criterios de HU-E1-05 («su siguiente
   solicitud ya se evalúa con el nuevo rol») y de HU-E1-06 («su siguiente solicitud es rechazada como no
   autorizada») son falsos hasta 15 minutos después del cambio. Es la razón de la unidad.
2. **HALLAZGO — documentación que afirma lo contrario.** `contexts/identity/infrastructure/seguridad.py`
   («A JWT cannot be revoked before it expires… acceptable for 15 minutes») y el docstring de
   `DesactivarUsuario` («Doing better than minutes would mean checking the database on every request»)
   describen la decisión anterior. Se corrigen en esta unidad para no dejar dos verdades.
3. **HALLAZGO (resuelto fuera de esta unidad) — la revocación por reuso de refresh se perdía.**
   *Actualización 2026-10-02:* se confirmó y se corrigió en `fix/identity-revocacion-por-reuso` (PR #47),
   y la carrera entre dos renovaciones simultáneas en `fix/identity-refresh-concurrente` (PR #57), los dos
   ya en `develop` (`backend/tests/integracion/test_api_sesiones.py`,
   `backend/tests/integracion/test_refresh_concurrente.py`). Lo que sigue es el texto original:
   En `POST /auth/refresh` (`api/routers/auth.py`), `RefrescarSesion` llama a `revocar_familia` y
   **luego lanza** `ReusoDeRefreshDetectado` dentro de `async for unidad in unidad_de_trabajo(...)`.
   `sesion_de_empresa` solo hace `commit` si el cuerpo termina sin excepción y su `except Exception` no
   captura el `GeneratorExit` con que se cierra el generador abandonado: la sesión se cierra sin commit y
   el `UPDATE revocado = true` se deshace. Si es cierto, la detección de robo revoca la familia solo en
   memoria y el ladrón conserva la sesión. **Es el mismo mecanismo de revocación de esta unidad, pero es
   otra historia (ADR-011, detección de reuso).** El caso de prueba 25 lo confirma o lo descarta; qué
   hacer con el resultado es la pregunta 6.

   *Segunda lectura (orquestador, 2026-09-29):* la excepción nace en el cuerpo del `async for`, no
   dentro del generador, así que `sesion_de_empresa` nunca llega al `commit`. El único test que cubre el
   reuso (`test_reusar_un_refresh_revoca_toda_la_familia`) usa fakes y no puede ver el rollback. Sigue sin
   ejecutarse contra PostgreSQL: el caso 25 corre en la CI.
4. **HALLAZGO menor — código HTTP de `SesionInvalida`.** `api/errors.py` no mapea `SesionInvalida`, así
   que `/auth/refresh` con un token inválido o de un usuario desactivado responde **409**, no 401. El BFF
   ya lo traduce (`status < 500` → 401 y borra cookies), por eso no se ve. No se cambia acá (ver «Fuera
   de esta unidad»); los tests aseveran «4xx con `error == "SesionInvalida"`», no el número.
5. **HALLAZGO de alcance de tests.** Dos archivos firman un JWT válido para un `usuario_id` inventado
   (`uuid4()`) y arman la app con `Recursos` sin base (`sesiones=None`); con la verificación por
   solicitud darían 401/503:
   - `tests/api/test_health.py`: `_autorizacion` solo la usa
     `test_un_error_de_dominio_se_traduce_sin_filtrar_internals`. Las demás pruebas del archivo no
     mandan token o mandan uno inválido (el caso 11 ya cubre que ese no llega al verificador).
   - `tests/api/test_reporte_fallido_se_confirma.py`: `_autorizacion` (vía `_pedir`) la usan las tres
     pruebas que llaman a la ruta (`test_un_fallo_de_generacion_…`, `test_un_periodo_sin_datos_…` y
     `test_un_rechazo_por_rol_…`, esta última con rol `SOLO_LECTURA`, que el verificador falso tiene
     que devolver tal cual).

   Se adaptan inyectando un verificador falso (ver Diseño). Los `test_api_*` de `tests/integracion/`
   obtienen su token registrándose de verdad, así que el usuario existe y no cambian.

## Las preguntas que el mapa dejó para este Gate

### 1. Mecanismo: consulta por solicitud, o versión de sesión con caché corta (D84)
**Recomendación: consultar el usuario en cada solicitud, por clave primaria, sin caché.**

- Es la única opción que cumple «la siguiente solicitud» de forma literal. Cualquier caché con TTL > 0
  reabre una ventana igual al TTL; invalidarla en escritura cierra casi todo, pero deja la carrera
  «lectura que falla el caché y repuebla con el valor viejo después de que otro borró la clave», que se
  resuelve con versiones y compare-and-set: mucha más superficie de ataque que la consulta que se quiere
  ahorrar.
- **Costo medido, no supuesto** (D84 lo pide): una lectura por PK en `usuario` (índice de la clave
  primaria; RLS agrega `empresa_id = current_setting(...)`), sobre un pool que ya existe. Se mide en
  **dos lugares**, y los dos números se anotan en «Decisiones»:
  - **Base local**: `EXPLAIN (ANALYZE)` y 200 llamadas. Umbral para reabrir la pregunta: p95 > 5 ms por
    consulta o una carga que sature el pool.
  - **Staging (Neon)**: ahí el costo dominante no es la consulta sino los viajes de red de cada
    verificación (ping del pool por `pool_pre_ping=True`, `set_config`, `SELECT`, `COMMIT`). Se miden
    200 llamadas a `GET /auth/empresa` con la compute despierta, con y sin verificación, y se anota el
    p95 agregado por solicitud. No hay umbral fijo: el número se presenta en el Gate 2 y la pregunta se
    reabre si el usuario lo considera inaceptable. Si solo puede medirse después del despliegue, queda
    anotado en `docs/aidlc/TODO.md` §22 y el Gate 2 lo dice.
- **No agrega un modo de falla nuevo**: toda ruta protegida ya necesita la base. Con Redis (caché) sí
  aparece uno (ver pregunta 2).
- **No cambia el esquema de autenticación**: el JWT se emite, se firma y viaja igual; el refresh opaco
  rotativo con detección de reuso no cambia (D84). Solo cambia que el token deja de ser autoridad sobre
  rol y estado. Por eso **no hace falta un ADR** (D84 lo exigía únicamente si el esquema cambiaba). Si la
  respuesta a esta pregunta fuera «caché» o «versión de sesión en el token», sí haría falta uno antes de
  cerrar el Gate 1.
- Descartado: caché en proceso con TTL corto. Con varias instancias cada una envejece por su cuenta, y
  «la siguiente solicitud» depende de a cuál instancia le toca.

### 2. Si la verificación no puede ejecutarse (base caída o lenta): ¿cerrado o abierto?
**Recomendación: cerrado, con 503 y no con 401. El límite de 3 s acota solo la consulta del usuario;
la toma de la conexión conserva el timeout de conexión de 10 s que ya existe, sin reintentos.**

*Revisado el 2026-10-09.* La versión anterior ponía 3 s sobre toda la verificación. Staging corre en
Neon, que suspende la compute ociosa ([ADR-0005](../../adr/0005-staging-database-neon.md),
«Consequences»: la primera solicitud tras un período sin uso es lenta), y `platform/database.py` fija
`TIMEOUT_DE_CONEXION_SEGUNDOS = 10` justamente porque despertarla lleva más de dos segundos. Con 3 s
sobre todo, la primera solicitud después de un rato sin uso daría 503, y el layout del panel llama a
`/auth/empresa` en cada navegación: el panel fallaría al abrirlo cada mañana.

- **Abierto está descartado**: aceptar el token cuando no se puede verificar es exactamente la ventana
  que la unidad cierra, y un atacante con token robado la provoca cargando la base.
- **503 y no 401**: la sesión no está revocada, el sistema no puede afirmarlo. Un 401 haría que el panel
  (`estadoDeEmpresa` en `(panel)/layout.tsx` trata todo 4xx como «sin sesión») sacara a todos los usuarios
  a la pantalla de ingreso durante una caída. Con 503 el layout propaga el error (>= 500 se relanza) y la
  sesión sobrevive a la caída.
- **Dos límites explícitos, uno por tramo** (`CLAUDE.md` §5), ambos fail-closed con 503:
  - **Tomar la conexión** (el `set_config` de `sesion_de_empresa`, que es donde la sesión la pide al
    pool): la acota `TIMEOUT_DE_CONEXION_SEGUNDOS = 10`, el mismo límite que ya rige para cualquier ruta.
    No se redefine ni se envuelve en otro más corto: es el valor elegido para que Neon alcance a
    despertar. Si la base está caída, una ruta protegida ya espera hoy hasta 10 s por su propia conexión;
    la verificación ocupa ese lugar (si falla, la ruta no corre), así que el peor caso por solicitud no
    empeora.
  - **La consulta del usuario** (`SELECT empresa_id, rol, estado …`): **3 s** con `asyncio.timeout`,
    ya con la conexión en mano. Una lectura por PK que tarda más que eso es una base degradada, no
    una compute dormida.
- **Sin reintento.** Se descartó «reintentar una vez la toma de conexión con 3 s»: no salva el arranque
  en frío (el segundo intento también necesita más de 3 s) y durante una caída duplica la espera.
- Con el pool agotado, la espera por una conexión libre la fija `pool_timeout` de SQLAlchemy (30 s por
  defecto; `crear_engine` no lo configura). Vale igual hoy para cualquier ruta y no se toca acá; el
  verificador independiente lo tiene a la vista.
- **Redis caído**: no tiene efecto, porque la unidad no usa Redis (un test lo prueba). Es una ventaja
  concreta de la pregunta 1.
- Las rutas públicas y `/health` no pasan por la verificación, así que el healthcheck sigue informando.

### 3. Granularidad de la revocación: ¿por usuario o por sesión?
**Recomendación: por usuario.** HU-E1-06 pide que el usuario desactivado «pierda el acceso» y que
«sus sesiones renovables queden revocadas» (todas, ya implementado con `revocar_de_usuario`). La
verificación por solicitud mira al **usuario**, así que todas sus sesiones e ids de dispositivo caen a la
vez. Revocar **una** sesión (cerrar sesión en un dispositivo) ya existe y funciona por familia de refresh
(`CerrarSesion`); un access token de esa familia sigue valiendo hasta 15 minutos y **eso no está en
ninguna historia**: agregar un `sid` al token y una lista de sesiones vivas sería un cambio de esquema
(ADR) sin historia detrás. Queda declarado en «Fuera de esta unidad».

### 4. Qué pasa con un token emitido antes de la desactivación cuando se reactiva al usuario
**Recomendación: se acepta y se documenta.** Si un Administrador reactiva a alguien dentro de los 15
minutos de vida de su último access token, ese token vuelve a valer, con el rol que el usuario tiene
ahora. Es coherente con HU-E1-06 RN-04 («recupera el acceso con el rol que tenía») y lo acota el TTL. La
alternativa —un instante `sesiones_validas_desde` por usuario— exige una columna y una migración por un
caso donde la persona autorizada es la misma. El caso de prueba 21 fija el comportamiento para que no sea
un accidente.

### 5. Respuesta al usuario revocado: ¿se distingue de «sin token»?
**Recomendación: no.** Mismo 401 y mismo cuerpo (`NoAutenticado`, «Se requiere iniciar sesion.») que un
token ausente o inválido. Quien tiene un token robado no debe aprender si el usuario fue desactivado,
no existe o cambió de empresa. El motivo (`usuario_inactivo`, `usuario_inexistente`,
`empresa_no_coincide`) va solo al log estructurado, sin el token ni el email.

### 6. El hallazgo 3 (revocación por reuso perdida): ¿se arregla acá?
*Actualización 2026-10-02: **ya no aplica**; el arreglo está en `develop` (hallazgo 3). Se conserva el
texto original:*
**Recomendación: en esta unidad solo se confirma con un test (caso 25, RED de caracterización); el arreglo
va en una unidad `fix/identity-…` aparte**, salvo que el usuario prefiera incluirlo. Razones: (a) `CLAUDE.md`
§8 («do not widen the scope; report it»), (b) es otra historia y otro riesgo (robo de refresh, no
desactivación), (c) la corrección probable es chica (confirmar la transacción antes de lanzar) pero cambia
el contrato de `unidad_de_trabajo` para todos los routers, y eso merece su propia revisión. Si el caso 25
falla, se anota en `docs/aidlc/TODO.md` y se le avisa al usuario en el Gate 2 con la salida real.

## Diseño

### Dominio — `contexts/identity/domain/`
Sin cambios. `Usuario`, `EstadoUsuario` y `RolUsuario` ya expresan lo necesario (`Usuario.activo`).

### Aplicación — `contexts/identity/application/`
- `ports.py`: nuevo puerto `PortConsultaDeUsuarioVigente` con
  `async def estado_actual(self, usuario_id: UsuarioId) -> EstadoActualDelUsuario | None`, y el DTO
  inmutable `EstadoActualDelUsuario(empresa_id, rol, estado)`. Un puerto propio y no un método más de
  `PortRepositorioUsuario`: lee tres columnas en vez de hidratar el agregado completo (con el JSONB de
  preferencias) en **cada solicitud**, y no obliga a tocar los dobles en memoria de los demás tests.
- `errors.py`: `SesionRevocada(SesionInvalida)` — el token es válido pero el usuario ya no puede operar.
- `verificacion_de_sesion.py` (nuevo, ≈ 60 líneas): caso de uso `VerificarSesionVigente`.
  - Entrada: `usuario_id`, `empresa_id_del_token`. Salida: `IdentidadVigente(empresa_id, usuario_id, rol)`.
  - Garantiza: devuelve el **rol de la base**, nunca el del token; lanza `SesionRevocada` si no hay
    fila, si el estado no es exactamente `ACTIVO` (un `INVITADO` tampoco opera) o si la empresa de la
    fila no es la del claim.
- `usuarios.py` y `seguridad.py` (infra): solo docstrings corregidos (hallazgo 2).

### Puertos y adaptadores
- `infrastructure/consulta_de_sesion.py` (nuevo): `ConsultaDeUsuarioVigentePostgres(sesion)` — un
  `SELECT empresa_id, rol, estado FROM usuario WHERE id = :id`, sin `FOR UPDATE` (no bloquea nada).
  Corre bajo RLS: el `WHERE` de la política ya limita a la empresa del token.
- `VerificadorDeSesionPostgres(sesiones, timeout_de_consulta)` (mismo archivo): abre
  `sesion_de_empresa(sesiones, empresa_id_del_token)` (la toma de conexión queda bajo el timeout de
  conexión de 10 s, pregunta 2), arma el adaptador y el caso de uso, acota **solo la consulta** con
  `asyncio.timeout(timeout_de_consulta)` y **cierra la sesión antes de devolver**.
  El middleware **nunca retiene una conexión mientras corre la ruta** (`call_next`): doblaría el consumo
  del pool y bajo carga produciría interbloqueos por agotamiento.
- Es un `empresa_id` firmado el que fija `app.current_empresa`: el token es de confianza en su firma, pero
  la fila se compara igual (defensa en profundidad, caso 22).

### API — `api/middleware/empresa.py` y `api/main.py`
- `EmpresaMiddleware` recibe un `VerificadorDeSesion` (Protocol definido en el propio módulo). Tras
  decodificar y validar la firma, llama al verificador y pone en `request.state` **el rol, el usuario y la
  empresa que devuelve**, no los del token. Ningún router cambia: todos ya leen `request.state.rol`.
- `SesionRevocada` → 401 con el mismo cuerpo que «sin token». Errores de infraestructura acotados
  (`SQLAlchemyError`, `OSError`, `TimeoutError`; sin `except Exception`) → **503**
  `{"error": "ServicioNoDisponible", "detalle": "No pudimos verificar tu sesion. Reintenta en unos segundos."}`,
  con log de nivel error.
- `create_app(settings, recursos, verificador=None)`: por defecto arma `VerificadorDeSesionPostgres` con
  `recursos.sesiones`; los tests lo reemplazan por uno falso. Es la costura que evita depender de una base,
  y la usan los dos archivos del hallazgo 5 (`test_health.py` y `test_reporte_fallido_se_confirma.py`).
- Rutas públicas (`RUTAS_PUBLICAS`, `PREFIJOS_PUBLICOS`): **sin cambios**. `/auth/refresh` y `/auth/login`
  ya rechazan a un usuario inactivo dentro de su caso de uso.

### Otros contextos
Ninguno. Los demás contextos reciben el rol vigente por `request.state`, como hoy. Los workers de Celery
no pasan por el middleware y quedan igual (ver «Fuera de esta unidad»).

### Frontend
**Sin cambios de comportamiento; un comentario se corrige.** El panel ya trata un 4xx de `/auth/empresa`
como sesión inválida y redirige a `/`; un 503 se propaga como error. La interfaz sigue leyendo el rol de
los claims del token solo para dibujar botones (`leerClaims`, documentado como no-decisión): el backend
decide.

- **Sin bucle de redirección** (comprobado en el código): ante un 401 del middleware, `(panel)/layout.tsx`
  redirige a `/` **sin borrar las cookies**, y ni `(ingreso)/layout.tsx` ni `(ingreso)/page.tsx` redirigen
  cuando hay cookie de sesión (`FormularioDeIngreso` solo navega después de un ingreso exitoso). La
  cookie de acceso vieja queda hasta su `maxAge` (15 min, `lib/session.ts`); cada intento de volver al
  panel repite el 401 y vuelve a `/`. No es un riesgo: el token ya no autoriza nada.
- **Comentario que deja de ser cierto**: `features/identity/components/RenovadorDeSesion.tsx:13-14`
  («a role change or a deactivation still takes effect within fifteen minutes»). Con esta unidad surte
  efecto en la siguiente solicitud. Se corrige el comentario; el código no cambia.
- **Comentario revisado y que sigue siendo cierto**: `(panel)/layout.tsx:12-14` habla de no llevar
  `onboarding_completo` en el JWT, no de rol ni de estado; la unidad no lo vuelve falso y no se toca.

## Infraestructura

- **Migraciones**: **No aplica.** La consulta usa la clave primaria de `usuario`; no hay columnas ni
  índices nuevos.
- **Trabajo asíncrono**: No aplica.
- **Configuración**: No aplica. El timeout de 3 s de la consulta es una constante con nombre en el
  módulo del verificador; la toma de conexión usa `TIMEOUT_DE_CONEXION_SEGUNDOS` sin cambios. No se agrega
  variable de entorno ni cambia ningún `.env.example`.
- **Integraciones externas**: No aplica. (PostgreSQL ya es dependencia; la llamada lleva timeout explícito
  y el fallo se maneja fail-closed, ver pregunta 2. Redis: no se usa.)

## Riesgos que obligan a tests
- [ ] Toca dinero — no aplica
- [ ] Comprobantes fiscales / CAE — no aplica
- [ ] Webhook — no aplica (las rutas `/webhooks/` y `/contador/` siguen públicas, con test de que no
  invocan al verificador)
- [x] Datos por empresa (`empresa_id`) — la consulta corre bajo RLS y compara la empresa de la fila con
  la del token: casos 5, 15 y 22
- [ ] Salida de un LLM — no aplica
- [ ] Datos personales a un LLM — no aplica
- [x] *(propio de esta unidad)* Autenticación y autorización — revocación efectiva en la siguiente
  solicitud, rol tomado de la base, y **fail-closed** ante base caída o lenta: casos 1–4, 6–9, 17–21
- [x] *(propio de esta unidad)* Carreras y dependencias de infraestructura — refresh vivo insertado tras
  la desactivación, Redis sin efecto y arranque en frío de Neon sin 503: casos 12, 23 y 27
- [x] *(propio de esta unidad)* Costo por navegación — cada navegación del panel pasa a costar **dos
  lecturas** a la base: la verificación del middleware y la propia `GET /auth/empresa`
  (`api/routers/auth.py`, `ver_empresa`), cada una con su conexión del pool. Se mide en la pregunta 1 y
  no se optimiza en esta unidad (`docs/aidlc/TODO.md` §4 ya propone un endpoint de «contexto de sesión»)

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/identity/application/ports.py` (puerto + DTO)
- [ ] `backend/src/cheatsheet/contexts/identity/application/errors.py` (`SesionRevocada`)
- [ ] `backend/src/cheatsheet/contexts/identity/application/verificacion_de_sesion.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/identity/application/usuarios.py` (docstring de `DesactivarUsuario`)
- [ ] `backend/src/cheatsheet/contexts/identity/infrastructure/consulta_de_sesion.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/identity/infrastructure/seguridad.py` (docstring)
- [ ] `backend/src/cheatsheet/api/middleware/empresa.py`
- [ ] `backend/src/cheatsheet/api/main.py`
- [ ] `backend/tests/contexts/identity/conftest.py` (doble `ConsultaDeUsuarioVigenteEnMemoria`)
- [ ] `backend/tests/contexts/identity/application/test_verificacion_de_sesion.py` (nuevo)
- [ ] `backend/tests/api/test_middleware_de_sesion.py` (nuevo; middleware con verificador falso)
- [ ] `backend/tests/api/test_health.py` (inyecta el verificador falso; solo
  `test_un_error_de_dominio_se_traduce_sin_filtrar_internals` lo necesita)
- [ ] `backend/tests/api/test_reporte_fallido_se_confirma.py` (inyecta el verificador falso en
  `create_app`; lo necesitan las tres pruebas que pasan por `_pedir`)
- [ ] `backend/tests/integracion/test_identidad_postgres.py` (adaptador bajo RLS, casos 14–16)
- [ ] `backend/tests/integracion/test_api_revocacion_de_sesion.py` (nuevo; casos 17–25)

### Frontend
- [ ] `frontend/src/features/identity/components/RenovadorDeSesion.tsx` (solo el comentario de las
  líneas 13-14)

### Docs
- [ ] `docs/aidlc/units.md` (estado de la fila)
- [ ] `docs/aidlc/TODO.md`: registrar el hallazgo 4 y el de `renovarSesion` («Fuera de esta unidad»), y
  **corregir la entrada vieja de §4** («La renovación de sesión es manual, y se nota»), que sigue
  describiendo un problema que `67f2db4` resolvió el 2026-10-05 con `RenovadorDeSesion`. Se corrige en
  esta unidad y no aparte porque esta unidad ya edita `TODO.md` y cambia el mismo comportamiento que
  esa entrada describe; se marca como resuelta citando el commit, sin borrarla

## Casos de prueba

Modo: **test primero**. Los casos marcados RED tienen que fallar antes de tocar el código.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: usuario `ACTIVO` → `IdentidadVigente` con el rol de la base aunque el token diga otro | unit | pendiente |
| 2 | RED: usuario `INACTIVO` → `SesionRevocada` | unit | pendiente |
| 3 | RED: usuario `INVITADO` → `SesionRevocada` (solo `ACTIVO` opera) | unit | pendiente |
| 4 | RED: sin fila (borrado, o de otra empresa bajo RLS) → `SesionRevocada` | unit | pendiente |
| 5 | RED: la fila pertenece a una empresa distinta del claim → `SesionRevocada` | unit | pendiente |
| 6 | RED: verificador lanza `SesionRevocada` → 401 con el mismo cuerpo que «sin token» | unit (API) | pendiente |
| 7 | RED: `request.state.rol` es el del verificador (token ADMINISTRADOR, base OPERADOR → la ruta ve OPERADOR) | unit (API) | pendiente |
| 8 | RED: `OSError` / `SQLAlchemyError` en el verificador → 503, nunca 200 ni 401 (fail-closed) | unit (API) | pendiente |
| 9 | RED: la consulta del usuario que excede 3 s (con la conexión ya tomada) → 503 | unit | pendiente |
| 10 | `/health`, `/auth/login`, `/webhooks/…`, `/contador/…` no invocan al verificador | unit (API) | pendiente |
| 11 | Token de firma mala, expirado o sin `Bearer` → 401 sin invocar al verificador | unit (API) | pendiente |
| 12 | RED: con un Redis que falla ante cualquier uso, una sesión válida sigue autenticando | unit (API) | pendiente |
| 13 | El log de rechazo lleva el motivo y no contiene el token ni el email | unit (API) | pendiente |
| 14 | El adaptador devuelve rol, estado y empresa de un usuario de la empresa en curso | integración (PostgreSQL) | pendiente |
| 15 | Desde la sesión de la empresa B, el usuario de A → `None` (RLS) | integración (PostgreSQL) | pendiente |
| 16 | La verificación emite **una sola** sentencia (sin N+1) y no toma bloqueos de fila | integración (PostgreSQL) | pendiente |
| 17 | RED: desactivar a un usuario con token vigente → su siguiente solicitud da 401 (HU-E1-06) | integración (API) | pendiente |
| 18 | RED: tras desactivar, `/auth/refresh` con su refresh token es rechazado (4xx, `SesionInvalida`) y todas sus familias quedaron `revocado` (HU-E1-06) | integración (API) | pendiente |
| 19 | RED: Administrador → Operador; con el mismo token, una acción solo de Administrador da 403 en la siguiente solicitud (HU-E1-05) | integración (API) | pendiente |
| 20 | Operador → Administrador; con el mismo token, la acción ya se permite en la siguiente solicitud | integración (API) | pendiente |
| 21 | Reactivar dentro de los 15 min: el token anterior vuelve a operar con el rol previo (comportamiento aceptado, pregunta 4) | integración (API) | pendiente |
| 22 | RED: JWT firmado con `sub` de un usuario de A y `empresa_id` de B → 401, sin datos de B | integración (API) | pendiente |
| 23 | Un refresh vivo creado **después** de la desactivación (carrera con `RefrescarSesion`) es rechazado al usarse | integración (API) | pendiente |
| 24 | Regresión: un usuario desactivado no puede iniciar sesión con su contraseña | integración (API) | pendiente |
| 25 | ~~Caracterización del hallazgo 3~~: ya cubierto en `develop` por `test_api_sesiones.py` y `test_refresh_concurrente.py`. Esta unidad solo verifica que sigan verdes con el verificador por solicitud | integración (API) | guarda existente |
| 26 | Las pruebas existentes de `tests/api/test_health.py` y `tests/api/test_reporte_fallido_se_confirma.py` siguen verdes con el verificador falso inyectado (hallazgo 5) | unit (API) | pendiente |
| 27 | RED: una toma de conexión que tarda más de 3 s y menos de 10 s (Neon despertando) **no** da 503: la solicitud se verifica y responde normalmente | unit | pendiente |

## Verificación de esta unidad (Gate 2)

Además de `ruff format --check . && ruff check . && mypy . && pytest` y la suite del frontend (sin
cambios, se corre igual), el Gate 2 incluye:

- **Verificador independiente**, con estas preguntas de partida: ¿hay algún camino que llegue a un
  router sin pasar por la verificación (ruta no listada como pública)? ¿algún `except` traga un error de
  infraestructura y deja pasar? ¿el 503 puede convertirse en 200 por un reintento o por el manejador
  genérico de `api/errors.py`? ¿el middleware retiene una conexión durante `call_next`? ¿el `empresa_id`
  de `app.current_empresa` sale de un valor sin verificar?
- La medición de costo de la pregunta 1, con sus dos números (base local y staging), o la constancia de
  que el de staging quedó en `docs/aidlc/TODO.md` §22.
- Que el límite de 3 s acota solo la consulta y no la toma de conexión (caso 27), para que el primer
  ingreso del día en staging no dé 503.
- Que las pruebas de sesión ya existentes (caso 25) siguen verdes.

## Fuera de esta unidad

- **Revocar una sola sesión (un dispositivo) al instante**: requiere un `sid` en el token y una lista de
  sesiones vivas (cambio de esquema → ADR) y ninguna historia lo pide. Cerrar sesión sigue revocando la
  familia de refresh; su access token vale hasta 15 min.
- ~~Arreglar la revocación por reuso de refresh~~: resuelto en `develop` (PRs #47 y #57).
- **Cambiar el código HTTP de `SesionInvalida`** a 401 (hallazgo 4): afecta a `/auth/login`, al BFF y a
  sus tests; es una decisión de contrato, no de esta unidad.
- **Tareas de Celery y workers**: no pasan por el middleware. Ninguna tarea actúa con el token de un
  usuario; si alguna llegara a hacerlo, tendría que llamar al mismo caso de uso.
- **Desactivar una empresa entera**: no existe el caso de uso (`empresa.activa` no se escribe en ningún
  camino), así que no hay nada que revocar.
- ~~Renovación automática de sesión en el panel~~: ya existe. `67f2db4` (2026-10-05) agregó
  `RenovadorDeSesion`, que renueva cada 10 minutos y al volver a la pestaña, y manda a `/` ante un 401.
  La entrada de `docs/aidlc/TODO.md` §4 que la da por manual quedó vieja y se corrige en esta unidad
  (ver «Archivos a tocar > Docs»).
- **Interfaz**: los botones que dibuja `leerClaims` siguen leyendo el rol del token hasta la próxima
  renovación, que con `RenovadorDeSesion` ocurre a lo sumo a los ~10 minutos (o antes, al volver a la
  pestaña); solo afecta lo que se ve, no lo que se permite.
- **HALLAZGO informado, preexistente: una caída de la base durante la renovación cierra la sesión.**
  `renovarSesion` (`frontend/src/app/api/auth/_sesion.ts`, bloque `catch`) borra las dos cookies ante
  **cualquier** error de `/auth/refresh`, incluido un 5xx (su comentario lo declara a propósito). Una
  caída breve de la base que coincida con una renovación saca al usuario al ingreso, aunque su sesión
  siga viva. No lo introduce esta unidad (`/auth/refresh` es pública y no pasa por el verificador) y
  cambiarlo es otra decisión de contrato del BFF: se registra en `docs/aidlc/TODO.md` y no se arregla
  acá (`CLAUDE.md` §8).
- **HU-E1-03 y HU-E1-08** (términos y privacidad) son de `terminos-y-privacidad`.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
*(Se completa al aprobar el Gate 1, con la respuesta a cada pregunta de arriba. Propuestas: 1 consulta por
PK sin caché, con la medición en la base local y en staging; 2 fail-closed con 503, 3 s sobre la consulta
y 10 s (el timeout de conexión existente) sobre la toma de conexión, sin reintento; 3 por usuario; 4 se
acepta la reactivación con token vigente; 5 mismo 401 que «sin token»; 6 ya no aplica.)*

*Ninguna de estas propuestas requiere un ADR: ninguna cambia el esquema de autenticación (pregunta 1), y
la revisión de la pregunta 2 solo reparte límites de tiempo dentro de la misma verificación. Haría falta
uno si la respuesta a la pregunta 1 fuera «caché» o «versión de sesión en el token», o la de la pregunta
3 fuera «por sesión».*
