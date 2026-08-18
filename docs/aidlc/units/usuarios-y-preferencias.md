# Unidad: usuarios-y-preferencias

**HUs**: HU-E1-04, HU-E1-05, HU-E1-06, HU-E1-07
**Contexto dueño**: `identity`
**Rama**: `feature/identity-cimientos-identidad-y-bitacora` (la misma del épico, por la decisión del 2026-08-13)

Última unidad del épico 1. Cierra `identity` y con eso el épico entero.

## Qué hace

Un Administrador invita gente a su empresa por email, le asigna uno de tres roles, se lo cambia,
la desactiva y la reactiva — sin poder nunca dejar a la empresa sin un Administrador activo. Quien
recibe la invitación entra por un link, elige su contraseña y queda activo. Y cualquier usuario,
sea cual sea su rol, edita sus propias preferencias de idioma, zona horaria y suscripciones.

Todo lo que cambia un usuario ajeno queda en el Log de Operaciones, que la unidad 1 ya dejó listo.

---

## ⚠️ Lo que hay que resolver antes: el login escribe fuera de su empresa

**Encontrado al planificar esta unidad. No es un riesgo teórico: `/auth/login` está roto contra un
PostgreSQL real.**

`login`, `refresh` y `logout` abren la transacción con `EmpresaId(uuid4())` — un UUID inventado —
porque en ese momento todavía no se sabe a qué empresa pertenece quien entra
([`auth.py:129`](../../../backend/src/cheatsheet/api/routers/auth.py)). Después buscan al usuario
con la función `SECURITY DEFINER`, que sí lo encuentra, y **escriben la fila de `refresh_token` con
el `empresa_id` verdadero mientras `app.current_empresa` sigue valiendo el UUID inventado**.

La política de la migración 0002 dice:

```sql
WITH CHECK (empresa_id = NULLIF(current_setting('app.current_empresa', true), '')::uuid)
```

El `INSERT` no puede pasar. Y el `UPDATE` del logout tampoco: su `USING` no ve ninguna fila, así que
la revocación **no falla, simplemente no revoca** — un logout que no cierra la sesión, en silencio.

No lo detectó nadie porque los tests de esos casos usan dobles en memoria, y los tests de
aislamiento que corren contra PostgreSQL de verdad
([`test_aislamiento_entre_empresas.py`](../../../backend/tests/integracion/test_aislamiento_entre_empresas.py))
prueban el mecanismo sobre `registro_de_auditoria`, no sobre este camino. Uno de ellos se llama
`test_no_se_puede_insertar_una_fila_de_otra_empresa` — o sea que el repositorio ya tiene la prueba
de que esto se rechaza, sin aplicarla acá.

**Por qué se resuelve en esta unidad y no se anota como deuda:** aceptar una invitación es
exactamente el mismo caso — no hay sesión, la empresa se descubre a partir del token — así que esta
unidad tiene que construir el camino pre-tenant igual. Si no se arregla antes, se duplica el patrón
roto en un lugar más.

**Cómo se arregla:** dos transacciones en vez de una. La primera solo resuelve la identidad con la
función `SECURITY DEFINER` y no escribe nada. La segunda se abre ya con el `empresa_id` verdadero y
hace el trabajo. Se encapsula en un helper de `api/dependencies.py`, `unidad_para_empresa_resuelta`,
para que ningún endpoint futuro tenga que acordarse.

**Y para que no vuelva:** un test de integración contra PostgreSQL real que hace login y verifica
que la fila de `refresh_token` quedó escrita, y otro que verifica que el logout la revocó. Es la
regla del repositorio — todo bug arreglado empieza por el test que lo reproduce.

---

## Diseño

### Dominio

**`EstadoUsuario`** (nuevo `StrEnum`): `INVITADO` · `ACTIVO` · `INACTIVO`. **Reemplaza a
`Usuario.activo`**, que era booleano.

