---
entregable: plan
parte: 02-entorno-de-produccion
responsable: Juan Caballero
estado: borrador
hu: []
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/etapa-6/entregables/plan/01-puesta-en-produccion.md
  - docs/adr/0005-staging-database-neon.md
  - docs/adr/0006-staging-hosting-render.md
  - docs/staging-deployment.md
  - docs/staging-database.md
  - docs/configuration-management.md
  - render.yaml
  - backend/Dockerfile
  - backend/.env.example
  - backend/src/cheatsheet/platform/settings.py
  - backend/scripts/provision_app_role.py
  - backend/scripts/verify_rls.py
  - docs/aidlc/TODO.md
observaciones: >
  La sección propone el entorno de producción a partir de staging; no lo da por decidido. La
  elección de proveedor queda en la actividad 2.1 y se registra en un ADR, como pide ADR-0006.
  Alineada con PLAN-§1: el certificado de plataforma de ARCA (1.4) y la aplicación productiva de
  MercadoPago (1.6) se gestionan allí, y esta sección solo los carga en el entorno; las
  integraciones de la empresa piloto se conectan el día D (1.13). Las actividades 2.1, 2.2 y 2.3
  cubren las condiciones previas a D que la introducción del plan asigna a esta sección.
  Al cierre de esta sección GitHub Actions no tiene minutos disponibles en la cuenta del
  proyecto (riesgo listado): el despliegue automatizado que se describe no corre hasta resolverlo.
---

## 2. Preparar el entorno de producción

### Objetivo

Dejar listo, antes del despliegue (PLAN-§3), un entorno de producción **separado de staging**
donde la empresa piloto opere con datos y servicios reales: base de datos, procesos del sistema,
almacenamiento, credenciales de las integraciones y monitoreo. El entorno replica la forma de
staging, que ya está verificada (ADR-0005, ADR-0006, `render.yaml`), y cambia lo que staging
resuelve de forma provisoria: integraciones simuladas, planes que suspenden los servicios inactivos,
base de datos en otra región que el cómputo, y Beat dentro del worker.

El sistema protege este paso por sí mismo: con `APP_ENV=production`, `platform/settings.py` rechaza
cualquier adaptador simulado (ARCA, MercadoPago, WhatsApp, correo, planillas, modelo de lenguaje,
almacenamiento) y el proceso no arranca. Una variable faltante se detecta al iniciar el servicio,
no en una operación de la empresa piloto.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 2.1 | Decidir el proveedor de alojamiento de producción y registrarlo en un ADR. Propuesta: mantener Render para la API, el panel, el worker y Redis, como en staging, y ubicar la base de datos **en la misma región que el cómputo** para eliminar la latencia entre regiones que staging tiene hoy. La alternativa de llevar el panel a Vercel, que plantea `docs/architecture.md`, se evalúa en el mismo ADR | Arquitecto de Software | D-21 | — |
| 2.2 | Verificar que las unidades pendientes que la introducción del plan pone como condición previa a D estén integradas en `main`: canal real de WhatsApp para recordatorios y avisos, y proveedores de embeddings y de transcripción | Arquitecto de Software | D-21 | 1.3 |
| 2.3 | Obtener las credenciales de producción que no gestiona PLAN-§1 (el certificado de ARCA es la actividad 1.4 y la aplicación de MercadoPago, la 1.6): aplicación de Meta con WhatsApp Business, cliente OAuth2 de Google con las APIs de Sheets, Drive y Picker, clave de la API del modelo de lenguaje y proveedor de correo transaccional por SMTP | Analista de Integraciones | D-21 | 1.3 |
| 2.4 | Crear el proyecto de base de datos de producción, PostgreSQL 16 con `pgvector` y `btree_gist`, **distinto del de staging**, en un plan que no suspenda el cómputo y que incluya respaldo automático y restauración a un punto en el tiempo | Analista de Infraestructura y Datos | D-20 | 2.1 |
| 2.5 | Crear el rol de la aplicación con `backend/scripts/provision_app_role.py` (nunca desde la consola del proveedor, que le otorga `BYPASSRLS`) y aplicar las migraciones con el rol dueño | Analista de Infraestructura y Datos | D-19 | 2.4 |
| 2.6 | Ejecutar `backend/scripts/verify_rls.py` contra la base de producción vacía y conservar la salida como evidencia del aislamiento entre empresas | Analista de Infraestructura y Datos | D-19 | 2.5 |
| 2.7 | Crear Redis de producción en la misma región que el cómputo, con política `noeviction` y en un plan sin suspensión | Analista de Infraestructura y Datos | D-19 | 2.1 |
| 2.8 | Crear el bucket de almacenamiento de objetos de producción, separado del de staging, con una credencial de lectura y escritura limitada a ese bucket | Analista de Infraestructura y Datos | D-19 | 2.1 |
| 2.9 | Crear los servicios a partir de `render.yaml`, apuntando a la rama `main` y con el despliegue automático desactivado: la API con `backend/Dockerfile` y control de salud en `/health/live`; el panel en Node 22; el worker de Celery **sin** Beat, y Beat como un servicio aparte de una sola instancia, para poder escalar el worker sin duplicar las tareas programadas | Analista de Infraestructura y Datos | D-18 | 2.5, 2.7, 2.8 |
| 2.10 | Generar los secretos propios del entorno, `JWT_SECRET` y `SECRETS_ENCRYPTION_KEY`, **distintos de los de staging**, y guardarlos el mismo día en el gestor de contraseñas del equipo. La clave de cifrado no se regenera nunca: cifra las credenciales de las integraciones de cada empresa | Analista de Infraestructura y Datos | D-18 | 2.9 |
| 2.11 | Configurar el dominio del panel y de la API, con TLS, y fijar `APP_BASE_URL` con la dirección pública del panel en la API, el worker y el panel | Analista de Infraestructura y Datos | D-17 | 2.9 |
| 2.12 | Registrar las direcciones de producción en cada proveedor: el `redirect_uri` de MercadoPago, idéntico a `APP_BASE_URL`; las URL de los webhooks de MercadoPago y de WhatsApp; los orígenes y las direcciones de retorno del cliente OAuth2 de Google | Analista de Integraciones | D-12 | 1.6, 2.3, 2.11 |
| 2.13 | Cargar las variables de entorno de producción en la API, el worker y Beat, con `APP_ENV=production` y los adaptadores reales: `ARCA_ADAPTADOR=arca`, `MERCADOPAGO_ADAPTADOR=mercadopago`, `WHATSAPP_ADAPTADOR=meta`, `EMAIL_ADAPTADOR=smtp`, `PLANILLA_ADAPTADOR=google`, `LLM_ADAPTADOR=anthropic`, `ALMACENAMIENTO_ADAPTADOR=r2`, con sus credenciales | Analista de Infraestructura y Datos | D-10 | 1.4, 1.6, 2.3, 2.10, 2.12 |
| 2.14 | Configurar el pipeline de despliegue a producción: los secretos del repositorio para producción (direcciones de la base, ganchos de despliegue de cada servicio, URL pública de la API) y un trabajo que despliega desde `main` solo con aprobación manual, con la misma secuencia que staging: CI en verde, migraciones, verificación del aislamiento, despliegue y control de salud | Gestión de Configuración y Documentación | D-9 | 2.9 |
| 2.15 | Configurar el monitoreo: un control externo de disponibilidad sobre `/health`, la retención de los registros de cada servicio y el aviso al equipo cuando un servicio deja de responder | Analista de Infraestructura y Datos | D-8 | 2.9 |
| 2.16 | Verificar el entorno vacío: `/health` responde 200 con base de datos y Redis disponibles; `verify_rls.py` termina sin errores; los cuatro servicios arrancan con `APP_ENV=production`, lo que prueba que las credenciales de plataforma están cargadas; el panel carga y la pantalla de ingreso responde. La conexión de cada integración se verifica el día D con la empresa piloto (actividad 1.13 y HU-E2-05 — Validar el estado de una conexión externa) | Analista de QA | D-7 | 2.6, 2.13, 2.14, 2.15 |

