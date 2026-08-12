# **Épica 1 — Onboarding y Gestión de la Organización**

**Bounded Contexts asociados:** BC1 Identidad y Organización  
**Acciones de dominio (Bloque K):** RegistrarEmpresa, RegistrarUsuario, CambiarRolDeUsuario, ActualizarPreferencias  
Esta épica agrupa las historias relativas al alta de la empresa en la plataforma, la aceptación del marco contractual, y la gestión de los usuarios que operan el sistema con sus respectivos roles y preferencias personales.

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
* RN-04: Al completar el registro exitosamente, el sistema redirige automáticamente al paso 2 del onboarding. El usuario no puede acceder al dashboard hasta completar los pasos 1 y 2\.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Completo el formulario con email y contraseña válidos y hago clic en “Ingresar” | El sistema crea la cuenta y me redirige al paso 2 del onboarding | PAN-ONB-02 |
| Hago clic en “Continuar con Google” y autorizo el acceso | El sistema crea la cuenta con los datos de Google y me redirige al paso 2 | PAN-ONB-02 |
| Ingreso un email ya registrado | El sistema muestra que ese email ya tiene una cuenta y ofrece iniciar sesión | PAN-ONB-01 |
| Ingreso una contraseña menor a 8 caracteres | El sistema indica que la contraseña debe tener al menos 8 caracteres y bloquea el registro | PAN-ONB-01 |
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
| Ingreso un CUIT inválido o inexistente en ARCA | El sistema indica que el CUIT no fue encontrado en ARCA y bloquea el avance | PAN-ONB-02 |
| Intento avanzar sin completar todos los campos obligatorios | El sistema marca los campos faltantes y bloquea el botón Continuar | PAN-ONB-02 |
| Completo todos los campos y hago clic en Continuar | El sistema guarda los datos y me redirige al paso 3 de integraciones | PAN-ONB-03 |

## **HU-E1-03 — Aceptar los términos y condiciones del servicio**

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

* RN-01: El sistema registra la versión de los términos aceptada y la fecha y hora de aceptación, conforme a los atributos terminos\_version y terminos\_fecha\_aceptacion de la entidad Empresa.  
* RN-02: La aceptación es obligatoria para completar el registro. No es posible avanzar sin aceptar.  
* RN-03: Si la versión de los términos se actualiza con posterioridad, el sistema solicita una nueva aceptación al usuario en su siguiente ingreso, registrando la nueva versión y fecha.  
* RN-04: El texto vigente de los términos es accesible para consulta en todo momento desde el pie del formulario de registro.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Visualizo el formulario de registro | Veo la casilla de aceptación de términos con un enlace al texto vigente | PAN-ONB-01 |
| Intento completar el registro sin aceptar los términos | El sistema bloquea el avance e indica que la aceptación es obligatoria | PAN-ONB-01 |
| Acepto los términos y completo el registro | El sistema registra la versión aceptada y la fecha y hora de aceptación | PAN-ONB-01 |
| Ingreso luego de que los términos fueron actualizados | El sistema me solicita aceptar la nueva versión antes de continuar | PAN-ONB-01 |

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
| Invito a un nuevo usuario con email y rol | El sistema envía el email de invitación y muestra el usuario como Invitación pendiente | PAN-USR-01 |
| Invito a un email que ya pertenece a la empresa | El sistema indica que ese email ya está registrado y bloquea la invitación | PAN-USR-01 |
| El usuario invitado acepta y crea su contraseña | Su estado cambia a Activo y puede acceder según su rol | PAN-USR-01 |

## **HU-E1-05 — Asignar o cambiar el rol de un usuario**

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
* RN-04: El cambio de rol queda registrado en el Log de Operaciones con usuario afectado, rol anterior, rol nuevo, ejecutor y timestamp.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Cambio el rol de un usuario activo | El cambio aplica inmediatamente y queda registrado en el log | PAN-USR-01 |
| Intento quitar el rol de Administrador al único Administrador activo | El sistema indica que debe existir al menos un Administrador activo y bloquea la acción | PAN-USR-01 |
| Ingreso como Operador a la sección de Usuarios | No tengo disponible la acción de cambiar roles | PAN-USR-01 |

## **HU-E1-06 — Desactivar el acceso de un usuario**

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
* RN-02: Las acciones históricas del usuario desactivado se conservan en el Log de Operaciones.  
* RN-03: No se puede desactivar al único usuario con rol Administrador activo.  
* RN-04: Un usuario desactivado puede ser reactivado posteriormente por un Administrador, conservando su rol previo.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Desactivo un usuario activo | Pierde acceso inmediatamente y su estado cambia a Inactivo | PAN-USR-01 |
| Intento desactivar al único Administrador activo | El sistema indica que debe existir al menos un Administrador activo y bloquea la acción | PAN-USR-01 |
| Reactivo un usuario inactivo | Recupera el acceso con el rol que tenía antes de la desactivación | PAN-USR-01 |
| Consulto el log tras desactivar un usuario | Las acciones históricas de ese usuario siguen visibles | PAN-LOG-01 |

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

* RN-01: Las preferencias son individuales de cada usuario y no afectan a los demás usuarios de la empresa, conforme a los atributos pref\_idioma, pref\_zona\_horaria y pref\_suscripciones de la entidad Usuario.  
* RN-02: La preferencia de suscripciones determina qué notificaciones del sistema recibe el usuario y por qué canal.  
* RN-03: Los cambios de preferencias aplican de forma inmediata tras guardar.  
* RN-04: La zona horaria del usuario afecta únicamente la visualización de fechas y horas en su sesión; no altera los datos almacenados.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a mis preferencias personales | Veo mis preferencias actuales de idioma, zona horaria y suscripciones | PAN-USR-02 |
| Cambio mi idioma y guardo | La interfaz se actualiza al nuevo idioma de forma inmediata | PAN-USR-02 |
| Modifico mis suscripciones a notificaciones | Dejo de recibir las notificaciones que desactivé a partir de ese momento | PAN-USR-02 |
| Cambio mi zona horaria | Las fechas y horas se muestran en mi nuevo huso sin alterar los datos de otros usuarios | PAN-USR-02 |

# **Épica 2 — Integración con Sistemas Externos**

**Bounded Contexts asociados:** BC4 Integración con Sistemas Externos  
**Acciones de dominio (Bloque K):** ConfigurarIntegración  
Esta épica agrupa las historias relativas a la conexión y validación de los servicios externos con los que opera CheatSheet: ARCA para facturación electrónica, MercadoPago para cobros, WhatsApp Business para el canal conversacional, y Google Sheets o Excel Online para la sincronización de planillas.

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

