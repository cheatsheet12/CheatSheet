# Decisiones — Épico 10 · Panel de auditoría y notificaciones

> Lo que este épico decidió, **por qué**, y qué se paga por ello. Una decisión sin costo
> anotado es una decisión que nadie revisó.
>
> Cierran la serie del sistema: D1–D19 en [`units.md`](../../units.md), D20–D27 en el
> [épico 6](../06-cobros-y-recordatorios/decisiones.md), D28–D37 en el
> [épico 7](../07-agenda-y-recursos/decisiones.md), D38–D50 en el
> [épico 8](../08-agente-de-whatsapp/decisiones.md) y D51–D70 en el
> [épico 9](../09-reporteria-y-paquete-contable/decisiones.md).

---

## D71 — el timeline **es la bitácora**, filtrada por entidad

HU-E12-02 RN-01 pide «el timeline de ejecución con sus pasos internos». La lectura obvia es una
tabla de pasos: `paso_de_operacion`, con su nombre, su momento y su resultado.

**No hace falta, y tenerla sería peor.** Cada paso de una operación ya escribe su propia fila en
`registro_de_auditoria` nombrando la misma `entidad_afectada`: un comprobante deja `validar`,
`enviar_a_arca` y `autorizar`. El timeline es esa consulta, ordenada por timestamp.

Una segunda tabla significaría **escribir dos veces lo mismo** y, el día que las dos no
coincidan, tener dos versiones de qué pasó — que es lo único que una bitácora no puede
permitirse. Y significaría además que un contexto que agrega una operación nueva tiene que
acordarse de escribir en las dos.

**La duración sale de lo mismo**: la distancia entre la primera fila y la última (RN-03). Una
operación que dejó **una sola** fila no tiene duración: se devuelve `None` y la pantalla dice
«No registrada», porque «0 ms» sería afirmar algo que nadie midió.

**Lo que cuesta:** el timeline depende de que la `entidad_afectada` se escriba igual en todos
los pasos. Ya era así —es una cadena `Tipo:id`— pero ahora tiene una consecuencia visible, y
está anotado en los pendientes.

---

## D72 — `detalle jsonb`, nullable, y **casi siempre vacío**

Lo que el timeline no puede reconstruir son «los datos de entrada que la dispararon» y «los
datos de salida del servicio externo» (RN-01). Eso sí necesita una columna, y llega como
`registro_de_auditoria.detalle jsonb` **nullable y sin `server_default`**: la tabla ya tiene
filas y no se puede reescribir —HS-T5 RN-03 le niega el `UPDATE` al rol de la aplicación—, y una
columna nullable se agrega sin tocar una sola fila.

**Un solo emisor la llena hoy**: la autorización de un comprobante, que es la que RN-02 nombra
(«para operaciones fiscales, el detalle incluye los datos del comprobante y el resultado de
ARCA»). Guarda tipo, número, total, estado, CAE y —cuando ARCA dice que no— el código y la
descripción **tal como los contestó**, porque parafrasearlos los volvería imposibles de buscar.

**Nunca datos personales y nunca un secreto.** Lo que entra ahí lo lee cualquiera que abra el
panel de auditoría, y vive para siempre en una tabla que nadie puede corregir.

**Lo que cuesta:** casi todas las operaciones muestran «Esta operación no registró datos
adicionales.». Es la verdad, y decirla es mejor que inventar un detalle a partir de lo que se
puede deducir.

---

## D73 — Solo Lectura **no entra** a la bitácora

RN-05 y RN-04 lo dicen textualmente, y el encabezado de la épica 12 explica por qué: ese rol
puede corresponder a un actor externo o de alcance amplio, y la bitácora expone el registro
crudo de toda la operación —incluidos datos de clientes y mensajes de terceros—. Lo fiscal que
un contador necesite sale por los reportes y el paquete contable del épico 9.

**El guarda vive en el caso de uso**, no en el router: es lo que PRU-09 enseñó. Y por eso
`ListarOperaciones` acepta `rol=None` — hay un llamador que no es una persona, el reporte de
operaciones del épico 9, que ya comprobó el permiso de quien lo pidió. Un rol obligatorio ahí
habría significado inventarle uno a un contexto.

**Lo que cuesta:** el centro de notificaciones sí lo ve ese rol, y eso podría leerse como una
inconsistencia. No lo es: RN-05 de HU-E11-03 le niega las **acciones de gestión**, y marcar como
leída una notificación propia es acuse de recibo, no gestión.

