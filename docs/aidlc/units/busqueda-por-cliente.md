# Unidad: busqueda-por-cliente

**HUs**: HU-E12-01   **Contexto dueño**: observability   **Rama**: fix/observability-busqueda-por-cliente

> Origen: issue #176, encontrado en la prueba manual de la Etapa 6 en staging (12/10/2026).
> Severidad **Mayor**. Es el pendiente 1 del épico 10 (decisión D77). Es un `fix/…` cortado de
> `develop` (`9676a1f`); el PR va a `develop`.

## Qué hace

En el Log de operaciones, buscar un cliente no encuentra sus operaciones: por nombre («Ana») no
encuentra nada, y por id solo encuentra el alta del cliente, porque sus turnos se registran como
`Turno:<id>` y en ningún lado figura de qué cliente son. Esta unidad hace que **buscar un cliente
por nombre encuentre su alta, sus ediciones y sus turnos**.

Comportamiento observable después del fix:

- En «Buscar», escribir «Ana» muestra las operaciones sobre los clientes cuyo nombre contiene
  «Ana» —su alta, sus ediciones y todas las operaciones de sus turnos—, además de lo que ya
  encontraba la búsqueda por operación, entidad o CAE.
- Cada operación de turno guarda en su detalle el `cliente_id` del turno, y el detalle de la
  operación (PAN-LOG-02) lo muestra en «Datos registrados».

**Fuera de esta unidad:**
- Cobros y comprobantes: sus eventos tampoco dicen de qué cliente son. Es el mismo cambio en
  `payments` y `billing`, módulos de otros integrantes; queda como pendiente, con este patrón.
- Las operaciones de turno ya registradas: la tabla es inmutable (HS-T5 RN-03), así que no se
  completan hacia atrás. Solo las nuevas guardan el cliente.

## La historia

> **HU-E12-01 — Ver la bitácora de operaciones**
>
> RN-03: Los filtros disponibles son por rango de fechas, módulo, estado e iniciador, y búsqueda por
> operación, cliente o archivo.
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | Busco por cliente o archivo | El listado filtra las operaciones relacionadas | PAN-LOG-01 |

## Lo que ya existe y el hueco

| Dónde | Qué |
|---|---|
| `backend/.../observability/infrastructure/repository.py:153-162` | La búsqueda hace `ILIKE` sobre `accion` y `entidad_afectada`, nada más (D77) |
| `backend/.../observability/application/ports.py:32-50` | `FiltrosDeBitacora`: sin filtro por cliente |
| `backend/.../observability/infrastructure/models.py:56` | `detalle` es `JSONB` nullable (D72): admite un id, que no es un dato personal |
| `backend/.../scheduling/application/turnos.py:494-512` | `_auditar`: **todas** las operaciones de turno pasan por acá, sin `detalle` |
| `backend/.../api/routers/bitacora.py:225-240` | Los parámetros del listado |
| `frontend/.../master_data/api/cliente.ts` + `index.ts` | `listarClientes({ texto })` ya busca clientes por nombre |
| `docs/aidlc/epicas/10-…/pendientes.md` §1 | Recomienda resolver el nombre en la pantalla y no escribir nombres en la bitácora |

## Diseño

- **Dominio**: no aplica.
- **Aplicación (`observability`)**: `FiltrosDeBitacora` gana `clientes: tuple[UUID, ...] = ()`.
- **Infraestructura (`observability`)**: la condición de búsqueda pasa a ser **(texto en `accion` o
  `entidad_afectada`) O (la entidad es `Cliente:<id>` de alguno de esos clientes) O (`detalle ->>
  'cliente_id'` es alguno de ellos)**. Los ids van como parámetros, nunca interpolados.
- **API (`bitacora.py`)**: nuevo parámetro `cliente_id` (lista de UUID), que llega a `clientes`.
- **Aplicación (`scheduling`)**: `_auditar` guarda `detalle = {"cliente_id": "<uuid>"}`. Es un id,
  no un dato personal: D72 se respeta, y el nombre nunca entra en la bitácora.
