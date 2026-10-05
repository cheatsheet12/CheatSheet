# Unidad: ajustes-menores-del-agente

**HUs**: HS-T2, HU-E8-05   **Contexto dueño**: conversational   **Rama**: fix/conversational-ajustes-menores-del-agente

> Origen: hallazgos de una auditoría de código sobre `agente-y-atencion-humana` (mergeada). Dos bugs
> **Menores**, independientes entre sí, dentro de `conversational`. Un tercero (B6, el contador de
> FAQ) salió de esta unidad: pasó a `usos-de-faq-por-periodo`. B5 además se confirmó en
> `staging` el 2026-10-03. Es un `fix/…` cortado de `develop` (`2eff3a0`); el PR va a `develop` y no
> depende de ninguna otra unidad. Ninguno de los tres está registrado en
> [`pendientes.md`](../epicas/08-agente-de-whatsapp/pendientes.md) del épico 8.

## Qué hace

Dos correcciones chicas, una por sección, cada una con su test que la reproduce primero:

- **B5 — La intención del mensaje entrante se guarda** (HS-T2 RN-02 / CA1). Hoy el agente interpreta
  el mensaje pero la intención sólo queda en el texto de la acción de auditoría; el mensaje se guarda
  con `intencion = None` y el hilo de PAN-WA-01 no muestra la etiqueta. Después del fix, el mensaje
  entrante interpretado queda con su intención y el panel la muestra.
- **B7 — El pedido explícito de una persona deja de dispararse por subcadenas** (HU-E8-05 RN-01 / CA1).
  Hoy «soy una persona que quiere un turno» escala la conversación. Después del fix, se escala cuando
  el cliente **pide** una persona, no cuando la nombra.

**Fuera de esta unidad:**
- Entender un «sí» como respuesta a «¿Querés que te derive con un asesor?» (`MENSAJE_OFRECER_ASESOR`):
  es estado de conversación, la misma decisión abierta que el pendiente #5 del épico 8.
- Reemplazar el `InterpreteSimulado` (también clasifica por subcadenas): es un doble que se niega en
  producción, y su reemplazo es una decisión de despliegue.
- El contador de usos de las FAQ por período (B6, HU-E9-04 RN-02): pasó a su propia unidad,
  `usos-de-faq-por-periodo` (tabla de eventos, habilitada por el ADR-0012).

## La historia

> **HS-T2 — Procesar un mensaje entrante recibido desde WhatsApp**
> * RN-01: El proceso registra el mensaje entrante con su contenido, tipo y conversación asociada,
>   conforme a la entidad Mensaje.
> * RN-02: El sistema interpreta la intención del mensaje y la clasifica (turno, consulta, pago, FAQ).
>
> | Cuando | Espero |
> | :---- | :---- |
> | Llega un mensaje entrante | El sistema lo registra e interpreta su intención |

> **HU-E8-05 — Ser derivado a un asesor humano**
> * RN-01: La derivación se produce cuando el agente no interpreta la intención con confianza
>   suficiente o cuando el cliente **la solicita explícitamente**, conforme a la entidad Escalamiento.
>
> | Cuando | Espero |
> | :---- | :---- |
> | Solicito explícitamente hablar con una persona | El agente deriva la conversación a un asesor humano y me lo avisa |

## Hallazgos

