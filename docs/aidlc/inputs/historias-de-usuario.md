# **Épica 1 — Onboarding y Gestión de la Organización**

**Bounded Contexts asociados:** BC1 Identidad y Organización
**Acciones de dominio (Bloque K):** RegistrarEmpresa, RegistrarUsuario, CambiarRolDeUsuario, ActualizarPreferencias
Esta épica agrupa las historias relativas al alta de la empresa en la plataforma, la aceptación del marco contractual, y la gestión de los usuarios que operan el sistema con sus respectivos roles y preferencias personales. Los mensajes de validación entre comillas son textos del sistema.

## **HU-E1-01 — Registrar empresa e iniciar sesión**

| ID | HU-E1-01 |
| :---- | :---- |
| **Actor** | Administrador (nuevo usuario) |
| **Acción Bloque K** | RegistrarEmpresa |
| **Descripción** | Como nuevo usuario, quiero registrarme en CheatSheet con email y contraseña o con mi cuenta de Google, para acceder a la plataforma y comenzar a configurar mi empresa. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-ONB-01 (Onboarding — Inicio de sesión) |

**Precondiciones**

* El usuario no tiene cuenta registrada en CheatSheet.
* El usuario tiene acceso a internet y un navegador compatible.

**Reglas de negocio**

* RN-01: El registro con email requiere una contraseña de mínimo 8 caracteres. El sistema no define complejidad adicional en esta versión.
* RN-02: El registro con Google utiliza OAuth2. CheatSheet solicita únicamente el email y nombre del perfil de Google; no accede a otros datos de la cuenta.
* RN-03: Un email ya registrado no puede usarse para crear una nueva cuenta. El sistema informa al usuario y ofrece la opción de iniciar sesión.
* RN-04: Al completar el registro exitosamente, el sistema redirige automáticamente al paso 2 del onboarding. El usuario no puede acceder al dashboard hasta completar los pasos 1 y 2.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Completo el formulario con email y contraseña válidos y hago clic en “Ingresar” | El sistema crea la cuenta y me redirige al paso 2 del onboarding | PAN-ONB-02 |
| Hago clic en “Continuar con Google” y autorizo el acceso | El sistema crea la cuenta con los datos de Google y me redirige al paso 2 | PAN-ONB-02 |
| Ingreso un email ya registrado | El sistema muestra “Ese email ya tiene una cuenta asociada. ¿Desea iniciar sesión?” | PAN-ONB-01 |
| Ingreso una contraseña menor a 8 caracteres | El sistema muestra “La contraseña debe tener al menos 8 caracteres.” y bloquea el registro | PAN-ONB-01 |
| Ingreso un email con formato inválido | El sistema muestra “Ingrese un email válido.” y no permite continuar | PAN-ONB-01 |
| Ingreso credenciales correctas en el login | El sistema inicia sesión y me redirige al dashboard o al paso pendiente del onboarding | PAN-ONB-01 |

## **HU-E1-02 — Configurar datos de la empresa**

| ID | HU-E1-02 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | RegistrarEmpresa |
| **Descripción** | Como administrador, quiero ingresar los datos fiscales de mi empresa, para que CheatSheet pueda conectarse con ARCA y operar en mi nombre desde el inicio. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-ONB-02 (Onboarding — Datos de empresa) |

**Precondiciones**

* El usuario completó el paso 1 del onboarding (HU-E1-01).
* El usuario tiene a mano el CUIT de la empresa y datos del responsable.

**Reglas de negocio**

* RN-01: El CUIT ingresado es validado contra ARCA en tiempo real. Un CUIT inválido o inexistente bloquea el avance al paso siguiente.
* RN-02: La condición IVA se determina automáticamente a partir del CUIT validado. El usuario puede corregirla manualmente si difiere.
* RN-03: Los campos obligatorios son: nombre comercial, CUIT, condición IVA, nombre del responsable y email de contacto.
* RN-04: Este paso es bloqueante. El usuario no puede acceder al dashboard ni al paso 3 sin completarlo.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso un CUIT válido | El sistema lo valida contra ARCA, completa automáticamente la condición IVA y habilita el resto del formulario | PAN-ONB-02 |
| Ingreso un CUIT con formato inválido | El sistema muestra “El CUIT debe contener 11 dígitos.” y no consulta a ARCA | PAN-ONB-02 |
| Ingreso un CUIT inexistente en el padrón de ARCA | El sistema muestra “No se encontró el CUIT en el padrón de ARCA.” y bloquea el avance | PAN-ONB-02 |
| Intento avanzar sin completar todos los campos obligatorios | El sistema marca los campos faltantes con “Este campo es obligatorio.” y bloquea el botón Continuar | PAN-ONB-02 |
| Completo todos los campos y hago clic en Continuar | El sistema guarda los datos y me redirige al paso 3 de integraciones | PAN-ONB-03 |

## **HU-E1-03 — Aceptar los términos y condiciones del servicio**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E1-03 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | RegistrarEmpresa |
| **Descripción** | Como administrador, quiero aceptar los términos y condiciones del servicio durante el registro, para dejar constancia del marco contractual bajo el cual opero la plataforma. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-ONB-01 (Onboarding — Inicio de sesión) |

**Precondiciones**

* El usuario está en proceso de registro de su empresa.

**Reglas de negocio**

* RN-01: El sistema registra la versión de los términos aceptada y la fecha y hora de aceptación, conforme a los atributos terminos_version y terminos_fecha_aceptacion de la entidad Empresa.
* RN-02: La aceptación es obligatoria para completar el registro. No es posible avanzar sin aceptar.
* RN-03: Si la versión vigente de los términos difiere de terminos_version de la Empresa, el sistema solicita una nueva aceptación a un Administrador de la empresa en su siguiente ingreso, antes de continuar, y registra la nueva versión y fecha. Los usuarios con otros roles no se ven bloqueados. Los términos son un vínculo contractual con la empresa y sus atributos viven en la entidad Empresa (RN-01).
* RN-04: El texto vigente de los términos es accesible para consulta en todo momento desde el pie del formulario de registro.
* RN-05: El texto de los términos es una página pública, legible sin sesión, que muestra su número de versión y su fecha de vigencia. El enlace del formulario de registro nunca debe devolver error.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Visualizo el formulario de registro | Veo la casilla de aceptación de términos con un enlace al texto vigente | PAN-ONB-01 |
| Intento completar el registro sin aceptar los términos | El sistema muestra “Debe aceptar los términos y condiciones para continuar.” y bloquea el avance | PAN-ONB-01 |
| Acepto los términos y completo el registro | El sistema registra la versión aceptada y la fecha y hora de aceptación | PAN-ONB-01 |
| Ingreso luego de que los términos fueron actualizados | El sistema me solicita aceptar la nueva versión antes de continuar | PAN-ONB-01 |
| Hago clic, sin sesión iniciada, en el enlace a los términos | Veo el texto vigente con su versión y fecha de vigencia | PAN-ONB-01 |
| Se publica una nueva versión y un Administrador ingresa | Se le solicita aceptarla antes de continuar y se registra la nueva versión y fecha | PAN-ONB-01 |
| Se publica una nueva versión y un Operador ingresa | Puede operar con normalidad | PAN-ONB-01 |

## **HU-E1-04 — Registrar un nuevo usuario en la empresa**

| ID | HU-E1-04 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | RegistrarUsuario |
| **Descripción** | Como administrador, quiero invitar a un nuevo usuario a mi empresa asignándole un rol, para que pueda operar el sistema según las atribuciones de su rol. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-USR-01 (Configuración — Usuarios) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.

**Reglas de negocio**

* RN-01: Los roles disponibles son un catálogo cerrado no configurable: Administrador, Operador y Solo Lectura. Los permisos de cada rol son fijos y no se modifican granularmente.
* RN-02: La invitación se envía por email. El usuario invitado debe aceptarla y crear su contraseña antes de poder acceder.
* RN-03: No pueden coexistir dos usuarios con el mismo email dentro de la misma empresa.
* RN-04: Una invitación pendiente puede reenviarse o revocarse mientras no haya sido aceptada.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la sección de Usuarios | Veo el listado de usuarios de mi empresa con nombre, email, rol y estado | PAN-USR-01 |
| Invito a un nuevo usuario con email y rol | El sistema envía el email de invitación y muestra el usuario como “Invitación pendiente” | PAN-USR-01 |
| Invito a un email que ya pertenece a la empresa | El sistema muestra “Ese email ya está registrado en la empresa.” y bloquea la invitación | PAN-USR-01 |
| Invito sin seleccionar un rol | El sistema muestra “Debe asignar un rol al usuario.” y no permite enviar la invitación | PAN-USR-01 |
| El usuario invitado acepta y crea su contraseña | Su estado cambia a “Activo” y puede acceder según su rol | PAN-USR-01 |

## **HU-E1-05 — Asignar o cambiar el rol de un usuario**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E1-05 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | CambiarRolDeUsuario |
| **Descripción** | Como administrador, quiero cambiar el rol de un usuario existente, para ajustar sus atribuciones cuando cambian sus responsabilidades. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-USR-01 (Configuración — Usuarios) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El usuario a modificar existe y está activo.

**Reglas de negocio**

* RN-01: El cambio de rol aplica de forma inmediata sobre las siguientes acciones del usuario afectado.
* RN-02: Una empresa debe conservar siempre al menos un usuario con rol Administrador activo. El sistema no permite quitar el rol de Administrador al único que lo posee.
* RN-03: Solo el rol Administrador puede cambiar roles. El Operador y el Solo Lectura no acceden a esta funcionalidad.
* RN-04: El cambio de rol queda registrado en la bitácora con usuario afectado, rol anterior, rol nuevo, ejecutor y timestamp.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Cambio el rol de un usuario activo | El cambio aplica inmediatamente y queda registrado en la bitácora | PAN-USR-01 |
| Intento quitar el rol de Administrador al único Administrador activo | El sistema muestra “Debe existir al menos un Administrador activo.” y bloquea la acción | PAN-USR-01 |
| Ingreso como Operador a la sección de Usuarios | No tengo disponible la acción de cambiar roles | PAN-USR-01 |
| Cambio el rol de un usuario que tiene una sesión abierta | Su siguiente solicitud ya se evalúa con el nuevo rol; una acción permitida solo por el rol anterior es rechazada, sin esperar a que venza el token de acceso (hoy queda una ventana de hasta 15 minutos) | PAN-USR-01 |

## **HU-E1-06 — Desactivar el acceso de un usuario**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E1-06 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (método sobre Usuario) |
| **Descripción** | Como administrador, quiero desactivar el acceso de un usuario, para impedir que siga operando el sistema sin perder su historial de acciones. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-USR-01 (Configuración — Usuarios) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El usuario a desactivar existe y está activo.

**Reglas de negocio**

* RN-01: Un usuario desactivado pierde el acceso de forma inmediata.
* RN-02: Las acciones históricas del usuario desactivado se conservan en la bitácora.
* RN-03: No se puede desactivar al único usuario con rol Administrador activo.
* RN-04: Un usuario desactivado puede ser reactivado posteriormente por un Administrador, conservando su rol previo.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Desactivo un usuario activo | Pierde acceso inmediatamente y su estado cambia a “Inactivo” | PAN-USR-01 |
| Intento desactivar al único Administrador activo | El sistema muestra “Debe existir al menos un Administrador activo.” y bloquea la acción | PAN-USR-01 |
| Reactivo un usuario inactivo | Recupera el acceso con el rol que tenía antes de la desactivación | PAN-USR-01 |
| Consulto la bitácora tras desactivar un usuario | Las acciones históricas de ese usuario siguen visibles | PAN-LOG-01 |
| Desactivo a un usuario con sesión abierta y token de acceso aún vigente (hoy queda una ventana de hasta 15 minutos) | Su siguiente solicitud es rechazada como no autorizada y sus sesiones renovables quedan revocadas | PAN-USR-01 |
| El usuario desactivado intenta renovar su sesión | El sistema lo rechaza y lo lleva al inicio de sesión | PAN-ONB-01 |

## **HU-E1-07 — Actualizar preferencias personales**

| ID | HU-E1-07 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | ActualizarPreferencias |
| **Descripción** | Como usuario del sistema, quiero actualizar mis preferencias personales de idioma, zona horaria y suscripciones a notificaciones, para adaptar la plataforma a mi forma de trabajar. |
| **Prioridad** | Baja |
| **Complejidad** | Baja |
| **Pantalla** | PAN-USR-02 (Configuración — Preferencias personales) |

**Precondiciones**

* El usuario tiene sesión iniciada con cualquier rol.

**Reglas de negocio**

* RN-01: Las preferencias son individuales de cada usuario y no afectan a los demás usuarios de la empresa, conforme a los atributos pref_idioma, pref_zona_horaria y pref_suscripciones de la entidad Usuario.
* RN-02: La preferencia de suscripciones determina qué notificaciones del sistema recibe el usuario y por qué canal.
* RN-03: Los cambios de preferencias aplican de forma inmediata tras guardar.
* RN-04: La zona horaria del usuario afecta únicamente la visualización de fechas y horas en su sesión; no altera los datos almacenados.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a mis preferencias personales | Veo mis preferencias actuales de idioma, zona horaria y suscripciones | PAN-USR-02 |
| Cambio mi idioma y guardo | El sistema confirma “Preferencias actualizadas.” y la interfaz se actualiza al nuevo idioma de inmediato | PAN-USR-02 |
| Modifico mis suscripciones a notificaciones | Dejo de recibir las notificaciones que desactivé a partir de ese momento | PAN-USR-02 |
| Cambio mi zona horaria | Las fechas y horas se muestran en mi nuevo huso sin alterar los datos de otros usuarios | PAN-USR-02 |

## **HU-E1-08 — Consultar y aceptar la política de privacidad**

> Incorporada por ADR-0009 (2026-09-29).

| ID | HU-E1-08 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura (y cualquier visitante para la consulta) |
| **Acción Bloque K** | (método sobre Usuario) |
| **Descripción** | Como usuario del sistema, quiero consultar la política de privacidad y aceptarla de forma expresa, para dejar constancia del consentimiento sobre el tratamiento de mis datos personales conforme a la Ley 25.326 de Protección de Datos Personales. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-ONB-01 (Onboarding — casilla de aceptación) / PAN-LEG-01 (Política de privacidad, pública; código a confirmar) |

**Precondiciones**

* Existe una versión vigente de la política de privacidad publicada.
* Para aceptar: el usuario está en proceso de registro (HU-E1-01), acepta una invitación (HU-E1-04) o ingresa habiendo cambiado la versión vigente.

**Reglas de negocio**

* RN-01: La política es un texto versionado. Cada versión tiene identificador y fecha de vigencia, es inmutable una vez publicada, y hay una sola vigente. Las anteriores se conservan como evidencia.
* RN-02: La aceptación se registra por Usuario, con usuario_id, versión aceptada y fecha y hora, y queda en la bitácora. El consentimiento es personal y la empresa no puede otorgarlo por sus usuarios, a diferencia de los términos (HU-E1-03), que son contractuales y se registran en la Empresa.
* RN-03: La aceptación es obligatoria y expresa. Se hace con una casilla propia, no premarcada y separada de la de términos y condiciones. Aplica también al registro con Google, que exige aceptar antes de “Continuar con Google”.
* RN-04: Los usuarios invitados (HU-E1-04) deben aceptar la política en su primer ingreso, al crear su contraseña y antes de acceder. Aceptan solo la política, no los términos, porque el contrato es de la empresa.
* RN-05: Cuando cambia la versión vigente, cada usuario debe aceptar la nueva en su siguiente ingreso, antes de operar. Hasta entonces solo puede ver la política y cerrar sesión. La aceptación anterior se conserva en el historial. No se borran datos por no aceptar.
* RN-06: La política es una página pública, legible sin sesión, con ruta estable, que muestra versión y fecha de vigencia. Se enlaza desde el pie del registro, del inicio de sesión y del panel.
* RN-07: El texto debe incluir como mínimo la información que exige la Ley 25.326 (finalidad, destinatarios, responsable, carácter de los datos, derechos de acceso, rectificación y supresión), el tratamiento de datos de clientes finales y de proveedores externos, y la verificación de la identidad del pagador contra MercadoPago cuando se informa una transferencia (finalidad del tratamiento). Su contenido se valida con asesoría legal antes de publicarse.
* RN-08: El Contador externo ingresa por enlace con token y no es Usuario. Solo ve un aviso informativo con enlace a la política, sin aceptación registrada.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Visualizo el formulario de registro | Veo una casilla propia, sin marcar, con enlace a la política vigente | PAN-ONB-01 |
| Intento registrarme sin aceptarla | El sistema muestra “Debe aceptar la política de privacidad para continuar.” y bloquea el avance | PAN-ONB-01 |
| Intento continuar con Google sin aceptarla | El sistema bloquea la acción y muestra el mismo mensaje | PAN-ONB-01 |
| Acepto y completo el registro | El sistema registra mi usuario, la versión y la fecha y hora, y lo deja en la bitácora | PAN-ONB-01 |
| Acepto una invitación y creo mi contraseña | Debo aceptar la política antes de acceder | PAN-ONB-01 |
| Se publica una nueva versión y ingreso | El sistema me solicita aceptarla antes de continuar; si no acepto, solo puedo cerrar sesión | PAN-ONB-01 |
| Abro la política sin sesión iniciada | Veo el texto con versión y fecha de vigencia | PAN-LEG-01 |
| Consulto la bitácora tras una aceptación | Veo usuario, versión aceptada y timestamp | PAN-LOG-01 |

# **Épica 2 — Integración con Sistemas Externos**

**Bounded Contexts asociados:** BC4 Integración con Sistemas Externos
**Acciones de dominio (Bloque K):** ConfigurarIntegración
Esta épica agrupa las historias relativas a la conexión y validación de los servicios externos con los que opera CheatSheet: ARCA para facturación electrónica, MercadoPago para cobros, WhatsApp Business para el canal conversacional, y Google Sheets o Excel Online para la sincronización de planillas. Los mensajes de validación entre comillas son textos del sistema; los atribuidos a terceros son devueltos por cada servicio.

## **HU-E2-01 — Conectar cuenta de ARCA con credenciales validadas**

| ID | HU-E2-01 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | ConfigurarIntegración |
| **Descripción** | Como administrador, quiero conectar mi cuenta de ARCA mediante credenciales validadas, para habilitar la emisión de comprobantes fiscales electrónicos en nombre de mi empresa. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-CFG-INT (Configuración — Integraciones) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* La empresa tiene CUIT validado durante el onboarding.

**Reglas de negocio**

* RN-01: La conexión con ARCA requiere las credenciales fiscales (certificado y clave) asociadas al CUIT de la empresa. El sistema las almacena cifradas, conforme al atributo credencial_contenido_cifrado de la entidad ConfiguraciónDeIntegración.
* RN-02: El sistema valida las credenciales contra ARCA antes de marcar la integración como activa. Credenciales inválidas dejan la integración en estado no conectado.
* RN-03: La integración registra el ambiente (homologación o producción) en el que opera.
* RN-04: Si las credenciales expiran o son revocadas, el sistema marca la integración como inactiva y notifica al administrador.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso credenciales fiscales válidas | El sistema las valida contra ARCA y marca la integración como “Conectada” | PAN-CFG-INT |
| Ingreso credenciales inválidas | El sistema muestra “Las credenciales no pudieron validarse contra ARCA.” y mantiene la integración como no conectada | PAN-CFG-INT |
| Las credenciales expiran con posterioridad | El sistema marca la integración como inactiva y me notifica | PAN-CFG-INT |
| Consulto el estado de la integración ARCA | Veo el ambiente configurado y el estado actual de la conexión | PAN-CFG-INT |

## **HU-E2-02 — Conectar cuenta de MercadoPago**

