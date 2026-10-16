# Unidad: bandeja-tras-tomar

**HUs**: HU-E9-01 (PAN-WA-01)   **Contexto dueño**: conversational (`features/conversational`, sólo frontend)   **Rama**: fix/conversational-bandeja-tras-tomar

> **Plan aprobado en Gate 1 (2026-10-15).** Origen: issue #227 (severidad Menor, encontrado por nosotros; `reglas.md` §8.3: quien lo encuentra lo corrige).
> Evidencia leída sobre `origin/develop` (`07bcac1`). Rutas relativas a `frontend/src/` salvo aviso.

## Qué hace

Al tomar una conversación desde el hilo abierto, la bandeja de la izquierda se actualiza sola: el renglón pasa a «En atención» y el contador «esperan» baja en uno, sin recargar la página. Lo mismo al cerrar el escalamiento («Devolver al agente», «Dar por finalizada»), que hoy tiene el mismo defecto por el mismo camino.

**Fuera de esta unidad:** actualización en vivo por cambios hechos por *otro* operador (polling o push) y cualquier cambio de backend.

## Hallazgos

| Dónde (`origin/develop`) | Qué |
|---|---|
| `app/(panel)/conversaciones/[conversacionId]/page.tsx:36,55-62` | La página (server) trae el listado una vez y compone `<BandejaDeConversaciones inicial={listado}>` con `<HiloDeConversacion>` como `children`. No hay ningún canal entre los dos componentes |
| `features/conversational/components/BandejaDeConversaciones.tsx:81` | `useState(inicial)`: la bandeja copia el listado al montar y sólo lo vuelve a pedir en `cambiarFiltro` (`:86-96`) |
| `…/BandejaDeConversaciones.tsx:99,138` | El contador sale de `estado_escalamiento === "ABIERTO"` sobre ese estado local → queda en «2 esperan» |
| `…/HiloDeConversacion.tsx:58,77-88` | `correr()` ejecuta la acción y recarga **sólo el hilo** (`setHilo(await verConversacion(hilo.id))`). Por eso la derecha pasa a «En atención» y la izquierda no |
| `…/HiloDeConversacion.tsx:112-124,187-214` | «Tomar», «Devolver al agente» y «Dar por finalizada» pasan todos por `correr()` |
| `…/FilaDeConversacion.tsx:27,34` | El renglón muestra «Espera un asesor» / «Todavía no la tomó nadie» según el estado local de la bandeja |
| `api/conversacion.ts:114-123` | `listarConversaciones(soloEscaladas)` ya existe y devuelve el estado derivado por el backend (RN-01) |

**Causa raíz:** dos copias del mismo dato (el estado del escalamiento) en dos componentes hermanos, y la acción sólo refresca una. No es un problema de backend: F5 muestra el estado correcto. No hay librería de caché (ni React Query ni SWR en `package.json`); el estado es `useState` puro.

## Diseño

- **Dominio / aplicación / backend**: sin cambios.
- **Frontend** (`features/conversational`):
  - Nuevo `components/AvisoDeBandeja.ts`: un `createContext` con `avisarCambio(): void`, valor por defecto *no-op* (el hilo sigue funcionando suelto, como en sus tests actuales). Precedente del patrón: `shared/ui/Desplegable.tsx:42`. **Interno**: no se exporta en `index.ts` (R5 intacta, la página no cambia).
  - `BandejaDeConversaciones`: extrae `recargar(filtro)` de `cambiarFiltro` y envuelve el grid en el provider; `avisarCambio` = `recargar(soloEscaladas)` con el filtro vigente. Una falla al recargar usa el mismo `Alert` que hoy («No se pudo actualizar la bandeja.»).
  - `HiloDeConversacion`: `useContext` y, en `correr()`, tras la acción exitosa, `avisarCambio()`. No se calcula nada en el cliente: la bandeja vuelve a preguntarle al backend (RN-01).
- **Ruta**: `app/(panel)/conversaciones/[conversacionId]/page.tsx` sin cambios (funciona porque un contexto de un componente cliente llega a los `children` que vienen del server).

## Infraestructura

No aplica (sin migraciones, tareas, variables ni integraciones).

## Riesgos que obligan a tests (marcar los que apliquen)

Ninguno de la lista aplica (no toca dinero, fiscal, webhooks, aislamiento, LLM ni datos personales).

## Archivos a tocar

