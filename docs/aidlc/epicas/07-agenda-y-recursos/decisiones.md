# Decisiones — Épico 7 · Agenda y recursos

> Lo que este épico decidió, **por qué**, y qué se paga por ello. Una decisión sin costo
> anotado es una decisión que nadie revisó.
>
> Continúan la serie del sistema: D1–D19 están en [`units.md`](../../units.md) y D20–D27 en el
> [épico 6](../06-cobros-y-recordatorios/decisiones.md).

---

## D28 — el doble booking lo impide PostgreSQL, no Python

**El riesgo de este contexto es uno solo y tiene nombre.** Dos personas con el mismo horario
con el mismo profesional es el error que el cliente descubre en la puerta del local, y que se
arregla llamando por teléfono a uno de los dos.

Ninguna comprobación en la aplicación lo evita. Entre el `SELECT` que dice «esa franja está
libre» y el `INSERT` que la reserva hay una ventana, y dos requests concurrentes caben en ella:
ninguna de las dos transacciones ve a la otra hasta que la primera hace commit.

**Lo que se hizo:** una restricción de exclusión sobre `(recurso_id, rango de la franja)` con
`btree_gist` — la extensión que la migración 0001 instaló para este momento. El motor compara
los rangos dentro de la misma transacción y rechaza el segundo, siempre.

```sql
EXCLUDE USING gist (
    recurso_id WITH =,
    franja_de_turno(franja_inicio, franja_duracion_min) WITH &&
) WHERE (estado IN ('RESERVADO', 'CONFIRMADO'))
```

Es **parcial**: sólo los turnos abiertos ocupan. Un turno cancelado liberó su horario y uno
completado ya pasó; que siguieran bloqueando dejaría al negocio sin poder revender una franja
que quedó libre.

**Lo que cuesta:** `ReservarTurno` puede fallar **después** de haber pasado todas sus
validaciones, y la pantalla tiene que estar preparada para eso — el selector de horarios marca
lo ocupado, pero esa marca es una ayuda y no una garantía. El repositorio traduce la violación
a `FranjaOcupada` con la frase de la historia; sin esa traducción, un doble booking evitado
llegaría como un 500 y el usuario volvería a intentar.

**Cómo se verificó:** `tests/integracion/test_agenda_postgres.py` corre dos reservas
simultáneas contra el motor y afirma que entra una. Y —lo que hace que eso sea evidencia—
**saca la restricción y comprueba que sin ella entran las dos**. Es el mismo método con el que
el épico 5 verificó D14 sacando el `FOR UPDATE`.

---

## D29 — la franja es inicio más duración; el rango se calcula

El DER modela `franja_inicio` + `franja_duracion_min`, no un `tstzrange`. Se respetó.

**Por qué no agregar la columna de rango:** sería guardar el mismo hecho dos veces, con la
posibilidad de que discrepen. Un `UPDATE` que corrigiera la duración y no el rango dejaría una
fila que dice dos cosas distintas, y la que gobierna el doble booking sería la equivocada.

**El problema que trajo:** una restricción de exclusión sólo acepta expresiones **inmutables**,
y `timestamptz + interval` está marcado `STABLE` en PostgreSQL.

**Lo que se hizo:** una función `franja_de_turno(timestamptz, integer)` declarada `IMMUTABLE`.
No es una mentira para pasar el chequeo: la marca `STABLE` del operador existe porque un
intervalo puede tener meses o días, y ésos sí dependen de la zona horaria. `n * interval '1
minute'` sólo tiene parte de tiempo, y sumarle tiempo a un `timestamptz` es aritmética sobre el
instante. La función es inmutable de verdad, y su comentario dice exactamente por qué — para
que nadie la «mejore» aceptando un intervalo arbitrario.

---

## D30 — reprogramar no es un estado

Las historias lo dicen dos veces y con todas las letras: HU-E7-01 RN-02 («no constituye un
estado en sí mismo») y HU-E7-02 RN-02 («conserva su estado»).

**Lo que se hizo:** `EstadoTurno` tiene los cinco valores del DER y ninguno más, y
`Turno.reprogramar` no recibe ni toca el estado. Un test afirma que `"REPROGRAMADO"` no está en
el enum, que es la forma de que un agregado futuro se caiga en vez de colarse.

**Lo que cuesta:** «¿este turno se movió?» no se contesta mirando el turno. Se contesta con la
bitácora, donde `reprogramar_turno` queda registrado con el usuario y el momento (RN-05). Es
menos cómodo y es correcto: el estado dice qué es el turno hoy, y la bitácora dice qué le pasó.

---

## D31 — la disponibilidad se calcula, no se materializa

No hay tabla de slots libres. Lo que se guarda es el **patrón semanal** más sus excepciones, y
los horarios de cualquier fecha se derivan de esa regla.

**Por qué:** una tabla de slots hay que barrerla, extenderla hacia adelante y mantenerla
consistente con cada cambio de horario. Un patrón alcanza para contestar por una fecha de
dentro de un año, sin nada que se venza.

