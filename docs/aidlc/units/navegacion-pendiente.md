# Unidad: navegacion-pendiente

**HUs**: HU-E1-01 (y, por el mismo defecto, HU-E1-02, HU-E1-04, HU-E2-04, HU-E5-03, HU-E5-04, HU-E6-03, HU-E7-06)
**Contexto dueño**: frontend (`shared/`, transversal)   **Rama**: fix/frontend-navegacion-pendiente

> Origen: hallazgo **H-P1**, reproducido en `staging` el 2026-10-05 al ingresar al panel. Es un
> `fix/…` cortado de `develop` (`956b72c`); el PR va a `develop` y no depende de ninguna otra unidad.
> Responsable: Luciano. Toca componentes de `features/identity`, `features/billing`,
> `features/payments`, `features/scheduling` y `features/spreadsheet_sync`, cuyo autor es Cristian
> (salvo `payments` y `scheduling`); se resuelve como unidad transversal, igual que
> `borrado-sin-cuerpo`.

## Qué hace

Hoy, en todo formulario que hace una mutación y después navega, el botón vuelve a habilitarse en
cuanto la mutación responde, **antes** de que la navegación termine. Con el backend lento, la pantalla
queda varios segundos sin cambios y con el botón activo; un segundo clic repite la mutación. En el
login eso es un segundo `POST /api/auth/login`; en la emisión de un comprobante es **un segundo
comprobante con CAE**.

Comportamiento observable después del fix: el botón queda en «cargando» y deshabilitado desde el
clic hasta que la página de destino se muestra; un segundo clic no vuelve a llamar a la API; si la
mutación falla, el botón se libera y se muestra el error como hoy.

## Hallazgos

| Dónde | Qué |
|---|---|
| DevTools en `staging`, 2026-10-05 | un clic → `POST /api/auth/login` 200 (2,18 s, botón deshabilitado) → el botón se rehabilita → `GET /panel?_rsc=…` 200 tarda ~4 s sin cambios en pantalla → segundo clic → segundo `POST /api/auth/login` 200 innecesario. Con un solo clic y esperando, el panel abre solo |
| `features/identity/components/FormularioDeIngreso.tsx:62-86` | `await ingresar(…)` → `router.push(…)` (devuelve `void`; la navegación es asíncrona) → `finally { setEnviando(false) }`: el estado se libera en el mismo tick |
| `node_modules/next/dist/client/components/app-router.js:288-305` (14.2.15) | `push`, `replace` y `refresh` despachan dentro de `startTransition` |
| `node_modules/next/dist/shared/lib/router/action-queue.js:83-104` | cada acción hace `setState(promesaDiferida)` dentro de `startTransition`; la promesa se resuelve cuando llega la respuesta del servidor |
| `node_modules/next/dist/client/components/use-reducer-with-devtools.js:76-83` | `useUnwrapState` hace `use(promesa)`: el árbol del router **suspende** hasta que la navegación resuelve |
| `frontend/src/app/` | no hay ningún `loading.tsx`: la transición retiene la pantalla anterior hasta tener el payload RSC completo (los ~4 s en blanco) |
| `action-queue.js:121-135` | un `ACTION_NAVIGATE` que llega con otra acción pendiente la marca `discarded` y su estado **nunca se aplica** |
| `features/identity/components/BotonDeSalida.tsx:36-38` | hace `refresh()` y después `push("/")`: por la línea anterior, el `refresh` queda descartado y su limpieza del `prefetchCache` (`refresh-reducer.js:80`) no ocurre. La razón escrita en su comentario (líneas 9-11) hoy no se cumple |
| `backend/…/billing/application/emision.py:1-21` | `EmitirComprobante` persiste y encola sin clave de idempotencia de pedido: dos `POST` iguales son dos comprobantes |

### Alcance verificado — todos los usos de navegación del frontend

`rg` sobre `frontend/src` de `router.push|replace|refresh|back`, `useRouter`, `redirect(` y
`window.location`. Los `redirect()` de páginas de servidor y de rutas BFF no tienen estado de cliente:
no aplican.

