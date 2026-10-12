# Unidad: google-real-y-write-back

**HU principal**: HU-E3-07  **Prerequisito que se completa**: OAuth por archivo de HU-E2-04  **Contexto dueño**: spreadsheet_sync  **Rama**: `fix/spreadsheet_sync-google-write-back-real`

## Qué hace

Una empresa autoriza una planilla concreta de Google Sheets, conserva el acceso para las
tareas programadas y ve los registros creados en el panel o por el agente en una hoja propia
de CheatSheet. Un vínculo sin permiso de escritura, de Excel o de archivo subido no escribe.
Esta unidad habilita la credencial que necesita después HU-E3-04; la lectura incremental
queda en `sincronizacion-incremental-real`.

## Diagnóstico confirmado

- El canje OAuth actual devuelve solo `access_token`; descarta `refresh_token` y no crea
  `ConfiguracionDeIntegracion`. El vínculo tiene la FK prevista pero queda nula.
- `escritura_de_planilla()` construye `EscrituraEnGoogleSheets` con `token=""`.
- El formulario acepta una URL antes del consentimiento. Con el alcance acotado `drive.file`,
  pegar una URL no concede por sí solo acceso al archivo: hace falta que el usuario lo abra
  con un selector compatible, como Google Picker.
- El adaptador actual envía `values.update` a una hoja que todavía no creó. Además, escribe
  solo las primeras 500 filas y marca la escritura completa; una próxima corrida sobrescribe
  el comienzo de la hoja con solo los registros posteriores a la marca temporal.

## Diseño

- **Dominio**: conservar las tres guardas existentes y la hoja original inmutable. El
  vínculo mantiene `configuracion_integracion_id` y `hoja_cheatsheet`; no se agregan secretos
  ni tokens al agregado.
- **Aplicación**: separar el canje/registro de credencial de la selección del documento. La
  vinculación final exige un documento que Google permita describir con el token de esa
  empresa. La escritura recibe un token vigente por vínculo en cada ejecución; nunca usa
  una credencial global ni una caché de tokens.
- **Integrations**: mediante su contrato publicado de aplicación, guardar cifrado el token
  de renovación que devuelve Google, asociado a `empresa_id` y `GOOGLE_SHEETS`.
  Resolver una credencial solo para la empresa y el vínculo solicitado; pedir un token de
  acceso nuevo en cada ejecución y reflejar revocación como estado que requiere reconectar.
  Ni la clave de cifrado ni el token de renovación salen de este contexto.
- **Google ACL**: mantener el alcance `drive.file`. Canje, renovación, lectura de metadatos,
  creación y protección de la hoja propia y escritura usan timeout, reintentos acotados para
  fallas transitorias y errores explícitos para 401/403. La protección se crea o comprueba
  por identificador de hoja, sin tocar la hoja de la empresa.
- **Escritura**: reconstruir la hoja propia con todos los registros PANEL/AGENTE actuales,
  en lotes completos y con un orden estable por nombre e identificador. Escribir todas las páginas,
  retirar solo filas sobrantes de esa hoja y registrar `ultima_escritura` únicamente después
  del éxito total. Reintentar una corrida produce el mismo contenido; ningún lote parcial
  se considera completado. La lista se obtiene mediante el servicio de aplicación de
  `master_data`, que conserva el filtro de origen.
- **Frontend**: para el adaptador Google real, elegir un archivo de Google Sheets mediante
  Picker con un token de acceso de corta vida que permanece solo en memoria del navegador;
  luego completar el consentimiento offline del backend. No se pone en URL, cookies, logs ni storage
  persistente del navegador. Se conserva el recorrido simulado de staging hasta configurar
  el proveedor real. La pantalla muestra si la escritura está disponible para el vínculo.
- **Otros contextos**: `spreadsheet_sync` consume solo `integrations/application` y
  `master_data/application`, como permite el Context Map. Las dependencias concretas se
  arman en API y worker.

## Infraestructura

- **Migraciones**: reutilizar `configuracion_de_integracion` y la FK existente; verificar
  la unicidad por empresa/proveedor y el aislamiento RLS. Una migración nueva solo si las
  pruebas demuestran que el esquema actual no alcanza. Los vínculos Google ya creados sin
  credencial requieren reconexión: no existe un refresh token recuperable.
- **Trabajo asíncrono**: mantener Beat y la cola `incremental_sync`. Resolver credencial
  dentro de la transacción de cada empresa. Un fallo de Google deja el vínculo intacto y
  permite reintento; una credencial revocada pide reconectar, sin bucle de reintentos.
