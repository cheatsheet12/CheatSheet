# Unidad: borrado-sin-cuerpo

**HUs**: HU-E9-04 (y, por el mismo defecto, HU-E4-03, HU-E1-04, HU-E2-04, HU-E10-05)
**Contexto dueño**: frontend (`lib/`, transversal)   **Rama**: fix/frontend-borrado-sin-cuerpo

> Origen: reproducido en `staging` el 2026-10-03 al eliminar una FAQ desde PAN-WA-02. Severidad:
> **Mayor**. Es un `fix/…` cortado de `develop` (`2eff3a0`); el PR va a `develop` y no depende de
> ninguna otra unidad. Responsable: Luciano. Revisor: Vincenzo.

## Qué hace

Hoy, al eliminar una FAQ, la pantalla muestra un error aunque el backend **sí** la borró (al
refrescar ya no está). El defecto no es de la FAQ: está en `llamarApi`, la única puerta del BFF al
backend, que intenta leer como JSON el cuerpo **vacío** de un `204 No Content`. Por eso fallan igual
todos los `DELETE` del panel cuyo endpoint responde 204.

Comportamiento observable después del fix: un 204 (o cualquier respuesta exitosa sin cuerpo) se
trata como éxito sin datos; el BFF le contesta al navegador `200 {}` y la pantalla muestra la
operación como hecha. Las respuestas JSON y los errores siguen exactamente igual.

**Fuera de esta unidad:**
- Cambiar los endpoints del backend para que devuelvan 200 con cuerpo: el 204 es correcto.
- Que el BFF le reenvíe al navegador un 204 en lugar de `200 {}`: ningún cliente lo necesita (todos
  miran sólo `respuesta.ok`) y obligaría a una rama aparte en `reenviarAlBackend`.
- `subirBinario` (`lib/api.ts:131`) tiene el mismo `respuesta.json()`, pero la única subida
  (`POST /planillas/archivo`) responde 201 con cuerpo. No se toca; queda anotado.

## La historia

> **HU-E9-04 — Administrar el repositorio de FAQ** (Administrador, PAN-WA-02)
>
> * RN-03: Una FAQ eliminada deja de estar disponible para el agente de forma inmediata.
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | Elimino una FAQ | El sistema solicita confirmación y, al confirmar, el agente deja de usarla de inmediato | PAN-WA-02 |

El backend cumple RN-03; lo que falla es el «al confirmar»: la pantalla le dice al Administrador
que no se pudo, y el Administrador no tiene forma de saber que sí.

## Hallazgos

| Dónde | Qué |
|---|---|
| `backend/src/cheatsheet/api/routers/conversaciones.py:417-441` | `DELETE /faqs/{faq_id}` responde `Response(status_code=204)`, sin cuerpo |
| `frontend/src/lib/api.ts:80-84` | `llamarApi` hace `return (await respuesta.json()) as T;` ante **cualquier** respuesta `ok`. Con cuerpo vacío, `json()` lanza `SyntaxError` |
| `frontend/src/lib/api.ts:85-89` | el `catch` sólo traduce `AbortError`; el `SyntaxError` se relanza tal cual |
| `frontend/src/app/api/usuarios/_proxy.ts:30-38` | `reenviarAlBackend`: un error que no es `ErrorDeApi` → `respuestaDeError(null)` → **500 `{ error: "ErrorInterno" }`** al navegador. La línea 34 (`NextResponse.json(datos ?? {})`) ya anticipa `datos` vacío, pero nunca llega ahí |
| `frontend/src/app/api/faqs/[faqId]/route.ts:23-25` | `DELETE` → `reenviarAlBackend(\`/faqs/${faqId}\`, "DELETE")` |
| `frontend/src/features/conversational/api/faq.ts:163-168` | `eliminarFaq` sólo mira `respuesta.ok`; con 500 lanza `ErrorDeFaq`. Con `200 {}` no hace nada más: es éxito |
| `frontend/src/app/api/conversaciones/__tests__/rutas.test.ts:29-32,185-192` | **por qué no lo vio ningún test**: las pruebas de rutas mockean `llamarApi` entero y le hacen devolver `{}`; la costura entre `fetch` y `json()` con un 204 nunca se ejercita. Lo mismo en `categorias`, `planillas` y `reporteria` |
| `frontend/src/lib/__tests__/api.test.ts` | prueba 200 con JSON, errores 4xx/5xx y timeout; **no hay caso 204** |
| `frontend/src/app/api/auth/logout/route.ts:22-29` | también llama a `POST /auth/logout` (204, `auth.py:278-292`); hoy el `SyntaxError` se traga en su `catch` deliberado, así que no se ve. Con el fix deja de lanzar, sin cambio visible |
| `frontend/src/features/master_data/api/categoria.ts:53-55` | `pedir` ya trata el 204 del lado del navegador (`return undefined as T`): es el precedente de tipado que se reutiliza |

