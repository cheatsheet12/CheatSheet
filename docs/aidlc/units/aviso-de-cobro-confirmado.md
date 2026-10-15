# Unidad: aviso-de-cobro-confirmado

**HUs**: HU-E8-04 (RN-01)   **Contexto dueño**: payments (dispara) · conversational (registra el mensaje, por la raíz de composición)   **Rama**: feature/payments-aviso-de-cobro-confirmado

> Base: `origin/develop` @ `07bcac1`. Revisa: **Vincenzo** (`etapa-6/reparto.md`: revisa los módulos de Luciano y los de Paula). Se avisa a **Paula** porque se toca su `payments`.

## Qué hace

Cuando el webhook de MercadoPago aprueba un cobro, el cliente recibe por WhatsApp una confirmación inmediata («recibimos tu pago de X por $ Y») y el mensaje queda en su hilo como `SALIENTE`/`SISTEMA`, con su `wamid` y su estado de entrega. Es lo que ya pasa con los avisos de turno (U7). Una notificación repetida de MercadoPago no genera un segundo mensaje.

## Evidencia del hueco (verificada en `origin/develop`)

- `payments/application/confirmacion.py:127-175`: `_aprobar` aprueba, guarda, baja el saldo y publica **solo** un `EventoAuditable` (`:163`). No publica ningún evento `PagoConfirmado` y no avisa al cliente.
- `api/routers/webhooks.py:88-95`: el router descarta el `ResultadoDeConfirmacion`. Nada pasa después del commit.
- `business_config/application/plantillas.py:54-84` y `business_config/domain/plantilla.py:89-98`: hay seis códigos y ninguno es de pago confirmado (`cobro_generado` es el link, no la confirmación).
- `.aprobar(` aparece **una sola vez** en `backend/src` (`confirmacion.py:152`). El webhook es el único camino de aprobación, así que no hay un segundo punto que cubrir.

## Diseño

- **Dominio**: no cambia. No se agrega un evento de dominio: el bus es síncrono y corre dentro de la transacción (`platform/events.py`). Un suscriptor que llama a Meta haría E/S dentro del webhook, y además le mandaría el mensaje también a la transacción perdedora de una carrera.
- **Aplicación** (`payments`): un caso de uso nuevo, `AvisarPagoConfirmado`. Recibe el `Cobro` aprobado, pide el contacto (`PortContactoDeCliente`, que ya existe) y llama a un puerto nuevo, `PortAvisoDePago.avisar(...)`. **Nunca levanta**: un fallo del canal no puede voltear un pago ya guardado (mismo criterio D33 que los turnos).
- **Puertos y adaptadores**: `AvisoDePagoPorWhatsApp` en `payments/infrastructure/avisos.py`. Usa una plantilla aprobada (`cobro_pagado`) si la hay, y si no, el texto de fábrica. Pide los `Protocol` locales `CanalDeAvisos` y `PlantillasAprobadas` (R3). El monto va con `formatear_es_ar` (`Decimal`, `ROUND_HALF_UP`).
- **Cuándo se dispara**: en `webhooks.py`, **después de que cierra** la unidad de trabajo del pago, y solo si el resultado es `aprobado and not ya_procesado and not huerfano`. Abre una segunda unidad de trabajo (canal, `NotificarAlCliente`, savepoint). Esto lo hace idempotente por construcción: solo la transacción que ganó el índice único `payment_id` llega a ese punto. Las repetidas cortan en `buscar_por_payment_id` y quedan `ya_procesado`, y la perdedora de una carrera falla al hacer commit, así que nunca envía.
- **Otros contextos**: el puente es `api/avisos_de_cobro.py`, que une el `CanalDeAvisos` de payments con `NotificarAlCliente` de conversational y la plantilla de business_config. Es el mismo patrón que `api/avisos_de_turno.py`. Con esto, la fila 91 del Context Map (`docs/architecture.md`), que hoy dice «for scheduling notices», pasa a cubrir también los avisos de payments. Ver la decisión 2.
- **Frontend**: no aplica. La plantilla nueva aparece sola en PAN-CFG-NOT por la siembra perezosa de `ListarPlantillas`.

## Infraestructura

- **Migraciones**: ninguna. `codigo` es `varchar`, solo con el índice único `(empresa_id, codigo)` (`0021`), y `ListarPlantillas` siembra los códigos que faltan. La última migración en develop es `0043`.
- **Trabajo asíncrono**: no aplica. El aviso no se reintenta (D6 de U7) y la falla queda `FALLIDO` en el hilo.
- **Configuración**: ninguna variable nueva.
- **Integraciones externas**: WhatsApp por `PortMensajeria`. Ya tiene timeout y backoff (ADR-0011). Sin plantilla aprobada y fuera de las 24 h, Meta contesta `131047` y el mensaje queda `FALLIDO`.

## Riesgos que obligan a tests

- [x] Toca dinero: el monto se formatea con `Decimal` y `ROUND_HALF_UP`. Test de formato.
- [x] Consume un webhook: test de entrega duplicada (un mismo `payment_id`, un solo aviso).
- [x] Aislamiento entre empresas: el aviso sale por el canal de la empresa de la URL.
- [x] Datos personales: ningún log lleva teléfono, nombre ni texto.

