# Pendientes — Épico 8 · Agente de WhatsApp y atención humana

> Lo que este épico deja abierto, con **por qué se dejó** y **quién lo cierra**. Un pendiente
> sin dueño es un pendiente que nadie va a mirar, así que cada uno dice de qué épico es.

---

## Lo que bloquea una demo real

### 1. No hay proveedor de embeddings · **decisión de despliegue, no de épico**

`EmbeddingsSimulados` hashea el texto en un vector estable. **No entiende significados, y no
finge entenderlos**: dos preguntas parecidas dan vectores distintos.

Es el único doble del sistema que **no** se niega en producción, y es a propósito: no hay
adaptador real que lo reemplace todavía. Hasta que se elija un proveedor —y se agregue su
adaptador junto a `InterpreteAnthropic`—, la búsqueda por significado degrada a «no encuentro
nada», que el caso de uso convierte en **ofrecer un asesor**. Eso es correcto y es honesto: el
cliente recibe una persona, no una respuesta equivocada.

**Lo que hace falta:** un `PortEmbeddings` real. La forma ya está —`version` y `vectorizar`—,
`embedding_modelo_version` ya guarda con qué modelo se calculó cada vector, y el barrido de Beat
ya reindexa lo obsoleto. Es un archivo.

### 2. El transcriptor de notas de voz devuelve un texto fijo · **decisión de despliegue**

`TranscriptorSimulado` se niega en producción, así que no se puede desplegar sin que alguien se
entere. El camino de HS-T7 está completo —se transcribe, se interpreta el texto, el audio no se
guarda, y una calidad baja escala— y lo único que falta es el cliente del proveedor de
transcripción.

### 3. El webhook necesita una URL pública para probarse de punta a punta

`/webhooks/whatsapp/{empresa}` está implementado y probado con firma real (HMAC-SHA256), pero
Meta necesita alcanzarlo. En `staging` eso significa registrar la URL en la app de Meta y
configurar `WHATSAPP_WEBHOOK_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN`. Desde `canal-real-de-whatsapp`
(U5) las dos variables están declaradas en `render.yaml` (API, `sync: false`) y en
`docs/staging-deployment.md` §3; falta cargar sus valores cuando exista la app de Meta
(`TODO.md` §22.30 y §22.39).

**Sin el secreto configurado, ninguna firma valida** y todo se descarta (con 200, decisión
D49). Es lo contrario de lo cómodo y es a propósito, igual que en el épico 6.

---

## Lo que funciona y podría funcionar mejor

### 4. Los callbacks de entrega llegan y no se procesan

`Mensaje.marcar_entrega` existe, avanza sin retroceder y está probado; `estado_entrega` se
guarda. Lo que falta es leer los `statuses` de la notificación de Meta y llamarlo. **Lo hace la
unidad `entregas-de-whatsapp` (U7)**, que también reintenta entre barridos los transitorios agotados.

**Es lo que cierra el pendiente #3 del épico 6** («el estado de entrega nunca se actualiza
después del envío»). El parser del webhook ya los distingue de los mensajes —los ignora
explícitamente y contesta 200— así que lo que falta es una rama, no una estructura.

### 5. ~~El agente ofrece horarios pero todavía no confirma la reserva~~ · **cerrado por `reserva-y-cancelacion-por-whatsapp`**

Resuelto: el estado de la conversación vive en `conversacion.dialogo` (decisión **D99**). El agente guarda
lo que ofreció, lee la respuesta del cliente con un analizador determinista y reserva o cancela por los casos
de uso de `scheduling`. Cubre HU-E8-01 (CA1 a CA4, CA6, CA7) y HU-E8-02. Queda a la vista lo que sólo se
prueba contra PostgreSQL y el modelo real: ver `TODO.md` §22 y §25.

### 6. `POLITICA_DE_TURNO` sigue sin configuración tipada · **cuando haga falta**

Es el pendiente #9 del épico 7. `TipoRegla` tiene el valor desde el épico 6; lo que va a
contener —anticipación mínima, hasta cuándo se puede cancelar— es política que el agente va a
consumir.

