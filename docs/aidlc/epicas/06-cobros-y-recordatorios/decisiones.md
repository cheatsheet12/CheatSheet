# Decisiones — Épico 6 · Cobros y recordatorios

> Las decisiones que este épico tuvo que tomar y no estaban en los insumos. Cada una dice qué
> se eligió, **por qué**, y qué se paga por haberlo elegido. Las numeradas siguen la serie
> del sistema (`docs/aidlc/units.md` trae D1–D19).

**Historias**: HU-E6-01 … HU-E6-06 · HU-E11-01 · HS-T1, HS-T3
**Contextos**: `payments`, `business_config`, `billing`
**Rama**: `feature/payments-cobros-y-recordatorios`

---

## D20 — El webhook se hace idempotente con el `payment_id` de MercadoPago, no con una clave nuestra

HS-T1 RN-04 exige que una notificación repetida no genere efectos duplicados. Había dos formas:
una clave de idempotencia en Redis, como usan los barridos del épico 4, o **el propio
identificador del pago**.

**Se usa `mp_payment_id`, guardado en la fila del cobro y con índice único parcial.**

MercadoPago reintenta un webhook durante horas si no recibe un 200, y manda la misma
notificación varias veces por diseño. Una clave en Redis con TTL protege durante el TTL y
después deja de proteger — y el peor caso de una notificación tardía es exactamente el que hay
que cubrir. Una columna con índice único protege para siempre, sobrevive a un `FLUSHALL` y es
verificable con una consulta.

**Lo que se paga:** una escritura más en la transacción del webhook, y que la idempotencia sea
por `(empresa, payment_id)` en vez de por evento — si MercadoPago mandara dos pagos distintos
para un mismo cobro, los dos se procesan. Es lo correcto: son dos pagos.

## D21 — El webhook contesta 200 antes de hacer el trabajo pesado, pero **después** de registrar el pago

MercadoPago corta a los 22 segundos y reintenta ante cualquier cosa que no sea 2xx. La
tentación es contestar 200 de entrada y encolar todo; el problema es que un fallo al encolar
deja el pago perdido y a MercadoPago convencido de que llegó.

**Se persiste el pago y se cambia el estado del cobro dentro del request** —es una escritura,
es rápida— y **se encolan los efectos** (reducir el saldo del comprobante, detener los
recordatorios, avisar) en la misma transacción. Recién ahí contesta 200.

**Lo que se paga:** el request hace más que un `INSERT`. A cambio, un webhook que contestó 200
es un webhook cuyo pago está guardado, y eso es lo que MercadoPago tiene derecho a asumir.

## D22 — Un webhook cuya firma no valida se registra y se descarta con 200, no con 401

HS-T1 RN-01 pide validar la autenticidad, y el criterio dice «lo descarta sin alterar el cobro
y registra el intento». La pregunta que no responde es **qué código HTTP** devolver.

**Se devuelve 200 y se registra el intento.** Un 401 le dice a MercadoPago «reintentá», y
MercadoPago reintenta durante horas una notificación que nunca va a validar — llenando la
bitácora de intentos idénticos. Un 200 corta el reintento, que es lo correcto para una firma
inválida: no es un error transitorio.

**Lo que se paga:** un atacante que manda basura recibe 200. No importa: no obtiene
información, no altera nada, y queda registrado. Confundir «acepté» con «procesé» sería el
error, y por eso la bitácora dice explícitamente `webhook_rechazado`.

## D23 — El vencimiento a `VENCIDO` lo hace un barrido, no una propiedad calculada

HU-E6-01 RN-03 dice que un cobro pasa a `VENCIDO` «automáticamente al superar su vencimiento».
Eso se puede leer de dos formas: una propiedad derivada de la fecha, o una transición real.

**Es una transición real, hecha por un barrido de Beat.** Tres razones:

1. **Los recordatorios dependen del estado**, y HS-T3 RN-03 los detiene en `APROBADO` y
   `CANCELADO`. Un estado que sólo existe al leerlo no dispara nada.
2. **La bitácora tiene que registrarlo.** «Cuándo pasó a mora» es una pregunta que se hace en
   una discusión con un cliente, y una propiedad calculada no deja rastro.
3. **El listado filtra por estado en la base** (RN-02). Un estado calculado en Python obliga a
   traer todo y filtrar en memoria, lo que se rompe con paginación.

**Lo que se paga:** un cobro puede estar unos minutos vencido y todavía figurar `PENDIENTE`. Es
aceptable: la mora no es un evento al segundo.

