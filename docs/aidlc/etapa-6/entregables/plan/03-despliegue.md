---
entregable: plan
parte: 03-despliegue
responsable: Juan Caballero
estado: borrador
hu: []
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/etapa-6/entregables/plan/01-puesta-en-produccion.md
  - docs/aidlc/etapa-6/entregables/plan/02-entorno-de-produccion.md
  - docs/configuration-management.md
  - docs/staging-deployment.md
  - docs/adr/0006-staging-hosting-render.md
  - .github/workflows/ci.yml
  - backend/alembic.ini
  - backend/scripts/verify_rls.py
observaciones: >
  Alineada con PLAN-§1: la versión se congela y se etiqueta en la actividad 1.8 (D-7), el ensayo
  en staging es la actividad 1.9 (D-5) y el despliegue en producción ocurre el día D a primera
  hora (1.12), antes de crear la empresa piloto (1.13). Esta sección detalla cómo se ejecutan
  esos pasos. La secuencia repite la que staging ya ejecuta en cada cambio sobre develop (job
  deploy-staging de ci.yml): CI en verde, migraciones, verificación del aislamiento, despliegue y
  control de salud. La vuelta atrás de una versión está en PLAN-§8.
---

## 3. Realizar el despliegue

### Objetivo

Publicar en el entorno de producción (PLAN-§2) la versión congelada en la actividad 1.8, con la
base de datos migrada y el aislamiento entre empresas verificado, el día D antes de que se cree la
empresa piloto y se carguen sus datos (actividad 1.13 y PLAN-§4). El mismo procedimiento se usa
después para publicar las correcciones del período de estabilización.

La versión se publica desde una etiqueta de la rama `main`, que según la gestión de configuración
solo recibe cambios desde `develop` por un Pull Request aprobado, o desde una rama `hotfix/` ante
una falla crítica. El orden de los pasos es el que staging aplica hoy en cada cambio: **CI en
verde, migraciones, verificación del aislamiento, despliegue de cada servicio y control de
salud**. Si un paso falla, los siguientes no corren y el entorno sigue con la versión anterior.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 3.1 | Verificar que la etiqueta creada en la actividad 1.8 corresponde a la versión que pasó las pruebas del sistema en staging: mismo commit, CI en verde y las pruebas PRU-01 a PRU-09 en estado Aprobada o Re-ejecutada | Analista de QA | D-7 | 1.8 |
| 3.2 | Preparar el trabajo de despliegue a producción para esa etiqueta: secretos del repositorio, ganchos de despliegue de cada servicio y aprobación manual obligatoria | Gestión de Configuración y Documentación | D-6 | 2.14, 3.1 |
| 3.3 | Ensayar en staging, como parte de la actividad 1.9, la secuencia completa de las actividades 3.5 a 3.10 con la versión congelada, y registrar cuánto dura cada paso | Analista de Infraestructura y Datos | D-5 | 3.2 |
| 3.4 | Confirmar que no entró ningún cambio a `main` después de la etiqueta, que el entorno de producción sigue respondiendo y que el control de disponibilidad no registró caídas, como insumo de la reunión de decisión (actividad 1.11) | Analista de Infraestructura y Datos | D-1 | 2.16, 3.3 |
| 3.5 | Tomar un respaldo de la base de producción antes de migrar y anotar su identificador. En el primer despliegue la base está vacía, pero el paso se ejecuta igual para dejar probado el procedimiento que se repite en cada corrección | Analista de Infraestructura y Datos | D, primera hora | 1.11, 3.4 |
| 3.6 | Aprobar el trabajo de despliegue y aplicar las migraciones (`alembic -c backend/alembic.ini upgrade head`) con el rol dueño de la base | Analista de Infraestructura y Datos | D, primera hora | 3.5 |
| 3.7 | Ejecutar `backend/scripts/verify_rls.py` contra la base migrada. Si termina con error, el despliegue se detiene antes de publicar ningún servicio | Analista de Infraestructura y Datos | D, primera hora | 3.6 |
| 3.8 | Publicar los servicios en este orden: API, worker, Beat y panel. El worker y Beat se publican siempre junto con la API, porque un worker con código anterior contra un esquema nuevo procesa tareas a medias en lugar de fallar | Analista de Infraestructura y Datos | D, primera hora | 3.7 |
| 3.9 | Confirmar el control de salud: `/health` responde 200 con base de datos y Redis disponibles dentro de los diez minutos, y la versión publicada en cada servicio coincide con la etiqueta de la actividad 1.8 | Analista de Infraestructura y Datos | D, primera hora | 3.8 |
| 3.10 | Ejecutar la prueba de humo: el panel carga, la pantalla de ingreso responde y los registros de los cuatro servicios no muestran errores al arrancar | Analista de QA | D, primera hora | 3.9 |
| 3.11 | Registrar el despliegue (etiqueta, commit, identificador del respaldo, hora y resultado de cada paso) y avisar que puede comenzar la actividad 1.13 | Gestión de Configuración y Documentación | D, primera hora | 3.10 |
| 3.12 | Sostener el congelamiento de cambios durante la estabilización: solo se publican correcciones por rama `hotfix/`, que repiten las actividades 3.5 a 3.11 y se integran también en `develop`. No se publican migraciones que borren o renombren columnas | Gestión de Configuración y Documentación | D+1 a D+14 | 3.11 |