| Dónde | Qué |
|---|---|
| `contexts/conversational/application/agente.py:232-252` | **B5.** `_guardar_entrante` crea el `Mensaje` sin `intencion` (queda en `None`) y no lo devuelve |
| `contexts/conversational/application/agente.py:177-178` | **B5.** `lectura = await self._interprete.leer(…)`; la intención sólo viaja a `_auditar` (acción `interpretar_mensaje:<intencion>`, líneas 411-433) y al `Respuesta` de retorno; **nunca se escribe en el mensaje** |
| `contexts/conversational/domain/conversacion.py:135` | **B5.** `Mensaje.intencion: Intencion \| None = None` ya existe |
| `contexts/conversational/infrastructure/models.py:71` · `repositories.py:290,304` | **B5.** La columna `mensaje.intencion` ya existe (migración `0021_agente_conversacional`) y el repositorio la lee y la escribe. **No hace falta migración** |
| `contexts/conversational/application/ports.py:136` | **B5.** `PortRepositorioMensaje.guardar` ya existe (lo usa `CerrarEscalamiento._reclasificar`, `atencion.py:313-337`, que **sí** escribe la intención al devolver el hilo al agente) |
| `api/routers/conversaciones.py:92,173` | **B5.** `MensajeSalida.intencion` ya se expone |
| `frontend/src/features/conversational/components/HiloDeConversacion.tsx:109` | **B5.** El hilo ya pinta `· {ETIQUETAS_DE_INTENCION[…]}` cuando la intención no es `null`. **El frontend no tiene bug**: no le llega el dato |
| `contexts/conversational/application/agente.py:88-96` | **B7.** `PEDIDOS_DE_HUMANO` incluye `"una persona"`, `"un humano"`, `"un asesor"` sueltos |
| `contexts/conversational/application/agente.py:170-173` · `438-446` | **B7.** `_pide_una_persona` hace `any(frase in texto.lower() …)`: subcadena pura. «soy una persona que quiere un turno» contiene «una persona» → escala sin pasar por el modelo |
| `backend/tests/contexts/conversational/application/test_agente.py:226-236` | **B7.** El único caso positivo probado es «quiero hablar con una persona por favor»; no hay ningún caso negativo |
| `contexts/conversational/application/agente.py` | El archivo ya tiene **456 líneas** (> 400 de `CLAUDE.md` §5). B7 saca la detección a un módulo propio, así que el fix no lo agranda |

## Diseño

### B5 — guardar la intención del mensaje entrante

- **Dominio**: sin cambios (`Mensaje.intencion` ya existe).
- **Aplicación** (`agente.py`, `ProcesarMensajeEntrante`):
  - `_guardar_entrante` **devuelve** el `Mensaje` que agregó.
  - Después de `leer` y de decidir el camino, se escribe la intención en ese mensaje y se llama a
    `self._mensajes.guardar(mensaje)`. Se extrae a un helper (`_anotar_intencion`) para que
    `ejecutar` no crezca.
  - **Qué intención se guarda**: la **misma que devuelve `Respuesta`** — `lectura.intencion` si la
    confianza alcanza el umbral, `Intencion.DESCONOCIDA` si no (Gate 1, Q3). Así el hilo del
    panel y lo que el agente hizo dicen lo mismo.
  - Los caminos que **no interpretan** dejan `intencion = None`, que en el dominio significa «no se
    clasificó» (docstring de `Intencion`): con un escalamiento abierto (el agente calla), con
    transcripción pobre, y con el pedido explícito de una persona. No se finge una clasificación que
    no ocurrió.
  - Si el intérprete falla con una excepción, el mensaje ya quedó guardado (paso 3 de HS-T2) y la
    intención sigue en `None`: el orden «registrar antes de interpretar» no cambia.
- **Puertos y adaptadores**: sin cambios (`PortRepositorioMensaje.guardar` ya existe y el adaptador
  SQL ya persiste `intencion`).
- **Otros contextos**: no aplica.
- **Frontend**: sin cambios de código. Se agrega un test que fija que el hilo muestra la etiqueta.

### B7 — detectar el pedido, no la palabra

- **Dominio**: módulo nuevo `contexts/conversational/domain/pedido_de_persona.py` con una función pura
  `pide_una_persona(texto: str) -> bool` y su vocabulario. Es una regla de negocio (HU-E8-05 RN-01)
  sin I/O ni framework: cumple R1. Sale de `agente.py`, que baja de tamaño.
- **Regla, determinista y sin LLM:**
  1. **Normalizar**: minúsculas, sin tildes (`unicodedata` NFKD), signos de puntuación como
     separadores de cláusula.
  2. **Destinatario**: `persona`, `humano`, `humana`, `asesor`, `asesora`, `operador`, `operadora`,
     precedido de artículo (`un`, `una`) o de `con`; y la frase fija `atencion humana`.
  3. **Pedido**: dentro de la **misma cláusula**, el destinatario va precedido (a pocas palabras) por
     un verbo de pedido: `quiero`, `necesito`, `prefiero`, `hablar`, `comunicarme`, `pasame`,
     `paseme`, `pasenme`, `derivame`, `que me atienda`; o `hablar con alguien`.
  4. **Mensaje que es sólo el destinatario** (`"un asesor"`, `"una persona por favor"`,
     `"atención humana"`) también cuenta: es un pedido escrito en telegrama.
  Todo con límites de palabra (`\b`), así «personal» o «asesoramiento» no disparan.
