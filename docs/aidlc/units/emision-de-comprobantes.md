# Unidad: emision-de-comprobantes

**HUs**: HU-E5-03, HU-E5-01, HU-E5-02   **Contexto dueño**: billing   **Rama**: feature/billing-facturacion-electronica

## Qué hace

Emite un comprobante fiscal contra ARCA y obtiene su CAE, lo lista y lo muestra. Es el
corazón del épico y la unidad más grande del sistema hasta acá: agregado `Comprobante` con
Single Table Inheritance (ADR-010), `ItemDeComprobante`, la máquina de estados
`BORRADOR → VALIDADO → ENVIADO_A_ARCA → AUTORIZADO / RECHAZADO`, el cliente de **WSFEv1**
(ADR-0008), la emisión asíncrona de RN-04, y las pantallas PAN-FAC-01, PAN-FAC-02 y
PAN-FAC-03.

Las tres historias van juntas por lo que dice el mapa: un listado de comprobantes que
todavía no se pueden emitir es una tabla vacía, y emitir sin poder ver el resultado no es
verificable.

## Las tres preguntas que el Gate 1 tenía que responder

### 1. ¿La emisión asíncrona usa `TareaAsincrona` (épico 4) o una tarea suelta?

**Usa `TareaAsincrona`.** Es exactamente lo que HS-T6 construyó para esto: una emisión que
agota sus reintentos tiene que quedar visible en la DLQ y no desaparecer en un log de
Celery. Y el estado del comprobante (`ENVIADO_A_ARCA`) es información de negocio, distinto
del estado de la tarea que lo empuja — los dos existen y no son el mismo.

### 2. ¿Qué hace el sistema si ARCA autoriza pero la respuesta se pierde? · **D17**

Es la peor falla posible y **ninguna historia la cubre**, así que se decide acá.

**Nunca se reintenta `FECAESolicitar` a ciegas.** Un reintento después de un resultado
desconocido es la forma exacta de emitir dos comprobantes por una venta, y el segundo
también lleva CAE. Antes de cualquier reintento se **reconcilia**:

1. El número ya fue sorteado y está guardado en nuestra fila, **dentro de la transacción**
   que lo sorteó (D14). Sabemos con qué número salimos aunque no sepamos qué pasó después.
2. Se pregunta a ARCA por ese comprobante con **`FECompConsultar(tipo, punto, numero)`**.
3. Si ARCA lo tiene → **fue autorizado**. Se guarda el CAE que ARCA devuelve. No se emite
   nada nuevo.
4. Si ARCA no lo tiene → **nunca se autorizó**. Recién ahí se reintenta, con el mismo
   número.

El número **no se devuelve al pool en una falla ambigua**. Un hueco en la numeración es una
observación de la AFIP; dos comprobantes con el mismo número es un problema de otro orden.
Sólo un rechazo explícito de ARCA —que es una respuesta, no una incógnita— libera el número
con `devolver_numero()`.

El estado `ENVIADO_A_ARCA` es lo que hace posible todo esto: se persiste **antes** de mandar
el sobre, en su propia transacción. Un comprobante en ese estado significa «no sabemos», y
la reconciliación es lo que lo saca de ahí.

### 3. ¿Quién valida los montos antes de mandarlos? (heredada de D13)

El dominio, y antes de que exista un sobre. `Comprobante.validar()` exige al menos un ítem,
precios mayores a cero, y que `subtotal + total_iva == total` — cierto por construcción
gracias a D15 (redondeo por ítem) y verificado igual, porque ARCA lo rechaza con un código
que no dice que faltó un centavo. Un comprobante que no valida no llega a `VALIDADO` y por
lo tanto no llega al sobre.

## Diseño

- **Dominio**: `Comprobante` (agregado), `ItemDeComprobante`, `Receptor` (VO desnormalizado),
  `CAE` (VO), `EstadoComprobante` con su tabla de transiciones legales, `AlicuotaIVA` propia
  de `billing` **con el `codigo_arca`** que WSFEv1 pide (3 = 0 %, 4 = 10,5 %, 5 = 21 %), y
  `TIPOS_VALIDOS`: la tabla emisor × receptor → tipos permitidos (D16).
- **Aplicación**: `EmitirComprobante` (valida, sortea el número, persiste y encola),
  `AutorizarComprobante` (el lado del worker: habla con ARCA y resuelve el estado),
  `ReconciliarComprobante` (D17), `ListarComprobantes` y `VerComprobante`.
- **Puertos**: `PortRepositorioComprobante`, `PortAutorizacionDeArca`
  (`FECAESolicitar` + `FECompConsultar`), `PortValidacionDeReceptor` (el padrón, vía el
  servicio de aplicación de `integrations`).
- **Otros contextos**: `integrations` (ticket y padrón) y `master_data` (el cliente receptor),
  los dos por servicio de aplicación. `reference_data` para el parámetro vigente a la fecha.
- **Frontend**: PAN-FAC-01 (listado con filtros), PAN-FAC-02 (detalle con CAE y PDF),
  PAN-FAC-03 (nueva emisión).

## Infraestructura

