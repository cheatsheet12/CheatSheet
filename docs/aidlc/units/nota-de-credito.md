# Unidad: nota-de-credito

**HUs**: HU-E5-04   **Contexto dueño**: billing   **Rama**: feature/billing-facturacion-electronica

## Qué hace

Anula un comprobante autorizado, total o parcialmente, emitiendo una nota de crédito contra
él. Pantalla PAN-FAC-04.

Reusa entera la máquina de emisión de la unidad anterior: **una nota de crédito *es* un
comprobante**, con otro tipo y una referencia. Lo que agrega es el vínculo obligatorio con
el original (RN-01), el tipo determinado por el del original (RN-02), el tope de monto
(RN-03) y el estado de anulación que el original refleja (RN-05).

Se separó de `emision-de-comprobantes` no por tamaño sino **por riesgo**: es la única
operación del sistema que puede reversar plata ya documentada ante ARCA, y merece su propio
gate en lugar de entrar como el último tercio de un PR que ya trae tres pantallas.

## La pregunta que el Gate 1 tenía que responder · **D19**

> ¿El «estado de anulación» de RN-05 es un estado del original, una suma de notas
> asociadas, o las dos cosas?

**Las dos, y la suma es la verdad.**

- **Lo anulado se calcula sumando las notas de crédito autorizadas** contra el original. Es
  un hecho derivado y no una columna: una columna sería una segunda copia de algo que ya
  está en las filas, y las dos copias se separan el día que una nota se autoriza y la
  actualización de la columna falla.
- **`ANULADO` es un estado del original y sólo aparece en la anulación total.** El enum del
  DER lo tiene y la máquina ya permite `AUTORIZADO → ANULADO`, así que se usa para lo que
  sirve: que el listado de PAN-FAC-01 pueda filtrar sin sumar nada, y que la emisión se
  niegue a anular de nuevo algo que ya está anulado del todo.
- **La anulación parcial no es un estado.** Es un monto, y el original sigue `AUTORIZADO`
  porque eso es lo que es: un comprobante vigente por su saldo.

Dicho de otro modo: la columna es un caché de una pregunta que se puede hacer siempre, y
está permitido perderla —recalcularla es una consulta—. Lo contrario, tener sólo la columna,
no se puede recalcular.

**El monto anulado no toca `saldo_pendiente`.** Ese atributo es de cobros (HU-E5-03 RN-06,
épico 6) y significa otra cosa: cuánto falta que le paguen a la empresa. Una nota de crédito
reduce lo facturado, no lo cobrado, y mezclarlos haría que una devolución se lea como un
pago.

## Diseño

- **Dominio**: sin agregado nuevo. `Comprobante.anular()` ya existía; se agrega
  `nota_de_credito_para(original, ...)`, la fábrica que construye la nota con el tipo que
  determina el original (RN-02) y su receptor copiado.
- **Aplicación**: `EmitirNotaDeCredito` —valida RN-01 y RN-03 y delega en `EmitirComprobante`
  para todo lo demás— y `EstadoDeAnulacion`, la consulta derivada.
- **Puertos**: `PortRepositorioComprobante.notas_de(origen_id)`.
- **Frontend**: PAN-FAC-04, más el botón «Anular» en el detalle de un comprobante autorizado.

## Riesgos que obligan a tests

- [x] **Toca dinero** — reversa importes ya documentados
- [x] **Toca comprobantes fiscales / CAE** — la nota también lleva CAE y también es irreversible
- [ ] Consume un webhook — no
- [x] **Agrega datos con `empresa_id`** — misma tabla, mismo RLS
- [ ] Usa salida de un LLM — no
- [x] **Datos personales o fiscales** — el receptor, copiado del original

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico; D19 decidida acá |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | al cierre del epico |