- **Aplicación**: `agente.py` importa `pide_una_persona` y borra `PEDIDOS_DE_HUMANO` y
  `_pide_una_persona`. El lugar del chequeo (antes del modelo) no cambia.
- **Puertos, otros contextos, frontend**: no aplica.

Consecuencia aceptada: un pedido muy indirecto («me atiende alguien de carne y hueso?») no escala
por esta vía; si el modelo no lo entiende, escala por baja confianza a los dos intentos (RN-01,
primer motivo). Un falso positivo (escalar a quien quería un turno) es peor que un falso negativo
que igual termina en una persona.

## Infraestructura

- **Migraciones**: no aplica. `mensaje.intencion` ya existe.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no aplica.
- **Integraciones externas**: no aplica (no se agrega ninguna llamada externa; B7 no usa el LLM).

## Riesgos que obligan a tests

- [ ] Toca dinero: no aplica
- [ ] Comprobantes fiscales / CAE: no aplica
- [ ] Webhook: no aplica (B5 corre dentro del webhook de WhatsApp, pero la idempotencia no cambia;
      el test existente `test_un_mensaje_repetido_no_llega_al_modelo` sigue cubriéndola)
- [ ] Datos con `empresa_id`: no aplica (no hay tablas ni consultas nuevas)
- [x] Salida de un LLM: B5 **guarda** la intención que devolvió el intérprete. Ya viene validada por
      schema (`interprete.py:55-57`, enum cerrado) y el valor guardado es un `Intencion` del enum;
      no dispara ningún efecto real nuevo
- [ ] Datos personales a un LLM: no aplica (B7 justamente evita el LLM)

## Archivos a tocar

### Backend
- [ ] `backend/src/cheatsheet/contexts/conversational/application/agente.py` (B5, B7)
- [ ] `backend/src/cheatsheet/contexts/conversational/domain/pedido_de_persona.py` (nuevo, B7)
- [ ] `backend/tests/contexts/conversational/application/test_agente.py` (B5, B7)
- [ ] `backend/tests/contexts/conversational/domain/test_pedido_de_persona.py` (nuevo, B7)
- [ ] `backend/tests/integracion/test_api_conversacional.py` (B5)

### Frontend
- [ ] `frontend/src/features/conversational/components/__tests__/pantallas.test.tsx` (B5)

### Docs
- [ ] `docs/aidlc/units.md` (fila de la unidad)
- [ ] `docs/aidlc/units/ajustes-menores-del-agente.md` (este plan)

## Casos de prueba

