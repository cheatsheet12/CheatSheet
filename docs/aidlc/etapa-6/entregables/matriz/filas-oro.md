---
entregable: matriz
parte: filas-oro
responsable: Luciano Oro
estado: borrador
hu: [HU-E8-01, HU-E8-02, HU-E8-03, HU-E8-04, HU-E8-05, HS-T2, HS-T7, HU-E9-01, HU-E9-02, HU-E9-04, HU-E11-02]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - docs/aidlc/inputs/prototipos.md
  - docs/aidlc/inputs/der.md
  - docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md
  - docs/aidlc/TODO.md
  - docs/aidlc/units.md
  - docs/adr/0011-outbound-whatsapp-channel-via-composition-root.md
  - docs/adr/0012-faq-uses-per-month-and-share.md
  - render.yaml
  - backend/src/cheatsheet/contexts/conversational/
  - backend/src/cheatsheet/contexts/business_config/application/plantillas.py
  - backend/src/cheatsheet/contexts/scheduling/application/
  - backend/src/cheatsheet/contexts/scheduling/infrastructure/avisos.py
  - backend/src/cheatsheet/api/conversacional.py
  - backend/src/cheatsheet/api/mensajeria.py
  - frontend/src/features/conversational/
  - frontend/src/features/business_config/
observaciones: >
  Estado al 13/10/2026 sobre develop (commit 886b466). Ningún ítem figura como Probado: la prueba
  manual de este módulo en staging se hizo entre el 03/10 y el 05/10/2026 (PRU-05 se re-ejecutó el
  05/10, después del PR #81) y se repite el 13/10/2026 sobre el código actual. Si esa corrida pasa
  sin bugs críticos ni mayores abiertos, pasan a Probado con fecha 13/10/2026 estos siete ítems:
  HU-E8-01, HU-E8-02, HS-T2, HU-E9-01, HU-E9-02, HU-E9-04 y, solo si se acepta como fuera de alcance
  el criterio del motivo «pago no verificado», HU-E8-05. No pueden pasar a Probado con esa corrida
  HU-E8-03 y HS-T7 (embeddings y transcripción sin adaptador real), HU-E8-04 (la confirmación de un
  cobro pagado al cliente no existe y los avisos y recordatorios solo corren con el canal simulado) ni
  HU-E11-02 (en staging el doble aprueba toda plantilla, así que el criterio de la plantilla no
  aprobada no puede ejercitarse). Las fechas de esos cuatro ítems, 31/10/2026, son el cierre de la
  Etapa 6 de reparto.md y no un compromiso de unidad: el responsable las confirma.
  Integración real: staging corre WHATSAPP_ADAPTADOR=simulado (render.yaml), por lo que mensajes,
  avisos, recordatorios y revisión de plantillas ante Meta no se ejercitaron contra el proveedor
  (no existe aún la cuenta de Meta con número de prueba, TODO.md §22.30). Los adaptadores reales de WhatsApp, de
  plantillas de Meta y del intérprete (Anthropic) existen en el código; los de embeddings y de
  transcripción no existen y el ADR del proveedor no se publicó en develop (los ADR llegan hasta
  el 0014 y ninguno lo trata). El render.yaml no define LLM_ADAPTADOR: si staging usa el
  intérprete real depende de lo cargado en el panel de Render, y la extracción de pedidos de turno
  con el modelo real no se verificó (TODO.md §22.13).
  Bugs corregidos desde la corrida del 05/10, verificados en el historial de git: PR #84 (horario de
  atención y política fuera de horario, issue #71, HS-T2 RN-04), PR #87 (la frase que introduce la
  oferta de horarios repetía el encabezado, HU-E8-01), PR #126 (un identificador de mensaje
  entrante de más de 160 caracteres desbordaba su columna y devolvía 500, HS-T2) y PR #135 (la
  falta de permiso por rol responde 403 en Atención y Escalamiento, FAQ y plantillas). Los PR #99
  (usos de FAQ por mes), #104 (canal real de WhatsApp), #109 (plantillas ante Meta), #114, #115 y
  #122 (estados de entrega, reintentos y avisos de turno) y #123, #124 y #125 (recordatorio de
  turno) son funcionalidad nueva y no correcciones; su verificación en staging sigue pendiente.
  Riesgo para la corrida de hoy, no confirmado: el esquema ESQUEMA_DE_LECTURA del intérprete
  (conversational/infrastructure/interprete.py) declara minimum y maximum sobre números, el mismo
  tipo de cota que la API de Anthropic rechazó con 400 en el mapeo de planillas y que el PR #164
  quitó. Si staging usa el intérprete real y la API rechaza el esquema, el agente devuelve confianza
  cero y escala todo mensaje.
  Diferencias entre el código y las HU: HU-E8-01 y HU-E8-02 tienen la reserva y la cancelación
  hechas, pero un turno con seña no se cancela por WhatsApp: se deriva a un asesor (pendiente 6 del
  épico 8, falta la política de turnos tipada). HU-E8-04 RN-01 pide confirmar por WhatsApp una
  reserva o un pago: la reserva se confirma, el cobro pagado no. HU-E8-05 RN-05 y su cuarto criterio
  (motivo «pago no verificado») dependen de HU-E6-08 y HU-E8-06, que no están implementadas y no figuran
  entre los 68 ítems de la matriz. HS-T2 y HU-E8-01 piden el agente activo, pero el interruptor
  «Agente activo» no existe (pendiente 23): la política fuera de horario lo reemplaza. En HS-T2 la
  intención PAGO no tiene flujo automático: el agente ofrece un asesor. En HU-E11-02 una
  plantilla no aprobada nunca se usa, pero el mensaje sale igual con el texto de fábrica de cada
  notificación. En HU-E9-02 los botones del panel desaparecen al cerrar el escalamiento, por lo
  que el rechazo del cierre repetido solo se ejerce llamando a la API. HU-E9-04 se asigna a
  Atención y Escalamiento y HU-E11-02 a Configuración del Negocio, según reparto.md §2.
