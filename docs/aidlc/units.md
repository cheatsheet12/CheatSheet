# Mapa de unidades

> Las unidades de cada épico de [`roadmap.md`](roadmap.md), con su contexto dueño, sus historias,
> sus dependencias y su estado. Hay **un solo** archivo para todo el proyecto: cada sesión de mapeo
> agrega las filas de su épico. La columna `Épico` coincide **textualmente** con el nombre en el
> roadmap — eso es lo que ata los dos documentos.

Estados: `pendiente` · `en curso` · `en revisión` (PR abierto) · `mergeada`.
El estado del épico **se deriva** de estas filas; no se escribe en ningún lado.

| Épico | Unidad | Contexto dueño | HUs | Depende de | Responsable | Rama | Estado |
|---|---|---|---|---|---|---|---|
| Cimientos, identidad y bitácora | cimientos-y-bitacora | observability | HS-T5 | — | Cristian | feature/identity-cimientos-identidad-y-bitacora | mergeada |
| Cimientos, identidad y bitácora | identidad-y-onboarding | identity | HU-E1-01, HU-E1-02, HU-E1-03 | cimientos-y-bitacora | Cristian | feature/identity-cimientos-identidad-y-bitacora | mergeada |
| Cimientos, identidad y bitácora | usuarios-y-preferencias | identity | HU-E1-04, HU-E1-05, HU-E1-06, HU-E1-07 | identidad-y-onboarding | Cristian | feature/identity-cimientos-identidad-y-bitacora | mergeada |
| Conexión con los servicios externos | mecanismo-de-integraciones | integrations | HU-E2-05 | — | Cristian | feature/integrations-mecanismo-de-integraciones | mergeada |
| Conexión con los servicios externos | conexion-whatsapp | integrations | HU-E2-03 | mecanismo-de-integraciones | Cristian | feature/integrations-conexion-whatsapp | mergeada |
| Conexión con los servicios externos | conexion-arca | integrations | HU-E2-01 | mecanismo-de-integraciones | Cristian | feature/integrations-conexion-arca | mergeada |
| Conexión con los servicios externos | padron-y-datos-fiscales | identity | deuda D1 de HU-E1-02 | conexion-arca | Cristian | feature/identity-padron-y-datos-fiscales | mergeada |
| Conexión con los servicios externos | conexion-mercadopago | integrations | HU-E2-02 | mecanismo-de-integraciones | Cristian | feature/integrations-conexion-mercadopago | mergeada |
| Catálogo de clientes y servicios | catalogo-de-clientes | master_data | HU-E4-01 | — | Cristian | feature/master_data-catalogo-de-clientes | mergeada |
| Catálogo de clientes y servicios | catalogo-de-servicios | master_data | HU-E4-02 | catalogo-de-clientes | Cristian | feature/master_data-catalogo-de-servicios | en revisión |
| Catálogo de clientes y servicios | categorias-y-clasificacion | master_data | HU-E4-03, HU-E4-04 | catalogo-de-clientes, catalogo-de-servicios | Cristian | feature/master_data-categorias-y-clasificacion | en curso |


---

## Épico 1 — Cimientos, identidad y bitácora

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **cimientos-y-bitacora** | **Las seis unidades técnicas del roadmap §5, completas, más HS-T5.** Backend: composition root de FastAPI (`api/`), healthcheck y manejo uniforme de errores; `platform/settings.py` y sesión de base de datos; migraciones (Alembic); aislamiento multi-empresa con RLS por `empresa_id` (ADR-002); esqueleto de Celery + Beat con las cinco colas (ADR-003), `ClaveDeIdempotencia` y reintentos con backoff (ADR-009); esqueleto de tests (fixtures de base, factories, dobles de servicios externos) con el umbral del 80% corriendo en CI. Dominio: el agregado `RegistroDeAuditoria`, su tabla inmutable y el mecanismo por el que cualquier contexto publica un evento auditable (`observability` como OHS). Frontend: BFF de Next.js, cookie HttpOnly del JWT, layouts `(panel)` y `(public)`, wrapper de fetch y sistema de diseño mínimo. **Sin pantalla de negocio**: leer la bitácora es el épico 10 |
| **identidad-y-onboarding** | HU-E1-01, HU-E1-02 y HU-E1-03 — el onboarding entero de punta a punta: agregados `Empresa` y `Usuario`; alta con email/contraseña (Argon2id) y con OAuth2 de Google; login; JWT corto + refresh opaco rotativo con detección de reuso (ADR-011); aceptación de términos con versión y fecha; datos fiscales de la empresa con CUIT y `CondicionIVA` (ver D1); bloqueo del dashboard hasta completar los pasos 1 y 2. Pantallas PAN-ONB-01 y PAN-ONB-02 |
| **usuarios-y-preferencias** | HU-E1-04, HU-E1-05, HU-E1-06 y HU-E1-07 — todo lo que un Administrador hace sobre los usuarios de su empresa, más lo que cada usuario hace sobre sí mismo: invitación por email y su aceptación, catálogo cerrado de tres roles con RBAC, cambio de rol, desactivación y reactivación, el invariante «siempre al menos un Administrador activo», y `pref_idioma` / `pref_zona_horaria` / `pref_suscripciones`. Pantallas PAN-USR-01 y PAN-USR-02 |

