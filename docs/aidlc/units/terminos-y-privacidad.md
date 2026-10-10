# Unidad: terminos-y-privacidad

**HUs**: HU-E1-03, HU-E1-08   **Contexto dueño**: identity   **Rama**: feature/identity-terminos-y-privacidad (tramo 1) · `-alta` (tramo 2) · `-reaceptacion` (tramo 3)

> **Gate 1 aprobado el 2026-10-10** con las recomendaciones de las doce preguntas. Origen: revisión del profesor de 2026-09,
> [ADR-0009](../../adr/0009-review-adjustments-scope-change.md), decisión D83 (`docs/aidlc/units.md`,
> bloque del épico 1). La evidencia se leyó sobre `origin/develop` en `5980a7a` (2026-10-10). Las rutas
> son relativas a `backend/src/cheatsheet/` o a `frontend/src/` salvo que se indique otra cosa.
>
> Las respuestas del bloque **«Preguntas para el Gate 1»** son sus recomendaciones; quedan resumidas
> en «Decisiones tomadas durante la unidad».

## Qué hace

Publica los Términos y Condiciones y la Política de Privacidad como **páginas públicas, versionadas y con
ruta estable** (`/terminos`, `/privacidad`), hoy inexistentes. Registra **cada aceptación** en una tabla
propia: la política la acepta cada Usuario (en el alta, al aceptar una invitación y cuando cambia la
versión), y los términos los acepta la Empresa a través de un Administrador. Las casillas pasan a ser
dos, separadas y sin marcar, también para «Continuar con Google». Cuando cambia una versión vigente,
quien la debe aceptar queda bloqueado hasta aceptarla (solo puede leer el texto y cerrar sesión). El
Contador externo ve un aviso con el enlace a la política, sin aceptación registrada.

## Encuadre (Paso 0)

- **Contexto dueño**: `identity`. Las aceptaciones son del Usuario y de la Empresa, dos agregados de
  este contexto. `observability` recibe los eventos de bitácora por el mecanismo que ya existe
  (`shared/auditoria.py`, `EventoAuditable`). No hace falta ningún edge nuevo en el Context Map.
- **Capas**: dominio (valores y una entidad nueva), aplicación (casos de uso y puertos),
  infraestructura (catálogo de textos, repositorio, consulta por solicitud), `api/` (router nuevo,
  middleware, `auth.py`) y frontend (`features/identity`, rutas en `(public)`, `(alta)`, `(ingreso)` y
  `(panel)`, y una línea en la página del contador).
- **Una migración** (tabla `aceptacion_legal` con RLS y backfill). **Sin integraciones externas**, sin
  trabajo asíncrono. Una variable de entorno **se elimina** (`TERMINOS_VERSION_VIGENTE`).

## Alcance, atado a las historias

| Regla / criterio | Qué hace esta unidad | Tramo |
|---|---|---|
| HU-E1-03 RN-01 | Se conservan `empresa.terminos_version` y `empresa.terminos_fecha_aceptacion` (DER) como estado vigente **y** cada aceptación queda como fila en `aceptacion_legal` | 2 |
| HU-E1-03 RN-02 | La aceptación pasa a ser una **entrada obligatoria del backend** (hoy solo la exige el navegador) | 2 |
| HU-E1-03 RN-03 y criterios 6–7 | Re-aceptación por un Administrador cuando cambia la versión; los otros roles no se bloquean | 3 |
| HU-E1-03 RN-04, RN-05 y criterio 5 | Página pública `/terminos` con versión y fecha de vigencia; enlace en el pie del registro | 1 |
| HU-E1-08 RN-01 | Catálogo de versiones inmutables, una sola vigente, las anteriores conservadas | 1 |
| HU-E1-08 RN-02 | Fila por Usuario con `usuario_id`, versión y fecha, más evento en la bitácora | 2 |
| HU-E1-08 RN-03 y criterios 1–3 | Casilla propia, sin marcar, separada de la de términos; también antes de «Continuar con Google» | 2 |
| HU-E1-08 RN-04 y criterio 5 | El invitado acepta **solo** la política al crear su contraseña | 2 |
| HU-E1-08 RN-05 y criterio 6 | Bloqueo hasta aceptar la versión nueva; solo leer y cerrar sesión; no se borra nada | 3 |
| HU-E1-08 RN-06 y criterio 7 | Página pública `/privacidad` (PAN-LEG-01); enlaces en el pie del registro, del ingreso y del panel | 1 |
| HU-E1-08 RN-07 | Texto borrador con el contenido mínimo de la Ley 25.326, la verificación del pagador contra MercadoPago (D94) y la marca «pendiente de validación legal» (pregunta 2) | 1 |
| HU-E1-08 RN-08 | Aviso con enlace en la página del contador, sin aceptación | 1 |
| HU-E1-08 criterio 8 | La bitácora muestra usuario, versión y timestamp | 2 |

**Fuera de esta unidad:**
- **El contenido legal definitivo.** RN-07 exige validación de asesoría legal; esta unidad publica un
  borrador marcado como tal y deja la validación en `docs/aidlc/TODO.md` (pregunta 2).
- Una página pública con el **historial** de versiones anteriores. Se conservan (archivos en el repo y
  filas en la base), pero no se exponen en esta unidad (pregunta 10).
- Consentimientos de clientes finales (WhatsApp) o de proveedores: la política los **describe**
  (RN-07), pero quienes no son Usuarios no aceptan nada en esta unidad.
- Reducir `api/routers/auth.py` por debajo de 400 líneas (hallazgo 7): se reporta, no se refactoriza acá.
- El enlace «¿Olvidaste tu contraseña?» a `/recuperar` (`FormularioDeIngreso.tsx:159`), que tampoco
  tiene ruta: otra historia.

## Hallazgos — el código contradice a las historias o a sí mismo

