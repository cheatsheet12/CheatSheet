# Unidad: cliente-en-el-turno

**HUs**: HU-E7-02, HU-E7-06   **Contexto dueño**: scheduling   **Rama**: fix/scheduling-cliente-en-el-turno

> Origen: issue #167, encontrado en la prueba manual de la Etapa 6 en staging (12/10/2026, Estudio
> Ejemplo SRL). Severidad **Mayor**. Es un `fix/…` cortado de `develop` (`9676a1f`); el PR va a
> `develop`.

## Qué hace

El detalle del turno (PAN-AGE-02) hoy muestra servicio, recurso y origen, pero **no para quién es
el turno**: quien atiende el teléfono abre el turno y no sabe de qué cliente es. La agenda sí
muestra el nombre. Esta unidad agrega el **cliente** al detalle del turno, y muestra también para
qué cliente se está creando un turno en «Nuevo turno», donde hoy el cliente viaja solo en el
`?cliente=` de la URL.

Comportamiento observable después del fix:

- PAN-AGE-02 muestra las filas «Cliente» (nombre), «CUIT» (formateado, `20-22222222-3`),
  «WhatsApp» y «Email» en la tarjeta «Turno», antes de «Servicio», para que quien atiende pueda
  contactar al cliente del turno sin salir de la pantalla. Un dato que el cliente no tiene se
  muestra «—».
- «Nuevo turno» muestra el nombre del cliente elegido en el encabezado del formulario.
- Si el cliente no se puede leer (borrado, o cualquier error de la consulta), se muestra «—», igual
  que hoy con un recurso o un servicio que no se encuentra en la misma página.

