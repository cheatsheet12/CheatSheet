# Unidad: duplicado-de-cliente-sin-id

**HUs**: HU-E4-01   **Contexto dueño**: master_data   **Rama**: fix/master_data-duplicado-de-cliente-sin-id

## Qué hace

Corrige un bug encontrado en la prueba manual de HU-E4-01 (Etapa 6, `reparto.md` — módulo Datos
Maestros, responsable Juan): al crear un cliente con un CUIT que ya existe, el panel muestra el
mensaje "Ya existe un cliente con ese CUIT." pero **nunca ofrece el botón "ver duplicado"**, aunque
el criterio de aceptación lo exige y el componente que lo renderiza (`FormularioDeCliente.tsx`) ya
está preparado para hacerlo.

## Diseño

- **Dominio**: no cambia. `ClienteDuplicado` (`master_data/application/errors.py`) ya lleva
  `cliente_existente_id`, y el router (`api/routers/clientes.py:168-169`) ya lo incluye en el cuerpo
  del 409. La causa está enteramente en el frontend, en la cadena que traduce ese 409 hasta el
  componente.
- **Aplicación**: no aplica (no hay caso de uso nuevo).
- **Puertos y adaptadores**: no aplica.
- **Otros contextos**: ninguno — el bug no sale de `master_data` ni de la infraestructura
  compartida del BFF que ya usa.
- **Frontend** — la causa raíz, en tres archivos, todos ya existentes:
  1. `frontend/src/lib/api.ts` — `leerFalla()` parsea el cuerpo del error y solo extrae `detalle` y
     `error` (código). Descarta cualquier otro campo, incluido `cliente_existente_id`. `ErrorDeApi`
     no tiene dónde guardarlo aunque lo leyera.
  2. `frontend/src/app/api/usuarios/_proxy.ts` — `reenviarAlBackend()`, rama `error.status === 409`,
     reenvía `{ error: error.codigo, detalle: error.detalle }` al navegador. Como `ErrorDeApi` nunca
     tuvo el id, no hay nada que reenviar.
  3. `frontend/src/features/master_data/api/cliente.ts` — `pedir()` ya intenta leer
     `cuerpoDeError.cliente_existente_id` de la respuesta del BFF (comentario en el encabezado del
     archivo: "HU-E4-01 asks the screen to «ofrecer ver el duplicado»"), pero esa respuesta nunca lo
     trae, así que `ErrorDeCatalogo.clienteExistenteId` siempre es `null` y
     `FormularioDeCliente.tsx` nunca muestra el botón (`duplicadoId !== null` nunca se cumple).

  El fix agrega un campo opcional y genérico a `ErrorDeApi` para cualquier dato extra que un 409 de
  negocio traiga más allá de `codigo`/`detalle` (hoy solo lo usa este caso; es el único en todo el
  backend — verificado con `grep -rn "_existente_id" backend/src/cheatsheet`), lo completa en
  `leerFalla()`, y lo reenvía en `_proxy.ts` solo cuando está presente. No se toca el contrato de
  ningún otro 409 (el de `spreadsheet_sync`, p. ej., no manda campos extra y sigue sin mandarlos).

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)

- [ ] Toca dinero
- [ ] Toca comprobantes fiscales / CAE
- [ ] Consume un webhook
- [ ] Agrega datos con `tenant_id`
- [ ] Usa salida de un LLM
- [ ] Datos personales o fiscales

Ninguno aplica: es una corrección de propagación de un campo ya validado por el backend.

## Archivos a tocar

- [x] frontend/src/lib/api.ts
- [x] frontend/src/lib/__tests__/api.test.ts
- [x] frontend/src/app/api/usuarios/_proxy.ts
- [x] frontend/src/app/api/clientes/__tests__/rutas.test.ts

`features/master_data/api/cliente.ts` (`pedir()`) y `FormularioDeCliente.tsx` ya leían y renderizaban
`cliente_existente_id` correctamente — eso nunca estuvo roto, solo nunca le llegaba el dato. Esa capa
ya tiene cobertura (`cliente.test.ts`, `ListadoDeClientes.test.tsx`) que sigue pasando sin tocarla:
agregar un tercer test ahí sería cubrir dos veces el mismo tramo. Decisión registrada abajo.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un 409 con `cliente_existente_id` llega desde `llamarApi` con ese dato en `ErrorDeApi.extra` | unit (`lib/api.ts`) | aprobado |
| 2 | Un 409 sin campos extra deja `ErrorDeApi.extra` vacío (no rompe el resto de los 409) | unit (`lib/api.ts`) | aprobado |
| 3 | `reenviarAlBackend` reenvía `cliente_existente_id` en el JSON del 409 cuando el error lo trae | unit (`_proxy.ts`, vía `rutas.test.ts` de `/api/clientes`) | aprobado |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-11 | aprobado |
| 2 · Verificación | 2026-10-11 | frontend: format/lint/typecheck/test:coverage verdes (118 archivos, 1427 tests, 89.54% cobertura). Backend: ruff/mypy verdes, pytest local 3269 passed / 654 skipped (necesitan Postgres). Contra la rama de Neon del equipo: alembic upgrade head OK, pytest 3099 passed — `tests/integracion/` no corrió: el guard de `guarda.py` la rechazó porque la base de esa rama se llama `neondb` y no `cheatsheet_integracion` como exige `backend/tests/README.md`. No se tocó el guard. Probado además a mano en `localhost:3000` (panel local contra la API de staging): el botón "Ver el cliente existente" aparece y navega al duplicado correcto |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Se encontró durante la prueba manual de HU-E4-01 (staging), no en una unidad de código nueva —
  Juan decidió corregirlo de inmediato en vez de solo anotarlo y seguir probando.
