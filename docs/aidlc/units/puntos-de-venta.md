# Unidad: puntos-de-venta

**HUs**: HU-E5-05   **Contexto dueño**: billing   **Rama**: feature/billing-facturacion-electronica

## Qué hace

Da de alta y administra los puntos de venta desde los que la empresa factura: número,
descripción, estado, y —lo que de verdad importa— **la numeración por tipo de comprobante**.
Verifica contra ARCA que el punto esté habilitado antes de poder usarlo (RN-03), impide dos
puntos con el mismo número en una empresa, y desactiva sin borrar (RN-04). Pantalla
PAN-FAC-05.

Trae además los cimientos de `billing` que ninguna unidad posterior va a volver a decidir:
el repositorio con RLS, la primera migración del contexto y la feature `billing` del
frontend.

Va antes de la emisión porque **un comprobante se emite desde un punto de venta**, y su
número sale de acá. Empezar por la emisión sería empezar por el paso que necesita este.

## Diseño

- **Dominio**: agregado `PuntoDeVenta`, con `TipoComprobante` cerrado en los seis del DER y
  su `codigo_arca` (1, 3, 6, 8, 11, 13 — los códigos reales de WSFEv1, no un enum nuestro
  que después haya que traducir en el borde). Los dos invariantes que viven acá:
  **un punto inactivo no numera** y **la numeración es por `(punto, tipo)`**, nunca global.
- **Aplicación**: `ListarPuntosDeVenta`, `RegistrarPuntoDeVenta` y
  `CambiarEstadoDePuntoDeVenta`. Las tres verifican el rol; las dos que escriben exigen
  Administrador.
- **Puertos y adaptadores**: `PortRepositorioPuntoDeVenta` —con `tomar_para_emitir`, que es
  el método que `emision-de-comprobantes` va a usar y la razón de la decisión D14— y
  `PortHabilitacionDeArca` (`FEParamGetPtosVenta`, real y simulado).
- **Otros contextos**: `integrations` es OHS y se llega por servicio de aplicación.
  `reference_data` todavía no se consume acá: la validación contra el catálogo es de la
  emisión, no del alta de un punto.
- **Frontend**: `features/billing` completa —`api/puntoDeVenta.ts`, `components/PuntosDeVenta.tsx`,
  `index.ts`—, BFF `/api/puntos-de-venta`, página bajo `(panel)/facturacion/` y entrada de menú.

## Infraestructura

- **Migraciones**: `0017_punto_de_venta`. La tabla del DER sin cambios, con RLS, índice
  único `(empresa_id, numero)` y `CHECK numero BETWEEN 1 AND 99999`. **Sin `DELETE`** en el
  `GRANT`.
- **Trabajo asíncrono**: ninguno. Un alta de punto de venta es sincrónica: el usuario espera
  la respuesta de ARCA porque de eso depende si el punto queda usable.
- **Configuración**: nada nuevo. Reusa `ARCA_WSFE_URL_*` de `parametros-fiscales`.
- **Integraciones externas**: WSFEv1 `FEParamGetPtosVenta`, con timeout, reintentos y manejo
  de falla, por el mismo `platform/soap.py` que promovió la unidad anterior.

## Decisiones

**D14 — la numeración se serializa en el motor, no en el proceso.** `tomar_para_emitir` hace
`SELECT … FOR UPDATE` sobre la fila del punto, y el número sale dentro de esa transacción.
Es el mismo mecanismo que el épico 1 usó para «siempre al menos un Administrador», y acá hay
más en juego: dos comprobantes autorizados con el mismo número se arreglan con la AFIP, no
con un `UPDATE`.

`with_for_update()` y **no** `nowait`: la segunda emisión debe *esperar*, no fallar. Esperar
es lento y correcto; fallar empuja el reintento al llamador, y un reintento que vuelve a leer
el contador es la carrera otra vez.

**«ARCA dice que no» y «no pudimos preguntarle a ARCA» son dos errores distintos**
(`PuntoDeVentaNoHabilitado` vs. `ArcaNoDisponible`). Colapsarlos tiene dos formas de salir
mal, y las dos malas: bloquear un punto legítimo durante una caída, o activar uno que ARCA
nunca habilitó. Lo segundo se descubre cuando rechazan la primera factura, con un código de
error que habla de otra cosa.

