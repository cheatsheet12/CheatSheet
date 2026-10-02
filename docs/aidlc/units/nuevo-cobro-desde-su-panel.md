# Unidad: nuevo-cobro-desde-su-panel

**HUs**: HU-E6-03 **Contexto dueño**: payments (con una pieza de lectura en master_data) **Rama**: feature/payments-nuevo-cobro-desde-su-panel

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D92 (`docs/aidlc/epicas/06-cobros-y-recordatorios/decisiones.md`). La rama sale de
> `feature/master_data-duracion-de-servicios` (cadena de ramas sobre el PR #45); su PR apunta a esa
> rama y pasa a `develop` cuando el #45 se mergea. Tamaño: S.

## Qué hace

Hoy `/cobros/nuevo` solo funciona si se llega con `?cliente=<id>`: quien entra por el menú lateral ve
«Falta elegir el cliente» y un enlace a Clientes, y `payments` acepta **cualquier UUID** como cliente
sin comprobar que exista. Esta unidad hace que PAN-COB-03 se pueda completar sin haber elegido un
cliente antes: lleva un **selector obligatorio de clientes activos** con búsqueda por nombre o CUIT;
«Cobrar» desde la fila del cliente sigue abriendo la pantalla con ese cliente preseleccionado y
editable; si el selector no encuentra ninguno, ofrece un enlace a Clientes. El cobro **no crea
clientes** (D92). Y el backend deja de aceptar clientes que no existen o están inactivos.

**Fuera de esta unidad:**
- Crear un cliente desde el cobro (D92 lo descartó: exige validar el CUIT contra ARCA, HU-E4-01 RN-02).
- Los selectores de cliente de facturación (HU-E5-03, unidad `tipos-de-comprobante-por-receptor`) y de
  agenda (HU-E7-06, unidad `limites-e-intervalo-de-turnos`). Esas unidades **reusan**
  `SelectorDeClientes`, que esta unidad deja exportado por `features/master_data`.
- Medio de pago, `fecha_pago`, reembolsos parciales y transferencias (D91, D93, D94): unidades
  `fecha-de-pago`, `reembolsos-parciales-y-manuales`, `cobro-por-transferencia`.
- Asociar el cobro a un turno como seña (HU-E6-07): ya resuelta en `agenda-y-recursos`.
- Una clave de idempotencia para el `POST /cobros` (ver «Riesgos», no se agrega).
- El mensaje «MercadoPago no está conectado.» del prototipo como texto propio: hoy toda falla de la
  pasarela se aplana a `PasarelaNoDisponible` a propósito (`api/mercadopago.py`); no se toca.

## Las preguntas que el mapa dejó para este Gate

### 1. ¿Cómo se compone el selector sin romper R5, y cómo se resuelve el cliente preseleccionado?

`NuevoCobro` (payments) no puede importar internos de `master_data` (R5), y la página del servidor no
puede pasarle funciones a un componente cliente. Propuesta:

- `features/master_data` exporta `SelectorDeClientes` por su `index.ts`. Al elegir a alguien hace
  `router.replace(`${destino}?cliente=<id>`)`, con `destino` como prop de texto (`/cobros/nuevo`).
- La página (`app/(panel)/cobros/nuevo/page.tsx`) es la que compone: renderiza el selector y el
  formulario. La URL es la única fuente de verdad del cliente: la página se vuelve a renderizar en el
  servidor al cambiar de cliente, y **gratis** vuelve a pedir los comprobantes de ese cliente
  (pregunta 3).
- Para mostrar el nombre del cliente preseleccionado hace falta leer **uno por id**, y hoy no existe
  `GET /clientes/{id}` (el comentario de `api/routers/clientes.py` lo anticipa). Se agrega
  `VerCliente` en `master_data/application/clientes.py`, `GET /clientes/{cliente_id}` (todos los roles
  leen, como el listado), el handler `GET` del BFF `app/api/clientes/[clienteId]/route.ts` y
  `verCliente` en `api/cliente.ts`.

**Recomendación: sí, agregar `GET /clientes/{id}` dentro de esta unidad.** Alternativas descartadas:
(a) pasar el nombre en la URL: se desactualiza y se puede falsear; (b) buscar el id en
`/clientes?solo_activos=true` (tope de 200 por página): falla en cuanto la empresa tenga más clientes
que eso. Lo que se paga: la unidad toca una lectura de `master_data` (una ruta y un caso de uso
triviales, sin migración).

### 2. ¿Qué valida el backend del cliente y con qué mensaje?

D92 dice que «el backend valida que el cliente exista por la capa de `application` de `master_data`
(R3)». Falta decir si un cliente **inactivo** también se rechaza. El selector solo ofrece activos y
las historias lo dicen (RN-05), pero un `?cliente=` viejo o un POST directo puede traer uno inactivo.

**Recomendación: se rechaza el que no existe, el de otra empresa y el inactivo, con un solo mensaje**
«El cliente seleccionado no existe o esta inactivo.» (sin tildes, convención del sistema; 422). Las
tres se colapsan como ya hace `CobroInexistente`: bajo RLS «no existe» y «es de otra empresa» son la
misma respuesta, y distinguirlas le diría a una empresa que el id ajeno es real. El texto «Debe
seleccionar un cliente.» de la historia queda para el botón deshabilitado del formulario, que es
donde la historia lo pide (PAN-COB-03).

### 3. ¿El comprobante asociado tiene que ser del cliente elegido? — **hallazgo H2**

Hoy la página trae **todos** los comprobantes autorizados con saldo de la empresa
(`/comprobantes?estado=AUTORIZADO`) y `GenerarCobro` solo compara el monto con el saldo
(`_exigir_saldo_suficiente`); nunca mira a quién pertenece el comprobante, aunque el comprobante
**sí tiene `cliente_id`** (`billing/domain/comprobante.py:264`, y la salida HTTP lo expone). Con un
selector editable, elegir un comprobante y después cambiar de cliente deja de ser un caso raro: se
podría cobrarle a Ana una factura de Bruno. HU-E6-06 no lo dice, pero es un cobro sobre la deuda de
otra persona.

**Recomendación: incluirlo.** El formulario ofrece solo los comprobantes del cliente elegido (filtro
por `cliente_id` en la página, sin endpoint nuevo) y el caso de uso lo refuerza: se agrega
`cliente_de(comprobante_id)` a `PortSaldoDeComprobante` (respaldado por el `VerComprobante` que
`SaldoViaBilling` ya usa) y `GenerarCobro` rechaza con «El comprobante no corresponde al cliente
elegido.» (422). Son ~10 líneas en un caso de uso que la unidad ya abre, y el hueco lo agranda esta
misma unidad. Si el Gate prefiere no ampliar, queda como pendiente anotado y el filtro del
formulario se hace igual.

### 4. La búsqueda por CUIT no encuentra el CUIT que la pantalla muestra — **hallazgo H3**

RN-05 pide «búsqueda por nombre o CUIT». El repositorio filtra con `ClienteORM.cuit.like('%texto%')`,
pero el CUIT se guarda **solo con dígitos** (`CUIT.valor`) y la API lo devuelve formateado
(`30-71234567-1`): quien copia el CUIT de la pantalla y lo pega en el buscador no obtiene nada. Es el
mismo filtro del listado de Clientes, así que el bug ya existe en PAN-DM-01.

**Recomendación: corregirlo en el backend** (`master_data/infrastructure/repositories.py::_filtrar`):
comparar el CUIT con el texto reducido a dígitos cuando haya dígitos, y seguir comparando el nombre
con el texto original. Beneficia a los dos buscadores y no duplica la lógica en cada frontend.
Alternativa: normalizar solo en el selector (si el texto son dígitos y guiones, mandar dígitos); más
chica y sin tocar `master_data`, pero deja el bug en Clientes. Nota de coordinación: hay otra unidad
de `master_data` en curso (`duracion-de-servicios`) y `normalizacion-de-datos` (D85) pendiente; el
cambio es una línea en un archivo distinto de los que toca esa unidad.

### 5. Un monto que rompe con 500 — **hallazgo H4**

`monto_desde` acepta cualquier texto que `Decimal` parsee. Probado: `Decimal("NaN") <= 0` levanta
`InvalidOperation` (el `Cobro.__post_init__` revienta con 500 en vez de 422), `Infinity` pasa el
`> 0` y falla en `quantize`, y un monto de más de 12 dígitos enteros desborda `Numeric(14,2)` en la
base. `test_montos.py` solo cubre «mil pesos». El formulario nuevo no cambia esto, pero es la misma
pantalla que la unidad rediseña y el sistema no puede tener un 500 en un flujo que toca plata.

**Recomendación: cerrarlo acá** en `monto_desde`: rechazar no finitos y montos por encima de la
capacidad de la columna (999.999.999.999,99) con «El monto debe ser mayor a cero.» para NaN/Infinity
y «El monto es demasiado grande.» para el tope (texto nuevo, se confirma en el Gate). No es una
decisión de negocio sino de robustez; el único texto nuevo es el del tope.

## Diseño

- **Dominio**: sin cambios (`Cobro` ya valida concepto y monto). H4 vive en `monto_desde`
  (`application/cobros.py`), no en el dominio.
- **Aplicación (payments)**: `GenerarCobro` sigue siendo el único caso de uso. Gana una dependencia
  `clientes: PortClienteDeCobro` y, antes de consultar comprobante o pasarela (para no gastar una
  llamada a MercadoPago), comprueba que el cliente exista y esté activo (`ClienteInexistente`, pregunta
  2) y, si hay comprobante, que sea de ese cliente (`ComprobanteDeOtroCliente`, pregunta 3). El orden
  queda: rol → cliente → comprobante y saldo → link → persistir → bitácora. Errores nuevos en
  `application/errors.py`, ambos `EntradaInvalida` (422 reenviando el texto, como el resto).
- **Aplicación (master_data)**: `VerCliente` (uno por id, todos los roles leen; `ClienteInexistente`
  propio de master_data si no existe). Pregunta 1.
- **Puertos y adaptadores**:
  - `payments/application/ports.py`: `PortClienteDeCobro.esta_activo(cliente_id) -> bool` y
    `PortSaldoDeComprobante.cliente_de(comprobante_id) -> UUID | None`.
  - `payments/infrastructure/clientes.py` (nuevo): `ClienteViaMasterData`, sobre
    `master_data.application.ports.PortRepositorioCliente` (mismo esquema que
    `scheduling/infrastructure/catalogo.py::ClientesViaMasterData`).
  - `payments/infrastructure/saldo.py`: `SaldoViaBilling.cliente_de`.
  - Ensamblado en el composition root: `api/mercadopago.py::armar_clientes(unidad)`, junto a
    `armar_saldos`; el router `api/routers/cobros.py` lo inyecta.
- **Otros contextos**: `payments → master_data` (Customer/Supplier) y `payments → billing` **ya
  existen en el Context Map** (`docs/architecture.md` §4, filas de `master_data` y `billing`); no hace
  falta ADR. `payments` no importa `domain/` ni `infrastructure/` de otro contexto (R3): solo el port de
  `application/` de `master_data`, y los adaptadores concretos se juntan en `api/`.
- **Frontend**:
  - `features/master_data`: `SelectorDeClientes` (búsqueda por texto contra `listarClientes` con
    `soloActivos`, resultados con nombre y CUIT, sin resultados → «No se encontraron clientes.» y enlace
    a `/datos-maestros/clientes`), `verCliente`, export en `index.ts`.
  - `features/payments`: `NuevoCobro` acepta `clienteId: string | null`; sin cliente el botón queda
    deshabilitado y muestra «Debe seleccionar un cliente.». Sigue sin importar nada de `master_data`.
  - `app/(panel)/cobros/nuevo/page.tsx`: compone selector + formulario; quita el estado vacío
    «Falta elegir el cliente» (contradice RN-05); pide el cliente por id y, si no existe o está inactivo,
    lo trata como sin cliente y lo avisa. Trae los comprobantes y filtra por `cliente_id` (pregunta 3).
    Se mantiene la redirección de Solo Lectura.

## Infraestructura

- **Migraciones**: no aplica. `cobro.cliente_id` sigue sin FK (`payments/infrastructure/models.py`): el
  DER no la declara entre contextos y la validación queda en la aplicación.
- **Trabajo asíncrono**: no aplica. La cadena de recordatorios ya arranca por el barrido de Beat
  (D23, D25); un cobro con cliente válido es lo que evita recordatorios a un cliente que no existe.
- **Configuración**: no aplica.
- **Integraciones externas**: no se agrega ninguna. MercadoPago mantiene su timeout, reintento y
  aplanado a `PasarelaNoDisponible`. Lo nuevo es que la validación de cliente ocurre **antes** de la
  llamada, así que un cliente inválido no gasta una preferencia en MercadoPago.

## Riesgos que obligan a tests (marcar los que apliquen)
- [x] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → el monto sigue viajando como texto y la
  aplicación no cambia el redondeo; se agrega H4 (NaN, Infinity, tope) y se vuelve a correr
  `test_montos.py`
- [ ] Toca comprobantes fiscales / CAE → no aplica: solo se lee `cliente_id` de un comprobante
- [ ] Consume un webhook → no aplica
- [x] Agrega datos con `empresa_id` → un cliente de **otra empresa** no es válido para el cobro
  (integración con RLS), y `GET /clientes/{id}` no filtra entre empresas
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales a un LLM → no aplica (el CUIT del selector no sale del panel)

Sobre idempotencia: **no se marca** «consume un webhook», pero `POST /cobros` no tiene clave de
idempotencia: un doble envío crea dos cobros y dos links. Hoy lo mitiga el botón con `cargando`
(`NuevoCobro`) y esta unidad no lo empeora; agregar una clave es de otra unidad.

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/payments/application/cobros.py` (`GenerarCobro`, `monto_desde`)
- [x] `backend/src/cheatsheet/contexts/payments/application/errors.py`
- [x] `backend/src/cheatsheet/contexts/payments/application/ports.py`
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/clientes.py` (nuevo)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/saldo.py`
- [x] `backend/src/cheatsheet/api/mercadopago.py` (`armar_clientes`)
- [x] `backend/src/cheatsheet/api/routers/cobros.py`
- [x] `backend/src/cheatsheet/contexts/master_data/application/clientes.py` (`VerCliente`)
- [x] `backend/src/cheatsheet/api/routers/clientes.py` (`GET /clientes/{cliente_id}`)
- [x] `backend/src/cheatsheet/contexts/master_data/infrastructure/repositories.py` (`_filtrar`, pregunta 4)
- [x] `backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py`
- [x] `backend/tests/contexts/payments/application/test_confirmacion.py` (`SaldosFalsos.cliente_de`)
- [x] `backend/tests/contexts/payments/application/test_montos.py`
- [x] `backend/tests/contexts/payments/infrastructure/test_clientes_via_master_data.py` (nuevo)
- [x] `backend/tests/contexts/master_data/application/test_clientes.py`
- [x] `backend/tests/integracion/test_api_mercadopago.py`
- [x] `backend/tests/integracion/test_api_clientes.py`
- [x] `backend/tests/integracion/test_clientes_postgres.py`
- [x] `backend/tests/contexts/master_data/infrastructure/test_filtro_de_cuit.py` (nuevo: el patron de CUIT, parte pura de H3)

### Frontend
- [x] `frontend/src/features/master_data/components/SelectorDeClientes.tsx` (nuevo)
- [x] `frontend/src/features/master_data/components/__tests__/SelectorDeClientes.test.tsx` (nuevo)
- [x] `frontend/src/features/master_data/api/cliente.ts` (`verCliente`)
- [x] `frontend/src/features/master_data/index.ts`
- [x] `frontend/src/shared/pantallas-maestros.css` (estilos del selector, si hacen falta)
- [x] `frontend/src/app/api/clientes/[clienteId]/route.ts` (`GET`)
- [x] `frontend/src/app/api/clientes/__tests__/rutas.test.ts`
- [x] `frontend/src/features/payments/components/NuevoCobro.tsx`
- [x] `frontend/src/features/payments/components/__tests__/pantallas.test.tsx`
- [x] `frontend/src/app/(panel)/cobros/nuevo/page.tsx`
- [x] `frontend/src/app/(panel)/cobros/__tests__/pagina.test.tsx`
- [x] `frontend/src/features/master_data/api/__tests__/cliente.test.ts` (nuevo: `verCliente`)

### Docs
- [ ] `docs/aidlc/units.md` (fila de la unidad: `Responsable`, `Rama`, estado)

## Casos de prueba

Modo: **test primero**. Los casos marcados RED tienen que fallar antes de tocar el código.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: `GenerarCobro` con un cliente inexistente → `ClienteInexistente`, no llama a la pasarela y no persiste ni audita | unit | RED observado (ImportError al colectar) → verde |
| 2 | RED: cliente inactivo → mismo rechazo | unit | RED observado (ImportError al colectar) → verde |
| 3 | Cliente activo → el cobro se genera como hasta ahora (los tests existentes pasan con el fake nuevo) | unit | verde (los tests existentes pasan con el fake nuevo; no era RED) |
| 4 | Solo Lectura sigue rechazado **antes** de consultar al cliente (no filtra si el id existe) | unit | verde (no era RED; asserta que el fake de clientes no recibe consultas) |
| 5 | RED: comprobante de otro cliente → `ComprobanteDeOtroCliente`; con el del mismo cliente se genera | unit | RED observado (ImportError al colectar) → verde |
| 6 | RED: `monto_desde("NaN")`, `"Infinity"` y un monto sobre el tope → `EntradaInvalida` (no `InvalidOperation`) | unit | RED observado: `monto_desde` aceptaba `NaN`, `Infinity` y `1e30` (comprobado a mano) y el test no colectaba → verde |
| 7 | El monto `"1210.005"` se redondea `ROUND_HALF_UP` a `1210.01` y nunca pasa por `float` | unit | verde (no era RED: el redondeo ya existia en el dominio; el test pasa por `Cobro`) |
| 8 | `ClienteViaMasterData.esta_activo`: activo → `True`; inactivo e inexistente → `False` | unit (contrato del adaptador) | RED observado (ImportError al colectar, con el adaptador movido aparte) → verde |
| 9 | RED: `VerCliente` devuelve el cliente para los cuatro roles (Solo Lectura incluido) y falla si no existe | unit | RED observado (ImportError al colectar) → verde. Solo hay tres roles y los tres leen: no existe un cuarto (Contador no es un `RolUsuario`) |
| 10 | RED: `POST /cobros` con un cliente que no existe → 422 con el texto de la pregunta 2, sin llamar a MercadoPago | integración (API) | escrito, **sin ejecutar**: se saltea sin PostgreSQL/Redis; sin RED observado. Pendiente de CI |
| 11 | `POST /cobros` con cliente válido → 201; con `Solo Lectura` → 403 | integración (API) | escrito, **sin ejecutar** (201 con cliente valido). El 403 de Solo Lectura no aplica: el caso de uso lo rechaza con `EntradaInvalida` (422) y eso lo cubre el caso 4 (unit) |
| 12 | RED: `GET /clientes/{id}` → 200 con el cliente; de otra empresa → 404/422 igual que inexistente | integración (API) | escrito, **sin ejecutar**; sin RED observado. Responde 422 (no 404) para los dos, igual que un id inexistente. Pendiente de CI |
| 13 | RED: un cliente de **otra empresa** no es válido para el cobro (RLS) | integración (PostgreSQL) | escrito, **sin ejecutar**; sin RED observado. Pendiente de CI |
| 14 | RED: buscar `30-71234567-1` (formateado) encuentra al cliente cuyo CUIT se guardó como `30712345671`; buscar por nombre sigue funcionando | integración (PostgreSQL) | escrito, **sin ejecutar** contra la base; la parte pura (`_patron_de_cuit`) tiene RED observado → verde. Pendiente de CI |
| 15 | RED: `SelectorDeClientes` pide solo activos, busca por el texto y lista nombre y CUIT | unit (frontend) | RED observado (el modulo no existia) → verde |
| 16 | RED: sin resultados muestra el aviso y el enlace a `/datos-maestros/clientes` | unit (frontend) | RED observado → verde |
| 17 | Elegir un cliente navega a `/cobros/nuevo?cliente=<id>` (`router.replace`) | unit (frontend) | verde (no era RED) |
| 18 | RED: `NuevoCobro` con `clienteId = null` → botón deshabilitado, «Debe seleccionar un cliente.» y no llama a `generarCobro` | unit (frontend) | RED observado → verde |
| 19 | RED: la página sin `?cliente=` renderiza selector y formulario (ya no «Falta elegir el cliente») | unit (frontend) | RED observado → verde |
| 20 | La página con `?cliente=` muestra a ese cliente preseleccionado y editable; con un id que no existe lo trata como sin cliente y avisa | unit (frontend) | verde (no era RED); los dos casos de «no existe» y el de inactivo, mas que un 500 no se disfraza |
| 21 | RED: la página ofrece solo los comprobantes con saldo **del cliente elegido** | unit (frontend) | RED observado → verde |
| 22 | Solo Lectura sigue redirigido antes de llamar a la API | unit (frontend) | verde (el test existente sigue pasando) |
| 23 | El BFF reenvía `GET /api/clientes/{id}` | unit (frontend) | RED observado (`getCliente is not a function`) → verde |
| 24 | En el navegador (`run-local`): entrar desde el menú, buscar, elegir, generar, y desde la fila de Clientes con «Cobrar»; verificar que lo escrito en concepto y monto no se pierde al elegir cliente | manual | **pendiente**: manual, para quien revise (`run-local`) |
| 25 | `SaldoViaBilling.cliente_de`: devuelve el `cliente_id` del comprobante; `None` si el comprobante no existe | unit (contrato del adaptador) | verde (no era RED: el adaptador ya estaba escrito, el hueco era de test; 2 tests nuevos, y mypy sobre el fake completo del puerto) |
| 26 | Comprobante inexistente (`cliente_de` → `None`) → `CobroInexistente` «El comprobante no existe», no `ComprobanteDeOtroCliente`; sin pasarela, sin cobro guardado y sin evento | unit | verde; mutado a mano (`dueno != cliente_id` sin el `is not None`) el test falla, y se restauró |
| 27 | El caso 5 (comprobante de otro cliente) ahora afirma también que no hay llamada a la pasarela, ni cobro guardado, ni evento | unit | verde (ampliado, no era RED) |
| 28 | RED: al cambiar de cliente se deja de mostrar el error del cliente anterior («El comprobante no corresponde al cliente elegido.») | unit (frontend) | RED observado (el error seguía en pantalla tras el `rerender`) → verde |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-30 | aprobado; las cinco preguntas según la recomendación, con un tope de cobro propio en lugar del de la columna (ver «Decisiones») |
| 2 · Verificación | 2026-09-30 | aprobado. ruff, mypy y pytest en verde (1399 pasan; 349 omitidos por requerir PostgreSQL o Redis); cobertura local 74 %, sin bajar. Arquitectura: 649 archivos, fronteras intactas. Frontend: lint, typecheck y test:coverage en verde (836 tests, 84,43 %; `payments` y `master_data` al 100 %). Verificador independiente: aprobado con notas; sus huecos de test se cerraron antes del Gate. Pendientes: casos de API y PostgreSQL (los corre la CI cuando la cadena llegue a `develop`), el caso manual del navegador (24) y el tope de MercadoPago |
| 3 · PR | 2026-09-30 | PR draft [#49](https://github.com/cheatsheet12/CheatSheet/pull/49) apilado sobre el #48; la CI corre cuando la cadena llegue a `develop` |

## Decisiones tomadas durante la unidad
- P1: se agrega `GET /clientes/{id}` (`VerCliente`, ruta, handler del BFF y `verCliente`) dentro de la unidad.
- P2: se rechaza el cliente inexistente, de otra empresa o inactivo con un solo mensaje: «El cliente seleccionado no existe o esta inactivo.» (422).
- P3 (H2): se incluye; el formulario ofrece solo comprobantes del cliente elegido y `GenerarCobro` rechaza con «El comprobante no corresponde al cliente elegido.».
- P4 (H3): la búsqueda por CUIT se corrige en el backend de `master_data` (`_filtrar`).
- P5 (H4): el tope **no** es la capacidad de la columna sino un tope de negocio: `MONTO_MAXIMO_DE_COBRO = 100.000.000,00` (decisión de Luciano: el tope de la columna es exageradamente grande). Por encima: «El monto es demasiado grande.». NaN e Infinity: «El monto debe ser mayor a cero.». Al implementar se confirma en la documentación de MercadoPago que el link admite ese monto; si su límite es menor, manda el de MercadoPago y se anota acá.
- P5, verificacion pendiente: no se encontro en el repositorio la documentacion del limite de monto de MercadoPago para una preferencia de checkout (no se navego la web). `MONTO_MAXIMO_DE_COBRO` queda en 100.000.000,00 y su comentario marca «PENDIENTE DE VERIFICAR»; si el limite de MercadoPago fuera menor, manda el de MercadoPago.
- Implementacion H3: `_patron_de_cuit` reduce el texto a digitos **solo si** son digitos y separadores de CUIT (`-`, `.`, espacio); un texto con letras («Panaderia 2», «3M») se compara como se escribio, para no traer clientes por un digito suelto.
- Implementacion H2: si `cliente_de` devuelve `None` (comprobante inexistente) `GenerarCobro` no lanza `ComprobanteDeOtroCliente` sino que deja que la comprobacion del saldo lance `CobroInexistente` con su mensaje.
- Implementacion P1: `VerCliente` exige lectura (Administrador, Operador, Solo Lectura) y devuelve tambien al inactivo; la lectura por id se separo en `_rutas_de_lectura` para no pasar el techo de complejidad de `_rutas_de_catalogo`.
- Hallazgo fuera de alcance, anotado: `payments/infrastructure/pasarela.py` envía `float(cobro.monto)` a MercadoPago.
- Verificador independiente (Gate 2): aprobado con notas; se cerraron los huecos de test de `cliente_de` y el error que quedaba al cambiar de cliente. Fuera de alcance, anotados: un monto de 0,004 pasa `monto_desde` y redondea a 0,00 (preexistente, dominio `Cobro`), y los comodines `%`/`_` del LIKE no se escapan (preexistente).