### Orden

```
cimientos-y-bitacora ── identidad-y-onboarding ── usuarios-y-preferencias
```

Cadena lineal, un responsable, sin paralelismo. Cada unidad deja la anterior demostrable: la primera
levanta el proceso y la bitácora, la segunda registra una empresa que ya audita cada operación, la
tercera opera sobre los usuarios de esa empresa.

### Notas

- **Unidades gruesas, deliberadamente.** Tres unidades para ocho historias, no ocho para ocho. El
  costo de cada unidad no es solo su código: son tres gates, un plan y un PR. Con historias de esta
  granularidad —HU-E1-03 son dos columnas y un checkbox; HU-E1-07 son tres campos— el plan llegaría
  a ser más largo que el diff, que es justamente el caso que el workflow manda resolver escribiendo
  una línea y ejecutando. Se agrupa por **pantalla y transacción compartida**: las dos pantallas del
  onboarding en una unidad, las dos de configuración de usuarios en otra.
- **El precio, dicho de frente:** los PRs son grandes, sobre todo el de `cimientos-y-bitacora`, y si
  el Gate 2 falla hay más superficie que desandar. Se acepta a cambio de tres ceremonias en lugar de
  ocho. Si una unidad se vuelve inmanejable durante la implementación, se dice y se re-corta el mapa
  con el equipo — nunca partiéndola dentro de la rama (regla 1c).
- **La bitácora entra en la unidad de cimientos y eso la mejora, no la infla.** HS-T5 no tiene
  pantalla y `observability` es OHS: no depende de nadie. Su tabla `registro_de_auditoria` es además
  la **primera tabla real** del sistema, o sea contra qué se prueban de verdad las migraciones, el
  RLS por `empresa_id` y las fixtures. Sin ella, los cimientos se verificarían contra nada. Y va
  antes que identity porque HU-E1-05 RN-04 y HU-E1-06 RN-02 exigen registro en el Log de
  Operaciones: si el sumidero llegara después, identity se entregaría con un criterio incumplido.
- **`cimientos-y-bitacora` cruza `observability` + `platform` + frontend.** Declara `observability`
  como contexto dueño porque es el único que recibe código de dominio; el resto es infraestructura
  sin dueño de negocio.
- **Trabajo en paralelo: no aplica.** Un solo responsable (Cristian). La regla 1c del workflow sigue
  vigente por si eso cambia.
- **Las tres unidades comparten una sola rama** (decisión del 2026-08-13), en lugar de una rama y
  un PR cada una como pide la regla 1a. El épico entero entra a `develop` de una vez.
  **Lo que se gana:** una sola ceremonia de PR en lugar de tres encadenadas, sin rebases entre
  ramas que dependen unas de otras. **Lo que se paga:** un PR con las ocho historias, y un revert
  que se lleva el épico completo. Los **gates 1 y 2 siguen siendo por unidad** — lo que se unificó
  es la rama y el gate 3, no la planificación ni la verificación.
- **Esto no habilita a partir unidades dentro de la rama.** Si la descomposición resulta mala, se
  dice y se re-corta el mapa deliberadamente (regla 1c), que es lo mismo de antes.

### Decisión D1 — resuelta

El roadmap §6 la dejaba abierta: HU-E1-02 RN-01 exige validar el CUIT contra ARCA en tiempo real
durante el onboarding, pero la credencial fiscal de la empresa recién se carga en el épico 2.

**Resolución (2026-08-12): validación estructural en el épico 1; consulta al padrón en el épico 2.**
`identidad-y-onboarding` valida formato y dígito verificador del CUIT, y `CondicionIVA` se elige
manualmente. No se introduce una credencial ARCA de plataforma.

Consecuencias, explícitas para que nadie las descubra después:

- El épico 1 **cierra con HU-E1-02 RN-01 parcialmente cumplida**. La autocompletación de
  `CondicionIVA` desde el padrón (criterio de aceptación 1 de HU-E1-02) tampoco se cumple todavía.