- **Configuración**: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` y
  `SECRETS_ENCRYPTION_KEY` existentes; agregar al `.env.example` las variables públicas
  necesarias para Picker (clave de API restringida y número de proyecto), sin valores
  reales. En staging, API y worker usarán el adaptador `google` solo tras configurar el
  cliente OAuth y el proyecto de Google Cloud. Juan no tiene acceso a esa configuración;
  el cambio de entorno queda como paso operativo documentado para quien sí lo tenga.
- **Contrato externo**: OAuth `authorization_code` y `refresh_token` en
  `https://oauth2.googleapis.com/token`; metadatos, `batchUpdate` y `values` en
  `https://sheets.googleapis.com/v4/spreadsheets`. En 401/403 se informa pérdida de
  permiso; 429/5xx y timeouts se reintentan con backoff limitado. Los tests usan dobles,
  nunca Google real. Documentación oficial:
  [OAuth web](https://developers.google.com/identity/protocols/oauth2/web-server),
  [alcance drive.file](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
  [Picker web](https://developers.google.com/workspace/drive/picker/guides/web-picker),
  [Sheets batchUpdate](https://developers.google.com/workspace/sheets/api/guides/batchupdate).

## Riesgos que obligan a tests

- [x] Aislamiento por `empresa_id`: un vínculo no puede usar la credencial de otra empresa.
- [x] Secretos: el refresh token queda cifrado en reposo y ausente de respuestas y logs;
  el token efímero de Picker vive solo en memoria del navegador.
- [x] Reintentos y lotes: fallo intermedio no adelanta `ultima_escritura`; reintentar no duplica.
- [x] Tres guardas anti-bucle: lectura y escritura, hoja propia y origen PANEL/AGENTE.
- [x] Google revocado, permiso insuficiente y hoja propia faltante o ya creada.
- [x] Cambios de una persona normalizados no se escriben en la hoja original.

## Archivos a tocar

- [x] `backend/src/cheatsheet/contexts/integrations/application/` y adaptador OAuth Google:
      guardar, resolver y renovar credenciales por empresa.
- [x] `backend/src/cheatsheet/contexts/spreadsheet_sync/application/{ports,vinculos,sincronizacion}.py`:
      contrato de OAuth, vínculo y escritura idempotente.
- [x] `backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/{google_sheets,escritura,ensamblado}.py`:
      Picker/Sheets ACL, hoja propia protegida y lotes.
- [x] `backend/src/cheatsheet/api/routers/planillas.py` y
      `backend/src/cheatsheet/workers/tasks_spreadsheet.py`: composición por empresa.
- [x] `frontend/src/features/spreadsheet_sync/` y `frontend/src/app/api/planillas/google/`:
      selección real, callback y estado del vínculo.
- [x] `frontend/.env.example`, configuración de Render y runbook de staging.
- [x] Tests de aplicación, API, HTTP simulado y frontend; prueba real de staging pendiente.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | El canje conserva refresh token cifrado y lo asocia a la empresa correcta | unit/integración DB | unit pasa; DB pendiente |
| 2 | Un token vencido se renueva; uno revocado no escribe ni se registra como éxito | contrato HTTP | pasa con doble HTTP |
| 3 | Seleccionar archivo con Picker permite vincularlo; cancelar no crea vínculo | frontend/API | pasa con Picker simulado |
| 4 | Se crea y protege solo la hoja de CheatSheet; una segunda corrida la reutiliza | contrato HTTP | pasa con doble HTTP |
| 5 | Más de 500 registros se escriben completos y una falla intermedia no adelanta la marca | unit/contrato HTTP | pasa |
| 6 | Solo vínculos Google de lectura y escritura y origen PANEL/AGENTE escriben | unit | pasa |
| 7 | Una empresa no lee ni usa el token de otra | integración DB | unit pasa; DB pendiente |
| 8 | Con Google real en staging, crear un cliente PANEL aparece en la hoja propia | manual, requiere acceso del equipo a Google Cloud y Render | pendiente |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | Juan indicó avanzar primero con HU-E3-07 sobre el plan presentado; HU-E3-04 queda para después |
| 2 · Verificación | 2026-10-12 | Juan aprobó la verificación y pidió preparar el PR. Se corrigieron hallazgos de revisión sobre múltiples vínculos y revocación. Pasan 3288 pruebas backend (655 omitidas por PostgreSQL/Redis) y 1431 frontend; lint, tipos y build del panel pasan. La prueba Google real sigue pendiente del despliegue. |
| 3 · PR | 2026-10-12 | Juan pidió el PR. [#190](https://github.com/cheatsheet12/CheatSheet/pull/190) abierto contra `develop`; prueba real de staging pendiente del merge y despliegue. |

## Decisiones tomadas durante la unidad

- La lectura incremental de HU-E3-04 queda en una segunda unidad; esta conserva y usa la
  credencial por empresa para cerrar HU-E3-07.
- Se mantiene `drive.file` y se agrega selección real del archivo; no se amplía el acceso
  a todas las planillas de la cuenta.
- Juan creó el proyecto de Google Cloud y configuró los dos callbacks OAuth y la clave
  restringida de Picker. La activación en Render y la prueba real de staging siguen
  pendientes; los tests no equivalen a esa validación externa.
- Una empresa conserva una credencial Google conectada para todos sus vínculos. Al
  agregar otra planilla, el sistema comprueba que esa credencial también la pueda abrir;
  no reemplaza silenciosamente el token de los vínculos anteriores.
