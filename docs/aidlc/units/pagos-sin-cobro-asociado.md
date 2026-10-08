# Unidad: pagos-sin-cobro-asociado

**HUs**: HU-E6-03, HS-T1 **Contexto dueño**: payments **Rama**: feature/payments-pagos-sin-cobro-asociado

> Origen: Gate 2 de `cobro-con-clave-de-idempotencia` (2026-10-06, decisión de Luciano). Ese plan
> dejó como riesgo aceptado la «preferencia huérfana pagable» y anotó la solución a evaluar:
> «guardar el cobro antes de pedir el link, encontrar el pago también por `external_reference` y
> alertar el pago sin cobro» (`units/cobro-con-clave-de-idempotencia.md:142-150` y `:246`).
> Depende de `cobro-con-clave-de-idempotencia` (mergeada, #102). Tamaño: M.

## Qué hace

Hoy un pago aprobado de MercadoPago que no se puede atar a un cobro **se pierde en silencio**:
`ConfirmarPago` deja un log `info` (`webhook_sin_cobro_asociado`) y contesta 200, así que
MercadoPago no reintenta y el pago no queda registrado en ningún lado. Esta unidad hace dos cosas:

1. **Encuentra el cobro por `external_reference`** (que ya viaja con el id del cobro desde
   `nuevo-cobro-desde-su-panel`), y deja de depender de un `preference_id` que, según la
   documentación de MercadoPago, el pago no trae.
2. **Registra y alerta todo pago aprobado que no se puede imputar** —sin cobro, o sobre un cobro
   que ya estaba pagado— como un `PagoSinImputar` con su monto en `Decimal`, idempotente por
   `payment_id`, con evento de bitácora `Resultado.ERROR` que `NotificarPorEventos` convierte en
   notificación de severidad alta.

**Fuera de esta unidad** (salvo lo que decidan las preguntas):
- Una pantalla para listar o resolver pagos sin imputar: no hay HU ni prototipo (P8).
- Imputar a mano un pago sin imputar a un cobro: es una operación sobre dinero sin historia que la
  pida (P8).
- El pago sobre un cobro **cancelado**: ya lo resolvió `cancelacion-invalida-el-link`
  (`registrar_pago_huerfano`, `confirmacion.py:167-209`) y se mantiene igual (P7).
- La concurrencia de dos notificaciones simultáneas del mismo pago en la tabla `cobro`
  (`TODO.md` §20.7): esta unidad solo garantizaba que la tabla nueva no devolviera 500 por eso. **La carrera de la confirmación se cerró después, en la revisión independiente** (ver «Correcciones de la revisión independiente»).

## Qué existe hoy (evidencia)

- **La preferencia ya lleva el id del cobro.** `PasarelaMercadoPago.crear_link` manda
  `"external_reference": str(cobro.id)` (`backend/src/cheatsheet/contexts/payments/infrastructure/pasarela.py:108-110`).
- **Pero el pago se busca solo por preferencia.** `ConfirmarPago._encontrar` usa
  `pago.preference_id` y `buscar_por_preference_id` (`application/confirmacion.py:111-115`); si no
  encuentra, log `info` y `ResultadoDeConfirmacion(aprobado=False)` (`confirmacion.py:102-107`).
  El router contesta 200 (`api/routers/webhooks.py:88-101`).
- **El `preference_id` del pago se lee de un campo que no es la preferencia.**
  `_preferencia_de` toma `datos["preference_id"]` o, si falta, `datos["order"]["id"]`
  (`pasarela.py:312-314`). El tipo `PaymentResponse` del SDK oficial no tiene `preference_id`, y
  `order.id` es el id de la **merchant order** (`PaymentOrder { id: number; type }`), no el de la
  preferencia (fuentes abajo). El comentario de `pasarela.py:138` ya dice que
  `external_reference` «sí viene», pero no se lee. **Si el sandbox lo confirma, hoy ningún pago real
  encontraría su cobro**: es la causa más probable de «pagos sin cobro» en producción, mucho antes
  que la preferencia huérfana. Ningún test usa un cuerpo de pago real
  (`tests/contexts/payments/infrastructure/test_pasarela_contrato.py:208-209` arma
  `{"id", "status", ...}` y la pasarela simulada resuelve por su propio diccionario,
  `pasarela_simulada.py:89-97`).
- **La preferencia huérfana no se puede pagar en la práctica.** `GenerarCobro` pide el link antes de
  persistir (`application/generacion_de_cobro.py:127-133`) y la respuesta HTTP sale **después** del
  commit (`api/routers/cobros.py:290-311`, `platform/database.py:178-181`). Si el commit falla, la
  URL del link nunca llega al panel ni a un recordatorio: nadie la tiene para pagarla. El riesgo es
  teórico; aun así, si llegara un pago por esa preferencia, esta unidad lo registraría y alertaría
  (P1).
- **Regenerar el link no invalida el anterior en MercadoPago.** `RegenerarLink.ejecutar` crea la
  preferencia nueva y reemplaza el objeto (`application/cobros.py:165-173`), pero el link viejo sigue
  pagable hasta su `expiration_date_to`. Un pago por el link viejo trae (si trae) el
  `preference_id` viejo, que ya no está en la fila: hoy es un pago sin cobro. Con la búsqueda por
  `external_reference` se imputa al cobro correcto. HU-E6-03 dice «el sistema invalida el anterior»
  (P9).
- **Un segundo pago sobre un cobro ya pagado se descarta como repetido.** Con otro `payment_id`,
  `ConfirmarPago._aprobar` lo trata como `ya_procesado` (`confirmacion.py:128-134`): la plata entró
  y nadie se entera. Con el link viejo pagable, pagar los dos links es posible (P4).
- **Idempotencia actual**: `buscar_por_payment_id` sobre `cobro.mp_payment_id` antes de llamar a
  MercadoPago (D20, `confirmacion.py:87-93`), con índice único `uq_cobro_operacion`
  `(empresa_id, COALESCE(numero_de_operacion, mp_payment_id))` (`infrastructure/models.py:120-126`).
- **Alertas**: `NotificarPorEventos` convierte todo `EventoAuditable` con `Resultado.ERROR` en
  notificación, sin romper la transacción (`contexts/observability/application/notificaciones.py:110-136`).
  Es el mismo camino que ya usa `pago_sobre_cobro_cancelado`.

## Contratos externos (MercadoPago)

| Dato | Qué dice la fuente | Estado |
|---|---|---|
| `GET /v1/payments/{id}` trae `external_reference` («Integrator-supplied external reference for reconciliation») y `order: { id, type }` («Order associated with this payment»); **no** trae `preference_id` | Tipos del SDK oficial: [sdk-nodejs `payment/commonTypes.ts`](https://github.com/mercadopago/sdk-nodejs/blob/master/src/clients/payment/commonTypes.ts) | A confirmar en sandbox (`TODO.md` §20.17) |
| `order.id` es la merchant order; la merchant order sí tiene `preference_id` («Checkout preference that originated this order»), `external_reference` y `payments` | [sdk-nodejs `merchantOrder/commonTypes.ts`](https://github.com/mercadopago/sdk-nodejs/blob/master/src/clients/merchantOrder/commonTypes.ts); el ejemplo IPN oficial obtiene la orden con `$payment->order->id` ([IPN](https://www.mercadopago.com.br/developers/pt/docs/adobe-commerce/resources/notifications/ipn)) | Fuente secundaria (SDK); §20.17 |
| La preferencia acepta `external_reference` y lo propaga al pago | [Checkout Pro — `POST /checkout/preferences`](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro/how-tos/improve-payment-approval/industry-data); `PreferenceResponse.external_reference` en el SDK | §20.17 |
| Después del 200 se consulta el pago con `GET /v1/payments/{id}` usando el `data.id` de la notificación | [Notificaciones de Checkout Pro](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/payment-notifications) | Ya implementado |
| `transaction_amount` del pago es igual al precio del item de la preferencia (sin recargo de cuotas, que va en `transaction_details.total_paid_amount`) | No encontré una afirmación primaria explícita | **No verificado**: §20.18 |
| MercadoPago puede generar otro `payment_id` para el mismo intento («reprocesa con ids distintos», comentario de `confirmacion.py:129-131`) | Sin fuente | **No verificado**: §20.19 |

Las páginas de referencia de la API (`/developers/*/reference/payments/_payments_id/get`)
devolvieron 404/403 a la consulta automática; por eso la fuente de los campos es el SDK oficial.

## Diseño

- **Dominio** (`contexts/payments/domain/pago_sin_imputar.py`, nuevo):
  - Agregado `PagoSinImputar` (lenguaje ubicuo: un pago que entró y no se imputó a ninguna deuda):
    `id`, `empresa_id`, `mp_payment_id: str`, `referencia_externa: str | None`,
    `cobro_id: UUID | None` (el cobro encontrado cuando lo hay, p. ej. ya pagado),
    `motivo: MotivoSinImputar`, `monto: Decimal | None` (redondeado con `redondear`,
    `ROUND_HALF_UP`, nunca desde `float`), `fecha_aprobacion: datetime | None`, `recibido_en`.
  - `MotivoSinImputar` (StrEnum cerrado): `SIN_COBRO` (no hay cobro con esa referencia ni esa
    preferencia), `COBRO_YA_PAGADO` (P4), `MONTO_DISTINTO` (P5).
  - Sin estados ni transiciones: es un hecho registrado, como `registrar_pago_huerfano` (P8).
- **Aplicación** (`application/confirmacion.py`):
  - `PagoRecibido` gana `referencia_externa: str | None = None`.
  - `_encontrar`: primero `referencia_externa` → si es un UUID válido, `buscar_por_id` (bajo RLS:
    una referencia de otra empresa no se ve); si no, `preference_id` como hoy (P2).
  - Orden completo de `ejecutar`: `buscar_por_payment_id` en cobros **y** en pagos sin imputar (las
    dos son la primera línea de D20, antes de llamar a MercadoPago) → `consultar_pago` → no
    aprobado: igual que hoy → encontrar cobro → `CANCELADO`: huérfano como hoy → cerrado
    (`APROBADO`, `REEMBOLSADO*`): `COBRO_YA_PAGADO` → monto distinto: `MONTO_DISTINTO` → aprobar.
    Sin cobro: `SIN_COBRO`.
  - Nuevo método privado `_registrar_sin_imputar(motivo, pago, cobro?)`: guarda el agregado y
    publica `EventoAuditable(accion="pago_sin_imputar", entidad_afectada="PagoSinImputar:{id}",
    resultado=Resultado.ERROR, usuario_id=None)`; log `warning` sin datos personales (ids y
    motivo, nunca el pagador).
  - `ResultadoDeConfirmacion` gana `sin_imputar: bool = False` (mismo criterio que `huerfano`).
  - Si `confirmacion.py` pasa de 400 líneas, el registro de pagos sin imputar se extrae a
    `application/pagos_sin_imputar.py`.
- **Puertos y adaptadores**:
  - `PortRepositorioPagoSinImputar` (en `application/ports_de_pagos.py`, nuevo, porque `ports.py`
    tiene 366 líneas): `agregar(pago)` y `buscar_por_payment_id(payment_id)`.
  - `RepositorioPagoSinImputarPostgres` (`infrastructure/repositorio_pago_sin_imputar.py`, nuevo).
    Un `IntegrityError` del índice `uq_pago_sin_imputar_payment` (por nombre) se traduce a «ya
    registrado» y no a 500: dos notificaciones simultáneas del mismo pago dejan una sola fila.
  - `PasarelaMercadoPago.consultar_pago` lee `external_reference`; `_preferencia_de` deja de tomar
    `order.id` (P2). `PasarelaSimulada.consultar_pago` devuelve la referencia del cobro que creó el
    link, para que el camino feliz local siga funcionando.
  - `RegenerarLink`: después de crear la preferencia nueva, `invalidar_link` sobre la anterior
    (puerto existente de `cancelacion-invalida-el-link`); si la invalidación falla, la operación
    entera falla y la preferencia nueva queda sin publicar (P9).
- **Otros contextos**: ninguno nuevo. La notificación llega por el publicador de eventos existente
  (`payments` → `observability`), igual que `pago_sobre_cobro_cancelado`.
- **Frontend**: no aplica (P8).
- **ADR**: no hace falta (P10). No hay arista nueva en el Context Map ni estrategia transversal: es
  una tabla de `payments` y un cambio en cómo el ACL lee una respuesta de MercadoPago.

## Infraestructura

- **Migraciones**: una de Alembic, **número = el siguiente libre al mergear** (hoy el head de
  `develop` es `0035`; `down_revision` al head real en ese momento). En esta rama quedó como
  `0036_pago_sin_imputar.py` (`down_revision = "0035"`); **se renumera y se re-apunta al integrar**
  si `develop` tomó el número.
  - Tabla `pago_sin_imputar`: `id UUID PK`, `empresa_id UUID NOT NULL` (FK a `empresa`),
    `mp_payment_id VARCHAR(120) NOT NULL`, `referencia_externa VARCHAR(256) NULL`,
    `cobro_id UUID NULL` (FK a `cobro`), `motivo VARCHAR(20) NOT NULL` con `CHECK` sobre los tres
    valores, `monto NUMERIC(14,2) NULL`, `fecha_aprobacion TIMESTAMPTZ NULL`,
    `recibido_en TIMESTAMPTZ NOT NULL`.
  - Índice único `uq_pago_sin_imputar_payment (empresa_id, mp_payment_id)`.
  - **RLS y permisos como `reembolso` (migración `0027_reembolsos.py:116`)**: RLS forzada,
    política `aislamiento_por_empresa` por `app.current_empresa`, y la tabla es **de solo agregar**
    (`GRANT SELECT, INSERT`, sin `UPDATE` ni `DELETE`): un pago sin imputar es un hecho, no se edita.
  - Reversible: `downgrade` borra la tabla (se pierden los registros de pagos sin imputar; los
    eventos de bitácora y las notificaciones quedan). Sin backfill: los pagos perdidos antes de la
    unidad no se pueden reconstruir desde nuestros datos.
  - El modelo va en `infrastructure/models.py` (módulo ya registrado), así que `migrations/env.py`
    no cambia; se confirma al implementar.
- **Trabajo asíncrono**: no aplica. Todo ocurre dentro del request del webhook (D21).
- **Configuración**: no aplica. Sin variables nuevas.
- **Integraciones externas**: MercadoPago, sin endpoints nuevos. `consultar_pago` conserva timeout,
  reintentos con backoff y el aplanado a `PasarelaNoDisponible` (503 → MercadoPago reintenta).
  `invalidar_link` ya existe con el mismo tratamiento. Tests sin red: `httpx.MockTransport` y
  `PasarelaSimulada`.

## Riesgos que obligan a tests (marcar los que apliquen)
- [x] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → el monto del pago se lee desde el texto
  (`_monto_de`), se redondea con `redondear` y se compara contra el cobro en `Decimal`
  (`1210.005` contra `1210.01` es igual; `1210.02` no)
- [ ] Toca comprobantes fiscales / CAE → no aplica; un pago sin imputar **no** baja el saldo de
  ningún comprobante (D26)
- [x] Consume un webhook → la misma notificación de un pago sin imputar, dos veces o en paralelo,
  deja **una** fila y **un** evento; la segunda no llama a MercadoPago
- [x] Agrega datos con `empresa_id` → RLS en la tabla nueva; una `external_reference` con el id de
  un cobro de otra empresa no lo encuentra (queda `SIN_COBRO` en la empresa que recibió el pago)
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales → no se guardan datos del pagador; logs solo con ids

## Archivos a tocar

### Backend
- [x] `backend/src/cheatsheet/contexts/payments/domain/pago_sin_imputar.py` (nuevo)
- [x] `backend/src/cheatsheet/contexts/payments/application/ports.py` (`PagoRecibido.referencia_externa`)
- [x] `backend/src/cheatsheet/contexts/payments/application/ports_de_pagos.py` (nuevo: `PortRepositorioPagoSinImputar`)
- [x] `backend/src/cheatsheet/contexts/payments/application/confirmacion.py` (búsqueda, motivos, registro)
- [x] `backend/src/cheatsheet/contexts/payments/application/cobros.py` (`RegenerarLink` invalida el anterior, si P9)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/pasarela.py` (`external_reference`, `_preferencia_de`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/pasarela_simulada.py`
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/models.py` (`PagoSinImputarORM`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/repositorio_pago_sin_imputar.py` (nuevo)
- [x] `backend/src/cheatsheet/api/routers/webhooks.py` (armar el repositorio nuevo; el cableado vive en `infrastructure/ensamblado.py`, también tocado)
- [x] `backend/migrations/versions/0036_pago_sin_imputar.py` (nuevo; número provisorio, se renumera al integrar)
- [x] `backend/tests/contexts/payments/domain/test_pago_sin_imputar.py` (nuevo)
- [x] `backend/tests/contexts/payments/application/test_confirmacion.py`
- [x] `backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py` (regenerar, si P9)
- [x] `backend/tests/contexts/payments/infrastructure/test_pasarela_contrato.py`
- [x] `backend/tests/integracion/test_pagos_sin_imputar_postgres.py` (nuevo; solo CI)
- [x] `backend/tests/integracion/test_migracion_0036.py` (nuevo; solo CI)
- [x] `backend/tests/integracion/conftest.py` (`BORRADOS`: `pago_sin_imputar` antes de `cobro`)
- [x] `backend/tests/contexts/payments/application/test_pagos_sin_imputar.py` (nuevo)
- [x] `backend/tests/integracion/test_api_mercadopago.py` (webhook de punta a punta; solo CI)

### Frontend
- No aplica (P8).

### Docs
- [x] `docs/aidlc/units/pagos-sin-cobro-asociado.md` (este plan)
- [x] `docs/aidlc/units.md` (fila de la unidad: `Rama`, estado)
- [x] `docs/aidlc/TODO.md` (§20.17–20.19 y §22.43)
- [x] `docs/aidlc/epicas/06-cobros-y-recordatorios/pendientes.md` (#15: la pantalla y la imputación manual)

**Tamaño estimado**: ~750 líneas de autoría (≈ 300 de código, ≈ 400 de tests, ≈ 50 de migración).
Supera la referencia de 400; se entrega en dos commits de unidad de trabajo (1: lectura de
`external_reference` + búsqueda + regenerar; 2: `PagoSinImputar`, tabla y alerta) dentro de un
solo PR, salvo que se pida partirlo.

## Casos de prueba

Modo: **test primero**. Los de PostgreSQL y API no corren en la máquina local (sin Docker): se
escriben y los confirma la CI.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: `consultar_pago` con un cuerpo de pago real (`external_reference`, `order: {id, type}`, sin `preference_id`) devuelve `referencia_externa` y **no** toma `order.id` como preferencia | contrato (ACL) | hecho · RED observado (`AttributeError`: `PagoRecibido` no tenía `referencia_externa`) · `test_pasarela_contrato.py` |
| 2 | RED: un pago aprobado con `referencia_externa` = id de un cobro `PENDIENTE` y sin preferencia lo aprueba (estado, `mp_payment_id`, saldo del comprobante, bitácora `confirmar_pago`) | unit | hecho · RED observado (2 fallas: sin preferencia el pago no encontraba el cobro y quedaba en el log) · `test_pagos_sin_imputar.py` |
| 3 | Un pago con la preferencia y sin referencia sigue encontrándose por preferencia (compatibilidad) | unit | hecho · pasa antes y después (compatibilidad): no RED por diseño |
| 4 | Referencia que no es un UUID, o UUID sin cobro → `PagoSinImputar(SIN_COBRO)`, evento `pago_sin_imputar` con `Resultado.ERROR`, ningún cobro tocado | unit | hecho · RED observado (`TypeError`: `ConfirmarPago` sin `sin_imputar`) · tres variantes: sin referencia, no UUID, UUID sin cobro |
| 5 | RED: segundo pago (otro `payment_id`) sobre un cobro `APROBADO` → `COBRO_YA_PAGADO` con `cobro_id`; el cobro y el saldo no cambian | unit | hecho · RED observado (igual que el 4) · y los tres tests viejos de «otro `payment_id` sobre cobro cerrado» ahora afirman `sin_imputar` |
| 6 | Monto distinto (`1210.02` contra `1210.01`) → `MONTO_DISTINTO`, el cobro sigue `PENDIENTE`; `1210.005` contra `1210.01` aprueba | unit | hecho · RED observado · incluye el caso sin `transaction_amount` (se aprueba como antes) |
| 7 | Pago no aprobado (`pending`, `in_process`) sin cobro → no se registra nada (como hoy) | unit | hecho · parametrizado con `pending`, `in_process`, `rejected`, `authorized` |
| 8 | RED: la misma notificación de un pago sin imputar dos veces → una fila, un evento, una sola llamada a la pasarela | unit | hecho · RED observado · más la carrera: la lectura previa no lo ve y el índice lo rechaza, sin segundo evento |
| 9 | Pago sobre cobro `CANCELADO` sigue por `registrar_pago_huerfano` sin cambios | unit | hecho · regresión, no RED |
| 10 | El monto del pago sin imputar se guarda en `Decimal` desde el texto, redondeado `ROUND_HALF_UP` | unit (dominio) | hecho · RED observado (`ModuleNotFoundError` de `pago_sin_imputar`) · `test_pago_sin_imputar.py` |
| 11 | RED (si P9): regenerar el link invalida la preferencia anterior; si la invalidación falla, no se guarda el link nuevo y no hay bitácora | unit | hecho · RED observado (2 fallas) · más: regenerar un cobro sin link no invalida nada |
| 12 | `PagoSinImputar` sobrevive la ida y vuelta en PostgreSQL con `Numeric(14,2)` | integración (PostgreSQL) | hecho · escrito, **solo CI** (PostgreSQL) · `test_pagos_sin_imputar_postgres.py` |
| 13 | RLS: la empresa B no ve los pagos sin imputar de A; una referencia con el id de un cobro de A recibida por B queda `SIN_COBRO` en B | integración (PostgreSQL) | hecho · escrito, **solo CI** (PostgreSQL), con la referencia cruzada por `ConfirmarPago` real |
| 14 | Dos inserciones concurrentes del mismo `(empresa, payment_id)` → una fila; la segunda se traduce a «ya registrado», no a 500 | integración (PostgreSQL) | hecho · escrito, **solo CI** (PostgreSQL), con `asyncio.gather` y el `IntegrityError` ajeno que no se traga |
| 15 | La migración sube y baja limpia | integración (PostgreSQL) | hecho · escrito, **solo CI** (PostgreSQL) · `test_migracion_0036.py` |
| 16 | Webhook de punta a punta: pago sin cobro → 200, fila y notificación de severidad alta | integración (API) | hecho · escrito, **solo CI** (PostgreSQL y Redis) · `test_api_mercadopago.py` (sin cobro y camino feliz) |
| 17 | En sandbox: los campos reales del pago, monto y reproceso (§20.17–20.19) | manual | pendiente: `TODO.md` §20.17–20.19 (sandbox) |
| 18 | En staging (Render): regenerar un link, pagar el viejo y ver que se rechaza (si P9) o que se imputa; pagar dos veces y ver el aviso | manual | pendiente: `TODO.md` §22.43 (staging) |

## Verificaciones que no se pueden hacer sin sandbox o navegador

- §20.17 — `GET /v1/payments/{id}` de un pago de Checkout Pro: ¿trae `external_reference` igual al
  que mandó la preferencia? ¿trae `preference_id`? ¿`order.id` es la merchant order?
- §20.18 — `transaction_amount` es igual al precio del item aun con cuotas o recargos.
- §20.19 — ¿MercadoPago genera un `payment_id` distinto para el mismo intento al reprocesar?
  Si pasa, el caso `COBRO_YA_PAGADO` daría falsos avisos.
- §22.43 — prueba en staging del link regenerado y del doble pago.

## Preguntas para el Gate 1

Responder en bloque (por ejemplo «todas con la recomendación» o «P4: b»).

1. **Preferencia huérfana: ¿se cambia cómo se crea un cobro?** La nota del Gate 2 proponía
   «guardar el cobro antes de pedir el link». Hacerlo exige dos transacciones, un estado nuevo
   («sin link») y un camino de limpieza cuando MercadoPago falla, y contradice el criterio de
   HU-E6-03 «no crea el cobro». Además, la URL de esa preferencia nunca llega a nadie: la respuesta
   sale después del commit (`routers/cobros.py:290-311`).
   (a) No cambiar la creación: con la búsqueda por referencia y el registro de pagos sin imputar,
   un pago imposible-pero-posible sobre esa preferencia queda guardado y alertado.
   (b) Guardar antes de pedir el link, como decía la nota.
   (c) Id del cobro derivado de la clave de idempotencia (`uuid5`), para que un reintento herede la
   referencia de la preferencia huérfana.
   **Recomendación: (a).**
2. **Orden de búsqueda.** Primero `external_reference` (si es un UUID), después `preference_id`; y
   `_preferencia_de` deja de usar `order.id`, que es la merchant order. **Recomendación: sí.**
3. **¿Qué pagos sin cobro se registran?** (a) Todo pago aprobado que llega a
   `/webhooks/mercadopago/{empresa}` y no encuentra cobro, tenga o no referencia; (b) solo los que
   traen una referencia con forma de UUID. La ruta lleva la empresa y solo la usan nuestras
   preferencias, así que lo que llega ahí es, casi seguro, nuestro. **Recomendación: (a)**, con el
   mismo motivo `SIN_COBRO`.
4. **Segundo pago sobre un cobro ya pagado** (otro `payment_id`; hoy se descarta como repetido).
   (a) Registrar `COBRO_YA_PAGADO` y alertar; (b) dejarlo como hoy. **Recomendación: (a)**: entró
   plata y alguien tiene que devolverla. Queda sujeto a §20.19.
5. **¿Se compara el monto al imputar?** Hoy `ConfirmarPago` no lo compara. Con la búsqueda por
   referencia, comparar en `Decimal` y, si difiere, no aprobar y registrar `MONTO_DISTINTO`.
   **Recomendación: sí.** Queda sujeto a §20.18 (cuotas).
6. **Pagos no aprobados sin cobro** (`pending`, `in_process`, `rejected`): **Recomendación: no se
   registran**; solo el aprobado mueve plata.
7. **Dónde se guarda.** (a) Tabla y agregado nuevos `pago_sin_imputar`; (b) columnas en `cobro`
   (imposible para `SIN_COBRO`: no hay fila). El pago sobre un cobro cancelado sigue con su
   mecanismo actual y no se migra. **Recomendación: (a).**
8. **Pantalla e imputación manual.** No hay HU ni prototipo para listar o resolver pagos sin
   imputar. **Recomendación:** fuera de la unidad; el aviso de severidad alta y la bitácora son la
   visibilidad, y la pantalla queda anotada en `pendientes.md` del épico 6 para una historia nueva.
9. **Regenerar el link invalida el anterior en MercadoPago.** Es un criterio de HU-E6-03 que hoy no
   se cumple y es la fuente viva de pagos por links viejos. Crear el nuevo, después invalidar el
   viejo; si la invalidación falla, la operación entera falla (el link nuevo nunca se publica).
   **Recomendación: incluirlo** en esta unidad (puerto ya existente, ~20 líneas más tests).
10. **ADR.** No hay arista nueva ni estrategia transversal. **Recomendación: sin ADR**; la decisión
    queda en este plan.
11. **Nombre del lenguaje ubicuo.** `PagoSinImputar` / `pago_sin_imputar` (cubre los tres motivos)
    en lugar de `PagoSinCobro`. **Recomendación: `PagoSinImputar`.**

## Estado de la implementación (2026-10-07)

Tres commits de trabajo en la rama: (1) lectura de `external_reference`, búsqueda por referencia y
`RegenerarLink` que invalida el link anterior; (2) `PagoSinImputar`, tabla, repositorio, alerta y
cableado del webhook; (3) documentación. Gates locales (con el `.venv` del repo principal y
`PYTHONPATH` al worktree): `ruff format --check`, `ruff check`, `mypy` y `pytest` verdes; los tests
contra PostgreSQL y Redis quedan para la CI del PR (no hay Docker local, y **nunca** se corren
contra Neon ni staging) y `test_guards.sh` no corre local (falta `jq`).

### Hecho

- `PagoRecibido.referencia_externa`; `PasarelaMercadoPago.consultar_pago` la lee de
  `external_reference`; `_preferencia_de` ya no cae en `order.id` (la merchant order).
- `ConfirmarPago._encontrar`: primero la referencia (UUID válido, `buscar_por_id` bajo RLS), después
  la preferencia. `PasarelaSimulada` devuelve la referencia del cobro que creó el link.
- `RegenerarLink` crea el link nuevo, **invalida el anterior** y recién entonces guarda y registra; si
  la invalidación falla, no se guarda nada.
- `PagoSinImputar` / `MotivoSinImputar` (dominio), `PortRepositorioPagoSinImputar` (puerto aparte),
  `RegistrarPagoSinImputar` (aplicación, en su propio módulo: `confirmacion.py` quedó en 306 líneas),
  `RepositorioPagoSinImputarPostgres` y migración `0036`.
- `ConfirmarPago`: orden completo del diseño. `ResultadoDeConfirmacion.sin_imputar`.

### Decisiones tomadas al implementar (ninguna cambia una respuesta del Gate 1)

- **Migración `0036`**: el head de esta rama es `0035`. El número es provisorio y se renumera al
  integrar si `develop` lo tomó (lo dice el docstring de la migración).
- **`CHECK` extra `ck_pago_sin_imputar_cobro`** `(motivo = 'SIN_COBRO') = (cobro_id IS NULL)`: el plan
  decía «`cobro_id` cuando lo hay»; el dominio ya lo exige y el esquema lo repite, como en
  `reembolso`.
- **Referencia larga**: se acota a 256 caracteres en vez de rechazarla; un `external_reference` de un
  tercero no puede tumbar el registro de un pago que entró.
- **Pago aprobado sin `transaction_amount`**: se aprueba como antes (no hay con qué contradecir al
  cobro). Solo un monto informado y distinto da `MONTO_DISTINTO`.
- **Repetición de un pago sin imputar**: `aprobado=False, ya_procesado=True, sin_imputar=True`, sin
  llamar a MercadoPago ni volver a avisar. Si dos notificaciones compiten, la que pierde el índice
  único devuelve lo mismo y no publica evento.
- **`ConfirmarPago` exige `sin_imputar`** (argumento obligatorio): no hay forma de construirlo sin
  registro y volver a perder pagos en silencio.
- **Tests existentes cambiados por P4**: los tres que afirmaban `ya_procesado` para «otro
  `payment_id` sobre un cobro cerrado» (aprobado, aprobado con fecha, reembolsado) ahora afirman
  `sin_imputar` y, el último, el evento `pago_sin_imputar`. El mismo `payment_id` sigue siendo
  idempotencia.
- **Orden en `RegenerarLink`**: la invalidación va antes de `guardar`. Si MercadoPago confirma y
  `guardar` falla después, el cobro queda con el link viejo muerto: se resuelve repitiendo
  «regenerar» (la invalidación es idempotente). La preferencia nueva de una invalidación fallida
  queda sin publicar en MercadoPago, mismo riesgo aceptado que en P1.
- **Notificación**: el texto lo arma `NotificarPorEventos` («`pago_sin_imputar` falló sobre
  `PagoSinImputar:<id>`»); no se tocó `observability`.

### Correcciones de la revisión independiente (2026-10-07)

1. **Tamaño de archivo**: `infrastructure/pasarela.py` tenía 408 líneas (límite 400, `CLAUDE.md` §5).
   Los lectores de respuesta (`preferencia_de`, `referencia_de`, `monto_de`, `moneda_de`,
   `fecha_de_aprobacion`, `fecha_iso`, `respuesta_de_reembolso`) pasaron, sin cambiar de comportamiento,
   a `infrastructure/pasarela_respuestas.py`; `pasarela.py` quedó en 337 líneas. Commit propio, tests
   del contrato en verde.
2. **Doble aprobación concurrente**: `ConfirmarPago._encontrar` leía el cobro con un `get` simple, así
   que dos webhooks con `payment_id` distinto sobre el mismo cobro abierto podían aprobarlo los dos (el
   segundo pisaba `mp_payment_id`, el saldo bajaba dos veces y el primer pago nunca quedaba registrado).
   Ahora lo lee con `buscar_para_actualizar` (`SELECT ... FOR UPDATE`) por **las dos** búsquedas
   (referencia y, tras hallarlo, preferencia): el segundo espera, ve `APROBADO` y queda
   `COBRO_YA_PAGADO`. RED: 2 fallas unitarias (`cobros.bloqueados` vacío). Caso 15, **solo CI**
   (PostgreSQL): dos confirmaciones solapadas, una aprobada y una `COBRO_YA_PAGADO`
   (`test_pagos_sin_imputar_postgres.py`). Con esto la carrera de `TODO.md` §20.7 queda **cerrada para
   la confirmación**.
3. **Moneda**: `PagoRecibido.moneda` (de `currency_id`, en mayúsculas, `None` si falta). Un pago cuya
   moneda está informada y no es `ARS` no se aprueba y se registra como `MONTO_DISTINTO`, por el mismo
   camino que un monto distinto; sin `currency_id` se aprueba como antes (misma decisión que con el
   monto). RED: 44 fallas (`TypeError` por el argumento `moneda` inexistente) y, tras agregar el campo,
   los casos de lectura y de decisión en verde.
4. **Documentación** (`TODO.md`): §20.20 (el `PUT` de `expiration_date_to` sobre una preferencia ya
   vencida es aceptado), §22.44 (hallazgo previo: `monto_de` levanta `InvalidOperation` ante un
   `transaction_amount` no numérico o `NaN`, el webhook responde 500 y MercadoPago reintenta; no se
   corrige acá), y §20.17/§20.18 ahora piden verificar que `transaction_amount` y `currency_id` vienen
   en el pago real (si faltan, se aprueba sin comparar, por decisión).

### Evidencia RED

- Caso 1: `AttributeError: 'PagoRecibido' object has no attribute 'referencia_externa'`.
- Casos 2 y 3: 2 fallas de 3 (el pago con referencia y sin preferencia quedaba en el log
  `webhook_sin_cobro_asociado`); el 3 pasa antes y después.
- Casos 4–9: 36 fallas por `TypeError` (`ConfirmarPago` sin `sin_imputar`) antes de implementar.
- Caso 10: `ModuleNotFoundError` de `domain.pago_sin_imputar`.
- Caso 11: 2 fallas (no invalidaba; no fallaba al fallar la invalidación).
- Casos 12–16: escritos para la CI, sin RED local.

### Huecos para el dueño

- Correr en la CI los casos 12–16 y `test_guards.sh`; renumerar `0036` si corresponde.
- §20.17–20.19 y §22.43 siguen abiertos. Si el sandbox muestra que el pago no trae
  `external_reference`, falta el plan B de §20.17 (la merchant order).
- La pantalla para listar o resolver pagos sin imputar y la imputación manual quedan en
  `epicas/06-cobros-y-recordatorios/pendientes.md` #15.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-07 | Aprobado por Luciano con las recomendaciones de las 11 preguntas: 1 (a) no cambia la creación del cobro; 2 sí; 3 (a); 4 (a); 5 sí; 6 no se registran; 7 (a) `pago_sin_imputar`; 8 pantalla fuera de la unidad; 9 se incluye; 10 sin ADR; 11 `PagoSinImputar` |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- Las del Gate 1 están en la fila de la tabla de arriba; las de la implementación, en «Estado de
  la implementación».