- **Migraciones**: `0018_comprobante`. Las dos tablas del DER —`comprobante` e
  `item_de_comprobante`— con RLS en la primera, **sin `DELETE`** en ninguna, índice único
  `(punto_de_venta_id, tipo, numero)` y los cuatro montos en `NUMERIC`.
- **Trabajo asíncrono**: `billing.autorizar_comprobante`, en su propia cola. Registrada en
  Beat sólo para el barrido de reconciliación de D17.
- **Integraciones externas**: WSFEv1 `FECAESolicitar` y `FECompConsultar`.

## Decisiones nuevas de esta unidad

**D17 — reconciliar antes de reintentar.** Ver arriba. Es la decisión más importante del
épico después de D14, y las dos protegen lo mismo desde lados distintos: D14 impide que dos
emisiones simultáneas saquen el mismo número; D17 impide que una emisión ambigua se
convierta en dos comprobantes.

**El ticket deja de viajar como blob opaco fuera de `integrations`.** `empaquetar` y
`desempaquetar` vivían en `infrastructure/arca/wsaa.py`, y `billing` no puede importar de
ahí (R3). Se mueven a `integrations/application/`, que es donde vive el contrato del Open
Host Service. Los dos importadores que tenían —`adaptadores.py` y `padron.py`— se
actualizaron en vez de dejar un reexport en `wsaa.py`: son dos, y un reexport habría dejado
dos lugares donde buscar el formato en vez de uno.

**`HabilitacionEnArca` y `CatalogosDeWsfe` dejan de recibir un dict de credenciales** y
reciben un resolutor. Es la pieza que las dos unidades anteriores dejaron anotada como
pendiente, y es esta la que la necesita de verdad.

## Decisiones que aparecieron implementando y el plan no anticipaba

**D18 - ARCA es la autoridad de la correlatividad; nuestro contador es un cache.** WSFEv1
exige numeracion estrictamente correlativa por `(punto, tipo)` y rechaza cualquier otra cosa
hasta que los dos contadores coincidan. Un hueco entonces no es un detalle cosmetico: **es
una caida de la facturacion**. Y los huecos pasan por razones que el agregado no puede
evitar -- un comprobante rechazado despues de que uno posterior ya saco su numero, una fila
restaurada de un backup, un punto usado desde otro lado.

El numero que se saca es `max(el nuestro, FECompUltimoAutorizado) + 1`, preguntado dentro
del candado del punto de venta. `devolver_numero` paso a informar si pudo en vez de romper:
un comprobante rechazado es el resultado normal de preguntarle a ARCA, no una condicion de
error del punto de venta, y el hueco que puede dejar lo cierra la sincronizacion siguiente.

**El almacenamiento de objetos se promovio a `platform/`.** El PDF se cachea en R2, que
vivia en `spreadsheet_sync/infrastructure/` y que R3 pone fuera del alcance de `billing`. Es
el tercer ascenso del epico, despues de `soap.py` y `wsfe.py`, y por la misma razon: la
alternativa era una segunda copia de un adaptador. **Los puertos no se movieron** -- un
puerto es el contrato del consumidor, y cada contexto declara el suyo; lo que se comparte es
el adaptador y su fabrica, que ademas **tiene** que ser una sola: dos instancias del doble en
memoria serian dos buckets distintos.

**El adaptador de R2 filtraba excepciones de `botocore`.** Se noto al escribir el cache del
PDF: para ese llamador «no esta» y «R2 no contesta» significan lo mismo -- regenerar --, pero
atraparlas sin tiparlas habria exigido un `except Exception`, que `CLAUDE.md` seccion 5
prohibe. Ahora `leer` traduce a `FileNotFoundError` y `AlmacenamientoNoDisponible`, que es
donde correspondia desde el principio: el otro consumidor **si** las distingue.

## Riesgos que obligan a tests

- [x] **Toca dinero** — los cuatro montos del comprobante
- [x] **Toca comprobantes fiscales / CAE** — es *el* caso
- [ ] Consume un webhook — no
- [x] **Agrega datos con `empresa_id`** — RLS en `comprobante`
- [ ] Usa salida de un LLM — no
- [x] **Datos personales o fiscales** — el receptor: CUIT, razón social, domicilio

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico; D17 decidida acá |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | al cierre del epico |

