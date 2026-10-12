---
entregable: matriz
parte: filas-gomez
responsable: Emanuel Gomez
estado: borrador
hu: [HU-E7-01, HU-E7-02, HU-E7-03, HU-E7-04, HU-E7-05, HU-E7-06, HU-E12-01, HU-E12-02, HS-T5, HS-T6, HU-E11-03, HU-E9-03]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - docs/aidlc/inputs/der.md
  - docs/aidlc/epicas/07-agenda-y-recursos/pendientes.md
  - docs/aidlc/epicas/10-panel-de-auditoria-y-notificaciones/pendientes.md
  - backend/src/cheatsheet/contexts/scheduling/
  - backend/src/cheatsheet/contexts/observability/
  - frontend/src/features/scheduling/
  - frontend/src/features/observability/
observaciones: >
  Prueba manual en staging del 12/10/2026 sobre Estudio Ejemplo SRL (30-00000005-8) con los tres
  roles. Ningún bug crítico. Bugs mayores encontrados, pendientes de issue y de corrección: los
  errores de los modales de recursos y de reprogramación aparecen detrás del modal (mismo defecto
  que #74); el panel no permite cargar una excepción de horario especial; el detalle del turno no
  muestra el cliente; el calendario del filtro de fechas de la agenda se abre detrás de las
  tarjetas; las operaciones rechazadas de Agenda no llegan a la bitácora con resultado error; el
  detalle de una operación no registra duración ni datos de entrada y salida. Siguen abiertos #85
  y #86. HU-E7-02 y HU-E7-06 quedan En desarrollo porque el aviso al cliente exige el canal real de
  WhatsApp, que cierra la unidad de Luciano (reparto.md §2). No ejecutable en esta empresa: avisos
  por WhatsApp (no conectado), detalle fiscal con CAE (ARCA no conectado), filtro por iniciador IA
  (sin operaciones del agente), notificaciones (no se generó ninguna) y HS-T6 (sin forma de
  provocar una tarea agotada desde el panel).
---

## Filas — Emanuel Gomez

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |
|---|---|---|---|---|---|---|---|---|
| Agenda y Recursos | Ver la agenda de turnos desde el panel | HU-E7-01 | Administrador, Operador, Solo Lectura | Turno | PAN-AGE-01 | Codificado | No aplica | 24/10/2026 |
| Agenda y Recursos | Cancelar o reprogramar un turno desde el panel | HU-E7-02 | Administrador, Operador | Turno | PAN-AGE-02 | En desarrollo | Simulada · pendiente de validar | 24/10/2026 |
| Agenda y Recursos | Registrar la asistencia o inasistencia a un turno | HU-E7-03 | Administrador, Operador | Turno | PAN-AGE-02 | Probado | No aplica | 12/10/2026 |
| Agenda y Recursos | Definir la disponibilidad de un recurso reservable | HU-E7-04 | Administrador | RecursoReservable, PatronDeDisponibilidad | PAN-AGE-03 | Codificado | No aplica | 24/10/2026 |
| Agenda y Recursos | Registrar excepciones de disponibilidad | HU-E7-05 | Administrador | ExcepcionDeDisponibilidad | PAN-AGE-03 | Codificado | No aplica | 24/10/2026 |
| Agenda y Recursos | Crear un turno manualmente desde el panel | HU-E7-06 | Administrador, Operador | Turno | PAN-AGE-02 | En desarrollo | Simulada · pendiente de validar | 24/10/2026 |
| Auditoría y Bitácora | Ver la bitácora de operaciones | HU-E12-01 | Administrador, Operador | RegistroDeAuditoria | PAN-LOG-01 | Codificado | No aplica | 24/10/2026 |
| Auditoría y Bitácora | Ver el detalle de una operación individual | HU-E12-02 | Administrador, Operador | RegistroDeAuditoria | PAN-LOG-02 | Codificado | No aplica | 24/10/2026 |
| Auditoría y Bitácora | Registrar automáticamente las operaciones en la auditoría | HS-T5 | Sistema | RegistroDeAuditoria | PAN-LOG-01 | Codificado | No aplica | 24/10/2026 |
| Auditoría y Bitácora | Derivar a la cola de fallos (DLQ) las tareas asíncronas agotadas | HS-T6 | Sistema | TareaAsincrona | — | Codificado | No aplica | 24/10/2026 |
| Notificaciones y Soporte | Consultar el centro de notificaciones del panel | HU-E11-03 | Administrador, Operador, Solo Lectura | Notificacion | PAN-CFG-NOT | Codificado | No aplica | 24/10/2026 |
| Notificaciones y Soporte | Abrir una solicitud de soporte a CheatSheet | HU-E9-03 | Administrador | SolicitudDeSoporte | PAN-SOP-01 | Probado | No aplica | 12/10/2026 |

### Qué respalda cada estado

| HU | Prueba manual en staging (12/10/2026) |
|---|---|
| HU-E7-01 | La agenda muestra los turnos por día, semana, mes y lista, con su estado; un turno reprogramado aparece en su franja nueva con el mismo estado; un mes sin turnos muestra «No hay turnos para el período seleccionado.»; Solo Lectura la ve sin «Nuevo turno». Bugs mayores abiertos: el calendario del filtro «Desde» se abre detrás de las tarjetas, y el filtro con una sola fecha devuelve vacío (#85). Menor: la vista por defecto es «Mes», no el día en curso |
| HU-E7-02 | Reprogramar a una franja libre conserva el estado; a una franja ocupada o, como Operador, a una hora pasada, se rechaza con el mensaje de la HU; la corrección a posteriori del Administrador mueve el turno a una franja pasada libre y rechaza la solapada; cancelar deja el turno Cancelado; todo queda en la bitácora. Bugs mayores: el error del modal de reprogramar queda detrás del modal y el detalle no muestra el cliente. Aviso por WhatsApp no ejecutado: WhatsApp no conectado |
| HU-E7-03 | Un turno futuro muestra «El turno aún no transcurrió.» y no ofrece la acción; un turno pasado ofrece «Marcar completado» y «No se presentó»; Completado habilita la facturación; las dos marcas quedan en la bitácora |
| HU-E7-04 | Recurso creado con horario de lunes a viernes, slot de 15 minutos y un servicio asociado; hora de inicio posterior a la de fin, slot de 4 y de 481 minutos e intervalo negativo se rechazan sin guardar; con intervalo de 10 minutos y un turno de 14:00 a 14:45, el siguiente inicio libre es 15:00 y 14:50 se rechaza. Bug mayor: los mensajes de error quedan detrás del modal (#74). Menor: una franja por día (#86) |
| HU-E7-05 | El día sin atención no ofrece horarios; la excepción repetida se rechaza con «Ya existe una excepción para esa fecha en este recurso.». Bug mayor: el panel no permite cargar un horario especial; por la API funciona y la disponibilidad lo respeta |
| HU-E7-06 | Ejecutada como PRU-04, Aprobada. Carga a posteriori del Administrador verificada (Completado, rechazo por solapamiento y por franja no terminada); el Operador no tiene la opción y la API se la rechaza con 403. Confirmación por WhatsApp no ejecutada: WhatsApp no conectado |
| HU-E12-01 | Listado con momento, módulo, operación, entidad, iniciador y estado; filtros por módulo, estado y rango funcionan; sin coincidencias muestra «No hay operaciones para los filtros seleccionados.»; Solo Lectura recibe 403. Bug mayor: la búsqueda por cliente no encuentra sus turnos ni busca por nombre (pendiente 1 del épico 10). Filtro por IA no ejecutado: sin operaciones del agente |
| HU-E12-02 | El detalle muestra resumen y timeline. Bug mayor: «Duración: No registrada», sin datos de entrada ni de salida, y el responsable como identificador. Detalle fiscal y detalle con error no ejecutados: sin ARCA y sin operaciones con error |
| HS-T5 | Cada operación exitosa de Agenda, Datos Maestros, Identidad y Soporte quedó registrada; PUT, PATCH y DELETE sobre un registro responden 405. Bug mayor: ninguna operación rechazada de Agenda queda registrada con resultado error |
| HS-T6 | No ejecutable desde el panel; respaldado por los tests automáticos del caso de uso |
| HU-E11-03 | Los tres roles acceden al centro y ven «No tenés notificaciones.». Marcar como leída y severidad alta no ejecutados: no se generó ninguna notificación |
| HU-E9-03 | La solicitud pide asunto, descripción y prioridad; queda Abierta y se consulta en «Mis solicitudes»; Operador y Solo Lectura no ven el formulario y la API les responde 403. Menores: sin asunto o descripción el botón se deshabilita sin mostrar el mensaje de la HU; Operador y Solo Lectura ven la solicitud del Administrador |