**Reactivar vuelve a preguntarle a ARCA.** Un punto puede quedar bloqueado en la AFIP
después de que nosotros lo registramos. Reactivarlo desde nuestra propia fila sería confiar
en una foto para un permiso que vive del otro lado.

**Desactivar conserva los numeradores** (RN-04). Reactivar no puede reiniciar la numeración:
ARCA se acuerda de lo que autorizó aunque nosotros hayamos tenido el punto apagado.

**El duplicado lo atrapa el índice único, no una lectura previa.** Un
«¿existe? → no → insertá» pierde contra una segunda pestaña, y el número es justo lo que no
puede duplicarse. El repositorio traduce el `IntegrityError` al mensaje de la historia.

**No hay `DELETE` en ninguna capa** —ni permiso, ni método de repositorio, ni ruta, ni botón.
Un punto que emitió comprobantes no se puede sacar sin dejarlos huérfanos, y esos
comprobantes llevan un CAE. Una ruta que sólo puede fallar es peor que una que no existe.

**Sólo el Administrador administra los puntos.** Más estricto que el mapeo del épico 4, donde
el Operador escribe: esto es la numeración fiscal, no trabajo del día a día. El guarda está
en el caso de uso y no sólo en el router, por lo que enseñó PRU-09.

## Riesgos que obligan a tests

- [ ] Toca dinero — no directamente
- [x] **Toca comprobantes fiscales / CAE** — es la numeración con la que se emiten
- [ ] Consume un webhook — no
- [x] **Agrega datos con `empresa_id`** — RLS, y el aislamiento se prueba contra PostgreSQL
- [ ] Usa salida de un LLM — no
- [ ] Datos personales o fiscales — no: el número de punto es público en el comprobante

## Archivos a tocar

- [x] `backend/src/cheatsheet/contexts/billing/domain/punto_de_venta.py`
- [x] `backend/src/cheatsheet/contexts/billing/application/` — `puntos_de_venta.py`, `ports.py`, `errors.py`
- [x] `backend/src/cheatsheet/contexts/billing/infrastructure/` — `models.py`, `repositories.py`, `habilitacion.py`, `ensamblado.py`
- [x] `backend/migrations/versions/0017_punto_de_venta.py`
- [x] `backend/src/cheatsheet/api/routers/puntos_de_venta.py` + `api/main.py`
- [x] `backend/tests/contexts/billing/…` y `backend/tests/integracion/test_puntos_de_venta_postgres.py`
- [x] `frontend/src/features/billing/` — `api/puntoDeVenta.ts`, `components/PuntosDeVenta.tsx`, `index.ts`
- [x] `frontend/src/app/api/puntos-de-venta/` y `frontend/src/app/(panel)/facturacion/puntos-de-venta/page.tsx`

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un punto habilitado en ARCA queda disponible | unit | **OK** |
| 2 | Uno no habilitado se rechaza con el texto de la historia (RN-03) | unit | **OK** |
| 3 | Uno reportado pero **bloqueado** tampoco se activa | unit | **OK** |
| 4 | ARCA caida no es lo mismo que ARCA diciendo que no | unit | **OK** |
| 5 | Solo el Administrador administra; los demas solo listan | unit | **OK** |
| 6 | Desactivar conserva los numeradores (RN-04) | unit | **OK** |
| 7 | Un punto desactivado no numera | unit | **OK** |
| 8 | Reactivar vuelve a preguntarle a ARCA | unit | **OK** |
| 9 | La numeracion es por `(punto, tipo)` y no global (RN-02) | unit | **OK** |
| 10 | Los `codigo_arca` son los reales de WSFEv1 | unit | **OK** |
| 11 | **Dos emisiones simultaneas no sacan el mismo numero (D14)** | integracion | **OK** |
| 12 | Diez concurrentes dan diez numeros distintos | integracion | **OK** |
| 13 | Dos puntos con el mismo numero en una empresa se rechazan | integracion | **OK** |
| 14 | El mismo numero en dos empresas convive | integracion | **OK** |
| 15 | Una empresa no ve ni puede tomar los puntos de otra | integracion | **OK** |
| 16 | El numerador sobrevive a la ida y vuelta (JSONB reasignado) | integracion | **OK** |
| 17 | No se puede borrar un punto de venta | integracion | **OK** |
| 18 | PAN-FAC-05 lista numero, descripcion y estado | frontend | **OK** |
| 19 | Las dos frases de la historia llegan a la pantalla | frontend | **OK** |
| 20 | La pantalla ofrece desactivar y nunca eliminar | frontend | **OK** |
| 21 | Solo Lectura ve el listado y ninguna accion | frontend | **OK** |
| 22 | El BFF no llega al backend sin sesion, y el 422 cruza con `detalle` | frontend | **OK** |
| 23 | El lector de `FEParamGetPtosVenta` saca `Nro` y `Bloqueado` | unit | **OK** |
| 24 | Un espacio de nombres movido igual se lee | unit | **OK** |
| 25 | **Todo lo que no sea un `"N"` explicito se lee como bloqueado** | unit | **OK** |
| 26 | Una falla SOAP devuelve vacio; ARCA inalcanzable levanta `ArcaNoDisponible` | unit | **OK** |
| 27 | Una empresa sin ticket no sale a la red | unit | **OK** |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | al cierre del epico |

