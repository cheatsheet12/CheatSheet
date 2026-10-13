---
entregable: pruebas
parte: PRU-05
responsable: Luciano Oro
estado: borrador
hu: [HU-E8-01, HU-E7-01, HU-E12-01]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - docs/aidlc/inputs/prototipos.md
  - docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md
  - docs/staging-deployment.md
  - render.yaml
  - backend/src/cheatsheet/api/routers/whatsapp.py
  - backend/src/cheatsheet/api/conversacional.py
  - backend/src/cheatsheet/api/mensajeria.py
  - backend/src/cheatsheet/contexts/conversational/application/agente.py
  - backend/src/cheatsheet/contexts/conversational/application/reserva_por_whatsapp.py
  - backend/src/cheatsheet/contexts/conversational/domain/textos_de_turnos.py
  - backend/src/cheatsheet/contexts/conversational/infrastructure/interprete.py
  - backend/src/cheatsheet/contexts/scheduling/application/turnos.py
  - backend/src/cheatsheet/contexts/observability/infrastructure/repository.py
  - frontend/src/app/(panel)/navegacion-lateral.tsx
  - frontend/src/app/(panel)/agenda/page.tsx
  - frontend/src/features/scheduling/components/AgendaDelDia.tsx
  - frontend/src/features/scheduling/components/BarraDeAgenda.tsx
  - frontend/src/features/scheduling/components/DetalleDeTurno.tsx
  - frontend/src/features/observability/components/Bitacora.tsx
  - frontend/src/features/conversational/components/BandejaDeConversaciones.tsx
  - frontend/src/features/conversational/components/HiloDeConversacion.tsx
  - frontend/src/features/conversational/components/LineaDeTiempo.tsx
observaciones: >
  Historia de la prueba. Primera ejecución (03/10/2026) Fallida: el agente ofrecía horarios pero no
  recordaba cuáles, y «Prefiero el primero» no creaba ningún turno (issue #68, corregido en el PR
  #81). Re-ejecutada el 05/10/2026 y aprobada, sobre otra empresa de prueba (CUIT 30-00000000-7, ya
  tomado en staging y excluido por reglas.md §6). Esta versión se ejecuta de nuevo sobre Estudio
  Ejemplo SRL con CUIT 30-00000006-6 y con el código vigente en develop: no hereda ningún resultado
  de esas corridas. El hallazgo cosmético de la corrida del 05/10 (encabezado repetido en la oferta
  de alternativas) ya está corregido en textos_de_turnos.py.

  Diferencias entre las HU y el código. (1) HU-E7-01 RN-01 fija el día en curso como vista por
  defecto; la agenda abre en la vista Mes y el día se alcanza con «Día». (2) El canal de origen del
  turno solo se muestra en el detalle (PAN-AGE-02, campo «Origen», valor «Agente»); la lista y los
  calendarios no lo muestran, y las vistas Día, Semana y Mes indican el estado solo con color y con
  texto accesible. (3) La bandeja de PAN-WA-01 titula todos los hilos «Conversación con el agente»
  y no muestra el nombre del cliente; abre filtrada por «Esperan a un asesor» y hay que pulsar
  «Todas». (4) La bitácora rotula los módulos «Conversaciones» y «Agenda», no «Canal Conversacional
  (WhatsApp)» ni «Agenda y Recursos». (5) La operación reservar_turno queda con iniciador
  «Sistema»: solo interpretar_mensaje y reservar_turno_por_whatsapp llevan «Agente IA». (6)
  HU-E12-01 RN-03 pide buscar por cliente o archivo; «Buscar» filtra por operación y entidad
  afectada. (7) HU-E8-01 exige el agente activo: el código no tiene un interruptor, y el horario de
  atención, si no se configura, es siempre abierto. (8) Los textos del agente difieren de los
  ejemplos de la HU (tuteo, listado numerado, «Contestame con el número o con la hora»); la HU los
  da «por ejemplo». (9) El código de la operación de interpretación queda en mayúsculas
  (interpretar_mensaje:TURNO), no en minúsculas como en el paso 7.

  Entorno de staging. Corrida del 13/10/2026 con la API y el worker desplegados en el commit
  946fcde de develop. render.yaml fija WHATSAPP_ADAPTADOR=simulado: la confirmación queda
  registrada en el hilo con estado «Enviado» pero no llega a un teléfono real, y por eso la
  integración con Meta no se verifica en esta prueba. LLM_ADAPTADOR vale anthropic en staging: el
  intérprete es el modelo real. Antes de la corrida, el esquema de salida del intérprete usaba
  restricciones que la API de Anthropic rechaza con 400 y cada mensaje habría escalado; se
  corrigió en el PR #213 y se desplegó antes de ejecutar. El correo de staging sale por Amazon
  SES en modo sandbox y rechaza destinatarios no verificados: la invitación del Operador no pudo
  enviarse y el paso 8 no se ejecutó.
