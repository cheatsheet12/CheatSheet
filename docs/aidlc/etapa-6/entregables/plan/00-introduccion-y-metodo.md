---
entregable: plan
parte: 00-introduccion-y-metodo
responsable: Cristian Suarez
estado: listo
hu: [HS-T3, HU-E7-02, HU-E7-06, HU-E8-03, HU-E8-04, HS-T7]
fuentes:
  - docs/adr/0006-staging-hosting-render.md
  - docs/configuration-management.md
  - docs/staging-deployment.md
  - docs/architecture.md
  - docs/aidlc/TODO.md
  - docs/aidlc/etapa-6/reparto.md
observaciones: >
  La fecha calendario de D queda sin fijar a propósito: se define después de la aprobación del
  entregable. Las demás secciones usan solo la notación relativa. architecture.md ubica el panel
  en Vercel y staging lo corre en Render (ADR-0006); el plan no da por decidido ninguno de los dos
  para producción y deja la elección a PLAN-§2.
---

# Plan de implementación

## Introducción

Este documento planifica la puesta en producción de CheatSheet, la plataforma que integra
facturación electrónica ante ARCA, cobros por MercadoPago, agenda de turnos y atención por WhatsApp
para pequeñas y medianas empresas de Argentina. Fija el método de implementación, el día de puesta
en producción y la notación de fechas, y organiza las ocho actividades que exige la planificación:
puesta en producción, entorno, despliegue, carga inicial, usuarios, validación, comunicación y
contingencia.

El sistema se valida hoy en **staging**, un entorno compartido que se actualiza solo con cada
cambio aprobado en la rama `develop`, aplica las migraciones y verifica el aislamiento entre
empresas antes de publicar cada versión. En staging las integraciones con ARCA, MercadoPago y
WhatsApp corren en modo homologación o simulado, con datos de prueba. La producción todavía **no
existe ni está decidida**: este plan la propone a partir de lo que staging ya resuelve, sin darla
por hecha.

## Método de implementación

El método elegido es la **implementación piloto**: el sistema entra en producción con **una sola
empresa piloto**, que opera con datos y servicios reales durante un período acotado. Recién cuando
el piloto cumple sus criterios de salida, el sistema se abre a nuevas empresas.

### Por qué piloto

CheatSheet es una plataforma multiempresa: cada empresa adopta el sistema por separado y sus datos
están aislados de los de las demás. Eso permite acotar el riesgo a una empresa sin construir nada
adicional, y es lo que vuelve natural el método piloto.

| Método | Evaluación |
|---|---|
| Directa | Descartado. Habilitar a todas las empresas a la vez expone desde el primer día a todas ellas a un error en la emisión de comprobantes o en la imputación de cobros, que son operaciones con efecto fiscal y monetario. |
| Paralela | Descartado. Operar el sistema anterior y CheatSheet a la vez obliga a emitir cada comprobante dos veces, y un comprobante con CAE no se puede deshacer: la doble emisión duplica la obligación fiscal. Lo mismo ocurre con un link de cobro generado por los dos caminos. |
| Por fases | Descartado como método principal. Los módulos dependen entre sí (un turno genera un cobro, un cobro aprobado genera un comprobante), por lo que habilitarlos de a uno deja procesos a medias. |
| **Piloto** | **Elegido.** Limita el impacto de una falla a una empresa, ejercita todos los módulos juntos con datos reales y permite volver a la operación anterior de esa empresa sin afectar a otras. |

### Empresa piloto

La empresa piloto se elige con este perfil:

- Responsable Inscripto, con punto de venta habilitado en ARCA para emitir comprobantes electrónicos.
- Trabaja con turnos y cobra por MercadoPago, de modo que el piloto ejercite agenda, cobros y
  facturación en el mismo flujo.
- Lleva hoy su operación en planillas, lo que permite la carga inicial por ingesta (PLAN-§4) y
  conserva una operación anterior a la que volver (PLAN-§8).
- Tiene un Administrador disponible para la capacitación y para reportar incidencias durante el
  período de estabilización.