| ID | HU-E2-02 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | ConfigurarIntegración |
| **Descripción** | Como administrador, quiero conectar mi cuenta de MercadoPago, para poder generar links de cobro y conciliar pagos automáticamente. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-CFG-INT (Configuración — Integraciones) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El usuario posee una cuenta de MercadoPago.

**Reglas de negocio**

* RN-01: La conexión utiliza OAuth2 contra MercadoPago. El sistema almacena el token de acceso cifrado.
* RN-02: El sistema valida la conexión obteniendo los datos de la cuenta antes de marcarla como activa.
* RN-03: Si el token se revoca o expira, el sistema marca la integración como inactiva y notifica al administrador.
* RN-04: La integración de MercadoPago es prerequisito para la generación de links de cobro (Épica 6).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Inicio la conexión con MercadoPago | El sistema abre el flujo OAuth2 de autorización | PAN-CFG-INT |
| Autorizo el acceso | El sistema valida la cuenta y marca la integración como “Conectada” | PAN-CFG-INT |
| Cancelo la autorización en MercadoPago | El sistema mantiene la integración como no conectada e indica “La conexión con MercadoPago no se completó.” | PAN-CFG-INT |
| El token se revoca con posterioridad | El sistema marca la integración como inactiva y me notifica | PAN-CFG-INT |

## **HU-E2-03 — Conectar cuenta de WhatsApp**

| ID | HU-E2-03 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | ConfigurarIntegración |
| **Descripción** | Como administrador, quiero conectar mi cuenta de WhatsApp Business, para que el agente conversacional pueda atender a mis clientes en mi nombre. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-CFG-INT (Configuración — Integraciones) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El número a conectar está habilitado para WhatsApp Business API.

**Reglas de negocio**

* RN-01: La conexión requiere verificación del número por parte de Meta mediante la WhatsApp Business API.
* RN-02: El proceso de verificación puede demorar entre 24 y 72 horas. Durante ese período la integración permanece en estado pendiente y el agente no responde.
* RN-03: El sistema registra el display name verificado y la calidad de la línea informada por Meta.
* RN-04: La integración de WhatsApp es prerequisito para el canal conversacional (Épica 8) y el escalamiento (Épica 9).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Inicio la conexión de un número de WhatsApp Business | El sistema inicia el proceso de verificación con Meta y muestra estado “Pendiente de verificación” | PAN-CFG-INT |
| La verificación con Meta se completa | El sistema marca la integración como “Conectada” con el display name verificado | PAN-CFG-INT |
| La verificación falla | El sistema muestra el motivo devuelto por Meta y mantiene la integración como no conectada | PAN-CFG-INT |

## **HU-E2-04 — Vincular planilla de Google Sheets o Excel**

| ID | HU-E2-04 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | ConfigurarIntegración |
| **Descripción** | Como administrador, quiero vincular mi planilla de Google Sheets o Excel Online, para que el sistema sincronice mis datos automáticamente sin exportaciones manuales. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-ING-01 (Ingesta de Datos — Carga) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El usuario tiene permisos de lectura sobre la planilla a vincular.

**Reglas de negocio**

* RN-01: La vinculación con Google Sheets requiere autorización OAuth2 con permisos de lectura sobre el archivo específico seleccionado, no sobre todo el Drive.
* RN-02: El vínculo de planilla registra el proveedor, la dirección de sincronización y las hojas involucradas, conforme a la entidad VínculoDePlanilla.
* RN-03: El mapeo de columnas se genera en la primera vinculación mediante IA y queda almacenado para sincronizaciones posteriores.
* RN-04: Si la estructura de la planilla cambia, el sistema pausa la sincronización automática y notifica al administrador.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Selecciono vincular Google Sheets | El sistema inicia el flujo OAuth2 de lectura sobre el archivo elegido | PAN-ING-01 |
| Autorizo y selecciono la planilla | El sistema analiza la hoja y propone el mapeo de columnas para revisión | PAN-ING-02 |
| No otorgo los permisos de lectura solicitados | El sistema muestra “Se requieren permisos de lectura sobre la planilla para vincularla.” y no crea el vínculo | PAN-ING-01 |
| Confirmo el vínculo | El sistema guarda la configuración y realiza la primera sincronización | PAN-ING-01 |

## **HU-E2-05 — Validar el estado de una conexión externa**

| ID | HU-E2-05 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | ConfigurarIntegración |
| **Descripción** | Como administrador u operador, quiero validar el estado de mis conexiones externas, para confirmar que las integraciones están operativas antes de depender de ellas. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-CFG-INT (Configuración — Integraciones) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* Existe al menos una integración configurada.

**Reglas de negocio**

* RN-01: La validación realiza una verificación en vivo contra cada servicio externo y reporta su estado actual.
* RN-02: Los estados posibles por integración son: conectado, atención (degradado) y no conectado.
* RN-03: El dashboard muestra el estado consolidado de todas las integraciones con la marca de tiempo de la última verificación.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Solicito verificar el estado de las integraciones | El sistema consulta cada servicio y muestra su estado actualizado con la hora de verificación | PAN-CFG-INT |
| Una integración está degradada | El sistema la muestra en estado “Atención” con el detalle disponible | PAN-CFG-INT |
| Una integración perdió la conexión | El sistema la muestra como “No conectada” e indica la acción para reconectarla | PAN-CFG-INT |

# **Épica 3 — Sincronización de Planillas**

**Bounded Contexts asociados:** BC5 Sincronización de Planillas [CORE]
**Acciones de dominio (Bloque K):** MapearPlanilla, ProcesarPlanilla, SincronizarDesdePlanilla, EscribirEnPlanilla
Esta épica agrupa las historias del núcleo diferenciador de CheatSheet: la interpretación inteligente de planillas del usuario y su sincronización bidireccional con el resto de la plataforma. Constituye el habilitador que conecta las herramientas existentes de la PyME con las automatizaciones del sistema. Los mensajes de validación entre comillas son textos del sistema.

## **HU-E3-01 — Mapear los encabezados de la planilla con asistencia inteligente**

| ID | HU-E3-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | MapearPlanilla |
| **Descripción** | Como administrador u operador, quiero que el sistema interprete automáticamente los encabezados de mi planilla, para no tener que adaptar manualmente mi archivo al formato del sistema. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-ING-02 (Ingesta de Datos — Revisión de Mapeo) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* El usuario subió una planilla o vinculó una fuente de datos.

**Reglas de negocio**

* RN-01: El motor de IA detecta las columnas del archivo y propone un mapeo al esquema interno, asignando un nivel de confianza a cada columna (Alta, Media o Baja), conforme a la entidad EntradaDeMapeo.
* RN-02: El mapeo propuesto se almacena con su huella de encabezado para reutilizarse en sincronizaciones posteriores mientras la estructura no cambie.
* RN-03: Las columnas con confianza Baja se marcan como Sin asignar y requieren intervención manual.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Subo un archivo con columnas en cualquier orden o nombre | El sistema propone un mapeo automático con nivel de confianza por columna (Alta, Media o Baja) | PAN-ING-02 |
| Una columna tiene confianza Baja | El sistema la marca como “Sin asignar” y la señala para revisión manual | PAN-ING-02 |
| El sistema reconoce una estructura ya mapeada antes | Reutiliza el mapeo almacenado sin volver a solicitarlo | PAN-ING-02 |

## **HU-E3-02 — Confirmar o corregir el mapeo propuesto**

| ID | HU-E3-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | MapearPlanilla |
| **Descripción** | Como administrador u operador, quiero revisar, corregir y confirmar el mapeo propuesto antes de activarlo, para asegurar que mis datos se interpreten correctamente. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-ING-02 (Ingesta de Datos — Revisión de Mapeo) |

**Precondiciones**

* El sistema generó una propuesta de mapeo (HU-E3-01).

**Reglas de negocio**

* RN-01: El usuario puede corregir manualmente cualquier asignación de columna antes de confirmar.
* RN-02: No es posible confirmar el mapeo mientras existan columnas obligatorias sin asignar.
* RN-03: Al confirmar, el mapeo queda activo y habilita el procesamiento de la planilla.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Reviso el mapeo propuesto | Veo cada columna original, el campo interno asignado, un ejemplo de dato y el nivel de confianza | PAN-ING-02 |
| Corrijo manualmente una asignación | El sistema acepta el cambio y actualiza la vista previa | PAN-ING-02 |
| Intento confirmar con columnas obligatorias sin asignar | El sistema muestra “Debe asignar todas las columnas obligatorias antes de continuar.” y el botón Confirmar y procesar permanece deshabilitado | PAN-ING-02 |
| Confirmo un mapeo completo | El sistema activa el mapeo y habilita el procesamiento | PAN-ING-02 |

## **HU-E3-03 — Procesar la carga inicial de la planilla**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E3-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | ProcesarPlanilla |
| **Descripción** | Como administrador u operador, quiero procesar la carga inicial de mi planilla, para alimentar el sistema con mis datos existentes. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-ING-01 (Ingesta de Datos — Carga) |

**Precondiciones**

* El mapeo de la planilla fue confirmado (HU-E3-02).

**Reglas de negocio**

* RN-01: El procesamiento es asíncrono. El sistema muestra el resultado en Cargas recientes una vez completado, sin bloquear la interfaz.
* RN-02: Las filas con datos inválidos (por ejemplo CUIT mal formado) se marcan como error pero no abortan el procesamiento del resto.
* RN-03: El procesamiento registra filas totales, filas procesadas correctamente y filas con error, conforme a la entidad ProcesamientoDePlanilla.
* RN-04: Los valores de cada fila se normalizan según HU-E4-05 antes de guardarse en el catálogo. La planilla original no se modifica.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Confirmo el procesamiento | El sistema inicia el procesamiento asíncrono y muestra el archivo con estado “Procesando” | PAN-ING-01 |
| El procesamiento finaliza sin errores | El estado cambia a “Procesado” con el total de filas procesadas | PAN-ING-01 |
| El archivo tiene filas con datos inválidos | El estado muestra “Con errores” indicando la cantidad de filas válidas y fallidas | PAN-ING-01 |
| Subo un archivo de formato no soportado | El sistema muestra “Formato no aceptado. Use .xlsx, .xls o .csv.” y no inicia la carga | PAN-ING-01 |
| El archivo supera el tamaño máximo permitido | El sistema muestra “El archivo supera el límite de 25 MB.” y no inicia la carga | PAN-ING-01 |
| Una fila trae el nombre “MARIA DE LOS ANGELES perez  ” | Se guarda con el formato normalizado (HU-E4-05) y la planilla original queda intacta | PAN-ING-01 |
| Una fila de servicio trae una duración fuera de 5 a 480 minutos | La fila se marca con error y no aborta el resto (RN-02) | PAN-ING-01 |

## **HU-E3-04 — Sincronizar los cambios incrementales de la planilla**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E3-04 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | SincronizarDesdePlanilla |
| **Descripción** | Como administrador u operador, quiero que el sistema sincronice automáticamente los cambios incrementales de mi planilla, para mantener los datos actualizados sin reprocesar todo el archivo. |
| **Prioridad** | Media |
| **Complejidad** | Alta |
| **Pantalla** | PAN-ING-01 (Ingesta de Datos — Carga) |

**Precondiciones**

* Existe un vínculo de planilla activo con mapeo confirmado.

**Reglas de negocio**

* RN-01: La sincronización incremental procesa únicamente las filas nuevas o modificadas desde la última lectura, conforme a los atributos ultima_lectura y ultima_escritura de VínculoDePlanilla.
* RN-02: Si una sincronización falla, el evento se registra en la bitácora con estado Error y se notifica al administrador.
* RN-03: Si la estructura de la planilla cambia (columnas agregadas, renombradas o eliminadas), el sistema pausa la sincronización automática y solicita revisar el mapeo.
* RN-04: Al detectar cambios, el sistema compara el valor normalizado (HU-E4-05) de la planilla con el valor normalizado almacenado. Una diferencia que desaparece al normalizar no se considera un cambio.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Se modifica una fila en la planilla vinculada | El sistema detecta el cambio y lo sincroniza en la siguiente corrida | PAN-ING-01 |
| Se agregan filas nuevas | El sistema procesa solo las filas nuevas sin reprocesar las existentes | PAN-ING-01 |
| Cambia la estructura de columnas de la planilla | El sistema pausa la sincronización y muestra “La estructura de la planilla cambió. Revise el mapeo para reanudar la sincronización.” | PAN-ING-01 |
| Una sincronización falla | El sistema registra el error en la bitácora y notifica al administrador | PAN-LOG-01 |
| Una celda cambia solo en mayúsculas o espacios respecto de lo almacenado | El sistema no registra cambio ni actualiza el registro | PAN-ING-01 |

## **HU-E3-05 — Consultar el resultado y los errores de un procesamiento**

| ID | HU-E3-05 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | ProcesarPlanilla |
| **Descripción** | Como usuario del panel, quiero consultar el resultado detallado de un procesamiento de planilla, para identificar qué filas fallaron y por qué. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-ING-03 (Ingesta de Datos — Detalle de procesamiento) |

**Precondiciones**

* Existe al menos un procesamiento de planilla registrado.

**Reglas de negocio**

* RN-01: El detalle muestra filas totales, procesadas y con error, junto con el motivo de cada error de fila, conforme a la entidad ErrorDeFila.
* RN-02: Cada error de fila indica el número de fila del archivo original y la descripción del problema.
* RN-03: El detalle permite descargar el listado de errores para su corrección externa.
* RN-04: El rol Solo Lectura accede a la consulta sin posibilidad de reprocesar.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro el detalle de un procesamiento | Veo el resumen de filas totales, procesadas y con error | PAN-ING-03 |
| Reviso los errores | Veo cada fila fallida con su número de fila original y el motivo (por ejemplo “CUIT inválido en la fila 42.”) | PAN-ING-03 |
| Descargo el listado de errores | El sistema genera un archivo con las filas fallidas y sus motivos | PAN-ING-03 |
| Ingreso como Solo Lectura | Veo el resultado y los errores sin la opción de reprocesar | PAN-ING-03 |

## **HU-E3-06 — Reprocesar una planilla tras corregir errores**

| ID | HU-E3-06 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | ProcesarPlanilla |
| **Descripción** | Como administrador u operador, quiero reprocesar una planilla luego de corregir los errores detectados, para incorporar las filas que habían fallado. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-ING-03 (Ingesta de Datos — Detalle de procesamiento) |

**Precondiciones**

* Existe un procesamiento previo con filas en error.
* El usuario corrigió los datos en la fuente.

**Reglas de negocio**

* RN-01: El reprocesamiento reutiliza el mapeo ya confirmado de la planilla.
* RN-02: El reprocesamiento no duplica las filas ya procesadas correctamente; solo incorpora las corregidas.
* RN-03: El resultado del reprocesamiento se registra como un nuevo procesamiento vinculado al original.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Solicito reprocesar tras corregir errores | El sistema reutiliza el mapeo y procesa las filas corregidas | PAN-ING-03 |
| Existen filas ya procesadas correctamente | El sistema no las duplica | PAN-ING-03 |
| El reprocesamiento finaliza | El sistema muestra el nuevo resultado vinculado al procesamiento original | PAN-ING-03 |

## **HU-E3-07 — Escribir de vuelta en la planilla los registros gestionados desde el panel**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E3-07 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | EscribirEnPlanilla |
| **Descripción** | Como administrador u operador, quiero que los registros creados o modificados desde el panel o por el agente se escriban de vuelta en mi planilla, para mantener una única fuente de datos coherente entre el panel y la planilla que sigo usando. |
| **Prioridad** | Media |
| **Complejidad** | Alta |
| **Pantalla** | PAN-ING-02 (Ingesta de Datos — Vínculo de planilla) |

**Precondiciones**

* Existe un vínculo de planilla con dirección de sincronización LECTURA_Y_ESCRITURA.
* El proveedor del vínculo es Google Sheets (el write-back no aplica a Excel Online, que es de solo lectura).

**Reglas de negocio**

* RN-01: La escritura de vuelta solo se realiza sobre vínculos cuya dirección es LECTURA_Y_ESCRITURA; los vínculos de solo lectura no se escriben.
* RN-02: La escritura se realiza únicamente sobre la hoja propia protegida del sistema, nunca sobre la hoja original de la empresa, conforme al mecanismo anti-bucle del ADR-007.
* RN-03: Solo se escriben los registros cuyo origen es PANEL o AGENTE; los registros cuyo origen es la propia planilla no se reescriben.
* RN-04: La escritura de vuelta se ejecuta de forma asíncrona y registra su última marca temporal en el estado de sincronización del vínculo.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Creo un registro desde el panel sobre un vínculo de lectura y escritura | El registro se escribe en la hoja protegida del sistema y se actualiza la marca de última escritura | PAN-ING-02 |
| El vínculo es de solo lectura | El sistema no intenta escribir y lo indica en el estado del vínculo | PAN-ING-02 |
| El registro proviene de la planilla original | El sistema no lo reescribe, evitando el bucle de sincronización | PAN-ING-02 |
| El proveedor del vínculo es Excel Online | El sistema no ofrece la escritura de vuelta e indica que solo está disponible para Google Sheets | PAN-ING-02 |
| Un registro de planilla se normaliza al guardarse | La versión normalizada no se escribe sobre la hoja original ni se reescribe el registro (RN-02 y RN-03) | PAN-ING-02 |

# **Épica 4 — Gestión de Datos Maestros**

**Bounded Contexts asociados:** BC2 Datos Maestros
**Acciones de dominio (Bloque K):** GestionarCategoría (y operaciones sobre Cliente y Servicio)
Esta épica agrupa las historias relativas a la administración del catálogo de clientes, servicios y categorías de la empresa. Estos datos maestros dan soporte transversal a la facturación, la agenda y los cobros. Los mensajes de validación entre comillas son textos del sistema.

## **HU-E4-01 — Consultar y gestionar el catálogo de clientes**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E4-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta + métodos sobre Cliente) |
| **Descripción** | Como administrador u operador, quiero ver, crear y editar clientes desde el panel, para mantener actualizado el catálogo de clientes de mi empresa independientemente de la planilla. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-DM-01 (Datos Maestros — Clientes) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.

**Reglas de negocio**

* RN-01: Cada cliente tiene un campo origen (PLANILLA, PANEL o AGENTE) asignado automáticamente y no editable, conforme a la entidad Cliente.
* RN-02: El CUIT es validado contra ARCA al crear o editar un cliente. Un CUIT inválido bloquea el guardado.
* RN-03: No pueden existir dos clientes con el mismo CUIT dentro de la misma empresa.
* RN-04: Un cliente creado desde el panel queda disponible inmediatamente para facturación, agenda y cobros.
* RN-05: Nombre, email, WhatsApp y CUIT se guardan normalizados según HU-E4-05. La unicidad de CUIT (RN-03) se evalúa sobre el CUIT normalizado.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo de Clientes | Veo el listado con nombre, CUIT, origen, WhatsApp y estado | PAN-DM-01 |
| Creo un cliente con CUIT válido | El sistema valida contra ARCA, completa razón social y condición IVA y guarda con origen PANEL | PAN-DM-01 |
| Ingreso un CUIT con formato inválido | El sistema muestra “El CUIT debe contener 11 dígitos.” y no guarda el cliente | PAN-DM-01 |
| Intento crear un cliente con CUIT ya existente | El sistema muestra “Ya existe un cliente con ese CUIT.” y ofrece ver el duplicado | PAN-DM-01 |
| Edito un cliente existente | Los cambios se guardan y quedan disponibles para los demás módulos | PAN-DM-01 |
| Creo un cliente con el CUIT “20-12345678-9” y ya existe el mismo CUIT en dígitos | El sistema muestra “Ya existe un cliente con ese CUIT.” | PAN-DM-01 |

## **HU-E4-02 — Consultar y gestionar el catálogo de servicios**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E4-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta + métodos sobre Servicio) |
| **Descripción** | Como administrador u operador, quiero ver, crear y editar los servicios de mi catálogo, para que el agente pueda ofrecerlos al reservar turnos y la facturación los use como ítems. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-DM-02 (Datos Maestros — Servicios) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.