```
ruff format --check .   393 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 393 source files
guard_architecture      418 file(s) checked - architecture boundaries intact
pytest --cov            1109 passed - 0 skipped - cobertura 93%  (umbral 80)
alembic current         0018 (head)
tsc --noEmit            sin errores
eslint . --max-warnings=0   limpio
vitest run --coverage   461 passed - cobertura sobre el umbral
```

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | El subtotal de un item se redondea a dos decimales (D15) | unit | **OK** |
| 2 | El IVA se calcula sobre el subtotal **ya redondeado** | unit | **OK** |
| 3 | Los totales cierran contra la suma de items | unit | **OK** |
| 4 | Las alicuotas llevan los codigos reales de ARCA (3, 4, 5) | unit | **OK** |
| 5 | `redondear` usa HALF_UP y no el del banquero | unit | **OK** |
| 6 | La tabla de tipos es la del regimen (RN-01, D16) | unit | **OK** |
| 7 | Un consumidor final no puede emitir | unit | **OK** |
| 8 | **`AUTORIZADO` es terminal: no se pisa un CAE con otro** | unit | **OK** |
| 9 | Un comprobante en vuelo no se puede modificar | unit | **OK** |
| 10 | Un rechazado se puede corregir y volver a emitir | unit | **OK** |
| 11 | Un CUIT invalido no consulta a ARCA | unit | **OK** |
| 12 | Un CUIT dado de baja no es lo mismo que uno inexistente | unit | **OK** |
| 13 | Sin condicion de IVA no se adivina | unit | **OK** |
| 14 | Emitir deja el comprobante en vuelo y lo encola | unit | **OK** |
| 15 | **Emitir pregunta a ARCA donde va la numeracion (D18)** | unit | **OK** |
| 16 | Solo Lectura no emite | unit | **OK** |
| 17 | Un rechazo guarda las palabras de ARCA y libera el numero | unit | **OK** |
| 18 | Una tarea reentregada no reenvia un comprobante ya resuelto | unit | **OK** |
| 19 | **ARCA caida deja el comprobante donde estaba y no libera el numero** | unit | **OK** |
| 20 | **Si ARCA lo tiene registrado se guarda ese CAE y no se emite de nuevo (D17)** | unit | **OK** |
| 21 | Si ARCA no lo tiene, el comprobante se puede volver a emitir | unit | **OK** |
| 22 | Si tampoco se puede preguntar, no se toca nada | unit | **OK** |
| 23 | Un comprobante recien enviado no se reconcilia | unit | **OK** |
| 24 | Reconciliar dos veces no pisa el CAE | unit | **OK** |
| 25 | Un comprobante sobrevive entero a la ida y vuelta, con `Decimal` | integracion | **OK** |
| 26 | Editar un borrador reescribe sus items sin dejar huerfanos | integracion | **OK** |
| 27 | Dos comprobantes con el mismo numero y tipo se rechazan | integracion | **OK** |
| 28 | El mismo numero en dos tipos distintos convive (RN-02) | integracion | **OK** |
| 29 | Dos borradores sin numero no son un duplicado | integracion | **OK** |
| 30 | Una empresa no ve los comprobantes de otra, ni sus items | integracion | **OK** |
| 31 | No se puede borrar un comprobante | integracion | **OK** |
| 32 | Un CAE sin estado autorizado lo rechaza el esquema | integracion | **OK** |
| 33 | Una factura no puede tener comprobante de origen | integracion | **OK** |
| 34 | El barrido ve las empresas con algo en vuelo y nada mas | integracion | **OK** |
| 35 | El listado ordena por fecha descendente, borradores al final | integracion | **OK** |
| 36 | Los filtros de la historia funcionan juntos | integracion | **OK** |
| 37 | La entrada de Beat de la reconciliacion existe | unit | **OK** |
| 38 | Lo que sale del renderizador es un PDF | unit | **OK** |
| 39 | El encabezado lleva el numero como lo imprime ARCA | unit | **OK** |
| 40 | El pie dice que el papel no es el comprobante fiscal | unit | **OK** |
| 41 | **Un fallo de lectura de la cache regenera en vez de romper** | unit | **OK** |
| 42 | Un comprobante sin autorizar no es descargable | unit | **OK** |
| 43 | PAN-FAC-01 muestra las seis columnas y filtra contra el servidor | frontend | **OK** |
| 44 | PAN-FAC-02 muestra CAE, vencimiento y las palabras de ARCA | frontend | **OK** |
| 45 | **PAN-FAC-02 avisa que no se vuelva a emitir uno en vuelo** | frontend | **OK** |
| 46 | PAN-FAC-02 no ofrece editar nada (RN-01) | frontend | **OK** |
| 47 | PAN-FAC-03 no ofrece nada hasta que el CUIT se valida | frontend | **OK** |
| 48 | PAN-FAC-03 solo ofrece los tipos legales (RN-01) | frontend | **OK** |
| 49 | Sin items el boton Emitir queda deshabilitado y se dice por que | frontend | **OK** |
| 50 | Los montos cruzan como texto en el cliente y en el BFF | frontend | **OK** |
| 51 | El BFF no llega al backend sin sesion, y el PDF tampoco | frontend | **OK** |

## Lo que esta unidad deja abierto

**El `saldo_pendiente` se registra y no lo consume nadie** (HU-E5-03 RN-06). Es del epico 6,
y esta dicho en el mapa: aca se guarda igual al total y nada lo mueve.

**`turno_id` se crea y nadie lo escribe** (RN-05). Quien produce un turno llega en el epico
7. La columna existe, sin FK, por el hallazgo H4 del DER.

**La emision no valida contra `parametro_fiscal`.** El catalogo se sincroniza desde la
unidad 1 y la tabla de tipos vive en el dominio por D16, asi que hoy no se consulta. Lo que
si haria falta consultarlo es el Libro IVA del epico 9, que necesita la alicuota **vigente
el dia de emision** -- y para eso la unidad 1 dejo `ParametroVigenteA(fecha)`.
