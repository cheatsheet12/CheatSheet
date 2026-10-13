---
entregable: plan
parte: 08-contingencia
responsable: Luciano Oro
estado: borrador
hu: [HU-E2-05, HU-E4-05, HU-E5-04, HU-E5-05, HU-E6-04, HU-E6-05, HU-E6-08, HS-T1, HS-T5, HS-T6]
fuentes:
  - docs/aidlc/etapa-6/entregables/plan/00-introduccion-y-metodo.md
  - docs/aidlc/etapa-6/entregables/plan/01-puesta-en-produccion.md
  - docs/aidlc/etapa-6/entregables/plan/02-entorno-de-produccion.md
  - docs/aidlc/etapa-6/entregables/plan/03-despliegue.md
  - render.yaml
  - .github/workflows/ci.yml
  - docs/staging-deployment.md
  - docs/staging-database.md
  - docs/configuration-management.md
  - docs/architecture.md
  - docs/adr/0004-arca-wsaa-access-tickets.md
  - docs/adr/0005-staging-database-neon.md
  - docs/adr/0006-staging-hosting-render.md
  - docs/adr/0007-llm-provider-anthropic.md
  - docs/adr/0008-wsfev1-cliente-propio.md
  - docs/adr/0010-payment-date-method-and-refunds.md
  - docs/adr/0011-outbound-whatsapp-channel-via-composition-root.md
  - docs/adr/0014-arca-web-service-delegation.md
  - docs/aidlc/inputs/historias-de-usuario.md
  - backend/alembic.ini
  - backend/migrations/env.py
  - backend/migrations/versions/
  - backend/scripts/verify_rls.py
  - backend/.env.example
  - backend/src/cheatsheet/platform/settings.py
  - backend/src/cheatsheet/api/routers/health.py
  - backend/src/cheatsheet/api/routers/webhooks.py
  - backend/src/cheatsheet/api/routers/whatsapp.py
  - backend/src/cheatsheet/api/routers/correccion.py
  - backend/src/cheatsheet/workers/
  - backend/src/cheatsheet/contexts/billing/application/emision.py
  - backend/src/cheatsheet/contexts/billing/domain/punto_de_venta.py
  - backend/src/cheatsheet/contexts/payments/application/reintentos.py
  - backend/src/cheatsheet/contexts/payments/infrastructure/envio.py
  - backend/src/cheatsheet/contexts/conversational/application/agente.py
  - backend/src/cheatsheet/contexts/master_data/infrastructure/correccion.py
  - frontend/src/shared/motivos-de-falla.ts
  - frontend/src/features/conversational/api/conversacion.ts
  - frontend/src/features/conversational/components/HiloDeConversacion.tsx
  - frontend/src/features/conversational/components/BandejaDeConversaciones.tsx
  - frontend/src/features/integrations/components/TarjetaDeIntegracion.tsx
  - frontend/src/features/billing/components/DetalleDeComprobante.tsx
  - frontend/src/features/billing/components/AnularComprobante.tsx
observaciones: >
  1) La fecha calendario de D no está fijada (plan/00): todo se expresa relativo a D. Las dependencias
  de PLAN-§4 a PLAN-§7, que todavía no están integradas, se citan por sección; al integrar,
  reemplazar cada «PLAN-§n» por el número de actividad. 2) La producción no está decidida (ADR-0006,
  actividad 2.1). Cuatro capacidades del proveedor no se pueden comprobar desde el repositorio y
  quedan «a confirmar» en las actividades 8.2 y 8.4: restauración de la base a un punto en el
  tiempo, publicación manual de un commit anterior desde la consola, suspensión del servicio de la
  API y registro de despliegues con el commit de cada uno. 3) docs/staging-deployment.md (§3) todavía
  cita la tabla ticket_de_acceso, eliminada por la migración 0043 (ADR-0014): hoy el recifrado
  alcanzaría configuracion_de_integracion y ticket_de_plataforma. 4) Que HU-E6-08 sirva para un cobro
  pagado por link cuya notificación se perdió no lo dice la historia ni lo prueba el código leído:
  se confirma en la validación (PLAN-§6). 5) El recuento de downgrade() (26 revisiones eliminan
  tablas, 6 solo columnas y 9 ninguna) sale de leer el texto de cada archivo; la actividad 8.3 lo
  confirma ejecutándolo. 6) Inconsistencias detectadas en PLAN-§0 a PLAN-§3, no editadas: (a) PLAN-§0
  y 2.2 dan por pendiente el canal real de WhatsApp para recordatorios y avisos, pero en develop ya
  existen EnvioPorWhatsApp y AvisoPorWhatsApp y no queda EnvioPorConsola ni AvisoPorConsola en
  backend/src; (b) 1.12 publica la versión en D y 3.4 a 3.10 en D-7, y 1.8 congela en D-7 mientras
  3.3 integra en D-8 y 3.11 congela desde D-6; (c) 3.8 verifica la versión publicada con /health, que
  no informa versiones; (d) 3.11 integra los hotfix/ también en develop, pero el trabajo conventions
  de la CI rechaza un PR de hotfix/ hacia develop y uno de main hacia develop; (e) 2.13 no nombra
  CATALOGOS_FISCALES_ADAPTADOR=wsfe, que el proceso exige en producción, ni los secretos de webhook
  que no exige; (f) 2.15 controla /health, que solo sondea la base y Redis, no el worker ni Beat; (g) 2.16 y su criterio de listo citan
  «Conectada», pero el panel muestra «Conectado» (TarjetaDeIntegracion.tsx).