* RN-01: La conexión con ARCA requiere las credenciales fiscales (certificado y clave) asociadas al CUIT de la empresa. El sistema las almacena cifradas, conforme al atributo credencial\_contenido\_cifrado de la entidad ConfiguraciónDeIntegración.  
* RN-02: El sistema valida las credenciales contra ARCA antes de marcar la integración como activa. Credenciales inválidas dejan la integración en estado no conectado.  
* RN-03: La integración registra el ambiente (homologación o producción) en el que opera.  
* RN-04: Si las credenciales expiran o son revocadas, el sistema marca la integración como inactiva y notifica al administrador.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso credenciales fiscales válidas | El sistema las valida contra ARCA y marca la integración como Conectada | PAN-CFG-INT |
| Ingreso credenciales inválidas | El sistema indica el error de validación y mantiene la integración como no conectada | PAN-CFG-INT |
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
| Autorizo el acceso | El sistema valida la cuenta y marca la integración como Conectada | PAN-CFG-INT |
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
* RN-04: La integración de WhatsApp es prerequisito para el canal conversacional (Épica 8\) y el escalamiento (Épica 9).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Inicio la conexión de un número de WhatsApp Business | El sistema inicia el proceso de verificación con Meta y muestra estado pendiente | PAN-CFG-INT |
| La verificación con Meta se completa | El sistema marca la integración como Conectada con el display name verificado | PAN-CFG-INT |
| La verificación falla | El sistema notifica el motivo y mantiene la integración como no conectada | PAN-CFG-INT |

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
| Confirmo el vínculo | El sistema guarda la configuración y realiza la primera sincronización | PAN-ING-01 |
| La estructura de la planilla cambia | El sistema pausa la sincronización automática y me notifica | PAN-ING-01 |

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
| Una integración está degradada | El sistema la muestra en estado Atención con el detalle disponible | PAN-CFG-INT |
| Una integración perdió la conexión | El sistema la muestra como No conectada e indica la acción para reconectarla | PAN-CFG-INT |

# **Épica 3 — Sincronización de Planillas**

**Bounded Contexts asociados:** BC5 Sincronización de Planillas \[CORE\]  
**Acciones de dominio (Bloque K):** MapearPlanilla, ProcesarPlanilla, SincronizarDesdePlanilla, EscribirEnPlanilla  
Esta épica agrupa las historias del núcleo diferenciador de CheatSheet: la interpretación inteligente de planillas del usuario y su sincronización con el resto de la plataforma. Constituye el habilitador que conecta las herramientas existentes de la PyME con las automatizaciones del sistema.

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
| Subo un archivo con columnas en cualquier orden o nombre | El sistema propone un mapeo automático con nivel de confianza por columna | PAN-ING-02 |
| Una columna tiene confianza Baja | La columna queda marcada como Sin asignar | PAN-ING-02 |
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
| Intento confirmar con columnas obligatorias sin asignar | El botón Confirmar y procesar permanece deshabilitado | PAN-ING-02 |
| Confirmo un mapeo completo | El sistema activa el mapeo y habilita el procesamiento | PAN-ING-02 |

## **HU-E3-03 — Procesar la carga inicial de la planilla**

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
* RN-02: Las filas con CUIT inválido se marcan como error pero no abortan el procesamiento del resto.  
* RN-03: El procesamiento registra filas totales, filas procesadas correctamente y filas con error, conforme a la entidad ProcesamientoDePlanilla.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Confirmo el procesamiento | El sistema inicia el procesamiento asíncrono y muestra el archivo con estado Procesando | PAN-ING-01 |
| El procesamiento finaliza sin errores | El estado cambia a Procesado con el total de filas procesadas | PAN-ING-01 |
| El archivo tiene filas con datos inválidos | El estado muestra Con errores indicando filas válidas y fallidas | PAN-ING-01 |

## **HU-E3-04 — Sincronizar los cambios incrementales de la planilla**

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

* RN-01: La sincronización incremental procesa únicamente las filas nuevas o modificadas desde la última lectura, conforme a los atributos ultima\_lectura y ultima\_escritura de VínculoDePlanilla.  
* RN-02: Si una sincronización falla, el evento se registra en el Log de Operaciones con estado Error y se notifica al administrador.  
* RN-03: La sincronización reutiliza el mapeo vigente sin solicitar nueva confirmación salvo cambio de estructura.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Se modifica una fila en la planilla vinculada | El sistema detecta el cambio y lo sincroniza en la siguiente corrida | PAN-ING-01 |
| Se agregan filas nuevas | El sistema procesa solo las filas nuevas sin reprocesar las existentes | PAN-ING-01 |
| Una sincronización falla | El sistema registra el error en el log y me notifica | PAN-LOG-01 |

## **HU-E3-05 — Consultar el resultado y los errores de un procesamiento**

| ID | HU-E3-05 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | ProcesarPlanilla |
| **Descripción** | Como administrador u operador, quiero consultar el resultado detallado de un procesamiento de planilla, para identificar qué filas fallaron y por qué. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-ING-03 (Ingesta de Datos — Detalle de procesamiento) |

**Precondiciones**

* Existe al menos un procesamiento de planilla registrado.

**Reglas de negocio**

* RN-01: El detalle muestra filas totales, procesadas y con error, junto con el motivo de cada error de fila, conforme a la entidad ErrorDeFila.  
* RN-02: Cada error de fila indica el número de fila del archivo original y la descripción del problema.  
* RN-03: El detalle permite descargar el listado de errores para su corrección externa.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro el detalle de un procesamiento | Veo el resumen de filas totales, procesadas y con error | PAN-ING-03 |
| Reviso los errores | Veo cada fila fallida con su número original y el motivo | PAN-ING-03 |
| Descargo el listado de errores | El sistema genera un archivo con las filas fallidas y sus motivos | PAN-ING-03 |

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

# **Épica 4 — Gestión de Datos Maestros**

**Bounded Contexts asociados:** BC2 Datos Maestros  
**Acciones de dominio (Bloque K):** GestionarCategoría (y operaciones sobre Cliente y Servicio)  
Esta épica agrupa las historias relativas a la administración del catálogo de clientes, servicios y categorías de la empresa. Estos datos maestros dan soporte transversal a la facturación, la agenda y los cobros.

## **HU-E4-01 — Consultar y gestionar el catálogo de clientes**

