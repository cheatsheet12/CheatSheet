# Unidad: correccion-de-filas-con-error

**HUs**: HU-E3-05, HU-E3-06 **Contexto dueño**: spreadsheet_sync **Rama**: feature/spreadsheet_sync-correccion-de-filas

> Origen: pedido directo del dueño del producto durante la verificación de la pantalla de ingesta
> («no me deja corregir»). La rama sale de `feature/frontend-logo-de-marca`, que trae el rediseño del
> detalle de la carga sobre el que se apoya la pantalla; su PR apunta a esa rama y pasa a `develop`
> cuando aquella se mergea.

## Qué hace

Hoy el detalle de una carga lista las filas que fallaron con su motivo y ofrece **reprocesar**: el
usuario tiene que ir a su planilla, corregir el dato y volver. HU-E3-06 se pensó así, pero en la
práctica quien ve «El dígito verificador del CUIT no es correcto» quiere arreglarlo ahí mismo.

Esta unidad agrega la **corrección en el sistema**: en cada fila con error, un botón «Corregir» abre
un panel con los valores de esa fila —leídos del archivo ya subido y mapeados a los campos del
sistema— editables. Al guardar se valida con las mismas reglas del alta; si pasa, la fila se importa,
el error queda **corregido** y los contadores se actualizan. Si no pasa, el motivo se muestra en el
mismo panel y no se cambia nada.

**Fuera de esta unidad:** escribir la corrección de vuelta en la planilla de origen (sigue siendo del
write-back de HU-E3-07), corregir filas de planillas de Google (esta unidad solo lee archivos
subidos), y ampliar la ingesta a otros datos además de clientes y servicios.

## Decisiones

### 1. El error no se borra: se marca corregido

`PortRepositorioProcesamiento` dice «no `eliminar`» a propósito: el procesamiento es el registro de
un import que ya escribió en `master_data`. Borrar el error de una fila corregida borraría la
historia de que falló. Se agrega a `error_de_fila` una columna **`corregida_en`** (`timestamptz`,
nullable); un error con valor ahí es historia y no cuenta como pendiente.

**Migración 0035**, reversible, sin backfill (todos los errores existentes quedan pendientes). El
`GRANT UPDATE` de `error_de_fila` ya existe desde 0014, así que no hay política nueva.
**Renumerada** de 0033 a 0035 al integrar con `develop`.

### 2. Los contadores

Corregir una fila hace `filas_error -= 1` y `filas_ok += 1`; `filas_totales` no cambia. Si ya no
quedan errores pendientes y el estado era `CON_ERRORES`, pasa a `COMPLETADO`. Los contadores nunca se
tocan directamente: los mueve `ProcesamientoDePlanilla.corregir_fila`, por la misma razón que `cerrar`
no recibe el estado (el contador decide el final).

### 3. Qué se le muestra y qué se puede editar

Los valores salen **del archivo, no de la base**: el sistema nunca guardó la fila (solo su número y el
motivo). Se lee el archivo guardado (`referencia_archivo`), se toma la fila por número y se le aplica
el **mapeo del procesamiento** (`mapeo_id`), así que lo editable son los campos del sistema (Nombre,
CUIT, Condición de IVA…) y no las columnas crudas. Las columnas «Sin asignar» no se muestran: el
usuario decidió que no van.

Un procesamiento sin `referencia_archivo` (planilla de Google) responde 422 con un motivo claro.

### 4. La validación es la del alta

Se ingiere por el mismo `PortIngestaDeCatalogo` que usa el procesamiento (`master_data` decide qué es
un `Cliente`), **no se duplica ninguna regla** en esta unidad. Un `ErrorDeDominio` sale como 422 con
su mensaje, que es lo que la pantalla muestra. Como la unidad de trabajo descarta la transacción si el
cuerpo levanta, una corrección rechazada no deja nada escrito.

### 5. Permisos, auditoría, reproceso

- **Solo Lectura no corrige** (HU-E3-05 RN-04), validado en el caso de uso y no solo en el router.
- Acción de bitácora propia: `corregir_fila_de_carga`, con `ProcesamientoDePlanilla:<id>` como
  entidad. **Nunca los valores**: son CUIT y teléfonos.
- `filas_a_reprocesar` pasa a contar **solo los errores pendientes**: reprocesar no vuelve a leer una
  fila ya corregida.

## Diseño

### Dominio — `contexts/spreadsheet_sync/domain/procesamiento.py`
- `ErrorDeFila.corregida_en: datetime | None = None` y la propiedad `pendiente`.
- `ProcesamientoDePlanilla.corregir_fila(numero_fila, ahora)`: exige un procesamiento terminado y un
  error pendiente con ese número; marca el error, mueve los contadores, cierra el estado.
- `filas_a_reprocesar` filtra los pendientes. `errores_pendientes` como propiedad.

### Aplicación — `contexts/spreadsheet_sync/application/correcciones.py` (nuevo)
- `LeerFilaConError`: `ejecutar(procesamiento_id, numero_fila)` → `VistaDeFilaConError` (número,
  motivo y los campos con su valor actual).
- `CorregirFila`: `ejecutar(empresa_id, usuario_id, rol, procesamiento_id, numero_fila, valores, ahora)`.
  Valida que las claves sean atributos conocidos, descarta los vacíos y exige al menos uno.

### Infraestructura
- `models.py` y `repositories.py`: la columna y el `actualizar` que ahora también persiste
  `corregida_en` de los errores ya guardados.
- Migración `0035_correccion_de_fila_con_error.py`.

### API — `api/routers/planillas.py`
- `GET /planillas/cargas/{id}/filas/{numero}` → la vista para editar.
- `POST /planillas/cargas/{id}/filas/{numero}/correccion` con `{"valores": {...}}` → 200 con el
  detalle actualizado de la carga.
- `ErrorDeFilaSalida` suma `corregida: bool`; `puede_reprocesar` mira los pendientes.

### Frontend
- BFF `app/api/planillas/cargas/[cargaId]/filas/[numeroFila]/route.ts` (GET y POST), sobre
  `reenviarAlBackend`.
- `DetalleDeCarga`: botón «Corregir» por fila pendiente, fila corregida con su marca, y un panel
  (`Modal`) con los campos editables, el motivo del error y el mensaje de rechazo.

## Pruebas

- **Dominio:** corregir mueve los contadores y cierra el estado; no se corrige dos veces; no se
  corrige una fila sin error; `filas_a_reprocesar` excluye lo corregido.
- **Aplicación:** lee la fila mapeada del archivo; rechaza un procesamiento sin archivo; la corrección
  válida ingiere y marca; la inválida deja todo igual y propaga el motivo; Solo Lectura no corrige;
  un atributo desconocido se rechaza; nunca se auditan los valores.
- **Integración (PostgreSQL):** la columna persiste y la RLS sigue aislando por empresa.
- **Frontend:** el panel carga la fila, envía los valores editados, muestra el rechazo sin cerrarse y
  actualiza el detalle al corregir; el BFF reenvía y no filtra más de lo debido.
- **Verificación hacia atrás:** sin el `corregida_en` en `filas_a_reprocesar`, el test de reproceso
  falla.

## Estado

Plan aprobado por el dueño del producto en el chat («claro si, tiene que funcionar, hacelo»).