Se aparta del DER, que modela `usuario.activo boolean NN`, y es una extensión declarada del hueco
**H1** — el propio DER admite que no modela «estado de invitación pendiente». Dos razones:

1. PAN-USR-01 muestra tres estados. Dos de ellos caben en un booleano; el tercero no.
2. El invariante de HU-E1-05 RN-02 y HU-E1-06 RN-03 —«al menos un Administrador activo»— **no debe
   contar a quien fue invitado como Administrador y todavía no aceptó**. Con un booleano, un
   invitado tendría `activo = true` sin poder entrar, y el sistema creería tener un administrador
   que no existe. Con el enum, el invariante es `rol = ADMINISTRADOR AND estado = ACTIVO` y no hay
   nada sutil que razonar en la regla que protege el acceso de la empresa.

**`Invitacion`** (agregado nuevo): `id`, `empresa_id`, `usuario_id`, `hash_del_token`, `expira_en`,
`aceptada_en`, `revocada`. Métodos `aceptar(ahora)`, `revocar()`, `esta_vigente(ahora)`.

Mismo patrón que `RefreshToken`, y por la misma razón: **el token se guarda hasheado, nunca en
claro**. Un token de invitación en la base es una cuenta lista para que la tome quien lea un dump.
Es opaco, aleatorio, de un solo uso y con vencimiento.

**`PreferenciasDeNotificacion`** (value object nuevo) → se serializa a `pref_suscripciones jsonb`,
la columna que el DER declara y que la unidad anterior dejó sin implementar porque HU-E1-07 caía
acá. Es un mapa de categoría a conjunto de canales:

- `CanalDeNotificacion`: `EMAIL` · `PANEL`
- `CategoriaDeNotificacion`: `FACTURACION` · `COBROS` · `SINCRONIZACION` · `AGENDA` · `SISTEMA`

El DER declara la columna `jsonb` y ningún esquema, así que el esquema hay que definirlo. Las cinco
categorías **no son inventadas**: son las de los épicos que van a emitir notificaciones (5, 6, 4, 7
y el resto). Cada épico que agregue una categoría agrega un valor al enum; que sea un catálogo
cerrado y no texto libre es lo mismo que ya se decidió para `Modulo` en la bitácora.

**`Usuario`** cambia: `estado` en lugar de `activo`, y gana `cambiar_rol`, `desactivar`,
`reactivar`, `aceptar_invitacion(hash, nombre)` y `pref_suscripciones`.
`actualizar_preferencias` se extiende con las suscripciones.

**El invariante «al menos un Administrador activo» no vive en `Usuario`.** Es una regla sobre el
conjunto de usuarios de una empresa, y ningún agregado la puede sostener solo. Vive en los servicios
de aplicación que pueden romperla, que son exactamente dos: cambiar rol y desactivar.

### Aplicación

Un caso de uso por servicio. Todos los que tocan a un usuario ajeno exigen rol Administrador
(HU-E1-04, HU-E1-05 RN-03, HU-E1-06) y publican su `EventoAuditable`.

| Servicio | Entrada | Qué garantiza |
|---|---|---|
| `ListarUsuarios` | `empresa_id` | Nombre, email, rol y estado de la empresa, y de ninguna otra |
| `InvitarUsuario` | email, nombre, rol, ejecutor | El email no existe (RN-03); crea `Usuario` en `INVITADO` sin hash y una `Invitacion`; devuelve el token en claro **una sola vez**, para que el caller encole el envío |
| `ReenviarInvitacion` | `invitacion_id`, ejecutor | Solo mientras esté pendiente (RN-04). Revoca el token viejo y emite uno nuevo — reenviar no debe dejar dos llaves vivas |
| `RevocarInvitacion` | `invitacion_id`, ejecutor | Solo mientras esté pendiente (RN-04). Marca la invitación y **borra la fila de `usuario`** |
| `AceptarInvitacion` | token, contraseña, nombre | Token vigente, no usado, no revocado, no vencido; fija el hash, pasa a `ACTIVO`, y devuelve una sesión ya iniciada |
| `CambiarRolDeUsuario` | `usuario_id`, rol nuevo, ejecutor | Inmediato (RN-01). Rechaza si deja a la empresa sin Administrador activo (RN-02) |
| `DesactivarUsuario` | `usuario_id`, ejecutor | Acceso perdido de inmediato. Mismo invariante (RN-03) |
| `ReactivarUsuario` | `usuario_id`, ejecutor | Vuelve con **el rol que tenía** (RN-04): el rol nunca se borró, solo el estado cambió |
| `ActualizarPreferencias` | `usuario_id`, idioma, zona, suscripciones | Sobre uno mismo, cualquier rol. Inmediato |