| ID | HU-E4-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta \+ métodos sobre Cliente) |
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

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo de Clientes | Veo el listado con nombre, CUIT, origen, WhatsApp y estado | PAN-DM-01 |
| Creo un cliente con CUIT válido | El sistema valida contra ARCA, completa razón social y condición IVA y guarda con origen PANEL | PAN-DM-01 |
| Intento crear un cliente con CUIT ya existente | El sistema indica el duplicado y ofrece verlo | PAN-DM-01 |
| Edito un cliente existente | Los cambios quedan disponibles para los demás módulos | PAN-DM-01 |

## **HU-E4-02 — Consultar y gestionar el catálogo de servicios**

| ID | HU-E4-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta \+ métodos sobre Servicio) |
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

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo de Servicios | Veo el listado con nombre, precio, IVA, duración y estado | PAN-DM-02 |
| Creo un servicio agendable sin duración | El sistema indica que la duración es obligatoria y bloquea el guardado | PAN-DM-02 |
| Creo un servicio con datos válidos | Queda disponible para el agente y para nuevos comprobantes | PAN-DM-02 |
| Edito el precio de un servicio | El nuevo precio aplica a operaciones futuras; los comprobantes emitidos mantienen su precio original | PAN-DM-02 |

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
| Intento crear una categoría con nombre duplicado en el mismo ámbito | El sistema lo impide e informa el conflicto | PAN-DM-03 |
| Edito el nombre de una categoría | El cambio se refleja en todos los elementos clasificados con ella | PAN-DM-03 |
| Elimino una categoría en uso | El sistema solicita confirmación y al confirmar los elementos quedan sin esa clasificación | PAN-DM-03 |

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

# **Épica 5 — Facturación**

**Bounded Contexts asociados:** BC6 Facturación \[CORE\]  
**Acciones de dominio (Bloque K):** EmitirComprobante, AnularComprobante  
Esta épica agrupa las historias del núcleo de facturación electrónica: la emisión de comprobantes fiscales con obtención de CAE ante ARCA, su anulación mediante notas de crédito, la consulta del historial y la administración de los puntos de venta.

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
| Aplico filtro por rango de fechas | El listado muestra solo los comprobantes del período | PAN-FAC-01 |
| Aplico filtro por estado Error | Veo solo los comprobantes que fallaron en la autorización | PAN-FAC-01 |
| No hay comprobantes para los filtros | El sistema muestra un estado vacío con mensaje acorde | PAN-FAC-01 |

## **HU-E5-02 — Consultar el estado y detalle de un comprobante**

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
* RN-03: El PDF descargable es el comprobante oficial generado al momento de la autorización.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro un comprobante del listado | Veo el detalle completo con datos fiscales, CAE y vencimiento | PAN-FAC-02 |
| El comprobante está Autorizado | El botón Descargar PDF está disponible | PAN-FAC-02 |
| El comprobante está en Error | Veo el motivo devuelto por ARCA y no hay opción de descarga | PAN-FAC-02 |

## **HU-E5-03 — Emitir un comprobante fiscal y obtener su CAE**

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
* El cliente receptor existe en Datos Maestros o se crea en el momento.

**Reglas de negocio**

* RN-01: El tipo de comprobante disponible se determina por la combinación de la condición IVA del emisor y del receptor; el sistema no permite emitir un tipo fiscalmente inválido.  
* RN-02: El CUIT del receptor se valida contra ARCA antes de habilitar la emisión.  
* RN-03: El comprobante debe tener al menos un ítem con descripción, cantidad y precio unitario.  
* RN-04: La emisión es asíncrona; el sistema actualiza el estado del comprobante cuando recibe respuesta de ARCA.  
* RN-05: Un comprobante puede originarse en un turno completado, en cuyo caso hereda los datos del servicio y del cliente, conforme al atributo turno\_id de la entidad Comprobante.  
* RN-06: El comprobante registra su saldo pendiente, que habilita la asociación de cobros parciales, conforme al atributo saldo\_pendiente de la entidad Comprobante.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso el CUIT de un receptor válido | El sistema valida contra ARCA, completa razón social y condición IVA y habilita el formulario | PAN-FAC-03 |
| Ingreso un CUIT inválido | El sistema indica que el CUIT no fue encontrado y bloquea el formulario | PAN-FAC-03 |
| Intento emitir sin ítems | El botón Emitir permanece deshabilitado | PAN-FAC-03 |
| Confirmo la emisión | El comprobante aparece en el listado con estado Pendiente mientras aguarda respuesta de ARCA | PAN-FAC-01 |
| ARCA autoriza el comprobante | El estado cambia a Autorizado con CAE visible y PDF disponible | PAN-FAC-02 |
| ARCA rechaza el comprobante | El estado cambia a Error con el mensaje devuelto visible en el detalle | PAN-FAC-02 |

## **HU-E5-04 — Anular un comprobante mediante una nota de crédito**

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

* RN-01: Una nota de crédito debe estar asociada obligatoriamente a un comprobante original autorizado, conforme al atributo comprobante\_origen\_id de la entidad Comprobante.  
* RN-02: El tipo de nota de crédito (A, B o C) debe coincidir con el del comprobante original; el sistema lo determina automáticamente.  
* RN-03: El monto de la nota de crédito no puede superar el del comprobante original.  
* RN-04: La emisión es asíncrona; el estado se actualiza cuando ARCA responde.  
* RN-05: Una vez autorizada la nota de crédito, el comprobante original refleja su nuevo estado de anulación total o parcial.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Selecciono un comprobante autorizado para anular | El sistema precarga tipo de nota, datos del receptor y monto máximo disponible | PAN-FAC-04 |
| Ingreso un monto mayor al del comprobante original | El sistema lo impide e informa el límite | PAN-FAC-04 |
| Confirmo la emisión | La nota de crédito aparece en el listado con estado Pendiente | PAN-FAC-01 |
| ARCA autoriza la nota de crédito | El estado cambia a Autorizado y el comprobante original refleja su anulación total o parcial | PAN-FAC-02 |

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
* RN-02: La numeración de comprobantes es independiente por punto de venta y por tipo de comprobante, conforme al atributo numerador\_por\_tipo.  
* RN-03: Un punto de venta debe estar habilitado en ARCA antes de poder emitir comprobantes con él.  
* RN-04: Desactivar un punto de venta impide nuevas emisiones con él pero conserva los comprobantes ya emitidos.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la administración de puntos de venta | Veo el listado con número, descripción y estado de cada punto | PAN-FAC-05 |
| Agrego un punto de venta habilitado en ARCA | Queda disponible para la emisión de comprobantes | PAN-FAC-05 |
| Desactivo un punto de venta | No se pueden emitir nuevos comprobantes con él, pero los existentes se conservan | PAN-FAC-05 |

