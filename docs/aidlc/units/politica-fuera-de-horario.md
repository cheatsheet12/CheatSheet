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

## Qué hace

Hoy el agente contesta igual a las 3 de la mañana que a las 11, y cuando deriva a un asesor le
dice al cliente «Lo derivo con un asesor que va a continuar la conversación.» aunque nadie vaya a
leerlo hasta el día siguiente. No hay dónde cargar el horario de atención ni la política.

Después de esta unidad:

- **La empresa carga su horario de atención** (una franja por día de la semana, o el día cerrado)
  y **elige su política fuera de horario** en la configuración del agente (PAN-WA-02), como
  muestra el prototipo. Se guarda como una regla de negocio más (HU-E11-01): aparece en
  PAN-CFG-RN con su tipo, prioridad y estado, y desactivarla deja de aplicarla de inmediato.
- **Política por defecto — «El agente responde siempre» (a).** Fuera de horario el agente sigue
  contestando, reservando y cancelando como de día. Lo único que cambia es la derivación: cuando
  el cliente pide una persona o el agente escala, el aviso agrega desde cuándo lo va a atender un
  asesor («…Ahora estamos fuera del horario de atención: un asesor te va a responder a partir del
  lunes 12/10 a las 09:00.»).
- **Política alternativa — «Fuera de horario, mensaje fijo» (b).** Fuera de horario el agente
  **no contesta**: el mensaje se registra igual (lo ve el operador) y el cliente recibe un único
  mensaje fijo con el horario en que se lo atiende. **El modelo no se llama.**
- **Sin horario configurado, nada cambia**: el agente atiende y deriva como hoy. Una empresa que
  nunca entró a la pantalla no puede quedar muda de golpe.
- Lo que no cambia: el modelo **no decide** si el negocio está abierto ni qué política rige. Eso
  lo calcula una función pura de business_config sobre la hora argentina; el modelo ni se entera.

**Fuera de esta unidad:**
- **Feriados y días especiales.** Ninguna historia los pide y el sistema no tiene calendario de
  feriados. Un feriado se trata como el día de la semana que es. Se anota un pendiente nuevo.
- **Horario cortado (dos franjas el mismo día, p. ej. 9–13 y 16–20).** El prototipo muestra una
  franja por día y ninguna historia pide más. El JSON se guarda como lista de franjas por día
  (con `version`), así que sumar la segunda franja después no requiere migrar datos (pendiente
  nuevo).
- **Zona horaria por empresa.** El DER no la tiene; todo el sistema usa `ZONA_ARGENTINA` (D-épico
  7, `ZONA_DE_LA_AGENDA`). El prototipo dice «Zona horaria: ART (GMT-3)» como texto fijo.
- **El interruptor «Agente activo»** del encabezado de PAN-WA-01/02: ver Pregunta 6.
- **Textos editables por la empresa**: ver Pregunta 5.

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
> agente de WhatsApp activo y dentro de su horario de atención.» (ver Pregunta 1).

**Prototipo PAN-WA-02** (`inputs/prototipos/agente-whatsapp.html:272-287`): tarjeta «Horarios de
atención — Cuándo el agente responde automáticamente», un renglón por día con interruptor y
«09:00 a 19:00» (sábado 09:00–14:00, domingo apagado), y «Zona horaria: ART (GMT-3)». La
anotación oficial de PAN-WA-02 (`anotaciones-comportamiento-oficial.html:196-210`): «Activar
agente / horarios — Enciende o pausa el agente y define la franja de atención automática». Solo
Admin. **Ningún prototipo muestra el selector de política**: se propone el mínimo (ver Frontend).

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
| `agente.py:169-174, 203, 297` | Los cuatro caminos que escalan (transcripción pobre, pedido de persona, baja confianza, desenlace de turnos —p. ej. seña—) pasan **todos** por `_escalar` (`:317-335`), que dice `MENSAJE_DERIVACION` (`:333`). Un solo punto para la política (a) |
| `agente.py:176-182` | La respuesta a un diálogo vigente (U10) se lee sin el modelo, **antes** de interpretar |
| `agente.py` | **370 líneas** (límite 400): lo nuevo va en módulos propios; `agente.py` gana sólo dos llamadas |
| `conversational/domain/conversacion.py:106-117, 138` | `Mensaje.origen` (`AGENTE` · `OPERADOR` · `SISTEMA`): se puede saber si el agente ya habló en un período sin releer textos |
| `conversational/application/ports.py` | 345 líneas; `PortRepositorioMensaje.del_hilo` (`:153`) ya existe |
| `api/routers/whatsapp.py:128-158` | `_procesar` arma `ProcesarMensajeEntrante` por mensaje, una transacción por mensaje |
| `frontend/src/app/(panel)/configuracion/respuestas/page.tsx` | Es PAN-WA-02 (FAQ). Ahí va la tarjeta del horario |
| `frontend/src/features/payments/api/regla.ts:9, 38-42` | La pantalla PAN-CFG-RN vive en `features/payments` (épico 6) con `TipoRegla` y `ETIQUETAS_DE_TIPO` cerrados a tres: una regla nueva se vería **sin rótulo** |
| `frontend/src/features/business_config/index.ts` | Vacío (`export {}`). U8 planea poner ahí su editor de agenda; esta unidad sigue el mismo patrón |

## Diseño