---

## 8. Plan de contingencia y rollback

### Objetivo

Esta sección define cuándo se vuelve atrás una puesta en producción, cómo se hace y cómo sigue operando la empresa piloto mientras se corrige. Parte de lo que el repositorio ya resuelve (el orden del trabajo de despliegue, `verify_rls.py`, las migraciones de Alembic y los barridos de Celery) y marca como **medida pendiente** lo que hoy no existe. La producción no está decidida (ADR-0006): los procedimientos se escriben sobre la propuesta de PLAN-§2 y lo que el repositorio no puede demostrar de un proveedor figura como «a confirmar» en la actividad que lo verifica.

El método piloto separa dos reversiones. La **reversión de la versión** vuelve el código y, si hace falta, la base a un estado conocido (procedimiento A). El **retorno de la empresa piloto a su operación anterior**, que el método deja lista y sin uso en paralelo, saca a la empresa del sistema sin afectar a otras (procedimiento B).

Principios que ordenan las actividades:

- **Fallar sin publicar.** El trabajo `deploy-staging` de `.github/workflows/ci.yml` corre CI, aplica `alembic upgrade head` con el rol dueño, ejecuta `verify_rls.py` y solo entonces llama a los ganchos de despliegue; todos los servicios tienen `autoDeploy: false` (`render.yaml`). Si un paso falla, ningún servicio se publica y todos siguen con la versión anterior. Si falla `verify_rls.py`, la base ya quedó migrada. La actividad 2.14 crea el equivalente para `main`: hoy `main` no despliega nada.
- **Sin interruptores de funcionalidad.** La reversión de código es publicar otra versión, la de datos es un `downgrade()` o una restauración, y la de efectos fiscales o de dinero es una compensación. Los frenos disponibles son los del Administrador sobre su empresa: desactivar un punto de venta, que impide nuevas emisiones y conserva lo emitido (HU-E5-05 — Configurar y administrar los puntos de venta), y cancelar un cobro pendiente, que invalida su link (HU-E6-04 — Cancelar un cobro).
- **Lo fiscal y el dinero se compensan, no se revierten.** Un comprobante autorizado se reversa con una nota de crédito (HU-E5-04 — Anular un comprobante mediante una nota de crédito, ADR-0008) y un cobro pagado, con un reembolso (HU-E6-05 — Reembolsar un cobro, ADR-0010). Un `downgrade()` que elimina tablas con datos reales los destruye (el de la revisión 0018 elimina `comprobante` e `item_de_comprobante`): en producción solo se ejecuta uno que la actividad 8.3 marcó sin pérdida de datos.
- **La bitácora no se edita.** El rol de la aplicación solo puede leer y agregar en `registro_de_auditoria` (HS-T5 — Registrar automáticamente las operaciones en la auditoría; control 5 de `verify_rls.py`); una corrección deja su propio registro.
- **`SECRETS_ENCRYPTION_KEY` no se regenera.** Cifra las credenciales de las empresas; rotarla exige volver a cifrar lo guardado y hoy no hay herramienta que lo haga.

### Actividades