## D24 — Las reglas de negocio son un JSONB validado en el dominio, no una tabla por tipo

HU-E11-01 pide reglas parametrizables de tres tipos distintos (`ESCALAMIENTO_DE_COBRO`,
`POLITICA_DE_TURNO`, `AGENDA_DE_NOTIFICACION`), y el DER las pone en una tabla con
`configuracion jsonb`.

**Se respeta el DER, y cada tipo tiene su propia clase de configuración que valida al
construirse.** El JSONB entra y sale por una fábrica que sabe qué forma tiene cada tipo; nada
lee `configuracion["dias"]` directamente.

La alternativa —una tabla por tipo— daría validación en el esquema y costaría tres migraciones
por cada tipo nuevo, además de romper la resolución por prioridad de RN-05, que compara reglas
de tipos distintos.

**Lo que se paga:** una configuración escrita a mano en la base puede tener cualquier forma. Lo
compensa que la única escritura pasa por el caso de uso, y que leer una mal formada **falla al
construir** en vez de propagar un `KeyError` a la mitad de un barrido.

## D25 — La cadena de recordatorios se ancla en el `paso`, no en la fecha del último envío

HS-T3 RN-05 exige que el planificador no mande el mismo paso dos veces, y el DER pone
`recordatorio.paso` justamente para eso.

**El barrido pregunta cuál es el paso máximo ya enviado para un cobro y despacha el
siguiente**, si la regla dice que corresponde. No mira «cuándo fue el último»: mira «cuál
falta».

La diferencia importa cuando el planificador se atrasa. Si un cobro debía recibir los pasos 1,
2 y 3 y el worker estuvo caído dos días, un barrido basado en fechas manda los tres de golpe.
Uno basado en el paso manda el 1, y el 2 en la corrida siguiente — que es lo que un cliente
espera de una cadena de recordatorios.

**Lo que se paga:** ponerse al día lleva tantas corridas como pasos atrasados. Es correcto:
mandar tres mensajes en un minuto es peor que mandarlos tarde.

## D26 — Un cobro asociado a un comprobante reduce el saldo **al aprobarse**, nunca al crearse

HU-E6-06 RN-03 lo dice, y vale escribirlo acá porque la implementación tiene una tentación
clara: descontar el saldo al generar el link, para que el listado muestre el comprobante como
«en proceso de cobro».

**No.** Un link generado no es plata cobrada. Un comprobante cuyo saldo bajó porque alguien
generó un link que nadie pagó es un comprobante que miente en el balance, y en el reporte del
épico 9. El saldo baja cuando MercadoPago confirma, y en ninguna otra transición.

**El tope de RN-02 se valida contra el saldo pendiente en el momento de crear el cobro**, y lo
vuelve a validar la aprobación: dos links por el total del mismo comprobante son legítimos
—alguien puede cancelar uno— pero **dos pagos** no.

## D27 — El reembolso es asíncrono y el estado no se toca hasta que MercadoPago confirma

HU-E6-05 RN-03 y RN-04 lo piden, y la consecuencia se parece a la decisión D17 del épico 5: hay
un estado «pedimos y no sabemos».

**No se agrega un estado al enum del DER.** El cobro sigue `APROBADO` mientras el reembolso
está en vuelo, y lo que existe es un campo `reembolso_solicitado_en`. La pantalla muestra
«Reembolso en proceso» a partir de eso, que es lo que pide el criterio de aceptación.

Agregar `REEMBOLSO_EN_PROCESO` al enum habría sido más explícito y peor: un cobro con un
reembolso rechazado tiene que volver a `APROBADO` (RN-03), y una transición de vuelta a un
estado anterior es exactamente la forma que la máquina de estados del épico 5 evita.

---

## Cómo se relacionan con lo anterior

- **D20 y D22** son a los webhooks lo que **D17** es a la emisión: un resultado ambiguo se
  resuelve preguntando o registrando, nunca repitiendo.
- **D23 y D25** usan el mismo patrón de barrido que **HS-T6** (épico 4) y la reconciliación de
  **D17**: el estado lo mueve un proceso, no una lectura.
- **D26** es la contracara de **D19**: allá lo anulado se derivaba porque las notas son filas;
  acá el saldo se persiste porque es del comprobante y lo consultan tres contextos.

---

## D91 — «cobrado» se mide por fecha de pago, y la tasa de cobro solo sobre lo creado en el período