### Decisiones técnicas (resueltas con evidencia, no son preguntas)

**T1 · El horario de atención no es la disponibilidad de los recursos.** La disponibilidad
(`PatronDeDisponibilidad`) dice cuándo se puede **reservar** un turno con un recurso; el horario
de atención dice cuándo **una persona atiende el canal**. Pueden diferir en los dos sentidos
(una sala reservable de 8 a 22 con asesores de 9 a 18; un consultorio que atiende consultas por
WhatsApp aunque ese día no haya agenda). El prototipo los muestra en pantallas distintas
(PAN-AGE-03 vs. PAN-WA-02) y el agente ya consulta la disponibilidad por `PortAgenda`. Derivar uno
del otro está en la Pregunta 2.

**T2 · Vive en `business_config` como un cuarto `TipoRegla`: `HORARIO_DE_ATENCION`.** Es
comportamiento del sistema parametrizado por empresa, que es la definición de HU-E11-01, y
`regla_de_negocio` es el único lugar del DER para eso. Una regla = horario **y** política (una
fila, una tarjeta, un interruptor en PAN-CFG-RN).
- Descartado *una tabla nueva en conversational*: sería un agregado que el DER y
  `docs/architecture.md` §3 no tienen (27 agregados) → ADR, para algo que la tabla de reglas ya
  resuelve con su prioridad, su estado y su RLS.
- Descartado *reutilizar `AGENDA_DE_NOTIFICACION`*: significa otra cosa y U8 la toma.
- **Se aparta del DER** en un valor del enum `tipo_regla`. La columna es `varchar(40)` sin CHECK,
  así que no hay migración. Se anota como decisión **D100** (o el siguiente número libre) en
  `08-agente-de-whatsapp/decisiones.md`, como D99 hizo con `conversacion.dialogo`.

**T3 · No hace falta ADR.** (1) El edge `business_config → conversational` ya está en el Context
Map y ya se usa (plantillas). (2) Ninguna historia se modifica: HS-T2 RN-04 delega en «la
política definida», y la opción (c) es esa política. (3) Un valor más de un enum ya decidido por
D24 («una tabla, un JSONB validado por tipo») es una decisión de épico, no de arquitectura. La
precondición de HU-E8-01 se discute en la Pregunta 1: si Luciano la ve como una regla, ahí sí
hace falta un ADR que enmiende la historia **antes de cerrar este Gate 1**.

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
  ya es el día siguiente y **también otro día de la semana**.
- Franja semiabierta `[desde, hasta)`: a las 19:00 en punto de una franja 09:00–19:00 ya está
  cerrado. `hasta` admite `24:00` (fin del día); `desde < hasta`; no cruza la medianoche (un
  horario hasta las 2 se carga como dos días: `20:00–24:00` y `00:00–02:00`, y son contiguos).
- Al menos un día con franja: «ningún día» no es un horario (sería el agente apagado, Pregunta 6).
- JSON `{"version": 1, "politica": "AGENTE_RESPONDE" | "MENSAJE_FIJO", "dias": [{"dia": 0..6,
  "franjas": [{"desde": "HH:MM", "hasta": "HH:MM"}]}]}`, lunes 0 como en `recurso.py`. Una sola
  franja por día en esta unidad (ver «Fuera de esta unidad»). Leer una fila mal formada **falla
  al construir** (D24).
- `proxima_apertura(ahora)`: la primera franja que empieza después de `ahora` (o `ahora` mismo
  si está abierto), buscando hasta 7 días adelante — siempre la encuentra porque hay al menos un
  día. `cerrado_desde(ahora)`: el `hasta` de la última franja que terminó antes de `ahora`,
  buscando hasta 7 días atrás.

**T6 · Sin regla configurada, o con la regla desactivada, la empresa está «siempre abierta».**
`ConsultarAtencion` devuelve `configurado=False, abierto=True`. Es lo que pasa hoy, y RN-04 de
HU-E11-01 («deja de aplicarse de inmediato») se cumple sin un caso especial. A diferencia del
escalamiento de cobros, **no hay horario por defecto**: inventarle un horario a una empresa haría
que su agente cambie de comportamiento sin que nadie lo haya pedido.

**T7 · Política (a) — un solo punto: `_escalar`.** Si al escalar el negocio está cerrado, el
aviso es `MENSAJE_DERIVACION` + «Ahora estamos fuera del horario de atención: un asesor te va a
responder a partir de {cuando}.» Vale para los cuatro motivos (pedido de persona, baja confianza,
transcripción pobre, desenlace de turnos con seña). El escalamiento se crea igual: el operador lo
encuentra en su bandeja al abrir. `MENSAJE_OFRECER_ASESOR` («¿Querés que te derive…?») no cambia:
la hora se dice cuando la derivación ocurre, que es cuando el cliente queda esperando a una
persona. Dentro de horario, el texto es exactamente el de hoy.

**T8 · Política (b) — dónde corta.** El orden de `ejecutar` pasa a ser:
1. idempotencia → cliente → hilo → transcribir → **registrar** (RN-01: el mensaje queda siempre,
   el operador lo tiene que ver; el audio se transcribe igual porque HS-T7 RN-03 no guarda el
   audio, y sin texto el mensaje se perdería);
2. escalamiento abierto → el agente calla (sin cambios: con un operador en el hilo no sale ni el
   mensaje fijo);
