---
entregable: pruebas
parte: PRU-04
responsable: Emanuel Gomez
estado: borrador
hu: [HU-E7-06, HU-E7-01]
fuentes:
  - backend/src/cheatsheet/contexts/scheduling/application/turnos.py
  - backend/src/cheatsheet/contexts/scheduling/infrastructure/avisos.py
  - backend/src/cheatsheet/api/agenda.py
  - frontend/src/app/(panel)/agenda/nuevo/page.tsx
  - frontend/src/features/scheduling/components/NuevoTurno.tsx
  - frontend/src/features/scheduling/components/DetalleDeTurno.tsx
  - frontend/src/features/master_data/components/FilaDeCliente.tsx
observaciones: >
  Borrador sin ejecutar. El recurso «Consultorio 1» no figura en los datos ficticios de reglas.md
  §6, que no definen recursos; se usa ese nombre genérico. La duración estándar de 45 minutos de
  «Consulta general» se carga como preparación, porque §6 no fija duraciones. El panel no tiene un
  selector de cliente en Nuevo turno: el cliente se elige antes, desde la acción «Agendar» de su
  fila en Clientes. La confirmación por WhatsApp (HU-E7-06 RN-04) sale por el adaptador real solo
  si la empresa tiene WhatsApp conectado; HU-E2-03 todavía no se validó en staging, así que el
  paso 5 puede quedar sin poder verificarse en el teléfono del cliente.
---

## PRU-04 — Crear un turno manualmente desde el panel

**Tipo:** Funcional

| Campo | Contenido |
|---|---|
| ID de prueba | PRU-04 |
| CU/HU referenciado | HU-E7-06 — Crear un turno manualmente desde el panel; HU-E7-01 — Ver la agenda de turnos desde el panel |
| Pantalla / Reporte | PAN-AGE-02, PAN-AGE-01 |
| Datos de entrada | Empresa Estudio Ejemplo SRL, CUIT `30-00000005-8`, Responsable Inscripto. Usuario `admin.gomez@estudio-ejemplo.test` con rol Administrador. Cliente Ana Prueba, CUIT `20-22222222-3`, WhatsApp `+54 9 11 0000-0000`. Servicio agendable «Consulta general», $ 15.000,00, IVA 21 %, duración estándar 45 minutos. Servicio agendable «Sesión de seguimiento», $ 9.500,00, IVA 21 %, **no** asociado al recurso. Recurso «Consultorio 1», tipo espacio, activo, con «Consulta general» asociada, disponibilidad de lunes a viernes de 09:00 a 18:00, duración de slot 15 minutos, sin intervalo entre turnos. Fecha del turno: el día hábil siguiente al de la ejecución, 10:00 |
| Pasos | 1. Ingresar a staging con `admin.gomez@estudio-ejemplo.test`. <br> 2. Ingresar a Clientes y, en la fila de Ana Prueba, elegir «Agendar». <br> 3. En Nuevo turno (PAN-AGE-02), elegir el recurso «Consultorio 1» y abrir el selector «Servicio»; verificar que ofrece «Consulta general — 45 min» y no ofrece «Sesión de seguimiento». <br> 4. Elegir «Consulta general» y la fecha del turno; verificar que los horarios ofrecidos avanzan de a 15 minutos. <br> 5. Elegir el horario 10:00, hacer clic en «Reservar turno» y abrir el turno creado; verificar su estado, su origen y su franja de 10:00 a 10:45. <br> 6. Ingresar a la Agenda (PAN-AGE-01), filtrar por la fecha del turno y verificar que el turno aparece. <br> 7. Volver a Nuevo turno desde la fila de Ana Prueba, elegir el mismo recurso, servicio y fecha, y verificar que el horario 10:00 figura tachado como tomado. <br> 8. En Nuevo turno, elegir la fecha de hoy y un horario anterior a la hora actual, si el selector lo ofrece, y hacer clic en «Reservar turno». <br> 9. Ingresar a Log de operaciones (PAN-LOG-01) y verificar el registro de la reserva con el usuario que la ejecutó. |
| Resultado esperado | HU-E7-06: «Creo un turno en una franja disponible — El turno queda Reservado con canal de reserva PANEL y aparece en la agenda»; «Selecciono un servicio no asociado al recurso — El sistema no ofrece ese servicio para ese recurso»; «Creo el turno para un cliente con WhatsApp registrado — El sistema crea el turno y envía la confirmación al cliente por WhatsApp»; «Creo un turno para hoy en una hora anterior a la actual — El sistema muestra “No se puede agendar un turno en un horario que ya pasó.” y no lo crea»; «Elijo un servicio agendable de 45 minutos — El turno se crea con duración de 45 minutos y los inicios ofrecidos siguen el paso del slot del recurso»; «Intento crear un turno en una franja ocupada — El sistema muestra “El horario seleccionado no está disponible.” y no crea el turno». HU-E7-06 RN-05: la creación queda en la bitácora con el usuario que la ejecutó. HU-E7-01: «Abro la agenda — Veo los turnos del recurso y rango seleccionados con su estado». Por lo tanto: el turno queda Reservado, con origen «Cargado desde el panel», de 10:00 a 10:45, visible en la agenda y en la bitácora; el horario tomado deja de ofrecerse como libre; y una hora ya pasada no crea turno |
| Resultado obtenido | PENDIENTE DE EJECUCIÓN |
| Estado | PENDIENTE DE EJECUCIÓN |
| Evidencia | PENDIENTE DE EJECUCIÓN |

![Figura PRU-04-1 — Nuevo turno con el recurso, el servicio de 45 minutos y la grilla de horarios](capturas/PRU-04_1.png)

![Figura PRU-04-2 — El detalle del turno creado: Reservado y cargado desde el panel](capturas/PRU-04_2.png)

![Figura PRU-04-3 — La agenda del día con el turno nuevo](capturas/PRU-04_3.png)
