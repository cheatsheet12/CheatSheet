# Roadmap — CheatSheet

> Todas las historias del sistema, repartidas en épicos ordenados. Cada épico termina en algo
> demostrable en `staging`. Ninguna historia queda afuera.

Insumo: [`inputs/historias-de-usuario.md`](inputs/historias-de-usuario.md) — 59 HUs agrupadas en
12 épicas temáticas, más 7 historias de sistema. **Ese agrupamiento es por bounded context, no un
orden de construcción.** Este documento lo re-corta en rebanadas verticales y lo ordena por
dependencia. Las dos numeraciones conviven; la tabla de trazabilidad (§4) las vincula.

---

## 1. Los épicos, en orden

| # | Épico | Historias | Contextos | Termina en (demo) |
|---|---|---|---|---|
| 1 | **Cimientos, identidad y bitácora** | HU-E1-01 … HU-E1-07 · HS-T5 | `identity`, `observability` | Una empresa se registra, completa el onboarding, invita usuarios y les cambia el rol — y **cada acción queda registrada en la bitácora**, aunque todavía no exista pantalla para leerla |
| 2 | **Conexión con los servicios externos** | HU-E2-01, HU-E2-02, HU-E2-03, HU-E2-05 · *(deuda de D1: consulta de padrón de HU-E1-02)* | `integrations`, `identity` | PAN-CFG-INT mostrando ARCA y MercadoPago **conectados de verdad** (credenciales validadas contra el servicio) y WhatsApp en verificación de Meta, con la verificación en vivo de estado funcionando; y el CUIT del onboarding validado ya contra el padrón |
| 3 | **Catálogo de clientes y servicios** | HU-E4-01 … HU-E4-04 | `master_data` | ABM completo de clientes (con CUIT validado contra ARCA) y de servicios (precio, IVA, agendable), clasificados por categorías propias de la empresa |
| 4 | **Sincronización de planillas** | HU-E2-04 · HU-E3-01 … HU-E3-06 · HS-T6 | `spreadsheet_sync`, `observability` | Se vincula una planilla real, la IA propone el mapeo, el usuario lo corrige y confirma, la carga inicial puebla el catálogo del épico 3, se ven los errores de fila y se reprocesa tras corregirlos |
| 5 | **Facturación electrónica** | HU-E5-01 … HU-E5-05 · HS-T4 | `billing`, `reference_data` | Se emite una factura contra ARCA en homologación y **se obtiene un CAE real**, se descarga el PDF, se la anula con una nota de crédito y se administran los puntos de venta |
| 6 | **Cobros y recordatorios** | HU-E6-01 … HU-E6-06 · HU-E11-01 · HS-T1, HS-T3 | `payments`, `business_config`, `billing` | Se genera un link de MercadoPago, se paga en sandbox, el webhook lo marca **Pagado sin duplicar efectos**, baja el saldo del comprobante asociado y la cadena de recordatorios se despacha —y se detiene— según la regla configurada |
| 7 | **Agenda y recursos** | HU-E7-01 … HU-E7-05 · HU-E6-07 | `scheduling`, `payments` | Se configuran recursos con disponibilidad semanal y excepciones, se ve la agenda del día, se cancela y reprograma **rechazando solapamientos**, se marca asistencia y se seña un turno con un cobro |
| 8 | **Agente de WhatsApp y atención humana** | HU-E8-01 … HU-E8-05 · HU-E9-01, HU-E9-02, HU-E9-04 · HU-E11-02 · HS-T2, HS-T7 | `conversational`, `business_config` | Un cliente reserva y cancela un turno conversando por WhatsApp (incluida una nota de voz), consulta una FAQ, y cuando el agente no entiende **la conversación escala y un operador la atiende desde el panel con el contexto previo** |
| 9 | **Reportería y paquete contable** | HU-E10-01 … HU-E10-06 | `reporting` | Dashboard de KPIs con datos reales acumulados por los épicos anteriores, generación y descarga de reportes, y el contador externo entrando por enlace a descargar el paquete contable |
| 10 | **Panel de auditoría y notificaciones** | HU-E12-01, HU-E12-02 · HU-E11-03 · HU-E9-03 | `observability`, `business_config` | La bitácora completa filtrable por módulo, estado e iniciador, con el detalle y el timeline de cada operación; el centro de notificaciones; y el alta de solicitudes de soporte |

---

## 2. Cobertura

- **Historias totales: 66** (59 `HU-…` + 7 `HS-T…`) · **asignadas: 66** · **sin asignar: ninguna**
- Ninguna historia aparece en dos épicos.
- Reparto: 8 · 4 · 4 · 8 · 6 · 9 · 6 · 11 · 6 · 4.

---

## 3. El orden — por qué este y no otro

### Lo que va primero porque todo lo demás lo presupone

Los épicos 1 a 3 no son "la capa de infraestructura": son las tres cosas que **toda otra historia
da por sentadas**. No se puede facturar sin empresa (`tenant_id`), sin CUIT validado, sin punto de
venta y sin un cliente receptor. El épico 1 existe porque 59 historias empiezan con "el usuario
tiene sesión iniciada"; el 3, porque facturación, agenda y cobros consumen `Cliente` y `Servicio`.

