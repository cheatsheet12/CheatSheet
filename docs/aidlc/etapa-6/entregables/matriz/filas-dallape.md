---
entregable: matriz
parte: filas-dallape
responsable: Vincenzo Dallape
estado: borrador
hu: [HU-E5-01, HU-E5-02, HU-E5-03, HU-E5-04, HU-E5-05, HS-T4]
fuentes:
  - docs/aidlc/inputs/historias-de-usuario.md
  - docs/aidlc/inputs/prototipos.md
  - docs/aidlc/inputs/der.md
  - docs/aidlc/units.md
  - docs/aidlc/units/vinculo-de-planilla.md
  - docs/aidlc/units/mapeo-asistido.md
  - docs/aidlc/units/carga-y-errores.md
  - docs/aidlc/units/sincronizacion-y-write-back.md
  - docs/aidlc/units/correccion-de-filas-con-error.md
  - docs/aidlc/units/parametros-fiscales.md
  - docs/aidlc/units/puntos-de-venta.md
  - docs/aidlc/units/emision-de-comprobantes.md
  - docs/aidlc/units/nota-de-credito.md
  - docs/aidlc/units/delegacion-arca.md
  - docs/aidlc/TODO.md
  - backend/src/cheatsheet/platform/settings.py
  - backend/src/cheatsheet/api/arca.py
  - backend/src/cheatsheet/contexts/spreadsheet_sync/
  - backend/src/cheatsheet/contexts/billing/
  - backend/src/cheatsheet/contexts/reference_data/
  - frontend/src/features/spreadsheet_sync/
  - frontend/src/features/billing/
  - render.yaml
observaciones: >
  Prueba manual en staging del 13/10/2026 sobre la empresa de demostración Estudio Ejemplo SRL
  (30-00000001-5), con PRU-01 y las capturas de MAN-50: HU-E5-01 y HU-E5-05 pasan a Probado; las
  demás siguen en Codificado o En desarrollo por criterios sin implementar, con fecha estimada.
  Diferencias entre HU y código: (1) HU-E5-02 RN-04, HU-E5-03 RN-07 a RN-10 y RN-14, y HU-E5-04 RN-06 (ADR-0009) dependen de las
  unidades pendientes tipos-de-comprobante-por-receptor y arca-homologacion-completa: hoy no existen
  la condición «IVA No Alcanzado», el período del servicio, el vencimiento de pago, ni el origen y la
  fecha de la condición del receptor guardados en el comprobante; (2) HS-T4 RN-03: la emisión no
  consulta parametro_fiscal, porque la tabla de tipos válidos vive en el dominio (D16); la consulta
  por fecha (ParametroVigenteA) existe y no la usa la emisión; (3) bug menor abierto: una alícuota
  inválida en POST /comprobantes responde 500 en lugar de 422 (TODO §28). Para el integrador de la
  V4: en HU-E5-04 y HS-T4 el adaptador real de WSFEv1 está activo en staging pero no se ejercitó
  contra ARCA; se usa «Simulada · pendiente de validar» como el valor cerrado más cercano. En
  HU-E5-05 la habilitación del punto de venta es simulada fuera de producción porque homologación no
  lleva registro de puntos de venta.
---

## Filas — Vincenzo Dallape