# **Épica 6 — Cobros**

**Bounded Contexts asociados:** BC7 Cobros \[CORE\]  
**Acciones de dominio (Bloque K):** GenerarCobro (y métodos sobre Cobro: cancelar, reembolsar)  
Esta épica agrupa las historias del núcleo de cobranzas: la generación de links de pago, el seguimiento del estado de los cobros, su cancelación y reembolso, y la asociación de cobros a comprobantes y turnos.

## **HU-E6-01 — Consultar el estado de los cobros**

| ID | HU-E6-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta sobre Cobro) |
| **Descripción** | Como administrador u operador, quiero ver el estado general de todos los cobros del período con métricas de resumen, para tener visibilidad de lo cobrado, lo pendiente y lo que está en mora. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-COB-01 (Cobros — Listado) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.  
* Existe al menos un cobro registrado.

**Reglas de negocio**

* RN-01: Las métricas del encabezado (cobrado, pendiente, en mora, tasa de cobro) se calculan sobre el período activo; el período por defecto es el mes en curso.  
* RN-02: Un cobro pasa a estado En mora automáticamente al superar su vencimiento sin confirmación de pago.  
* RN-03: El listado permite filtrar por estado (Todos, Pagados, Pendientes, En mora) y buscar por cliente, concepto u operación.  
* RN-04: El rol Solo Lectura puede ver el listado y métricas pero no ejecutar acciones.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo Cobros | Veo las cuatro métricas del encabezado con sus variaciones respecto al período anterior | PAN-COB-01 |
| Aplico filtro En mora | El listado muestra solo los cobros vencidos ordenados por antigüedad | PAN-COB-01 |
| Un cobro supera su vencimiento sin pago | Su estado cambia automáticamente a En mora | PAN-COB-01 |

## **HU-E6-02 — Consultar el detalle de un cobro**