### El riesgo se adelanta, no se posterga

Facturación (5) va antes que agenda (7) y que el agente (8) aunque el catálogo la ponga después de
sincronización. Un comprobante con CAE es **irreversible ante ARCA**: una sorpresa ahí es infinitamente
más barata en el mes 3 que en el mes 7. Lo mismo vale para cobros (6): mueve dinero real y depende de
webhooks duplicados que solo se descubren integrando.

El agente conversacional (8) queda octavo pese a ser Core, y a propósito: es el único contexto **no
determinista** del sistema, y traduce intenciones a llamadas sobre agenda, cobros y facturación. Sin
esos tres funcionando, lo único que se puede probar del agente es que entiende — que es la mitad
fácil. Se construye cuando hay algo real que pueda hacer, y romper.

### Lo transversal se instala cuando aparece, no al final

Tres mecanismos atraviesan todo el sistema y por eso se adelantan al épico que primero los necesita:

- **La bitácora (HS-T5) va en el épico 1.** Unas quince historias repartidas por todo el catálogo
  terminan en "queda registrado en el Log de Operaciones" (HU-E1-05 RN-04, HU-E6-04 RN-05,
  HU-E7-02 RN-04, HS-T1 RN-05…). Si el sumidero de auditoría llega último, los nueve épicos previos
  se entregan con un criterio de aceptación incumplido y hay que volver a abrir ocho contextos para
  emitir eventos. El **panel** para leerla es otra cosa y sí puede esperar (épico 10).
- **Las reglas de negocio (HU-E11-01) van en el épico 6.** HS-T3 las declara precondición explícita:
  sin regla de escalamiento activa no hay recordatorios que despachar.
- **Las plantillas de notificación (HU-E11-02) van en el épico 8.** Los envíos por WhatsApp requieren
  plantillas aprobadas por Meta (RN-03); el agente no puede escribirle a nadie sin ellas.

### WhatsApp se conecta en el épico 2 aunque el agente sea el 8

HU-E2-03 RN-02 dice que la verificación del número por parte de Meta **demora entre 24 y 72 horas**.
Es tiempo de calendario que no se compra con esfuerzo. Se arranca en el épico 2 y para cuando el
épico 8 empiece, la línea ya está verificada. Es la única pieza que se adelanta por plazo externo y
no por dependencia técnica.

### Cada épico termina en algo que se puede mostrar

Ninguno es una capa. El 1 no es "el backend de identidad": es una empresa que se registra y opera.
El 4 no es "el parser de planillas": es una planilla real del usuario alimentando el catálogo. Si un
épico no se puede demostrar en `staging`, está mal cortado.

---

## 4. Trazabilidad con la numeración del documento

Las "Épicas 1…12" del insumo agrupan por bounded context. Este roadmap las re-corta. La correspondencia:

| Épica del documento | Va a los épicos del roadmap |
|---|---|
| 1 — Onboarding y Gestión de la Organización | **1** (completa) |
| 2 — Integración con Sistemas Externos | **2** (ARCA, MercadoPago, WhatsApp, estado) · **4** (HU-E2-04, planilla) |
| 3 — Sincronización de Planillas | **4** (completa) |
| 4 — Gestión de Datos Maestros | **3** (completa) |
| 5 — Facturación | **5** (completa) |
| 6 — Cobros | **6** · **7** (HU-E6-07, seña de turno) |
| 7 — Agenda | **7** (completa) |
| 8 — Canal Conversacional | **8** (completa) |
| 9 — Atención y Escalamiento | **8** (HU-E9-01, HU-E9-02, HU-E9-04) · **10** (HU-E9-03, soporte) |
| 10 — Reportería y Análisis | **9** (completa) |
| 11 — Configuración del Negocio | **6** (HU-E11-01) · **8** (HU-E11-02) · **10** (HU-E11-03) |
| 12 — Auditoría y Observabilidad | **10** (completa) |
| Historias de Sistema | **1** (HS-T5) · **4** (HS-T6) · **5** (HS-T4) · **6** (HS-T1, HS-T3) · **8** (HS-T2, HS-T7) |

### Los seis cambios respecto del orden del documento

1. **Datos maestros pasa de 4.ᵃ a 3.ᵃ, delante de sincronización.** El Context Map declara
   `spreadsheet_sync → master_data` y HU-E3-03 escribe `Cliente` y `Servicio` (con `origen = PLANILLA`,
   HU-E4-01 RN-01). No se puede ingerir hacia un catálogo que todavía no existe.
2. **Integraciones se parte en dos.** Tres de las cuatro (ARCA, MercadoPago, WhatsApp) comparten el
   mismo mecanismo — `ConfiguracionDeIntegracion`, credencial cifrada, verificación en vivo — y se
   construyen juntas. La cuarta (HU-E2-04, planilla) **no**: sus criterios de aceptación terminan en
   PAN-ING-02 revisando el mapeo, o sea que es el primer paso del flujo de ingesta, no una integración
   más. Va con el épico 4.