3. **cerrado y política (b)**: si hay un diálogo vigente y el mensaje es una respuesta, se sigue
   (Pregunta 4); si no, el mensaje fijo (una vez por período, Pregunta 3) y **termina**: sin
   transcripción-pobre-escala, sin pedido de persona, **sin intérprete, sin embeddings, sin FAQ**;
   la intención del entrante queda `None` («no se clasificó», como define U3);
4. el resto, igual que hoy.

**T9 · «Una vez por período de cierre» sin columna nueva.** El agente ya avisó si en el hilo hay
un saliente con `origen = AGENTE` con `momento ≥ cerrado_desde(ahora)`: en (b), mientras está
cerrado, el agente no manda otra cosa que el mensaje fijo (o la continuación de un diálogo, que
también es una respuesta que el cliente recibió). No se relee ningún texto (lo que T2 de U10
descartó) y los avisos `SISTEMA` (recordatorios de U7/U8) y los del operador no cuentan.

**T10 · Bitácora (HS-T2 CA4 «Bitácora», RN-05).** En (b), el mensaje fijo publica
`responder_fuera_de_horario` con **iniciador IA**, módulo `CONVERSATIONAL`, entidad
`Conversacion:<id>`; un mensaje silenciado por T9 no publica nada (sólo log `fuera_de_horario_ya_avisado`).
En (a), los eventos de siempre (`interpretar_mensaje:*`, `escalar_conversacion`). En
business_config: `alta_regla_de_horario_de_atencion` / `editar_regla_de_horario_de_atencion`
(como el escalamiento) y los `activar_regla` / `desactivar_regla` que ya existen.

**T11 · Una configuración ilegible no voltea el webhook.** Si `ConsultarAtencion` falla al leer la
regla (`EntradaInvalida` por un JSON escrito a mano), el ACL de conversational la trata como «sin
horario» y registra `horario_ilegible`: el mensaje se procesa como hoy. Un 500 haría que Meta
reintente y el cliente no reciba nada. Es el criterio de `dialogo_ilegible` (U10).

**T12 · Tamaños.** `regla.py` (254) gana sólo el valor del enum y `interpretada_como_atencion`;
el horario vive en `domain/horario_de_atencion.py` (nuevo). Los casos de uso van en
`application/atencion.py` (nuevo) y no en `reglas.py`, que U8 también agranda. En conversational
la lógica va en `application/fuera_de_horario.py` y `domain/fuera_de_horario.py` (nuevos);
`agente.py` queda debajo de 400.

### Dominio

**business_config** (`domain/horario_de_atencion.py`, nuevo, puro):
- `FranjaDeAtencion(desde, hasta)` en minutos desde la medianoche (0 ≤ desde < hasta ≤ 1440),
  con `desde_texto("HH:MM")` y `como_texto`.
- `PoliticaFueraDeHorario` (`AGENTE_RESPONDE` = (a), por defecto; `MENSAJE_FIJO` = (b)).
- `ConfiguracionDeAtencion(dias: Mapping[int, FranjaDeAtencion], politica)` con invariantes
  (días 0–6 sin repetir, al menos uno), `como_json` / `desde_json` (con `version`) que fallan al
  leer algo mal formado, y `esta_abierto(instante)`, `proxima_apertura(instante)`,
  `cerrado_desde(instante)` sobre `instante.astimezone(ZONA_ARGENTINA)`.
- `EstadoDeAtencion(configurado, abierto, politica, proxima_apertura, cerrado_desde)` y
  `SIEMPRE_ABIERTO` (T6).
- Mensajes de validación: «La hora de cierre debe ser posterior a la de apertura.», «Indicá al
  menos un día con horario de atención.», «El horario debe tener el formato HH:MM.».

**business_config** (`domain/regla.py`): `TipoRegla.HORARIO_DE_ATENCION` y
`ReglaDeNegocio.interpretada_como_atencion()` (falla si el tipo no es ése, como la de
escalamiento).

**conversational** (`domain/fuera_de_horario.py`, nuevo, puro):
- `PoliticaFueraDeHorario` propia (`AGENTE_RESPONDE`, `MENSAJE_FIJO`) y
  `AtencionDelNegocio(abierto, politica, proxima_apertura, cerrado_desde)`.
- `cuando_se_atiende(proxima_apertura, ahora) -> str` en hora argentina, sin depender del locale
  («hoy a las 09:00», «mañana a las 09:00», «el lunes 12/10 a las 09:00»; reutiliza los nombres de
  día de `textos_de_turnos.py`).
- `aviso_de_derivacion(atencion, ahora) -> str` (T7) y `mensaje_fuera_de_horario(atencion, ahora)`
  (b) — textos en la Pregunta 5.
- `ya_avisado(mensajes, desde) -> bool` (T9).

### Aplicación

**business_config** (`application/atencion.py`, nuevo):
- `ConfigurarHorarioDeAtencion` — sólo Administrador (`MOTIVO_SOLO_ADMIN`), reemplaza en vez de
  acumular, reactiva al guardar, audita (T10). Copia de la forma de `ConfigurarEscalamiento`.
- `ConsultarAtencion` — **el Open Host Service** (sin chequeo de rol, como
  `ConsultarReglasVigentes`): lista las `HORARIO_DE_ATENCION`, `resolver` por prioridad (RN-05),
  sin regla → `SIEMPRE_ABIERTO` (T6); con regla → `EstadoDeAtencion` calculado para `ahora`.