**Por qué revocar borra la fila y no la desactiva.** El email es único en toda la plataforma. Si la
invitación revocada dejara la fila con `estado = INACTIVO`, ese email quedaría tomado para siempre y
volver a invitar a la misma persona sería imposible. Quien nunca aceptó nunca hizo nada: no hay
historial que preservar. El evento de auditoría de la invitación registra al **ejecutor**, no al
invitado, así que no se pierde nada al borrar.

**La carrera del último Administrador.** Dos administradores que se degradan mutuamente al mismo
tiempo pasan los dos el conteo y la empresa se queda sin ninguno. El conteo por sí solo no alcanza:
es un *check-then-act*. Las dos operaciones que pueden romper el invariante toman antes un
`SELECT … FOR UPDATE` sobre la fila de `empresa`, que las serializa. Barato, y es el único lugar del
sistema donde perder la carrera significa quedarse afuera de la propia cuenta.

**Desactivar corta la sesión de verdad.** Sin esto, RN-01 («pierde el acceso de forma inmediata»)
sería falso hasta que venza el JWT. Desactivar revoca todos los `refresh_token` del usuario, así que
la sesión muere apenas expira el access token, que vive minutos. Hacerlo instantáneo exigiría
consultar la base en cada request, que es justo lo que un JWT corto existe para evitar.

### Puertos y adaptadores

| Puerto | Adaptador |
|---|---|
| `PortRepositorioUsuario` *(se extiende)* | + `listar_de_empresa`, `contar_administradores_activos`, `eliminar` |
| `PortRepositorioInvitacion` *(nuevo)* | PostgreSQL; el `buscar_por_hash` pre-tenant va por `SECURITY DEFINER` |
| `PortRepositorioRefreshToken` *(se extiende)* | + `revocar_de_usuario(usuario_id)` |
| `PortRepositorioEmpresa` *(se extiende)* | + `bloquear(empresa_id)` — el `FOR UPDATE` del invariante |
| `PortTokenDeInvitacion` *(nuevo)* | `secrets.token_urlsafe` + SHA-256, igual que el refresh |
| `PortEnvioDeEmail` *(nuevo)* | `aiosmtplib` en producción, adaptador de consola en local |

`docs/architecture.md` §7 declara `PortNotificacionEmail` para `reporting` y `payments`, no para
`identity`, y nunca se implementó. Este puerto se declara **en `identity`**, que es lo que manda el
hexagonal: cada contexto declara los puertos que sus casos de uso necesitan. Cuando el épico 9 pida
el suyo, se verá si el adaptador se extrae a un lugar común — extraerlo ahora, con un solo
consumidor, sería adivinar la forma que necesita el segundo.

**Emails: plantillas en archivo, nunca texto embebido en la lógica.** Misma regla que la
constitución fija para los prompts, y por la misma razón: un texto que se muestra afuera se revisa,
se versiona y se cambia sin tocar código.

### Otros contextos

Solo `observability`, por evento de dominio, con el `PublicadorEnProceso` que ya existe. Es la arista
`all → observability` (OHS) que el Context Map ya permite. **Ningún import cruzado nuevo.**

