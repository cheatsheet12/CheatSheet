# Unidad: cuenta-de-prueba-por-etiqueta

**HUs**: HU-E2-02 (RN-01, RN-02), HS-T1   **Contexto dueño**: integrations   **Rama**: fix/integrations-cuenta-de-prueba-por-etiqueta

> Unidad correctiva que **corrige a [`test-token-en-el-canje`](test-token-en-el-canje.md)** (PR #89).
> Aquella hizo que una cuenta de prueba pudiera conectarse en staging, pero lo logró pidiendo
> credenciales de sandbox, y el checkout de sandbox falla al pagar. Severidad **Crítica**
> (`etapa-6/reglas.md` §8): bloquea el cobro de punta a punta en staging.

## El defecto

Con el cobro CB-565A11B7 ($ 1.234,56) creado en staging, el comprador de prueba no pudo pagar: el
checkout de `sandbox.mercadopago.com.ar` mostró «Oh, no, algo anduvo mal» al tocar «Pagar», con
«Dinero disponible» y con tarjeta. El pago nunca se creó: no llegó ningún aviso a la
`notification_url`.

Diagnóstico corrido en el worker de staging el 05/10/2026, sin imprimir secretos:

```
prefijo del token: TEST
users/me: {"id": 3344260422, "site_id": "MLA", "tags": ["test_user", "normal"], ...}
preferencia 200 {"notification_url": "https://cheatsheet-api-j4hv.onrender.com/webhooks/mercadopago/adf353cf-…", ...}
items: [{"unit_price": 1234.56, "currency_id": "ARS"}]
```

- El token es de **sandbox** (`TEST-…`), por el `test_token` que agregó el PR #89. Por eso el link
  lleva a `sandbox.mercadopago.com.ar`, el checkout que falla.
- `/users/me` identifica la cuenta de prueba por su **etiqueta `test_user`**.
- La preferencia está bien armada: la `notification_url` y el monto exacto de
  `notification-url-en-la-preferencia` funcionan del lado de MercadoPago.

## La causa de fondo

El cruce de ambiente decidía «cuenta real o de prueba» por `live_mode`. Ese campo dice **qué
credenciales firmaron el token**, no de quién es la cuenta: una cuenta de prueba que autoriza con
credenciales productivas recibe `live_mode: true`. Por eso el vendedor de prueba se rechazaba como
real, y el PR #89 lo «arregló» pidiendo credenciales de sandbox en lugar de corregir la señal.

## Diseño

- `ClienteMercadoPago` **deja de enviar `test_token`**; se elimina `credenciales_de_prueba`.
- `mapeo.es_cuenta_real(cuenta)`: la cuenta es real salvo que `/users/me` traiga la etiqueta
  `test_user`. `TokensDeMercadoPago` pierde `cuenta_real`: el token no dice nada sobre eso.
- `ConectorMercadoPago.conectar` lee la cuenta **antes** de juzgarla (el canje sigue primero, y nada
  se da por conectado sin leer la cuenta, como pide RN-02).
- `renovar` **no vuelve a juzgar** la cuenta: un refresh no cambia de quién es, la respuesta del
  token no lo dice, y la renovación mezcla sus parámetros sobre los guardados, así que el tipo
  registrado al conectar se conserva. Antes una cuenta de prueba renovada habría pasado a
  «Atención» todos los días.
- El simulador imita el modelo real: `live_mode` siempre `true` y la etiqueta en `/users/me`.

Se mantiene: una cuenta real en staging se rechaza; una cuenta de prueba en producción conecta en
«Atención».

## Tests

- Nuevos: el canje y la renovación no envían `test_token`; una cuenta de prueba con `live_mode: true`
  conecta en staging; sin la etiqueta se rechaza aunque `live_mode` sea `false`; la renovación no
  vuelve a juzgar el tipo de cuenta.
- Reemplazados: los tres tests de `test_token` del PR #89 y el de la renovación que marcaba
  «Atención».

## Despliegue

**Después del merge hay que reconectar MercadoPago** en cada empresa de staging: el token guardado
hoy es de sandbox. Después se paga el link con el comprador de prueba en el checkout normal.

## Riesgo abierto

Que una cuenta de prueba pague bien en el checkout normal es lo que MercadoPago indica hoy para sus
cuentas de prueba, pero no quedó confirmado en su documentación pública. Si falla, el paso siguiente
es el soporte de MercadoPago, no más código.

## Verificación (Gate 2)

Corrida local del 05/10/2026, con PostgreSQL y Redis en Docker:

```
ruff format --check / ruff check   sin cambios · All checks passed!
mypy .                             Success: no issues found in 654 source files
guard_architecture --scan          725 file(s) checked — architecture boundaries intact
pytest --cov                       2654 passed · 87,88 % (umbral 80 %)
mercadopago/mapeo.py 99 % · simulado.py 97 % · cliente.py 87 %
```
