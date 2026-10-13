# Unidad: mapeo-google-sheets-real

**HUs**: HU-E3-01, HU-E3-02, HU-E3-03, HU-E3-05, HU-E3-06 (vínculos Google Sheets)  **Contexto dueño**: spreadsheet_sync  **Rama**: `fix/spreadsheet_sync-mapeo-google-real`

## Qué hace

Una planilla Google ya vinculada muestra «Revisar mapeo». El panel lee encabezados y ejemplos de la hoja elegida, propone la correspondencia con IA y permite corregirla y confirmarla. Luego el worker lee las filas de esa hoja, las ingresa de forma asíncrona y muestra los errores por fila en Cargas recientes. La lectura usa la credencial OAuth de la empresa y el permiso al archivo otorgado en Picker. La sincronización automática de modificaciones posteriores sigue pendiente en HU-E3-04.

## Diseño

- **Dominio**: no cambian agregados ni reglas de `Mapeo` o `VinculoDePlanilla`. Se conserva `hoja_empresa` como la hoja fuente y `hoja_cheatsheet` como destino separado de la escritura de vuelta.
- **Aplicación**: `LeerEncabezados` distingue archivo subido de vínculo Google. Para Google exige un identificador de documento y credencial asociada al vínculo; devuelve el mismo contrato `ColumnaConEjemplo` que usa el mapeo de archivos. `ProponerMapeo`, la huella, la corrección y la confirmación se reutilizan. `ProcesarPlanilla` recibe un `PlanillaLeida` del lector correspondiente en vez de asumir bytes de R2; mantiene una sola rutina para aplicar el mapeo, normalizar mediante `master_data`, contar filas y registrar errores.
- **Puerto y adaptador**: un puerto de lectura de hoja recibe documento, hoja y token de acceso efímero. El adaptador de Google consulta Sheets `spreadsheets.values.get` para las primeras 100 filas al mostrar encabezados y lee las filas completas por lotes acotados al procesar. Convierte valores a texto conservando los números de fila de Google. Nunca consulta la hoja propia de CheatSheet ni envía ejemplos al modelo. El adaptador simulado permite pruebas sin red.
- **Otros contextos**: `spreadsheet_sync` obtiene el token mediante el servicio existente de `integrations`, con `empresa_id` y `configuracion_integracion_id`. No accede a tablas de otra empresa fuera de los repositorios autorizados.
- **API**: `GET /planillas/{vinculo_id}/encabezados` resuelve el token en la misma unidad de trabajo y mantiene la respuesta existente. `POST /planillas/cargas` conserva el contrato de encolado. El detalle de la carga indica si las filas admiten corrección dentro del panel, según el origen del procesamiento. Los errores de permiso o revocación se muestran como reconexión necesaria; los fallos temporales se informan sin crear un mapeo vacío.
- **Frontend**: la tarjeta ofrece «Revisar mapeo» para archivos y Google Sheets, pero no para Excel Online. La revisión y confirmación usan las rutas existentes. «Procesar la planilla» queda disponible para Google tras confirmar. Cargas recientes muestra el resultado y los errores con números de fila de Google. Para un error de Google se corrige la fuente y se reprocesan solo las filas fallidas; la edición de una fila dentro del panel, que actualmente lee R2, se ofrece únicamente para archivos subidos. El detalle necesita conocer el proveedor del vínculo para mostrar la acción correcta.

## Infraestructura