---

## PRU-05 — Una reserva hecha por WhatsApp aparece en la agenda y en la bitácora

**Tipo:** Integración

| Campo | Contenido |
|---|---|
| ID de prueba | PRU-05 |
| CU/HU referenciado | HU-E8-01 — Reservar un turno conversando por WhatsApp; HU-E7-01 — Ver la agenda de turnos desde el panel; HU-E12-01 — Ver la bitácora de operaciones |
| Pantalla / Reporte | PAN-AGE-01 (Agenda), PAN-AGE-02 (Detalle de turno), PAN-LOG-01 (Log de operaciones); el hilo de la conversación se consulta en PAN-WA-01 |
| Datos de entrada | Empresa Estudio Ejemplo SRL, CUIT `30-00000006-6`, Responsable Inscripto, en staging. Administrador `admin.oro@estudio-ejemplo.test` y Operador `operador.oro@estudio-ejemplo.test`. Cliente Ana Prueba, CUIT `20-22222222-3`, con el WhatsApp `+54 9 11 0000-0000` registrado como contacto (el sistema lo guarda como `5491100000000`). Servicio Consulta general, $ 15.000,00 sin IVA, IVA 21 %, marcado «Se puede reservar por agenda», con duración estándar de 30 minutos. Un recurso activo con horario semanal de lunes a viernes de 09:00 a 18:00, duración del slot de 30 minutos, intervalo entre turnos sin modificar, y el servicio Consulta general asociado. Horario de atención sin configurar. Mensaje 1: «Quiero un turno para mañana». Mensaje 2: «Prefiero el primero». Ambos se envían como mensaje entrante simulado: un pedido `POST` a `/webhooks/whatsapp/{empresa_id}` de la API, con un cuerpo JSON en el formato de notificación de Meta (mensaje de tipo texto, remitente `5491100000000`, identificador único) y la cabecera `X-Hub-Signature-256` con el HMAC-SHA256 del cuerpo exacto, calculado con el secreto `WHATSAPP_WEBHOOK_SECRET` del entorno de staging |
| Pasos | 1. Ingresar al panel de staging con `admin.oro@estudio-ejemplo.test` (Administrador) y abrir «Operaciones › Agenda». Pulsar «Día», avanzar con «Período siguiente» (flecha derecha) hasta el día siguiente y verificar que no hay turnos de Ana Prueba y que se muestra «No hay turnos para el período seleccionado.». <br> 2. Enviar el mensaje 1 como mensaje entrante simulado firmado desde el número de Ana Prueba y verificar que la API responde 200. <br> 3. Abrir «Operaciones › Agente WhatsApp», pulsar «Todas» y abrir la conversación más reciente (su título es «Conversación con el agente»: la lista no muestra el nombre del cliente). Recargar la página si el hilo no muestra el mensaje. Verificar que el mensaje del Cliente lleva la marca «Turno» y que el Agente respondió con un listado numerado de horarios del día siguiente, con estado de entrega «Enviado». Capturar la pantalla como `PRU-05_1.png`. <br> 4. Dentro de los 30 minutos posteriores al paso 2, enviar el mensaje 2 como mensaje entrante simulado firmado desde el mismo número y verificar que la API responde 200. <br> 5. Recargar el hilo y verificar que el mensaje «Prefiero el primero» lleva la marca «Turno» y que el Agente confirmó con «Listo, tu turno quedó reservado para el …», con el día y la hora del primer horario ofrecido. Capturar la pantalla como `PRU-05_2.png`. <br> 6. Abrir «Operaciones › Agenda», pulsar «Día» y avanzar con «Período siguiente» (flecha derecha) hasta el día siguiente. Verificar que aparece un bloque de Ana Prueba con el servicio Consulta general en la hora confirmada. Capturar la pantalla como `PRU-05_3.png`. Abrir el bloque y verificar en el detalle (PAN-AGE-02) el estado «Reservado», el servicio Consulta general, el recurso y el origen «Agente». <br> 7. Abrir «Análisis › Log de operaciones», escribir `turno` en «Buscar» y verificar tres registros, todos en estado «Completado»: «Interpretar mensaje:turno» (módulo Conversaciones, iniciado por Agente IA), «Reservar turno» (módulo Agenda, iniciado por Sistema) y «Reservar turno por whatsapp» (módulo Conversaciones, iniciado por Agente IA). Capturar la pantalla como `PRU-05_4.png`. Elegir «Agente IA» en «Iniciador» y verificar que solo quedan los dos registros del agente. <br> 8. Abrir el menú de la cuenta del encabezado, pulsar «Cerrar sesión», ingresar con `operador.oro@estudio-ejemplo.test` (Operador) y repetir los pasos 6 y 7 sin capturar. Verificar que ve el mismo turno y los mismos registros. |
| Resultado esperado | HU-E8-01: «Escribo que quiero un turno y para cuándo» → el agente interpreta la intención y ofrece horarios disponibles reales; «Elijo uno de los horarios ofrecidos» → el agente confirma el turno y lo registra (RN-04: el cliente recibe la confirmación por el mismo canal). HU-E7-01: «Abro la agenda» → se ven los turnos del recurso y del rango seleccionados con su estado. HU-E12-01: «Ingreso al Log de Operaciones» → se ve el listado con timestamp, módulo, operación, entidad afectada, iniciador y estado; «Filtro por iniciador IA» → se ven solo las operaciones ejecutadas automáticamente por el agente. Por lo tanto: el hilo muestra los dos mensajes del cliente clasificados como «Turno» y las dos respuestas del agente; la agenda del día siguiente muestra un turno de Ana Prueba, con Consulta general, en estado «Reservado» y origen «Agente»; la bitácora registra la interpretación del mensaje y la creación del turno, y el Operador ve lo mismo que el Administrador |
| Resultado obtenido | Ejecutada el 13/10/2026 en staging (commit 946fcde), con el intérprete real de Anthropic. Antes de la corrida se envió el mensaje 1 desde el número de otro cliente de prueba (Bruno Ficticio) para comprobar el secreto y la dirección de la API; recibió la misma oferta y no se le respondió. <br> 1. La agenda del miércoles 14/10 mostraba «No hay turnos para el período seleccionado.». <br> 2. Mensaje 1 enviado a las 10:30: la API respondió 200. <br> 3. El hilo mostró «Quiero un turno para mañana» con la marca «Turno» y la respuesta del Agente «Tengo estos horarios disponibles:» con 1) miércoles 14/10 a las 09:00, 2) 11:00, 3) 13:30 y 4) 15:30, y «¿Cuál preferís? Contestame con el número o con la hora.», con estado «Enviado» (Figura PRU-05-1). <br> 4. Mensaje 2 enviado a las 10:34, cuatro minutos después: la API respondió 200. <br> 5. «Prefiero el primero» quedó con la marca «Turno» y el Agente confirmó «Listo, tu turno quedó reservado para el miércoles 14/10 a las 09:00.», con estado «Enviado» (Figura PRU-05-2). <br> 6. La vista Día del 14/10 mostró «1 turno»: el bloque 09:00–09:30 de Ana Prueba con Consulta general, en el color de «Reservado» (Figura PRU-05-3). El detalle mostró estado «Reservado», servicio Consulta general, recurso Consultorio 1 y origen «Agente». <br> 7. Con «Buscar» = `turno`, la bitácora mostró 4 registros, todos «Completado», y 3 del agente de IA: «Reservar turno» (Agenda, Sistema, 10:34:59), «Reservar turno por whatsapp» (Conversaciones, Agente IA, 10:34:57), ambos sobre el turno 330bbb63…; «Interpretar mensaje:TURNO» (Conversaciones, Agente IA, 10:30:58) sobre la conversación de Ana; y la misma interpretación a las 10:27:26 sobre la conversación del envío de comprobación (Figura PRU-05-4). Con «Agente IA» en «Iniciador» quedaron solo los tres registros del agente. <br> 8. No ejecutado: la invitación del Operador no se pudo enviar porque el correo de staging (Amazon SES en sandbox) rechaza destinatarios no verificados. Queda pendiente verificar que el Operador ve el mismo turno y los mismos registros |
| Estado | Aprobada (pasos 1 a 7; el paso 8 no se ejecutó, ver «Resultado obtenido») |
| Evidencia | Figuras PRU-05-1 a PRU-05-4 |

![Figura PRU-05-1 — El hilo muestra el mensaje del cliente clasificado como Turno y la oferta de horarios del agente](capturas/PRU-05_1.png)

![Figura PRU-05-2 — El hilo muestra la elección del cliente y la confirmación del turno por el agente](capturas/PRU-05_2.png)

![Figura PRU-05-3 — La agenda del día siguiente muestra el turno de Ana Prueba creado por WhatsApp](capturas/PRU-05_3.png)

![Figura PRU-05-4 — El Log de operaciones registra la interpretación del mensaje y la creación del turno](capturas/PRU-05_4.png)

### Módulos involucrados

- Canal Conversacional (WhatsApp): recibe el mensaje entrante firmado, interpreta la intención, ofrece los horarios y confirma el turno por el mismo canal.
- Datos Maestros: identifica a Ana Prueba por su número de WhatsApp.
- Agenda y Recursos: calcula los horarios disponibles, crea el turno con origen «Agente» y lo muestra en la agenda.
- Auditoría y Bitácora: registra la interpretación del mensaje, la creación del turno y el iniciador de cada operación.
