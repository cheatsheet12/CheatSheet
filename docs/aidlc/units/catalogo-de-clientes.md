# Unidad: catalogo-de-clientes

**HUs**: HU-E4-01 **Contexto dueño**: master_data **Rama**: feature/master_data-catalogo-de-clientes

## Qué hace

Un Administrador o un Operador entra a **PAN-DM-01**, ve el catálogo de clientes de su empresa
—nombre, CUIT, origen, WhatsApp y estado—, crea uno nuevo validando el CUIT contra el padrón de
ARCA, edita los existentes y los desactiva. Un cliente creado desde el panel queda con
`origen = PANEL` y disponible en el acto para los épicos que vienen (RN-04).

Es además la primera unidad de `master_data`, así que estrena el contexto: su tabla con RLS por
`empresa_id`, su repositorio, su router y su feature en el frontend. Las dos unidades siguientes
heredan todo eso y no lo vuelven a decidir.

---

## Las tres preguntas que el mapa dejó abiertas para este Gate

### 1. El CUIT de un cliente es **opcional**

El DER deja `cliente.cuit` nullable y `condicion_iva` también; HU-E4-01 RN-02 habla como si siempre
hubiera un CUIT que validar. Gana el DER, por una razón que no está en esta historia sino en la
siguiente épica que toca la tabla: **HU-E8-01 crea clientes desde WhatsApp**, donde lo único que hay
es un número de teléfono. Si el CUIT fuera obligatorio, el agente no podría registrar a nadie y la
solución sería inventar un CUIT de relleno, que es exactamente el dato sucio que este contexto
existe para no tener.

Entonces: **`nombre` es lo único obligatorio.** Con CUIT, se valida y es único; sin CUIT, el cliente
existe igual con su contacto.

Consecuencia declarada, para el épico 5: un cliente sin CUIT o sin `CondicionIVA` **no puede recibir
una Factura A**. Eso lo resuelve `billing` cuando llegue —tiene que revalidar contra ARCA de todos
modos—, no este formulario.

### 2. Que ARCA no esté conectada **no bloquea** el guardado

Es el mismo problema que `padron-y-datos-fiscales` ya resolvió para el onboarding, y se resuelve
igual porque la distinción es la misma: **no encontrado bloquea, no se pudo preguntar no bloquea.**

Las tres respuestas del padrón, y qué hace cada una acá:

| Respuesta | Qué significa | Qué hace el alta |
|---|---|---|
| `ENCONTRADO` | ARCA conoce el CUIT | Completa razón social y `CondicionIVA`, y guarda |
| `NO_ENCONTRADO` | ARCA dice que ese CUIT no existe | **Bloquea** (RN-02: «un CUIT inválido bloquea el guardado») |
| `NO_DISPONIBLE` | No se pudo preguntar: ARCA sin conectar, certificado vencido, el servicio caído | **Guarda**, y la pantalla dice por qué no se validó |

«ARCA sin conectar» es un caso más de `NO_DISPONIBLE`, no un cuarto estado. La integración es
opcional (épico 2) y una empresa que todavía no la configuró tiene que poder cargar sus clientes; lo
contrario sería que una pantalla de datos maestros dependa de un certificado fiscal.

**La validación estructural sí bloquea siempre**, con o sin ARCA: once dígitos y dígito verificador,
que es de dónde sale el mensaje «El CUIT debe contener 11 dígitos.» del criterio de aceptación. Eso
no necesita red.

**La alternativa descartada** era una columna `cuit_validado` que distinguiera un cliente verificado
de uno que entró sin poder preguntar. Se descartó por dos motivos: agrega una columna que el DER no
tiene, y no sirve de nada sin un barrido que revalide lo pendiente cuando ARCA se conecta — que es
trabajo con forma de tarea periódica, o sea otra unidad. Si el épico 5 lo necesita, lo pide con su
caso de uso detrás.

### 3. Un cliente **no se borra**: se desactiva

HU-E4-01 pide ver, crear y editar; nunca borrar. El DER trae `activo`, y ADR-007 dice que lo que
desaparece de la planilla se marca ausente y nunca se elimina. Además `comprobante`, `cobro` y
`turno` referencian al cliente por id **sin FK declarada** (hueco H4 del DER): un borrado físico no
lo impediría nadie y dejaría documentos fiscales apuntando al vacío.