## Archivos a tocar

- [x] `backend/src/cheatsheet/contexts/payments/application/avisos.py` (nuevo) · `ports_envio.py` · `confirmacion.py` (`recien_aprobado`)
- [x] `backend/src/cheatsheet/contexts/payments/infrastructure/avisos.py` (nuevo)
- [x] `backend/src/cheatsheet/api/avisos_de_cobro.py` (nuevo) · `api/routers/webhooks.py`
- [x] `backend/src/cheatsheet/contexts/business_config/application/plantillas.py` · `domain/plantilla.py`
- [x] `docs/architecture.md` (fila 91 del Context Map, «six templates» → siete) · nota en `docs/adr/0011-…`
- [x] Frontend (PAN-CFG-NOT): etiqueta e ícono de `cobro_pagado` en `features/conversational` y su test
- [x] `backend/tests/contexts/payments/application/test_avisos.py` · `backend/tests/contexts/payments/infrastructure/test_avisos.py` · `backend/tests/api/test_webhook_aviso_de_pago.py` (+ `montaje_webhook_aviso_de_pago.py`)

## Casos de prueba (RED primero)

| # | Caso | Tipo |
|---|---|---|
| 1 | `test_pago_aprobado_avisa_al_cliente_una_vez` | integración (api) |
| 2 | `test_webhook_repetido_no_vuelve_a_avisar` | integración (api) |
| 3 | `test_pago_huerfano_no_avisa` · `test_pago_pendiente_no_avisa` | integración (api) |
| 4 | `test_falla_del_canal_no_voltea_el_pago_y_contesta_200` | integración (api) |
| 5 | `test_aviso_usa_plantilla_aprobada_y_si_no_texto_de_fabrica` | unit |
| 6 | `test_aviso_queda_en_el_hilo_como_sistema` · `test_cliente_sin_telefono_no_avisa` | unit |
| 7 | `test_monto_del_aviso_redondea_half_up` | unit |

## Gates

`ruff format --check .` · `ruff check .` · `mypy .` · `pytest` (cobertura ≥ 80 %). Se corre el **CI local** porque GitHub Actions no tiene cuota hasta el 2026-11-01. El volumen estimado es de unas 230 líneas de producción y 250 de tests, unas 480 en total: queda por encima de la referencia de 400 porque cada caso de idempotencia pide su propio test.

## Decisiones tomadas durante la unidad

- **Los casos 5 a 7 se probaron en dos niveles.** El caso de uso (`application/test_avisos.py`: contacto,
  sin teléfono, nunca levanta, `recien_aprobado`) y el adaptador (`infrastructure/test_avisos.py`:
  plantilla o texto de fábrica, formato del monto). El del hilo como `SISTEMA` se prueba en el test de
  la API con `NotificarAlCliente` real.
- **`ResultadoDeConfirmacion.recien_aprobado`** concentra la condición «aprobado ahora» (ni repetido, ni
  huérfano, ni sin cobro) en `payments`, en vez de repetirla en el router.
- **La nota de ADR-0011** va en el punto 6 de la decisión (donde se dice que los avisos se registran en
  la conversación), no en el 2.
- **El frontend sí se toca**: PAN-CFG-NOT tiene un mapa de etiquetas y otro de íconos por código; sin
  entrada, la pantalla mostraría `cobro_pagado` crudo.

## Decisiones aprobadas

Aprobadas por Luciano el 2026-10-15, junto con el plan.

1. **El aviso sale dentro del request del webhook, después del commit**, solo cuando el cobro se aprobó
   en ese request (ni repetido ni huérfano). No es una tarea Celery. `NotificarAlCliente` no levanta
   por errores del canal y la llamada a Meta tiene timeout.
2. **Context Map y ADR-0011**: se actualiza la fila payments → conversational y se agrega una nota en
   ADR-0011 §2. El edge `conversational → payments` ya existe; solo se amplía lo que se registra.
3. **Plantilla nueva `cobro_pagado`** con las variables `{{nombre}}`, `{{concepto}}` y `{{monto}}`. Si
   no hay una plantilla aprobada, se usa el texto de fábrica. La fecha de pago queda afuera (puede ser
   aproximada, D91).
4. **También se avisa en la seña de un turno.** La seña es un cobro y RN-01 no distingue.
5. **B2 («pago no verificado») queda diferido.** Se incorporará a la unidad `comprobante-por-whatsapp`
   cuando exista `cobro-por-transferencia`.

## Fuera de alcance

- Aviso de «pago no verificado» (B2): se incorpora a `comprobante-por-whatsapp` una vez que exista
  `cobro-por-transferencia`.
- Reintento del aviso: no se reintenta (D6 de U7); la falla queda `FALLIDO` en el hilo.
- Evento de dominio `PagoConfirmado` y cualquier trabajo asíncrono.
- Frontend: la plantilla aparece sola en PAN-CFG-NOT.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-10-15 | Aprobado por Luciano con las decisiones 1–5 |
