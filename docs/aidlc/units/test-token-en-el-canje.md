# Unidad: test-token-en-el-canje

**HUs**: HU-E2-02 (RN-01, RN-02)   **Contexto dueño**: integrations   **Rama**: fix/integrations-test-token-en-el-canje

> Unidad correctiva, encontrada en la prueba manual de la Etapa 6 sobre staging (05/10/2026).
> Severidad **Crítica** según `etapa-6/reglas.md` §8: bloquea la HU entera fuera de producción.
> No hay issue: el defecto queda documentado acá y en el commit, por decisión del usuario.

## El defecto

Con `MERCADOPAGO_ADAPTADOR=mercadopago` en staging, **ninguna cuenta podía conectarse**:

- una cuenta real se rechaza, como corresponde: «La cuenta de MercadoPago es real y este entorno es
  de homologacion»;
- un **usuario de prueba vendedor** se rechazaba con el mismo mensaje.

Logs de la API (`cheatsheet-api`, 05/10/2026 23:58–23:59 UTC), tres intentos con el vendedor de
prueba, idénticos: `POST https://api.mercadopago.com/oauth/token` → 200, evento
`ConexionRechazada`, `POST /integraciones/MERCADOPAGO/autorizacion/canje` → 422.

Causa: el canje (`ClienteMercadoPago.canjear`) nunca enviaba `test_token`. La documentación de
OAuth de MercadoPago dice que, para generar credenciales de prueba, se envía `test_token` en `true`.
Sin él, MercadoPago devuelve un token con `live_mode: true` aunque haya autorizado un usuario de
prueba, y el cruce con `APP_ENV` (`mapeo.estado_por_ambiente`) lo rechaza.

Los tests no lo vieron porque el simulador fabrica `live_mode` a partir del código reservado, sin
pasar por el cliente HTTP, y los tests de contrato no verificaban el cuerpo en ese punto.

## Diseño

- `ConfiguracionMercadoPago` suma `credenciales_de_prueba: bool`, **sin valor por defecto**:
  equivocarse en cualquiera de los dos sentidos es silencioso hasta que se mueve dinero (en
  producción, un `test_token` dejaría a la empresa cobrando con dinero ficticio).
- `ClienteMercadoPago._post_token` agrega `test_token: true` cuando está activo. Aplica al canje y
  a la renovación: renovar sin él cambiaría el par de prueba por uno productivo.
- `registro.py` lo arma como `not settings.es_produccion`.

## Desvío del plan aprobado

El plan proponía que el simulador imitara a MercadoPago (sin `test_token`, `live_mode: true`). No se
hace: el simulador reemplaza al cliente HTTP entero y nunca ve el cuerpo del pedido, así que no
tiene dónde observarlo. La red de seguridad queda en los tests de contrato, que sí ejercitan el
cliente real contra `httpx.MockTransport`.

## Tests

Primero los tests, que no podían pasar sin el cambio:

- `test_fuera_de_produccion_el_canje_pide_credenciales_de_prueba`
- `test_en_produccion_el_canje_no_pide_credenciales_de_prueba`
- `test_fuera_de_produccion_la_renovacion_tambien_pide_credenciales_de_prueba`

## Fuera de alcance

Encontrados en la misma prueba, de otro contexto (payments), sin tocar acá:

- La preferencia de pago no envía `notification_url` (`payments/infrastructure/pasarela.py`), y el
  webhook de la aplicación no puede llevar el `empresa_id` que exige `/webhooks/mercadopago/{id}`:
  con MercadoPago real ningún pago aprobado llega al sistema.
- `unit_price` sigue saliendo como `float(cobro.monto)` (`TODO.md` §20.6).

## Verificación (Gate 2)

Corrida local del 05/10/2026, **sin PostgreSQL ni Redis**: Docker Desktop no arrancó en la máquina.

```
ruff format --check .        658 files already formatted
ruff check .                 All checks passed!
mypy .                       Success: no issues found in 653 source files
guard_architecture --scan    718 file(s) checked — architecture boundaries intact
pytest                       2162 passed, 485 skipped (los que necesitan PostgreSQL o Redis)
integrations, cobertura      86 % (mercadopago/cliente.py 88 %)
```

Segunda corrida, el mismo día, con PostgreSQL y Redis levantados en Docker:

```
pytest --cov                 2647 passed in 190.70s
cobertura total              87.82 % (umbral 80 %)
```

La prueba de punta a punta es conectar el vendedor de prueba en staging después del merge.
