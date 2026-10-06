# Unidad: renovar-la-sesion

**HUs**: HU-E1-01 (iniciar sesión)   **Contexto dueño**: identity   **Rama**: fix/identity-renovar-la-sesion

> Unidad correctiva, pedida por el usuario el 05/10/2026 durante la prueba manual de la Etapa 6:
> la sesión del panel vencía cada 15 minutos y cortaba las pruebas. Es la diferencia D-06 del guion
> de prueba de identidad.

## El defecto

El backend entrega un **refresh token de 30 días** (`REFRESH_TTL_DIAS`) y el panel tenía
`POST /api/auth/refresh` para usarlo, pero **nadie la llamaba**. La cookie de acceso dura 15 minutos
(`lib/session.ts`) y, al vencer:

- navegar a cualquier pantalla del panel llevaba al login (`(panel)/layout.tsx`);
- cualquier acción hecha desde una pantalla ya abierta terminaba en 401.

## Diseño — y el desvío del plan aprobado

El plan aprobado proponía un **middleware de Next.js**. No sirve: la cookie del refresh está
restringida a `path=/api/auth` (`_sesion.ts`, a propósito, porque es la credencial poderosa), así
que una petición a `/cobros` o a `/panel` nunca la lleva y el middleware no tendría con qué renovar.
El objetivo se mantiene y se resuelve con dos piezas:

1. **`GET /api/auth/renovar`**, dentro de `/api/auth`, donde la cookie sí llega. El layout del panel,
   cuando no hay cookie de acceso, redirige ahí en vez de al login. Renueva las dos cookies y vuelve
   al panel; si el refresh no existe o es rechazado, limpia las cookies y va al login.
   - Es un GET que escribe cookies, y es seguro porque la cookie del refresh es `SameSite=Strict`:
     un enlace desde otro sitio llega sin ella y termina en el login.
   - `destino` sólo acepta una ruta de este sitio (`destinoSeguro`); cualquier otra cosa vuelve a
     `/panel`. Sin eso sería un open redirect.
2. **`RenovadorDeSesion`**, un componente cliente montado en el layout del panel: renueva cada 10
   minutos y también al volver a la pestaña tras una pausa más larga (los timers de una pestaña en
   segundo plano se frenan). Un 401 manda al login; una falla de red no cierra nada.

La lógica de renovación quedó en un solo lugar, `renovarSesion()` en `_sesion.ts`, que usan las dos
rutas.

**Lo que no cambia:** el token de acceso sigue durando 15 minutos, así que un cambio de rol o una
desactivación siguen aplicándose en 15 minutos como máximo, y esta unidad no pisa
`revocacion-inmediata-de-sesion`. Mientras se use el panel, la sesión dura hasta los 30 días del
refresh.

## Tests

- `api/auth/__tests__/renovar.test.ts`: renueva y entra; vuelve a la pantalla de origen; sin refresh
  va al login sin llamar al backend; un refresh rechazado limpia las dos cookies; una empresa sin
  onboarding vuelve al onboarding; siete casos de `destinoSeguro`, incluidos otro origen, `//host`,
  barra invertida y `/api/`.
- `RenovadorDeSesion.test.tsx`: renueva cada diez minutos; renueva al volver tras una pausa; no
  renueva al volver enseguida; un 401 manda al login; una falla de red no.
- Los tests existentes de `POST /api/auth/refresh` siguen pasando sin cambios.

## Verificación (Gate 2)

Corrida local del 05/10/2026:

```
prettier --check src     All matched files use Prettier code style!
eslint                   No ESLint warnings or errors
tsc --noEmit             sin errores
vitest --coverage        961 passed · 87,79 % de cobertura
next build               Compiled successfully · ƒ /api/auth/renovar
```

Falta la prueba en staging: iniciar sesión, dejar pasar más de 15 minutos y seguir navegando y
guardando sin que el panel pida login.