*Enmienda de la revisión de 2026-09 · ADR-0009 · unidad `fecha-de-pago` · HU-E6-01, HU-E6-02*

HU-E6-01 medía todo el encabezado sobre el período activo sin decir por qué fecha. Un cobro creado
en febrero y pagado en marzo caía en febrero, y si el numerador fuera por fecha de pago y el
denominador por fecha de creación, la tasa de cobro podría pasar del 100 %.

**«Cobrado» se mide por la fecha de pago (`fecha_pago`). La tasa de cobro se calcula solo sobre los
cobros creados en el período, así que no puede superar el 100 %. Pendiente y en mora mantienen su
base actual.** El mismo criterio rige en el tablero de reportería (D98). Un reembolso resta de
«cobrado» en el período en que se devolvió el dinero, no en el del pago original (D93). El detalle
del cobro muestra medio de pago, fecha de pago y, si fue por transferencia, el número de operación.

**Modelo, para el Gate 1 de `fecha-de-pago`:**

- `cobro` no tiene fecha de pago. Se agrega `fecha_pago` (`timestamptz`): en un pago por link es la
  fecha de aprobación informada por MercadoPago, y en una transferencia, la fecha de la operación
  verificada (D94).
- Los cobros ya APROBADOS necesitan una carga inicial: se completa desde MercadoPago cuando se pueda y,
  si no, con `updated_at`, marcada como aproximada. Falta decidir cómo se marca esa aproximación.
- El detalle muestra `medio_de_pago` y `numero_de_operacion`, que define el ADR de medios de pago y
  reembolsos (D93). Ese ADR se escribe una sola vez, en el Gate 1 de la primera unidad de este épico
  que lo necesite, y las demás lo consumen. Mientras no exista, todo cobro es por link.

## D92 — un cobro no crea clientes: se elige uno que ya existe

*Enmienda de la revisión de 2026-09 · ADR-0009 · unidad `nuevo-cobro-desde-su-panel` · HU-E6-03 (y HU-E5-03, HU-E7-06)*

La precondición de HU-E6-03 decía «el cliente existe en Datos Maestros o se crea en el momento», y
nada del formulario de PAN-COB-03 permitía elegir uno sin haber llegado desde la fila del cliente.

**El cobro no crea clientes. PAN-COB-03 lleva un selector obligatorio de clientes activos, con
búsqueda por nombre o CUIT; «Generar cobro» desde la fila del cliente sigue abriendo la pantalla con
ese cliente preseleccionado; y si el selector no encuentra ninguno, ofrece un enlace a Clientes.**
Se quitó «o se crea en el momento» de las tres historias que lo decían: HU-E6-03, HU-E5-03 y
HU-E7-06.

Crear un cliente exige validar su CUIT contra ARCA (HU-E4-01 RN-02), y hacerlo desde un cobro, una
factura y un turno triplicaría ese formulario. La alternativa, un botón «Crear cliente» que vuelva a
la pantalla con el cliente preseleccionado, se descartó por lo mismo.

**Para el Gate 1:** el selector lo expone `features/master_data` por su `index.ts`, sin que
`payments` importe sus internos (R5), y el backend valida que el cliente exista por la capa de
`application` de `master_data` (R3).

**Lo que se paga:** crear un cliente nuevo obliga a salir a Clientes y volver.

## D93 — reembolsos parciales, para los dos medios, y registro manual de los de transferencia

*Enmienda de la revisión de 2026-09 · ADR-0009 · unidad `reembolsos-parciales-y-manuales` · HU-E6-05 (y HU-E6-06)*

HU-E6-05 solo conocía un reembolso total por la API de MercadoPago (RN-02, RN-03). Dos huecos: no
había reembolso parcial, y un cobro pagado por transferencia no puede reembolsarse por esa API.

**El cobro conserva el monto acumulado reembolsado.** Está `REEMBOLSADO_PARCIAL` («Reembolsado
parcialmente») cuando 0 < reembolsado < monto, y `REEMBOLSADO` solo cuando reembolsado = monto; la suma
de los reembolsos nunca supera el monto (`Decimal`). Vale para los dos medios:

- **Por link:** sigue por la API de MercadoPago, asíncrono, como en D27.
- **Por transferencia:** el dinero se devuelve por fuera de la plataforma y el Administrador lo
  registra con «Registrar reembolso»: monto, fecha en que se devolvió el dinero, referencia opcional
  (número de operación o comprobante bancario) y motivo. Es declarativo, porque el sistema no puede
  verificar dinero saliente. Queda en la bitácora con usuario y timestamp, los registros nunca se
  borran y un error se corrige con un nuevo registro visible.

