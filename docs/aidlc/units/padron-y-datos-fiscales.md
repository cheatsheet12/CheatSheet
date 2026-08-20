# Unidad: padron-y-datos-fiscales

**HUs**: deuda D1 de HU-E1-02 (RN-01, RN-02 y criterio de aceptación 1)
**Contexto dueño**: `identity`
**Rama**: `feature/identity-padron-y-datos-fiscales`
**Depende de**: `conexion-arca` (mergeada — PR #11)

---

## Qué hace

Con la credencial fiscal que dejó `conexion-arca`, el sistema consulta el **padrón A5 de
ARCA** y deja de creerle al usuario lo que dice su CUIT: verifica que exista, y completa
razón social y `CondicionIVA` con lo que ARCA tiene registrado.

Tres momentos en que eso ocurre:

1. **Al conectar ARCA.** La conexión termina y el sistema revalida los datos fiscales de
   la empresa contra el padrón, completa lo que esté vacío y avisa si algo no cierra.
2. **Desde la pantalla de datos de la empresa** (nueva, `(panel)/configuracion/empresa`),
   con el botón «Validar contra ARCA» sobre el CUIT.
3. **Al guardar los datos fiscales**, si ARCA está conectada: un CUIT que el padrón no
   conoce bloquea el guardado, que es lo que pide RN-01.

Lo que **no** hace, y hay que decirlo antes que nada: **el paso 2 del onboarding sigue
sin validación real contra ARCA**. Ver «El hueco que esta unidad no puede cerrar».

---

## El hueco que esta unidad no puede cerrar

HU-E1-02 RN-01 dice que el CUIT «es validado contra ARCA en tiempo real» durante el paso 2
del onboarding. **Eso no se puede hacer, y no por falta de esfuerzo:**

- consultar el padrón A5 exige un ticket de acceso de WSAA;
- emitir ese ticket exige el certificado y la clave privada **de la empresa**;
- el certificado se carga en Configuración → Integraciones, que es *posterior* al paso 2.

La única salida sería una credencial de ARCA de plataforma —CheatSheet consultando el
padrón con su propio certificado—, y está cerrada por partida doble: la **decisión D1** del
mapa de unidades la descartó explícitamente («No se introduce una credencial ARCA de
plataforma») y `conexion-arca` borró `AFIP_CERT_PATH` / `AFIP_KEY_PATH` de `.env.example`
justamente para que no exista un lugar donde ponerla.

**Consecuencia asumida:** el paso 2 conserva la validación estructural (formato y dígito
verificador) y su mensaje honesto de hoy. RN-01 se cumple **en el ciclo de vida de la
empresa**, no en el instante del alta: en cuanto ARCA se conecta, el CUIT queda verificado
contra el padrón, y a partir de ahí cada guardado lo revalida. HU-E2-01 declara como
precondición «La empresa tiene CUIT validado durante el onboarding» — esa precondición
queda invertida, y esta unidad es la que hace explícita la inversión en vez de fingir que
no existe.

---

## Diseño

### Dominio

**No hay agregado nuevo y `Empresa` no cambia de forma.** Lo único que se mueve:

- **`CondicionIVA` pasa al Shared Kernel** (`shared/fiscal.py`), re-exportado desde
  `identity/domain/valores.py` para que los imports existentes sigan funcionando.
  *Por qué:* la traducción de lo que ARCA responde a una condición de IVA vive en el ACL
  de ARCA, que está en `integrations/infrastructure/arca/`; importar el enum desde
  `identity/domain/` rompería R3 y contradiría ADR-0003. Es **exactamente** el caso de
  `RolUsuario` y se resuelve igual (ver la cabecera de `shared/roles.py`): la condición de
  IVA es vocabulario fiscal argentino que `billing` y `reporting` también van a necesitar.
  `identity` sigue siendo dueño del concepto — el enum del DER es suyo.
- **No es un ADR.** No se mueve un agregado ni se abre un edge nuevo: la fila Shared Kernel
  del Context Map ya existe y el precedente de `RolUsuario` se resolvió sin ADR.

### Aplicación

**En `integrations` (una operación nueva del Open Host Service):**

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `ConsultarPadron` | `empresa_id`, `cuit` | `DatosDePadron \| None` | Resuelve el ticket de `PADRON_A5` reusando `ObtenerTicketDeAcceso` (o sea, respeta la regla de un TA vivo por CUIT y servicio), consulta el padrón y traduce la respuesta. `None` es «ARCA no conoce ese CUIT»; que no se haya podido consultar es una **excepción**, nunca un `None` |

Esa distinción es la que sostiene la respuesta a la pregunta 3 del Gate 1: si ARCA está
caída **no se inventa un rechazo**. Un `None` bloquea; una excepción deja pasar y avisa.

**En `identity` (el dueño de la escritura):**

| Caso de uso | Entrada | Salida | Qué garantiza |
|---|---|---|---|
| `ConsultarPadronDeCuit` | `empresa_id`, `cuit`, `rol` | `ResultadoDePadron` | La consulta que dispara el botón de la pantalla. Administrador únicamente. Devuelve `encontrado(datos)` · `no_encontrado` · `no_disponible(motivo)`, y **no escribe nada**: es una consulta |
| `RevalidarDatosFiscales` | `empresa_id` | `AvisoFiscal \| None` | El automatismo posterior a conectar ARCA. Completa razón social y `CondicionIVA` **sólo si están vacías**, y devuelve la discrepancia cuando la hay |
| `CompletarDatosDeEmpresa` *(cambia)* | + `padron: PortPadron \| None` | igual | Cuando el padrón está disponible y **no conoce** el CUIT, levanta `CuitInexistenteEnPadron` y no guarda (RN-01). Cuando no se pudo consultar, guarda como hoy |

`RevalidarDatosFiscales` chequea **dos cosas**, y la segunda es casi gratis y vale mucho:

1. que el CUIT de la empresa exista en el padrón;
2. que el CUIT del **certificado** coincida con el de la empresa. `conexion-arca` ya extrae
   el CUIT del subject del certificado y lo guarda en los parámetros de la integración. Una
   diferencia ahí significa que alguien cargó el certificado de otro contribuyente — el
   tipo de error que, sin este chequeo, recién aparece cuando el primer comprobante sale
   emitido a nombre equivocado.

La discrepancia **no se persiste en una columna nueva**: se publica como `EventoAuditable`
con `Resultado.RECHAZADO` (queda en la bitácora, que es el épico 10) y se devuelve al
endpoint de conexión, que la muestra en la tarjeta de ARCA. La pantalla de datos de la
empresa la vuelve a calcular cada vez que se abre, así que no hay estado que se
desincronice ni migración que justificar.

### Puertos y adaptadores

| Puerto | Dónde | Adaptador | Nota |
|---|---|---|---|
| `PortConsultaDePadron` | `integrations/application/ports.py` | `ClientePadronA5` en `integrations/infrastructure/arca/padron.py` | SOAP contra `personaServiceA5`. Reusa el parseo seguro y la traducción de fallas de `wsaa.py` |
| ídem | ídem | `ArcaSimulado` *(crece)* | Ya implementa los otros tres puertos de ARCA; suma este. Se niega a construirse en `production` |
| `PortPadron` | `identity/application/ports.py` | `PadronViaIntegraciones` en `identity/infrastructure/padron.py` | **El único archivo de `identity` que importa `integrations`**, y sólo su `application/` |

Ese último renglón es el Anti-Corruption Layer de la unidad: la capa de aplicación de
`identity` no importa nada de otro contexto — habla con su propio puerto y con su propio
DTO. Cambiar de proveedor de padrón mañana toca un archivo.

`ParDeAdaptadores` (el registro de `integrations`) suma una ranura opcional `padron`,
igual que sumó `emisor` en `conexion-arca`. Sólo ARCA la llena.

### Otros contextos

`identity` → `integrations`, llamando a su servicio de aplicación. **Es un edge que el
Context Map ya permite**: la fila OHS de `integrations` lista a `identity` entre sus
consumidores, y ADR-0003 dice que cualquier contexto puede llamar lo que vive en
`application/`. No hace falta ADR.

La dirección importa: `integrations` **no** aprende nada de `identity` en esta unidad. Sigue
sin importar un solo módulo de otro contexto, que es lo que lo mantiene siendo un OHS.

### Frontend

- **`features/identity`**:
  - `FormularioDeEmpresa` gana un prop `modo: "onboarding" | "edicion"`, valores iniciales,
    el botón **«Validar contra ARCA»** junto al CUIT y tres estados de respuesta: encontrado
    (autocompleta lo vacío, **propone** reemplazo cuando difiere de lo tipeado), no
    encontrado (bloquea) y no disponible (mensaje honesto, no bloquea).
  - `api/cliente.ts`: `verEmpresa()`, `consultarPadron(cuit)`.
  - `index.ts` expone la pantalla de edición; nada nuevo se filtra fuera del feature (R5).
- **`features/integrations`**: `FormularioDeArca` muestra el `aviso_fiscal` que devuelve la
  conexión, si vino. Un campo opcional en un tipo que ya existe; el feature no aprende nada
  de `identity`.
- **Ruta nueva**: `(panel)/configuracion/empresa/page.tsx` + su entrada en la navegación del
  panel. El layout dice que la entrada la agrega la unidad que construye la pantalla, así
  que se agrega acá y no antes.

---

## Infraestructura

### Migraciones

**No aplica.** Nada nuevo se persiste: los datos fiscales ya tienen sus columnas, el ticket
de `PADRON_A5` usa la tabla `ticket_de_acceso` que `conexion-arca` creó (la clave es
`(empresa_id, servicio)`, y el padrón es el segundo servicio), y la discrepancia va a la
bitácora en lugar de a una columna.

### Trabajo asíncrono

**No aplica.** Las tres consultas son sincrónicas y disparadas por una acción del usuario.
El barrido de vencimientos que `conexion-arca` dejó en Beat no cambia.

### Configuración — `backend/.env.example`

| Variable | Valor de ejemplo | Por qué |
|---|---|---|
| `ARCA_PADRON_URL_HOMOLOGACION` | `https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5` | Igual que WSAA: ARCA separa los ambientes por DNS |
| `ARCA_PADRON_URL_PRODUCCION` | `https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5` | La elige `APP_ENV`, **nunca** el request |

Sin secretos nuevos: la credencial es la que ya está cifrada en `configuracion_de_integracion`.

---

## Contrato del proveedor — ARCA padrón A5

Escalada de «nueva integración externa». Es un servicio distinto de WSAA aunque sea el
mismo organismo: otro host, otro WSDL, otra semántica de error.

### El intercambio

| | |
|---|---|
| **Operación** | `getPersona` sobre `personaServiceA5` (SOAP 1.1, `POST`, `text/xml`) |
| **Autenticación** | El `token` y el `sign` del ticket de `ws_sr_padron_a5`, más `cuitRepresentada` — el CUIT **del titular del certificado**, que sale de los parámetros que guardó `conexion-arca` |
| **Parámetro** | `idPersona`: el CUIT a consultar, 11 dígitos sin guiones |
| **Respuesta útil** | `datosGenerales`: `razonSocial` (o `apellido` + `nombre` para personas físicas) y `estadoClave`; `datosMonotributo` / `datosRegimenGeneral` con la lista de impuestos |
| **Timeout** | 15 s, el mismo que WSAA — ARCA es lento y un timeout corto se parece demasiado a un CUIT inexistente |
| **Reintentos** | 3, backoff exponencial desde 1 s, sólo ante fallas de transporte y 5xx sin `Fault` |

**La traducción a `CondicionIVA`** vive en el ACL y es la parte con contenido fiscal:
`datosMonotributo` presente → `MONOTRIBUTO`; impuesto de IVA en el régimen general →
`RESPONSABLE_INSCRIPTO`; IVA exento → `EXENTO`; nada de lo anterior → `CONSUMIDOR_FINAL`.
Cuando la respuesta no alcanza para decidir, se devuelve `None` y el usuario elige — RN-02
permite corregir a mano, así que adivinar sería peor que no contestar.

### Modos de falla

| Qué pasa | Cómo se ve | Qué hace el sistema |
|---|---|---|
| El CUIT no existe | `Fault` con `No existe persona con ese Id` | `None` → **bloquea** el guardado (RN-01) |
| Ticket vencido o inválido | `Fault` de autenticación | Renueva vía `ObtenerTicketDeAcceso` y reintenta una vez; si vuelve a fallar, «no disponible» |
| La empresa no conectó ARCA | `TicketNoDisponible` | «No disponible» — **no bloquea**: es la situación normal recién salido del onboarding |
| ARCA caída / timeout | Transporte o 5xx | «No disponible» tras los reintentos. **Nunca se convierte en un rechazo** |
| XML hostil | `DefusedXmlException` | Traducido a `ProveedorNoDisponible`, igual que en `wsaa.py` — el defecto que un test destapó en la unidad anterior |

### Cómo se prueba sin red

`ArcaSimulado` fabrica respuestas del padrón **atravesando el parseo real**, como ya hace
con WSAA: el test ejercita el mismo código que corre en producción y no una rama paralela.
Un CUIT reservado responde «no existe», así que el camino bloqueante se puede demostrar en
una laptop. Los tests de contrato usan payloads fijos y transporte `httpx.MockTransport`.

---

## Riesgos que obligan a tests

- [ ] Toca dinero → **no**
- [x] **Datos personales o fiscales** → razón social y CUIT reales viajan y se guardan.
      Nunca a un LLM, nunca al log: se registra *que* se consultó, jamás *qué* devolvió
- [x] **Datos con `empresa_id`** → test de aislamiento: la empresa A no puede consultar el
      padrón con la credencial de la empresa B
- [x] **Integración externa nueva** → tests de contrato con payloads fijos, sin red
- [ ] Webhook → no aplica
- [ ] Salida de un LLM → no aplica
- [x] **Irreversible por otro lado**: un `CondicionIVA` equivocado cambia qué comprobante
      emite el épico 5. Test por cada rama de la traducción

---

## Archivos a tocar

**Backend — `shared`**
- [x] `shared/fiscal.py` *(nuevo)* — `CondicionIVA`
- [x] `contexts/identity/domain/valores.py` — re-exporta, como con `RolUsuario`

**Backend — `integrations`**
- [x] `application/ports.py` — `PortConsultaDePadron`, `DatosDePadron`
- [x] `application/padron.py` *(nuevo)* — `ConsultarPadron`
- [x] `application/errors.py` — `ConsultaDePadronNoDisponible`
- [x] `infrastructure/arca/padron.py` *(nuevo)* — cliente SOAP + traducción
- [x] `infrastructure/arca/soap.py` *(nuevo, no estaba en el plan)* — transporte compartido
- [x] `infrastructure/arca/wsaa.py` — pasa a usarlo; suma `empaquetar` / `desempaquetar`
- [x] `domain/valores.py` — `CLAVE_CUIT` sube al dominio
- [x] `application/integraciones.py` — `cuit_declarado` en `VistaDeIntegracion`
- [x] `infrastructure/arca/simulado.py` — suma el cuarto puerto
- [x] `infrastructure/registro.py` — ranura `padron`
- [x] `infrastructure/ensamblado.py`, `platform/settings.py`, `backend/.env.example`

**Backend — `identity`**
- [x] `application/ports.py` — `PortPadron`, `DatosFiscalesDePadron`
- [x] `application/onboarding.py` — `ConsultarPadronDeCuit`, `RevalidarDatosFiscales`, cambio en `CompletarDatosDeEmpresa`
- [x] `application/errors.py` — `CuitInexistenteEnPadron`
- [x] `infrastructure/padron.py` *(nuevo)* — el ACL
- [x] `infrastructure/ensamblado.py`

**Backend — `api`**
- [x] `routers/auth.py` — `GET /auth/empresa` completo, `POST /auth/empresa/padron`
- [x] `routers/integraciones.py` — el `aviso_fiscal` en la respuesta de conexión

**Frontend**
- [x] `features/identity/components/FormularioDeEmpresa.tsx` + tests
- [x] `features/identity/api/cliente.ts` + tests · `index.ts`
- [x] `features/integrations/components/FormularioDeArca.tsx` — muestra el aviso
- [x] `app/(panel)/configuracion/empresa/page.tsx` *(nueva)* · `app/(panel)/layout.tsx`
- [x] `app/api/auth/empresa/route.ts` (GET) · `app/api/auth/empresa/padron/route.ts` *(nueva)*

**Tests**
- [x] `tests/contexts/integrations/application/test_padron.py`
- [x] `tests/contexts/integrations/infrastructure/test_padron_contrato.py`
- [x] `tests/contexts/identity/application/test_padron.py`
- [x] `tests/integracion/test_api_empresa_padron.py`
- [x] `tests/contexts/identity/infrastructure/test_padron_acl.py` *(no estaba en el plan)*
- [x] `tests/contexts/integrations/conftest.py`, `tests/conftest.py` — dobles y settings

---

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un CUIT que el padrón conoce devuelve razón social y `CondicionIVA` | contrato | hecho |
| 2 | `datosMonotributo` presente → `MONOTRIBUTO` | contrato | hecho |
| 3 | IVA en régimen general → `RESPONSABLE_INSCRIPTO` | contrato | hecho |
| 4 | IVA exento → `EXENTO` | contrato | hecho |
| 5 | Sin impuestos reconocibles → `None`, y el usuario elige | contrato | hecho |
| 6 | Persona física: `apellido` + `nombre` arman la razón social | contrato | hecho |
| 7 | `Fault` de «no existe persona» → `None`, no excepción | contrato | hecho |
| 8 | Timeout y 5xx reintentan con backoff y terminan en `ProveedorNoDisponible` | contrato | hecho |
| 9 | XML hostil → `ProveedorNoDisponible`, no un stacktrace | contrato | hecho |
| 10 | `ConsultarPadron` reusa el ticket vigente y no llama a WSAA de más | unit | hecho |
| 11 | Ticket rechazado → renueva una vez y reintenta | unit | **descartado** |
| 12 | Empresa sin ARCA conectada → «no disponible», sin tocar la red | unit | hecho |
| 13 | `cuitRepresentada` sale del certificado, no del CUIT consultado | unit | hecho |
| 14 | La consulta jamás loguea razón social ni CUIT | unit | hecho |
| 15 | `CompletarDatosDeEmpresa` bloquea un CUIT inexistente | unit | hecho |
| 16 | `CompletarDatosDeEmpresa` guarda igual si el padrón no está disponible | unit | hecho |
| 17 | `RevalidarDatosFiscales` completa sólo los campos vacíos | unit | hecho |
| 18 | `RevalidarDatosFiscales` no pisa una razón social ya cargada | unit | hecho |
| 19 | CUIT del certificado ≠ CUIT de la empresa → aviso y evento auditado | unit | hecho |
| 20 | El evento auditado registra la consulta, nunca su contenido | unit | hecho |
| 21 | Un Operador no puede consultar el padrón | unit | hecho |
| 22 | La empresa A no consulta con la credencial de la B | integración | hecho |
| 23 | `PUT /auth/empresa` con CUIT inexistente responde 4xx y no guarda | integración | hecho |
| 24 | Conectar ARCA devuelve el `aviso_fiscal` cuando hay discrepancia | integración | hecho |
| 25 | El formulario propone reemplazo en vez de pisar lo tipeado | frontend | hecho |
| 26 | «No disponible» no bloquea el botón de guardar | frontend | hecho |
| 27 | La pantalla de edición carga los valores actuales | frontend | hecho |

---

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-20 | **aprobado** sin cambios |
| 2 · Verificación | 2026-08-20 | **en verde** — salida real abajo |
| 3 · PR | | |

### Salida real del Gate 2

```
ruff format --check .   228 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 224 source files
pytest                  514 passed — cobertura 89.79% (umbral 80)
guard_architecture      246 file(s) checked — architecture boundaries intact
test_guards.sh          54 cases, all correct — the guards are active
```

```
frontend  format:check   All matched files use Prettier code style!
frontend  lint           No ESLint warnings or errors
frontend  typecheck      tsc --noEmit, sin errores
frontend  test:coverage  224 passed — 88.28% líneas
```

`pytest` corrió con PostgreSQL y Redis levantados, así que los 63 tests de integración
—RLS incluida— se ejecutaron de verdad en lugar de saltearse.

**`gitleaks` 8.30.1 reporta 3 hallazgos, y los mismos 3 aparecen en `develop`**: ninguno
lo introduce esta unidad. Son los dos de `backend/tests/conftest.py` y el de
`.claude/hooks/test_guards.sh:34` que `conexion-arca` ya había declarado. La versión que
CI fija (8.21.2) no los marca.

### Desvíos del plan, dichos de frente

**1. Se extrajo `arca/soap.py`, que el plan no mencionaba.** El padrón necesitaba lo mismo
que WSAA ya tenía: la política de reintentos, la distinción entre una falla SOAP y una
caída, y el parseo con `defusedxml`. Copiarlo habría duplicado justo lo que menos conviene
duplicar —una defensa que existe en uno de dos parsers no existe—, así que se compartió.

**Y al compartirlo apareció algo que ninguna de las dos unidades había visto:**
`soapenv:Server` significa «tuve un mal momento» en WSAA y «no existe esa persona» en el
padrón. El mismo código, sentidos opuestos. Por eso el transporte compartido **no traduce**
la falla: la devuelve envuelta y cada servicio decide. Traducir en la capa común habría
hecho que un CUIT inexistente se leyera como una caída de ARCA, o al revés.

**2. El caso 11 se descartó, no se olvidó.** Decía «ticket rechazado → renueva una vez y
reintenta». No se puede: ARCA se niega a emitir un segundo ticket mientras el primero viva
(`coe.alreadyAuthenticated`), así que forzar la renovación sobre un ticket que ARCA acaba
de rechazar fallaría igual. Y en el caso en que ARCA sí lo considere vencido,
`hay_que_renovar` ya lo cubre sin necesidad de forzar nada. Implementarlo habría sido
código que no puede ejecutarse con éxito.

**3. `CLAVE_CUIT` subió al dominio y `cuit_declarado` se publicó en `VistaDeIntegracion`.**
El plan prometía comparar el CUIT del certificado con el de la empresa, pero no decía cómo
cruzaba la frontera. La clave del parámetro vivía en el adaptador de ARCA, donde la capa de
aplicación no puede leerla (R2). Subirla al dominio —como ya estaba `CLAVE_ETIQUETA`— y
publicar un campo con nombre es lo que evita que el composition root aprenda claves de ARCA.

**4. El hallazgo se audita como dos acciones con nombre, no como una con detalle.**
`EventoAuditable` no tiene campo de texto libre, y agregárselo significaba una columna en
la tabla de auditoría compartida — exactamente la migración que esta unidad se comprometió
a no hacer. Así que hay `padron_cuit_inexistente` y `padron_certificado_ajeno`, que además
es lo que el épico 10 puede filtrar.

**5. `CuitInexistenteEnPadron` terminó siendo `EntradaInvalida` (422) y no un
`ErrorDeDominio` genérico (409).** Lo encontró el test de integración: HU-E1-02 lo redacta
como «el sistema indica que el CUIT no fue encontrado», que es un mensaje al lado de un
campo, no un conflicto con el estado del servidor. Es el mismo criterio que `ConexionRechazada`
en `integrations`.

**6. `empaquetar` / `desempaquetar` en `wsaa.py`.** El formato del ticket —token y firma en
dos líneas— lo escribía el emisor con un f-string y ahora lo lee el cliente del padrón. Un
formato acordado entre dos módulos por costumbre es un formato que se rompe callado.

---

## Decisiones tomadas durante la unidad

- **¿Dónde corre la validación, si el onboarding no puede?** → Pantalla en el panel
  (`(panel)/configuracion/empresa`, reusando el formulario de PAN-ONB-02) **más**
  revalidación automática al conectar ARCA. El paso 2 del onboarding queda estructural.
- **¿Dónde vive la consulta al padrón?** → `integrations` publica `ConsultarPadron` como
  operación de su OHS; `identity` la alcanza tras su propio puerto `PortPadron`.
- **¿Qué se hace con lo que devuelve ARCA?** → Completa lo vacío, **propone** lo que
  difiere, y bloquea un CUIT inexistente **sólo cuando la consulta efectivamente se hizo**.
- **`CondicionIVA` al Shared Kernel**, con el precedente de `RolUsuario`. Sin ADR: no se
  mueve un agregado ni se abre un edge nuevo.

---

## Deuda que esta unidad declara

- **El paso 2 del onboarding sigue sin validación contra ARCA.** No es pereza: es la
  consecuencia de D1 y de no tener credencial de plataforma. Cerrarlo de verdad exige
  cambiar el orden del onboarding (cargar el certificado antes de los datos fiscales), que
  contradice el prototipo y RN-04, o una credencial de plataforma, que está descartada.
  Queda escrito acá para que el épico 5 no lo descubra solo.
- **La discrepancia entre el CUIT del certificado y el de la empresa no se persiste.** Vive
  en la bitácora y se recalcula al abrir la pantalla. Si el épico 10 necesita listarla sin
  releer el log, ahí se decidirá si merece columna.
- **Un ticket que ARCA rechaza pero que nosotros creemos vigente no se puede forzar.** Es la
  contracara del caso 11 descartado: si el reloj se corriera o ARCA revocara un ticket antes
  de su vencimiento, la consulta falla hasta que la fila expire sola. Cerrar eso pide una
  operación de invalidación en `ObtenerTicketDeAcceso`, y no hay evidencia todavía de que el
  caso ocurra.
- **La pantalla `(panel)/configuracion/empresa` no tiene código de pantalla en el mapa de
  navegación de Etapa 5.** Reusa el diseño de PAN-ONB-02 sin stepper. Si el mapa se
  actualiza, ahí se le pone código; inventarle uno ahora sería inventar un diseño.