Así que no hay `DELETE`. Hay `activo`, que es la columna «estado» del listado, y desactivar oculta
del catálogo activo sin tocar nada histórico.

---

## Diseño

### Dominio — `contexts/master_data/domain/`

- **`Cliente`** (`cliente.py`), agregado raíz. Campos del DER: `id`, `empresa_id`, `nombre`,
  `cuit`, `condicion_iva`, `contacto_whatsapp`, `contacto_email`, `origen`,
  `presente_en_planilla`, `referencia_fila_planilla`, `activo`, `created_at` / `updated_at`.
  - `Cliente.registrar(...)` construye con `origen` recibido y `activo=True`.
  - `renombrar`, `actualizar_contacto`, `actualizar_datos_fiscales`, `desactivar`, `reactivar`.
  - **`origen` no tiene setter** (RN-01, «asignado automáticamente y no editable»). No es una
    validación del formulario: es que el agregado no expone la operación.
  - `categoria_id` **no se crea** — decisión D8 del mapa: la clasificación es N a N y llega en
    `categorias-y-clasificacion`.
- **`OrigenDato`** (`valores.py`), enum cerrado del DER `origen_dato`: `PLANILLA · PANEL · AGENTE`.
  Nace acá porque `master_data` es su dueño; `spreadsheet_sync` lo va a leer en el épico 4 por la
  vía que corresponda entonces.
- **`presente_en_planilla` y `referencia_fila_planilla` existen desde el día uno**, con `False` y
  `None` para todo lo que crea el panel. Son ADR-006 y ADR-007 hechos columna y el épico 4 los
  escribe; agregarlos después sería un backfill sobre datos reales.

### Aplicación — `contexts/master_data/application/`

Un caso de uso por servicio, como en el resto del sistema:

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `ListarClientes` | `empresa_id`, `rol`, filtros (texto, origen, sólo activos), paginado | `Sequence[VistaDeCliente]` + total | Lectura permitida a los tres roles con acceso; nunca cruza empresas |
| `RegistrarCliente` | `empresa_id`, `usuario_id`, `rol`, datos del formulario | `VistaDeCliente` | `origen = PANEL`; CUIT único (RN-03); padrón consultado si hay CUIT; audita |
| `EditarCliente` | ídem + `cliente_id` | `VistaDeCliente` | No toca `origen`; revalida contra el padrón **sólo si el CUIT cambió** |
| `CambiarEstadoDeCliente` | `empresa_id`, `usuario_id`, `rol`, `cliente_id`, `activo` | `VistaDeCliente` | Desactiva o reactiva; audita |
| `ConsultarPadronParaCliente` | `empresa_id`, `rol`, `cuit` | `VistaDePadron` | No escribe nada. Es el botón «Validar contra ARCA» del formulario |

**Autorización**: `application/autorizacion.py` propio del contexto, con `RolUsuario` del Shared
Kernel — el mismo patrón que `integrations` estrenó y por el mismo motivo (R3 impide mirar el
dominio de `identity`, y el rol ya viaja en la request). La matriz de acceso del mapa de navegación
§5 dice **Admin ● · Operador ● · Solo Lectura RO · Contador —**, así que:

- leer: `ADMINISTRADOR`, `OPERADOR`, `SOLO_LECTURA`;
- crear, editar y cambiar estado: `ADMINISTRADOR`, `OPERADOR`.

**El duplicado se detecta en la base, no en una consulta previa.** `RegistrarCliente` intenta
insertar y traduce la violación del índice único a `ClienteDuplicado`, que **lleva el id del cliente
existente** — porque el criterio de aceptación no pide sólo el mensaje «Ya existe un cliente con ese
CUIT.», pide además «ofrece ver el duplicado». Un `SELECT` previo sería una condición de carrera con
mejor prensa.

**Auditoría**: cada escritura publica un `EventoAuditable` con `Modulo.MASTER_DATA` —que ya existe
en `shared/auditoria.py`— por el mecanismo que dejó `cimientos-y-bitacora`.

