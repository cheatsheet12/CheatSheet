# Unidad: responsable-de-la-operacion

**HUs**: HU-E12-02   **Contexto dueño**: observability   **Rama**: fix/observability-responsable-de-la-operacion

> Origen: issue #169, encontrado en la prueba manual de la Etapa 6 en staging (12/10/2026). Es un
> `fix/…` cortado de `develop` (`9676a1f`); el PR va a `develop`.

## Qué hace

El detalle de una operación (PAN-LOG-02) muestra el **responsable** como un identificador
(`880aeb94-…`): quien audita no sabe quién hizo la operación. Esta unidad muestra el **nombre y el
email** del usuario.

Comportamiento observable después del fix:

- «Responsable» muestra «Emanuel Gomez · admin.gomez@estudio-ejemplo.test» en lugar del id.
- Una operación sin usuario sigue diciendo «Sin usuario: la ejecutó la plataforma».
- Si el usuario ya no figura entre los de la empresa, o la lista no se pudo leer, se muestra el id,
  como hoy: es feo pero es cierto, y una celda vacía haría pensar que la operación no tuvo
  responsable.

**Lo que el issue también señalaba y no se cambia, porque son decisiones documentadas:**
- «Duración: No registrada» en una operación de un solo paso: `consultas.py` lo decide así porque
  «mostrar "0 ms" sería afirmar algo que nadie midió».
- «Esta operación no registró datos adicionales.»: **D72** — solo la autorización de comprobantes
  guarda detalle, y nunca datos personales, porque la tabla es inmutable y la lee cualquiera con
  acceso a la auditoría.

## La historia

> **HU-E12-02 — Ver el detalle de una operación individual**
>
> RN-01: El detalle muestra el resumen de la operación, los datos de entrada que la dispararon, los
> datos de salida del servicio externo y el timeline de ejecución con sus pasos internos.
>
> HU-E7-06 RN-05 / HU-E7-02 RN-07: la operación queda en la bitácora **con el usuario** que la
> ejecutó.

## Lo que ya existe y el hueco

| Dónde | Qué |
|---|---|
| `frontend/src/features/observability/components/DetalleDeOperacion.tsx:137-138` | «Responsable» pinta `operacion.usuario_id` crudo |
| `frontend/src/app/(panel)/auditoria/[operacionId]/page.tsx` | La página del servidor solo pide `GET /bitacora/{id}` |
| `backend/src/cheatsheet/api/routers/usuarios.py:240-260` | `GET /usuarios` devuelve `id`, `email`, `nombre`, `rol` y `estado`, y lo puede leer **cualquier rol** (los que acceden a la bitácora, Administrador y Operador, incluidos) |
| `frontend/src/features/identity/index.ts` | Exporta el tipo `UsuarioDeLaEmpresa` |

## Diseño

- **Dominio, aplicación, API**: no aplica.
- **Otros contextos**: la página del servidor lee `GET /usuarios` de `identity` por HTTP (BFF → API),
  igual que la agenda lee `GET /clientes`. El tipo se importa de `@/features/identity` (su
  `index.ts`): respeta R5.
- **Frontend**:
  - `auditoria/[operacionId]/page.tsx`: pide `GET /usuarios` junto con el detalle y resuelve el
    responsable; un error de la API al leer los usuarios deja la página en pie (se muestra el id).
  - `DetalleDeOperacion.tsx`: nueva prop opcional con el nombre y el email del responsable.

## Infraestructura

No aplica (sin migraciones, sin tareas, sin configuración, sin integraciones).

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [ ] Datos con `empresa_id` → `GET /usuarios` corre bajo RLS: solo devuelve usuarios de la empresa
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales → nombre y email se muestran dentro de la empresa, a los roles que ya pueden ver la lista de usuarios; no se escriben en la bitácora (D72 intacta)

## Archivos a tocar
- [x] frontend/src/app/(panel)/auditoria/[operacionId]/page.tsx
- [x] frontend/src/features/observability/components/DetalleDeOperacion.tsx
- [x] frontend/src/features/observability/components/__tests__/pantallas.test.tsx
- [x] frontend/src/app/(panel)/auditoria/__tests__/pagina.test.tsx (nuevo)
- [x] frontend/src/features/observability/index.ts (exporta `ResponsableDeOperacion`)
- [x] docs/aidlc/units.md (mi fila) · docs/aidlc/units/responsable-de-la-operacion.md

## Casos de prueba

El primero se escribe **antes** del arreglo y tiene que fallar con el código actual.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | El detalle muestra el nombre y el email del responsable, no su id (reproduce #169) | componente (vitest) | ✅ (falló antes del arreglo) |
| 2 | Una operación sin usuario sigue diciendo «Sin usuario: la ejecutó la plataforma» | componente (vitest) | ✅ (regresión: ya funcionaba) |
| 3 | La página pide `GET /usuarios` y resuelve el responsable | página (vitest) | ✅ |
| 4 | Si `GET /usuarios` falla, la página se renderiza y muestra el id | página (vitest) | ✅ |
| 5 | Verificación manual en staging después del merge | manual | pendiente (después del merge) |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-13 | aprobado sin cambios |
| 2 · Verificación | 2026-10-13 | Frontend: Prettier ✔, lint ✔, typecheck ✔, 1431 tests ✔, cobertura 91,03 %. Backend sin cambios |
| 3 · PR | 2026-10-13 | PR #218 a `develop`. CI bloqueado por la facturación de Actions de la organización |

## Decisiones tomadas durante la unidad
- La duración de una operación de un solo paso y el detalle vacío (D72) no se tocan: son decisiones documentadas, no bugs.
