# Unidad: conexion-arca

**HUs**: HU-E2-01   **Contexto dueño**: `integrations`   **Rama**: `feature/integrations-conexion-arca`

Tercera unidad del épico 2. Depende de `mecanismo-de-integraciones` y de `conexion-whatsapp`, las
dos **mergeadas** en `develop` (PRs #8 y #9). Aprovecha lo que dejaron: el agregado, el cifrado, el
registro de adaptadores, `PENDIENTE`, el transporte de mail en `platform/` y el Beat que ya corre.

> **Esta unidad trae ADR.** [ADR-0004](../../adr/0004-arca-wsaa-access-tickets.md) decide cómo se
> autentica el sistema contra WSAA y quién guarda el ticket. Se aprueba junto con este plan, como
> pide la escalada del workflow: la decisión afecta a `billing` y a `reference_data` además de a
> `integrations`, y es cara de revertir.

---

## Qué hace

El Administrador carga el certificado fiscal y la clave privada de su empresa. El sistema los valida
**contra ARCA de verdad** —firma un pedido de ticket y lo manda a WSAA— y recién con el ticket en la
mano marca la integración como Conectada, registrando el ambiente. Credenciales inválidas dejan la
integración sin conectar y muestran el motivo. Un barrido diario detecta el vencimiento del
certificado antes de que ocurra y avisa por mail.

Y deja publicado el ticket de acceso, que es lo que el épico 5 va a necesitar para emitir.

---

## Diseño

### Dominio

| Qué | Cambio |
|---|---|
| `TicketDeAcceso` | **Agregado nuevo** (gap H11). `empresa_id`, `servicio`, `contenido` cifrado, `expira_en`. Sabe si está vigente y si entró en el margen de renovación. **No sabe pedirse a sí mismo**: eso es infraestructura |
| `ServicioDeArca` | Value object: `WSFE` y `PADRON_A5`. Cerrado, porque el TA es por servicio y un string libre acá es un ticket que nadie encuentra después |
| `ConfiguracionDeIntegracion` | **Sin cambios.** Lo que ARCA agrega —vencimiento del certificado, CUIT del titular— entra por `actualizar_parametros` y por `CLAVE_ETIQUETA`, que la unidad anterior dejó justo para esto |

**Ninguna palabra de ARCA entra al dominio.** `loginTicketRequest`, `token`, `sign` y los códigos de
falla de WSAA son vocabulario del proveedor y se quedan en la ACL (ADR-008). El agregado ve bytes
opacos y una fecha.

### Aplicación

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `ObtenerTicketDeAcceso` **(nuevo, publicado)** | `empresa_id`, `servicio` | `TicketVigente` (token, sign, expira) | Devuelve uno válido: reusa el guardado o lo renueva. **Nunca devuelve la credencial ni la clave** |
| `RevisarVencimientos` **(nuevo)** | `empresa_id` | `list[Desenlace]` | Lee el `notAfter` guardado y decide: vigente, por vencer, vencida. **Sin una sola llamada a ARCA** |
| `ConectarIntegracion` *(existente)* | — | — | Sin cambios: el conector de ARCA ya encaja en el puerto que la unidad 1 definió |

`ObtenerTicketDeAcceso` es la operación que ADR-0004 publica. Se suma a `ports.py` y a
`integraciones.py`, que juntos son el contrato del OHS.

### Puertos y adaptadores

| Puerto | Adaptador | Dónde |
|---|---|---|
| `PortConectorDeIntegracion` | `ConectorArca` — firma, llama a WSAA, guarda el ticket | `integrations/infrastructure/arca/conector.py` |
| `PortVerificadorDeConexion` | `VerificadorArca` — lee el vencimiento local; sólo llama a WSAA si no hay ticket vigente | `…/arca/verificador.py` |
| `PortRepositorioTickets` **(nuevo)** | `RepositorioTicketsSQL` | `…/infrastructure/repositories.py` |
| *(los dos primeros)* | `ArcaSimulado` — recorre el ciclo sin red | `…/arca/simulado.py` |

El firmante CMS (`…/arca/firma.py`) y el cliente WSAA (`…/arca/wsaa.py`) van separados a propósito:
la firma es criptografía pura y se prueba sin socket; el cliente es SOAP y se prueba con transporte
falso.

### Otros contextos

**Ninguno todavía, y ese es el punto de ADR-0004.** `billing` va a consumir `ObtenerTicketDeAcceso`
en el épico 5 y `identity` en la unidad siguiente (`padron-y-datos-fiscales`), los dos como clientes
del OHS. Esta unidad **publica la operación y no la usa desde afuera**, así que no agrega ninguna
arista al Context Map.

### Frontend

| Archivo | Cambio |
|---|---|
| `components/FormularioDeArca.tsx` | **Nuevo.** Dos archivos: certificado (`.crt`/`.pem`) y clave privada (`.key`). Se leen en el navegador y viajan juntos |
| `components/GrillaDeIntegraciones.tsx` | Tercera rama de `conectar`: ARCA abre su formulario. MercadoPago queda como la última con credencial de relleno |
| `components/TarjetaDeIntegracion.tsx` | Sin cambios: `etiqueta` y `detalle` ya alcanzan para mostrar CUIT y vencimiento |

**La clave privada pasa por el navegador, y no hay forma de evitarlo**: el backend tiene que firmar
con ella. Lo que sí se puede es que no quede en ningún lado — se lee del archivo, se manda una vez
por HTTPS, y el componente se desmonta con el modal.

---

## Infraestructura

### Migración — `0006_ticket_de_acceso.py`

```sql
CREATE TABLE ticket_de_acceso (
    id uuid PRIMARY KEY,
    empresa_id uuid NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    servicio varchar(30) NOT NULL,
    contenido_cifrado bytea NOT NULL,
    algoritmo varchar(40) NOT NULL,
    expira_en timestamptz NOT NULL
);
```

Único sobre `(empresa_id, servicio)`, RLS por `empresa_id` con `FORCE ROW LEVEL SECURITY`, grants
sólo a `cheatsheet_app`. Reversible, sin backfill: la tabla es nueva.

**Gap H11, dicho de frente.** El DER no tiene esta entidad porque modela la *credencial*, no la
sesión que se deriva de ella. La justificación entera está en ADR-0004: el TA dura 12 h, ARCA
**rechaza emitir otro mientras el anterior viva**, y perderlo deja a la empresa sin poder
autenticarse hasta que expire.

**El token y el sign se guardan cifrados**, con el mismo AES-256-GCM y la misma marca de generación
que las credenciales. Son secretos: quien los tenga habla con ARCA en nombre de la empresa durante
12 horas.

### Trabajo asíncrono

Una entrada nueva de Beat, con la misma forma que el sondeo de WhatsApp:

| | Despachador | Tarea por empresa |
|---|---|---|
| Nombre | `integrations.revisar_vencimientos` | `integrations.revisar_empresa` |
| Cola | `integrations_sync` | `integrations_sync` |
| Disparo | Beat, **una vez por día** | El despachador |
| Idempotencia | ninguna (lee y despacha) | `ClaveDeIdempotencia` sobre `(empresa, día)` |

**Una vez por día, no cada 30 minutos.** Lo que se vigila es un `notAfter` que se mueve una vez cada
dos años. Y no cuesta una llamada a ARCA: el vencimiento está en el certificado que ya tenemos.

Reusa `empresas_con_integracion_pendiente`… no: necesita **su propia función `SECURITY DEFINER`**,
`empresas_con_integracion_de_arca()`, porque el criterio es otro. Mismo formato, mismo mínimo —
devuelve `empresa_id` y nada más.

### Configuración — `backend/.env.example`

```bash
ARCA_ADAPTADOR=                  # arca | simulado — 'simulado' es rechazado en produccion
ARCA_WSAA_URL_HOMOLOGACION=      # default https://wsaahomo.afip.gov.ar/ws/services/LoginCms
ARCA_WSAA_URL_PRODUCCION=        # default https://wsaa.afip.gov.ar/ws/services/LoginCms
ARCA_TIMEOUT_SEGUNDOS=           # default 15
ARCA_MARGEN_RENOVACION_MINUTOS=  # default 30
ARCA_AVISO_VENCIMIENTO_DIAS=     # default 30
```

**Se proponen borrar `AFIP_CERT_PATH` y `AFIP_KEY_PATH`.** Están declaradas hacia adelante desde el
épico 1 y describen un certificado **de plataforma que no existe ni va a existir**: la credencial es
por empresa y vive cifrada en la base. Dejarlas es invitar a que alguien monte un certificado
compartido, que es exactamente el error que haría que una empresa facture con el CUIT de otra.
`AFIP_CUIT`, `AFIP_WSAA_URL` y `AFIP_WSFE_URL` también se reordenan bajo el bloque nuevo.

---

## Contrato del proveedor — ARCA WSAA

*(Sección exigida por la escalada «nueva integración externa».)*

### El intercambio

1. Se arma un **loginTicketRequest**: XML con `uniqueId`, `generationTime`, `expirationTime` y el
   `service` pedido.
2. Se firma como **CMS/PKCS#7 en DER**, con el certificado y la clave de la empresa, y se codifica
   en base64. `cryptography` lo hace en proceso —`PKCS7SignatureBuilder(...).sign(DER, [Binary])`—
   y ya está en las dependencias: **no se agrega PyAfipWs** (ADR-0004, punto 1).
3. Se hace `POST` SOAP 1.1 a `LoginCms` con ese blob.
4. La respuesta trae un **loginTicketResponse** con `token`, `sign` y `expirationTime`.

| Ambiente | Endpoint |
|---|---|
| Homologación | `https://wsaahomo.afip.gov.ar/ws/services/LoginCms` |
| Producción | `https://wsaa.afip.gov.ar/ws/services/LoginCms` |

**Acá sí hay dos hosts distintos**, a diferencia de Meta. `Ambiente` se sigue derivando de `APP_ENV`
como decidió la unidad 1, y ahora esa decisión elige a qué servidor de ARCA se habla — que es la
diferencia entre practicar y emitir un comprobante irreversible.

### Modos de falla

| Falla | Respuesta |
|---|---|
| El certificado no es X.509 válido, o la clave no le corresponde | `ConexionRechazada`, **sin llamar a ARCA**. Es verificable localmente |
| El certificado ya venció | `ConexionRechazada` con la fecha, **sin llamar a ARCA** |
| `coe.alreadyAuthenticated` — ya hay un TA vivo | **No es un error**: se reusa el guardado. Si no lo tenemos, se informa cuándo se podrá reintentar |
| `cms.sign.InvalidCertificate` / `cms.cert.untrusted` | `ConexionRechazada` — el certificado no está habilitado para ese servicio en ARCA |
| `cms.cert.expired`, `cms.cert.notFound` | `ConexionRechazada` con el motivo de ARCA |
| HTTP 5xx, timeout, DNS | `ProveedorNoDisponible`. Reintento con backoff; la integración no cambia de estado |
| SOAP fault desconocido | `ATENCION` con el código crudo, por la misma razón que en WhatsApp: ARCA agrega códigos y un `KeyError` en una tarea de Beat es una integración muda |

Timeout explícito de 15 s —ARCA es más lento que Meta— y reintentos con backoff y jitter.

### Cómo se prueba sin red

- **La firma CMS se prueba de verdad**, con un certificado autofirmado generado en el test: se firma
  y se verifica que el CMS resultante es DER parseable y contiene lo que debe. Cero red.
- **El cliente WSAA** se prueba con `httpx.MockTransport` contra respuestas SOAP grabadas: una
  exitosa y una por cada código de falla de la tabla.
- **Ningún test toca ARCA**, ni homologación. Es la regla del workflow y acá pesa doble: homologación
  también tiene límites de uso.

---

## Riesgos que obligan a tests

- [ ] Toca dinero → **no aplica** todavía. Esta unidad habilita la emisión; no emite
- [x] **Toca comprobantes fiscales / CAE** → indirectamente, y es lo que la hace delicada: una
      credencial mal validada o un ambiente mal registrado significa emitir en el servidor
      equivocado. Test de que `Ambiente` sale de `APP_ENV` y **nunca del request**
- [ ] Consume un webhook → **no aplica**
- [x] **Agrega datos con `empresa_id`** → aislamiento sobre `ticket_de_acceso`, que es tabla nueva:
      el ticket de una empresa no puede ser leído ni renovado por otra
- [ ] Usa salida de un LLM → **no aplica**
- [x] **Datos personales y fiscales** → el certificado, la clave privada y el CUIT del titular. Nunca
      a un LLM, nunca a un log, nunca de vuelta por la API

---

## Archivos a tocar

**Backend — dominio y aplicación**
- [ ] `contexts/integrations/domain/ticket.py` — `TicketDeAcceso`, `ServicioDeArca`
- [ ] `contexts/integrations/application/ports.py` — `PortRepositorioTickets`, `TicketVigente`
- [ ] `contexts/integrations/application/tickets.py` — `ObtenerTicketDeAcceso`
- [ ] `contexts/integrations/application/vencimientos.py` — `RevisarVencimientos`
- [ ] `contexts/integrations/application/errors.py` — `TicketNoDisponible`

**Backend — infraestructura**
- [ ] `contexts/integrations/infrastructure/arca/{__init__,firma,wsaa,mapeo,conector,verificador,simulado}.py`
- [ ] `contexts/integrations/infrastructure/{registro,ensamblado,repositories,models}.py`
- [ ] `contexts/integrations/infrastructure/plantillas/certificado_por_vencer.{html,txt}`

**Backend — plataforma, workers, migración**
- [ ] `platform/settings.py` — `AdaptadorDeArca` y las seis variables
- [ ] `workers/tasks_integrations.py` — el barrido de vencimientos
- [ ] `workers/beat.py` — segunda entrada, diaria
- [ ] `migrations/versions/0006_ticket_de_acceso.py`
- [ ] `backend/.env.example`
- [ ] `backend/pyproject.toml` — **ninguna dependencia nueva**; se corrige el comentario que anuncia
      PyAfipWs para este épico

**Frontend**
- [ ] `features/integrations/components/FormularioDeArca.tsx` — **nuevo**
- [ ] `features/integrations/components/GrillaDeIntegraciones.tsx`
- [ ] `features/integrations/api/cliente.ts`

**Tests** — dominio, firma, contrato WSAA, tickets, vencimientos, aislamiento, workers, frontend

**Docs**
- [ ] `docs/adr/0004-arca-wsaa-access-tickets.md` → `Accepted` cuando se apruebe el PR
- [ ] `docs/architecture.md` §7 — `PortRepositorioTickets` y el adaptador WSAA
- [ ] `docs/aidlc/units.md` y `docs/aidlc/TODO.md`

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un bundle PEM con certificado y clave se parsea en las dos piezas | unit | pendiente |
| 2 | Un certificado sin su clave, o con una clave que no le corresponde, se rechaza | unit | pendiente |
| 3 | Un certificado vencido se rechaza **sin llamar a ARCA** | unit | pendiente |
| 4 | El CMS firmado es DER parseable y lleva el certificado del firmante | unit | pendiente |
| 5 | El `loginTicketRequest` lleva `uniqueId`, ventana temporal y el servicio pedido | unit | pendiente |
| 6 | `TicketDeAcceso` sabe si está vigente, y si entró en el margen de renovación | unit | pendiente |
| 7 | Un `loginTicketResponse` correcto se traduce a token, sign y vencimiento | contrato | pendiente |
| 8 | `coe.alreadyAuthenticated` no es un error: se reusa el ticket guardado | contrato | pendiente |
| 9 | `cms.cert.untrusted` → `ConexionRechazada` con el motivo de ARCA | contrato | pendiente |
| 10 | `cms.cert.expired` → `ConexionRechazada` | contrato | pendiente |
| 11 | Un SOAP fault desconocido → `ATENCION`, sin excepción | contrato | pendiente |
| 12 | 5xx y timeout → `ProveedorNoDisponible` tras agotar el backoff | contrato | pendiente |
| 13 | El timeout de 15 s llega al cliente HTTP | contrato | pendiente |
| 14 | Se habla al endpoint de **homologación** cuando `APP_ENV` no es producción | unit | pendiente |
| 15 | `Ambiente` **no** se puede elegir desde el request | integración | pendiente |
| 16 | Conectar ARCA con credenciales válidas deja `CONECTADO` y audita | integración | pendiente |
| 17 | Conectar con credenciales inválidas no escribe ninguna fila | integración | pendiente |
| 18 | `ObtenerTicketDeAcceso` devuelve el guardado si sigue vigente | integración | pendiente |
| 19 | Dentro del margen de renovación, pide uno nuevo y reemplaza el anterior | integración | pendiente |
| 20 | El ticket se guarda **cifrado**: el token no está en claro en la base | integración | pendiente |
| 21 | Aislamiento: la empresa A no lee ni renueva el ticket de la B | integración | pendiente |
| 22 | Dos servicios distintos conviven como dos tickets de la misma empresa | integración | pendiente |
| 23 | Un certificado a 20 días de vencer → `ATENCION` y aviso, sin llamar a ARCA | integración | pendiente |
| 24 | Un certificado vencido → `NO_CONECTADO` y aviso (RN-04) | integración | pendiente |
| 25 | El barrido diario no vuelve a avisar lo mismo dos veces | integración | pendiente |
| 26 | Ni la clave privada ni el token salen por ninguna respuesta ni por ningún log | integración | pendiente |
| 27 | El adaptador simulado **lanza** al construirse en `production` | unit | pendiente |
| 28 | El formulario exige los dos archivos y no los deja en el DOM tras enviar | frontend | pendiente |
| 29 | La tarjeta de ARCA muestra el CUIT y el ambiente configurado (criterio 4) | frontend | pendiente |

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan + ADR-0004 | 2026-08-19 | **esperando aprobación** |
| 2 · Verificación | | |
| 3 · PR | | |

---

## Decisiones tomadas durante la unidad

- **D-a — El ticket se guarda en tabla propia y cifrado** (respuesta del usuario, 2026-08-19).
  Gap H11. Redis quedó descartado porque un reinicio pierde un ticket que ARCA sigue considerando
  vivo, y eso deja a la empresa sin poder autenticarse hasta 12 horas: un reinicio de infraestructura
  convertido en caída funcional. El detalle completo, en ADR-0004.
- **D-b — `ObtenerTicketDeAcceso` se publica ahora** (respuesta del usuario, 2026-08-19). El código
  existe igual porque hace falta para validar, y `billing` no puede conseguirlo solo sin romper el
  punto 3 de ADR-0003. Dejarlo para el épico 5 sería descubrir el bloqueo con la unidad ya planificada.
- **D-c — Vencimiento: barrido diario y aviso 30 días antes** (respuesta del usuario, 2026-08-19).
  RN-04 pide marcar inactiva al vencer; avisar antes es lo que lo vuelve útil, porque renovar un
  certificado de ARCA lleva días y enterarse el día que venció significa no poder facturar. El
  `notAfter` se lee localmente, así que el barrido no gasta ni una llamada.
- **D-d — Sin PyAfipWs.** Firma el CMS `cryptography`, que ya es dependencia. ADR-012 sigue vigente
  para WSFEv1 en el épico 5, que es otro servicio. Verificado antes de escribir el plan: la firma
  produce un CMS DER de ~1.3 KB, en proceso, sin `openssl` de línea de comandos ni `M2Crypto`.
- **D-e — La verificación de HU-E2-05 para ARCA lee el vencimiento local**, y sólo llama a WSAA si no
  hay ticket vigente. Llamar siempre quemaría el ticket de 12 h en cada refresco de pantalla y
  chocaría con la regla del proveedor. Un ticket vigente *es* prueba de que la credencial funcionó.

## Deuda que esta unidad declara

- Conseguir el certificado y la clave de **homologación** de ARCA es tarea de despliegue → `TODO.md`.
- `WSFEv1` y la emisión son el épico 5. Esta unidad deja el ticket, nada más.
- La consulta al padrón (deuda D1) es la unidad siguiente, y usa el mismo ticket con otro servicio.