### Criterio de listo

El entorno de producción está listo para el despliegue cuando se cumple todo esto:

- El ADR de la actividad 2.1 está aprobado y el entorno coincide con lo que decide.
- La base de producción es distinta de la de staging, tiene respaldo automático activo y
  `verify_rls.py` termina sin errores contra ella.
- La API, el panel, el worker y Beat arrancan con `APP_ENV=production`, lo que prueba que ningún
  adaptador simulado quedó configurado.
- `JWT_SECRET` y `SECRETS_ENCRYPTION_KEY` son propios del entorno y están guardados en el gestor de
  contraseñas del equipo.
- Las credenciales de plataforma de ARCA, MercadoPago, WhatsApp, Google, el modelo de lenguaje y
  el correo están cargadas, y su conexión queda lista para verificarse el día D (actividad 1.13).
- El pipeline despliega desde `main` solo con aprobación manual y aborta si la verificación del
  aislamiento falla.
- El control de disponibilidad avisa al equipo cuando `/health` deja de responder.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| La delegación del servicio de facturación ante ARCA o la revisión de la aplicación de Meta demoran más que la ventana de preparación | Media | Alto | Iniciar los trámites en D-21 (actividades 1.4, 1.7 y 2.3). La reunión de decisión (actividad 1.11) posterga D si falta una credencial |
| GitHub Actions sin minutos disponibles en la cuenta del proyecto, como ocurre hoy en staging, deja sin correr el CI y el despliegue automatizado | Alta | Alto | Resolver el plan de la cuenta antes de D-9. Mientras tanto, desplegar a mano siguiendo la misma secuencia de PLAN-§3: migraciones, `verify_rls.py`, despliegue y control de salud |
| El rol de la aplicación se crea desde la consola del proveedor, hereda `BYPASSRLS` y el aislamiento entre empresas deja de aplicarse sin ningún error visible | Baja | Alto | Crear el rol solo con `provision_app_role.py`, que se niega a informar éxito si el rol puede saltear RLS, y exigir `verify_rls.py` en verde (actividad 2.6) |
| Se pierde o se regenera `SECRETS_ENCRYPTION_KEY` y las credenciales de las integraciones quedan ilegibles | Baja | Alto | Guardarla en el gestor de contraseñas el mismo día (actividad 2.10). Una rotación exige volver a cifrar las credenciales guardadas |
| Se reutilizan la base, el bucket o los secretos de staging y se mezclan datos de prueba con datos reales | Baja | Alto | Recursos y secretos propios en cada actividad. La verificación de la actividad 2.16 se hace con el entorno vacío |
| Latencia entre regiones si el cómputo y la base de datos quedan separados, como en staging | Media | Medio | Decidirlo en el ADR de la actividad 2.1, con la base en la misma región que el cómputo |
| Costo de los planes sin suspensión, que staging evita con planes gratuitos | Alta | Medio | Dimensionar para una sola empresa piloto y ampliar recién en la etapa de evaluación del piloto |
