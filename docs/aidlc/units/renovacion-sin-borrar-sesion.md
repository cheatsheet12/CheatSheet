# Unidad: renovacion-sin-borrar-sesion

**HUs**: HU-E1-01 (sesión, ADR-011)   **Contexto dueño**: identity (BFF `app/api/auth` + `features/identity`)   **Rama**: fix/identity-renovacion-sin-borrar-sesion

> **Gate 1 aprobado el 2026-10-09** (la rama sale de `develop` después de que entre `revocacion-inmediata-de-sesion`). Origen: decisión 7 de `revocacion-inmediata-de-sesion` y
> TODO §25 (primer punto). **§25 todavía no está en `develop`**: vive en el worktree de esa unidad
> (`feature/identity-revocacion-inmediata-de-sesion`, `8a0044a`, `docs/aidlc/TODO.md:724-729`).
> Evidencia leída sobre `origin/develop` (`f728599`). Rutas relativas a `frontend/src/` salvo aviso.

## Qué hace

Una renovación de sesión que falla porque la API no pudo contestar (5xx, timeout, red caída) deja de
cerrar la sesión: las dos cookies quedan como estaban y el próximo intento (el tick de 10 minutos o la
próxima navegación) renueva normalmente. Sólo una respuesta definitiva de la API (4xx: token vencido,
revocado, reusado o inexistente) termina la sesión, como hoy.

**Fuera de esta unidad:**
- Cambiar el código HTTP de `SesionInvalida` (409 → 401). TODO §25, segundo punto: decisión de contrato.
- Mostrar un aviso en el ingreso (`FormularioDeIngreso` no lee parámetros de consulta; ver D4).
- Reintentos con backoff dentro del BFF o un período de gracia para el reuso en `RefrescarSesion`.

## Hallazgos

| Dónde (`origin/develop`) | Qué |
|---|---|
| `app/api/auth/_sesion.ts:93-98` | El `catch` de `renovarSesion` llama `cerrarSesion()` y `borrarRefresh()` **antes** de mirar el error: 4xx → `rechazada`, todo lo demás → `caida`, pero las dos cookies se borran en ambos casos |
| `app/api/auth/_sesion.ts:75-78` | El comentario lo declara a propósito («A 5xx clears them too») |
| `lib/api.ts:99-103` | Un timeout de `llamarApi` (10 s, `:20`) se convierte en `ErrorDeApi(504)`; un error de red sale como `TypeError` (no es `ErrorDeApi`). Los dos terminan en `caida` |
| `app/api/auth/refresh/route.ts:27-28` | `caida` → **502** con cuerpo `{"error": "SesionInvalida"}` (el código miente: la sesión no es inválida) |
| `app/api/auth/renovar/route.ts:25-26` | Cualquier resultado distinto de `renovada` redirige a `/` (ingreso) |
| `features/identity/components/RenovadorDeSesion.tsx:30-35` | Sólo redirige ante **401**; un 502 o un error de red se ignoran («the next tick tries again»). El componente ya es correcto: el daño lo hizo el BFF al borrar las cookies |
| `app/(panel)/layout.tsx:50-53` | Sin cookie de acceso redirige a `/api/auth/renovar`, que sin refresh va a `/`. Tras una caída, la primera navegación o el siguiente tick (`sin-refresh` → 401) sacan al usuario |
| `app/(panel)/layout.tsx:80-88` | Precedente: `estadoDeEmpresa` trata 4xx como sesión inválida y **relanza** ≥ 500; la sesión sobrevive a una caída en ese camino, pero no en el de renovación |
| `lib/session.ts:15,18` · `_sesion.ts:18-19` | Cookies `cheatsheet_session` (15 min, `path=/`, `lax`) y `cheatsheet_refresh` (30 días, `path=/api/auth`, `strict`) |
| Llamadores de `renovarSesion` | Sólo dos: `refresh/route.ts:23` (tick y vuelta a la pestaña) y `renovar/route.ts:24` (navegación). No hay otro camino de renovación del lado servidor |
| `backend/.../api/errors.py:35-46` · `identity/application/errors.py:65-70` | `SesionInvalida` y `ReusoDeRefreshDetectado` no están mapeadas: responden **409**, no 401. «Sólo 401 cierra» dejaría un token revocado reintentando para siempre |
| `backend/.../api/routers/auth.py:208-236` | Sólo el reuso confirma su transacción; cualquier otra falla la descarta. Ante un 5xx el refresh viejo **sigue siendo válido**: conservarlo es seguro |
| `backend/.../identity/application/sesiones.py:152-160` | Sin período de gracia: presentar un token ya usado revoca la familia. Relevante para el timeout (D2) |
| `backend/.../platform/database.py:59` | `TIMEOUT_DE_CONEXION_SEGUNDOS = 10`, igual al timeout de `llamarApi`: despertar Neon (ADR-0005) al volver a la pestaña puede superar los 10 s del BFF → 504 → hoy, sesión cerrada (inferido, no medido) |

