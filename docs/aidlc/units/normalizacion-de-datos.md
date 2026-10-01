# Unidad: normalizacion-de-datos

**HUs**: HU-E4-05 (nueva), HU-E4-01, HU-E3-03, HU-E3-04, HU-E3-07 (modificadas por ADR-0009)   **Contexto dueño**: master_data (sin edges nuevos: `spreadsheet_sync` y `conversational` ya llegan por su capa de aplicación)   **Rama**: feature/master_data-normalizacion-de-datos

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D85 (`docs/aidlc/units.md:438-465`). La rama sale de `feature/master_data-duracion-de-servicios`
> (cadena: #45 → `turnos-no-en-el-pasado` → `duracion-de-servicios`); su PR apunta a esa rama.
>
> **Base de la rama, revisada.** Funcionalmente esta unidad no depende de ninguna de las dos anteriores:
> `turnos-no-en-el-pasado` es de `scheduling` y no toca nada de acá. Pero `duracion-de-servicios`
> modificó **los mismos archivos** que esta unidad tiene que tocar: `master_data/application/ingesta.py`
> (+41 líneas), `master_data/domain/servicio.py` (+28) y `tests/.../test_ingesta.py` (+88)
> (`git diff --stat feature/infra-ajustes-de-la-revision...HEAD`). Sacarla de #45 directo obligaría a
> resolver esos conflictos a mano al integrar. **Recomendación: quedarse sobre la unidad 2.** La unidad 1
> viene de arrastre y no molesta.
>
> **Tamaño**: lo que pide D85 completo es L. Se propone partirla (pregunta P1): **esta unidad** hace la
> normalización en las tres entradas y la comparación en la resincronización (sin migración, sin
> frontend); la corrección de datos existentes (HU-E4-05 RN-09) pasa a una unidad nueva,
> `correccion-de-datos-existentes`, que es la única que necesita migración y pantalla.

## Qué hace

Hoy `Cliente`, `Servicio` y `CategoriaEmpresa` guardan el nombre como llega, con solo un `strip()`
(`cliente.py:138-144`, `servicio.py:202-208`, `categoria.py:110-116`). Eso deja duplicados aparentes,
espacios dobles, caracteres invisibles pegados desde una planilla y nombres en mayúsculas sostenidas.
Además, la ingesta pisa el registro aunque la fila no haya cambiado (`ingesta.py:93-103`), así que una
diferencia de mayúsculas es un «cambio».

Esta unidad:

1. agrega un **normalizador de dominio** de `master_data` (funciones puras, idempotentes) con las reglas
   RN-01 a RN-04 de HU-E4-05;
2. lo aplica **dentro de los agregados**, que son el punto de entrada común: panel, planilla y agente
   pasan por `Cliente.registrar/renombrar`, `Servicio.registrar/renombrar` y
   `CategoriaEmpresa.registrar/renombrar`, así que se normaliza una sola vez y en un solo lugar (RN-07);
3. hace que la ingesta **no toque** un cliente cuando la fila, normalizada, coincide con lo almacenado
   normalizado (HU-E3-04 RN-04 y HU-E4-05 RN-08), y por eso tampoco lo vuelve a escribir en la hoja propia
   (HU-E3-07);
4. evalúa la unicidad de categoría sobre el nombre normalizado (HU-E4-05 RN-04) y deja probada la de CUIT
   sobre el CUIT normalizado (HU-E4-01 RN-05), que ya rige.

### Lo que las historias piden, textual

**HU-E4-05** (`docs/aidlc/inputs/historias-de-usuario.md:822-866`):
- RN-01: «se eliminan espacios al inicio y al final, se colapsan los espacios internos repetidos en uno y
  se descartan caracteres de control e invisibles. No se agregan ni se quitan tildes.»
- RN-02: «se capitaliza cada palabra, salvo las partículas de, del, la, las, los, y, e, que van en
  minúscula excepto al inicio. Una palabra se capitaliza solo si viene completamente en mayúsculas o
  completamente en minúsculas. Las que tienen mayúsculas mezcladas (por ejemplo “McDonald”) se preservan.»
- RN-03: «las siglas societarias (S.A., S.R.L., S.A.S., SAS, S.A.U., S.C.A. y equivalentes) se conservan
  en mayúsculas tal como fueron escritas, con o sin puntos. El resto se capitaliza como en RN-02. Las
  palabras totalmente en mayúsculas de hasta 4 letras se conservan por suponerse siglas propias (IBM,
  YPF), lo que acepta falsos positivos como “SUR”. Un cliente se trata como razón social cuando su CUIT
  empieza con 30, 33 o 34; en otro caso, como persona.»
- RN-04: «solo cuando el texto viene todo en mayúsculas o todo en minúsculas, se deja la primera letra en
  mayúscula y el resto en minúscula. La unicidad de categoría (HU-E4-03 RN-02) se evalúa sobre el valor
  normalizado, sin distinguir mayúsculas.»
- RN-05: «email en minúsculas y sin espacios; WhatsApp solo dígitos, de 8 a 15; CUIT en 11 dígitos,
  mostrado como XX-XXXXXXXX-X» — «ya vigentes, se citan y no se rehacen».
- RN-06: «los textos libres (FAQ, descripciones de cobro o de ítem, mensajes) solo reciben RN-01. Los
  comprobantes ya emitidos nunca se modifican».
- RN-07: «es idempotente … y se aplica una sola vez, en el punto de entrada común de datos maestros …
  Los demás contextos la usan a través de la capa de aplicación de Datos Maestros.»
- RN-08: «la planilla original de la empresa nunca se reescribe … En la resincronización se compara el
  valor normalizado de la planilla con el almacenado».
- RN-09: corrección única de datos existentes (dry-run, respaldo restaurable, no toca comprobantes ni
  hojas, colisiones informadas y no cambiadas, bitácora con conteos) → **propuesta para otra unidad (P1)**.
- Criterios: «JUAN CARLOS DE LA CRUZ» → «Juan Carlos de la Cruz»; CUIT 30-… con «ferreteria lopez
  s.r.l.» → «Ferreteria Lopez S.R.L.»; «  Ana   Perez » → «Ana Perez»; «Ana@Mail.COM» → «ana@mail.com»;
  «+54 9 11 1234-5678» → solo dígitos; el agente crea «maria gomez» → «Maria Gomez»; la planilla trae
  «MARIA GOMEZ» y el catálogo tiene «Maria Gomez» → «la resincronización no registra cambio y la planilla
  queda intacta»; categoría «VIP» con «Vip» existente → «Ya existe una categoría con ese nombre en este
  ámbito.»; la corrección de datos existentes (RN-09).

**HU-E4-01 RN-05** (`:710`): «Nombre, email, WhatsApp y CUIT se guardan normalizados según HU-E4-05. La
unicidad de CUIT (RN-03) se evalúa sobre el CUIT normalizado.» Criterio: «Creo un cliente con el CUIT
“20-12345678-9” y ya existe el mismo CUIT en dígitos → “Ya existe un cliente con ese CUIT.”»

**HU-E3-03 RN-04** (`:537`): «Los valores de cada fila se normalizan según HU-E4-05 antes de guardarse en
el catálogo. La planilla original no se modifica.» Criterio: «Una fila trae el nombre “MARIA DE LOS
ANGELES perez  ” → se guarda con el formato normalizado y la planilla original queda intacta».

**HU-E3-04 RN-04** (`:573`): «compara el valor normalizado (HU-E4-05) de la planilla con el valor
normalizado almacenado. Una diferencia que desaparece al normalizar no se considera un cambio.» Criterio:
«Una celda cambia solo en mayúsculas o espacios respecto de lo almacenado → el sistema no registra cambio
ni actualiza el registro».

**HU-E3-07** (`:679`), criterio nuevo: «Un registro de planilla se normaliza al guardarse → la versión
normalizada no se escribe sobre la hoja original ni se reescribe el registro (RN-02 y RN-03)».

## Lo que ya existe (se cita, no se rehace) y el hueco

| Regla | Estado hoy | Evidencia | Hueco |
|---|---|---|---|
| Email en minúsculas (RN-05) | Vigente | `shared/contacto.py:46` (`strip().lower()`; un espacio interno no pasa el regex de `:30`) | Ninguno: test de caracterización |
| WhatsApp solo dígitos, 8 a 15 (RN-05) | Vigente | `shared/contacto.py:73-78` | Ninguno: test de caracterización |
| CUIT en 11 dígitos (RN-05) | Vigente | `shared/fiscal.py:80` | Ninguno |
| CUIT mostrado XX-XXXXXXXX-X (RN-05) | Vigente | `shared/fiscal.py:88` (`formateado`), usado en `api/routers/clientes.py:121` | Ninguno |
| Unicidad de CUIT sobre el normalizado (HU-E4-01 RN-03/RN-05) | Vigente | índice parcial `0008_cliente.py:89-95`; `_exigir_cuit_libre` compara dígitos (`master_data/infrastructure/repositories.py:121-127`); mensaje `:41` | Solo falta el test del criterio con guiones |
| Unicidad de categoría sin distinguir mayúsculas | Vigente **a medias** | índice `(empresa_id, lower(nombre), aplica_a)` (`0010_categorias.py:89-90`); búsqueda `strip().lower()` (`master_data/infrastructure/categorias.py:106`) sobre el texto **crudo** que manda la aplicación (`application/categorias.py:164`) | «VIP  GOLD» (espacio doble) no encuentra «Vip gold»: pasa la búsqueda y choca con el índice → **500**, porque el `IntegrityError` de `categoria_empresa` no se traduce (solo `repositories.py:138` lo hace, para `cliente`) |
| Nombres: limpieza y mayúsculas (RN-01 a RN-04) | **No existe** | `cliente.py:138-144`, `servicio.py:202-208`, `categoria.py:110-116`: solo `strip()` | Todo el normalizador |
| Agente pasa por la aplicación (RN-07) | Vigente | `conversational/infrastructure/acl.py:200-217` llama a `RegistrarCliente` con `origen=AGENTE` | Se normaliza solo, al estar en el agregado |
| Planilla pasa por la aplicación (RN-07) | Vigente | `spreadsheet_sync/infrastructure/catalogo.py:19-63` → `IngerirClienteDesdePlanilla` / `IngerirServicioDesdePlanilla` | Idem |
| Sin falsos cambios en la resincronización (HU-E3-04 RN-04) | **No existe** | `ingesta.py:93-103` siempre llama `renombrar` + `actualizar_contacto` + `guardar`, que mueven `actualizado_en` | Comparación normalizada y «no tocar» |
| La planilla original nunca se escribe (HU-E3-07 RN-02/RN-03) | Vigente | `ProcesarPlanilla` no tiene puerto de escritura (`spreadsheet_sync/application/procesamientos.py:90-140`); write-back solo en hoja propia (`sincronizacion.py:172-175`) y solo `PANEL`/`AGENTE` (`ingesta.py:288`) | Falta el test del criterio nuevo, y que un `PANEL` sin cambios reales no vuelva a la hoja propia (hoy sí vuelve: `ingesta.py:311` filtra por `actualizado_en`, que la ingesta movió) |
| Comprobantes emitidos intactos (RN-06) | Vigente por diseño | `billing` toma la razón social **del padrón**, no del catálogo (`billing/application/emision.py:112-113`), y el comprobante la desnormaliza | Ninguno |

### Hallazgos

1. **hallazgo — editar un cliente normaliza con el CUIT viejo.** `EditarCliente` llama a `renombrar`
   (`application/clientes.py:293`) **antes** de `actualizar_datos_fiscales` (`:294-296`). Si en la misma
   edición se carga un CUIT 30-…, el nombre se trataría como persona. Se corrige invirtiendo el orden (sin
   líneas nuevas: el archivo tiene 392).
2. **hallazgo — `_condicion_iva` no colapsa espacios internos.** `ingesta.py:171` hace
   `strip().upper().replace(" ", "_")`: «Responsable  Inscripto» (doble espacio) queda en `None`. Es un
   campo de texto de la fila y RN-01 aplica a todos: se limpia con RN-01 antes de mapear. **Este es el
   único punto de contacto con `IVA_NO_ALCANZADO`** (ver «Coordinación con la unidad 5»).
3. **hallazgo, fuera de alcance (se reporta) — un cliente de planilla sin CUIT se duplica en cada
   reproceso.** La ingesta solo busca por CUIT (`ingesta.py:92`); sin CUIT siempre crea (`:105-118`).
   El criterio «MARIA GOMEZ vs Maria Gomez» no dice si hay CUIT. Ver P6.
4. **hallazgo, contexto — la lectura incremental de la hoja viva no existe.** `workers/tasks_spreadsheet.py:220`
   («Reading the live sheet is not here yet») y `TODO.md` §15.1. Por eso la comparación de HU-E3-04 RN-04
   se implementa **en la ingesta** (`IngerirClienteDesdePlanilla`), que es lo que va a llamar la lectura
   viva cuando exista; hoy se ejercita con la carga y el reproceso. Los dos criterios de lectura de HU-E3-04
   siguen abiertos y no son de esta unidad.
5. **hallazgo menor, fuera de alcance — `categoria_empresa` no traduce su `IntegrityError`** (ver tabla).
   Con la búsqueda normalizada de esta unidad el caso de los espacios desaparece; queda solo la carrera de
   dos pestañas, que ya existía. Se anota en `TODO.md`.
6. **Límites de tamaño a la vista**: `application/clientes.py` y `application/categorias.py` tienen 392
   líneas cada uno; `spreadsheet_sync/application/mapeos.py` ya tiene 425 (preexistente, no se toca);
   `frontend/.../ListadoDeClientes.tsx` 395; los tests `test_categorias.py` (591) y `test_clientes.py` (445)
   ya pasan de 400. **Esta unidad no agrega líneas netas a los dos primeros y escribe sus tests en archivos
   nuevos.**

## Coordinación con la unidad 5 (`tipos-de-comprobante-por-receptor`) sobre `IVA_NO_ALCANZADO`

Leído del plan de la unidad 5 en `feature/billing-tipos-de-comprobante-por-receptor`
(`docs/aidlc/units/tipos-de-comprobante-por-receptor.md`, «Diseño» y «Bloque de radio de explosión»):

| Pieza | Dueña | Qué hace esta unidad |
|---|---|---|
| `CondicionIVA.IVA_NO_ALCANZADO` en `shared/fiscal.py` | **unidad 5** | Nada. No agrega el miembro ni lo usa en tests |
| Test «“IVA No Alcanzado” de una planilla queda como el valor nuevo» (su caso 27, en `test_ingesta.py`) | **unidad 5** | Nada. Su test pasa por `_condicion_iva` |
| Limpieza RN-01 del texto de la condición antes de mapear (`ingesta.py:164-173`) | **esta unidad** | Cambia 1-2 líneas de `_condicion_iva` y lo prueba con valores **que ya existen** («  responsable   inscripto » → `RESPONSABLE_INSCRIPTO`) |
| Opción «IVA No Alcanzado» en `FormularioDeCliente.tsx` | **unidad 5** | Nada: esta unidad no toca el frontend |
| `cliente.condicion_iva_confirmada_en` (bloque B de la unidad 5) | **unidad 5 / su bloque B** | Nada |

**Consecuencia**: las dos unidades son independientes y pueden mergearse en cualquier orden. Cuando
ambas estén, «IVA  No  Alcanzado» (con espacios de más) también se reconoce, sin que ninguna lo pruebe
contra la otra. El único conflicto textual posible es que las dos agregan tests al final de
`test_ingesta.py`; para evitarlo, los de esta unidad van en un archivo nuevo
(`test_ingesta_normalizada.py`). **Hay que avisarlo en el plan de la unidad 5** (una línea en su
«Bloque de radio de explosión»), no se edita desde acá.

## Las preguntas que el mapa dejó para este Gate (D85)

**«Dónde vive el normalizador y cómo se cablean las tres entradas.»** En `master_data/domain/normalizacion.py`,
funciones puras sin dependencias; lo llaman los tres agregados al construir o renombrar. Las tres entradas
ya convergen en esos agregados por la capa de aplicación (tabla de arriba), así que **no hay cableado
nuevo**: panel (`RegistrarCliente`/`EditarCliente`, servicios, categorías), planilla
(`IngerirClienteDesdePlanilla`/`IngerirServicioDesdePlanilla`) y agente (`DirectorioViaMasterData` →
`RegistrarCliente`). Ningún otro contexto importa el normalizador. No va a `shared/`: un solo contexto lo
usa («never in anticipation», `shared/fiscal.py:109-110`).

**«La unicidad de categoría y de CUIT pasa a evaluarse sobre el valor normalizado; el índice único actual
de categoría hay que revisarlo.»** Revisado: **el índice `lower(nombre)` alcanza y no cambia.** Como todo
nombre se guarda ya colapsado y limpio, `lower()` sobre el valor guardado es exactamente «el normalizado
sin distinguir mayúsculas». Lo que cambia es la búsqueda previa (`_exigir_nombre_libre`), que pasa a
recibir el nombre normalizado. El de CUIT ya compara dígitos (tabla). **Sin migración.**

**«La corrección única de datos existentes.»** Ver P1: se propone como unidad aparte, con su diseño
preliminar al final.

## Preguntas (con recomendación; P1 y P6 necesitan a una persona, el resto se puede aprobar en bloque)

### P1. ¿Se parte la unidad? (alcance)
Lo que pide D85 suma: normalizador + tres agregados + resincronización sin falsos cambios + unicidad
(**esta unidad**, ~650 líneas con tests, sin migración ni frontend) **más** la corrección de datos
existentes de RN-09: tabla de respaldo con RLS y migración, informe dry-run, aplicación transaccional,
restauración, informe de colisiones, bitácora, API solo-Administrador y una sección en PAN-DM-01
(~700 líneas más, backend + frontend + migración).
- **A (recomendada)**: partir. Esta unidad = puntos 1-4 de «Qué hace». Unidad nueva
  `correccion-de-datos-existentes` (master_data, HU-E4-05 RN-09, depende de `normalizacion-de-datos`).
  Se actualiza `units.md` **antes** de implementar (regla «no cabe en una unidad»).
- B: todo en una. Un PR de ~1.350 líneas que mezcla una regla de dominio con una operación masiva sobre
  datos reales.

**Razón**: son dos riesgos distintos. La normalización es una función pura con tests exhaustivos; la
corrección es una escritura masiva con respaldo, que es el riesgo dominante de este dominio («datos
sucios; nunca borrar»). Separarlas deja revisar la segunda con calma y con la primera ya probada (la
corrección **usa** el normalizador). Además, la corrección es la única que necesita migración, lo que
saca a esta unidad del problema de numeración (ver Infraestructura).

### P2. Partículas frente a «hasta 4 letras en mayúsculas» en razón social
RN-03 dice que las palabras en mayúsculas de hasta 4 letras se conservan, y «el resto se capitaliza como
en RN-02» (que pone las partículas en minúscula). Leído literal, «FERRETERIA DE LA COSTA SA» daría
«Ferreteria DE LA Costa SA».
- **A (recomendada)**: las partículas `de, del, la, las, los, y, e` ganan, salvo al inicio: «Ferreteria de
  la Costa SA». La regla de 4 letras se aplica al resto («YPF», «IBM», «SUR»).
- B: literal; «DE» y «LA» quedan en mayúsculas.

**Razón**: la lista de partículas es cerrada y explícita; la de 4 letras es una heurística que la propia
historia admite que se equivoca (D85: «Lo que se paga: falsos positivos de siglas»). Sumar a esos falsos
positivos las partículas no lo pide nadie.
Corolario (sin pregunta aparte): la regla de partículas se aplica **solo a palabras que se están
capitalizando** (todo mayúsculas o todo minúsculas). Una «De» escrita así se preserva, igual que
«McDonald», porque RN-02 preserva lo que viene con mayúsculas mezcladas.

### P3. La lista cerrada de «siglas societarias y equivalentes»
- **Recomendada**: constante con, sin puntos y comparando sin distinguir mayúsculas: `SA, SRL, SAS, SAU,
  SCA, SCS, SH, SGR, SAIC, SACI, SACIF, SAICF, SAICA, SRLU`. Cualquiera de ellas, escrita **con** puntos
  (`s.r.l.`) o sin (`srl`), se pasa a mayúsculas conservando los puntos tal como vinieron («S.R.L.»,
  «SRL»). Se excluyen a propósito **sin puntos** las que son palabras del castellano («SE», «SC»): solo
  cuentan si vienen con puntos («S.E.», «S.C.»).

**Razón**: «y equivalentes» no es implementable; una lista en una constante, con su test, sí, y crecerla
es una línea. Las tipologías salen de la Ley General de Sociedades 19.550 y de las SAS (Ley 27.349);
**no verifiqué una fuente primaria en esta sesión** y la lista queda a validar por el equipo.

### P4. Guion, apóstrofo y representación Unicode
- **Recomendada**: (a) dentro de una palabra que se capitaliza, la letra después de `-` o `'` también va
  en mayúscula («MARIA-JOSE» → «Maria-Jose», «O'BRIEN» → «O'Brien»); (b) RN-01 incluye pasar el texto a
  **NFC**; (c) todo espacio Unicode (tab, salto de línea, espacio duro U+00A0) cuenta como espacio y se
  colapsa; el resto de los caracteres de control (`Cc`) y de formato (`Cf`: U+200B, U+FEFF, U+00AD…) se
  descarta.

**Razón**: (a) sin esto, «O'brien» es peor que lo que entró; (b) NFC no agrega ni quita tildes (RN-01),
solo unifica cómo se codifica la misma «á», y sin eso dos «María» iguales a la vista son dos textos
distintos, que es el duplicado aparente que la historia quiere evitar; (c) un tab entre dos palabras
tiene que separarlas, no pegarlas. Las tres son idempotentes.

### P5. RN-06: ¿esta unidad limpia los textos libres de otros contextos?
RN-06 dice que FAQ, descripciones de cobro o de ítem y mensajes «solo reciben RN-01», bajo el título
«fuera de alcance».
- **A (recomendada)**: no en esta unidad. HU-E4-05 es una regla sobre Cliente, Servicio y CategoríaEmpresa
  (su «Acción Bloque K»); `master_data` no tiene textos libres (verificado: `Servicio` no tiene
  descripción). Limpiar mensajes de WhatsApp o conceptos de cobro tocaría `conversational`, `payments` y
  `billing` y alteraría contenido que el usuario escribió. Se anota en `TODO.md` como «sin unidad».
- B: aplicar RN-01 acá también a `cobro.concepto` e ítems de comprobante (otros contextos, otro PR).

### P6. Clientes de planilla **sin** CUIT en la resincronización
La ingesta identifica a un cliente solo por CUIT (`ingesta.py:92`). Sin CUIT, cada reproceso crea otro
(hallazgo 3).
- **A (recomendada)**: el criterio «MARIA GOMEZ vs Maria Gomez» se prueba **con CUIT**, que es la única
  identidad que hoy existe; la identidad de un cliente sin CUIT (por `referencia_fila_planilla`, que ya
  está en el modelo y nadie escribe, `domain/cliente.py:49`) se decide con la lectura incremental viva
  (`TODO.md` §15.1), que es quien la necesita. Se anota como hallazgo sin unidad.
- B: resolverlo acá escribiendo y buscando por `referencia_fila_planilla`. Es una decisión de identidad
  que cambia la ingesta entera y no la pide HU-E4-05.

## Diseño

### Dominio — `contexts/master_data/domain/`
- **Nuevo `normalizacion.py`** (~150 líneas), funciones puras sobre `str`, sin `datetime` ni I/O:
  - `limpiar_texto(texto) -> str` — RN-01 (+P4 b/c): NFC, espacios Unicode → espacio, descarta `Cc`/`Cf`,
    colapsa y recorta.
  - `normalizar_nombre_de_persona(texto) -> str` — RN-01 + RN-02 (+P2 corolario, P4 a).
  - `normalizar_razon_social(texto) -> str` — RN-01 + RN-03 (+P2, P3).
  - `normalizar_nombre_de_cliente(texto, cuit: CUIT | None) -> str` — elige por prefijo
    `{"30", "33", "34"}`; sin CUIT, persona.
  - `normalizar_nombre_de_catalogo(texto) -> str` — RN-01 + RN-04 (servicio y categoría).
  - Constantes `PARTICULAS`, `SIGLAS_SOCIETARIAS`, `PREFIJOS_DE_RAZON_SOCIAL`, `LARGO_MAXIMO_SIGLA = 4`.
  - Palabra = secuencia separada por un espacio. «Todo mayúsculas / todo minúsculas» se mide sobre las
    letras con caja; una palabra sin letras («1234», «-») no cambia.
- `cliente.py`: `_nombre_valido(nombre, cuit)` = `normalizar_nombre_de_cliente` y luego las validaciones
  de vacío y largo (que ya existen) sobre el resultado. `registrar` pasa su `cuit`; `renombrar` usa
  `self.cuit`. Un nombre hecho solo de invisibles queda vacío → «El nombre del cliente es obligatorio».
- `servicio.py` y `categoria.py`: `_nombre_valido` usa `normalizar_nombre_de_catalogo`.
- `categoria.py`: `clave_de_unicidad` (`:119`, hoy sin uso) pasa a ser `normalizar_nombre_de_catalogo(…).lower()`,
  y es lo que usa la aplicación para preguntar por duplicados.
- Sin eventos nuevos. `OrigenDato` no cambia.

### Aplicación — `contexts/master_data/application/`
- `clientes.py` — `EditarCliente`: se invierte el orden: primero `actualizar_datos_fiscales`, después
  `renombrar` (hallazgo 1). Cero líneas netas.
- `categorias.py` — `_exigir_nombre_libre` busca por el nombre normalizado
  (`normalizar_nombre_de_catalogo(nombre)`). +1/2 líneas (queda ≤ 394).
- `ingesta.py` — `IngerirClienteDesdePlanilla`:
  - construye el nombre normalizado con el CUIT de la fila y los value objects de contacto;
  - si existe por CUIT, compara **normalizado contra normalizado**: `normalizar_nombre_de_cliente(fila)`
    vs `normalizar_nombre_de_cliente(existente.nombre, existente.cuit)` (el almacenado puede ser previo a
    esta unidad: RN-04 de HU-E3-04 dice «valor normalizado almacenado»), y `Telefono`/`Email` por
    igualdad de value object;
  - **sin diferencias**: no llama a `renombrar` ni a `actualizar_contacto`; si `presente_en_planilla` ya
    era `True`, **no guarda**; si era `False`, lo marca y guarda sin mover `actualizado_en`;
  - con diferencias: como hoy (renombra, actualiza contacto, guarda);
  - `ResultadoDeIngesta` gana `modificado: bool` (default `True`, para no romper a quien lo construye).
  - `_condicion_iva` limpia con `limpiar_texto` antes de `upper().replace(" ", "_")` (hallazgo 2).
  - `IngerirServicioDesdePlanilla`: sin cambios de código; normaliza el agregado. **No hay «sin cambios»
    para servicios**: la ingesta nunca busca un servicio existente (`ingesta.py:121-136`, decisión de
    épico 3), así que la comparación de HU-E3-04 no tiene contra qué hacerse. Se dice en el docstring.
  - Tamaño estimado de `ingesta.py`: 326 → ~365. Si pasara de 400, la comparación sale a
    `application/comparacion.py`.
- `ListarClientesParaEscrituraDeVuelta`: sin cambios. El criterio de HU-E3-07 se cumple porque `PLANILLA`
  se excluye (`:288`) y porque un cliente `PANEL` sin cambios reales ya no mueve `actualizado_en`.

### Puertos y adaptadores
No aplica: ningún puerto nuevo. `PortRepositorioCategoria.buscar_por_nombre_y_ambito` mantiene su firma y
su `strip().lower()` (`infrastructure/categorias.py:106`), que con un argumento ya normalizado es idempotente.

### Otros contextos
- `spreadsheet_sync`: sin cambios de código. Llega por `infrastructure/catalogo.py` (edge existente,
  Context Map §4 `spreadsheet_sync → master_data`).
- `conversational`: sin cambios de código. Llega por `DirectorioViaMasterData` → `RegistrarCliente`
  (edge existente `master_data → conversational`, C/S). El nombre provisorio «WhatsApp 1234»
  (`conversational/application/agente.py:205-207`) tiene mayúsculas mezcladas y **se preserva**.
- `billing`: no afectado. La razón social del comprobante sale del padrón (`emision.py:112-113`), no del
  catálogo; los emitidos están desnormalizados (RN-06).
- `identity`: no afectado (`Empresa.razon_social` no es del catálogo).
- **Sin ADR**: ningún edge nuevo, ningún agregado cambia de contexto.

### Frontend
No aplica en esta unidad. Las pantallas PAN-DM-01/02/03 y PAN-ING-01 ya muestran lo que devuelve la API,
que pasa a venir normalizado; el CUIT ya se muestra formateado (`api/routers/clientes.py:121`). No se
agrega «vista previa» del nombre normalizado: ninguna historia la pide.

## Infraestructura

- **Migraciones**: **no aplica en esta unidad** (con P1 = A). Ningún índice cambia (ver «Las preguntas
  que el mapa dejó»).
  **El problema de numeración, dicho explícitamente** (afecta a `correccion-de-datos-existentes` y a
  las unidades paralelas): los identificadores de Alembic de este repo son los números (`revision =
  "0025"`, `down_revision = "0024"`, `0025_servicio_duracion_en_rango.py:34-35`). Hoy, en ramas vivas:
  - `0025` — `duracion-de-servicios` (esta cadena).
  - `0026` — **dos veces**: `0026_fecha_medio_y_operacion_de_pago.py` (cadena de cobros, ya commiteada)
    y `0026_comprobante_condicion_del_receptor.py` (planeada en la unidad 5, que ya anota renumerar).
  - `0027` — `reembolsos` (cadena de cobros).
  - `limites-e-intervalo-de-turnos` (unidad 7) sale de la unidad 1, cuya cabeza es la `0024`: si necesita
    migración (el hueco entre turnos de ADR-0009), la tomaría como `0025` y **chocaría** con
    `duracion-de-servicios`. Su plan ya la numera `0028` (con `down_revision = "0024"` a re-apuntar al
    rebasar).
  Dos archivos con el mismo `revision`, o dos con el mismo `down_revision`, rompen `alembic upgrade head`
  al juntarse las cadenas en `develop`.
  **Recomendación**: reservar números en una nota de `units.md` y fijar el `down_revision` al rebasar
  sobre `develop`: `0028` unidad 7 (ya planificada así), `0029` unidad 5 (renumera su `0026`), **`0030`
  `correccion-de-datos-existentes`**. El número es una etiqueta; lo que importa es que la cadena sea
  lineal al integrar, y eso se verifica con `alembic heads` (una sola cabeza) antes de cada PR.
  Si P1 = B, la migración es de esta unidad y lleva el `0030`.
- **Trabajo asíncrono**: no cambia. La ingesta sigue en el worker `spreadsheet_processing`; no hay
  tareas nuevas.
- **Configuración**: no aplica; ningún `.env.example` cambia.
- **Integraciones externas**: no aplica. Ninguna llamada nueva a ARCA, Google ni al LLM. El nombre que el
  agente propone pasa por el agregado como cualquier otro (el nombre provisorio no sale de un LLM).

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero → no aplica (precio de servicio no cambia)
- [ ] Toca comprobantes fiscales / CAE → no aplica; test de que `billing` no lee el catálogo para el nombre no hace falta: ya está probado por su propia unidad
- [ ] Consume un webhook → no aplica
- [x] Datos con `empresa_id` → no agrega tablas; el test de PostgreSQL de unicidad de categoría corre bajo RLS (dos empresas pueden tener «Vip» cada una)
- [ ] Usa salida de un LLM → no aplica
- [x] Datos personales → **tests con nombres y CUIT ficticios** (CUIT de prueba con dígito verificador válido, como `30-71234567-1` que ya usan los tests de `identity`); ningún dato real; nada se envía a un LLM

Riesgos que no son tests, dichos con todas las letras:
- **Falsos positivos aceptados por la historia**: «SUR», «RIO», «SOL» en una razón social quedan en
  mayúsculas; las tildes nunca se agregan («Maria» no pasa a «María»).
- **La normalización cambia lo que el usuario ve al guardar.** Quien escriba «JUAN PEREZ» verá «Juan
  Perez». Es lo pedido; se anota para la demo.
- **Datos viejos sin normalizar conviven con los nuevos** hasta la corrección de RN-09. La comparación de
  la resincronización normaliza **los dos lados**, así que no genera falsos cambios contra filas viejas;
  pero el listado puede mostrar «JUAN PEREZ» (viejo) junto a «Juan Perez» (nuevo) hasta entonces.
- **Re-normalizar al renombrar** un cliente viejo lo normaliza (es la vía natural de corrección por
  edición).
- **Idempotencia**: sin `hypothesis` en `requirements-dev.txt`; se prueba con un corpus parametrizado
  (todos los casos de los tests aplicados dos veces). No se agrega dependencia.

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/normalizacion.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/cliente.py` (`_nombre_valido`, `registrar`, `renombrar`)
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/servicio.py` (`_nombre_valido`)
- [ ] `backend/src/cheatsheet/contexts/master_data/domain/categoria.py` (`_nombre_valido`, `clave_de_unicidad`)
- [ ] `backend/src/cheatsheet/contexts/master_data/application/clientes.py` (orden en `EditarCliente`)
- [ ] `backend/src/cheatsheet/contexts/master_data/application/categorias.py` (`_exigir_nombre_libre`)
- [ ] `backend/src/cheatsheet/contexts/master_data/application/ingesta.py` (comparación, `ResultadoDeIngesta.modificado`, `_condicion_iva`)
- [ ] `backend/tests/contexts/master_data/domain/test_normalizacion.py` (nuevo)
- [ ] `backend/tests/contexts/master_data/domain/test_cliente.py`, `test_servicio.py`, `test_categoria.py`
- [ ] `backend/tests/contexts/master_data/application/test_normalizacion_en_el_panel.py` (nuevo: clientes y categorías; los archivos actuales pasan de 400)
- [ ] `backend/tests/contexts/master_data/application/test_ingesta_normalizada.py` (nuevo)
- [ ] `backend/tests/contexts/conversational/infrastructure/test_directorio_via_master_data.py` (nuevo)
- [ ] `backend/tests/integracion/test_normalizacion_postgres.py` (nuevo)
- [ ] `backend/tests/integracion/test_api_clientes.py` / `test_api_categorias.py` (un caso cada uno, si entran ≤ 400; si no, en el archivo nuevo de PostgreSQL)

### Frontend
- No aplica.

### Docs
- [ ] `docs/aidlc/units.md`: fila de esta unidad (`en curso`, Luciano, rama) y, si P1 = A, la fila nueva
  `correccion-de-datos-existentes` + la nota de reserva de migraciones
- [ ] `docs/aidlc/units.md` (nota de D85): «el índice de categoría se revisó y no cambia»
- [ ] `docs/aidlc/TODO.md`: hallazgos 3 y 5 y P5 (sin unidad); §22 con las verificaciones manuales.
  **§20-22 no existen en esta rama** (están en la cadena de cobros, `feature/reporting-indicadores-de-cobranza`);
  se agrega la sección «Fase 2» con el mismo encabezado y se resuelve el conflicto al integrar.
- [ ] Una línea en el plan de la unidad 5 sobre `_condicion_iva` (se pide; no se edita desde esta rama)
- Sin ADR.

## Casos de prueba

Modo: **test primero**. Los casos RED tienen que fallar antes de tocar el código. Los de PostgreSQL se
escriben y, sin Docker local, **se saltean**; corren en la CI cuando la cadena llegue a `develop`. Los de
caracterización (C) documentan algo que ya funciona y se espera que pasen de entrada.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED RN-01: recorta, colapsa «  Ana   Perez » → «Ana Perez»; tab, salto y U+00A0 cuentan como espacio; U+200B, U+FEFF, U+00AD y controles se descartan; «José» no pierde la tilde; «José» en NFD y en NFC dan el mismo resultado | unit (dominio) | pendiente |
| 2 | RED RN-02: «JUAN CARLOS DE LA CRUZ» → «Juan Carlos de la Cruz»; «MARIA DE LOS ANGELES perez  » → «Maria de los Angeles Perez»; «McDonald» y «De» mezcladas se preservan; partícula al inicio («DE LA FUENTE ANA» → «De la Fuente Ana»); «y», «e»; «O'BRIEN» → «O'Brien», «MARIA-JOSE» → «Maria-Jose» | unit (dominio) | pendiente |
| 3 | RED RN-03: «ferreteria lopez s.r.l.» → «Ferreteria Lopez S.R.L.»; «IBM ARGENTINA SA» → «IBM Argentina SA»; «SUR» se conserva; «FERRETERIA DE LA COSTA SA» → «Ferreteria de la Costa SA» (P2); «srl» → «SRL»; «se» suelto no es sigla y «S.E.» sí (P3) | unit (dominio) | pendiente |
| 4 | RED: CUIT 30/33/34 → razón social; 20/23/24/27 y sin CUIT → persona | unit (dominio) | pendiente |
| 5 | RED RN-04: «CORTE DE PELO» → «Corte de pelo»; «corte» → «Corte»; «Corte VIP» se preserva; «VIP» → «Vip» | unit (dominio) | pendiente |
| 6 | RED RN-07: idempotencia de las cuatro funciones sobre el corpus de 1-5 (`f(f(x)) == f(x)`) | unit (dominio) | pendiente |
| 7 | RED: `Cliente.registrar`/`renombrar`, `Servicio` y `CategoriaEmpresa` guardan el nombre normalizado; un nombre hecho solo de invisibles da «… es obligatorio»; el largo máximo se mide después de normalizar | unit (dominio) | pendiente |
| 8 | RED HU-E4-05: `RegistrarCliente` (panel) con «JUAN CARLOS DE LA CRUZ» y con CUIT 30-… + «ferreteria lopez s.r.l.» | unit (aplicación) | pendiente |
| 9 | C RN-05: «Ana@Mail.COM» → «ana@mail.com»; «+54 9 11 1234-5678» → solo dígitos | unit (aplicación) | pendiente |
| 10 | RED hallazgo 1: `EditarCliente` que carga un CUIT 30-… y un nombre en la misma edición lo normaliza como razón social | unit (aplicación) | pendiente |
| 11 | C HU-E4-01: alta con CUIT escrito con guiones cuando ya existe en dígitos → «Ya existe un cliente con ese CUIT.» | unit (aplicación) | pendiente |
| 12 | RED HU-E4-05/RN-04: con «Vip» existente, «VIP» → «Ya existe una categoria con ese nombre en este ambito.»; con «Vip gold» existente, «VIP   GOLD» también (hoy pasa la búsqueda) | unit (aplicación) | pendiente |
| 13 | RED agente: `DirectorioViaMasterData.alta_rapida(nombre="maria gomez")` → «Maria Gomez», origen `AGENTE`; «WhatsApp 1234» se preserva | unit (ACL conversational) | pendiente |
| 14 | RED HU-E3-03: la fila «MARIA DE LOS ANGELES perez  » se guarda normalizada; la `FilaDeCatalogo` de entrada no cambia | unit (aplicación) | pendiente |
| 15 | RED HU-E3-04: cliente «Maria Gomez» con CUIT; la fila trae «MARIA GOMEZ», mismo CUIT, email con otras mayúsculas → no se llama a `guardar`, `actualizado_en` no se mueve, `modificado = False` | unit (aplicación) | pendiente |
| 16 | RED HU-E3-04: almacenado viejo «MARIA  GOMEZ» (sin normalizar) y fila «Maria Gomez» → tampoco es cambio | unit (aplicación) | pendiente |
| 17 | RED: un cambio real (otro nombre o teléfono) sí guarda y mueve `actualizado_en`; un cliente con `presente_en_planilla = False` se marca sin mover `actualizado_en` | unit (aplicación) | pendiente |
| 18 | RED HU-E3-07: un cliente `PLANILLA` normalizado no está en `ListarClientesParaEscrituraDeVuelta`; un cliente `PANEL` reingerido con solo diferencias de mayúsculas no entra en la ventana `desde` | unit (aplicación) | pendiente |
| 19 | RED hallazgo 2: «  responsable   inscripto » de una planilla → `RESPONSABLE_INSCRIPTO` | unit (aplicación) | pendiente |
| 20 | RED: la ingesta de servicio «CORTE DE PELO» guarda «Corte de pelo» | unit (aplicación) | pendiente |
| 21 | RED: «VIP» y «Vip» chocan en el índice real; dos empresas pueden tener «Vip» cada una (RLS) | integración (PostgreSQL) | escrito; se saltea sin Docker (CI) |
| 22 | RED: reingerir dos veces la misma fila con solo diferencias de mayúsculas deja `updated_at` igual en la base | integración (PostgreSQL) | escrito; se saltea sin Docker (CI) |
| 23 | RED: `POST /clientes` con «JUAN CARLOS DE LA CRUZ» responde el nombre normalizado; `POST /categorias` «VIP» con «Vip» → 409 con el mensaje | integración (API) | escrito; se saltea sin Docker (CI) |
| 24 | Compuertas: `ruff format --check`, `ruff check`, `mypy`, `pytest` (cobertura ≥ 80 %), `guard_architecture`; frontend sin cambios | compuertas | pendiente |
| 25 | En el navegador: PAN-DM-01/02/03 muestran el nombre normalizado después de guardar | manual | pendiente → `TODO.md` §22 |

## Verificaciones que no se pueden hacer acá

Van a `docs/aidlc/TODO.md` §22 (no dependen de MercadoPago ni de ARCA; no hay ítems para §20 ni §21):
- 22.x: en el navegador, crear un cliente «JUAN CARLOS DE LA CRUZ», un servicio «CORTE DE PELO» y la
  categoría «VIP» con «Vip» existente, y ver los resultados de los criterios.
- 22.y: con una **hoja de Google real** (requiere las credenciales de `TODO.md` §11.2/§15.2): procesar una
  fila «MARIA DE LOS ANGELES perez  », comprobar que la hoja original no cambió y que la hoja «CheatSheet
  (no editar)» no recibe el registro `PLANILLA`.
- 22.z: el criterio «una celda cambia solo en mayúsculas → no registra cambio» contra la **lectura viva**
  queda bloqueado por `TODO.md` §15.1 (la lectura incremental no existe); hoy se verifica por reproceso.
- Los casos 21 a 23 (PostgreSQL) se saltean en local sin Docker; se observan en la CI.

## Si P1 = A: la unidad nueva `correccion-de-datos-existentes` (diseño preliminar, se decide en su Gate 1)

- **HU**: HU-E4-05 RN-09. **Contexto**: master_data. **Depende de**: `normalizacion-de-datos`.
- **Qué hay para corregir, verificado**: solo **nombres** (`cliente.nombre`, `servicio.nombre`,
  `categoria_empresa.nombre`). CUIT, email y WhatsApp se guardan desde el principio a través de sus value
  objects (`fiscal.py:80`, `contacto.py:46,73`), así que ya están normalizados. Colisiones posibles: solo
  de **categoría** (dos categorías que difieren en espacios internos); los nombres de cliente y de
  servicio no tienen unicidad, y el CUIT no cambia.
- **Respaldo**: tabla `respaldo_de_normalizacion` (`id`, `empresa_id`, `corrida_id`, `entidad`,
  `entidad_id`, `campo`, `valor_original`, `valor_normalizado`, `created_at`) con RLS por
  `app.current_empresa` (patrón `0010_categorias.py:71-95`). Se escribe **en la misma transacción** que el
  cambio: no hay cambio sin respaldo. Alternativa descartada: un archivo en R2 (no es transaccional).
  Contiene nombres (dato personal): mismo nivel de protección que la tabla de origen.
- **Casos de uso**: `InformarCorreccion` (dry-run: conteos por entidad, hasta N ejemplos, colisiones),
  `AplicarCorreccion` (respaldo + cambio, salta colisiones, evento `EventoAuditable` con **conteos en
  `detalle` y ningún nombre**, `shared/auditoria.py:121-133`), `RestaurarCorreccion(corrida_id)` (vuelve
  al original solo donde el valor actual sigue siendo el normalizado, para no pisar ediciones posteriores).
  No toca `comprobante` ni hojas (no tiene puertos hacia ellos).
- **Quién la dispara** (pregunta para su Gate): recomendado, el **Administrador** desde una sección de
  PAN-DM-01 (el criterio cita esa pantalla) en un componente nuevo, porque `ListadoDeClientes.tsx` ya
  tiene 395 líneas; API en un router nuevo, porque `api/routers/clientes.py` tiene 318.
- **Migración**: `0030` provisoria (ver Infraestructura).

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- (pendiente de Gate 1: P1 a P6)