```
ruff format --check .   371 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 371 source files
guard_architecture      389 file(s) checked - architecture boundaries intact
pytest --cov            1030 passed - 0 skipped - cobertura 94%  (umbral 80)
alembic current         0017 (head)
tsc --noEmit            sin errores
eslint . --max-warnings=0   limpio
vitest run              413 passed - cobertura sobre el umbral
```

## Lo que aparecio al implementar y el plan no anticipaba

**El test de concurrencia se verifico al reves antes de darlo por bueno.** Un test de
carrera que pasa no prueba nada por si solo: puede estar pasando porque el candado funciona
o porque las dos corrutinas nunca llegaron a solaparse. Se le saco el `with_for_update()` al
repositorio a proposito y se volvio a correr:

```
assert [1, 2, 2, 2, 2, 2, ...] == [1, 2, 3, 4, 5, 6, ...]
```

Nueve de diez comprobantes con el numero 2. Con el candado, `[1..10]`. Recien ahi el test
vale como prueba de D14.

**El adaptador real contra WSFEv1 estaba sin test, y tenia un bug.** El plan daba por
cubierta la habilitacion con los dobles del caso de uso, y eso deja afuera lo unico que el
doble no puede tener: el parser de la respuesta de ARCA. Un parser roto no tira excepcion
--devuelve cero puntos-- y cero puntos se lee igual que «ARCA no te habilito ninguno».

Al escribir el test aparecio esto:

```python
bloqueado = (nodo.findtext("{*}Bloqueado") or "N").strip().upper() != "N"
```

Un `<Bloqueado></Bloqueado>` vacio es *falsy*, asi que el default disparaba y «ARCA no nos
dijo» se leia como **no bloqueado** -- la direccion insegura, en la unica rama que nadie
iba a mirar. El comentario que estaba al lado decia que la lectura era conservadora. No lo
era. Ahora solo un `"N"` explicito habilita.

**El mismo hueco existia en `CatalogosDeWsfe`, de la unidad 1**, escrito con la misma forma
y probado igual de a medias. Se le agrego su test de contrato en este commit --siete casos,
incluido que una falla en un catalogo no se lleva puestos a los otros tres (RN-04 por
entrada)--. No es ampliar el alcance: es la misma clase de agujero, en la misma rama, en el
mismo epico, y encontrado por este trabajo.

Los dos clientes tampoco aceptaban `transporte` inyectado, que es como se prueban **todos**
los demas clientes SOAP del repositorio (`wsaa.py`, `padron.py`). Se les agrego el
parametro; sin el, el lector solo era alcanzable metiendo mano en un atributo privado.

**Los tests sincronicos del dominio se separaron a su propio modulo.** El
`pytestmark = pytest.mark.asyncio` del modulo de aplicacion los marcaba a todos, y pytest
avisa por cada test sincrono marcado. Estan en `tests/contexts/billing/domain/`.

## Lo que esta unidad deja abierto

**`habilitacion_de_arca()` todavia se arma con el mapa de credenciales vacio**, igual que
`catalogos_fiscales()` de la unidad anterior. Es la misma pieza pendiente —resolver el
ticket de cada empresa desde `integrations`— y se arma una sola vez en
`emision-de-comprobantes`, que la necesita si o si.

**El comentario de `test_servicios/__tests__/rutas.test.ts` sobre `respuestaDeError` quedo
viejo.** Dice que el BFF reenvia `detalle` solo para `EntradaInvalida`; desde el epico 4 lo
reenvia en cualquier 422. El test sigue pasando porque afirma sobre el comportamiento, no
sobre el comentario. Anotado en `TODO.md`.
