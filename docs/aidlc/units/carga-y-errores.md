# Unidad: carga-y-errores

**HUs**: HU-E3-03, HU-E3-05, HU-E3-06   **Contexto dueño**: spreadsheet_sync   **Rama**: feature/spreadsheet_sync-sincronizacion-de-planillas

## Qué hace

Lee la planilla, aplica el mapeo confirmado a cada fila, escribe `Cliente` y `Servicio` en
`master_data` con `origen = PLANILLA`, y cuenta todo. Las filas que fallan quedan
registradas con el número de fila del archivo original y no frenan al resto. Pantalla
PAN-ING-03 con el resumen, el detalle por fila, la descarga del listado y el reproceso.

## La regla que define la unidad

HU-E3-03 RN-02: **una fila inválida se marca y no aborta el procesamiento del resto.**
Cuarenta mil filas y un CUIT mal formado tienen que dar 39.999 clientes y una línea que
dice cuál falló. Todo el diseño existe para sostener eso: `_procesar_fila` captura
`ErrorDeDominio` y lo convierte en un `ErrorDeFila`; cualquier otra excepción es un bug
nuestro y se deja propagar, porque una fila que se traga un `TypeError` se contaría como un
error que el usuario no puede corregir.

## Decisiones

**La escritura va por un servicio de aplicación de `master_data`, no por sus
repositorios.** La regla R3 lo exige y el Context Map declara el arco. `ingesta.py` vive en
`master_data` y no en el contexto que lo llama: este pide en sus propias palabras, aquel
decide qué significa para un `Cliente`.

**No es `RegistrarCliente` con un parámetro.** Ese caso de uso **es** el panel: fija
`origen = PANEL`, consulta el padrón de ARCA en cada escritura y rechaza un CUIT duplicado.
Los tres están mal acá — cuarenta mil filas serían cuarenta mil llamadas a ARCA, y un CUIT
repetido es una actualización porque la planilla es la fuente de verdad (ADR-006).

**`CON_ERRORES` es un cuarto estado que el DER no tiene.** El DER cierra el enum en
`EN_CURSO`, `COMPLETADO` y `FALLIDO`; HU-E3-03 describe una corrida que terminó, llenó el
catálogo y dejó filas atrás. Colapsarlo en `FALLIDO` haría que «se procesaron 39.999 de
40.000» parezca una importación fallida.

**El reproceso lee sólo las filas que fallaron.** Eso es todo lo que hace falta para el «no
duplica las filas ya procesadas» de HU-E3-06 RN-02, y evita tener que inventar una
identidad de fila.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Una fila inválida no aborta el resto, y queda su número original (RN-02) | unit | **OK** |
| 2 | Sin errores el estado es `COMPLETADO`; con errores, `CON_ERRORES` | unit | **OK** |
| 3 | Veinte filas, diez rotas: entran las diez buenas | unit | **OK** |
| 4 | Un archivo ilegible es `FALLIDO`, que no es lo mismo que `CON_ERRORES` | unit | **OK** |
| 5 | No se procesa sin un mapeo confirmado (precondición de RN-01) | unit | **OK** |
| 6 | Las columnas `Sin asignar` no llegan al catálogo | unit | **OK** |
| 7 | El reproceso lee sólo las filas indicadas (HU-E3-06 RN-02) | unit | **OK** |
| 8 | Solo Lectura no reprocesa (HU-E3-05 RN-04) | unit | **OK** |
| 9 | No se reprocesa lo que no dejó errores | unit | **OK** |
| 10 | La fila 2 del archivo es la primera de datos (HU-E3-05 RN-02) | unit | **OK** |
| 11 | Un CSV exportado de Excel en español (con BOM) se lee igual | unit | **OK** |
| 12 | Las filas vacías no se cuentan | unit | **OK** |
| 13 | `1.234,50` es mil doscientos treinta y cuatro con cincuenta | unit | **OK** |
| 14 | `21`, `21%`, `0.21` y `10,5` se leen como alícuotas | unit | **OK** |
| 15 | Un CUIT repetido actualiza en vez de rechazar (ADR-006) | unit | **OK** |
| 16 | Un cliente ingerido nace con `origen = PLANILLA` | unit | **OK** |
| 17 | El resumen, las filas fallidas y la descarga se ven en PAN-ING-03 | componente | **OK** |
| 18 | El CSV de errores escapa las comillas de un motivo | unit (vitest) | **OK** |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | al cierre del epico |

```
ruff format --check .   331 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 331 source files
pytest --cov            956 passed - 0 skipped - cobertura 95%  (umbral 80)
frontend lint           No ESLint warnings or errors
frontend typecheck      sin errores
frontend test:coverage  386 passed - 85.84 % lineas
frontend build          compila, /ingesta/[cargaId] y 11 rutas BFF registradas
```

## Lo que aparecio al implementar y el plan no anticipaba

**`PortRepositorioServicio` no tiene `buscar_por_nombre`, a proposito.** Su docstring dice
por que: dos sucursales pueden vender el mismo «Corte», asi que los servicios no tienen
regla de unicidad. La ingesta por lo tanto **siempre crea** un servicio y nunca empareja uno
existente. Agregar la busqueda hubiera dado vuelta una decision del epico 3 desde adentro
del contexto que la consume. La consecuencia queda dicha en el codigo: **correr una carga
inicial completa dos veces duplica todos los servicios**. Ninguna historia pide evitarlo —el
reproceso solo vuelve sobre lo que fallo y la sincronizacion incremental solo lee lo que
cambio— pero es una decision sobre identidad de servicio que alguien va a tener que tomar
con `master_data` el dia que importe.

**El guard de arquitectura volvio a atajar la misma clase de error**, esta vez con
`PlanillaLeida`: estaba definido junto al lector y lo importaba el puerto, incluso bajo
`TYPE_CHECKING`. Es un DTO de aplicacion y ahora vive en `ports.py`. Van dos en este epico.

**El techo de complejidad partio el router en tres.** `_rutas_de_procesamiento` llego a 11 y
el limite es 10. La division que significa algo aca es entre lo que **encola trabajo** (202)
y lo que **lee un resultado**, y el reproceso hace las dos cosas, asi que quedo solo.
