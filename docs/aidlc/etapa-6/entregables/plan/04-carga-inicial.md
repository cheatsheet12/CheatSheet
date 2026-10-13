---
entregable: plan
parte: 04-carga-inicial
responsable: Paula Ferreira
estado: borrador
hu: [HU-E2-04, HU-E3-01, HU-E3-02, HU-E3-03, HU-E3-05, HU-E3-06, HU-E4-01, HU-E4-02, HU-E5-05, HU-E11-01]
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/inputs/historias-de-usuario.md
  - backend/scripts/verify_rls.py
observaciones: >
  Las dependencias de la columna «Depende de» se citan a nivel de sección (PLAN-§2,
  PLAN-§3) porque esas secciones todavía no están escritas; sus números de actividad
  se alinean cuando se publiquen. Las fechas son relativas a D y las propone la
  responsable; se ajustan al fijarse la fecha calendario de D en plan/00. La empresa
  piloto usa sus propios datos reales en la carga; los datos ficticios de §6 son solo
  para las pruebas en staging.
---

## 4. Carga inicial de datos

### Objetivo

La carga inicial deja a la empresa piloto operando en producción con sus datos maestros, su configuración y sus integraciones cargados y verificados antes de D, de modo que el primer cobro y el primer comprobante se emitan sobre información correcta. Como la empresa piloto lleva hoy su operación en planillas, los clientes y los servicios se cargan por la ingesta del sistema y no a mano.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 4.1 | Relevar con la empresa piloto sus planillas de origen de clientes y servicios y verificar que contengan los campos que la ingesta necesita | Analista Funcional y Diseño de Experiencia | D-14 | PLAN-§3 |
| 4.2 | Conectar las integraciones externas de la empresa piloto con ARCA, MercadoPago y WhatsApp (HU-E2-01, HU-E2-02, HU-E2-03) | Analista de Infraestructura y Datos | D-10 | PLAN-§2 |
| 4.3 | Vincular la planilla de Google Sheets o Excel y confirmar el mapeo de encabezados propuesto (HU-E2-04, HU-E3-01, HU-E3-02) | Analista Funcional y Diseño de Experiencia | D-9 | 4.1 |
| 4.4 | Procesar la carga inicial de clientes y servicios por ingesta (HU-E3-03), consultar el resultado y corregir los errores de fila antes de reprocesar (HU-E3-05, HU-E3-06) | Analista Funcional y Diseño de Experiencia | D-8 a D-6 | 4.3 |
| 4.5 | Configurar los puntos de venta (HU-E5-05) y las reglas de negocio de escalamiento de cobros y de política de turnos (HU-E11-01) | Analista Funcional y Diseño de Experiencia | D-5 | 4.2, 4.4 |
| 4.6 | Verificar la carga: los clientes y servicios coinciden con el origen, los CUIT son válidos y una empresa no accede a los datos de otra (`verify_rls.py`) | Analista Funcional y Diseño de Experiencia | D-4 | 4.4, 4.5 |

### Criterio de listo

- Los clientes y los servicios cargados coinciden en cantidad y datos con las planillas de origen, sin errores de fila pendientes.
- Los puntos de venta y las reglas de negocio quedan configurados y activos.
- La verificación de aislamiento (`verify_rls.py`) confirma que la empresa piloto no accede a datos de otra empresa.
- No queda en producción ningún dato de prueba ni dato real de otra empresa.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Datos sucios en las planillas de origen (CUIT inválidos, clientes duplicados) | Media | Alto | La ingesta valida cada fila y marca los errores; se corrigen y se reprocesan antes de dar la carga por buena (HU-E3-05, HU-E3-06), y la sincronización nunca borra datos |
| Mapeo incorrecto de los encabezados de la planilla | Media | Alto | Se confirma el mapeo propuesto antes de procesar (HU-E3-02) y se revisa el resultado de la primera carga |
| Carga sobre un entorno sin aislamiento entre empresas | Baja | Crítico | Se corre `verify_rls.py` antes de habilitar la operación y la carga no avanza si el aislamiento falla |
| Integración externa sin conectar al momento de configurar | Media | Medio | La conexión con ARCA, MercadoPago y WhatsApp (4.2) precede a la configuración y a la operación; su validación la cubre PLAN-§2 |