**Reglas de negocio**

* RN-01: Cada servicio tiene nombre, precio sin IVA, alícuota de IVA y un indicador agendable. Los servicios agendables requieren duración estándar en minutos, conforme a la entidad Servicio.
* RN-02: El precio debe ser mayor a cero. La alícuota de IVA es un enum cerrado: 0%, 10.5% o 21%.
* RN-03: Un servicio agendable sin duración definida no puede guardarse.
* RN-04: Desactivar un servicio no elimina los comprobantes ni turnos históricos que lo referencian; solo lo oculta del catálogo activo.
* RN-05: La duración estándar (duracion_estandar_min) de un servicio agendable es un número entero de minutos entre 5 y 480. Aplica a panel, ingesta de planilla y agente. Esa duración es la que se asigna al turno (HU-E7-06 RN-08). RN-03 (duración obligatoria) no cambia.
* RN-06: Para emisores Monotributo y Exento, que emiten Factura C (HU-E5-03 RN-12), el precio del catálogo es el precio final y la alícuota de IVA se ignora.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo de Servicios | Veo el listado con nombre, precio, IVA, duración y estado | PAN-DM-02 |
| Creo un servicio agendable sin duración | El sistema muestra “La duración es obligatoria para servicios agendables.” y bloquea el guardado | PAN-DM-02 |
| Ingreso un precio cero o negativo | El sistema muestra “El precio debe ser mayor a cero.” y no guarda el servicio | PAN-DM-02 |
| Creo un servicio con datos válidos | El servicio queda disponible para el agente y para nuevos comprobantes | PAN-DM-02 |
| Edito el precio de un servicio | El nuevo precio aplica a operaciones futuras; los comprobantes emitidos mantienen su precio original | PAN-DM-02 |
| Ingreso una duración de 4 minutos o de 481 minutos o más (por ejemplo 99999) | El sistema muestra “La duración debe estar entre 5 y 480 minutos.” y no guarda | PAN-DM-02 |
| Ingreso una duración de 5 o de 480 minutos | El sistema la acepta | PAN-DM-02 |
| Emito con un emisor Monotributo o Exento un servicio con alícuota de IVA cargada | El comprobante toma el precio del catálogo como precio final y no aplica la alícuota | PAN-FAC-03 |

## **HU-E4-03 — Gestionar categorías personalizadas**

| ID | HU-E4-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | GestionarCategoría |
| **Descripción** | Como administrador u operador, quiero crear, editar y eliminar categorías personalizadas, para organizar mis clientes y servicios según los criterios de mi negocio. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-DM-03 (Datos Maestros — Categorías) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.

**Reglas de negocio**

* RN-01: Cada categoría tiene un nombre y un ámbito de aplicación (clientes, servicios o ambos), conforme a la entidad CategoríaEmpresa.
* RN-02: No pueden existir dos categorías con el mismo nombre y ámbito dentro de la misma empresa.
* RN-03: Al eliminar una categoría, los clientes o servicios que la tenían asignada quedan sin esa clasificación, sin afectar el resto de sus datos.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Creo una categoría nueva | Queda disponible para clasificar clientes o servicios según su ámbito | PAN-DM-03 |
| Intento crear una categoría con nombre duplicado en el mismo ámbito | El sistema muestra “Ya existe una categoría con ese nombre en este ámbito.” y bloquea el guardado | PAN-DM-03 |
| Edito el nombre de una categoría | El cambio se refleja en todos los elementos clasificados con ella | PAN-DM-03 |
| Elimino una categoría en uso | El sistema solicita confirmación y, al confirmar, los elementos quedan sin esa clasificación | PAN-DM-03 |

## **HU-E4-04 — Clasificar clientes o servicios mediante categorías**

| ID | HU-E4-04 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | GestionarCategoría |
| **Descripción** | Como administrador u operador, quiero asignar categorías a mis clientes y servicios, para segmentarlos y analizarlos según los criterios de mi negocio. |
| **Prioridad** | Baja |
| **Complejidad** | Baja |
| **Pantalla** | PAN-DM-01 / PAN-DM-02 |

**Precondiciones**

* Existe al menos una categoría creada (HU-E4-03).
* Existe al menos un cliente o servicio.

**Reglas de negocio**

* RN-01: Solo pueden asignarse categorías cuyo ámbito corresponda al elemento (categorías de clientes a clientes, de servicios a servicios).
* RN-02: Un cliente o servicio puede tener más de una categoría asignada.
* RN-03: La asignación y desasignación de categorías es inmediata y no afecta operaciones históricas.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Asigno una categoría a un cliente | El cliente queda clasificado y es filtrable por esa categoría | PAN-DM-01 |
| Asigno una categoría de servicios a un servicio | El servicio queda clasificado correctamente | PAN-DM-02 |
| Intento asignar una categoría de ámbito incorrecto | El sistema no ofrece esa categoría para ese elemento | PAN-DM-01 |

## **HU-E4-05 — Normalización de los datos del catálogo**

> Incorporada por ADR-0009 (2026-09-29).

| ID | HU-E4-05 |
| :---- | :---- |
| **Actor** | Administrador / Operador (regla transversal: también aplica a la ingesta de planillas y al agente de WhatsApp) |
| **Acción Bloque K** | (regla transversal sobre Cliente, Servicio y CategoríaEmpresa) |
| **Descripción** | Como administrador u operador, quiero que los datos del catálogo se guarden con un formato uniforme, sin importar cómo se ingresen, para evitar duplicados aparentes y ver la información de forma consistente. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-DM-01 / PAN-DM-02 / PAN-DM-03 / PAN-ING-01 |

**Precondiciones**

* El dato ingresa por alguno de los tres caminos: panel, ingesta de planilla (HU-E3-03 y HU-E3-04) o agente de WhatsApp.

**Reglas de negocio**

* RN-01 (todos los campos de texto): se eliminan espacios al inicio y al final, se colapsan los espacios internos repetidos en uno y se descartan caracteres de control e invisibles. No se agregan ni se quitan tildes.
* RN-02 (nombre de persona): se capitaliza cada palabra, salvo las partículas de, del, la, las, los, y, e, que van en minúscula excepto al inicio. Una palabra se capitaliza solo si viene completamente en mayúsculas o completamente en minúsculas. Las que tienen mayúsculas mezcladas (por ejemplo “McDonald”) se preservan.
* RN-03 (razón social): las siglas societarias (S.A., S.R.L., S.A.S., SAS, S.A.U., S.C.A. y equivalentes) se conservan en mayúsculas tal como fueron escritas, con o sin puntos. El resto se capitaliza como en RN-02. Las palabras totalmente en mayúsculas de hasta 4 letras se conservan por suponerse siglas propias (IBM, YPF), lo que acepta falsos positivos como “SUR”. Un cliente se trata como razón social cuando su CUIT empieza con 30, 33 o 34; en otro caso, como persona.
* RN-04 (nombres de servicio y categoría): solo cuando el texto viene todo en mayúsculas o todo en minúsculas, se deja la primera letra en mayúscula y el resto en minúscula. La unicidad de categoría (HU-E4-03 RN-02) se evalúa sobre el valor normalizado, sin distinguir mayúsculas.
* RN-05 (identificadores y contacto, ya vigentes, se citan y no se rehacen): email en minúsculas y sin espacios; WhatsApp solo dígitos, de 8 a 15; CUIT en 11 dígitos, mostrado como XX-XXXXXXXX-X.
* RN-06 (fuera de alcance): los textos libres (FAQ, descripciones de cobro o de ítem, mensajes) solo reciben RN-01. Los comprobantes ya emitidos nunca se modifican, porque los datos del receptor están desnormalizados a propósito.
* RN-07: la normalización es idempotente (normalizar dos veces da lo mismo) y se aplica una sola vez, en el punto de entrada común de datos maestros, sin importar el camino. Los demás contextos la usan a través de la capa de aplicación de Datos Maestros.
* RN-08: la planilla original de la empresa nunca se reescribe (HU-E3-07 RN-02). En la resincronización se compara el valor normalizado de la planilla con el almacenado, de modo que no se crean falsos cambios.
* RN-09 (datos existentes): corrección única por empresa, con estas condiciones:
  * Se genera un informe previo (dry-run) con cantidades y ejemplos.
  * Se hace un respaldo restaurable de los valores originales antes de aplicar.
  * No toca comprobantes ni las hojas.
  * Los casos que colisionarían con una restricción de unicidad (CUIT o categoría) se informan y no se cambian.
  * Se registra en la bitácora con los conteos.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Creo un cliente persona con “JUAN CARLOS DE LA CRUZ” | Se guarda como “Juan Carlos de la Cruz” | PAN-DM-01 |
| Creo un cliente con CUIT 30-… y razón social “ferreteria lopez s.r.l.” | Se guarda como “Ferreteria Lopez S.R.L.” | PAN-DM-01 |
| Ingreso “  Ana   Perez ” con espacios sobrantes | Se guarda como “Ana Perez” | PAN-DM-01 |
| Ingreso el email “Ana@Mail.COM” | Se guarda como “ana@mail.com” | PAN-DM-01 |
| Ingreso el teléfono “+54 9 11 1234-5678” | Se guarda solo con dígitos | PAN-DM-01 |
| El agente crea un cliente con origen AGENTE con el nombre “maria gomez” | Se guarda como “Maria Gomez” | Canal WhatsApp |
| La planilla trae “MARIA GOMEZ” y el catálogo tiene “Maria Gomez” | La resincronización no registra cambio y la planilla queda intacta | PAN-ING-01 |
| Creo la categoría “VIP” y ya existe “Vip” en el mismo ámbito | El sistema muestra “Ya existe una categoría con ese nombre en este ámbito.” | PAN-DM-03 |
| Ejecuto la corrección de datos existentes | Obtengo el informe previo, existe el respaldo y los cambios quedan en la bitácora | PAN-DM-01 |

# **Épica 5 — Facturación**

**Bounded Contexts asociados:** BC6 Facturación [CORE]
**Acciones de dominio (Bloque K):** EmitirComprobante, AnularComprobante
Esta épica agrupa las historias del núcleo de facturación electrónica: la emisión de comprobantes fiscales con obtención de CAE ante ARCA, su anulación mediante notas de crédito, la consulta del historial y la administración de los puntos de venta. Los mensajes de validación entre comillas corresponden a textos del sistema; los mensajes atribuidos a ARCA son devueltos por el organismo y se citan a modo de ejemplo representativo.

## **HU-E5-01 — Consultar el listado de comprobantes emitidos**

| ID | HU-E5-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | (consulta sobre Comprobante) |
| **Descripción** | Como usuario del panel, quiero ver el listado de comprobantes emitidos con filtros por período, tipo y estado, para tener visibilidad del historial de facturación de mi empresa. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-FAC-01 (Facturación — Listado) |

**Precondiciones**

* El usuario tiene sesión iniciada con cualquier rol.
* La empresa tiene al menos un comprobante emitido.

**Reglas de negocio**

* RN-01: El listado muestra únicamente comprobantes de la empresa del usuario autenticado; el aislamiento multi-tenant es transparente.
* RN-02: Los filtros disponibles son: rango de fechas, tipo de comprobante (Factura A/B/C, Nota de Crédito A/B/C) y estado (Autorizado, Pendiente, Error).
* RN-03: El listado se ordena por fecha de emisión descendente por defecto.
* RN-04: El rol Solo Lectura puede ver y filtrar pero no iniciar acciones sobre los comprobantes.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo de Facturación | Veo el listado ordenado por fecha con número, tipo, cliente, monto, fecha y estado | PAN-FAC-01 |
| Aplico filtro por rango de fechas | El listado muestra solo los comprobantes del período seleccionado | PAN-FAC-01 |
| Aplico filtro por estado Error | Veo solo los comprobantes que fallaron en la autorización ante ARCA | PAN-FAC-01 |
| No hay comprobantes que coincidan con los filtros | El sistema muestra el mensaje “No hay comprobantes para los filtros seleccionados.” | PAN-FAC-01 |
| Ingreso como Solo Lectura | Veo y filtro el listado sin acciones de emisión ni anulación disponibles | PAN-FAC-01 |

## **HU-E5-02 — Consultar el estado y detalle de un comprobante**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E5-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | (consulta sobre Comprobante) |
| **Descripción** | Como usuario del panel, quiero ver el detalle completo de un comprobante, para verificar los datos fiscales, el CAE otorgado y descargar el PDF. |
| **Prioridad** | Alta |
| **Complejidad** | Baja |
| **Pantalla** | PAN-FAC-02 (Facturación — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con cualquier rol.
* El comprobante existe en el sistema.

**Reglas de negocio**

* RN-01: Un comprobante autorizado (con CAE) es inmutable; el detalle no permite edición.
* RN-02: El detalle muestra número, tipo, fecha, datos del receptor, ítems, total, CAE y vencimiento de CAE.
* RN-03: El PDF descargable es una representación imprimible derivada del comprobante; no es la fuente de verdad fiscal, que es el propio registro junto con su CAE. El sistema lo genera sobre la base del registro vigente y lo sirve mediante una política de cacheo con expiración, regenerándolo si fuese necesario.
* RN-04: El detalle y el PDF muestran la condición IVA del receptor con su origen y fecha, y la leyenda de RN-13 de HU-E5-03 cuando corresponda.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro un comprobante del listado | Veo el detalle completo con datos fiscales, CAE y vencimiento de CAE | PAN-FAC-02 |
| El comprobante está Autorizado | El botón “Descargar PDF” está disponible y al usarlo obtengo la representación imprimible vigente | PAN-FAC-02 |
| El comprobante está en Error | Veo el mensaje devuelto por ARCA y no se ofrece la descarga del PDF | PAN-FAC-02 |
| Ingreso como Solo Lectura | Veo el detalle completo sin acciones de gestión | PAN-FAC-02 |
| Abro un comprobante autorizado | Veo la condición IVA del receptor con su origen y fecha | PAN-FAC-02 |

## **HU-E5-03 — Emitir un comprobante fiscal y obtener su CAE**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E5-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | EmitirComprobante |
| **Descripción** | Como administrador u operador, quiero emitir un comprobante fiscal y obtener su CAE, para documentar legalmente una operación de venta de mi empresa. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-FAC-03 (Facturación — Nueva emisión) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* La empresa tiene ARCA conectado y un punto de venta configurado.
* El cliente receptor existe en Datos Maestros.

**Reglas de negocio**

* RN-01: El tipo de comprobante disponible se determina por la combinación de la condición IVA del emisor y del receptor, según la tabla de combinaciones válidas que sigue a estas reglas; el sistema no permite emitir un tipo fiscalmente inválido.
* RN-02: El CUIT del receptor se valida contra ARCA antes de habilitar la emisión, y en la misma consulta al padrón se obtiene su condición frente al IVA (RN-07). El CUIT del receptor sigue siendo obligatorio.
* RN-03: El comprobante debe tener al menos un ítem con descripción, cantidad y precio unitario; el precio unitario debe ser mayor a cero.
* RN-04: La emisión es asíncrona; el sistema actualiza el estado del comprobante cuando recibe respuesta de ARCA.
* RN-05: Un comprobante puede originarse en un turno completado, en cuyo caso hereda los datos del servicio y del cliente, conforme al atributo turno_id de la entidad Comprobante.
* RN-06: El comprobante registra su saldo pendiente, que habilita la asociación de cobros parciales, conforme al atributo saldo_pendiente de la entidad Comprobante.
* RN-07 (fuente de verdad de la condición): al momento de la emisión, la condición IVA del receptor proviene del padrón de ARCA. La condición guardada en el catálogo de clientes es dato de referencia: si difiere de la del padrón, se actualiza con la del padrón y el cambio se registra en la bitácora. El padrón se reconsulta al confirmar la emisión y, si el resultado difiere del que se mostró en el formulario, se pide reconfirmar el tipo.
* RN-08: Un CUIT existente sin inscripción en IVA ni Monotributo se trata como Consumidor Final, o como “IVA No Alcanzado” si el padrón así lo indica, y no se bloquea la emisión. Un CUIT inexistente sigue bloqueando.
* RN-09 (evidencia): el comprobante guarda la condición IVA del receptor usada, su origen (PADRÓN o ÚLTIMA CONFIRMADA) y la fecha de la confirmación, visibles en el detalle.
* RN-10 (padrón no disponible): se usa la última condición confirmada por el padrón, con su fecha, y el hecho queda en la bitácora. Si el cliente nunca tuvo una condición confirmada por el padrón, se bloquea con “No se pudo consultar el padrón de ARCA y no hay una condición de IVA confirmada para este cliente. Intente nuevamente.”
* RN-11: Todo comprobante y nota de crédito informa a ARCA la condición IVA del receptor (CondicionIVAReceptorId, RG 5616/2024).
* RN-12: La Factura C no discrimina IVA: IVA cero, total igual al subtotal. Para emisores Monotributo y Exento, el precio del catálogo es el precio final y la alícuota del servicio no se muestra ni se aplica (HU-E4-02 RN-06).
* RN-13: En la Factura A a un receptor Monotributo se incluye la leyenda: “El crédito fiscal discriminado en el presente comprobante, sólo podrá ser computado a efectos del Régimen de Sostenimiento e Inclusión Fiscal para Pequeños Contribuyentes de la Ley Nº 27.618”. Se muestra en el detalle y en el PDF.
* RN-14 (servicios): el concepto es “Servicios” y son obligatorios el período del servicio (desde y hasta, con desde menor o igual a hasta) y la fecha de vencimiento de pago, que no puede ser anterior a la fecha de emisión. Si el comprobante nace de un turno, el período por defecto es la fecha del turno y el vencimiento por defecto es la fecha de emisión.

**Tabla de combinaciones válidas (RN-01)**

| Emisor | Receptor | Tipo |
| :---- | :---- | :---- |
| Responsable Inscripto | Responsable Inscripto | Factura A |
| Responsable Inscripto | Monotributo | Factura A (RG 5003/2021), con la leyenda de RN-13 |
| Responsable Inscripto | Exento | Factura B |
| Responsable Inscripto | Consumidor Final | Factura B |
| Responsable Inscripto | IVA No Alcanzado | Factura B (a verificar en homologación) |
| Monotributo | cualquiera | Factura C |
| Exento | cualquiera | Factura C |

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso un CUIT con dígito verificador inválido | El sistema muestra “El CUIT ingresado no es válido. Debe contener 11 dígitos correctos.” y no consulta a ARCA | PAN-FAC-03 |
| Ingreso un CUIT válido pero inexistente en el padrón | El sistema muestra “No se encontró el CUIT en el padrón de ARCA.” y bloquea la emisión | PAN-FAC-03 |
| Ingreso un CUIT válido y existente | El sistema completa automáticamente razón social y condición IVA y habilita el resto del formulario | PAN-FAC-03 |
| Intento emitir sin ningún ítem cargado | El sistema muestra “Debe agregar al menos un ítem para emitir el comprobante.” y el botón Emitir permanece deshabilitado | PAN-FAC-03 |
| Cargo un ítem con precio unitario cero o negativo | El sistema muestra “El precio unitario debe ser mayor a cero.” y no permite continuar | PAN-FAC-03 |
| Selecciono una combinación de comprobante fiscalmente inválida para las condiciones de IVA | El sistema no ofrece ese tipo y muestra “El tipo de comprobante no es válido para la condición de IVA del receptor.” | PAN-FAC-03 |
| Confirmo la emisión | El comprobante aparece en el listado con estado Pendiente mientras aguarda respuesta de ARCA | PAN-FAC-01 |
| ARCA autoriza el comprobante | El estado cambia a Autorizado, se muestra el CAE y su vencimiento, y queda disponible la descarga del PDF | PAN-FAC-02 |
| ARCA rechaza el comprobante | El sistema muestra el código y la descripción devueltos por ARCA, por ejemplo “Error 10016: el comprobante no cumple la resolución general vigente.”, y deja el comprobante en estado Error con ese detalle visible | PAN-FAC-02 |
| Emisor Responsable Inscripto y receptor Monotributo | Solo se ofrece Factura A y se agrega la leyenda de RN-13 | PAN-FAC-03 |
| Emisor Responsable Inscripto y receptor Consumidor Final o Exento | Solo se ofrece Factura B | PAN-FAC-03 |
| Emisor Monotributo o Exento | Solo se ofrece Factura C, sin IVA discriminado y con el precio del catálogo como precio final | PAN-FAC-03 |
| La condición del padrón difiere de la del catálogo | Se emite con la del padrón, el cliente se actualiza y queda registro en la bitácora | PAN-FAC-03 |
| El CUIT existe pero no está inscripto en IVA ni Monotributo | Se emite como Consumidor Final, o como IVA No Alcanzado si el padrón lo indica, sin bloquear | PAN-FAC-03 |
| El padrón no responde y hay una condición previamente confirmada | Se emite con ella, el detalle muestra “Última confirmación del padrón: fecha” y se registra en la bitácora | PAN-FAC-02 |
| El padrón no responde y nunca hubo confirmación | El sistema bloquea con el mensaje de RN-10 | PAN-FAC-03 |
| Falta el período del servicio o el vencimiento de pago | El sistema muestra “Debe indicar el período del servicio y la fecha de vencimiento de pago.” y no permite emitir | PAN-FAC-03 |
| El vencimiento de pago es anterior a la emisión | El sistema muestra “El vencimiento de pago no puede ser anterior a la fecha de emisión.” | PAN-FAC-03 |

## **HU-E5-04 — Anular un comprobante mediante una nota de crédito**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E5-04 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | AnularComprobante |
| **Descripción** | Como administrador u operador, quiero anular un comprobante autorizado mediante una nota de crédito, para reversar total o parcialmente una factura emitida con error o por una devolución. |
| **Prioridad** | Media |
| **Complejidad** | Alta |
| **Pantalla** | PAN-FAC-04 (Facturación — Nueva nota de crédito) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* Existe un comprobante con estado Autorizado al cual asociar la nota de crédito.
* La empresa tiene ARCA conectado.

**Reglas de negocio**

* RN-01: Una nota de crédito debe estar asociada obligatoriamente a un comprobante original autorizado, conforme al atributo comprobante_origen_id de la entidad Comprobante.
* RN-02: El tipo de nota de crédito (A, B o C) debe coincidir con el del comprobante original; el sistema lo determina automáticamente.
* RN-03: El monto de la nota de crédito no puede superar el del comprobante original.
* RN-04: La emisión es asíncrona; el estado se actualiza cuando ARCA responde.
* RN-05: Una vez autorizada la nota de crédito, el comprobante original refleja su nuevo estado de anulación total o parcial.
* RN-06: La nota de crédito hereda del comprobante original el tipo, la condición IVA del receptor, la leyenda y, si corresponde, el período de servicio y el vencimiento de pago. No reconsulta el padrón y la condición heredada se informa a ARCA.
* RN-07: La nota de crédito puede iniciarse desde el aviso de reembolso de HU-E6-05, con el comprobante original precargado. El sistema nunca la emite automáticamente: la emisión requiere confirmación expresa del usuario.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Selecciono un comprobante autorizado para anular | El sistema precarga tipo de nota, datos del receptor y monto máximo disponible | PAN-FAC-04 |
| Ingreso un monto mayor al del comprobante original | El sistema muestra “El monto de la nota de crédito no puede superar el del comprobante original.” y bloquea la emisión | PAN-FAC-04 |
| Intento emitir sin seleccionar un comprobante de referencia | El sistema muestra “Debe seleccionar el comprobante que desea anular.” y no permite continuar | PAN-FAC-04 |
| Confirmo la emisión | La nota de crédito aparece en el listado con estado Pendiente | PAN-FAC-01 |
| ARCA autoriza la nota de crédito | El estado cambia a Autorizado y el comprobante original refleja su anulación total o parcial | PAN-FAC-02 |
| ARCA rechaza la nota de crédito | El sistema muestra el código y la descripción devueltos por ARCA y deja la nota en estado Error con ese detalle visible | PAN-FAC-02 |
| Emito una nota de crédito sobre un comprobante cuyo receptor cambió de condición después | La nota usa la condición del original y no consulta el padrón | PAN-FAC-04 |
| ARCA autoriza la nota | El detalle muestra la misma condición del receptor que el original | PAN-FAC-02 |
| Llego desde el aviso de reembolso de un cobro | Se abre la nota de crédito con el comprobante original precargado y no se emite hasta que confirmo | PAN-FAC-04 |

## **HU-E5-05 — Configurar y administrar los puntos de venta**

| ID | HU-E5-05 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre PuntoDeVenta) |
| **Descripción** | Como administrador, quiero configurar y administrar mis puntos de venta, para emitir comprobantes con la numeración fiscal correspondiente a cada uno. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-FAC-05 (Facturación — Puntos de venta) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* La empresa tiene ARCA conectado.