**Interacción con `revocacion-inmediata-de-sesion`.** Su 503 sale del `EmpresaMiddleware`, y
`/auth/refresh` es pública (`backend/.../api/middleware/empresa.py:42`): ese 503 **no llega** a
`renovarSesion`. La relación es indirecta: la misma caída de la base que hace responder 503 al
middleware hace que `/auth/refresh` responda 500 (manejador genérico, `errors.py:62-78`) o que el BFF
corte a los 10 s (504). Con esa unidad el panel sobrevive la caída en `/auth/empresa`, y la renovación
lo saca igual: esta unidad cierra esa mitad. **No hay dependencia de código**: esa rama sólo toca un
comentario de `RenovadorDeSesion.tsx:13-14`, que esta unidad no modifica.

## Diseño

- **Dominio / aplicación / backend**: sin cambios. La evidencia no lo exige (D1).
- **BFF** (`app/api/auth/_sesion.ts`, `renovarSesion`): borrar las dos cookies **sólo** cuando el error
  es `ErrorDeApi` con `status < 500` (`rechazada`). En `caida` (≥ 500, timeout = 504, `TypeError` de
  red, cualquier otra excepción) no se toca ninguna cookie. Se conserva también la cookie de acceso:
  vence sola por su `maxAge`, y borrarla sólo adelanta un redirect a `/api/auth/renovar` que pegaría
  contra la misma caída. Se corrige el comentario de `:72-79`.
- **BFF** (`refresh/route.ts`): `caida` sigue en **502**, con código `ServicioNoDisponible` (el mismo
  que usa el 503 del middleware de la unidad de revocación) en lugar de `SesionInvalida`. Comentario
  de `:11-13` actualizado.
- **BFF** (`renovar/route.ts`): sin cambio de código. En `caida` sigue yendo a `/`, ahora con las
  cookies intactas: la próxima entrada al panel vuelve a renovar. Redirigir al `destino` crearía un
  bucle panel → renovar → panel mientras dure la caída (D3).
- **`RenovadorDeSesion.tsx`**: sin cambios (ya ignora todo lo que no es 401). Se agrega un test.

## Infraestructura

- **Migraciones / trabajo asíncrono / configuración / integraciones**: no aplica.

## Riesgos que obligan a tests

- [x] Sesión y credenciales → un 5xx o un timeout conserva las dos cookies; un 4xx las borra (regresión
      de seguridad: un token revocado no puede quedar vivo en el navegador).

## Archivos a tocar

- [x] `frontend/src/app/api/auth/_sesion.ts` · `frontend/src/app/api/auth/refresh/route.ts`
- [x] `frontend/src/app/api/auth/__tests__/google-y-refresh.test.ts` · `.../__tests__/renovar.test.ts`
- [x] `frontend/src/features/identity/components/__tests__/RenovadorDeSesion.test.tsx`
- [x] `docs/aidlc/TODO.md` (§25, primer punto → resuelto) · `docs/aidlc/units.md` (fila)

## Casos de prueba (TDD: vitest, `npm run test`; RED antes del cambio)

Mismo patrón que los tests existentes: `next/headers` falso con `almacen`/`cookiesBorradas` y
`llamarApi` mockeado conservando `ErrorDeApi` real.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** — `POST /api/auth/refresh`, API 503: responde 502 `ServicioNoDisponible`, `cookiesBorradas` vacío, refresh y acceso siguen en `almacen` | unit (ruta) | hecho |
| 2 | **RED** — ídem con 500 `ErrorInterno` | unit (ruta) | hecho |
| 3 | **RED** — ídem con `ErrorDeApi(504)` (el timeout de `llamarApi`) | unit (ruta) | hecho |
| 4 | **RED** — ídem con `TypeError` (red caída) | unit (ruta) | hecho |
| 5 | **RED** — `GET /api/auth/renovar`, API 503: redirige a `/` y no borra el refresh | unit (ruta) | hecho |
| 6 | **RED** — 503 y después éxito: el segundo intento rota con el refresh viejo y escribe el par nuevo | unit (ruta) | hecho |
| 7 | 409 `SesionInvalida` → 401 y borra las dos cookies (regresión) | unit (ruta) | hecho |
| 8 | 401 → 401 y borra las dos (ya cubierto en `renovar.test.ts:92`; se agrega en refresh) | unit (ruta) | hecho |
| 9 | 422 (cuerpo inválido) → 401 y borra las dos | unit (ruta) | hecho |
| 10 | Éxito → 200 y escribe las dos cookies (ya cubierto, `google-y-refresh.test.ts:161`) | unit (ruta) | hecho |
| 11 | `RenovadorDeSesion` ante un 502 no redirige (caracterización; pasa hoy) | unit (jsdom) | hecho |

