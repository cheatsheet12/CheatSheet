# Unidad: dlq-y-tareas-asincronas

**HUs**: HS-T6   **Contexto dueño**: observability   **Rama**: feature/spreadsheet_sync-sincronizacion-de-planillas

## Qué hace

Le da al sistema un lugar donde una tarea asíncrona muere sin llevarse la cola puesta. Hoy
`PoliticaDeReintentos.agoto_los_intentos()` calcula el techo de reintentos y **no lo llama nadie**:
una tarea que falla siempre reintenta para siempre. Esta unidad agrega el agregado `TareaAsincrona`,
su tabla, y la derivación a la cola de fallos al agotar los intentos, con su registro en la bitácora
del épico 1. Sin pantalla.

## Diseño

- **Dominio**: agregado raíz `TareaAsincrona` en `observability/domain/`, ya anunciado por el
  docstring del contexto. Estado como enum cerrado del DER —`PENDIENTE` · `EN_CURSO` · `COMPLETADA`
  · `FALLIDA` · `DLQ`— con métodos de transición que validan adentro del agregado (patrón State, el
  mismo de `Comprobante` y `Cobro`). Las transiciones legales son las únicas cuatro que existen:
  `PENDIENTE → EN_CURSO`, `EN_CURSO → COMPLETADA`, `EN_CURSO → FALLIDA` (quedan intentos) y
  `FALLIDA → DLQ` (se agotaron). `DLQ` y `COMPLETADA` son terminales.
- **Aplicación**: tres casos de uso en `observability/application/tareas.py` —
  `RegistrarIntentoDeTarea` (marca el arranque y suma el intento), `RegistrarResultadoDeTarea`
  (completa o falla, y al fallar decide si quedan intentos) y `DerivarTareasAgotadasADLQ` (el
  barrido). El tercero es el que consume Beat.
- **Puertos y adaptadores**: `PortRepositorioTareaAsincrona` en `application/ports.py`; el adaptador
  SQLAlchemy en `infrastructure/`, con RLS por `empresa_id` como todas las tablas del sistema.
- **Otros contextos**: ninguno. `observability` es OHS y no depende de nadie — la misma razón por la
  que `cimientos-y-bitacora` pudo ir primero en el épico 1. El evento de auditoría se publica por el
  mecanismo que esa unidad ya dejó, no por uno nuevo.
- **Frontend**: **No aplica.** Leer la DLQ es HU-E12-01/02, épico 10.

## Infraestructura

- **Migraciones**: una, `0011_tarea_asincrona`. Tabla `tarea_asincrona` exactamente como el DER
  (`id`, `empresa_id`, `tipo`, `payload` jsonb, `estado`, `intentos`, `clave_idempotencia`,
  `resultado`, timestamps) más el enum `estado_tarea`. Índice parcial sobre
  (`empresa_id`, `estado`) filtrado a `FALLIDA`, que es lo único que el barrido consulta. Reversible;
  sin backfill — no hay tareas históricas que migrar.
- **Trabajo asíncrono**: entrada de Beat `barrido_dlq`, dueño el worker 4, ya reservada en la tabla
  de [`workers/beat.py`](../../../backend/src/cheatsheet/workers/beat.py). Intervalo desde `Settings`
  y no hardcodeado, por la razón que ese módulo ya explica. El barrido es idempotente por
  construcción: derivar a `DLQ` una tarea que ya está en `DLQ` no es una transición legal, así que
  correrlo dos veces no hace nada la segunda vez.
- **Configuración**: `DLQ_BARRIDO_MINUTOS` en `backend/.env.example`.
- **Integraciones externas**: **No aplica.**

## Decisiones

**La DLQ es un estado en una tabla, no una sexta cola de Celery.** ADR-003 fijó cinco colas y cinco
workers, y cada cola es un deployment: una sexta costaría un proceso más para siempre. RN-03 solo
pide que una tarea en la DLQ **no bloquee el procesamiento de las demás**, y un estado terminal ya lo
garantiza — la tarea deja de reencolarse y el worker sigue con la siguiente. Una cola aparte además
sería peor para RN-04, que pide poder analizar y reprocesar: una fila se consulta con SQL, un mensaje
en una cola no.

**`TareaAsincrona` no es `RegistroDeAuditoria`, aunque las dos vivan en `observability`.** La
bitácora es inmutable y registra operaciones de negocio; `TareaAsincrona` es estado de ejecución y
muta en cada intento. Meterlas en la misma tabla rompería la inmutabilidad que el épico 1 construyó a
propósito. La relación es al revés: agotar los intentos **publica** un evento auditable
`TareaAsincronaDerivadaADLQ` (RN-04), que es un renglón de la bitácora y no reemplaza a la fila.

## Riesgos que obligan a tests

- [ ] Toca dinero — no
- [ ] Toca comprobantes fiscales / CAE — no
- [ ] Consume un webhook — no
- [x] **Agrega datos con `empresa_id`** → test de aislamiento entre empresas
- [ ] Usa salida de un LLM — no
- [ ] Datos personales o fiscales — `payload` **puede** llevarlos (una fila de planilla con un CUIT).
      No sale del sistema y nunca va a un LLM, pero por eso `resultado` guarda el motivo del fallo y
      no el payload entero, y el logging estructurado nunca lo escribe.

## Archivos a tocar

- [ ] `backend/src/cheatsheet/contexts/observability/domain/tarea_asincrona.py`
- [ ] `backend/src/cheatsheet/contexts/observability/application/tareas.py`
- [ ] `backend/src/cheatsheet/contexts/observability/application/ports.py`
- [ ] `backend/src/cheatsheet/contexts/observability/infrastructure/` — modelo y repositorio
- [ ] `backend/migrations/versions/0011_tarea_asincrona.py`
- [ ] `backend/src/cheatsheet/workers/beat.py` — la entrada del barrido
- [ ] `backend/src/cheatsheet/workers/base.py` — conectar `agoto_los_intentos` con la derivación
- [ ] `backend/.env.example`
- [ ] `backend/tests/contexts/observability/…`

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Una tarea que falla con intentos disponibles queda `FALLIDA` y se reintenta (RN-01) | unit | pendiente |
| 2 | Una tarea que agota el máximo configurado pasa a `DLQ` (RN-02) | unit | pendiente |
| 3 | La derivación a DLQ publica `TareaAsincronaDerivadaADLQ` en la bitácora (RN-04) | unit | pendiente |
| 4 | Una transición ilegal (`COMPLETADA → DLQ`, `DLQ → EN_CURSO`) es rechazada por el agregado | unit | pendiente |
| 5 | Con una tarea en `DLQ`, el barrido sigue procesando las demás sin bloquearse (RN-03) | unit | pendiente |
| 6 | El barrido corrido dos veces no vuelve a derivar lo ya derivado | unit | pendiente |
| 7 | Una empresa no ve las tareas de otra | integración (PostgreSQL) | pendiente |
| 8 | `resultado` guarda el motivo del fallo y nunca el payload completo | unit | pendiente |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 — Plan | 2026-09-07 | pendiente de aprobación |
| 2 — Verificación | — | — |
| 3 — PR | — | al cierre del épico, con las cinco unidades |