---

## D74 — se notifica **lo que salió mal**, y a quien se suscribió

El DER tiene `notificacion` y HU-E11-03 la muestra, pero ninguna historia dice quién la crea.
Había que elegir, y la elección gobierna si la pantalla sirve.

**Lo que se hizo:** `NotificarPorEventos` es un suscriptor del mismo publicador que la bitácora,
enganchado en el composition root. Convierte en notificación **sólo** los eventos con
`Resultado.ERROR`, con severidad alta, y sólo para los usuarios activos que eligieron esa
categoría en el canal `PANEL` (RN-02, las preferencias de HU-E1-07). La traducción entre módulo
de la bitácora y categoría de suscripción vive en una tabla, `CATEGORIA_DE`, escrita una vez.

Un aviso por cada operación exitosa sería un centro que nadie mira — y un centro que nadie mira
hace que la vez que sí importaba pase desapercibida entre doscientas que no.

**Lo que cuesta:** hay avisos que una PyME querría y que hoy no llegan —«tu certificado vence en
quince días», «se sincronizó la planilla»—. Cada uno es un `EventoAuditable` con otro resultado,
o un emisor propio. Está en los pendientes.

---

## D75 — notificar **no puede** romper la operación que lo produjo

El suscriptor corre dentro de la transacción de la operación que describe. Si dejara escapar su
excepción, un cobro confirmado se desharía porque no se pudo escribir un aviso en el panel.

`NotificarPorEventos.manejar` atrapa, registra y sigue. Es la misma regla que D33 (el aviso de un
turno) y D48 (el canal del agente), aplicada al canal más barato de todos — y es lo contrario de
D58 (el mail del contador), donde el mensaje **es** el hecho de negocio.

**Lo que cuesta:** un aviso puede perderse sin que nadie se entere salvo por una línea de log.
Es el modo de falla correcto para algo que describe un hecho que ya ocurrió.

---

## D76 — marcar leída es **de ida**, y sobre la propia

`marcar_leida` es idempotente y no existe `marcar_no_leida`. «Lo vi» es un hecho; un botón que
lo deshace convierte el estado de lectura en una preferencia de interfaz, que es justo lo que
deja de servir para saber si alguien se enteró de que la sincronización viene fallando hace tres
días.

Y el destinatario se compara en el caso de uso, no se delega a RLS: **RLS acota a la empresa y
adentro de una empresa hay varias personas**. Dos operadores comparten política y no comparten
bandeja. Una notificación ajena da el mismo error que una inexistente, como en todo el sistema.

**Lo que cuesta:** quien marcó por error no puede desmarcar. La notificación sigue en la lista.

---

## D77 — la búsqueda mira `accion` y `entidad_afectada`, y nada más

RN-03 pide «búsqueda por operación, cliente o archivo». Las tres cosas están escritas en esas dos
columnas: la acción dice qué se hizo, y la entidad dice sobre qué — `Cliente:<id>`,
`Planilla:<id>`.

Buscar el **nombre** de un cliente exigiría un `JOIN` contra `master_data`, que R3 no permite
desde acá, y convertiría la bitácora en una vista de clientes — con los datos personales que la
épica justamente decidió no abrirle a Solo Lectura.

**Lo que cuesta:** hoy se busca por id de cliente y por nombre de operación, no por «Ferretería
Ñandú». Es una limitación real y está en los pendientes con las dos formas de resolverla.

---

## D78 — el filtro viaja con **el mismo texto que la tabla muestra**

`identity`, `ia`, `error`: los valores de los enums, que es lo que la API devuelve. No los
nombres de los miembros (`IDENTITY`, `IA`, `ERROR`).

Un filtro que hay que escribir distinto de como se lee obliga al frontend a traducir, y esa
traducción es donde una mayúscula de más devuelve la lista entera sin que nadie lo note. Y un
valor que no existe **se rechaza** en vez de ignorarse, por lo mismo: un filtro inválido que
devuelve todo le hace creer al usuario que filtró.

**Lo que cuesta:** los valores en minúscula se ven en la URL. Es un detalle estético contra una
clase entera de bug silencioso.

---

## D79 — `SolicitudDeSoporte` vive en `observability`