**Efectos:** devolver dinero no anula el comprobante. Si el cobro está asociado a uno, el sistema
advierte que corresponde una nota de crédito y ofrece el acceso directo (D89), pero nunca la emite. El
saldo del comprobante sube por el evento de dominio `PagoReembolsado`, simétrico a `PagoConfirmado`
(D26). El reembolso resta de «cobrado» en el período de la devolución (D91) y no reactiva los
recordatorios.

**D27 sigue en pie.** Allí se rechazó agregar `REEMBOLSO_EN_PROCESO` al enum porque un reembolso
rechazado obligaría a volver a `APROBADO`, y una transición hacia atrás es lo que la máquina de
estados evita. `REEMBOLSADO_PARCIAL` es otra cosa: es un estado estable del que solo se avanza, y
«Reembolso en proceso» sigue siendo `reembolso_solicitado_en`.

**Modelo, para el Gate 1 de `reembolsos-parciales-y-manuales`.** Se resuelve en el mismo ADR de medios
de pago y reembolsos de D91, que se escribe antes de la migración:

- `medio_de_pago` (enum), monto acumulado reembolsado y el estado `REEMBOLSADO_PARCIAL`.
- Los datos de cada reembolso —monto, fecha, referencia, motivo y `registrado_por`— como filas propias,
  no como columnas del cobro, porque el historial no se borra.
- Cómo afecta al acumulado un registro de corrección, y cómo consulta `reporting` la fecha de
  devolución sin un join (D51).
- Que los barridos de recordatorios (D23, D25) excluyan los estados reembolsados.

**Lo que se paga:** el registro manual es una declaración; si el Administrador se equivoca, la
plataforma lo deja a la vista pero no lo detecta.

## D94 — una transferencia solo confirma el cobro si MercadoPago la verifica y el pagador es quien debe

*Enmienda de la revisión de 2026-09 · ADR-0009 · unidad `cobro-por-transferencia` · HU-E6-08 (y HU-E8-06)*

Un cliente puede pagar por transferencia, y no hay forma de confirmar ese pago sin revisar un
comprobante a mano; además, un número de operación es una prueba al portador: quien lo conozca puede
reclamarlo sobre otro cobro.

**La transferencia se registra sobre un cobro existente y la confirma código determinista de
`payments`, sin intervención humana, consultando la API de MercadoPago con el número de operación.**
Confirma solo si la operación existe y es de la cuenta de la empresa, está aprobada, tiene el monto
exacto del cobro (`Decimal`), no es anterior a la creación del cobro, y **la identificación del
pagador (DNI o CUIT) coincide con el CUIT del cliente del cobro.** Si no coincide (un familiar, o una
empresa que pagó en nombre del cliente), el cobro sigue pendiente y el caso se escala a una persona
(HU-E8-05). La comparación se hace en memoria; la identificación del pagador no se persiste ni se
registra en logs, solo su resultado (coincide / no coincide). Con esa regla el riesgo de un reclamo
de un tercero queda cerrado.

Un número de operación produce efecto una sola vez por empresa. Si MercadoPago no confirma, hay 3
intentos en 10 minutos con timeout y backoff y luego escalamiento; tras 3 verificaciones fallidas en
24 horas sobre un cobro no se aceptan más números hasta «Reintentar verificación». No existe
confirmación manual sin verificación. Al confirmarse, el cobro pasa a APROBADO con medio TRANSFERENCIA
y se publica el `PagoConfirmado` existente (D26).

**Modelo, para el Gate 1 de `cobro-por-transferencia`:** `medio_de_pago`, `numero_de_operacion` (único
por empresa) y `fecha_pago`, definidos por el ADR de medios de pago y reembolsos (D91, D93). Hay que
resolver cómo se compara un DNI con el CUIT del cliente y qué se hace con un cliente sin CUIT (hoy se
trata como «no coincide»).

**A verificar en el sandbox de MercadoPago antes de escribir el adaptador:**

- Que la identificación del pagador venga en las transferencias entrantes, no solo en los pagos por
  link.
- Si las operaciones por transferencia son consultables con las credenciales del vendedor. Las
  transferencias desde bancos externos a un CVU podrían no serlo, y esos casos caen en el escalamiento.

**Lo que se paga:** un pago legítimo hecho por un tercero termina en manos de una persona.
