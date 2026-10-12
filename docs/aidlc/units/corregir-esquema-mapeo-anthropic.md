# Unidad: corregir-esquema-mapeo-anthropic

**HUs**: HU-E3-01   **Contexto dueño**: spreadsheet_sync   **Rama**: fix/spreadsheet_sync-esquema-mapeo-anthropic

## Qué hace

Corrige el `400 Bad Request` que impide al adaptador real de Anthropic proponer el mapeo de encabezados de un archivo subido. El pedido enviará un JSON Schema admitido por la API y seguirá validando localmente que la confianza esté entre 0 y 1 antes de aceptar una asignación. La revisión y corrección manual siguen disponibles cuando el proveedor falle.

Esta unidad cubre el camino de archivo subido. La lectura de celdas de Google Sheets vinculadas y la sincronización incremental pertenecen a otra brecha y no intervienen en este 400.

## Diagnóstico y alcance

En staging, `ANTHROPIC_API_KEY` faltaba inicialmente; después de configurarla y usar `claude-sonnet-5-5`, la solicitud llegó a Anthropic y devolvió 400. `ModeloDeLenguajeAnthropic.proponer_mapeo` envía `ESQUEMA_DE_MAPEO` en `output_config.format`. La propiedad `confianza` declara `minimum: 0` y `maximum: 1`. La documentación actual de Anthropic sobre salidas estructuradas indica expresamente que las restricciones numéricas en un esquema crudo no están admitidas y generan 400. El identificador del modelo y la forma de `output_config.format` sí están documentados como válidos. Esta es una causa demostrada en el contrato publicado; la prueba en staging determinará si había además otro motivo para el 400.

## Diseño

- **Dominio**: no cambia; los umbrales `NivelDeConfianza` siguen vigentes.
- **Aplicación**: no cambia `ProponerMapeo` ni su degradación a mapeo manual.
- **Puertos y adaptadores**: quitar `minimum` y `maximum` del campo `confianza` de `ESQUEMA_DE_MAPEO` en `infrastructure/modelo.py`. Mantener el tipo `number` en el esquema y la comprobación `0 <= score <= 1` de `_interpretar`.
- **Otros contextos**: ninguno.
- **Frontend**: no cambia.

## Infraestructura

- **Migraciones**: no aplica.
- **Trabajo asíncrono**: no aplica.
- **Configuración**: no se agregan variables; staging ya tiene `ANTHROPIC_API_KEY`, `LLM_ADAPTADOR=anthropic` y `LLM_MODELO=claude-sonnet-5-5` según la prueba registrada.
- **Integraciones externas**: se usa el adaptador Anthropic existente, con su timeout y su manejo de fallas. Los tests automatizados no llaman a la red. Tras desplegar, repetir la propuesta en staging y comprobar una asignación automática con confianza visible, o registrar el cuerpo del error si persistiera el 400.

## Riesgos que obligan a tests

- [ ] Toca dinero
- [ ] Toca comprobantes fiscales / CAE
- [ ] Consume un webhook
- [ ] Agrega datos con `tenant_id`
- [x] Usa salida de un LLM: conservar la validación local del score y de los atributos antes de cualquier procesamiento
- [ ] Datos personales o fiscales: el modelo continúa recibiendo solo nombres de columnas

## Archivos a tocar

- [x] `backend/tests/contexts/spreadsheet_sync/infrastructure/test_modelo.py`: prueba de regresión del esquema enviado y conservación del rechazo local de scores fuera de rango.
- [x] `backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/modelo.py`: quitar las dos restricciones numéricas del esquema enviado.
- [x] Este plan: registrar Gate 1 y la verificación local. Gate 3 queda pendiente.

## Secuencia de implementación

1. En la rama prevista, escribir un test que inspeccione el esquema que `proponer_mapeo` entrega a `messages.create` mediante un doble del cliente externo. El doble rechazará una propiedad `confianza` con `minimum` o `maximum` y devolverá una propuesta válida cuando el contrato sea admitido. Afirmar la asignación interpretada, no solo la presencia del doble.
2. Ejecutar ese test y registrar el fallo esperado con el código actual: el esquema contiene las dos restricciones numéricas.
3. Quitar únicamente `minimum` y `maximum` del esquema. Ejecutar otra vez el test y los casos existentes de `_interpretar`, incluidos `-0.2` y `1.5`, que deben continuar descartados.
4. Ejecutar los gates del repositorio para backend (`ruff format --check .`, `ruff check .`, `mypy .`, `pytest`). No hay cambios de frontend. Revisar el diff para comprobar que no se modificó la lógica de degradación ni se incluyeron datos de clientes en logs.
5. Con la unidad desplegada en staging, subir un archivo de prueba nuevo con encabezados reconocibles y abrir PAN-ING-02. Confirmar que al menos una columna recibe propuesta automática y que el log no muestra el 400. Si vuelve a fallar, capturar `codigo`, `mensaje` y `cuerpo` del error y volver al diagnóstico antes de ampliar el fix.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | El adaptador envía un esquema sin restricciones numéricas no admitidas y convierte una respuesta válida en una asignación | unit, sin red | aprobado: rojo antes del fix, verde después |
| 2 | Una confianza menor que 0 o mayor que 1 se descarta localmente | unit existente | aprobado |
| 3 | Un proveedor que falla deja el mapeo manual disponible | unit existente | aprobado |
| 4 | En staging, un archivo nuevo recibe una propuesta automática sin 400 | manual | pendiente |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-12 | aprobado por Juan |
| 2 · Verificación | 2026-10-12 | aprobado por Juan: `ruff format --check .` (866 archivos), `ruff check .`, `mypy .` (861 archivos) en verde; `pytest -q -p no:cacheprovider --basetemp=backend/.pytest_tmp_codex`: 3270 passed, 655 skipped, 2 warnings preexistentes. `pytest backend/tests/contexts/spreadsheet_sync --cov=cheatsheet.contexts.spreadsheet_sync.infrastructure.modelo`: 133 passed, 90 % de cobertura del adaptador. Frontend sin cambios: lint y typecheck en verde, test:coverage termina con código 0; format:check falla en 499 archivos preexistentes. Falta validación manual en staging tras deploy. |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Juan pidió comenzar por el 400 de Anthropic de HU-E3-01; la lectura real de Google Sheets queda para otra unidad.