Donde el DER la pone, y con una razón que se sostiene: el ticket que alguien abre casi siempre
cita una operación que salió mal, y este es el contexto que sabe qué pasó. Un contexto nuevo para
cuatro columnas sería una carpeta más y la misma información del otro lado de una frontera.

---

## D80 — el estado del ticket lo mueve **CheatSheet**, no la empresa

RN-03: «la solicitud queda en estado abierto hasta que el equipo de CheatSheet la atienda y la
cierre». El agregado tiene la máquina de estados completa —`ABIERTA → EN_REVISION → RESUELTA →
CERRADA`— y la API de este épico expone **sólo el alta y la consulta**.

Dejar que el administrador cierre su propio ticket convierte «resuelta» en una opinión, y el
número que mide a soporte —cuánto tardó en contestar— deja de significar algo.

**`CERRADA` no vuelve**, además: reabrir un ticket pierde la fecha en que se resolvió. Si el
problema sigue, se abre otro y se cita el anterior — que de paso deja ver que pasó dos veces.

**Lo que cuesta:** no hay forma de cerrar un ticket desde el panel, ni siquiera uno abierto por
error. Está en los pendientes.

---

## D81 — la paginación es por **desplazamiento**, no por cursor

La pantalla del panel es una tabla con paginado clásico y un total al pie. Un `OFFSET` sobre el
índice `(empresa_id, timestamp)` es barato en las primeras páginas, que son las que alguien
mira, y permite mostrar «página 2 de 40» — que un cursor no permite sin contar igual.

**Lo que cuesta:** la página 400 de una empresa con un millón de operaciones es lenta. Cuando eso
pase, el cambio es en el repositorio y no en la pantalla: el puerto ya recibe un filtro, no un
número de página.

---

## D82 — el Administrador abre los tickets, y el listado es **de la empresa**

El actor de HU-E9-03 es el Administrador, así que sólo él abre. Pero lo que se lista son las
solicitudes de la **empresa**, no las de la persona: dos administradores de la misma empresa no
tienen por qué abrir el mismo ticket dos veces porque cada uno ve sólo el suyo.

Es la misma línea que separa la bandeja de notificaciones —que sí es personal, porque la escribe
una preferencia personal— de todo lo demás, que es de la empresa.

---

## D101 — una **operación fallida** es una falla de ejecución, no un rechazo de validación

> Agregada el 13/10/2026, durante las pruebas manuales de la Etapa 6 (issue #168). Pendiente de
> confirmación del revisor de HS-T5.

La prueba en staging encontró que ningún rechazo de Agenda —franja ocupada, horario pasado,
excepción duplicada, slot fuera de rango— llega a la bitácora con resultado `ERROR`, y lo leyó
contra HS-T5 RN-04 («se registran tanto las exitosas como las fallidas»). Había que decidir qué
cuenta como «fallida».

**Lo que se decide:** una operación fallida es una operación que **se intentó ejecutar y no
terminó bien** —ARCA rechazó el comprobante, MercadoPago no respondió, el padrón falló, una tarea
agotó sus reintentos—. Un pedido que un caso de uso **rechaza por una regla de negocio antes de
ejecutar nada** no es una operación fallida: no ocurrió, no cambió nada, y quien lo pidió ya ve
el motivo en la pantalla con la frase de la historia. No va a la bitácora.

Es lo que el sistema ya hace en todos los contextos: `billing`, `payments`, `identity`,
`reference_data` y el envío de recordatorios publican `Resultado.ERROR` sólo ante fallas de
ejecución, y ninguno lo hace ante un rechazo de validación.

**Por qué no la otra lectura:**

- La bitácora se escribe **en la misma transacción** que la operación (unidad
  `cimientos-y-bitacora`). Un rechazo levanta una excepción y la transacción se deshace: registrarlo
  obligaría a atrapar, confirmar y relanzar en cada ruta, el patrón de #47, sólo para guardar algo
  que no pasó.
- Cada evento `ERROR` se convierte en una notificación de **severidad alta** (D74). Con los
  rechazos adentro, cada «El horario seleccionado no está disponible.» sería una alerta roja para
  el Administrador, y el centro de notificaciones se llenaría de lo que D74 quiso evitar.

**Consecuencia:** HS-T5 RN-04 queda cubierta por los errores de ejecución que ya se registran.
Si alguna vez hace falta saber cuántas veces se intentó reservar una franja ocupada, eso es una
métrica de uso, no una fila de auditoría.
