---
entregable: matriz
parte: filas-suarez
responsable: Cristian Suarez
estado: borrador
hu: [HU-E1-01, HU-E1-02, HU-E1-03, HU-E1-04, HU-E1-05, HU-E1-06, HU-E1-07, HU-E2-01, HU-E2-02, HU-E2-03, HU-E2-04, HU-E2-05]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - docs/aidlc/inputs/der.md
  - backend/src/cheatsheet/contexts/identity/
  - backend/src/cheatsheet/contexts/integrations/
  - frontend/src/features/identity/
  - frontend/src/features/integrations/
observaciones: >
  Prueba manual en staging del 11/10/2026 sobre Estudio Ejemplo SRL (30-00000001-5) con los tres
  roles. Bugs encontrados y corregidos: 403 por rol en nueve módulos (PR #135), frase del 403 en el
  BFF (PR #136), redirecciones armadas con el host interno de Render en la renovación de sesión y en
  la vuelta de Google Sheets (mayor, rama fix/frontend-redireccion-con-url-publica), y el padrón
  consultado con un CUIT mal formado (menor, rama fix/identity-padron-valida-el-cuit). HU-E1-01 y
  HU-E2-04 pasan a Probado cuando se mergee la corrección de las redirecciones. Diferencias menores
  de texto con la HU, sin bloquear: «Ese email ya tiene una cuenta. ¿Iniciar sesión?»,
  «Ingresá los 11 dígitos del CUIT», la razón social vacía no muestra «Este campo es obligatorio»
  (sí deshabilita Guardar) y la cabecera muestra el rol como «solo_lectura». Para el integrador de
  la V4: «Real · validada» es un valor nuevo de Integración real, para un adaptador real ejercitado
  contra el servicio externo (homologación o sandbox).
---

## Filas — Cristian Suarez

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |
|---|---|---|---|---|---|---|---|---|
| Identidad y Acceso | Registrar empresa e iniciar sesión | HU-E1-01 | Administrador | Empresa, Usuario | PAN-ONB-01 | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Identidad y Acceso | Configurar datos de la empresa | HU-E1-02 | Administrador | Empresa | PAN-ONB-02 | Probado | Real · validada | 11/10/2026 |
| Identidad y Acceso | Aceptar los términos y condiciones del servicio | HU-E1-03 | Administrador | Empresa, Usuario | PAN-ONB-01 | Probado | No aplica | 11/10/2026 |
| Usuarios y Permisos | Registrar un nuevo usuario en la empresa | HU-E1-04 | Administrador | Usuario | PAN-USR-01 | Probado | Simulada · pendiente de validar | 11/10/2026 |
| Usuarios y Permisos | Asignar o cambiar el rol de un usuario | HU-E1-05 | Administrador | Usuario | PAN-USR-01 | Probado | No aplica | 11/10/2026 |
| Usuarios y Permisos | Desactivar el acceso de un usuario | HU-E1-06 | Administrador | Usuario | PAN-USR-01 | Probado | No aplica | 11/10/2026 |
| Usuarios y Permisos | Actualizar preferencias personales | HU-E1-07 | Administrador, Operador, Solo Lectura | Usuario | PAN-USR-02 | Probado | No aplica | 11/10/2026 |
| Integraciones Externas | Conectar cuenta de ARCA con credenciales validadas | HU-E2-01 | Administrador | ConfiguracionDeIntegracion | PAN-CFG-INT | Probado | Real · validada | 11/10/2026 |
| Integraciones Externas | Conectar cuenta de MercadoPago | HU-E2-02 | Administrador | ConfiguracionDeIntegracion | PAN-CFG-INT | Probado | Real · validada | 11/10/2026 |
| Integraciones Externas | Conectar cuenta de WhatsApp | HU-E2-03 | Administrador | ConfiguracionDeIntegracion | PAN-CFG-INT | Codificado | Simulada · pendiente de validar | 20/10/2026 |
| Integraciones Externas | Vincular planilla de Google Sheets o Excel | HU-E2-04 | Administrador | VinculoDePlanilla | PAN-ING-01 | Codificado | Simulada · pendiente de validar | 13/10/2026 |
| Integraciones Externas | Validar el estado de una conexión externa | HU-E2-05 | Administrador, Operador | ConfiguracionDeIntegracion | PAN-CFG-INT | Probado | Real · validada | 11/10/2026 |

### Qué respalda cada estado

| HU | Prueba manual en staging (11/10/2026) |
|---|---|
| HU-E1-01 | Email inválido, contraseña corta y email ya registrado se rechazan; el inicio de sesión con credenciales correctas funciona. Pendiente: la renovación de sesión redirigía al host interno (corregido, sin mergear). El ingreso con Google no se ejercitó: Google no está configurado en staging |
| HU-E1-02 | CUIT válido consultado al padrón (simulado en staging; el real se validó contra homologación el 08/10/2026); CUIT inexistente informado; formato inválido frenado en el panel |
| HU-E1-03 | Sin aceptar los términos el alta se rechaza con el mensaje de la HU; la re-aceptación de una versión nueva se pidió y registró |
| HU-E1-04 | Invitaciones de Solo Lectura y Operador enviadas y aceptadas; email ya existente (409) y sin rol (422) rechazados; el envío por email está en modo consola en staging |
| HU-E1-05 | Cambio de rol aplicado y revertido; el último Administrador no pierde el rol (409); el Operador no tiene la acción (PRU-08); queda en la bitácora |
| HU-E1-06 | Desactivación y reactivación con el rol anterior; el último Administrador no se desactiva (409); la desactivación revoca sesiones y queda en la bitácora |
| HU-E1-07 | Preferencias de idioma, zona horaria y suscripciones leídas y guardadas |
| HU-E2-01 | Delegación verificada contra ARCA homologación y CAE obtenido en staging (Factura A 0003-00000001, CAE 86410985729308) |
| HU-E2-02 | Vendedor de prueba conectado por OAuth contra MercadoPago y cuenta real rechazada (06/10/2026); la conexión sigue «Conectada» en la verificación del 11/10/2026. El pago de un cobro sigue bloqueado (TODO §29.1), lo que afecta a HS-T1 y no a esta HU |
| HU-E2-03 | No ejecutada: requiere la aplicación de Meta y el número de prueba del canal real de WhatsApp |
| HU-E2-04 | Vínculo creado con el adaptador simulado de Google; la vuelta al panel redirigía al host interno (corregido, sin mergear) |
| HU-E2-05 | «Verificar estado» consulta ARCA y MercadoPago reales y muestra la hora de verificación; una integración sin conectar ofrece «Conectar» |
