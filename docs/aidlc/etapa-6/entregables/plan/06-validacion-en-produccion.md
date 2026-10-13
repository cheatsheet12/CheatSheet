---
entregable: plan
parte: 06-validacion-en-produccion
responsable: Emanuel Gomez
estado: borrador
hu: [HS-T1, HS-T5, HU-E5-03, HU-E6-03, HU-E7-06, HU-E8-01, HU-E12-01]
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/etapa-6/reparto.md
  - docs/staging-deployment.md
  - backend/scripts/verify_rls.py
  - backend/src/cheatsheet/api/main.py
observaciones: >
  Las pruebas de esta sección reutilizan los guiones PRU-01 … PRU-09 del documento de pruebas del
  sistema, con los datos reales de la empresa piloto en lugar de los ficticios de staging. Las
  dependencias hacia PLAN-§2, PLAN-§3 y PLAN-§8 se citan a nivel de sección porque esas secciones
  todavía no están escritas. En producción no se emite ningún comprobante ni se genera ningún cobro
  de prueba: un comprobante con CAE no se deshace (plan/00), por eso las validaciones fiscales y de
  cobro se hacen sobre la primera operación real de la piloto.
---

## 6. Pruebas de validación en producción

### Objetivo

Confirmar, el día D y durante la estabilización, que el sistema desplegado en producción hace con
los datos y los servicios reales de la empresa piloto lo mismo que se verificó en staging. La
validación separa dos tipos de prueba: las **técnicas**, que no tocan datos de negocio y se corren
antes de habilitar a la piloto, y las **funcionales**, que se hacen sobre las primeras operaciones
reales de la piloto, acompañadas por el equipo. Ninguna prueba en producción emite un comprobante
o genera un cobro que no corresponda a una operación real: un comprobante con CAE no se deshace.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 6.1 | Adaptar los guiones PRU-01 … PRU-09 a producción: reemplazar los datos ficticios por los de la piloto, marcar qué pasos tienen efecto fiscal o monetario y fijar quién acompaña cada uno | Analista de QA | D-7 | 5.4 |
| 6.2 | Verificar el despliegue: `GET /health` responde 200 con la base y Redis disponibles, las migraciones están aplicadas y la versión desplegada es la aprobada | Analista de Infraestructura y Datos | D-1 | PLAN-§3 |
| 6.3 | Verificar el aislamiento entre empresas con `verify_rls.py` sobre la base de producción, con la carga inicial ya hecha | Analista de QA | D-1 | 4.6, 5.7 |
| 6.4 | Verificar las conexiones externas de la piloto con «Verificar estado» en Integraciones: ARCA, MercadoPago y WhatsApp deben figurar «Conectada» (HU-E2-05) | Analista de Integraciones | D-1 | 4.2 |
| 6.5 | Prueba de humo de acceso: cada rol inicia sesión y ve solo las acciones que le corresponden | Analista de QA | D, al inicio de la jornada | 5.6 |
| 6.6 | Validar la primera emisión real de la piloto (PRU-01): el comprobante obtiene CAE, su numeración es correlativa con ARCA y queda en la bitácora con el resultado de ARCA (HU-E5-03) | Analista de QA | D | 6.4, 6.5 |
| 6.7 | Validar el primer cobro real de la piloto (PRU-02 y PRU-06): el link se genera, el pago aprobado llega por el webhook, el cobro pasa a pagado sin diferencia de monto y aparece en los indicadores (HU-E6-03, HS-T1) | Analista de QA | D | 6.4, 6.5 |
| 6.8 | Validar la agenda con un turno real (PRU-04 y PRU-05): un turno creado en el panel y uno reservado por WhatsApp aparecen en la agenda sin superposición, y el cliente recibe la confirmación por WhatsApp (HU-E7-06, HU-E8-01) | Analista de QA | D | 6.4, 6.5 |
| 6.9 | Revisar la bitácora al cierre de D: cada operación de 6.6 a 6.8 está registrada con su iniciador y resultado, y no hay operaciones con error sin explicar (HS-T5, HU-E12-01) | Analista de QA | D, al cierre | 6.6, 6.7, 6.8 |
| 6.10 | Decidir la continuidad del piloto con el resultado de 6.2 a 6.9: si una validación falla con un bug crítico, se aplica PLAN-§8 | Arquitecto de Software | D, al cierre | 6.9, PLAN-§8 |
| 6.11 | Conciliar a diario los comprobantes emitidos contra ARCA y los cobros aprobados contra MercadoPago, y revisar la bitácora y la cola de fallos | Analista de QA | D+1 a D+14 | 6.10 |
| 6.12 | Medir los criterios de salida del piloto de plan/00 y emitir el informe de validación | Analista de QA | D+15 a D+30 | 6.11 |

### Criterio de listo

- 6.2 a 6.5 terminan sin fallas antes de que la piloto opere.
- La primera emisión, el primer cobro y el primer turno reales de la piloto se validaron con su
  guion, y cada operación figura en la bitácora con resultado completado.
- Durante la estabilización no hay diferencias entre los comprobantes del panel y ARCA, ni entre
  los cobros del panel y MercadoPago.
- El informe de 6.12 registra, por guion, la fecha, el responsable, el resultado y los bugs
  abiertos, y responde si se cumplen los criterios de salida del piloto.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Una prueba en producción emite un comprobante o genera un cobro que no corresponde a una operación real | Baja | Crítico | 6.1 marca los pasos con efecto fiscal o monetario; esos pasos se hacen solo sobre operaciones reales de la piloto y acompañados por el equipo |
| Una integración externa funciona en homologación pero no con las credenciales de producción | Media | Alto | 6.4 verifica las tres conexiones el día anterior; sin las tres «Conectadas», D no avanza |
| El webhook de MercadoPago no llega a producción y el cobro queda pendiente | Media | Alto | 6.7 sigue el primer pago de punta a punta; si el cobro no cambia de estado se revisa la URL de notificaciones antes de habilitar más cobros |
| Una falla queda sin detectar porque la bitácora no la registra como error | Media | Medio | 6.9 contrasta las operaciones esperadas con las registradas, y 6.11 suma la conciliación contra ARCA y MercadoPago como control independiente |
| La validación encuentra un bug crítico el día D | Media | Alto | 6.10 aplica PLAN-§8: la piloto vuelve a su operación anterior, que conservó lista para retomarse |
