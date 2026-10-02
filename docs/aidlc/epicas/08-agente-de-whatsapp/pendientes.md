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
configurar `WHATSAPP_WEBHOOK_SECRET` y `WHATSAPP_WEBHOOK_VERIFY_TOKEN`.

**Sin el secreto configurado, ninguna firma valida** y todo se descarta (con 200, decisión
D49). Es lo contrario de lo cómodo y es a propósito, igual que en el épico 6.

---

## Lo que funciona y podría funcionar mejor

### 4. Los callbacks de entrega llegan y no se procesan

`Mensaje.marcar_entrega` existe, avanza sin retroceder y está probado; `estado_entrega` se
guarda. Lo que falta es leer los `statuses` de la notificación de Meta y llamarlo.

**Es lo que cierra el pendiente #3 del épico 6** («el estado de entrega nunca se actualiza
después del envío»). El parser del webhook ya los distingue de los mensajes —los ignora
explícitamente y contesta 200— así que lo que falta es una rama, no una estructura.

### 5. El agente ofrece horarios pero todavía no confirma la reserva

`ProcesarMensajeEntrante` cubre el primer criterio de HU-E8-01 —«ofrece horarios disponibles
reales»— y el ACL tiene `reservar`, que es el motor determinista. Lo que no existe es el **paso
intermedio**: recordar qué horarios se ofrecieron para poder entender «el jueves a las 10:30».

Eso es estado de conversación, y necesita una decisión que no se tomó: dónde vive. Las opciones
razonables son una columna JSONB en `conversacion` o releer los últimos mensajes salientes. **No
se improvisó** porque la mitad peligrosa —que la reserva la haga el motor y no el modelo— ya
está resuelta y probada; lo que falta es la parte fácil, y hacerla mal significaría que el
agente reserve algo que el cliente no eligió.

Lo mismo aplica a HU-E8-02 (cancelar por WhatsApp): `turnos_de` y `cancelar` están en el ACL, y
falta el paso de «cuál de los dos».

### 6. `POLITICA_DE_TURNO` sigue sin configuración tipada · **cuando haga falta**

Es el pendiente #9 del épico 7. `TipoRegla` tiene el valor desde el épico 6; lo que va a
contener —anticipación mínima, hasta cuándo se puede cancelar— es política que el agente va a
consumir cuando complete el flujo del pendiente #5.

### 7. `AGENDA_DE_NOTIFICACION` tampoco

El tercer `TipoRegla`, que gobernaría «recordale al cliente el turno de mañana» (HU-E8-04
RN-02). El canal ya existe ahora, así que el barrido es posible; falta la regla que diga cuándo.

### 8. No hay índice `ivfflat` sobre `faq.embedding_vector`

La búsqueda hace un escaneo secuencial. **Es lo correcto hoy**: un índice `ivfflat` necesita
datos para elegir sus listas, y construirlo sobre una tabla vacía produce un plan peor que el
escaneo. Con las decenas de FAQ que tiene una PyME, el escaneo gana.

El día que una empresa tenga miles, el índice es una migración de dos líneas.

### 9. Editar una plantilla no la vuelve a poner `PENDIENTE` ante Meta

Editar el cuerpo de una plantilla aprobada la invalida en la práctica, pero **quien lo decide es
Meta y no nosotros**. Ponerla en `PENDIENTE` acá sería inventar una respuesta del proveedor.

Lo que falta es el cliente de la API de plantillas de Meta: enviar la plantilla editada,
recibir su estado, y guardarlo. Hasta entonces, `estado_aprobacion_meta` refleja lo que alguien
haya cargado.

### 10. El listado de conversaciones no pagina

Igual que los listados de los épicos 5, 6 y 7. **Épico 9**, junto con la del resto del panel.
La bandeja del operador —`solo_escaladas=true`— es chica por naturaleza, así que el caso de uso
diario no muerde.

---

## Lo que este épico dejó preparado para otros

### 11. El canal real de WhatsApp ya existe · **cierra pendientes del 6 y del 7**

`MensajeriaWhatsApp` es el cliente de la Cloud API que los épicos 6 y 7 anotaron como
pendiente. Lo que **todavía no se hizo** es reemplazar sus adaptadores de consola por éste:

- `payments.EnvioPorConsola` (recordatorios de cobro, HS-T3);
- `scheduling.AvisoPorConsola` (avisos de turno, HU-E7-02 RN-03/RN-04).

Los dos siguen negándose a arrancar en producción, así que el pendiente no muerde en silencio.
El cambio es de composition root: armar `MensajeriaWhatsApp` en `api/mercadopago.py` y
`api/agenda.py` en lugar de los dobles, y adaptar la firma de sus puertos, que hoy son distintas
—cada contexto declaró la suya, que es lo correcto bajo R3—. **Es una unidad chica y merece
serlo**, porque toca el camino de los mensajes que salen a clientes reales de tres contextos a
la vez.

### 12. `iniciador` está en la bitácora y nadie lo filtra todavía · **épico 10**

La columna existe, se escribe, y `RegistroDeAuditoria.fue_de_la_ia` la lee. HU-E12-01 pide
filtrar la bitácora por iniciador, y eso es el panel de auditoría del épico 10.

### 13. Las plantillas están y los adaptadores no las usan

`ResolverPlantilla` funciona y `armar_plantillas` la cablea, pero los tres adaptadores que
mandan mensajes —el del agente, el de turnos y el de cobros— siguen con su texto escrito
adentro.

**Es deliberado:** el texto de fábrica tiene que existir igual (una empresa que no editó nada
tiene que recibir mensajes), y conectar la plantilla es un cambio en cada adaptador que conviene
hacer junto con el #11, cuando esos adaptadores se toquen de todas formas.

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

### 17. `AgendaViaScheduling.horarios_ofrecibles` elige el primer servicio del recurso

Cuando un recurso presta varios servicios, el ACL toma el de id más bajo para armar el horario
ofrecible. Es arbitrario y está a la vista.

No muerde todavía porque el agente **no confirma reservas** (pendiente #5): los horarios que
ofrece son del recurso, y el servicio se decide cuando se reserve de verdad. El día que se cierre
ese flujo, el servicio tiene que salir de lo que el cliente pidió — que es parte de la misma
decisión pendiente.


### 18. El diálogo de «ese horario ya pasó, te ofrezco otros» no existe · **cierra con el #5**

HU-E8-01 RN-06 pide que el agente, ante una fecha u hora que ya pasó, lo indique y ofrezca
alternativas futuras. **El diálogo no se agregó porque el flujo conversacional todavía no llama a
`reservar`** (pendiente #5): no hay un paso donde un horario elegido se confirme, así que no hay
dónde atrapar el rechazo.

Lo que sí quedó listo con la unidad `turnos-no-en-el-pasado` (D95): `horarios_ofrecibles` ya
filtra los horarios pasados con el reloj inyectado, y `PortAgenda.reservar` puede levantar
`TurnoEnElPasado` —el motor vuelve a verificar al confirmar— sin excepción a posteriori en este
canal. Cuando se cierre el #5, el diálogo es atrapar ese error y volver a llamar a
`horarios_ofrecibles`.