| # | Dónde (`origin/develop`) | Qué |
|---|---|---|
| 1 | `contexts/identity/application/onboarding.py:124-163` | `AceptarTerminos` **no está conectado a ninguna ruta** (`api/routers/auth.py:26` solo importa `CompletarDatosDeEmpresa`) y **no exige Administrador**, a diferencia de `CompletarDatosDeEmpresa` (`:65-67`). Su comentario (`:159-160`) dice que la versión queda en la bitácora, pero el evento no lleva `detalle` |
| 2 | `contexts/identity/domain/empresa.py:89-91` | `debe_reaceptar_terminos` solo se usa en tests (`tests/contexts/identity/domain/test_agregados.py:92-102`). **HU-E1-03 RN-03 no se cumple de punta a punta**, aunque el épico 1 figura «cerrado en código» en `units.md` |
| 3 | `api/routers/auth.py:61-64, 187` | `RegistroEntrada` no trae ninguna aceptación: el backend registra la versión de `settings.terminos_version_vigente` **sin que nadie la haya aceptado**. La obligatoriedad (RN-02) vive solo en `FormularioDeIngreso.tsx:62-64` |
| 4 | `api/routers/auth.py:366-378` · `FormularioDeIngreso.tsx:194` | El alta con Google registra los términos sin casilla alguna: el enlace «Continuar con Google» no está condicionado. Contradice HU-E1-08 RN-03 y, de hecho, HU-E1-03 RN-02 |
| 5 | `FormularioDeIngreso.tsx:166-178` | **Una sola casilla** para términos y política («Acepto los Términos y Condiciones y la Política de Privacidad»). HU-E1-08 RN-03 exige una propia, separada |
| 6 | `FormularioDeIngreso.tsx:174` · `frontend/src/app/` | El enlace `/terminos` no tiene ruta: **responde 404** (D83). No existe `/privacidad` |
| 7 | `api/routers/auth.py` | **526 líneas**, por encima del límite de 400 de `CLAUDE.md` §5 (no hay hook que lo haga cumplir). Esta unidad lo toca en tres rutas; por eso lo nuevo va a un router propio (pregunta 11) |
| 8 | `platform/settings.py:470, 610` · `backend/.env.example:91` | La versión vigente es una variable de entorno con valor por defecto `"1.0"`, **sin texto ni fecha detrás**. Toda empresa registrada hasta hoy tiene `terminos_version = "1.0"` de un texto que nunca existió (pregunta 3) |
| 9 | `FormularioDeIngreso.tsx:63` vs. HU-E1-03 | El mensaje es el de las anotaciones de comportamiento («Debés aceptar los Términos y Condiciones.», `anotaciones-comportamiento.html:176`); la historia, enmendada por ADR-0009, dice «Debe aceptar los términos y condiciones para continuar.» (pregunta 9) |
| 10 | `api/middleware/empresa.py:49-67` · `consulta_de_sesion.py:78-91` | La verificación por solicitud (unidad `revocacion-inmediata-de-sesion`) lee una sola fila de `usuario`. Es el lugar natural para el bloqueo de RN-05, y extenderla cambia el costo de cada solicitud (Diseño, «Bloqueo») |
| 11 | `contexts/identity/infrastructure/models.py:40-62` | `usuario` no tiene `created_at` (el DER lo declara): no se puede saber quién fue «el primer Administrador» de una empresa. Para atribuir el backfill se usa la bitácora (pregunta 4) |
| 12 | `docs/aidlc/units.md` (fila `renovacion-sin-borrar-sesion`) | Figura «en revisión», pero el PR #118 ya está en `develop` (`e9916a5`). No es de esta unidad; se reporta |

## Diseño

### Dominio — `contexts/identity/domain/legal.py` (nuevo)

- **`DocumentoLegal`** (`StrEnum`): `TERMINOS`, `PRIVACIDAD`. Catálogo cerrado.
- **`VersionDeDocumento`** (value object, inmutable): `documento`, `version` (identificador corto,
  formato `N.N`, hasta 20 caracteres, igual que `empresa.terminos_version`), `vigente_desde` (fecha,
  interpretada en `America/Argentina/Buenos_Aires`), `borrador: bool` (pregunta 2).
- **`CatalogoLegal`** (servicio de dominio puro): recibe la lista de versiones publicadas y responde
  `vigente(documento, hoy)` = la de mayor `vigente_desde <= hoy`. Garantiza **una sola vigente** por
  documento (RN-01) y rechaza al construirse dos versiones con el mismo identificador o la misma fecha.
- **`AceptacionLegal`** (entidad inmutable, como `Invitacion` vive fuera de los dos agregados raíz):
  `id`, `empresa_id`, `usuario_id` (obligatorio salvo en filas de backfill de términos, ver Migración),
  `documento`, `version`, `fecha_aceptacion` (con zona). Constructor `registrar(...)`.
- **`documentos_pendientes(rol, terminos_de_la_empresa, acepto_privacidad_vigente, vigentes)`**
  (función pura): `PRIVACIDAD` si el usuario no aceptó la vigente; `TERMINOS` **solo si el rol es
  Administrador** y `empresa.debe_reaceptar_terminos(vigente)` (HU-E1-03 RN-03: los otros roles no se
  bloquean). Es la única regla de bloqueo, y vive en el dominio.
- **`Empresa`** no cambia de forma: `aceptar_terminos` y `debe_reaceptar_terminos`
  (`domain/empresa.py:85-91`) siguen siendo la fuente del estado vigente que exige el DER.

### Aplicación — un caso de uso por servicio

| Servicio | Entrada → salida | Qué garantiza |
|---|---|---|
| `ConsultarDocumentoVigente` (nuevo) | `documento` → versión, fecha de vigencia, `borrador`, texto | Lectura pública; no toca la base |
| `ConsultarVersionesVigentes` (nuevo) | — → `{TERMINOS: v, PRIVACIDAD: v}` | Lo que los formularios muestran y luego mandan como consentimiento |
| `RegistrarEmpresa` / `RegistrarConGoogle` (cambian, `application/registro.py:42, 117`) | suman `consentimiento: Consentimiento(version_terminos, version_privacidad)` | Sin consentimiento → `ConsentimientoRequerido` (422, mensaje de la historia). Versión distinta de la vigente → `VersionLegalDesactualizada` (409). Registra `empresa.aceptar_terminos` **y** dos filas en `aceptacion_legal`, en la misma transacción que crea empresa y usuario |
| `AceptarInvitacion` (cambia, `application/invitaciones.py:230`) | suma `version_privacidad` | RN-04: solo la política; misma validación de versión; la fila nace en la transacción que activa al usuario |
| `AceptarDocumentosLegales` (nuevo; **reemplaza** al `AceptarTerminos` sin uso) | `usuario_id`, `rol`, lista de `(documento, version)` | Valida contra la vigente; `TERMINOS` exige Administrador (`exigir_administrador`, 403); idempotente por versión (una segunda aceptación de la misma versión no crea otra fila); actualiza `empresa` si son términos |
| `VerificarSesionVigente` (cambia, `application/verificacion_de_sesion.py:31-57`) | suma las vigentes del catálogo | `IdentidadVigente` gana `pendientes: frozenset[DocumentoLegal]`, calculado por `documentos_pendientes` |

`Consentimiento` es un value object de aplicación (dos versiones, ambas obligatorias). Errores nuevos
en `application/errors.py`: `ConsentimientoRequerido` (`EntradaInvalida` → 422),
`VersionLegalDesactualizada` (`InvarianteViolada` → 409). El 403 de rol ya lo da `OperacionNoPermitida`.

### Puertos y adaptadores

| Puerto (`application/ports.py`) | Adaptador | Nota |
|---|---|---|
| `PortCatalogoLegal` — `versiones()` y `texto(documento, version)` | `infrastructure/legal/catalogo.py` + archivos `infrastructure/legal/<documento>/<version>.md` | Se carga una vez al arrancar; **cero E/S por solicitud**. Precedente de archivos empaquetados: `infrastructure/plantillas/invitacion.html` (`email_invitacion.py:40`) |
| `PortRepositorioAceptacionLegal` — `agregar`, `acepto(usuario_id, documento, version)` | `infrastructure/aceptaciones.py` (archivo nuevo; `repositories.py` ya tiene 299 líneas) | Solo `INSERT` y `SELECT` |
| `PortConsultaDeUsuarioVigente.estado_actual` (cambia, `ports.py:117-128`) | `ConsultaDeUsuarioVigentePostgres` (`consulta_de_sesion.py:78-91`) | Sigue siendo **una sentencia**: `usuario` JOIN `empresa` para `terminos_version`, más `EXISTS` sobre `aceptacion_legal` con la versión vigente como parámetro. `EstadoActualDelUsuario` (`ports.py:105-114`) suma dos campos |

