---
entregable: plan
parte: 03-despliegue
responsable: Juan Caballero
estado: borrador
hu: []
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/etapa-6/entregables/plan/02-entorno-de-produccion.md
  - docs/configuration-management.md
  - docs/staging-deployment.md
  - docs/adr/0006-staging-hosting-render.md
  - .github/workflows/ci.yml
  - backend/alembic.ini
  - backend/scripts/verify_rls.py
observaciones: >
  La secuencia de despliegue repite la que staging ya ejecuta en cada cambio sobre develop (job
  deploy-staging de ci.yml): CI en verde, migraciones, verificación del aislamiento, despliegue y
  control de salud. Lo nuevo para producción es la rama main, la aprobación manual, el respaldo
  previo y el congelamiento de cambios durante el piloto. La vuelta atrás de una versión está en
  PLAN-§8. Depende de PLAN-§2, que también está en borrador.
---

## 3. Realizar el despliegue

### Objetivo

Publicar en el entorno de producción (PLAN-§2) **una versión identificada** del sistema, que ya pasó
por staging, con la base de datos migrada y el aislamiento entre empresas verificado, de forma que
la carga inicial (PLAN-§4) arranque sobre un sistema estable. El mismo procedimiento se usa después
para publicar las correcciones del período de estabilización.

La versión se publica desde la rama `main`, que según la gestión de configuración solo recibe
cambios desde `develop` por un Pull Request aprobado, o desde una rama `hotfix/` ante una falla
crítica. El orden de los pasos es el que staging aplica hoy en cada cambio: **CI en verde,
migraciones, verificación del aislamiento, despliegue de cada servicio y control de salud**. Si un
paso falla, los siguientes no corren y el entorno sigue con la versión anterior.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 3.1 | Cerrar el alcance de la versión: solo entran a `develop` los cambios ya aprobados que la empresa piloto va a usar, y se confirma que no queda ningún bug crítico abierto | Gestión de Configuración y Documentación | D-9 | 2.2 |
| 3.2 | Verificar la versión candidata en staging: CI en verde, las pruebas PRU-01 a PRU-09 en estado Aprobada o Re-ejecutada, y una recorrida de los módulos que usa la empresa piloto con los tres roles | Analista de QA | D-9 | 3.1 |
| 3.3 | Abrir el Pull Request de `develop` a `main`, revisarlo y aprobarlo. Al mergear, marcar el commit con una etiqueta de versión (por ejemplo `v1.0.0`) y registrar en las notas de la versión qué historias incluye | Gestión de Configuración y Documentación | D-8 | 3.2 |
| 3.4 | Tomar un respaldo de la base de producción antes de migrar y anotar su identificador. En el primer despliegue la base está vacía, pero el paso se ejecuta igual para dejar probado el procedimiento que se repite en cada corrección | Analista de Infraestructura y Datos | D-7 | 2.4, 3.3 |
| 3.5 | Aprobar el trabajo de despliegue a producción y aplicar las migraciones (`alembic -c backend/alembic.ini upgrade head`) con el rol dueño de la base | Analista de Infraestructura y Datos | D-7 | 2.14, 3.4 |
| 3.6 | Ejecutar `backend/scripts/verify_rls.py` contra la base migrada. Si termina con error, el despliegue se detiene antes de publicar ningún servicio | Analista de Infraestructura y Datos | D-7 | 3.5 |
| 3.7 | Publicar los servicios en este orden: API, worker, Beat y panel. El worker y Beat se publican siempre junto con la API, porque un worker con código anterior contra un esquema nuevo procesa tareas a medias en lugar de fallar | Analista de Infraestructura y Datos | D-7 | 2.13, 3.6 |
| 3.8 | Confirmar el control de salud: `/health` responde 200 con base de datos y Redis disponibles dentro de los diez minutos, y la versión publicada en cada servicio coincide con la etiqueta de la actividad 3.3 | Analista de Infraestructura y Datos | D-7 | 3.7 |
| 3.9 | Ejecutar la prueba de humo sobre la versión publicada: iniciar sesión en el panel, recorrer cada módulo sin modificar datos y verificar cada integración desde «Integraciones» | Analista de QA | D-7 | 3.8 |
| 3.10 | Registrar el despliegue: etiqueta, commit, identificador del respaldo, hora y resultado de cada paso, y avisar al equipo que el entorno queda listo para la carga inicial | Gestión de Configuración y Documentación | D-7 | 3.9 |
| 3.11 | Iniciar el congelamiento de cambios: desde este momento y hasta D+14 solo se publican en producción correcciones por rama `hotfix/`, que vuelven a pasar por las actividades 3.4 a 3.10 y se integran también en `develop`. Durante el piloto no se publican migraciones que borren o renombren columnas | Gestión de Configuración y Documentación | D-6 a D+14 | 3.10 |
| 3.12 | Confirmar el día anterior a la puesta en producción que la versión publicada sigue siendo la etiquetada, que `/health` responde 200 y que el control de disponibilidad no registró caídas desde el despliegue | Analista de Infraestructura y Datos | D-1 | 3.11 |

### Criterio de listo

El despliegue está terminado cuando se cumple todo esto:

- La versión publicada en la API, el worker, Beat y el panel es la misma y coincide con una
  etiqueta de `main`.
- Las migraciones están aplicadas y `verify_rls.py` terminó sin errores contra la base de
  producción.
- `/health` responde 200 y la prueba de humo de la actividad 3.9 no encontró errores.
- Existe un respaldo de la base tomado antes de la migración, con su identificador registrado.
- El despliegue quedó registrado y el equipo fue avisado de que puede comenzar la carga inicial.
- El congelamiento de cambios y el procedimiento de `hotfix/` están comunicados al equipo.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Una migración falla en producción | Baja | Alto | El trabajo de despliegue se detiene antes de publicar los servicios y el entorno sigue con la versión anterior. Se corrige la migración en `develop` y se repite desde la actividad 3.3 |
| El worker o Beat quedan con una versión anterior a la de la API | Media | Alto | Publicar los cuatro servicios en el mismo trabajo (actividad 3.7) y comparar la versión de cada uno en la actividad 3.8 |
| Una migración destructiva deja una ventana en que el código anterior no puede leer el esquema nuevo | Baja | Alto | Durante el piloto solo se publican migraciones que agregan; un cambio que quita columnas se hace en dos versiones, primero dejando de usarlas y después borrándolas |
| GitHub Actions sin minutos disponibles impide correr el CI y el trabajo de despliegue | Alta | Alto | Resolver el plan de la cuenta antes de D-9 (PLAN-§2). Si no se resuelve, ejecutar a mano los mismos pasos en el mismo orden, con dos integrantes presentes y registrando cada salida |
| Un gancho de despliegue se filtra y alguien publica una versión sin pasar por el pipeline | Baja | Medio | Tratar los ganchos como credenciales: solo en los secretos del repositorio, nunca en un archivo ni en un registro. Rotarlos si se sospecha una filtración |
| La versión publicada tiene un defecto que aparece recién con la operación de la empresa piloto | Media | Alto | Corregir por `hotfix/` siguiendo las actividades 3.4 a 3.10. Si la falla afecta comprobantes, cobros o datos de otra empresa, aplicar la vuelta atrás de PLAN-§8 |