### Frontend

`features/identity` es la única feature que se toca. Su `index.ts` suma `TablaDeUsuarios`,
`ModalDeInvitacion`, `FormularioDePreferencias` y `FormularioDeAceptacion`.

Rutas nuevas:

- `(panel)/configuracion/usuarios` → PAN-USR-01
- `(panel)/configuracion/preferencias` → PAN-USR-02
- `(public)/invitacion/[token]` → aceptar la invitación. **Tercera pantalla, que el catálogo no
  numera**: HU-E1-04 RN-02 exige que el invitado cree su contraseña y en ningún `PAN-…` pasa eso.

**Maquetación (hueco P9).** No hay prototipo de ninguna de las dos. Decidido: tabla con las cuatro
columnas que pide el criterio de aceptación —nombre, email, rol, estado— acciones por fila, y el
alta por modal. Se construye con el catálogo del PDF §1.3 y los tokens que ya están en
`shared/tokens.css`; hacen falta tres piezas nuevas del sistema de diseño (`Tabla`, `Modal`,
`Select`), que se agregan ahí y no dentro de la feature.

El **rol gobierna lo que se ve**: un Operador o un Solo Lectura no ve la sección Usuarios ni sus
acciones (HU-E1-05 RN-03). Eso es cosmética, no seguridad — quien decide es el backend en cada
endpoint, y esconder el botón solo evita ofrecer algo que va a ser rechazado.

**Idioma: decidido no traducir la interfaz.** `pref_idioma` y `pref_zona_horaria` se guardan y
gobiernan **el formato de fechas, horas y números** en todo el panel, vía un helper de `shared/`.
La traducción de la interfaz no se hace: el sistema tiene un solo idioma y montar i18n para un
catálogo de un idioma es infraestructura sin nadie del otro lado.

**Consecuencia, dicha de frente:** el criterio «cambio mi idioma y la interfaz se actualiza» **queda
incumplido**, igual que la consulta al padrón de ARCA quedó incumplida por D1. El selector de idioma
muestra una sola opción. Cuando exista un segundo idioma, se monta `next-intl` y se extraen los
textos; nada de lo que se escribe ahora lo impide.

---

## Infraestructura

### Migraciones — `0003_usuarios_y_preferencias`

- `usuario`: `activo boolean` → `estado varchar(20) NOT NULL`; `+ pref_suscripciones jsonb NOT NULL`
- `invitacion`: tabla nueva, con RLS por `empresa_id`, `FORCE ROW LEVEL SECURITY` y los grants al rol
  de aplicación — el mismo tratamiento que las otras cuatro tablas
- `buscar_invitacion_para_aceptar(p_hash)`: función `SECURITY DEFINER`, tercera del sistema. Devuelve
  `empresa_id`, `usuario_id` y el vencimiento, **nada más**. Existe por lo mismo que las otras dos:
  aceptar una invitación pasa antes de que haya empresa, y la alternativa es `BYPASSRLS`, que apaga
  la barrera entera para siempre para resolver una consulta
- Índices: `ix_invitacion_empresa`, y único sobre `hash_del_token`

**Reversible**, con `downgrade` completo. **Sin backfill**: no hay producción. El `upgrade` mapea
`activo = true → ACTIVO` y `false → INACTIVO`, que es correcto porque nadie fue invitado todavía.

### Trabajo asíncrono

Una tarea, `identity.enviar_invitacion`, en la cola **`notifications`** (ADR-003).

- **Idempotente** por `ClaveDeIdempotencia` sobre `(empresa_id, invitacion_id)`: un reintento de
  Celery no manda dos veces el mismo mail.
- **Reintentos con backoff** ante fallo de SMTP, con tope. Un servidor de correo caído no debe perder
  la invitación ni martillarlo.
- **El token en claro viaja en el argumento de la tarea, no en la base.** Es lo que obliga a que el
  envío se encole en el mismo request que crea la invitación: después ya no existe en ningún lado.
