# Mapa de unidades

> Las unidades de cada épico de [`roadmap.md`](roadmap.md), con su contexto dueño, sus historias,
> sus dependencias y su estado. Hay **un solo** archivo para todo el proyecto: cada sesión de mapeo
> agrega las filas de su épico. La columna `Épico` coincide **textualmente** con el nombre en el
> roadmap — eso es lo que ata los dos documentos.

Estados: `pendiente` · `en curso` · `en revisión` (PR abierto) · `mergeada`.
El estado del épico **se deriva** de estas filas; no se escribe en ningún lado.

| Épico | Unidad | Contexto dueño | HUs | Depende de | Responsable | Rama | Estado |
|---|---|---|---|---|---|---|---|
| Cimientos, identidad y bitácora | cimientos-y-bitacora | observability | HS-T5 | — | Cristian | feature/identity-cimientos-identidad-y-bitacora | mergeada |
| Cimientos, identidad y bitácora | identidad-y-onboarding | identity | HU-E1-01, HU-E1-02, HU-E1-03 | cimientos-y-bitacora | Cristian | feature/identity-cimientos-identidad-y-bitacora | mergeada |
| Cimientos, identidad y bitácora | usuarios-y-preferencias | identity | HU-E1-04, HU-E1-05, HU-E1-06, HU-E1-07 | identidad-y-onboarding | Cristian | feature/identity-cimientos-identidad-y-bitacora | mergeada |
| Cimientos, identidad y bitácora | revocacion-por-reuso | identity | HU-E1-01 | — | Luciano | fix/identity-revocacion-por-reuso | mergeada |
| Cimientos, identidad y bitácora | refresh-concurrente | identity | HU-E1-01 | revocacion-por-reuso | Luciano | fix/identity-refresh-concurrente | mergeada |
| Cimientos, identidad y bitácora | infra-computo-de-staging | observability | — (unidad técnica) | — | Luciano | fix/infra-computo-de-staging | mergeada |
| Conexión con los servicios externos | mecanismo-de-integraciones | integrations | HU-E2-05 | — | Cristian | feature/integrations-mecanismo-de-integraciones | mergeada |
| Conexión con los servicios externos | conexion-whatsapp | integrations | HU-E2-03 | mecanismo-de-integraciones | Cristian | feature/integrations-conexion-whatsapp | mergeada |
| Conexión con los servicios externos | conexion-arca | integrations | HU-E2-01 | mecanismo-de-integraciones | Cristian | feature/integrations-conexion-arca | mergeada |
| Conexión con los servicios externos | padron-y-datos-fiscales | identity | deuda D1 de HU-E1-02 | conexion-arca | Cristian | feature/identity-padron-y-datos-fiscales | mergeada |
| Conexión con los servicios externos | conexion-mercadopago | integrations | HU-E2-02 | mecanismo-de-integraciones | Cristian | feature/integrations-conexion-mercadopago | mergeada |
| Catálogo de clientes y servicios | catalogo-de-clientes | master_data | HU-E4-01 | — | Cristian | feature/master_data-catalogo-de-clientes | mergeada |
| Catálogo de clientes y servicios | catalogo-de-servicios | master_data | HU-E4-02 | catalogo-de-clientes | Cristian | feature/master_data-catalogo-de-servicios | mergeada |
| Catálogo de clientes y servicios | categorias-y-clasificacion | master_data | HU-E4-03, HU-E4-04 | catalogo-de-clientes, catalogo-de-servicios | Cristian | feature/master_data-categorias-y-clasificacion | mergeada |
| Sincronización de planillas | dlq-y-tareas-asincronas | observability | HS-T6 | — | Cristian | feature/spreadsheet_sync-sincronizacion-de-planillas | mergeada |
| Sincronización de planillas | vinculo-de-planilla | spreadsheet_sync | HU-E2-04 | — | Cristian | feature/spreadsheet_sync-sincronizacion-de-planillas | mergeada |
| Sincronización de planillas | mapeo-asistido | spreadsheet_sync | HU-E3-01, HU-E3-02 | vinculo-de-planilla | Cristian | feature/spreadsheet_sync-sincronizacion-de-planillas | mergeada |
| Sincronización de planillas | corregir-esquema-mapeo-anthropic | spreadsheet_sync | HU-E3-01 | mapeo-asistido | Juan | fix/spreadsheet_sync-esquema-mapeo-anthropic | en revisión |
| Sincronización de planillas | google-real-y-write-back | spreadsheet_sync | HU-E3-07 (completa OAuth de HU-E2-04) | sincronizacion-y-write-back | Juan | fix/spreadsheet_sync-google-write-back-real | en revisión |
| Sincronización de planillas | mapeo-google-sheets-real | spreadsheet_sync | HU-E3-01, HU-E3-02, HU-E3-03, HU-E3-05, HU-E3-06 (Google Sheets) | google-real-y-write-back | Juan | fix/spreadsheet_sync-mapeo-google-real | en curso |
| Sincronización de planillas | sincronizacion-incremental-real | spreadsheet_sync | HU-E3-04 | google-real-y-write-back | Juan | fix/spreadsheet_sync-incremental-real | pendiente |
| Sincronización de planillas | carga-y-errores | spreadsheet_sync | HU-E3-03, HU-E3-05, HU-E3-06 | dlq-y-tareas-asincronas, mapeo-asistido | Cristian | feature/spreadsheet_sync-sincronizacion-de-planillas | mergeada |
| Sincronización de planillas | sincronizacion-y-write-back | spreadsheet_sync | HU-E3-04, HU-E3-07 | carga-y-errores | Cristian | feature/spreadsheet_sync-sincronizacion-de-planillas | mergeada |
| Facturación electrónica | parametros-fiscales | reference_data | HS-T4 | — | Cristian | feature/billing-facturacion-electronica | mergeada |
| Facturación electrónica | puntos-de-venta | billing | HU-E5-05 | — | Cristian | feature/billing-facturacion-electronica | mergeada |
| Facturación electrónica | emision-de-comprobantes | billing | HU-E5-01, HU-E5-02, HU-E5-03 | parametros-fiscales, puntos-de-venta | Cristian | feature/billing-facturacion-electronica | mergeada |
| Facturación electrónica | nota-de-credito | billing | HU-E5-04 | emision-de-comprobantes | Cristian | feature/billing-facturacion-electronica | mergeada |
| Cobros y recordatorios | cobros-y-recordatorios | payments | HU-E6-01 … HU-E6-06, HU-E11-01, HS-T1, HS-T3 | emision-de-comprobantes | vichen12 | feature/payments-cobros-agenda-agente-y-reportes | mergeada |
| Agenda y recursos | agenda-y-recursos | scheduling | HU-E7-01 … HU-E7-06, HU-E6-07 | cobros-y-recordatorios | vichen12 | feature/payments-cobros-agenda-agente-y-reportes | mergeada |
| Agente de WhatsApp y atención humana | agente-y-atencion-humana | conversational | HU-E8-01 … HU-E8-05, HU-E9-01, HU-E9-02, HU-E9-04, HU-E11-02, HS-T2, HS-T7 | agenda-y-recursos | vichen12 | feature/payments-cobros-agenda-agente-y-reportes | mergeada |
| Reportería y paquete contable | reporteria-y-paquete-contable | reporting | HU-E10-01 … HU-E10-06 | agente-y-atencion-humana | vichen12 | feature/payments-cobros-agenda-agente-y-reportes | mergeada |
| Reportería y paquete contable | reporte-fallido-persistido | reporting | HU-E10-03 | — | Luciano | fix/reporting-reporte-fallido-persistido | mergeada |
| Reportería y paquete contable | paquete-fallido-visible | reporting | HU-E10-04 | reporte-fallido-persistido | — | — | pendiente |
| Panel de auditoría y notificaciones | panel-de-auditoria-y-notificaciones | observability | HU-E12-01, HU-E12-02, HU-E11-03, HU-E9-03 | reporteria-y-paquete-contable | vichen12 | feature/observability-panel-de-auditoria | mergeada |
| Cobros y recordatorios | cancelacion-invalida-el-link | payments | HU-E6-04, HS-T1 | cobros-y-recordatorios | Cristian | fix/payments-cancelacion-invalida-el-link | en revisión |
| Cimientos, identidad y bitácora | revocacion-inmediata-de-sesion | identity | HU-E1-05, HU-E1-06 | — | Luciano | feature/identity-revocacion-inmediata-de-sesion | mergeada |
| Cimientos, identidad y bitácora | renovacion-sin-borrar-sesion | identity | HU-E1-01 | revocacion-inmediata-de-sesion | Luciano | fix/identity-renovacion-sin-borrar-sesion | mergeada |
| Cimientos, identidad y bitácora | terminos-y-privacidad | identity | HU-E1-03, HU-E1-08 | — | Luciano | feature/identity-terminos-y-privacidad (tramos 1, 2, 3) | mergeada |
| Catálogo de clientes y servicios | duracion-de-servicios | master_data | HU-E4-02 | — | Luciano | feature/master_data-duracion-de-servicios | mergeada |
| Catálogo de clientes y servicios | normalizacion-de-datos | master_data | HU-E4-05, HU-E4-01, HU-E3-03, HU-E3-04, HU-E3-07 | — | Luciano | feature/master_data-normalizacion-de-datos | mergeada |
| Catálogo de clientes y servicios | correccion-de-datos-existentes | master_data | HU-E4-05 (RN-09) | normalizacion-de-datos | Luciano | feature/master_data-correccion-de-datos-existentes | mergeada |
| Facturación electrónica | tipos-de-comprobante-por-receptor | billing | HU-E5-03, HU-E5-02, HU-E5-04 | — | — | — | pendiente |
| Facturación electrónica | arca-homologacion-completa | billing | HU-E5-03 | tipos-de-comprobante-por-receptor | — | — | pendiente |
| Cobros y recordatorios | nuevo-cobro-desde-su-panel | payments | HU-E6-03 | — | Luciano | feature/payments-nuevo-cobro-desde-su-panel | mergeada |
| Cobros y recordatorios | fecha-de-pago | payments | HU-E6-01, HU-E6-02 | — | Luciano | feature/payments-fecha-de-pago | mergeada |
| Cobros y recordatorios | reembolsos-parciales-y-manuales | payments | HU-E6-05 | fecha-de-pago | Luciano | feature/payments-reembolsos-parciales-y-manuales | mergeada |
| Cobros y recordatorios | reembolsos-en-vuelo | payments | HU-E6-05 | reembolsos-parciales-y-manuales | — | — | pendiente |
| Cobros y recordatorios | reembolso-rechazado-persistido | payments | HU-E6-05 | — | — | — | absorbida por `reembolsos-parciales-y-manuales` |
| Cobros y recordatorios | cobro-por-transferencia | payments | HU-E6-08 | reembolsos-parciales-y-manuales | — | — | pendiente |
| Agenda y recursos | turnos-no-en-el-pasado | scheduling | HU-E7-06, HU-E7-02, HU-E8-01 | — | Luciano | feature/scheduling-turnos-no-en-el-pasado | mergeada |
| Agenda y recursos | limites-e-intervalo-de-turnos | scheduling | HU-E7-04, HU-E7-06 | turnos-no-en-el-pasado | Luciano | feature/scheduling-limites-e-intervalo-de-turnos | mergeada |
| Agenda y recursos | router-de-agenda-por-responsabilidad | scheduling | HU-E7-01 … HU-E7-06 (referencia) | — | Luciano | fix/scheduling-router-de-agenda-por-responsabilidad | mergeada |
| Agente de WhatsApp y atención humana | comprobante-por-whatsapp | conversational | HU-E8-06, HU-E8-05 | cobro-por-transferencia | — | — | pendiente |
| Agente de WhatsApp y atención humana | usos-de-faq-por-periodo | conversational | HU-E9-04 | ADR-0012 | Luciano | feature/conversational-usos-de-faq-por-periodo | mergeada |
| Agente de WhatsApp y atención humana | reserva-y-cancelacion-por-whatsapp | conversational | HU-E8-01, HU-E8-02, HS-T2 | ajustes-menores-del-agente | Luciano | feature/conversational-reserva-y-cancelacion-por-whatsapp | mergeada |
| Reportería y paquete contable | indicadores-de-cobranza | reporting | HU-E10-01 | fecha-de-pago | Luciano | feature/reporting-indicadores-de-cobranza | mergeada |
| Agente de WhatsApp y atención humana | telefono-del-operador | conversational | HU-E9-01 | — | Luciano | fix/conversational-telefono-del-operador | mergeada |
| Agente de WhatsApp y atención humana | borrado-sin-cuerpo | frontend (`lib/`, transversal) | HU-E9-04, HU-E4-03, HU-E1-04, HU-E2-04, HU-E10-05 | — | Luciano | fix/frontend-borrado-sin-cuerpo | mergeada |
| Agente de WhatsApp y atención humana | ajustes-menores-del-agente | conversational | HS-T2, HU-E8-05 | — | Luciano | fix/conversational-ajustes-menores-del-agente | mergeada |
| Agente de WhatsApp y atención humana | politica-fuera-de-horario | business_config (conversational aplica la política por su ACL) | HS-T2, HU-E11-01, HU-E8-05 | reserva-y-cancelacion-por-whatsapp | Luciano | feature/business_config-politica-fuera-de-horario | mergeada |
| Cimientos, identidad y bitácora | navegacion-pendiente | frontend (`shared/`, transversal) | HU-E1-01, HU-E1-02, HU-E1-04, HU-E2-04, HU-E5-03, HU-E5-04, HU-E6-03, HU-E7-06 | — | Luciano | fix/frontend-navegacion-pendiente | mergeada |
| Cobros y recordatorios | cobro-con-clave-de-idempotencia | payments | HU-E6-03 | navegacion-pendiente | Luciano | feature/payments-cobro-con-clave-de-idempotencia | mergeada |
| Cobros y recordatorios | pagos-sin-cobro-asociado | payments | HU-E6-03, HS-T1 | cobro-con-clave-de-idempotencia | Luciano | — | pendiente |
| Agente de WhatsApp y atención humana | canal-real-de-whatsapp | conversational | HS-T3, HU-E7-02, HU-E7-06, HU-E8-04 | — | Luciano | feature/conversational-canal-real-de-whatsapp | mergeada (#104) |
| Agente de WhatsApp y atención humana | plantillas-de-whatsapp-en-meta | business_config | HU-E11-02, HU-E8-04, HS-T3, HU-E7-02, HU-E7-06 | canal-real-de-whatsapp (mergeada), ADR-0011 (aceptado) | Luciano | feature/business_config-plantillas-de-whatsapp-en-meta | mergeada |
| Agente de WhatsApp y atención humana | entregas-de-whatsapp | conversational | HU-E8-04, HS-T3, HU-E6-02, HU-E7-02, HU-E7-06 | canal-real-de-whatsapp, plantillas-de-whatsapp-en-meta | Luciano | feature/conversational-entregas-de-whatsapp (tramos i, ii, iii) | mergeada |
| Agente de WhatsApp y atención humana | recordatorio-de-turno | scheduling | HU-E8-04, HU-E11-01 | plantillas-de-whatsapp-en-meta, entregas-de-whatsapp | Luciano | feature/scheduling-recordatorio-de-turno (tramos 1, 2, 3) | mergeada |
| Agente de WhatsApp y atención humana | wamid-entrante-largo | conversational | HS-T2 | entregas-de-whatsapp | Luciano | fix/conversational-wamid-entrante-largo | mergeada |
| Agente de WhatsApp y atención humana | dobles-de-conversational-por-responsabilidad | conversational | HS-T2 | entregas-de-whatsapp | Luciano | fix/conversational-dobles-por-responsabilidad | mergeada |
| Agente de WhatsApp y atención humana | corregir-esquema-de-lectura-anthropic | conversational | HU-E8-01, HU-E8-02 | agente-y-atencion-humana | Luciano | fix/conversational-esquema-de-lectura-anthropic | en revisión |
| Cobros y recordatorios | recordatorio-por-email | payments | HS-T3 | canal-real-de-whatsapp | Luciano | — | pendiente |
| Cimientos, identidad y bitácora | integracion-en-neon | tests de integración (`backend/tests/integracion`, transversal) | — | — | Luciano | feature/infra-integracion-en-neon | mergeada |
| Cimientos, identidad y bitácora | mypy-en-pre-commit | infra (`.pre-commit-config.yaml`, transversal) | — (unidad técnica) | — | Emanuel | fix/infra-mypy-en-pre-commit | en revisión |
| Agenda y recursos | agenda-con-una-sola-fecha | scheduling | HU-E7-01 | mypy-en-pre-commit | Emanuel | fix/scheduling-agenda-con-una-sola-fecha | en revisión |
| Panel de auditoría y notificaciones | busqueda-por-cliente | observability | HU-E12-01 | mypy-en-pre-commit | Emanuel | fix/observability-busqueda-por-cliente | en revisión |
| Agenda y recursos | cliente-en-el-turno | scheduling | HU-E7-02, HU-E7-06 | — | Emanuel | fix/scheduling-cliente-en-el-turno | en revisión |
| Agenda y recursos | confirmar-cancelacion | scheduling | HU-E7-02 | — | Emanuel | fix/scheduling-confirmar-cancelacion | en revisión |
| Agenda y recursos | facturar-turno-completado | scheduling | HU-E7-03 | — | Emanuel | fix/scheduling-facturar-turno-completado | en revisión |
| Panel de auditoría y notificaciones | soporte-campos-obligatorios | observability | HU-E9-03 | — | Emanuel | fix/observability-soporte-campos-obligatorios | en revisión |
| Panel de auditoría y notificaciones | titulo-de-soporte | observability | HU-E9-03 | — | Emanuel | fix/observability-titulo-de-soporte | en revisión |
| Agenda y recursos | calendario-del-filtro | scheduling | HU-E7-01 | — | Emanuel | fix/scheduling-calendario-del-filtro | en revisión |
| Agenda y recursos | horario-especial | scheduling | HU-E7-05 | — | Emanuel | fix/scheduling-horario-especial | en revisión |
| Panel de auditoría y notificaciones | responsable-de-la-operacion | observability | HU-E12-02 | — | Emanuel | fix/observability-responsable-de-la-operacion | en revisión |
| Panel de auditoría y notificaciones | rotulos-de-la-bitacora | observability | HU-E12-01 | — | Emanuel | fix/observability-rotulos-de-la-bitacora | en revisión |
| Panel de auditoría y notificaciones | menu-sin-bitacora-para-lectura | observability | HU-E12-01 | — | Emanuel | fix/observability-menu-sin-bitacora-para-lectura | en revisión |
| Agenda y recursos | elegir-cliente-en-nuevo-turno | scheduling | HU-E7-06 | — | Emanuel | fix/scheduling-elegir-cliente-en-nuevo-turno | en curso |
| Agenda y recursos | error-dentro-del-modal | scheduling | HU-E7-02, HU-E7-04, HU-E7-05 | — | Emanuel | fix/scheduling-error-dentro-del-modal | en revisión |


---

## Épico 1 — Cimientos, identidad y bitácora

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **cimientos-y-bitacora** | **Las seis unidades técnicas del roadmap §5, completas, más HS-T5.** Backend: composition root de FastAPI (`api/`), healthcheck y manejo uniforme de errores; `platform/settings.py` y sesión de base de datos; migraciones (Alembic); aislamiento multi-empresa con RLS por `empresa_id` (ADR-002); esqueleto de Celery + Beat con las cinco colas (ADR-003), `ClaveDeIdempotencia` y reintentos con backoff (ADR-009); esqueleto de tests (fixtures de base, factories, dobles de servicios externos) con el umbral del 80% corriendo en CI. Dominio: el agregado `RegistroDeAuditoria`, su tabla inmutable y el mecanismo por el que cualquier contexto publica un evento auditable (`observability` como OHS). Frontend: BFF de Next.js, cookie HttpOnly del JWT, layouts `(panel)` y `(public)`, wrapper de fetch y sistema de diseño mínimo. **Sin pantalla de negocio**: leer la bitácora es el épico 10 |
| **identidad-y-onboarding** | HU-E1-01, HU-E1-02 y HU-E1-03 — el onboarding entero de punta a punta: agregados `Empresa` y `Usuario`; alta con email/contraseña (Argon2id) y con OAuth2 de Google; login; JWT corto + refresh opaco rotativo con detección de reuso (ADR-011); aceptación de términos con versión y fecha; datos fiscales de la empresa con CUIT y `CondicionIVA` (ver D1); bloqueo del dashboard hasta completar los pasos 1 y 2. Pantallas PAN-ONB-01 y PAN-ONB-02 |
| **usuarios-y-preferencias** | HU-E1-04, HU-E1-05, HU-E1-06 y HU-E1-07 — todo lo que un Administrador hace sobre los usuarios de su empresa, más lo que cada usuario hace sobre sí mismo: invitación por email y su aceptación, catálogo cerrado de tres roles con RBAC, cambio de rol, desactivación y reactivación, el invariante «siempre al menos un Administrador activo», y `pref_idioma` / `pref_zona_horaria` / `pref_suscripciones`. Pantallas PAN-USR-01 y PAN-USR-02 |

### Orden

```
cimientos-y-bitacora ── identidad-y-onboarding ── usuarios-y-preferencias
```

Cadena lineal, un responsable, sin paralelismo. Cada unidad deja la anterior demostrable: la primera
levanta el proceso y la bitácora, la segunda registra una empresa que ya audita cada operación, la
tercera opera sobre los usuarios de esa empresa.

### Notas

- **Unidades gruesas, deliberadamente.** Tres unidades para ocho historias, no ocho para ocho. El
  costo de cada unidad no es solo su código: son tres gates, un plan y un PR. Con historias de esta
  granularidad —HU-E1-03 son dos columnas y un checkbox; HU-E1-07 son tres campos— el plan llegaría
  a ser más largo que el diff, que es justamente el caso que el workflow manda resolver escribiendo
  una línea y ejecutando. Se agrupa por **pantalla y transacción compartida**: las dos pantallas del
  onboarding en una unidad, las dos de configuración de usuarios en otra.
- **El precio, dicho de frente:** los PRs son grandes, sobre todo el de `cimientos-y-bitacora`, y si
  el Gate 2 falla hay más superficie que desandar. Se acepta a cambio de tres ceremonias en lugar de
  ocho. Si una unidad se vuelve inmanejable durante la implementación, se dice y se re-corta el mapa
  con el equipo — nunca partiéndola dentro de la rama (regla 1c).
- **La bitácora entra en la unidad de cimientos y eso la mejora, no la infla.** HS-T5 no tiene
  pantalla y `observability` es OHS: no depende de nadie. Su tabla `registro_de_auditoria` es además
  la **primera tabla real** del sistema, o sea contra qué se prueban de verdad las migraciones, el
  RLS por `empresa_id` y las fixtures. Sin ella, los cimientos se verificarían contra nada. Y va
  antes que identity porque HU-E1-05 RN-04 y HU-E1-06 RN-02 exigen registro en el Log de
  Operaciones: si el sumidero llegara después, identity se entregaría con un criterio incumplido.
- **`cimientos-y-bitacora` cruza `observability` + `platform` + frontend.** Declara `observability`
  como contexto dueño porque es el único que recibe código de dominio; el resto es infraestructura
  sin dueño de negocio.
- **Trabajo en paralelo: no aplica.** Un solo responsable (Cristian). La regla 1c del workflow sigue
  vigente por si eso cambia.
- **Las tres unidades comparten una sola rama** (decisión del 2026-08-13), en lugar de una rama y
  un PR cada una como pide la regla 1a. El épico entero entra a `develop` de una vez.
  **Lo que se gana:** una sola ceremonia de PR en lugar de tres encadenadas, sin rebases entre
  ramas que dependen unas de otras. **Lo que se paga:** un PR con las ocho historias, y un revert
  que se lleva el épico completo. Los **gates 1 y 2 siguen siendo por unidad** — lo que se unificó
  es la rama y el gate 3, no la planificación ni la verificación.
- **Esto no habilita a partir unidades dentro de la rama.** Si la descomposición resulta mala, se
  dice y se re-corta el mapa deliberadamente (regla 1c), que es lo mismo de antes.

### Decisión D1 — resuelta

El roadmap §6 la dejaba abierta: HU-E1-02 RN-01 exige validar el CUIT contra ARCA en tiempo real
durante el onboarding, pero la credencial fiscal de la empresa recién se carga en el épico 2.

**Resolución (2026-08-12): validación estructural en el épico 1; consulta al padrón en el épico 2.**
`identidad-y-onboarding` valida formato y dígito verificador del CUIT, y `CondicionIVA` se elige
manualmente. No se introduce una credencial ARCA de plataforma.

Consecuencias, explícitas para que nadie las descubra después:

- El épico 1 **cierra con HU-E1-02 RN-01 parcialmente cumplida**. La autocompletación de
  `CondicionIVA` desde el padrón (criterio de aceptación 1 de HU-E1-02) tampoco se cumple todavía.
- **El épico 2 carga con completarla**: cuando HU-E2-01 deja la credencial de ARCA cargada y
  validada, se agrega la consulta de padrón al onboarding y a la edición de datos de la empresa.
  Eso se mapeará como unidad del épico 2, no acá.
- Un CUIT estructuralmente válido pero inexistente en ARCA **entra al sistema** hasta entonces. Es
  aceptable porque ningún comprobante se emite antes del épico 5, y la emisión revalida contra ARCA.

### Decisión D83 — los términos los acepta la empresa; la política de privacidad la acepta cada usuario · ADR-0009

HU-E1-03 RN-03 pedía una nueva aceptación «al usuario», pero `terminos_version` y
`terminos_fecha_aceptacion` son atributos de `empresa` (RN-01 y DER). Y la revisión de 2026-09 sumó
la política de privacidad conforme a la Ley 25.326 (HU-E1-08), que el catálogo no tenía.

**Los términos son un vínculo contractual con la empresa, y los re-acepta un Administrador; los
demás roles no se bloquean. La política es un consentimiento personal, y lo acepta cada Usuario.**
Los invitados aceptan solo la política, porque el contrato es de la empresa; el Contador externo
no es Usuario y solo ve un aviso con el enlace. Las dos páginas son públicas, versionadas y con
ruta estable: el enlace `/terminos` responde hoy 404, lo que vuelve informada solo en apariencia la
aceptación de RN-02. La casilla de la política es propia, sin marcar y separada de la de términos.

La empresa no puede otorgar por sus usuarios un consentimiento que es personal. El texto de la
política incluye la verificación de la identidad del pagador contra MercadoPago (D94), y su
contenido se valida con asesoría legal antes de publicarse.

**Modelo, para el Gate 1 de `terminos-y-privacidad`:** el DER no tiene dónde guardar aceptaciones
por usuario. Hace falta una tabla, por ejemplo `aceptacion_legal` (`usuario_id`, `documento`,
`version`, `fecha_aceptacion`), sin guardar IP. También se resuelven dónde viven los textos
versionados y el código de pantalla de la política (`PAN-LEG-01`, a asignar).

**Lo que se paga:** un bloqueo más en el ingreso de cada usuario cuando cambia la versión, y dos
rutas públicas que hay que mantener siempre disponibles.

### Decisión D84 — cambiar el rol o desactivar a un usuario se evalúa en su siguiente solicitud · ADR-0009

HU-E1-05 RN-01 y HU-E1-06 RN-01 piden efecto inmediato. El token de acceso corto deja hoy una
ventana de hasta 15 minutos en la que rige el rol o el estado anterior. La historia ya decía lo
correcto; lo que falla es la implementación, y por eso solo ganó criterios verificables.

**El rol y el estado del usuario se evalúan contra el estado actual en cada solicitud, no contra lo
que dice el token.** Desactivar a un usuario revoca además sus sesiones renovables, y el intento de
renovar una sesión de un usuario desactivado se rechaza y lleva al inicio de sesión.

**Para el Gate 1 de `revocacion-inmediata-de-sesion`:** el mecanismo (consultar el usuario en cada
solicitud, o una versión de sesión con caché corta) se elige midiendo su costo por solicitud. Si
cambia el esquema de autenticación, necesita su propio ADR antes de cerrar el Gate 1
(`docs/adr/README.md`). El refresh opaco rotativo con detección de reuso no cambia.

### Estado

**Cerrado en código.** Las tres unidades pasaron el Gate 2 en verde (2026-08-18) y el épico
entero entró a `develop` en un solo PR — [#5](https://github.com/cheatsheet12/CheatSheet/pull/5) —
por la decisión del 2026-08-13.

Lo que queda no es código: son las credenciales reales de Google OAuth2 y del correo transaccional,
que hoy corren simuladas, más la deuda declarada. Todo eso está en [`TODO.md`](TODO.md) §2 y §3.

### Fuera de alcance de este épico

- Pantalla de la bitácora (HU-E12-01, HU-E12-02) → épico 10.
- Centro de notificaciones (HU-E11-03) → épico 10. Este épico solo envía el email de invitación.
- Cola de fallos DLQ (HS-T6) → épico 4.
- Consulta de CUIT al padrón de ARCA → épico 2, por D1.

---

## Épico 2 — Conexión con los servicios externos

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **mecanismo-de-integraciones** | El andamiaje que las otras cuatro presuponen, más HU-E2-05. Dominio: el agregado `ConfiguracionDeIntegracion` con `SistemaExterno`, `Ambiente` (homologación / producción), `EstadoDeConexion` (conectado · atención · no conectado) y la marca de tiempo de la última verificación. Plataforma: el cifrado de credenciales en reposo (AES-256-GCM), con `credencial_algoritmo` en su propia columna para poder rotar sin adivinar con qué se cifró cada fila. Aplicación: el puerto `PortVerificadorDeConexion` y el registro que resuelve un verificador por sistema; el caso de uso de verificación en vivo de HU-E2-05. Frontend: `features/integrations` y la pantalla PAN-CFG-INT en `(panel)/configuracion/integraciones`, con la grilla de cuatro tarjetas del prototipo. **Sin ningún proveedor real**: los cuatro verificadores son simulados, igual que `ProveedorOAuthSimulado` en el épico 1. Termina en la pantalla mostrando las cuatro integraciones «No conectada» y el botón de verificar funcionando |
| **conexion-whatsapp** | HU-E2-03 — alta del número de WhatsApp Business contra Meta, estado `pendiente` mientras dura la verificación, tarea de Beat que consulta el resultado, `display_name` verificado y calidad de la línea, motivo de rechazo cuando falla, y la notificación al Administrador en los tres desenlaces |
| **conexion-arca** | HU-E2-01 — carga del certificado y la clave privada asociados al CUIT de la empresa, cifrados con el mecanismo de la unidad 1; validación real contra WSAA obteniendo un ticket de acceso antes de marcar Conectada; ambiente registrado; detección de credencial vencida o revocada que pasa la integración a inactiva y notifica |
| **padron-y-datos-fiscales** | La deuda D1 del épico 1. Consulta al padrón de ARCA con la credencial que dejó `conexion-arca`: valida que el CUIT exista, autocompleta razón social y `CondicionIVA`, y lo hace tanto en el paso 2 del onboarding (PAN-ONB-02) como en la edición de datos de la empresa. Cierra HU-E1-02 RN-01 y su criterio de aceptación 1, que el épico 1 entregó a medias |
| **conexion-mercadopago** | HU-E2-02 — flujo OAuth2 contra MercadoPago, token de acceso y de refresco cifrados, validación de la conexión leyendo los datos de la cuenta antes de marcarla activa, y revocación o expiración que la pasa a inactiva y notifica |

### Orden

```
mecanismo-de-integraciones ─┬─ conexion-whatsapp
                            ├─ conexion-arca ── padron-y-datos-fiscales
                            └─ conexion-mercadopago
```

Un solo responsable, así que se ejecutan en serie: **mecanismo → whatsapp → arca → padrón → mercadopago**.

**WhatsApp va segunda, y es lo único del orden que no se negocia.** HU-E2-03 RN-02 dice que Meta
tarda entre 24 y 72 horas en verificar el número, y eso es tiempo de calendario que no se compra con
esfuerzo. Arrancarla apenas exista el andamiaje pone el reloj a correr mientras se construyen ARCA y
MercadoPago; dejarla última agrega tres días muertos al final del épico. Es la misma razón por la que
el roadmap §3 la adelantó al épico 2 aunque el agente conversacional sea el 8.

Las otras tres son independientes entre sí: ninguna lee nada de las otras. Si en algún momento hay un
segundo responsable, ese es el punto de corte natural (regla 1c).

### Notas

- **Cinco unidades para cuatro historias — y sí, es lo contrario de lo que hizo el épico 1.** Ahí se
  agruparon ocho historias en tres unidades porque eran chicas: «HU-E1-03 son dos columnas y un
  checkbox». Acá tres de las cuatro historias están marcadas **Complejidad Alta** en el insumo, y
  cada una es una integración externa distinta: WSAA de ARCA habla SOAP con certificado cliente,
  MercadoPago habla OAuth2 sobre REST, Meta habla Graph API con una verificación asíncrona de 72
  horas. Lo único que comparten es el agregado y la tarjeta en la pantalla — que es exactamente lo
  que se extrajo a la unidad 1. Juntarlas daría un PR con tres protocolos, tres modos de falla y
  tres juegos de tests de contrato, o sea el PR de `cimientos-y-bitacora` otra vez pero peor.
- **Una rama y un PR por unidad. Se vuelve a la regla 1a y se abandona la excepción del 2026-08-13.**
  El épico 1 corrió las tres unidades sobre una rama única. Acá eso sería un error concreto, no un
  gusto: `conexion-whatsapp` **no puede cerrar hasta que Meta responda**, entre uno y tres días
  después de que el código esté listo. Con rama única, ARCA y MercadoPago quedarían rehenes de ese
  reloj externo, y `conexion-arca` es justamente lo que el épico 5 (facturación) necesita mergeado
  para poder planificarse. Se paga con cinco ceremonias de PR en lugar de una; se compra que una
  espera de terceros no bloquee al resto.
- **`padron-y-datos-fiscales` es unidad aparte y su dueño es `identity`, no `integrations`.** Escribe
  sobre el agregado `Empresa` — razón social y `CondicionIVA` —, y el workflow manda que la unidad
  declare como dueño al contexto que hace la escritura. Llega a la credencial de ARCA llamando al
  servicio de aplicación de `integrations`, nunca a su dominio (R3). **La alternativa que se
  descartó** era plegarla dentro de `conexion-arca`, que tiene el atractivo de dejar esa unidad
  terminando en algo demostrable de punta a punta; se descartó porque obligaría a que una unidad de
  `integrations` escriba en `identity`, que es el tipo de ambigüedad de propiedad que después nadie
  sabe dónde tocar.
- **`mecanismo-de-integraciones` no es una unidad técnica encubierta.** Lleva HU-E2-05 detrás: la
  verificación en vivo y el estado consolidado son *su* historia, no un extra. Por eso no necesita la
  escalada de «trabajo sin historia» del workflow, y por eso termina en una pantalla que se puede
  mostrar aunque no haya ningún proveedor conectado.
- **Los cuatro proveedores arrancan simulados, a propósito.** Es la misma decisión que el épico 1
  tomó con Google OAuth y con el correo, y que funcionó: el flujo se recorre entero en una laptop,
  los tests no tocan la red (regla del workflow, paso 3), y el simulado **lanza al construirse en
  `production`**. Conseguir las credenciales reales de ARCA homologación, de MercadoPago sandbox y
  de Meta es tarea de despliegue y va en el `TODO.md` del épico, no en el código.
- **Cada una de las tres conexiones dispara la escalada de «nueva integración externa»**: su plan de
  Gate 1 debe traer sección de contratos —endpoints por ambiente, autenticación, modos de falla— y
  tests de contrato. Eso es por unidad, no acá.
- **`mecanismo-de-integraciones` carga además con reconciliar `backend/.env.example`.** Agrega
  `SECRETS_ENCRYPTION_KEY`, así que la Definition of Done (`CLAUDE.md` §7) la obliga a tocar ese
  archivo igual; y el archivo hoy está **desincronizado con el código desde el épico 1** — declara
  `ENVIRONMENT`, `JWT_SECRET_KEY`, `JWT_ACCESS_TOKEN_MINUTES` y `REFRESH_TOKEN_DAYS` cuando
  `platform/settings.py` lee `APP_ENV`, `JWT_SECRET`, `JWT_ACCESS_TTL_MINUTOS` y `REFRESH_TTL_DIAS`,
  y le faltan las once variables de las unidades 2 y 3. Copiarlo hoy no levanta el proceso. Se dice
  acá para que quede claro que es deuda heredada que se salda de paso, no alcance nuevo.

### Decisión D7 — la pantalla de integraciones es de configuración, no un paso del onboarding

Las cuatro historias del épico nombran **PAN-CFG-INT (Configuración — Integraciones)**. Ese código
**no existe en el mapa de navegación de Etapa 5**: la única pantalla de integraciones maquetada es
**PAN-ONB-03 — Integraciones**, el tercer paso del onboarding en `prototipos/onboarding.html`.
Son dos ubicaciones distintas del mismo contenido y hay que elegir una.

**Resolución (2026-08-18): se construye como pantalla de configuración, en
`(panel)/configuracion/integraciones`, reutilizando el diseño de PAN-ONB-03 tal cual.**

Los tres motivos, en orden de peso:

1. **HU-E2-05 no es un paso, es una consulta recurrente.** La hace el Administrador *o el Operador*,
   «antes de depender de ellas». Un paso de onboarding se atraviesa una vez; esto se mira cada vez
   que algo falla.
2. **El propio prototipo dice que es opcional.** El pie de PAN-ONB-03 ofrece «Configurar esto
   después» — nunca fue una compuerta.
3. **El épico 1 ya decidió lo contrario y está mergeado.** El dashboard se desbloquea al completar
   los pasos 1 y 2; meter un paso 3 obligatorio ahora rompería a las empresas ya registradas.

Consecuencias explícitas:

- El código de pantalla que se usa en el código y en los planes es **PAN-CFG-INT**, el de las
  historias. PAN-ONB-03 queda como el origen del diseño visual, y la grilla de cuatro tarjetas se
  toma de ahí sin rediseñar nada.
- **El onboarding no gana un paso 3.** El indicador «PASO 3 DE 3» del prototipo no se replica.
- Entrar a la pantalla requiere Administrador para conectar y desconectar; ver el estado lo permite
  también el Operador, como pide HU-E2-05.

### Decisión escalada a ADR — [ADR-0003](../adr/0003-integrations-open-host-service.md), `Accepted`

**El Context Map (`docs/architecture.md` §4) no tiene ninguna fila para `integrations`.** No figura
como upstream ni como downstream de nadie, y este épico necesita que al menos `identity` lo consuma
(la unidad `padron-y-datos-fiscales`), con `billing`, `payments`, `conversational` y
`spreadsheet_sync` detrás en los épicos 5, 6, 8 y 4 — todos por el mismo motivo: obtener una
credencial validada.

Se escaló a ADR el mismo 2026-08-18, porque modificar el Context Map es arquitectura y un mapa de
unidades reparte trabajo. [ADR-0003](../adr/0003-integrations-open-host-service.md) propone declarar
`integrations` como **OHS (Open Host Service)** — un único contrato en su capa de aplicación que
cualquier contexto puede llamar, sin que `integrations` conozca a ninguno de sus consumidores y sin
que la clave de cifrado salga nunca del contexto. Quedó **`Accepted` con el merge del PR #6**, que
es lo que destraba el Gate 1 de `mecanismo-de-integraciones`.

### Estado

**Cerrado en código** (2026-08-20). Las cinco unidades pasaron sus tres gates y están en
`develop`: PRs [#7](https://github.com/cheatsheet12/CheatSheet/pull/7) y
[#8](https://github.com/cheatsheet12/CheatSheet/pull/8) (`mecanismo-de-integraciones`),
[#9](https://github.com/cheatsheet12/CheatSheet/pull/9) (`conexion-whatsapp`),
[#11](https://github.com/cheatsheet12/CheatSheet/pull/11) (`conexion-arca`),
[#12](https://github.com/cheatsheet12/CheatSheet/pull/12) (`padron-y-datos-fiscales`) y
[#13](https://github.com/cheatsheet12/CheatSheet/pull/13) (`conexion-mercadopago`).

**Cerrado en código no es cerrado.** El criterio de demo que le puso el roadmap §1 es «PAN-CFG-INT
mostrando ARCA y MercadoPago **conectados de verdad**», y los tres proveedores corren hoy contra
adaptadores simulados. Ese último paso no es código: son las credenciales de ARCA homologación,
de la aplicación de MercadoPago y del usuario de sistema de Meta, y está en [`TODO.md`](TODO.md) §5.
El reloj que manda es el de Meta: 24 a 72 horas por número (HU-E2-03 RN-02).

### Fuera de alcance de este épico

- **HU-E2-04 — vincular planilla de Google Sheets o Excel** → épico 4. El roadmap §4 la separó de
  las otras tres: sus criterios de aceptación terminan en PAN-ING-02 revisando el mapeo, o sea que
  es el primer paso del flujo de ingesta y no una integración más. La tarjeta «Google Sheets» de la
  pantalla existe desde la unidad 1, pero **sin acción**, hasta el épico 4.
- **Emitir un comprobante con la credencial de ARCA** → épico 5. Acá la credencial se carga, se
  cifra y se valida; nada la usa todavía.
- **Generar un link de cobro con el token de MercadoPago** → épico 6.
- **Que el agente responda por el número de WhatsApp** → épico 8. Acá la línea queda verificada y en
  silencio.
- **Centro de notificaciones** → épico 10. Este épico notifica al Administrador por los canales que
  ya existen; no construye la bandeja donde leerlas.

---

## Épico 3 — Catálogo de clientes y servicios

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **catalogo-de-clientes** | HU-E4-01 — el agregado `Cliente` y la tabla `cliente` del DER, con `origen` (`origen_dato`: PLANILLA · PANEL · AGENTE) asignado por el sistema y no editable (RN-01) y `presente_en_planilla` desde la primera migración. Unicidad de CUIT por empresa (RN-03) como índice único parcial sobre (`empresa_id`, `cuit`), no como chequeo en aplicación. Validación contra el padrón de ARCA al crear y al editar (RN-02), llamando a `ConsultarPadron` de `integrations` y reutilizando el patrón de tres estados que dejó `padron-y-datos-fiscales` — encontrado completa razón social y `CondicionIVA`, no encontrado bloquea, no disponible **no** bloquea. Pantalla PAN-DM-01: listado con nombre, CUIT, origen, WhatsApp y estado, más el formulario de alta y edición. Trae además los cimientos del contexto, que ninguna otra unidad va a tener que volver a decidir: repositorio con RLS por `empresa_id`, la migración inicial de `master_data` y el `features/master_data` del frontend con su `index.ts` |
| **catalogo-de-servicios** | HU-E4-02 — agregado `Servicio` y tabla `servicio`: `precio` en `Decimal` (nunca `float`, `CLAUDE.md` §3.5), `alicuota_iva` como enum cerrado de tres valores —0 %, 10,5 % y 21 % (RN-02)—, el par `agendable` / `duracion_estandar_min` con el invariante de RN-03 vivo en el dominio y no en el formulario, y la desactivación que oculta del catálogo activo sin tocar comprobantes ni turnos históricos (RN-04). Pantalla PAN-DM-02 con listado y formulario. El criterio «edito el precio y los comprobantes emitidos mantienen el suyo» **no se implementa acá**: es la desnormalización que el DER ya declara para `comprobante`, y se verifica en el épico 5 |
| **categorias-y-clasificacion** | HU-E4-03 y HU-E4-04 — agregado `CategoriaEmpresa` con `nombre` y `aplica_a`, unicidad por (`empresa_id`, `nombre`, `aplica_a`) (RN-02) y eliminación que desclasifica sin tocar el resto de los datos del elemento (RN-03), sobre PAN-DM-03. Encima de eso, la asignación de HU-E4-04 sobre las dos pantallas que para entonces ya existen: validación de ámbito (RN-01), varias categorías por elemento (RN-02, ver D8) y el filtro por categoría en los dos listados |

### Orden

```
catalogo-de-clientes ── catalogo-de-servicios ── categorias-y-clasificacion
```

Cadena lineal, un responsable, sin paralelismo.

**Las categorías van últimas aunque el DER ponga la FK `categoria_id` dentro de `cliente` y
`servicio`.** Ese orden de lectura es tentador y es el equivocado: HU-E4-04 —asignar y filtrar— no
se puede demostrar sin elementos que clasificar, así que arrancar por ahí entregaría una pantalla
que crea categorías que no clasifican nada, y dejaría media historia colgada de una unidad
posterior. La tabla de enlace la agrega la tercera migración; para eso está Alembic.

### Notas

- **Tres unidades para cuatro historias**, que es el punto medio entre los dos épicos anteriores y
  no una posición cómoda: el épico 1 agrupó ocho historias en tres unidades porque eran diminutas,
  el épico 2 abrió cinco unidades para cuatro historias porque cada una era un protocolo distinto.
  Acá las cuatro viven en un solo contexto y ninguna habla un protocolo propio, pero son **tres
  pantallas** del mapa de navegación y dos de las historias están marcadas Complejidad Media.
- **La alternativa descartada era juntar clientes y servicios en una sola unidad.** Tiene a favor
  que las dos son el mismo ABM con distinta forma. Se descartó porque ese PR juntaría la única
  llamada externa del épico —el padrón de ARCA— con la única regla de dinero —precio y alícuota—,
  que son dos superficies de test que no se parecen en nada, y porque dos pantallas del mapa de
  navegación son dos pantallas. Se paga con una ceremonia de PR más.
- **Una rama y un PR por unidad**, como el épico 2 y a diferencia del épico 1. Acá no hay ningún
  reloj externo que lo obligue, pero tampoco hay nada que lo desaconseje, y tres PRs de ABM se
  revisan mejor que uno con tres pantallas.
- **`catalogo-de-servicios` depende de `catalogo-de-clientes` sólo por el andamiaje del contexto**
  —repositorio, migración inicial, feature del frontend—, no por los datos: las dos tablas no se
  miran entre sí. Si alguna vez hay un segundo responsable, ese es el punto de corte natural
  (regla 1c), y cuesta poco: se adelanta la migración inicial a la primera unidad y se paraleliza.
- **`master_data` es Supporting, no Core.** Nada de este épico emite comprobantes ni mueve dinero.
  Lo que sí hace es fijar el vocabulario que después consumen `billing`, `payments`, `scheduling` y
  `conversational` (Context Map §4, fila C/S). Un nombre mal puesto acá se paga cuatro veces.
- **`origen` y `presente_en_planilla` entran en la primera migración aunque este épico sólo escriba
  `PANEL`.** Son ADR-006 y ADR-007 hechos columna, y el épico 4 los lee para decidir qué sobrescribe
  la planilla y qué se marca ausente. Agregarlas después sería un backfill sobre datos reales.

### Decisión D8 — un elemento puede tener varias categorías, y el DER modela una sola

`cliente` y `servicio` traen en el DER una columna `categoria_id uuid FK → categoria_empresa`: una
categoría por elemento. **HU-E4-04 RN-02 dice lo contrario**, sin ambigüedad: «un cliente o servicio
puede tener más de una categoría asignada». No hay lectura que concilie las dos cosas.

**Resolución (2026-08-31): gana la historia. Se modela con dos tablas de enlace,
`cliente_categoria` y `servicio_categoria`, y la columna `categoria_id` no se crea.**

El precedente es H1, el hueco que el propio DER declara: cuando el DER y una historia se
contradicen, el DER es un boceto y la historia es el requisito. Acá además la columna todavía no
existe en ninguna base, así que la divergencia no cuesta una migración de datos — sólo cuesta
decirla.

Consecuencias explícitas:

- **El DER entregado queda desactualizado en dos tablas.** Es un insumo de Etapa 5 y no se reescribe
  (regla del workflow); la divergencia se documenta acá y en el plan de `categorias-y-clasificacion`.
- La unicidad de RN-02 de HU-E4-03 sigue siendo sobre `categoria_empresa`, no sobre el enlace.
- El filtro «filtrable por esa categoría» de HU-E4-04 pasa a ser un `JOIN`, no un `WHERE` sobre una
  columna. Es la parte que se paga, y es barata.

### Decisión D9 — el ámbito «ambos» no existe en el enum del DER

HU-E4-03 RN-01 dice que cada categoría tiene un ámbito «(clientes, servicios o ambos)». El enum
`aplica_a` del DER tiene cuatro valores —`CLIENTE · SERVICIO · FAQ · TURNO`— y ninguno es «ambos».

**Resolución (2026-08-31): se agrega el valor `AMBOS` al enum, y la pantalla PAN-DM-03 ofrece
solamente los tres que le corresponden: `CLIENTE`, `SERVICIO` y `AMBOS`.**

`FAQ` y `TURNO` quedan en el enum sin uso hasta los épicos 8 y 7, que son sus dueños. La
alternativa era no ofrecer «ambos» y obligar a elegir uno, que es más limpio en la base y
directamente incumple RN-01.

Consecuencia para la validación de ámbito de HU-E4-04 RN-01: una categoría es asignable a un cliente
si su `aplica_a` es `CLIENTE` o `AMBOS`, y a un servicio si es `SERVICIO` o `AMBOS`. Esa regla vive
en el dominio de `CategoriaEmpresa`, no en el filtro del combo.

### Hueco P10 — PAN-DM-01, PAN-DM-02 y PAN-DM-03 no tienen prototipo

Las tres pantallas están en el mapa de navegación de Etapa 5, con su código y sus roles
(Admin · Operador), pero **ninguna está maquetada**: no hay `datos-maestros.html` en
`inputs/prototipos/`. Es exactamente el hueco P9, el de PAN-USR-01 y PAN-USR-02, que el épico 1 ya
atravesó.

Se resuelve igual, porque funcionó: se construyen con el catálogo de componentes del PDF §1.3 y los
tokens ya importados, reusando el listado y el formulario que `usuarios-y-preferencias` dejó en el
sistema de diseño. Si el prototipo aparece, se ajustan. No es una decisión de este mapa; se anota
para que nadie lo descubra a mitad de la unidad y crea que falta un insumo.

### Decisión D85 — el formato de los datos se normaliza una sola vez, en la entrada común de `master_data` · ADR-0009

Panel, planilla y agente escriben `Cliente`, `Servicio` y `CategoriaEmpresa`, y cada camino los
guardaba como llegaban. Eso produce duplicados aparentes («Vip» y «VIP») y falsos cambios en la
resincronización (HU-E4-05, HU-E3-03, HU-E3-04, HU-E3-07, HU-E4-01).

**La normalización es una regla de dominio de `master_data`, idempotente, y se aplica una sola vez
en el punto de entrada común, sea cual sea el camino.** Ingesta y agente la alcanzan por la capa de
`application` de `master_data` (R3). En la resincronización se compara el valor normalizado de la
planilla con el normalizado almacenado, de modo que una diferencia que desaparece al normalizar no
es un cambio; la planilla original nunca se reescribe (ADR-007, HU-E3-07 RN-02). Los identificadores
que ya se normalizan (email, teléfono, CUIT en `shared/`) se citan y no se rehacen. Los textos libres
solo reciben la limpieza de espacios, y los comprobantes emitidos nunca se modifican porque sus datos
están desnormalizados a propósito.

Las reglas de mayúsculas de HU-E4-05 son deliberadas: una palabra se capitaliza solo si viene toda en
mayúsculas o toda en minúsculas, de modo que «McDonald» se preserva; las siglas societarias y las
palabras en mayúsculas de hasta 4 letras se conservan; y un cliente es razón social si su CUIT
empieza con 30, 33 o 34.

**Para el Gate 1 de `normalizacion-de-datos`:**

- Dónde vive el normalizador (funciones puras del dominio) y cómo se cablean las tres entradas.
- La unicidad de categoría y de CUIT pasa a evaluarse sobre el valor normalizado, sin distinguir
  mayúsculas; el índice único actual de categoría hay que revisarlo.
- La corrección única de datos existentes: informe previo (dry-run), respaldo restaurable de los
  valores originales —y dónde se guarda—, los casos que colisionarían con una unicidad se informan y no
  se cambian, y no toca comprobantes ni hojas.

**Lo que se paga:** falsos positivos de siglas («SUR» queda en mayúsculas) y que las tildes no se
agreguen ni se quiten nunca, así que «Maria» no se corrige a «María».

**Cómo se resolvió en el Gate 1 de `normalizacion-de-datos` (2026-10-01):** la corrección única de
datos existentes (RN-09) se partió en la unidad `correccion-de-datos-existentes`; el normalizador vive
en `master_data/domain/normalizacion.py` y el índice `lower(nombre)` de categoría no cambia.

**Números de migración reservados** (las cadenas de ramas parten de cabezas distintas): `0028`
`limites-e-intervalo-de-turnos`, `0029` `tipos-de-comprobante-por-receptor` (renumera su `0026`),
`0030` `correccion-de-datos-existentes`. Al rebasar sobre `develop` se re-apunta el `down_revision`, y
antes de cada PR `alembic heads` tiene que dar una sola cabeza.

### Decisión D86 — un servicio agendable dura entre 5 y 480 minutos · ADR-0009

HU-E4-02 RN-03 exige duración a los servicios agendables, pero ninguna regla la acotaba, y esa
duración es la del turno (D96) y decide la grilla de la agenda.

**La duración estándar es un entero de minutos entre 5 y 480, en panel, ingesta de planilla y agente
por igual** (HU-E4-02 RN-05). Una fila de planilla fuera de rango se marca con error y no aborta el
resto del procesamiento (HU-E3-03 RN-02).

**Para el Gate 1 de `duracion-de-servicios`:** el invariante vive en el dominio de `Servicio` y se
refuerza con una restricción en la base. Hay que decidir qué se hace con los servicios existentes
que estén fuera de rango (informe previo y corrección explícita, sin cambios silenciosos).

### Lo que se alinea de paso

Dos cosas que este épico toca inevitablemente y conviene que no se descubran dentro de una rama:

- **`CUIT` se muda a `shared/fiscal.py`.** Hoy vive en `identity/domain/valores.py`, y el docstring
  de `shared/fiscal.py` ya dejó escrita la regla: «`CUIT` stays in `identity` … A value object moves
  here when a second context needs it, never in anticipation». `Cliente.cuit` es ese segundo
  contexto. La mudanza es la misma que ya se hizo con `CondicionIVA` y con `RolUsuario`:
  `identity/domain/valores.py` lo re-exporta y ningún import existente se rompe. Le toca a
  `catalogo-de-clientes`.
- **La fila del Context Map de `integrations` no nombra a `master_data`.** Enumera
  `identity, spreadsheet_sync, billing, payments, conversational`, y este épico agrega un consumidor.
  **No hace falta un ADR nuevo**: [ADR-0003](../adr/0003-integrations-open-host-service.md) ya
  decidió que `integrations` es un OHS que **cualquier** contexto puede llamar, y la lista de la
  tabla es la enumeración de los consumidores conocidos al escribirla, no una lista blanca. Se
  agrega `master_data` a esa celda de `docs/architecture.md` §4 en la unidad que estrena el edge.

### Preguntas que resuelve el Gate 1 de cada unidad

No se responden acá —el mapa reparte trabajo, no diseña— pero se dejan escritas para que el plan de
cada unidad las encare en vez de tropezarlas:

| # | Pregunta | Unidad |
|---|---|---|
| 1 | ¿Se puede crear un cliente **sin** CUIT? El DER lo deja nullable y un consumidor final no tiene uno; HU-E4-01 RN-02 habla como si siempre hubiera CUIT que validar | `catalogo-de-clientes` |
| 2 | ¿Qué pasa cuando la empresa **todavía no conectó ARCA**? El padrón necesita certificado, y la integración es opcional. El precedente de `padron-y-datos-fiscales` es que «no se pudo preguntar» no bloquea; falta decidir si eso alcanza para un alta de cliente o si hace falta decirlo en la pantalla | `catalogo-de-clientes` |
| 3 | ¿Un cliente se **elimina** o sólo se desactiva? El DER tiene `activo` y ADR-007 dice que lo que sale de la planilla se marca ausente y nunca se borra; HU-E4-01 habla de crear y editar, nunca de borrar | `catalogo-de-clientes` |
| 4 | ¿La alícuota de IVA es un enum propio de `master_data` o sale de `reference_data`, que es el contexto dueño del catálogo fiscal (`tipo_catalogo_fiscal: ALICUOTA_IVA`)? RN-02 la declara cerrada de tres valores; el épico 5 la va a necesitar vigente por fecha | `catalogo-de-servicios` |

### Estado

**Mapa aprobado el 2026-08-31**, junto con D8 y D9. Responsable de las tres unidades: Cristian.

- `catalogo-de-clientes` — mergeada el 2026-09-01, [#23](https://github.com/cheatsheet12/CheatSheet/pull/23).
- `catalogo-de-servicios` — mergeada el 2026-09-01, [#25](https://github.com/cheatsheet12/CheatSheet/pull/25).
- `categorias-y-clasificacion` — mergeada el 2026-09-01, [#26](https://github.com/cheatsheet12/CheatSheet/pull/26).

**Épico cerrado.** Las cuatro historias (HU-E4-01 … HU-E4-04) y las tres pantallas
(PAN-DM-01, PAN-DM-02, PAN-DM-03) están en `develop`. El criterio de demo del roadmap §1 —«ABM
completo de clientes (con CUIT validado contra ARCA) y de servicios (precio, IVA, agendable),
clasificados por categorías propias de la empresa»— se cumple, con una salvedad heredada del épico
2: el padrón de ARCA corre contra su adaptador simulado hasta que existan las credenciales de
homologación ([`TODO.md`](TODO.md) §5).

**La última fila de un épico necesita su propio PR, siempre.** El paso `en revisión` → `mergeada` no
puede ocurrir dentro del PR de la unidad, porque el merge pasa después; y a diferencia de las dos
anteriores, esta no tiene una unidad siguiente que se la lleve de paso. Pasó tres veces en este
épico y las tres se resolvieron distinto: [#24](https://github.com/cheatsheet12/CheatSheet/pull/24)
con un PR aparte —que chocó con #25—, la de servicios dentro del PR de la unidad que seguía, y esta
con un PR de cierre. **Para el épico 4: llevar la fila de la unidad anterior en el PR de la
siguiente, y cerrar la última con un PR propio.**

**Las dos filas de estado se mueven en el PR de la unidad que sigue, y no en uno propio.** El
épico ya pagó una vez el precio de hacerlo aparte: [#24](https://github.com/cheatsheet12/CheatSheet/pull/24)
movió la fila de `catalogo-de-clientes` mientras [#25](https://github.com/cheatsheet12/CheatSheet/pull/25)
movía la de `catalogo-de-servicios`, y **chocaron**. La regla 1c del workflow dice que dos filas
distintas son dos líneas distintas y git las mezcla sin conflicto; es cierto para filas lejanas y
falso para filas **contiguas**, que es como quedan siempre las unidades de un mismo épico. Git
necesita al menos una línea sin cambiar entre dos modificaciones para separarlas en hunks.

**El mapa viaja en el PR de esa unidad**, no en uno propio: la rama de la unidad se cortó del commit
del mapa, que es lo mismo que hizo el épico 2 con `mecanismo-de-integraciones`.

### Fuera de alcance de este épico

- **Poblar el catálogo desde una planilla** (HU-E2-04, HU-E3-01 … HU-E3-07) → épico 4. Este épico
  deja las columnas que esa ingesta necesita, y nada más.
- **Escribir de vuelta en la planilla lo que se crea desde el panel** (HU-E3-07) → épico 4.
- **Que un cliente reciba un comprobante** → épico 5; **que tenga un cobro** → épico 6; **que reserve
  un turno** → épico 7; **que el agente lo consulte por WhatsApp** → épico 8. Acá el catálogo existe
  y todavía no lo consume nadie.
- **Importación masiva por CSV o alta múltiple.** Ninguna historia la pide, y la vía de carga masiva
  del producto es la planilla.
- **Historial de cambios de un cliente o un servicio** más allá de lo que ya registra la bitácora del
  épico 1.

---

## Épico 4 — Sincronización de planillas

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **dlq-y-tareas-asincronas** | HS-T6 — el agregado `TareaAsincrona` y su tabla, con `intentos`, el máximo configurado y la máquina de estados que ADR-009 ya declara, más la derivación a la cola de fallos al agotar los reintentos (RN-02) y el evento `TareaAsincronaDerivadaADLQ` en la bitácora del épico 1 (RN-04). Sin pantalla: leer la DLQ es el épico 10. Va primera por la misma razón por la que `cimientos-y-bitacora` abrió el épico 1 — es el sumidero que todo lo demás necesita, y este épico es el primero que mete trabajo asíncrono pesado de verdad. Sin ella, una fila envenenada en la carga inicial reintenta para siempre y traba la cola `ingesta` entera (RN-03) |
| **vinculo-de-planilla** | HU-E2-04 — el agregado `VinculoDePlanilla` y su tabla, y **las tres vías por las que una planilla entra al sistema**: OAuth2 de Google con permiso de lectura sobre el archivo elegido y no sobre todo el Drive (RN-01), Excel Online, y el archivo subido a mano (ver D10). Registra proveedor, dirección de sincronización y hojas involucradas (RN-02). Pantalla PAN-ING-01 con la zona de arrastre y el vínculo, más `Cargas recientes` todavía vacío. Trae además los cimientos del contexto que ninguna otra unidad va a volver a decidir: repositorio con RLS por `empresa_id`, la migración inicial de `spreadsheet_sync`, el almacenamiento del archivo en R2 y el `features/spreadsheet_sync` del frontend con su `index.ts` |
| **mapeo-asistido** | HU-E3-01 y HU-E3-02 — los agregados `Mapeo` y `EntradaDeMapeo`: el modelo propone la asignación de cada columna al esquema interno con un nivel de confianza (RN-01), la `huella_encabezado` permite reutilizar el mapeo mientras la estructura no cambie (RN-02), y las columnas de confianza Baja quedan `Sin asignar` (RN-03). Encima, la revisión de HU-E3-02 sobre PAN-ING-02: corrección manual, vista previa, y el bloqueo de `Confirmar y procesar` mientras falte una columna obligatoria. **Es el primer LLM del sistema** — ver D11 y D12 |
| **carga-y-errores** | HU-E3-03, HU-E3-05 y HU-E3-06 — el agregado `ProcesamientoDePlanilla` con `ErrorDeFila`, la tarea asíncrona que lee el archivo y escribe `Cliente` y `Servicio` en `master_data` con `origen = PLANILLA`, y el aislamiento de RN-02: una fila inválida se marca y no aborta el resto. Validaciones de entrada de HU-E3-03 (formatos `.xlsx`/`.xls`/`.csv`, límite de 25 MB). Pantalla PAN-ING-03 con el resumen, el detalle por fila con su número original y su motivo, y la descarga del listado de errores (RN-03), en solo lectura para el rol Solo Lectura (RN-04). El reprocesamiento de HU-E3-06 reutiliza el mapeo confirmado, no duplica lo ya procesado y queda vinculado al procesamiento original |
| **sincronizacion-y-write-back** | HU-E3-04 y HU-E3-07 — la sincronización incremental que procesa solo lo nuevo o modificado desde `ultima_lectura`, la detección de cambio de estructura que **pausa** la sincronización y manda a revisar el mapeo (RN-03), y la escritura de vuelta: solo sobre vínculos `LECTURA_Y_ESCRITURA`, solo sobre la hoja propia protegida del sistema y nunca sobre la hoja original de la empresa, y solo para registros con `origen` PANEL o AGENTE — que es el mecanismo anti-bucle de ADR-007 hecho código. Excel Online no escribe: es de solo lectura, y la pantalla lo dice |

### Orden

```
dlq-y-tareas-asincronas ───────────────┐
                                       ├─ carga-y-errores ── sincronizacion-y-write-back
vinculo-de-planilla ── mapeo-asistido ─┘
```

Las dos primeras no dependen de nada y son las únicas del proyecto hasta hoy que **podrían ir en
paralelo** si hubiera dos responsables. No los hay, así que se hacen en ese orden y la observación
queda escrita por si eso cambia (regla 1c).

**`carga-y-errores` es la única que espera a dos.** Necesita el mapeo confirmado para saber qué
significa cada columna, y necesita la DLQ porque es la primera tarea del sistema que procesa miles
de filas de datos ajenos: es exactamente donde un reintento infinito duele.

### Notas

- **Cinco unidades para nueve historias**, y es el épico más grande hasta ahora: `spreadsheet_sync`
  hoy son cuatro `__init__.py` vacíos, hay **cinco tablas nuevas** del DER más la de `TareaAsincrona`,
  y **tres pantallas**. No se agrupa más porque cada unidad habla un protocolo distinto —OAuth2 de
  Google, un LLM, lectura de archivos binarios, escritura remota— que es el mismo criterio por el que
  el épico 2 abrió cinco unidades para cuatro historias.
- **Todo el épico comparte una sola rama** (`feature/spreadsheet_sync-sincronizacion-de-planillas`),
  decisión del **2026-09-07**, igual que el épico 1 el 2026-08-13. Cada unidad es **uno o más commits**
  con su propio mensaje, no un PR. **Lo que se gana:** una sola ceremonia de PR en lugar de cinco
  encadenadas, y ningún rebase entre unidades que dependen unas de otras — que acá son casi todas.
  **Lo que se paga:** un PR con nueve historias y seis tablas, y un revert que se lleva el épico
  entero. Los **gates 1 y 2 siguen siendo por unidad**; lo unificado es la rama y el gate 3.
- **La fila de estado de cada unidad se mueve en el commit de la unidad siguiente**, nunca en uno
  propio, por lo que le pasó al épico 3 con [#24](https://github.com/cheatsheet12/CheatSheet/pull/24)
  y [#25](https://github.com/cheatsheet12/CheatSheet/pull/25): filas contiguas del mismo épico chocan
  porque git necesita al menos una línea sin cambiar entre dos modificaciones. Acá el riesgo es menor
  —una sola rama— pero la regla se mantiene.
- **HS-T6 entra en este épico y no en el 1, aunque sea infraestructura.** El épico 1 la declaró deuda
  con dueño explícito («No hay DLQ → épico 4», `TODO.md` §3). Llega ahora porque ahora hay quien la
  use: hasta este épico, el trabajo asíncrono del sistema era mandar un mail y sondear una API.

### Decisión D10 — el archivo subido a mano no tiene proveedor en el DER

`proveedor_planilla` tiene exactamente dos valores, `GOOGLE_SHEETS` y `EXCEL_ONLINE`. Pero
HU-E3-03 tiene dos criterios de aceptación sobre **subir un archivo** —«Formato no aceptado. Use
.xlsx, .xls o .csv.» y «El archivo supera el límite de 25 MB.»— y el prototipo `ingesta.html` tiene
la zona de arrastre al lado del botón de vincular. La vía existe, el enum no la contempla, y
`procesamiento_de_planilla.vinculo_id` es `NN`: un procesamiento **tiene** que colgar de un vínculo.

**Se agrega `ARCHIVO` al enum.** Un archivo subido es un vínculo con `direccion = SOLO_LECTURA`, sin
credencial OAuth, cuyo `hoja_empresa` es la hoja del libro y cuya referencia vive en R2. Con eso el
`vinculo_id` obligatorio sigue siendo cierto, y las unidades 3, 4 y 5 tratan las tres vías igual en
lugar de arrastrar dos caminos paralelos por todo el contexto.

**Lo que se paga, dicho de frente:** queda un «vínculo» que no vincula nada — no hay a qué volver a
leer, porque el archivo es una foto. La sincronización incremental de HU-E3-04 y el write-back de
HU-E3-07 **no aplican** a `ARCHIVO` y tienen que decirlo explícitamente, igual que ya lo dicen para
`EXCEL_ONLINE`. Es una guarda más en la unidad 5.

**Alternativa descartada:** hacer `vinculo_id` nullable. Cuesta un `None` en cada consulta del
contexto y en cada guarda de escritura, para siempre, a cambio de no tocar un enum.

**Por eso la subida vive en `vinculo-de-planilla` y no en `carga-y-errores`:** esa unidad es «cómo
entra una planilla al sistema», por cualquiera de las tres vías. Procesar los bytes es la unidad 4.

### Decisión D11 — no hay proveedor de LLM elegido, y este épico lo necesita · **escala a ADR**

[`docs/architecture.md`](../architecture.md) declara el puerto `PortModeloDeLenguaje` y lo asigna a
`spreadsheet_sync` y `conversational`, y reserva el worker 8 para llamadas de LLM. **Ningún documento
elige un proveedor**, y los ADR del repositorio van del 0001 al 0006 sin tocar el tema.

`mapeo-asistido` es el primer consumidor. La decisión no es de una unidad —la hereda el épico 8
entero, que es el agente conversacional— así que **es un ADR**, y va antes del Gate 1 de esa unidad.
Tiene que cubrir: proveedor y modelo, dónde viven los prompts versionados (`CLAUDE.md` §5), el schema
contra el que se valida cada respuesta, timeout y límite de tokens, y qué hace el sistema cuando el
modelo no contesta — que para el mapeo es degradar a «todas las columnas Sin asignar» y dejar que el
usuario mapee a mano, nunca bloquear la ingesta.

### Decisión D12 — al modelo se le mandan encabezados, nunca filas

`CLAUDE.md` §3.6 es absoluto: **nunca se mandan datos personales o fiscales reales a un LLM sin
anonimizar**. Y HU-E3-02 pide mostrar «un ejemplo de dato» por columna en la revisión del mapeo, lo
que invita a mandarle filas de muestra al modelo para que infiera mejor. Son clientes reales: nombre,
CUIT, teléfono, dirección.

**El modelo recibe únicamente los nombres de las columnas** y el catálogo de atributos internos de
destino. El ejemplo de dato de PAN-ING-02 se lee de la planilla y se muestra en pantalla **sin pasar
por el modelo**. La huella de encabezado de RN-02 se calcula sobre los nombres de columna, que es lo
único que el modelo vio, así que la reutilización del mapeo tampoco filtra nada.

**Lo que se paga:** un encabezado ambiguo (`Codigo`, `Tipo`, `Nro`) se resuelve peor sin ver datos, y
va a caer más seguido en confianza Baja. Eso es exactamente lo que RN-03 manda hacer con la confianza
Baja —marcarla `Sin asignar` y pedir intervención manual—, así que el modo de falla ya está diseñado.
Se prefiere un mapeo que pregunta más a uno que filtra datos de clientes.

### Preguntas que resuelve el Gate 1 de cada unidad

- **`dlq-y-tareas-asincronas`** — ¿`TareaAsincrona` es una tabla propia de `observability` o el
  registro que ya escribe cada worker? ¿La DLQ es una cola de Celery, una tabla, o las dos?
- **`vinculo-de-planilla`** — ¿el OAuth2 de Google reusa el mecanismo de `integrations` del épico 2
  (`ConfiguracionDeIntegracion`, credencial cifrada) o es propio? La FK
  `vinculo_de_planilla.configuracion_integracion_id` sugiere lo primero, y eso decide si esta unidad
  toca dos contextos.
- **`mapeo-asistido`** — ¿cuáles son las columnas «obligatorias» de RN-02, y salen de los agregados
  `Cliente` y `Servicio` del épico 3 o de una lista propia?
- **`carga-y-errores`** — ¿una fila de planilla puede crear un `Cliente` **y** un `Servicio`, o cada
  vínculo apunta a una sola entidad de destino? El DER no lo dice y cambia el mapeo entero.
- **`sincronizacion-y-write-back`** — ¿cada cuánto corre el sondeo, y en qué cola? ¿Qué detecta el
  cambio de estructura: la huella de encabezado de RN-02, o algo más barato?

### Estado

**Mapa aprobado el 2026-09-07.** Responsable de las cinco unidades: Cristian.

Las cinco están **mergeadas a `develop`** el 2026-09-13, en una sola rama
(`feature/spreadsheet_sync-sincronizacion-de-planillas`), un commit por unidad, por el
PR [#28](https://github.com/cheatsheet12/CheatSheet/pull/28). El Gate 3 quedó cerrado ahí.

La corrida con la que se cierran las cinco, **con PostgreSQL y Redis reales**:

```
ruff format --check .   335 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 335 source files
guard_architecture      361 file(s) checked - architecture boundaries intact
pytest --cov            969 passed - 0 skipped - cobertura 94%  (umbral 80)
alembic current         0015 (head)
frontend lint           No ESLint warnings or errors
frontend test:coverage  386 passed - 85.84 % lineas
frontend build          compila
```

**Lo que el épico no cierra:** los dos criterios de lectura incremental de HU-E3-04 («se
modifica una fila», «se agregan filas nuevas»). El write-back y la detección de cambio de
estructura están; falta el token OAuth por empresa para volver a leer la hoja viva. Dicho en
`units/sincronizacion-y-write-back.md` y en `TODO.md`.

### Fuera de alcance de este épico

- **Leer la DLQ desde el panel.** HS-T6 deja el sumidero y el evento en la bitácora; la pantalla es
  del **épico 10**, igual que pasó con HS-T5 en el épico 1.
- **Que el agente de WhatsApp escriba en la planilla.** HU-E3-07 RN-03 nombra el origen `AGENTE`, y
  la guarda se construye acá, pero quien lo produce llega en el **épico 8**.
- **Emitir un comprobante a un cliente ingerido** → épico 5. Acá el catálogo se puebla y todavía no
  lo consume nadie.
- **Reprocesamiento manual de una tarea de la DLQ.** HS-T6 RN-04 pide que el evento quede registrado
  «para permitir su análisis y eventual reprocesamiento manual»: se registra, y el reprocesamiento se
  dispara a mano contra la cola, sin pantalla.
- **Más proveedores de planilla.** El DER cierra el enum en Google Sheets y Excel Online, y D10 le
  agrega el archivo suelto. Nada más.

---

## Épico 5 — Facturación electrónica

> **Este es el épico de mayor riesgo del sistema.** `CLAUDE.md` §1 lo dice de una:
> «**Legal/tax** — a wrongly issued document is irreversible». Un CAE no se deshace: lo
> único que existe para revertir una factura es otra factura, la nota de crédito, que
> también va a ARCA y también queda para siempre. Todo lo que sigue está ordenado por esa
> frase.

### Qué hace cada unidad

| Unidad | Alcance |
|---|---|
| **parametros-fiscales** | HS-T4 — la tabla `parametro_fiscal` del DER, sin `empresa_id` porque es el catálogo de ARCA y es igual para todas las empresas, **versionada por vigencia**: un parámetro nuevo no reemplaza al anterior (RN-02), y la facturación usa el que regía **el día de emisión** y no el de hoy (RN-03). La sincronización periódica desde ARCA, con la regla de falla de RN-04: si no se puede sincronizar, se conserva el último vigente y se registra el error — nunca se queda sin catálogo. Sin pantalla. Va primera por la misma razón que `cimientos-y-bitacora` y `dlq-y-tareas-asincronas`: es contra lo que la emisión valida, y una emisión que valida contra nada no valida |
| **puntos-de-venta** | HU-E5-05 — agregado `PuntoDeVenta` y su tabla: número, descripción, activo, y `numerador_por_tipo` (RN-02). Verificación contra ARCA de que el punto está habilitado antes de activarlo (RN-03), unicidad del número por empresa, y la desactivación que impide nuevas emisiones sin tocar las hechas (RN-04). Pantalla PAN-FAC-05. Trae además los cimientos de `billing` que ninguna otra unidad va a volver a decidir: repositorio con RLS, la migración inicial del contexto y el `features/billing` del frontend |
| **emision-de-comprobantes** | HU-E5-03, HU-E5-01 y HU-E5-02 — el corazón del épico. Agregado `Comprobante` con Single Table Inheritance (ADR-010) e `ItemDeComprobante`; la máquina de estados `BORRADOR → VALIDADO → ENVIADO_A_ARCA → AUTORIZADO / RECHAZADO`; el adaptador de **WSFEv1** (ver D13) consumiendo el ticket que `integrations` ya emite (ADR-0004); la emisión asíncrona de RN-04; la validación del CUIT receptor contra el padrón (RN-02) reusando lo que dejó `padron-y-datos-fiscales`; la tabla de combinaciones válidas emisor/receptor (RN-01, ver D16); y la numeración por punto de venta y tipo, que es la que no puede repetirse nunca (D14). Pantallas PAN-FAC-01, PAN-FAC-02 y PAN-FAC-03 |
| **nota-de-credito** | HU-E5-04 — la anulación total o parcial. `comprobante_origen_id` obligatorio contra un comprobante autorizado (RN-01), el tipo determinado por el del original (RN-02), el monto que no puede superarlo (RN-03), y el estado de anulación que el original refleja cuando ARCA autoriza (RN-05). Pantalla PAN-FAC-04. Reusa entera la máquina de emisión de la unidad anterior: una nota de crédito **es** un comprobante, con otro tipo y una referencia |

### Orden

```
parametros-fiscales ──┐
                      ├─ emision-de-comprobantes ── nota-de-credito
puntos-de-venta ──────┘
```

Las dos primeras no dependen de nada y podrían ir en paralelo. `emision-de-comprobantes`
espera a las dos: sin punto de venta habilitado no hay numeración fiscal (precondición de
HU-E5-03), y sin catálogo de parámetros no hay contra qué validar el tipo.

### Notas

- **Cuatro unidades para seis historias.** HU-E5-01 y HU-E5-02 —listado y detalle— **no son
  una unidad propia**, y esa es la decisión de corte que más vale explicar: un listado de
  comprobantes que todavía no se pueden emitir es una tabla vacía, y el épico 3 ya rechazó
  esa forma con las categorías. Al revés también: emitir sin poder ver el resultado no es
  verificable. Las tres viajan juntas, y la unidad es grande a propósito.
- **`nota-de-credito` sí se separa**, aunque sea el mismo agregado. No por tamaño: por
  **riesgo**. Es la única operación del sistema que puede reversar plata ya documentada
  ante ARCA, y merece su propio Gate 1 y su propia verificación en lugar de entrar como el
  último tercio de un PR que ya trae tres pantallas.
- **Una sola rama para el épico** (`feature/billing-facturacion-electronica`), unidades como
  commits, igual que los épicos 1 y 4. Gates 1 y 2 siguen siendo por unidad.
- **Lo que este épico hereda y no vuelve a construir:** el ticket de acceso a ARCA
  (ADR-0004, `integrations`), la consulta al padrón (`padron-y-datos-fiscales`), la DLQ
  (HS-T6, épico 4) y el catálogo de clientes (épico 3). Es el primer épico que se apoya
  casi enteramente en lo anterior.

### Decisión D13 — cómo habla `billing` con WSFEv1 · **escala a ADR**

[ADR-0004](../adr/0004-arca-wsaa-access-tickets.md) lo dejó dicho con nombre y apellido:
«ADR-012 stands and is not superseded. It decides how `billing` talks to **WSFEv1**, and
**epic 5 makes that call**». Ese ADR de Etapa 5 nombra **PyAfipWs**, y
`backend/pyproject.toml` lo anota como pendiente de llegar con este épico.

La pregunta es real y no está resuelta: PyAfipWs es una librería grande, con estado propio y
licencia GPL, y el épico 2 ya demostró que **no hacía falta** para WSAA — la firma CMS
salieron cuarenta líneas con `cryptography`. WSFEv1 es otra cosa: es una superficie SOAP
grande con semántica fiscal de verdad, donde equivocarse no es un bug sino un comprobante
mal emitido.

El ADR tiene que cerrar: PyAfipWs o un cliente propio sobre `defusedxml` —que ya está en el
proyecto y ya parsea SOAP de ARCA—, qué se gana y qué se paga en cada caso, y muy
concretamente **quién valida los montos antes de mandarlos**. Va antes del Gate 1 de
`emision-de-comprobantes`.

### Decisión D14 — la numeración no puede repetirse, y `jsonb` sola no lo garantiza

`punto_de_venta.numerador_por_tipo` es un `jsonb`, y la numeración es **independiente por
punto de venta y por tipo** (HU-E5-05 RN-02). Dos emisiones simultáneas sobre el mismo punto
y el mismo tipo tienen que sacar números distintos: si sacan el mismo, ARCA rechaza el
segundo —o peor, autoriza dos comprobantes con el mismo número, que es una inconsistencia
fiscal que hay que arreglar con la AFIP y no con un `UPDATE`.

Un `jsonb` leído y escrito sin candado es exactamente la carrera que produce eso. **Se
serializa con `SELECT … FOR UPDATE` sobre la fila del punto de venta**, que es el mismo
mecanismo con el que el épico 1 protegió el invariante del último Administrador, y por el
mismo motivo: es el único chequeo que no puede perder contra una segunda pestaña.

**Lo que se paga:** un candado por punto de venta. Dos operadores emitiendo a la vez sobre
el mismo punto se serializan. Es correcto y es lento, y es el precio de que la numeración
sea numeración.

### Decisión D15 — el redondeo del IVA se decide una vez, acá

`CLAUDE.md` §3.5 y §5 son terminantes: `Decimal` siempre, y redondeo **explícito** con
`quantize` y `ROUND_HALF_UP`. Lo que esas reglas no dicen es **dónde** se redondea, y en un
comprobante hay tres lugares posibles: por ítem, por alícuota, o sobre el total.

Se redondea **por ítem** al calcular su subtotal, y los totales son sumas de valores ya
redondeados. Es lo que hace que `subtotal + total_iva == total` sea cierto por construcción
y no por suerte, y es lo que ARCA valida: un comprobante cuyos totales no cierran contra la
suma de sus ítems se rechaza con un código que no explica que faltó un centavo.

Queda escrito acá, en el mapa, porque las tres unidades que tocan plata tienen que hacer lo
mismo y la tercera no puede descubrirlo leyendo la primera.

### Decisión D16 — la tabla de tipos válidos es regla de negocio, no parámetro de ARCA

HU-E5-03 RN-01 dice que el tipo disponible «se determina por la combinación de la condición
IVA del emisor y del receptor». Eso podría vivir en `parametro_fiscal` —es fiscal, y ARCA lo
publica— o en el dominio de `billing`.

**Va en el dominio de `billing`.** `parametro_fiscal` está versionado por vigencia porque
modela cosas que ARCA cambia: alícuotas, topes, códigos. La correspondencia A/B/C no es de
esas: es estructura del régimen —un Responsable Inscripto le factura A a otro Responsable
Inscripto y B a un Consumidor Final— y no cambia con una resolución trimestral. Modelarla
como parámetro versionado invitaría a que alguien la «actualice» sincronizando, y a que un
comprobante emitido ayer se valide contra la tabla de hoy.

**Lo que se paga:** si el régimen cambia de verdad, es un release y no una fila. Ha pasado
dos veces en veinte años.

### Decisión D87 — el tipo de comprobante sale de la condición del receptor, y el padrón es la fuente de verdad · ADR-0009

D16 dejó la tabla de tipos válidos en el dominio de `billing`. Esta decisión la completa y no la
contradice: sigue siendo un release y no una fila (HU-E5-03 RN-01, HU-E5-02, HU-E5-04).

**Tabla.** Responsable Inscripto emite Factura A a Responsable Inscripto y a Monotributo (RG 5003/2021,
con la leyenda de la Ley 27.618 en el detalle y en el PDF), y Factura B a Exento y a Consumidor Final;
Monotributo y Exento emiten siempre Factura C.

**El padrón de ARCA es la fuente de verdad de la condición del receptor.** Se consulta con el CUIT y se
reconsulta al confirmar la emisión: si difiere del resultado mostrado, se pide reconfirmar el tipo. La
condición del catálogo de clientes es dato de referencia y se actualiza con la del padrón, con registro
en la bitácora. Si el padrón no responde se usa la última condición confirmada, con su fecha; si nunca
hubo una, la emisión se bloquea. El comprobante guarda la condición usada, su origen y su fecha, y todo
comprobante y nota de crédito informa a ARCA `CondicionIVAReceptorId` (RG 5616/2024). Un CUIT existente
sin inscripción se trata como Consumidor Final o «IVA No Alcanzado», y no bloquea; uno inexistente sí.
El concepto es «Servicios», con período y vencimiento de pago obligatorios y, si nace de un turno, con
valores por defecto.

**Un receptor «IVA No Alcanzado» con emisor Responsable Inscripto recibe Factura B**, regla que
`arca-homologacion-completa` (D90) verifica contra homologación antes de darla por cerrada. Y HU-E5-03
ya no admite crear el cliente en el momento: el cliente existe en Datos Maestros (mismo criterio que
D92).

Fuentes de los hechos fiscales: RG 5003/2021, RG 5616/2024 y el manual WSFEv1 v4.7 del 2026-09-01.

**Modelo, para el Gate 1 de `tipos-de-comprobante-por-receptor`:** el enum `condicion_iva` no tiene
`IVA_NO_ALCANZADO`; `comprobante` no tiene concepto, período del servicio, vencimiento de pago ni
origen y fecha de la condición del receptor; `cliente` no guarda la fecha de última confirmación por
padrón. La consulta al padrón sigue por `integrations` (ADR-0003).

**Lo que se paga:** una llamada más al padrón al confirmar, y que cambiar la tabla sea un release.

### Decisión D88 — en Factura C, el precio del catálogo es el precio final · ADR-0009

El catálogo guarda el precio sin IVA y una alícuota (0, 10,5 o 21 %; HU-E4-02 RN-01 y RN-02), pero la
Factura C no discrimina IVA (HU-E5-03 RN-12).

**Para emisores Monotributo y Exento el precio del catálogo es el precio final, y la alícuota se
ignora:** no se muestra ni se aplica, el IVA es cero y el total es igual al subtotal. El redondeo por
ítem de D15 sigue rigiendo. Aplicar la alícuota inflaría el total de un comprobante que no puede
discriminarla.

**Para el Gate 1 de `tipos-de-comprobante-por-receptor`:** cómo se etiqueta la alícuota en la pantalla
de servicios cuando el emisor es Monotributo o Exento, y el test de redondeo de esta rama.

### Decisión D89 — la nota de crédito hereda el contexto fiscal del original · ADR-0009

HU-E5-04 RN-02 ya obligaba a repetir el tipo del original. Faltaba decir qué más hereda y qué no
(HU-E5-04 RN-06 y RN-07).

**La nota de crédito hereda el tipo, la condición IVA del receptor, la leyenda y, si corresponde, el
período de servicio y el vencimiento de pago. No reconsulta el padrón, y la condición heredada es la
que se informa a ARCA.** Revierte ese comprobante, no el estado actual del receptor. Puede iniciarse
desde el aviso de reembolso de un cobro (D93) con el original precargado, y nunca se emite sola: es un
documento fiscal irreversible.

**Para el Gate 1:** el acceso directo desde el reembolso es un enlace a una ruta con el id del
comprobante, no un import entre features del frontend (R5).

### Decisión D90 — `arca-homologacion-completa` cierra contra homologación, no contra fixtures · ADR-0009

La tabla de D87 se apoya en normativa; solo homologación dice qué acepta ARCA. Los tests no tocan la
red (`CLAUDE.md` §5), así que esa verificación no puede vivir en el CI.

**Una unidad aparte, que depende de `tipos-de-comprobante-por-receptor`, recorre en homologación cada
combinación de emisor y receptor de la tabla, más el receptor «IVA No Alcanzado» y el campo de
condición del receptor por tipo, y deja escritos los códigos que ARCA acepta o rechaza.** De ahí salen
los fixtures de contrato que después sí corren en CI.

**Para el Gate 1:** las credenciales de homologación y los puntos de venta de prueba que se usan, y qué
se hace si ARCA rechaza una combinación que la norma permite: se corrige la tabla de D87 con un release
y no se emite ese tipo hasta entonces.

### Preguntas que resuelve el Gate 1 de cada unidad

- **`parametros-fiscales`** — ¿qué parámetros exactamente se sincronizan, y de qué método de
  WSFEv1 salen? El DER dice `tipo_catalogo_fiscal` sin enumerarlo.
- **`puntos-de-venta`** — ¿la verificación de RN-03 pega contra ARCA en el momento de
  activar, o se apoya en un catálogo sincronizado? Lo primero es más veraz y cuesta una
  llamada por alta.
- **`emision-de-comprobantes`** — ¿la emisión asíncrona de RN-04 usa `TareaAsincrona`
  (épico 4) o una tarea suelta? Y la pregunta que más importa: **¿qué hace el sistema si
  ARCA autoriza pero la respuesta se pierde?** Un CAE emitido que no llegó es el peor estado
  posible y no lo cubre ninguna historia.
- **`nota-de-credito`** — ¿el «estado de anulación» de RN-05 es un estado del original, una
  suma de notas asociadas, o las dos cosas? El DER tiene `ANULADO` en el enum pero la
  anulación puede ser parcial. **Respondida (D19): las dos, y la suma es la verdad.** Lo
  anulado se calcula sumando las notas autorizadas; `ANULADO` es un caché de la anulación
  total, y la parcial no es un estado sino un monto.

### Estado

**Mapa escrito el 2026-09-07. Épico completo el 2026-09-07 y mergeado a `develop` el
2026-09-13** por el PR [#34](https://github.com/cheatsheet12/CheatSheet/pull/34). Las cuatro
unidades verificadas con servicios reales. Responsable: Cristian.

Decisiones que se tomaron durante la implementación y no estaban en este mapa:

- **D17 — reconciliar antes de reintentar.** `FECAESolicitar` no es idempotente, así que un
  resultado desconocido se resuelve preguntando (`FECompConsultar`) y nunca reenviando. Es la
  respuesta a la pregunta que el mapa dejó abierta y ninguna historia cubría.
- **D18 — ARCA es la autoridad de la correlatividad.** El número se saca como
  `max(el nuestro, FECompUltimoAutorizado) + 1`, porque WSFEv1 rechaza cualquier hueco hasta
  que los dos contadores coincidan.
- **D19 — lo anulado se deriva, no se guarda.** Ver arriba.

### Fuera de alcance de este épico

- **Asociar un cobro a un comprobante** (HU-E6-06) → épico 6. Acá `saldo_pendiente` se
  registra (HU-E5-03 RN-06) y todavía no lo consume nadie.
- **Emitir desde un turno completado.** HU-E5-03 RN-05 nombra `turno_id`, y la columna se
  crea; quien lo produce llega en el **épico 7**.
- **El Libro IVA Ventas** y el paquete contable → **épico 9**. Este épico emite; leerlos en
  conjunto es reportería.
- **Facturación recurrente o masiva.** Ninguna historia la pide.
- **Otros comprobantes fiscales** —notas de débito, recibos, remitos—. El enum del DER cierra
  en facturas y notas de crédito A/B/C.

---

## Épicos 6 a 10 — construidos sin plan de unidad

Los cinco épicos que cierran el sistema —cobros, agenda, agente de WhatsApp, reportería y
panel de auditoría— **no tienen un plan de unidad cada uno**, y el mapa de arriba los lista
con una sola fila por épico en lugar de con las unidades en que se habrían cortado. Esto no
es una omisión que haya que completar en silencio: es lo que efectivamente pasó, y queda
escrito acá porque un mapa que no dice la verdad sobre cómo se construyó algo es peor que no
tener mapa.

### Qué hay en su lugar

Cada uno dejó dos documentos bajo [`epicas/`](epicas/), y son buenos:

| Épico | Decisiones | Pendientes |
|---|---|---|
| 6 — Cobros y recordatorios | [`decisiones.md`](epicas/06-cobros-y-recordatorios/decisiones.md) | [`pendientes.md`](epicas/06-cobros-y-recordatorios/pendientes.md) |
| 7 — Agenda y recursos | [`decisiones.md`](epicas/07-agenda-y-recursos/decisiones.md) | [`pendientes.md`](epicas/07-agenda-y-recursos/pendientes.md) |
| 8 — Agente de WhatsApp | [`decisiones.md`](epicas/08-agente-de-whatsapp/decisiones.md) | [`pendientes.md`](epicas/08-agente-de-whatsapp/pendientes.md) |
| 9 — Reportería y paquete contable | [`decisiones.md`](epicas/09-reporteria-y-paquete-contable/decisiones.md) | [`pendientes.md`](epicas/09-reporteria-y-paquete-contable/pendientes.md) |
| 10 — Panel de auditoría y notificaciones | [`decisiones.md`](epicas/10-panel-de-auditoria-y-notificaciones/decisiones.md) | [`pendientes.md`](epicas/10-panel-de-auditoria-y-notificaciones/pendientes.md) |

Las decisiones continúan la serie del sistema sin cortarla —D1–D19 están en este archivo y
la serie sigue en D20 y llega hasta el épico 10—, cada una con su porqué y con lo que se
paga por haberla tomado. En ese sentido el rastro de decisiones **no** se perdió.

### Qué sí falta, y conviene decirlo con todas las letras

Lo que no existe es el **plan de unidad**, que es el artefacto del Gate 1: el documento que
se aprueba *antes* de escribir código y que fija alcance, orden, casos de prueba y preguntas
abiertas. Los épicos 1 a 5 tienen uno por unidad bajo [`units/`](units/); los épicos 6 a 10
no tienen ninguno. En términos del workflow, esos cinco épicos pasaron del insumo al código
sin la compuerta del medio.

La consecuencia práctica es una sola y es acotada: no hay contra qué contrastar lo
implementado salvo el código y sus tests. Por eso la verificación de estos cinco épicos se
apoyó en los gates del repositorio y en QA sobre la aplicación corriendo, y no en el recorrido
de casos de prueba que un plan de unidad habría declarado de antemano.

### Por qué no se escriben los planes ahora

Un plan de unidad escrito después de que el código existe no es un plan: es una descripción
con forma de plan. No sirve para lo único que un Gate 1 sirve —discutir el alcance cuando
todavía es barato cambiarlo— y al quedar archivado junto a los nueve planes reales de los
épicos 1 a 5 haría creer que estos cinco épicos se planificaron igual que aquellos.

La regla que queda para lo que venga: **`epicas/` documenta decisiones, `units/` documenta
planes, y el mapa de arriba dice cuál de las dos cosas tiene cada épico.**
