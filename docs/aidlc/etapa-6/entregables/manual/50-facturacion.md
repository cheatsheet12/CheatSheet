---
entregable: manual
parte: 50-facturacion
responsable: Vincenzo Dallape
estado: borrador
hu: [HU-E5-01, HU-E5-02, HU-E5-03, HU-E5-04, HU-E5-05]
fuentes:
  - frontend/src/app/(panel)/navegacion-lateral.tsx
  - frontend/src/app/(panel)/facturacion/page.tsx
  - frontend/src/app/(panel)/facturacion/nueva/page.tsx
  - frontend/src/app/(panel)/facturacion/[comprobanteId]/page.tsx
  - frontend/src/app/(panel)/facturacion/[comprobanteId]/anular/page.tsx
  - frontend/src/app/(panel)/facturacion/puntos-de-venta/page.tsx
  - frontend/src/features/billing/api/comprobante.ts
  - frontend/src/features/billing/api/puntoDeVenta.ts
  - frontend/src/features/billing/api/mensajesDeError.ts
  - frontend/src/features/billing/components/
  - frontend/src/features/payments/components/ReembolsosDeCobro.tsx
  - backend/src/cheatsheet/api/routers/comprobantes.py
  - backend/src/cheatsheet/api/routers/puntos_de_venta.py
  - backend/src/cheatsheet/api/arca.py
  - backend/src/cheatsheet/contexts/billing/application/
  - backend/src/cheatsheet/contexts/billing/domain/
  - backend/src/cheatsheet/contexts/billing/infrastructure/emisor.py
  - backend/src/cheatsheet/contexts/billing/infrastructure/receptor.py
  - docs/aidlc/TODO.md (§19, §21, §28)
  - docs/aidlc/units.md (D87 a D90)
  - docs/adr/0014-arca-web-service-delegation.md
observaciones: >
  Las funcionalidades se presentan en el orden en que se usan (puntos de venta, emisión,
  listado, detalle, anulación), no en el orden de los ID. Diferencias entre HU y código,
  documentadas tal como las muestra el panel: (1) HU-E5-03 RN-14 (concepto «Servicios», período
  del servicio y vencimiento de pago), RN-08 («IVA No Alcanzado»), RN-10 (uso de la última condición
  confirmada si el padrón no responde) y la reconfirmación del tipo de RN-07 no están implementadas:
  son la unidad pendiente tipos-de-comprobante-por-receptor; por eso no aparecen sus mensajes. (2)
  HU-E5-02 RN-04 / HU-E5-03 RN-09: el detalle muestra la condición frente al IVA del receptor, pero
  no su origen ni su fecha (misma unidad pendiente). (3) HU-E5-03: el precio cero o negativo no se
  bloquea en el formulario; el mensaje «El precio unitario debe ser mayor a cero.» llega del
  servidor al hacer clic en «Emitir comprobante». El mensaje «El tipo de comprobante no es válido
  para la condición de IVA del receptor.» no se ve desde el panel, porque el selector solo ofrece
  los tipos válidos. (4) HU-E5-04: «Debe seleccionar el comprobante que desea anular.» tampoco se
  ve desde el panel, porque la nota de crédito siempre se inicia desde un comprobante; una nota de
  crédito no se puede anular con otra. El comprobante original pasa a «Anulado» solo con una
  anulación total; una parcial lo deja «Autorizado» con el aviso «Anulado parcialmente». (5)
  HU-E5-05: el alta verifica contra ARCA y crea el punto ya activo; si ARCA no lo tiene
  habilitado, no se crea (la HU dice «no permite activarlo»). Operador y Solo Lectura ven la
  pantalla de puntos de venta en modo consulta (la HU nombra solo al Administrador). (6) La
  descarga del PDF está disponible para los tres roles. (7) El detalle no se actualiza solo
  mientras el comprobante está «Pendiente»: hay que recargar la página. (8) Varios mensajes del
  servidor llegan sin tildes («La empresa no tiene conectada la integracion con ARCA»); se
  transcriben literales. (9) Sin verificar en homologación: la Factura C (TODO §28) y los casos de
  TODO §21 (unidad pendiente arca-homologacion-completa).
  Capturas tomadas en staging el 13/10/2026 sobre Estudio Ejemplo SRL (30-00000001-5), la
  empresa de la Demo 2, con ARCA conectado contra homologación: el CAE de MAN-50-4 lo otorgó ARCA
  (ver PRU-01).
---

## Facturación

### Para qué sirve

El módulo Facturación Electrónica emite comprobantes fiscales ante ARCA y guarda el CAE que ARCA
otorga a cada uno. Permite consultar los comprobantes emitidos, descargar su representación en PDF,
anular un comprobante autorizado mediante una nota de crédito y administrar los puntos de venta con
los que se numeran.