| # | Actividad | Responsable (rol) | Cuándo | Depende de |
|---|---|---|---|---|
| 8.1 | Fijar los criterios de reversión de la tabla siguiente, el plazo de interrupción que justifica el retorno de la empresa piloto a su operación anterior, quién decide (el Arquitecto de Software) y quién ejecuta cada procedimiento | Arquitecto de Software | D-14 | 1.3 |
| 8.2 | Confirmar con la documentación del proveedor de base de datos elegido en 2.1, sobre el plan contratado en 2.4, la ventana de retención y el procedimiento de una restauración a un punto en el tiempo hacia un destino nuevo, y ensayarla en una base descartable. Hasta confirmarlo no se asume que exista (escenario 6) | Analista de Infraestructura y Datos | D-14 | 2.4 |
| 8.3 | Ensayar en una base descartable el ciclo `alembic -c backend/alembic.ini downgrade` y `upgrade head` sobre las 41 revisiones de `backend/migrations/versions/` y registrar cuáles destruyen datos al retroceder | Analista de QA | D-10 | — |
| 8.4 | Confirmar y ensayar en staging cómo se publica de nuevo el commit anterior de cada servicio (API, panel, worker y Beat) sin pasar por el trabajo de despliegue, cómo se lee en la consola el commit de cada despliegue y cómo se suspende el servicio de la API. Es el camino del procedimiento A cuando el trabajo de despliegue no puede publicar la versión anterior | Analista de Infraestructura y Datos | D-10 | 2.9 |
| 8.5 | Contrastar la lista de variables de 2.13 con `platform/settings.py` y `render.yaml`: las que el proceso exige al arrancar (entre ellas `CATALOGOS_FISCALES_ADAPTADOR=wsfe`) y las que no exige y silencian una función si faltan (`MERCADOPAGO_WEBHOOK_SECRET`, `WHATSAPP_WEBHOOK_SECRET`, `WHATSAPP_WEBHOOK_VERIFY_TOKEN`). Un arranque fallido con `ConfiguracionFaltante` es una señal de configuración incorrecta y no de código | Analista de Integraciones | D-9 | 2.13 |
| 8.6 | Inventariar los secretos de producción (`SECRETS_ENCRYPTION_KEY`, `JWT_SECRET`, `ARCA_CREDENCIAL_PLATAFORMA`, las contraseñas de los dos roles de la base, los ganchos de despliegue y la credencial de cada proveedor), documentar cómo se revoca y se reemplaza cada uno (escenario 8) y comprobar que un segundo rol lee las copias guardadas en 2.10 | Arquitecto de Software | D-9 | 2.10, 2.14 |
| 8.7 | Antes de aprobar el Pull Request a `main` de 3.3, clasificar cada migración nueva de la versión: aditiva o no, y reversible sin pérdida de datos o no, según 8.3. Una migración que no es aditiva no entra durante el piloto (3.11) | Arquitecto de Software | D-8 | 3.2, 8.3 |
| 8.8 | Completar el registro de 3.10 con la revisión de Alembic de la base (`alembic current`) y con el commit y la etiqueta de la versión anterior de cada servicio, que son el destino de la vuelta atrás (en el primer despliegue no existe versión anterior). El commit de cada servicio se lee en el registro de despliegues de la consola, porque `/health` no informa versiones | Gestión de Configuración y Documentación | D-7 | 3.10 |
| 8.9 | Escribir el guion del ensayo 1.9 con tres casos de vuelta atrás: una migración que falla en el trabajo de despliegue; la publicación manual del commit anterior sobre una base ya migrada, con la salida de `verify_rls.py` y su control 7; y la restauración de la base a un destino nuevo | Analista de QA | D-7 | 8.2, 8.3, 8.4 |
| 8.10 | Definir cómo se detecta un worker o un Beat detenido, que `/health` no cubre (procedimiento del escenario 7), y quién mira esas señales cada día entre D y D+14 | Analista de Infraestructura y Datos | D-6 | 2.15 |
| 8.11 | Definir los procedimientos de compensación de la tabla de efectos que no se deshacen: nota de crédito, cancelación y reembolso de cobros | Analista de Integraciones | D-5 | PLAN-§6 |
| 8.12 | Definir el procedimiento ante una corrección masiva de nombres no deseada: restaurar la corrida desde la corrección de datos (HU-E4-05 — Normalización de los datos del catálogo), que conserva lo editado después | Analista de Infraestructura y Datos | D-5 | PLAN-§4 |
| 8.13 | Definir el flujo de corrección urgente: una rama `hotfix/` hacia `main`, con plan de una línea y las mismas verificaciones y revisión; el mismo cambio llega a `develop` por una rama `fix/` del módulo afectado, porque el trabajo `conventions` de la CI no admite un PR de `hotfix/` ni de `main` hacia `develop` | Gestión de Configuración y Documentación | D-5 | 3.11 |
| 8.14 | Registrar en el ensayo 1.9 el resultado de cada caso del guion de 8.9 (pasos, tiempo y desvíos) y corregir este plan con lo observado | Analista de QA | D-5 | 1.8, 8.9 |
| 8.15 | Definir con el Administrador de la empresa piloto qué hace la empresa durante una interrupción (por ejemplo, atender por teléfono y anotar turnos y cobros en papel) y cómo se cargan esos datos después | Analista Funcional y Diseño de Experiencia | D-3 | PLAN-§7 |
| 8.16 | Definir los mensajes, los canales y quién avisa a la empresa piloto y al equipo de una interrupción, de una falla de ARCA, MercadoPago, Meta, el proveedor del modelo o la plataforma de alojamiento, y de una vuelta atrás | Gestión de Configuración y Documentación | D-3 | PLAN-§7 |
| 8.17 | Nominar un suplente por rol y comprobar que cada uno accede a la consola del proveedor, al repositorio, a los secretos y a los proveedores externos | Arquitecto de Software | D-3 | 8.6 |
| 8.18 | Revisar con el equipo cada escenario, cerrar las **medidas pendientes** o aceptarlas por escrito, y dejar esta sección en estado listo antes de la reunión de decisión | Arquitecto de Software | D-2 | 8.1 a 8.17 |
| 8.19 | Tomar un punto de restauración de la base inmediatamente antes de la carga inicial, para que un defecto de la carga se deshaga restaurando mientras la empresa piloto todavía no opera | Analista de Infraestructura y Datos | D, antes de 1.13 | 1.12, 8.2 |
| 8.20 | Mantener este plan activo, registrar cada incidente (hora, señal, severidad según 1.16, decisión y tiempo de recuperación) y revisar con él los criterios de 8.1 | Arquitecto de Software | D a D+30 | 1.15 |

**Criterios de reversión (actividad 8.1).** La severidad usa la escala del proyecto: es Crítico lo que afecta dinero, un comprobante fiscal, datos de otra empresa o pérdida de datos.

