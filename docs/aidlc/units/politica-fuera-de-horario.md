# Unidad: politica-fuera-de-horario

**HUs**: HS-T2 (RN-04 y su criterio «El mensaje llega fuera del horario de atención»), HU-E11-01 (RN-01, RN-04, RN-05), HU-E8-05 (RN-04)   **Contexto dueño**: business_config (regla `HORARIO_DE_ATENCION`: configuración, validación y cálculo de «¿está abierto?»); conversational la aplica leyendo el servicio de aplicación publicado de business_config detrás de un ACL propio   **Rama**: feature/business_config-politica-fuera-de-horario   **Responsable**: Luciano

> Origen: issue **#71** (I-09, «No existe la política de fuera de horario», Mayor), probado en
> staging el 03/10/2026: «No hay horario de atención configurable, ni interruptor de "agente
> activo", ni definición de la política». La decisión de producto que el issue pedía ya está
> tomada (**opción (c)**, Luciano, 2026-10-05; ver «Decisiones tomadas durante la unidad»).
>
> **Base:** `develop` en `24ab1e6` (U10 `reserva-y-cancelacion-por-whatsapp` ya mergeada, cabeza
> de migraciones `0032`). No depende de Meta, del ADR-0011 ni de U5–U8 (ver «Coordinación»).
> **No necesita migración** (ver Infraestructura).
>
> **Gate 1 aprobado** (Luciano, 2026-10-05) con las seis recomendaciones y tres ajustes que este
> plan ya incorpora: **horario cortado** y **fechas sin atención** entran al alcance, y la
> respuesta a un diálogo en (b) **agrega la oración de fuera de horario** (choque entre las
> preguntas 3 y 4, ver T9).

## Qué hace

Hoy el agente contesta igual a las 3 de la mañana que a las 11, y cuando deriva a un asesor le
dice al cliente «Lo derivo con un asesor que va a continuar la conversación.» aunque nadie vaya a
leerlo hasta el día siguiente. No hay dónde cargar el horario de atención ni la política.

Después de esta unidad:

- **La empresa carga su horario de atención** —una o varias franjas por día de la semana
  (**horario cortado**, p. ej. 09:00–13:00 y 16:00–20:00), o el día cerrado— y **las fechas sin
  atención** (feriados, vacaciones: el negocio cerrado todo ese día, sea el día de la semana que
  sea), y **elige su política fuera de horario** en la configuración del agente (PAN-WA-02), como
  muestra el prototipo. Se guarda como una regla de negocio más (HU-E11-01): aparece en
  PAN-CFG-RN con su tipo, prioridad y estado, y desactivarla deja de aplicarla de inmediato.
- **«Fuera de horario»** es todo lo que no cae dentro de una franja: la noche, el día cerrado, el
  **hueco entre dos franjas del mismo día** (13:30 con 09–13 y 16–20) y una **fecha sin atención**.
- **Política por defecto — «El agente responde siempre» (a).** Fuera de horario el agente sigue
  contestando, reservando y cancelando como de día. Lo único que cambia es la derivación: cuando
  el cliente pide una persona o el agente escala, el aviso agrega desde cuándo lo va a atender un
  asesor («…Ahora estamos fuera del horario de atención: un asesor te va a responder a partir del
  lunes 12/10 a las 09:00.»).
- **Política alternativa — «Fuera de horario, mensaje fijo» (b).** Fuera de horario el agente
  **no contesta**: el mensaje se registra igual y el cliente recibe un único mensaje fijo por
  período de cierre con el horario en que se lo atiende. **El modelo no se llama.** La excepción
  es la respuesta a una oferta que el agente hizo antes de cerrar (elegir un horario, confirmar
  una cancelación): se atiende sin el modelo y **termina con la oración de fuera de horario**.
  **Visibilidad:** esos mensajes nocturnos quedan guardados en la conversación, pero **no
  aparecen en la vista inicial de la bandeja PAN-WA-01**, que arranca filtrada por conversaciones
  escaladas (`conversaciones/page.tsx:25`, `solo_escaladas=true`): el operador los ve sólo si
  quita el filtro («Todas», `BandejaDeConversaciones.tsx:79, 132`). Es coherente con la decisión:
  en (b) no se escala, y el mensaje fijo le pide al cliente que vuelva a escribir en horario.
- **Sin horario configurado, nada cambia**: el agente atiende y deriva como hoy. Una empresa que
  nunca entró a la pantalla no puede quedar muda de golpe.
- Lo que no cambia: el modelo **no decide** si el negocio está abierto ni qué política rige. Eso
  lo calcula una función pura de business_config sobre la hora argentina; el modelo ni se entera.

**Fuera de esta unidad:**
- **Calendario automático de feriados nacionales.** Depende de un tercero (una fuente oficial o un
  servicio que publique los feriados y sus traslados). Mientras tanto, la empresa carga a mano sus
  fechas sin atención. Queda como pendiente del épico 8.
- **Que una fecha sin atención bloquee la agenda.** El horario de atención no es la
  disponibilidad de los recursos (T1): para que un recurso no se pueda reservar un feriado, se
  carga la excepción del recurso en PAN-AGE-03 (HU-E7-05), como hoy. La pantalla lo avisa.
- **Zona horaria por empresa.** El DER no la tiene; todo el sistema usa `ZONA_ARGENTINA` (D-épico
  7, `ZONA_DE_LA_AGENDA`). El prototipo dice «Zona horaria: ART (GMT-3)» como texto fijo.
- **El interruptor «Agente activo»** del encabezado de PAN-WA-01/02 (Pregunta 6, resuelta: queda
  como pendiente del épico 8).
- **Textos editables por la empresa** (Pregunta 5, resuelta: textos fijos del sistema).
- **Cambios en la bandeja PAN-WA-01** (su filtro inicial sigue siendo «sólo escaladas»; ver la
  nota de visibilidad arriba y el punto 5 de «Decisiones tomadas»).

## Las historias

> **HS-T2 — Procesar un mensaje entrante recibido desde WhatsApp**
> Precondiciones: «La integración de WhatsApp está operativa.» · «El agente está activo o existe
> un operador disponible.»
> * RN-01: El proceso registra el mensaje entrante con su contenido, tipo y conversación asociada,
>   conforme a la entidad Mensaje.
> * RN-03: Si la confianza de interpretación es insuficiente, se inicia un escalamiento a un asesor
>   humano.
> * **RN-04: Si el mensaje llega fuera del horario de atención configurado, el sistema responde
>   según la política definida.**
> * RN-05: El evento queda registrado en la bitácora con iniciador IA.
>
> | Cuando | Espero | Referencia |
> | :---- | :---- | :---- |
> | **El mensaje llega fuera del horario de atención** | **El sistema responde según la política configurada para fuera de horario** | Bitácora |

> **HU-E11-01 — Definir reglas de negocio parametrizables** (PAN-CFG-RN)
> * RN-01: Cada regla tiene un tipo, una configuración parametrizable, una prioridad y un estado
>   activo/inactivo, conforme a la entidad ReglaDeNegocio.
> * RN-04: Una regla desactivada deja de aplicarse de forma inmediata sin afectar las operaciones
>   ya procesadas bajo ella.
> * RN-05: Cuando existe más de una regla aplicable, se resuelve por su prioridad.

> **HU-E8-05 — Ser derivado a un asesor humano**
> * RN-04: El cliente recibe un aviso de que su conversación fue derivada.
> * CA: «Mi conversación es derivada → Recibo un aviso, por ejemplo "Lo derivo con un asesor que
>   va a continuar la conversación."»

> **HU-E8-01 — Reservar un turno conversando por WhatsApp** — Precondición: «La empresa tiene el
> agente de WhatsApp activo y dentro de su horario de atención.» (Pregunta 1, resuelta: no
> requiere ADR).

> **Precedente de las fechas sin atención — HU-E7-05** (`inputs/historias-de-usuario.md:1585`):
> «registrar excepciones de disponibilidad sobre un recurso, para reflejar **feriados, vacaciones
> o aperturas especiales** fuera del horario habitual». Es **por recurso**; las fechas sin
> atención de esta unidad son su análogo a nivel del negocio (sólo cierres, sin aperturas
> especiales).

**HS-T2 RN-04** dice «horario de atención configurado» sin fijar su forma: que admita varias
franjas por día y fechas cerradas no la contradice ni la enmienda (no hace falta ADR).

**Prototipo PAN-WA-02** (`inputs/prototipos/agente-whatsapp.html:272-287`): tarjeta «Horarios de
atención — Cuándo el agente responde automáticamente», un renglón por día con interruptor y
«09:00 a 19:00» (sábado 09:00–14:00, domingo apagado), y «Zona horaria: ART (GMT-3)». La
anotación oficial de PAN-WA-02 (`anotaciones-comportamiento-oficial.html:196-210`): «Activar
agente / horarios — Enciende o pausa el agente y define la franja de atención automática». Solo
Admin. **Ningún prototipo muestra el selector de política, la segunda franja ni las fechas sin
atención**: se agrega el mínimo, con los patrones de la pantalla de Recursos (ver Frontend).

## Hallazgos (relevados sobre `develop` `24ab1e6`, 2026-10-05)