**Reglas de negocio**

* RN-01: Cada punto de venta tiene un número, una descripción y un estado activo/inactivo, conforme a la entidad PuntoDeVenta.
* RN-02: La numeración de comprobantes es independiente por punto de venta y por tipo de comprobante, conforme al atributo numerador_por_tipo.
* RN-03: Un punto de venta debe estar habilitado en ARCA antes de poder emitir comprobantes con él.
* RN-04: Desactivar un punto de venta impide nuevas emisiones con él pero conserva los comprobantes ya emitidos.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la administración de puntos de venta | Veo el listado con número, descripción y estado de cada punto | PAN-FAC-05 |
| Agrego un punto de venta no habilitado en ARCA | El sistema muestra “El punto de venta no está habilitado en ARCA.” y no permite activarlo | PAN-FAC-05 |
| Agrego un punto de venta habilitado en ARCA | Queda disponible para la emisión de comprobantes | PAN-FAC-05 |
| Intento crear un punto de venta con un número ya existente | El sistema muestra “Ya existe un punto de venta con ese número.” y bloquea el guardado | PAN-FAC-05 |
| Desactivo un punto de venta | No se pueden emitir nuevos comprobantes con él, pero los existentes se conservan | PAN-FAC-05 |

# **Épica 6 — Cobros**

**Bounded Contexts asociados:** BC7 Cobros [CORE]
**Acciones de dominio (Bloque K):** GenerarCobro (y métodos sobre Cobro: cancelar, reembolsar)
Esta épica agrupa las historias del núcleo de cobranzas: la generación de links de pago, el seguimiento del estado de los cobros, su cancelación y reembolso, y la asociación de cobros a comprobantes y turnos. Equivalencia UI–dominio: las etiquetas Pagado y En mora que muestra la interfaz corresponden, respectivamente, a los estados de dominio APROBADO y VENCIDO del agregado Cobro. El estado del dominio es la fuente de verdad; las etiquetas son solo de presentación. En estas historias, “pagado” siempre refiere al estado del Cobro confirmado por MercadoPago (APROBADO), no a la cancelación total del saldo de un comprobante. Los mensajes de validación entre comillas son textos del sistema; los atribuidos a MercadoPago son devueltos por la plataforma y se citan a modo de ejemplo.

## **HU-E6-01 — Consultar el estado de los cobros**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E6-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | (consulta sobre Cobro) |
| **Descripción** | Como usuario del panel, quiero ver el estado general de todos los cobros del período con métricas de resumen, para tener visibilidad de lo aprobado, lo pendiente y lo vencido (mostrado en la interfaz como cobrado, pendiente y en mora). |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-COB-01 (Cobros — Listado) |

**Precondiciones**

* El usuario tiene sesión iniciada con cualquier rol.
* Existe al menos un cobro registrado.

**Reglas de negocio**

* RN-01: Las métricas del encabezado (cobrado, pendiente, en mora, tasa de cobro) se calculan sobre el período activo; el período por defecto es el mes en curso. En estas métricas, cobrado agrupa los cobros en estado APROBADO y en mora agrupa los cobros en estado VENCIDO. “Cobrado en el período” se mide por la fecha de pago del cobro (fecha_pago), no por su fecha de creación, y descuenta los reembolsos en el período en que se devolvió el dinero (HU-E6-05 RN-11). La tasa de cobro se calcula solo sobre los cobros creados en el período, de modo que no puede superar el 100 %.
* RN-02: El listado puede filtrarse por estado de cobro (PENDIENTE, APROBADO, VENCIDO, CANCELADO, REEMBOLSADO_PARCIAL, REEMBOLSADO), mostrados con sus etiquetas de interfaz.
* RN-03: Un cobro pasa al estado VENCIDO automáticamente al superar su vencimiento sin confirmación de pago.
* RN-04: El rol Solo Lectura accede a la consulta sin posibilidad de generar, cancelar ni reembolsar cobros.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al listado de cobros | Veo las métricas del período (cobrado, pendiente, en mora, tasa de cobro) y la lista de cobros con su estado | PAN-COB-01 |
| Filtro por estado en mora | Veo solo los cobros en estado VENCIDO (etiqueta “En mora”) ordenados por antigüedad | PAN-COB-01 |
| Un cobro supera su vencimiento sin pago | Su estado pasa automáticamente a VENCIDO (etiqueta “En mora”) | PAN-COB-01 |
| No hay cobros que coincidan con el filtro | El sistema muestra el mensaje “No hay cobros para los filtros seleccionados.” | PAN-COB-01 |
| Ingreso como Solo Lectura | Veo la información sin acciones de generación, cancelación ni reembolso | PAN-COB-01 |
| Un cobro creado en febrero se paga en marzo y miro marzo | Su monto suma en “cobrado” de marzo y no en el de febrero | PAN-COB-01 |
| Miro un período en el que se pagaron cobros creados en períodos anteriores | La tasa de cobro se calcula solo con los cobros creados en el período y no supera el 100 % | PAN-COB-01 |

## **HU-E6-02 — Consultar el detalle de un cobro**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E6-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | (consulta sobre Cobro) |
| **Descripción** | Como usuario del panel, quiero ver el detalle completo de un cobro, para conocer el historial de recordatorios, el estado del link de pago y los datos del cliente. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-COB-02 (Cobros — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con cualquier rol.
* El cobro existe y tiene al menos un link de pago generado.

**Reglas de negocio**

* RN-01: El detalle muestra el historial de recordatorios con timestamp, canal, estado de lectura y el próximo recordatorio programado, conforme a la entidad Recordatorio.
* RN-02: El estado del link de pago se sincroniza con MercadoPago; si el cliente paga, el estado del cobro pasa a APROBADO (mostrado en la interfaz como “Pagado”) de forma automática mediante el webhook.
* RN-03: Un link de pago activo puede copiarse desde el detalle para envío manual.
* RN-04: El rol Solo Lectura accede al detalle sin acciones de gestión.
* RN-05: El detalle muestra el medio de pago, la fecha de pago y, si el pago fue por transferencia, el número de operación.
* RN-06: Si el cobro tiene reembolsos, el detalle muestra el monto acumulado reembolsado y cada reembolso registrado con su fecha, referencia, motivo y usuario (HU-E6-05).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro un cobro del listado | Veo monto adeudado, datos del cliente, detalle del cobro, link de pago y recordatorios | PAN-COB-02 |
| El cliente paga el cobro | El estado pasa a APROBADO (etiqueta “Pagado”) automáticamente y se detienen los recordatorios | PAN-COB-02 |
| Copio el link de pago | El sistema copia el link y muestra la confirmación “Link copiado al portapapeles.” | PAN-COB-02 |
| Abro un cobro pagado | Veo el medio de pago y la fecha de pago, y el número de operación si fue por transferencia | PAN-COB-02 |
| Abro un cobro con reembolsos registrados | Veo el acumulado reembolsado y el detalle de cada reembolso | PAN-COB-02 |
| Ingreso como Solo Lectura | Veo el detalle sin acciones de gestión | PAN-COB-02 |

## **HU-E6-03 — Generar un link de cobro para un cliente**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E6-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | GenerarCobro |
| **Descripción** | Como administrador u operador, quiero generar un link de pago de MercadoPago para un cliente, para cobrar operaciones que no provienen de una factura automática. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-COB-03 (Cobros — Nuevo cobro) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* La empresa tiene MercadoPago conectado.
* El cliente existe en Datos Maestros.

**Reglas de negocio**

* RN-01: El link se genera vía API de MercadoPago; el sistema almacena el identificador de preferencia para rastrear el pago, conforme al atributo mp_preference_id de la entidad Cobro.
* RN-02: El concepto y el monto son obligatorios; el monto debe ser mayor a cero y en pesos argentinos.
* RN-03: Al generar el link, el sistema inicia la cadena de recordatorios escalonados por WhatsApp.
* RN-04: Un cobro puede tener un solo link de pago activo a la vez.
* RN-05: PAN-COB-03 se puede completar sin haber elegido un cliente antes. Incluye un selector obligatorio de clientes activos, con búsqueda por nombre o CUIT.
* RN-06: La acción “Generar cobro” desde la fila del cliente en PAN-DM-01 se mantiene y abre PAN-COB-03 con ese cliente preseleccionado, editable.
* RN-07: El cobro no crea clientes. Si el selector no encuentra resultados, ofrece un enlace a Clientes (PAN-DM-01) para crearlo allí, donde se valida su CUIT contra ARCA (HU-E4-01 RN-02).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Intento generar sin completar el concepto | El sistema muestra “Debe ingresar un concepto para el cobro.” y el botón Generar permanece deshabilitado | PAN-COB-03 |
| Ingreso un monto cero o negativo | El sistema muestra “El monto debe ser mayor a cero.” y no permite continuar | PAN-COB-03 |
| Confirmo la generación con datos válidos | El link aparece en el detalle con estado Activo y comienza la cadena de recordatorios | PAN-COB-02 |
| MercadoPago no responde al generar el link | El sistema muestra “No se pudo generar el link de pago. Intente nuevamente.” y no crea el cobro | PAN-COB-03 |
| Ya existe un link activo para ese cobro y genero uno nuevo | El sistema invalida el anterior, activa el nuevo y registra el cambio en la bitácora | PAN-COB-02 |
| Abro “Nuevo cobro” desde el menú | Veo un selector de clientes sin necesidad de ir a Clientes | PAN-COB-03 |
| Intento generar sin elegir cliente | El sistema muestra “Debe seleccionar un cliente.” y el botón Generar permanece deshabilitado | PAN-COB-03 |
| Uso “Generar cobro” desde la fila de un cliente | PAN-COB-03 se abre con ese cliente preseleccionado | PAN-COB-03 |
| Busco un cliente que no existe | El selector no ofrece resultados y muestra un enlace a Clientes | PAN-COB-03 |

## **HU-E6-04 — Cancelar un cobro**

| ID | HU-E6-04 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (gestión sobre Cobro) |
| **Descripción** | Como administrador u operador, quiero cancelar un cobro pendiente o vencido, para dar de baja una deuda que ya no corresponde cobrar. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-COB-02 (Cobros — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* El cobro existe y tiene estado PENDIENTE o VENCIDO (etiquetas “Pendiente” o “En mora”).

**Reglas de negocio**

* RN-01: Solo pueden cancelarse cobros en estado PENDIENTE o VENCIDO; un cobro APROBADO no es cancelable.
* RN-02: La cancelación requiere un motivo obligatorio de al menos 10 caracteres.
* RN-03: La cancelación lleva el cobro al estado CANCELADO, invalida el link de pago activo si existe y detiene los recordatorios asociados.
* RN-04: La cancelación queda registrada en la bitácora con el motivo, el usuario y el timestamp.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Intento cancelar un cobro ya aprobado | El sistema muestra “Un cobro pagado no puede cancelarse. Si corresponde, emita un reembolso.” | PAN-COB-02 |
| Inicio la cancelación de un cobro pendiente o en mora | El sistema solicita un motivo obligatorio antes de confirmar | PAN-COB-02 |
| Confirmo la cancelación con un motivo de menos de 10 caracteres | El sistema muestra “El motivo debe tener al menos 10 caracteres.” y no permite confirmar | PAN-COB-02 |
| Confirmo la cancelación con un motivo válido | El cobro pasa a CANCELADO, el link se invalida y se detienen los recordatorios | PAN-COB-02 |

## **HU-E6-05 — Reembolsar un cobro**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E6-05 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (gestión sobre Cobro) |
| **Descripción** | Como administrador, quiero reembolsar total o parcialmente un cobro aprobado, o registrar el reembolso que hice por fuera de la plataforma, para devolver al cliente un pago que corresponde restituir y dejar constancia de ello. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-COB-02 (Cobros — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El cobro existe y tiene estado APROBADO (etiqueta “Pagado”) o REEMBOLSADO_PARCIAL (etiqueta “Reembolsado parcialmente”).
* Para reembolsar por la API de MercadoPago, el cobro se pagó por link y la empresa tiene MercadoPago conectado.

**Reglas de negocio**

* RN-01: Solo pueden reembolsarse cobros con estado APROBADO o REEMBOLSADO_PARCIAL.
* RN-02: El cobro conserva el monto acumulado reembolsado. Pasa al estado REEMBOLSADO_PARCIAL (etiqueta “Reembolsado parcialmente”) cuando 0 < reembolsado < monto del cobro, y al estado REEMBOLSADO solo cuando reembolsado = monto del cobro. La suma de los reembolsos nunca puede exceder el monto del cobro. Los montos se manejan con Decimal. Vale para ambos medios de pago.
* RN-03: El reembolso de un cobro pagado por link se ejecuta vía API de MercadoPago; si es rechazado, el cobro mantiene su estado y su acumulado, y se notifica al administrador.
* RN-04: El reembolso por API de MercadoPago es asíncrono; el estado y el acumulado se actualizan cuando MercadoPago confirma.
* RN-05: Las acciones de esta historia están restringidas al rol Administrador; el Operador puede ver el detalle pero no reembolsar ni registrar reembolsos.
* RN-06: Todo reembolso queda registrado en la bitácora con usuario y timestamp.
* RN-07: Un cobro pagado por transferencia (HU-E6-08) se devuelve manualmente por fuera de la plataforma y el Administrador lo registra con la acción “Registrar reembolso”. Los datos a ingresar son: monto, fecha en que se devolvió el dinero, referencia opcional de la devolución (número de operación o comprobante bancario) y motivo. Para estos cobros no se ofrece el reembolso por API.
* RN-08: El registro de un reembolso de transferencia es declarativo: el sistema no puede verificar dinero saliente. Los registros nunca se borran; un error se corrige con un nuevo registro visible que deja constancia de la corrección.
* RN-09 (efecto fiscal): devolver dinero no anula el comprobante. Si el cobro está asociado a un comprobante, tras registrar o confirmar el reembolso el sistema advierte que corresponde emitir una nota de crédito (HU-E5-04) y ofrece un acceso directo a ella. Nunca la emite automáticamente, porque es un documento fiscal irreversible.
* RN-10 (saldo): un reembolso aumenta el saldo pendiente del comprobante asociado (HU-E6-06 RN-05) mediante el evento de dominio PagoReembolsado, simétrico a PagoConfirmado.
* RN-11 (reportes): un reembolso resta de “cobrado” en el período en que se devolvió el dinero, no en el del pago original.
* RN-12: Un cobro reembolsado no reactiva los recordatorios.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Intento reembolsar un cobro que no está aprobado | El sistema muestra “Solo pueden reembolsarse cobros pagados.” y no ofrece la acción | PAN-COB-02 |
| Ingreso un monto de reembolso mayor al monto pendiente de reembolsar | El sistema muestra “El monto a reembolsar no puede superar el monto pendiente de reembolso del cobro.” y bloquea la acción | PAN-COB-02 |
| Confirmo el reembolso con monto válido | El sistema envía la solicitud y el cobro muestra “Reembolso en proceso” | PAN-COB-02 |
| MercadoPago confirma un reembolso por el monto total del cobro | El cobro pasa a REEMBOLSADO y se registra el monto devuelto | PAN-COB-02 |
| MercadoPago confirma un reembolso menor al monto del cobro | El cobro pasa a REEMBOLSADO_PARCIAL (“Reembolsado parcialmente”) y muestra el acumulado reembolsado | PAN-COB-02 |
| Reembolso el resto de un cobro reembolsado parcialmente hasta igualar su monto | El cobro pasa a REEMBOLSADO | PAN-COB-02 |
| MercadoPago rechaza el reembolso | El cobro mantiene su estado APROBADO y el sistema notifica al administrador con el motivo devuelto por MercadoPago | PAN-COB-02 |
| Ingreso como Operador al detalle de un cobro pagado | Veo el detalle pero la acción de reembolso no está disponible | PAN-COB-02 |
| Abro un cobro pagado por transferencia como Administrador | No se ofrece el reembolso por API y sí la acción “Registrar reembolso” | PAN-COB-02 |
| Registro un reembolso de transferencia con monto, fecha y motivo | El sistema lo guarda, actualiza el acumulado y el estado, y lo deja en la bitácora con usuario y timestamp | PAN-COB-02 |
| Registro un reembolso que haría superar el monto del cobro | El sistema muestra el mensaje de monto máximo y no lo registra | PAN-COB-02 |
| Registro o confirmo el reembolso de un cobro asociado a un comprobante | El sistema advierte que corresponde una nota de crédito y ofrece el acceso directo, sin emitirla | PAN-COB-02 |
| Se reembolsa un cobro asociado a un comprobante | El saldo pendiente del comprobante aumenta en el monto reembolsado | PAN-FAC-02 |
| Un cobro pagado se reembolsa | No se reactivan los recordatorios | PAN-COB-02 |
| Un reembolso se devolvió en un período distinto al del pago | Resta de “cobrado” en el período de la devolución | PAN-COB-01 |

## **HU-E6-06 — Asociar un cobro a un comprobante existente**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E6-06 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | GenerarCobro |
| **Descripción** | Como administrador u operador, quiero asociar un cobro a un comprobante ya emitido, para vincular el pago con su documento fiscal y actualizar su saldo pendiente. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-COB-03 (Cobros — Nuevo cobro) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* Existe un comprobante autorizado con saldo pendiente.

**Reglas de negocio**

* RN-01: El cobro asociado referencia al comprobante, conforme al atributo comprobante_id de la entidad Cobro.
* RN-02: El monto del cobro no puede superar el saldo pendiente del comprobante.
* RN-03: Al confirmarse el pago (estado APROBADO), el sistema reduce el saldo pendiente del comprobante en el monto cobrado.
* RN-04: Un comprobante puede tener varios cobros asociados hasta saldar su total (pagos parciales).
* RN-05: Al registrarse o confirmarse un reembolso de un cobro asociado (HU-E6-05), el sistema aumenta el saldo pendiente del comprobante en el monto reembolsado.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Genero un cobro y lo asocio a un comprobante con saldo | El sistema vincula el cobro al comprobante | PAN-COB-03 |
| Ingreso un monto mayor al saldo pendiente del comprobante | El sistema muestra “El monto no puede superar el saldo pendiente del comprobante.” e indica el saldo disponible | PAN-COB-03 |
| El cliente paga un cobro parcial | El cobro pasa a APROBADO y el saldo pendiente del comprobante se reduce en el monto cobrado | PAN-FAC-02 |
| Se reembolsa un cobro asociado | El saldo pendiente del comprobante aumenta en el monto reembolsado | PAN-FAC-02 |

## **HU-E6-07 — Asociar un cobro a un turno como seña**

| ID | HU-E6-07 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | GenerarCobro |
| **Descripción** | Como administrador u operador, quiero asociar un cobro a un turno como seña, para asegurar la reserva mediante un pago anticipado del cliente. |
| **Prioridad** | Baja |
| **Complejidad** | Media |
| **Pantalla** | PAN-COB-03 (Cobros — Nuevo cobro) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* Existe un turno reservado al cual asociar la seña.

**Reglas de negocio**

* RN-01: El cobro de seña referencia al turno, conforme al atributo turno_id de la entidad Cobro.
* RN-02: El estado del pago de la seña (APROBADO) puede condicionar la confirmación del turno, según la regla de negocio configurada.
* RN-03: Si el turno se cancela, el tratamiento de la seña (reembolso o retención) sigue la política de turnos vigente.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Genero un cobro y lo asocio a un turno como seña | El sistema vincula el cobro al turno | PAN-COB-03 |
| El cliente paga la seña | El cobro pasa a APROBADO y el turno refleja la seña abonada | PAN-AGE-02 |
| El turno se cancela con seña pagada | El sistema aplica la política de turnos vigente sobre la seña | PAN-AGE-02 |

## **HU-E6-08 — Registrar un cobro pagado por transferencia**

> Incorporada por ADR-0009 (2026-09-29).

| ID | HU-E6-08 |
| :---- | :---- |
| **Actor** | Administrador / Operador (y el Sistema, cuando la verificación la dispara HU-E8-06) |
| **Acción Bloque K** | (gestión sobre Cobro) |
| **Descripción** | Como administrador u operador, quiero registrar el pago de un cobro hecho por transferencia ingresando su número de operación, para que el sistema lo confirme automáticamente contra MercadoPago sin revisar comprobantes a mano. |
| **Prioridad** | Media |
| **Complejidad** | Alta |
| **Pantalla** | PAN-COB-02 (Cobros — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador (o la verificación la dispara el Sistema desde HU-E8-06).
* El cobro existe y tiene estado PENDIENTE o VENCIDO.
* La empresa tiene MercadoPago conectado (HU-E2-02).

**Reglas de negocio**

* RN-01: El cobro tiene un medio de pago: LINK_MERCADOPAGO (por defecto, cobros de HU-E6-03) o TRANSFERENCIA. Pasa a TRANSFERENCIA solo cuando el pago se confirma por esta vía. El cobro siempre nace por HU-E6-03 y la transferencia se registra sobre un cobro existente.
* RN-02: La confirmación es determinista y no requiere intervención humana. El sistema consulta la API de MercadoPago con el número de operación y confirma solo si se cumplen todas estas condiciones:
  * a) la operación existe y pertenece a la cuenta de MercadoPago de la empresa (destino igual a la cuenta del negocio);
  * b) su estado es aprobado;
  * c) el monto es exactamente el del cobro, en pesos, comparado con Decimal;
  * d) la fecha de la operación no es anterior a la creación del cobro;
  * e) la identidad del pagador coincide con la del cliente del cobro (RN-10).