| Señal | Dónde se observa | Decisión | Procedimiento |
|---|---|---|---|
| El trabajo de despliegue falla en las migraciones (3.5) o en `verify_rls.py` (3.6) | Trabajo de despliegue | No es una vuelta atrás: ningún servicio se publicó. Se corrige y se repite desde 3.3 | Escenario 5 |
| `/health` no responde 200 en los diez minutos posteriores a la publicación (3.8) | Trabajo de despliegue y consola | El Arquitecto de Software decide entre corregir hacia adelante y volver a la versión anterior | A |
| La prueba de humo (3.9) o la validación en producción (1.14) falla en la emisión con CAE, en el cobro o en el aislamiento entre empresas | Analista de QA | Crítico: se activa la vuelta atrás (1.15) | A |
| Una empresa ve datos de otra | Cualquier persona del equipo o de la empresa piloto | Crítico: no se espera el diagnóstico; se suspende el servicio de la API | A, paso 2 |
| Un comprobante autorizado tiene datos erróneos | Administrador u Operador, o la validación | No se revierte: se compensa | Compensación |
| Un cobro tiene monto o imputación errónea | Administrador u Operador, o la validación | No se revierte: se compensa | Compensación |
| La interrupción impide emitir comprobantes o cobrar y supera el plazo fijado en 8.1 | Administrador de la empresa piloto | El Arquitecto de Software decide el retorno de la empresa a su operación anterior | B |
| Un defecto Mayor o Menor | Analista de QA | No hay vuelta atrás: se corrige por `hotfix/` (8.13) | — |

**Procedimiento A — Vuelta atrás de una versión publicada.** Decide el Arquitecto de Software y ejecuta el Analista de Infraestructura y Datos.

1. Registrar la hora, la señal y el punto de retorno de 8.8 (commit, etiqueta, revisión de Alembic y respaldo de 3.4).
2. Si hay datos de una empresa visibles para otra o un error de dinero en curso, suspender el servicio de la API en la consola del proveedor antes de diagnosticar (capacidad a confirmar en 8.4). En cualquier otro caso, el servicio sigue atendiendo.
3. Preferir corregir hacia adelante: un `hotfix/` pequeño (8.13) conserva las migraciones ya aplicadas y recorre todo el trabajo de despliegue.
4. Si hay que volver a la versión anterior y la versión publicada no trajo migraciones, publicar el commit anterior: con un `hotfix/` que revierta el cambio, que recorre el trabajo de despliegue completo, o con la publicación manual de 8.4.
5. Si la versión trajo migraciones, aplicar la clasificación de 8.7:
   - Aditivas: publicar el commit anterior a mano (8.4) sobre la base ya migrada, sin retroceder la base. El trabajo de despliegue no puede hacerlo: el control 7 de `verify_rls.py` exige que la base esté en la última revisión del código, y un `hotfix/` que revierta la migración quitaría el archivo y `alembic upgrade head` no encontraría la revisión que la base ya tiene.
   - No aditivas (no deberían existir durante el piloto, 3.11): retroceder con `alembic -c backend/alembic.ini downgrade` hasta la revisión anterior a la defectuosa, solo si 8.3 la marcó sin pérdida de datos, con el rol dueño y desde la copia del repositorio que contiene la migración, porque el código anterior no tiene el archivo. Si pierde datos, restaurar la base (escenario 6) antes de publicar la versión anterior.
6. Verificar: `/health` responde 200; `verify_rls.py` se ejecuta desde la copia del commit publicado (con migraciones aditivas se espera que falle solo el control 7, porque la base está en una revisión posterior a la del código; cualquier otra falla detiene el procedimiento y se trata como Crítica); el commit de los cuatro servicios coincide en la consola.
7. Registrar el resultado y el tiempo de recuperación en 8.20.

**Procedimiento B — Retorno de la empresa piloto a su operación anterior.** Decide el Arquitecto de Software; ejecutan el Administrador de la empresa piloto y el Analista de Integraciones.

1. Avisar a la empresa por el canal de 8.16 y acordar la hora del cambio.
2. Esperar a que no queden comprobantes en `ENVIADO_A_ARCA`: la reconciliación los resuelve dentro de su intervalo. Desde este momento no se emite nada nuevo desde el panel.
3. El Administrador desactiva los puntos de venta (HU-E5-05), para que la emisión use un solo camino, como exige el método de implementación.
4. Cancelar los cobros pendientes con link activo que la empresa prefiera cobrar por su camino anterior (HU-E6-04). Los demás siguen cobrándose y el webhook los registra mientras la API esté en pie.
5. Mantener el panel y la API disponibles para consulta: nada se borra y los comprobantes emitidos conservan su CAE.
6. Si la empresa vuelve a emitir desde el sistema con el mismo punto de venta, el contador de números se alinea con el último número autorizado por ARCA en la emisión siguiente.
7. Antes de habilitar de nuevo a la empresa, corregir la causa y repetir la validación 1.14. Registrar todo en 8.20.

**Compensación de efectos que no se deshacen.**