| Sitio | Patrón | ¿Afectado? | Efecto de un segundo clic |
|---|---|---|---|
| `identity/…/FormularioDeIngreso.tsx:76` | mutación → `push` → libera | **sí** | segundo login (HU-E1-01) |
| `identity/…/FormularioDeAceptacion.tsx:70` | mutación → `push` → libera | **sí** | segunda llamada a `aceptarInvitacion` con el mismo token mientras navega (HU-E1-04) |
| `identity/…/FormularioDeEmpresa.tsx:181` | onboarding: `push("/panel")` → libera | **sí** | segundo guardado (HU-E1-02) |
| `identity/…/FormularioDeEmpresa.tsx:185` | edición: `refresh()` → libera | **sí** (menor) | segundo guardado idéntico mientras refresca |
| `billing/…/NuevaEmision.tsx:166` | mutación → `push` → libera | **sí — crítico** | **segundo comprobante con CAE** (HU-E5-03) |
| `billing/…/AnularComprobante.tsx:105` | mutación → `push` → libera | **sí — crítico** | segunda nota de crédito si queda saldo (HU-E5-04) |
| `payments/…/NuevoCobro.tsx:77` | mutación → `push` → libera | **sí — dinero** | segundo cobro y segundo link de pago (HU-E6-03) |
| `scheduling/…/NuevoTurno.tsx:121` | mutación → `push` → libera | **sí** | el backend rechaza el solapamiento y la pantalla muestra «no disponible» mientras navega (HU-E7-06) |
| `spreadsheet_sync/…/IngestaDePlanillas.tsx:236` | `await` + `window.location.href`, **sin** estado pendiente | **sí** (variante) | dos `state` OAuth; la cookie `planilla_oauth_state` puede quedar con el otro y el callback falla (HU-E2-04) |
| `identity/…/BotonDeSalida.tsx:37-38` | `saliendo` nunca se libera | no (doble clic) | — pero el `refresh` se descarta (ver Hallazgos) |
| `spreadsheet_sync/…/RevisionDeMapeo.tsx:137-138` | `trabajando` sólo se libera en error; `push` antes que `refresh` | no | — |
| `integrations/…/GrillaDeIntegraciones.tsx:143` | `window.location.assign`; `ocupada` sólo se libera en error | no | — |
| `billing/…/AnularComprobante.tsx:218`, `payments/…/NuevoCobro.tsx:145`, `scheduling/…/NuevoTurno.tsx:312`, `identity/…/FormularioDeEmpresa.tsx:457` | «Cancelar»/«Volver»: navegación sin mutación | no | navega dos veces al mismo lugar |
| `app/(panel)/panel/SelectorDePeriodoEnUrl.tsx:40`, `master_data/…/SelectorDeClientes.tsx:83` | `replace` de la URL, sin mutación ni indicador | no | ninguno; sólo falta indicador de espera (ver Preguntas) |

## Diseño

**Fix elegido: un hook compartido que ejecuta la mutación y, si sale bien, la navegación dentro de
`useTransition`, y expone un único `pendiente` que dura mutación + navegación.** Los ocho sitios
afectados lo usan en lugar de su `useState` de envío. Arregla la clase de defecto, no cada botón.