**Inmutabilidad de lo publicado (RN-01):** el catálogo declara, por versión, el SHA-256 de su archivo.
Un test unitario recalcula los hashes: editar un texto ya publicado rompe la CI. Corregir un texto es
publicar una versión nueva.

### Bloqueo por versión nueva (HU-E1-03 RN-03, HU-E1-08 RN-05) — dónde se hace cumplir

En el **backend**, en el mismo paso que ya verifica la sesión en cada solicitud (pregunta 5):

1. `VerificadorDeSesionPostgres` (`consulta_de_sesion.py:94-130`) recibe el catálogo al armarse en
   `api/main.py:79` y devuelve `IdentidadVigente.pendientes`.
2. `EmpresaMiddleware` (`api/middleware/empresa.py:134-152`) guarda `pendientes_legales` en
   `request.state` y, si no está vacío, responde **403 `AceptacionLegalPendiente`** a todo lo que no
   esté en una lista corta y explícita: `GET /auth/empresa`, `GET /legal/pendientes`,
   `POST /legal/aceptaciones`. Cerrar sesión (`/auth/logout`) y renovar (`/auth/refresh`) ya son
   públicas (`:49-67`) y siguen funcionando.
3. El costo de la consulta por solicitud **se mide** igual que en `revocacion-inmediata-de-sesion`
   (pregunta 1 de ese plan): `EXPLAIN (ANALYZE)` local y p95 en staging, anotados en «Decisiones».

En el **frontend**, solo la navegación:

- `GET /auth/empresa` suma `aceptaciones_pendientes` (sin consulta extra: sale de `request.state`).
  `(panel)/layout.tsx:56-63` redirige a `/aceptacion-legal` si la lista no está vacía, **antes** del
  chequeo de onboarding. Sin esto, el 403 caería en `estadoDeEmpresa` (`:80-88`), que trata todo 4xx
  como sesión inválida y mandaría al ingreso en un bucle.
- `(alta)/onboarding/empresa/page.tsx` hace el mismo chequeo (hoy no verifica nada, `:12-14`): quien
  dejó el onboarding a medias antes del despliegue acepta primero y completa después.

### API

Router nuevo `api/routers/legal.py` (prefijo `/legal`), incluido en `api/main.py:110` junto a `auth`:

| Método y ruta | Sesión | Qué devuelve |
|---|---|---|
| `GET /legal/terminos`, `GET /legal/privacidad` | pública (rutas **exactas** en `RUTAS_PUBLICAS`, no un prefijo) | versión, `vigente_desde`, `borrador`, texto |
| `GET /legal/vigentes` | pública | las dos versiones vigentes |
| `GET /legal/pendientes` | sí | documentos pendientes con versión y fecha |
| `POST /legal/aceptaciones` | sí | `{documentos: [{documento, version}]}` → 204 |

Cambios en `api/routers/auth.py` (mínimos, por el hallazgo 7): `RegistroEntrada` suma
`consentimiento`; `GoogleEntrada` suma `consentimiento` opcional (obligatorio solo si la cuenta es
nueva, pregunta 6); `AceptacionEntrada` suma `version_privacidad`; `EmpresaSalida` suma
`aceptaciones_pendientes`. Se borra el uso de `settings.terminos_version_vigente` (`:187`, `:375`).

### Otros contextos

`observability`, por evento de dominio (sin cambios en su código):

| Acción | `entidad_afectada` | `detalle` |
|---|---|---|
| `aceptar_terminos` (nombre que ya existe, `onboarding.py:154`) | `Empresa:<id> terminos <version>` | `{"documento": "TERMINOS", "version": "<v>"}` |
| `aceptar_politica_de_privacidad` | `Usuario:<id> privacidad <version>` | `{"documento": "PRIVACIDAD", "version": "<v>"}` |

La versión va también en `entidad_afectada` para que el **listado** de la bitácora la muestre
(criterio 8 de HU-E1-08), con el mismo recurso que `invitaciones.py:124` usa para el rol. `usuario_id`
del evento es quien aceptó. Ningún dato personal en `detalle` (`shared/auditoria.py:133-136`).

### Frontend

**`features/identity`** (todo lo nuevo sale por `index.ts`, regla R5):

- `CasillasLegales`: dos casillas separadas y sin marcar, cada una con su enlace y su mensaje de error
  (RN-03). La usan el registro (las dos) y la invitación (solo privacidad).
- `TextoLegal`: dibuja el texto del catálogo. Los textos se escriben en un **subconjunto de Markdown**
  (títulos `##`, párrafos, listas `-`) y este componente lo arma con elementos de React: sin
  `dangerouslySetInnerHTML` y sin dependencia nueva (pregunta 1).
- `FormularioDeReaceptacion`: la variante de PAN-ONB-01 para quien tiene pendientes. Muestra qué cambió
  (documento, versión, fecha), enlaza el texto, ofrece **«Aceptar»** y **«Cerrar sesión»** y nada más
  (RN-05, pregunta 7).
- `EnlacesLegales` (pie) y `AvisoDePrivacidad` (contador).
- `FormularioDeIngreso`: dos casillas en modo registro; en ese modo el botón de Google **no navega**
  si falta alguna y muestra el mismo mensaje (criterio 3 de HU-E1-08); con las dos marcadas va a
  `/api/auth/google?terminos=<v>&privacidad=<v>`. Pie con los dos enlaces en ambos modos (RN-06).
- `FormularioDeAceptacion`: suma la casilla de privacidad.
- `api/cliente.ts`: `registrar` y `aceptarInvitacion` mandan las versiones; nuevas `aceptarDocumentos`.

**Rutas:**

| Ruta | Grupo | Pantalla |
|---|---|---|
| `/terminos` | `(public)` (nueva) | PAN-LEG-02 (pregunta 8) |
| `/privacidad` | `(public)` (nueva) | PAN-LEG-01 |
| `/aceptacion-legal` | `(alta)` (nueva) | PAN-ONB-01, variante de re-aceptación |
| `/` | `(ingreso)` | lee `/legal/vigentes` en el servidor y se las pasa al formulario |
| `/invitacion/[token]` | `(alta)` | ídem, solo privacidad |
| `(panel)/layout.tsx` | — | redirección por pendientes; pie de `carcasa-del-panel.tsx:140` con los enlaces |
| `/contador/[valor]` | `(public)` | compone `AvisoDePrivacidad` desde `@/features/identity` |

**Las páginas públicas nunca deben dar error (HU-E1-03 RN-05).** Se renderizan en el servidor con
revalidación (ISR, una hora) en lugar de `no-store`: si el backend no responde al revalidar, Next sigue
sirviendo la última versión buena. `lib/api.ts:81` fija `cache: "no-store"` por defecto; la página usa
la opción de revalidación de `fetch` sin cambiar ese valor por defecto para el resto del panel.

**BFF:** `app/api/auth/registro` y `invitaciones/aceptar` reenvían las versiones;
`app/api/auth/google/route.ts` guarda el consentimiento en una cookie HttpOnly de 10 minutos junto al
`state` (`:35-45`) y `google/callback` la reenvía; nueva `app/api/legal/aceptaciones/route.ts`.

## Infraestructura

### Migración — `00NN_aceptacion_legal.py`