Un comprobante autorizado no se modifica ni se borra: la única forma de reversarlo, total o
parcialmente, es emitir una nota de crédito, que también se informa a ARCA y también queda
registrada.

Antes de emitir el primer comprobante, la empresa necesita:

- ARCA conectada, con el servicio de facturación electrónica delegado en CheatSheet (MAN-20).
- Su condición frente al IVA cargada en «Datos de la empresa» (MAN-10).
- Al menos un punto de venta activo, habilitado en ARCA para el CUIT de la empresa.
- El cliente receptor cargado en el catálogo de clientes, con su CUIT (MAN-30).

### Quién puede usarla

| Funcionalidad | Administrador | Operador | Solo Lectura |
|---|---|---|---|
| Listado y detalle de comprobantes | Consulta, filtra y descarga el PDF | Consulta, filtra y descarga el PDF | Consulta, filtra y descarga el PDF |
| Emitir un comprobante | Sí | Sí | No: el botón no aparece y la dirección de la pantalla lo devuelve al listado |
| Anular con nota de crédito | Sí | Sí | No: la acción no aparece y la dirección de la pantalla lo devuelve al detalle |
| Puntos de venta | Agrega, desactiva y activa | Solo consulta | Solo consulta |

El servidor aplica las mismas restricciones aunque la acción se pida sin pasar por el panel.

### Cómo llegar

- «Menú › Operaciones › Facturación» para el listado de comprobantes, la emisión, el detalle y la
  nota de crédito.
- «Menú › Sistema › Puntos de venta» para administrar los puntos de venta. La sección «Sistema»
  aparece cerrada al ingresar: se abre con un clic sobre su título.

### Configurar los puntos de venta

HU-E5-05 — Configurar y administrar los puntos de venta. Cada punto de venta lleva su propia
numeración por tipo de comprobante, igual que en ARCA. El panel no habilita puntos de venta en
ARCA: el punto se habilita primero en el sitio de ARCA, para el CUIT de la empresa, y después se
agrega en el panel.

#### Paso a paso

1. Ingresar a «Menú › Sistema › Puntos de venta».
2. Hacer clic en «Agregar punto de venta».
3. Completar «Número» con el número habilitado en ARCA (por ejemplo, `1`).
4. Completar «Descripción» (por ejemplo, «Consultorio central»).
5. Hacer clic en «Agregar» y esperar el mensaje «Verificando en ARCA…».
6. Verificar que el punto aparezca en el listado con el número en cuatro dígitos (`0001`) y el
   estado «Activo».

![Figura MAN-50-1 — La pantalla Puntos de venta con el punto 0003 activo](capturas/MAN-50_1.png)

Cada punto muestra su estado («Activo» o «Inactivo») y, bajo «Último emitido», el último número
autorizado por cada tipo de comprobante; mientras no emitió ninguno, dice «Sin emisiones».

Para dejar de emitir con un punto, hacer clic en «Desactivar» y confirmar el aviso. Los
comprobantes ya emitidos se conservan y la numeración queda donde está. Para volver a usarlo,
hacer clic en «Activar»: el sistema verifica otra vez contra ARCA que siga habilitado. Un punto de
venta no se elimina.

#### Mensajes y errores frecuentes

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| «El punto de venta no está habilitado en ARCA.» | ARCA no tiene ese número habilitado para el CUIT de la empresa, o lo tiene bloqueado | Habilitar el punto de venta en el sitio de ARCA y volver a agregarlo o activarlo |
| «Ya existe un punto de venta con ese número.» | La empresa ya cargó ese número | Usar el punto existente o, si está «Inactivo», hacer clic en «Activar» |
| «La empresa no tiene conectada la integracion con ARCA» | Falta conectar ARCA | Conectar ARCA (MAN-20) y volver a intentar |
| «ARCA no respondio a la consulta de puntos de venta» | ARCA no respondió en ese momento | Esperar unos minutos y volver a intentar |

### Emitir un comprobante

HU-E5-03 — Emitir un comprobante fiscal y obtener su CAE. La emisión tiene tres pasos: el CUIT del
receptor se valida contra el padrón de ARCA, se elige el tipo de comprobante y el punto de venta, y
se cargan los ítems. El tipo de comprobante disponible depende de la condición frente al IVA de la
empresa y de la del receptor: el panel solo ofrece los tipos válidos para esa combinación.

#### Paso a paso

1. Ingresar a «Menú › Operaciones › Facturación».
2. Hacer clic en «Emitir comprobante».
3. En «¿A quién le facturás?», buscar al cliente por nombre o por CUIT (por ejemplo, Ana Prueba) y
   hacer clic en «Facturar».
4. Esperar que el paso «Receptor» muestre «Verificado en el padrón de ARCA», con el nombre, el CUIT,
   la condición frente al IVA y los tipos de «Se le puede emitir». El CUIT del cliente se valida
   solo; si se corrige, hacer clic en «Validar».