**Lo que decidió `reserva-y-cancelacion-por-whatsapp` mientras no exista:** el agente **no cancela un turno
con seña** —avisa que lo deriva y escala con el motivo «Cancelación de turno con seña»— y los turnos sin
seña se cancelan sin anticipación mínima, como desde el panel. Cuando exista la política tipada, el agente
la aplica.

### 7. `AGENDA_DE_NOTIFICACION` tampoco

El tercer `TipoRegla`, que gobernaría «recordale al cliente el turno de mañana» (HU-E8-04
RN-02). El canal ya existe ahora (U5), así que el barrido es posible; falta la regla que diga cuándo.
**Lo hace la unidad `recordatorio-de-turno` (U8)**, que depende de U6 (plantillas).

### 8. No hay índice `ivfflat` sobre `faq.embedding_vector`

La búsqueda hace un escaneo secuencial. **Es lo correcto hoy**: un índice `ivfflat` necesita
datos para elegir sus listas, y construirlo sobre una tabla vacía produce un plan peor que el
escaneo. Con las decenas de FAQ que tiene una PyME, el escaneo gana.

El día que una empresa tenga miles, el índice es una migración de dos líneas.

### 9. ~~Editar una plantilla no la vuelve a poner `PENDIENTE` ante Meta~~ · **cerrado por `plantillas-de-whatsapp-en-meta` (U6)**

Editar el cuerpo de una plantilla aprobada la invalida en la práctica, pero **quien lo decide es
Meta y no nosotros**. Ponerla en `PENDIENTE` acá sería inventar una respuesta del proveedor.

**Cerrado por U6.** Editar una plantilla de WhatsApp la manda a Meta **antes de guardarla**: si Meta la
refuta (422 con su texto) o no contesta (503), no se guarda nada; si la acepta, el estado lo escribe
solo lo que Meta contesta (webhook `message_template_status_update` y conciliación periódica).
El agregado no inventa ningún estado.

### 10. El listado de conversaciones no pagina

Igual que los listados de los épicos 5, 6 y 7. **Épico 9**, junto con la del resto del panel.
La bandeja del operador —`solo_escaladas=true`— es chica por naturaleza, así que el caso de uso
diario no muerde.

---

## Lo que este épico dejó preparado para otros

### 11. ~~El canal real de WhatsApp ya existe~~ · **cerrado por `canal-real-de-whatsapp` (U5, ADR-0011)**

Resuelto: `payments.EnvioPorWhatsApp` (recordatorios de cobro, HS-T3) y
`scheduling.AvisoPorWhatsApp` (avisos de turno, HU-E7-02 RN-03/RN-04) mandan **texto** por
`MensajeriaWhatsApp`, armado una vez por unidad de trabajo en `api/mensajeria.py` y pasado hacia
adentro como un `Protocol` local (ningún contexto importa a otro). `EnvioPorConsola` y
`AvisoPorConsola` salieron de `src/`. En producción, una empresa sin WhatsApp conectado usa
`SinCanal` (levanta `CanalNoConectado`): el turno se cancela igual y el recordatorio queda
`FALLIDO`. Un fallo de Meta nunca voltea la operación ni reenvía lo que ya salió.

**Lo que queda, y de quién es:** fuera de la ventana de 24 h Meta sólo acepta plantillas
(error 131047), así que **hasta U6, en producción, un recordatorio o un aviso iniciado por la
empresa fuera de la ventana queda `FALLIDO`** (visible en PAN-COB-02). **U6 lo cierra** para cobros y
turnos cuando la empresa tiene la plantilla aprobada; sin ella, sigue igual. Las verificaciones con un
número de prueba real están en `TODO.md` §22.30–22.40.

### 12. `iniciador` está en la bitácora y nadie lo filtra todavía · **épico 10**

La columna existe, se escribe, y `RegistroDeAuditoria.fue_de_la_ia` la lee. HU-E12-01 pide
filtrar la bitácora por iniciador, y eso es el panel de auditoría del épico 10.

### 13. ~~Las plantillas están y los adaptadores no las usan~~ · **cerrado con nota por `plantillas-de-whatsapp-en-meta` (U6)**

`ConsultarPlantillaParaEnviar` funciona y `armar_plantillas` la cablea, pero los tres adaptadores que
mandan mensajes —el del agente, el de turnos y el de cobros— siguen con su texto escrito
adentro.