**El número se asigna al implementar**, después de que entre la cola. `develop` termina en `0039`
(`0039_reintento_de_recordatorios.py`); `0040_recordatorio_de_turno.py` ya está tomado en
`feature/scheduling-recordatorio-de-turno-modelo` y `-envio` (no mergeadas). **Número esperado: 0041.**

```
aceptacion_legal
  id                uuid PK
  empresa_id        uuid NN  FK empresa  ON DELETE RESTRICT
  usuario_id        uuid     FK usuario  ON DELETE RESTRICT
  documento         varchar(20) NN  CHECK (documento IN ('TERMINOS','PRIVACIDAD'))
  version           varchar(20) NN
  fecha_aceptacion  timestamptz NN
  created_at        timestamptz NN default now()
  CHECK (usuario_id IS NOT NULL OR documento = 'TERMINOS')
  UNIQUE (usuario_id, version) WHERE documento = 'PRIVACIDAD'
  UNIQUE (empresa_id, version) WHERE documento = 'TERMINOS'
```

- **Lleva `empresa_id` y RLS `aislamiento_por_empresa` con `FORCE`**, como `usuario`, `invitacion` y
  `refresh_token` (`0003_usuarios_y_preferencias.py:42-46, 139-146`). Aunque la política sea por
  usuario, cada usuario pertenece a una sola empresa (`usuario.empresa_id` NN) y toda lectura ocurre
  en una sesión acotada a la suya, incluida la verificación por solicitud (`consulta_de_sesion.py:124`).
  Sin `empresa_id`, la tabla sería la única de identity sin barrera de RLS. `backend/scripts/verify_rls.py`
  la controla sola: chequea toda tabla con `empresa_id`.
- **Sin IP** (D83). Los eventos de bitácora sí la llevan, como toda operación (pregunta 12).
- **Solo `SELECT, INSERT`** para `cheatsheet_app`: una aceptación es evidencia y no se edita ni se
  borra (mismo criterio que `registro_de_auditoria`, `0001_registro_de_auditoria.py:75-76`).
  `RESTRICT` en las dos claves por la misma razón. `RevocarInvitacion` borra usuarios `INVITADO`
  (`invitaciones.py:182-227`), que nunca tienen aceptaciones: el invitado acepta al activarse.
- **Backfill, sin inventar datos** (patrón de `0027_reembolsos.py:24-32`; corre con el rol de
  migraciones, que tiene `BYPASSRLS`): por cada empresa con `terminos_version`, una fila `TERMINOS` con
  esa versión y esa fecha, atribuida al usuario del evento `registrar_empresa` /
  `registrar_empresa_con_google` de `registro_de_auditoria` (`entidad_afectada = 'Empresa:<id>'`); si no
  aparece, `usuario_id = NULL` (pregunta 4). Ninguna fila de `PRIVACIDAD`: nadie aceptó todavía una
  política que no existía. **No se borra ni se modifica nada**: las columnas de `empresa` quedan igual.
- **Reversible con pérdida declarada**: `downgrade` borra la tabla y con ella el historial; las
  columnas de `empresa` conservan la última aceptación de términos.

### Trabajo asíncrono

No aplica.

### Configuración

Se **elimina** `TERMINOS_VERSION_VIGENTE` (`backend/.env.example:91`, `platform/settings.py:470, 610`,
`backend/tests/conftest.py:104`): la versión vigente pasa a salir del catálogo, una sola fuente. Si
Render la tiene cargada, sobra y se quita (anotado en el PR del tramo 2). Ninguna variable nueva.

### Integraciones externas

No aplica.

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero
- [ ] Toca comprobantes fiscales / CAE
- [ ] Consume un webhook
- [x] Agrega datos con `empresa_id` → test de aislamiento entre empresas sobre `aceptacion_legal`
- [ ] Usa salida de un LLM
- [x] Datos personales → la aceptación es un consentimiento de la Ley 25.326; nada personal en
  `detalle` de la bitácora, nada enviado a un LLM
- [x] **Toca autenticación** (middleware de cada solicitud): el Gate 2 del tramo 3 incluye un
  verificador independiente, como `revocacion-inmediata-de-sesion`

## Archivos a tocar

**Tramo 1 — textos públicos**
- [x] `backend/src/cheatsheet/contexts/identity/domain/legal.py` (`DocumentoLegal`, `VersionDeDocumento`, `CatalogoLegal`)
- [x] `backend/src/cheatsheet/contexts/identity/infrastructure/legal/catalogo.py` · `legal/terminos/<v>.md` · `legal/privacidad/<v>.md`
- [x] `backend/src/cheatsheet/contexts/identity/application/legal.py` (`ConsultarDocumentoVigente`, `ConsultarVersionesVigentes`) · `application/ports.py` (`PortCatalogoLegal`)
- [x] `backend/src/cheatsheet/api/routers/legal.py` · `api/main.py` · `api/middleware/empresa.py` (`RUTAS_PUBLICAS`)
- [x] `frontend/src/features/identity/components/{TextoLegal,EnlacesLegales,AvisoDePrivacidad}.tsx` · `index.ts` · `api/cliente.ts`
- [x] `frontend/src/app/(public)/terminos/page.tsx` · `(public)/privacidad/page.tsx` · `(public)/contador/[valor]/page.tsx` · `(panel)/carcasa-del-panel.tsx` · `FormularioDeIngreso.tsx` (solo el pie)
- [x] Tests: `backend/tests/contexts/identity/domain/test_legal.py` · `.../application/test_legal.py` · `backend/tests/api/test_legal.py` · tests de componentes y páginas
- [x] `docs/aidlc/TODO.md` (validación legal del texto, pregunta 2)

**Tramo 2 — aceptación en el alta**
- [x] `backend/migrations/versions/0041_aceptacion_legal.py` (sin tocar `migrations/env.py`: importa el módulo `models` entero, y el modelo nuevo vive ahí)
- [x] `contexts/identity/domain/legal.py` (`AceptacionLegal`) · `infrastructure/models.py` (`AceptacionLegalORM`) · `infrastructure/aceptaciones.py` · `infrastructure/ensamblado.py` · `infrastructure/legal/catalogo.py` (`catalogo_publicado`, una sola instancia por proceso)
- [x] `contexts/identity/application/registro.py` · `invitaciones.py` · `errors.py` · `ports.py` · `aceptaciones.py` (nuevo: `Consentimiento` y `RegistradorDeAceptaciones`, el único lugar que valida el consentimiento y escribe la evidencia) · `legal.py` (`vigente_a`)
- [x] `api/routers/auth.py` (tres entradas, +11 líneas netas: 526 → 537) · `api/routers/legal.py` (`ConsentimientoEntrada`) · `api/errors.py` no hizo falta: `ConsentimientoRequerido` es `EntradaInvalida` (422) y `VersionLegalDesactualizada` es `InvarianteViolada` (409)
- [x] `platform/settings.py` · `backend/tests/conftest.py` · **pendiente del dueño: quitar `TERMINOS_VERSION_VIGENTE` de `backend/.env.example:91`** (los agentes no editan `.env*`) y de Render si está cargada
- [x] `frontend/src/features/identity/components/{CasillasLegales,FormularioDeIngreso,FormularioDeAceptacion}.tsx` · `validacion/consentimiento.ts` · `api/cliente.ts` · `index.ts`
- [x] `frontend/src/app/(ingreso)/page.tsx` · `(alta)/invitacion/[token]/page.tsx` · `app/_versiones-legales.ts` · `app/api/auth/{google,google/callback}/route.ts` (`registro` e `invitaciones/aceptar` no cambian: reenvían el cuerpo tal cual, y ahora el cuerpo trae las versiones)
- [x] `backend/tests/integracion/conftest.py` — `"DELETE FROM aceptacion_legal"` **antes** de `"DELETE FROM usuario"` y de `"DELETE FROM empresa"` (`:146-149`), de la hoja a la raíz
- [x] `backend/tests/integracion/test_migracion_0041.py` · `test_aceptacion_legal_postgres.py` · `consentimiento.py` (versiones vigentes para los tests) · ajustes en `test_identidad_postgres.py` y en los 19 `test_api_*`/`test_*_postgres.py` que se registran o aceptan una invitación (mandan consentimiento)

