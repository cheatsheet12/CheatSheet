# Pendientes — Épico 7 · Agenda y recursos

> Lo que este épico deja abierto, con **por qué se dejó** y **quién lo cierra**. Un pendiente
> sin dueño es un pendiente que nadie va a mirar, así que cada uno dice de qué épico es.

---

## Lo que bloquea una demo real

### 1. El aviso de turno sale a un log, no a WhatsApp · **épico 8**

`AvisoPorConsola` registra el mensaje y no manda nada. Es el único adaptador del épico que no
tiene par real, y es deliberado: el canal es WhatsApp Business y su cliente lo construye el
épico 8 junto con el agente. Es exactamente el mismo pendiente que dejó el épico 6 con los
recordatorios de cobro, y se cierra con el mismo adaptador.

**Lo que sí se hizo para que el pendiente no muerda:** el doble se niega a arrancar en
producción, así que no se puede desplegar sin que alguien se entere; y el texto de los tres
avisos ya está escrito y probado, así que lo que falta es el transporte, no el mensaje.

### 2. Nadie confirma un turno todavía

`Turno.confirmar()` existe y la transición `RESERVADO → CONFIRMADO` es legal, pero **ningún
caso de uso la llama**. La confirmación la da el cliente, y el cliente habla por WhatsApp:
es del **épico 8**.

La agenda muestra el estado igual y el filtro de PAN-AGE-01 lo ofrece, así que el día que
llegue no hay que tocar ni la pantalla ni el esquema.

---

## Lo que funciona y podría funcionar mejor

### 3. La agenda trabaja en una sola zona horaria

Decisión **D34**. `ZONA_DE_LA_AGENDA` es una constante porque el DER no le da zona horaria a
`empresa` — sólo `usuario.pref_zona_horaria`, que es preferencia de visualización.

**Qué haría falta:** una columna `empresa.zona_horaria`, y que `RecursoReservable` la reciba en
lugar de leer la constante. El punto de cambio es una función de tres líneas (`_local` en
`domain/recurso.py`), y está así justamente para que ese cambio sea uno solo.

**Mientras tanto no muerde:** todas las empresas del alcance operan en Argentina, y el país no
tiene horario de verano. El test que compara un turno de las 22 contra su lectura en UTC es el
que va a seguir cuidando esto cuando cambie.

### 4. El selector de horarios puede ofrecer una franja que se toma un segundo después

Decisión **D28** y su consecuencia. `GET /turnos/disponibilidad` marca los horarios ocupados
en el momento de la consulta; entre esa respuesta y el `POST` puede entrar otro turno.

**Es aceptable y está dicho** —en el docstring de `DisponibilidadSalida` y en la pantalla—:
quien decide es la restricción de exclusión, y reservar puede fallar con «El horario
seleccionado no está disponible.» aunque figurara libre. La alternativa sería bloquear la
franja al abrir el formulario, que deja horarios reservados por gente que se fue a almorzar.

### 5. No hay paginación en la agenda ni en el listado de recursos

Igual que los listados de los épicos 5 y 6. La agenda se acota por rango de fechas, que en la
práctica la mantiene chica —un día, una semana— pero un rango largo trae todo. **Épico 9**,
junto con la paginación del resto del panel.

### 6. El catálogo de servicios agendables trae hasta 50

`CatalogoViaMasterData.listar_agendables` usa `ListarServicios` con su página por defecto. Una
empresa con más de 50 servicios no vería los últimos en el selector de PAN-AGE-02.

**Por qué quedó así:** los filtros y la paginación de `master_data` viven en su `domain/`, y
R3 prohíbe que `scheduling` los importe. Pasar una página explícita requeriría o mover
`FiltrosDeServicio`/`Pagina` a la capa de aplicación de ese contexto —cambio que le pertenece a
`master_data`— o publicar una consulta pensada para este caso. **Épico 9**, junto con la
paginación general; es el mismo cambio.

### 7. Un turno no se puede editar, sólo mover o cancelar

No hay forma de cambiarle el cliente ni el servicio a un turno existente. Ninguna historia lo
pide: HU-E7-02 habla de cancelar y reprogramar, y cambiar el servicio cambia la duración, que
cambia la franja, que es una reprogramación con otro nombre.