**Fuera de esta unidad:**
- Un enlace del turno a la ficha del cliente.
- Los demás hallazgos de Agenda (#165, #171, #172, #173): cada uno es su propia unidad.

## La historia

> **HU-E7-02 — Cancelar o reprogramar un turno desde el panel**
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | Abro un turno de la agenda | Veo su detalle y las acciones disponibles según su estado | PAN-AGE-02 |
>
> **HU-E7-06 — Crear un turno manualmente desde el panel** — precondición: «El cliente existe en
> Datos Maestros».

## Lo que ya existe y el hueco

| Dónde | Qué |
|---|---|
| `frontend/src/app/(panel)/agenda/[turnoId]/page.tsx:42-61` | La página del servidor resuelve el nombre del **recurso** y del **servicio** desde sus ids (`llamarApi`) y se los pasa al componente. El cliente no se resuelve |
| `frontend/src/features/scheduling/components/DetalleDeTurno.tsx:39-48, 117-126` | Props `recurso` y `servicio` (strings ya resueltos); la tarjeta «Turno» pinta Servicio, Recurso y Origen. No hay prop ni fila de cliente |
| `frontend/src/app/(panel)/agenda/page.tsx:44-48` | La agenda ya resuelve los nombres de los clientes del lado del servidor con `GET /clientes`: **el patrón existe** y este fix lo repite |
| `frontend/src/app/(panel)/agenda/nuevo/page.tsx` | Recibe `?cliente=`, no lo lee; el formulario no dice para quién es el turno |
| `backend/src/cheatsheet/api/routers/clientes.py:226-240` | `GET /clientes/{cliente_id}` → `VerCliente`: **todos los roles que leen el catálogo** lo pueden leer (`exigir_lectura`), y bajo RLS «no existe» y «de otra empresa» responden igual |
| `backend/src/cheatsheet/api/routers/agenda_forma.py:126-140` | `TurnoSalida` lleva `cliente_id`, no el nombre |

**Por qué no se cambia el backend.** En Cobros (#153, rama `fix/payments-cliente-en-detalle`, sin
mergear) el nombre se agregó a la respuesta de la API porque el CUIT no vive en `payments` (D92).
En Agenda no hace falta: la pantalla ya resuelve los nombres en la página del servidor y
`GET /clientes/{id}` existe. Agregar `cliente_nombre` a `TurnoSalida` haría que `scheduling` dependa
de un dato de `master_data` en su contrato, para una necesidad que es solo de pantalla.

## Diseño

- **Dominio**: no aplica.
- **Aplicación**: no aplica.
- **Puertos y adaptadores**: no aplica.
- **Otros contextos**: la página del servidor de la agenda lee `GET /clientes/{id}` de `master_data`
  por HTTP (BFF → API), igual que `agenda/page.tsx` lee `GET /clientes`. El tipo `Cliente` se importa
  de `@/features/master_data` (su `index.ts`), como ya hace `agenda/page.tsx`: respeta R5.
- **Frontend**:
  - `DetalleDeTurno.tsx`: nueva prop `cliente: DatosDelCliente | null` (nombre, CUIT, WhatsApp y
    email, todo lo que ya devuelve `ClienteSalida`) y las filas «Cliente», «CUIT», «WhatsApp» y
    «Email» en la tarjeta «Turno». El CUIT llega ya formateado por la API, igual que en el detalle
    del cobro (#153); el WhatsApp se muestra tal como está guardado. Solo texto: sin enlaces
    `wa.me` ni `mailto:` (fuera de alcance).
  - `agenda/[turnoId]/page.tsx`: pide `GET /clientes/{turno.cliente_id}` junto con recursos y
    servicios (`Promise.all`); si falla, `"—"`.
  - `agenda/nuevo/page.tsx` + `NuevoTurno.tsx`: la página resuelve el nombre del `?cliente=` y el
    formulario lo muestra en su encabezado («Datos del turno · Para Ana Prueba» o equivalente); si
    falla, `"—"`.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [x] Datos con `empresa_id` → el nombre sale de `GET /clientes/{id}`, que corre bajo RLS: un turno
      no puede mostrar el cliente de otra empresa. No se agrega lógica de aislamiento nueva; el test
      de página cubre que un error de la consulta no rompe la pantalla.
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales → el nombre del cliente se muestra solo dentro de la empresa, en el panel; no
      se loguea.

## Archivos a tocar
- [x] frontend/src/features/scheduling/components/DetalleDeTurno.tsx
- [x] frontend/src/features/scheduling/components/NuevoTurno.tsx
- [x] frontend/src/app/(panel)/agenda/[turnoId]/page.tsx
- [x] frontend/src/app/(panel)/agenda/nuevo/page.tsx
- [x] frontend/src/features/scheduling/components/__tests__/pantallas.test.tsx
- [x] frontend/src/app/(panel)/agenda/__tests__/pagina.test.tsx
- [x] docs/aidlc/units.md (mi fila) · docs/aidlc/units/cliente-en-el-turno.md
- [x] frontend/src/features/scheduling/index.ts (exporta el tipo `ClienteDelTurno`)

## Casos de prueba

El primero se escribe **antes** del arreglo y tiene que fallar con el código actual (`CLAUDE.md` §5).

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | El detalle de un turno muestra «Cliente» con el nombre y «CUIT» con el CUIT recibidos (reproduce #167) | componente (vitest) | ✅ (falló antes del arreglo: 3 rojos) |
| 1b | El detalle muestra «WhatsApp» y «Email» del cliente | componente (vitest) | ✅ |
| 1c | Un cliente sin CUIT, sin WhatsApp o sin email muestra «—» en esa fila | componente (vitest) | ✅ |
| 2 | La página del detalle pide `GET /clientes/{cliente_id}` y le pasa nombre, CUIT, WhatsApp y email al componente | página (vitest) | ✅ |
| 3 | Si `GET /clientes/{id}` falla, la página igual se renderiza y muestra «—» en las cuatro filas | página (vitest) | ✅ |
| 4 | «Nuevo turno» muestra el nombre del cliente del `?cliente=` | página + componente (vitest) | ✅ |
| 5 | Los tests existentes de PAN-AGE-02 (acciones por estado, Solo Lectura sin acciones) siguen verdes | regresión | ✅ (117 tests de agenda en verde) |
| 6 | Verificación manual en staging después del merge: el turno de Ana Prueba muestra «Ana Prueba» y «20-22222222-3» | manual | pendiente (después del merge) |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | aprobado, con dos cambios pedidos: sumar el CUIT y el contacto (WhatsApp, email) del cliente |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- Gate 1: el usuario pidió sumar el CUIT del cliente al detalle (12/10/2026) → fila «CUIT».
- Gate 1: el usuario pidió sumar también el WhatsApp y el email, para contactar al cliente del turno (12/10/2026) → filas «WhatsApp» y «Email», casos 1b y 1c.
- Página del detalle: solo se atrapa `ErrorDeApi` al leer el cliente (cualquier código → «—»); otro error se relanza, igual que `leer()` del turno.
- Arreglo solo en el frontend, resolviendo el nombre en la página del servidor como ya hace la agenda; sin cambios en la API de `scheduling` (ver «Por qué no se cambia el backend»).