Durante el piloto la empresa conserva su operación anterior **lista para retomarse**, pero no la
usa en paralelo: cada comprobante y cada cobro se emite por un solo camino.

## Fecha D y notación de fechas

**D** es el día de puesta en producción: la jornada en que la empresa piloto empieza a operar con
CheatSheet. Su fecha calendario **se fija después de la aprobación de este entregable** y se
registra en este apartado. Hasta entonces, todas las secciones del plan fechan sus actividades
respecto de D.

| Notación | Significado |
|---|---|
| D-n | n días corridos antes de la puesta en producción |
| D | Día de puesta en producción |
| D+n | n días corridos después de la puesta en producción |

Ninguna sección escribe una fecha absoluta: así, si D se mueve, el plan entero se mueve con ella
sin contradicciones.

### Etapas del piloto

| Etapa | Período | Qué ocurre |
|---|---|---|
| Preparación | D-21 a D-1 | Se prepara el entorno de producción, se despliega la versión aprobada, se carga la información inicial, se crean los usuarios y se capacita a la empresa piloto |
| Puesta en producción | D | La empresa piloto empieza a operar; se ejecutan las pruebas de validación en producción |
| Estabilización | D+1 a D+14 | Soporte intensivo, registro y corrección de incidencias, revisión diaria de la bitácora |
| Evaluación | D+15 a D+30 | Se miden los criterios de salida y se decide si el sistema se abre a nuevas empresas |

### Criterios de salida del piloto

El piloto termina y el sistema se abre a nuevas empresas cuando se cumplen todos estos criterios:

- Ningún bug crítico abierto. Se considera crítico lo que afecta dinero, un comprobante fiscal,
  datos de otra empresa o pérdida de datos.
- Todos los comprobantes emitidos durante el piloto tienen CAE y coinciden con lo registrado en
  ARCA.
- Todos los cobros aprobados en MercadoPago figuran como cobrados en el panel, sin diferencias de
  monto.
- La empresa piloto opera al menos diez días hábiles seguidos sin volver a su operación anterior.

Si al llegar a D+30 algún criterio no se cumple, el piloto se extiende y se vuelve a evaluar. Los
criterios de reversión durante el piloto están en PLAN-§8.

## Condiciones previas a D

D no se fija mientras haya un módulo que la empresa piloto vaya a usar sin integración real. Al
cierre de este documento quedan pendientes:

| Condición | Ítems que cierra | Sección que la verifica |
|---|---|---|
| Canal real de WhatsApp para recordatorios de cobro y avisos de turno, que hoy solo se registran en el log | HS-T3, HU-E7-02, HU-E7-06, HU-E8-04 | PLAN-§2 |
| Proveedor de embeddings y de transcripción de audios para el agente de WhatsApp, que hoy corren simulados | HU-E8-03, HS-T7 | PLAN-§2 |
| Credenciales de producción de ARCA (certificado fiscal), MercadoPago, WhatsApp Business, inicio de sesión con Google y correo transaccional | Todos los módulos con integración externa | PLAN-§2 |
| Decisión sobre el proveedor de alojamiento de producción | Todo el sistema | PLAN-§2 |

## Organización del plan

Cada sección desarrolla una actividad de la planificación. Los responsables se nombran por rol y
las dependencias entre actividades se citan por número (por ejemplo, la actividad 2.3).

| Sección | Actividad | Responsable |
|---|---|---|
| PLAN-§1 | Plan de puesta en producción | Arquitecto de Software |
| PLAN-§2 | Preparar el entorno de producción | Analista de Infraestructura y Datos |
| PLAN-§3 | Realizar el despliegue | Analista de Infraestructura y Datos |
| PLAN-§4 | Carga inicial de datos | Analista Funcional y Diseño de Experiencia |
| PLAN-§5 | Usuarios, perfiles y permisos | Analista de QA |
| PLAN-§6 | Pruebas de validación en producción | Analista de QA |
| PLAN-§7 | Comunicación e inicio de operaciones | Analista Funcional y Diseño de Experiencia |
| PLAN-§8 | Plan de contingencia y rollback | Analista de Integraciones |
