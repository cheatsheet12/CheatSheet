# Unidad: categorias-y-clasificacion

**HUs**: HU-E4-03, HU-E4-04 **Contexto dueño**: master_data
**Rama**: feature/master_data-categorias-y-clasificacion

## Qué hace

Un Administrador u Operador entra a **PAN-DM-03**, crea categorías propias de su negocio con un
ámbito —clientes, servicios o ambos—, las edita y las elimina. Y desde PAN-DM-01 y PAN-DM-02
clasifica clientes y servicios con ellas, pudiendo asignar más de una, y filtra los dos listados
por categoría.

Cierra el épico 3.

---

## La dependencia de `catalogo-de-servicios` — resuelta antes de escribir código

El plan se aprobó cuando `catalogo-de-servicios` estaba **en revisión y no en `develop`**, así que
esta rama se cortó de `feature/master_data-catalogo-de-servicios` amparada en la regla 1c, que
permite arrancar sobre una dependencia sin mergear si el plan declara qué asume.

**Duró poco: [#25](https://github.com/cheatsheet12/CheatSheet/pull/25) se mergeó el 2026-09-01**, y
la rama se sincronizó con `develop` antes de la primera línea de implementación. La concesión queda
registrada porque pasó, no porque siga vigente: hoy esta unidad depende de código que está en
`develop` como cualquier otra, y su migración `0010` va sobre la `0009` ya mergeada.

**Lo que sí dejó como lección**, y está en `TODO.md`: al mergear #24 y #25 apareció un conflicto en
`docs/aidlc/units.md` que la regla 1c dice que no debería existir. Ver la nota al final de este
documento.

---

## Las dos decisiones que esta unidad ejecuta, y una que resuelve

### D8, del mapa del épico: la clasificación es N a N

El DER pone `categoria_id uuid FK` dentro de `cliente` y de `servicio`. HU-E4-04 RN-02 dice que un
elemento «puede tener más de una categoría asignada». **Gana la historia**, como aprobó el mapa: dos
tablas de enlace, `cliente_categoria` y `servicio_categoria`, y la columna `categoria_id` nunca se
crea — ni se creó en las migraciones 0008 y 0009, así que no hay dato que migrar.

**Un efecto secundario que vale la pena nombrar porque es gratis:** el criterio «edito el nombre de
una categoría y el cambio se refleja en todos los elementos clasificados con ella» se cumple **por
construcción**. El nombre vive en una sola fila. Con una copia desnormalizada habría que salir a
actualizar N filas y ese criterio sería un trabajo; acá es una consecuencia de normalizar.

### D9, del mapa del épico: el ámbito `AMBOS`

El enum `aplica_a` del DER tiene `CLIENTE · SERVICIO · FAQ · TURNO` y RN-01 pide «clientes,
servicios o ambos». Se agrega **`AMBOS`**. `FAQ` y `TURNO` no se implementan: son de los épicos 8 y
7, y la pantalla ofrece únicamente los tres que le corresponden.

El enum vive en `master_data/domain/valores.py` junto a `OrigenDato` y `AlicuotaIVA`, y se llama
**`AmbitoDeCategoria`** — `aplica_a` es el nombre de la columna, no un buen nombre de tipo.

### Nueva: `categoria_empresa` **sí** se puede borrar

Las dos unidades anteriores no conceden `DELETE` a la aplicación, a propósito y con un test cada una
que lo comprueba. Esta lo concede, y la asimetría es deliberada y no un descuido:

| | `cliente` · `servicio` | `categoria_empresa` |
|---|---|---|
| Quién los referencia | `comprobante`, `cobro`, `turno` — **sin FK declarada** (hueco H4 del DER) | sólo las dos tablas de enlace, **dentro de este mismo contexto y con FK real** |
| Qué se pierde al borrar | historia fiscal apuntando al vacío | una clasificación, que es exactamente lo que RN-03 pide perder |
| Qué dice la historia | nunca habla de borrar | «quiero crear, editar y **eliminar** categorías» |

RN-03 es explícita: al eliminar, «los clientes o servicios que la tenían asignada quedan sin esa
clasificación, **sin afectar el resto de sus datos**». Eso es un `ON DELETE CASCADE` sobre las tablas
de enlace, y nada más. No hay dato de negocio que sobreviva a la categoría.

---

## Diseño

### Dominio — `contexts/master_data/domain/`

- **`AmbitoDeCategoria`** (`valores.py`): `CLIENTE · SERVICIO · AMBOS`.
- **`CategoriaEmpresa`** (`categoria.py`), agregado raíz: `id`, `empresa_id`, `nombre`, `aplica_a`,
  `creado_en`.
  - `registrar`, `renombrar`, `cambiar_ambito`.
  - **`admite_clientes` / `admite_servicios`** — las dos propiedades donde vive RN-01 de HU-E4-04.
    Una categoría admite clientes si su ámbito es `CLIENTE` o `AMBOS`. La regla está acá y no en el
    combo de la pantalla, porque el agente del épico 8 también va a clasificar.
  - **`exigir_admite_cliente()` / `exigir_admite_servicio()`** levantan `AmbitoIncompatible` — el
    guard que la asignación llama.
- **`Clasificacion`** — **no** se crea un agregado para el enlace. Es una relación sin identidad ni
  ciclo de vida propios: existe o no existe. Modelarla como entidad agregaría un id que nadie usa y
  un repositorio que sólo tiene `agregar` y `quitar`.

### Aplicación — `contexts/master_data/application/categorias.py`

| Caso de uso | Qué garantiza |
|---|---|
| `ListarCategorias` | Lectura con los tres roles de siempre; filtro opcional por ámbito |
| `RegistrarCategoria` | RN-02, con el mensaje «Ya existe una categoria con ese nombre en este ambito.» |
| `RenombrarCategoria` | Mismo control de duplicado; el cambio alcanza a todos los elementos por construcción |
| `EliminarCategoria` | Borra la categoría y, en cascada, sus clasificaciones. Audita |
| `ClasificarCliente` / `ClasificarServicio` | RN-01 de HU-E4-04: valida el ámbito antes de asignar. Idempotente: asignar dos veces la misma categoría deja una sola fila |
| `DesclasificarCliente` / `DesclasificarServicio` | Quitar lo que no está no es un error |

**El duplicado se comprueba con una consulta y lo impide un índice único**, exactamente como en
`catalogo-de-clientes` y por el mismo motivo: la consulta es la que puede nombrar el conflicto en el
mensaje, y el índice es el único que no pierde la carrera con una segunda pestaña.

**La unicidad es insensible a mayúsculas.** RN-02 dice «el mismo nombre»; «VIP» y «vip» son el mismo
nombre para cualquiera que mire la lista, y permitir las dos produce dos filas que se ven idénticas.
El índice va sobre `lower(nombre)`.

**Una consecuencia de RN-02 que se acepta y no se corrige:** «VIP» con ámbito `CLIENTE` y «VIP» con
ámbito `AMBOS` **pueden coexistir**, porque el ámbito es distinto y la regla habla de nombre *y*
ámbito. Las dos son asignables a un cliente, así que el combo va a mostrar «VIP» dos veces. Prohibir
los ámbitos que se solapan sería inventar una regla que la historia no tiene; se deja anotado para
que quien lo vea sepa que se miró.

**La asignación es idempotente y el borrado tolerante**, porque HU-E4-04 RN-03 describe la
asignación como inmediata y sin efectos históricos: reintentar un click no es un error de negocio.

### Puertos y adaptadores

- **`PortRepositorioCategoria`**: `agregar`, `guardar`, `eliminar`, `buscar_por_id`,
  `buscar_por_nombre_y_ambito`, `listar`.
- **`PortClasificaciones`**: `asignar_a_cliente`, `quitar_de_cliente`, `categorias_de_cliente`, y
  los tres equivalentes de servicio. Un puerto propio y no un método más en los repositorios de
  cliente y servicio: el enlace no pertenece a ninguno de los dos agregados.

### Otros contextos

**Ninguno.** Todo ocurre dentro de `master_data`.

### Frontend

- **PAN-DM-03**: `app/(panel)/datos-maestros/categorias/page.tsx`, con `ListadoDeCategorias` y su
  formulario. Entrada nueva en la navegación.
- **PAN-DM-01 y PAN-DM-02** ganan dos cosas: un selector de categorías en el formulario —que ofrece
  **sólo las del ámbito correcto**, que es el criterio de aceptación de HU-E4-04— y un filtro por
  categoría en el listado.
- **BFF**: `app/api/categorias/…` y las rutas de clasificación, **con sus tests desde el principio**.
- **El borrado pide confirmación** (criterio de HU-E4-03) con `Button variante="destructivo"`, que ya
  confirma.

---

## Infraestructura

### Migraciones

Una sola, **`0010_categorias.py`**, sobre 0009. Tres tablas.

`categoria_empresa`, con las columnas del DER (`id`, `empresa_id`, `nombre`, `aplica_a`,
`created_at`) y un **índice único funcional** sobre (`empresa_id`, `lower(nombre)`, `aplica_a`).

`cliente_categoria` y `servicio_categoria`, cada una con:

- clave primaria compuesta (`cliente_id`, `categoria_id`) — que es la que hace idempotente la
  asignación en la base y no sólo en el caso de uso;
- **`empresa_id` propia**, y esto es una decisión: la alternativa era una política RLS con un
  `EXISTS` contra la tabla padre, y sería la única política con subconsulta del sistema. Se prefiere
  la columna denormalizada y la **misma** política que las otras doce tablas — una barrera que se
  lee igual en todos lados es una barrera que se revisa bien;
- FKs a los dos padres con **`ON DELETE CASCADE`**, que es RN-03 hecho esquema.

**Los `GRANT` no son los mismos que en 0008 y 0009**: acá `categoria_empresa`,
`cliente_categoria` y `servicio_categoria` conceden **`DELETE`** además de SELECT/INSERT/UPDATE.
La justificación está arriba y se repite en el docstring de la migración, porque un revisor que
llegue a esa línea después de haber leído las dos anteriores va a querer saber por qué cambió.

**Lo que la FK no puede impedir, y sí impide la aplicación.** Una FK se verifica con los permisos
del dueño de la tabla, así que *ve* filas que la RLS esconde: en principio se podría insertar un
enlace entre un cliente de la empresa A y una categoría de la empresa B. Lo que lo impide es que el
caso de uso **lee la categoría por el repositorio antes de asignar**, y ese `SELECT` sí pasa por la
política — una categoría ajena simplemente no aparece, y la asignación falla con «no existe». Hay un
test de integración por ese camino exacto.

### Trabajo asíncrono · Configuración · Integraciones externas

**No aplica** en los tres casos.

---

## Riesgos que obligan a tests

- [ ] Toca dinero — no.
- [ ] Toca comprobantes fiscales / CAE — no.
- [ ] Consume un webhook — no.
- [x] **Agrega datos con `empresa_id`** → aislamiento entre empresas contra PostgreSQL real, en las
      **tres** tablas nuevas, más el caso cruzado de arriba.
- [ ] Usa salida de un LLM — no.
- [ ] Datos personales o fiscales — no: una categoría es una etiqueta del negocio.

---

## Archivos a tocar

### Backend

- [x] `domain/valores.py` — `AmbitoDeCategoria`
- [x] `domain/categoria.py`
- [x] `domain/cliente.py` · `domain/servicio.py` — filtro por categoría
- [x] `application/ports.py` · `application/errors.py`
- [x] `application/categorias.py`
- [x] `infrastructure/models.py` — `CategoriaEmpresaORM` y las dos de enlace
- [x] `infrastructure/repositories.py` · `infrastructure/ensamblado.py`
- [x] `api/routers/categorias.py` · `api/routers/clientes.py` · `api/routers/servicios.py` · `api/main.py`
- [x] `migrations/versions/0010_categorias.py`
- [x] `tests/contexts/master_data/…` · `tests/integracion/…`

### Frontend

- [x] `features/master_data/api/categoria.ts` · `index.ts`
- [x] `features/master_data/components/ListadoDeCategorias.tsx` · `FormularioDeCategoria.tsx`
- [x] `features/master_data/components/SelectorDeCategorias.tsx` — compartido por los dos formularios
- [x] Los cuatro componentes de clientes y servicios, para el selector y el filtro
- [x] `app/(panel)/datos-maestros/categorias/page.tsx` · `app/(panel)/layout.tsx`
- [x] `app/api/categorias/…` y sus tests de ruta
- [x] `shared/componentes.css`

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Nombre duplicado en el mismo ámbito: «Ya existe una categoria con ese nombre en este ambito.» | unit | verde |
| 2 | El duplicado es insensible a mayúsculas: «VIP» y «vip» chocan | unit | verde |
| 3 | El mismo nombre en **otro** ámbito sí se puede | unit | verde |
| 4 | Renombrar a un nombre ya usado en el mismo ámbito se bloquea | unit | verde |
| 5 | Renombrar se refleja en los elementos clasificados, sin tocarlos | integración | verde |
| 6 | Eliminar una categoría en uso deja a los elementos sin esa clasificación y con el resto intacto | integración | verde |
| 7 | Asignar una categoría de ámbito incorrecto se rechaza | unit | verde |
| 8 | `AMBOS` es asignable a clientes **y** a servicios | unit | verde |
| 9 | Un elemento admite varias categorías (RN-02 de HU-E4-04) | integración | verde |
| 10 | Asignar dos veces la misma categoría deja una sola fila | integración | verde |
| 11 | Desasignar algo que no estaba asignado no es un error | unit | verde |
| 12 | **Aislamiento** en las tres tablas nuevas | integración | verde |
| 13 | **No se puede clasificar con una categoría de otra empresa** | integración | verde |
| 14 | Los dos listados filtran por categoría | integración | verde |
| 15 | La aplicación **sí** puede borrar una categoría, y sigue sin poder borrar clientes ni servicios | integración | verde |
| 16 | Cada escritura deja bitácora con `Modulo.MASTER_DATA` | integración | verde |
| 17 | `SOLO_LECTURA` lista y no escribe | unit | verde |
| 18 | PAN-DM-03 lista, crea, edita y pide confirmación al eliminar | frontend | verde |
| 19 | El selector ofrece **sólo** las categorías del ámbito correcto | frontend | verde |
| 20 | Las rutas del BFF rechazan sin sesión | frontend | verde |

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-01 | aprobado |
| 2 · Verificación | 2026-09-01 | presentada — ver abajo |
| 3 · PR | | |

## Verificación — Gate 2 (2026-09-01)

Con PostgreSQL y Redis levantados: **ningún test se salteó**.

| Gate | Comando | Resultado |
|---|---|---|
| Formato Python | `ruff format --check backend` | **verde** — 285 archivos |
| Lint Python | `ruff check backend` | **verde** |
| Tipos | `mypy backend` | **verde** — 285 archivos |
| Arquitectura | `guard_architecture.py --scan .` | **verde** — 312 archivos |
| Tests Python | `pytest backend` | **verde** — **798 pasan, 0 salteados** |
| Cobertura Python | `--cov=cheatsheet` | **89.99 %** |
| Typecheck y lint frontend | `npm run typecheck` · `npm run lint` | **verde** |
| Tests frontend | `npm run test:coverage` | **verde** — 333 pasan · 85.41 % líneas · 82.01 % funciones |

Módulos de la unidad: `application/categorias.py` 94 %, `domain/categoria.py` 96 %,
`infrastructure/categorias.py` 80 %, `api/routers/categorias.py` 78 %.

## Lo que los tests encontraron

**Un 204 anotado `-> None` rompe la aplicación entera.** El `DELETE` de categorías es el
primero de la API, y su primera versión hizo fallar **6 tests y 81 errores, ninguno en el
archivo culpable**: con `from __future__ import annotations` —que tienen todos los módulos—
FastAPI recibe la anotación como el string `"None"`, la resuelve a `NoneType`, que es una
clase y por lo tanto *truthy*, y afirma que un 204 no puede tener response model. La app no
se construye. Resuelto con `response_model=None` y un comentario que lo explica donde
alguien lo va a leer.

**Y un defecto en código ya mergeado, que esta unidad esquivó en vez de heredar.** Al
escribir el test del BFF se ve que `respuestaDeError` reenvía `detalle` **sólo** para
`EntradaInvalida`, y que `leerFalla` descarta cualquier campo extra. Consecuencia: el
`cliente_existente_id` que `catalogo-de-clientes` se tomó el trabajo de devolver **nunca
llega al navegador**, y el mensaje de duplicado tampoco — o sea que «ofrece ver el
duplicado» de HU-E4-01 no se cumple de punta a punta. Por eso `CategoriaDuplicada` se
declaró `EntradaInvalida` (422) y no `InvarianteViolada` (409): es la única forma de que el
mensaje de RN-02 llegue a la pantalla sin tocar la política del BFF, que es de otra unidad.
Queda en [`TODO.md`](../TODO.md) §10.

**La cobertura de funciones del frontend cruzó el umbral hacia abajo**, por la razón que
esta misma unidad había anotado dos veces: ninguna `page.tsx` del repo tenía test. Se
escribió el primero del proyecto — cubre las tres pantallas de Datos Maestros y prueba el
redirect sin sesión y el mapeo de rol a `puedeEditar`, que es lógica real y no relleno.

## Desvíos del plan

1. **Apareció `VerClasificacion`**, un caso de uso de lectura que el plan no listaba. Hace
   falta porque las casillas del selector tienen que abrir ya tildadas, y para eso el
   estado se necesita **antes** de tocar nada; `ClasificarCliente` devuelve el conjunto
   nuevo, que es la otra mitad.
2. **`categorias.py` se separó de `repositories.py`** en `infrastructure/`. Ese archivo ya
   tenía dos agregados y 237 líneas, y `CLAUDE.md` §5 corta en 400.
3. **La etiqueta del filtro de PAN-DM-03 pasó a «Filtrar por ámbito»**, porque decía lo
   mismo que el campo del formulario. Lo encontró un test que no sabía cuál de los dos
   elegir — y si un test no puede distinguirlos, un lector de pantalla tampoco.

## Decisiones tomadas durante la unidad

- 2026-09-01 · ¿Se arranca sobre una rama sin mergear? → **Sí**, cortando de
  `feature/master_data-catalogo-de-servicios` y declarando la asunción (regla 1c). Dejó de importar
  el mismo día: #25 se mergeó y la rama se sincronizó con `develop` antes de escribir código.
- 2026-09-01 · ¿`categoria_empresa` concede `DELETE`? → **Sí**, y es la única de las tres tablas de
  `master_data` que lo hace. RN-03 lo pide y nada fuera del contexto la referencia.
- 2026-09-01 · ¿La unicidad distingue mayúsculas? → **No.** «VIP» y «vip» son el mismo nombre.
- 2026-09-01 · ¿Las tablas de enlace llevan `empresa_id`? → **Sí**, para que la política RLS sea la
  misma que en las otras doce tablas y no la única con subconsulta.