**Es deliberado:** el texto de fábrica tiene que existir igual (una empresa que no editó nada
tiene que recibir mensajes), y conectar la plantilla es un cambio en cada adaptador que conviene
hacer junto con U6 (`plantillas-de-whatsapp-en-meta`). U5 dejó los adaptadores de cobros y de turnos
con su texto de fábrica y sin cambiar su forma, a propósito.

**Cerrado con nota por U6:** los adaptadores de **cobros y turnos** usan la plantilla aprobada de Meta
(`ConsultarPlantillaParaEnviar`, por la raíz de composición) y caen al texto de fábrica si no hay una
aprobada. **El agente sigue con su texto por diseño**: contesta siempre dentro de la ventana de 24 h,
donde el texto libre es válido y gratuito. `armar_plantillas` y `PortPlantillas` se retiraron (código
muerto).

---

## Deuda de este épico que conviene no olvidar

### 14. `EscalamientoNoReabrible` es 422 y `CobroNoCancelable` es 409, y los dos quieren lo mismo

Decisión **D50**. Las dos historias piden que el sistema **diga** por qué no se puede, y el BFF
reenvía el `detalle` sólo en un 422 (`respuestaDeError`).

Este épico eligió que la frase llegue. **El épico 6 eligió lo contrario para el mismo problema**,
y su comentario afirma que «el router lo reenvía explícitamente» — lo cual, leyendo
`respuestaDeError`, no es cierto: el texto de «Un cobro pagado no puede cancelarse» no llega a
la pantalla.

Hay que resolverlo en **un solo sentido**, y la resolución no es de este épico: o el BFF reenvía
el detalle también en 409 —lo que expondría textos de otros errores que hoy no se muestran—, o
las excepciones que llevan una frase de historia derivan todas de `EntradaInvalida`. La segunda
es más chica; la primera es más honesta. **Merece su propia decisión.**

### 15. La lectura de `contador` y `ventana_maximo` es una interpretación

Decisión **D42**. El DER da las dos columnas sin decir qué cuentan, y este épico eligió
«intentos seguidos sin entender» porque le da trabajo a una regla que las historias sí escriben.

Si algún día hace falta la ventana de 24 horas de Meta —que es lo que el nombre sugiere— va a
necesitar sus propias columnas. Está dicho acá para que nadie descubra la ambigüedad leyendo
código.

### 16. El agente actúa con rol `OPERADOR` contra `scheduling`

`ROL_DEL_AGENTE = RolUsuario.OPERADOR`, y no `ADMINISTRADOR`: es exactamente lo que el agente
necesita —reservar y cancelar turnos— y nada de lo que no.

**Sigue siendo un rol de persona usado por un componente que no es una persona.** La forma
correcta a futuro es un permiso propio; hoy el sistema no tiene granularidad más fina que el rol,
y agregarla por este caso sería un cambio en los siete épicos anteriores.

### 17. ~~`AgendaViaScheduling.horarios_ofrecibles` elige el primer servicio del recurso~~ · **cerrado por `reserva-y-cancelacion-por-whatsapp`**

Resuelto: el servicio sale de lo que pidió el cliente. Con un solo servicio agendable con recurso activo no
se pregunta; con varios, el texto se compara de forma determinista con el catálogo y, si no hay una
coincidencia única, el agente pregunta con una lista numerada. `horarios_ofrecibles` se reemplazó por
`servicios_ofrecibles` y `horarios_libres(servicio_id, dia)`.

### 18. ~~El diálogo de «ese horario ya pasó, te ofrezco otros» no existe~~ · **cerrado por `reserva-y-cancelacion-por-whatsapp`**

Resuelto: ante una fecha u hora que ya pasó, o un horario que se venció mientras el cliente dudaba, el agente
lo dice y ofrece alternativas vigentes; el motor vuelve a verificar al confirmar (`HorarioEnElPasado`).

---

## Lo que dejó `reserva-y-cancelacion-por-whatsapp`

### 19. Reprogramar un turno por WhatsApp no tiene historia

