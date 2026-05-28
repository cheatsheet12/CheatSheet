# billing — Módulo de facturación electrónica

Emisión y validación de comprobantes electrónicos contra **AFIP/ARCA**.

- **Stack:** Python
- **Entradas externas:** Web Services de AFIP (WSAA, WSFE)
- **Variables de entorno relevantes:** `AFIP_CUIT`, `AFIP_CERT_PATH`, `AFIP_KEY_PATH`, `AFIP_WSAA_URL`, `AFIP_WSFE_URL`

> En `dev` y `staging` se usan los endpoints de **homologación**; en `prod`, los de producción.
