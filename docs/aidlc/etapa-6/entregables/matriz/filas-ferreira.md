---
entregable: matriz
parte: filas-ferreira
responsable: Paula Ferreira
estado: borrador
hu: [HU-E6-01, HU-E6-02, HU-E6-03, HU-E6-04, HU-E6-05, HU-E6-06, HU-E6-07, HU-E11-01, HS-T1, HS-T3]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - frontend/src/features/payments/
  - backend/src/cheatsheet/contexts/payments/
  - backend/src/cheatsheet/contexts/business_config/
observaciones: >
  Actualización del 13/10/2026 sobre el borrador del 12/10. Cambios desde entonces, ya
  integrados: se resolvió el bloqueo de MercadoPago y el pago de un cobro se confirma por
  external_reference (PR #194 y #196); PRU-06 se re-ejecutó en staging con MercadoPago real
  (entorno de prueba) y quedó Aprobado, por lo que HS-T1 pasa a Codificado con integración
  Real · validada. En HU-E6-03 entró el control para regenerar el link e invalidar el
  anterior (el criterio 5 que PRU-02 marcó faltante) y, con MercadoPago real, pasa a
  Codificado · Real · validada. También se integraron, en el módulo Cobros: aceptar el monto
  con coma decimal (PR #148), mostrar los errores de los diálogos de reembolso y cancelación
  dentro del modal, y mostrar el nombre y el CUIT del cliente en el detalle; PRU-08 se
  re-ejecutó sobre un cobro pagado por MercadoPago. HU-E6-07 ya no queda a confirmar: el
  alcance se confirmó con el referente del épico y se dividió en unidades; la primera está
  en desarrollo (plan de unidad de la seña de turno), por lo que sigue En desarrollo con
  integración Sin implementar.
  Ningún ítem se marca Probado todavía: §5.4 exige PR mergeado a develop, tests en verde y
  prueba manual sin bugs críticos ni mayores abiertos; la responsable debe confirmar que no
  queda ningún bug mayor abierto en HU-E6-02, HU-E6-04 y HU-E6-05 antes de pasarlos, y las
  fechas estimadas (17/10) quedan pendientes de reconfirmar. WhatsApp y ARCA siguen en modo
  simulado donde aplica (regla de la V3).
---

## Filas de la matriz de trazabilidad — Paula Ferreira

Las filas siguientes corresponden a los diez ítems asignados en `reparto.md`: el módulo Cobros (HU-E6-01 a HU-E6-07, HS-T1 y HS-T3) y Configuración del Negocio (HU-E11-01). Cada fila mantiene las nueve columnas de la V3.

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |
|---|---|---|---|---|---|---|---|---|
| Cobros | Consultar el estado de los cobros | HU-E6-01 | Administrador / Operador / Solo Lectura | Cobro | PAN-COB-01 | Codificado | No aplica | 17/10/2026 |
| Cobros | Consultar el detalle de un cobro | HU-E6-02 | Administrador / Operador / Solo Lectura | Cobro | PAN-COB-02 | Codificado | No aplica | 17/10/2026 |
| Cobros | Generar un link de cobro para un cliente | HU-E6-03 | Administrador / Operador | Cobro | PAN-COB-03 | Codificado | Real · validada | 17/10/2026 |
| Cobros | Cancelar un cobro | HU-E6-04 | Administrador / Operador | Cobro | PAN-COB-02 | En desarrollo | Simulada | 17/10/2026 |
| Cobros | Reembolsar un cobro | HU-E6-05 | Administrador | Cobro | PAN-COB-02 | En desarrollo | Simulada | 17/10/2026 |
| Cobros | Asociar un cobro a un comprobante existente | HU-E6-06 | Administrador / Operador | Cobro, Comprobante | PAN-COB-03 | En desarrollo | Simulada | 24/10/2026 |
| Cobros | Asociar un cobro a un turno como seña | HU-E6-07 | Administrador / Operador | Cobro, Turno | PAN-COB-03 | En desarrollo | Sin implementar | 24/10/2026 |
| Cobros | Confirmar un pago a partir del webhook de MercadoPago | HS-T1 | Sistema | Cobro | PAN-LOG-01 | Codificado | Real · validada | 17/10/2026 |
| Cobros | Despachar recordatorios de cobro según la regla de escalamiento | HS-T3 | Sistema | Recordatorio | PAN-LOG-01 | En desarrollo | Simulada | 17/10/2026 |
| Configuración del Negocio | Definir reglas de negocio parametrizables | HU-E11-01 | Administrador | ReglaDeNegocio | PAN-CFG-RN | Codificado | No aplica | 17/10/2026 |