- **Migraciones**: no aplica; el vínculo ya guarda hoja, ID de documento e ID de la configuración OAuth.
- **Trabajo asíncrono**: la tarea existente `spreadsheet_sync.procesar_planilla` en `spreadsheet_processing` resuelve el token por empresa y lee la hoja Google cuando el vínculo no es un archivo. Conserva el registro del procesamiento, los errores por fila, la política de reintentos y la marca `ultima_lectura` solo al completar. El reproceso reutiliza la tarea y filtra por los números de fila que fallaron; no vuelve a ingresar las exitosas. El incremental permanece pendiente.
- **Configuración**: no se agregan variables; se reutilizan `GOOGLE_OAUTH_*`, `PLANILLA_ADAPTADOR` y `SECRETS_ENCRYPTION_KEY` en la API.
- **Google Sheets**: lecturas GET con timeout y reintentos limitados para 429, 5xx y fallos de red. 401/403 exigen reconectar y no se reintentan. Los encabezados se obtienen de las primeras 100 filas; la ingesta usa lotes de 500 filas para no pedir toda la hoja en una sola respuesta. Se corta con un error claro si el contenido leído supera 25 MB, el mismo límite de los archivos. No se registra contenido de celdas ni tokens en logs.

## Riesgos que obligan a tests

- [x] Un vínculo de otra empresa no puede obtener encabezados usando la credencial de la empresa activa.
- [x] Token vencido se renueva; autorización revocada no lee ni crea propuesta vacía.
- [x] Hoja elegida, hoja propia y ejemplos: solo se lee la hoja fuente; el modelo recibe solo nombres de columnas.
- [x] Fallas y formatos de respuesta de Google no se convierten en un mapeo exitoso.
- [x] Fila inválida no aborta la carga; el número de fila coincide con la hoja Google y las filas válidas se normalizan.
- [x] Reproceso no duplica filas ya exitosas y rechaza un cambio de encabezados antes de aplicar el mapeo confirmado.
- [x] Archivo subido conserva su comportamiento; Excel Online sigue sin acción de mapeo ni carga.

## Archivos a tocar

- [x] `backend/src/cheatsheet/contexts/spreadsheet_sync/application/{ports,mapeos}.py`
- [x] `backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/google_sheets.py`
- [x] `backend/src/cheatsheet/contexts/spreadsheet_sync/application/procesamientos.py` y `backend/src/cheatsheet/workers/tasks_spreadsheet.py`
- [x] `backend/src/cheatsheet/api/routers/planillas.py` y composición de credenciales existente
- [x] Tarjeta de planilla y detalle de cargas del frontend; la revisión reutiliza el componente existente
- [x] Tests de aplicación, adaptador HTTP de Google, worker y frontend

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Google lee encabezados y primeros ejemplos de la hoja fuente sin leer la hoja propia | contrato HTTP | automatizado |
| 2 | Token vencido se renueva y un token revocado exige reconexión | aplicación/contrato | cubierto por tests de credenciales existentes y ruta de lectura |
| 3 | Empresa distinta no usa el vínculo ni la credencial | API/integración | cubierto por repositorio con RLS y obtención de credencial por empresa; prueba manual pendiente |
| 4 | Propuesta IA, corrección y confirmación funcionan con columnas Google | aplicación/API | reutiliza casos existentes; prueba manual pendiente |
| 5 | Procesar Google incorpora filas válidas, conserva números y errores de las inválidas | worker/aplicación | automatizado |
| 6 | Reprocesar Google lee solo filas fallidas y no duplica las exitosas | worker/aplicación | cubierto por la lógica de reproceso existente; prueba manual pendiente |
| 7 | Archivo sigue funcionando; Excel no ofrece mapeo; Google ofrece procesar | frontend/regresión | automatizado |
| 8 | Prueba manual con un documento Google real en staging | manual | pendiente |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | Juan aprobó el mapeo de Google Sheets y amplió el alcance para incluir la ingesta inicial de filas |
| 2 · Verificación | 2026-10-13 | 3306 tests backend y 1434 frontend pasan; 655 tests de integración pasan en PostgreSQL y Redis locales aislados. Ruff, MyPy, TypeScript y ESLint pasan. Prueba manual con Google real pendiente. |
| 3 · PR | 2026-10-12 | PR borrador #206 contra `develop`; revisión de Vincenzo y prueba manual en staging pendientes |

## Decisiones tomadas durante la unidad

- Se implementan juntos el mapeo y la carga inicial de Google. La lectura incremental queda en HU-E3-04 y no se activa por el solo hecho de confirmar un mapeo.