### Alcance verificado — qué pantallas tienen hoy el mismo error

Todos los `reenviarAlBackend(…, "DELETE")` del BFF, cruzados con el código de estado del endpoint:

| Ruta BFF | Endpoint backend | Responde | Cliente (feature) | Pantalla | HU | ¿Afectada? |
|---|---|---|---|---|---|---|
| `app/api/faqs/[faqId]` | `conversaciones.py:417` | 204 | `eliminarFaq` (`conversational/api/faq.ts:163`) | `/configuracion/respuestas` (PAN-WA-02) | HU-E9-04 | **sí** |
| `app/api/categorias/[categoriaId]` | `categorias.py:161` | 204 | `eliminarCategoria` (`master_data/api/categoria.ts:83`) | `/datos-maestros/categorias` | HU-E4-03 | **sí** |
| `app/api/usuarios/invitaciones/[invitacionId]` | `usuarios.py:210-231` | 204 | `revocarInvitacion` (`identity/api/cliente.ts:203`) | `/configuracion/usuarios` | HU-E1-04 (RN-04) | **sí** |
| `app/api/planillas/[vinculoId]` | `planillas.py:559` | 204 | `desvincularPlanilla` (`spreadsheet_sync/api/planilla.ts:140`) | `/ingesta` (PAN-ING-01) | HU-E2-04 | **sí** |
| `app/api/reporteria/contador` | `reporteria.py:537-551` | 204 | `revocarContador` (`reporting/api/paquete.ts:208`) | `/configuracion/paquete-contable` (PAN-REP-02) | HU-E10-05 (RN-03) | **sí** |
| `app/api/recursos/[recursoId]/excepciones/[fecha]` | `agenda.py:461` | **200** con `RecursoSalida` | `scheduling/api/recurso.ts:219` | `/agenda/recursos` | HU-E7 | **no** |
| `app/api/auth/logout` (POST, sin `reenviarAlBackend`) | `auth.py:278` | 204 | — | cierre de sesión | HU-E1-01 | no visible (el `catch` lo traga) |

Ningún otro llamador de `llamarApi` apunta a un endpoint 204: el resto son páginas de servidor y
rutas que hacen `GET`/`POST`/`PUT` con respuesta JSON.

## Diseño

**Fix elegido: `llamarApi` lee el cuerpo como texto y devuelve `undefined` si viene vacío (204 o
cualquier éxito sin cuerpo); si no, lo parsea con `JSON.parse`.** Un solo lugar, el que tiene el
defecto: arregla las cinco pantallas a la vez y cualquier `DELETE` futuro, sin tocar las rutas.

Alternativa descartada, en una línea: atrapar el `SyntaxError` en `reenviarAlBackend` (o parchear
las cinco rutas) — deja el defecto en la puerta compartida, no cubre `logout` ni llamadores futuros,
y atrapar `SyntaxError` escondería un 200 con JSON realmente roto.

- **Dominio / Aplicación / Puertos y adaptadores**: no aplica (sin cambios en el backend).
- **Otros contextos**: no aplica.
- **Frontend** (`frontend/src/lib/api.ts`, sólo `llamarApi`):
  - reemplazar la línea 84 por la lectura en dos pasos:
    `const texto = await respuesta.text(); if (texto === "") return undefined as T; return JSON.parse(texto) as T;`
    (o una función privada `leerCuerpo<T>(respuesta)` si ayuda a la lectura). Un 204 siempre llega con
    texto vacío, así que no hace falta una rama aparte por código de estado.
  - **Tipado** (`strict`, sin `any`): la firma sigue siendo `Promise<T>`. El `undefined as T` es la
    misma afirmación de contrato que ya hace el `as T` del JSON, y es el precedente de `pedir` en
    `master_data/api/categoria.ts:54`. Se documenta en el comentario de la función: **quien llame a
    un endpoint 204 declara `T` como `unknown` o `undefined`** — los dos llamadores actuales
    (`reenviarAlBackend` y `logout`) ya usan `llamarApi<unknown>`.
  - Un JSON inválido en un 200 sigue lanzando `SyntaxError` (igual que hoy con `json()`): no se
    esconde.
  - `reenviarAlBackend` **no cambia**: con `datos === undefined`, la línea 34 ya devuelve
    `NextResponse.json({})` → **200 `{}`** al navegador.
  - Clientes del navegador: **no cambian**. `eliminarFaq`, `revocarContador` y `desvincularPlanilla`
    sólo miran `respuesta.ok`; `pedir` (categorías) y `enviar` (identity) parsean `{}` sin error y lo
    descartan (`Promise<void>`).
  - `features/*/index.ts`: sin cambios.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica (el timeout, el token y la traducción de errores de
  `llamarApi` no cambian).

## Riesgos que obligan a tests