Si alguna vez hace falta, la respuesta es cancelar y crear, que además deja los dos hechos en
la bitácora en vez de uno solo mal contado.

---

## Lo que este épico dejó preparado para otros

### 8. El agente todavía no reserva · **épico 8**

`CanalDeReserva.AGENTE` existe desde ahora y `ReservarTurno` acepta el canal como parámetro,
así que el agente de WhatsApp entra por el mismo caso de uso que el panel — con las mismas
validaciones y el mismo rechazo por solapamiento. Lo que falta es quien lo llame.

`GET /turnos/disponibilidad` está construido pensando en eso: es la consulta que el agente
necesita para ofrecer horarios reales, y por eso devuelve los horarios del recurso y no una
vista de pantalla.

### 9. `POLITICA_DE_TURNO` sigue sin configuración tipada · **épico 8**

Es el pendiente #10 del épico 6, del otro lado. `TipoRegla` tiene el valor desde el épico 6,
pero nadie escribe ni lee su configuración. Lo que va a contener —cuánta anticipación mínima,
cuántas horas antes se puede cancelar— es política de turnos, y la va a consumir el agente.

**Este épico no la necesitó**: un turno creado desde el panel lo crea alguien que trabaja en la
empresa, y no hay regla que le impida agendar para dentro de diez minutos.

### 10. HS-T1 RN-03 ahora sí puede cerrarse · **épico 8**

«Si el cobro está asociado a un turno como seña, se actualiza el estado del turno». Es el
pendiente #9 del épico 6, y la mitad que faltaba ya está: `AsignarSenaAlTurno` existe y
`turno.cobro_id` se escribe.

Lo que todavía **no** existe es el camino inverso —que aprobar el cobro confirme el turno—,
porque confirmar un turno es lo que hace el cliente (pendiente #2) y el ACL de `payments` hacia
`scheduling` se arma en el épico que introduzca el flujo completo de la seña.

### 11. El recordatorio de turno no existe · **épico 8**

`AGENDA_DE_NOTIFICACION` es el tercer `TipoRegla` y es lo que va a gobernar «recordale al
cliente el turno de mañana». No hay barrido de Beat en este épico y es a propósito: sin canal
real de WhatsApp, un barrido escribiría recordatorios en un log.

---

## Deuda de este épico que conviene no olvidar

### 12. El nombre de la restricción se compara como texto

`RepositorioTurnoPostgres` decide si un `IntegrityError` es un solapamiento buscando
`"excl_turno_recurso_franja"` dentro del texto del error. asyncpg no expone el nombre de la
restricción de forma tipada a través de SQLAlchemy, así que es eso o tragarse todos los
`IntegrityError` como «ocupado» — que diría algo falso sobre la mitad de ellos.

**El riesgo real:** si alguien renombra la restricción en una migración futura y no toca la
constante, el doble booking evitado vuelve a llegar como un 500. La constante está al lado del
nombre en el módulo y el test de integración se cae si dejan de coincidir, que es lo que hace
que el riesgo sea detectable.

### 13. `_reemplazar_hijos` borra y reescribe las tres tablas del recurso

Guardar un recurso hace `DELETE` + `INSERT` de sus patrones, excepciones y servicios, en lugar
de reconciliar fila por fila. Un horario semanal tiene siete filas en el peor caso, así que el
costo es nada.

**Lo que sí cambia:** los `id` de las filas hijas cambian en cada guardado. Nadie los referencia
—no salen por la API, que devuelve el recurso entero— pero si alguna vez alguien quisiera
apuntar a una excepción por id, esto es lo primero que hay que cambiar.

### 14. La apertura especial hereda la duración de slot del patrón

El DER no le da columna `duracion_slot_min` a `excepcion_de_disponibilidad`, así que
`horarios_del_dia` la toma del patrón de ese día, o del más corto del recurso, o —si no hay
ninguno— ofrece la franja entera como un solo turno.

Es una regla derivada que nadie escribió, y está documentada en el método. Si el comportamiento
sorprende a alguien, la respuesta es la columna en el DER, no una segunda heurística.