* RN-03: Idempotencia por número de operación.
  * Un número de operación produce efecto una sola vez por empresa.
  * El mismo comprobante enviado de nuevo sobre el mismo cobro no genera efecto adicional y se informa que ya está registrado.
  * Aplicarlo a otro cobro se rechaza.
  * La unicidad también cubre los pagos recibidos por link (mp_payment_id).
* RN-04: Al confirmarse, en una única operación atómica:
  * el cobro pasa a APROBADO, con medio TRANSFERENCIA, número de operación y fecha de pago;
  * se invalida el link activo;
  * se detienen los recordatorios;
  * se publica el evento PagoConfirmado existente, que reduce el saldo del comprobante asociado (HU-E6-06 RN-03) y dispara la confirmación al cliente (HU-E8-04 RN-01);
  * todo queda en la bitácora.
* RN-05: Si MercadoPago no confirma (rechazo, incumplimiento de RN-02, timeout, error o no encontrada tras reintentos), el cobro sigue en su estado y el caso se escala a una persona (HU-E8-05, con motivo “pago no verificado”). Toda llamada tiene timeout explícito y reintentos con backoff acotados: 3 intentos en 10 minutos.
* RN-06: No se aplica a cobros APROBADO, CANCELADO, REEMBOLSADO ni REEMBOLSADO_PARCIAL. Si el cobro ya está APROBADO, se trata como posible pago duplicado: no se aplica y se escala.
* RN-07: Solo se persisten número de operación, monto, fecha, estado y resultado de la verificación (incluido el resultado coincide / no coincide de RN-10). Los datos del pagador y las cuentas de la respuesta de MercadoPago no se guardan ni se registran en logs.
* RN-08: Tras 3 verificaciones fallidas sobre un mismo cobro en 24 h, no se aceptan más números por ese camino hasta que un usuario del panel use “Reintentar verificación”.
* RN-09: El rol Solo Lectura ve el medio y el número de operación sin acciones. En esta versión no existe confirmación manual sin verificación.
* RN-10 (identidad del pagador): la operación solo confirma el cobro si la identificación del pagador (DNI o CUIT) devuelta por la API de MercadoPago coincide con el CUIT del cliente del cobro; si MercadoPago informa un DNI, se compara con el documento que integra el CUIT del cliente. Si no coincide (por ejemplo, un familiar o una empresa que pagó en nombre del cliente) o el cliente no tiene CUIT cargado, el cobro sigue pendiente y el caso se escala a una persona (HU-E8-05). La comparación la hace en memoria código determinista de Cobros; la identificación del pagador no se persiste ni se registra en logs, solo su resultado (coincide / no coincide).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Registro un número de operación válido, aprobado, por el monto exacto, a la cuenta de la empresa y con pagador que coincide con el cliente | El cobro pasa a APROBADO con medio “Transferencia”, se detienen los recordatorios, se invalida el link y baja el saldo del comprobante | PAN-COB-02 |
| Registro el mismo número dos veces sobre el mismo cobro | El sistema informa “Esta operación ya está registrada en este cobro.” y no genera efecto nuevo | PAN-COB-02 |
| Registro un número ya usado en otro cobro | El sistema lo rechaza con “Esta operación ya fue aplicada a otro cobro.” | PAN-COB-02 |
| El monto de la operación difiere del del cobro | El cobro sigue pendiente y el caso se escala a una persona | PAN-COB-02 |
| La operación es de otra cuenta o no está aprobada | El cobro sigue pendiente y el caso se escala | PAN-COB-02 |
| El pagador de la operación no coincide con el CUIT del cliente del cobro | El cobro sigue pendiente, el caso se escala y no se guarda la identificación del pagador | PAN-COB-02 |
| MercadoPago no responde | Tras los reintentos, el cobro sigue pendiente, se escala y se notifica | PAN-COB-02 |
| El cobro ya está APROBADO por link | El sistema no aplica la transferencia y escala por posible pago duplicado | PAN-COB-02 |
| Un usuario usa “Reintentar verificación” sobre un caso escalado | El sistema repite la verificación con las mismas reglas | PAN-COB-02 |
| Ingreso como Solo Lectura | No tengo la acción de registrar | PAN-COB-02 |

# **Épica 7 — Agenda**

**Bounded Contexts asociados:** BC8 Agenda [CORE]
**Acciones de dominio (Bloque K):** ReservarTurno, CancelarTurno, ReprogramarTurno, MarcarTurnoCompletado, MarcarNoShow
Esta épica agrupa las historias de gestión de la agenda desde el panel: la visualización de turnos, su cancelación, reprogramación y registro de asistencia, y la configuración de los recursos reservables con su disponibilidad y excepciones. Conforme al modelo, la reprogramación es una operación que modifica la franja horaria del turno y conserva su estado; no constituye un estado en sí mismo. Los mensajes de validación entre comillas son textos del sistema.

## **HU-E7-01 — Ver la agenda de turnos desde el panel**

| ID | HU-E7-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | (consulta sobre Turno) |
| **Descripción** | Como usuario del panel, quiero ver la agenda de turnos, para conocer la ocupación de los recursos y el estado de cada turno. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-AGE-01 (Agenda — Vista de turnos) |

**Precondiciones**

* El usuario tiene sesión iniciada con cualquier rol.
* Existe al menos un recurso reservable configurado (HU-E7-04).

**Reglas de negocio**

* RN-01: La agenda puede visualizarse por recurso y por rango de fechas; la vista por defecto es el día en curso.
* RN-02: Los estados visibles de un turno son Reservado, Confirmado, Cancelado, Completado y No se presentó, conforme a la enumeración de estados del modelo. La reprogramación de un turno es una acción que modifica su franja horaria y conserva su estado; no constituye un estado en sí mismo.
* RN-03: El rol Solo Lectura visualiza la agenda sin posibilidad de reservar, cancelar ni reprogramar turnos.
* RN-04: Además de los turnos originados por el agente, el administrador y el operador pueden crear turnos manualmente desde el panel (ver HU-E7-06).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro la agenda | Veo los turnos del recurso y rango seleccionados con su estado | PAN-AGE-01 |
| Un turno fue reprogramado | Veo el turno en su nueva franja conservando su estado; no aparece un estado “Reprogramado” | PAN-AGE-01 |
| No hay turnos para el rango seleccionado | El sistema muestra “No hay turnos para el período seleccionado.” | PAN-AGE-01 |
| Ingreso como Solo Lectura | Visualizo la agenda sin acciones de gestión | PAN-AGE-01 |

## **HU-E7-02 — Cancelar o reprogramar un turno desde el panel**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E7-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | CancelarTurno / ReprogramarTurno |
| **Descripción** | Como administrador u operador, quiero cancelar o reprogramar un turno desde el panel, para gestionar novedades que el agente no resuelve automáticamente. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-AGE-02 (Agenda — Detalle de turno) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* El turno existe y está en estado Reservado o Confirmado.

**Reglas de negocio**

* RN-01: La reprogramación verifica disponibilidad del recurso en el nuevo horario; si la franja está ocupada, el sistema rechaza la operación por solapamiento.
* RN-02: La reprogramación modifica la franja horaria del turno y conserva su estado.
* RN-03: Al cancelar, el sistema notifica al cliente por WhatsApp si tiene número registrado.
* RN-04: Al reprogramar, el sistema notifica al cliente con el nuevo horario por WhatsApp si tiene número registrado, salvo en la corrección a posteriori (RN-07).
* RN-05: Ambas acciones quedan registradas en la bitácora.
* RN-06: No se puede reprogramar un turno a un instante ya transcurrido. La comparación es contra el instante actual, no solo el día, y se hace al confirmar. Esto vale para el Operador y para el agente de WhatsApp, que nunca pueden reprogramar al pasado. Mensaje: “No se puede reprogramar un turno a un horario que ya pasó.”
* RN-07 (corrección a posteriori, excepción exclusiva del Administrador): el Administrador puede reprogramar un turno a un instante ya pasado con las mismas reglas de la carga a posteriori de HU-E7-06 RN-07: la nueva franja debe haber finalizado; se sigue rechazando el solapamiento con otros turnos reales del recurso, sin exigir disponibilidad base ni respetar el intervalo entre turnos; no se envía mensaje de WhatsApp al cliente; y queda en la bitácora marcada como “corrección a posteriori”, con el usuario.
* RN-08: La reprogramación conserva la duración, que debe seguir entre 5 y 480 minutos, y considera el intervalo entre turnos del recurso en el chequeo de solapamiento (HU-E7-04 RN-07), salvo en la corrección a posteriori.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro un turno de la agenda | Veo su detalle y las acciones disponibles según su estado | PAN-AGE-02 |
| Cancelo un turno Reservado o Confirmado | El turno pasa a Cancelado y el cliente recibe notificación si tiene número registrado | PAN-AGE-02 |
| Reprogramo a una franja disponible | El turno se mueve a la nueva franja conservando su estado, el cliente recibe notificación y queda en la bitácora | PAN-AGE-02 |
| Reprogramo a una franja ocupada | El sistema muestra “El horario seleccionado no está disponible.” y mantiene el turno en su franja original | PAN-AGE-02 |
| Reprogramo a una hora posterior a la actual | El turno se mueve conservando su estado | PAN-AGE-02 |
| Ingreso como Operador y reprogramo a una hora de hoy ya transcurrida | El sistema muestra “No se puede reprogramar un turno a un horario que ya pasó.” y mantiene el turno en su franja original | PAN-AGE-02 |
| Como Administrador reprogramo a una franja pasada ya finalizada y libre | El turno se mueve, no se envía mensaje al cliente y la bitácora lo marca como “corrección a posteriori” con mi usuario | PAN-AGE-02 |
| Como Administrador reprogramo a una franja pasada que se solapa con otro turno del recurso | El sistema muestra “El horario seleccionado no está disponible.” y mantiene el turno en su franja original | PAN-AGE-02 |

## **HU-E7-03 — Registrar la asistencia o inasistencia a un turno**

| ID | HU-E7-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | MarcarTurnoCompletado / MarcarNoShow |
| **Descripción** | Como administrador u operador, quiero registrar si un turno fue cumplido o si el cliente no se presentó, para mantener la trazabilidad de la agenda y habilitar la facturación del servicio prestado. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-AGE-02 (Agenda — Detalle de turno) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* El turno existe y su horario ya transcurrió.

**Reglas de negocio**

* RN-01: Marcar como Completado o No se presentó solo está disponible cuando la hora del turno ya pasó.
* RN-02: Un turno marcado como Completado habilita la emisión del comprobante asociado al servicio.
* RN-03: El registro de asistencia o inasistencia queda en la bitácora.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Intento marcar asistencia en un turno futuro | El sistema no ofrece la acción e indica “El turno aún no transcurrió.” | PAN-AGE-02 |
| Marco un turno pasado como Completado | El turno pasa a Completado y habilita la facturación del servicio | PAN-AGE-02 |
| Marco un turno pasado como No se presentó | El turno pasa a No se presentó y queda registrado en la bitácora | PAN-AGE-02 |

## **HU-E7-04 — Definir la disponibilidad de un recurso reservable**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E7-04 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre RecursoReservable) |
| **Descripción** | Como administrador, quiero crear recursos reservables y definir su disponibilidad semanal, para que el agente pueda ofrecer turnos reales sin solapamientos. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-AGE-03 (Agenda — Configuración de recursos) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.

**Reglas de negocio**

* RN-01: Un recurso reservable tiene nombre, tipo (persona o espacio) y una disponibilidad base semanal por día y franja, conforme a las entidades RecursoReservable y PatrónDeDisponibilidad. Cada franja del patrón define además la duración del slot: el paso de la grilla de horarios de inicio que se ofrecen. La duración del slot no es la duración del turno, que es la duracion_estandar_min del servicio (HU-E7-06 RN-08).
* RN-02: Un recurso puede asociarse a uno o más servicios agendables; solo esos servicios pueden reservarse en él.
* RN-03: Desactivar un recurso no cancela los turnos ya reservados; solo impide nuevas reservas.
* RN-04: Debe existir al menos un recurso activo para que el agente pueda ofrecer turnos.
* RN-05: La duración del slot la elige la empresa, entre 5 y 480 minutos, y no puede superar la extensión de la franja.
* RN-06: Cada recurso tiene un intervalo entre turnos opcional, en minutos (0 por defecto, máximo 480), que se agrega después de cada turno.
* RN-07: Un turno nuevo o reprogramado debe empezar a partir del fin del turno anterior más el intervalo, y su fin más el intervalo no debe pisar el inicio del siguiente. El turno debe terminar dentro de la franja; el intervalo posterior al último turno de la franja puede exceder hora_fin. El agente solo ofrece inicios que cumplan lo anterior.
* RN-08: Cambiar el intervalo o la duración del slot aplica a reservas y reprogramaciones nuevas; no mueve turnos existentes.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la configuración de recursos | Veo el listado con nombre, tipo, servicios asociados y estado | PAN-AGE-03 |
| Creo un recurso con disponibilidad base semanal | Queda disponible para reservas en el horario configurado | PAN-AGE-03 |
| Defino una franja con hora de inicio posterior a la de fin | El sistema muestra “La hora de inicio debe ser anterior a la hora de fin.” y no guarda la franja | PAN-AGE-03 |
| Asocio servicios al recurso | Solo esos servicios pueden reservarse en ese recurso | PAN-AGE-03 |
| Desactivo un recurso con turnos futuros | Los turnos reservados se mantienen pero no se permiten nuevas reservas | PAN-AGE-03 |
| Ingreso una duración de slot de 4 o de 481 minutos | El sistema muestra “La duración del slot debe estar entre 5 y 480 minutos.” | PAN-AGE-03 |
| Configuro un intervalo de 10 minutos y hay un turno de 09:00 a 09:30 | El siguiente turno puede empezar a las 09:40 o más tarde | PAN-AGE-03 |
| No configuro intervalo | El intervalo es 0 y los turnos pueden ser contiguos | PAN-AGE-03 |
| Ingreso un intervalo negativo | El sistema lo rechaza y no guarda | PAN-AGE-03 |