- Sin schedule en Beat: la dispara el endpoint.

### Configuración — variables nuevas

| Variable | Para qué |
|---|---|
| `EMAIL_ADAPTADOR` | `smtp` o `consola`. En local, consola: el link va al log estructurado |
| `SMTP_HOST` · `SMTP_PORT` · `SMTP_USUARIO` · `SMTP_PASSWORD` | El servidor. Sirve con cualquier proveedor transaccional |
| `SMTP_TLS` | STARTTLS |
| `SMTP_REMITENTE` | El `From:` |
| `SMTP_TIMEOUT_SEGUNDOS` | Obligatorio por constitución §5 |
| `INVITACION_TTL_DIAS` | Vencimiento del token. Por defecto 7 |
| `APP_BASE_URL` | Para construir el link. Sin esto el mail lleva a `undefined` |

Van a **`backend/.env.example`**. ⚠️ **Ese archivo está denegado por permisos en este entorno**, así
que las tengo que pasar para que las pegues a mano, igual que las siete de las unidades anteriores.
Es parte de la Definition of Done y no lo puedo cerrar yo.

### Integraciones externas

**SMTP**, detrás de un ACL propio (ADR-008). Timeout explícito, reintentos con backoff en la tarea,
y falla manejada: si el correo no sale, la invitación **igual queda creada** y el Administrador puede
reenviarla. Perder la invitación porque el servidor de correo tosió sería peor que un mail tardío.

Sandbox vs producción: `EMAIL_ADAPTADOR=consola` es el modo de desarrollo. **Ningún test toca la
red** — el adaptador de consola y un doble cubren todo.

---

## Riesgos que obligan a tests

- [ ] Toca dinero → no
- [ ] Toca comprobantes fiscales / CAE → no
- [ ] Consume un webhook → no
- [x] **Agrega datos con `empresa_id`** → `invitacion` necesita su test de aislamiento contra
      PostgreSQL real, como toda tabla nueva
- [ ] Usa salida de un LLM → no
- [x] **Datos personales** → nombres y emails. No van a ningún LLM. Y no se loguean: el link de
      invitación lleva un token que es una credencial

Riesgos propios de esta unidad, que también obligan a test:

- [x] **El invariante del último Administrador**, incluida la carrera entre dos operaciones simultáneas
- [x] **El token de invitación**: un solo uso, vence, se revoca, y nunca se guarda en claro
- [x] **RBAC**: que un Operador reciba 403, no una pantalla vacía
- [x] **El camino pre-tenant** (login, refresh, logout, aceptación) contra PostgreSQL real

---

## Archivos a tocar

**Backend — dominio**
- [x] `identity/domain/valores.py` — `EstadoUsuario`, `CanalDeNotificacion`, `CategoriaDeNotificacion`, `PreferenciasDeNotificacion`
- [x] `identity/domain/usuario.py` — `estado`, transiciones, suscripciones
- [x] `identity/domain/invitacion.py` — nuevo

**Backend — aplicación**
- [x] `identity/application/errors.py` — `UltimoAdministradorActivo`, `InvitacionInvalida`, `PermisoDenegado`
- [x] `identity/application/ports.py` — los seis puertos de arriba
- [x] `identity/application/autorizacion.py` — `exigir_administrador`
- [x] `identity/application/usuarios.py` — listar, cambiar rol, desactivar, reactivar
- [x] `identity/application/invitaciones.py` — invitar, reenviar, revocar, aceptar
- [x] `identity/application/preferencias.py` — actualizar

**Backend — infraestructura**
- [x] `identity/infrastructure/models.py` · `repositories.py` · `ensamblado.py`
- [x] `identity/infrastructure/email_invitacion.py` — SMTP + consola *(el plan lo llamaba `email_smtp.py`; el nombre dice qué manda, no por dónde)*
- [x] `identity/infrastructure/plantillas/invitacion.{txt,html}`
- [x] `identity/infrastructure/tokens_invitacion.py`

