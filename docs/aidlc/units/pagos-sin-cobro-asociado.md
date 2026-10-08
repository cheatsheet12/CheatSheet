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
  (`TODO.md` §20.7): esta unidad solo garantiza que la tabla nueva no devuelva 500 por eso.

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
  `develop` es `0035`; `down_revision` al head real en ese momento).
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
- [ ] `backend/src/cheatsheet/contexts/payments/domain/pago_sin_imputar.py` (nuevo)
- [ ] `backend/src/cheatsheet/contexts/payments/application/ports.py` (`PagoRecibido.referencia_externa`)
- [ ] `backend/src/cheatsheet/contexts/payments/application/ports_de_pagos.py` (nuevo: `PortRepositorioPagoSinImputar`)
- [ ] `backend/src/cheatsheet/contexts/payments/application/confirmacion.py` (búsqueda, motivos, registro)
- [ ] `backend/src/cheatsheet/contexts/payments/application/cobros.py` (`RegenerarLink` invalida el anterior, si P9)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/pasarela.py` (`external_reference`, `_preferencia_de`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/pasarela_simulada.py`
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/models.py` (`PagoSinImputarORM`)
- [ ] `backend/src/cheatsheet/contexts/payments/infrastructure/repositorio_pago_sin_imputar.py` (nuevo)
- [ ] `backend/src/cheatsheet/api/routers/webhooks.py` (armar el repositorio nuevo)
- [ ] `backend/migrations/versions/00NN_pago_sin_imputar.py` (nuevo)
- [ ] `backend/tests/contexts/payments/domain/test_pago_sin_imputar.py` (nuevo)
- [ ] `backend/tests/contexts/payments/application/test_confirmacion.py`
- [ ] `backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py` (regenerar, si P9)
- [ ] `backend/tests/contexts/payments/infrastructure/test_pasarela_contrato.py`
- [ ] `backend/tests/integracion/test_pagos_sin_imputar_postgres.py` (nuevo)
- [ ] `backend/tests/integracion/test_api_mercadopago.py` (webhook de punta a punta)

### Frontend
- No aplica (P8).

### Docs
- [x] `docs/aidlc/units/pagos-sin-cobro-asociado.md` (este plan)
- [x] `docs/aidlc/units.md` (fila de la unidad: `Rama`, estado)
- [x] `docs/aidlc/TODO.md` (§20.17–20.19 y §22.43)
- [ ] `docs/aidlc/epicas/06-cobros-y-recordatorios/pendientes.md` (lo que queda fuera: pantalla e imputación manual)

**Tamaño estimado**: ~750 líneas de autoría (≈ 300 de código, ≈ 400 de tests, ≈ 50 de migración).
Supera la referencia de 400; se entrega en dos commits de unidad de trabajo (1: lectura de
`external_reference` + búsqueda + regenerar; 2: `PagoSinImputar`, tabla y alerta) dentro de un
solo PR, salvo que se pida partirlo.

## Casos de prueba

Modo: **test primero**. Los de PostgreSQL y API no corren en la máquina local (sin Docker): se
escriben y los confirma la CI.

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | RED: `consultar_pago` con un cuerpo de pago real (`external_reference`, `order: {id, type}`, sin `preference_id`) devuelve `referencia_externa` y **no** toma `order.id` como preferencia | contrato (ACL) | pendiente |
| 2 | RED: un pago aprobado con `referencia_externa` = id de un cobro `PENDIENTE` y sin preferencia lo aprueba (estado, `mp_payment_id`, saldo del comprobante, bitácora `confirmar_pago`) | unit | pendiente |
| 3 | Un pago con la preferencia y sin referencia sigue encontrándose por preferencia (compatibilidad) | unit | pendiente |
| 4 | Referencia que no es un UUID, o UUID sin cobro → `PagoSinImputar(SIN_COBRO)`, evento `pago_sin_imputar` con `Resultado.ERROR`, ningún cobro tocado | unit | pendiente |
| 5 | RED: segundo pago (otro `payment_id`) sobre un cobro `APROBADO` → `COBRO_YA_PAGADO` con `cobro_id`; el cobro y el saldo no cambian | unit | pendiente |
| 6 | Monto distinto (`1210.02` contra `1210.01`) → `MONTO_DISTINTO`, el cobro sigue `PENDIENTE`; `1210.005` contra `1210.01` aprueba | unit | pendiente |
| 7 | Pago no aprobado (`pending`, `in_process`) sin cobro → no se registra nada (como hoy) | unit | pendiente |
| 8 | RED: la misma notificación de un pago sin imputar dos veces → una fila, un evento, una sola llamada a la pasarela | unit | pendiente |
| 9 | Pago sobre cobro `CANCELADO` sigue por `registrar_pago_huerfano` sin cambios | unit | pendiente |
| 10 | El monto del pago sin imputar se guarda en `Decimal` desde el texto, redondeado `ROUND_HALF_UP` | unit (dominio) | pendiente |
| 11 | RED (si P9): regenerar el link invalida la preferencia anterior; si la invalidación falla, no se guarda el link nuevo y no hay bitácora | unit | pendiente |
| 12 | `PagoSinImputar` sobrevive la ida y vuelta en PostgreSQL con `Numeric(14,2)` | integración (PostgreSQL) | pendiente |
| 13 | RLS: la empresa B no ve los pagos sin imputar de A; una referencia con el id de un cobro de A recibida por B queda `SIN_COBRO` en B | integración (PostgreSQL) | pendiente |
| 14 | Dos inserciones concurrentes del mismo `(empresa, payment_id)` → una fila; la segunda se traduce a «ya registrado», no a 500 | integración (PostgreSQL) | pendiente |
| 15 | La migración sube y baja limpia | integración (PostgreSQL) | pendiente |
| 16 | Webhook de punta a punta: pago sin cobro → 200, fila y notificación de severidad alta | integración (API) | pendiente |
| 17 | En sandbox: los campos reales del pago, monto y reproceso (§20.17–20.19) | manual | pendiente: `TODO.md` §20.17–20.19 |
| 18 | En staging (Render): regenerar un link, pagar el viejo y ver que se rechaza (si P9) o que se imputa; pagar dos veces y ver el aviso | manual | pendiente: `TODO.md` §22.43 |

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

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | | |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