## **HU-E7-05 — Registrar excepciones de disponibilidad**

| ID | HU-E7-05 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre RecursoReservable) |
| **Descripción** | Como administrador, quiero registrar excepciones de disponibilidad sobre un recurso, para reflejar feriados, vacaciones o aperturas especiales fuera del horario habitual. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-AGE-03 (Agenda — Configuración de recursos) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* Existe un recurso reservable con disponibilidad base (HU-E7-04).

**Reglas de negocio**

* RN-01: Una excepción define un día específico sin atención o con horario distinto al habitual, conforme a la entidad ExcepciónDeDisponibilidad.
* RN-02: El sistema no permite configurar una excepción que contradiga otra existente para el mismo recurso y fecha.
* RN-03: Las excepciones tienen prioridad sobre la disponibilidad base al calcular los horarios ofrecidos.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Agrego una excepción de día sin atención | El agente no ofrece ese día al reservar | PAN-AGE-03 |
| Agrego una excepción de horario especial | El agente ofrece el horario de la excepción en lugar del habitual | PAN-AGE-03 |
| Intento agregar una excepción que contradice otra existente | El sistema muestra “Ya existe una excepción para esa fecha en este recurso.” y bloquea el guardado | PAN-AGE-03 |

## **HU-E7-06 — Crear un turno manualmente desde el panel**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E7-06 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | ReservarTurno |
| **Descripción** | Como administrador u operador, quiero crear un turno manualmente desde el panel, para agendar atenciones de clientes que no reservan por el canal de WhatsApp (por teléfono, presencialmente o por decisión interna). |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-AGE-02 (Agenda — Detalle de turno) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* Existe al menos un recurso reservable con disponibilidad.
* El cliente existe en Datos Maestros.

**Reglas de negocio**

* RN-01: La creación manual verifica la disponibilidad del recurso en la franja elegida; si está ocupada, el sistema rechaza la operación por solapamiento. El solapamiento considera el intervalo entre turnos del recurso (HU-E7-04 RN-07), salvo en la carga a posteriori (RN-07).
* RN-02: El turno creado manualmente registra su canal de reserva como PANEL, conforme al atributo canal_reserva de la entidad Turno, distinguiéndolo de los originados por el agente.
* RN-03: El servicio seleccionado debe estar asociado al recurso elegido y ser agendable.
* RN-04: Si el cliente tiene número de WhatsApp registrado, el sistema le envía la confirmación del turno por ese canal.
* RN-05: La creación manual queda registrada en la bitácora con el usuario que la ejecutó.
* RN-06: No se puede crear un turno en un instante ya transcurrido. La comparación es contra el instante actual, no solo el día, y se hace al confirmar la creación. Mensaje: “No se puede agendar un turno en un horario que ya pasó.”
* RN-07 (carga a posteriori, excepción exclusiva del Administrador): registra una atención ya realizada, con estas reglas:
  * La franja debe haber finalizado.
  * El turno se crea directamente como Completado, con canal PANEL.
  * No envía confirmación por WhatsApp ni recordatorios.
  * Sigue rechazando solapamientos con otros turnos reales del recurso, pero no exige que la franja esté dentro de la disponibilidad base ni respeta el intervalo entre turnos.
  * Queda en la bitácora marcado como “carga a posteriori”, con el usuario.
  * Habilita la facturación (HU-E7-03 RN-02).
* RN-08: La duración del turno es la duración estándar del servicio elegido (duracion_estandar_min, entre 5 y 480 minutos, HU-E4-02 RN-05) y no se ingresa a mano. La duración del slot del recurso (HU-E7-04 RN-05) es el paso de la grilla de horarios de inicio que se ofrecen, no la duración del turno.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Creo un turno en una franja disponible | El turno queda Reservado con canal de reserva PANEL y aparece en la agenda | PAN-AGE-02 |
| Intento crear un turno en una franja ocupada | El sistema muestra “El horario seleccionado no está disponible.” y no crea el turno | PAN-AGE-02 |
| Selecciono un servicio no asociado al recurso | El sistema no ofrece ese servicio para ese recurso | PAN-AGE-02 |
| Creo el turno para un cliente con WhatsApp registrado | El sistema crea el turno y envía la confirmación al cliente por WhatsApp | PAN-AGE-02 |
| Creo un turno para hoy en una hora anterior a la actual | El sistema muestra “No se puede agendar un turno en un horario que ya pasó.” y no lo crea | PAN-AGE-02 |
| Creo un turno para hoy en una hora posterior a la actual | El sistema lo crea | PAN-AGE-02 |
| Ingreso como Operador y quiero cargar una atención pasada | No tengo disponible la carga a posteriori | PAN-AGE-02 |
| Como Administrador registro una atención ya realizada | El turno queda Completado con canal PANEL, sin mensaje al cliente, y la bitácora marca “carga a posteriori” | PAN-AGE-02 |
| Como Administrador registro una atención pasada que se solapa con otro turno del recurso | El sistema muestra “El horario seleccionado no está disponible.” | PAN-AGE-02 |
| Elijo un servicio agendable de 45 minutos | El turno se crea con duración de 45 minutos y los inicios ofrecidos siguen el paso del slot del recurso | PAN-AGE-02 |

# **Épica 8 — Canal Conversacional (Cliente vía WhatsApp)**

**Bounded Contexts asociados:** BC9 Conversacional [CORE]
**Acciones de dominio (Bloque K):** ReservarTurno, CancelarTurno, ProcesarMensajeEntrante, EscalarConversación
Esta épica agrupa las historias en las que el actor es el cliente final de la PyME, que interactúa con el sistema a través del canal de WhatsApp. A diferencia del resto del modelo, estas historias no tienen pantalla de panel asociada: su interfaz es la conversación. Constituyen el modo de uso principal del producto desde la perspectiva del cliente. Los textos entre comillas son respuestas del agente a modo de ejemplo representativo, no literales fijos.

## **HU-E8-01 — Reservar un turno conversando por WhatsApp**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E8-01 |
| :---- | :---- |
| **Actor** | Cliente final |
| **Acción Bloque K** | ReservarTurno |
| **Descripción** | Como cliente de la PyME, quiero reservar un turno conversando por WhatsApp en lenguaje natural, para agendar una atención sin necesidad de llamar ni usar una aplicación. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | Canal WhatsApp |

**Precondiciones**

* La empresa tiene el agente de WhatsApp activo y dentro de su horario de atención.
* Existe al menos un recurso reservable con disponibilidad.

**Reglas de negocio**

* RN-01: El agente interpreta la intención del mensaje y, si corresponde a una reserva, consulta la disponibilidad real de los recursos antes de ofrecer horarios.
* RN-02: El agente solo ofrece horarios efectivamente disponibles, considerando la disponibilidad base y las excepciones del recurso.
* RN-03: La reserva se confirma mediante un motor determinista que valida la disponibilidad en el momento de confirmar, evitando solapamientos.
* RN-04: Una vez confirmada la reserva, el turno queda registrado y el cliente recibe la confirmación por el mismo canal.
* RN-05: Si durante la conversación el agente no logra interpretar la intención con confianza suficiente, la conversación se deriva a un asesor humano (ver HU-E8-05).
* RN-06: El agente solo ofrece horarios futuros. El motor determinista vuelve a verificar, al confirmar, que el inicio no es anterior al instante actual. En este canal no existe la excepción a posteriori.
* RN-07: La duración del turno es la duración estándar del servicio (duracion_estandar_min, HU-E7-06 RN-08). Los horarios ofrecidos siguen la grilla del slot del recurso y respetan el intervalo entre turnos (HU-E7-04).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Escribo que quiero un turno y para cuándo | El agente interpreta la intención y ofrece horarios disponibles reales, por ejemplo “Tengo disponible el jueves a las 10:30 o el viernes a las 17:00. ¿Cuál prefiere?” | Canal WhatsApp |
| Elijo uno de los horarios ofrecidos | El agente confirma la reserva y registra el turno, por ejemplo “Listo, su turno quedó reservado para el jueves a las 10:30.” | Canal WhatsApp |
| El horario que pido no está disponible | El agente lo indica y ofrece alternativas cercanas disponibles | Canal WhatsApp |
| Dos clientes intentan el mismo horario casi simultáneamente | El motor determinista confirma solo a uno y ofrece al otro alternativas, sin generar solapamiento | Canal WhatsApp |
| El agente no logra entender mi pedido tras varios intentos | La conversación se deriva a un asesor humano | Canal WhatsApp |
| Pido un turno para una fecha u hora que ya pasó | El agente lo indica y ofrece alternativas futuras | Canal WhatsApp |
| El horario ofrecido pasa mientras dudo y luego lo elijo | El motor lo rechaza y el agente ofrece alternativas vigentes | Canal WhatsApp |

## **HU-E8-02 — Cancelar un turno conversando por WhatsApp**

| ID | HU-E8-02 |
| :---- | :---- |
| **Actor** | Cliente final |
| **Acción Bloque K** | CancelarTurno |
| **Descripción** | Como cliente de la PyME, quiero cancelar un turno conversando por WhatsApp, para liberar mi reserva cuando no podré asistir. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | Canal WhatsApp |

**Precondiciones**

* El cliente tiene un turno reservado a su nombre.
* El agente está activo.

**Reglas de negocio**

* RN-01: El agente identifica el turno del cliente a partir de su número y, si tiene más de uno, solicita que indique cuál cancelar.
* RN-02: Al cancelar, el horario queda liberado para nuevas reservas.
* RN-03: Si el turno tenía una seña asociada, el tratamiento sigue la política de turnos vigente.
* RN-04: La cancelación se confirma al cliente por el mismo canal.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Escribo que quiero cancelar mi turno | El agente identifica mi turno y solicita confirmación | Canal WhatsApp |
| Tengo más de un turno reservado | El agente me pide indicar cuál deseo cancelar | Canal WhatsApp |
| No tengo ningún turno reservado | El agente lo indica, por ejemplo “No encuentro turnos reservados a su nombre.” | Canal WhatsApp |
| Confirmo la cancelación | El agente cancela el turno, libera el horario y me lo confirma | Canal WhatsApp |

## **HU-E8-03 — Consultar una FAQ a través del agente**

| ID | HU-E8-03 |
| :---- | :---- |
| **Actor** | Cliente final |
| **Acción Bloque K** | ProcesarMensajeEntrante |
| **Descripción** | Como cliente de la PyME, quiero hacer una consulta frecuente por WhatsApp, para obtener una respuesta inmediata sin esperar atención humana. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | Canal WhatsApp |

**Precondiciones**

* El agente está activo.
* La empresa configuró respuestas frecuentes (FAQ).

**Reglas de negocio**

* RN-01: El agente interpreta la consulta y, si corresponde a una FAQ configurada, responde automáticamente con la respuesta definida, conforme a la entidad FAQ.
* RN-02: La búsqueda de la FAQ adecuada se realiza por significado, no solo por coincidencia exacta de palabras.
* RN-03: Si ninguna FAQ responde la consulta con confianza suficiente, el agente ofrece derivar a un asesor humano.
* RN-04: El sistema registra el uso de cada FAQ para su análisis posterior.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Hago una consulta cubierta por una FAQ | El agente responde automáticamente con la información configurada | Canal WhatsApp |
| Mi consulta no coincide exactamente pero tiene el mismo significado | El agente reconoce la intención y responde la FAQ adecuada | Canal WhatsApp |
| Mi consulta no está cubierta por ninguna FAQ | El agente ofrece derivarme a un asesor humano | Canal WhatsApp |

## **HU-E8-04 — Recibir confirmaciones y recordatorios**

| ID | HU-E8-04 |
| :---- | :---- |
| **Actor** | Cliente final |
| **Acción Bloque K** | (notificación saliente) |
| **Descripción** | Como cliente de la PyME, quiero recibir confirmaciones y recordatorios por WhatsApp, para no olvidar mis turnos ni mis pagos pendientes. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | Canal WhatsApp |

**Precondiciones**

* El cliente tiene un número de WhatsApp registrado.
* Existe un turno o cobro asociado al cliente.

**Reglas de negocio**

* RN-01: El sistema envía confirmación inmediata al concretarse una reserva o un pago.
* RN-02: Los recordatorios de turno y de cobro se despachan según las reglas de escalamiento configuradas (ver historias de sistema).
* RN-03: El cliente puede responder a un recordatorio y esa respuesta inicia una conversación gestionada por el agente.
* RN-04: El estado de entrega y lectura de cada mensaje se registra para seguimiento.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Concreto una reserva | Recibo una confirmación inmediata por WhatsApp | Canal WhatsApp |
| Se acerca la fecha de mi turno | Recibo un recordatorio según la regla configurada | Canal WhatsApp |
| Respondo a un recordatorio | El agente retoma la conversación e interpreta mi respuesta | Canal WhatsApp |

## **HU-E8-05 — Ser derivado a un asesor humano**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E8-05 |
| :---- | :---- |
| **Actor** | Cliente final |
| **Acción Bloque K** | EscalarConversación |
| **Descripción** | Como cliente de la PyME, quiero ser derivado a un asesor humano cuando el agente no puede resolver mi caso, para recibir atención personalizada sin tener que repetir todo desde cero. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | Canal WhatsApp |

**Precondiciones**

* El cliente está en una conversación activa con el agente.

**Reglas de negocio**

* RN-01: La derivación se produce cuando el agente no interpreta la intención con confianza suficiente o cuando el cliente la solicita explícitamente, conforme a la entidad Escalamiento.
* RN-02: Al derivar, el sistema registra el motivo del escalamiento y deja la conversación a la espera de un asesor.
* RN-03: El contexto de la conversación previa queda disponible para el asesor que la atienda, evitando que el cliente deba repetir información.
* RN-04: El cliente recibe un aviso de que su conversación fue derivada.
* RN-05: Un pago por transferencia que no pudo verificarse (HU-E6-08, HU-E8-06), incluido el caso en que la identidad del pagador no coincide con la del cliente, deriva la conversación con el motivo “pago no verificado”, y el asesor ve el cobro y el número de operación.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Solicito explícitamente hablar con una persona | El agente deriva la conversación a un asesor humano y me lo avisa | Canal WhatsApp |
| El agente no entiende mi caso tras varios intentos | La conversación se escala automáticamente | Canal WhatsApp |
| Mi conversación es derivada | Recibo un aviso, por ejemplo “Lo derivo con un asesor que va a continuar la conversación.”, y el asesor cuenta con el contexto previo | Canal WhatsApp |
| Informo una transferencia que no se pudo verificar | La conversación se deriva con el motivo “pago no verificado” y el asesor ve el cobro y el número de operación | Canal WhatsApp |

## **HU-E8-06 — Informar un pago enviando el comprobante por WhatsApp**

> Incorporada por ADR-0009 (2026-09-29).

| ID | HU-E8-06 |
| :---- | :---- |
| **Actor** | Cliente final |
| **Acción Bloque K** | ProcesarMensajeEntrante |
| **Descripción** | Como cliente de la PyME, quiero enviar por WhatsApp el comprobante de mi transferencia de MercadoPago, para que mi pago quede registrado sin llamar ni esperar atención humana. |
| **Prioridad** | Media |
| **Complejidad** | Alta |
| **Pantalla** | Canal WhatsApp |

**Precondiciones**

* La empresa tiene el agente activo y MercadoPago conectado.
* El número del cliente corresponde a un cliente con al menos un cobro PENDIENTE o VENCIDO.
* Está disponible la verificación de HU-E6-08.
* El canal de WhatsApp puede recibir imágenes y documentos.

**Reglas de negocio**

* RN-01: Se aceptan imágenes JPEG o PNG y PDF, hasta 10 MB. Otros tipos o tamaños mayores se responden pidiendo un archivo válido o que el cliente escriba el número de operación. El archivo se procesa con límites de tiempo y memoria.
* RN-02 (el archivo del comprobante no se envía a ningún LLM externo): contiene nombres, CUIT/CUIL y CVU/CBU, y CLAUDE.md §3.6 prohíbe enviar datos personales reales a un LLM sin anonimizar, algo inviable de garantizar sobre una imagen. La extracción del número de operación sigue esta escalera, todo dentro de la infraestructura propia:
  1. si el cliente escribe el número en un mensaje de texto, se extrae con una expresión regular antes de que el mensaje llegue al clasificador de intención, sin modelo; ni el número ni ningún token con forma de CUIT o CUIL del mismo mensaje se envían al LLM;
  2. si es PDF con texto, se lee el texto localmente;
  3. si es imagen, OCR local;
  4. si falla o es ambigua, el agente pide al cliente que escriba el número de operación.
* RN-03: Toda salida de extracción se valida contra un esquema: el número de operación es solo dígitos con largo permitido, el monto es Decimal y la fecha es válida. Si no cumple, se trata como no extraída. Monto y fecha son solo pistas (por ejemplo, para orientar entre varios cobros) y nunca deciden.
* RN-04: El cobro se identifica por el número de teléfono del cliente. Con un solo cobro pendiente se continúa; con varios el agente pregunta cuál y nunca elige por su cuenta; con ninguno lo informa y ofrece derivar (HU-E8-05).
* RN-05: Ningún efecto monetario se dispara desde una salida de modelo. Solo la verificación determinista de HU-E6-08 contra la API de MercadoPago, incluida la identidad del pagador, confirma el cobro. La respuesta al cliente se arma con plantillas a partir del resultado de esa verificación, no con texto libre del modelo.
* RN-06: La respuesta al cliente es una de tres: confirmado, en verificación, o derivado a un asesor (HU-E8-05). No se revelan motivos técnicos (cuentas, montos, coincidencias ni identidad del pagador).
* RN-07: El archivo y su texto extraído nunca llegan al LLM. En mensaje.contenido se guarda un marcador (“comprobante recibido”) y no el texto extraído, y nada de esto se registra en logs. El contenido del archivo es dato no confiable y nunca se interpreta como instrucciones.
* RN-08 (retención):
  * El archivo se guarda en almacenamiento privado, cifrado, con acceso solo para Administrador y Operador mediante enlaces firmados de corta duración, y cada acceso queda en la bitácora.
  * Si la verificación confirma el pago, el archivo se elimina de inmediato y solo permanecen los datos estructurados de HU-E6-08.
  * Si el caso se escala, se conserva hasta 30 días después del cierre del escalamiento, con un máximo absoluto de 90 días.
  * Un proceso programado lo elimina.
  * Se elimina también ante un pedido de supresión del titular, salvo obligación legal.