### Puertos y adaptadores

| Puerto (`application/ports.py`) | Adaptador (`infrastructure/`) |
|---|---|
| `PortRepositorioCliente` — `agregar`, `guardar`, `buscar_por_id`, `buscar_por_cuit`, `listar_de_empresa(filtros, paginado)` | `repositories.py` sobre SQLAlchemy async, dentro de la sesión con `app.current_empresa` seteado |
| `PortPadron` — `consultar(empresa_id, cuit) -> DatosDePadron \| None`, levanta `PadronNoDisponible` | `infrastructure/padron.py`, que llama a `ConsultarPadron` de `integrations.application` |

El puerto de padrón se **redeclara** en `master_data` en vez de importar el de `identity`: son dos
contextos distintos hablando con el mismo OHS, y compartir el `Protocol` significaría que uno importe
el `application/` del otro sin que el Context Map lo permita.

### Otros contextos

**`master_data` → `integrations`**, llamando a `ConsultarPadron` en su capa de aplicación. Es el edge
que ADR-0003 ya autorizó — «un contrato en su capa de aplicación que **cualquier** contexto puede
llamar» — así que **no hace falta ADR nuevo**. Sí hace falta agregar `master_data` a la celda de
consumidores de la fila OHS de `integrations` en [`docs/architecture.md`](../../architecture.md) §4,
que hoy enumera los cinco conocidos al escribirla. Es documentación poniéndose al día con una
decisión ya tomada, y entra en esta unidad.

Ningún otro contexto se toca. `billing`, `payments`, `scheduling` y `conversational` son downstream
de `master_data` (Context Map, fila C/S) pero todavía no existen.

### Value objects que se mudan al Shared Kernel

Dos, y las dos mudanzas son la regla que `shared/fiscal.py` dejó escrita: *«A value object moves here
when a second context needs it, never in anticipation»*. `master_data` es ese segundo contexto.

- **`CUIT` → `shared/fiscal.py`**, junto a `CondicionIVA`, que ya está ahí.
- **`Email` → `shared/contacto.py`** (módulo nuevo), porque `cliente.contacto_email` lo necesita y
  vive hoy en `identity/domain/valores.py`. Con él nace **`Telefono`**, que no existe en ningún lado
  todavía y `contacto_whatsapp` necesita: normaliza a dígitos con prefijo internacional opcional y
  no valida más que eso — el número real lo valida WhatsApp cuando el épico 8 le escriba.

En los dos casos `identity/domain/valores.py` los **re-exporta**, exactamente como se hizo con
`CondicionIVA` y con `RolUsuario`: ningún import existente se rompe, `identity` sigue siendo el dueño
conceptual, y R4 se mantiene porque `shared/` no importa nada de `contexts/`.

### Frontend

- **`features/master_data/`** — se estrena. `index.ts` expone `ListadoDeClientes`, el cliente de API
  (`listarClientes`, `crearCliente`, `editarCliente`, `cambiarEstadoDeCliente`, `consultarPadron`) y
  sus tipos. Nada más sale de la feature (R5).
- **Componentes**: `ListadoDeClientes.tsx` (tabla + filtros + buscador) y `FormularioDeCliente.tsx`
  (alta y edición en `Modal`), construidos con `Tabla`, `Modal`, `Campo`, `Select`, `Badge`,
  `Button` y `Alert` del sistema de diseño — que ya tienen todo lo que PAN-DM-01 necesita.
- **Ruta**: `app/(panel)/datos-maestros/clientes/page.tsx`, delgada, que compone la feature.
- **BFF**: `app/api/clientes/route.ts` (GET, POST), `app/api/clientes/[clienteId]/route.ts` (PUT),
  `app/api/clientes/[clienteId]/estado/route.ts` (PUT) y `app/api/clientes/padron/route.ts` (GET),
  con el wrapper de fetch y la cookie HttpOnly que ya existen.
- **Sin prototipo (hueco P10)**: se maqueta con el catálogo de componentes del PDF §1.3 y los tokens
  importados, reusando la forma del listado de usuarios (PAN-USR-01), que es el precedente P9.