## Verificación (Gate 2)

- `frontend/`: `npm run lint`, `npm run typecheck`, `npm run format:check`, `npm run test:coverage`
  (cobertura de `app/api/auth` sin bajar).
- Backend sin cambios: `ruff format --check . && ruff check . && mypy . && pytest` se corren igual y
  deben quedar como en `develop`.
- Navegador (staging de Render, no local): queda en `docs/aidlc/TODO.md` §22 como verificación manual
  (tirar la API con el panel abierto y comprobar que al volver la sesión sigue).

## Decisiones para el responsable

| # | Pregunta | Recomendación |
|---|---|---|
| D1 | ¿Qué respuestas cierran la sesión: sólo 401, o todo 4xx? | **Todo 4xx (`status < 500`), como hoy.** La negativa definitiva de la API es **409** (`SesionInvalida`, `ReusoDeRefreshDetectado`), no 401; «sólo 401» dejaría un token revocado reintentando cada 10 minutos. Un 422 también es definitivo (la cookie no sirve). La API no emite 408 ni 429 en esta ruta, así que no hace falta excluirlos. No requiere tocar el backend |
| D2 | Ante un timeout o error de red (no se sabe si la API rotó el token), ¿conservar o borrar? | **Conservar.** Si la API no llegó a rotar, el token sigue válido y la sesión sobrevive. Si rotó y la respuesta se perdió, el próximo intento presenta un token usado: la API revoca la familia, responde 409 y la sesión termina — el mismo final que hoy, diez minutos después, con un `reuso_de_refresh_detectado` en el log que conviene saber leer. Borrar garantiza el cierre en los dos casos |
| D3 | En la navegación (`/api/auth/renovar`) con la API caída, ¿ir al ingreso o a otra pantalla? | **Ir a `/` como hoy, con las cookies intactas.** Volver al `destino` arma un bucle mientras dure la caída; una pantalla de error nueva es UI fuera del alcance. Al volver a entrar al panel se renueva solo |
| D4 | ¿Avisar al usuario o espaciar los reintentos? | **Ninguna de las dos.** El intervalo de 10 minutos ya es el espaciado y la renovación al volver a la pestaña sólo corre tras 10 minutos de pausa. Un aviso describe algo que el usuario no puede resolver; la acción que falle por la caída ya muestra su propio error |

## Dependencias

Sin dependencia de código con `revocacion-inmediata-de-sesion` (archivos distintos). **Se recomienda
cortar de `develop` después de su merge**: trae la entrada TODO §25 que esta unidad marca resuelta, y
las dos cubren la misma caída. Si se adelanta, la entrada se crea acá y se concilia al mergear.

## Tamaño estimado

Chica: ~10 líneas de producción, ~110 de tests, docs. Un commit `fix(identity): …`.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-09 | Aprobado por Luciano con las recomendaciones D1–D4 |
| 2 · Verificación | 2026-10-09 | Aprobado por Luciano. RED observado en 6 tests (cookies borradas ante 503, 500, 504 y error de red); lint, typecheck y tests del frontend en verde, `app/api/auth` con 100 % de cobertura. El CI local completo se corre en el Gate 3, cuando revocación entre a `develop` |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- D1: todo 4xx (`status < 500`) cierra la sesión, como hoy.
- D2: ante timeout o error de red se conservan las cookies.
- D3: `/api/auth/renovar` con la API caída va a `/` con las cookies intactas.
- D4: sin aviso al usuario ni espaciado extra de reintentos.
- La rama se apila sobre `revocacion-inmediata-de-sesion` (`c0e926c`); se mergea `develop` cuando esa unidad entre.