**Backend — API, workers, migraciones, settings**
- [x] `api/routers/usuarios.py` — nuevo · `api/routers/auth.py` — aceptación · `api/main.py`
- [x] `api/middleware/empresa.py` — la ruta pública de aceptación
- [x] `identity/infrastructure/resolucion.py` — el arreglo del camino pre-tenant *(el plan lo ponía en `api/dependencies.py`; vive en el contexto porque consulta las funciones `SECURITY DEFINER` de identity, y la raíz de composición no tiene por qué conocerlas)*
- [x] `workers/tasks_identity.py`
- [x] `migrations/versions/0003_usuarios_y_preferencias.py`
- [x] `platform/settings.py` — las diez variables

**Backend — tests**
- [x] `tests/contexts/identity/{domain,application,infrastructure}/…`
- [x] `tests/integracion/test_aislamiento_invitacion.py`
- [x] `tests/integracion/test_camino_pre_tenant.py` — el que reproduce el defecto del login

**Frontend**
- [x] `shared/ui/{Tabla,Modal,Select}.tsx` · `shared/componentes.css` · `shared/formato.ts`
- [x] `features/identity/components/{TablaDeUsuarios,ModalDeInvitacion,FormularioDePreferencias,FormularioDeAceptacion}.tsx`
- [x] `features/identity/api/cliente.ts` · `index.ts`
- [x] `app/(panel)/configuracion/{usuarios,preferencias}/page.tsx` · `app/(public)/invitacion/[token]/page.tsx`
- [x] `app/api/usuarios/…` y `app/api/auth/invitaciones/aceptar/route.ts` — BFF
- [x] Tests de todo lo anterior

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | `EstadoUsuario` — las transiciones válidas y las que no | unit | ✅ |
| 2 | Reactivar devuelve el rol previo, no uno por defecto (HU-E1-06 RN-04) | unit | ✅ |
| 3 | `PreferenciasDeNotificacion` — ida y vuelta a jsonb sin pérdida | unit | ✅ |
| 4 | `PreferenciasDeNotificacion` rechaza categoría o canal desconocido | unit | ✅ |
| 5 | `Invitacion.esta_vigente` — vencida, usada, revocada, vigente | unit | ✅ |
| 6 | Invitar con un email que ya existe en la empresa se rechaza (RN-03) | aplicación | ✅ |
| 7 | Invitar con un email de **otra** empresa también se rechaza (email único global) | aplicación | ✅ |
| 8 | Invitar crea el usuario en `INVITADO` y **sin** hash de contraseña | aplicación | ✅ |
| 9 | Un Operador que invita recibe `PermisoDenegado` | aplicación | ✅ |
| 10 | Un Solo Lectura que cambia un rol recibe `PermisoDenegado` (RN-03) | aplicación | ✅ |
| 11 | Reenviar invalida el token anterior | aplicación | ✅ |
| 12 | Revocar libera el email para volver a invitar a la misma persona | aplicación | ✅ |
| 13 | Reenviar o revocar una invitación **ya aceptada** se rechaza (RN-04) | aplicación | ✅ |
| 14 | Aceptar fija la contraseña, pasa a `ACTIVO` y devuelve sesión | aplicación | ✅ |
| 15 | El mismo token no se puede usar dos veces | aplicación | ✅ |
| 16 | Un token vencido se rechaza | aplicación | ✅ |
| 17 | Aceptar con contraseña de menos de 8 caracteres se rechaza | aplicación | ✅ |
| 18 | **Quitarle Administrador al único activo se bloquea** (HU-E1-05 RN-02) | aplicación | ✅ |
| 19 | **Desactivar al único Administrador activo se bloquea** (HU-E1-06 RN-03) | aplicación | ✅ |
| 20 | **Un Administrador `INVITADO` no cuenta para el invariante** | aplicación | ✅ |
| 21 | Con dos Administradores activos, degradar a uno sí se permite | aplicación | ✅ |
| 22 | Desactivar revoca los refresh tokens del usuario (RN-01) | aplicación | ✅ |
| 23 | Cambiar rol y desactivar publican su `EventoAuditable` con ejecutor, afectado y valores (RN-04) | aplicación | ✅ |
| 24 | El listado solo trae usuarios de la empresa del ejecutor | aplicación | ✅ |
| 25 | Las preferencias de un usuario no tocan las de otro (HU-E1-07 RN-01) | aplicación | ✅ |
| 26 | El token de invitación se guarda hasheado: el valor en claro no aparece en la fila | infra | ✅ |
| 27 | El adaptador de consola no abre ningún socket | infra | ✅ |
| 28 | El adaptador SMTP aplica timeout y reintenta con backoff | infra | ✅ |
| 29 | El envío falla y la invitación **igual queda creada** y reenviable | infra | ✅ |
| 30 | La tarea es idempotente: dos ejecuciones, un solo mail | infra | ✅ |
| 31 | La plantilla del mail no filtra el token en el log | infra | ✅ |
| 32 | **`invitacion` aísla por empresa** contra PostgreSQL real | integración | ✅ |
| 33 | **Login escribe su `refresh_token`** contra PostgreSQL real *(el defecto de arriba)* | integración | ✅ |
| 34 | **Logout revoca de verdad** contra PostgreSQL real *(íd.)* | integración | ✅ |
| 35 | Aceptar una invitación funciona sin sesión previa, con RLS activo | integración | ✅ |
| 36 | La migración 0003 sube y baja limpia | integración | ✅ |
| 37 | La carrera del último Administrador: dos operaciones simultáneas, una falla | integración | ✅ |
| 38 | `TablaDeUsuarios` — un Operador no ve las acciones de administración | frontend | ✅ |
| 39 | El modal de invitación valida el email y no envía vacío | frontend | ✅ |
| 40 | Desactivar pide confirmación antes de ejecutar | frontend | ✅ |
| 41 | `FormularioDePreferencias` carga las actuales y guarda los cambios | frontend | ✅ |
| 42 | `shared/formato` respeta la zona horaria del usuario | frontend | ✅ |
| 43 | `FormularioDeAceptacion` exige 8 caracteres y confirma la contraseña | frontend | ✅ |
| 44 | Las rutas BFF de usuarios no devuelven ningún token al navegador | frontend | ✅ |

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-14 | aprobado, sin cambios pedidos — incluido el arreglo del camino pre-tenant |
| 2 · Verificación | 2026-08-18 | todos los gates en verde — ver abajo |
| 3 · PR | | (unificado para el épico) |