5. En «Tipo de comprobante», elegir el tipo. Si hay uno solo posible, ya aparece elegido.
6. En «Punto de venta», elegir el punto con el que se numera el comprobante.
7. Completar «Domicilio del receptor (opcional)» si corresponde.
8. En «Descripción 1», escribir el concepto o elegir un servicio del catálogo de la lista de
   sugerencias (por ejemplo, Consulta general, $ 15.000,00, «IVA 21%»).
9. Completar «Cantidad», «Precio unitario» e «IVA». Para agregar otra línea, hacer clic en
   «Agregar ítem».
10. Revisar el recuadro «Resumen»: mientras falte algo, «Para emitir falta:» indica qué.
11. Hacer clic en «Emitir comprobante».
12. Esperar a que el panel abra el detalle del comprobante con el estado «Pendiente» y el aviso
    «Esperando la respuesta de ARCA».

![Figura MAN-50-2 — La pantalla «Nueva emisión» con el receptor verificado y un ítem cargado](capturas/MAN-50_2.png)

El sistema calcula el IVA y los totales; el panel no muestra totales hasta que el comprobante está
emitido. Con un emisor Responsable Inscripto y un receptor Monotributo, el comprobante es una
Factura A y lleva la leyenda de la Ley Nº 27.618, visible en el detalle y en el PDF.

No hay que volver a emitir un comprobante «Pendiente»: si ARCA ya lo autorizó, un segundo intento
sería un segundo comprobante por la misma venta.

#### Mensajes y errores frecuentes

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| «Todavía no tenés un punto de venta activo, y sin punto de venta no hay numeración fiscal.» | La empresa no tiene ningún punto de venta activo | Seguir el enlace «Configurá uno» y agregar un punto de venta |
| «Sin CUIT: no se le puede emitir un comprobante» | El cliente del catálogo no tiene CUIT cargado | Hacer clic en «Completar sus datos» y cargar el CUIT del cliente (MAN-30) |
| «El CUIT ingresado no es válido. Debe contener 11 dígitos correctos.» | El CUIT tiene un dígito verificador incorrecto; no se consulta a ARCA | Corregir el CUIT y hacer clic en «Validar» |
| «No se encontró el CUIT en el padrón de ARCA.» | El CUIT es válido pero no existe en el padrón | Verificar el CUIT con el cliente |
| «El CUIT figura en el padrón de ARCA pero no está activo.» | El receptor existe pero está inactivo en ARCA | Consultar al cliente su situación fiscal antes de emitir |
| «Tu empresa todavía no tiene una condición de IVA cargada. Completá los datos fiscales antes de emitir comprobantes.» | Faltan los datos fiscales de la empresa | Completar «Datos de la empresa» (MAN-10) |
| «Debe agregar al menos un ítem para emitir el comprobante.» | No hay ningún ítem con descripción y precio; el botón queda deshabilitado | Cargar al menos un ítem |
| «El precio unitario debe ser mayor a cero.» | Un ítem tiene precio cero o negativo | Corregir el precio y volver a hacer clic en «Emitir comprobante» |
| «No pudimos emitir el comprobante ahora. Antes de reintentar, revisá el listado por si se emitió.» | El panel no recibió la respuesta del servidor | Revisar el listado antes de volver a emitir |

### Consultar el listado de comprobantes

HU-E5-01 — Consultar el listado de comprobantes emitidos. El listado muestra solo los comprobantes
de la empresa, del más reciente al más antiguo, con número, tipo, cliente, total, fecha y estado.

#### Paso a paso

1. Ingresar a «Menú › Operaciones › Facturación».
2. Para filtrar por estado, hacer clic en «Todos», «Autorizados», «Pendientes» o «Con error», o
   elegir una opción en «Estado».
3. Para filtrar por período, completar «Desde» y «Hasta».
4. Para filtrar por tipo, elegir una opción en «Tipo» (Factura A, B o C, o Nota de crédito A, B o C).
5. Revisar la cantidad de resultados arriba de la tabla.
6. Para quitar los filtros, hacer clic en «Limpiar filtros».
7. Hacer clic en el número de un comprobante, o en cualquier parte de su fila, para abrir el detalle.

![Figura MAN-50-3 — El listado de comprobantes con sus filtros y una Factura A autorizada](capturas/MAN-50_3.png)

Los estados que muestra el listado son:

| Estado | Qué significa |
|---|---|
| «Pendiente» | El comprobante se envió a ARCA y todavía no hay respuesta |
| «Autorizado» | ARCA lo autorizó y otorgó el CAE |
| «Error» | ARCA lo rechazó; el motivo se ve en el detalle |
| «Anulado» | Una o más notas de crédito autorizadas lo anularon por el total |

