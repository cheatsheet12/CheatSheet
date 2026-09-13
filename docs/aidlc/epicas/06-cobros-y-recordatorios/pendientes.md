# Pendientes — Épico 6 · Cobros y recordatorios

> Lo que este épico deja abierto, con **por qué se dejó** y **quién lo cierra**. Un pendiente
> sin dueño es un pendiente que nadie va a mirar, así que cada uno dice de qué épico es.

---

## Lo que bloquea una demo real

### 1. El recordatorio sale a un log, no a WhatsApp · **épico 8**

`EnvioPorConsola` registra el recordatorio y devuelve `ENVIADO`. Es el único adaptador del
épico que no tiene par real, y es deliberado: el canal es WhatsApp Business y su cliente lo
construye el épico 8 junto con el agente.

**Lo que sí se hizo para que el pendiente no muerda:** el doble se niega a arrancar en
producción, así que no se puede desplegar sin que alguien se entere; y devuelve `ENVIADO` y
**no** `ENTREGADO`, para que PAN-COB-02 no muestre un estado de lectura inventado — que es
justo el dato que alguien mira antes de llamar por teléfono a un cliente que «no contesta».

### 2. El webhook necesita una URL pública para probarse de punta a punta

`/webhooks/mercadopago/{empresa}` está implementado y probado con firma real (HMAC-SHA256),
pero MercadoPago necesita alcanzarlo. En `staging` eso significa registrar la URL en la
aplicación de MercadoPago y configurar `MERCADOPAGO_WEBHOOK_SECRET`.

**Sin el secreto configurado, ninguna firma valida** y todos los webhooks se descartan (con
200, decisión D22). Es lo contrario de lo cómodo y es a propósito: lo cómodo —aceptar todo
mientras no haya secreto— convierte un despliegue mal configurado en un endpoint público que
mueve el estado de los cobros.

### 3. El estado de entrega nunca se actualiza después del envío

`Recordatorio.marcar_entrega` existe y el esquema guarda `estado_entrega`, pero nada llama a
ese método después del despacho: los callbacks de entrega y lectura son de WhatsApp Business
y llegan por su propio webhook. **Épico 8.**

---

## Lo que funciona y podría funcionar mejor

### 4. El vencimiento tiene una ventana de hasta una hora

Decisión **D23**: el paso a `VENCIDO` lo hace un barrido, y Beat lo corre cada hora. Un cobro
puede estar vencido de hecho y figurar `PENDIENTE` durante ese rato.

**Es aceptable y está dicho:** la mora no es un evento al segundo. `Cobro.esta_vencido_a`
existe justamente para quien necesite el hecho del calendario sin esperar al barrido, y la
pantalla podría usarlo si alguna vez la diferencia molesta.

### 5. La cadena de recordatorios se pone al día de a un paso por corrida

Decisión **D25**. Si el worker estuvo caído tres días, un cobro que debía recibir los pasos 1,
2 y 3 recibe el 1 en la primera corrida, el 2 en la siguiente, y así.

**Es lo correcto** —tres mensajes en un minuto es peor que tres mensajes tarde— pero significa
que ponerse al día lleva tantas horas como pasos atrasados. Si eso alguna vez importa, la
respuesta no es mandar todo junto: es correr el barrido más seguido durante la recuperación.

### 6. No hay paginación en el listado de cobros

Igual que el listado de comprobantes del épico 5. Las métricas **sí** están preparadas: se
suman en la base y sobre el período entero, no sobre la página, así que agregar paginación no
va a hacer que el encabezado empiece a mentir. **Épico 9**, junto con la del resto del panel.

### 7. Un reembolso parcial no deja el cobro «parcialmente reembolsado»

`monto_reembolsado` guarda cuánto se devolvió, pero el estado va a `REEMBOLSADO` sea total o
parcial. El enum del DER no tiene un estado intermedio y **no se le agregó uno** por lo mismo
que decidió D27: los estados que representan un matiz de otro estado se pagan en cada
transición del resto del sistema.

Quien necesite la distinción la tiene en el monto, que es un dato y no un estado.

---

## Lo que este épico dejó preparado para otros

### 8. `cobro.turno_id` existe y nadie lo escribe · **épico 7**

HU-E6-07 —asociar un cobro a un turno como seña— está asignada al épico 7, no a éste. La
columna existe, sin FK (hallazgo H4 del DER, `turno` es de otro bounded context), y
`GenerarCobro` ya acepta el parámetro. Lo que falta es quien produzca el turno.

### 9. HS-T1 RN-03 actualiza el comprobante pero todavía no el turno

«si está asociado a un turno como seña, se actualiza el estado del turno». La mitad del
comprobante está hecha (decisión D26); la del turno espera al **épico 7**, y va a entrar como
un segundo ACL al lado de `SaldoViaBilling` — el lugar ya está y la forma también.

### 10. Los otros dos tipos de `ReglaDeNegocio` no tienen configuración tipada

`TipoRegla` tiene los tres valores del DER desde el principio, pero sólo
`ESCALAMIENTO_DE_COBRO` tiene su clase de configuración. `POLITICA_DE_TURNO` la suma el
**épico 7** y `AGENDA_DE_NOTIFICACION` el **épico 8**, cada uno con su propia validación
(decisión D24).

El enum está completo desde ahora a propósito: es parte de una clave de almacenamiento, y un
catálogo ampliado más tarde por una unidad que no tiene otro motivo para tocar ese archivo es
peor que uno escrito una vez.

### 11. PAN-CFG-NOT (plantillas de notificación) no es de este épico

HU-E11-02 está asignada al **épico 8**, con el resto de lo conversacional. La tabla
`plantilla_de_notificacion` del DER todavía no existe, y por eso los recordatorios de este
épico arman su texto en el adaptador de envío en vez de leer una plantilla.

---

## Deuda de este épico que conviene no olvidar

### 12. `PasarelaSimulada` decide rechazar un reembolso por la palabra «rechazar»

Es un truco para poder caminar la rama de HU-E6-05 RN-03 en una laptop sin editar código, y
está documentado en la clase. **No es una API**: si alguna vez hace falta más de una condición
simulada, la respuesta es un doble configurable y no una segunda palabra mágica.

### 13. El token de MercadoPago se lee y no se refresca en el momento

`TokenDesdeIntegraciones` lee la credencial guardada. El refresco lo hace el barrido diario de
`integrations` (épico 2), así que un token vencido entre dos barridos hace fallar el cobro con
`PasarelaNoDisponible` en vez de refrescarse al vuelo.

**Es una decisión consciente**: refrescar dentro del request de un cobro significa escribir la
credencial nueva en la transacción del cobro, y un rollback por cualquier otro motivo perdería
el refresco. El margen del barrido (15 días) es mucho mayor que la vida del token, así que la
ventana es teórica — pero está dicha.

### 14. `npm run format:check` marca 163 archivos en Windows, y ninguno está mal

El repositorio no tiene `.gitattributes` y este entorno tiene `core.autocrlf=true`, así que git
convierte a CRLF al bajar y Prettier —que espera LF— rechaza **todos** los archivos, los de este
épico y los de los cinco anteriores por igual. En CI, sobre Linux, el checkout es LF y la
verificación pasa.

**La trampa es real:** correr `prettier --write` para «arreglarlo» produce un diff de 163
archivos que git vuelve a convertir en el próximo checkout. La verificación local honesta es
`npx prettier --check --end-of-line auto .`, que es la que se corrió acá.

El arreglo de fondo es un `.gitattributes` con `* text=auto eol=lf`, y **no es de este épico**:
toca el repositorio entero y merece su propio cambio, con la renormalización que implica.