- **Otros contextos**: la pantalla de la bitácora busca clientes en `master_data` por nombre
  (`listarClientes`, importado de su `index.ts`, como permite R5) y manda sus ids como
  `cliente_id`. El backend de `observability` no conoce a `master_data` (R3 intacta). Se mandan los
  de la primera página del catálogo (hasta 50), que es lo que `listarClientes` devuelve.
- **Frontend (`observability`)**: `Bitacora.tsx` resuelve los clientes antes de pedir el listado;
  si esa búsqueda falla, se busca solo por texto, como hoy.

## Infraestructura

- **Migraciones**: no aplica (la columna `detalle` ya existe).
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [ ] Consume un webhook → no aplica
- [x] **Datos con `empresa_id`**: la búsqueda sigue bajo RLS; un id de cliente de otra empresa no devuelve nada. Test de integración.
- [ ] Usa salida de un LLM → no aplica
- [x] **Datos personales**: la bitácora guarda el `cliente_id`, nunca el nombre (D72). Test que lo verifica.

## Archivos a tocar
- [x] backend/src/cheatsheet/contexts/observability/application/ports.py
- [x] backend/src/cheatsheet/contexts/observability/infrastructure/repository.py
- [x] backend/src/cheatsheet/api/routers/bitacora.py
- [x] backend/src/cheatsheet/contexts/scheduling/application/turnos.py
- [x] backend/tests/… (scheduling: el detalle del evento; observability: el filtro en el doble en memoria y en la integración)
- [x] frontend/src/features/observability/api/bitacora.ts · components/Bitacora.tsx · tests
- [x] docs/aidlc/units.md (mi fila) · docs/aidlc/units/busqueda-por-cliente.md · docs/aidlc/epicas/10-…/pendientes.md (§1 resuelto en parte)

## Casos de prueba

Los casos 1 y 4 se escriben **antes** del arreglo y tienen que fallar con el código actual.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Reservar un turno publica el evento con `detalle = {"cliente_id": …}` y sin el nombre del cliente | unit (pytest) | ✅ (falló antes del arreglo) |
| 2 | Listar la bitácora con `clientes` devuelve el alta del cliente y las operaciones de sus turnos, y no las de otro cliente | unit con doble (pytest) | ✅ (falló antes: el filtro no existía) |
| 3 | Lo mismo contra PostgreSQL, incluido que un id de otra empresa no devuelve nada | integración (pytest; en local se omite sin base) | escrito; en local se omite sin base (corre en el CI o con la base de Docker) |
| 4 | Buscar «Ana» en la pantalla pide los clientes por nombre y manda sus ids como `cliente_id` | componente (vitest) | ✅ (falló antes del arreglo) |
| 5 | Si la búsqueda de clientes falla, se busca solo por texto | componente (vitest) | ✅ (regresión) |
| 6 | Verificación manual en staging después del merge: buscar «Ana» muestra los turnos nuevos de Ana Prueba | manual | pendiente (después del merge) |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-13 | aprobado sin cambios |
| 2 · Verificación | 2026-10-13 | aprobado. Backend: ruff ✔, mypy ✔, pytest 3272 ✔ / 656 omitidos (incluye el test de integración nuevo, sin base local). Frontend: lint ✔, typecheck ✔, 1429 tests ✔, cobertura 90,84 % |
| 3 · PR | 2026-10-13 | aprobado por adelantado; push hecho, el PR lo abre el usuario |

## Decisiones tomadas durante la unidad
- La rama se apoya en `fix/infra-mypy-en-pre-commit` (#202): sin ese arreglo, el hook `mypy` de pre-commit no deja commitear Python. Hasta que #202 se mergee, este PR muestra también su commit.
- Opción B (pedida por el usuario, 13/10/2026): resolver el nombre en la pantalla y además registrar el cliente de cada operación de turno, para que la búsqueda encuentre sus turnos.
