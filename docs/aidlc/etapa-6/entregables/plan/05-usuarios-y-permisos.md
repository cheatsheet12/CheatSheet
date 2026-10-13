---
entregable: plan
parte: 05-usuarios-y-permisos
responsable: Emanuel Gomez
estado: borrador
hu: [HU-E1-01, HU-E1-02, HU-E1-03, HU-E1-04, HU-E1-05, HU-E1-06, HU-E1-07]
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/inputs/historias-de-usuario.md
  - backend/src/cheatsheet/contexts/identity/application/usuarios.py
  - backend/src/cheatsheet/contexts/identity/application/autorizacion.py
  - backend/src/cheatsheet/contexts/identity/infrastructure/email_invitacion.py
  - backend/scripts/verify_rls.py
  - docs/staging-deployment.md
observaciones: >
  Las dependencias hacia PLAN-§2 y PLAN-§3 se citan a nivel de sección porque esas secciones
  todavía no están escritas; sus números de actividad se alinean cuando se publiquen. La 4.6 se
  cita según el borrador de PLAN-§4. En staging las invitaciones no se envían por email: el enlace
  queda en el log del worker (modo consola); producción necesita el correo transaccional, que es
  una de las credenciales que plan/00 pone como condición previa a D.
---

## 5. Usuarios, perfiles y permisos

### Objetivo

Dejar a cada persona de la empresa piloto con su cuenta activa y el rol que corresponde a su
tarea antes de D, y comprobar en producción que cada rol puede hacer exactamente lo que le toca y
nada más. CheatSheet tiene tres roles fijos, que no se configuran: **Administrador** (configura la
empresa, factura, cobra e invita usuarios), **Operador** (factura, cobra y agenda, sin tocar la
configuración) y **Solo Lectura** (consulta y descarga, sin modificar nada). Cada permiso se
controla dos veces: el panel no muestra la acción y la API la rechaza aunque se la llame
directamente.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 5.1 | Relevar con la empresa piloto quién va a usar el sistema y asignar a cada persona un rol según su tarea, con al menos dos Administradores | Analista Funcional y Diseño de Experiencia | D-14 | — |
| 5.2 | Configurar el correo transaccional de producción para el envío de invitaciones y verificar que una invitación de prueba llega a una casilla del equipo | Analista de Infraestructura y Datos | D-10 | PLAN-§2 |
| 5.3 | Registrar la empresa piloto con su primer Administrador: alta de la cuenta, aceptación de los términos y datos fiscales con el CUIT validado contra el padrón de ARCA (HU-E1-01, HU-E1-02, HU-E1-03) | Analista Funcional y Diseño de Experiencia | D-9 | 5.2, PLAN-§3 |
| 5.4 | Invitar al resto de las personas con el rol asignado en 5.1 y confirmar que cada una aceptó su invitación (HU-E1-04, HU-E1-05) | Analista Funcional y Diseño de Experiencia | D-7 | 5.1, 5.3 |
| 5.5 | Verificar que no quedan invitaciones pendientes ni cuentas de prueba, y que la empresa tiene dos Administradores activos | Analista de QA | D-6 | 5.4 |
| 5.6 | Verificar los permisos por rol en producción repitiendo los pasos de pantalla y de API de PRU-07, PRU-08 y PRU-09 con las cuentas reales, sin ejecutar ninguna operación con efecto fiscal ni monetario: cada acción prohibida debe responder 403 y no modificar datos | Analista de QA | D-3 | 5.5, 4.6 |
| 5.7 | Verificar el aislamiento entre empresas con `verify_rls.py` sobre la base de producción y con un usuario de otra empresa que intenta leer datos de la piloto | Analista de QA | D-3 | PLAN-§3 |
| 5.8 | Configurar con cada usuario sus preferencias de idioma, zona horaria y suscripciones a notificaciones (HU-E1-07) | Analista Funcional y Diseño de Experiencia | D-2 | 5.4 |
| 5.9 | Revisar con el Administrador de la piloto la lista de usuarios y sus roles; desactivar a quien ya no corresponda (HU-E1-06) | Analista de QA | D+7 y D+14 | 5.6 |

### Criterio de listo

- Cada persona relevada en 5.1 tiene su cuenta activa con el rol asignado, y no queda ninguna
  invitación pendiente ni cuenta de prueba.
- La empresa tiene al menos dos Administradores activos, de modo que la ausencia de uno no deja
  la configuración sin responsable.
- Las verificaciones de 5.6 y 5.7 terminan sin una sola acción prohibida aceptada y sin lectura
  de datos de otra empresa.
- El resultado de 5.6 y 5.7 queda registrado con fecha y responsable, y la bitácora muestra las
  altas, invitaciones y cambios de rol hechos en esta sección.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Las invitaciones no llegan porque el correo transaccional no está configurado o cae en spam | Media | Alto | 5.2 se valida con una casilla del equipo antes de invitar; si falla, el enlace se reenvía con «Reenviar» desde Usuarios una vez corregido el correo |
| Una persona recibe un rol con más permisos de los que su tarea necesita | Media | Alto | La asignación de 5.1 la valida el Administrador de la piloto y se revisa en 5.9; el rol se corrige al instante desde Usuarios |
| El único Administrador queda inactivo o pierde el acceso | Baja | Alto | 5.1 exige dos Administradores; el sistema impide quitar el rol o desactivar al último Administrador activo |
| Un permiso controlado solo en el panel queda abierto en la API | Baja | Crítico | 5.6 prueba cada acción prohibida llamando directamente a la API; un 403 faltante es un bug crítico y D no avanza (PLAN-§8) |
| Un usuario de otra empresa accede a datos de la piloto | Baja | Crítico | 5.7 corre `verify_rls.py` y la prueba cruzada; si falla, la base no se usa y D no avanza |
| Quedan en producción cuentas creadas para pruebas | Media | Medio | 5.5 revisa la lista de usuarios antes de D y desactiva toda cuenta que no figure en 5.1 |