- **Nada de lógica de negocio en el panel** (`CLAUDE.md` §5): el dígito verificador se valida también
  en el backend, y es el backend el que decide si un CUIT bloquea.

---

## Infraestructura

### Migraciones

Una sola, **`0008_cliente.py`**, sobre la revisión 0007.

- Tabla `cliente` con las columnas del DER menos `categoria_id` (D8), enums como `String` — es la
  convención que fijó 0004 y evita un `ALTER TYPE` cada vez que un enum crece.
- **Índice único parcial** `uq_cliente_empresa_cuit` sobre (`empresa_id`, `cuit`)
  `WHERE cuit IS NOT NULL`: RN-03 en la base. Parcial porque el CUIT es opcional y varios clientes
  sin CUIT no son duplicados entre sí.
- Índice `ix_cliente_empresa` para el listado.
- **RLS igual que todas las tablas con `empresa_id`**: `ENABLE` + `FORCE ROW LEVEL SECURITY`,
  política `aislamiento_por_empresa` contra `app.current_empresa`, `GRANT` sólo a `cheatsheet_app`,
  nada a `PUBLIC`. **Ninguna función `SECURITY DEFINER`**: acá no hay ninguna lectura entre empresas
  que justificar.
- **Reversible y sin backfill**: la tabla es nueva, `downgrade` la borra entera.

### Trabajo asíncrono

**No aplica.** Nada de esta unidad es diferido: el padrón se consulta en línea, dentro de la request,
como ya lo hace el onboarding.

### Configuración

**No aplica.** No hay variables nuevas: la credencial de ARCA la administra `integrations` y la clave
de cifrado ya está en `backend/.env.example` desde el épico 2.

### Integraciones externas

**No aplica como integración nueva.** ARCA ya está en `.env.example` y su contrato, sus timeouts y su
política de reintentos viven en `integrations` desde `conexion-arca`. Esta unidad es un consumidor
del OHS, no un proveedor nuevo, así que no dispara la escalada de contratos del workflow.

---

## Riesgos que obligan a tests

- [ ] Toca dinero — **no**. No hay `Decimal` en esta unidad; el precio llega con los servicios.
- [ ] Toca comprobantes fiscales / CAE — **no**.
- [ ] Consume un webhook — **no**.
- [x] **Agrega datos con `empresa_id`** → test de aislamiento entre empresas, sobre la base real, con
      dos empresas y la RLS activa.
- [ ] Usa salida de un LLM — **no**.
- [x] **Datos personales y fiscales** — nombre, CUIT, email y teléfono de personas reales. No salen
      hacia ningún LLM, no se loguean, y el CUIT no aparece en ningún mensaje de error que viaje a
      otra empresa.

---

## Archivos a tocar

### Backend