Modo: **test primero** (`CLAUDE.md` §5: todo bug arreglado empieza con un test que lo reproduce). Cada
RED falla contra el código actual **por el motivo correcto** y su commit va antes que el del fix.
Ningún test toca la red: intérprete, mensajería y embeddings son los dobles de
`tests/contexts/conversational/application/dobles.py` (`InterpreteProgramado`,
`MensajeriaEnMemoria`, `RepositorioMensajeEnMemoria`), cableados por `Escena` de `test_agente.py`.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | **RED B5** `test_el_mensaje_entrante_guarda_la_intencion_interpretada`: `Escena(lectura=leyendo(TURNO))`, procesar «quiero un turno» → el único entrante de `escena.mensajes` tiene `intencion is Intencion.TURNO`. **Hoy falla**: es `None` | unit (aplicación) | hecho · RED `d05970f` (`None is Intencion.TURNO` fallaba) → verde en `4cc3b9c` |
| 2 | B5: con confianza bajo el umbral (`leyendo(FAQ, 0.3)`), el entrante queda con `Intencion.DESCONOCIDA`, igual que `Respuesta.intencion` | unit (aplicación) | hecho · RED `d05970f` (`None`, esperado `DESCONOCIDA`) → verde en `4cc3b9c` |
| 3 | B5: los caminos que no interpretan dejan `intencion is None` — escalamiento abierto, transcripción pobre y pedido explícito de una persona | unit (aplicación) | hecho · verde antes y después (también cubre transcripción pobre y escalamiento abierto) |
| 4 | **RED B5 de API**: webhook firmado con «hola, cuánto sale un corte» (el `InterpreteSimulado` lo lee `FAQ` 0.9) → `GET /conversaciones/{id}` devuelve el entrante con `"intencion": "FAQ"`. **Hoy falla**: `null`. Prueba que el `guardar` llega a PostgreSQL y no sólo al objeto en memoria | integración (PostgreSQL) | escrito en `d05970f`; se saltea local (sin Docker), lo confirma el CI |
| 5 | B5 frontend: `HiloDeConversacion` con un mensaje `intencion: "TURNO"` muestra «Turno» en la línea del autor; con `null` no muestra etiqueta. **No es RED** (el componente ya está bien): fija el contrato | unit frontend (Vitest) | ok — `pantallas.test.tsx` «muestra la intención del mensaje del cliente…» verde |
| 6 | **RED B7** `test_nombrar_a_una_persona_no_es_pedirla`: procesar «soy una persona que quiere un turno» con `leyendo(TURNO)` → **no** escala, el intérprete vio el texto, no hay escalamiento abierto. **Hoy falla**: escala por subcadena | unit (aplicación) | hecho · RED `e003487` (`escalado=True` por subcadena) → verde en el commit del fix B7 |
| 7 | B7 negativos (paramétrico, dominio): «soy una persona que quiere un turno», «mi mamá es una persona mayor, ¿tienen rampa?», «el asesor me dijo que viniera el martes», «hablé con alguien ayer», «necesito asesoramiento contable», «¿cuánto sale el personal trainer?» → `False` | unit (dominio) | hecho · 6 negativos en `test_pedido_de_persona.py`, verde |
| 8 | B7 positivos (paramétrico, dominio): «quiero hablar con una persona por favor», «hablar con alguien», «pasame con un humano», «necesito un asesor», «Quiero hablar con un ASESOR!», «atención humana», «ATENCION HUMANA», «un asesor», «una persona por favor», «que me atienda una persona» → `True` | unit (dominio) | hecho · 11 positivos en `test_pedido_de_persona.py`, verde |
| 9 | B7: el test existente `test_el_pedido_explicito_de_una_persona_no_pasa_por_el_modelo` sigue verde sin cambios | unit (existente) | hecho · verde sin cambios |
| 10 | El resto de `test_agente.py` y de `tests/integracion/test_api_conversacional.py` sigue verde | unit + integración (existente) | unit hecho (suite completa verde local); integración: CI |

Los casos 1 y 6 son la evidencia local de los RED. El 4 lo confirma contra la base real; sin
Docker local se saltea y su RED lo muestra la primera corrida de CI sobre el commit del test.

## Verificaciones que no se pueden hacer acá

- Los casos 4 y 10 (integración) necesitan PostgreSQL: **el Gate 2 no se cierra sin la salida real
  del CI** en esos casos.
- Ver la etiqueta de intención en el hilo de PAN-WA-01 con un mensaje real de WhatsApp en `staging`
  (donde se observó B5) queda en `docs/aidlc/TODO.md` (sandbox).

## Preguntas para el Gate 1

1. **¿Una unidad o tres?** → **Recomendación: una unidad, una rama, un PR**, con un commit RED y un
   commit fix por bug (cuatro commits). Los tres son Menores, del mismo contexto, sin migración, y
   suman pocas decenas de líneas de código; tres PRs triplican la revisión y el CI para nada. Si uno
   se traba en la revisión, se puede revertir su par de
   commits sin tocar los otros dos.
2. **B5 — bajo el umbral de confianza, ¿qué intención se guarda en el mensaje?** (a) **`DESCONOCIDA`**,
   igual que `Respuesta` y que lo que el agente hizo (ofrecer un asesor); (b) la que el modelo dijo
   aunque no alcance. → **Recomendación: (a)**. La lectura cruda ya queda en la auditoría
   (`interpretar_mensaje:<intencion>`); el hilo tiene que contar lo que el agente decidió.
3. **B7 — ¿alcanza el vocabulario propuesto** (destinatarios: persona, humano/a, asesor/a,
   operador/a, «atención humana»; verbos: quiero, necesito, prefiero, hablar, comunicarme, pasame,
   derivame, que me atienda)? → **Recomendación: sí**, como lista cerrada en el módulo nuevo; agregar
   una palabra después es una línea más un caso de test.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-04 | aprobado con cambios: B6 pasa a la unidad usos-de-faq-por-periodo |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- Q1: una unidad, un PR; B6 sale y pasa a la unidad `usos-de-faq-por-periodo` (contador por período
  con tabla de eventos, habilitado por el ADR-0012).
- Q3 (B5): bajo el umbral de confianza la intención guardada es `Intencion.DESCONOCIDA` (opción a).
- Q4 (B7): vocabulario cerrado propuesto, con límites de palabra: aprobado.
