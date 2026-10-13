# Unidad: mapeo-google-sheets-real

**HUs**: HU-E3-01, HU-E3-02 (vínculos Google Sheets)  **Contexto dueño**: spreadsheet_sync  **Rama**: `fix/spreadsheet_sync-mapeo-google-real`

## Qué hace

Una planilla Google ya vinculada muestra «Revisar mapeo». El panel lee los encabezados y ejemplos de la hoja elegida, propone la correspondencia con IA y permite corregirla y confirmarla. La lectura usa la credencial OAuth de la empresa y el permiso al archivo otorgado en Picker. Este cambio no procesa filas ni sincroniza modificaciones; esas operaciones siguen en HU-E3-03 y HU-E3-04.

## Diseño

- **Dominio**: no cambian agregados ni reglas de `Mapeo` o `VinculoDePlanilla`. Se conserva `hoja_empresa` como la hoja fuente y `hoja_cheatsheet` como destino separado de la escritura de vuelta.
- **Aplicación**: `LeerEncabezados` distingue archivo subido de vínculo Google. Para Google exige un identificador de documento y credencial asociada al vínculo; devuelve el mismo contrato `ColumnaConEjemplo` que usa el mapeo de archivos. `ProponerMapeo`, la huella, la corrección y la confirmación se reutilizan.
- **Puerto y adaptador**: un puerto de lectura de encabezados de una hoja recibe documento, hoja y token de acceso efímero. El adaptador de Google consulta Sheets `spreadsheets.values.get` para las primeras 100 filas de la hoja fuente, convierte valores a texto y toma el primer ejemplo no vacío por columna. Nunca consulta la hoja propia de CheatSheet ni envía ejemplos al modelo. El adaptador simulado permite pruebas sin red.
- **Otros contextos**: `spreadsheet_sync` obtiene el token mediante el servicio existente de `integrations`, con `empresa_id` y `configuracion_integracion_id`. No accede a tablas de otra empresa fuera de los repositorios autorizados.
- **API**: `GET /planillas/{vinculo_id}/encabezados` resuelve el token en la misma unidad de trabajo y mantiene la respuesta existente. Los errores de permiso o revocación se muestran como reconexión necesaria; los fallos temporales se informan sin crear un mapeo vacío.
- **Frontend**: la tarjeta ofrece «Revisar mapeo» para archivos y Google Sheets, pero no para Excel Online. La revisión y confirmación usan las rutas existentes. Para Google se oculta la acción «Procesar» y se explica que la carga inicial desde Google aún está pendiente, de modo que confirmar no lleva a una operación que el worker descarta.

## Infraestructura

- **Migraciones**: no aplica; el vínculo ya guarda hoja, ID de documento e ID de la configuración OAuth.
- **Trabajo asíncrono**: no aplica a leer encabezados. La carga inicial y el incremental permanecen pendientes.
- **Configuración**: no se agregan variables; se reutilizan `GOOGLE_OAUTH_*`, `PLANILLA_ADAPTADOR` y `SECRETS_ENCRYPTION_KEY` en la API.
- **Google Sheets**: una lectura GET con timeout y reintentos limitados para 429, 5xx y fallos de red. 401/403 exigen reconectar y no se reintentan. El rango acotado evita descargar la planilla completa solo para mostrar encabezados y ejemplos. No se registra contenido de celdas ni tokens en logs.

## Riesgos que obligan a tests

- [x] Un vínculo de otra empresa no puede obtener encabezados usando la credencial de la empresa activa.
- [x] Token vencido se renueva; autorización revocada no lee ni crea propuesta vacía.
- [x] Hoja elegida, hoja propia y ejemplos: solo se lee la hoja fuente; el modelo recibe solo nombres de columnas.
- [x] Fallas y formatos de respuesta de Google no se convierten en un mapeo exitoso.
- [x] Archivo subido conserva su comportamiento, Excel Online sigue sin acción de mapeo y Google no ofrece procesar todavía.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/contexts/spreadsheet_sync/application/{ports,mapeos}.py`
- [ ] `backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/google_sheets.py`
- [ ] `backend/src/cheatsheet/api/routers/planillas.py` y composición de credenciales existente
- [ ] `frontend/src/features/spreadsheet_sync/components/{TarjetaDePlanilla,RevisionDeMapeo}.tsx` y la página de revisión
- [ ] Tests de aplicación, contrato HTTP/API y frontend

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Google lee encabezados y primeros ejemplos de la hoja fuente sin leer la hoja propia | contrato HTTP | pendiente |
| 2 | Token vencido se renueva y un token revocado exige reconexión | aplicación/contrato | pendiente |
| 3 | Empresa distinta no usa el vínculo ni la credencial | API/integración | pendiente |
| 4 | Propuesta IA, corrección y confirmación funcionan con columnas Google | aplicación/API | pendiente |
| 5 | Archivo sigue funcionando; Excel no ofrece mapeo; Google no ofrece procesar | frontend/regresión | pendiente |
| 6 | Prueba manual con un documento Google real en staging | manual | pendiente |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | Juan aprobó el alcance conversado; documento pendiente de revisión |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Se implementa el mapeo de Google ahora y se mantiene la carga inicial/incremental en sus unidades pendientes. No se presentará el botón de procesar hasta que exista lectura de filas.