- `configuracion_de_atencion_desde(crudo)` — traduce el formulario; la validación es del dominio.

**conversational**:
- `ports.py`: `PortHorarioDeAtencion.consultar(ahora) -> AtencionDelNegocio` (lo único que
  conversational sabe del horario).
- `application/fuera_de_horario.py` (nuevo, `AtencionFueraDeHorario`):
  `consultar(contexto)` (una consulta por mensaje, sólo si hace falta); `atender_cerrado(contexto,
  texto) -> Desenlace | None` para (b) (T8, T9, T10; delega la continuación del diálogo en
  `TurnosPorWhatsApp.continuar`); `aviso_de_derivacion(contexto)` para (a) (T7).
- `agente.py`: recibe `horario: PortHorarioDeAtencion`; después del chequeo de escalamiento
  abierto llama a `atender_cerrado` y, si devuelve algo, termina; `_escalar` usa
  `aviso_de_derivacion` en lugar de `MENSAJE_DERIVACION` fijo. Nada más.

### Puertos y adaptadores

- `conversational/infrastructure/horario.py` (nuevo, `HorarioViaConfiguracion`): implementa
  `PortHorarioDeAtencion` sobre `ConsultarAtencion` (R3: importa sólo `application/` de
  business_config, como `payments/infrastructure/cadena.py`); traduce la política al enum propio;
  T11.
- `api/conversacional.py`: `armar_horario_de_atencion(unidad, empresa_id)` con
  `ConfiguracionDeNegocio.armar(unidad).reglas`.
- `api/routers/whatsapp.py` (`_procesar`): pasa `horario=armar_horario_de_atencion(…)`.
- `api/routers/reglas.py`: `PUT /reglas/horario-de-atencion` (entrada `{dias: [{dia, desde,
  hasta}], politica, prioridad}`; sólo Admin; 422 con el mensaje del dominio). La lectura es el
  `GET /reglas` de siempre (devuelve el JSONB tal cual, `:49-51`), como hace U8 con la agenda.

### Otros contextos

- `conversational → business_config` por servicio de aplicación (`ConsultarAtencion`) detrás de un
  ACL: **la fila `business_config → payments, scheduling, conversational` del Context Map ya lo
  permite. No hace falta ADR para el edge** (ver T3 y Pregunta 1 para la historia).
- `scheduling`, `identity`, `master_data`: no se tocan.
- `shared/zona_horaria.py`: se reutiliza sin cambios.

### Frontend

- `features/business_config/api/atencion.ts` (nuevo): `TipoRegla` no se toca acá; lee la regla
  `HORARIO_DE_ATENCION` de `/api/reglas` de forma defensiva (una configuración mal formada se
  muestra vacía, como `pasosDe`) y `configurarHorarioDeAtencion(...)` hace `PUT`.
- `features/business_config/components/HorarioDeAtencion.tsx` (nuevo): la tarjeta del prototipo —
  un renglón por día con interruptor y dos `input type="time"` (con `24:00` permitido como
  «hasta»), «Zona horaria: ART (GMT-3)» — más **lo mínimo que el prototipo no tiene**: un grupo de
  dos radios «Fuera de horario: ● El agente responde igual (avisa desde cuándo atiende un asesor)
  ○ El agente no responde y envía un mensaje fijo», y el botón «Guardar». Sin regla, la tarjeta
  dice «Sin horario configurado: el agente atiende y deriva a cualquier hora.» y precarga los
  valores del prototipo sin guardarlos. Sólo el Administrador edita (PAN-WA-02 es «Solo Admin»);
  el resto la ve en modo lectura. El subtítulo del prototipo («Cuándo el agente responde
  automáticamente») pasa a «Cuándo atiende el negocio», porque con la política por defecto el
  agente responde a toda hora.
- `features/business_config/index.ts`: exporta `HorarioDeAtencion` y sus tipos.
- `app/(panel)/configuracion/respuestas/page.tsx` (PAN-WA-02): compone la tarjeta arriba de
  `RespuestasFrecuentes` (la ruta compone dos features, R5).
- `app/api/reglas/horario-de-atencion/route.ts` (nuevo, BFF `PUT`).
- `features/payments/api/regla.ts`: `TipoRegla` y `ETIQUETAS_DE_TIPO` suman
  `HORARIO_DE_ATENCION: "Horario de atención"`, para que PAN-CFG-RN la liste con rótulo y su
  interruptor de activa/inactiva funcione (RN-01, RN-04).

## Infraestructura

- **Migraciones**: **ninguna.** `regla_de_negocio.tipo` es `varchar(40)` sin CHECK
  (`0019_regla_y_cobro.py:137`) y la configuración es `jsonb`; la RLS de `regla_de_negocio` ya
  aísla por empresa. La cabeza de `develop` sigue en `0032` y la `0031` sigue reservada.
- **Trabajo asíncrono**: no aplica. La política se evalúa al llegar cada mensaje; no hay barrido
  ni nada que «despierte» al abrir.
- **Configuración**: no aplica (sin variables nuevas).
- **Integraciones externas**: ninguna nueva. En (b) fuera de horario **se ahorra** la llamada al
  LLM y a los embeddings; WhatsApp: un saliente por período de cierre.

## Riesgos que obligan a tests

