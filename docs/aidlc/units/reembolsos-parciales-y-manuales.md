# Unidad: reembolsos-parciales-y-manuales

**HUs**: HU-E6-05 (y HU-E6-06 RN-05, HU-E6-01 RN-02) **Contexto dueño**: payments (con una escritura en billing por su capa de aplicación y una lectura en reporting que hereda la métrica) **Rama**: feature/payments-reembolsos-parciales-y-manuales

> Origen: revisión del profesor de 2026-09, [ADR-0009](../../adr/0009-review-adjustments-scope-change.md),
> decisión D93 (`docs/aidlc/epicas/06-cobros-y-recordatorios/decisiones.md`) y el modelo ya decidido en
> [ADR-0010](../../adr/0010-payment-date-method-and-refunds.md) (Aceptado), puntos 4 a 7. La rama sale de
> `feature/payments-fecha-de-pago` (cadena de ramas: PR #50 sobre #49 sobre #48 sobre #45); su PR
> apunta a esa rama y pasa a `develop` cuando la cadena llegue. Tamaño del mapa: M; **con todo lo que
> pide la historia queda en el borde de L** (ver pregunta 2, que propone sacar un barrido a una unidad
> chica). `cobro-por-transferencia` depende de esta unidad. **Esta unidad no re-decide el modelo**: lo
> implementa, y cierra en este Gate solo lo que el ADR dejó explícitamente para acá (la lista exacta de
> columnas, punto 4).

## Qué hace

Hoy un cobro solo admite **un** reembolso, por la API de MercadoPago, que se confirma en el mismo
request y deja el cobro en `REEMBOLSADO` aunque se haya devuelto una parte; si MercadoPago lo rechaza,
el rechazo **no queda escrito** (ni el estado ni la bitácora), y si MercadoPago no contesta, la marca de
«en proceso» también se pierde aunque la plata pueda haber salido. Esta unidad hace que:

- un cobro pagado por link se pueda reembolsar **total o parcialmente**, varias veces, hasta su monto;
  el estado pasa a `REEMBOLSADO_PARCIAL` («Reembolsado parcialmente») o a `REEMBOLSADO` según el
  acumulado, y el rechazo o la falta de respuesta de MercadoPago **quedan registrados**;
- un cobro pagado por transferencia no ofrezca la API y sí **«Registrar reembolso»** (monto, fecha de
  devolución, referencia opcional, motivo), declarativo;
- cada reembolso sea una **fila inmutable** con fecha, origen, autor y referencia, y un error se corrija
  con una **fila de corrección visible** que puede bajar el estado (ADR-0010 punto 5);
- el reembolso **suba el saldo** del comprobante asociado, advierta que corresponde una nota de crédito
  (sin emitirla) y **reste de «cobrado» en el período de la devolución** (RN-11), no en el del pago.

**Fuera de esta unidad:**
- **El barrido automático que concilia reembolsos que quedaron «en proceso»** (MercadoPago contestó
  `in_process` o no contestó): propuesta de unidad nueva `reembolsos-en-vuelo` (pregunta 2). Acá el
  administrador lo destraba con «Actualizar estado», que usa el mismo caso de uso que el barrido va a
  llamar.
- Registrar una transferencia y que un cobro llegue a `TRANSFERENCIA` (HU-E6-08, D94): unidad
  `cobro-por-transferencia`. Hasta que exista, «Registrar reembolso» solo se ejercita en tests (pregunta 9).
- Detectar reembolsos hechos por fuera del sistema desde el panel de MercadoPago sobre un cobro por link
  (no hay notificación verificada que lo cuente; ver «Verificaciones contra el sandbox»).
- Emitir la nota de crédito (HU-E5-04): solo se advierte y se ofrece el enlace (RN-09, D89).
- El `float(cobro.monto)` de `pasarela.py:85` (crear link): sigue en `TODO.md` §20.6. El de reembolsar
  (`pasarela.py:163`) **sí** entra (pregunta 3).
- «Cobrado por semana» y el tablero de reportería (HU-E10-01, D98): unidad `indicadores-de-cobranza`.
  Reporting hereda el nuevo «cobrado» neto porque reusa `MetricasDelPeriodo`, y nada más.
- Pasar `application/cobros.py` por debajo de 400 líneas (hallazgo H8): esta unidad no le suma líneas,
  le saca `ReembolsarCobro`.
- Un `CHECK` sobre los valores de `cobro.estado` (hallazgo H13): no existe hoy y no se agrega.

## Las preguntas que el mapa dejó para este Gate

### 1. ¿Esta unidad absorbe `reembolso-rechazado-persistido`? — **hallazgo H1**

La unidad `reembolso-rechazado-persistido` (registrada en `units.md` de la rama
`fix/identity-revocacion-por-reuso`, todavía no en esta cadena) corrige que `ReembolsarCobro` guarda
el rechazo y levanta **dentro** de `unidad_de_trabajo`: la excepción descarta la transacción, así que
el cobro vuelve a como estaba **y el evento `Resultado.ERROR` se pierde** — el administrador no recibe
la notificación que pide RN-03. El patrón de arreglo está documentado en el docstring de
`unidad_de_trabajo` en esa rama: capturar dentro del cuerpo del `async for`, dejar terminar el ciclo y
re-levantar después.

El defecto es **más grave** que un rechazo perdido, y el comentario del código dice lo contrario de lo
que pasa (`cobros.py:444`: «Persistido antes de pedirlo»):
- Si MercadoPago no contesta (`PasarelaNoDisponible` tras tres intentos), el `guardar` previo se
  deshace igual: **la plata puede haber salido y no queda rastro**.
- `_pedir` genera un `X-Idempotency-Key` nuevo (`uuid4`) en cada llamada: si el administrador reintenta
  después de un timeout, MercadoPago recibe **otra** clave y puede ejecutar **un segundo reembolso**.

**Recomendación: sí, absorberla**, y cerrar esa unidad en el mapa como «absorbida por
`reembolsos-parciales-y-manuales`». Esta unidad reescribe ese mismo caso de uso (lo parte en dos
transacciones, ver «Diseño»); arreglarlo por separado sería escribir dos veces un código que esta unidad
reemplaza, y dos ramas tocando `ReembolsarCobro` a la vez chocan. Lo que se paga: la unidad crece un
poco y el arreglo llega recién con esta cadena, no por la rama rápida de `fix/`. Alternativa: dejarla
aparte y mergearla primero sobre `develop`; solo conviene si esta cadena va a tardar semanas en llegar.

### 2. ¿Cómo se cumple RN-04 (asíncrono) sin que la unidad deje de ser M? — **hallazgo H3**

Hoy el reembolso se confirma en el mismo request (`cobros.py:467`), contra RN-04 y D27. MercadoPago
responde el `POST /v1/payments/{id}/refunds` con un objeto de reembolso que trae `status`
(referencia oficial; el ejemplo muestra `approved`, **el resto de los valores no está enumerado**), y
existe `GET /v1/payments/{id}/refunds/{refund_id}` para consultarlo después. Que un reembolso quede
`in_process` y cuándo se resuelve **no está verificado**.

**Recomendación:**
- **Dos transacciones** en el request, con la marca de «en proceso» comprometida **antes** de hablar con
  MercadoPago: `SolicitarReembolso` (T1: bloquea el cobro, valida el monto, guarda
  `reembolso_solicitado_en`, el monto pedido y una **clave de idempotencia persistida**; commit) y
  `EnviarReembolso` (T2: llama a MercadoPago con esa clave y registra lo que contestó).
- Resultado `approved` → se confirma en T2 (fila `reembolso`, acumulado, estado, saldo, bitácora).
  `rejected` o 4xx → se registra el rechazo (se limpia la marca, evento `ERROR` con el motivo de
  MercadoPago), **commit**, y recién después se levanta para que la pantalla muestre el motivo.
  `in_process` o sin respuesta → **queda en proceso**, con el id de MercadoPago si lo hubo, commit, y la
  pantalla dice «Reembolso en proceso».
- **«Actualizar estado»** (solo Administrador, solo con un reembolso en proceso): con id de MercadoPago
  consulta `GET …/refunds/{refund_id}`; sin id reenvía el `POST` **con la misma clave**. Es el mismo caso
  de uso (`ActualizarReembolso`) que un barrido llamaría.
- **El barrido de Beat que hace eso solo** (mismo patrón que D17 en `billing`: función `SECURITY
  DEFINER` para listar empresas con reembolsos en vuelo, fan-out por empresa, ventana de vuelo) va a una
  **unidad nueva `reembolsos-en-vuelo`** (S, depende de esta). Con él adentro esta unidad es L.

Lo que se paga: hasta que llegue el barrido, un reembolso `in_process` espera a que alguien apriete
«Actualizar estado», y mientras tanto ese cobro no acepta otro reembolso (ver pregunta 4, un solo
reembolso en vuelo por cobro). Alternativa A: todo asíncrono ya (tarea Celery + barrido): la unidad pasa a
L y habría que partir por otro lado (sacar el registro manual, que igual no se puede demostrar hasta
`cobro-por-transferencia`). Alternativa B: confirmar solo con la respuesta del `POST` y no ofrecer
«Actualizar estado»: un `in_process` queda trabado para siempre. No las recomiendo. **Si el Gate acepta,
el mapa se actualiza antes de codear**: fila nueva `reembolsos-en-vuelo` (payments, HU-E6-05, depende
de esta) y `reembolso-rechazado-persistido` marcada absorbida.

### 3. ¿Se arregla acá el `float(monto)` del reembolso (`pasarela.py:163`)?

`CLAUDE.md` §3.5 prohíbe `float` para plata, y esta unidad es dueña del reembolso. Con dos decimales
y montos hasta 100.000.000,00 el `float` hoy no pierde un centavo al serializarse (la representación
más corta de un `float` que viene de un `Decimal` de dos decimales es la misma cadena), pero es la regla
absoluta y es la línea que esta unidad reescribe. **Recomendación: sí.** El cuerpo del reembolso se arma
con el `Decimal` ya redondeado como **literal numérico JSON** (`amount` es `number` en la referencia; no
se manda como texto porque no está verificado que MercadoPago lo acepte). El `float` de `crear_link`
(`pasarela.py:85`) **no se toca**: es otra operación y sigue en `TODO.md` §20.6; el ayudante queda
listo para que quien lo tome lo reuse.

### 4. La lista exacta de columnas (ADR-0010 punto 4 lo deja para este Gate)

**Tabla `reembolso`** (una fila por reembolso o corrección, `SELECT` e `INSERT` solamente):

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `uuid` PK | |
| `empresa_id` | `uuid NOT NULL` | RLS `aislamiento_por_empresa`, `FORCE` |
| `cobro_id` | `uuid NOT NULL` FK `cobro(id)` | mismo contexto; sin `ON DELETE CASCADE` (el cobro no se borra) |
| `monto` | `NUMERIC(14,2) NOT NULL` | `<> 0`; negativo **si y solo si** es corrección |
| `fecha_devolucion` | `timestamptz NOT NULL` | cuándo volvió el dinero (UTC) |
| `origen` | `varchar(20) NOT NULL` | `CHECK IN ('API_MERCADOPAGO','MANUAL')` |
| `referencia` | `varchar(120) NULL` | la del administrador (número de operación o comprobante bancario) |
| `motivo` | `varchar(500) NULL` | obligatorio si `origen = 'MANUAL'` (incluye correcciones) |
| `corrige_a` | `uuid NULL` FK `reembolso(id)` | índice único parcial: **una fila se corrige una sola vez** |
| `mp_refund_id` | `varchar(120) NULL` | id del reembolso en MercadoPago; índice único `(empresa_id, mp_refund_id)` parcial |
| `registrado_por` | `uuid NULL` | `NULL` cuando confirma el sistema; sin FK (otro contexto, como `turno_id`) |
| `created_at` | `timestamptz NOT NULL` | |

Índices: `(empresa_id, fecha_devolucion)` para la métrica; `(cobro_id)` para el historial.
`mp_refund_id` va aparte de `referencia` porque tiene otra semántica: es la **clave de idempotencia de
la confirmación** (una misma respuesta de MercadoPago, una sola fila), como `mp_payment_id` lo es del
pago (D20); `referencia` es texto libre de una persona y no puede ser único.

**En `cobro`**: `monto_reembolsado` pasa a `NOT NULL DEFAULT 0` con `CHECK (0 <= monto_reembolsado AND
monto_reembolsado <= monto)` (hoy prohíbe el cero, que una corrección total necesita, hallazgo H7), y
el reembolso en vuelo gana tres columnas que viven **mientras** está en vuelo (D27 sigue: no es un
estado): `reembolso_solicitado_monto NUMERIC(14,2)`, `reembolso_clave_idempotencia uuid` y
`reembolso_mp_refund_id varchar(120)`, con un `CHECK` de «todas o ninguna» junto con
`reembolso_solicitado_en` (salvo el id de MercadoPago, que puede faltar). Más un `CHECK` que ata el
estado al acumulado: `REEMBOLSADO_PARCIAL` ⇔ `0 < acumulado < monto`, `REEMBOLSADO` ⇔ `acumulado = monto`.

**Recomendación: esta lista.** Alternativa: guardar la solicitud en vuelo como una fila de `reembolso`
con estado. Se descarta: obliga a `UPDATE` sobre una tabla que el ADR declara solo-inserción, y una
fila que después «se rechaza» es un registro que dice algo que no pasó.

### 5. ¿Cómo es exactamente una corrección?

RN-08 y el ADR dicen «fila negativa que apunta a la que corrige», no dicen cuánto corrige.
**Recomendación: una corrección anula la fila entera** (`monto = -original`), exige motivo, y si el
error era de monto se registra después una fila nueva con el monto correcto. Solo se corrigen filas
`MANUAL` que no sean correcciones ni estén ya corregidas (índice único sobre `corrige_a`, que además
cierra la carrera de dos correcciones simultáneas). Las filas `API_MERCADOPAGO` **no se corrigen**: el
dinero salió por MercadoPago y MercadoPago es la fuente de verdad. El estado se recalcula del
acumulado, así que una corrección puede **bajarlo** (`REEMBOLSADO → REEMBOLSADO_PARCIAL → APROBADO`,
ADR-0010 punto 5, decisión P8 de `fecha-de-pago`). Lo que se paga: corregir 1000 → 100 son dos filas y
no una. Alternativa: corrección parcial (fila por la diferencia): una fila con dos correcciones es
difícil de leer en el historial y de acotar en la base.

### 6. ¿Qué pasa con los reembolsos que ya existen?

Hoy un cobro `REEMBOLSADO` tiene `monto_reembolsado` y ninguna fila, y si el reembolso fue parcial igual
figura `REEMBOLSADO` (epic-6 `pendientes.md`, ítem 7). **Recomendación:** la migración 0027 crea **una
fila por cada cobro `REEMBOLSADO`** con `monto = monto_reembolsado`, `origen = 'API_MERCADOPAGO'`
(hasta hoy no había otro camino), `fecha_devolucion = updated_at` (la única fecha que hay),
`registrado_por = NULL` y `motivo = 'Registrado antes de ADR-0010; fecha aproximada'`; y **re-deriva el
estado** del acumulado: los parciales pasan a `REEMBOLSADO_PARCIAL`. Un `REEMBOLSADO` sin
`monto_reembolsado` (no debería existir) se informa por `NOTICE` y el `CHECK` de estado se agrega `NOT
VALID`, mismo mecanismo que la 0025/0026; no se inventa un monto. Lo que se paga: una fecha de
devolución aproximada que no queda marcada en una columna. Alternativa: agregar
`fecha_devolucion_aproximada` a la tabla, simétrica a `fecha_pago_aproximada`; más honesta, una columna
más para filas que en staging son un puñado. Si el Gate la prefiere, entra sin cambiar el resto.

### 7. «Cobrado» y tasa de cobro con reembolsos — **hallazgo H4** (H2 de `fecha-de-pago`)

Hoy «cobrado» suma solo `APROBADO` por `fecha_pago`: un reembolso **saca al cobro entero** de su
período de pago, y un parcial lo saca igual. **Recomendación:**
- **Cobrado** = Σ `monto` de cobros `APROBADO`, `REEMBOLSADO_PARCIAL` y `REEMBOLSADO` con `fecha_pago` en
  el período − Σ `reembolso.monto` con `fecha_devolucion` en el período (las correcciones, negativas,
  suman de vuelta). Puede dar **negativo** en un período que devolvió más de lo que cobró, y se muestra
  así: es lo que pasó con la caja. Se suma en la base, en `Decimal`, y `reembolso` se consulta sin join
  contra `cobro` (ADR-0010 punto 6).
- **Tasa de cobro**: el numerador `cobrado_de_lo_creado` pasa a contar los tres estados pagados **por su
  monto bruto** (un cobro que se pagó y después se devolvió **se cobró**; el reembolso no es una falla de
  cobranza). Así un cobro reembolsado deja de desaparecer del numerador y del denominador. Sigue sin
  pasar de 100 %.
- La forma de la respuesta HTTP no cambia (`cobrado`, `pendiente`, `en_mora`, `tasa_de_cobro`).

Alternativa para la tasa: medirla neta de reembolsos; mezcla «qué se cobró» con «qué se devolvió» y la
puede bajar meses después de cerrado el período. No la recomiendo.

### 8. La fecha de un reembolso manual

La historia pide «fecha en que se devolvió el dinero»: un **día**, no un instante. El ADR fija
`timestamptz`. **Recomendación:** el formulario pide un día; se guarda como **las 12:00 de ese día en
hora de Argentina** (15:00 UTC). El mediodía cae en el mismo día en UTC y en Argentina, así que el
reembolso no cambia de período según qué grilla use el filtro (hoy los límites del período se arman en
UTC, `MetricasDelPeriodo`). Se valida: no posterior a hoy (Argentina) ni anterior al día de
`fecha_pago`. Para un reembolso por API la fecha es el `date_created` que informa MercadoPago si es
plausible (con zona horaria, no en el futuro más la tolerancia de reloj, no anterior a `fecha_pago`),
y si no, el momento de la confirmación. Alternativa: columna `date` solo para manuales; dos tipos para
un mismo hecho en la misma columna no entran.

### 9. «Registrar reembolso» solo para transferencias, que todavía no existen

RN-07 lo ofrece para cobros por transferencia, y **ningún cobro llega a `TRANSFERENCIA` hasta
`cobro-por-transferencia`**, que depende de esta unidad. **Recomendación: respetar la historia** (solo
`TRANSFERENCIA`), probarlo con cobros de fixture y dejar anotado que la demo en staging llega con la
unidad siguiente. Lo que se paga: una acción que en staging no se ve hasta la próxima unidad.
Alternativa: permitir el registro manual también en cobros por link (un reembolso hecho desde el panel
de MercadoPago); se descarta porque ese dinero lo informa MercadoPago y, el día que el barrido o un
webhook lo detecte, quedaría contado dos veces.

### 10. RN-10 pide un evento `PagoReembolsado` «simétrico a `PagoConfirmado`» — **hallazgo H5**

`PagoConfirmado` **no existe**: el saldo del comprobante baja con una llamada directa al puerto
`PortSaldoDeComprobante.registrar_cobro`, dentro de la misma transacción (`confirmacion.py:149`, D26).
**Recomendación: ser simétrico con lo que existe**, no con lo que la historia supone: un método nuevo
`registrar_reembolso(comprobante_id, monto)` en el mismo puerto y el mismo ACL (`saldo.py`), en la misma
transacción que la fila. Sube el saldo con **tope en el total** del comprobante (hallazgo H11:
`registrar_cobro` recorta en cero, así que sumar sin tope podría dejar un saldo mayor al total); una
corrección negativa lo vuelve a bajar con piso en cero. Alternativa: introducir `PagoConfirmado` y
`PagoReembolsado` como eventos de dominio con un suscriptor en billing: es un cambio de arquitectura de
la confirmación del pago que ninguna historia de esta unidad pide.

## Diseño

- **Dominio** (`payments/domain/`):
  - `cobro.py`: `EstadoCobro.REEMBOLSADO_PARCIAL`. Transiciones nuevas: `APROBADO → REEMBOLSADO_PARCIAL |
    REEMBOLSADO`, `REEMBOLSADO_PARCIAL → REEMBOLSADO_PARCIAL | REEMBOLSADO | APROBADO`, `REEMBOLSADO →
    REEMBOLSADO_PARCIAL | APROBADO` (las que bajan solo las alcanza una corrección; el estado se deriva del
    acumulado en un único método `_estado_por_acumulado`, ADR-0010 punto 5). `monto_reembolsado:
    Decimal = 0`, `pendiente_de_reembolso` (= monto − acumulado), `admite_reembolso` (APROBADO o PARCIAL).
  - `solicitar_reembolso(monto, clave, ahora)`: solo por link, estado que admite reembolso, **sin otro en
    vuelo**, `0 < monto ≤ pendiente_de_reembolso`; guarda monto, clave y fecha de la solicitud. No cambia
    el estado (D27).
  - `confirmar_reembolso(reembolso, ahora)`: exige una solicitud en vuelo; aplica el monto confirmado al
    acumulado, re-deriva el estado y limpia la solicitud. `rechazar_reembolso(ahora)`: limpia la solicitud
    sin tocar estado ni acumulado (RN-03).
  - `registrar_reembolso_manual(...)`: solo `TRANSFERENCIA`, estado que admite reembolso, monto ≤
    pendiente, fecha plausible, motivo no vacío. `corregir_reembolso(original, motivo, usuario, ahora)`: solo
    filas `MANUAL` no corregidas; aplica `-original.monto` y re-deriva el estado.
  - Mensajes: `MENSAJE_REEMBOLSO_EXCEDIDO` pasa al texto de la historia, «El monto a reembolsar no puede
    superar el monto pendiente de reembolso del cobro.» (hallazgo H9).
  - `reembolso.py` (nuevo): `Reembolso` (frozen) con `OrigenDeReembolso` (`API_MERCADOPAGO`, `MANUAL`) y las
    invariantes de la fila (monto distinto de cero, negativo ⇔ `corrige_a`, motivo en manuales, `Decimal`
    redondeado con `redondear`). `recibe_recordatorios` no cambia: los estados reembolsados no están
    abiertos, así que RN-12 y D93 («los barridos excluyen los reembolsados») salen por construcción.
- **Aplicación**: `application/reembolsos.py` (nuevo; `ReembolsarCobro` sale de `cobros.py`, H8).
  Todos exigen Administrador (RN-05) y publican `EventoAuditable` con `detalle` (monto, origen, id del
  reembolso, motivo de MercadoPago cuando lo hay; **nunca** la referencia bancaria ni datos del pagador).
  - `SolicitarReembolso` (T1): carga el cobro **con bloqueo de fila**, valida, persiste la solicitud y su
    clave. Acción `solicitar_reembolso`.
  - `EnviarReembolso` (T2): llama a la pasarela con la clave guardada y despacha el resultado:
    `aceptado` → `_confirmar` (fila, acumulado, estado, saldo, evento `confirmar_reembolso`);
    `rechazado` → rechazo + evento `ERROR` con el motivo, **y devuelve** el resultado para que el borde
    re-levante después del commit; `en_proceso` o `PasarelaNoDisponible` → deja la solicitud (guarda el id de
    MercadoPago si vino) y publica `reembolso_sin_confirmar` (`ERROR` solo cuando no hubo respuesta, para
    que alguien se entere).
  - `ActualizarReembolso`: consulta por id o reenvía con la misma clave; mismo despacho. Si ya no hay nada
    en vuelo, no hace nada (idempotente).
  - `RegistrarReembolsoManual` y `CorregirReembolso`: una transacción, cobro bloqueado, fila + acumulado +
    estado + saldo + evento.
  - Una sola función `_aplicar(cobro, reembolso)` hace «fila + acumulado + saldo» para los tres caminos,
    para que no existan tres formas de sumar plata.
- **Puertos y adaptadores**:
  - `PortRepositorioCobro.buscar_para_actualizar(cobro_id)` (`SELECT … FOR UPDATE`).
  - `PortRepositorioReembolso` (nuevo): `agregar`, `de_cobro`, `buscar_por_id`. Adaptador en
    `repositories.py` (o `repositorio_reembolso.py` si `repositories.py` pasa de 400 líneas).
  - `PortPasarelaDePago.reembolsar(empresa_id, payment_id, monto, clave) -> RespuestaDeReembolso` (deja de
    ser `bool`: `estado` ∈ {aceptado, rechazado, en_proceso}, `mp_refund_id`, `monto`, `fecha`, `motivo`) y
    `consultar_reembolso(empresa_id, payment_id, refund_id)`. `PasarelaMercadoPago`: `_pedir` acepta la clave
    de idempotencia desde afuera; el `status` de MercadoPago se traduce en el ACL (`approved` → aceptado,
    `rejected`/`cancelled` → rechazado, cualquier otro → en proceso, **nunca** aceptado por defecto); un 4xx
    es rechazado con el `message` de MercadoPago sin traducir; `amount` sin `float` (pregunta 3); fechas con el
    mismo lector tolerante que `date_approved`. `PasarelaSimulada`: «rechazar» en la descripción rechaza (como
    hoy) y «demorar» deja el reembolso en proceso hasta el primer «Actualizar estado», para caminar las tres
    ramas en una laptop.
  - `PortSaldoDeComprobante.registrar_reembolso` (pregunta 10), en `saldo.py`.
  - `metricas` (pregunta 7): una tercera agregación sobre `reembolso` por `fecha_devolucion`.
- **Otros contextos**:
  - `billing`: escritura del saldo por su capa de aplicación (`VerComprobante` + repositorio publicado), el
    mismo edge que ya usa `registrar_cobro` (`payments → billing`, Context Map §4). Sin ADR.
  - `reporting`: `CobranzasViaPayments.totales` hereda «cobrado» neto sin cambiar código; `filas` muestra el
    estado nuevo como ya muestra los otros (el valor del enum). Sin ADR.
  - `observability`: el evento `ERROR` ya se convierte en notificación (`NotificarPorEventos`); nada nuevo.
- **HTTP** (`api/routers/reembolsos.py`, nuevo, montado bajo `/cobros`; `cobros.py` ya tiene 363 líneas):
  - `POST /cobros/{id}/reembolso` (existe): T1, luego T2 en otra `unidad_de_trabajo`; 200 con el cobro
    (confirmado o en proceso); 422 con el motivo de MercadoPago **después** del commit del rechazo; 409 si
    ya hay uno en vuelo o el estado no lo admite.
  - `POST /cobros/{id}/reembolso/actualizacion`, `POST /cobros/{id}/reembolsos` (manual),
    `POST /cobros/{id}/reembolsos/{reembolso_id}/correccion`. Montos como texto (`monto_desde`), fecha como
    `YYYY-MM-DD`.
  - `DetalleSalida` gana `reembolsos: list[ReembolsoSalida]` y `reembolso_en_proceso_monto`;
    `monto_reembolsado` deja de ser `null`.
- **Frontend** (`features/payments`, sin importar otro feature, R5):
  - `api/cobro.ts`: `REEMBOLSADO_PARCIAL` con etiqueta «Reembolsado parcialmente» y su tono; el filtro de
    estado del listado lo incluye (HU-E6-01 RN-02); tipos `Reembolso`, funciones `registrarReembolso`,
    `corregirReembolso`, `actualizarReembolso`.
  - `components/ReembolsosDeCobro.tsx` (nuevo, para que `DetalleDeCobro.tsx`, 372 líneas, no pase de 400):
    historial (fecha de devolución, monto, origen, referencia, motivo, «Corregido»/«Corrección»); acción
    «Corregir» por fila manual; modal «Registrar reembolso» (monto, fecha, referencia, motivo).
  - `DetalleDeCobro.tsx`: «Reembolsar» en `APROBADO` y `REEMBOLSADO_PARCIAL`, solo por link, sin otro en
    vuelo, con el pendiente precargado; «Registrar reembolso» solo en `TRANSFERENCIA`; «Reembolso en
    proceso» con el monto y «Actualizar estado»; «Reembolsado» muestra el acumulado; aviso de nota de crédito
    con enlace a `/facturacion/{comprobante_id}/anular` cuando hay comprobante y acumulado > 0 (RN-09, D89:
    un enlace a una ruta, no un import). Operador y Solo Lectura ven todo y no ven acciones.
  - BFF: `app/api/cobros/[cobroId]/reembolso/actualizacion/route.ts`,
    `app/api/cobros/[cobroId]/reembolsos/route.ts`,
    `app/api/cobros/[cobroId]/reembolsos/[reembolsoId]/correccion/route.ts`.
  - `index.ts`: sin exportaciones nuevas salvo lo que la página ya compone. Rutas del panel: sin cambios.

## Infraestructura

- **Migraciones**: `backend/migrations/versions/0027_reembolsos.py` (`down_revision = "0026"`).
  1. Tabla `reembolso` (pregunta 4), `ENABLE` + `FORCE ROW LEVEL SECURITY`, política
     `aislamiento_por_empresa` (`USING` y `WITH CHECK` sobre `app.current_empresa`), **`GRANT SELECT,
     INSERT`** (sin `UPDATE` ni `DELETE`) a `cheatsheet_app`; índices y `CHECK` de la pregunta 4.
  2. `cobro`: `monto_reembolsado` → backfill `COALESCE(..., 0)`, `NOT NULL DEFAULT 0`; reemplaza
     `ck_cobro_reembolso` por `0 <= x <= monto`; las tres columnas de la solicitud en vuelo y su `CHECK`.
  3. Backfill de la pregunta 6 (una fila por `REEMBOLSADO`, re-derivar parciales) con `NOTICE` por empresa.
  4. `ck_cobro_fecha_de_pago` se recrea **`NOT VALID`** incluyendo `REEMBOLSADO_PARCIAL` (hoy lista solo
     `APROBADO` y `REEMBOLSADO`, hallazgo H7); `ck_cobro_estado_de_reembolso` nuevo, `NOT VALID` si el informe
     no dio cero.
  - `estado` es `varchar(20)` sin `CHECK` de valores: `REEMBOLSADO_PARCIAL` (19 caracteres) entra sin tocarla.
  - `empresas_con_cobros_abiertos()` no cambia (filtra `PENDIENTE`/`VENCIDO`).
  - **Reversible con pérdida declarada**: `downgrade` vuelve `REEMBOLSADO_PARCIAL` a `REEMBOLSADO` (el
    comportamiento viejo), restaura el `CHECK` viejo (acumulado en cero → `NULL`), borra las columnas en vuelo
    y la tabla. Se pierde el historial; se documenta en la migración.
  - El ORM (`models.py`) declara índices y `CHECK` con las mismas expresiones, como en la 0026.
- **Trabajo asíncrono**: no aplica en esta unidad si el Gate acepta la pregunta 2 (el barrido va a
  `reembolsos-en-vuelo`). Idempotencia de lo que sí hay: la clave persistida hacia MercadoPago y el índice
  único de `mp_refund_id` hacia nosotros.
- **Configuración**: no aplica. Sin variables nuevas ni cambios en `.env.example`.
- **Integraciones externas**: MercadoPago, ya integrado. `POST /v1/payments/{id}/refunds` con `amount`
  (parcial; sin `amount` sería total, y **nunca** se manda sin él) y `X-Idempotency-Key`;
  `GET /v1/payments/{id}/refunds/{refund_id}`. Timeout 15 s, tres intentos con reintento en 5xx y red,
  **la misma clave en los tres** (ya es así dentro de `_pedir`) y ahora también entre requests. Rechazos
  conocidos de la referencia: `2063`, `2024`/`15016` (pago muy viejo; 180 días según la guía), `4040`,
  `4041`, `4293`, `4295` (parcial no soportado para esa transacción): todos se tratan como rechazo con el
  mensaje de MercadoPago. Sandbox vs producción: nada verificado (ver la sección de sandbox).

## Riesgos que obligan a tests (marcar los que apliquen)
- [x] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → monto pedido redondeado una vez en el
  dominio; `0.10 + 0.20` acumulado da `0.30`; el tope `acumulado ≤ monto` en dominio y en la base;
  el cuerpo a MercadoPago sin `float`; «cobrado» neto sumado en la base
- [ ] Toca comprobantes fiscales / CAE → no aplica: la nota de crédito solo se ofrece, nunca se emite
- [x] Consume un webhook → no se agrega ninguno, pero **una misma confirmación, un solo efecto**:
  «Actualizar estado» dos veces, o la respuesta del `POST` y después la consulta, insertan una sola fila
  (dominio: sin solicitud en vuelo no confirma; base: único `mp_refund_id`). Y el webhook `payment` de
  un pago ya conocido sigue siendo `ya_procesado` sin tocar el reembolso
- [x] Agrega datos con `empresa_id` → aislamiento: RLS de `reembolso`; `mp_refund_id` único por empresa;
  «cobrado» de una empresa no resta reembolsos de otra
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales a un LLM → no aplica; la referencia bancaria no va a la bitácora ni a logs

Riesgos que no son tests, dichos con todas las letras:
- **Concurrencia: dos reembolsos a la vez que juntos superan lo pagado.** Solo el `CHECK` de la base
  **no alcanza**: dos transacciones que leen acumulado 0 y escriben cada una su monto terminan con el
  acumulado de la última (se pierde una actualización), el `CHECK` pasa y hay dos filas que suman más que
  el cobro. Se previene en tres capas: (1) todo camino que suma carga el cobro con `SELECT … FOR UPDATE`,
  así que el segundo espera y ve el acumulado nuevo; (2) por API, la solicitud en vuelo es un mutex:
  mientras exista, el dominio rechaza otra (y T1 se commitea antes de hablar con MercadoPago, así que el
  segundo la ve); (3) el `CHECK 0 <= acumulado <= monto` es el piso que un bug futuro no puede saltear.
  Manual y API no compiten: uno es solo `TRANSFERENCIA` y el otro solo link. Test de integración con dos
  sesiones reales (caso 27).
- **La suma de las filas y el acumulado pueden divergir** si algún camino escribe uno sin el otro. Una sola
  función los escribe juntos en la misma transacción, y un test de integración compara
  `Σ reembolso.monto` con `cobro.monto_reembolsado` después de cada camino. No se agrega un trigger.
- **Plata devuelta sin rastro** (H1): se cierra porque la solicitud y su clave se commitean antes de la
  llamada; lo que queda abierto es un reembolso que MercadoPago ejecutó y nosotros no confirmamos hasta
  «Actualizar estado» (o el barrido de la unidad siguiente).
- **La idempotencia del lado de MercadoPago está documentada, no verificada**: la referencia dice que la
  clave permite reintentar «sin el riesgo de realizar la misma acción más de una vez»; cuánto dura esa
  garantía y qué devuelve el reintento, no. Es la base de «Actualizar estado» sin id; va al sandbox.
- **`in_process` puede no existir para reembolsos** (la referencia solo muestra `approved`). Si nunca
  aparece, la rama «en proceso» queda solo para la falta de respuesta, que sí existe.
- **Saldo del comprobante**: con tope en el total y piso en cero puede no volver exactamente a lo que era
  si antes se recortó (H11). Se anota, no se corrige: requiere saber cuánto recortó `registrar_cobro`.
- **Un reembolso de un comprobante ya anulado por nota de crédito** sube el saldo de un comprobante que no
  debería tener saldo. No está en ninguna historia; se anota para `billing`.
- **«Cobrado» negativo** en un período puede sorprender en pantalla; es la definición de RN-11 (pregunta 7).

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/payments/domain/cobro.py` (estado, transiciones, métodos de reembolso, mensaje)
- [x] `backend/src/cheatsheet/contexts/payments/domain/reembolso.py` (nuevo)
- [x] `backend/src/cheatsheet/contexts/payments/application/ports.py` (`PortRepositorioReembolso`, `RespuestaDeReembolso`, `buscar_para_actualizar`, `consultar_reembolso`, `registrar_reembolso`)
- [x] `backend/src/cheatsheet/contexts/payments/application/reembolsos.py` (nuevo: los cinco casos de uso)
- [x] `backend/src/cheatsheet/contexts/payments/application/cobros.py` (sale `ReembolsarCobro`)
- [x] `backend/src/cheatsheet/contexts/payments/application/errors.py` (`ReembolsoEnProceso`, `ReembolsoNoCorregible`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/models.py` (`ReembolsoORM`, columnas y `CHECK`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/repositories.py` (mapeos, `FOR UPDATE`, `metricas`, repositorio de reembolsos)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/pasarela.py` (respuesta tipada, clave, `consultar_reembolso`, sin `float`, simulada)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/saldo.py` (`registrar_reembolso`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/ensamblado.py` (repositorio de reembolsos)
- [x] `backend/migrations/versions/0027_reembolsos.py` (nuevo)
- [x] `backend/src/cheatsheet/api/routers/reembolsos.py` (nuevo) y su registro en la app
- [x] `backend/src/cheatsheet/api/routers/cobros.py` (`DetalleSalida`, sale la ruta de reembolso)
- [x] `backend/tests/contexts/payments/domain/test_cobro.py` y `test_reembolso.py` (nuevo)
- [x] `backend/tests/contexts/payments/application/test_reembolsos.py` (nuevo; los tests de reembolso de `test_cobros_y_recordatorios.py` se mudan acá)
- [x] `backend/tests/contexts/payments/application/test_confirmacion.py` (`CobrosFalsos`, `PasarelaFalsa`, webhook de un pago reembolsado)
- [x] `backend/tests/contexts/payments/infrastructure/test_pasarela_contrato.py`
- [x] `backend/tests/contexts/payments/infrastructure/test_saldo_via_billing.py`
- [x] `backend/tests/integracion/test_cobros_postgres.py` (métricas; el caso 12 de `fecha-de-pago` cambia a propósito)
- [x] `backend/tests/integracion/test_reembolsos_postgres.py` (nuevo: RLS, grants, concurrencia, suma)
- [x] `backend/tests/integracion/test_migracion_0027.py` (nuevo)
- [x] `backend/tests/integracion/test_api_reembolsos.py` (nuevo)

### Frontend
- [x] `frontend/src/features/payments/api/cobro.ts`
- [x] `frontend/src/features/payments/components/DetalleDeCobro.tsx`
- [x] `frontend/src/features/payments/components/ReembolsosDeCobro.tsx` (nuevo)
- [x] `frontend/src/features/payments/components/ListadoDeCobros.tsx` (opción de filtro)
- [x] (el tono del estado nuevo vive en `api/cobro.ts`, `tonoDeEstado`)
- [x] `frontend/src/app/api/cobros/[cobroId]/reembolso/actualizacion/route.ts` (nuevo)
- [x] `frontend/src/app/api/cobros/[cobroId]/reembolsos/route.ts` (nuevo)
- [x] `frontend/src/app/api/cobros/[cobroId]/reembolsos/[reembolsoId]/correccion/route.ts` (nuevo)
- [x] `frontend/src/features/payments/api/__tests__/cobro.test.ts`
- [x] `frontend/src/features/payments/components/__tests__/pantallas.test.tsx` (y `reembolsos.test.tsx` si conviene separarlo)
- [x] `frontend/src/app/api/cobros/__tests__/rutas.test.ts`
- [x] `frontend/src/app/(panel)/cobros/__tests__/pagina.test.tsx`

### Archivos que el plan no listaba (los pidió una regla de `CLAUDE.md` o la implementación)
- [x] `backend/src/cheatsheet/contexts/payments/domain/dinero.py` (`redondear` y `CENTAVOS`: `Cobro` y `Reembolso` se necesitan y el redondeo no puede ser un import circular)
- [x] `backend/src/cheatsheet/contexts/payments/domain/estado_de_cobro.py` y `reembolsos_de_cobro.py` (`cobro.py` ya pasaba de 400 líneas: tipos y constantes a un archivo, los reembolsos como mixin de `Cobro` en otro; `cobro.py` los reexporta)
- [x] `backend/src/cheatsheet/contexts/payments/application/reembolsos_comunes.py` y `reembolsos_manuales.py` (`reembolsos.py` pasaba de 400 líneas: la API (T1, T2) queda en `reembolsos.py`; el registro manual, la corrección y el historial en `reembolsos_manuales.py`; el guarda, la carga con bloqueo y `aplicar` en `reembolsos_comunes.py`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/pasarela_simulada.py` (`pasarela.py` pasaba de 400 líneas; se reexporta) y `repositorio_reembolso.py` (el plan lo preveía si `repositories.py` pasaba de 400)
- [x] `backend/src/cheatsheet/api/mercadopago.py` (el doble simulado pasa a ser de proceso) y `backend/src/cheatsheet/api/main.py` (registro del router)
- [x] `backend/tests/api/test_reembolso_confirma_el_estado.py` y `test_pasarela_simulada_compartida.py` (nuevos: contrato de commit y doble de proceso); `backend/tests/integracion/conftest.py` (`DELETE FROM reembolso` antes de `cobro`)
- [x] `frontend/src/shared/pantallas-cobros.css` (el historial de reembolsos)

### Docs
- [x] `docs/aidlc/units.md` (fila de la unidad; si se aprueba la pregunta 2, fila nueva `reembolsos-en-vuelo` y `reembolso-rechazado-persistido` absorbida): ya hecho en el Gate 1
- [x] `docs/aidlc/TODO.md` §20 (ítems de la sección de sandbox)
- [x] `docs/aidlc/epicas/06-cobros-y-recordatorios/pendientes.md` ítem 7 (cerrado por esta unidad)
- Sin ADR nuevo: el modelo es el de ADR-0010, y las decisiones de este Gate caben dentro de sus límites.

## Casos de prueba

Modo: **test primero**. Los casos marcados RED tienen que fallar antes de tocar el código. Los de
integración (PostgreSQL) se escriben y corren en CI si el entorno local no tiene base; el estado dice
honestamente cuál se observó.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: reembolso parcial confirmado → `REEMBOLSADO_PARCIAL`, acumulado = monto confirmado | unit (dominio) | GREEN (RED: fallaba la colección, `ImportError`); `test_cobro.py` |
| 2 | RED: segundo reembolso que completa el monto → `REEMBOLSADO`; uno que lo supera → rechazado con el mensaje de la historia | unit (dominio) | GREEN (RED: ídem) |
| 3 | RED: `solicitar_reembolso` sobre `REEMBOLSADO_PARCIAL` se admite; sobre `PENDIENTE`, `CANCELADO` y `REEMBOLSADO` → «Solo pueden reembolsarse cobros pagados.» | unit (dominio) | GREEN (RED: ídem) |
| 4 | RED: con un reembolso en vuelo, otra solicitud se rechaza | unit (dominio) | GREEN (RED: ídem) |
| 5 | RED: por API solo cobros `LINK_MERCADOPAGO`; manual solo `TRANSFERENCIA` | unit (dominio) | GREEN (RED: ídem) |
| 6 | RED: el rechazo deja estado y acumulado intactos (`APROBADO` y también `REEMBOLSADO_PARCIAL`) | unit (dominio) | GREEN (RED: ídem), con `APROBADO` y con `REEMBOLSADO_PARCIAL` |
| 7 | RED: corrección de una fila manual → fila negativa; baja `REEMBOLSADO → REEMBOLSADO_PARCIAL → APROBADO`; corregir dos veces, corregir una corrección o una fila de API → rechazado | unit (dominio) | GREEN (RED: ídem); también la red de seguridad si se saltea `ya_corregido` |
| 8 | RED: `Reembolso` exige monto distinto de cero, negativo ⇔ `corrige_a`, motivo en manuales; redondea `ROUND_HALF_UP`; `0.10 + 0.20` acumula `0.30` | unit (dominio) | GREEN (RED: `test_reembolso.py` no importaba); `0.10 + 0.20 = 0.30` |
| 9 | RED: fecha manual del futuro o anterior al pago → rechazada; un día se guarda como 12:00 de Argentina | unit (dominio) | GREEN (RED: ídem); el «hoy» se mide en Argentina, no en UTC |
| 10 | RED: `SolicitarReembolso` persiste solicitud, monto y clave **antes** de llamar a la pasarela (la pasarela falsa ve el cobro ya marcado) | unit (aplicación) | GREEN (RED: `ImportError`), `test_reembolsos.py`; la pasarela ve el cobro ya marcado |
| 11 | RED (H1): MercadoPago rechaza → el rechazo y el evento `ERROR` con el motivo **quedan escritos** aunque el borde devuelva 422 | unit (aplicación) + integración (API) | GREEN unit y **contrato de commit** con doble (`tests/api/test_reembolso_confirma_el_estado.py`, RED: el router no existía; un mutante que levanta adentro del ciclo lo hace fallar); PostgreSQL: escrito, **no corrido** (sin Docker local): corre en CI |
| 12 | RED (H1): MercadoPago no responde → la solicitud queda en vuelo y hay un evento que avisa; no se pierde nada | unit (aplicación) + integración (API) | GREEN unit y contrato de commit (la marca y la clave sobreviven); PostgreSQL: escrito, **no corrido** (sin Docker local): corre en CI |
| 13 | RED: aceptado → una fila `API_MERCADOPAGO` con `mp_refund_id` y fecha de MercadoPago; `en_proceso` → sin fila, en vuelo con el id | unit (aplicación) | GREEN (RED: `ImportError`) |
| 14 | RED: «Actualizar estado» con id consulta; sin id reenvía **con la misma clave**; dos veces seguidas → una sola fila | unit (aplicación) | GREEN (RED: ídem); sin id reenvía con la misma clave, dos veces = una fila |
| 15 | RED: MercadoPago confirma un monto mayor al pendiente → no se registra, queda en vuelo, evento `ERROR` | unit (aplicación) | GREEN (RED: ídem) |
| 16 | RED: el saldo del comprobante sube con el reembolso (tope en el total) y baja con la corrección (piso en cero); sin comprobante no se llama | unit (aplicación + ACL) | GREEN aplicación y ACL (`test_saldo_via_billing.py`, RED: 4 fallaban): tope en el total, piso en cero |
| 17 | RED: solo el Administrador solicita, actualiza, registra y corrige; Operador y Solo Lectura → rechazados | unit (aplicación) | GREEN (RED: ídem), Operador y Solo Lectura en los cinco casos de uso; y 422 en el router |
| 18 | Un cobro reembolsado (parcial o total) no vuelve a recibir recordatorios ni entra al barrido (RN-12) | unit (aplicación) | GREEN (dominio y aplicación, por construcción: no están abiertos) |
| 19 | El webhook `payment` de un pago ya reembolsado sigue siendo `ya_procesado` y no toca acumulado ni solicitud | unit (aplicación) | GREEN (`test_confirmacion.py`): `ya_procesado`, sin llamar a MercadoPago ni tocar el reembolso |
| 20 | RED: el adaptador manda `amount` como número JSON exacto sin `float`, con `X-Idempotency-Key` igual a la clave dada (y la misma en los reintentos) | unit (contrato, `MockTransport`) | GREEN (RED: 23 fallaban), `MockTransport`: cuerpo `{"amount": 1234.56}` exacto y la misma clave en los tres reintentos |
| 21 | RED: `status` `approved` → aceptado; `rejected`/`cancelled` → rechazado; otro o ausente → en proceso; 4xx → rechazado con el `message`; 5xx y timeout → `PasarelaNoDisponible` | unit (contrato) | GREEN (RED: ídem), incluidos `status` ausente/numérico → en proceso y 4xx de consulta → `PasarelaNoDisponible`; tras el verificador, el 4xx de negocio (400, 404, 422) es rechazo y los ambiguos (401, 403, 408, 409, 425, 429) levantan `PasarelaNoDisponible` (ver caso 38) |
| 22 | RED: `PasarelaSimulada`: «rechazar» rechaza, «demorar» queda en proceso hasta la primera consulta | unit | GREEN (RED: ídem); «rechazar», «demorar» y la misma clave devuelven lo mismo. El doble pasó a ser de proceso (ver «Desvíos» del reporte) |
| 23 | RED: métricas — pago en febrero, reembolso en marzo: febrero suma el bruto, marzo resta el reembolso; parcial y total; una corrección suma de vuelta; «cobrado» puede ser negativo | integración (PostgreSQL) | escrito, **no corrido** (sin Docker local): corre en CI |
| 24 | RED: la tasa cuenta los estados reembolsados por su bruto y no pasa de 100 % | unit + integración | unit GREEN (`test_metricas.py`, cobrado negativo); integración: escrito, **no corrido** (sin Docker local): corre en CI |
| 25 | RED: `reembolso` rechaza `UPDATE` y `DELETE` para `cheatsheet_app`; RLS aísla empresas; `mp_refund_id` único por empresa, repetible en otra | integración (PostgreSQL) | escrito, **no corrido** (sin Docker local): corre en CI |
| 26 | RED: `CHECK` de la base: acumulado fuera de `[0, monto]`, estado que no concuerda con el acumulado, monto cero en `reembolso`, corrección positiva → rechazados | integración (PostgreSQL) | escrito, **no corrido** (sin Docker local): corre en CI |
| 27 | RED: **dos registros manuales concurrentes** (dos sesiones) cuyo total supera el cobro → uno entra y el otro se rechaza; `Σ reembolso.monto = cobro.monto_reembolsado` | integración (PostgreSQL) | escrito, **no corrido** (sin Docker local): corre en CI (fuerza el solapamiento con un `sleep` tras tomar el bloqueo) |
| 28 | Después de cada camino (API, manual, corrección), `Σ reembolso.monto = cobro.monto_reembolsado` | integración (PostgreSQL) | escrito, **no corrido** (sin Docker local): corre en CI; además cada camino por API en `test_api_reembolsos.py` |
| 29 | RED: migración sobre datos viejos: cada `REEMBOLSADO` gana su fila; un parcial viejo pasa a `REEMBOLSADO_PARCIAL`; un `REEMBOLSADO` sin monto se informa por `NOTICE` | integración (migración) | escrito, **no corrido** (sin Docker local): corre en CI |
| 30 | La migración sube, baja y vuelve a subir; al bajar `REEMBOLSADO_PARCIAL` vuelve a `REEMBOLSADO` | integración (migración) | escrito, **no corrido** (sin Docker local): corre en CI (el `downgrade` a 0025 de `test_migracion_0026.py` también lo recorre) |
| 31 | `GET /cobros/{id}` trae `reembolsos`, `monto_reembolsado` numérico y `reembolso_en_proceso_monto`; las rutas nuevas responden 200/409/422 según el caso | integración (API) | escrito, **no corrido** (sin Docker local): corre en CI (`test_api_reembolsos.py`) |
| 32 | RED: detalle — «Reembolsar» en `APROBADO`/`REEMBOLSADO_PARCIAL` por link con el pendiente precargado; «Registrar reembolso» solo en transferencia; nada para Operador | unit (frontend) | GREEN (RED: 24 fallaban), Vitest |
| 33 | RED: «Reembolso en proceso» con monto y «Actualizar estado»; historial con corrección visible; «Corregir» solo en filas manuales no corregidas | unit (frontend) | GREEN (RED: ídem) |
| 34 | RED: aviso de nota de crédito con enlace a `/facturacion/{id}/anular` cuando hay comprobante y acumulado > 0; sin comprobante no aparece | unit (frontend) | GREEN (RED: ídem) |
| 35 | RED: etiqueta «Reembolsado parcialmente» y la opción en el filtro del listado | unit (frontend) | GREEN (RED: ídem) |
| 36 | En el navegador (`run-local`, pasarela simulada): reembolso parcial, completarlo, uno «rechazar», uno «demorar» y «Actualizar estado»; ver el encabezado del período | manual | pendiente, para quien revise (`run-local`, pasarela simulada; «rechazar» y «demorar» en la descripción del cobro) |
| 37 | En sandbox de MercadoPago: los ítems de la sección siguiente | manual (sandbox) | pendiente; anotado en `TODO.md` §20 (20.5, 20.9 a 20.16) |
| 38 | RED (verificador, D1): un 401, 403, 408, 409, 425 o 429 al reembolsar **no** es un rechazo: levanta `PasarelaNoDisponible` y el reembolso queda en vuelo con su clave; 400, 404 y 422 siguen siendo rechazo | unit (contrato, `MockTransport`) | GREEN (RED: los 6 estados ambiguos fallaban, se tomaban como `RECHAZADO`) |
| 39 | RED (verificador, M7): la clave de idempotencia y los campos del reembolso en vuelo sobreviven al mapeo `Cobro` <-> `CobroORM` (`_a_fila` / `_a_dominio`, puros, sin base) | unit (infraestructura) | GREEN; mutante que quita la asignación de la clave en `_a_fila` → falla (RED observado), restaurado. La persistencia real sigue en `tests/integracion/` (no corrida local) |

## Verificaciones contra el sandbox

Van a `docs/aidlc/TODO.md` §20. El 20.5 ya existe y esta unidad lo detalla; los demás son nuevos.

| # | Qué verificar | Qué pasa si falla |
|---|---|---|
| 20.5 | (existente) La API acepta reembolsos **parciales** en un pago por link de Checkout Pro, varios sobre el mismo pago, y con qué respuesta. La referencia lo afirma ([Create refund](https://www.mercadopago.com.ar/developers/en/reference/online-payments/checkout-api-payments/create-refund/post), [Configure refunds and cancellations](https://www.mercadopago.com.ar/developers/en/docs/checkout-pro-preferences/additional-settings/refunds-and-cancellations)) y lista el error `4295` «parcial no soportado» para algunas transacciones | Si un medio no admite parcial, se muestra el rechazo con el motivo; si ninguno, cambia HU-E6-05 |
| 20.9 | Qué valores de `status` devuelve el `POST` de reembolso (la referencia solo muestra `approved`) y si un reembolso de tarjeta vuelve aprobado en el acto | Si nunca hay `in_process`, la rama «en proceso» queda solo para la falta de respuesta |
| 20.10 | Semántica de `X-Idempotency-Key`: reenviar el mismo `POST` con la misma clave devuelve el mismo reembolso y no crea otro; cuánto tiempo vale la clave | **Crítico**: si no deduplica, «Actualizar estado» sin id puede duplicar un reembolso; habría que consultar la lista de reembolsos del pago en vez de reenviar |
| 20.11 | `GET /v1/payments/{id}/refunds/{refund_id}` ([referencia](https://www.mercadopago.com.ar/developers/en/reference/chargebacks/_payments_id_refunds_refund_id/get)) devuelve `status`, `amount` y `date_created` con zona horaria | Si la fecha falta, la devolución toma el momento de la confirmación |
| 20.12 | Si un reembolso dispara un webhook `payment` (`payment.updated`) o solo el tópico `topic_claims_integration_wh` que la guía de [Webhooks](https://www.mercadopago.com.ar/developers/en/docs/checkout-pro-preferences/additional-content/notifications/webhooks) asocia a «creación de reembolsos y reclamos» | Define si `reembolsos-en-vuelo` puede confirmar por notificación además de por barrido, y si se pueden detectar reembolsos hechos desde el panel de MercadoPago |
| 20.13 | `amount` con centavos (`0.10`, `1234.56`) se reembolsa exacto; mínimo por reembolso y cantidad máxima de parciales por pago | Un centavo de diferencia entre la fila y lo devuelto |
| 20.14 | El cuerpo de un rechazo trae `message` legible (códigos `2063`, `2024`/`15016`, `4293`, `4295` de la referencia) y el plazo de 180 días de la guía | Si no hay mensaje, la pantalla muestra solo el código |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-30 | aprobado; las diez preguntas según la recomendación. `units.md` actualizado antes del código (P1 y P2) |
| 2 · Verificación | 2026-09-30 | aprobado, incluido el cambio de regla de los 4xx ambiguos. ruff y mypy (sin caché) en verde; pytest 1544 pasan, 404 omitidos por requerir PostgreSQL o Redis; cobertura local 75,43 % contra 74 % antes (el 80 % se mide en la CI). Migración 0027 renderizada en SQL offline en ambos sentidos. Arquitectura: fronteras intactas. Frontend: 872 tests en verde. Verificador independiente: aprobado con notas (16 de 19 mutantes detectados en local; los 3 restantes los cubren los casos de PostgreSQL); su riesgo D1 se corrigió con test primero antes del Gate. Pendientes: casos contra PostgreSQL (CI) y sandbox (`TODO.md` §20.5, §20.9 a §20.16; el 20.10 es crítico) |
| 3 · PR | 2026-09-30 | PR draft [#51](https://github.com/cheatsheet12/CheatSheet/pull/51) apilado sobre el #50; la CI corre cuando la cadena llegue a `develop` |

## Decisiones tomadas durante la unidad
- P1: la unidad absorbe `reembolso-rechazado-persistido` (reescribe el mismo caso de uso); la fila queda marcada «absorbida» en `units.md`.
- P2: el reembolso se pide en dos transacciones (en vuelo y clave de idempotencia confirmados antes de llamar a MercadoPago) con la acción «Actualizar estado»; el barrido automático de RN-04 va a la unidad nueva `reembolsos-en-vuelo` (S), registrada en `units.md`.
- P3: se corrige el `float` de `pasarela.py` en `reembolsar` (el `Decimal` viaja como número JSON); el de `crear_link` sigue en `TODO.md` §20.6.
- P4: columnas según la propuesta del plan (`corrige_a` único y `mp_refund_id` único por empresa en `reembolso`; el pedido en vuelo en `cobro`), con los CHECK que atan estado y acumulado.
- P5: una corrección anula la fila entera, con motivo obligatorio; solo se corrigen filas `MANUAL`.
- P6: cada `REEMBOLSADO` existente recibe una fila con fecha `updated_at`, marcada aproximada en el motivo; los parciales viejos se re-derivan a `REEMBOLSADO_PARCIAL`; las anomalías se informan por `NOTICE` y el CHECK entra `NOT VALID`.
- P7: «Cobrado» es neto (pagos por `fecha_pago` menos devoluciones por su fecha) y puede ser negativo; la tasa cuenta los tres estados pagados por su monto bruto.
- P8: la fecha de un reembolso manual se carga como día y se guarda a las 12:00 de Argentina; no puede ser futura ni anterior al pago.
- P9: el registro manual queda solo para `TRANSFERENCIA`.
- P10: sin evento `PagoReembolsado`; el saldo del comprobante se ajusta por llamada directa al puerto, como `registrar_cobro`.
- Lo que solo el sandbox puede confirmar quedó en `docs/aidlc/TODO.md` §20.5 y §20.9 a §20.14 (el 20.10, idempotencia, es crítico).
- Verificador independiente (Gate 2): aprobado con notas. Corregido antes del Gate: los 4xx ambiguos del reembolso (401, 403, 408, 409, 425, 429) ya no se toman como rechazo; el reembolso queda en vuelo con su clave, porque un 409 o un 429 tras un timeout puede significar que MercadoPago ya lo procesó, y borrar la clave reabría el doble reembolso.
- Una corrección registra `fecha_devolucion` en el momento de corregir, no en la fecha de la fila original: impacta en el período en que se corrige y no reescribe períodos cerrados.
- Limitación conocida (D3): la segunda transacción (T2) mantiene el bloqueo `FOR UPDATE` sobre el cobro y una conexión durante la llamada a MercadoPago (hasta ~45 s con los tres intentos). Se acepta por ahora; lo resuelve `reembolsos-en-vuelo`.