| ID | HU-E6-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta sobre Cobro) |
| **Descripción** | Como administrador u operador, quiero ver el detalle completo de un cobro, para conocer el historial de recordatorios, el estado del link de pago y los datos del cliente. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-COB-02 (Cobros — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.  
* El cobro existe y tiene al menos un link de pago generado.

**Reglas de negocio**

* RN-01: El detalle muestra el historial de recordatorios con timestamp, canal, estado de lectura y el próximo recordatorio programado, conforme a la entidad Recordatorio.  
* RN-02: El estado del link de pago se sincroniza con MercadoPago; si el cliente paga, el estado se actualiza automáticamente a Pagado.  
* RN-03: Un link de pago activo puede copiarse desde el detalle para envío manual.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro un cobro del listado | Veo monto adeudado, datos del cliente, detalle del cobro, link de pago y recordatorios | PAN-COB-02 |
| El cliente paga desde el link | El estado cambia automáticamente a Pagado y se detienen los recordatorios | PAN-COB-02 |
| Copio el link de pago | El link se copia con confirmación visual | PAN-COB-02 |

## **HU-E6-03 — Generar un link de cobro para un cliente**

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
* El cliente existe en Datos Maestros o se crea en el momento.

**Reglas de negocio**

* RN-01: El link se genera vía API de MercadoPago; el sistema almacena el identificador de preferencia para rastrear el pago, conforme al atributo mp\_preference\_id de la entidad Cobro.  
* RN-02: El concepto y el monto son obligatorios; el monto debe ser mayor a cero y en pesos argentinos.  
* RN-03: Al generar el link, el sistema inicia la cadena de recordatorios escalonados por WhatsApp.  
* RN-04: Un cobro puede tener un solo link de pago activo a la vez.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Hago clic en Nuevo cobro | Veo el formulario con cliente, concepto y monto | PAN-COB-03 |
| Intento generar sin concepto o sin monto | El botón Generar permanece deshabilitado | PAN-COB-03 |
| Confirmo la generación | El link aparece en el detalle con estado Activo y comienzan los recordatorios | PAN-COB-02 |
| MercadoPago no responde | El sistema informa el error y no crea el cobro | PAN-COB-03 |

## **HU-E6-04 — Cancelar un cobro**

| ID | HU-E6-04 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (método sobre Cobro) |
| **Descripción** | Como administrador u operador, quiero cancelar un cobro pendiente o en mora, para dar de baja una deuda que ya no corresponde cobrar. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-COB-02 (Cobros — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.  
* El cobro existe y tiene estado Pendiente o En mora.

**Reglas de negocio**

* RN-01: Solo pueden cancelarse cobros en estado Pendiente o En mora; un cobro Pagado no es cancelable.  
* RN-02: La cancelación requiere un motivo obligatorio de al menos 10 caracteres.  
* RN-03: Al cancelar, el sistema invalida el link de pago activo en MercadoPago si existe.  
* RN-04: La cancelación detiene la cadena de recordatorios automáticos.  
* RN-05: La cancelación queda registrada en el Log de Operaciones con el motivo, el usuario y el timestamp.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Intento cancelar un cobro Pagado | La opción de cancelar no está disponible | PAN-COB-02 |
| Inicio la cancelación de un cobro Pendiente o En mora | El sistema solicita un motivo obligatorio antes de confirmar | PAN-COB-02 |
| Confirmo la cancelación con motivo válido | El cobro pasa a Cancelado, el link se invalida y los recordatorios se detienen | PAN-COB-02 |

## **HU-E6-05 — Reembolsar un cobro aprobado**

| ID | HU-E6-05 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (método sobre Cobro) |
| **Descripción** | Como administrador, quiero emitir un reembolso sobre un cobro ya pagado, para devolver total o parcialmente un monto cobrado por error o devolución acordada. |
| **Prioridad** | Media |
| **Complejidad** | Alta |
| **Pantalla** | PAN-COB-02 (Cobros — Detalle) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.  
* El cobro existe y tiene estado Pagado.  
* La empresa tiene MercadoPago conectado.

**Reglas de negocio**

* RN-01: Solo pueden reembolsarse cobros con estado Pagado.  
* RN-02: El monto del reembolso no puede superar el monto original cobrado.  
* RN-03: El reembolso se ejecuta vía API de MercadoPago; si es rechazado, el cobro mantiene su estado Pagado y se notifica al administrador.  
* RN-04: El reembolso es asíncrono; el estado se actualiza cuando MercadoPago confirma.  
* RN-05: La acción está restringida al rol Administrador.  
* RN-06: El reembolso queda registrado en el Log de Operaciones.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Intento reembolsar un cobro no Pagado | La opción de reembolso no está disponible | PAN-COB-02 |
| Ingreso un monto mayor al cobrado | El sistema lo impide e informa el límite | PAN-COB-02 |
| Confirmo el reembolso | El sistema envía la solicitud y el cobro muestra Reembolso en proceso | PAN-COB-02 |
| MercadoPago confirma el reembolso | El cobro pasa a Reembolsado con el monto reembolsado visible | PAN-COB-02 |

## **HU-E6-06 — Asociar un cobro a un comprobante existente**

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

* RN-01: El cobro asociado referencia al comprobante, conforme al atributo comprobante\_id de la entidad Cobro.  
* RN-02: El monto del cobro no puede superar el saldo pendiente del comprobante.  
* RN-03: Al confirmarse el pago, el sistema reduce el saldo pendiente del comprobante en el monto cobrado.  
* RN-04: Un comprobante puede tener varios cobros asociados hasta saldar su total (pagos parciales).

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Genero un cobro y lo asocio a un comprobante con saldo | El sistema vincula el cobro al comprobante | PAN-COB-03 |
| Ingreso un monto mayor al saldo pendiente | El sistema lo impide e informa el saldo disponible | PAN-COB-03 |
| El cliente paga un cobro parcial | El saldo pendiente del comprobante se reduce en el monto cobrado | PAN-FAC-02 |

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

* RN-01: El cobro de seña referencia al turno, conforme al atributo turno\_id de la entidad Cobro.  
* RN-02: El estado del pago de la seña puede condicionar la confirmación del turno, según la regla de negocio configurada.  
* RN-03: Si el turno se cancela, el tratamiento de la seña (reembolso o retención) sigue la política de turnos vigente.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Genero un cobro y lo asocio a un turno como seña | El sistema vincula el cobro al turno | PAN-COB-03 |
| El cliente paga la seña | El turno refleja la seña abonada | PAN-AGE-02 |
| El turno se cancela con seña pagada | El sistema aplica la política de turnos vigente sobre la seña | PAN-AGE-02 |

# **Épica 7 — Agenda**

**Bounded Contexts asociados:** BC8 Agenda \[CORE\]  
**Acciones de dominio (Bloque K):** ReservarTurno, CancelarTurno, ReprogramarTurno, MarcarTurnoCompletado, MarcarNoShow  
Esta épica agrupa las historias de gestión de la agenda desde el panel: la visualización de turnos, su cancelación, reprogramación y registro de asistencia, y la configuración de los recursos reservables con su disponibilidad y excepciones.

## **HU-E7-01 — Ver la agenda de turnos desde el panel**

| ID | HU-E7-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta sobre Turno) |
| **Descripción** | Como administrador u operador, quiero ver la agenda de turnos del día y de períodos futuros desde el panel, para tener visibilidad completa de los turnos sin depender del agente. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-AGE-01 (Agenda — Vista general) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.  
* Existe al menos un recurso reservable configurado (HU-E7-04).

**Reglas de negocio**

* RN-01: La agenda muestra turnos agrupados por día; la vista por defecto es el día en curso.  
* RN-02: Los estados visibles son Reservado, Confirmado por cliente, Reprogramado, Cancelado, Completado y No se presentó.  
* RN-03: El usuario puede filtrar por recurso reservable, servicio y estado de turno.  
* RN-04: Decisión pendiente: si el administrador puede crear un turno manualmente desde el panel además de ver los existentes.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo de Agenda | Veo los turnos del día con cliente, servicio, recurso, hora y estado | PAN-AGE-01 |
| Navego a un día futuro | Veo los turnos reservados para ese día | PAN-AGE-01 |
| Filtro por recurso reservable | El listado muestra solo los turnos de ese recurso | PAN-AGE-01 |

## **HU-E7-02 — Cancelar o reprogramar un turno desde el panel**

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

* RN-01: La reprogramación verifica disponibilidad del recurso en el nuevo horario; si el slot está ocupado, el sistema rechaza la operación por solapamiento.  
* RN-02: Al cancelar, el sistema notifica al cliente por WhatsApp si tiene número registrado.  
* RN-03: Al reprogramar, el sistema notifica al cliente con el nuevo horario por WhatsApp si tiene número registrado.  
* RN-04: Ambas acciones quedan registradas en el Log de Operaciones.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro un turno de la agenda | Veo su detalle y las acciones disponibles según su estado | PAN-AGE-02 |
| Cancelo un turno Reservado o Confirmado | El turno pasa a Cancelado y el cliente recibe notificación | PAN-AGE-02 |
| Reprogramo a un horario disponible | El turno se mueve, el cliente recibe notificación y queda en el log | PAN-AGE-02 |
| Reprogramo a un horario ocupado | El sistema informa que el horario no está disponible y mantiene el turno original | PAN-AGE-02 |

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
* RN-03: El registro de asistencia o inasistencia queda en el Log de Operaciones.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Intento marcar asistencia en un turno futuro | La acción no está disponible | PAN-AGE-02 |
| Marco un turno pasado como Completado | El turno pasa a Completado y habilita la facturación del servicio | PAN-AGE-02 |
| Marco un turno pasado como No se presentó | El turno pasa a No se presentó y queda registrado en el log | PAN-AGE-02 |

## **HU-E7-04 — Definir la disponibilidad de un recurso reservable**

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

* RN-01: Un recurso reservable tiene nombre, tipo (persona o espacio) y una disponibilidad base semanal por día y franja, conforme a las entidades RecursoReservable y PatrónDeDisponibilidad.  
* RN-02: Un recurso puede asociarse a uno o más servicios agendables; solo esos servicios pueden reservarse en él.  
* RN-03: Desactivar un recurso no cancela los turnos ya reservados; solo impide nuevas reservas.  
* RN-04: Debe existir al menos un recurso activo para que el agente pueda ofrecer turnos.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la configuración de recursos | Veo el listado con nombre, tipo, servicios asociados y estado | PAN-AGE-03 |
| Creo un recurso con disponibilidad base semanal | Queda disponible para reservas en el horario configurado | PAN-AGE-03 |
| Asocio servicios al recurso | Solo esos servicios pueden reservarse en ese recurso | PAN-AGE-03 |
| Desactivo un recurso con turnos futuros | Los turnos reservados se mantienen pero no se permiten nuevas reservas | PAN-AGE-03 |

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
| Intento agregar una excepción que contradice otra existente | El sistema muestra el conflicto y bloquea el guardado | PAN-AGE-03 |

# **Épica 8 — Canal Conversacional (Cliente vía WhatsApp)**

**Bounded Contexts asociados:** BC9 Conversacional \[CORE\]  
**Acciones de dominio (Bloque K):** ReservarTurno, CancelarTurno, ProcesarMensajeEntrante, EscalarConversación  
Esta épica agrupa las historias en las que el actor es el cliente final de la PyME, que interactúa con el sistema a través del canal de WhatsApp. A diferencia del resto del modelo, estas historias no tienen pantalla de panel asociada: su interfaz es la conversación. Constituyen el modo de uso principal del producto desde la perspectiva del cliente.

## **HU-E8-01 — Reservar un turno conversando por WhatsApp**

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

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Escribo que quiero un turno y para cuándo | El agente interpreta la intención y me ofrece horarios disponibles reales | Canal WhatsApp |
| Elijo uno de los horarios ofrecidos | El agente confirma la reserva y registra el turno | Canal WhatsApp |
| El horario que pido no está disponible | El agente me ofrece alternativas cercanas disponibles | Canal WhatsApp |
| El agente no logra entender mi pedido | La conversación se deriva a un asesor humano | Canal WhatsApp |

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

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Solicito explícitamente hablar con una persona | El agente deriva la conversación a un asesor humano | Canal WhatsApp |
| El agente no entiende mi caso tras varios intentos | La conversación se escala automáticamente | Canal WhatsApp |
| Mi conversación es derivada | Recibo un aviso y el asesor cuenta con el contexto previo | Canal WhatsApp |

# **Épica 9 — Atención y Escalamiento (Operador)**

**Bounded Contexts asociados:** BC9 Conversacional \[CORE\] / BC10 Observabilidad y Auditoría  
**Acciones de dominio (Bloque K):** EscalarConversación, AbrirSolicitudDeSoporte  
Esta épica agrupa las historias del operador humano que atiende las conversaciones que el agente deriva, resuelve los escalamientos y abre solicitudes de soporte al equipo de CheatSheet. Complementa el canal conversacional aportando la capa de atención humana.

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
* Existe una conversación en estado escalado a la espera de atención.

**Reglas de negocio**

* RN-01: Al tomar una conversación escalada, el operador asume el control y el agente deja de responder en ese hilo, conforme a la entidad Escalamiento.  
* RN-02: El operador dispone del contexto completo de la conversación previa con el agente.  
* RN-03: Los mensajes enviados por el operador se distinguen visualmente de los del agente en el historial.  
* RN-04: La toma de la conversación queda registrada con el operador asignado y el timestamp.  
* RN-05: Decisión pendiente: si el agente puede reclasificar el tipo del hilo al retomar el control luego de la intervención humana.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Veo una conversación escalada | Puedo tomarla para atenderla personalmente | PAN-WA-01 |
| Tomo la conversación | El agente deja de responder y dispongo del contexto previo | PAN-WA-01 |
| Envío un mensaje al cliente | El mensaje se envía por WhatsApp y se distingue del agente en el historial | PAN-WA-01 |

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

* El operador atendió una conversación escalada (HU-E9-01).

**Reglas de negocio**

* RN-01: Al cerrar el escalamiento, el operador puede devolver la conversación al agente o darla por finalizada.  
* RN-02: Si devuelve la conversación al agente, este retoma el hilo con el contexto actualizado por la intervención humana.  
* RN-03: El cierre del escalamiento registra el estado final y queda en el Log de Operaciones.  
* RN-04: Un escalamiento cerrado no puede reabrirse; un nuevo pedido del cliente genera un escalamiento nuevo.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Resuelvo el caso y devuelvo la conversación al agente | El agente retoma el hilo con el contexto actualizado | PAN-WA-01 |
| Resuelvo el caso y lo doy por finalizado | El escalamiento queda cerrado y registrado en el log | PAN-WA-01 |
| Intento reabrir un escalamiento cerrado | El sistema no lo permite; un nuevo pedido genera uno nuevo | PAN-WA-01 |

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
| Intento enviar sin asunto o sin descripción | El sistema lo impide e indica los campos obligatorios | PAN-SOP-01 |
| Envío la solicitud | Queda registrada en estado abierto y puedo consultar su estado | PAN-SOP-01 |

## **HU-E9-04 — Administrar el repositorio de FAQ**

| ID | HU-E9-04 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre FAQ) |
| **Descripción** | Como administrador, quiero agregar, editar y eliminar preguntas frecuentes del agente, para que responda automáticamente las consultas más comunes de mis clientes. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-WA-02 (Agente WhatsApp — Configuración) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.  
* El agente está configurado y activo.