---

## Filas — Luciano Oro

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |
|---|---|---|---|---|---|---|---|---|
| Canal Conversacional (WhatsApp) | Reservar un turno conversando por WhatsApp | HU-E8-01 | Cliente final | Conversacion, Mensaje, Turno | Canal WhatsApp | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Canal Conversacional (WhatsApp) | Cancelar un turno conversando por WhatsApp | HU-E8-02 | Cliente final | Conversacion, Mensaje, Turno | Canal WhatsApp | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Canal Conversacional (WhatsApp) | Consultar una FAQ a través del agente | HU-E8-03 | Cliente final | Conversacion, Mensaje, FAQ | Canal WhatsApp | En desarrollo | Sin implementar | 31/10/2026 |
| Canal Conversacional (WhatsApp) | Recibir confirmaciones y recordatorios | HU-E8-04 | Cliente final | Mensaje, Turno, Cobro, Recordatorio | Canal WhatsApp | En desarrollo | Simulada · pendiente de validar | 31/10/2026 |
| Canal Conversacional (WhatsApp) | Ser derivado a un asesor humano | HU-E8-05 | Cliente final | Conversacion, Escalamiento | Canal WhatsApp | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Canal Conversacional (WhatsApp) | Procesar un mensaje entrante recibido desde WhatsApp | HS-T2 | Sistema | Mensaje, Conversacion, Escalamiento | Bitácora | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Canal Conversacional (WhatsApp) | Transcribir las notas de voz entrantes de WhatsApp | HS-T7 | Sistema | Mensaje | Bitácora | En desarrollo | Sin implementar | 31/10/2026 |
| Atención y Escalamiento | Atender una conversación escalada | HU-E9-01 | Operador, Administrador | Escalamiento, Conversacion, Mensaje | PAN-WA-01 | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Atención y Escalamiento | Resolver y cerrar un escalamiento | HU-E9-02 | Operador, Administrador | Escalamiento | PAN-WA-01 | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Atención y Escalamiento | Administrar el repositorio de preguntas frecuentes | HU-E9-04 | Administrador | FAQ, UsoDeFAQ | PAN-WA-02 | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Configuración del Negocio | Administrar las plantillas de notificación | HU-E11-02 | Administrador | PlantillaDeNotificacion | PAN-CFG-NOT | Codificado | Simulada · pendiente de validar | 31/10/2026 |