**Tramo 3 — re-aceptación**
- [x] `contexts/identity/domain/legal.py` (`documentos_pendientes`) · `application/verificacion_de_sesion.py` (`IdentidadVigente.pendientes`) · `application/aceptaciones.py` (`AceptarDocumentosLegales`, junto al `RegistradorDeAceptaciones` que reutiliza; no en `application/legal.py`) · `application/onboarding.py` (se borra `AceptarTerminos`, sin uso)
- [x] `contexts/identity/infrastructure/consulta_de_sesion.py` · `infrastructure/aceptaciones.py` (`agregar` devuelve `bool`, `INSERT … ON CONFLICT DO NOTHING`) · `infrastructure/ensamblado.py` · `application/ports.py` · `api/middleware/empresa.py` (`RUTAS_CON_PENDIENTES`) · `api/main.py` · `api/routers/legal.py` (`GET /legal/pendientes`, `POST /legal/aceptaciones`) · `api/routers/auth.py` (`EmpresaSalida`, +2 líneas: 537 → 539)
- [x] `frontend/src/features/identity/components/{FormularioDeReaceptacion,VigilanteDeAceptacionLegal,etiquetas-legales}` · `app/(alta)/aceptacion-legal/page.tsx` · `app/(alta)/layout.tsx` · `app/(alta)/_componentes/PanelDelAlta.tsx` · `app/(panel)/layout.tsx` · `app/(alta)/onboarding/empresa/page.tsx` · `app/api/legal/aceptaciones/route.ts`
- [x] Tests: `tests/integracion/consentimiento.py` (`verificador_de_sesion`, `sembrar_privacidad_vigente`) · `test_consulta_de_sesion_postgres.py` (la consulta cambia) · `test_bloqueo_legal_postgres.py` · `test_api_bitacora.py` (la siembra del usuario Solo Lectura) · `test_aceptacion_legal_postgres.py` (el duplicado ya no levanta `IntegrityError` en el repositorio) · `tests/api/` con verificador falso (suma `pendientes`) y `test_bloqueo_legal.py` · fakes de `contexts/identity/` (`fila`, `ConsultaDeUsuarioVigenteEnMemoria`)
- [x] `docs/aidlc/TODO.md` §22.74–22.76 y §27 · este plan (`units.md` no se toca: lo actualiza el dueño al cerrar el tramo)

## Casos de prueba

TDD: cada caso se escribe en RED antes del código. Backend con `pytest`; integración contra
PostgreSQL real (`backend/tests/integracion/`, se saltean sin base y la CI siempre la configura);
frontend con `vitest` (`npm run test:coverage`). Ningún test toca la red.

| # | Caso | Tipo | Tramo | Estado |
|---|---|---|---|---|
| 1 | `CatalogoLegal.vigente` elige la de mayor `vigente_desde <= hoy`; una futura no es vigente | unit dominio | 1 | hecho |
| 2 | El catálogo rechaza dos versiones con el mismo identificador o la misma fecha | unit dominio | 1 | hecho |
| 3 | El SHA-256 de cada archivo publicado coincide con el declarado (editar un texto rompe la CI) | unit infra | 1 | hecho |
| 4 | El texto vigente de privacidad contiene los apartados mínimos de RN-07 (finalidad, destinatarios, responsable, carácter de los datos, derechos ARCO, clientes finales y proveedores, verificación del pagador contra MercadoPago) | unit infra | 1 | hecho |
| 5 | `GET /legal/terminos` y `/legal/privacidad` responden **sin token** con versión y fecha | API | 1 | hecho |
| 6 | Una ruta con prefijo `/legal/` que no está en la lista exacta **sí** exige sesión | API | 1 | hecho |
| 7 | `/terminos` y `/privacidad` muestran versión, fecha de vigencia y la marca de borrador | página (vitest) | 1 | hecho |
| 8 | `TextoLegal` no interpreta HTML incrustado en el texto | componente | 1 | hecho |
| 9 | El pie del ingreso (ambos modos), del registro y del panel enlaza las dos páginas | componente | 1 | hecho |
| 10 | La página del contador muestra el aviso con el enlace y no ofrece aceptar | página | 1 | hecho |
| 11 | `AceptacionLegal` exige versión, fecha con zona y `usuario_id` para `PRIVACIDAD` | unit dominio | 2 | hecho |
| 12 | Registro sin consentimiento → 422 con «Debe aceptar …» y no crea empresa ni usuario | unit aplicación + API | 2 | hecho |
| 13 | Registro con una versión que ya no es la vigente → 409 y no crea nada | unit aplicación | 2 | hecho |
| 14 | Registro válido → `empresa.terminos_*`, una fila `TERMINOS`, una fila `PRIVACIDAD` y dos eventos de bitácora con la versión en `entidad_afectada` | unit aplicación + integración | 2 | hecho |
| 15 | Google, cuenta nueva sin consentimiento → no se crea la cuenta (pregunta 6); con consentimiento → igual que el caso 14 | unit aplicación + API | 2 | hecho |
| 16 | Google, cuenta existente → inicia sesión sin pedir consentimiento | API | 2 | hecho |
| 17 | Aceptar invitación sin `version_privacidad` → rechazo y el usuario sigue `INVITADO`; con ella → una fila `PRIVACIDAD` y **ninguna** de `TERMINOS` | unit aplicación + integración | 2 | hecho |
| 18 | Las dos casillas aparecen separadas y sin marcar; cada una bloquea con su mensaje | componente | 2 | hecho |
| 19 | En modo registro, «Continuar con Google» sin las casillas no navega y muestra el mensaje | componente | 2 | hecho |
| 20 | La cookie de consentimiento viaja del inicio del flujo de Google al callback y se borra después | BFF (vitest) | 2 | hecho |
| 21 | RLS: una empresa no ve ni inserta aceptaciones de otra | integración | 2 | hecho |
| 22 | El rol de la aplicación no puede `UPDATE` ni `DELETE` en `aceptacion_legal` | integración | 2 | hecho |
| 23 | Índices parciales: la misma versión de privacidad dos veces para el mismo usuario se rechaza | integración | 2 | hecho |
| 24 | Migración: el backfill crea una fila `TERMINOS` por empresa con términos, atribuida por la bitácora, `NULL` si no hay evento, y no toca `empresa` | integración (`test_migracion_00NN.py`) | 2 | hecho |
| 25 | `documentos_pendientes`: Administrador con términos viejos → `TERMINOS`; Operador y Solo Lectura con términos viejos → nada; cualquiera sin la privacidad vigente → `PRIVACIDAD` | unit dominio | 3 | hecho |
| 26 | La consulta por solicitud devuelve los pendientes en **una** sentencia, bajo RLS | integración | 3 | hecho |
| 27 | Con pendientes, una ruta cualquiera → 403 `AceptacionLegalPendiente`; `GET /auth/empresa`, `GET /legal/pendientes` y `POST /legal/aceptaciones` → pasan | API | 3 | hecho |
| 28 | Un Operador no puede aceptar `TERMINOS` (403) | unit aplicación | 3 | hecho |
| 29 | Aceptar la versión vigente desbloquea en la solicitud siguiente; aceptarla dos veces no duplica la fila | integración | 3 | hecho |
| 30 | La aceptación anterior sigue en la tabla después de aceptar la nueva (RN-05: historial) | integración | 3 | hecho |
| 31 | El layout del panel redirige a `/aceptacion-legal` con pendientes, antes del chequeo de onboarding; el onboarding hace lo mismo | página (vitest) | 3 | hecho |
| 32 | La pantalla de re-aceptación ofrece solo «Aceptar» y «Cerrar sesión» | componente | 3 | hecho |
| 33 | Costo de la consulta por solicitud medido (local y staging), anotado en «Decisiones» | medición | 3 | hecho en local (decisión 24); staging en `TODO.md` §22.74 |