**Lo que cuesta:** cada pregunta de disponibilidad recalcula. Para un recurso con un horario
semanal eso son siete filas y una comparación de horas — no es un costo real. Si algún día lo
fuera, la respuesta es cachear el cálculo, no materializar la tabla.

---

## D32 — la excepción reemplaza al patrón, y hay una sola por fecha

HU-E7-05 RN-03 dice que las excepciones «tienen prioridad» sobre la disponibilidad base. Se
interpretó como **reemplazo**, no como suma: una apertura especial es *el* horario de ese día.

Sumarlas haría que abrir un sábado a la mañana abriera también el horario habitual del sábado
—que puede no existir— o que un bloqueo parcial dejara el resto del día abierto sin que nadie
lo pidiera.

RN-02 pide rechazar «una excepción que contradiga otra existente para el mismo recurso y
fecha». **Se resolvió garantizando que no haya dos**: con una sola excepción por fecha, la
segunda siempre contradice a la primera, sea del tipo que sea, y no hay que comparar
excepciones entre sí buscando incompatibilidades. La regla es un índice único
(`uq_excepcion_recurso_fecha`), no un `if` — el `if` pierde contra dos pestañas abiertas.

**Lo que cuesta:** no se puede tener un bloqueo de la mañana y una apertura de la noche el
mismo día. Nadie lo pidió, y el día que se pida la respuesta es una excepción con varias
franjas, no dos filas que hay que interpretar juntas.

---

## D33 — el aviso por WhatsApp no puede voltear la operación

HU-E7-02 RN-03/RN-04 y HU-E7-06 RN-04 piden avisarle al cliente. El aviso va **después** de
persistir, y su fallo no revierte nada.

**Por qué:** un turno cancelado sigue cancelado aunque Meta esté caída. Lo contrario dejaría al
negocio sin poder cancelar por un problema ajeno, que es peor que un cliente que se entera por
teléfono.

Y un cliente **sin número registrado** es un camino previsto, no una falla: la regla dice «si
tiene número registrado». El puerto devuelve `None` y la operación sigue.

**El estado hoy:** el único adaptador es el de consola, que se niega a arrancar en producción.
El cliente real de WhatsApp Business lo construye el **épico 8**, junto con el agente — el
mismo trato que el épico 6 hizo con los recordatorios de cobro, y está en los pendientes.

---

## D34 — la agenda trabaja en una zona horaria del sistema

`ZONA_DE_LA_AGENDA` es una constante: `America/Argentina/Buenos_Aires`.

**Por qué no es un dato de la empresa:** el DER no le da zona horaria a `empresa`. Lo único que
hay es `usuario.pref_zona_horaria`, que es una preferencia de visualización — a qué hora *ve*
las cosas quien mira el panel — y no el horario en el que el local abre. Usar la del usuario
haría que el horario de atención de un recurso cambiara según quién lo consulte.

**Lo que cuesta:** una empresa que atienda en otro huso necesita esa columna primero. Está en
los pendientes, con el lugar exacto donde entraría.

**Lo que se hizo para que el pendiente no muerda:** toda comparación entre un `datetime` y una
hora del patrón pasa por una sola función, `_local`. Un test afirma que un turno de las 22 de
un martes se lee como martes aunque en UTC sea miércoles — que es el bug que corre la agenda
un día entero y que nadie encuentra mirando el código.

---

## D35 — «ya transcurrió» se mide contra el fin de la franja

HU-E7-03 RN-01 permite marcar asistencia sólo cuando el turno «ya pasó». Se midió contra el
**fin**, no contra el inicio.

Marcar «no se presentó» a los cinco minutos de empezado un turno de una hora sería marcarlo
mientras el cliente todavía puede llegar. Y no es un flag guardado: se calcula contra el reloj
que el caso de uso recibe, porque un dato derivado que además se guarda es un dato que a las
tres de la mañana de algún día va a estar desactualizado.

---

## D36 — un recurso sin servicios asociados no admite ninguno

HU-E7-04 RN-02 dice que «sólo esos servicios pueden reservarse». La lista vacía se leyó
literalmente: **ninguno**.

La alternativa —«sin lista, todos»— convierte un recurso a medio configurar en uno que acepta
cualquier reserva. Ese error se descubre cuando alguien ya reservó, que es tarde.

**Lo que cuesta:** un recurso recién creado no sirve para nada hasta que se le asocian
servicios. La pantalla lo dice, y es mejor que la sorpresa.

---

## D37 — la seña cruza por id, en las dos direcciones y sin join

HU-E6-07 asocia un cobro a un turno. El DER (hallazgo H4) declara `turno.cobro_id` **con** FK y
`cobro.turno_id` **sin** ella, y esa asimetría se respetó: el turno se crea primero, así que el
cobro puede apuntarlo sin que la FK ordene la creación al revés.

En el código las dos direcciones cruzan por id y sin join, que es lo que R3 pide.
`AsignarSenaAlTurno` es un caso de uso de `scheduling` que el composition root llama después de
que `payments` generó el cobro; `payments` nunca escribe en `turno`.