- [ ] Toca dinero: no aplica.
- [ ] Comprobantes fiscales / CAE: no aplica.
- [x] Consume un webhook → el mismo `externo_id` fuera de horario en (b) produce **un solo**
      mensaje fijo (caso 27).
- [x] Datos con `empresa_id` → el horario de la empresa A nunca rige para la B (casos 12, 29).
- [x] Usa salida de un LLM → **al revés**: se prueba que en (b) fuera de horario el modelo **no se
      llama** (casos 16, 17, 20, 23) y que ninguna decisión de horario depende de él.
- [ ] Datos personales al LLM: no cambia (en (b) llega menos, no más).
- [x] **Zona horaria** → un `datetime` UTC comparado contra un horario local es el bug clásico
      del borde de la medianoche (casos 3, 4, 26).
- [x] **Rollback**: `repositories.py:39` hace `TipoRegla(fila.tipo)`; si esta unidad se revierte
      con reglas `HORARIO_DE_ATENCION` cargadas, `GET /reglas` del código viejo falla. Se anota
      en el PR: revertir exige desactivar y borrar esas filas a mano antes.

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/business_config/domain/horario_de_atencion.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/business_config/domain/regla.py` (`HORARIO_DE_ATENCION`, `interpretada_como_atencion`)
- [ ] `backend/src/cheatsheet/contexts/business_config/application/atencion.py` (nuevo: `ConfigurarHorarioDeAtencion`, `ConsultarAtencion`)
- [ ] `backend/src/cheatsheet/api/routers/reglas.py` (`PUT /reglas/horario-de-atencion`)
- [ ] `backend/src/cheatsheet/contexts/conversational/domain/fuera_de_horario.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/conversational/application/fuera_de_horario.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/conversational/application/ports.py` (`PortHorarioDeAtencion`)
- [ ] `backend/src/cheatsheet/contexts/conversational/application/agente.py` (dos llamadas; < 400 líneas)
- [ ] `backend/src/cheatsheet/contexts/conversational/infrastructure/horario.py` (nuevo, ACL)
- [ ] `backend/src/cheatsheet/api/conversacional.py` (`armar_horario_de_atencion`)
- [ ] `backend/src/cheatsheet/api/routers/whatsapp.py` (`_procesar` pasa el horario)
- [ ] `backend/tests/contexts/business_config/domain/test_horario_de_atencion.py` (nuevo)
- [ ] `backend/tests/contexts/business_config/application/test_atencion.py` (nuevo)
- [ ] `backend/tests/contexts/conversational/domain/test_fuera_de_horario.py` (nuevo)
- [ ] `backend/tests/contexts/conversational/application/horario_fijo.py` (nuevo: doble `HorarioFijo`; `dobles.py` ya pasa de 400)
- [ ] `backend/tests/contexts/conversational/application/escena.py` (el horario en la escena, «siempre abierto» por defecto)
- [ ] `backend/tests/contexts/conversational/application/test_fuera_de_horario.py` (nuevo)
- [ ] `backend/tests/contexts/conversational/infrastructure/test_horario.py` (nuevo, ACL)
- [ ] `backend/tests/integracion/test_horario_de_atencion_postgres.py` (nuevo: RLS y API de punta a punta)

### Frontend
- [ ] `frontend/src/features/business_config/api/atencion.ts` (nuevo) y `api/__tests__/atencion.test.ts`
- [ ] `frontend/src/features/business_config/components/HorarioDeAtencion.tsx` (nuevo) y `components/__tests__/HorarioDeAtencion.test.tsx`
- [ ] `frontend/src/features/business_config/index.ts`
- [ ] `frontend/src/app/(panel)/configuracion/respuestas/page.tsx`
- [ ] `frontend/src/app/api/reglas/horario-de-atencion/route.ts` (nuevo)
- [ ] `frontend/src/features/payments/api/regla.ts` y `api/__tests__/regla.test.ts` (rótulo del tipo nuevo)

### Documentación
- [x] `docs/aidlc/units/politica-fuera-de-horario.md` (este plan)
- [x] `docs/aidlc/units.md` (fila nueva)
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/decisiones.md` (D100: cuarto `TipoRegla`; política (c); «siempre abierto» sin regla)
- [ ] `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` (nuevos: feriados, horario cortado, interruptor «agente activo» si la Pregunta 6 lo deja afuera)
- [ ] `docs/aidlc/TODO.md` §22 (verificaciones manuales en staging, ver abajo)

## Casos de prueba