| Efecto | Cómo se compensa | Quién | Fuente |
|---|---|---|---|
| Comprobante autorizado con datos erróneos | Nota de crédito total o parcial desde el detalle del comprobante («Anular con nota de crédito», luego «Emitir nota de crédito», PAN-FAC-04). El monto no supera el del original, la nota también va a ARCA y el original permanece. Si ARCA la rechaza, queda en estado Error con el detalle | Administrador u Operador | HU-E5-04, ADR-0008 |
| Comprobante en `ENVIADO_A_ARCA` o `RECHAZADO` | No se reemite a mano: la reconciliación lo resuelve. Uno rechazado puede emitirse de nuevo | Administrador u Operador | `emision.py` |
| Cobro pendiente o vencido que no corresponde | Cancelarlo con un motivo de al menos 10 caracteres: invalida el link y detiene los recordatorios (PAN-COB-02) | Administrador u Operador | HU-E6-04 |
| Cobro pagado que no corresponde | Reembolsarlo. Si estaba asociado a un comprobante, el sistema advierte que corresponde una nota de crédito y no la emite sola. Un error de registro se corrige con un nuevo registro, no se edita | Administrador | HU-E6-05, ADR-0010 |
| Nombres de clientes, servicios y categorías corregidos de forma masiva | Restaurar la corrida (PAN-DM-01): devuelve los nombres del respaldo `respaldo_de_normalizacion` y conserva lo editado después | Administrador | HU-E4-05 |
| Registros de la bitácora | No se corrigen ni se borran | — | HS-T5 |

**Detección disponible hoy.**

- `/health` responde 503 con `estado: degradado` cuando PostgreSQL o Redis no responden; `/health/live` solo prueba el proceso. Ninguno informa versiones ni el estado del worker o de Beat (`api/routers/health.py`).
- La consola del proveedor de alojamiento: registro de despliegues y registros de cada servicio. El gancho de despliegue solo solicita el despliegue; la causa de una falla está en el registro del servicio (`docs/staging-deployment.md`, §9).
- El trabajo de despliegue de la CI y, desde 2.14, el de producción.
- La bitácora del panel (PAN-LOG-01), que registra los webhooks rechazados (HS-T1 — Confirmar un pago a partir del webhook de MercadoPago) y las tareas agotadas (HS-T6 — Derivar a la cola de fallos (DLQ) las tareas asíncronas agotadas).
- **Medida pendiente:** no existe un sistema de alertas propio. El control externo de 2.15 cubre `/health`; el resto se detecta por revisión activa (8.10, 1.16).

**Escenarios.** Los roles son los del plan; «Operador» y «Administrador» son los roles de la empresa. Cada tabla dice cómo se detecta la falla, qué hacer de inmediato y cómo se recupera.

**Escenario 1 — ARCA no disponible, certificado vencido o delegación revocada**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Crítico (efecto fiscal). Analista de Integraciones; decide el Arquitecto de Software |
| Detección | Un comprobante permanece en `ENVIADO_A_ARCA` más de cinco minutos (`VENTANA_DE_VUELO`); el worker registra `autorizacion_sin_respuesta_de_arca`; la verificación de la conexión en «Integraciones» deja de mostrar «Conectado» (HU-E2-05 — Validar el estado de una conexión externa) |
| Acción inmediata | No emitir de nuevo un comprobante que figura en vuelo: `FECAESolicitar` no es idempotente y un segundo envío puede generar dos documentos con CAE, por eso la tarea de autorización no reintenta a propósito. Si la interrupción se prolonga, el Administrador desactiva el punto de venta (HU-E5-05) |
| Recuperación | `billing.reconciliar_comprobantes` corre cada `BILLING_RECONCILIACION_MINUTOS` (cinco por defecto) y pregunta a ARCA por cada comprobante en vuelo sin reenviar: con registro, guarda el CAE; sin registro, lo pasa a `RECHAZADO` aclarando que no llegó a autorizarse, y puede emitirse de nuevo. Si ARCA sigue sin responder, el comprobante no cambia. Certificado de plataforma vencido o delegación revocada: renovar el certificado (1.4), reemplazar `ARCA_CREDENCIAL_PLATAFORMA` en cada servicio que la declara y verificar de nuevo la delegación (ADR-0014) |
| Prevención y medida pendiente | El ticket de acceso de la plataforma se guarda cifrado en la base (`ticket_de_plataforma`) y no en Redis, porque WSAA no emite otro mientras el anterior vive (ADR-0004, ADR-0014). **Medida pendiente:** no hay procedimiento escrito para que la empresa piloto siga vendiendo mientras ARCA no responde (8.15) ni un plazo máximo tolerable |

**Escenario 2 — MercadoPago: notificaciones duplicadas, perdidas o rechazadas**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Crítico (dinero). Analista de Integraciones; decide el Arquitecto de Software |
| Detección | Un cobro sigue «Pendiente» después de que el cliente pagó; en la bitácora, notificaciones descartadas por firma inválida (HS-T1); el webhook responde 503 cuando no puede consultar a MercadoPago |
| Acción inmediata | Notificaciones duplicadas: ninguna, el procesamiento es idempotente por el identificador del cobro en MercadoPago, `payment_id` (caso de uso e índice único). No marcar a mano un cobro como pagado: el sistema no admite confirmación manual sin verificación (HU-E6-08 — Registrar un cobro pagado por transferencia, RN-09) |
| Recuperación | MercadoPago reintenta mientras el webhook responde 503, que es el único caso en que se le pide; una firma inválida se registra y se contesta 200 para que no reintente durante horas. El estado nunca se toma del cuerpo recibido: se consulta a la API de MercadoPago con el token de la empresa. Si se perdieron notificaciones, el repositorio no tiene un barrido que consulte los cobros pagados y no notificados (ni `workers/beat.py` ni `workers/tasks_payments.py`): se concilia contra la cuenta de MercadoPago y se registra el cobro con el número de operación (HU-E6-08), que el sistema confirma contra la API. Que ese camino sirva para un cobro pagado por link se confirma en la validación (PLAN-§6) |
| Prevención y medida pendiente | `MERCADOPAGO_WEBHOOK_SECRET` cargado (8.5): el sistema arranca sin él y, sin secreto, ninguna firma vale y ningún cobro se confirma. `.env.example` declara `MP_WEBHOOK_SECRET`, un nombre que el código no lee. **Medida pendiente:** conciliación diaria de la cuenta de MercadoPago contra el listado de cobros durante la vigilancia (1.16) |

