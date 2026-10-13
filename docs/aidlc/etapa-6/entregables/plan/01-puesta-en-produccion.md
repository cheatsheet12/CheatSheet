---
entregable: plan
parte: 01-puesta-en-produccion
responsable: Cristian Suarez
estado: borrador
hu: [HU-E2-01, HU-E2-02, HU-E2-03, HU-E2-05, HS-T1]
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/adr/0006-staging-hosting-render.md
  - docs/adr/0014-arca-web-service-delegation.md
  - docs/configuration-management.md
  - docs/staging-deployment.md
  - backend/.env.example
  - docs/aidlc/TODO.md
observaciones: >
  Las secciones PLAN-§2 a PLAN-§8 todavía no están escritas, así que la columna «Depende de» cita
  la sección y no la actividad. Al integrar, reemplazar cada «PLAN-§n» por el número de actividad
  correspondiente. Esta sección coordina a las demás: no repite cómo se prepara el entorno, cómo
  se despliega ni cómo se vuelve atrás, solo cuándo ocurre cada cosa y qué condición la habilita.
---

## 1. Plan de puesta en producción

### Objetivo

Coordinar el paso de CheatSheet de staging a producción con la empresa piloto definida en el
método de implementación: fijar la secuencia de hitos desde la preparación hasta la evaluación,
habilitar cada hito con una condición verificable y concentrar en una sola decisión, el día D-1,
si la puesta en producción se hace o se posterga.

La puesta en producción parte de lo que staging ya resuelve. Cada cambio aprobado en `develop`
pasa siete controles automáticos, aplica las migraciones, verifica que ninguna empresa pueda leer
datos de otra y recién entonces se publica (`docs/configuration-management.md`, apartado de
despliegue continuo). Las integraciones con ARCA y MercadoPago ya se ejercitaron contra los
servicios reales en modo homologación y prueba: un comprobante con CAE emitido desde staging y un
cobro pagado por MercadoPago que el sistema imputó solo. Lo que falta es lo que staging no tiene
por diseño: credenciales productivas, datos reales y una empresa que opere con ellos.

El sistema tiene una protección propia para este paso: con `APP_ENV=production`, los adaptadores
simulados de ARCA, MercadoPago y WhatsApp se niegan a construirse. Una variable de integración mal
configurada impide que el sistema arranque, en lugar de dejarlo operando con un simulador.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 1.1 | Fijar la fecha calendario de D y registrarla en el método de implementación | Arquitecto de Software | D-21 | — |
| 1.2 | Confirmar la empresa piloto según el perfil del método de implementación y designar a su Administrador como contacto | Analista Funcional y Diseño de Experiencia | D-21 | 1.1 |
| 1.3 | Revisar las condiciones previas a D del método de implementación y asignar cada una a su sección | Arquitecto de Software | D-21 | 1.1 |
| 1.4 | Gestionar en ARCA, con la clave fiscal de CheatSheet, el certificado de plataforma productivo para los servicios de facturación electrónica y de padrón | Analista de Integraciones | D-21 a D-14 | 1.3 |
| 1.5 | Pedir a la empresa piloto que delegue «Facturación Electrónica» en la CUIT de CheatSheet desde el Administrador de Relaciones de Clave Fiscal, y aceptar la designación desde la cuenta de CheatSheet | Analista de Integraciones | D-14 a D-10 | 1.2, 1.4 |
| 1.6 | Crear la aplicación productiva de MercadoPago con la cuenta real de CheatSheet, con la URL de retorno y la de notificaciones del dominio de producción | Analista de Integraciones | D-14 | PLAN-§2 |
| 1.7 | Iniciar la verificación del número de WhatsApp Business de la empresa piloto ante Meta, que demora entre 24 y 72 horas | Analista de Integraciones | D-10 | 1.2, PLAN-§2 |
| 1.8 | Congelar la versión a publicar: integrar `develop` en `main` con las pruebas del sistema aprobadas y etiquetar la versión. Desde este punto solo entran correcciones de bugs críticos | Gestión de Configuración y Documentación | D-7 | PLAN-§6 |
| 1.9 | Ensayar en staging la secuencia completa del día D: despliegue de la versión congelada, validación y vuelta atrás | Analista de Infraestructura y Datos | D-5 | 1.8, PLAN-§3, PLAN-§8 |
| 1.10 | Capacitar al Administrador de la empresa piloto con el manual de usuario, en staging | Analista Funcional y Diseño de Experiencia | D-5 a D-3 | 1.2, PLAN-§7 |
| 1.11 | Reunión de decisión: revisar el criterio de listo de esta sección y decidir si D se mantiene o se posterga | Arquitecto de Software | D-1 | 1.4 a 1.10, PLAN-§2 a PLAN-§8 |
| 1.12 | Desplegar en producción la versión congelada y verificar el estado de los servicios | Analista de Infraestructura y Datos | D, primera hora | 1.11, PLAN-§3 |
| 1.13 | Crear la empresa piloto y sus usuarios, cargar los datos iniciales y conectar ARCA, MercadoPago y WhatsApp desde Integraciones | Analista de QA, con el Administrador de la empresa piloto | D, después de 1.12 | PLAN-§4, PLAN-§5 |
| 1.14 | Ejecutar las pruebas de validación en producción, incluida la emisión de un primer comprobante con CAE y el pago de un primer cobro reales | Analista de QA | D, después de 1.13 | PLAN-§6 |
| 1.15 | Comunicar a la empresa piloto el inicio de operaciones, o activar la vuelta atrás si alguna validación falla | Arquitecto de Software | D, cierre | 1.14, PLAN-§7, PLAN-§8 |
| 1.16 | Revisar cada día la bitácora de operaciones y las incidencias reportadas, y clasificar cada una por severidad | Analista de QA | D+1 a D+14 | 1.15 |
| 1.17 | Medir los criterios de salida del piloto y decidir si el sistema se abre a nuevas empresas o el piloto se extiende | Arquitecto de Software | D+30 | 1.16 |