* RN-09: El mismo comprobante enviado dos veces produce un solo efecto (HU-E6-08 RN-03) y el agente responde que ya está registrado. Un mismo mensaje entregado más de una vez por el webhook se procesa una sola vez. Se aplican los límites de intentos de HU-E6-08 RN-08 y un límite de frecuencia por teléfono.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Envío una captura del comprobante y tengo un único cobro pendiente | El agente extrae el número, lo verifica (HU-E6-08) y me responde, por ejemplo “Recibimos su pago de $X. ¡Gracias!” | Canal WhatsApp |
| Tengo varios cobros pendientes | El agente me pregunta a cuál corresponde antes de verificar | Canal WhatsApp |
| No tengo cobros pendientes | El agente lo indica y ofrece derivarme | Canal WhatsApp |
| Envío una imagen ilegible | El agente me pide que escriba el número de operación | Canal WhatsApp |
| Escribo el número de operación en texto | El agente lo toma con una expresión regular antes del clasificador de intención, sin procesar imagen ni usar modelo, y verifica | Canal WhatsApp |
| Escribo el número de operación junto con un CUIT en el mismo mensaje | Ni el número ni el CUIT se envían al LLM | Canal WhatsApp |
| La verificación no confirma el pago o no está disponible | El cobro sigue pendiente, la conversación se deriva y recibo un aviso | Canal WhatsApp |
| Envío el mismo comprobante dos veces | El agente responde que ya está registrado y no hay efecto adicional | Canal WhatsApp |
| Envío un archivo de tipo no soportado | El agente me pide un JPEG, PNG o PDF, o el número escrito | Canal WhatsApp |
| El pago se confirmó | El archivo del comprobante se elimina y no queda su texto en la conversación | Canal WhatsApp |

# **Épica 9 — Atención y Escalamiento (Operador)**

**Bounded Contexts asociados:** BC9 Conversacional [CORE] / BC10 Observabilidad y Auditoría
**Acciones de dominio (Bloque K):** EscalarConversación, AbrirSolicitudDeSoporte
Esta épica agrupa las historias del operador humano que atiende las conversaciones que el agente deriva, resuelve los escalamientos y abre solicitudes de soporte al equipo de CheatSheet. La condición de conversación escalada se deriva de la existencia de un Escalamiento abierto asociado a la conversación, no de un estado de la conversación, cuyos estados son únicamente ACTIVA y ARCHIVADA. Los mensajes de validación entre comillas son textos del sistema.

## **HU-E9-01 — Atender una conversación escalada**

| ID | HU-E9-01 |
| :---- | :---- |
| **Actor** | Operador / Administrador |
| **Acción Bloque K** | EscalarConversación |
| **Descripción** | Como operador, quiero atender una conversación que el agente derivó, para resolver personalmente los casos que la automatización no pudo cerrar. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Pantalla** | PAN-WA-01 (Agente WhatsApp — Conversaciones) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Operador o Administrador.
* Existe una conversación con un escalamiento abierto a la espera de atención.

**Reglas de negocio**

* RN-01: El escalamiento se modela como una entidad propia (Escalamiento) asociada a la conversación; la condición de “escalada” se deriva de la existencia de un escalamiento abierto, no de un estado de la conversación, cuyos estados son únicamente ACTIVA y ARCHIVADA.
* RN-02: Al tomar el escalamiento, el operador asume el control y el agente deja de responder en ese hilo.
* RN-03: El operador dispone del contexto completo de la conversación previa con el agente.
* RN-04: Los mensajes enviados por el operador se distinguen visualmente de los del agente en el historial.
* RN-05: Al devolver el control al agente, este reevalúa la intención del hilo y actualiza su clasificación (Turno, Consulta, Pago, FAQ) automáticamente. El operador puede modificar manualmente esa clasificación antes de devolver el control.
* RN-06: La toma del escalamiento queda registrada con el operador asignado y el timestamp.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Veo una conversación con escalamiento abierto | Puedo tomarla para atenderla personalmente | PAN-WA-01 |
| Tomo el escalamiento | El agente deja de responder y dispongo del contexto previo | PAN-WA-01 |
| Envío un mensaje al cliente | El mensaje se envía por WhatsApp y se distingue del agente en el historial | PAN-WA-01 |
| Devuelvo el control al agente | El agente reevalúa y reclasifica el hilo automáticamente; puedo ajustar esa clasificación antes de devolverlo | PAN-WA-01 |

## **HU-E9-02 — Resolver y cerrar un escalamiento**

| ID | HU-E9-02 |
| :---- | :---- |
| **Actor** | Operador / Administrador |
| **Acción Bloque K** | EscalarConversación |
| **Descripción** | Como operador, quiero resolver y cerrar un escalamiento, para registrar que el caso fue atendido y devolver la conversación al flujo normal. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-WA-01 (Agente WhatsApp — Conversaciones) |

**Precondiciones**

* El operador atendió una conversación con escalamiento abierto (HU-E9-01).

**Reglas de negocio**

* RN-01: Al cerrar el escalamiento, el operador puede devolver la conversación al agente o darla por finalizada.
* RN-02: Si devuelve la conversación al agente, este retoma el hilo con el contexto actualizado por la intervención humana.
* RN-03: El cierre del escalamiento registra el estado final y queda en la bitácora.
* RN-04: Un escalamiento cerrado no puede reabrirse; un nuevo pedido del cliente genera un escalamiento nuevo.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Resuelvo el caso y devuelvo la conversación al agente | El agente retoma el hilo con el contexto actualizado | PAN-WA-01 |
| Resuelvo el caso y lo doy por finalizado | El escalamiento queda cerrado y registrado en la bitácora | PAN-WA-01 |
| Intento reabrir un escalamiento cerrado | El sistema no lo permite; indica que un nuevo pedido del cliente generará un escalamiento nuevo | PAN-WA-01 |

## **HU-E9-03 — Abrir una solicitud de soporte a CheatSheet**

| ID | HU-E9-03 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | AbrirSolicitudDeSoporte |
| **Descripción** | Como administrador, quiero abrir una solicitud de soporte al equipo de CheatSheet, para reportar un problema o pedir ayuda con la plataforma. |
| **Prioridad** | Baja |
| **Complejidad** | Baja |
| **Pantalla** | PAN-SOP-01 (Soporte — Nueva solicitud) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.

**Reglas de negocio**

* RN-01: La solicitud registra asunto, descripción, prioridad y el usuario que la abre, conforme a la entidad SolicitudDeSoporte.
* RN-02: El asunto y la descripción son obligatorios.
* RN-03: La solicitud queda en estado abierto hasta que el equipo de CheatSheet la atienda y la cierre.
* RN-04: El administrador puede consultar el estado de sus solicitudes abiertas.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro una nueva solicitud de soporte | El sistema solicita asunto, descripción y prioridad | PAN-SOP-01 |
| Intento enviar sin asunto o sin descripción | El sistema muestra “El asunto y la descripción son obligatorios.” y no permite enviar | PAN-SOP-01 |
| Envío la solicitud | Queda registrada en estado abierto y puedo consultar su estado | PAN-SOP-01 |

## **HU-E9-04 — Administrar el repositorio de FAQ**

> Modificada por ADR-0012 (2026-10-04).

| ID | HU-E9-04 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre FAQ) |
| **Descripción** | Como administrador, quiero agregar, editar y eliminar preguntas frecuentes del agente y ver cuánto se usa cada una, para que responda automáticamente las consultas más comunes de mis clientes y saber si mis cambios mejoran esas respuestas. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-WA-02 (Agente WhatsApp — Configuración) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El agente está configurado y activo.

**Reglas de negocio**

* RN-01: Cada FAQ tiene una pregunta disparadora y una respuesta; ambos campos son obligatorios, conforme a la entidad FAQ.
* RN-02: El sistema muestra, por cada FAQ, cuántas veces fue usada **en el mes calendario en curso** («Este mes»), **en el mes calendario anterior** («Mes anterior») y **desde su creación** («Total»). Los meses se cuentan en hora de Argentina (America/Argentina/Buenos_Aires): un uso a las 23:30 del último día del mes pertenece a ese mes. Los usos registrados antes de esta modificación no tienen fecha: suman al total y no a ningún mes.
* RN-03: Una FAQ eliminada deja de estar disponible para el agente de forma inmediata.
* RN-04: No existe un límite en la cantidad de FAQ que una empresa puede configurar. De definirse a futuro un modelo de planes, podría incorporarse una restricción; en el alcance actual no aplica.
* RN-05: Un uso se cuenta una sola vez, cuando el agente respondió la consulta con esa FAQ **y** el mensaje de WhatsApp salió (no quedó como fallido). Una coincidencia por debajo del umbral de HU-E8-03 RN-03 no es un uso. Un mismo mensaje entrante reenviado por WhatsApp no genera un segundo uso.
* RN-06: El detalle de cada FAQ muestra su **participación** antes y después de su última edición: los usos de esa FAQ divididos por todas las consultas que el agente respondió con alguna FAQ de la empresa, en la misma cantidad de días antes y después de la edición (como máximo 30 días; menos si la edición o la FAQ son más recientes). Se informa como porcentaje con un decimal. Editar es cambiar el texto de la pregunta o de la respuesta.
* RN-07: Cuando la comparación no puede hacerse, el detalle lo dice en lugar de mostrar un porcentaje: si la FAQ nunca se editó, si se editó hace menos de un día, si se editó durante su primer día (no hay historia previa), o si en uno de los dos lapsos la empresa no tuvo consultas respondidas por FAQ.
* RN-08: Los usos de una FAQ eliminada siguen contando en el total de consultas respondidas de la empresa, para que la participación de las demás no cambie hacia atrás.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Agrego una FAQ nueva | Aparece en el listado con «Este mes», «Mes anterior» y «Total» en cero y disponible para el agente | PAN-WA-02 |
| Intento guardar una FAQ sin pregunta o sin respuesta | El sistema muestra “La pregunta y la respuesta son obligatorias.” y no permite guardar | PAN-WA-02 |
| Elimino una FAQ | El sistema solicita confirmación y, al confirmar, el agente deja de usarla de inmediato | PAN-WA-02 |
| Reviso el listado de FAQ | Cada una muestra cuántas veces fue respondida este mes, el mes anterior y en total | PAN-WA-02 |
| El agente responde con una FAQ el último día del mes a las 22:00 (hora de Argentina) | Ese uso cuenta en «Este mes» de ese mes y, desde el día 1, en «Mes anterior» | PAN-WA-02 |
| El agente encuentra la FAQ pero el WhatsApp no sale | El uso no se cuenta | PAN-WA-02 |
| WhatsApp reenvía el mismo mensaje entrante | La FAQ suma un solo uso | PAN-WA-02 |
| Abro el detalle de una FAQ editada hace 10 días | Veo su participación en los 10 días previos y en los 10 días posteriores a la edición | PAN-WA-02 |
| Abro el detalle de una FAQ que nunca edité | Veo que no hay una edición con la cual comparar | PAN-WA-02 |
| Abro el detalle de una FAQ editada en un lapso sin consultas respondidas por FAQ | Veo «Sin consultas respondidas por FAQ» en ese lapso, no un porcentaje | PAN-WA-02 |

# **Épica 10 — Reportería y Análisis**

**Bounded Contexts asociados:** BC11 Reportería
**Acciones de dominio (Bloque K):** ObtenerKPIsDelDashboard, GenerarReporte, PrevisualizarReporte, GenerarPaqueteContable
Esta épica agrupa las historias de análisis y reportería: la visualización de indicadores del tablero, la generación y descarga de reportes, y la elaboración y distribución del paquete contable mensual al contador externo. Los mensajes de validación entre comillas son textos del sistema.

## **HU-E10-01 — Visualizar los indicadores (KPIs) del tablero**

> Modificada por ADR-0009 (2026-09-29).

| ID | HU-E10-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | ObtenerKPIsDelDashboard |
| **Descripción** | Como usuario del panel, quiero ver el dashboard de reportes del período con métricas de facturación, cobros, turnos y operaciones, para tener una visión consolidada de la actividad comercial. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-REP-01 (Reportería — Tablero) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador, Operador, Solo Lectura o Contador externo.

**Reglas de negocio**

* RN-01: El período por defecto es el mes en curso; el usuario puede cambiarlo con el selector.
* RN-02: Las métricas del encabezado son total facturado, total cobrado, turnos gestionados y operaciones totales, con su variación respecto al período anterior.
* RN-03: El gráfico de facturación por semana muestra el facturado neto agrupado por semana del período.
* RN-04: El rol Contador externo puede ver el dashboard pero no acceder a ningún otro módulo.
* RN-05: El rol Solo Lectura accede a esta consulta sin posibilidad de ejecutar acciones de gestión sobre los datos visualizados.
* RN-06: La pantalla Inicio (código de pantalla a confirmar) muestra el resumen de cobros con el mismo selector de período que Reportes (por defecto, el mes en curso), usando la misma definición de métricas. Esta historia cubre Inicio; no hay una historia aparte.
* RN-07: Reportes incluye visualizaciones de cobranza que siguen el período seleccionado: cobrado por semana y cobros por estado.
* RN-08: “Cobrado”, incluido el “total cobrado” de RN-02 y el “cobrado por semana”, se mide por fecha de pago, y los reembolsos restan en el período en que se devolvió el dinero (HU-E6-05 RN-11). “Cobros por estado” agrupa los cobros creados en el período por su estado actual y lo indica en el subtítulo del gráfico. La tasa de cobro se calcula solo sobre los cobros creados en el período, de modo que no puede superar el 100 % (HU-E6-01 RN-01).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo Reportes | Veo las métricas del encabezado, el gráfico semanal y la distribución por tipo de comprobante | PAN-REP-01 |
| Cambio el período a un mes anterior | Las métricas y gráficos se actualizan para ese período | PAN-REP-01 |
| El período seleccionado no tiene actividad | El sistema muestra “No hay actividad registrada para este período.” | PAN-REP-01 |
| Ingreso como Solo Lectura | Visualizo los indicadores sin acciones de gestión | PAN-REP-01 |
| Ingreso a Inicio | Veo el resumen de cobros del mes en curso con un selector de período | Inicio (código a confirmar) |
| Cambio el período en Inicio | El resumen se actualiza con las mismas cifras que Reportes para ese período | Inicio (código a confirmar) |
| Ingreso a Reportes | Veo “cobrado por semana” y “cobros por estado” además de facturación | PAN-REP-01 |
| Cambio el período | Ambos gráficos de cobranza se actualizan | PAN-REP-01 |
| Un cobro se pagó dentro del período pero se creó antes | Aparece en “cobrado” del período del pago | PAN-REP-01 |
| El período seleccionado solo tiene cobros y ningún comprobante | Veo las métricas de cobranza en lugar del mensaje de período sin actividad | PAN-REP-01 |

## **HU-E10-02 — Previsualizar un reporte antes de generarlo**

| ID | HU-E10-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | PrevisualizarReporte |
| **Descripción** | Como administrador u operador, quiero previsualizar un reporte antes de generarlo, para confirmar que el contenido y el período son los correctos. |
| **Prioridad** | Baja |
| **Complejidad** | Baja |
| **Pantalla** | PAN-REP-01 (Reportería — Tablero) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.

**Reglas de negocio**

* RN-01: La previsualización muestra una estimación del contenido del reporte (cantidad de comprobantes, totales) sin generar el archivo definitivo, conforme a la entidad Reporte.
* RN-02: La previsualización refleja los filtros de período y tipo seleccionados.
* RN-03: La previsualización no consume el ciclo de generación; el usuario puede ajustarla cuantas veces necesite.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Selecciono período y tipo de reporte | Veo una previsualización con la estimación de su contenido | PAN-REP-01 |
| Ajusto los filtros | La previsualización se actualiza sin generar el archivo | PAN-REP-01 |
| Confirmo desde la previsualización | El sistema procede a generar el reporte definitivo | PAN-REP-01 |

## **HU-E10-03 — Generar y descargar un reporte en el formato deseado**

| ID | HU-E10-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | GenerarReporte |
| **Descripción** | Como administrador u operador, quiero generar y descargar un reporte en el formato que necesito, para analizar la información fuera de la plataforma o compartirla. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-REP-01 (Reportería — Tablero) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* Existe actividad en el período seleccionado.

**Reglas de negocio**

* RN-01: El reporte puede generarse en los formatos disponibles (por ejemplo PDF o CSV) según el tipo de reporte.
* RN-02: La generación registra el tipo, formato, filtros y período, conforme a la entidad Reporte.
* RN-03: El archivo generado queda disponible para descarga y referencia posterior.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Solicito generar un reporte en un formato | El sistema lo genera y lo deja disponible para descarga | PAN-REP-01 |
| Intento generar un reporte de un período sin actividad | El sistema muestra “No hay datos para generar el reporte en el período seleccionado.” | PAN-REP-01 |
| Descargo el reporte | Obtengo el archivo en el formato seleccionado con los datos del período | PAN-REP-01 |
| Consulto reportes generados antes | Veo el historial con su tipo, formato y período | PAN-REP-01 |

## **HU-E10-04 — Generar el paquete contable mensual**

| ID | HU-E10-04 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | GenerarPaqueteContable |
| **Descripción** | Como administrador, quiero configurar la generación del paquete contable mensual, para que mi contador reciba toda la documentación fiscal sin que yo lo haga manualmente cada mes. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-REP-02 (Reportería — Configuración automática) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.

**Reglas de negocio**

* RN-01: El paquete se genera automáticamente con los datos del mes cerrado, conforme a la entidad PaqueteContable.
* RN-02: El día de envío es configurable; el formato puede ser PDF, XML o ambos.
* RN-03: El contenido del paquete es configurable: facturas, notas de crédito, reporte de cobros, log de operaciones y resumen ejecutivo.
* RN-04: La configuración del envío automático está restringida al rol Administrador.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la configuración automática | Veo el estado del envío, día, formato y contenido del paquete | PAN-REP-02 |
| Activo el envío automático | El sistema muestra la fecha y hora del próximo envío programado | PAN-REP-02 |
| Activo el envío sin haber configurado el email del contador | El sistema muestra “Debe indicar el email del contador para activar el envío automático.” | PAN-REP-02 |
| Genero un paquete de prueba | El sistema lo genera con los datos actuales y lo deja disponible para descarga inmediata | PAN-REP-02 |

## **HU-E10-05 — Compartir el paquete contable con el contador mediante enlace**

| ID | HU-E10-05 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | GenerarPaqueteContable |
| **Descripción** | Como administrador, quiero compartir el paquete contable con mi contador mediante un enlace de acceso limitado, para que pueda descargarlo sin tener una cuenta en el sistema. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-REP-02 (Reportería — Configuración automática) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.

**Reglas de negocio**

* RN-01: El contador accede mediante un enlace de acceso limitado enviado por email, sin necesidad de cuenta, conforme a la entidad TokenDeAccesoContable.
* RN-02: El acceso del contador es fijo: ver y descargar reportes y paquetes; no accede a facturación, cobros, configuración ni datos de clientes.
* RN-03: El administrador puede revocar el acceso en cualquier momento, invalidando el enlace de inmediato.
* RN-04: Solo puede haber un contador externo activo por empresa a la vez.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Invito al contador con su email | El sistema envía el enlace de acceso limitado y lo muestra como “Invitado con acceso limitado” | PAN-REP-02 |
| Ingreso un email con formato inválido | El sistema muestra “Ingrese un email válido.” y no envía la invitación | PAN-REP-02 |
| Reviso los permisos del contador | Veo qué puede ver y descargar y qué tiene restringido | PAN-REP-02 |
| Revoco el acceso del contador | El enlace queda invalidado de inmediato | PAN-REP-02 |

## **HU-E10-06 — Acceder al paquete contable como contador externo**

| ID | HU-E10-06 |
| :---- | :---- |
| **Actor** | Contador externo |
| **Acción Bloque K** | GenerarPaqueteContable |
| **Descripción** | Como contador externo, quiero acceder al paquete contable mediante un enlace seguro, para descargar la documentación fiscal de mi cliente sin necesidad de una cuenta. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | Enlace seguro |

**Precondiciones**

* El administrador compartió el acceso (HU-E10-05).
* El enlace de acceso está vigente.

**Reglas de negocio**