**Escenario 3 — Canal de WhatsApp (Meta) caído o sin entrega**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Mayor. Analista de Integraciones; los Operadores atienden por teléfono (8.15) |
| Detección | En el hilo, mensajes con estado «No se pudo enviar»; en el detalle del cobro (PAN-COB-02), recordatorios fallidos con el motivo en castellano, por ejemplo «Meta estaba saturado y no aceptó el mensaje» o «WhatsApp no está conectado»; ausencia de mensajes entrantes. Al responder desde el hilo, el panel informa «No se pudo enviar el mensaje.» |
| Acción inmediata | Avisar a la empresa y atender por teléfono. Lo recibido antes de la caída ya está guardado: el mensaje entrante se registra antes de interpretarlo. Un mensaje del Operador que no salió no se guarda: se vuelve a enviar |
| Recuperación | Meta reintenta las notificaciones entrantes y el sistema las deduplica por identificador externo (índice único), de modo que un reintento no repite una acción. Los avisos de turno fallidos no se reintentan y la falla queda en el hilo. Los recordatorios de cobro se reintentan solo ante fallas transitorias, con esperas de una y dos horas, y nunca cuando el mensaje pudo haber salido, porque un duplicado es peor que uno faltante (ADR-0011). Restablecido el canal, el Operador revisa los fallidos y contacta al cliente |
| Prevención y medida pendiente | Número de WhatsApp Business verificado por Meta (1.7) y `WHATSAPP_WEBHOOK_SECRET` cargado (8.5): sin él cada notificación se descarta con respuesta 200. Fuera de las 24 horas de la conversación, Meta solo acepta plantillas aprobadas. **Medida pendiente:** los pasos `EMAIL` y `PANEL` de la cadena de recordatorios quedan fallidos hasta que exista su unidad (`payments/infrastructure/envio.py`), por lo que no hay canal alternativo para los recordatorios |

**Escenario 4 — Proveedor del modelo de lenguaje caído, lento o con respuesta inválida**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Menor: el modelo no ejecuta acciones con efecto real. Analista de Integraciones; los Operadores atienden los hilos |
| Detección | Mensajes entrantes que el agente no entiende, más conversaciones en «Esperan a un asesor» y fallas del proveedor en los registros de la API y del worker |
| Acción inmediata | Ninguna técnica: la falla es un estado previsto. Pedir a los Operadores que prioricen «Esperan a un asesor» |
| Recuperación | Con tiempo de espera, rechazo o respuesta mal formada, el intérprete devuelve una lectura de confianza cero; cada lectura bajo el umbral cuenta como intento fallido, el agente ofrece un asesor y al tercer intento escala la conversación. Los diálogos de turno ya abiertos y el pedido explícito de una persona se resuelven sin el modelo. En la ingesta de planillas el mapeo degrada a «Sin asignar» y se completa a mano (ADR-0007). Las FAQ que quedaron sin vector se reindexan cada seis horas |
| Prevención y medida pendiente | Tiempo de espera y `max_tokens` explícitos (`LLM_TIMEOUT_SEGUNDOS`, `LLM_MAX_TOKENS`), salida validada contra un esquema y adaptador simulado prohibido en producción: `LLM_ADAPTADOR` debe valer `anthropic`. **Medida pendiente:** límite de gasto y aviso ante consumo anormal en la cuenta del proveedor; el repositorio no los implementa |

**Escenario 5 — Despliegue defectuoso o migración que falla**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Mayor; Crítico si afecta comprobantes, cobros o el aislamiento. Ejecuta el Analista de Infraestructura y Datos; decide el Arquitecto de Software |
| Detección | El trabajo de despliegue falla en las migraciones, en `verify_rls.py` o en la espera de `/health` (diez minutos: 40 intentos cada 15 segundos); en la consola, un servicio que no arranca. En staging, el primer pedido tras un período de inactividad tarda unos 30 segundos: no es una falla |
| Acción inmediata | Si falló una migración o `verify_rls.py`, ningún servicio se publicó: corregir y repetir desde 3.3. Si el despliegue se publicó y falla, aplicar los criterios de 8.1 y el procedimiento A |
| Recuperación | Procedimiento A. En 32 de las 41 revisiones el `downgrade()` elimina tablas o columnas (recuento a confirmar en 8.3), por lo que la base casi nunca se retrocede: se evita con migraciones aditivas (3.11) y se corrige hacia adelante. La API, el worker y Beat se publican siempre juntos (3.7) |
| Prevención y medida pendiente | `autoDeploy: false` en todos los servicios; orden migraciones, aislamiento, despliegue y `/health`; punto de retorno en 8.8; clasificación de migraciones en 8.7. **Medida pendiente:** la decisión de alojamiento de producción (2.1) puede cambiar la consola y las capacidades que usa el procedimiento A |