Ninguna HU lo pide. Si el cliente pide mover un turno, el agente ofrece un asesor (como con `PAGO`) y no toca
la agenda. Si se quiere automatizar, hace falta primero la historia: qué pasa con la seña, qué anticipación
mínima rige (pendiente #6) y si se reprograma sobre la misma oferta de horarios.

### 20. ~~El historial que se le manda al intérprete incluye los textos del agente~~ · **cerrado por `reserva-y-cancelacion-por-whatsapp`**

Resuelto (decisión de Luciano, 2026-10-05): al intérprete sólo le llega lo que escribió el cliente, con los
datos personales ocultos. **Todo** saliente se reemplaza por el descriptor de quien lo escribió, también los
del agente (`[Respuesta del agente]`), y no sólo los que listan turnos. Los textos del agente los arma el
sistema con datos de la agenda y del directorio («tu turno de Psicología del jueves 14/10», «Hola Ana»):
marcar únicamente los que hablan de turnos obligaba a guardar una marca que `mensaje` no tiene y a que cada
texto nuevo se acordara de marcarse. Lo que se pierde es poco: las respuestas a una oferta o a una
confirmación ya no pasan por el modelo (las lee el analizador determinista), y un mensaje que queda ambiguo
sin ese contexto vuelve con baja confianza, que repregunta o escala. Ver D99, punto 5.

### 21. La extracción real del modelo no se probó

Los tests no tocan la red: `pedido_de_turno` se prueba contra el esquema y contra el intérprete simulado.
Hay que verificar en staging con `LLM_ADAPTADOR=anthropic` que la API acepta el esquema anidado con
`pattern` y `maxItems` en `output_config.format`, que `max_tokens` alcanza, y cómo extrae frases reales
(«el jueves que viene a la tarde», «no llego mañana»). Ver `TODO.md` §22.

---

## Lo que dejó `politica-fuera-de-horario`

### 22. No hay calendario automático de feriados nacionales · **depende de un tercero**

La empresa carga a mano sus fechas sin atención (feriados, vacaciones). Un calendario automático necesita una
fuente oficial o un servicio que publique los feriados nacionales y sus traslados, y decidir qué hace el sistema
cuando el calendario y la carga manual discrepan. Mientras tanto, la tarjeta «Fechas sin atención» de PAN-WA-02
es el único camino. Ver D100, punto 4.

### 23. El interruptor «Agente activo» del prototipo no existe

PAN-WA-01 y PAN-WA-02 lo muestran en el encabezado («Enciende o pausa el agente»), y el issue #71 también lo
menciona. Ninguna regla ni criterio dice qué hace un agente pausado (¿silencio total?, ¿mensaje fijo?, ¿todo a la
bandeja del operador?): sólo aparece como precondición de HS-T2 y de HU-E9-04. Decidirlo es una pregunta de
producto. Mientras tanto, la política (b) cubre el caso más pedido —que el agente no conteste con el negocio
cerrado— y desactivar la regla en PAN-CFG-RN vuelve al comportamiento de siempre (D100).

## Lo que dejó `usos-de-faq-por-periodo`

### 24. ~~El contador de usos de FAQ no tenía período~~ · **cerrado por `usos-de-faq-por-periodo` (ADR-0012)**

`faq.usos` era un entero sin fecha: la pantalla decía «Usos en el período» y mostraba el total desde
que la FAQ existe, el agente lo contaba antes de mandar el WhatsApp (un envío fallido sumaba) y lo
incrementaba con una lectura-modificación-escritura de toda la fila (dos respuestas simultáneas
perdían un uso, y una respuesta que se cruzaba con una edición del administrador se la pisaba).

Ahora cada respuesta enviada con una FAQ es una fila de `faq_uso` (solo inserción, única por
mensaje), la pantalla muestra «Este mes», «Mes anterior» y «Total» con los meses en hora de
Argentina, y el detalle de cada FAQ muestra su participación antes y después de su última edición.
El contador viejo quedó como línea de base (`usos_anteriores`) y entra solo en el total.

**Lo que queda, y es deliberado:** un fallo de entrega que Meta informe después no descuenta el uso
(ADR-0012, punto 1; depende de los callbacks de estado, pendiente #4); `faq_uso` no se poda (si se
poda, se pliega en `usos_anteriores` en la misma transacción); y las FAQ existentes muestran «sin
ediciones» hasta su próxima edición real, porque no hay forma honesta de saber la anterior.