- [ ] `backend/src/cheatsheet/shared/fiscal.py` — recibe `CUIT`
- [ ] `backend/src/cheatsheet/shared/contacto.py` — nuevo: `Email` (mudado) y `Telefono` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/identity/domain/valores.py` — re-exporta los dos
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/cliente.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/valores.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/application/ports.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/application/errors.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/application/autorizacion.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/application/clientes.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/application/padron.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/models.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/repositories.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/padron.py`
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/ensamblado.py`
- [ ] `backend/src/cheatsheet/api/routers/clientes.py`
- [ ] `backend/src/cheatsheet/api/main.py` — monta el router
- [ ] `backend/migrations/versions/0008_cliente.py`
- [ ] `backend/tests/contexts/master_data/…`
- [ ] `backend/tests/api/…` y `backend/tests/integracion/…`

### Frontend

- [ ] `frontend/src/features/master_data/index.ts`
- [ ] `frontend/src/features/master_data/api/cliente.ts`
- [ ] `frontend/src/features/master_data/components/ListadoDeClientes.tsx`
- [ ] `frontend/src/features/master_data/components/FormularioDeCliente.tsx`
- [ ] `frontend/src/features/master_data/components/__tests__/…`
- [ ] `frontend/src/app/(panel)/datos-maestros/clientes/page.tsx`
- [ ] `frontend/src/app/api/clientes/route.ts`
- [ ] `frontend/src/app/api/clientes/[clienteId]/route.ts`
- [ ] `frontend/src/app/api/clientes/[clienteId]/estado/route.ts`
- [ ] `frontend/src/app/api/clientes/padron/route.ts`

### Documentación

- [x] `docs/architecture.md` §4 — `master_data` entra en la fila OHS de `integrations`
- [x] `docs/aidlc/units.md` — estado de la fila

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un CUIT de 10 dígitos no construye el value object, y el alta responde «El CUIT debe contener 11 dígitos.» | unit | verde |
| 2 | Un CUIT con dígito verificador incorrecto se rechaza sin llamar al padrón | unit | verde |
| 3 | Alta con CUIT que el padrón conoce: guarda con razón social y `CondicionIVA` del padrón y `origen = PANEL` | integración | verde |
| 4 | Alta con CUIT que el padrón **no** conoce: no guarda | integración | verde |
| 5 | Alta con ARCA sin conectar: **guarda igual**, y la respuesta dice que no se pudo validar | integración | verde |
| 6 | Alta con el padrón caído (`PadronNoDisponible`): mismo desenlace que el 5 — no se confunde con «no encontrado» | unit | verde |
| 7 | Segundo cliente con el mismo CUIT en la misma empresa: `ClienteDuplicado` con el id del existente | integración | verde |
| 8 | El mismo CUIT en **dos empresas distintas** sí se puede: el índice único es por empresa | integración | verde |
| 9 | Dos clientes sin CUIT conviven: el índice parcial no los considera duplicados | integración | verde |
| 10 | **Aislamiento**: la empresa A no ve, no edita y no desactiva un cliente de la empresa B | integración | verde |
| 11 | `origen` no cambia al editar, ni siquiera si el payload lo trae | unit | verde |
| 12 | Editar sin tocar el CUIT no consulta el padrón | unit | verde |
| 13 | Desactivar oculta del catálogo activo y el cliente sigue existiendo; reactivar lo devuelve | integración | verde |
| 14 | Un `SOLO_LECTURA` lista pero no crea, edita ni desactiva; un `OPERADOR` hace las cuatro cosas | unit | verde |
| 15 | Cada escritura deja un `RegistroDeAuditoria` con `Modulo.MASTER_DATA` | integración | verde |
| 16 | `ListadoDeClientes` muestra nombre, CUIT, origen, WhatsApp y estado, y filtra por texto y origen | frontend | verde |
| 17 | El formulario muestra el mensaje de duplicado con el enlace a ver el existente | frontend | verde |
| 18 | Los imports viejos de `CUIT` y `Email` desde `identity.domain.valores` siguen funcionando | unit | verde |

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-31 | aprobado |
| 2 · Verificación | 2026-08-31 | aprobada — 670 tests, 89.86 % de cobertura |
| 3 · PR | 2026-08-31 | [#23](https://github.com/cheatsheet12/CheatSheet/pull/23) abierto a `develop` |

## Desvíos del plan

Cuatro, y el primero es el único que cambia una decisión de diseño.

1. **El duplicado se busca antes de insertar, y el índice sigue siendo el que lo impide.** El plan
   decía «se detecta en la base, no en una consulta previa» y eso resultó ser media verdad. El
   índice único es efectivamente lo único que no puede perder la carrera con una segunda pestaña —
   eso no cambió—, pero cuando salta, **la sesión de SQLAlchemy ya no sirve para hacer otra
   consulta**, y sin otra consulta no hay id del cliente existente que devolver. Y el id es la
   mitad del criterio de aceptación («ofrece ver el duplicado»).
   Así que quedan los dos: un `SELECT` que **nombra** al duplicado en el caso normal, y el índice
   que lo **impide** siempre. `ClienteDuplicado.cliente_existente_id` pasó a ser opcional: en la
   carrera —rara— el mensaje llega sin enlace, que es la respuesta honesta cuando no se puede
   averiguar cuál era.
2. **`backend/migrations/env.py`** no estaba en la lista de archivos y había que tocarlo: los
   modelos de cada contexto se registran ahí y un modelo ausente es una tabla que `autogenerate`
   propone borrar en silencio.
3. **`backend/tests/integracion/conftest.py`** tampoco: la limpieza entre tests necesita
   `DELETE FROM cliente`.
4. **El router se partió en dos sub-routers** (`_rutas_de_padron` y `_rutas_de_catalogo`) porque
   `crear_router` entero superaba la complejidad ciclomática de 10 que fija `CLAUDE.md` §5. Es el
   mismo arreglo que ya tenía el router de usuarios, y de paso deja `/clientes/padron` montado
   antes de las rutas con `{cliente_id}`.

---

## Verificación — Gate 2 (2026-08-31)

| Gate | Comando | Resultado |
|---|---|---|
| Formato Python | `ruff format --check .` | **verde** |
| Lint Python | `ruff check .` | **verde** |
| Tipos | `python -m mypy backend` | **verde** — 255 archivos |
| Tests Python | `pytest backend` | **verde** — 670 pasan, **ninguno se saltea** |
| Cobertura | `pytest --cov=cheatsheet` | **89.86 %**, muy por encima del umbral de 80 % |
| Typecheck frontend | `npm run typecheck` | **verde** |
| Lint frontend | `npm run lint` | **verde** |
| Tests frontend | `npm run test` | **verde** — 242 pasan en 24 archivos |
| Formato frontend | `npm run format:check` | **falla, y no por esta unidad** — ver abajo |

### Los tests de integración, contra PostgreSQL de verdad

Se levantaron los servicios (`docker compose -f backend/docker-compose.yml up -d`) y corrieron los
**19 casos nuevos**: 10 en `test_clientes_postgres.py` y 9 en `test_api_clientes.py`. Todos verdes.
Son los que no se pueden fingir:

- **el aislamiento por `empresa_id`**, que es una política del motor: una empresa no ve, no lee por
  id, no escribe ni borra un cliente de otra, y una sesión sin empresa declarada no ve nada;
- **el índice único parcial**: el mismo CUIT en dos empresas convive, en la misma no, y varios
  clientes **sin** CUIT tampoco chocan entre sí — que es la razón de que el índice lleve
  `WHERE cuit IS NOT NULL`;
- **que la aplicación no tenga `DELETE`**: el `GRANT` de la migración 0008 no lo concede y el
  intento levanta `ProgrammingError`;
- **el 409 con el id del duplicado**, de punta a punta, que es la costura que ninguna prueba
  unitaria mira.

Con los servicios arriba la suite entera pasa a **670 casos, ninguno salteado, 89.86 % de
cobertura**. Los módulos de esta unidad: `application/clientes.py` 99 %, `domain/cliente.py` 98 %,
`api/routers/clientes.py` 90 %, `infrastructure/repositories.py` 85 %.

### Lo que sigue fallando, y no es de esta unidad

- **`ruff format --check` y `mypy` sobre la raíz** incluyen `tmp/` y `output/`, dos directorios sin
  trackear del entorno local, y ahí sí hay errores (scripts de PDF sin anotar). Sobre `backend/`,
  que es lo que esta unidad toca, los dos pasan.
- **`npm run format:check` falla en 113 archivos, ninguno de ellos por su contenido.** El checkout
  tiene `core.autocrlf=true`, así que **todo** el repositorio está en disco con CRLF y Prettier
  espera LF. Falla igual en archivos que esta unidad no tocó. Los archivos nuevos se verificaron con
  `prettier --check --end-of-line auto` y pasan. Está anotado en `TODO.md`.

---

## Decisiones tomadas durante la unidad

- 2026-08-31 · ¿Puede existir un cliente sin CUIT? → **Sí.** Sólo `nombre` es obligatorio; HU-E8-01
  crea clientes desde WhatsApp con nada más que un teléfono.
- 2026-08-31 · ¿Qué pasa si ARCA no está conectada? → **No bloquea.** Es un caso de `NO_DISPONIBLE`,
  el mismo patrón de `padron-y-datos-fiscales`. La validación estructural sí bloquea siempre.
- 2026-08-31 · ¿Se borra un cliente? → **No.** Sólo `activo`, por ADR-007 y por el hueco H4.