3. **Las historias de sistema dejan de ser un bloque final.** Son las automatizaciones que constituyen
   la propuesta de valor del producto; dejarlas para el final es construir el producto sin su valor.
   Cada una se reparte al épico que la usa.
4. **La auditoría se parte: el sumidero (HS-T5) al épico 1, el panel (HU-E12-01/02) al 10.** Ver §3.
5. **Configuración del Negocio se disuelve.** Sus tres historias sirven a tres épicos distintos y en
   tres momentos distintos; mantenerlas juntas obligaría a construirlas cuando ninguna tiene consumidor.
6. **El escalamiento se reúne.** HU-E8-05 (el cliente es derivado) y HU-E9-01/02 (el operador atiende y
   cierra) son los dos extremos de un mismo mecanismo. Separados, el épico 8 entregaría una derivación
   que no lleva a ninguna parte. HU-E9-04 (FAQ) entra ahí también, porque HU-E8-03 la presupone.

> El orden **interno** de cada épica del documento tampoco es de construcción: en la Épica 7, por
> ejemplo, HU-E7-01 declara como precondición a HU-E7-04. Eso se resuelve en el mapa de unidades de
> cada épico, no acá.

---

## 5. Unidades técnicas (sin HU detrás)

Trabajo de cimientos que ninguna historia pide y todo el resto necesita. **Va dentro del épico 1**,
justificado por lo que habilita — nunca como épico propio ni como cajón de sastre. No hay más unidades
técnicas que estas: cualquier otra que aparezca después es una señal de que algo se planificó mal.

| Unidad técnica | Qué habilita |
|---|---|
| Arranque de la aplicación FastAPI (composition root, healthcheck, manejo de errores) | Que exista un proceso donde montar el primer router |
| Sesión de base de datos e infraestructura de migraciones (Alembic) | Que cualquier agregado pueda persistirse y revertirse |
| Aislamiento multi-tenant en la capa de persistencia (`tenant_id` del Shared Kernel) | HU-E5-01 RN-01: "el aislamiento multi-tenant es transparente". Si no está desde la primera tabla, se retrofitea en las 27 |
| Esqueleto de Celery + Beat y de las cinco colas | El primer trabajo asíncrono (HU-E3-03, HU-E5-03) y el planificador (HS-T3, HS-T4) |
| Esqueleto de tests: fixtures de base de datos, factories, dobles de los servicios externos | El umbral de cobertura del 80% desde el primer módulo, y la regla de que los tests nunca tocan la red |
| Cascarón del frontend: BFF, cookie HttpOnly del JWT, layout `(panel)` / `(public)`, sistema de diseño mínimo | Que la primera pantalla sea una pantalla y no una página suelta |

---

## 6. Decisiones abiertas

Ninguna bloquea el arranque. Cada una debe resolverse **antes del mapa de unidades de su épico**, no
durante la implementación.

| # | Decisión | Épico | Origen |
|---|---|---|---|
| ~~D1~~ | **Resuelta (2026-08-12).** Cómo se valida un CUIT contra ARCA antes de que la empresa haya cargado su certificado. → **Validación estructural (formato y dígito verificador) en el épico 1; consulta al padrón en el épico 2**, cuando HU-E2-01 ya dejó la credencial cargada. No se introduce credencial de plataforma. El detalle y sus consecuencias están en [`units.md`](units.md) § Decisión D1 | 1 → 2 | Detectada acá |
| D2 | ¿El administrador puede crear un turno manualmente desde el panel, o solo ver los que llegan por el agente? | 7 | HU-E7-01 RN-04 |
| D3 | ¿El agente puede reclasificar el tipo del hilo al retomar el control tras la intervención humana? | 8 | HU-E9-01 RN-05 |
| D4 | ¿Hay un límite máximo de FAQ por plan contratado? | 8 | HU-E9-04 RN-04 |
| D5 | ¿El Operador puede configurar el envío automático del paquete contable y gestionar el acceso del contador, o es exclusivo del Administrador? | 9 | HU-E10-04, HU-E10-05 |
| D6 | ¿El administrador puede generar un paquete contable de un período arbitrario fuera del ciclo automático? | 9 | HU-E10-04 RN-04 |

D1 es la única de las seis que es **estructural**: cambia qué credenciales administra la plataforma y
cómo se modela `ConfiguracionDeIntegracion`. Si la respuesta no es la propuesta, el épico 1 cambia de
forma. Las otras cinco son de alcance y se responden en una línea.

---

## 7. Estado

Aprobado el roadmap, cada épico entra al flujo por su propio mapa de unidades
([`units.md`](units.md), paso 1a de [`.claude/aidlc/workflow.md`](../../.claude/aidlc/workflow.md)).
Un épico puede re-cortarse más adelante con evidencia; el catálogo no se vuelve a repartir cada sprint.