### Qué respalda cada estado

| HU | Evidencia en el código de develop y lo que falta |
|---|---|
| HU-E8-01 | Desde el PR #81 el agente guarda la oferta en el diálogo de la conversación, lee la elección del cliente de forma determinista, reserva por los casos de uso de Agenda y Recursos y confirma por el mismo canal; el PR #87 corrigió el encabezado de la oferta. Los horarios pasados se rechazan al ofrecer y al confirmar. Falta verificar en staging la extracción del modelo real (`TODO.md` §22.13) y que el cliente reciba un solo mensaje con el canal real (§22.15) |
| HU-E8-02 | Desde el PR #81 el agente busca los turnos del cliente por su número, pide cuál si hay varios y confirmación, y cancela con un «sí» explícito. Un turno con seña se deriva a un asesor con el motivo «Cancelación de turno con seña» |
| HU-E8-03 | `EmbeddingsSimulados` (`conversational/infrastructure/canal.py`) vectoriza por hash: el agente solo reconoce una pregunta frecuente cuando el texto coincide, no por significado, lo que incumple RN-02. Sin coincidencia ofrece un asesor y cada respuesta enviada suma un uso (PR #99). Cierra la unidad de embeddings y transcripción, que no está en develop |
| HU-E8-04 | La confirmación de una reserva hecha desde el panel y los avisos de cancelación y reprogramación salen por el canal de WhatsApp y quedan en el hilo (PR #104, #122); el recordatorio de turno se barre cada 15 minutos con reintentos acotados (PR #123, #124, #125); el recordatorio de cobro usa el mismo canal (PR #104); los estados de entrega se registran con el motivo de falla (PR #114, #115) y la respuesta del cliente retoma el hilo. No existe ningún mensaje al cliente cuando se confirma el cobro de un cliente (RN-01) |
| HU-E8-05 | El agente deriva cuando la confianza es baja, tras varios intentos fallidos y ante el pedido explícito del cliente; registra el motivo, avisa al cliente y deja el hilo al asesor con su contexto. No existe el motivo «pago no verificado» (RN-05) |
| HS-T2 | El webhook registra el mensaje con su identificador (idempotente), interpreta la intención, encamina o escala, aplica la política fuera de horario (PR #84) y publica el evento con iniciador IA. El PR #126 descarta en el borde el identificador de más de 160 caracteres. Falta verificar la política fuera de horario en staging (`TODO.md` §22.17) y la entrega real por Meta (§22.39) |
| HS-T7 | `TranscriptorSimulado` devuelve un texto fijo con calidad alta; el camino completo existe (se transcribe, se interpreta el texto, el audio no se guarda y una calidad menor a 0,5 escala) pero no hay adaptador real |
| HU-E9-01 | Tomar el escalamiento, responder como Operador (sale por el canal de WhatsApp), ver el contexto y reclasificar al devolver funcionan en PAN-WA-01; el PR #135 hizo que el rol sin permiso reciba 403 |
| HU-E9-02 | Devolver al agente o dar por finalizada cierra el escalamiento y queda en la bitácora; un cierre repetido se rechaza con la frase de la HU. Al devolver sin clasificación manual el agente reclasifica con el intérprete, que es el único servicio externo que usa |
| HU-E9-04 | Alta, edición, baja con confirmación y los contadores «Este mes», «Mes anterior» y «Total» con la participación antes y después de la edición (ADR-0012, PR #99). Un uso solo cuenta si el mensaje salió; las respuestas nuevas se buscan por texto idéntico mientras los embeddings sean simulados |
| HU-E11-02 | Las plantillas se listan con su estado en Meta, se envían a revisión al editarlas, la variable no válida se rechaza con la frase de la HU y el estado solo lo escribe lo que Meta informa (PR #109). Los avisos de cobro y de turno usan la plantilla aprobada y caen al texto de fábrica si no hay una. En staging el doble aprueba toda plantilla, por lo que la revisión real de Meta no se ejercitó (`TODO.md` §22.36 a §22.50) |
