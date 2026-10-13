---
entregable: matriz
parte: filas-caballero
responsable: Juan Caballero
estado: borrador
hu: [HU-E4-01, HU-E4-02, HU-E4-03, HU-E4-04, HU-E3-01, HU-E3-02, HU-E3-03, HU-E3-04, HU-E3-05, HU-E3-06, HU-E3-07]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - docs/aidlc/units.md
  - docs/aidlc/TODO.md
  - backend/src/cheatsheet/contexts/master_data/
  - backend/src/cheatsheet/contexts/spreadsheet_sync/
  - frontend/src/features/master_data/
  - frontend/src/features/spreadsheet_sync/
observaciones: >
  Estado al 13/10/2026 sobre develop. Prueba manual en staging con la empresa de prueba de Juan
  Caballero, rol Administrador, los días 12/10 y 13/10/2026.
  Bugs encontrados en la prueba y corregidos: el botón «Ver el cliente existente» no aparecía ante
  un CUIT duplicado (PR #155); corregir una columna de un mapeo guardado respondía 500 por clave
  duplicada (PR #163); la IA del mapeo respondía 400 porque el esquema enviado a Anthropic tenía
  límites que la API no admite (PR #162 para el diagnóstico, PR #164 para el arreglo).
  Desde el 12/10 se integraron el mapeo y la carga desde Google Sheets (PR #206 y #207) y la
  escritura de vuelta real (PR #190), y se probaron el 13/10.
  HU-E3-04 queda En desarrollo: la sincronización incremental no vuelve a leer la hoja vinculada
  (TODO.md §15.1); la unidad sincronizacion-incremental-real está pendiente.
  Diferencias menores sin corregir: los mensajes de validación del backend salen sin tildes
  («digitos», «duracion», «digito verificador»); la revisión de mapeo respondió 500 para dos
  vínculos de archivo creados en una sesión anterior, sin reproducirse con archivos nuevos.
---

## Filas — Juan Caballero

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |
|---|---|---|---|---|---|---|---|---|
| Datos Maestros | Consultar y gestionar el catálogo de clientes | HU-E4-01 | Administrador, Operador | Cliente | PAN-DM-01 | Probado | Simulada · pendiente de validar | 12/10/2026 |
| Datos Maestros | Consultar y gestionar el catálogo de servicios | HU-E4-02 | Administrador, Operador | Servicio | PAN-DM-02 | Probado | No aplica | 12/10/2026 |
| Datos Maestros | Gestionar categorías personalizadas | HU-E4-03 | Administrador, Operador | CategoríaEmpresa | PAN-DM-03 | Probado | No aplica | 12/10/2026 |
| Datos Maestros | Clasificar clientes o servicios mediante categorías | HU-E4-04 | Administrador, Operador | Cliente, Servicio | PAN-DM-01 / PAN-DM-02 | Probado | No aplica | 12/10/2026 |
| Ingesta y Sincronización de Planillas | Mapear los encabezados de la planilla con asistencia inteligente | HU-E3-01 | Administrador, Operador | EntradaDeMapeo | PAN-ING-02 | Probado | Real · validada | 13/10/2026 |
| Ingesta y Sincronización de Planillas | Confirmar o corregir el mapeo propuesto | HU-E3-02 | Administrador, Operador | Mapeo | PAN-ING-02 | Probado | Real · validada | 13/10/2026 |
| Ingesta y Sincronización de Planillas | Procesar la carga inicial de la planilla | HU-E3-03 | Administrador, Operador | ProcesamientoDePlanilla | PAN-ING-01 | Probado | Real · validada | 13/10/2026 |
| Ingesta y Sincronización de Planillas | Sincronizar los cambios incrementales de la planilla | HU-E3-04 | Administrador, Operador | VínculoDePlanilla | PAN-ING-01 | En desarrollo | Sin implementar | 20/10/2026 |
| Ingesta y Sincronización de Planillas | Consultar el resultado y los errores de un procesamiento | HU-E3-05 | Administrador, Operador, Solo Lectura | ErrorDeFila | PAN-ING-03 | Probado | No aplica | 12/10/2026 |
| Ingesta y Sincronización de Planillas | Reprocesar una planilla tras corregir errores | HU-E3-06 | Administrador, Operador | ProcesamientoDePlanilla | PAN-ING-03 | Probado | No aplica | 12/10/2026 |
| Ingesta y Sincronización de Planillas | Escribir de vuelta en la planilla los registros gestionados desde el panel | HU-E3-07 | Administrador, Operador | VínculoDePlanilla | PAN-ING-02 | Probado | Real · validada | 13/10/2026 |

### Qué respalda cada estado

| HU | Prueba manual en staging |
|---|---|
| HU-E4-01 | 12/10/2026. Listado con nombre, CUIT, origen, WhatsApp y estado; alta con CUIT válido que completa razón social y condición frente al IVA desde el padrón de ARCA (simulado en staging) y queda con origen PANEL; un CUIT con formato inválido bloquea el guardado; un CUIT duplicado, con o sin puntuación (RN-05), muestra «Ya existe un cliente con ese CUIT.» y el botón «Ver el cliente existente», que filtra el listado; la edición guarda los cambios; el cliente creado aparece de inmediato en el selector de «Nuevo cobro» (RN-04). El botón del duplicado faltaba y se corrigió en el PR #155 |
| HU-E4-02 | 12/10/2026. Listado con nombre, precio, IVA, duración y estado; un servicio agendable sin duración, un precio cero y duraciones de 4 y 481 minutos bloquean el guardado, y 5 y 480 se aceptan; alta y edición se guardan. El criterio cruzado con facturación (PAN-FAC-03) pertenece a Facturación Electrónica |
| HU-E4-03 | 12/10/2026. Alta de categoría; nombre duplicado en el mismo ámbito bloquea el guardado; renombrar se refleja en el filtro de los elementos clasificados. La eliminación con confirmación abre un diálogo nativo del navegador y se verificó con el test automatizado `ListadoDeCategorias.test.tsx` |
| HU-E4-04 | 12/10/2026. Una categoría de Clientes clasifica un cliente y otra de Servicios, un servicio, y ambos quedan filtrables; cada selector ofrece solo las categorías de su ámbito |
| HU-E3-01 | 13/10/2026. Con un archivo subido y con una planilla de Google Sheets vinculada, la IA propuso el campo y la confianza de cada columna (RN-01); las columnas sin coincidencia quedaron en «Sin asignar» sin bloquear (RN-03); un segundo archivo con los mismos encabezados reutilizó el mapeo guardado. El 400 de Anthropic se corrigió en el PR #164 |
| HU-E3-02 | 12/10 y 13/10/2026. Columna, campo, ejemplo y confianza por fila; la corrección manual marca «Corregida»; sin la columna obligatoria asignada, «Confirmar y procesar» queda deshabilitado con el mensaje de la HU; al confirmar se habilita el procesamiento. Se repitió con una planilla de Google Sheets. El 500 al corregir un mapeo guardado se corrigió en el PR #163 |
| HU-E3-03 | 12/10 y 13/10/2026. El procesamiento es asíncrono y avisa que el resultado aparece en «Cargas recientes»; las filas con CUIT inválido quedan con error sin abortar el resto; los nombres se guardan normalizados con origen PLANILLA. Se repitió con una planilla de Google Sheets. No se probaron el formato no soportado ni el límite de 25 MB |
| HU-E3-04 | No se puede probar: la sincronización incremental no vuelve a leer la hoja vinculada (TODO.md §15.1) |
| HU-E3-05 | 12/10/2026. Totales de filas procesadas y con error, cada fila con su número original y su motivo; «Descargar el listado de errores» baja un CSV idéntico a lo mostrado. No se probó con el rol Solo Lectura |
| HU-E3-06 | 12/10/2026. «Corregir» en cada fila la reprocesa sin esperar un botón global; terminó en 4 de 4 procesadas y 0 con error, estado «Procesado», sin duplicar filas ya corregidas |
| HU-E3-07 | 13/10/2026. Un cliente creado desde el panel apareció en la planilla de Google Sheets vinculada |