**Escenario 6 — Pérdida o corrupción de la base de datos, de Redis o del almacenamiento de objetos**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Crítico (base); Mayor (Redis y almacenamiento). Analista de Infraestructura y Datos; el Arquitecto de Software decide la restauración |
| Detección | `/health` en 503 con `base_de_datos: false` o `redis: false`; errores de conexión en los registros de cada servicio |
| Acción inmediata | Base: detener la escritura, no aplicar migraciones y no regenerar claves. Redis: comprobar que se usa la cadena de conexión interna y la misma región que los servicios |
| Recuperación | **Base.** La restauración a un punto en el tiempo depende del plan contratado y no está confirmada hasta 8.2. Es el último recurso porque devuelve toda la base a un instante anterior: los comprobantes emitidos después existen en ARCA y no en la base (el contador de números se alinea solo con ARCA, pero no hay herramienta que reconstruya las filas), los cobros pagados después no se vuelven a notificar y la bitácora también retrocede. Después de restaurar hay que conciliar contra ARCA y MercadoPago. **Redis.** Es el intermediario y el almacén de resultados de Celery, y guarda el estado del flujo OAuth2 y el registro de idempotencia; no guarda datos de negocio. Si se pierde, se pierden las tareas encoladas: un comprobante en vuelo lo resuelve la reconciliación, los barridos retoman por estado y el flujo OAuth2 en curso se reinicia. La política `noeviction` impide que descarte claves por presión de memoria. **Almacenamiento de objetos.** Lo usan la carga de planillas, el paquete contable y el PDF de los comprobantes; si no responde, esas funciones fallan y se repiten al volver, y el comprobante y su CAE siguen en la base |
| Prevención y medida pendiente | Punto de restauración antes de cada migración (3.4) y antes de la carga inicial (8.19); `verify_rls.py` tras cada migración. **Medida pendiente:** herramienta que reconstruya desde ARCA los comprobantes ausentes después de una restauración, copias de seguridad fuera del proveedor de la base y ensayo periódico de restauración |

**Escenario 7 — Worker o Beat detenido**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Mayor; Crítico si deja comprobantes sin resolver. Analista de Infraestructura y Datos |
| Detección | `/health` no lo cubre. Estado del servicio en la consola; ausencia del registro `barrido_dlq_despachado` (una línea por pasada del barrido de tareas agotadas) durante más de dos intervalos de `DLQ_BARRIDO_MINUTOS`; comprobantes que no salen de `ENVIADO_A_ARCA`; invitaciones de usuarios que no llegan, porque las envía el worker |
| Acción inmediata | Reiniciar el servicio desde la consola. No escalar a más de una instancia el servicio que ejecuta Beat: dos programadores duplican cada barrido y cada correo a los Administradores |
| Recuperación | El worker confirma las tareas al terminarlas y las devuelve a la cola si el proceso muere (`task_acks_late`, `task_reject_on_worker_lost`); los barridos consultan por estado y retoman lo pendiente; Beat reconstruye su calendario en cada arranque y los barridos están alineados al reloj, de modo que una interrupción retrasa cada barrido hasta su siguiente instante programado |
| Prevención | API, worker y Beat se publican juntos (3.7). `SECRETS_ENCRYPTION_KEY` del worker idéntica a la de la API: de lo contrario cada autorización falla con `CredencialIlegible` aunque los datos estén bien |

**Escenario 8 — Secreto expuesto o perdido**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Crítico. Arquitecto de Software; el Analista de Infraestructura y Datos para la base y los entornos; el Analista de Integraciones para los proveedores |
| Detección | `gitleaks` en el hook de commit y en el trabajo `secret-scan` de la CI; un secreto visto en un registro, un Pull Request o un canal; uso anómalo de una cuenta |
| Acción inmediata | Revocar en el proveedor y reemplazar en las variables de cada servicio: certificado de plataforma de ARCA, aplicación de MercadoPago, aplicación de Meta, clave del modelo de lenguaje, credencial de almacenamiento, aplicación OAuth2 de Google y SMTP. Rol de la aplicación en la base: ejecutar de nuevo `provision_app_role.py` con una `APP_ROLE_PASSWORD` nueva, actualizar `DATABASE_URL` y reiniciar (`docs/staging-database.md`, §6). Rol dueño: restablecer la contraseña en la consola del proveedor y actualizar `DATABASE_URL_MIGRATIONS`. `JWT_SECRET`: reemplazarlo invalida los tokens de acceso firmados con el anterior. Ganchos de despliegue: regenerarlos y actualizar los secretos del repositorio |
| Recuperación | Un secreto que llegó al historial de git se trata como comprometido aunque se borre del código. `SECRETS_ENCRYPTION_KEY` no se regenera: rotarla exige volver a cifrar `configuracion_de_integracion` y `ticket_de_plataforma`, y **no existe herramienta de recifrado** (medida pendiente). Si se perdiera sin copia, las credenciales guardadas por las empresas quedan ilegibles y cada una debe reconectar sus integraciones. Registrar el incidente en 8.20 y avisar a las empresas afectadas |
| Prevención | Ninguna credencial en el código ni `.env` en el repositorio (`CLAUDE.md`, §3); copias en el gestor de contraseñas del equipo (2.10); inventario y reemplazo documentados en 8.6 |