---

---

## Gate 2 — verificación (2026-08-18)

Corrido sobre PostgreSQL 16 y Redis reales en contenedor (`backend/docker-compose.yml`, puertos
5433 y 6380). Ninguna prueba toca la red fuera de eso: SMTP, Google y Celery están detrás de
dobles.

```
ruff format --check .   sin cambios
ruff check .            All checks passed!
mypy .                  Success: no issues found in 150 source files
guard_architecture      188 file(s) checked — architecture boundaries intact
pytest --cov            235 passed · cobertura 87.79%  (umbral 80%)

frontend: next lint     ✔ No ESLint warnings or errors
frontend: tsc --noEmit  limpio
frontend: vitest        176 passed · cobertura 91.24%
frontend: next build    compila; 21 rutas registradas
```

Los 44 casos de prueba del plan están escritos y pasan. Seis corren contra PostgreSQL de verdad,
porque el RLS y el `FOR UPDATE` no tienen doble posible.

### Lo que la implementación encontró y el plan no preveía

**Un segundo defecto del mismo tipo que el del login.** La migración 0003 elimina `usuario.activo`,
y la función `SECURITY DEFINER` `buscar_usuario_para_login` de la 0002 seguía seleccionando esa
columna. PostgreSQL no recompila una función cuando cambia la tabla de abajo, así que el esquema
migraba limpio y **el primer login fallaba** con «column u.activo does not exist». Lo encontró el
test de integración del camino pre-tenant, que es exactamente para lo que se escribió. La función
se redefine en la 0003 y el `downgrade` restaura la forma de la 0002.

