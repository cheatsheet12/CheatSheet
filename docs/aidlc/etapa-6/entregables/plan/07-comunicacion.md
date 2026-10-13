---
entregable: plan
parte: 07-comunicacion
responsable: Paula Ferreira
estado: borrador
hu: [HU-E1-01, HU-E6-03, HU-E5-03, HU-E7-06, HU-E12-01, HU-E11-03]
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/etapa-6/entregables/manual/
  - docs/aidlc/etapa-6/entregables/correcciones/capacitacion.md
observaciones: >
  Las dependencias de la columna «Depende de» se citan a nivel de sección (PLAN-§5,
  PLAN-§6) porque esas secciones todavía no están escritas; sus números de actividad
  se alinean cuando se publiquen. Las fechas son relativas a D y las propone la
  responsable; se ajustan al fijarse la fecha calendario de D en plan/00. La
  capacitación se apoya en el manual de usuario y en el plan de capacitación, ambos
  entregables de esta etapa.
---

## 7. Comunicación e inicio de operaciones

### Objetivo

Esta sección prepara a la empresa piloto para operar con CheatSheet y acompaña el inicio de operaciones en D, con una capacitación previa, la comunicación del cambio y un canal de soporte durante la estabilización. La operación anterior de la empresa queda lista para retomarse, pero no se usa en paralelo: cada cobro y cada comprobante se emite por un solo camino.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 7.1 | Capacitar al Administrador de la empresa piloto con el manual de usuario y el plan de capacitación, cubriendo el ingreso, los cobros, la facturación y la agenda | Analista Funcional y Diseño de Experiencia | D-5 | PLAN-§5, 4.6 |
| 7.2 | Comunicar a la empresa piloto la fecha D, qué cambia en su operación diaria y el canal por el que reportar incidencias | Analista Funcional y Diseño de Experiencia | D-3 | 7.1 |
| 7.3 | Acompañar el inicio de operaciones en D: el primer cobro, el primer comprobante y el primer turno reales | Analista Funcional y Diseño de Experiencia | D | PLAN-§6 |
| 7.4 | Sostener el canal de soporte y registrar las incidencias durante la estabilización, con revisión diaria de la bitácora | Analista Funcional y Diseño de Experiencia | D+1 a D+14 | 7.3 |
| 7.5 | Comunicar a la empresa piloto el cierre de la estabilización y el resultado de la evaluación del piloto | Analista Funcional y Diseño de Experiencia | D+30 | 7.4, PLAN-§6 |

### Criterio de listo

- El Administrador de la empresa piloto completó la capacitación y sabe generar un cobro, emitir un comprobante, crear un turno y consultar la bitácora.
- La empresa piloto recibió la comunicación de la fecha D y conoce el canal de soporte.
- El canal de soporte queda activo durante toda la estabilización.
- Las incidencias de la estabilización quedan registradas y con seguimiento.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Resistencia al cambio o baja adopción de la empresa piloto | Media | Alto | Capacitación previa con el manual, acompañamiento en D y operación anterior lista para retomarse (PLAN-§8) |
| Incidencias no reportadas o detectadas tarde | Media | Medio | Canal de soporte definido en 7.2 y revisión diaria de la bitácora durante la estabilización |
| Capacitación insuficiente para el volumen de operación | Baja | Medio | La capacitación cubre los flujos completos de cobros, facturación y agenda, y el manual queda disponible como material de consulta |