**Reglas de negocio**

* RN-01: Cada FAQ tiene una pregunta disparadora y una respuesta; ambos campos son obligatorios, conforme a la entidad FAQ.  
* RN-02: El sistema muestra cuántas veces fue usada cada FAQ en el período actual.  
* RN-03: Una FAQ eliminada deja de estar disponible para el agente de forma inmediata.  
* RN-04: Decisión pendiente: si se establece un límite máximo de FAQ por plan contratado.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Agrego una FAQ nueva | Aparece en el listado con contador en cero y disponible para el agente | PAN-WA-02 |
| Intento guardar una FAQ sin pregunta o sin respuesta | El sistema lo impide e indica el campo obligatorio | PAN-WA-02 |
| Elimino una FAQ | El sistema solicita confirmación y el agente deja de usarla | PAN-WA-02 |
| Reviso el listado de FAQ | Cada una muestra cuántas veces fue respondida este mes | PAN-WA-02 |

# **Épica 10 — Reportería y Análisis**

**Bounded Contexts asociados:** BC11 Reportería  
**Acciones de dominio (Bloque K):** ObtenerKPIsDelDashboard, GenerarReporte, PrevisualizarReporte, GenerarPaqueteContable  
Esta épica agrupa las historias de análisis y reportería: la visualización de indicadores del tablero, la generación y descarga de reportes, y la elaboración y distribución del paquete contable mensual al contador externo.

## **HU-E10-01 — Visualizar los indicadores (KPIs) del tablero**

| ID | HU-E10-01 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | ObtenerKPIsDelDashboard |
| **Descripción** | Como administrador u operador, quiero ver el dashboard de reportes del período con métricas de facturación, cobros, turnos y operaciones, para tener una visión consolidada de la actividad comercial. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Pantalla** | PAN-REP-01 (Reportes — Dashboard) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador, Operador o Contador externo.  
* Existe al menos un comprobante emitido en el período.

**Reglas de negocio**

