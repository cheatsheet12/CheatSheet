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
  1. La prueba se ejecutó en staging con la integración real de MercadoPago, en su
  entorno de prueba (cuentas de test de MercadoPago). El pago se completó abriendo el
  link de checkout del cobro e iniciando sesión con una cuenta pagadora de prueba;
  MercadoPago envió la notificación del webhook y el sistema confirmó el cobro de forma
  automática. La empresa de staging se denomina «Distribuidora La Esquina SRL» y así
  aparece en el encabezado de las capturas.
  2. El criterio de HS-T1 sobre reducir el saldo del comprobante asociado solo se
  ejercita si el cobro está asociado a un comprobante; con un cobro sin comprobante ese
  criterio no aplica y se deja constancia en el resultado.
  3. El criterio 4 (idempotencia ante una notificación repetida) quedó evidenciado en
  staging: MercadoPago reenvió la notificación del mismo pago varias veces y el Log de
  operaciones muestra una única operación `confirmar_pago` completada, mientras que las
  notificaciones posteriores del mismo pago quedaron registradas como `webhook_rechazado`
  (sin un segundo pago confirmado). Además se verificó en el entorno local reenviando la
  misma notificación del webhook de forma controlada, sin efectos duplicados.
---

## PRU-06 — El webhook de MercadoPago aprueba el cobro y aparece en el listado y en los indicadores

**Tipo:** Integración

| Campo | Contenido |
|---|---|
| ID de prueba | PRU-06 |
| CU/HU referenciado | HS-T1 — Confirmar un pago a partir del webhook de MercadoPago; HU-E6-01 — Consultar el estado de los cobros; HU-E10-01 — Visualizar los indicadores del tablero |
| Pantalla / Reporte | PAN-COB-01 (listado de cobros), PAN-COB-02 (detalle del cobro), PAN-REP-01 (tablero de indicadores) |
| Datos de entrada | Administrador de la empresa «Distribuidora La Esquina SRL» (staging). Un cobro pendiente a nombre del cliente **Ana Prueba** (CUIT 20-22222222-3), concepto `Consulta general`, monto `$ 15.000,00`, con link de MercadoPago generado. MercadoPago conectado con cuentas de prueba (ver observación 1). |
| Pasos | 1. Ingresar al panel con el usuario Administrador y registrar en el tablero (PAN-REP-01) el valor inicial de la métrica «Cobrado» del período. <br> 2. Navegar a «Menú › Cobros» (PAN-COB-01) y verificar que el cobro de prueba figura en estado «Pendiente». <br> 3. Abrir el link de pago del cobro en el checkout de MercadoPago, iniciar sesión con una cuenta pagadora de prueba y completar el pago; MercadoPago envía la notificación del webhook y el sistema confirma el cobro (ver observación 1). <br> 4. Abrir el detalle del cobro (PAN-COB-02) y verificar que pasó a «Pagado», con su fecha de pago y el medio «Link de MercadoPago». <br> 5. Volver al listado (PAN-COB-01) y verificar que el cobro figura «Pagado». <br> 6. Abrir el tablero (PAN-REP-01) y verificar que el monto del cobro se sumó a la métrica «Cobrado» del período. <br> 7. Reenviar la misma notificación una segunda vez y verificar que el cobro y las métricas no cambian (ver observación 3). |
| Resultado esperado | **Criterios de aceptación de HS-T1, HU-E6-01 y HU-E10-01.** 1. Al recibir un webhook de pago válido, el cobro pasa a APROBADO (etiqueta «Pagado») y se detiene la cadena de recordatorios (HS-T1 RN-02). 2. El cobro aprobado figura en el listado (PAN-COB-01) con la etiqueta «Pagado» (HU-E6-01). 3. El monto del cobro se suma a la métrica «Cobrado» del período en el tablero (HU-E10-01 RN-08). 4. Una notificación repetida del mismo pago no genera efectos duplicados (HS-T1 RN-04). 5. El evento queda registrado en la bitácora con iniciador Sistema (HS-T1 RN-05). |
| Resultado obtenido | Se cumplieron los cinco criterios. 1. Al pagar el link con la cuenta de prueba, MercadoPago envió el webhook y el cobro `CB-D2E79512` (`Consulta general`, $ 15.000,00) pasó de «Pendiente» a «Pagado» (APROBADO), con fecha de pago 12/10/2026 21:03 y medio «Link de MercadoPago». 2. En el listado (PAN-COB-01) el cobro figura con la etiqueta «Pagado». 3. La métrica «Cobrado» del período pasó de $ 0,00 a $ 15.000,00 y «Pendiente» bajó de $ 30.000,00 a $ 15.000,00, tanto en el encabezado de Cobros como en el tablero de Reportes (PAN-REP-01). 4. No hubo efectos duplicados (RN-04): en staging MercadoPago reenvió la notificación del pago varias veces y el Log de operaciones registra una única operación `confirmar_pago` completada, con las notificaciones posteriores del mismo pago como `webhook_rechazado`; se corroboró además en el entorno local reenviando la misma notificación, sin cambios en el cobro ni en las métricas (observación 3). 5. El evento quedó en la bitácora (Log de operaciones) como `confirmar_pago`, iniciador «Sistema», resultado «Completado» (RN-05). El criterio de reducir el saldo del comprobante no aplica: el cobro no está asociado a un comprobante (observación 2). |
| Estado | Aprobado |
| Evidencia | ![Figura PRU-06-1 — Listado de Cobros antes del pago: «Cobrado» $ 0,00, «Pendiente» $ 30.000,00 y el cobro «Consulta general» (CB-D2E79512) en estado «Pendiente».](capturas/PRU-06_1.png) <br> ![Figura PRU-06-2 — Tablero de Reportes antes del pago: la métrica «Cobrado» del período en $ 0,00 y «Pendiente de cobro» en $ 30.000,00.](capturas/PRU-06_2.png) <br> ![Figura PRU-06-3 — Detalle del cobro CB-D2E79512 después del pago: estado «Pagado», fecha de pago 12/10/2026 21:03 y medio «Link de MercadoPago».](capturas/PRU-06_3.png) <br> ![Figura PRU-06-4 — Listado de Cobros después del pago: «Cobrado» $ 15.000,00 y el cobro CB-D2E79512 en estado «Pagado».](capturas/PRU-06_4.png) <br> ![Figura PRU-06-5 — Tablero de Reportes después del pago: la métrica «Cobrado» del período en $ 15.000,00 y «Pendiente de cobro» en $ 15.000,00.](capturas/PRU-06_5.png) <br> ![Figura PRU-06-6 — Log de operaciones: la operación `confirmar_pago` sobre el cobro CB-D2E79512, iniciada por «Sistema» y «Completado»; las notificaciones repetidas del mismo pago figuran como `webhook_rechazado`.](capturas/PRU-06_6.png) |

### Módulos involucrados

- **Cobros**: recibe la notificación del webhook, confirma el pago y lleva el cobro a APROBADO; el listado (PAN-COB-01) lo refleja con la etiqueta «Pagado».
- **Tablero e Indicadores**: suma el monto del cobro aprobado a la métrica «Cobrado» del período (PAN-REP-01).
- **Integraciones Externas**: la notificación entrante del webhook de MercadoPago, con la integración real de MercadoPago en su entorno de prueba (cuentas de test).
