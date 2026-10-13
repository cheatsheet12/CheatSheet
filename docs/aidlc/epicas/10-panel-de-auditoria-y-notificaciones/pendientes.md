# Pendientes — Épico 10 · Panel de auditoría y notificaciones

> Lo que este épico deja abierto, con **por qué se dejó** y **quién lo cierra**. Un pendiente
> sin dueño es un pendiente que nadie va a mirar.
>
> Es el último épico del roadmap, así que varios de estos ya no tienen «el épico que viene»: lo
> que tienen es la primera persona que se los encuentre.

---

## Lo que la pantalla todavía no puede hacer

### 1. La búsqueda no encuentra por nombre de cliente · **decisión D77**

RN-03 dice «búsqueda por operación, cliente o archivo». Hoy se busca sobre `accion` y
`entidad_afectada`, así que se encuentra por **id** de cliente y por nombre de operación, no por
«Ferretería Ñandú».

Hay dos formas de cerrarlo, y ninguna es un `JOIN` desde este contexto:

1. **Que el emisor escriba el nombre en `detalle`.** La columna ya existe (D72) y es un campo
   más en el evento. Cuesta que cada emisor se acuerde, y mete un dato personal en una tabla
   inmutable — que es exactamente lo que D72 dice que no debe pasar.
2. **Que la pantalla resuelva el id contra `master_data` antes de buscar.** El frontend ya tiene
   las dos features; sería buscar el cliente, tomar su id y filtrar por él. Es más trabajo de
   pantalla y no ensucia la bitácora.

**La segunda es la que este épico recomienda.** Queda escrita acá para que quien la haga no
tenga que redescubrir por qué la primera es tentadora y peor.

> **Resuelto en parte (13/10/2026, #176, unidad `busqueda-por-cliente`):** la pantalla resuelve el
> nombre contra `master_data` y manda los ids (`cliente_id`); la búsqueda trae las operaciones sobre
> `Cliente:<id>` y las que guardan ese `cliente_id` en su `detalle`. Las operaciones de turno ya lo
> guardan —un id, nunca el nombre, así que D72 se respeta—. **Falta lo mismo en `payments` y
> `billing`:** sus eventos todavía no dicen de qué cliente son, y una búsqueda por cliente no
> encuentra sus cobros ni sus comprobantes. Las operaciones registradas antes del cambio no se
> completan: la tabla es inmutable.

### 2. No hay forma de cerrar un ticket desde el panel · **decisión D80**

Es deliberado —el estado lo mueve CheatSheet—, pero significa que un ticket abierto por error
queda abierto para siempre desde el punto de vista de la empresa.

**Lo que hace falta si se decide que sí:** un `POST /soporte/{id}/cierre` que sólo permita
`ABIERTA → CERRADA` y sólo a quien lo abrió. El agregado ya tiene la transición; lo que falta es
decidir si «cerrada por la empresa» y «cerrada por soporte» son el mismo estado.

### 3. El globito de no leídas no está en el layout

`ContarNoLeidas` existe y la API lo devuelve en cada listado, pero el número no se muestra en la
barra de navegación: hay que entrar a la pantalla para verlo.

**Lo que hace falta:** una llamada en el layout del panel y un badge. Es media hora de frontend y
no toca backend.

---

## Lo que depende de que alguien decida

### 4. Sólo se notifica lo que falla · **decisión D74**

Hay avisos que una PyME querría y que hoy no llegan: «tu certificado de ARCA vence en quince
días», «la sincronización de la planilla terminó», «el paquete contable de marzo está listo».

Cada uno es una decisión de producto, no de código: el mecanismo está —un `EventoAuditable` y una
categoría— y lo que falta es elegir cuáles valen la pena. Agregarlos todos convierte el centro en
un feed, que es lo que D74 evitó a propósito.

### 5. Las notificaciones no salen por email

`CanalDeNotificacion` tiene `EMAIL` desde el épico 1 y las preferencias lo guardan, pero este
épico sólo alimenta el canal `PANEL`. Alguien suscripto por email a «Cobros» no recibe nada.

**Lo que hace falta:** un segundo suscriptor que arme el mensaje y lo mande por el transporte
compartido de `platform/email.py`, más una plantilla. El puerto y el transporte ya existen desde
el épico 2; lo que hay que pensar es la frecuencia — un mail por cada error es un mail de más.

### 6. `plantilla_id` se guarda y no se usa

El DER le da a `notificacion` una FK a `plantilla_de_notificacion` y la migración la declara. Hoy
siempre es `NULL`: el texto lo escribe el suscriptor en el momento.

Tiene sentido el día que las notificaciones salgan por WhatsApp o por email, donde el texto sí
tiene que ser editable sin tocar código (que es lo que las plantillas del épico 8 resuelven). Por
ahora, una plantilla para una frase de una línea sería una indirección sin lector.

---

## Deuda técnica conocida

### 7. La paginación es por desplazamiento · **decisión D81**

La página 400 de una empresa con un millón de operaciones va a ser lenta. El cambio, cuando haga
falta, es en el repositorio: el puerto recibe un filtro, no un número de página, así que la
pantalla no se entera.

### 8. El timeline depende de que la entidad se escriba igual en todos los pasos

Es la contracara de D71. `entidad_afectada` es una cadena `Tipo:id` y nadie la valida contra un
formato: un emisor que escriba `comprobante:<id>` en minúscula deja ese paso fuera del timeline,
y el síntoma es una pantalla a la que le falta un paso — no un error.

**Lo que hace falta:** o un helper compartido que arme la cadena (`entidad(Comprobante, id)`), o
un test que recorra los emisores. Lo primero es mejor y son diez líneas en `shared/auditoria.py`.

### 9. `workers/tasks_observability.py` sigue al 46 %

Es el barrido de la DLQ, del épico 4, y este épico no lo tocó. Lo que está probado es el caso de
uso; lo que falta es la mecánica del reparto contra una base real. El total del backend queda en
**87 %**, bien por encima del umbral.

---

## Lo que el sistema entero deja abierto

Con este épico se cierran las diez del roadmap. Lo que queda para una versión siguiente está
repartido en los `pendientes.md` de cada uno; los tres que más pesan:

- **Los adaptadores simulados que todavía no tienen par real**: el proveedor de embeddings y el
  transcriptor de audio (épico 8). Los dos se niegan a arrancar en producción, así que no se
  puede desplegar sin que alguien se entere.
- **El almacenamiento en memoria** (épicos 3, 5 y 9): configurar R2 es una variable de entorno,
  y sin eso los archivos generados no sobreviven a un reinicio.
- **La reportería recorre comprobantes en Python** (épico 9, pendiente 6): correcto para una
  PyME, caro para la empresa que crezca. La consulta agregada es trabajo de `billing`.
