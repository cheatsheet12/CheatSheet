# Unidad: cobro-con-clave-de-idempotencia

**HUs**: HU-E6-03 **Contexto dueño**: payments (con la pieza de envío en `frontend/src/features/payments` y el BFF) **Rama**: feature/payments-cobro-con-clave-de-idempotencia

> Origen: Gate 1 de `navegacion-pendiente` (2026-10-05), P1 y su reparto: emisión y nota de
> crédito son de `billing` y van como issue [#97](https://github.com/cheatsheet12/CheatSheet/issues/97)
> (Cristian); el cobro es esta unidad. PR #98 solo registró ese reparto en `units.md` y en el plan
> de `navegacion-pendiente` (documentación, **sin infraestructura compartida**). Depende de
> `navegacion-pendiente` (mergeada). Tamaño: S/M.

## Qué hace

Hoy cada `POST /cobros` crea un cobro nuevo y pide una preferencia nueva a MercadoPago. El panel
ya no permite el doble clic (#90), pero un reintento de red, un 504 del BFF (timeout de 10 s) con el
backend todavía trabajando, dos pestañas o un cliente que no es el panel producen **dos cobros y
dos links pagables** para la misma deuda. Esta unidad agrega una **clave de idempotencia por
pedido**: el panel genera una clave por formulario y la manda en `X-Idempotency-Key`; el backend la
guarda con el cobro bajo un índice único `(empresa_id, clave)`. El mismo pedido repetido devuelve el
cobro ya creado, **sin volver a llamar a MercadoPago**; la misma clave con otros datos se rechaza.

**Fuera de esta unidad:**
- Emisión y nota de crédito (`POST /comprobantes`, `POST /comprobantes/{id}/notas-de-credito`):
  issue #97, `billing`. Esta unidad fija el contrato HTTP común (ver P7) para que #97 lo reuse.
- Regenerar link, cancelar, reembolsos: `regenerar` y `cancelar` ya son idempotentes por estado
  (un segundo pedido no crea nada nuevo); el reembolso por API ya usa su propia clave persistida
  (`reembolso_clave_idempotencia`, `api/routers/reembolsos.py`), que es la clave **hacia
  MercadoPago**, no la del pedido del usuario.
- El timeout del BFF (10 s) frente a los reintentos de MercadoPago (15 s × 3): preexistente; esta
  unidad lo vuelve inofensivo (reintentar con la misma clave es seguro) pero no lo cambia.
- `float(cobro.monto)` en `pasarela.py`, anotado en `nuevo-cobro-desde-su-panel`: ya resuelto con el
  literal exacto del `Decimal` (`_numero_json`); no se toca.

## Precedentes leídos

- **`api/routers/reembolsos.py`**: la clave se genera una vez, se **confirma en una transacción
  propia antes** de hablar con MercadoPago y se reusa en cada reintento. Resuelve otro problema
  (que MercadoPago no ejecute dos reembolsos), y no tiene helpers reutilizables para un encabezado
  de pedido: se toma la idea (clave persistida junto al agregado, `UUID`), no el código.
- **`shared/idempotencia.py::ClaveDeIdempotencia`**: es la clave **derivada** (empresa + tipo +
  huella del payload) de tareas y webhooks (ADR-009, `platform/cache.py`, `SET NX` en Redis). No
  sirve para el pedido: dos cobros legítimos e idénticos (mismo cliente, monto y concepto, en dos
  momentos) tendrían la misma huella y el segundo se perdería. La clave del pedido tiene que venir
  del cliente, que es el único que sabe si es «el mismo pedido» o «otro igual».
- **`identity/infrastructure/refresh_tokens.py`**: `pg_advisory_xact_lock(espacio, hashtext(...))`
  para serializar un leer-comprobar-escribir dentro de la transacción de la unidad de trabajo. Es
  el mecanismo que se reusa para la concurrencia (ver Diseño).

## Comportamiento definido (contrato HTTP)

| Pedido | Respuesta | Por qué |
|---|---|---|
| Clave nueva, datos válidos | **201** con el cobro (como hoy) | Sin cambios para el caso feliz |
| Misma clave, **mismos datos** | **201** con el cobro original, en su **estado actual**; sin llamar a MercadoPago, sin bitácora nueva | El cliente recibe la misma respuesta que habría recibido si la primera hubiera llegado (P2) |
| Misma clave, **otros datos** | **422** `ClaveDeIdempotenciaReusada`: «Esta clave ya se uso para generar un cobro con otros datos. Revise el listado de cobros antes de reintentar.» | Es un error del cliente, no un conflicto de estado del negocio; el borrador IETF `Idempotency-Key` usa 422 para este caso, y en este sistema 422 es lo que el BFF reenvía con texto (P3) |
| **Sin** encabezado | **422** `ClaveDeIdempotenciaFaltante`: «Falta la clave de idempotencia del pedido (encabezado X-Idempotency-Key).» | Obligatoria (P1) |
| Encabezado que no es un UUID | **422**: «La clave de idempotencia del pedido no es valida.» | Formato acotado y comparable con la columna (P4) |
| Dos pedidos **simultáneos** con la misma clave | El segundo **espera** a que el primero termine y devuelve el mismo cobro (201); si el primero falló (MercadoPago caído), el segundo lo intenta de nuevo | Bloqueo consultivo por clave (P5) |
| Misma clave en **otra empresa** | Cobro nuevo e independiente | El índice y el bloqueo incluyen `empresa_id`; bajo RLS una empresa no ve la clave de otra |

Orden dentro de `GenerarCobro`: **rol → bloqueo y búsqueda por clave → (si existe: comparar y
devolver) → cliente → comprobante y saldo → link → persistir con la clave → bitácora**. La búsqueda
va antes de validar el cliente a propósito: si el cliente se desactivó después del primer pedido,
el reintento igual tiene que devolver el cobro que ya existe, no un 422.

## Diseño

- **Dominio**: `Cobro` gana el atributo opcional `clave_idempotencia: UUID | None = None` (los
  cobros existentes no la tienen) y un método puro
  `es_el_mismo_pedido(cliente_id, monto, descripcion, comprobante_id) -> bool` que compara contra
  el monto **ya redondeado** con `redondear` (`ROUND_HALF_UP`), así `"1210.005"` y `"1210.01"` son
  el mismo pedido y nunca pasa por `float`. Se comparan los campos del cobro en lugar de guardar una
  huella del cuerpo (P6): son inmutables después de crear el cobro (no hay caso de uso que edite
  cliente, monto, concepto ni comprobante) y no agregan una columna que pueda divergir.
- **Aplicación**:
  - `GenerarCobro.ejecutar` recibe `clave_idempotencia: UUID` (obligatoria: el único llamador es el
    router). Errores nuevos en `application/errors.py`: `ClaveDeIdempotenciaReusada`
    (`EntradaInvalida`, 422). La falta y el formato inválido se resuelven en el router (son forma
    del pedido HTTP, no regla del caso de uso) con `EntradaInvalida` y los textos de la tabla.
  - En una repetición **no** se publica `generar_cobro` en la bitácora (no hubo efecto); se deja
    un log estructurado `cobro_pedido_repetido` con `cobro_id` y sin datos personales.
  - **Tamaño de archivos (`CLAUDE.md` §5, ≤ 400)**: `application/cobros.py` ya tiene **415** líneas
    (preexistente) y `application/ports.py` **400** exactas. `GenerarCobro` y sus dos helpers pasan
    a `application/generacion_de_cobro.py` (nuevo) y se actualizan los imports del router y de los
    tests (P8). Para el método nuevo del puerto se mueve un bloque cohesivo de `ports.py` (propuesta:
    `PortEnvioDeRecordatorio`, `PasoDeCadena` y `PortCadenaDeEscalamiento` a
    `application/ports_de_recordatorios.py`).
- **Puertos y adaptadores**:
  - `PortRepositorioCobro.buscar_por_clave_bloqueada(clave: UUID) -> Cobro | None`: toma
    `pg_advisory_xact_lock(ESPACIO_CLAVE_DE_COBRO, hashtext(empresa_id || ':' || clave))` y después
    lee el cobro con esa clave. El bloqueo se libera al terminar la transacción de la unidad de
    trabajo (commit o rollback), igual que `tomar_con_familia_bloqueada`. Un choque de hash solo hace
    esperar a dos claves distintas; no expone datos.
  - `RepositorioCobroPostgres` (`infrastructure/repositories.py`): implementa el método y mapea la
    columna en `_a_dominio` / `agregar`. `CobroORM` gana la columna y el índice.
  - **Respaldo del índice**: con el bloqueo, dos inserciones con la misma clave no pueden competir;
    igual, si la restricción `uq_cobro_clave_idempotencia` saltara, el repositorio traduce ese
    `IntegrityError` (solo esa restricción, por nombre) a `PedidoEnCurso` (`InvarianteViolada`, 409:
    «Ese pedido ya se esta procesando. Intente nuevamente.»). Nunca un 500, nunca un `except
    Exception`.
- **Otros contextos**: ninguno nuevo. Las dependencias `payments → master_data` y
  `payments → billing` siguen como están; no hace falta ADR por el Context Map.
- **ADR**: `docs/adr/README.md` pide ADR para una «idempotency strategy» que afecta a más de un
  módulo, y este contrato lo va a reusar `billing` (#97). Se propone **ADR-0013 «Request
  idempotency key»** (en inglés, número = el siguiente libre al implementar) con: nombre del
  encabezado, formato UUID, alcance `(empresa_id, clave)`, códigos de la tabla de arriba, bloqueo
  consultivo + índice único, y la regla de que la clave vive con el agregado que crea (P7).
- **Frontend**:
  - `features/payments/api/cobro.ts`: `generarCobro(datos, clave)` manda `X-Idempotency-Key: clave`.
  - `features/payments/components/NuevoCobro.tsx`: la clave se genera **una vez por formulario**
    (`useState(() => crypto.randomUUID())`) y se reusa en cada envío, reintento o doble clic; se
    **renueva solo después de un éxito**, dentro del `navegar` de `useAccionConNavegacion`, antes del
    `push`. Así, si el navegador restaura la pantalla desde el bfcache (el caso que
    `useAccionConNavegacion` ya atiende con `pageshow`), un nuevo envío es un cobro nuevo y no
    devuelve el anterior. Tras un error **no** se renueva: si el primer pedido sí llegó (504 del
    BFF), el reintento tiene que encontrarlo (P9). Ante `ClaveDeIdempotenciaReusada` se muestra el
    texto del backend y un enlace a `/cobros`.
  - BFF `app/api/cobros/route.ts`: el `POST` reenvía el encabezado del pedido entrante.
    `app/api/usuarios/_proxy.ts::reenviarAlBackend` gana un parámetro opcional `cabeceras`
    (aditivo: las otras ~90 rutas no cambian) que llega a `llamarApi({ headers })`, que ya lo
    soporta. #97 necesita lo mismo para `comprobantes`: se avisa a Cristian (P10).
  - `crypto.randomUUID()` está disponible en el navegador en contexto seguro (https en staging y
    `localhost` en desarrollo); el entorno de tests (vitest/jsdom sobre Node 18+) también lo tiene.

## Infraestructura

- **Migraciones**: una migración nueva de Alembic, **número = el siguiente libre al implementar**
  (hoy el head de `develop` es 0032; `usos-de-faq-por-periodo` (U4) probablemente tome 0033, y
  entonces esta es 0034 con `down_revision` al head real en ese momento).
  - `cobro.clave_idempotencia UUID NULL` (sin default: los cobros existentes quedan en `NULL`, no se
    les inventa una clave; **sin backfill**).
  - Índice único parcial `uq_cobro_clave_idempotencia ON cobro (empresa_id, clave_idempotencia)
    WHERE clave_idempotencia IS NOT NULL`, con la misma expresión declarada en `CobroORM`.
  - RLS: la tabla ya tiene la política por `empresa_id`; la columna nueva no cambia permisos.
  - **Reversible con pérdida declarada**: `downgrade` borra índice y columna; se pierden las claves
    (un reintento posterior con una clave vieja crearía otro cobro).
- **Trabajo asíncrono**: no aplica. La creación del cobro es síncrona (201).
- **Configuración**: no aplica. Sin variables nuevas en ningún `.env.example`.
- **Integraciones externas**: no se agrega ninguna. MercadoPago conserva timeout, reintentos y el
  aplanado a `PasarelaNoDisponible`. Lo nuevo es que un pedido repetido **no** llega a MercadoPago, y
  que dos pedidos concurrentes no dejan una preferencia huérfana pagable (el segundo nunca la pide).
  Tests sin red: pasarela simulada / `httpx.MockTransport` como hoy.

## Riesgos que obligan a tests (marcar los que apliquen)
- [x] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → la comparación del pedido repetido usa el
  monto redondeado: `"1210.005"` contra un cobro de `1210.01` es el mismo pedido; `"1210.02"` no
- [ ] Toca comprobantes fiscales / CAE → no aplica (solo se lee el comprobante asociado, como hoy)
- [x] Entrega duplicada (análogo al webhook) → un mismo pedido repetido o concurrente, **un solo**
  cobro y **una sola** llamada a MercadoPago
- [x] Agrega datos con `empresa_id` → la misma clave en dos empresas son dos cobros; una empresa no
  puede recuperar el cobro de otra adivinando su clave (RLS + índice con `empresa_id`)
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales a un LLM → no aplica

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/payments/domain/cobro.py` (`clave_idempotencia`, `es_el_mismo_pedido`)
- [x] `backend/src/cheatsheet/contexts/payments/application/generacion_de_cobro.py` (nuevo: `GenerarCobro` extraído)
- [x] `backend/src/cheatsheet/contexts/payments/application/cobros.py` (sale `GenerarCobro`)
- [x] `backend/src/cheatsheet/contexts/payments/application/errors.py` (`ClaveDeIdempotenciaReusada`, `PedidoEnCurso`)
- [x] `backend/src/cheatsheet/contexts/payments/application/ports.py` (`buscar_por_clave_bloqueada`)
- [x] `backend/src/cheatsheet/contexts/payments/application/ports_de_recordatorios.py` (nuevo: bloque movido)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/models.py` (columna e índice)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/repositories.py` (bloqueo, lectura, mapeo, traducción del `IntegrityError`)
- [x] `backend/src/cheatsheet/api/routers/cobros.py` (encabezado `X-Idempotency-Key`, validación, imports)
- [x] `backend/migrations/versions/0034_clave_de_idempotencia_de_cobro.py` (nuevo)
- [x] `backend/tests/contexts/payments/domain/…` (`es_el_mismo_pedido`)
- [x] `backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py` (y los imports movidos en `test_confirmacion.py` u otros que importen `GenerarCobro`)
- [x] `backend/tests/contexts/payments/application/test_generacion_idempotente.py` (nuevo)
- [x] `backend/tests/integracion/test_api_mercadopago.py` (los `POST /cobros` existentes mandan la clave; casos nuevos)
- [x] `backend/tests/integracion/test_cobros_postgres.py` (índice, RLS, concurrencia)

### Frontend
- [x] `frontend/src/features/payments/api/cobro.ts` (`generarCobro(datos, clave)`)
- [x] `frontend/src/features/payments/api/__tests__/cobro.test.ts`
- [x] `frontend/src/features/payments/components/NuevoCobro.tsx`
- [x] `frontend/src/features/payments/components/__tests__/pantallas.test.tsx`
- [x] `frontend/src/app/api/cobros/route.ts` (reenvía el encabezado)
- [x] `frontend/src/app/api/usuarios/_proxy.ts` (parámetro opcional `cabeceras`)
- [x] `frontend/src/app/api/cobros/__tests__/rutas.test.ts`

### Docs
- [x] `docs/adr/0013-request-idempotency-key.md` (nuevo, en inglés; aceptado en #100)
- [x] `docs/aidlc/units.md` (fila de la unidad: `Rama`, estado; ya figuraba «en curso»)
- [x] `docs/aidlc/units/cobro-con-clave-de-idempotencia.md` (este plan)

## Casos de prueba

Modo: **test primero**. Los casos RED tienen que fallar antes de tocar el código. Los de PostgreSQL
y API no corren en la máquina local (sin Docker): se escriben y los confirma la CI.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: `es_el_mismo_pedido` es verdadero con los mismos datos y con `1210.005` contra `1210.01`; falso si cambia cliente, monto, concepto o comprobante (incluido `None` contra un id) | unit (dominio) | hecho (verde en local) |
| 2 | RED: `GenerarCobro` con una clave nueva crea el cobro **con la clave** y llama una vez a la pasarela | unit | hecho (verde en local) |
| 3 | RED: segunda ejecución con la misma clave y los mismos datos → devuelve el **mismo** cobro (mismo id), la pasarela no se vuelve a llamar, no se persiste otro, no hay evento de bitácora nuevo | unit | hecho (verde en local) |
| 4 | RED: misma clave, otro monto (y otro cliente, concepto, comprobante) → `ClaveDeIdempotenciaReusada`, sin pasarela ni persistencia | unit | hecho (verde en local) |
| 5 | Repetición cuando el cliente ya está inactivo → devuelve el cobro original (la búsqueda va antes de validar el cliente) | unit | hecho (verde en local) |
| 6 | Solo Lectura con clave → rechazado por rol **antes** de buscar la clave (el fake no recibe consultas) | unit | hecho (verde en local) |
| 7 | Si la pasarela falla en el primer pedido, nada queda guardado y un segundo pedido con la misma clave crea el cobro | unit | hecho (verde en local) |
| 8 | RED: `POST /cobros` sin `X-Idempotency-Key` → 422 con el texto de la tabla; con un valor que no es UUID → 422 | integración (API) | hecho (verde en local) |
| 9 | RED: dos `POST /cobros` secuenciales con la misma clave → los dos 201 con el mismo `id`; MercadoPago (mock) recibió **una** preferencia | integración (API) | escrito; lo confirma la CI (sin Docker) |
| 10 | RED: misma clave con otro cuerpo → 422 `ClaveDeIdempotenciaReusada` | integración (API) | escrito; lo confirma la CI (sin Docker) |
| 11 | Los `POST /cobros` existentes de `test_api_mercadopago.py` siguen pasando mandando una clave | integración (API) | escrito; lo confirma la CI (sin Docker) |
| 12 | RED: dos pedidos **concurrentes** con la misma clave (dos sesiones, la pasarela del primero demora) → una sola fila, una sola llamada a la pasarela, las dos respuestas con el mismo id | integración (PostgreSQL) | escrito; lo confirma la CI (sin Docker) |
| 13 | RED: la misma clave en dos empresas → dos cobros; la empresa B no obtiene el cobro de A con la clave de A (RLS) | integración (PostgreSQL) | escrito; lo confirma la CI (sin Docker) |
| 14 | El índice único rechaza a nivel base una segunda fila `(empresa_id, clave)` y el repositorio la traduce a `PedidoEnCurso` (409), no a 500 | integración (PostgreSQL) | escrito; lo confirma la CI (sin Docker) |
| 15 | La migración sube y baja limpia sobre una base con cobros existentes (quedan con `NULL`) | integración (PostgreSQL) | escrito; lo confirma la CI (sin Docker) |
| 16 | RED: `generarCobro` manda `X-Idempotency-Key` con la clave recibida | unit (frontend) | hecho (verde en local) |
| 17 | RED: el BFF `POST /api/cobros` reenvía el encabezado al backend; sin encabezado no inventa uno | unit (frontend) | hecho (verde en local) |
| 18 | RED: `NuevoCobro` manda la **misma** clave en dos envíos tras un error (p. ej. 504) | unit (frontend) | hecho (verde en local) |
| 19 | RED: después de un éxito la clave se renueva (un nuevo envío desde la misma instancia usa otra) | unit (frontend) | hecho (verde en local) |
| 20 | Ante `ClaveDeIdempotenciaReusada` se muestra el texto del backend y el enlace a `/cobros` | unit (frontend) | hecho (verde en local) |
| 21 | `reenviarAlBackend` sin `cabeceras` se comporta exactamente como antes (las demás rutas) | unit (frontend) | hecho (verde en local) |
| 22 | En staging (Render): generar un cobro, volver con «Atrás» y generar otro → dos cobros distintos; cortar la red tras enviar y reintentar → un solo cobro | manual | pendiente: registrado en `docs/aidlc/TODO.md` §22.27 |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-06 | Aprobado por Luciano con las recomendaciones de las diez preguntas. El ADR-0013 se escribe y se acepta dentro de esta unidad, antes del código |
| 1 · Cierre | 2026-10-06 | El Gate 1 queda cerrado porque el ADR-0013 fue aceptado (PR #100, merge `4e79b1c`); desde ahí se escribe el código |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- Gate 1 (2026-10-06): Pregunta 1 → la clave es obligatoria; sin ella, 422.
- Gate 1 (2026-10-06): Pregunta 2 → el mismo pedido repetido devuelve 201 con el cobro original en su estado actual.
- Gate 1 (2026-10-06): Pregunta 3 → misma clave con otros datos, 422.
- Gate 1 (2026-10-06): Pregunta 4 → la clave es un UUID.
- Gate 1 (2026-10-06): Pregunta 5 → con dos pedidos simultáneos, el segundo espera al primero (lock transaccional de PostgreSQL).
- Gate 1 (2026-10-06): Pregunta 6 → «el mismo pedido» se reconoce comparando los campos del cobro, sin columna de huella.
- Gate 1 (2026-10-06): Pregunta 7 → ADR-0013 «Request idempotency key» dentro de esta unidad.
- Gate 1 (2026-10-06): Pregunta 8 → `GenerarCobro` se extrae a su propio módulo.
- Gate 1 (2026-10-06): Pregunta 9 → el panel renueva la clave solo después de un éxito.
- Gate 1 (2026-10-06): Pregunta 10 → el cambio de `_proxy.ts` y el ADR se hacen acá, y se avisa al responsable de #97 para que los reutilice.
- Migración: `0034`, porque `0033` la toma `usos-de-faq-por-periodo` (#99), que se mergea antes.
- Implementación: `application/cobros.py` pasa a 294 líneas y `GenerarCobro` vive en `application/generacion_de_cobro.py`; `exigir_gestor` (antes `_exigir_gestor`) es público porque lo comparten los dos módulos, y los tres `MENSAJE_*` que solo usaba `GenerarCobro` se mudaron con él.
- Implementación: `repositories.py` habría quedado sobre 400 líneas con el bloqueo, así que el mapeo `Cobro` ↔ `CobroORM` salió a `infrastructure/mapeo_de_cobro.py` (`a_dominio`, `a_fila`).
- Implementación: la validación del encabezado vive en `api/clave_de_pedido.py` (dependencia de FastAPI reutilizable por `billing`, #97), no en `routers/cobros.py`, que quedó en 385 líneas.
- Implementación: los tests contra PostgreSQL de la clave están en archivos nuevos (`test_cobro_clave_postgres.py`, `test_migracion_0034.py`) y no en `test_cobros_postgres.py` (997 líneas); los casos de API sí van en `test_api_mercadopago.py`.

## Preguntas para el Gate 1 (responder en bloque)

1. **¿La clave es obligatoria?** Recomendación: **sí**, 422 sin ella. El único llamador de `POST
   /cobros` es el panel a través del BFF, que la manda siempre; hacerla opcional deja abierto
   exactamente el hueco que #97 describe («un cliente que no es el panel»). Costo: cualquier cliente
   futuro de la API tiene que mandarla (se documenta en el ADR). Alternativa: opcional, con
   protección solo cuando viene.
2. **¿Qué código devuelve la repetición del mismo pedido?** Recomendación: **201** con el cobro en su
   estado actual, igual que la primera respuesta. El cliente no tiene que distinguir «lo creé» de
   «ya estaba» (para eso es la clave), y el BFF de todos modos lo aplana a 200. Alternativa: 200
   para marcar que no se creó nada (más informativo, obliga a otra rama en el router).
3. **Misma clave con otros datos: ¿409 o 422?** Recomendación: **422**. Es un error del pedido, no
   un conflicto con el estado del negocio (en este sistema 409 = `InvarianteViolada`); es lo que usa
   el borrador IETF de `Idempotency-Key`; y el BFF solo reenvía el texto de los 422, así que con 409
   habría que tocar `respuestaDeError`. El 409 queda reservado para el respaldo «pedido en curso».
4. **¿Formato de la clave?** Recomendación: **UUID** (columna `UUID`, como
   `reembolso_clave_idempotencia`), validado en el router. Acota el tamaño y el panel lo genera con
   `crypto.randomUUID()`. Alternativa: texto libre hasta 255 caracteres (más flexible para otros
   clientes, más superficie de validación). Debe ser el mismo en #97.
5. **¿Qué pasa con dos pedidos simultáneos?** Recomendación: **el segundo espera** al primero
   (bloqueo consultivo por `(empresa, clave)`) y devuelve el mismo cobro. Alternativa: no esperar y
   contestar 409 «en curso» (`pg_try_advisory_xact_lock`): libera antes la conexión, pero obliga al
   panel a reintentar. La espera está acotada por los timeouts de MercadoPago que ya existen.
6. **¿Cómo se reconoce «el mismo pedido»?** Recomendación: **comparando los campos del cobro**
   (cliente, monto redondeado, concepto, comprobante), sin columna de huella. Alternativa: guardar un
   SHA-256 del cuerpo canónico (lo que sugiere el borrador IETF); es una columna más y una regla de
   canonicalización que puede divergir del dominio (`"1210.005"` contra `"1210.01"`).
7. **¿ADR dentro de esta unidad?** Recomendación: **sí**, ADR-0013 «Request idempotency key» corto,
   porque `docs/adr/README.md` lo exige para una estrategia de idempotencia que cruza módulos, y
   así #97 sigue un contrato escrito en lugar de copiar código. Nota: el nombre estándar del
   borrador IETF es `Idempotency-Key`; se mantiene `X-Idempotency-Key` por lo ya acordado con #97 y
   porque es el que usa MercadoPago.
8. **¿Se extrae `GenerarCobro` a su propio módulo?** Recomendación: **sí**. `application/cobros.py`
   ya está en 415 líneas (sobre el tope de 400 de `CLAUDE.md` §5, preexistente) y `ports.py` en 400;
   agregar sin extraer los empuja más. Se mueven imports del router y de los tests, sin cambiar
   comportamiento.
9. **Frontend: ¿cuándo se renueva la clave?** Recomendación: **solo después de un éxito**, nunca al
   editar el formulario tras un error. Si el primer pedido llegó pero la respuesta no (504), editar el
   monto y reenviar con clave nueva crearía un segundo cobro; con la misma clave se recibe el 422 y
   el enlace al listado. Costo: quien corrige un monto después de un 504 ve ese aviso en vez de un
   cobro nuevo.
10. **Coordinación con #97 (Cristian):** el cambio en `app/api/usuarios/_proxy.ts` (parámetro
    opcional `cabeceras`) y el ADR los necesita también `billing`. Recomendación: **hacerlos en esta
    unidad** y avisarle a Cristian que los reuse; si #97 llega primero a `develop`, se reusa lo suyo y
    se ajusta este plan.
