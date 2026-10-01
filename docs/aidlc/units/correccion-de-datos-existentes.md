# Unidad: correccion-de-datos-existentes

**HUs**: HU-E4-05 (RN-09)   **Contexto dueño**: master_data (sin edges nuevos)   **Rama**: feature/master_data-correccion-de-datos-existentes

> Origen: P1 del Gate 1 de [`normalizacion-de-datos`](normalizacion-de-datos.md) (la corrección se partió
> en esta unidad), decisión D85 (`docs/aidlc/units.md:438-478`). La rama sale de
> `feature/master_data-normalizacion-de-datos` (PR #54); depende del normalizador
> `master_data/domain/normalizacion.py`, que esta unidad **usa y no cambia**. El PR apunta a esa rama.

## Qué hace

Corrige, una vez por empresa y a pedido de un Administrador, los nombres de clientes, servicios y
categorías guardados antes de la normalización de HU-E4-05. Primero muestra un informe previo
(cantidades, ejemplos y lo que no se va a tocar y por qué); al aplicar guarda un respaldo de cada valor
original en la misma transacción que el cambio, registra la operación en la bitácora solo con conteos
y permite restaurar una corrida sin pisar ediciones posteriores. No toca comprobantes ni hojas.

### Lo que las historias piden, textual

**HU-E4-05 RN-09** (`docs/aidlc/inputs/historias-de-usuario.md:849-854`):
«RN-09 (datos existentes): corrección única por empresa, con estas condiciones:
- Se genera un informe previo (dry-run) con cantidades y ejemplos.
- Se hace un respaldo restaurable de los valores originales antes de aplicar.
- No toca comprobantes ni las hojas.
- Los casos que colisionarían con una restricción de unicidad (CUIT o categoría) se informan y no
  se cambian.
- Se registra en la bitácora con los conteos.»

Criterio (`:868`): «Ejecuto la corrección de datos existentes | Obtengo el informe previo, existe
el respaldo y los cambios quedan en la bitácora | PAN-DM-01».

Actor de la historia (`:828`): «Administrador / Operador (regla transversal: …)». El mapa de
navegación da Datos Maestros a «Admin · Operador» (`prototipos/mapa-navegacion-oficial.html:65`).
RN-09 no nombra un rol (ver P1).

## Lo que ya existe (se cita, no se rehace) y el hueco

| Pieza | Estado hoy | Evidencia | Hueco |
|---|---|---|---|
| Normalizador puro e idempotente | Vigente | `domain/normalizacion.py:63-115` | Ninguno: se usa |
| Nombre de cliente según CUIT | Vigente | `normalizacion.py:95-99` | Ninguno |
| Unicidad de categoría | Vigente | índice `(empresa_id, lower(nombre), aplica_a)`, `0010_categorias.py:88-91`; `clave_de_unicidad`, `domain/categoria.py:120-127` | Detectar colisiones **antes** de escribir |
| CUIT, email y WhatsApp normalizados | Vigente desde el alta | `shared/fiscal.py:79-85`, `repositories.py:65-68` | Ninguno: no se corrigen (hallazgo 1) |
| Al leer no se normaliza | Vigente | `repositories.py:44-59` | Es lo que deja ver los valores viejos |
| RLS por `app.current_empresa` | Vigente | `platform/database.py:159-183` (`set_config(..., true)`); políticas, `0010_categorias.py:70-86` | Tabla nueva con el mismo patrón |
| Bitácora en la misma transacción | Vigente | `api/dependencies.py:74-97, 109-118` | Evento con conteos |
| Guard de Administrador en `master_data` | **No existe** | `application/autorizacion.py:18-31` | Agregarlo (hallazgo 6) |
| Corrección, respaldo, restauración, pantalla | **No existe** | — | Todo lo de esta unidad |

### Hallazgos

1. **RN-09 menciona colisiones de CUIT, pero no puede haberlas.** La corrección no cambia el CUIT:
   ya se guarda en 11 dígitos (`fiscal.py:79-85`, `repositories.py:65`). Las colisiones posibles son
   solo de **categoría**. Se deja un test de caracterización.
2. **Qué puede colisionar en categoría.** `lower()` ya iguala las mayúsculas, así que una colisión
   nueva solo puede venir de RN-01: espacios internos dobles, U+200B/U+FEFF/U+00AD, NFD frente a NFC,
   espacios Unicode. Por ejemplo, «Vip  Gold» junto a «Vip gold». También pueden chocar dos filas
   viejas que normalizan a la misma clave. Dos categorías con el mismo nombre y distinto `aplica_a`
   (CLIENTE y AMBOS) **no** colisionan, porque el índice incluye el ámbito, y van a seguir viéndose
   iguales. Se informa como dato; no se cambia.
3. **La restricción de servicio es `NOT VALID`** (`0025_servicio_duracion_en_rango.py:8-13, 48-51`).
   PostgreSQL la exige en cada UPDATE de la fila. Renombrar un servicio viejo con duración fuera de
   rango falla y **aborta toda la transacción**. Esos servicios se excluyen con el mismo predicado de
   `0025:63-68` y se informan (P7).
4. **Corregir con `renombrar` + `guardar` tocaría la hoja propia.** `Cliente.renombrar` mueve
   `actualizado_en` (`domain/cliente.py:81-83`), `_volcar` escribe `updated_at`
   (`repositories.py:74`) y el write-back elige PANEL/AGENTE por `actualizado_en > desde`
   (`application/ingesta.py:326, 350`; `spreadsheet_sync/infrastructure/escritura.py:157-165`).
   Por eso la corrección escribe **solo `nombre`**, con un UPDATE propio (P2). Contexto: hoy ese
   write-back no funciona (`TODO.md:600-603`).
5. **Un nombre puede quedar inválido después de normalizar.** Puede quedar vacío si era solo
   caracteres `Cf` (`normalizacion.py:73`), o más largo que el máximo: `str.lower()` expande «İ» a dos
   caracteres y `normalizacion.py:114, 145` no tienen la protección de `_mayuscula` (`:134-137`). Los
   límites son 60 en categoría y 200 en cliente y servicio (`categoria.py:24`, `cliente.py:31`,
   `servicio.py:30`). Se omiten con el motivo `NOMBRE_INVALIDO`. La expansión de `lower()` es un
   defecto menor del normalizador: se anota en `TODO.md` §20 y no se arregla acá.
6. **`master_data` no tiene un guard de Administrador**: solo `exigir_lectura` y `exigir_escritura`
   (`autorizacion.py:24-31`). El de `identity` no se puede importar (R3). Se agrega
   `exigir_administrador` en `master_data/application/autorizacion.py`, como en
   `business_config/application/reglas.py:38-40`.
7. **Tamaños**: `application/categorias.py` 396 y `application/clientes.py` 393 (el plan anterior
   decía 392); `ListadoDeClientes.tsx` 395; `api/routers/clientes.py` 318. **No se les agrega
   ninguna línea**: todo va en archivos nuevos. Con margen: `ports.py` 193, `models.py` 189,
   `index.ts` 78, `datos-maestros/clientes/page.tsx` 48.
8. **La tabla de respaldo no está en el DER** (BC2 tiene tres tablas, `der.md:86-135`). Se documenta
   como hueco del DER en `der.md`, con la razón: RN-09 la exige y el DER es anterior a ADR-0009.
9. **El `lower()` de Python y el de PostgreSQL pueden no coincidir** fuera de ASCII, según la
   intercalación. La detección del dominio es la primera barrera; la segunda es el índice, con un
   savepoint por categoría.
10. **Parte de los datos ya puede estar corregida**: editar un cliente lo vuelve a normalizar (Gate 2
    de `normalizacion-de-datos`, `normalizacion-de-datos.md:521-524`). El dry-run lo refleja; no hay
    nada que hacer.

## Preguntas (con recomendación; P1, P2, P3 y P6 necesitan a una persona, el resto se aprueba en bloque)

### P1. ¿Quién dispara la corrección y desde dónde?
- **A (recomendada)**: solo el **Administrador** (informe, aplicación y restauración), desde una
  sección nueva de PAN-DM-01 («Formato de los datos existentes»), con un componente nuevo
  (`CorreccionDeDatos.tsx`) y un router nuevo (`api/routers/correccion.py`).
- B: Administrador y Operador, como el actor de la historia.
- C: solo API, sin pantalla.

**Razón**: es una escritura masiva sobre todo el catálogo de la empresa, el mismo tipo de operación
que el sistema ya reserva al Administrador (puntos de venta, reglas, FAQ). El criterio cita PAN-DM-01,
así que C no lo cumple. Los archivos actuales de PAN-DM-01 y del router de clientes no tienen lugar
(hallazgo 7).

### P2. ¿La corrección mueve `updated_at`?
- **A (recomendada)**: no. Solo cambia `nombre`; `updated_at` queda como estaba.
- B: sí, como cualquier edición.

**Razón**: con B, el próximo write-back con `desde` enviaría a la hoja «CheatSheet (no editar)»
todos los clientes PANEL/AGENTE corregidos (hallazgo 4), y RN-09 dice «no toca las hojas». La
corrección es un cambio de formato, no una edición de negocio; queda registrada en la bitácora y en el
respaldo. Lo que se paga: la hoja propia sigue con el formato viejo de esos clientes hasta que se
editen o hasta un write-back completo.

### P3. La restauración, ¿con pantalla o solo por API?
- **A (recomendada)**: pantalla mínima dentro de la misma sección: lista de corridas (fecha y
  cantidad) con un botón «Restaurar» y confirmación. Unas 60 líneas más.
- B: solo API (`POST …/restauracion`), con un ítem en `TODO.md`.

**Razón**: un «respaldo restaurable» que solo se puede restaurar con `curl` no se puede demostrar en
`staging`.

### P4. ¿Sincrónica o como tarea asíncrona?
- **Recomendada**: sincrónica, dentro de la petición, en una transacción, con UPDATEs en lotes de
  500. Una pyme tiene cientos o pocos miles de registros: son segundos. Una tarea de Celery agregaría
  estado, reintentos y una DLQ para algo que corre una vez.

### P5. «Corrección única»: ¿se bloquea una segunda corrida?
- **Recomendada**: no se bloquea; la operación es idempotente. Una segunda aplicación encuentra 0
  cambios, no crea respaldo y registra «0» en la bitácora. Después de una restauración se puede volver
  a aplicar. «Única» se cumple porque todo lo que entra ya se normaliza (unidad anterior).

### P6. Tamaño
Estimación: unas 950 líneas de producción (backend ~700, frontend ~250) y unas 700 de tests. Pasa con
holgura la referencia de unas 400.
- **A (recomendada)**: una sola unidad y un PR, revisable por commits: (1) dominio y aplicación, (2)
  migración e infraestructura, (3) API, (4) frontend. Ninguna parte se puede verificar contra el
  criterio por separado.
- B: achicar con P3 = B (sin pantalla de restauración), unas 60 líneas menos.

### P7. Servicios con duración fuera de regla
- **Recomendada**: se omiten, se informan con el motivo `DURACION_FUERA_DE_REGLA` y se corrigen
  cuando alguien los edite (`0025:11`). La alternativa de un savepoint por servicio es más lenta y
  oculta la causa.

## Diseño

### Dominio — `contexts/master_data/domain/correccion.py` (nuevo, ~120 líneas)
- `EntidadCorregible(StrEnum)`: `CLIENTE`, `SERVICIO`, `CATEGORIA`.
- `MotivoDeOmision(StrEnum)`: `COLISION_DE_CATEGORIA`, `NOMBRE_INVALIDO`, `DURACION_FUERA_DE_REGLA`.
- `NombreRegistrado` (frozen): `entidad`, `id`, `nombre`, `cuit: CUIT | None`,
  `aplica_a: AmbitoDeCategoria | None`, `duracion_valida: bool = True`.
- `Cambio` (frozen): `entidad`, `id`, `original`, `normalizado`. `Omision`: `entidad`, `id`,
  `original`, `normalizado`, `motivo`.
- `PlanDeCorreccion` (frozen): `cambios`, `omisiones`, `conteos() -> Mapping[str, int]`.
- `planificar_correccion(registros: Iterable[NombreRegistrado]) -> PlanDeCorreccion`, función pura:
  1. Normaliza: cliente con `normalizar_nombre_de_cliente(nombre, cuit)`; servicio y categoría con
     `normalizar_nombre_de_catalogo`.
  2. Si el resultado es igual al original, no hace nada (eso la hace idempotente).
  3. Si está vacío o pasa `LARGO_MAXIMO_NOMBRE` del agregado, lo omite como `NOMBRE_INVALIDO`.
  4. Un servicio con `duracion_valida = False` se omite como `DURACION_FUERA_DE_REGLA`.
  5. En categorías, agrupa por `(clave final.lower(), aplica_a)`, donde la clave final es el
     normalizado si cambia y el original si no. En un grupo de más de una fila, **ninguna** de las que
     cambiarían se cambia: se omiten como `COLISION_DE_CATEGORIA`.
- Sin eventos de dominio nuevos. Sin `datetime` ni I/O (R1).

### Aplicación — `contexts/master_data/application/correccion.py` (nuevo, ~170 líneas)
- `InformarCorreccion.ejecutar(empresa_id, rol) -> InformeDeCorreccion`. Exige el Administrador (P1).
  Lee con el puerto, planifica y devuelve conteos por entidad (`a_corregir`, omitidos por motivo) y
  hasta `EJEMPLOS_POR_ENTIDAD = 5` pares «antes → después» por entidad. Los ejemplos muestran nombres
  **solo** al Administrador de esa empresa, que ya los ve en el listado; nunca van a la bitácora ni a
  los logs.
- `AplicarCorreccion.ejecutar(empresa_id, usuario_id, rol, direccion_ip) -> ResultadoDeCorreccion`:
  1. `exigir_administrador`.
  2. `await correccion.tomar_turno()`. Si no lo consigue, lanza `CorreccionEnCurso`
     (`OperacionNoPermitida`, 409).
  3. Lee, planifica y genera `corrida_id = uuid4()`.
  4. `aplicados = await correccion.aplicar(corrida_id, cambios, momento)`. Devuelve los cambios que
     se escribieron de verdad, porque el compare-and-set descarta las filas que cambiaron en el medio.
  5. Publica un `EventoAuditable` con `accion = "correccion_de_datos_aplicada"`,
     `entidad_afectada = f"correccion:{corrida_id}"` y `detalle` con conteos en texto (`clientes`,
     `servicios`, `categorias`, `omitidos_colision`, `omitidos_nombre_invalido`,
     `omitidos_duracion`).
  6. Todo corre en la transacción de la unidad de trabajo: si algo falla, no queda ni cambio, ni
     respaldo, ni bitácora.
- `RestaurarCorreccion.ejecutar(corrida_id, …) -> ResultadoDeRestauracion`. Exige el Administrador,
  toma el mismo turno y llama a `correccion.restaurar(corrida_id)`, que devuelve `restaurados` y
  `conservados` (los editados después). Si la corrida no existe, lanza `CorridaNoEncontrada` (404, mismo
  patrón que `CategoriaNoEncontrada`). Publica `correccion_de_datos_restaurada` con conteos.
- `ListarCorridas.ejecutar(empresa_id, rol) -> tuple[ResumenDeCorrida, ...]` (solo si P3 = A).
- `autorizacion.py`: `exigir_administrador(rol)` (+6 líneas). `errors.py`: `CorreccionEnCurso` y
  `CorridaNoEncontrada` (+15).

### Puertos y adaptadores
- `ports.py` (193 → ~228): `PortCorreccionDeNombres(Protocol)`:
  - `tomar_turno() -> bool`
  - `leer_nombres() -> Sequence[NombreRegistrado]`
  - `aplicar(corrida_id, cambios, momento) -> Sequence[Cambio]`
  - `restaurar(corrida_id) -> tuple[int, int]`
  - `existe_corrida(corrida_id) -> bool`
  - `listar_corridas() -> Sequence[ResumenDeCorrida]`
- `infrastructure/correccion.py` (nuevo, ~180 líneas), `CorreccionDeNombresPostgres(sesion)`:
  - `tomar_turno`: `SELECT pg_try_advisory_xact_lock(hashtextextended('correccion_de_datos:' || :empresa, 0))`.
    Se libera con la transacción. Sin espera: una segunda corrida simultánea recibe 409.
  - `leer_nombres`: tres SELECT de `id, nombre` (más `cuit` en cliente, `aplica_a` en categoría y, en
    servicio, el predicado de `0025` como columna booleana). Filtran solo por RLS, como el resto del
    contexto (`repositories.py:3-8`).
  - `aplicar` en clientes y servicios: lotes de 500 con
    `UPDATE <tabla> t SET nombre = v.nuevo FROM (VALUES …) v(id, original, nuevo) WHERE t.id = v.id AND t.nombre = v.original RETURNING t.id`.
    Sin tocar `updated_at` (P2). Después, un INSERT en `respaldo_de_normalizacion` solo para los ids
    devueltos.
  - `aplicar` en categorías: una por una, cada una en `begin_nested()`. Una `IntegrityError` del índice
    `uq_categoria_empresa_nombre_ambito` se traduce en una omisión por colisión (hallazgo 9).
  - `restaurar`: por entidad,
    `UPDATE <tabla> t SET nombre = r.valor_original FROM respaldo_de_normalizacion r WHERE r.corrida_id = :c AND r.entidad = :e AND t.id = r.entidad_id AND t.nombre = r.valor_normalizado RETURNING t.id`.
    `conservados` = filas del respaldo menos restauradas. Es idempotente por construcción: una segunda
    restauración encuentra `nombre = valor_original` y no coincide. Las categorías van con savepoint,
    por la misma razón.
- `infrastructure/models.py` (189 → ~215): `RespaldoDeNormalizacionORM`.
- `infrastructure/ensamblado.py`: `correccion: PortCorreccionDeNombres` en `DatosMaestros` (+3).

### Otros contextos
- `billing`: no se toca. La corrección no tiene puerto hacia `comprobante`, y los comprobantes emitidos
  tienen sus datos de receptor desnormalizados (HU-E4-05 RN-06; la razón social sale del padrón,
  `billing/application/emision.py:112-113`).
- `spreadsheet_sync`: no se toca. Sin puerto hacia hojas; `updated_at` no se mueve (P2), así que el
  write-back no lo recoge. La resincronización compara normalizado contra normalizado (unidad
  anterior), así que no hay falsos cambios ni antes ni después.
- `observability`: por el `EventoAuditable` del Shared Kernel (edge `all → observability` existente).
- **Sin ADR**: ningún edge nuevo.

### Frontend
- `features/master_data/api/correccion.ts` (nuevo, ~70): `informarCorreccion()`, `aplicarCorreccion()`,
  `listarCorridas()`, `restaurarCorreccion(id)`, con el patrón de `pedir` de `api/categoria.ts:42-60`.
- `features/master_data/components/CorreccionDeDatos.tsx` (nuevo, ~180):
  1. Botón «Revisar formato de los datos existentes» → informe con conteos por entidad, ejemplos
     «antes → después» y omitidos con su motivo en lenguaje de usuario.
  2. «Aplicar corrección» con confirmación → resultado.
  3. Lista de corridas con «Restaurar» (P3).
  4. Con 0 a corregir: «No hay datos para corregir».
- `features/master_data/index.ts`: exporta el componente (+2).
- `app/(panel)/datos-maestros/clientes/page.tsx`: renderiza `<CorreccionDeDatos />` debajo del listado
  solo si `claims.rol === "ADMINISTRADOR"` (+4). Es una cortesía; el guard es el backend.
- Sin prototipo para PAN-DM-01 (`prototipos.md:95-97`): se arma con el catálogo de componentes, como el
  resto de la pantalla.

### API — `api/routers/correccion.py` (nuevo, ~140)
- `GET /datos-maestros/correccion/informe`
- `POST /datos-maestros/correccion` → 201 con `corrida_id` y conteos
- `GET /datos-maestros/correccion/corridas` (si P3 = A)
- `POST /datos-maestros/correccion/{corrida_id}/restauracion`
- Se registra en `api/main.py` (+2). El rol se pasa al caso de uso, igual que en
  `api/routers/clientes.py:3-6`.

## Infraestructura

- **Migración `0030_respaldo_de_normalizacion.py`**. En esta rama: `revision = "0030"`,
  `down_revision = "0025"`, porque la cabeza es `0025` (`0025_servicio_duracion_en_rango.py:34-35`) y
  no hay `0026` a `0029` acá. Al rebasar sobre `develop` se vuelve a apuntar a la cabeza que corresponda
  (reserva en `units.md:476-478`) y se verifica que `alembic heads` dé una sola cabeza.
  - Tabla `respaldo_de_normalizacion`:
    - `id uuid PK`
    - `empresa_id uuid NN FK empresa ON DELETE CASCADE`
    - `corrida_id uuid NN`
    - `entidad varchar(20) NN CHECK IN ('CLIENTE','SERVICIO','CATEGORIA')`
    - `entidad_id uuid NN`
    - `campo varchar(30) NN DEFAULT 'nombre'`
    - `valor_original varchar(200) NN`
    - `valor_normalizado varchar(200) NN`
    - `usuario_id uuid NULL`
    - `created_at timestamptz NN`
  - Índice `(empresa_id, corrida_id)`.
  - `ENABLE` + `FORCE ROW LEVEL SECURITY` y política `aislamiento_por_empresa` literal, con el patrón
    de `0010_categorias.py:70-74`.
  - `GRANT SELECT, INSERT` a `cheatsheet_app`: **sin UPDATE ni DELETE**. El respaldo es inmutable,
    porque la restauración no lo modifica.
  - Reversible: `downgrade` borra la tabla. Sin backfill.
- **Trabajo asíncrono**: no aplica (P4).
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica.

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica
- [x] Toca comprobantes fiscales → test de que una corrida no cambia ninguna fila de `comprobante`
- [ ] Consume un webhook → no aplica
- [x] Datos con `empresa_id` → tabla nueva con RLS: aislamiento entre dos empresas (informe, aplicación, restauración y lectura del respaldo)
- [ ] Usa salida de un LLM → no aplica
- [x] Datos personales → el respaldo guarda nombres. La bitácora y los logs solo llevan conteos. Tests con nombres y CUIT ficticios

Riesgos que no son tests:
- **Retención del respaldo**: guarda nombres para siempre, con la misma protección que la tabla de
  origen (RLS). Cuánto se retienen queda en `TODO.md` §20 como pendiente, sin unidad.
- **Restaurar no es definitivo**: un cliente restaurado se vuelve a normalizar la próxima vez que
  alguien lo edita (decisión del Gate 2 anterior).
- **Ventana entre informe y aplicación**: la aplicación vuelve a calcular. El resultado que muestra es
  el real y puede diferir del informe si alguien editó en el medio.
- **Bloqueos de fila**: el UPDATE por lotes bloquea las filas tocadas hasta el commit (segundos). Una
  edición simultánea del panel espera y después escribe su propio valor, también normalizado.

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/correccion.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/master_data/application/correccion.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/master_data/application/ports.py` (`PortCorreccionDeNombres`)
- [ ] `backend/src/cheatsheet/contexts/master_data/application/autorizacion.py` (`exigir_administrador`)
- [ ] `backend/src/cheatsheet/contexts/master_data/application/errors.py` (`CorreccionEnCurso`, `CorridaNoEncontrada`)
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/correccion.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/models.py` (`RespaldoDeNormalizacionORM`)
- [ ] `backend/src/cheatsheet/contexts/master_data/infrastructure/ensamblado.py`
- [ ] `backend/migrations/versions/0030_respaldo_de_normalizacion.py` (nuevo)
- [ ] `backend/src/cheatsheet/api/routers/correccion.py` (nuevo) y `backend/src/cheatsheet/api/main.py`
- [ ] `backend/tests/contexts/master_data/domain/test_correccion.py` (nuevo)
- [ ] `backend/tests/contexts/master_data/application/test_correccion.py` (nuevo)
- [ ] `backend/tests/integracion/test_correccion_postgres.py` (nuevo)
- [ ] `backend/tests/integracion/test_api_correccion.py` (nuevo)

### Frontend
- [ ] `frontend/src/features/master_data/api/correccion.ts` (nuevo)
- [ ] `frontend/src/features/master_data/components/CorreccionDeDatos.tsx` (nuevo)
- [ ] `frontend/src/features/master_data/components/__tests__/CorreccionDeDatos.test.tsx` (nuevo)
- [ ] `frontend/src/features/master_data/index.ts`
- [ ] `frontend/src/app/(panel)/datos-maestros/clientes/page.tsx`

### Docs
- [ ] `docs/aidlc/units.md`: fila de esta unidad (estado) y la nota de D85 («`0030` usada»)
- [ ] `docs/aidlc/inputs/der.md`: hueco nuevo en BC2 por `respaldo_de_normalizacion` (hallazgo 8)
- [ ] `docs/aidlc/TODO.md` §20: retención del respaldo; la expansión de `lower()` del normalizador (hallazgo 5); verificaciones manuales
- Sin ADR.

## Casos de prueba

Modo: **test primero**. Los de PostgreSQL se saltean sin Docker y corren en la CI.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: cliente «JUAN PEREZ» → cambio a «Juan Perez»; con CUIT 30-… «ferreteria lopez s.r.l.» → «Ferreteria Lopez S.R.L.»; servicio «CORTE DE PELO» → «Corte de pelo» | unit (dominio) | pendiente |
| 2 | RED: un nombre ya normalizado no genera cambio; planificar sobre el resultado aplicado da 0 cambios (idempotencia) | unit (dominio) | pendiente |
| 3 | RED: categorías «Vip  Gold» y «Vip gold» con el mismo ámbito → la primera se omite como `COLISION_DE_CATEGORIA`; con ámbitos distintos → se corrige | unit (dominio) | pendiente |
| 4 | RED: dos categorías viejas que normalizan a la misma clave → las dos se omiten | unit (dominio) | pendiente |
| 5 | RED: nombre solo de U+200B → `NOMBRE_INVALIDO`; categoría que pasa 60 al normalizar («İ») → `NOMBRE_INVALIDO` | unit (dominio) | pendiente |
| 6 | RED: servicio con `duracion_valida = False` → `DURACION_FUERA_DE_REGLA` | unit (dominio) | pendiente |
| 7 | RED: `InformarCorreccion` devuelve conteos y como máximo 5 ejemplos por entidad, y no escribe nada | unit (aplicación) | pendiente |
| 8 | RED: Operador, Solo Lectura y Contador → `PermisoDenegado` en los tres casos de uso | unit (aplicación) | pendiente |
| 9 | RED: `AplicarCorreccion` publica un evento con conteos en `detalle` y **ningún nombre** (se recorre el `detalle` buscando los nombres de prueba) | unit (aplicación) | pendiente |
| 10 | RED: sin turno (`tomar_turno` = False) → `CorreccionEnCurso` y nada escrito | unit (aplicación) | pendiente |
| 11 | RED: corrida inexistente → `CorridaNoEncontrada` | unit (aplicación) | pendiente |
| 12 | RED: aplicar escribe el nombre y el respaldo en la misma transacción; un fallo forzado después del respaldo deja todo sin cambios | integración (PostgreSQL) | pendiente |
| 13 | RED: aplicar dos veces → la segunda da 0 cambios y no agrega filas de respaldo | integración (PostgreSQL) | pendiente |
| 14 | RED: `updated_at` de cliente y servicio no cambia; ninguna fila de `comprobante` cambia | integración (PostgreSQL) | pendiente |
| 15 | RED: servicio viejo con duración 9999 → omitido; la transacción no aborta | integración (PostgreSQL) | pendiente |
| 16 | RED: restaurar devuelve el original; un registro editado después de la corrección se conserva; restaurar dos veces da 0 la segunda | integración (PostgreSQL) | pendiente |
| 17 | RED: aislamiento — la corrida de la empresa A no lee ni cambia nombres de B; B no ve el respaldo de A; restaurar con el `corrida_id` de A desde B da «no encontrada» | integración (PostgreSQL, RLS) | pendiente |
| 18 | RED: dos aplicaciones simultáneas de la misma empresa → una responde 409 | integración (PostgreSQL) | pendiente |
| 19 | RED: colisión que solo detecta el índice (savepoint) → omitida; el resto se aplica | integración (PostgreSQL) | pendiente |
| 20 | C: el CUIT guardado nunca cambia y no existe un motivo «colisión de CUIT» (hallazgo 1) | integración (PostgreSQL) | pendiente |
| 21 | RED: API — Administrador 200/201; Operador 403; la bitácora tiene la fila `correccion_de_datos_aplicada` | integración (API) | pendiente |
| 22 | RED: la migración `0030` sube y baja; `alembic heads` da una sola cabeza | integración (migraciones) | pendiente |
| 23 | RED: `CorreccionDeDatos` muestra el informe, pide confirmación, muestra el resultado, restaura y muestra «No hay datos para corregir» con 0 | unit (frontend) | pendiente |
| 24 | RED: la sección no se renderiza para un rol que no es Administrador | unit (frontend) | pendiente |
| 25 | Compuertas: `ruff format --check`, `ruff check`, `mypy`, `pytest` (cobertura ≥ 80 %), `guard_architecture`; `npm run format:check`, `lint`, `typecheck`, `test:coverage` | compuertas | pendiente |
| 26 | En el navegador: PAN-DM-01 como Administrador → informe, aplicar, ver la bitácora, restaurar | manual | pendiente → `TODO.md` |

## Verificaciones que no se pueden hacer acá
- Los casos 12 a 22 (PostgreSQL) se saltean en local sin Docker y se observan en la CI.
- En `staging`, con datos cargados antes de la normalización: el criterio de PAN-DM-01 completo
  (informe, respaldo y bitácora) y que la hoja «CheatSheet (no editar)» no cambia después de aplicar.
- Que `lower()` de PostgreSQL coincida con el de Python en la intercalación de `staging` (hallazgo 9).

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
-