- [ ] Toca dinero: no aplica
- [ ] Comprobantes fiscales / CAE: no aplica
- [ ] Webhook: no aplica
- [ ] Datos con `empresa_id`: no aplica (el aislamiento lo hace el backend; el BFF no cambia)
- [ ] Salida de un LLM: no aplica
- [ ] Datos personales a un LLM: no aplica
- [x] **Puerta compartida**: `llamarApi` la usan todas las páginas y rutas del BFF; los casos 3 a 5
      fijan que JSON y errores no cambian

## Archivos a tocar

### Frontend
- [x] `frontend/src/lib/api.ts` (`llamarApi` y su comentario)
- [x] `frontend/src/lib/__tests__/api.test.ts` (casos 1, 3, 4, 5)
- [x] `frontend/src/app/api/faqs/__tests__/borrado.test.ts` (nuevo, caso 2)

### Docs
- [ ] `docs/aidlc/units.md` (fila de la unidad)
- [x] `docs/aidlc/units/borrado-sin-cuerpo.md` (este plan)

## Casos de prueba

Modo: **test primero** (`CLAUDE.md` §5: todo bug arreglado empieza con un test que lo reproduce).
El RED tiene que fallar contra el código actual **por el motivo correcto** (el `SyntaxError` de
`json()` sobre el cuerpo vacío / el 500 del BFF), no por armado. El commit del test va antes que el
del fix. Ningún test toca la red: `fetch` se reemplaza con `vi.stubGlobal("fetch", …)` y la sesión
con el `vi.mock` de `@/lib/session` / `next/headers`, como ya hacen `api.test.ts` y las pruebas de
rutas.

Detalle de armado: el 204 se construye con `new Response(null, { status: 204 })` (el constructor de
`Response` rechaza un cuerpo no nulo en un 204).

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED**: `llamarApi("/faqs/f1", { method: "DELETE" })` con `fetch` → `new Response(null, { status: 204 })` resuelve a `undefined`. **Hoy falla**: rechaza con `SyntaxError` | unit (`lib/__tests__/api.test.ts`) | ok · RED: `SyntaxError: Unexpected end of JSON input` (api.ts:84); GREEN tras el fix |
| 2 | **RED de ruta**: el `DELETE` de `app/api/faqs/[faqId]/route.ts` con sesión, `llamarApi` **real** y `fetch` stubbeado a 204 vacío → el navegador recibe **200 `{}`** y el `fetch` salió a `…/faqs/f1` con `method: "DELETE"`. **Hoy falla**: 500 `{ error: "ErrorInterno" }`. Archivo nuevo porque `conversaciones/__tests__/rutas.test.ts` mockea `llamarApi` entero | unit (ruta BFF, Vitest) | ok · RED: 500 en lugar de 200; GREEN tras el fix |
| 3 | Un 200 con cuerpo vacío (sin `Content-Length`) también resuelve a `undefined` | unit | ok · RED: `SyntaxError`; GREEN tras el fix |
| 4 | Un 200 con JSON sigue devolviendo el objeto parseado (regresión del camino común) | unit | ok · verde antes y después del fix (regresión) |
| 5 | Un 4xx/5xx sigue lanzando `ErrorDeApi` con `status`, `codigo` y `detalle` (los casos existentes «traduce un error…» y «cae al statusText…» siguen verdes sin cambios) | unit (existente) | ok · casos existentes verdes sin cambios (908 tests, 76 archivos) |
| 6 | Las pruebas de rutas existentes (`categorias`, `conversaciones`, `planillas`, `reporteria`, `usuarios`, `auth`) siguen verdes sin cambios | unit (existente) | ok · suite completa verde sin cambios en esas pruebas (908 tests, 76 archivos) |

El 1 es la evidencia local del RED de la causa; el 2 lo es del síntoma que vio el usuario.

## Verificaciones que no se pueden hacer acá

- Confirmar en `staging` que borrar una FAQ (y revocar una invitación, eliminar una categoría,
  desvincular una planilla y revocar el acceso del contador) ya no muestra error necesita el
  navegador contra el despliegue: queda en `docs/aidlc/TODO.md` (sandbox) al cerrar el Gate 2.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | aprobado (contexto «frontend (`lib/`, transversal)») |
| 2 · Verificación | 2026-10-04 | Aprobado por Luciano. RED: casos 1 y 3 `SyntaxError: Unexpected end of JSON input`, caso 2 `expected 500 to be 200`. GREEN: lint, typecheck, prettier y `test:coverage` en verde (908 tests, cobertura total 87,44 %). Pendiente: verificar en staging las cinco pantallas (`TODO.md`) |
| 3 · PR | 2026-10-04 | [#78](https://github.com/cheatsheet12/CheatSheet/pull/78) contra `develop`. **Mergeado el 2026-10-05** (`d50a8b4`). Cada responsable verifica su pantalla en staging (`TODO.md` §22.12) |

## Decisiones tomadas durante la unidad
- (ninguna todavía)