**El router de usuarios no arrancaba.** `GET /usuarios` no tiene path propio, y FastAPI rechaza un
path vacío cuando el router se incluye sin prefijo. El prefijo pasó a aplicarse en la inclusión.

### Apartamientos del plan, y por qué

| Plan | Implementación | Motivo |
|---|---|---|
| `api/dependencies.py` → `unidad_para_empresa_resuelta` | `identity/infrastructure/resolucion.py` | Consulta funciones `SECURITY DEFINER` propias de identity. La raíz de composición no tiene por qué conocerlas |
| `identity/infrastructure/email_smtp.py` | `email_invitacion.py` | El nombre dice qué manda, no por dónde. Cuando llegue el segundo correo del sistema, el archivo por transporte sería el lugar equivocado |

### Alcance que se agregó, declarado

Tres cosas que el plan no pedía y que se hicieron igual, porque eran deuda de la unidad anterior
que esta unidad se comprometió a saldar (sección «Deuda de la unidad anterior que esta salda»):

- **`/api/auth/google` y su callback.** El link existía en PAN-ONB-01 desde la unidad 2 y no tenía
  nada detrás. Incluye la validación de `state` — la única defensa contra un callback forjado.
- **`/api/auth/refresh`.** Sin él la sesión moría a los quince minutos.
- **El layout `(panel)` exige onboarding completo**, no solo la cookie. Hizo falta un
  `GET /auth/empresa` para saberlo sin meter el flag en el JWT, donde estaría vencido.

Y una cuarta, que no era deuda declarada pero era una rotura silenciosa: **los dos layouts usaban
tokens de diseño que dejaron de existir** cuando se importaron los prototipos de Etapa 5
(`--espacio-*`, `--color-texto-suave`). Renderizaban sin espaciado y nadie lo había visto.

### Lo que queda pendiente

Está todo en [`../TODO.md`](../TODO.md). En una línea: los dos `.env.example` (denegados por
permisos en mi entorno), credenciales reales de Google y de SMTP —hoy ambas corren simuladas, con
el simulado prohibido en producción— y el Gate 3.

## Decisiones tomadas durante la unidad

- **Idioma (2026-08-14):** se guarda `pref_idioma` y gobierna el formato de fechas, horas y números;
  la interfaz **no** se traduce y no se monta i18n. HU-E1-07 queda con un criterio incumplido,
  documentado, igual que D1.
- **Estado del usuario (2026-08-14):** `activo boolean` se reemplaza por `estado`
  (`INVITADO`/`ACTIVO`/`INACTIVO`). Apartamiento del DER declarado como extensión del hueco H1.
- **Correo (2026-08-14):** SMTP configurable por variables de entorno, con adaptador de consola en
  local. No se ata el épico 1 a ningún proveedor.
- **Maquetación de PAN-USR-01 (2026-08-14):** tabla de cuatro columnas con acciones por fila y alta
  por modal. Resuelve el hueco P9 para esta pantalla.

## Deuda de la unidad anterior que esta salda

Tres cabos que dejé sueltos en `identidad-y-onboarding` y que caen naturalmente acá:

- El link `/api/auth/google` del formulario de ingreso no tiene ningún route handler detrás.
- La ruta BFF `/api/auth/refresh` estaba planificada y no se construyó, así que hoy la sesión
  simplemente muere cuando vence el access token.
- El layout `(panel)` solo verifica que exista la cookie de sesión; el plan decía que además exigiera
  el onboarding completo.