Test primero: cada **RED** se escribe y se ve fallar contra el código actual antes de implementar.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED** `ConfiguracionDeAtencion`: ida y vuelta por JSON; rechaza `hasta ≤ desde`, día repetido, día fuera de 0–6, ningún día, «9:00» sin cero, `version` desconocida, política fuera del enum — cada uno con su mensaje | unit (dominio bc) | pendiente |
| 2 | `esta_abierto` con lunes 09:00–19:00: 08:59 cerrado, 09:00 abierto, 18:59 abierto, **19:00 cerrado** | unit (dominio bc) | pendiente |
| 3 | **RED** Borde de medianoche: lunes `20:00–24:00`, martes cerrado. `2026-10-06T02:59Z` (lunes 23:59 en Argentina, **martes en UTC**) → abierto; `2026-10-06T03:00Z` (martes 00:00) → cerrado | unit (dominio bc) | pendiente |
| 4 | Contigüidad: lunes `20:00–24:00` y martes `00:00–02:00` → abierto a las 23:59 y a las 00:00; `proxima_apertura` y `cerrado_desde` lo tratan como un solo tramo | unit (dominio bc) | pendiente |
| 5 | Día sin horario: domingo cerrado todo el día; `proxima_apertura` desde sábado 14:00 → lunes 09:00; con un solo día abierto a la semana → el mismo día de la semana siguiente | unit (dominio bc) | pendiente |
| 6 | `cerrado_desde`: lunes 22:00 → lunes 19:00; domingo 10:00 → sábado 14:00; lunes 08:00 → sábado 14:00 | unit (dominio bc) | pendiente |
| 7 | `interpretada_como_atencion` sobre una regla de escalamiento → falla; `TipoRegla("HORARIO_DE_ATENCION")` existe | unit (dominio bc) | pendiente |
| 8 | **RED** `ConfigurarHorarioDeAtencion`: crea la regla; un segundo guardado la reemplaza (una sola fila); guardar una desactivada la reactiva; evento `alta_…`/`editar_regla_de_horario_de_atencion` | unit (aplicación bc) | pendiente |
| 9 | Un Operador no puede configurar el horario (`MOTIVO_SOLO_ADMIN`) | unit (aplicación bc) | pendiente |
| 10 | **RED** `ConsultarAtencion`: sin regla → `configurado=False, abierto=True`; regla desactivada → igual (HU-E11-01 RN-04); con regla → estado calculado para `ahora` | unit (aplicación bc) | pendiente |
| 11 | Dos reglas `HORARIO_DE_ATENCION` activas → rige la de mayor prioridad y, a igualdad, la más reciente (RN-05) | unit (aplicación bc) | pendiente |
| 12 | Multi-tenant: la regla de la empresa A no se lee con la sesión de la empresa B (RLS) | integración (Postgres, CI) | pendiente |
| 13 | API: `PUT /reglas/horario-de-atencion` 200 para Admin; 422 con «La hora de cierre debe ser posterior a la de apertura.»; rechazo para Operador; `GET /reglas` la lista con su tipo, prioridad y estado | integración (API, CI) | pendiente |
| 14 | **RED** Política (a) fuera de horario: «quiero hablar con una persona» → escalamiento creado y el cliente recibe `MENSAJE_DERIVACION` + «…un asesor te va a responder a partir del lunes 12/10 a las 09:00.» | unit (aplicación conv) | pendiente |
| 15 | Política (a): baja confianza agotada y turno con seña fuera de horario → el mismo aviso con la hora; **dentro** de horario → exactamente `MENSAJE_DERIVACION` (sin cambios) | unit (aplicación conv) | pendiente |
| 16 | Política (a) fuera de horario: «¿cuánto sale?» → el agente interpreta y contesta la FAQ como de día (el intérprete **sí** se llama) | unit (aplicación conv) | pendiente |
| 17 | **RED** Política (b) fuera de horario: el entrante queda guardado (contenido, `intencion = None`); el cliente recibe **un** mensaje fijo con la próxima apertura; **el intérprete y los embeddings no se llamaron**; no hay escalamiento; evento `responder_fuera_de_horario` con iniciador IA | unit (aplicación conv) | pendiente |
| 18 | **RED** Política (b): segundo y tercer mensaje en el mismo cierre → se guardan, **ningún saliente nuevo**, el intérprete no se llamó (según Pregunta 3) | unit (aplicación conv) | pendiente |
| 19 | Política (b): un mensaje la noche siguiente (otro período de cierre) → el mensaje fijo sale de nuevo; un aviso `SISTEMA` o un mensaje del operador en el medio no cuentan como «ya avisado» | unit (aplicación conv) | pendiente |
| 20 | Política (b) fuera de horario: «quiero hablar con una persona» → mensaje fijo, sin escalamiento (según Pregunta 4), sin intérprete | unit (aplicación conv) | pendiente |
| 21 | Política (b) con escalamiento abierto → silencio (ni mensaje fijo): manda el operador (HU-E9-01 RN-02) | unit (aplicación conv) | pendiente |
| 22 | Política (b), diálogo vigente abierto a las 18:55 y cierre a las 19:00: «el primero» a las 19:02 → reserva sin el modelo (según Pregunta 4); «hola, ¿cuánto sale?» a las 19:02 → mensaje fijo, sin intérprete | unit (aplicación conv) | pendiente |
| 23 | Política (b) con audio fuera de horario: se transcribe y se guarda el texto, no se interpreta; transcripción pobre → mensaje fijo, **no** escala | unit (aplicación conv) | pendiente |
| 24 | Política (b) **dentro** de horario → el flujo de hoy, sin cambios | unit (aplicación conv) | pendiente |
| 25 | Sin horario configurado → los tests existentes del agente pasan sin tocarlos (la escena usa «siempre abierto») y la derivación dice `MENSAJE_DERIVACION` a cualquier hora | unit (aplicación conv) | pendiente |
| 26 | **RED** `cuando_se_atiende`: el domingo a las 22:30 de Argentina (`lunes 01:30Z`) con apertura el lunes 09:00 → «mañana a las 09:00», no «hoy»; el lunes 08:00 → «hoy a las 09:00»; el viernes 20:00 → «el lunes 12/10 a las 09:00» | unit (dominio conv) | pendiente |
| 27 | Mismo `externo_id` entregado dos veces fuera de horario en (b) → un solo mensaje fijo (idempotencia de siempre) | unit (aplicación conv) | pendiente |
| 28 | ACL: regla con JSON ilegible → «sin horario», log `horario_ilegible`, el mensaje se procesa como hoy (no 500); política de business_config → enum propio de conversational | unit (infra conv) | pendiente |
| 29 | De punta a punta por la API con el simulado: empresa A con (b) y cerrada, empresa B sin horario; un mensaje a cada una → A recibe el mensaje fijo y su entrante queda sin intención; B recibe la respuesta normal | integración (API, CI) | pendiente |
| 30 | **RED** `HorarioDeAtencion` (frontend): sin regla muestra «Sin horario configurado…» con los valores del prototipo precargados; con regla pinta sus días y su política; «Guardar» manda el `PUT` con el cuerpo esperado; el mensaje de validación del backend se muestra; un Operador la ve sin poder editar | unit (frontend) | pendiente |
| 31 | `atencion.ts`: lee la configuración de forma defensiva (mal formada → vacía); un error del `PUT` llega como `ErrorDeRegla` | unit (frontend) | pendiente |
| 32 | **RED** PAN-CFG-RN: una regla `HORARIO_DE_ATENCION` se lista con el rótulo «Horario de atención» (hoy sale vacío) | unit (frontend) | pendiente |
| 33 | `agente.py` < 400 líneas; ningún archivo nuevo > 400; funciones ≤ 50 líneas; `guard_architecture --scan` (R3: conversational sólo importa `application/` de business_config; R5 en la ruta) | revisión + `ruff` (C901) + guard | pendiente |

