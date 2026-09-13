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