* RN-01: El acceso mediante enlace permite ver reportes mensuales, ver gráficos del período y descargar paquetes contables.
* RN-02: El acceso no habilita edición ni visualización de datos de clientes, facturación o cobros.
* RN-03: El sistema registra los accesos del contador, conforme a los atributos accesos y revocado de la entidad TokenDeAccesoContable.
* RN-04: Si el administrador revoca el acceso, el enlace deja de funcionar de inmediato.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Accedo mediante el enlace seguro | Puedo ver los reportes mensuales y descargar los paquetes contables | Enlace seguro |
| Intento acceder a otros módulos | El sistema no me permite ver facturación, cobros ni datos de clientes | Enlace seguro |
| El administrador revocó mi acceso | El enlace deja de funcionar y muestra “El acceso a este paquete ya no está disponible.” | Enlace seguro |

# **Épica 11 — Configuración del Negocio**

**Bounded Contexts asociados:** BC3 Configuración de Negocio / BC10 Observabilidad y Auditoría
**Acciones de dominio (Bloque K):** (métodos sobre ReglaDeNegocio, PlantillaDeNotificación, Notificación)
Esta épica agrupa las historias de parametrización del comportamiento del sistema: la definición de reglas de negocio configurables, la administración de plantillas de notificación y la consulta del centro de notificaciones del panel. Los mensajes de validación entre comillas son textos del sistema.

## **HU-E11-01 — Definir reglas de negocio parametrizables**

| ID | HU-E11-01 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre ReglaDeNegocio) |
| **Descripción** | Como administrador, quiero definir reglas de negocio parametrizables, para ajustar el comportamiento del sistema (escalamiento de cobros, políticas de turno) a las necesidades de mi empresa. |
| **Prioridad** | Media |
| **Complejidad** | Alta |
| **Pantalla** | PAN-CFG-RN (Configuración — Reglas de negocio) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.

**Reglas de negocio**

* RN-01: Cada regla tiene un tipo, una configuración parametrizable, una prioridad y un estado activo/inactivo, conforme a la entidad ReglaDeNegocio.
* RN-02: La regla de escalamiento de cobros define cada cuántos días y por qué canal se envían los recordatorios; esta parametrización alimenta el despacho automático de recordatorios.
* RN-03: La política de turnos define el comportamiento ante señas, cancelaciones y no-shows.
* RN-04: Una regla desactivada deja de aplicarse de forma inmediata sin afectar las operaciones ya procesadas bajo ella.
* RN-05: Cuando existe más de una regla aplicable, se resuelve por su prioridad.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la configuración de reglas de negocio | Veo las reglas existentes con su tipo, prioridad y estado | PAN-CFG-RN |
| Defino la regla de escalamiento de cobros | El despacho de recordatorios pasa a regirse por la nueva parametrización | PAN-CFG-RN |
| Configuro una regla con parámetros inválidos (por ejemplo días en cero) | El sistema muestra “Los días de escalamiento deben ser mayores a cero.” y no guarda la regla | PAN-CFG-RN |
| Desactivo una regla | Deja de aplicarse de inmediato sin afectar lo ya procesado | PAN-CFG-RN |
| Existen dos reglas aplicables | El sistema resuelve según la prioridad configurada | PAN-CFG-RN |

## **HU-E11-02 — Administrar las plantillas de notificación**

| ID | HU-E11-02 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre PlantillaDeNotificación) |
| **Descripción** | Como administrador, quiero administrar las plantillas de notificación, para personalizar los mensajes que el sistema envía a clientes y usuarios. |
| **Prioridad** | Baja |
| **Complejidad** | Media |
| **Pantalla** | PAN-CFG-NOT (Configuración — Plantillas) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.

**Reglas de negocio**

* RN-01: Cada plantilla tiene un código identificador, un canal, un idioma y un cuerpo, conforme a la entidad PlantillaDeNotificación.
* RN-02: El cuerpo de la plantilla admite variables que el sistema reemplaza al enviar (por ejemplo nombre del cliente, fecha del turno).
* RN-03: Las plantillas que se envían por WhatsApp pueden requerir aprobación previa de Meta, reflejada en su estado de aprobación.
* RN-04: Una plantilla no aprobada no puede utilizarse para envíos por el canal que requiere aprobación.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la administración de plantillas | Veo las plantillas con su código, canal, idioma y estado | PAN-CFG-NOT |
| Edito el cuerpo de una plantilla con variables | El sistema guarda la plantilla y reemplaza las variables al enviar | PAN-CFG-NOT |
| Uso una variable no reconocida en el cuerpo | El sistema muestra “La variable indicada no es válida para esta plantilla.” y no guarda | PAN-CFG-NOT |
| Una plantilla de WhatsApp no está aprobada | El sistema no permite usarla para ese canal hasta su aprobación | PAN-CFG-NOT |

## **HU-E11-03 — Consultar el centro de notificaciones del panel**

| ID | HU-E11-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador / Solo Lectura |
| **Acción Bloque K** | (consulta sobre Notificación) |
| **Descripción** | Como usuario del panel, quiero consultar el centro de notificaciones, para enterarme de los eventos relevantes del sistema que requieren mi atención. |
| **Prioridad** | Baja |
| **Complejidad** | Baja |
| **Pantalla** | PAN-CFG-NOT (Configuración — Notificaciones) |

**Precondiciones**

* El usuario tiene sesión iniciada con cualquier rol.

**Reglas de negocio**

* RN-01: El centro de notificaciones lista los avisos dirigidos al usuario con su categoría, severidad y estado de lectura, conforme a la entidad Notificación.
* RN-02: Las notificaciones que recibe cada usuario dependen de sus preferencias de suscripción (HU-E1-07).
* RN-03: El usuario puede marcar notificaciones como leídas.
* RN-04: Las notificaciones de severidad alta se destacan visualmente.
* RN-05: El rol Solo Lectura accede a esta consulta sin posibilidad de ejecutar acciones de gestión sobre los datos visualizados.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro el centro de notificaciones | Veo los avisos dirigidos a mí con su categoría, severidad y estado | PAN-CFG-NOT |
| Marco una notificación como leída | Su estado cambia y deja de destacarse como pendiente | PAN-CFG-NOT |
| Recibo una notificación de severidad alta | El sistema la destaca visualmente | PAN-CFG-NOT |
| Ingreso como Solo Lectura | Consulto las notificaciones sin acciones de gestión | PAN-CFG-NOT |

# **Épica 12 — Auditoría y Observabilidad (panel)**

**Bounded Contexts asociados:** BC10 Observabilidad y Auditoría
**Acciones de dominio (Bloque K):** (consulta sobre RegistroDeAuditoría)
Esta épica agrupa las historias de consulta de la bitácora de operaciones: el registro completo de todo lo que el sistema ejecuta en nombre del usuario, que constituye la fuente de verdad sobre qué hizo el sistema, cuándo y con qué resultado. El acceso a la bitácora se restringe a los roles Administrador y Operador: dado que el rol Solo Lectura puede corresponder a un actor externo o de alcance amplio, y que la bitácora expone el registro crudo de toda la operación (incluyendo datos de clientes y mensajes de terceros), no se habilita a Solo Lectura. El detalle fiscal que pudiera requerir un contador se obtiene por los reportes y el paquete contable (Épica 10), no por la bitácora.

## **HU-E12-01 — Ver la bitácora de operaciones**

| ID | HU-E12-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta sobre RegistroDeAuditoría) |
| **Descripción** | Como administrador u operador, quiero ver la bitácora completa de operaciones con filtros, para auditar todo lo que el sistema ejecutó en nombre de mi empresa. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-LOG-01 (Log de Operaciones — Listado) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* Existe al menos una operación registrada.

**Reglas de negocio**

* RN-01: La bitácora registra cada operación con su timestamp, módulo, operación, entidad afectada, iniciador y estado, conforme a la entidad RegistroDeAuditoría.
* RN-02: El iniciador distingue si la operación fue ejecutada por la IA, por un usuario o por el sistema.
* RN-03: Los filtros disponibles son por rango de fechas, módulo, estado e iniciador, y búsqueda por operación, cliente o archivo.
* RN-04: La bitácora es de solo consulta; sus registros no pueden editarse ni eliminarse.
* RN-05: El acceso se restringe a Administrador y Operador; el rol Solo Lectura no accede a la bitácora.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al Log de Operaciones | Veo el listado con timestamp, módulo, operación, entidad afectada, iniciador y estado | PAN-LOG-01 |
| Filtro por módulo y estado | El listado muestra solo las operaciones que coinciden | PAN-LOG-01 |
| Filtro por iniciador IA | Veo solo las operaciones ejecutadas automáticamente por el agente | PAN-LOG-01 |
| Busco por cliente o archivo | El listado filtra las operaciones relacionadas | PAN-LOG-01 |
| No hay operaciones que coincidan con los filtros | El sistema muestra “No hay operaciones para los filtros seleccionados.” | PAN-LOG-01 |

## **HU-E12-02 — Ver el detalle de una operación individual**

| ID | HU-E12-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta sobre RegistroDeAuditoría) |
| **Descripción** | Como administrador u operador, quiero ver el detalle de una operación individual, para conocer los datos de entrada, la respuesta del servicio externo y el resultado final. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-LOG-02 (Log de Operaciones — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.
* La operación existe en la bitácora.

**Reglas de negocio**

* RN-01: El detalle muestra el resumen de la operación, los datos de entrada que la dispararon, los datos de salida del servicio externo y el timeline de ejecución con sus pasos internos.
* RN-02: Para operaciones fiscales, el detalle incluye los datos del comprobante y el resultado de ARCA (CAE, estado).
* RN-03: El detalle indica la duración de la operación y el estado final (completado, error o pendiente).
* RN-04: El acceso se restringe a Administrador y Operador; el rol Solo Lectura no accede al detalle de la bitácora.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro una operación de la bitácora | Veo su resumen, datos de entrada, datos de salida y timeline de ejecución | PAN-LOG-02 |
| Abro una operación de facturación | Veo los datos del comprobante y el resultado de ARCA (CAE, estado) | PAN-LOG-02 |
| Abro una operación con error | Veo el motivo del error y el punto del timeline donde ocurrió | PAN-LOG-02 |

# **Historias de Sistema y Técnicas**

**Bounded Contexts asociados:** Transversal (BC asociados según cada proceso)
**Acciones de dominio (Bloque K):** ConfirmarPago, ProcesarMensajeEntrante, EnviarRecordatorio, SincronizarParámetrosFiscales
Las siguientes funcionalidades son procesos automáticos disparados por planificadores o por webhooks de sistemas externos. No responden a la acción directa de un usuario, por lo que se documentan como historias de sistema: en lugar de una pantalla, cada una consigna su disparador. Su correcta especificación es esencial porque sustentan las automatizaciones que constituyen la propuesta de valor del producto. La referencia Bitácora indica que el resultado del proceso queda registrado en el registro de auditoría.

## **HS-T1 — Confirmar un pago a partir del webhook de MercadoPago**

| ID | HS-T1 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | ConfirmarPago |
| **Descripción** | El sistema recibe la notificación de pago de MercadoPago y actualiza el estado del cobro correspondiente de forma automática. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Disparador** | Webhook de MercadoPago |

**Precondiciones**

* Existe un cobro con link de pago activo.
* La integración de MercadoPago está operativa.

**Reglas de negocio**

* RN-01: El proceso valida la autenticidad del webhook antes de procesarlo.
* RN-02: Al confirmarse el pago, el cobro pasa a estado APROBADO (etiqueta de interfaz “Pagado”) y se detiene la cadena de recordatorios.
* RN-03: Si el cobro está asociado a un comprobante, se reduce su saldo pendiente; si está asociado a un turno como seña, se actualiza el estado del turno.
* RN-04: El procesamiento es idempotente: una notificación repetida del mismo pago no genera efectos duplicados.
* RN-05: El evento queda registrado en la bitácora con iniciador Sistema.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Llega un webhook de pago válido | El sistema actualiza el cobro a APROBADO y detiene los recordatorios | Bitácora |
| El cobro estaba asociado a un comprobante | El sistema reduce el saldo pendiente del comprobante en el monto cobrado | Bitácora |
| Llega una notificación repetida del mismo pago | El sistema no genera efectos duplicados (procesamiento idempotente) | Bitácora |
| El webhook no supera la validación de autenticidad | El sistema lo descarta sin alterar el cobro y registra el intento | Bitácora |

## **HS-T2 — Procesar un mensaje entrante recibido desde WhatsApp**

| ID | HS-T2 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | ProcesarMensajeEntrante |
| **Descripción** | El sistema recibe un mensaje entrante de WhatsApp, interpreta su intención y lo encamina al flujo correspondiente o al agente. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Disparador** | Webhook de WhatsApp |

**Precondiciones**

* La integración de WhatsApp está operativa.
* El agente está activo o existe un operador disponible.

**Reglas de negocio**

* RN-01: El proceso registra el mensaje entrante con su contenido, tipo y conversación asociada, conforme a la entidad Mensaje.
* RN-02: El sistema interpreta la intención del mensaje y la clasifica (turno, consulta, pago, FAQ).
* RN-03: Si la confianza de interpretación es insuficiente, se inicia un escalamiento a un asesor humano.
* RN-04: Si el mensaje llega fuera del horario de atención configurado, el sistema responde según la política definida.
* RN-05: El evento queda registrado en la bitácora con iniciador IA.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Llega un mensaje entrante | El sistema lo registra e interpreta su intención | Bitácora |
| La intención se interpreta con confianza suficiente | El sistema encamina el mensaje al flujo correspondiente (turno, consulta, pago o FAQ) | Bitácora |
| La intención no se interpreta con confianza suficiente | El sistema inicia un escalamiento a un asesor | Bitácora |
| El mensaje llega fuera del horario de atención | El sistema responde según la política configurada para fuera de horario | Bitácora |

## **HS-T3 — Despachar recordatorios de cobro según la regla de escalamiento**

| ID | HS-T3 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | EnviarRecordatorio |
| **Descripción** | El sistema despacha automáticamente los recordatorios de cobro pendientes según la regla de escalamiento configurada. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Disparador** | Planificador (Celery Beat) |

**Precondiciones**

* Existen cobros pendientes o vencidos.
* Existe una regla de escalamiento de cobros activa (HU-E11-01).

**Reglas de negocio**

* RN-01: El proceso evalúa los cobros pendientes y determina cuáles corresponden a recordatorio según la regla de escalamiento vigente, conforme a la entidad Recordatorio.
* RN-02: Cada recordatorio se despacha por el canal configurado y registra su paso en la secuencia de escalamiento.
* RN-03: Un cobro en estado APROBADO o CANCELADO deja de recibir recordatorios.
* RN-04: El estado de entrega de cada recordatorio se registra para seguimiento.
* RN-05: El proceso es idempotente respecto de la ventana de ejecución: no envía el mismo paso de recordatorio dos veces.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Un cobro alcanza el umbral de un paso de recordatorio | El sistema despacha el recordatorio por el canal configurado | Bitácora |
| Un cobro fue pagado (APROBADO) | El sistema deja de enviarle recordatorios | Bitácora |
| Se ejecuta el planificador dos veces en la misma ventana | El sistema no duplica el mismo paso de recordatorio | Bitácora |

## **HS-T4 — Sincronizar los parámetros fiscales desde ARCA con su vigencia**

| ID | HS-T4 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | SincronizarParámetrosFiscales |
| **Descripción** | El sistema sincroniza periódicamente los parámetros fiscales desde ARCA, manteniendo su vigencia temporal. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Disparador** | Planificador |

**Precondiciones**

* La integración de ARCA está operativa.

**Reglas de negocio**

* RN-01: El proceso obtiene los parámetros fiscales vigentes desde ARCA y los almacena con su rango de vigencia, conforme a la entidad ParámetroFiscal.
* RN-02: Un parámetro nuevo no reemplaza al anterior, sino que se registra con su propia vigencia, preservando el histórico.
* RN-03: La facturación utiliza el parámetro vigente a la fecha de emisión del comprobante.
* RN-04: Si la sincronización falla, se conserva el último parámetro vigente y se registra el error.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Se ejecuta la sincronización | El sistema obtiene los parámetros vigentes de ARCA y los almacena con su vigencia | Bitácora |
| Cambia un parámetro fiscal | El sistema lo registra preservando el histórico del anterior | Bitácora |
| La sincronización falla | El sistema conserva el último parámetro vigente y registra el error | Bitácora |

## **HS-T5 — Registrar automáticamente las operaciones en la auditoría**

| ID | HS-T5 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | (evento de dominio — Observabilidad) |
| **Descripción** | El sistema registra automáticamente en la bitácora cada operación relevante ejecutada, garantizando la trazabilidad completa. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Disparador** | Evento de dominio |

**Precondiciones**

* Se produce una operación relevante en cualquier contexto del sistema.

**Reglas de negocio**

* RN-01: Cada operación relevante emite un evento que el contexto de Observabilidad persiste como registro de auditoría, conforme a la entidad RegistroDeAuditoría.
* RN-02: El registro captura módulo, operación, entidad afectada, iniciador, resultado y timestamp.
* RN-03: Los registros de auditoría son inmutables: no pueden editarse ni eliminarse.
* RN-04: El registro es independiente del resultado de la operación: se registran tanto las exitosas como las fallidas.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Se ejecuta una operación exitosa | El sistema la registra en la bitácora con resultado completado | Bitácora |
| Una operación falla | El sistema la registra igualmente con resultado error | Bitácora |
| Se intenta alterar un registro de auditoría | El sistema no lo permite por ser inmutable | Bitácora |

## **HS-T6 — Derivar a la cola de fallos (DLQ) las tareas asíncronas agotadas**

| ID | HS-T6 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | (gestión de TareaAsíncrona) |
| **Descripción** | El sistema deriva a una cola de fallos las tareas asíncronas que agotaron sus reintentos, para su revisión sin bloquear el procesamiento. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Disparador** | Planificador |

**Precondiciones**

* Existe una tarea asíncrona que falló reiteradamente.

**Reglas de negocio**

* RN-01: Una tarea asíncrona reintenta su ejecución hasta el máximo configurado, conforme al atributo intentos de la entidad TareaAsíncrona.
* RN-02: Al agotar los reintentos, la tarea se deriva a la cola de fallos (DLQ) con su resultado y se marca su estado en consecuencia.
* RN-03: Una tarea en la DLQ no bloquea el procesamiento de las demás tareas.
* RN-04: El evento queda registrado para permitir su análisis y eventual reprocesamiento manual.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Una tarea falla menos veces que el máximo configurado | El sistema la reintenta | Bitácora |
| Una tarea agota sus reintentos | El sistema la deriva a la cola de fallos y la marca como tal | Bitácora |
| Una tarea está en la DLQ | El procesamiento de las demás tareas continúa sin bloqueo | Bitácora |

## **HS-T7 — Transcribir las notas de voz entrantes de WhatsApp**

| ID | HS-T7 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | ProcesarMensajeEntrante |
| **Descripción** | El sistema transcribe automáticamente las notas de voz entrantes de WhatsApp para interpretarlas como mensajes de texto. |
| **Prioridad** | Baja |
| **Complejidad** | Media |
| **Disparador** | Webhook de WhatsApp |

**Precondiciones**

* Llega un mensaje entrante de tipo nota de voz.
* La integración de WhatsApp está operativa.

**Reglas de negocio**

* RN-01: El proceso detecta el tipo de contenido del mensaje entrante, conforme al atributo tipo_contenido de la entidad Mensaje.
* RN-02: Las notas de voz se transcriben a texto antes de la interpretación de intención.
* RN-03: Una vez transcripta, se persiste únicamente el texto resultante asociado al mensaje; el audio original no se conserva, conforme a la decisión de minimización de datos personales del sistema.
* RN-04: Si la transcripción no alcanza calidad suficiente, el sistema deriva la conversación a un asesor humano.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Llega una nota de voz | El sistema la transcribe a texto antes de interpretarla y no conserva el audio original | Bitácora |
| La transcripción es de buena calidad | El sistema interpreta la intención igual que con un mensaje de texto | Bitácora |
| La transcripción no alcanza calidad suficiente | El sistema deriva la conversación a un asesor humano | Bitácora |
