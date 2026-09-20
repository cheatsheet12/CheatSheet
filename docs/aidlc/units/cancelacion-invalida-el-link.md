# Unidad: cancelacion-invalida-el-link

**HUs**: HU-E6-04 (RN-03), HS-T1   **Contexto dueño**: payments   **Rama**: fix/payments-cancelacion-invalida-el-link

> Unidad correctiva sobre el épico 6, ya mergeado. Se agrega al mapa deliberadamente y con el
> usuario, no en medio de un épico en vuelo. Es además la primera unidad de los épicos 6 a 10 que
> tiene plan: los otros documentan decisiones en `epicas/` y no pasaron por Gate 1.

## Qué hace

Cancelar un cobro deja de ser una anotación local: la preferencia se invalida **en MercadoPago**,
y si MercadoPago no puede confirmarlo la cancelación no ocurre. Y para el pago que igual entra por
un link ya cancelado —la carrera que ninguna invalidación cierra— el sistema deja de tragárselo en
silencio: lo registra contra el cobro y alerta al administrador.

## El defecto que cierra

Hoy `Cobro.cancelar` pasa el cobro a `CANCELADO` y `tiene_link_activo` devuelve `False`, pero eso
es una propiedad nuestra. La preferencia se creó con `expires: True` y
`expiration_date_to = cobro.vence_el` (`infrastructure/pasarela.py`), una fecha futura: el checkout
sigue vivo y el link ya está en el WhatsApp del cliente. `CancelarCobro` ni siquiera recibe la
pasarela.

Si el cliente paga, `ConfirmarPago._aprobar` ve `esta_abierto == False` y entra por la rama de
idempotencia: `logger.info("webhook_sobre_cobro_cerrado")` y 200. La plata está en la cuenta de
MercadoPago, el cobro sigue `CANCELADO`, `mp_payment_id` sigue en `None`, **no hay bitácora, no hay
notificación**. Se descubre conciliando el extracto.

Los dos agujeros son independientes: MercadoPago no puede retirar un cupón de Rapipago ya impreso
antes de la cancelación, así que la red hace falta aunque la invalidación sea perfecta.

## Diseño

- **Dominio** (`domain/cobro.py`): `cancelar` no cambia sus invariantes. Se agrega
  `registrar_pago_huerfano(payment_id, ahora)`, que guarda el `mp_payment_id` sobre un cobro
  `CANCELADO` **sin transicionar** — misma forma que D27: un hecho que se anota sin mover el estado.
  Se niega si el cobro está abierto o si ya tiene un `mp_payment_id`. Más la propiedad
  `tiene_pago_huerfano` para la pantalla.
- **Aplicación**:
  - `CancelarCobro` recibe ahora `pasarela: PortPasarelaDePago`. Orden: `cobro.cancelar(...)` en
    memoria primero —así un motivo corto nunca gasta una llamada a MercadoPago—, después
    `invalidar_link`, y recién después `guardar` + evento. Como `buscar_por_id` reconstituye un
    objeto de dominio aparte del ORM, si la invalidación levanta no se persiste nada: el cobro queda
    `PENDIENTE` y el 422 lleva el texto a la pantalla.
  - **No se llama a MercadoPago** cuando el cobro no tiene link, o cuando `esta_vencido_a(ahora)`:
    `expiration_date_to` es exactamente `vence_el`, así que la preferencia ya está muerta del lado
    del proveedor. Es una equivalencia exacta, no una heurística.
  - `ConfirmarPago._aprobar`: la rama de cobro cerrado se parte en dos. `CANCELADO` →
    `registrar_pago_huerfano` + `guardar` + `EventoAuditable(accion="pago_sobre_cobro_cancelado",
    resultado=Resultado.ERROR)`. `APROBADO`/`REEMBOLSADO` → como hoy. **No** se descuenta saldo del
    comprobante: la plata no está imputada a nada.
  - `ResultadoDeConfirmacion` suma `huerfano: bool = False`, con el mismo criterio por el que ya
    existe `ya_procesado`: que la bitácora pueda distinguir qué pasó.