## Verificación (Gate 2, en cada tramo)

```bash
ruff format --check . && ruff check . && mypy . && pytest
cd frontend && npm run format:check && npm run lint && npm run typecheck && npm run test:coverage
bash .claude/hooks/test_guards.sh
```

Más, en el tramo 3, un **verificador independiente** sobre el middleware y la consulta por solicitud.
Lo que solo se ve en un navegador (páginas públicas, flujo de Google, redirección por pendientes) se
prueba en **staging de Render**, no en local; lo que no pueda probarse antes del Gate 2 queda en
`docs/aidlc/TODO.md` §22.

## Tamaño estimado y tramos

Estimación (heurística de planificación, no un tope), en líneas escritas: dominio y aplicación ~350,
infraestructura y migración ~300, API ~200, frontend ~550, textos legales ~200, tests ~1.100. **Unas
2.700 en total**: no entra en un PR revisable. Se proponen **tres tramos, cada uno con su rama y su
PR a `develop`**, en orden, cada uno verificable por sí solo:

| Tramo | Rama | Cierra | Depende de | ~líneas |
|---|---|---|---|---|
| 1 · Textos públicos | `feature/identity-terminos-y-privacidad` | El 404, RN-01/04/05/06/08, el aviso del contador | — | ~800 |
| 2 · Aceptación en el alta | `feature/identity-terminos-y-privacidad-alta` | HU-E1-03 RN-01/02, HU-E1-08 RN-02/03/04, criterio 8 | tramo 1 mergeado | ~1.000 |
| 3 · Re-aceptación | `feature/identity-terminos-y-privacidad-reaceptacion` | HU-E1-03 RN-03, HU-E1-08 RN-05 | tramo 2 mergeado | ~900 |

Entre el tramo 2 y el 3, los usuarios existentes no tienen aceptación de privacidad y nada los bloquea
todavía: es un estado intermedio honesto (lo mismo que hoy), y el tramo 3 lo cierra.

## Preguntas para el Gate 1

**1. ¿Dónde viven los textos versionados?**
- (a) Archivos Markdown en el backend (`identity/infrastructure/legal/`), con un catálogo que declara
  versión, fecha de vigencia y hash; el frontend los pide por API.
- (b) Una tabla `documento_legal` en la base, con el texto adentro.
- (c) Archivos estáticos en el frontend, y el backend solo conoce los identificadores de versión.

**Recomendación: (a).** Una sola fuente de verdad para la versión vigente (la que el backend exige al
aceptar y la que la página muestra), la inmutabilidad la garantiza un test de hashes y la revisión del
PR, y publicar una versión es un PR más, sin pantalla de administración. (b) necesita una herramienta
para cargar textos que nadie pidió y deja la inmutabilidad en manos de permisos; (c) duplica la versión
en dos paquetes que se despliegan por separado, y el día que difieran se acepta un texto distinto del
que se mostró. El texto usa un subconjunto de Markdown dibujado por un componente propio, sin
dependencia nueva.

**2. ¿Qué texto se publica hasta que la asesoría legal lo valide (RN-07)?**
- (a) Un borrador que cubre todos los apartados mínimos de RN-07, con los datos del responsable
  marcados como `[a completar]`, publicado con `borrador = true` y una franja visible «Versión
  preliminar, pendiente de validación legal»; la versión validada se publica después como **versión
  nueva** (todos la vuelven a aceptar).
- (b) No publicar nada hasta tener el texto validado (la unidad espera).
- (c) Publicar el borrador sin marca.

**Recomendación: (a)**, con una entrada en `docs/aidlc/TODO.md` que diga que **no se publica en
producción** con `borrador = true`. Deja funcionando todo el mecanismo en staging sin inventar
contenido legal, y respeta RN-01 (lo publicado no se edita). (b) bloquea la unidad por un tercero; (c)
presenta como definitivo un texto que no lo es.

**3. ¿Qué pasa con los usuarios que ya existen al desplegar?**
- (a) Política: todos la aceptan en su siguiente solicitud (es RN-05 aplicada a la primera versión).
  Términos: se publican como versión **`1.1`**, así cada Administrador acepta el texto real; la `1.0`
  registrada hasta hoy queda en la historia.
- (b) Igual, pero los términos se publican como `1.0` y nadie los re-acepta.

**Recomendación: (a).** La `1.0` que figura en cada empresa es la de una variable de entorno sin texto
detrás (hallazgo 8): reutilizar el identificador haría pasar esa aceptación por la de un texto que la
persona nunca pudo leer, que es justo lo que D83 señala («informada solo en apariencia»). El costo es
un bloqueo por usuario, una sola vez, en staging.

**4. ¿A quién se atribuyen las aceptaciones de términos que ya existen (backfill)?**
- (a) Al usuario del evento `registrar_empresa` / `registrar_empresa_con_google` de la bitácora; si no
  hay evento, `usuario_id = NULL` (permitido solo para `TERMINOS` por un `CHECK`).
- (b) Al Administrador activo más antiguo — no se puede calcular: `usuario` no tiene `created_at`
  (hallazgo 11).
- (c) No migrar: empezar el historial desde cero.

**Recomendación: (a).** La bitácora registró en el mismo acto quién creó la empresa
(`registro.py:91, 162-174`), así que es el dato exacto, no una suposición; el `NULL` deja dicho «no se
sabe» en vez de inventarlo, como `registrado_por = NULL` en `0027_reembolsos.py`. (c) pierde la `1.0`
la primera vez que un Administrador acepte la `1.1`, porque las columnas de `empresa` se sobrescriben.

**5. ¿Dónde se hace cumplir el bloqueo por versión nueva?**
- (a) En el backend, en la verificación por solicitud que ya existe (403 salvo tres rutas), más la
  redirección en el frontend.
- (b) Solo en el frontend (el layout redirige; la API sigue respondiendo).