- **El épico 2 carga con completarla**: cuando HU-E2-01 deja la credencial de ARCA cargada y
  validada, se agrega la consulta de padrón al onboarding y a la edición de datos de la empresa.
  Eso se mapeará como unidad del épico 2, no acá.
- Un CUIT estructuralmente válido pero inexistente en ARCA **entra al sistema** hasta entonces. Es
  aceptable porque ningún comprobante se emite antes del épico 5, y la emisión revalida contra ARCA.

### Estado

**Cerrado en código.** Las tres unidades pasaron el Gate 2 en verde (2026-08-18) y el épico
entero entró a `develop` en un solo PR — [#5](https://github.com/cheatsheet12/CheatSheet/pull/5) —
por la decisión del 2026-08-13.

Lo que queda no es código: son las credenciales reales de Google OAuth2 y del correo transaccional,
que hoy corren simuladas, más la deuda declarada. Todo eso está en [`TODO.md`](TODO.md) §2 y §3.

### Fuera de alcance de este épico

- Pantalla de la bitácora (HU-E12-01, HU-E12-02) → épico 10.
- Centro de notificaciones (HU-E11-03) → épico 10. Este épico solo envía el email de invitación.
- Cola de fallos DLQ (HS-T6) → épico 4.
- Consulta de CUIT al padrón de ARCA → épico 2, por D1.

---

## Épico 2 — Conexión con los servicios externos

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **mecanismo-de-integraciones** | El andamiaje que las otras cuatro presuponen, más HU-E2-05. Dominio: el agregado `ConfiguracionDeIntegracion` con `SistemaExterno`, `Ambiente` (homologación / producción), `EstadoDeConexion` (conectado · atención · no conectado) y la marca de tiempo de la última verificación. Plataforma: el cifrado de credenciales en reposo (AES-256-GCM), con `credencial_algoritmo` en su propia columna para poder rotar sin adivinar con qué se cifró cada fila. Aplicación: el puerto `PortVerificadorDeConexion` y el registro que resuelve un verificador por sistema; el caso de uso de verificación en vivo de HU-E2-05. Frontend: `features/integrations` y la pantalla PAN-CFG-INT en `(panel)/configuracion/integraciones`, con la grilla de cuatro tarjetas del prototipo. **Sin ningún proveedor real**: los cuatro verificadores son simulados, igual que `ProveedorOAuthSimulado` en el épico 1. Termina en la pantalla mostrando las cuatro integraciones «No conectada» y el botón de verificar funcionando |
| **conexion-whatsapp** | HU-E2-03 — alta del número de WhatsApp Business contra Meta, estado `pendiente` mientras dura la verificación, tarea de Beat que consulta el resultado, `display_name` verificado y calidad de la línea, motivo de rechazo cuando falla, y la notificación al Administrador en los tres desenlaces |
| **conexion-arca** | HU-E2-01 — carga del certificado y la clave privada asociados al CUIT de la empresa, cifrados con el mecanismo de la unidad 1; validación real contra WSAA obteniendo un ticket de acceso antes de marcar Conectada; ambiente registrado; detección de credencial vencida o revocada que pasa la integración a inactiva y notifica |
| **padron-y-datos-fiscales** | La deuda D1 del épico 1. Consulta al padrón de ARCA con la credencial que dejó `conexion-arca`: valida que el CUIT exista, autocompleta razón social y `CondicionIVA`, y lo hace tanto en el paso 2 del onboarding (PAN-ONB-02) como en la edición de datos de la empresa. Cierra HU-E1-02 RN-01 y su criterio de aceptación 1, que el épico 1 entregó a medias |
| **conexion-mercadopago** | HU-E2-02 — flujo OAuth2 contra MercadoPago, token de acceso y de refresco cifrados, validación de la conexión leyendo los datos de la cuenta antes de marcarla activa, y revocación o expiración que la pasa a inactiva y notifica |

### Orden

```
mecanismo-de-integraciones ─┬─ conexion-whatsapp
                            ├─ conexion-arca ── padron-y-datos-fiscales
                            └─ conexion-mercadopago
```

Un solo responsable, así que se ejecutan en serie: **mecanismo → whatsapp → arca → padrón → mercadopago**.

**WhatsApp va segunda, y es lo único del orden que no se negocia.** HU-E2-03 RN-02 dice que Meta
tarda entre 24 y 72 horas en verificar el número, y eso es tiempo de calendario que no se compra con
esfuerzo. Arrancarla apenas exista el andamiaje pone el reloj a correr mientras se construyen ARCA y
MercadoPago; dejarla última agrega tres días muertos al final del épico. Es la misma razón por la que
el roadmap §3 la adelantó al épico 2 aunque el agente conversacional sea el 8.

Las otras tres son independientes entre sí: ninguna lee nada de las otras. Si en algún momento hay un
segundo responsable, ese es el punto de corte natural (regla 1c).

### Notas

- **Cinco unidades para cuatro historias — y sí, es lo contrario de lo que hizo el épico 1.** Ahí se
  agruparon ocho historias en tres unidades porque eran chicas: «HU-E1-03 son dos columnas y un
  checkbox». Acá tres de las cuatro historias están marcadas **Complejidad Alta** en el insumo, y
  cada una es una integración externa distinta: WSAA de ARCA habla SOAP con certificado cliente,
  MercadoPago habla OAuth2 sobre REST, Meta habla Graph API con una verificación asíncrona de 72
  horas. Lo único que comparten es el agregado y la tarjeta en la pantalla — que es exactamente lo
  que se extrajo a la unidad 1. Juntarlas daría un PR con tres protocolos, tres modos de falla y
  tres juegos de tests de contrato, o sea el PR de `cimientos-y-bitacora` otra vez pero peor.
- **Una rama y un PR por unidad. Se vuelve a la regla 1a y se abandona la excepción del 2026-08-13.**
  El épico 1 corrió las tres unidades sobre una rama única. Acá eso sería un error concreto, no un
  gusto: `conexion-whatsapp` **no puede cerrar hasta que Meta responda**, entre uno y tres días
  después de que el código esté listo. Con rama única, ARCA y MercadoPago quedarían rehenes de ese
  reloj externo, y `conexion-arca` es justamente lo que el épico 5 (facturación) necesita mergeado
  para poder planificarse. Se paga con cinco ceremonias de PR en lugar de una; se compra que una
  espera de terceros no bloquee al resto.
- **`padron-y-datos-fiscales` es unidad aparte y su dueño es `identity`, no `integrations`.** Escribe
  sobre el agregado `Empresa` — razón social y `CondicionIVA` —, y el workflow manda que la unidad
  declare como dueño al contexto que hace la escritura. Llega a la credencial de ARCA llamando al
  servicio de aplicación de `integrations`, nunca a su dominio (R3). **La alternativa que se
  descartó** era plegarla dentro de `conexion-arca`, que tiene el atractivo de dejar esa unidad
  terminando en algo demostrable de punta a punta; se descartó porque obligaría a que una unidad de
  `integrations` escriba en `identity`, que es el tipo de ambigüedad de propiedad que después nadie
  sabe dónde tocar.
- **`mecanismo-de-integraciones` no es una unidad técnica encubierta.** Lleva HU-E2-05 detrás: la
  verificación en vivo y el estado consolidado son *su* historia, no un extra. Por eso no necesita la
  escalada de «trabajo sin historia» del workflow, y por eso termina en una pantalla que se puede
  mostrar aunque no haya ningún proveedor conectado.
- **Los cuatro proveedores arrancan simulados, a propósito.** Es la misma decisión que el épico 1
  tomó con Google OAuth y con el correo, y que funcionó: el flujo se recorre entero en una laptop,
  los tests no tocan la red (regla del workflow, paso 3), y el simulado **lanza al construirse en
  `production`**. Conseguir las credenciales reales de ARCA homologación, de MercadoPago sandbox y
  de Meta es tarea de despliegue y va en el `TODO.md` del épico, no en el código.
- **Cada una de las tres conexiones dispara la escalada de «nueva integración externa»**: su plan de
  Gate 1 debe traer sección de contratos —endpoints por ambiente, autenticación, modos de falla— y
  tests de contrato. Eso es por unidad, no acá.
- **`mecanismo-de-integraciones` carga además con reconciliar `backend/.env.example`.** Agrega
  `SECRETS_ENCRYPTION_KEY`, así que la Definition of Done (`CLAUDE.md` §7) la obliga a tocar ese
  archivo igual; y el archivo hoy está **desincronizado con el código desde el épico 1** — declara
  `ENVIRONMENT`, `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_MINUTES` y `REFRESH_TOKEN_DAYS` cuando
  `platform/settings.py` lee `APP_ENV`, `JWT_SECRET`, `JWT_ACCESS_TTL_MINUTOS` y `REFRESH_TTL_DIAS`,
  y le faltan las once variables de las unidades 2 y 3. Copiarlo hoy no levanta el proceso. Se dice
  acá para que quede claro que es deuda heredada que se salda de paso, no alcance nuevo.

### Decisión D7 — la pantalla de integraciones es de configuración, no un paso del onboarding

Las cuatro historias del épico nombran **PAN-CFG-INT (Configuración — Integraciones)**. Ese código
**no existe en el mapa de navegación de Etapa 5**: la única pantalla de integraciones maquetada es
**PAN-ONB-03 — Integraciones**, el tercer paso del onboarding en `prototipos/onboarding.html`.
Son dos ubicaciones distintas del mismo contenido y hay que elegir una.

**Resolución (2026-08-18): se construye como pantalla de configuración, en
`(panel)/configuracion/integraciones`, reutilizando el diseño de PAN-ONB-03 tal cual.**

Los tres motivos, en orden de peso:

1. **HU-E2-05 no es un paso, es una consulta recurrente.** La hace el Administrador *o el Operador*,
   «antes de depender de ellas». Un paso de onboarding se atraviesa una vez; esto se mira cada vez
   que algo falla.
2. **El propio prototipo dice que es opcional.** El pie de PAN-ONB-03 ofrece «Configurar esto
   después» — nunca fue una compuerta.
3. **El épico 1 ya decidió lo contrario y está mergeado.** El dashboard se desbloquea al completar
   los pasos 1 y 2; meter un paso 3 obligatorio ahora rompería a las empresas ya registradas.

Consecuencias explícitas:

- El código de pantalla que se usa en el código y en los planes es **PAN-CFG-INT**, el de las
  historias. PAN-ONB-03 queda como el origen del diseño visual, y la grilla de cuatro tarjetas se
  toma de ahí sin rediseñar nada.
- **El onboarding no gana un paso 3.** El indicador «PASO 3 DE 3» del prototipo no se replica.
- Entrar a la pantalla requiere Administrador para conectar y desconectar; ver el estado lo permite
  también el Operador, como pide HU-E2-05.

### Decisión escalada a ADR — [ADR-0003](../adr/0003-integrations-open-host-service.md), `Accepted`

**El Context Map (`docs/architecture.md` §4) no tiene ninguna fila para `integrations`.** No figura
como upstream ni como downstream de nadie, y este épico necesita que al menos `identity` lo consuma
(la unidad `padron-y-datos-fiscales`), con `billing`, `payments`, `conversational` y
`spreadsheet_sync` detrás en los épicos 5, 6, 8 y 4 — todos por el mismo motivo: obtener una
credencial validada.

Se escaló a ADR el mismo 2026-08-18, porque modificar el Context Map es arquitectura y un mapa de
unidades reparte trabajo. [ADR-0003](../adr/0003-integrations-open-host-service.md) propone declarar
`integrations` como **OHS (Open Host Service)** — un único contrato en su capa de aplicación que
cualquier contexto puede llamar, sin que `integrations` conozca a ninguno de sus consumidores y sin
que la clave de cifrado salga nunca del contexto. Quedó **`Accepted` con el merge del PR #6**, que
es lo que destraba el Gate 1 de `mecanismo-de-integraciones`.

### Estado

**Cerrado en código** (2026-08-20). Las cinco unidades pasaron sus tres gates y están en
`develop`: PRs [#7](https://github.com/cheatsheet12/CheatSheet/pull/7) y
[#8](https://github.com/cheatsheet12/CheatSheet/pull/8) (`mecanismo-de-integraciones`),
[#9](https://github.com/cheatsheet12/CheatSheet/pull/9) (`conexion-whatsapp`),
[#11](https://github.com/cheatsheet12/CheatSheet/pull/11) (`conexion-arca`),
[#12](https://github.com/cheatsheet12/CheatSheet/pull/12) (`padron-y-datos-fiscales`) y
[#13](https://github.com/cheatsheet12/CheatSheet/pull/13) (`conexion-mercadopago`).

**Cerrado en código no es cerrado.** El criterio de demo que le puso el roadmap §1 es «PAN-CFG-INT
mostrando ARCA y MercadoPago **conectados de verdad**», y los tres proveedores corren hoy contra
adaptadores simulados. Ese último paso no es código: son las credenciales de ARCA homologación,
de la aplicación de MercadoPago y del usuario de sistema de Meta, y está en [`TODO.md`](TODO.md) §5.
El reloj que manda es el de Meta: 24 a 72 horas por número (HU-E2-03 RN-02).

### Fuera de alcance de este épico

- **HU-E2-04 — vincular planilla de Google Sheets o Excel** → épico 4. El roadmap §4 la separó de
  las otras tres: sus criterios de aceptación terminan en PAN-ING-02 revisando el mapeo, o sea que
  es el primer paso del flujo de ingesta y no una integración más. La tarjeta «Google Sheets» de la
  pantalla existe desde la unidad 1, pero **sin acción**, hasta el épico 4.
- **Emitir un comprobante con la credencial de ARCA** → épico 5. Acá la credencial se carga, se
  cifra y se valida; nada la usa todavía.
- **Generar un link de cobro con el token de MercadoPago** → épico 6.
- **Que el agente responda por el número de WhatsApp** → épico 8. Acá la línea queda verificada y en
  silencio.
- **Centro de notificaciones** → épico 10. Este épico notifica al Administrador por los canales que
  ya existen; no construye la bandeja donde leerlas.

---

## Épico 3 — Catálogo de clientes y servicios

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **catalogo-de-clientes** | HU-E4-01 — el agregado `Cliente` y la tabla `cliente` del DER, con `origen` (`origen_dato`: PLANILLA · PANEL · AGENTE) asignado por el sistema y no editable (RN-01) y `presente_en_planilla` desde la primera migración. Unicidad de CUIT por empresa (RN-03) como índice único parcial sobre (`empresa_id`, `cuit`), no como chequeo en aplicación. Validación contra el padrón de ARCA al crear y al editar (RN-02), llamando a `ConsultarPadron` de `integrations` y reutilizando el patrón de tres estados que dejó `padron-y-datos-fiscales` — encontrado completa razón social y `CondicionIVA`, no encontrado bloquea, no disponible **no** bloquea. Pantalla PAN-DM-01: listado con nombre, CUIT, origen, WhatsApp y estado, más el formulario de alta y edición. Trae además los cimientos del contexto, que ninguna otra unidad va a tener que volver a decidir: repositorio con RLS por `empresa_id`, la migración inicial de `master_data` y el `features/master_data` del frontend con su `index.ts` |
| **catalogo-de-servicios** | HU-E4-02 — agregado `Servicio` y tabla `servicio`: `precio` en `Decimal` (nunca `float`, `CLAUDE.md` §3.5), `alicuota_iva` como enum cerrado de tres valores —0 %, 10,5 % y 21 % (RN-02)—, el par `agendable` / `duracion_estandar_min` con el invariante de RN-03 vivo en el dominio y no en el formulario, y la desactivación que oculta del catálogo activo sin tocar comprobantes ni turnos históricos (RN-04). Pantalla PAN-DM-02 con listado y formulario. El criterio «edito el precio y los comprobantes emitidos mantienen el suyo» **no se implementa acá**: es la desnormalización que el DER ya declara para `comprobante`, y se verifica en el épico 5 |
| **categorias-y-clasificacion** | HU-E4-03 y HU-E4-04 — agregado `CategoriaEmpresa` con `nombre` y `aplica_a`, unicidad por (`empresa_id`, `nombre`, `aplica_a`) (RN-02) y eliminación que desclasifica sin tocar el resto de los datos del elemento (RN-03), sobre PAN-DM-03. Encima de eso, la asignación de HU-E4-04 sobre las dos pantallas que para entonces ya existen: validación de ámbito (RN-01), varias categorías por elemento (RN-02, ver D8) y el filtro por categoría en los dos listados |

### Orden

```
catalogo-de-clientes ── catalogo-de-servicios ── categorias-y-clasificacion
```

Cadena lineal, un responsable, sin paralelismo.

**Las categorías van últimas aunque el DER ponga la FK `categoria_id` dentro de `cliente` y
`servicio`.** Ese orden de lectura es tentador y es el equivocado: HU-E4-04 —asignar y filtrar— no
se puede demostrar sin elementos que clasificar, así que arrancar por ahí entregaría una pantalla
que crea categorías que no clasifican nada, y dejaría media historia colgada de una unidad
posterior. La tabla de enlace la agrega la tercera migración; para eso está Alembic.

### Notas

- **Tres unidades para cuatro historias**, que es el punto medio entre los dos épicos anteriores y
  no una posición cómoda: el épico 1 agrupó ocho historias en tres unidades porque eran diminutas,
  el épico 2 abrió cinco unidades para cuatro historias porque cada una era un protocolo distinto.
  Acá las cuatro viven en un solo contexto y ninguna habla un protocolo propio, pero son **tres
  pantallas** del mapa de navegación y dos de las historias están marcadas Complejidad Media.
- **La alternativa descartada era juntar clientes y servicios en una sola unidad.** Tiene a favor
  que las dos son el mismo ABM con distinta forma. Se descartó porque ese PR juntaría la única
  llamada externa del épico —el padrón de ARCA— con la única regla de dinero —precio y alícuota—,
  que son dos superficies de test que no se parecen en nada, y porque dos pantallas del mapa de
  navegación son dos pantallas. Se paga con una ceremonia de PR más.
- **Una rama y un PR por unidad**, como el épico 2 y a diferencia del épico 1. Acá no hay ningún
  reloj externo que lo obligue, pero tampoco hay nada que lo desaconseje, y tres PRs de ABM se
  revisan mejor que uno con tres pantallas.
- **`catalogo-de-servicios` depende de `catalogo-de-clientes` sólo por el andamiaje del contexto**
  —repositorio, migración inicial, feature del frontend—, no por los datos: las dos tablas no se
  miran entre sí. Si alguna vez hay un segundo responsable, ese es el punto de corte natural
  (regla 1c), y cuesta poco: se adelanta la migración inicial a la primera unidad y se paraleliza.
- **`master_data` es Supporting, no Core.** Nada de este épico emite comprobantes ni mueve dinero.
  Lo que sí hace es fijar el vocabulario que después consumen `billing`, `payments`, `scheduling` y
  `conversational` (Context Map §4, fila C/S). Un nombre mal puesto acá se paga cuatro veces.
- **`origen` y `presente_en_planilla` entran en la primera migración aunque este épico sólo escriba
  `PANEL`.** Son ADR-006 y ADR-007 hechos columna, y el épico 4 los lee para decidir qué sobrescribe
  la planilla y qué se marca ausente. Agregarlas después sería un backfill sobre datos reales.

### Decisión D8 — un elemento puede tener varias categorías, y el DER modela una sola

`cliente` y `servicio` traen en el DER una columna `categoria_id uuid FK → categoria_empresa`: una
categoría por elemento. **HU-E4-04 RN-02 dice lo contrario**, sin ambigüedad: «un cliente o servicio
puede tener más de una categoría asignada». No hay lectura que concilie las dos cosas.

**Resolución (2026-08-31): gana la historia. Se modela con dos tablas de enlace,
`cliente_categoria` y `servicio_categoria`, y la columna `categoria_id` no se crea.**

El precedente es H1, el hueco que el propio DER declara: cuando el DER y una historia se
contradicen, el DER es un boceto y la historia es el requisito. Acá además la columna todavía no
existe en ninguna base, así que la divergencia no cuesta una migración de datos — sólo cuesta
decirla.

Consecuencias explícitas:

- **El DER entregado queda desactualizado en dos tablas.** Es un insumo de Etapa 5 y no se reescribe
  (regla del workflow); la divergencia se documenta acá y en el plan de `categorias-y-clasificacion`.
- La unicidad de RN-02 de HU-E4-03 sigue siendo sobre `categoria_empresa`, no sobre el enlace.
- El filtro «filtrable por esa categoría» de HU-E4-04 pasa a ser un `JOIN`, no un `WHERE` sobre una
  columna. Es la parte que se paga, y es barata.

### Decisión D9 — el ámbito «ambos» no existe en el enum del DER

HU-E4-03 RN-01 dice que cada categoría tiene un ámbito «(clientes, servicios o ambos)». El enum
`aplica_a` del DER tiene cuatro valores —`CLIENTE · SERVICIO · FAQ · TURNO`— y ninguno es «ambos».

**Resolución (2026-08-31): se agrega el valor `AMBOS` al enum, y la pantalla PAN-DM-03 ofrece
solamente los tres que le corresponden: `CLIENTE`, `SERVICIO` y `AMBOS`.**

`FAQ` y `TURNO` quedan en el enum sin uso hasta los épicos 8 y 7, que son sus dueños. La
alternativa era no ofrecer «ambos» y obligar a elegir uno, que es más limpio en la base y
directamente incumple RN-01.

Consecuencia para la validación de ámbito de HU-E4-04 RN-01: una categoría es asignable a un cliente
si su `aplica_a` es `CLIENTE` o `AMBOS`, y a un servicio si es `SERVICIO` o `AMBOS`. Esa regla vive
en el dominio de `CategoriaEmpresa`, no en el filtro del combo.

### Hueco P10 — PAN-DM-01, PAN-DM-02 y PAN-DM-03 no tienen prototipo

Las tres pantallas están en el mapa de navegación de Etapa 5, con su código y sus roles
(Admin · Operador), pero **ninguna está maquetada**: no hay `datos-maestros.html` en
`inputs/prototipos/`. Es exactamente el hueco P9, el de PAN-USR-01 y PAN-USR-02, que el épico 1 ya
atravesó.

Se resuelve igual, porque funcionó: se construyen con el catálogo de componentes del PDF §1.3 y los
tokens ya importados, reusando el listado y el formulario que `usuarios-y-preferencias` dejó en el
sistema de diseño. Si el prototipo aparece, se ajustan. No es una decisión de este mapa; se anota
para que nadie lo descubra a mitad de la unidad y crea que falta un insumo.

### Lo que se alinea de paso

Dos cosas que este épico toca inevitablemente y conviene que no se descubran dentro de una rama:

- **`CUIT` se muda a `shared/fiscal.py`.** Hoy vive en `identity/domain/valores.py`, y el docstring
  de `shared/fiscal.py` ya dejó escrita la regla: «`CUIT` stays in `identity` … A value object moves
  here when a second context needs it, never in anticipation». `Cliente.cuit` es ese segundo
  contexto. La mudanza es la misma que ya se hizo con `CondicionIVA` y con `RolUsuario`:
  `identity/domain/valores.py` lo re-exporta y ningún import existente se rompe. Le toca a
  `catalogo-de-clientes`.
- **La fila del Context Map de `integrations` no nombra a `master_data`.** Enumera
  `identity, spreadsheet_sync, billing, payments, conversational`, y este épico agrega un consumidor.
  **No hace falta un ADR nuevo**: [ADR-0003](../adr/0003-integrations-open-host-service.md) ya
  decidió que `integrations` es un OHS que **cualquier** contexto puede llamar, y la lista de la
  tabla es la enumeración de los consumidores conocidos al escribirla, no una lista blanca. Se
  agrega `master_data` a esa celda de `docs/architecture.md` §4 en la unidad que estrena el edge.

### Preguntas que resuelve el Gate 1 de cada unidad

No se responden acá —el mapa reparte trabajo, no diseña— pero se dejan escritas para que el plan de
cada unidad las encare en vez de tropezarlas:

| # | Pregunta | Unidad |
|---|---|---|
| 1 | ¿Se puede crear un cliente **sin** CUIT? El DER lo deja nullable y un consumidor final no tiene uno; HU-E4-01 RN-02 habla como si siempre hubiera CUIT que validar | `catalogo-de-clientes` |
| 2 | ¿Qué pasa cuando la empresa **todavía no conectó ARCA**? El padrón necesita certificado, y la integración es opcional. El precedente de `padron-y-datos-fiscales` es que «no se pudo preguntar» no bloquea; falta decidir si eso alcanza para un alta de cliente o si hace falta decirlo en la pantalla | `catalogo-de-clientes` |
| 3 | ¿Un cliente se **elimina** o sólo se desactiva? El DER tiene `activo` y ADR-007 dice que lo que sale de la planilla se marca ausente y nunca se borra; HU-E4-01 habla de crear y editar, nunca de borrar | `catalogo-de-clientes` |
| 4 | ¿La alícuota de IVA es un enum propio de `master_data` o sale de `reference_data`, que es el contexto dueño del catálogo fiscal (`tipo_catalogo_fiscal: ALICUOTA_IVA`)? RN-02 la declara cerrada de tres valores; el épico 5 la va a necesitar vigente por fecha | `catalogo-de-servicios` |

### Estado

**Mapa aprobado el 2026-08-31**, junto con D8 y D9. Responsable de las tres unidades: Cristian.
`catalogo-de-clientes` pasó sus tres gates y entró a `develop` el 2026-09-01 —
[#23](https://github.com/cheatsheet12/CheatSheet/pull/23). Su plan y el registro de la verificación
están en [`units/catalogo-de-clientes.md`](units/catalogo-de-clientes.md).

**La próxima unidad es `catalogo-de-servicios`**, que ya tiene sus dependencias mergeadas.

**El mapa viaja en el PR de esa unidad**, no en uno propio: la rama de la unidad se cortó del commit
del mapa, que es lo mismo que hizo el épico 2 con `mecanismo-de-integraciones`.

### Fuera de alcance de este épico

- **Poblar el catálogo desde una planilla** (HU-E2-04, HU-E3-01 … HU-E3-07) → épico 4. Este épico
  deja las columnas que esa ingesta necesita, y nada más.
- **Escribir de vuelta en la planilla lo que se crea desde el panel** (HU-E3-07) → épico 4.
- **Que un cliente reciba un comprobante** → épico 5; **que tenga un cobro** → épico 6; **que reserve
  un turno** → épico 7; **que el agente lo consulte por WhatsApp** → épico 8. Acá el catálogo existe
  y todavía no lo consume nadie.
- **Importación masiva por CSV o alta múltiple.** Ninguna historia la pide, y la vía de carga masiva
  del producto es la planilla.
- **Historial de cambios de un cliente o un servicio** más allá de lo que ya registra la bitácora del
  épico 1.
