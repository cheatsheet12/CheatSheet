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

---

## D95 — un turno no nace ni se mueve al pasado, salvo la corrección a posteriori del Administrador

*Enmienda de la revisión de 2026-09 · ADR-0009 · unidad `turnos-no-en-el-pasado` · HU-E7-06, HU-E7-02, HU-E8-01*

El panel dejaba crear, y no decía si dejaba reprogramar, un turno a un horario ya transcurrido. Pero
hay un caso legítimo: registrar una atención que ya ocurrió, para poder facturarla.

**Crear o reprogramar a un instante ya transcurrido se rechaza.** La comparación es contra el
instante actual, no solo el día, y se hace al confirmar. Mensajes: «No se puede agendar un turno en un
horario que ya pasó.» y «No se puede reprogramar un turno a un horario que ya pasó.» El Operador y el
agente de WhatsApp nunca pueden; el agente solo ofrece horarios futuros y el motor los vuelve a
verificar al confirmar (HU-E8-01 RN-06).

**El Administrador tiene una única excepción, en dos formas:**

- **Carga a posteriori (HU-E7-06 RN-07):** registra una atención ya realizada. La franja debe haber
  terminado y el turno nace `COMPLETADO` con canal `PANEL`, sin confirmación ni recordatorios.
- **Corrección a posteriori (HU-E7-02 RN-07):** reprograma un turno a una franja pasada, con las mismas
  reglas y sin mensaje al cliente.

En ambas se sigue rechazando el solapamiento con otros turnos reales del recurso, pero no se exige la
disponibilidad base ni se respeta el intervalo entre turnos (D96), y queda en la bitácora marcada como
«carga a posteriori» o «corrección a posteriori», con el usuario. Habilita la facturación (HU-E7-03
RN-02).

**Los dos criterios de tiempo no se contradicen con D35.** Para crear o reprogramar en condiciones
normales, el inicio no puede ser anterior a ahora; para la excepción, la franja completa debe haber
terminado, que es el mismo «ya transcurrió» de D35. Un turno cuyo inicio pasó pero cuyo fin no, no
admite ninguna de las dos cosas. El reloj se recibe como parámetro del caso de uso, como en D35.

**Para el Gate 1:** la marca va en la bitácora y no hay columna nueva; hay que decidir si el turno
`COMPLETADO` se crea directo o se crea y transiciona en la misma transacción según la máquina de
estados, y que el panel y el agente comparten el caso de uso de reserva. La exclusión de la base
contra el solapamiento sigue valiendo también para la excepción. HU-E7-06 y HU-E5-03 también dejan de
admitir «se crea en el momento» para el cliente (D92).

## D96 — la duración del turno es la del servicio, el slot es el paso de la grilla, y el intervalo es por recurso

*Enmienda de la revisión de 2026-09 · ADR-0009 · unidad `limites-e-intervalo-de-turnos` · HU-E7-04, HU-E7-06*

Las historias no decían qué define `turno.franja_duracion_min`: la duración del servicio o el slot
de la franja del recurso. Tampoco existía un margen entre turnos consecutivos.

**La duración del turno es la `duracion_estandar_min` del servicio (D86) y no se ingresa a mano. La
duración del slot, entre 5 y 480 minutos y sin superar la franja, es el paso de la grilla de horarios
de inicio que se ofrecen.** Cada recurso tiene además un intervalo entre turnos opcional, en minutos
(0 por defecto, máximo 480), que se agrega después de cada turno: un turno nuevo o reprogramado
empieza desde el fin del anterior más el intervalo, y su fin más el intervalo no pisa el inicio del
siguiente. El intervalo posterior al último turno de la franja puede exceder `hora_fin`. Cambiar el
intervalo o el slot aplica a reservas nuevas y no mueve turnos existentes. El agente solo ofrece
inicios que cumplan todo esto.

Esto se apoya en D29 (la franja es inicio más duración) y D31 (la disponibilidad se calcula, no se
materializa).

**Modelo, para el Gate 1 de `limites-e-intervalo-de-turnos`:**

- Falta `intervalo_entre_turnos_min` en `recurso_reservable`.
- La restricción de exclusión con `btree_gist` sobre inicio y duración del DER no puede expresar un
  intervalo variable por recurso. Para que la base siga impidiendo el doble booking hay dos caminos:
  guardar en el turno el intervalo aplicado al reservar (por ejemplo `intervalo_posterior_min`), o
  pasar el chequeo al dominio. El primero conserva la garantía de la base; el segundo la pierde
  frente a dos reservas simultáneas.
- La carga y la corrección a posteriori (D95) no respetan el intervalo.

**Lo que se paga:** con intervalo, el horario de un turno deja de ser suficiente para saber si dos
turnos chocan; hay que mirar también el intervalo con que se reservó.