```
ruff format --check .   396 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 396 source files
guard_architecture      424 file(s) checked - architecture boundaries intact
pytest --cov            1133 passed - 0 skipped - cobertura 94%  (umbral 80)
alembic current         0018 (head)
tsc --noEmit            sin errores
eslint . --max-warnings=0   limpio
vitest run --coverage   473 passed - cobertura sobre el umbral
```

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | La nota hereda el tipo y el receptor del original (RN-01, RN-02) | unit | **OK** |
| 2 | Sin comprobante de referencia usa el texto de la historia | unit | **OK** |
| 3 | Solo se anula un comprobante **autorizado** | unit | **OK** |
| 4 | Una nota de credito no se anula con otra | unit | **OK** |
| 5 | Un monto mayor al original se rechaza con el texto de la historia (RN-03) | unit | **OK** |
| 6 | **Dos notas parciales son legitimas y la tercera no** | unit | **OK** |
| 7 | **Una nota rechazada no consume el cupo (D19)** | unit | **OK** |
| 8 | Una nota en vuelo tampoco reversa todavia | unit | **OK** |
| 9 | Una anulacion total deja el original `ANULADO` (RN-05) | unit | **OK** |
| 10 | **Una anulacion parcial no cambia el estado del original** | unit | **OK** |
| 11 | Reflejar la anulacion dos veces no rompe | unit | **OK** |
| 12 | Un comprobante comun no dispara ninguna anulacion | unit | **OK** |
| 13 | La nota aparece en el listado como cualquier comprobante | unit | **OK** |
| 14 | `notas_de` solo devuelve las del original pedido | unit | **OK** |
| 15 | El tipo de la nota lo determina la letra del original | unit | **OK** |
| 16 | **La nota lleva su propia serie en el mismo punto** | integracion | **OK** |
| 17 | Dos notas del mismo tipo no pueden repetir numero | integracion | **OK** |
| 18 | El estado de anulacion suma solo las autorizadas | integracion | **OK** |
| 19 | Una anulacion total persiste, y el CAE del original sigue ahi | integracion | **OK** |
| 20 | Una empresa no ve las notas de otra | integracion | **OK** |
| 21 | Una factura no puede apuntar a un origen | integracion | **OK** |
| 22 | PAN-FAC-04 precarga items, receptor y tope | frontend | **OK** |
| 23 | **PAN-FAC-04 no deja elegir el tipo (RN-02)** | frontend | **OK** |
| 24 | El tope se explica y bloquea, y bajando la cantidad se habilita | frontend | **OK** |
| 25 | Uno ya anulado del todo no ofrece formulario | frontend | **OK** |
| 26 | Solo viajan los items, con los montos como texto | frontend | **OK** |
| 27 | El detalle dice la anulacion parcial y el comprobante sigue autorizado | frontend | **OK** |
| 28 | El boton de anular aparece solo para quien puede | frontend | **OK** |

## Lo que aparecio al implementar y el plan no anticipaba

**Nada estructural, y eso es el resultado.** Era la prueba de si la unidad anterior habia
quedado bien: si emitir una nota de credito hubiera necesitado un segundo camino de emision,
D14, D17 y D18 tendrian dos implementaciones cada una. No hizo falta -- `EmitirNotaDeCredito`
delega en `EmitirComprobante` y agrega tres reglas.

La unica llamada de vuelta es `reflejar_anulacion`, que `_aplicar_respuesta` invoca cuando el
comprobante que acaba de autorizarse resulta ser una nota. Se importa dentro de la funcion
porque el modulo de notas importa `EmitirComprobante` del de emision, y nombrarlo arriba
cerraria el ciclo. La direccion de la dependencia es la correcta -- las notas se construyen
sobre la emision, no al reves -- y esa es la unica excepcion.

## Lo que esta unidad deja abierto

**El `saldo_pendiente` sigue sin moverse.** Una nota de credito reduce lo facturado, no lo
cobrado, y ese atributo es de cobros (epico 6). Mezclarlos haria que una devolucion se lea
como un pago.

**No hay reimpresion de la nota junto al original.** El PDF de cada uno se descarga por
separado, que es lo que la historia pide. Un documento que muestre los dos juntos es
reporteria, y eso es el epico 9.