- **Puertos y adaptadores**: `PortPasarelaDePago.invalidar_link(*, empresa_id, preference_id, ahora)`,
  que **no devuelve nada y levanta `PasarelaNoDisponible` si no puede garantizar que el link murió**.
  A diferencia de `reembolsar`, acá un rechazo no es una respuesta aceptable: un 4xx deja el link
  posiblemente vivo, así que también levanta. La única excepción es el 404 —la preferencia no existe
  en MercadoPago, no hay nada que pagar—, que cuenta como invalidada.
  - `PasarelaMercadoPago`: `PUT /checkout/preferences/{id}` con `expires: true` y
    `expiration_date_to` en el instante actual, ISO 8601 con offset. MercadoPago no tiene un DELETE
    de preferencias; adelantar el vencimiento es el mecanismo que existe. Reusa `_pedir`, con su
    timeout de 15 s y sus 3 intentos.
  - `PasarelaSimulada`: saca la preferencia de `self.links` y la anota en `self.invalidados`. Un
    cobro cuya descripción contenga «rechazar» hace que la invalidación falle, para que la rama de
    MercadoPago caído se pueda caminar en una laptop sin editar código — misma convención que ya usa
    para el reembolso.
- **Otros contextos**: ninguno nuevo. El aviso al administrador viaja por el publicador que ya
  existe: `NotificarPorEventos` de `observability` convierte todo `EventoAuditable` con
  `Resultado.ERROR` en notificación de severidad alta. **No hace falta ADR**: no se agrega ninguna
  arista al Context Map.
- **Frontend**: `features/payments` no necesita código nuevo para el error. `fallar()` ya reenvía el
  `detalle` de un 422 y `DetalleDeCobro` ya lo muestra con `mensajeDe(fallo, "No se pudo cancelar el
  cobro.")`. Se agrega sólo el dato del pago huérfano: un booleano en `CobroSalida`/`Cobro` y una
  línea en PAN-COB-02. Sin eso, la notificación manda al administrador a una pantalla donde no se ve
  nada raro.

## Infraestructura

- **Migraciones**: ninguna. `mp_payment_id` y su índice único ya existen desde la migración 0019, y
  es justamente ese índice el que hace idempotente el segundo webhook sobre un pago huérfano:
  `buscar_por_payment_id` lo encuentra y corta antes de alertar dos veces.
- **Trabajo asíncrono**: no aplica. Se descartó el reintento en el worker (decisión de esta unidad).
- **Configuración**: ninguna variable nueva; se usa el token de MercadoPago que ya resuelve
  `api/mercadopago.py`.
- **Integraciones externas**: MercadoPago, una operación nueva sobre una integración ya declarada.
  Timeout 15 s, 3 intentos con reintento ante timeout y 5xx, sin reintento ante 4xx — el camino que
  `_pedir` ya tiene.

## Riesgos que obligan a tests

- [x] Toca dinero → el caso central es plata que entra por un link que debería estar muerto
- [ ] Toca comprobantes fiscales / CAE → no aplica
- [x] Consume un webhook → test de entrega duplicada sobre el pago huérfano: dos notificaciones del
      mismo `payment_id`, un solo evento de error
- [x] Agrega datos con `empresa_id` → el pago huérfano se anota bajo RLS; test de aislamiento
- [ ] Usa salida de un LLM → no aplica
- [ ] Datos personales o fiscales a un LLM → no aplica

## Archivos a tocar