| Dónde | Qué |
|---|---|
| `docs/aidlc/inputs/der.md:136-147, 578` | El DER no tiene horario de atención en ninguna tabla. Lo único parametrizable por empresa es `regla_de_negocio` (`tipo` E, `configuracion jsonb`, `prioridad`, `activa`); `tipo_regla` = `ESCALAMIENTO_DE_COBRO · POLITICA_DE_TURNO · AGENDA_DE_NOTIFICACION` |
| `business_config/domain/regla.py:38-49` | `TipoRegla` con esos tres valores. **Ninguno es un horario**: `AGENDA_DE_NOTIFICACION` es «cuándo recordar un turno» (pendiente #7 del épico 8, lo toma U8) |
| `business_config/domain/regla.py:164-210, 213, 228` | `ReglaDeNegocio` (JSONB validado por una clase por tipo, D24), `resolver` (RN-05: prioridad y, a igualdad, la más reciente) y `ReglasVigentes` (sólo escalamiento) |
| `business_config/application/reglas.py:53-119, 166-190` | `ConfigurarEscalamiento` (sólo Admin, reemplaza, reactiva al guardar, audita) y `ConsultarReglasVigentes`, el Open Host Service que `payments` consume por `payments/infrastructure/cadena.py` — **el precedente exacto** de cómo otro contexto lee una regla |
| `migrations/versions/0019_regla_y_cobro.py:137` | `regla_de_negocio.tipo` es `String(40)` **sin CHECK**: un tipo nuevo no necesita migración |
| `business_config/infrastructure/repositories.py:39` | `TipoRegla(fila.tipo)`: código viejo leyendo un tipo nuevo levanta `ValueError` (riesgo de rollback, ver Riesgos) |
| `scheduling/domain/recurso.py:104, 196, 305` | `PatronDeDisponibilidad` / `RecursoReservable.horarios_del_dia`: disponibilidad **por recurso** para reservar turnos. No es el horario del negocio (ver T1) |
| `scheduling/application/errors.py:37` | `FueraDeHorario` = «el recurso no atiende en esa franja» (HU-E7-04). Mismo nombre, otro concepto |
| `identity/domain/empresa.py:30` · `identity/domain/usuario.py:49` | `Empresa` no tiene horario ni zona; `usuario.pref_zona_horaria` es preferencia de visualización (D-épico 7, `07-agenda-y-recursos/decisiones.md:140-145`) |
| `shared/zona_horaria.py:13` | `ZONA_ARGENTINA` (U10). Se reutiliza; `shared/` no es un contexto (R4) |
| `docs/architecture.md` §4 | Fila `business_config → payments, scheduling, conversational` (C/S, «`ReglaDeNegocio`, `PlantillaDeNotificacion`»): **el edge ya está permitido**. Hoy `conversational` ya lo usa para plantillas (`api/conversacional.py:215-237`) |
| `conversational/application/agente.py:163-167` | Con escalamiento abierto el agente calla (HU-E9-01 RN-02) |
| `agente.py:169-174, 203, 297` | Los cuatro caminos que escalan (transcripción pobre, pedido de persona, baja confianza, desenlace de turnos —p. ej. seña—) pasan **todos** por `_escalar` (`:317-335`), que dice `MENSAJE_DERIVACION` (`:333`). Un solo punto para el aviso de derivación |
| `agente.py:176-182` | La respuesta a un diálogo vigente (U10) se lee sin el modelo, **antes** de interpretar |
| `agente.py` | **370 líneas** (límite 400): lo nuevo va en módulos propios; `agente.py` gana sólo dos llamadas |
| `agente.py:336-343` · `salida.py:68` · `api/routers/whatsapp.py:156` | Todo saliente del agente se guarda con `momento = contexto.ahora`, el mismo `ahora` (reloj al empezar a procesar) con el que se decide si está abierto. Una respuesta a un mensaje procesado a las 18:59:59 queda con `momento` 18:59:59 aunque el envío termine después de las 19:00 (ver T9) |
| `turnos_por_whatsapp.py:48-60, 65-77` | `TurnosPorWhatsApp(conversaciones, salida, agenda, publicador)` arma la reserva y la cancelación sobre **una** `SalidaAlCliente`; `continuar` devuelve `None` si el texto no es una respuesta |
| `reserva_por_whatsapp.py:213-221, 348` · `cancelacion_por_whatsapp.py:198` | Cada continuación manda **un** saliente por su `_decir`. `PEDIR_CUANDO` es texto libre y devuelve `None` (lo lee el intérprete). `reserva_por_whatsapp.py` tiene **394 líneas**: no puede crecer |
| `reserva_por_whatsapp.py:277-285` · `cancelacion_por_whatsapp.py:146-148` | Dos continuaciones escalan: la tercera respuesta ambigua seguida (`escalar_por`, sin texto) y la cancelación de un turno con seña (manda `MENSAJE_TURNO_CON_SENA` **y** escala) |
| `conversational/domain/conversacion.py:106-117, 138` | `Mensaje.origen` (`AGENTE` · `OPERADOR` · `SISTEMA`): se puede saber si el agente ya habló en un período sin releer textos |
| `conversational/application/ports.py` | 345 líneas; `PortRepositorioMensaje.del_hilo` (`:153`) ya existe |
| `api/routers/whatsapp.py:128-158` | `_procesar` arma `ProcesarMensajeEntrante` por mensaje, una transacción por mensaje |
| `frontend/src/app/(panel)/conversaciones/page.tsx:25` · `features/conversational/components/BandejaDeConversaciones.tsx:79, 132` | La bandeja PAN-WA-01 arranca con `solo_escaladas=true`; el botón «Todas» quita el filtro |
| `frontend/src/app/(panel)/configuracion/respuestas/page.tsx` | Es PAN-WA-02 (FAQ). Ahí va la tarjeta del horario |
| `frontend/src/features/scheduling/components/RecursosReservables.tsx:470-501, 569-631` | El patrón a copiar: «Agregar franja» / «Quitar» por renglón con el error de horario invertido antes de guardar, y la tarjeta «Excepciones» (tabla de fechas + `Campo type="date"` «Día sin atención» + botón). Ese archivo tiene 643 líneas: se copia el patrón, no se importa nada (R5) |
| `frontend/src/features/payments/api/regla.ts:9, 38-42` | La pantalla PAN-CFG-RN vive en `features/payments` (épico 6) con `TipoRegla` y `ETIQUETAS_DE_TIPO` cerrados a tres: una regla nueva se vería **sin rótulo** |
| `frontend/src/features/business_config/index.ts` | Vacío (`export {}`). U8 planea poner ahí su editor de agenda; esta unidad sigue el mismo patrón |

## Diseño

### Decisiones técnicas (resueltas con evidencia, no son preguntas)

**T1 · El horario de atención no es la disponibilidad de los recursos.** La disponibilidad
(`PatronDeDisponibilidad`) dice cuándo se puede **reservar** un turno con un recurso; el horario
de atención dice cuándo **una persona atiende el canal**. Pueden diferir en los dos sentidos
(una sala reservable de 8 a 22 con asesores de 9 a 18; un consultorio que atiende consultas por
WhatsApp aunque ese día no haya agenda). El prototipo los muestra en pantallas distintas
(PAN-AGE-03 vs. PAN-WA-02) y el agente ya consulta la disponibilidad por `PortAgenda`. Por lo
mismo, una **fecha sin atención** del negocio no bloquea la agenda, ni una excepción de un recurso
cierra el canal (Pregunta 2, resuelta: se configuran aparte).

**T2 · Vive en `business_config` como un cuarto `TipoRegla`: `HORARIO_DE_ATENCION`.** Es
comportamiento del sistema parametrizado por empresa, que es la definición de HU-E11-01, y
`regla_de_negocio` es el único lugar del DER para eso. Una regla = horario, fechas sin atención
**y** política (una fila, una tarjeta, un interruptor en PAN-CFG-RN).
- Descartado *una tabla nueva en conversational* (ni para las fechas): sería un agregado que el
  DER y `docs/architecture.md` §3 no tienen (27 agregados) → ADR, para algo que la tabla de
  reglas ya resuelve con su prioridad, su estado y su RLS.
- Descartado *reutilizar `AGENDA_DE_NOTIFICACION`*: significa otra cosa y U8 la toma.
- **Se aparta del DER** en un valor del enum `tipo_regla`. La columna es `varchar(40)` sin CHECK,
  así que no hay migración. Se anota como decisión **D100** (o el siguiente número libre) en
  `08-agente-de-whatsapp/decisiones.md`, como D99 hizo con `conversacion.dialogo`.

**T3 · No hace falta ADR** (Pregunta 1, resuelta). (1) El edge `business_config → conversational`
ya está en el Context Map y ya se usa (plantillas). (2) Ninguna historia se modifica: HS-T2 RN-04
delega en «la política definida», y la opción (c) es esa política; «horario de atención
configurado» no fija su forma, así que el horario cortado y las fechas sin atención no la
enmiendan. (3) Un valor más de un enum ya decidido por D24 («una tabla, un JSONB validado por
tipo») es una decisión de épico, no de arquitectura. La precondición de HU-E8-01 describe el
escenario, no impone una regla.

**T4 · `business_config` contesta la pregunta, no entrega las filas.** Igual que
`ConsultarReglasVigentes` con `payments`: el servicio publicado `ConsultarAtencion` recibe
`ahora` y devuelve `EstadoDeAtencion(configurado, abierto, politica, proxima_apertura,
cerrado_desde)`. El cálculo («¿está abierto a esta hora argentina?», «¿cuándo abre?», «¿desde
cuándo está cerrado?») es una función pura del dominio de business_config, escrita una vez.
conversational no reimplementa el horario: lo traduce a su vocabulario en un ACL
(`HorarioViaConfiguracion`, en `conversational/infrastructure/`), con su propio enum de política
(R3: no importa el dominio de business_config).

**T5 · Semántica del horario.**
- Hora local de Argentina (`ZONA_ARGENTINA`), nunca UTC: entre las 21:00 y las 24:00 locales UTC
  ya es el día siguiente y **también otro día de la semana**, y **otra fecha** (una fecha sin
  atención se compara con la fecha local, nunca con la de UTC).
- **Franjas por día.** Cada día de la semana tiene **una o más** franjas semiabiertas
  `[desde, hasta)`: a las 13:00 en punto de 09:00–13:00 ya está cerrado. `hasta` admite `24:00`
  (fin del día); `desde < hasta`; no cruza la medianoche (un horario hasta las 2 se carga como dos
  días: `20:00–24:00` y `00:00–02:00`, y son contiguos). Las franjas de un mismo día van
  **ordenadas** por `desde` y **no se superponen ni se tocan** (`09:00–13:00` y `13:00–16:00` es
  una sola franja `09:00–16:00`: se rechaza para que haya una única forma de escribir cada
  horario). El **hueco** entre dos franjas del mismo día es «cerrado» a todos los efectos.
- **Fechas sin atención** (`fechas_cerradas`): fechas locales `AAAA-MM-DD`, sin repetir, a lo
  sumo **200** (tope de cordura: un año de feriados nacionales son unos 19). En una fecha sin
  atención el negocio está cerrado **las 24 horas**, sea el día de la semana que sea: sus franjas
  no cuentan, tampoco para la contigüidad de medianoche (lunes `20:00–24:00` + martes
  `00:00–02:00` con el martes sin atención → el lunes cierra a las 24:00).
- Al menos un día de la semana con franja: «ningún día» no es un horario (sería el agente
  apagado, Pregunta 6). Que las fechas sin atención tapen todos los días abiertos sí es posible
  (ver `proxima_apertura`).
- **JSON** `{"version": 1, "politica": "AGENTE_RESPONDE" | "MENSAJE_FIJO", "dias": [{"dia":
  0..6, "franjas": [{"desde": "HH:MM", "hasta": "HH:MM"}, …]}], "fechas_cerradas":
  ["AAAA-MM-DD", …]}`, lunes 0 como en `recurso.py`. Se escribe sólo los días con franjas, y
  `fechas_cerradas` siempre (ordenada, `[]` si no hay). Leer una fila mal formada **falla al
  construir** (D24).
- **Versión: se queda en `1`, y la lectura acepta que falte `fechas_cerradas` (= `[]`).** Ninguna
  fila `HORARIO_DE_ATENCION` existe en ningún ambiente: el tipo nace en esta unidad, así que la
  versión 1 se define acá, ya con la lista de franjas por día y con las fechas. Subir a `2` sería
  versionar contra datos que nunca existieron y obligaría a mantener un lector de `1` sin uso.
  Tolerar la ausencia cuesta una línea y cubre el JSON escrito a mano (T11). Cualquier otra
  `version` se rechaza.
- **Fechas pasadas:** el dominio las conserva y el cálculo las usa sólo si caen en su ventana
  (una fecha de ayer sí importa para `cerrado_desde`). `ConfigurarHorarioDeAtencion` descarta al
  guardar las anteriores a `hoy − 366 días` (ninguna cuenta puede alcanzarlas), así la lista no
  crece sin fin. La pantalla muestra sólo las de hoy en adelante y **reenvía sin cambios** las
  pasadas que oculta, para que guardar no altere el cálculo de la noche en curso.
- **`proxima_apertura(ahora)`**: si está abierto, `ahora`; si no, el `desde` de la primera franja
  que empieza después de `ahora`, recorriendo fecha por fecha desde la fecha local de `ahora`
  **hasta 366 días después** (de ahí el horizonte: con fechas sin atención, 7 días ya no
  alcanzan; 366 cubre un año entero, bisiesto incluido, y son a lo sumo 367 fechas × pocas
  franjas: cálculo trivial). Se salta las fechas sin atención y encuentra la apertura dentro del
  mismo día (13:30 con 09–13 y 16–20 → hoy 16:00). Si no hay ninguna en el horizonte devuelve
  **`None`** («sin próxima apertura»; los textos tienen su variante sin fecha, Pregunta 5).
- **`cerrado_desde(ahora)`** (sólo con el negocio cerrado): el `hasta` de la última franja de una
  fecha con atención que terminó a más tardar en `ahora`, recorriendo **hasta 366 días atrás**.
  En el hueco de un horario cortado es el cierre de la mañana (13:30 → hoy 13:00); en una fecha
  sin atención, el último cierre de una fecha anterior con atención (lunes 12/10 sin atención,
  10:00 → sábado 10/10 14:00). Si no hay ninguna en la ventana devuelve el borde de la ventana,
  `ahora − 366 días` («cerrado al menos desde»): siempre es un instante, y T9 sigue funcionando.

**T6 · Sin regla configurada, o con la regla desactivada, la empresa está «siempre abierta».**
`ConsultarAtencion` devuelve `configurado=False, abierto=True`. Es lo que pasa hoy, y RN-04 de
HU-E11-01 («deja de aplicarse de inmediato») se cumple sin un caso especial. A diferencia del
escalamiento de cobros, **no hay horario por defecto**: inventarle un horario a una empresa haría
que su agente cambie de comportamiento sin que nadie lo haya pedido.

**T7 · El aviso de derivación — un solo punto: `_escalar`.** Si al escalar el negocio está
cerrado, el aviso es `MENSAJE_DERIVACION` + «Ahora estamos fuera del horario de atención: un
asesor te va a responder a partir de {cuando}.» Vale para los cuatro motivos (pedido de persona,
baja confianza, transcripción pobre, desenlace de turnos) y **para las dos políticas**: en (a) es
el único cambio; en (b), con el negocio cerrado, sólo se llega a `_escalar` por el desenlace de un
diálogo que se siguió (T8: tercera respuesta ambigua o cancelación de un turno con seña). El
escalamiento se crea igual: el operador lo encuentra en su bandeja (vista inicial, porque está
escalado) al abrir. `MENSAJE_OFRECER_ASESOR` («¿Querés que te derive…?») no cambia: la hora se
dice cuando la derivación ocurre. Dentro de horario, el texto es exactamente el de hoy.

**T8 · Política (b) — dónde corta.** El orden de `ejecutar` pasa a ser:
1. idempotencia → cliente → hilo → transcribir → **registrar** (RN-01: el mensaje queda siempre
   en la conversación; el audio se transcribe igual porque HS-T7 RN-03 no guarda el audio, y sin
   texto el mensaje se perdería);
2. escalamiento abierto → el agente calla (sin cambios: con un operador en el hilo no sale ni el
   mensaje fijo);
3. **cerrado y política (b)** (`atender_cerrado`):
   - si el mensaje es la respuesta a un diálogo (`TurnosPorWhatsApp.continuar` devuelve algo), se
     atiende **sin el modelo** y el saliente **termina con la oración de fuera de horario** (T9);
     si ese desenlace escala, sigue T7. Sólo los pasos que lee el analizador determinista:
     elegir horario, elegir servicio, elegir el turno a cancelar, confirmar la cancelación.
     `PEDIR_CUANDO` es texto libre que necesita al intérprete: **no se sigue** (recibe el mensaje
     fijo). Un diálogo vencido se re-ofrece como de día (U10 T14), también con la oración;
   - si no, el mensaje fijo si el agente no avisó en este período, o silencio si ya avisó (T9),
     y **termina**: sin transcripción-pobre-escala, sin pedido de persona, **sin intérprete, sin
     embeddings, sin FAQ**; la intención del entrante queda `None` («no se clasificó», como
     define U3). El diálogo vigente no se cierra: si después llega la respuesta, se atiende;
4. el resto, igual que hoy.

**Cómo se agrega la oración sin tocar los pasos de turnos.** `atender_cerrado` continúa el diálogo
con un `TurnosPorWhatsApp` armado para ese mensaje sobre `SalidaConPosdata`, una subclase de
`SalidaAlCliente` (en `application/fuera_de_horario.py`) que agrega la oración al **primer**
saliente que manda y lo guarda así. Como cada continuación manda un solo saliente por su `_decir`,
la oración aparece una vez y queda en el hilo como saliente `AGENTE`. `reserva_por_whatsapp.py`
(394 líneas) y `cancelacion_por_whatsapp.py` **no se tocan**.

**T9 · «Una vez por período de cierre» sin columna nueva.** El agente ya avisó si en el hilo hay
un saliente con `origen = AGENTE` y `momento ≥ cerrado_desde(ahora)`. La regla vale porque en (b),
mientras está cerrado, **todo** saliente `AGENTE` lleva la información de fuera de horario: el
mensaje fijo, la respuesta a un diálogo (con la oración agregada, T8 — este es el arreglo del
choque entre las preguntas 3 y 4: sin la oración, una respuesta a un diálogo a las 19:05 haría
callar al agente ante un «¿cuánto sale?» a las 19:10 sin que el cliente supiera que estaba
cerrado) y el aviso de derivación con hora (T7). No se relee ningún texto (lo que T2 de U10
descartó), y los avisos `SISTEMA` (recordatorios de U7/U8) y los del operador no cuentan.
Revisado contra los casos en que podría fallar:
- **Respuesta justo antes del cierre:** su `momento` es el `ahora` con que se decidió «abierto»
  (Hallazgos, `salida.py:68`), así que es `< cerrado_desde` y no cuenta, aunque el envío termine
  pasadas las 19:00. A las 19:10 sale el mensaje fijo (caso 30).
- **Hueco de un horario cortado:** `cerrado_desde` es el cierre de la mañana (13:00); lo que el
  agente contestó a las 12:50 no cuenta → a las 13:30 sale el fijo; a la noche (`cerrado_desde`
  20:00) el de las 13:30 ya no cuenta → sale de nuevo (caso 24).
- **Fecha sin atención:** `cerrado_desde` es el último cierre de una fecha con atención anterior,
  así que el fin de semana largo es **un** período: el fijo del sábado a la noche silencia el
  lunes feriado; una FAQ contestada el martes 18:30 no silencia el miércoles sin atención (caso 30).
- **Sin ningún saliente previo** del agente en el hilo → el primer mensaje recibe el fijo (caso 22).
- **Riesgos aceptados** (no son fallas de la regla, ver Riesgos): cambiar el horario a la noche
  recalcula `cerrado_desde` y puede reenviar el fijo una vez; pasar de (a) a (b) a la noche cuenta
  las respuestas de (a) de esa noche, que no decían que estaba cerrado.

**T10 · Bitácora (HS-T2 CA4 «Bitácora», RN-05).** En (b), el mensaje fijo publica
`responder_fuera_de_horario` con **iniciador IA**, módulo `CONVERSATIONAL`, entidad
`Conversacion:<id>`; un mensaje silenciado por T9 no publica nada (sólo log
`fuera_de_horario_ya_avisado`); la respuesta a un diálogo publica los eventos de U10 de siempre.
En (a), los eventos de siempre (`interpretar_mensaje:*`, `escalar_conversacion`). En
business_config: `alta_regla_de_horario_de_atencion` / `editar_regla_de_horario_de_atencion`
(como el escalamiento) y los `activar_regla` / `desactivar_regla` que ya existen.

**T11 · Una configuración ilegible no voltea el webhook.** Si `ConsultarAtencion` falla al leer la
regla (`EntradaInvalida` por un JSON escrito a mano), el ACL de conversational la trata como «sin
horario» y registra `horario_ilegible`: el mensaje se procesa como hoy. Un 500 haría que Meta
reintente y el cliente no reciba nada. Es el criterio de `dialogo_ilegible` (U10).

**T12 · Tamaños** (≤ 400 líneas por archivo, ≤ 50 por función, complejidad ≤ 10). `regla.py`
(254) gana sólo el valor del enum y `interpretada_como_atencion`. El horario de business_config,
que con franjas múltiples, fechas y horizonte ya no entra cómodo en un archivo, se reparte en tres
módulos puros de `domain/`:
- `horario_de_atencion.py` (~180): `FranjaDeAtencion`, `PoliticaFueraDeHorario`,
  `ConfiguracionDeAtencion` con sus invariantes y mensajes;
- `horario_de_atencion_json.py` (~110): `como_json` / `desde_json`, versión y ausencia de
  `fechas_cerradas`;
- `apertura.py` (~150): `esta_abierto`, `proxima_apertura`, `cerrado_desde`, el horizonte y
  `EstadoDeAtencion` / `SIEMPRE_ABIERTO`; las búsquedas se escriben como un generador de
  «tramos» (franjas de fechas con atención, con la contigüidad de medianoche ya unida) hacia
  adelante y otro hacia atrás, para que cada función quede corta.
Los casos de uso van en `application/atencion.py` (nuevo) y no en `reglas.py`, que U8 también
agranda. En conversational: `domain/fuera_de_horario.py` (~160, textos y `ya_avisado`) y
`application/fuera_de_horario.py` (~170, `AtencionFueraDeHorario` + `SalidaConPosdata`), nuevos;
`agente.py` queda debajo de 400. En el frontend la tarjeta se parte en tres componentes (ver
Frontend).

### Dominio

**business_config** (`domain/horario_de_atencion.py`, `horario_de_atencion_json.py` y
`apertura.py`, nuevos, puros):
- `FranjaDeAtencion(desde, hasta)` en minutos desde la medianoche (0 ≤ desde < hasta ≤ 1440),
  con `desde_texto("HH:MM")` y `como_texto`.
- `PoliticaFueraDeHorario` (`AGENTE_RESPONDE` = (a), por defecto; `MENSAJE_FIJO` = (b)).
- `ConfiguracionDeAtencion(dias: Mapping[int, tuple[FranjaDeAtencion, ...]], fechas_cerradas:
  frozenset[date], politica)` con invariantes (días 0–6 sin repetir, al menos uno con franja;
  franjas de cada día ordenadas, sin superponerse ni tocarse; fechas sin repetir, a lo sumo 200).
- `como_json` / `desde_json` (T5: `version` 1, `fechas_cerradas` opcional al leer), que fallan al
  leer algo mal formado.
- `esta_abierto(config, instante)`, `proxima_apertura(config, instante) -> datetime | None`,
  `cerrado_desde(config, instante) -> datetime` sobre `instante.astimezone(ZONA_ARGENTINA)`, con
  el horizonte `HORIZONTE_DIAS = 366` (T5).
- `EstadoDeAtencion(configurado, abierto, politica, proxima_apertura: datetime | None,
  cerrado_desde)` y `SIEMPRE_ABIERTO` (T6).
- Mensajes de validación: «La hora de cierre debe ser posterior a la de apertura.», «Indicá al
  menos un día con horario de atención.», «El horario debe tener el formato HH:MM.», «Las franjas
  de un mismo día no pueden superponerse ni tocarse.», «Las franjas de un día deben ir de la más
  temprana a la más tarde.», «La fecha debe tener el formato AAAA-MM-DD.», «La fecha {fecha} está
  repetida.», «Podés cargar hasta 200 fechas sin atención.».

**business_config** (`domain/regla.py`): `TipoRegla.HORARIO_DE_ATENCION` y
`ReglaDeNegocio.interpretada_como_atencion()` (falla si el tipo no es ése, como la de
escalamiento).

**conversational** (`domain/fuera_de_horario.py`, nuevo, puro):
- `PoliticaFueraDeHorario` propia (`AGENTE_RESPONDE`, `MENSAJE_FIJO`) y
  `AtencionDelNegocio(abierto, politica, proxima_apertura: datetime | None, cerrado_desde)`.
- `cuando_se_atiende(proxima_apertura, ahora) -> str` en hora argentina, sin depender del locale:
  «hoy a las 16:00» (misma fecha local, también en el hueco de un horario cortado), «mañana a las
  09:00» (fecha local siguiente), «el martes 13/10 a las 09:00» (cualquier otra; la fecha
  desambigua aunque falte más de una semana). Reutiliza los nombres de día de
  `textos_de_turnos.py`. Sólo se llama con una apertura; sin apertura, cada texto usa su variante.
- `aviso_de_derivacion(atencion, ahora) -> str` (T7), `mensaje_fuera_de_horario(atencion, ahora)`
  (b) y `posdata_fuera_de_horario(atencion, ahora)` (la oración de T8) — textos en la Pregunta 5,
  cada uno con su variante para `proxima_apertura = None`.
- `ya_avisado(mensajes, desde) -> bool` (T9).

### Aplicación

**business_config** (`application/atencion.py`, nuevo):
- `ConfigurarHorarioDeAtencion` — sólo Administrador (`MOTIVO_SOLO_ADMIN`), reemplaza en vez de
  acumular, reactiva al guardar, descarta las fechas anteriores a `hoy − 366 días` (T5), audita
  (T10). Copia de la forma de `ConfigurarEscalamiento`.
- `ConsultarAtencion` — **el Open Host Service** (sin chequeo de rol, como
  `ConsultarReglasVigentes`): lista las `HORARIO_DE_ATENCION`, `resolver` por prioridad (RN-05),
  sin regla → `SIEMPRE_ABIERTO` (T6); con regla → `EstadoDeAtencion` calculado para `ahora`.
- `configuracion_de_atencion_desde(crudo)` — traduce el formulario; la validación es del dominio.

**conversational**:
- `ports.py`: `PortHorarioDeAtencion.consultar(ahora) -> AtencionDelNegocio` (lo único que
  conversational sabe del horario).
- `application/fuera_de_horario.py` (nuevo):
  - `AtencionFueraDeHorario`: `consultar(contexto)` (una consulta por mensaje, sólo si hace
    falta); `atender_cerrado(contexto, texto) -> Desenlace | None` para (b) (T8, T9, T10:
    continuación del diálogo sobre `SalidaConPosdata`, mensaje fijo o silencio);
    `aviso_de_derivacion(contexto)` (T7). Recibe las dependencias de `TurnosPorWhatsApp`
    (`conversaciones`, `agenda`, `publicador`, `mensajes`, `mensajeria`) para armar el de la
    noche.
  - `SalidaConPosdata(SalidaAlCliente)`: agrega la oración al primer saliente (T8).
- `agente.py`: recibe `horario: PortHorarioDeAtencion`; después del chequeo de escalamiento
  abierto llama a `atender_cerrado` y, si devuelve algo, termina por `_terminar` (que escala si el
  desenlace lo pide); `_escalar` usa `aviso_de_derivacion` en lugar de `MENSAJE_DERIVACION` fijo.
  Nada más.

### Puertos y adaptadores

- `conversational/infrastructure/horario.py` (nuevo, `HorarioViaConfiguracion`): implementa
  `PortHorarioDeAtencion` sobre `ConsultarAtencion` (R3: importa sólo `application/` de
  business_config, como `payments/infrastructure/cadena.py`); traduce la política al enum propio
  y pasa `proxima_apertura = None` tal cual; T11.
- `api/conversacional.py`: `armar_horario_de_atencion(unidad, empresa_id)` con
  `ConfiguracionDeNegocio.armar(unidad).reglas`.
- `api/routers/whatsapp.py` (`_procesar`): pasa `horario=armar_horario_de_atencion(…)`.
- `api/routers/reglas.py`: `PUT /reglas/horario-de-atencion` (entrada `{dias: [{dia, franjas:
  [{desde, hasta}]}], fechas_cerradas: ["AAAA-MM-DD"], politica, prioridad}`; sólo Admin; 422 con
  el mensaje del dominio). La lectura es el `GET /reglas` de siempre (devuelve el JSONB tal cual,
  `:49-51`), como hace U8 con la agenda.

### Otros contextos

- `conversational → business_config` por servicio de aplicación (`ConsultarAtencion`) detrás de un
  ACL: **la fila `business_config → payments, scheduling, conversational` del Context Map ya lo
  permite. No hace falta ADR** (T3).
- `scheduling`, `identity`, `master_data`: no se tocan. Las excepciones por recurso (HU-E7-05)
  siguen siendo lo que bloquea la agenda (T1).
- `shared/zona_horaria.py`: se reutiliza sin cambios.

### Frontend

- `features/business_config/api/atencion.ts` (nuevo): `TipoRegla` no se toca acá; lee la regla
  `HORARIO_DE_ATENCION` de `/api/reglas` de forma defensiva (una configuración mal formada se
  muestra vacía, como `pasosDe`; sin `fechas_cerradas` → `[]`) y
  `configurarHorarioDeAtencion(...)` hace `PUT`.
- `features/business_config/components/HorarioDeAtencion.tsx` (nuevo, ~200): la tarjeta del
  prototipo —un renglón por día, «Zona horaria: ART (GMT-3)»— más **lo mínimo que el prototipo no
  tiene**: un grupo de dos radios «Fuera de horario: ● El agente responde igual (avisa desde
  cuándo atiende un asesor) ○ El agente no responde y envía un mensaje fijo», la tarjeta de fechas
  y el botón «Guardar». Antes de mandar ordena las franjas de cada día por «desde»; si dos se
  superponen o se tocan, o una tiene el cierre antes de la apertura, muestra el error y deshabilita
  «Guardar» (como `horarioInvertido` en Recursos); el mensaje del backend se muestra igual. Sin
  regla, la tarjeta dice «Sin horario configurado: el agente atiende y deriva a cualquier hora.» y
  precarga los valores del prototipo sin guardarlos. Sólo el Administrador edita (PAN-WA-02 es
  «Solo Admin»); el resto la ve en modo lectura. El subtítulo del prototipo («Cuándo el agente
  responde automáticamente») pasa a «Cuándo atiende el negocio», porque con la política por
  defecto el agente responde a toda hora.
- `features/business_config/components/FranjasDelDia.tsx` (nuevo, ~120): el renglón de un día con
  su interruptor y sus franjas, cada una con dos `input type="time"` (con `24:00` permitido como
  «hasta») y «Quitar», y **«Agregar franja»** (el patrón de `RecursosReservables.tsx:470-501`).
  Quitar la última franja apaga el día.
- `features/business_config/components/FechasSinAtencion.tsx` (nuevo, ~110): tarjeta «Fechas sin
  atención», réplica de la tarjeta «Excepciones» de Recursos (`RecursosReservables.tsx:569-631`):
  tabla de fechas (de hoy en adelante, monoespaciadas) con «Quitar», un `Campo type="date"` y
  «Agregar fecha»; una fecha repetida no se agrega. A diferencia de Recursos, **no guarda al
  instante**: edita el estado de la tarjeta y se guarda con «Guardar» (un `PUT` reemplaza la
  regla entera). Las fechas pasadas no se muestran y se reenvían sin cambios (T5). Texto de ayuda:
  «Un feriado o unas vacaciones: ese día se atiende como fuera de horario. No bloquea los turnos:
  para eso, cargá la excepción en cada recurso.»
- `features/business_config/index.ts`: exporta `HorarioDeAtencion` y sus tipos.
- `app/(panel)/configuracion/respuestas/page.tsx` (PAN-WA-02): compone la tarjeta arriba de
  `RespuestasFrecuentes` (la ruta compone dos features, R5).
- `app/api/reglas/horario-de-atencion/route.ts` (nuevo, BFF `PUT`).
- `features/payments/api/regla.ts`: `TipoRegla` y `ETIQUETAS_DE_TIPO` suman
  `HORARIO_DE_ATENCION: "Horario de atención"`, para que PAN-CFG-RN la liste con rótulo y su
  interruptor de activa/inactiva funcione (RN-01, RN-04).
- **La bandeja PAN-WA-01 no se toca** (ver «Qué hace», visibilidad).

## Infraestructura

- **Migraciones**: **ninguna.** `regla_de_negocio.tipo` es `varchar(40)` sin CHECK
  (`0019_regla_y_cobro.py:137`) y la configuración es `jsonb` (las franjas múltiples y las fechas
  son parte del mismo JSON); la RLS de `regla_de_negocio` ya aísla por empresa. La cabeza de
  `develop` sigue en `0032` y la `0031` sigue reservada.
- **Trabajo asíncrono**: no aplica. La política se evalúa al llegar cada mensaje; no hay barrido
  ni nada que «despierte» al abrir.
- **Configuración**: no aplica (sin variables nuevas).
- **Integraciones externas**: ninguna nueva (el calendario automático de feriados queda afuera).
  En (b) fuera de horario **se ahorra** la llamada al LLM y a los embeddings; WhatsApp: un
  saliente por período de cierre, más la respuesta a un diálogo si la hay.

## Riesgos que obligan a tests

- [ ] Toca dinero: no aplica.
- [ ] Comprobantes fiscales / CAE: no aplica.
- [x] Consume un webhook → el mismo `externo_id` fuera de horario en (b) produce **un solo**
      mensaje fijo (caso 35).
- [x] Datos con `empresa_id` → el horario de la empresa A nunca rige para la B (casos 16, 37).
- [x] Usa salida de un LLM → **al revés**: se prueba que en (b) fuera de horario el modelo **no se
      llama**, tampoco al seguir un diálogo (casos 22, 23, 25, 27, 28, 31) y que ninguna decisión
      de horario depende de él.
- [ ] Datos personales al LLM: no cambia (en (b) llega menos, no más).
- [x] **Zona horaria** → un `datetime` UTC comparado contra un horario local es el bug clásico
      del borde de la medianoche, y una fecha sin atención comparada con la fecha UTC cierra el
      día equivocado (casos 4, 5, 9, 34).
- [x] **«Una vez por período» (T9)** → callar a un cliente que nunca supo que estaba cerrado es
      el error que más se nota; cada borde tiene su caso (casos 22, 23, 24, 27, 30).
- [x] **Horizonte** → con fechas sin atención la búsqueda puede no encontrar apertura; un bucle
      sin tope o un `None` sin texto rompería el webhook (casos 10, 34).
- [x] **Rollback**: `repositories.py:39` hace `TipoRegla(fila.tipo)`; si esta unidad se revierte
      con reglas `HORARIO_DE_ATENCION` cargadas, `GET /reglas` del código viejo falla. Se anota
      en el PR: revertir exige desactivar y borrar esas filas a mano antes.
- [ ] **Aceptados, sin test propio** (se anotan en D100): (1) editar el horario de noche
      recalcula `cerrado_desde` y puede reenviar el mensaje fijo una vez; (2) pasar de (a) a (b)
      de noche cuenta como «ya avisado» las respuestas de (a) de esa noche; (3) cancelar en (b) de
      noche un turno con seña manda dos salientes con la misma hora (el de la seña con la
      oración y el aviso de derivación), porque esa continuación manda texto **y** escala
      (`cancelacion_por_whatsapp.py:146-148`); (4) una fecha sin atención no bloquea la agenda
      (T1): la pantalla lo dice.

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/business_config/domain/horario_de_atencion.py` (nuevo: franjas, política, configuración e invariantes)
- [x] `backend/src/cheatsheet/contexts/business_config/domain/horario_de_atencion_json.py` (nuevo: JSON v1, `fechas_cerradas` opcional al leer)
- [x] `backend/src/cheatsheet/contexts/business_config/domain/apertura.py` (nuevo: `esta_abierto`, `proxima_apertura`, `cerrado_desde`, horizonte de 366 días, `EstadoDeAtencion`)
- [x] `backend/src/cheatsheet/contexts/business_config/domain/regla.py` (`HORARIO_DE_ATENCION`, `interpretada_como_atencion`)
- [x] `backend/src/cheatsheet/contexts/business_config/application/atencion.py` (nuevo: `ConfigurarHorarioDeAtencion` con la poda de fechas viejas, `ConsultarAtencion`)
- [x] `backend/src/cheatsheet/api/routers/reglas.py` (`PUT /reglas/horario-de-atencion`)
- [x] `backend/src/cheatsheet/contexts/conversational/domain/fuera_de_horario.py` (nuevo: `cuando_se_atiende`, los tres textos con su variante sin fecha, `ya_avisado`)
- [x] `backend/src/cheatsheet/contexts/conversational/application/fuera_de_horario.py` (nuevo: `AtencionFueraDeHorario`, `SalidaConPosdata`)
- [x] `backend/src/cheatsheet/contexts/conversational/application/ports.py` (`PortHorarioDeAtencion`)
- [x] `backend/src/cheatsheet/contexts/conversational/application/agente.py` (dos llamadas; < 400 líneas)
- [x] `backend/src/cheatsheet/contexts/conversational/infrastructure/horario.py` (nuevo, ACL)
- [x] `backend/src/cheatsheet/api/conversacional.py` (`armar_horario_de_atencion`)
- [x] `backend/src/cheatsheet/api/routers/whatsapp.py` (`_procesar` pasa el horario)
- [x] `backend/tests/contexts/business_config/domain/test_horario_de_atencion.py` (nuevo: invariantes y JSON)
- [x] `backend/tests/contexts/business_config/domain/test_apertura.py` (nuevo: cálculo, horario cortado, fechas, horizonte)
- [x] `backend/tests/contexts/business_config/application/test_atencion.py` (nuevo)
- [x] `backend/tests/contexts/conversational/domain/test_fuera_de_horario.py` (nuevo)
- [x] `backend/tests/contexts/conversational/application/horario_fijo.py` (nuevo: doble `HorarioFijo`; `dobles.py` ya pasa de 400)
- [x] `backend/tests/contexts/conversational/application/escena.py` (el horario en la escena, «siempre abierto» por defecto)
- [x] `backend/tests/contexts/conversational/application/test_fuera_de_horario.py` (nuevo: (a) y (b) sin diálogo)
- [x] `backend/tests/contexts/conversational/application/test_fuera_de_horario_dialogos.py` (nuevo: (b) con diálogo y los bordes de T9; aparte para que ningún archivo de tests pase de 400)
- [x] `backend/tests/contexts/conversational/infrastructure/test_horario.py` (nuevo, ACL)
- [x] `backend/tests/integracion/test_horario_de_atencion_postgres.py` (nuevo: RLS y API de punta a punta)

### Frontend
- [x] `frontend/src/features/business_config/api/atencion.ts` (nuevo) y `api/__tests__/atencion.test.ts`
- [x] `frontend/src/features/business_config/components/HorarioDeAtencion.tsx` (nuevo) y `components/__tests__/HorarioDeAtencion.test.tsx`
- [x] `frontend/src/features/business_config/components/FranjasDelDia.tsx` (nuevo; lo cubre el test de `HorarioDeAtencion`)
- [x] `frontend/src/features/business_config/components/FechasSinAtencion.tsx` (nuevo) y `components/__tests__/FechasSinAtencion.test.tsx`
- [x] `frontend/src/features/business_config/index.ts`
- [x] `frontend/src/app/(panel)/configuracion/respuestas/page.tsx`
- [x] `frontend/src/app/api/reglas/horario-de-atencion/route.ts` (nuevo)
- [x] `frontend/src/features/payments/api/regla.ts` y `api/__tests__/regla.test.ts` (rótulo del tipo nuevo)

### Documentación
- [x] `docs/aidlc/units/politica-fuera-de-horario.md` (este plan, con el Gate 1 registrado)
- [x] `docs/aidlc/units.md` (fila nueva; estado `en curso` desde el Gate 1)
- [x] `docs/aidlc/epicas/08-agente-de-whatsapp/decisiones.md` (D100: cuarto `TipoRegla`; política (c); «siempre abierto» sin regla; franjas múltiples y fechas sin atención por decisión de Gate 1; versión 1 con `fechas_cerradas` opcional; horizonte de 366 días; la oración en las respuestas a diálogos; los riesgos aceptados)
- [x] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (nuevos: **calendario automático de feriados nacionales** —depende de un tercero— e **interruptor «Agente activo»** —Pregunta 6—. El horario cortado y los feriados cargados a mano **ya no son pendientes**: entran en esta unidad)
- [x] `docs/aidlc/TODO.md` §22 (verificaciones manuales en staging, ver abajo)

## Casos de prueba

Test primero: cada **RED** se escribe y se ve fallar contra el código actual antes de implementar.
Fechas de ejemplo: el lunes 05/10/2026; el 12/10 es lunes, el 13/10 martes, el 14/10 miércoles.
Salvo que se diga otra cosa, horario lunes a viernes 09:00–19:00, sábado 09:00–14:00, domingo
cerrado.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** `ConfiguracionDeAtencion`: ida y vuelta por JSON (con dos franjas en un día y con fechas); rechaza `hasta ≤ desde`, día repetido, día fuera de 0–6, ningún día con franja, «9:00» sin cero, `version` desconocida, política fuera del enum, franjas superpuestas, franjas que se tocan, franjas desordenadas, fecha «12/10/2026» o «2026-13-01», fecha repetida, 201 fechas — cada uno con su mensaje | unit (dominio bc) | RED visto, verde |
| 2 | **RED** Versión: un JSON v1 **sin** `fechas_cerradas` se lee con la lista vacía; la escritura siempre la incluye, ordenada, y sólo los días con franjas | unit (dominio bc) | RED visto, verde |
| 3 | `esta_abierto` con lunes 09:00–19:00: 08:59 cerrado, 09:00 abierto, 18:59 abierto, **19:00 cerrado** | unit (dominio bc) | verde |
| 4 | **RED** Borde de medianoche: lunes `20:00–24:00`, martes cerrado. `2026-10-06T02:59Z` (lunes 23:59 en Argentina, **martes en UTC**) → abierto; `2026-10-06T03:00Z` (martes 00:00) → cerrado | unit (dominio bc) | RED visto, verde |
| 5 | Contigüidad: lunes `20:00–24:00` y martes `00:00–02:00` → abierto a las 23:59 y a las 00:00; `proxima_apertura` y `cerrado_desde` lo tratan como un solo tramo; **con el martes sin atención**, martes 00:30 está cerrado y `cerrado_desde` = martes 00:00 | unit (dominio bc) | verde |
| 6 | **RED** Horario cortado, lunes 09:00–13:00 y 16:00–20:00: 12:59 abierto; 13:00 cerrado; 13:30 cerrado con `proxima_apertura` = lunes 16:00 y `cerrado_desde` = lunes 13:00; 16:00 abierto; 20:00 cerrado con `cerrado_desde` = 20:00 y `proxima_apertura` = martes 09:00 | unit (dominio bc) | RED visto, verde |
| 7 | Día sin horario: domingo cerrado todo el día; `proxima_apertura` desde sábado 14:00 → lunes 09:00; con un solo día abierto a la semana → el mismo día de la semana siguiente | unit (dominio bc) | verde |
| 8 | `cerrado_desde`: lunes 22:00 → lunes 19:00; domingo 10:00 → sábado 14:00; lunes 08:00 → sábado 14:00 | unit (dominio bc) | verde |
| 9 | **RED** Fechas sin atención, con el 12/10 y el 14/10 sin atención: lunes 12/10 10:00 cerrado (es lunes y tiene franja); `proxima_apertura` desde sábado 10/10 20:00 → martes 13/10 09:00; `cerrado_desde` el lunes 12/10 10:00 → sábado 10/10 14:00; miércoles 14/10 10:00 → `cerrado_desde` martes 13/10 19:00 y `proxima_apertura` jueves 15/10 09:00; con el horario del caso 4 (lunes `20:00–24:00`) y el martes 06/10 sin atención, el lunes 05/10 23:30 local (`06/10 02:30Z`, ya martes 06/10 en UTC) sigue **abierto**: la fecha se compara en hora argentina | unit (dominio bc) | RED visto, verde |
| 10 | **RED** Horizonte: único día abierto el lunes y los 53 lunes de los próximos 366 días sin atención → `proxima_apertura` = `None` (sin bucle infinito); sin ninguna franja terminada en los 366 días anteriores → `cerrado_desde` = `ahora − 366 días`; una fecha sin atención de ayer sigue contando para `cerrado_desde`; una fecha a más de 366 días no cambia el cálculo de hoy | unit (dominio bc) | RED visto, verde |
| 11 | `interpretada_como_atencion` sobre una regla de escalamiento → falla; `TipoRegla("HORARIO_DE_ATENCION")` existe | unit (dominio bc) | verde |
| 12 | **RED** `ConfigurarHorarioDeAtencion`: crea la regla; un segundo guardado la reemplaza (una sola fila); guardar una desactivada la reactiva; evento `alta_…`/`editar_regla_de_horario_de_atencion`; al guardar descarta las fechas anteriores a `hoy − 366 días` y conserva las pasadas más recientes y las futuras | unit (aplicación bc) | RED visto, verde |
| 13 | Un Operador no puede configurar el horario (`MOTIVO_SOLO_ADMIN`) | unit (aplicación bc) | verde |
| 14 | **RED** `ConsultarAtencion`: sin regla → `configurado=False, abierto=True`; regla desactivada → igual (HU-E11-01 RN-04); con regla → estado calculado para `ahora`, con `proxima_apertura = None` cuando no hay apertura en el horizonte | unit (aplicación bc) | RED visto, verde |
| 15 | Dos reglas `HORARIO_DE_ATENCION` activas → rige la de mayor prioridad y, a igualdad, la más reciente (RN-05) | unit (aplicación bc) | verde |
| 16 | Multi-tenant: la regla de la empresa A no se lee con la sesión de la empresa B (RLS) | integración (Postgres, CI) | saltea en local (sin Docker), CI pendiente |
| 17 | API: `PUT /reglas/horario-de-atencion` con dos franjas en un día y fechas → 200 para Admin; 422 con «La hora de cierre debe ser posterior a la de apertura.» y con «Las franjas de un mismo día no pueden superponerse ni tocarse.»; rechazo para Operador; `GET /reglas` la lista con su tipo, prioridad, estado y su JSON | integración (API, CI) | saltea en local (sin Docker), CI pendiente |
| 18 | **RED** Política (a) fuera de horario: «quiero hablar con una persona» → escalamiento creado y el cliente recibe `MENSAJE_DERIVACION` + «…un asesor te va a responder a partir del lunes 12/10 a las 09:00.» | unit (aplicación conv) | RED visto, verde |
| 19 | Política (a): baja confianza agotada y turno con seña fuera de horario → el mismo aviso con la hora; **dentro** de horario → exactamente `MENSAJE_DERIVACION` (sin cambios) | unit (aplicación conv) | verde |
| 20 | **RED** Política (a), `{cuando}` en los bordes nuevos: pedido de persona el lunes 12/10 10:00 (sin atención) → «…a partir de mañana a las 09:00.» (y el sábado 10/10 20:00 → «…a partir del martes 13/10 a las 09:00.»); a las 13:30 en el hueco de 09–13 y 16–20 → «…a partir de hoy a las 16:00.»; sin apertura en el horizonte → «…un asesor te va a responder cuando retomemos la atención.» | unit (aplicación conv) | RED visto, verde |
| 21 | Política (a) fuera de horario: «¿cuánto sale?» → el agente interpreta y contesta la FAQ como de día (el intérprete **sí** se llama) | unit (aplicación conv) | verde |
| 22 | **RED** Política (b) fuera de horario, **sin ningún saliente previo del agente** en el hilo: el entrante queda guardado (contenido, `intencion = None`); el cliente recibe **un** mensaje fijo con la próxima apertura; **el intérprete y los embeddings no se llamaron**; no hay escalamiento; evento `responder_fuera_de_horario` con iniciador IA | unit (aplicación conv) | RED visto, verde |
| 23 | **RED** Política (b): segundo y tercer mensaje en el mismo cierre → se guardan, **ningún saliente nuevo**, el intérprete no se llamó, no se publica `responder_fuera_de_horario` (Pregunta 3) | unit (aplicación conv) | RED visto, verde |
| 24 | Política (b), otro período de cierre: un mensaje la noche siguiente → el mensaje fijo sale de nuevo; con horario cortado, fijo a las 13:30 y otro mensaje a las 20:30 → sale de nuevo (el de las 13:30 es anterior a `cerrado_desde` 20:00); un aviso `SISTEMA` o un mensaje del operador en el medio no cuentan como «ya avisado» | unit (aplicación conv) | verde |
| 25 | Política (b) fuera de horario: «quiero hablar con una persona» → mensaje fijo, sin escalamiento (Pregunta 4), sin intérprete | unit (aplicación conv) | verde |
| 26 | Política (b) con escalamiento abierto → silencio (ni mensaje fijo): manda el operador (HU-E9-01 RN-02) | unit (aplicación conv) | verde |
| 27 | **RED** Política (b), arreglo del choque 3/4: oferta de horarios a las 18:55, cierre 19:00. «el primero» a las 19:05 → reserva sin el modelo y **un solo** saliente que termina en «Te recordamos que ahora estamos fuera del horario de atención; atendemos de nuevo mañana a las 09:00.»; «¿cuánto sale?» a las 19:10 → **ningún saliente**, el intérprete no se llamó, no se publica `responder_fuera_de_horario` | unit (aplicación conv) | RED visto, verde |
| 28 | Política (b), diálogo vigente y un mensaje que no es respuesta: oferta 18:55; «hola, ¿cuánto sale?» a las 19:02 → mensaje fijo, sin intérprete, el diálogo sigue abierto; «el primero» a las 19:04 → reserva con la oración; en el paso `PEDIR_CUANDO`, «el jueves» a las 19:02 → mensaje fijo (texto libre, necesita el modelo); confirmar una cancelación con «sí» a las 19:02 → cancela y la confirmación lleva la oración | unit (aplicación conv) | verde |
| 29 | **RED** Política (b), diálogo que termina en escalamiento: tercera elección ambigua seguida a las 19:05 → escala con el aviso de derivación con la hora (T7), sin la oración duplicada; el mensaje siguiente → silencio (escalamiento abierto); cancelar de noche un turno con seña → dos salientes (el de la seña con la oración y el aviso con la hora) y escalamiento | unit (aplicación conv) | RED visto, verde |
| 30 | **RED** Bordes de T9: respuesta a un mensaje procesado con `ahora` 18:59:59 (saliente con `momento` 18:59:59 aunque el envío del doble tarde) → a las 19:10 sale el mensaje fijo; fijo el sábado 10/10 20:00 → el lunes 12/10 (sin atención) 10:00 silencio, un solo período desde el sábado 14:00; FAQ contestada el martes 13/10 18:30 → el miércoles 14/10 (sin atención) 10:00 recibe el fijo | unit (aplicación conv) | RED visto, verde |
| 31 | Política (b) con audio fuera de horario: se transcribe y se guarda el texto, no se interpreta; transcripción pobre → mensaje fijo, **no** escala | unit (aplicación conv) | verde |
| 32 | Política (b) **dentro** de horario → el flujo de hoy, sin cambios (también en la franja de la tarde de un horario cortado) | unit (aplicación conv) | verde |
| 33 | Sin horario configurado → los tests existentes del agente pasan sin tocarlos (la escena usa «siempre abierto») y la derivación dice `MENSAJE_DERIVACION` a cualquier hora | unit (aplicación conv) | verde |
| 34 | **RED** Textos: `cuando_se_atiende` el domingo a las 22:30 de Argentina (`lunes 01:30Z`) con apertura el lunes 09:00 → «mañana a las 09:00», no «hoy»; el lunes 08:00 → «hoy a las 09:00»; el lunes 13:30 en el hueco → «hoy a las 16:00»; el viernes 09/10 20:00 → «el lunes 12/10 a las 09:00»; con el 12/10 sin atención, el sábado 10/10 20:00 → «el martes 13/10 a las 09:00». Sin apertura: el mensaje fijo, el aviso de derivación y la oración usan su variante sin fecha (Pregunta 5) | unit (dominio conv) | RED visto, verde |
| 35 | Mismo `externo_id` entregado dos veces fuera de horario en (b) → un solo mensaje fijo (idempotencia de siempre) | unit (aplicación conv) | verde |
| 36 | ACL: regla con JSON ilegible → «sin horario», log `horario_ilegible`, el mensaje se procesa como hoy (no 500); política de business_config → enum propio de conversational; `proxima_apertura = None` pasa como `None` | unit (infra conv) | verde |
| 37 | De punta a punta por la API con el simulado: empresa A con (b) y cerrada, empresa B sin horario; un mensaje a cada una → A recibe el mensaje fijo y su entrante queda sin intención; B recibe la respuesta normal | integración (API, CI) | saltea en local (sin Docker), CI pendiente |
| 38 | **RED** `HorarioDeAtencion` (frontend): sin regla muestra «Sin horario configurado…» con los valores del prototipo precargados; con regla pinta sus días, sus franjas (dos en un día) y su política; «Agregar franja» suma un renglón y «Quitar» lo saca (quitar la última apaga el día); dos franjas superpuestas muestran el error y deshabilitan «Guardar»; «Guardar» manda el `PUT` con las franjas ordenadas y las fechas; el mensaje de validación del backend se muestra; un Operador la ve sin poder editar | unit (frontend) | RED visto, verde |
| 39 | **RED** `FechasSinAtencion`: agregar una fecha la suma a la tabla; «Quitar» la saca; una repetida no se agrega; las fechas pasadas no se muestran pero viajan sin cambios en el `PUT`; sin fechas muestra el texto vacío y la ayuda que dice que no bloquea los turnos | unit (frontend) | RED visto, verde |
| 40 | `atencion.ts`: lee la configuración de forma defensiva (mal formada → vacía; sin `fechas_cerradas` → `[]`); un error del `PUT` llega como `ErrorDeRegla` | unit (frontend) | verde |
| 41 | **RED** PAN-CFG-RN: una regla `HORARIO_DE_ATENCION` se lista con el rótulo «Horario de atención» (hoy sale vacío) | unit (frontend) | RED visto, verde |
| 42 | `agente.py` < 400 líneas; `reserva_por_whatsapp.py` y `cancelacion_por_whatsapp.py` sin cambios; ningún archivo nuevo > 400; funciones ≤ 50 líneas; `guard_architecture --scan` (R3: conversational sólo importa `application/` de business_config; R5 en la ruta) | revisión + `ruff` (C901) + guard | verde |

## Verificaciones que no se pueden hacer acá

- **PostgreSQL** (casos 16, 17, 37): sin Docker en esta máquina; se saltean en local y se confirman
  en la CI del PR.
- **WhatsApp real**: que el cliente reciba el mensaje fijo una sola vez de noche depende del número
  de prueba y de U5 → `TODO.md` §22 (nueva fila) / §25.
- **En staging** (`TODO.md` §22, nueva fila): con «Estudio Ejemplo SRL», cargar el horario del
  prototipo con un día cortado (09–13 y 16–20) y una fecha sin atención, con política (b);
  escribir en el hueco del mediodía y de noche y ver el mensaje fijo con «hoy a las 16:00» y con
  la fecha correcta; ver el entrante en PAN-WA-01 **quitando el filtro «sólo escaladas»**
  («Todas») y `responder_fuera_de_horario` en la bitácora; pasar a (a), pedir una persona y ver
  el aviso con la hora. Es la re-ejecución de I-09 (#71).
- **El modelo real**: no aplica — esta unidad no cambia el prompt ni el esquema.

## Coordinación

- **U10 `reserva-y-cancelacion-por-whatsapp`** (mergeada, `db62e0f`): se reutilizan
  `ZONA_ARGENTINA`, `TurnosPorWhatsApp` (armado de nuevo para la noche sobre `SalidaConPosdata`,
  T8), `SalidaAlCliente` (se subclasea, no se modifica) y los nombres de día de
  `textos_de_turnos.py`. No se cambia su comportamiento ni sus archivos.
- **U8 `recordatorio-de-turno`** (Gate 1 aprobado, sin implementar): toca los mismos archivos de
  business_config (`regla.py`: otro `TipoRegla` tipado; `reglas.py`; `api/routers/reglas.py`;
  `features/business_config/index.ts`). Por eso esta unidad pone su código en archivos nuevos
  (`horario_de_atencion*.py`, `apertura.py`, `atencion.py`, `atencion.ts`, los tres componentes)
  y en los compartidos agrega sólo líneas sueltas. Quien llegue segundo hace merge de `develop`
  (no rebase, el force push está denegado); los conflictos esperables son de una línea.
- **U5 `canal-real-de-whatsapp`** (Gate 1 condicionado al ADR-0011, **PR #62**): mueve
  `armar_mensajeria` a `api/mensajeria.py` y cambia `armar_agenda` y `_procesar` en
  `api/routers/whatsapp.py`, donde esta unidad agrega `horario=`. Conflicto de una línea, en el
  orden en que se mergeen. Con U5, el mensaje fijo sale por el canal real; antes, por el simulado.
- **U6 `plantillas-de-whatsapp-en-meta`**: borra `armar_plantillas` de `api/conversacional.py`,
  vecino de `armar_horario_de_atencion`. El mensaje fijo **no es plantilla**: contesta dentro de la
  ventana de 24 h que abrió el cliente al escribir, así que Meta no exige aprobación.
- **U7 `entregas-de-whatsapp`**: guarda avisos con `origen = SISTEMA` en el hilo; T9 sólo cuenta
  salientes `AGENTE`, así que un recordatorio no silencia el mensaje fijo (caso 24).
- **ADR-0011 (PR #62)**: agrega una fila `conversational → payments, scheduling, business_config`
  para el canal saliente; no toca la fila que esta unidad usa.
- **Migraciones**: ninguna; no compite por números.

## Fila de `docs/aidlc/units.md`

```
| Agente de WhatsApp y atención humana | politica-fuera-de-horario | business_config (conversational aplica la política por su ACL) | HS-T2, HU-E11-01, HU-E8-05 | reserva-y-cancelacion-por-whatsapp | Luciano | feature/business_config-politica-fuera-de-horario | en curso |
```

(Estado `en curso` desde la aprobación del Gate 1, 2026-10-05.)

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-05 | Aprobado por Luciano con las seis recomendaciones y tres ajustes: horario cortado y fechas cerradas dentro del alcance, y el arreglo del choque entre las preguntas 3 y 4 |
| 2 · Verificación | 2026-10-05 | Aprobado por Luciano. Local: `ruff` y `mypy` limpios (653 archivos), `pytest` 2156 pasan y 485 se saltean (PostgreSQL/Redis, sin Docker); frontend: prettier, lint y typecheck limpios, `test:coverage` 944 pasan, cobertura 87,76 %. Los RED se observaron mayormente como fallas de import (módulo inexistente); el caso 41 fue un RED por aserción. Quedan para la CI los casos 16, 17 y 37, y la revisión visual del CSS en staging (`TODO.md` §22.19) |
| 3 · PR | 2026-10-05 | [#84](https://github.com/cheatsheet12/CheatSheet/pull/84) contra `develop` (cierra #71). **Mergeado el 2026-10-05** (`9cedd14`), con la CI completa en verde (incluidos los casos 16, 17 y 37 contra PostgreSQL) y desplegado en staging |

## Decisiones tomadas durante la unidad

- Decisión de producto (2026-10-05, Luciano, previa al plan): **opción (c), cada empresa elige su
  política fuera de horario.** Por defecto (a): el agente sigue respondiendo las 24 h y sólo cambia
  la derivación a una persona —cuando el cliente la pide o el agente escala fuera de horario, el
  agente dice desde qué hora lo va a atender un asesor—. Alternativa (b), a elección de la empresa:
  fuera de horario el agente no responde y envía un mensaje fijo.
- Gate 1, Pregunta 1 (2026-10-05, Luciano) → la precondición de HU-E8-01 no se enmienda: **no hay
  ADR** (T3).
- Gate 1, Pregunta 2 → el horario de atención **se configura aparte** en PAN-WA-02, no se deduce de
  los recursos (T1).
- Gate 1, Pregunta 3 → en (b), **un mensaje fijo por período de cierre** (T9).
- Gate 1, Pregunta 4 → en (b), **(i) no se escala** un mensaje nocturno; **(ii) la respuesta a un
  diálogo vigente se sigue atendiendo** sin el modelo (T8).
- Gate 1, Pregunta 5 → **textos fijos del sistema**, no editables en esta unidad.
- Gate 1, Pregunta 6 → **sin interruptor «Agente activo»** en esta unidad; pendiente del épico 8.
- Gate 1, ajuste 1 (decisión de producto de Luciano) → **horario cortado dentro del alcance**:
  varias franjas por día, ordenadas, sin superponerse ni tocarse; el hueco entre franjas es «fuera
  de horario». El JSON ya guardaba una lista por día: sigue en `version: 1` (T5).
- Gate 1, ajuste 2 (decisión de producto de Luciano) → **fechas sin atención dentro del alcance**,
  cargadas a mano por la empresa; análogo de negocio de HU-E7-05 (que es por recurso). Sin ADR ni
  enmienda: HS-T2 RN-04 dice «horario de atención configurado» sin fijar su forma. El calendario
  automático de feriados nacionales queda afuera (depende de un tercero). Versión `1` con
  `fechas_cerradas` opcional al leer; horizonte de búsqueda de 366 días; sin apertura en el
  horizonte, textos sin fecha; fechas pasadas conservadas (la pantalla las oculta) y podadas al
  guardar pasado un año (T5).
- Gate 1, ajuste 3 → **choque entre las preguntas 3 y 4 (T9)**: en (b), con el negocio cerrado, la
  respuesta a un diálogo **termina con la oración de fuera de horario**, así todo saliente `AGENTE`
  del período informa el cierre y la regla «ya avisado» de T9 es cierta. Se agrega con
  `SalidaConPosdata`, sin tocar los pasos de turnos (T8).
- Gate 1, visibilidad (Pregunta 4 i) → los mensajes nocturnos de (b) quedan en la conversación pero
  **no en la vista inicial de PAN-WA-01** (filtrada por escaladas); se ven con «Todas». No se cambia
  la bandeja ni se agrega un pendiente: es la consecuencia buscada de no escalar, y el mensaje fijo
  le pide al cliente que vuelva a escribir en horario.

- Implementación (2026-10-05), desvíos del plan sin cambio de alcance:
  - **Caso 20**: el martes 13/10 es «mañana» del lunes 12/10 según `cuando_se_atiende` (T-textos y caso 34),
    así que el aviso del lunes 12/10 dice «a partir de mañana a las 09:00»; la forma «del martes 13/10» se prueba
    desde el sábado 10/10. El ejemplo del plan contradecía su propia regla.
  - **`ya_avisado` ignora los salientes `FALLIDO`**: si WhatsApp rechazó el mensaje, el cliente nunca se enteró y
    el siguiente mensaje debe reintentar. Se agregó un caso en `test_fuera_de_horario.py` (dominio).
  - **`atender_cerrado` recibe además el `Mensaje` guardado** para anotar la intención `TURNO` cuando sigue un
    diálogo (igual que el flujo de día); el mensaje fijo lo deja en `None`.
  - **`apertura.py` sin generador de «tramos»**: la contigüidad de medianoche no necesita unirlos (cada franja
    cubre su propio día local), así que `proxima_apertura` y `cerrado_desde` recorren las franjas fecha por fecha.
  - **Frontend**: el error del `PUT` es `ErrorDeAtencion` (no `ErrorDeRegla`, que es de `features/payments` y R5 no
    deja importarlo); «Hasta la medianoche» es una casilla por franja porque `input type="time"` no admite `24:00`;
    los helpers puros viven en `components/horario.ts`; se agregó un aviso cuando la regla está desactivada.
  - **Tests de PostgreSQL**: el rechazo del Operador a `PUT /reglas/horario-de-atencion` se afirma como 422
    (`EntradaInvalida(MOTIVO_SOLO_ADMIN)`, como el escalamiento).

## Preguntas del Gate 1 (resueltas el 2026-10-05)

Las seis recomendaciones se aprobaron tal como estaban escritas. Se conservan con su respuesta.

1. **¿La precondición de HU-E8-01 («…activo y dentro de su horario de atención») obliga a
   enmendar la historia por ADR?** Con la política (a) el agente reserva turnos a las 23:00.
   **Recomendación: no; no hace falta ADR.**
   *Por qué:* una precondición describe la situación en la que se escribió el escenario, no una
   regla de negocio; las reglas de HU-E8-01 (RN-01…RN-07) no mencionan el horario, y HS-T2 RN-04
   —que sí lo regula— delega en «la política definida», que es justamente lo que la empresa elige.
   Si se lee como prohibición, la opción (a) que ya se eligió la contradiría y habría que escribir
   el ADR (con el marcador «Modificada por ADR-XXXX», como ADR-0009) **antes** de cerrar este Gate.
   **Respuesta (Luciano, 2026-10-05): aprobada. Sin ADR.**

2. **¿El horario de atención se configura aparte, o se deduce de la disponibilidad de los
   recursos?**
   **Recomendación: aparte, en PAN-WA-02, como muestra el prototipo.**
   *Por qué:* son dos cosas (T1): cuándo se puede reservar con un recurso y cuándo una persona
   atiende el canal. Deducirlo de la unión de los recursos haría que una sala reservable hasta las
   22 «abra» el chat hasta las 22, y que una empresa sin recursos cargados (sólo FAQ) quede siempre
   cerrada. El costo es que la empresa carga dos horarios, uno por pantalla.
   **Respuesta: aprobada. Aparte, en PAN-WA-02** (y lo mismo para las fechas sin atención frente a
   las excepciones de los recursos).

3. **Con la política (b), ¿el mensaje fijo se manda a cada mensaje o una vez por cierre?**
   **Recomendación: una vez por período de cierre** (T9). Los mensajes siguientes de esa misma
   noche se guardan y no se contestan; la noche siguiente vuelve a salir.
   *Por qué:* el cliente que manda cinco mensajes seguidos recibiría cinco respuestas iguales, que
   en WhatsApp parece un bot roto. Se resuelve con el `origen` y el `momento` de los salientes que
   ya existen, sin columna nueva ni releer textos.
   **Respuesta: aprobada. Una vez por período**, con el ajuste 3 (la respuesta a un diálogo lleva la
   oración de fuera de horario, para que «ya avisado» sea cierto).

4. **Con la política (b), ¿la conversación queda pendiente para un asesor (escalamiento) y qué pasa
   con un diálogo abierto al cerrar?**
   **Recomendación: (i) no se escala; el mensaje fijo dice desde cuándo se atiende e invita a
   escribir de nuevo, y el entrante queda guardado en la conversación (visible en PAN-WA-01 sólo
   quitando el filtro «sólo escaladas»). (ii) La respuesta a un diálogo vigente (U10: elegir un
   horario ofrecido o confirmar una cancelación) se sigue atendiendo**, porque la lee el
   analizador determinista sin el modelo y la oferta vence a los 30 minutos.
   *Por qué (i):* escalar cada mensaje nocturno llenaría la bandeja del operador y, peor, haría
   callar al agente a la mañana (HU-E9-01 RN-02) hasta que una persona cierre el escalamiento,
   aunque la consulta fuera una FAQ. La alternativa (escalar con motivo «Mensaje fuera de
   horario») es coherente si la empresa que elige (b) quiere que **todo** lo nocturno lo vea una
   persona; cambia el texto del mensaje fijo y el caso 25.
   *Por qué (ii):* cortar a las 19:00 en punto una reserva ofrecida a las 18:55 deja al cliente con
   una oferta que no puede aceptar; contestarla no usa el modelo ni abre nada nuevo.
   **Respuesta: aprobada (i) y (ii)**, con el ajuste 3 y la nota de visibilidad.

5. **Textos y si la empresa los puede editar.**
   **Recomendación: textos fijos del sistema, no editables en esta unidad:**
   - Aviso de derivación con el negocio cerrado (T7): «Lo derivo con un asesor que va a continuar
     la conversación. Ahora estamos fuera del horario de atención: un asesor te va a responder a
     partir de {cuando}.» Sin apertura en el horizonte: «Lo derivo con un asesor que va a
     continuar la conversación. Ahora estamos fuera del horario de atención: un asesor te va a
     responder cuando retomemos la atención.»
   - Mensaje fijo (b): «Hola, gracias por escribirnos. En este momento estamos fuera del horario
     de atención. Atendemos de nuevo {cuando}: escribinos a partir de ese momento y te
     respondemos.» Sin apertura: «Hola, gracias por escribirnos. En este momento estamos fuera del
     horario de atención y todavía no tenemos fecha de regreso. Escribinos más adelante y te
     respondemos.»
   - Oración al final de la respuesta a un diálogo (b, ajuste 3): «Te recordamos que ahora estamos
     fuera del horario de atención; atendemos de nuevo {cuando}.» Sin apertura: «Te recordamos
     que ahora estamos fuera del horario de atención.»
   - `{cuando}` = «hoy a las 16:00» (también en el hueco de un horario cortado) / «mañana a las
     09:00» / «el martes 13/10 a las 09:00» (saltando las fechas sin atención).
   *Por qué:* la decisión (c) habla de «un mensaje fijo», y el dato que cambia (desde cuándo) ya lo
   pone el sistema. Hacerlo editable necesita un campo de texto con variables validadas (lo que
   `PlantillaDeNotificacion` hace para otra cosa) y ninguna historia lo pide; se puede sumar después
   sin tocar el modelo de datos.
   **Respuesta: aprobada. Textos fijos**, con las variantes sin fecha y la oración del ajuste 3.

6. **¿Entra el interruptor «Agente activo» del prototipo** (encabezado de PAN-WA-01/02, «Enciende
   o pausa el agente»), que el issue #71 también menciona?
   **Recomendación: no en esta unidad; queda como pendiente del épico 8.**
   *Por qué:* ninguna regla ni criterio dice qué hace un agente pausado (¿silencio total? ¿mensaje
   fijo? ¿todo a la bandeja del operador?), sólo aparece como precondición de HS-T2 («El agente
   está activo o existe un operador disponible») y de HU-E9-04. Decidirlo es otra pregunta de
   producto. Mientras tanto, la política (b) cubre el caso más pedido —que el agente no conteste
   cuando el negocio está cerrado— y desactivar la regla en PAN-CFG-RN vuelve al comportamiento de
   siempre.
   **Respuesta: aprobada. Fuera de esta unidad; pendiente del épico 8.**