**Recomendación: (a).** RN-05 dice «hasta entonces solo puede ver la política y cerrar sesión», y una
regla de negocio que vive solo en el navegador no se cumple (`CLAUDE.md` §5: el frontend no lleva
lógica de negocio). Cuesta extender una consulta que ya corre en cada solicitud (un `JOIN` y un
`EXISTS` por índice), y ese costo se mide (caso 33). No cambia el esquema de autenticación, así que no
hace falta un ADR (mismo criterio que D84).

**6. Alta con Google: ¿qué pasa si alguien llega a crear una cuenta sin haber marcado las casillas?**
(por ejemplo, tocando «Continuar con Google» desde el modo «Ingresar» con un email nuevo).
- (a) No se crea la cuenta: el BFF vuelve al formulario en modo registro con el mensaje «Debe aceptar
  la política de privacidad para continuar.». Las cuentas existentes inician sesión como hoy.
- (b) Se crea la cuenta sin aceptaciones y el bloqueo del tramo 3 se las pide al entrar.

**Recomendación: (a).** HU-E1-08 RN-03 exige aceptar **antes** de «Continuar con Google», y una empresa
sin términos aceptados no debería existir (`registro.py:74-76`). Cambia una línea del contrato actual
(«alta e ingreso son el mismo endpoint», `auth.py:349-353`) solo para cuentas nuevas sin
consentimiento; no reabre la enumeración de cuentas, porque Google ya probó que el email es de quien
pregunta.

**7. Si el usuario no acepta la versión nueva, ¿se le cierra la sesión?**
- (a) No se cierra sola: la pantalla ofrece solo «Aceptar» y «Cerrar sesión», y mientras tanto la API
  le responde 403 a todo lo demás. No se borra ningún dato.
- (b) Rechazar cierra la sesión de inmediato (un botón «No acepto»).

**Recomendación: (a).** Es lo que dice RN-05 («solo puede ver la política y cerrar sesión») y el
criterio («si no acepto, solo puedo cerrar sesión»): cerrar sesión es una opción, no una consecuencia.
Un botón «No acepto» que desloguea es (a) con otra etiqueta, y suma un camino más que probar.

**8. Códigos de pantalla.**
- (a) `PAN-LEG-01` = Política de privacidad (pública); `PAN-LEG-02` = Términos y condiciones
  (pública); la re-aceptación es una variante de `PAN-ONB-01` en la ruta `/aceptacion-legal`, que es
  la pantalla que nombran los criterios de las dos historias.
- (b) Un código propio para la re-aceptación (`PAN-LEG-03`).

**Recomendación: (a).** Respeta lo que las historias ya nombran (HU-E1-08 propone PAN-LEG-01 para la
política; los criterios de re-aceptación citan PAN-ONB-01) y asigna el único código que falta. Se anota
en «Decisiones» para que la próxima lectura del catálogo lo encuentre.

**9. ¿Qué mensaje muestran las casillas?**
- (a) El de las historias, enmendadas por ADR-0009: «Debe aceptar los términos y condiciones para
  continuar.» y «Debe aceptar la política de privacidad para continuar.».
- (b) El de las anotaciones de comportamiento para términos («Debés aceptar los Términos y
  Condiciones.») y el de la historia para privacidad.

**Recomendación: (a).** Las historias son posteriores a las anotaciones y son la fuente de los
criterios de aceptación; además, el mensaje de privacidad solo existe en la historia, y dos mensajes
en dos registros distintos en la misma pantalla se ven como un error.

**10. ¿Se publican también las versiones anteriores?**
- (a) No en esta unidad: se conservan (archivos en el repo, filas en la base) y la página muestra solo
  la vigente.
- (b) Sí: `/privacidad/<version>` para cada versión publicada.

**Recomendación: (a).** RN-01 pide **conservarlas como evidencia**, no publicarlas, y ningún criterio
lo exige. (b) es una ruta más que mantener siempre disponible; se suma cuando alguien la pida.

**11. `api/routers/auth.py` ya tiene 526 líneas (límite 400). ¿Qué se hace en esta unidad?**
- (a) Lo nuevo va a `api/routers/legal.py`; en `auth.py` solo los cuatro modelos de entrada/salida
  (unas 15 líneas netas), y el exceso se reporta en `docs/aidlc/TODO.md`.
- (b) Partir `auth.py` en esta unidad (sacar invitación y Google a su propio módulo).

**Recomendación: (a).** `CLAUDE.md` §8 pide no ampliar el alcance: partir el router de autenticación
es un refactor con su propio riesgo y merece su propio PR. Esta unidad no lo empeora de forma
apreciable.

**12. ¿Los eventos de bitácora de una aceptación guardan la IP, como todos los demás?**
- (a) Sí: la tabla `aceptacion_legal` no guarda IP (D83), y la bitácora la guarda como en toda
  operación (HS-T5).
- (b) No: estos eventos se publican con `direccion_ip = None`.

**Recomendación: (a).** D83 habla de la tabla de aceptaciones; la bitácora tiene su propia regla
(HS-T5 RN-02 lista la IP entre los datos que captura) y ya la aplica a cada alta, invitación y cambio
de rol. Hacer una excepción acá dejaría la bitácora inconsistente sin que ninguna regla lo pida.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-10 | Aprobado por Luciano con las recomendaciones de las preguntas 1–12. Tres tramos apilados; la migración toma el número libre al implementar (0041 si `recordatorio-de-turno` entra antes) |
| 2 · Verificación del tramo 1 | 2026-10-10 | Aprobado por Luciano. RED observado en cada caso; ruff, mypy, pytest (2977, sin PostgreSQL), frontend (1237), lint, typecheck, prettier y guards en verde. Hallazgos renumerados a `TODO.md` §27. El tramo 2 se apila en `feature/identity-terminos-y-privacidad-alta` |
| 2 · Verificación del tramo 2 | 2026-10-10 | Aprobado por Luciano con las correcciones de la verificación independiente (decisión 19): las cookies de OAuth se borran con su propio `path`, el consentimiento de Google viaja por POST desde el formulario y no por GET, y `acepto` queda para el tramo 3. Decisiones 13–18 confirmadas. Integración completa contra PostgreSQL local (640) y frontend (1360) en verde |
| 3 · PR | 2026-10-10 | Un PR por tramo, en orden 1 → 2 → 3. GitHub Actions sin cuota hasta el 2026-11-01: cada PR se verifica con el CI local (`backend/scripts/run_local_ci.py`), resumen en el PR |

## Decisiones tomadas durante la unidad

Gate 1 (2026-10-10), todas según la recomendación:

1. Textos legales en Markdown en `identity/infrastructure/legal/`, con catálogo de versión, vigencia y hash; el frontend los pide por API.
2. Hasta que la asesoría legal lo valide se publica un borrador marcado como tal que cubre RN-07; no va a producción como borrador (TODO). El texto validado sale como versión nueva.
3. Al desplegar, todos aceptan la política en su próxima solicitud; los términos se publican como `1.1` para que los Administradores acepten un texto real.
4. La aceptación previa se atribuye al usuario del evento `registrar_empresa*`; si no hay, `usuario_id` NULL, permitido solo para `TERMINOS` por un CHECK.
5. El bloqueo se hace cumplir en la verificación por solicitud del backend, más una redirección en el frontend. Sin ADR: el esquema de autenticación no cambia.
6. Alta con Google sin las casillas: no se crea la cuenta y se vuelve al modo registro con el mensaje. Las cuentas existentes no cambian.
7. No aceptar una versión nueva no cierra la sesión: la pantalla ofrece «Aceptar» y «Cerrar sesión», la API responde 403 al resto y no se borra nada.
8. Códigos de pantalla: PAN-LEG-01 (privacidad), PAN-LEG-02 (términos); la re-aceptación es una variante de PAN-ONB-01 en `/aceptacion-legal`.
9. Los mensajes de las casillas son los de las historias enmendadas por ADR-0009.
10. Las versiones anteriores se conservan como evidencia; no se publican en esta unidad.
11. El código nuevo va a `api/routers/legal.py`; `auth.py` (526 líneas) no se parte en esta unidad y el exceso se reporta en `TODO.md`.
12. Los eventos de bitácora de una aceptación guardan la IP como todos los demás; la tabla `aceptacion_legal` no la guarda.

