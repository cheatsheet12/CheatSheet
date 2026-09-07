# Unidad: mapeo-asistido

**HUs**: HU-E3-01, HU-E3-02   **Contexto dueño**: spreadsheet_sync   **Rama**: feature/spreadsheet_sync-sincronizacion-de-planillas

## Qué hace

El sistema lee los encabezados de la planilla, propone a qué campo interno corresponde cada
columna y con cuánta confianza, y deja al usuario corregir y confirmar antes de que se
procese una sola fila. Es **el primer LLM del sistema**.

## Diseño

- **Dominio**: agregados `Mapeo` y `EntradaDeMapeo`. `NivelDeConfianza` con los tres valores
  de RN-01, y los umbrales en `Decimal` — se comparan por igualdad, y `0.75` no es `0.75` en
  punto flotante binario.
- **Aplicación**: `ProponerMapeo`, `CorregirMapeo`, `ConfirmarMapeo`, más `huella_de()`.
- **Puertos**: `PortRepositorioMapeo` y `PortModeloDeLenguaje` — el puerto que
  `docs/architecture.md` declaraba desde Etapa 5 y que nadie había implementado.
- **Frontend**: `RevisionDeMapeo` sobre PAN-ING-02, con las cuatro columnas que pide el
  primer criterio de HU-E3-02.

## Decisiones

**ADR-0007 elige el proveedor**, porque la decisión la hereda el épico 8 entero y no era de
esta unidad. Modelo `claude-opus-5`, salida estructurada contra un JSON Schema, timeout y
`max_tokens` explícitos, prompt en archivo versionado, y adaptador simulado rechazado en
producción.

**El modelo ve encabezados y nada más** (decisión D12). El ejemplo de dato que HU-E3-02
muestra en pantalla se lee de la planilla y se renderiza sin pasar por el modelo. Hay un
test que le pasa un CUIT y un teléfono reales al caso de uso y afirma que no aparecen en la
llamada: la regla es de una línea y se rompe sin que nada más falle.

**La respuesta se valida dos veces.** El esquema la restringe en la API; `_interpretar` la
vuelve a validar acá. No es redundancia: `CLAUDE.md` §5 dice que la salida de un modelo es
entrada no confiable, y tres cosas que el esquema no puede ver —que la columna sea una de
las que preguntamos, que el atributo exista, que el score parsee— son justo las que
convierten un error de una llamada en cuarenta mil filas mal escritas.

**Fallar es un estado diseñado.** Timeout, rechazo, respuesta malformada o falta de API key
degradan a «todas las columnas Sin asignar», que es el estado que RN-03 ya dibuja. La
ingesta nunca se bloquea por la caída de un proveedor.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Los tres niveles de confianza y sus umbrales exactos (RN-01) | unit | **OK** |
| 2 | Una columna de confianza baja queda `Sin asignar` (RN-03) | unit | **OK** |
| 3 | Una columna corregida a mano pasa a confianza Alta | unit | **OK** |
| 4 | No se confirma con una obligatoria sin asignar, con el texto de la HU (RN-02) | unit | **OK** |
| 5 | Un mapeo confirmado no se corrige en el lugar; va por `nueva_version` | unit | **OK** |
| 6 | La huella cambia con la estructura y no con el formato (RN-02) | unit | **OK** |
| 7 | **Al modelo sólo le llegan nombres de columnas** (D12) | unit | **OK** |
| 8 | Los ejemplos igual llegan a la pantalla | unit | **OK** |
| 9 | Un modelo caído deja todo sin asignar y no bloquea | unit | **OK** |
| 10 | Un mapeo guardado se reutiliza sin llamar al modelo (RN-02) | unit | **OK** |
| 11 | Un atributo inventado por el modelo se descarta, no se corrige | unit | **OK** |
| 12 | Una respuesta que no cumple el esquema no propone nada y no revienta | unit | **OK** |
| 13 | Una entrada malformada no se lleva puestas a las demás | unit | **OK** |
| 14 | Solo Lectura no corrige ni confirma; un Operador sí | unit | **OK** |
| 15 | Las cuatro columnas de la revisión se ven en pantalla | componente | **OK** |
| 16 | «Confirmar y procesar» deshabilitado con obligatorias faltantes | componente | **OK** |
| 17 | La pantalla avisa cuando el modelo no pudo proponer | componente | **OK** |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | al cierre del epico |

```
ruff format --check .   321 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 321 source files
pytest --cov            914 passed - 0 skipped - cobertura 95%  (umbral 80)
frontend lint           No ESLint warnings or errors
frontend typecheck      sin errores
frontend test:coverage  374 passed - 87.11 % lineas
frontend build          compila, /ingesta y sus 8 rutas BFF registradas
```

## Lo que aparecio al implementar y el plan no anticipaba

**El guard de arquitectura atajó un error real.** `Asignacion` había quedado definido en
`infrastructure/modelo.py` e importado desde `application/ports.py`, que es exactamente la
regla R2. Es un DTO de aplicación y ahora vive ahí; el adaptador lo importa del puerto. Sin
el guard hubiera pasado la revisión.

**`mypy` verifica la llamada al SDK de verdad**, porque `anthropic` viene tipado. Encontró
dos cosas: que `output_config` necesita la forma exacta del `TypedDict`, y que `esfuerzo`
tiene que ser un `Literal` y no un `str`. Se resolvió con un import bajo `TYPE_CHECKING`,
que tipa sin romper el import diferido del paquete.

**`CLAUDE.md` §5 no deja capturar `Exception` a secas**, y la primera versión lo hacía «por
si el SDK crece un error más». Se corrigió capturando la jerarquía tipada del propio SDK,
guardada al construir el adaptador. Lo que queda **sin** capturar es igual de deliberado: un
error nuestro —un keyword mal escrito, un prompt que no existe— sale como el 500 que es, en
vez de esconderse detrás de un mapeo vacío que parece una caída del proveedor.

## Lo que esta unidad deja abierto

**Una regresión en la calidad del mapeo es invisible para CI**, porque ningún test llama al
modelo real. Quien ajuste el prompt necesita un juego de encabezados de verdad y una
comparación manual. Está escrito en ADR-0007 y es problema del épico 8 antes que de nadie.