**Escenario 9 — Un integrante del equipo no está disponible**

| Aspecto | Contenido |
|---|---|
| Severidad y rol | Mayor, según el rol. Arquitecto de Software, que asigna los reemplazos |
| Detección | Un Pull Request de corrección sin revisar o un incidente sin responsable |
| Acción inmediata | El suplente nominado asume el rol y lo registra en el incidente (8.20) |
| Recuperación | Rige la regla del reparto del equipo: quien prueba corrige y el autor del código revisa el arreglo; si el autor no está disponible o acumula más de dos Pull Requests esperando, revisa el Arquitecto de Software. Un `hotfix/` conserva las mismas verificaciones (8.13) |
| Prevención y medida pendiente | Un suplente por rol (8.17) con acceso a los mismos entornos y secretos. **Medida pendiente:** guardia formal y calendario de cobertura |

### Criterio de listo

- Cada actividad de 8.1 a 8.20 está cerrada o tiene una excepción aprobada por el Arquitecto de Software, y esta sección está en estado listo para la reunión de decisión (1.11).
- La restauración de la base (8.2) y la publicación manual del commit anterior (8.4) están confirmadas con la documentación del proveedor y ensayadas, o su ausencia quedó registrada como riesgo aceptado por escrito.
- El ensayo 1.9 recorrió los tres casos del guion de 8.9 y terminó con la versión anterior sirviendo, `/health` en 200 y `verify_rls.py` sin hallazgos distintos del control 7 esperado en el caso de migraciones aditivas.
- Los criterios de 8.1 están publicados y cada rol sabe qué le toca ante un incidente, incluido su suplente (8.17).
- `SECRETS_ENCRYPTION_KEY` y `ARCA_CREDENCIAL_PLATAFORMA` tienen copia verificada por un segundo rol (8.6).
- Las variables de producción fueron contrastadas con `platform/settings.py` (8.5) y los secretos de webhook están cargados.

### Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| El plan de la base de datos no ofrece restauración a un punto en el tiempo, o su ventana es insuficiente | Media | Alto: sin ella, un daño de datos no tiene retorno | Confirmarlo en 8.2; si no existe, tomar un punto de restauración antes de cada migración (3.4) y de la carga inicial (8.19) y aceptar el riesgo por escrito |
| Restaurar la base deja comprobantes con CAE sin fila local y cobros sin registrar | Baja | Alto: hay documentos fiscales y dinero sin reflejo en el sistema | Restaurar solo como último recurso y corregir hacia adelante; conciliar contra ARCA y MercadoPago (escenario 6); la herramienta de reconstrucción es una medida pendiente |
| Se vuelve atrás el código con una migración ya aplicada | Media | Alto | Migraciones solo aditivas durante el piloto (3.11), clasificadas en 8.7; publicación manual del commit anterior (8.4); ensayo en 1.9 |
| El control 7 de `verify_rls.py` impide que el trabajo de despliegue publique una versión anterior sobre una base más nueva | Media | Medio: la vuelta atrás depende de la consola del proveedor | Ensayar el caso en 8.9 y 8.14; confirmar en 8.4 que la consola permite publicar un commit anterior |
| Pérdida o regeneración de `SECRETS_ENCRYPTION_KEY` | Baja | Alto: las credenciales de las empresas quedan ilegibles | Copia en el gestor de contraseñas (2.10), verificada por un segundo rol (8.6); no regenerarla nunca |
| Un secreto de webhook falta y el sistema arranca igual | Media | Alto: los cobros pagados no se confirman o los mensajes entrantes se descartan sin error visible | Verificarlos en 8.5 y con la validación en producción (1.14) |
| Un worker o Beat se detiene sin que `/health` lo muestre | Media | Alto: comprobantes sin resolver, correos y barridos detenidos | Señales y responsable diario en 8.10; reinicio y reconciliación del escenario 7 |
| Un comprobante con CAE se emite con datos erróneos | Media | Alto: es irreversible y tiene efecto fiscal | Nota de crédito (8.11); validar con el primer comprobante real (1.14) |
| Una corrección urgente salta las verificaciones | Baja | Alto | Flujo `hotfix/` con las mismas verificaciones (8.13); no usar `CHEATSHEET_UNSAFE` sin autorización de la persona responsable, anotada en el PR |
| Un proveedor externo falla y la empresa piloto no tiene un proceso manual de respaldo | Media | Medio: el flujo queda interrumpido | Proceso manual acordado (8.15) y comunicación a las empresas (8.16) |
| La decisión de alojamiento de producción cambia los procedimientos | Media | Medio | Revisar 8.2, 8.4 y el procedimiento A cuando se decida el entorno (2.1) |
