---
entregable: pruebas
parte: PRU-02
responsable: Paula Ferreira
estado: borrador
hu: [HU-E6-03]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - docs/aidlc/inputs/prototipos.md
  - backend/src/cheatsheet/contexts/payments/application/cobros.py
  - backend/src/cheatsheet/contexts/payments/domain/cobro.py
  - frontend/src/features/payments/
observaciones: >
  1. RN-03 de HU-E6-03 indica que al generar el link se inicia la cadena de
  recordatorios escalonados por WhatsApp. En staging el canal real de WhatsApp
  aún no está implementado (pendiente 11 del épico 8): los recordatorios se
  registran mediante `EnvioPorConsola`, sin salida real. El detalle del cobro
  lo refleja con el texto «Todavía no se envió ningún recordatorio para este
  cobro.». El criterio verificable en staging es que la cadena quede programada,
  no que el mensaje llegue al destinatario.
  2. El criterio de aceptación 5 (regenerar link e invalidar el anterior) no es
  verificable desde el panel: la pantalla de detalle del cobro (PAN-COB-02) no
  expone un control para regenerar el link, aunque el backend sí lo soporta
  (`RegenerarLink` y `POST /cobros/{id}/link` en
  `backend/src/cheatsheet/contexts/payments/application/cobros.py`). Reportado
  como bug de frontend.
  3. Los CUIT ficticios de `reglas.md §6` no superan la validación de dígito
  verificador (`backend/src/cheatsheet/shared/fiscal.py`). El cliente Ana Prueba
  se creó con el DV corregido `20-22222222-3`. Reportado para actualizar
  `reglas.md`.
  4. La empresa de staging se denomina «Distribuidora La Esquina SRL»; las
  capturas la muestran en el encabezado del panel.
---

## PRU-02 — Generar un link de cobro para un cliente

**Tipo:** Funcional

| Campo | Contenido |
|---|---|
| ID de prueba | PRU-02 |
| CU/HU referenciado | HU-E6-03 — Generar un link de cobro para un cliente |
| Pantalla / Reporte | PAN-COB-03 (generación), PAN-COB-02 (detalle del cobro) |
| Datos de entrada | Administrador de la empresa de staging. Cliente **Ana Prueba** (CUIT `20-22222222-3`). Concepto `Consulta general`. Monto `$ 15.000,00`. MercadoPago conectado en Homologación. |
| Pasos | 1. Ingresar al panel con el usuario Administrador. <br> 2. Navegar a «Menú › Cobros». <br> 3. Pulsar «Generar cobro» para abrir PAN-COB-03. <br> 4. Sin completar ningún campo, verificar que el botón «Generar link de pago» permanece deshabilitado y aparecen los mensajes de validación. <br> 5. Seleccionar al cliente **Ana Prueba**, completar el concepto con `Consulta general`, ingresar monto `0` y verificar el mensaje de validación del monto. <br> 6. Reemplazar el monto por `15000` y verificar que el mensaje desaparece y el botón se habilita. <br> 7. Pulsar «Generar link de pago» y esperar la respuesta de MercadoPago. <br> 8. Verificar en el detalle del cobro (PAN-COB-02) que el link figura en estado `Activo`, con su referencia y medio de pago. |
| Resultado esperado | **Criterios de aceptación de HU-E6-03.** 1. Al intentar generar sin concepto, el sistema muestra «Debe ingresar un concepto para el cobro.» y el botón permanece deshabilitado. 2. Al ingresar un monto cero o negativo, el sistema muestra «El monto debe ser mayor a cero.» y no permite continuar. 3. Al confirmar con datos válidos, el link se genera en estado `Activo` y comienza la cadena de recordatorios. 4. Si MercadoPago no responde, el sistema no crea el cobro. 5. Si ya existe un link activo y se genera uno nuevo, el sistema invalida el anterior y registra el cambio en la bitácora. |
| Resultado obtenido | 1. Con el formulario vacío, el botón «Generar link de pago» aparece deshabilitado y se muestran los mensajes «Debe seleccionar un cliente.» y «Debe ingresar un concepto para el cobro.» (PRU-02_1.png). 2. Con cliente y concepto cargados y monto `0`, el campo monto se marca en rojo con el mensaje «El monto debe ser mayor a cero.» y el botón sigue deshabilitado; el mismo mensaje aparece con un monto negativo (PRU-02_2.png). 3. Con monto `15000` el mensaje desaparece y el botón se habilita (PRU-02_3.png); al pulsarlo, el sistema crea el cobro `CB-0DE64B52` y abre su detalle con el link de MercadoPago en estado `Activo`, monto `$ 15.000,00`, medio de pago «Link de MercadoPago» y vencimiento 4/11/26 (PRU-02_4.png). 4. El cobro se creó porque MercadoPago respondió correctamente; el caso de no respuesta no se forzó en esta corrida. 5. No verificable desde el panel: no existe control para regenerar el link en PAN-COB-02 (ver observación 2). El detalle confirma además que la cadena de recordatorios quedó iniciada sin envíos, consistente con la observación 1. |
| Estado | Aprobada con observaciones |
| Evidencia | PRU-02_1.png — PAN-COB-03 con el formulario vacío y los mensajes de validación. <br> PRU-02_2.png — PAN-COB-03 con monto en `0` y el mensaje «El monto debe ser mayor a cero.». <br> PRU-02_3.png — PAN-COB-03 con cliente, concepto y monto `15000` válidos, botón habilitado. <br> PRU-02_4.png — PAN-COB-02 con el cobro `CB-0DE64B52` y el link de MercadoPago en estado `Activo`. |
