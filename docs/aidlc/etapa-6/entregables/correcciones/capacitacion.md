---
entregable: correcciones
parte: capacitacion
responsable: Paula Ferreira
estado: borrador
hu: []
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - Plan_de_capacitacion.docx (Drive)
observaciones: >
  Este archivo reúne dos correcciones al documento «Plan de capacitación» de
  Drive: las inconsistencias numéricas señaladas en reparto.md (§1) y el agregado
  de un guion breve por tema solicitado por la cátedra (§2). El guion se redacta
  a partir de las historias de usuario de cada épica, para que describa lo que el
  sistema hace hoy. La asignación del módulo 10 se resuelve según HU-E9-01 y
  HU-E9-02, cuyo actor es «Operador / Administrador»: el error está en la tabla,
  no en el resumen.
---

## Correcciones a «Plan de capacitación»

### 1. Inconsistencias numéricas

#### Asignación del módulo 10

| Sección | Dice | Debe decir | Fuente |
|---|---|---|---|
| Tabla «Plan de capacitación por módulo» — fila 10 (Canal conversacional y atención), columna Rol destinatario | Operador | Administrador / Operador | HU-E9-01 y HU-E9-02 definen como actor «Operador / Administrador»: atender y cerrar un escalamiento es una acción de ambos roles. |

La tabla asigna el módulo 10 solo al Operador, pero el resumen del Administrador declara «módulos 1 a 14», que lo incluye. La contradicción se resuelve a favor del resumen: según HU-E9-01 (atender una conversación escalada) y HU-E9-02 (resolver y cerrar un escalamiento), el actor es «Operador / Administrador», de modo que el Administrador también recibe este módulo. El error está en la fila 10 de la tabla, que debe pasar a «Administrador / Operador».

#### Duraciones totales del resumen por rol

Los totales declarados no coinciden con la suma de las duraciones de la tabla. Sumando las filas que corresponden a cada rol:

| Sección | Dice | Debe decir | Fuente |
|---|---|---|---|
| Resumen por rol — Administrador | ≈ 8 h | ≈ 9 h 50 min | Suma de los módulos 1 a 14: 45+30+30+60+45+45+60+45+45+60+30+45+30+20 = 590 min. |
| Resumen por rol — Operador | ≈ 6 h | ≈ 6 h 30 min | Suma de los módulos 1, 5, 6, 7, 8, 9, 10 y 12: 45+45+45+60+45+45+60+45 = 390 min. |
| Resumen por rol — Solo Lectura | ≈ 2 h 15 min | ≈ 2 h 20 min | Suma de los módulos 1, 12, 14 y 15: 45+45+20+30 = 140 min. |

### 2. Guion breve por tema

La cátedra solicitó que cada tema de la tabla «Plan de capacitación por módulo» incluya una breve explicación de qué se mostraría durante la capacitación. Se agrega una columna «Qué se muestra» con el siguiente contenido para cada fila.

| # | Tema | Qué se muestra |
|---|---|---|
| 1 | Inducción general | Qué resuelve CheatSheet, cómo iniciar sesión con email o con Google, el recorrido por el menú lateral y qué puede hacer cada uno de los tres roles. |
| 2 | Configuración inicial de la empresa | Cómo completar los datos de la empresa y los datos fiscales durante el onboarding, de modo que la cuenta quede lista para facturar y cobrar. |
| 3 | Gestión de usuarios | Cómo invitar a un usuario por su email, asignarle un rol (Administrador, Operador o Solo Lectura) y desactivar su acceso cuando corresponde. |
| 4 | Conexión de integraciones externas | Cómo conectar las cuentas de ARCA, MercadoPago, WhatsApp y Google Sheets, y cómo verificar que cada conexión quedó activa. |
| 5 | Sincronización de planillas | Cómo vincular una planilla, mapear sus columnas con la asistencia del sistema, procesar la carga inicial y corregir las filas que quedaron con error. |
| 6 | Gestión de datos maestros | Cómo dar de alta y editar clientes y servicios, crear categorías propias y clasificar con ellas el catálogo. |
| 7 | Facturación electrónica | Cómo emitir un comprobante y obtener su CAE de ARCA, consultar el estado de los comprobantes, anular uno con una nota de crédito y administrar los puntos de venta. |
| 8 | Cobros | Cómo generar un link de pago de MercadoPago para un cliente, seguir el estado de los cobros, cancelar un cobro con su motivo y registrar un reembolso. |
| 9 | Agenda | Cómo ver la agenda de turnos, crear un turno manualmente, definir la disponibilidad de los recursos y registrar la asistencia. |
| 10 | Canal conversacional y atención | Cómo trabaja el agente de WhatsApp que reserva turnos y responde consultas, y cómo el operador atiende una conversación que el agente deriva a una persona. |
| 11 | Administración de FAQ y plantillas | Cómo cargar y mantener las preguntas frecuentes que responde el agente y cómo administrar las plantillas de los mensajes de notificación. |
| 12 | Reportería | Cómo leer los indicadores del tablero, previsualizar y descargar reportes, y generar el paquete contable del mes. |
| 13 | Configuración del negocio | Cómo definir las reglas parametrizables, como la cadena de recordatorios de cobro, y cómo usar el centro de notificaciones del panel. |
| 14 | Auditoría y observabilidad | Cómo consultar la bitácora de operaciones y abrir el detalle de una operación para ver qué pasó, quién la hizo y cuándo. |
| 15 | Consulta y lectura de información | Cómo recorrer listados, detalles y reportes en modo de solo lectura, para interpretar la información del sistema sin modificarla. |