## Verificaciones que no se pueden hacer acá

- **PostgreSQL** (casos 12, 13, 29): sin Docker en esta máquina; se saltean en local y se confirman
  en la CI del PR.
- **WhatsApp real**: que el cliente reciba el mensaje fijo una sola vez de noche depende del número
  de prueba y de U5 → `TODO.md` §22 (nueva fila) / §25.
- **En staging** (`TODO.md` §22, nueva fila): con «Estudio Ejemplo SRL», cargar el horario del
  prototipo con política (b), escribir fuera de horario y ver el mensaje fijo, el entrante en
  PAN-WA-01 y `responder_fuera_de_horario` en la bitácora; pasar a (a), pedir una persona y ver el
  aviso con la hora. Es la re-ejecución de I-09 (#71).
- **El modelo real**: no aplica — esta unidad no cambia el prompt ni el esquema.

## Coordinación

- **U10 `reserva-y-cancelacion-por-whatsapp`** (mergeada, `db62e0f`): se reutilizan
  `ZONA_ARGENTINA`, `TurnosPorWhatsApp.continuar` (Pregunta 4) y los nombres de día de
  `textos_de_turnos.py`. No se cambia su comportamiento.
- **U8 `recordatorio-de-turno`** (Gate 1 aprobado, sin implementar): toca los mismos archivos de
  business_config (`regla.py`: otro `TipoRegla` tipado; `reglas.py`; `api/routers/reglas.py`;
  `features/business_config/index.ts`). Por eso esta unidad pone su código en archivos nuevos
  (`horario_de_atencion.py`, `atencion.py`, `atencion.ts`, `HorarioDeAtencion.tsx`) y en los
  compartidos agrega sólo líneas sueltas. Quien llegue segundo hace merge de `develop` (no rebase,
  el force push está denegado); los conflictos esperables son de una línea.
- **U5 `canal-real-de-whatsapp`** (Gate 1 condicionado al ADR-0011, **PR #62**): mueve
  `armar_mensajeria` a `api/mensajeria.py` y cambia `armar_agenda` y `_procesar` en
  `api/routers/whatsapp.py`, donde esta unidad agrega `horario=`. Conflicto de una línea, en el
  orden en que se mergeen. Con U5, el mensaje fijo sale por el canal real; antes, por el simulado.
- **U6 `plantillas-de-whatsapp-en-meta`**: borra `armar_plantillas` de `api/conversacional.py`,
  vecino de `armar_horario_de_atencion`. El mensaje fijo **no es plantilla**: contesta dentro de la
  ventana de 24 h que abrió el cliente al escribir, así que Meta no exige aprobación.
- **U7 `entregas-de-whatsapp`**: guarda avisos con `origen = SISTEMA` en el hilo; T9 sólo cuenta
  salientes `AGENTE`, así que un recordatorio no silencia el mensaje fijo (caso 19).
- **ADR-0011 (PR #62)**: agrega una fila `conversational → payments, scheduling, business_config`
  para el canal saliente; no toca la fila que esta unidad usa.
- **Migraciones**: ninguna; no compite por números.

## Fila de `docs/aidlc/units.md`

```
| Agente de WhatsApp y atención humana | politica-fuera-de-horario | business_config (conversational aplica la política por su ACL) | HS-T2, HU-E11-01, HU-E8-05 | reserva-y-cancelacion-por-whatsapp | Luciano | feature/business_config-politica-fuera-de-horario | pendiente |
```

(Estado `en curso` cuando se apruebe el Gate 1.)

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Decisión de producto (2026-10-05, Luciano, previa al plan): **opción (c), cada empresa elige su
  política fuera de horario.** Por defecto (a): el agente sigue respondiendo las 24 h y sólo cambia
  la derivación a una persona —cuando el cliente la pide o el agente escala fuera de horario, el
  agente dice desde qué hora lo va a atender un asesor—. Alternativa (b), a elección de la empresa:
  fuera de horario el agente no responde y envía un mensaje fijo.

## Preguntas del Gate 1 (con recomendación)

1. **¿La precondición de HU-E8-01 («…activo y dentro de su horario de atención») obliga a
   enmendar la historia por ADR?** Con la política (a) el agente reserva turnos a las 23:00.
   **Recomendación: no; no hace falta ADR.**
   *Por qué:* una precondición describe la situación en la que se escribió el escenario, no una
   regla de negocio; las reglas de HU-E8-01 (RN-01…RN-07) no mencionan el horario, y HS-T2 RN-04
   —que sí lo regula— delega en «la política definida», que es justamente lo que la empresa elige.
   Si se lee como prohibición, la opción (a) que ya se eligió la contradiría y habría que escribir
   el ADR (con el marcador «Modificada por ADR-XXXX», como ADR-0009) **antes** de cerrar este Gate.

2. **¿El horario de atención se configura aparte, o se deduce de la disponibilidad de los
   recursos?**
   **Recomendación: aparte, en PAN-WA-02, como muestra el prototipo.**
   *Por qué:* son dos cosas (T1): cuándo se puede reservar con un recurso y cuándo una persona
   atiende el canal. Deducirlo de la unión de los recursos haría que una sala reservable hasta las
   22 «abra» el chat hasta las 22, y que una empresa sin recursos cargados (sólo FAQ) quede siempre
   cerrada. El costo es que la empresa carga dos horarios, uno por pantalla.

3. **Con la política (b), ¿el mensaje fijo se manda a cada mensaje o una vez por cierre?**
   **Recomendación: una vez por período de cierre** (T9). Los mensajes siguientes de esa misma
   noche se guardan y no se contestan; la noche siguiente vuelve a salir.
   *Por qué:* el cliente que manda cinco mensajes seguidos recibiría cinco respuestas iguales, que
   en WhatsApp parece un bot roto. Se resuelve con el `origen` y el `momento` de los salientes que
   ya existen, sin columna nueva ni releer textos.

4. **Con la política (b), ¿la conversación queda pendiente para un asesor (escalamiento) y qué pasa
   con un diálogo abierto al cerrar?**
   **Recomendación: (i) no se escala; el mensaje fijo dice desde cuándo se atiende e invita a
   escribir de nuevo, y el entrante queda en PAN-WA-01. (ii) La respuesta a un diálogo vigente
   (U10: elegir un horario ofrecido o confirmar una cancelación) se sigue atendiendo**, porque la
   lee el analizador determinista sin el modelo y la oferta vence a los 30 minutos.
   *Por qué (i):* escalar cada mensaje nocturno llenaría la bandeja del operador y, peor, haría
   callar al agente a la mañana (HU-E9-01 RN-02) hasta que una persona cierre el escalamiento,
   aunque la consulta fuera una FAQ. La alternativa (escalar con motivo «Mensaje fuera de
   horario») es coherente si la empresa que elige (b) quiere que **todo** lo nocturno lo vea una
   persona; cambia el texto del mensaje fijo y el caso 20.
   *Por qué (ii):* cortar a las 19:00 en punto una reserva ofrecida a las 18:55 deja al cliente con
   una oferta que no puede aceptar; contestarla no usa el modelo ni abre nada nuevo.

5. **Textos y si la empresa los puede editar.**
   **Recomendación: textos fijos del sistema, no editables en esta unidad:**
   - (a), al derivar fuera de horario: «Lo derivo con un asesor que va a continuar la
     conversación. Ahora estamos fuera del horario de atención: un asesor te va a responder a
     partir de {cuando}.»
   - (b): «Hola, gracias por escribirnos. En este momento estamos fuera del horario de atención.
     Atendemos de nuevo {cuando}: escribinos a partir de ese momento y te respondemos.»
   - `{cuando}` = «hoy a las 09:00» / «mañana a las 09:00» / «el lunes 12/10 a las 09:00».
   *Por qué:* la decisión (c) habla de «un mensaje fijo», y el dato que cambia (desde cuándo) ya lo
   pone el sistema. Hacerlo editable necesita un campo de texto con variables validadas (lo que
   `PlantillaDeNotificacion` hace para otra cosa) y ninguna historia lo pide; se puede sumar después
   sin tocar el modelo de datos.

6. **¿Entra el interruptor «Agente activo» del prototipo** (encabezado de PAN-WA-01/02, «Enciende
   o pausa el agente»), que el issue #71 también menciona?
   **Recomendación: no en esta unidad; queda como pendiente del épico 8.**
   *Por qué:* ninguna regla ni criterio dice qué hace un agente pausado (¿silencio total? ¿mensaje
   fijo? ¿todo a la bandeja del operador?), sólo aparece como precondición de HS-T2 («El agente
   está activo o existe un operador disponible») y de HU-E9-04. Decidirlo es otra pregunta de
   producto. Mientras tanto, la política (b) cubre el caso más pedido —que el agente no conteste
   cuando el negocio está cerrado— y desactivar la regla en PAN-CFG-RN vuelve al comportamiento de
   siempre.
