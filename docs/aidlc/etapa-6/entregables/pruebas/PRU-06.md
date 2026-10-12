---
entregable: pruebas
parte: PRU-06
responsable: Paula Ferreira
estado: borrador
hu: [HS-T1, HU-E6-01, HU-E10-01]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - backend/src/cheatsheet/api/routers/webhooks.py
  - backend/src/cheatsheet/contexts/payments/application/confirmacion.py
  - frontend/src/features/payments/
observaciones: >
  1. En staging MercadoPago está en modo simulado: el link de pago no procesa un pago
  real, por lo que el cobro no se aprueba con solo abrir el link. La confirmación se
  produce cuando el sistema recibe la notificación del webhook, cuyo disparo en staging
  lo coordina Infraestructura con el secreto del webhook del entorno. Por eso el paso 3
  describe la recepción de la notificación, no el pago desde el checkout de MercadoPago.
  2. El criterio de HS-T1 sobre reducir el saldo del comprobante asociado solo se
  ejercita si el cobro está asociado a un comprobante; con un cobro sin comprobante ese
  criterio no aplica y se deja constancia en el resultado.
  3. La empresa de staging se denomina «Distribuidora La Esquina SRL»; las capturas la
  muestran en el encabezado del panel.
---

## PRU-06 — El webhook de MercadoPago aprueba el cobro y aparece en el listado y en los indicadores

**Tipo:** Integración

| Campo | Contenido |
|---|---|
| ID de prueba | PRU-06 |
| CU/HU referenciado | HS-T1 — Confirmar un pago a partir del webhook de MercadoPago; HU-E6-01 — Consultar el estado de los cobros; HU-E10-01 — Visualizar los indicadores del tablero |
| Pantalla / Reporte | PAN-COB-01 (listado de cobros), PAN-COB-02 (detalle del cobro), PAN-REP-01 (tablero de indicadores) |
| Datos de entrada | Administrador de la empresa de staging. Un cobro pendiente pagado por link de MercadoPago (puede ser el generado en PRU-02, cliente **Ana Prueba**, concepto `Consulta general`, monto `$ 15.000,00`). MercadoPago conectado. |
| Pasos | 1. Ingresar al panel con el usuario Administrador y registrar en el tablero (PAN-REP-01) el valor inicial de la métrica «Cobrado» del período. <br> 2. Navegar a «Menú › Cobros» (PAN-COB-01) y verificar que el cobro de prueba figura en estado «Pendiente». <br> 3. Provocar la recepción de la notificación de pago del webhook de MercadoPago para ese cobro (ver observación 1). <br> 4. Abrir el detalle del cobro (PAN-COB-02) y verificar que pasó a «Pagado», con su fecha de pago y el medio «Link de MercadoPago». <br> 5. Volver al listado (PAN-COB-01) y verificar que el cobro figura «Pagado». <br> 6. Abrir el tablero (PAN-REP-01) y verificar que el monto del cobro se sumó a la métrica «Cobrado» del período. <br> 7. Provocar la recepción de la misma notificación una segunda vez y verificar que el cobro y las métricas no cambian. |
| Resultado esperado | **Criterios de aceptación de HS-T1, HU-E6-01 y HU-E10-01.** 1. Al recibir un webhook de pago válido, el cobro pasa a APROBADO (etiqueta «Pagado») y se detiene la cadena de recordatorios (HS-T1 RN-02). 2. El cobro aprobado figura en el listado (PAN-COB-01) con la etiqueta «Pagado» (HU-E6-01). 3. El monto del cobro se suma a la métrica «Cobrado» del período en el tablero (HU-E10-01 RN-08). 4. Una notificación repetida del mismo pago no genera efectos duplicados (HS-T1 RN-04). 5. El evento queda registrado en la bitácora con iniciador Sistema (HS-T1 RN-05). |
| Resultado obtenido | PENDIENTE DE EJECUCIÓN |
| Estado | PENDIENTE DE EJECUCIÓN |
| Evidencia | PENDIENTE DE EJECUCIÓN |

### Módulos involucrados

- **Cobros**: recibe la notificación del webhook, confirma el pago y lleva el cobro a APROBADO; el listado (PAN-COB-01) lo refleja con la etiqueta «Pagado».
- **Tablero e Indicadores**: suma el monto del cobro aprobado a la métrica «Cobrado» del período (PAN-REP-01).
- **Integraciones Externas**: la notificación entrante del webhook de MercadoPago, en modo simulado en el entorno de staging.