- [x] `frontend/src/features/conversational/components/AvisoDeBandeja.ts` (nuevo, ~20 líneas)
- [x] `frontend/src/features/conversational/components/BandejaDeConversaciones.tsx` (~15)
- [x] `frontend/src/features/conversational/components/HiloDeConversacion.tsx` (~6)
- [x] `frontend/src/features/conversational/components/__tests__/bandeja-tras-tomar.test.tsx` (nuevo, ~110; `pantallas.test.tsx` ya tiene 608 líneas)

Estimado: ~150 líneas cambiadas, la mayoría test.

## Casos de prueba

Vitest + Testing Library (jsdom), mockeando `api/conversacion` como `pantallas.test.tsx:23-40`. Cada caso monta **la misma composición que la página**: bandeja con dos escaladas `ABIERTO` y el hilo de una de ellas como `children`.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED.** Tomar la conversación → dentro de la lista (`within(getByRole("list"))`) el renglón dice «En atención» y la etiqueta pasa de «2 esperan» a «1 espera»; `listarConversaciones` se llamó con el filtro vigente (`false`). Hoy falla: `listarConversaciones` nunca se llama | unit (componente) | hecho · RED observado (la lista seguía en «Espera un asesor»), luego verde |
| 2 | «Dar por finalizada» también recarga la bandeja | unit | hecho · verde |
| 3 | Si la recarga de la bandeja falla, el hilo queda actualizado y la bandeja muestra «No se pudo actualizar la bandeja.» | unit | hecho · verde |
| 4 | Si la toma falla (`ErrorDeConversacion`), la bandeja **no** se recarga | unit | hecho · verde |

## Verificación (Gate 2)

CI local (Actions sin cuota hasta 2026-11-01), en `frontend/`:
`npx prettier --check --end-of-line auto .` · `npm run lint` · `npm run typecheck` · `npm run test:coverage`.
Backend sin cambios: no se corren sus gates. Después del merge, comprobar en staging (Render) los pasos del issue; si no se puede, va a `docs/aidlc/TODO.md` §20-22.

## Revisión

PR a `develop`, revisa **Vincenzo** (`reparto.md:36`: revisor de HU-E9-01; además es el autor del rediseño de bandeja e hilo, `2606aaa`). Cierra #227.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-15 | Aprobado por Luciano con las decisiones 1–5 |
| 2 · Verificación | 2026-10-15 | aprobado. CI local COMPLETE en `7a60953` (ruff, mypy, arquitectura, guardas, gitleaks, PostgreSQL, pytest-cov, integración, frontend install, format, lint, typecheck, R5 y Vitest). RED observado: 3 de 4 casos fallaban porque `listarConversaciones` nunca se llamaba; el cuarto es una guarda. La prueba en el navegador queda en `TODO.md` §22.78 |
| 3 · PR | 2026-10-15 | PR a develop. GitHub Actions sin cuota hasta el 2026-11-01: verificado con el CI local (`run_local_ci.py`, ADR-0016 propuesta en #117), resumen en el PR |

## Decisiones tomadas en el Gate 1

Aprobadas por Luciano el 2026-10-15, todas según la recomendación del borrador:

1. **Recargar la bandeja desde el backend** (`listarConversaciones` con el filtro vigente) en lugar de parchear el renglón localmente: el backend sigue siendo la única fuente del estado derivado (RN-01) y no hay que replicar en el cliente qué renglones salen del filtro «Esperan a un asesor» al cerrar.
2. **Contexto interno de React, no `router.refresh()`**: `router.refresh()` re-pide también el hilo y la bandeja ignoraría el `inicial` nuevo (`useState`), obligando a sincronizar props con estado. Precedente: `shared/ui/Desplegable.tsx`.
3. **También se recarga tras «Enviar»**: pasa por el mismo `correr()` y mantiene al día la hora del último mensaje del renglón; costo, un GET por mensaje enviado.
4. **También se recarga tras el cierre del escalamiento** («Devolver al agente», «Dar por finalizada»): es el mismo defecto por el mismo código; se menciona en el PR.
5. **No se rehace la captura `MAN-80_3.png` en este PR**: la figura (`manual/80-agente-y-atencion.md:131`) muestra el hilo, que ya estaba bien; se corrige al rehacer las capturas del capítulo.

## Decisiones tomadas durante la unidad

- El caso 4 (la toma falla y no se recarga) ya pasaba en RED: es la guarda que impide que el arreglo recargue sin éxito de la acción, no la reproducción del defecto.
- Al envolver la grilla en el `Provider`, `prettier` re-indenta el JSX de `BandejaDeConversaciones.tsx`: el diff bruto del archivo es grande, con `-w` son ~24 líneas.