Tramo 2 (2026-10-10), decisiones de implementación que el plan no fijaba:

13. **El consentimiento se valida antes que el resto**: un registro sin consentimiento responde 422 (y uno con una versión vieja, 409) aunque el email ya exista. Nada se escribe antes de validar, y todo corre en la transacción del llamador, así que un rechazo no deja empresa, usuario ni aceptación.
14. **Un único servicio** (`RegistradorDeAceptaciones`, `application/aceptaciones.py`) valida el consentimiento contra el catálogo y escribe la fila y el evento; `RegistrarEmpresa`, `RegistrarConGoogle` y `AceptarInvitacion` lo reciben. Así los tres caminos no pueden divergir. La fila de términos de una empresa se atribuye al usuario que la registra (el primer Administrador).
15. **Orden de los eventos**: primero `registrar_empresa` (o `registrar_empresa_con_google`) y después los de aceptación, para que el registro siga abriendo la historia de la empresa en la bitácora.
16. **Las páginas leen `/legal/vigentes` con revalidación de 60 s** (no 3600 como las páginas legales): una versión que entra en vigencia hoy no debe tardar una hora en llegar al formulario. Si la lectura falla, la página no cae: el formulario deja ingresar y se niega a crear cuentas, diciendo por qué.
17. **Google sin consentimiento vuelve con un solo mensaje**: el de la política de privacidad, tal como lo fija la pregunta 6. Las dos casillas están sin marcar en ese caso, pero el plan nombra un único mensaje y se respetó; marcar las dos y reintentar funciona.
18. **El catálogo es una instancia por proceso** (`catalogo_publicado()`): el router legal y el ensamblado de identidad comparten los textos ya leídos y verificados por hash.
19. **Gate 2 del tramo 2 (2026-10-10), aprobado por Luciano**: cuatro correcciones. (1) La cookie de consentimiento nunca se borraba: se pone con `path=/api/auth` pero `cookies().delete()` expira `Path=/`, así que el navegador conservaba la real. Ahora se vence con los mismos atributos con que se puso (`borrarCookieDeOAuth`, `app/api/auth/_oauth.ts`). (2) Lo mismo para `COOKIE_STATE`, que ya fallaba en `develop`: un `state` usado seguía vigente 10 minutos y podía repetirse; se corrige aquí por ser el mismo mecanismo en las mismas líneas. (3) El consentimiento ya no viaja en la query de un GET: el alta con Google es un `<form method="post">` con las dos versiones, el BFF responde 303 a Google, un GET no registra nada y un POST con `Origin` ajeno se trata como ingreso sin consentimiento (el backend sigue validando las versiones). El ingreso con una cuenta existente sigue siendo un enlace. (4) `PortRepositorioAceptacionLegal.acepto` se conserva: el plan (fila de `AceptarDocumentosLegales` y caso 29) exige que aceptar dos veces la misma versión no cree otra fila, y ese es su único uso; queda anotado en su docstring.

Tramo 3 (2026-10-10), decisiones de implementación que el plan no fijaba:

20. **`AceptarDocumentosLegales` vive en `application/aceptaciones.py`**, junto al `RegistradorDeAceptaciones` que reutiliza (no en `application/legal.py`, como decía el plan): escribe la fila y el evento por el mismo camino que el alta, así que no pueden divergir. Valida **todo antes de escribir** (un pedido que mezcla una privacidad válida con términos que el rol no puede aceptar no registra ninguno), es idempotente por versión y mueve `empresa.terminos_*` en la misma transacción. Una lista vacía es 422.
21. **`PortRepositorioAceptacionLegal.agregar` devuelve `bool`** (`INSERT … ON CONFLICT DO NOTHING … RETURNING`): dos pedidos que aceptan la misma versión a la vez dejan **una** fila y **un** evento, y el que pierde la carrera no recibe un 500 por `IntegrityError`. Los índices únicos parciales siguen siendo la garantía (el caso 23 lo prueba con un `INSERT` sin `ON CONFLICT`). Consecuencia: `acepto` se usa como atajo previo, no como único guarda.
22. **El 403 `AceptacionLegalPendiente` lleva `pendientes`** (nombres de documento, orden estable; ni versión ni texto: eso lo da `GET /legal/pendientes`). Se decide por **método y ruta exactos** (`RUTAS_CON_PENDIENTES`): `GET /auth/empresa`, `GET /legal/pendientes`, `POST /legal/aceptaciones`; `PUT /auth/empresa` o cualquier otro método sobre esas rutas se bloquea. Leer los textos, cerrar sesión y renovar ya eran públicas.
23. **Frontend, el 403 «desde cualquier llamada»**: `VigilanteDeAceptacionLegal` envuelve el `fetch` del navegador (montado en los layouts `(panel)` y `(alta)`) y, ante un 403 `AceptacionLegalPendiente` de `/api/…` de la propia app, navega a `/aceptacion-legal` y **no resuelve** la llamada, para que la pantalla no muestre «No se pudo completar la operación» (patrón del issue #75). Cualquier otro 403 pasa intacto (se inspecciona un clon). En una carga completa, el layout del panel y la página de onboarding redirigen antes de pintar. **Límite conocido**: una navegación blanda dentro del panel cuya *página de servidor* (no un `fetch` del navegador) reciba el 403 llega al error de Next; se reporta en `TODO.md` §22.75.
24. **Costo por solicitud (caso 33), base local, 2026-10-10** (PostgreSQL 16 en Docker, 3.000 usuarios con una aceptación cada uno, `ANALYZE`, 30 llamadas de calentamiento y 200 medidas, dos pasadas intercaladas): la verificación completa pasa de **p50 2,01 ms / p95 2,23 ms** (solo `usuario` por PK) a **p50 2,30 ms / p95 2,66 ms** con `JOIN empresa` y `EXISTS` sobre `aceptacion_legal` (segunda pasada: 2,02/2,26 contra 2,31/2,67). Suma **≈0,3 ms en p50 y ≈0,4 ms en p95**, una sola sentencia, sin ida y vuelta extra. `EXPLAIN (ANALYZE, BUFFERS)`: `Index Scan using usuario_pkey` + `Index Scan using empresa_pkey` + `Index Only Scan using uq_aceptacion_legal_privacidad`, 0,032 ms de ejecución, 9 buffers. (`'PRIVACIDAD'` va como literal en el SQL: el planificador solo prueba aplicable un índice parcial con un literal.) El catálogo se arma una vez en `create_app`. **Staging**: `TODO.md` §22.74.