Fundamento verificado (Next 14.2.15, React vendorizado `18.3.0-canary-14898b6a9-20240318`):
`router.push/replace/refresh` ya despachan dentro de `startTransition` y el router suspende con
`use()` hasta que la promesa de la acción resuelve (Hallazgos). Un `startTransition` del componente
que envuelve la llamada hace que esas actualizaciones pertenezcan a **su** transición, y React mantiene
`isPending` en `true` «hasta que todas las acciones terminan y el estado final se muestra»
([react.dev — `useTransition`](https://react.dev/reference/react/useTransition), sección *Building a
Suspense-enabled router*: los routers con Suspense envuelven la navegación en transiciones). La
llamada al router es síncrona dentro del callback y ocurre **después** del `await` de la mutación, así
que no depende de acciones asíncronas en `startTransition`.

Alternativa descartada: dejar el estado en `true` tras el éxito y confiar en el desmontaje (lo que ya
hacen `BotonDeSalida` y `RevisionDeMapeo`). No cubre `refresh()` sobre la misma página
(`FormularioDeEmpresa` en edición) y deja el botón trabado si la navegación no desmonta el componente.

- **Dominio / Aplicación / Puertos y adaptadores / Otros contextos**: no aplica.
- **Frontend — `frontend/src/shared/navegacion.ts`** (nuevo, junto a `formato.ts`; exportado desde
  `shared/index.ts`). Importa `react` y `next/navigation`, ninguna feature (R5). Forma propuesta:
  `useAccionConNavegacion(): { pendiente: boolean; ejecutar<T>(accion: () => Promise<T>, navegar: (resultado: T, router: AppRouterInstance) => void): Promise<void> }`.
  - `pendiente = enCurso || isPending`. `setEnCurso(false)` y `startTransition(…)` se llaman en el
    mismo tick: React los agrupa y no hay un render con el botón habilitado entre ambos.
  - **Doble envío imposible**: un `useRef` marca la ejecución en curso de forma síncrona; una segunda
    llamada mientras `pendiente` (o antes de que el estado se renderice) no invoca `accion`.
  - **Error**: libera el estado y la marca, **relanza** el error; cada componente conserva su `catch`
    y sus mensajes actuales. No se navega.
  - **Desmontaje**: si el componente se desmontó antes de que `accion` resuelva (la persona se fue a
    otra pantalla), no se navega: no se la arrastra de vuelta a un destino que ya no pidió.
  - Una navegación de página completa (`window.location`) no tiene transición: para
    `IngestaDePlanillas` se usa `ejecutar` con un `navegar` que asigna la URL; `pendiente` queda en
    `true` hasta que la página se va (sólo se libera en error).
- **`BotonDeSalida`**: pasa a `ejecutar(…, (_, router) => { router.push("/"); router.refresh(); })`.
  **El orden se invierte** a propósito: un `refresh` posterior queda en cola detrás de la navegación
  (`action-queue.js:136-142`) y se aplica, limpiando el `prefetchCache`; en el orden actual se
  descarta. El comentario conserva la razón y agrega por qué el orden importa. El `catch` que se traga
  la falla de `/api/auth/logout` se mantiene: salir siempre navega.
- **`RevisionDeMapeo` y `GrillaDeIntegraciones`**: no se tocan (no tienen el defecto).
- `features/*/index.ts`: sin cambios.

## Infraestructura

- **Migraciones / Trabajo asíncrono / Configuración / Integraciones externas**: no aplica.

## Riesgos que obligan a tests

- [x] Toca dinero: un segundo clic en `NuevoCobro` crea un segundo cobro → caso de no-duplicado
- [x] Comprobantes fiscales / CAE: un segundo clic en `NuevaEmision`/`AnularComprobante` emite otro
      documento irreversible → caso de no-duplicado en ambos
- [ ] Webhook / Datos con `empresa_id` / Salida de un LLM / Datos personales a un LLM: no aplica
- [x] **Pieza compartida**: el hook lo usan ocho pantallas de tres responsables; sus casos fijan el
      contrato (pendiente, error, reentrada, desmontaje)

## Archivos a tocar

### Frontend
- [ ] `frontend/src/shared/navegacion.ts` (nuevo) y `frontend/src/shared/index.ts`
- [ ] `frontend/src/shared/__tests__/navegacion.test.tsx` (nuevo, casos 1-6)
- [ ] `frontend/src/shared/__tests__/router-que-suspende.tsx` (nuevo, doble de prueba)
- [ ] `features/identity/components/`: `FormularioDeIngreso.tsx`, `FormularioDeAceptacion.tsx`,
      `FormularioDeEmpresa.tsx`, `BotonDeSalida.tsx` y sus tests
- [ ] `features/billing/components/`: `NuevaEmision.tsx`, `AnularComprobante.tsx`; tests en
      `AnularComprobante.test.tsx` y `pantallas.test.tsx`
- [ ] `features/payments/components/NuevoCobro.tsx`; test en `pantallas.test.tsx`
- [ ] `features/scheduling/components/NuevoTurno.tsx`; test en `pantallas.test.tsx`
- [ ] `features/spreadsheet_sync/components/IngestaDePlanillas.tsx` y su test (sujeto a la pregunta 2)

### Docs
- [ ] `docs/aidlc/units.md` (fila de la unidad)
- [x] `docs/aidlc/units/navegacion-pendiente.md` (este plan)

## Casos de prueba

Modo: **test primero** (`CLAUDE.md` §5). El RED tiene que fallar contra el código actual por el motivo
correcto (botón habilitado / segunda llamada a la API), no por armado. Vitest + Testing Library en
`jsdom`, sin red.

**Doble del router.** Un `vi.fn()` como `push` termina en el acto y haría pasar cualquier
implementación. `router-que-suspende.tsx` reproduce el mecanismo verificado de 14.2.15: el `push`
falso hace un `setState` en un componente arnés que, al cambiar, renderiza un hijo que suspende sobre
una promesa controlada por el test; resolverla equivale a «llegó el payload RSC». Los tests de
componentes lo usan en su `vi.mock("next/navigation")`.

Ningún test existente afirma hoy que el botón se rehabilita tras el éxito; los mocks de
`next/navigation` que sólo exponen `push` siguen sirviendo para los casos que no miran el pendiente.
`BotonDeSalida.test.tsx` cambia: afirma el orden `push` → `refresh`.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Hook: `pendiente` es `true` desde `ejecutar` hasta que la navegación resuelve, aunque `accion` ya resolvió | unit | pendiente |
| 2 | Hook: si `accion` rechaza, `pendiente` vuelve a `false`, el error se relanza y no se navega | unit | pendiente |
| 3 | Hook: una segunda llamada a `ejecutar` mientras está pendiente (incluso en el mismo tick) no invoca `accion` | unit | pendiente |
| 4 | Hook: desmontado antes de que `accion` resuelva → no se llama a `navegar` | unit | pendiente |
| 5 | Hook: `navegar` con `refresh()` sobre la misma página mantiene `pendiente` hasta que el refresh resuelve | unit | pendiente |
| 6 | Hook: no hay render intermedio con `pendiente === false` entre el fin de `accion` y el inicio de la transición | unit | pendiente |
| 7 | **RED** `FormularioDeIngreso`: tras resolver `ingresar`, el botón sigue deshabilitado y con `aria-busy` hasta resolver la navegación; un segundo submit no llama a `ingresar` de nuevo. Hoy falla: el botón se habilita | componente | pendiente |
| 8 | `FormularioDeIngreso`: `ingresar` rechaza → botón habilitado y mensaje de error como hoy | componente | pendiente |
| 9 | **RED** `NuevaEmision`: segundo clic tras resolver `emitirComprobante` y antes de la navegación → una sola llamada | componente | pendiente |
| 10 | **RED** `AnularComprobante`: ídem con `emitirNotaDeCredito` | componente | pendiente |
| 11 | **RED** `NuevoCobro`: ídem con `generarCobro` | componente | pendiente |
| 12 | **RED** `NuevoTurno`: ídem con `reservarTurno` | componente | pendiente |
| 13 | **RED** `FormularioDeAceptacion` y `FormularioDeEmpresa` (onboarding y edición): ídem | componente | pendiente |
| 14 | **RED** `BotonDeSalida`: `push("/")` se llama antes que `refresh()`; con el logout fallido igual navega | componente | pendiente |
| 15 | **RED** `IngestaDePlanillas` «Continuar»: deshabilitado mientras pide la URL; un segundo clic no llama a `iniciarVinculacionConGoogle` | componente | pendiente |
| 16 | Suites existentes de las ocho pantallas siguen verdes (errores, validaciones, destino de `push`) | regresión | pendiente |

## Verificaciones que no se pueden hacer acá

- Confirmar en `staging` que el login abre el panel con **un** clic y que el botón queda en
  «Ingresando…» durante los ~4 s del `GET /panel?_rsc=…`, y repetir con emisión, nota de crédito,
  cobro y turno: necesita el navegador contra el despliegue → `docs/aidlc/TODO.md` (sandbox) al
  cerrar el Gate 2.
- Que el `refresh` de `BotonDeSalida` ahora se aplica está deducido del código instalado de
  14.2.15, no observado en un navegador.

## Fuera de esta unidad

- **H10**: `/api/auth/refresh` nunca se llama y la cookie de acceso dura 15 min
  (`lib/session.ts:18`); pasado ese tiempo toda acción responde 401. Unidad aparte.
- **H-W2**: los temporizadores de Celery Beat se reinician en cada despliegue. Unidad aparte.
- La API en frío del plan gratuito de Render (explica la lentitud, no el doble clic).
- Idempotencia de pedido en el backend para emisión, nota de crédito y cobro (pregunta 1).

## Preguntas para el Gate 1

1. **Idempotencia en el backend.** Este fix impide el doble envío desde el panel, pero un reintento
   de red o dos pestañas siguen pudiendo emitir dos comprobantes o dos cobros. Recomendación: dejarlo
   fuera de esta unidad (es backend y de tres contextos) y registrarlo como unidad propia de
   `billing`/`payments`.
2. **`IngestaDePlanillas` «Continuar».** Es la variante de navegación completa, con efecto real
   (callback OAuth fallido). Recomendación: incluirlo; es el mismo síntoma y son pocas líneas.
3. **Selectores por URL** (`SelectorDeClientes`, `SelectorDePeriodoEnUrl`) no tienen indicador de
   espera, lo que también puede leerse como «hay que hacer dos clics», pero un segundo clic no tiene
   efecto. Recomendación: fuera de alcance; requiere decidir un indicador visual para un selector.
4. **Salida.** Mantener la navegación del router con el orden `push` → `refresh`, o usar
   `window.location.assign("/")`, que descarta todo el estado del cliente. Recomendación: lo primero,
   que conserva la intención documentada con el cambio mínimo.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-05 | Aprobado por Luciano: P1, P2, P3 y P4 según la recomendación |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- **Gate 1 (2026-10-05), respuestas de Luciano:**
  - P1: la idempotencia de pedido en el backend (emisión, nota de crédito, cobro) va en una unidad
    propia, inmediatamente después de esta.
  - P2: `IngestaDePlanillas` «Continuar» entra en esta unidad (caso 15).
  - P3: los selectores por URL quedan fuera de alcance.
  - P4: la salida conserva la navegación del router, con el orden `push` → `refresh`.
