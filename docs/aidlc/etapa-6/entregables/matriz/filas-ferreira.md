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
  Ningún ítem figura como Probado todavía: las correcciones de HU-E6-03 (criterio 5),
  HU-E6-05 (criterio 2) y HU-E6-02 (criterio 1) están en Pull Requests aún sin mergear
  a develop, y el módulo conserva bugs de severidad Mayor abiertos; §5.4 exige PR
  mergeado, tests en verde y prueba manual sin bugs críticos ni mayores abiertos.
  MercadoPago, WhatsApp y ARCA corren en modo simulado (sin adaptador real), por lo que
  los ítems que dependen de ellos quedan En desarrollo aunque sus tests estén en verde
  (regla de la V3). HU-E6-07 no está implementada de punta a punta: el esquema
  CobroEntrada y la pantalla de nuevo cobro no aceptan el turno; queda a confirmar con
  el equipo si entra en el alcance. Las fechas estimadas dependen del desbloqueo de
  staging y del merge de los Pull Requests, y las confirma la responsable.
---

## Filas de la matriz de trazabilidad — Paula Ferreira

Las filas siguientes corresponden a los diez ítems asignados en `reparto.md`: el módulo Cobros (HU-E6-01 a HU-E6-07, HS-T1 y HS-T3) y Configuración del Negocio (HU-E11-01). Cada fila mantiene las nueve columnas de la V3.

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |
|---|---|---|---|---|---|---|---|---|
| Cobros | Consultar el estado de los cobros | HU-E6-01 | Administrador / Operador / Solo Lectura | Cobro | PAN-COB-01 | Codificado | No aplica | 17/10/2026 |
| Cobros | Consultar el detalle de un cobro | HU-E6-02 | Administrador / Operador / Solo Lectura | Cobro | PAN-COB-02 | Codificado | No aplica | 17/10/2026 |
| Cobros | Generar un link de cobro para un cliente | HU-E6-03 | Administrador / Operador | Cobro | PAN-COB-03 | En desarrollo | Simulada | 17/10/2026 |
| Cobros | Cancelar un cobro | HU-E6-04 | Administrador / Operador | Cobro | PAN-COB-02 | En desarrollo | Simulada | 17/10/2026 |
| Cobros | Reembolsar un cobro | HU-E6-05 | Administrador | Cobro | PAN-COB-02 | En desarrollo | Simulada | 17/10/2026 |
| Cobros | Asociar un cobro a un comprobante existente | HU-E6-06 | Administrador / Operador | Cobro, Comprobante | PAN-COB-03 | En desarrollo | Simulada | 24/10/2026 |
| Cobros | Asociar un cobro a un turno como seña | HU-E6-07 | Administrador / Operador | Cobro, Turno | PAN-COB-03 | En desarrollo | Sin implementar | A confirmar |
| Cobros | Confirmar un pago a partir del webhook de MercadoPago | HS-T1 | Sistema | Cobro | PAN-LOG-01 | En desarrollo | Simulada | 17/10/2026 |
| Cobros | Despachar recordatorios de cobro según la regla de escalamiento | HS-T3 | Sistema | Recordatorio | PAN-LOG-01 | En desarrollo | Simulada | 17/10/2026 |
| Configuración del Negocio | Definir reglas de negocio parametrizables | HU-E11-01 | Administrador | ReglaDeNegocio | PAN-CFG-RN | Codificado | No aplica | 17/10/2026 |
