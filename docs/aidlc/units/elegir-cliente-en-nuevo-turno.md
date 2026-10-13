# Unidad: elegir-cliente-en-nuevo-turno

**HUs**: HU-E7-06   **Contexto dueño**: scheduling   **Rama**: fix/scheduling-elegir-cliente-en-nuevo-turno

> Origen: preparación de la demo de la Etapa 6 (13/10/2026). Al tocar «Nuevo turno» en la agenda,
> la pantalla no ofrece clientes: dice «Elegí primero para quién es el turno» y manda a Clientes.
> Severidad **Menor** (hay un camino alternativo: Clientes › Agendar). Es un `fix/…` cortado de
> `develop`; el PR va a `develop`.

## Qué hace

«Nuevo turno» es la acción principal de la agenda, y hoy termina en una tarjeta cuya única salida
es irse a otra pantalla. Nuevo cobro (PAN-COB-03) ya resolvió lo mismo con el selector de clientes
compartido de `master_data` (`SelectorDeClientes`). Esta unidad hace **exactamente lo mismo** en
la agenda.

Comportamiento observable después del fix:

- `/agenda/nuevo` muestra la tarjeta «Cliente» con «Buscar cliente por nombre o CUIT» y la lista
  de clientes activos, y debajo el formulario del turno.
- Sin cliente elegido, el formulario dice «Elegí primero el cliente.» y «Reservar turno» queda
  deshabilitado.
- Elegir un cliente navega a `/agenda/nuevo?cliente=<id>`: aparece «Cliente seleccionado» con su
  nombre y CUIT, el formulario dice «Para <cliente>» y se puede reservar. El cliente se puede
  cambiar desde el mismo selector.
- Un `?cliente=` que no existe, es de otra empresa o está inactivo muestra «El cliente indicado
  no existe o está inactivo.» y se trata como sin cliente. Un fallo del backend que no sea «no
  existe» no se disfraza de cliente vacío.
- El camino desde Clientes › Agendar no cambia: llega con el cliente ya elegido.

**Fuera de esta unidad:** cualquier cambio al selector compartido.

## La historia

> **HU-E7-06 — Crear un turno manualmente desde el panel** — precondición: «El cliente existe en
> Datos Maestros». El turno se crea para un cliente del catálogo.

## Lo que ya existe y el hueco

| Dónde | Qué |
|---|---|
| `frontend/src/app/(panel)/agenda/nuevo/page.tsx` | Sin `?cliente=` devuelve una tarjeta con «Elegí primero para quién es el turno. Ir a Clientes» |
| `frontend/src/features/master_data/components/SelectorDeClientes.tsx` | El selector compartido: busca clientes activos por nombre o CUIT y elige con `router.replace(destino?cliente=<id>)`. Su propio comentario dice que lo reusan facturación y la agenda, pero la agenda no lo usaba |
| `frontend/src/app/(panel)/cobros/nuevo/page.tsx` | El patrón a copiar: `cargarCliente` (activo, o aviso), `SelectorDeClientes` y el formulario siempre visible |

## Diseño

- **Dominio**: no aplica.
- **Aplicación**: no aplica.
- **Puertos y adaptadores**: no aplica.
- **Otros contextos**: el selector es de `master_data` y se importa de su `index.ts`; la página lo
  compone con el formulario de `scheduling`, que no lo importa (R5), igual que Nuevo cobro.
- **Frontend**:
  - `app/(panel)/agenda/nuevo/page.tsx`: igual que Nuevo cobro. `cargarCliente` (mismo
    comportamiento con inactivo, 404/422 y otros errores), `SelectorDeClientes` con
    `destino="/agenda/nuevo"` y `NuevoTurno` siempre visible.
  - `NuevoTurno.tsx`: `clienteId` y `clienteNombre` pueden ser `null`; sin cliente dice «Elegí
    primero el cliente.» y «Reservar turno» queda deshabilitado.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [x] Datos con `empresa_id` → el selector y `GET /clientes/{id}` corren bajo RLS; un id de otra
      empresa se trata como «no existe» (test del caso 404).
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales → nombre y CUIT del cliente, solo dentro de la empresa y en el panel; no se loguean.

## Archivos a tocar
- [x] frontend/src/app/(panel)/agenda/nuevo/page.tsx
- [x] frontend/src/features/scheduling/components/NuevoTurno.tsx
- [x] frontend/src/app/(panel)/agenda/__tests__/pagina.test.tsx
- [x] frontend/src/features/scheduling/components/__tests__/pantallas.test.tsx
- [x] docs/aidlc/units.md (mi fila) · docs/aidlc/units/elegir-cliente-en-nuevo-turno.md

## Casos de prueba

El primero se escribe **antes** del arreglo y tiene que fallar con el código actual (`CLAUDE.md` §5).

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Sin `?cliente=`, la página muestra el selector y el formulario, y ya no «Elegí primero para quién es el turno» (reproduce el hallazgo) | página (vitest) | ✅ (falló antes del arreglo) |
| 2 | Con un cliente lo muestra preseleccionado y el selector sigue disponible | página (vitest) | ✅ |
| 3 | Un cliente que no existe o es de otra empresa (422/404) se trata como sin cliente y se avisa | página (vitest) | ✅ |
| 4 | Un cliente inactivo se trata como sin cliente y se avisa | página (vitest) | ✅ |
| 5 | Un fallo del backend que no es «no existe» se deja subir | página (vitest) | ✅ |
| 6 | Sin cliente, «Reservar turno» queda deshabilitado aunque haya horario | componente (vitest) | ✅ |
| 7 | Solo Lectura sigue sin llegar a la pantalla, y los tests existentes de Nuevo turno siguen verdes | regresión (vitest) | ✅ (133 tests de agenda en verde) |
| 8 | Verificación manual en staging después del deploy: «Nuevo turno» desde la agenda ofrece Ana Prueba y Bruno Ficticio | manual | pendiente (después del deploy) |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-13 | aprobado por el usuario en el chat («bien perfecto»), con un cambio: hacerlo exactamente igual que Nuevo cobro |
| 2 · Verificación | 2026-10-13 | aprobado. Frontend: typecheck ✔, lint ✔, prettier ✔, 1476 tests ✔ (133 de agenda y scheduling). Sin cambios de backend |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- El usuario pidió hacerlo exactamente igual que Nuevo cobro (13/10/2026). Se descartó un selector propio de la agenda y se usa el `SelectorDeClientes` compartido de `master_data`, con la misma página: `cargarCliente`, aviso de cliente inválido y formulario siempre visible.
