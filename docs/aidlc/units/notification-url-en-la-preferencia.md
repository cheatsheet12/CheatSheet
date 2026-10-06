# Unidad: notification-url-en-la-preferencia

**HUs**: HS-T1 (RN-01), HU-E6-03   **Contexto dueño**: payments   **Rama**: fix/payments-notification-url-en-la-preferencia

> Unidad correctiva, encontrada al configurar MercadoPago real en staging durante la prueba manual de
> la Etapa 6 (05/10/2026). Severidad **Crítica** (`etapa-6/reglas.md` §8): dinero. Cobros es de Paula
> según `etapa-6/reparto.md`; la toma Cristian por pedido explícito. No hay issue: el defecto queda
> documentado acá y en el commit.

## Los dos defectos

**1. Ningún pago aprobado llegaba al sistema.** `PasarelaMercadoPago.crear_link` armaba la
preferencia sin `notification_url`. MercadoPago entonces avisa sólo a la URL configurada en la
aplicación, que es **una sola** y no puede llevar el `empresa_id` que exige
`/webhooks/mercadopago/{empresa_id}`. Con el adaptador real, un cliente pagaba y el cobro quedaba
«Pendiente» para siempre, con la plata ya en la cuenta. La documentación de MercadoPago (Checkout Pro,
notificaciones) dice que la URL de la preferencia tiene prioridad sobre la de la aplicación.

**2. El monto viajaba como `float`** (`TODO.md` §20.6). `unit_price` salía de `float(cobro.monto)`,
y el comentario de la línea decía lo contrario («Texto y no float»).

## Diseño

- **Setting nuevo `API_URL_PUBLICA`** → `Settings.mercadopago_url_de_notificaciones`, la raíz pública
  de la API. **Requerido al arrancar cuando `MERCADOPAGO_ADAPTADOR=mercadopago`**: sin él, un link
  cobra y nunca avisa, y eso tiene que frenar el proceso en el boot y no aparecer en una
  conciliación. Con el simulador es opcional. Se guarda sin barra final.
- `PasarelaMercadoPago` recibe `url_de_notificaciones` (obligatorio) y la preferencia lleva
  `notification_url = {url}/webhooks/mercadopago/{empresa_id}`.
- El cuerpo de `crear_link` se serializa con `json.dumps` usando una marca única en `unit_price`, y
  después la marca se reemplaza por `_numero_json(cobro.monto)`, el mismo helper que ya usaba el
  reembolso. Así el número es el literal exacto del `Decimal`.
- `backend/.env.example` y `render.yaml` (API y worker) declaran `API_URL_PUBLICA`. El worker la
  necesita aunque no cree links: carga los mismos `Settings`, que no arrancan sin ella.

## Tests (primero, fallando)

- `test_la_preferencia_le_dice_a_mercadopago_a_donde_avisar_el_pago`
- `test_el_monto_del_link_viaja_exacto_y_no_como_float`
- `test_una_descripcion_con_comillas_no_rompe_el_cuerpo`
- `tests/platform/test_url_de_notificaciones.py`: sin URL con el adaptador real no arranca; se
  guarda sin barra final; con el simulador es opcional.

## Despliegue — orden obligatorio

**Cargar `API_URL_PUBLICA` en Render (API y worker) ANTES de mergear.** Staging ya corre con
`MERCADOPAGO_ADAPTADOR=mercadopago`: si el código llega primero, los dos procesos se niegan a
arrancar. Valor en staging: `https://cheatsheet-api-j4hv.onrender.com`.

## Riesgo abierto, a verificar en staging

La documentación no aclara si los avisos a la `notification_url` de la preferencia llegan firmados
con `x-signature` y con el secreto de la aplicación. Si llegan sin firma, `_firma_valida` los
descarta (D22) y el pago tampoco se imputa. Se verifica pagando un link con el comprador de prueba y
leyendo los logs. Si no vienen firmados, es una decisión nueva y se trae al usuario antes de tocar
nada.

## Fuera de alcance — encontrado y no tocado

- `MERCADOPAGO_URL_DE_RETORNO` vale por defecto `http://localhost:3000/cobros` y no está declarada en
  staging: el comprador vuelve a `localhost` después de pagar. Tampoco figura en
  `backend/.env.example`, igual que `MERCADOPAGO_WEBHOOK_SECRET`.
- `platform/settings.py` ya superaba las 400 líneas antes de esta unidad (`CLAUDE.md` §5).

## Verificación (Gate 2)

Corrida local del 05/10/2026, con PostgreSQL y Redis en Docker:

```
ruff format --check .        659 files already formatted
ruff check .                 All checks passed!
mypy .                       Success: no issues found in 654 source files
guard_architecture --scan    718 file(s) checked — architecture boundaries intact
pytest --cov                 2653 passed
cobertura total              87.87 % (umbral 80 %) · payments/infrastructure/pasarela.py 96 %
```

Falta la prueba de punta a punta en staging: pagar un link con el comprador de prueba y ver el
cobro «Aprobado» (y el riesgo de la firma, arriba).