### Criterio de listo

La reunión de decisión (1.11) mantiene D solo si se cumplen todas estas condiciones. Si una falta,
D se posterga y se vuelve a fijar con la actividad 1.1.

- Las condiciones previas a D del método de implementación están cerradas.
- La empresa piloto delegó «Facturación Electrónica» en la CUIT de CheatSheet y la designación
  está aceptada en ARCA.
- La aplicación productiva de MercadoPago existe y su URL de retorno coincide, carácter por
  carácter, con la del panel de producción.
- El número de WhatsApp Business de la empresa piloto está verificado por Meta.
- La versión congelada pasó todas las pruebas del sistema en staging, sin bugs críticos abiertos.
- El ensayo de la actividad 1.9 terminó con el despliegue, la validación y la vuelta atrás
  completos.
- El Administrador de la empresa piloto completó la capacitación.
- Las secciones PLAN-§2 a PLAN-§8 están en estado listo.

La puesta en producción termina cuando la empresa piloto empieza a operar en D (actividad 1.15).
La actividad del plan termina con la decisión de la actividad 1.17.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| La empresa piloto no completa la delegación en ARCA antes de D | Media | Alto | Pedirla en D-14, con el paso a paso del capítulo de Integraciones del manual; la reunión de decisión posterga D si la designación no está aceptada |
| El certificado de plataforma productivo se demora o se gestiona con datos incorrectos | Baja | Alto | Gestionarlo en D-21, con margen de una semana antes de la delegación; el procedimiento ya se ejecutó completo en homologación |
| El certificado de plataforma vence sin aviso: hoy ningún control alerta su vencimiento | Media | Alto | Registrar la fecha de vencimiento en la entrega del entorno y programar la renovación con un mes de anticipación hasta que exista una alerta automática |
| Meta rechaza o demora la verificación del número de WhatsApp | Media | Medio | Iniciarla en D-10; si no está verificada en D-1, la empresa piloto arranca sin el agente de WhatsApp y los recordatorios, y se habilitan al verificarse |
| MercadoPago no deja operar la aplicación productiva con la cuenta de la empresa piloto | Baja | Alto | Conectar la cuenta real de la empresa piloto en D-3 desde una empresa de verificación en producción, sin cobrar, para confirmar la autorización antes de D |
| Se descubre un bug crítico entre el congelamiento y D | Media | Alto | Solo entran correcciones de bugs críticos, por rama de corrección y con las pruebas completas; si la corrección no llega a D-2, D se posterga |
| La decisión sobre el proveedor de alojamiento de producción no se toma a tiempo | Media | Alto | Es condición previa a D y se revisa en D-21; sin proveedor elegido no hay ensayo posible en D-5 |
| El Administrador de la empresa piloto no está disponible para la capacitación o para el día D | Baja | Medio | Designar un segundo usuario Administrador en la empresa piloto desde la actividad 1.2 |
