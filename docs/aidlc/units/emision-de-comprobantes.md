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
Host Service, y `wsaa.py` los reexporta para no tocar a sus cinco usuarios actuales.

**`HabilitacionEnArca` y `CatalogosDeWsfe` dejan de recibir un dict de credenciales** y
reciben un resolutor. Es la pieza que las dos unidades anteriores dejaron anotada como
pendiente, y es esta la que la necesita de verdad.

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
| 2 - Verificacion | - | pendiente |
| 3 - PR | - | al cierre del epico |