* RN-01: El período por defecto es el mes en curso; el usuario puede cambiarlo con el selector.  
* RN-02: Las métricas del encabezado son total facturado, total cobrado, turnos gestionados y operaciones totales, con su variación respecto al período anterior.  
* RN-03: El gráfico de facturación por semana muestra el facturado neto agrupado por semana del período.  
* RN-04: El rol Contador externo puede ver el dashboard pero no acceder a ningún otro módulo.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al módulo Reportes | Veo las métricas del encabezado, el gráfico semanal y la distribución por tipo de comprobante | PAN-REP-01 |
| Cambio el período a un mes anterior | Las métricas y gráficos se actualizan para ese período | PAN-REP-01 |
| El período no tiene actividad | El sistema muestra un estado vacío acorde | PAN-REP-01 |

## **HU-E10-02 — Previsualizar un reporte antes de generarlo**

| ID | HU-E10-02 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | PrevisualizarReporte |
| **Descripción** | Como administrador u operador, quiero previsualizar un reporte antes de generarlo, para confirmar que el contenido y el período son los correctos. |
| **Prioridad** | Baja |
| **Complejidad** | Baja |
| **Pantalla** | PAN-REP-01 (Reportes — Dashboard) |

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
| **Pantalla** | PAN-REP-01 (Reportes — Dashboard) |

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
| **Pantalla** | PAN-REP-02 (Reportes — Configuración automática) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.  
* Decisión pendiente: si el Operador también puede configurar el envío automático.

**Reglas de negocio**

* RN-01: El paquete se genera automáticamente con los datos del mes cerrado, conforme a la entidad PaqueteContable.  
* RN-02: El día de envío es configurable; el formato puede ser PDF, XML o ambos.  
* RN-03: El contenido del paquete es configurable: facturas, notas de crédito, reporte de cobros, log de operaciones y resumen ejecutivo.  
* RN-04: Decisión pendiente: si el administrador puede generar un paquete de un período arbitrario fuera del ciclo automático.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso a la configuración automática | Veo el estado del envío, día, formato y contenido del paquete | PAN-REP-02 |
| Activo el envío automático | El sistema muestra la fecha del próximo envío programado | PAN-REP-02 |
| Genero un paquete de prueba | El sistema lo genera con los datos actuales y lo deja disponible | PAN-REP-02 |

## **HU-E10-05 — Compartir el paquete contable con el contador mediante enlace**

| ID | HU-E10-05 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | GenerarPaqueteContable |
| **Descripción** | Como administrador, quiero compartir el paquete contable con mi contador mediante un enlace de acceso limitado, para que pueda descargarlo sin tener una cuenta en el sistema. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Pantalla** | PAN-REP-02 (Reportes — Configuración automática) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.  
* Decisión pendiente: si el Operador también puede gestionar el acceso del contador.

**Reglas de negocio**

* RN-01: El contador accede mediante un enlace de acceso limitado enviado por email, sin necesidad de cuenta, conforme a la entidad TokenDeAccesoContable.  
* RN-02: El acceso del contador es fijo: ver y descargar reportes y paquetes; no accede a facturación, cobros, configuración ni datos de clientes.  
* RN-03: El administrador puede revocar el acceso en cualquier momento, invalidando el enlace de inmediato.  
* RN-04: Solo puede haber un contador externo activo por empresa a la vez.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Invito al contador con su email | El sistema envía el enlace de acceso limitado y lo muestra como invitado | PAN-REP-02 |
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
| El administrador revocó mi acceso | El enlace deja de funcionar | Enlace seguro |

# **Épica 11 — Configuración del Negocio**

**Bounded Contexts asociados:** BC3 Configuración de Negocio / BC10 Observabilidad y Auditoría  
**Acciones de dominio (Bloque K):** (métodos sobre ReglaDeNegocio, PlantillaDeNotificación, Notificación)  
Esta épica agrupa las historias de parametrización del comportamiento del sistema: la definición de reglas de negocio configurables, la administración de plantillas de notificación y la consulta del centro de notificaciones del panel.

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
| Una plantilla de WhatsApp no está aprobada | El sistema no permite usarla para ese canal hasta su aprobación | PAN-CFG-NOT |

## **HU-E11-03 — Consultar el centro de notificaciones del panel**

| ID | HU-E11-03 |
| :---- | :---- |
| **Actor** | Administrador / Operador |
| **Acción Bloque K** | (consulta sobre Notificación) |
| **Descripción** | Como administrador u operador, quiero consultar el centro de notificaciones del panel, para enterarme de los eventos relevantes del sistema que requieren mi atención. |
| **Prioridad** | Baja |
| **Complejidad** | Baja |
| **Pantalla** | PAN-CFG-NOT (Configuración — Notificaciones) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador u Operador.

**Reglas de negocio**

* RN-01: El centro de notificaciones lista los avisos dirigidos al usuario con su categoría, severidad y estado de lectura, conforme a la entidad Notificación.  
* RN-02: Las notificaciones que recibe cada usuario dependen de sus preferencias de suscripción (HU-E1-07).  
* RN-03: El usuario puede marcar notificaciones como leídas.  
* RN-04: Las notificaciones de severidad alta se destacan visualmente.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro el centro de notificaciones | Veo los avisos dirigidos a mí con su categoría, severidad y estado | PAN-CFG-NOT |
| Marco una notificación como leída | Su estado cambia y deja de destacarse como pendiente | PAN-CFG-NOT |
| Recibo una notificación de severidad alta | El sistema la destaca visualmente | PAN-CFG-NOT |

# **Épica 12 — Auditoría y Observabilidad (panel)**

**Bounded Contexts asociados:** BC10 Observabilidad y Auditoría  
**Acciones de dominio (Bloque K):** (consulta sobre RegistroDeAuditoría)  
Esta épica agrupa las historias de consulta de la bitácora de operaciones: el registro completo de todo lo que el sistema ejecuta en nombre del usuario, que constituye la fuente de verdad sobre qué hizo el sistema, cuándo y con qué resultado.

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

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Ingreso al Log de Operaciones | Veo el listado con timestamp, módulo, operación, entidad afectada, iniciador y estado | PAN-LOG-01 |
| Filtro por módulo y estado | El listado muestra solo las operaciones que coinciden | PAN-LOG-01 |
| Filtro por iniciador IA | Veo solo las operaciones ejecutadas automáticamente por el agente | PAN-LOG-01 |
| Busco por cliente o archivo | El listado filtra las operaciones relacionadas | PAN-LOG-01 |

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

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Abro una operación de la bitácora | Veo su resumen, datos de entrada, datos de salida y timeline de ejecución | PAN-LOG-02 |
| Abro una operación de facturación | Veo los datos del comprobante y el resultado de ARCA | PAN-LOG-02 |
| Abro una operación con error | Veo el motivo del error y el punto del timeline donde ocurrió | PAN-LOG-02 |