### Criterio de listo

El despliegue está terminado cuando se cumple todo esto:

- La versión publicada en la API, el worker, Beat y el panel es la misma y coincide con la etiqueta
  de la actividad 1.8.
- Las migraciones están aplicadas y `verify_rls.py` terminó sin errores contra la base de
  producción.
- `/health` responde 200 y la prueba de humo de la actividad 3.10 no encontró errores.
- Existe un respaldo de la base tomado antes de la migración, con su identificador registrado.
- La secuencia se ensayó antes en staging y su duración entra en la primera hora del día D.
- El despliegue quedó registrado y el equipo fue avisado de que puede comenzar la actividad 1.13.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Una migración falla en producción | Baja | Alto | El trabajo de despliegue se detiene antes de publicar los servicios y el entorno sigue con la versión anterior. Se posterga el inicio de la actividad 1.13 y se aplica PLAN-§8 si corresponde |
| El worker o Beat quedan con una versión anterior a la de la API | Media | Alto | Publicar los cuatro servicios en el mismo trabajo (actividad 3.8) y comparar la versión de cada uno en la actividad 3.9 |
| La secuencia tarda más que la primera hora del día D y demora el inicio de operaciones | Media | Medio | Medir la duración en el ensayo de la actividad 3.3 y llevar el dato a la reunión de decisión (actividad 1.11) |
| Una migración destructiva deja una ventana en que el código anterior no puede leer el esquema nuevo | Baja | Alto | Durante el piloto solo se publican migraciones que agregan; un cambio que quita columnas se hace en dos versiones, primero dejando de usarlas y después borrándolas |
| GitHub Actions sin minutos disponibles impide correr el CI y el trabajo de despliegue | Alta | Alto | Resolver el plan de la cuenta antes de D-6 (PLAN-§2). Si no se resuelve, ejecutar a mano los mismos pasos en el mismo orden, con dos integrantes presentes y registrando cada salida |
| Un gancho de despliegue se filtra y alguien publica una versión sin pasar por el pipeline | Baja | Medio | Tratar los ganchos como credenciales: solo en los secretos del repositorio, nunca en un archivo ni en un registro. Rotarlos si se sospecha una filtración |
| La versión publicada tiene un defecto que aparece recién con la operación de la empresa piloto | Media | Alto | Corregir por `hotfix/` siguiendo la actividad 3.12. Si la falla afecta comprobantes, cobros o datos de otra empresa, aplicar la vuelta atrás de PLAN-§8 |