En cada fila, el ícono de descarga baja el PDF de un comprobante autorizado y el ícono «Anular con
nota de crédito» abre la nota de crédito (solo Administrador y Operador).

#### Mensajes y errores frecuentes

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| «Todavía no emitiste comprobantes.» | La empresa no emitió ningún comprobante | Emitir el primero con «Emitir comprobante» |
| «No hay comprobantes para los filtros seleccionados.» | Ningún comprobante coincide con los filtros | Cambiar los filtros o hacer clic en «Limpiar filtros» |
| «No se pudo actualizar el listado.» | El panel no pudo consultar el servidor | Volver a aplicar el filtro |

### Consultar el detalle de un comprobante

HU-E5-02 — Consultar el estado y detalle de un comprobante. El detalle muestra el tipo, el número
con el formato de ARCA (`0001-00000001`), el estado, la fecha de emisión, el total, el CAE y su
vencimiento, el punto de venta, el receptor con su CUIT y su condición frente al IVA, el saldo
pendiente y los ítems con subtotal e IVA. No admite ninguna edición.

#### Paso a paso

1. Ingresar a «Menú › Operaciones › Facturación».
2. Hacer clic en el número del comprobante.
3. Revisar «Datos fiscales»: «CAE», «Vencimiento del CAE» y «Punto de venta».
4. Para copiar el CAE o el CUIT, hacer clic en «Copiar CAE» o «Copiar CUIT».
5. Si el comprobante está «Autorizado», hacer clic en «Descargar PDF».
6. Si el comprobante está «Pendiente», recargar la página más tarde para ver el CAE o el motivo del
   rechazo.
7. Hacer clic en «Volver al listado» para regresar.

![Figura MAN-50-4 — El detalle de un comprobante autorizado con su CAE y el botón «Descargar PDF»](capturas/MAN-50_4.png)

#### Mensajes y errores frecuentes

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| «Esperando la respuesta de ARCA» | El comprobante se envió y ARCA todavía no contestó | Recargar la página más tarde; no emitirlo de nuevo |
| «ARCA rechazó el comprobante», con el código y la descripción de ARCA (por ejemplo, «Error 10016: …») | ARCA no autorizó el comprobante; queda en «Error» y sin PDF | Corregir lo que indica ARCA y emitir un comprobante nuevo |
| «ARCA no tiene registro de este comprobante, así que no llegó a autorizarse. Podés emitirlo de nuevo.» | El envío no llegó a ARCA | Emitir el comprobante de nuevo |
| «Anulado parcialmente» o «Anulado por completo» | Una o más notas de crédito autorizadas reversaron parte o todo el comprobante | Ninguna acción: es informativo |

### Anular un comprobante con una nota de crédito

HU-E5-04 — Anular un comprobante mediante una nota de crédito. Solo se anula un comprobante
autorizado. La nota de crédito toma del original el tipo (A, B o C), el receptor y su condición
frente al IVA, y no puede superar el monto que queda sin anular. La anulación puede ser total o
parcial; una nota de crédito no se anula con otra.

#### Paso a paso

1. Abrir el detalle del comprobante autorizado.
2. Hacer clic en «Anular con nota de crédito».
3. Leer el aviso «Anulando …», que indica qué nota de crédito se emite, a nombre de quién y hasta qué
   monto se puede anular.
4. En «Qué se anula», revisar los ítems: vienen los del original, que anulan el total.
5. Para una anulación parcial, bajar las cantidades o hacer clic en «Quitar» en las líneas que no se
   anulan.
6. Hacer clic en «Emitir nota de crédito».
7. Verificar que el panel vuelva al detalle del original y que la nota aparezca en el listado con el
   estado «Pendiente».

![Figura MAN-50-5 — La pantalla «Nota de crédito» con el comprobante original y los ítems precargados](capturas/MAN-50_5.png)

La nota de crédito también se inicia desde un cobro reembolsado, con el enlace «Emitir nota de
crédito» (MAN-60). En ningún caso se emite sola: requiere el clic en «Emitir nota de crédito».

#### Mensajes y errores frecuentes

| Mensaje | Qué significa | Qué hacer |
|---|---|---|
| «El monto de la nota de crédito no puede superar el del comprobante original.» | Los ítems superan el monto que queda sin anular; el botón se deshabilita | Bajar cantidades o precios hasta el monto indicado en el aviso |
| «Sólo se puede anular un comprobante que ARCA autorizó, y éste todavía no lo está.» | El comprobante está «Pendiente» o en «Error» | Esperar la autorización, o corregir y emitir un comprobante nuevo |
| «Ya está anulado del todo» | Las notas de crédito anteriores ya cubren el total | Ninguna acción: no queda saldo para anular |
| «No se pudo emitir la nota de crédito.» | El panel no recibió la respuesta del servidor | Revisar el listado antes de volver a intentar |