# **Historias de Sistema y Técnicas**

**Bounded Contexts asociados:** Transversal (BC asociados según cada proceso)  
**Acciones de dominio (Bloque K):** ConfirmarPago, ProcesarMensajeEntrante, EnviarRecordatorio, SincronizarParámetrosFiscales  
Las siguientes funcionalidades son procesos automáticos disparados por planificadores o por webhooks de sistemas externos. No responden a la acción directa de un usuario, por lo que se documentan como historias de sistema: en lugar de una pantalla, cada una consigna su disparador. Su correcta especificación es esencial porque sustentan las automatizaciones que constituyen la propuesta de valor del producto.

## **HS-T1 — Confirmar un pago a partir del webhook de MercadoPago**

| ID | HS-T1 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | ConfirmarPago |
| **Descripción** | El sistema recibe la notificación de pago de MercadoPago y actualiza el estado del cobro correspondiente de forma automática. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Disparador** |  webhook de MercadoPago |

**Precondiciones**

* Existe un cobro con link de pago activo.  
* La integración de MercadoPago está operativa.

**Reglas de negocio**

* RN-01: El proceso valida la autenticidad del webhook antes de procesarlo.  
* RN-02: Al confirmarse el pago, el cobro pasa a estado Pagado y se detiene la cadena de recordatorios.  
* RN-03: Si el cobro está asociado a un comprobante, se reduce su saldo pendiente; si está asociado a un turno como seña, se actualiza el estado del turno.  
* RN-04: El procesamiento es idempotente: una notificación repetida del mismo pago no genera efectos duplicados.  
* RN-05: El evento queda registrado en la bitácora con iniciador Sistema.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Llega un webhook de pago válido | El sistema actualiza el cobro a Pagado y detiene los recordatorios | Bitácora |
| El cobro estaba asociado a un comprobante | El sistema reduce el saldo pendiente del comprobante | Bitácora |
| Llega una notificación repetida del mismo pago | El sistema no genera efectos duplicados | Bitácora |
| El webhook no supera la validación de autenticidad | El sistema lo descarta y registra el intento | Bitácora |

## **HS-T2 — Procesar un mensaje entrante recibido desde WhatsApp**

| ID | HS-T2 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | ProcesarMensajeEntrante |
| **Descripción** | El sistema recibe un mensaje entrante de WhatsApp, interpreta su intención y lo encamina al flujo correspondiente o al agente. |
| **Prioridad** | Alta |
| **Complejidad** | Alta |
| **Disparador** |  webhook de WhatsApp |

**Precondiciones**

* La integración de WhatsApp está operativa.  
* El agente está activo o existe un operador disponible.

**Reglas de negocio**

* RN-01: El proceso registra el mensaje entrante con su contenido, tipo y conversación asociada, conforme a la entidad Mensaje.  
* RN-02: El sistema interpreta la intención del mensaje y la clasifica (turno, consulta, pago, FAQ).  
* RN-03: Si la confianza de interpretación es insuficiente, se inicia un escalamiento a un asesor humano.  
* RN-04: Si el horario está fuera del horario de atención configurado, el sistema responde según la política definida.  
* RN-05: El evento queda registrado en la bitácora con iniciador IA.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Llega un mensaje entrante | El sistema lo registra e interpreta su intención | Bitácora |
| La intención se interpreta con confianza | El sistema encamina el mensaje al flujo correspondiente | Bitácora |
| La intención no se interpreta con confianza | El sistema inicia un escalamiento a un asesor | Bitácora |

## **HS-T3 — Despachar recordatorios de cobro según la regla de escalamiento**

| ID | HS-T3 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | EnviarRecordatorio |
| **Descripción** | El sistema despacha automáticamente los recordatorios de cobro pendientes según la regla de escalamiento configurada. |
| **Prioridad** | Alta |
| **Complejidad** | Media |
| **Disparador** |  planificador (Celery Beat) |

**Precondiciones**

* Existen cobros pendientes o en mora.  
* Existe una regla de escalamiento de cobros activa (HU-E11-01).

**Reglas de negocio**

* RN-01: El proceso evalúa los cobros pendientes y determina cuáles corresponden a recordatorio según la regla de escalamiento vigente, conforme a la entidad Recordatorio.  
* RN-02: Cada recordatorio se despacha por el canal configurado y registra su paso en la secuencia de escalamiento.  
* RN-03: Un cobro pagado o cancelado deja de recibir recordatorios.  
* RN-04: El estado de entrega de cada recordatorio se registra para seguimiento.  
* RN-05: El proceso es idempotente respecto de la ventana de ejecución: no envía el mismo paso de recordatorio dos veces.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Un cobro alcanza el umbral de un paso de recordatorio | El sistema despacha el recordatorio por el canal configurado | Bitácora |
| Un cobro fue pagado | El sistema deja de enviarle recordatorios | Bitácora |
| Se ejecuta el planificador dos veces en la misma ventana | El sistema no duplica el mismo paso de recordatorio | Bitácora |

## **HS-T4 — Sincronizar los parámetros fiscales desde ARCA con su vigencia**

| ID | HS-T4 |
| :---- | :---- |
| **Actor** | Sistema |
| **Acción Bloque K** | SincronizarParámetrosFiscales |
| **Descripción** | El sistema sincroniza periódicamente los parámetros fiscales desde ARCA, manteniendo su vigencia temporal. |
| **Prioridad** | Media |
| **Complejidad** | Media |
| **Disparador** |  planificador |

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
| **Disparador** |  evento de dominio |

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
| **Disparador** |  planificador |

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
| Una tarea falla menos veces que el máximo | El sistema la reintenta | Bitácora |
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
| **Disparador** |  webhook de WhatsApp |

**Precondiciones**

* Llega un mensaje entrante de tipo nota de voz.  
* La integración de WhatsApp está operativa.

**Reglas de negocio**

* RN-01: El proceso detecta el tipo de contenido del mensaje entrante, conforme al atributo tipo\_contenido de la entidad Mensaje.  
* RN-02: Las notas de voz se transcriben a texto antes de la interpretación de intención.  
* RN-03: La transcripción se asocia al mensaje original conservando la referencia al audio.  
* RN-04: Si la transcripción no alcanza calidad suficiente, el sistema deriva la conversación a un asesor humano.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Llega una nota de voz | El sistema la transcribe a texto antes de interpretarla | Bitácora |
| La transcripción es de buena calidad | El sistema interpreta la intención como con un mensaje de texto | Bitácora |
| La transcripción no alcanza calidad suficiente | El sistema deriva la conversación a un asesor humano | Bitácora |