- [x] backend/src/cheatsheet/contexts/payments/domain/cobro.py
- [x] backend/src/cheatsheet/contexts/payments/application/ports.py
- [x] backend/src/cheatsheet/contexts/payments/application/cobros.py
- [x] backend/src/cheatsheet/contexts/payments/application/confirmacion.py
- [x] backend/src/cheatsheet/contexts/payments/infrastructure/pasarela.py
- [x] backend/src/cheatsheet/api/routers/cobros.py
- [x] backend/tests/contexts/payments/domain/test_cobro.py
- [x] backend/tests/contexts/payments/application/test_cobros_y_recordatorios.py
- [x] backend/tests/contexts/payments/application/test_confirmacion.py
- [x] backend/tests/contexts/payments/infrastructure/ (contrato de la pasarela)
- [x] frontend/src/features/payments/api/cobro.ts
- [x] frontend/src/features/payments/components/DetalleDeCobro.tsx

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Cancelar un cobro PENDIENTE con link invoca `invalidar_link` con su `preference_id` | unit | verde |
| 2 | Si `invalidar_link` levanta `PasarelaNoDisponible`, el cobro queda PENDIENTE y **no** se persiste ni se publica evento | unit | verde |
| 3 | Cancelar un cobro sin link no llama a MercadoPago | unit | verde |
| 4 | Cancelar un cobro ya vencido no llama a MercadoPago (la preferencia ya expiró) | unit | verde |
| 5 | Motivo de menos de 10 caracteres: falla antes de tocar MercadoPago | unit | verde |
| 6 | Cancelar un cobro APROBADO sigue devolviendo el texto de RN-01 y no llama a MercadoPago | unit | verde |
| 7 | Webhook aprobado sobre un cobro CANCELADO: guarda `mp_payment_id`, publica evento con `Resultado.ERROR`, el estado sigue CANCELADO | unit | verde |
| 8 | Ese mismo webhook repetido: un solo evento de error (idempotencia por `payment_id`) | unit | verde |
| 9 | Pago huérfano **no** descuenta el saldo del comprobante asociado | unit | verde |
| 10 | Webhook sobre un cobro APROBADO o REEMBOLSADO: comportamiento de hoy, sin alerta | unit | verde |
| 11 | `PasarelaMercadoPago.invalidar_link` arma el PUT correcto contra `MockTransport`; 404 cuenta como invalidada; 4xx levanta sin reintentar; 5xx y timeout reintentan 3 veces y levantan | contrato | verde |
| 12 | `PasarelaSimulada` invalida, y la palabra «rechazar» hace fallar la invalidación | unit | verde |
| 13 | Pago huérfano contra PostgreSQL: sobrevive la ida y vuelta, y comparte el índice único `uq_cobro_mp_payment_id` con la aprobación | integración | verde |
| 14 | PAN-COB-02 muestra el mensaje del backend cuando la cancelación falla, y marca el pago huérfano sólo cuando lo hay | unit (frontend) | verde |
| 15 | Una cancelación que falla no deja rastro en la base (el repositorio reconstituye, así que nada se escribe hasta `guardar`) | integración | verde |

### Lo que cambió respecto del plan

El caso 13 se reemplazó: el plan lo había escrito como «el evento produce notificación de
severidad alta vía `NotificarPorEventos`», y esa cadena ya está probada en `observability`
para todo `EventoAuditable` con `Resultado.ERROR` —volver a probarla acá habría sido probar
el otro contexto—. Lo que sí faltaba probar era la persistencia del pago huérfano, que es
código nuevo. Se agregó además el caso 15, que no estaba: es el único lugar donde se puede
afirmar de verdad que una cancelación fallida no escribe nada, porque los dobles en memoria
guardan la referencia que el caso de uso ya mutó.

## Lo que esta unidad NO puede probar

`CLAUDE.md` §5 prohíbe que los tests toquen la red, así que el caso 11 prueba **nuestro** lado del
contrato contra un `MockTransport`. Que MercadoPago acepte un `expiration_date_to` en el instante
actual sobre una preferencia viva sólo se confirma en sandbox, y eso depende de las credenciales
pendientes de `TODO.md` §5.3. Queda anotado como pendiente de validación del grupo 2, con el
precedente de `TODO.md` §19 a la vista: un cliente de ARCA leía «ARCA no dijo nada» como «no
bloqueado».

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-09-19 | aprobado, sin cambios (se mantiene el booleano de pago huérfano en PAN-COB-02) |
| 2 · Verificación | 2026-09-19 | corrida completa en verde: backend 1627 tests / 84.31% · frontend 800 tests / 84.02% · ruff, mypy y ESLint limpios · `gitleaks protect` sin hallazgos en el diff. Pendiente de que vos la des por buena. |
| 3 · PR | | |

## Decisiones tomadas durante la unidad

- ¿Qué pasa si MercadoPago no responde al cancelar? → **Falla la cancelación**, el cobro queda
  PENDIENTE. Mismo criterio que HU-E6-03 con el alta: la operación no se hace a medias. Se descartó
  cancelar local y reintentar en el worker, que dejaba una ventana con el cobro cancelado y el link
  todavía cobrable.
- ¿Qué pasa con un pago sobre un cobro cancelado? → **Se registra y se alerta**; el cobro sigue
  CANCELADO. Se descartó aceptarlo (`CANCELADO → APROBADO` resucita una deuda que alguien dio de
  baja con un motivo escrito) y se descartó el reembolso automático (mover plata hacia afuera sin
  aprobación, cuando HU-E6-05 RN-05 reserva el reembolso al Administrador).
- ¿Rama `fix/` o `feature/`? → **`fix/`**: RN-03 está escrita y el código no la cumple.