| Módulo | Funcionalidad | Historia de usuario | Actor | Entidad | Pantalla | Estado de codificación | Integración real | Fecha estimada para Probado |
|---|---|---|---|---|---|---|---|---|
| Facturación Electrónica | Consultar el listado de comprobantes emitidos | HU-E5-01 | Administrador, Operador, Solo Lectura | Comprobante | PAN-FAC-01 | Probado | No aplica | 13/10/2026 |
| Facturación Electrónica | Consultar el estado y detalle de un comprobante | HU-E5-02 | Administrador, Operador, Solo Lectura | Comprobante, ItemDeComprobante | PAN-FAC-02 | En desarrollo | No aplica | 24/10/2026 |
| Facturación Electrónica | Emitir un comprobante fiscal y obtener su CAE | HU-E5-03 | Administrador, Operador | Comprobante, ItemDeComprobante, Cliente, PuntoDeVenta | PAN-FAC-03 | En desarrollo | Real · validada | 24/10/2026 |
| Facturación Electrónica | Anular un comprobante mediante una nota de crédito | HU-E5-04 | Administrador, Operador | Comprobante, ItemDeComprobante | PAN-FAC-04 | En desarrollo | Simulada · pendiente de validar | 24/10/2026 |
| Facturación Electrónica | Configurar y administrar los puntos de venta | HU-E5-05 | Administrador | PuntoDeVenta | PAN-FAC-05 | Probado | Simulada · pendiente de validar | 13/10/2026 |
| Facturación Electrónica | Sincronizar los parámetros fiscales desde ARCA con su vigencia | HS-T4 | Sistema | ParametroFiscal | Sin pantalla | Codificado | Simulada · pendiente de validar | 20/10/2026 |

### Qué respalda cada estado

| HU | Qué respalda el estado |
|---|---|
| HU-E5-01 | Unidad `emision-de-comprobantes` mergeada en el PR #34, con la suite en verde en su verificación: listado por empresa con filtros por fecha, tipo y estado, y sin acciones para Solo Lectura. Prueba en staging del 13/10/2026 (PRU-01): la Factura A 0003-00000002 aparece en el listado con estado «Autorizado». |
| HU-E5-02 | Unidad `emision-de-comprobantes` (PR #34): detalle inmutable con CAE y vencimiento, mensaje de ARCA en los rechazados y PDF cacheado; leyenda de la Ley 27.618 agregada en el PR #132. Falta RN-04 (condición del receptor con su origen y fecha), que entra con la unidad pendiente `tipos-de-comprobante-por-receptor`. Prueba manual en staging pendiente |
| HU-E5-03 | Unidades `emision-de-comprobantes` (PR #34) y `delegacion-arca` (PR #112), y arreglos para obtener CAE real (PR #131 y #132): CAE otorgado por ARCA homologación el 10/10/2026 y en staging el 11/10/2026, con el padrón simulado en staging. Faltan las reglas de ADR-0009 (RN-07 a RN-10 y RN-14) y la Factura C contra ARCA, que cierran `tipos-de-comprobante-por-receptor` y `arca-homologacion-completa`, ambas pendientes. (PRU-01). PRU-01 Aprobada en staging el 13/10/2026: Factura A 0003-00000002 autorizada por ARCA homologación con CAE 86410988477094, detalle y PDF correctos. Confirmado el bug mayor de tipos ofrecidos (Factura A y Nota de crédito A sin preselección). |
| HU-E5-04 | Unidad `nota-de-credito` mergeada en el PR #34: comprobante de origen obligatorio, tipo heredado, tope de monto y anulación total o parcial derivada de las notas autorizadas; el aviso de reembolso enlaza a la nota sin emitirla. La nota usa el adaptador real de WSFEv1 en staging pero no se emitió ninguna contra ARCA (TODO §21.5), y la herencia del período y del vencimiento de RN-06 depende de `tipos-de-comprobante-por-receptor`. Prueba manual en staging pendiente |
| HU-E5-05 | Unidad `puntos-de-venta` mergeada en el PR #34, con tests de unicidad del número, numeración por tipo y desactivación sin borrar; parser real de habilitación probado con sobres grabados (TODO §19). En staging la habilitación es simulada (1 a 5 habilitados, 99 bloqueado) porque homologación no registra puntos de venta. Prueba en staging del 13/10/2026: el punto de venta 0003 se agrega y queda activo (Figura MAN-50-1). |
| HS-T4 | Unidad `parametros-fiscales` mergeada en el PR #34: catálogo versionado por vigencia, un valor nuevo no pisa al anterior y una falla conserva el último vigente, con tests del adaptador real y del simulado. En staging la tarea de Beat usa el adaptador real de WSFEv1, sin una corrida verificada contra ARCA. Prueba manual en staging pendiente (verificación en la bitácora) |
