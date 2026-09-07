# Unidad: vinculo-de-planilla

**HUs**: HU-E2-04   **Contexto dueño**: spreadsheet_sync   **Rama**: feature/spreadsheet_sync-sincronizacion-de-planillas

## Qué hace

Le da al sistema las tres vías por las que una planilla entra: el vínculo OAuth2 con Google
Sheets sobre un archivo elegido, el vínculo con Excel Online, y el archivo subido a mano.
Deja el vínculo guardado con su proveedor, su dirección de sincronización y sus hojas
(RN-02), y la pantalla PAN-ING-01 con la zona de arrastre y el botón de vincular. Trae
además los cimientos de `spreadsheet_sync`, que hoy son cuatro `__init__.py` vacíos.

## Diseño

- **Dominio**: agregado raíz `VinculoDePlanilla`. Value objects: `ProveedorPlanilla`
  (`GOOGLE_SHEETS` · `EXCEL_ONLINE` · `ARCHIVO`, ver D10), `DireccionSync` (`SOLO_LECTURA` ·
  `LECTURA_Y_ESCRITURA`) y `ReferenciaDeArchivo`. El invariante que vive en el agregado:
  **sólo Google Sheets admite `LECTURA_Y_ESCRITURA`** — Excel Online es de solo lectura por
  el proveedor (HU-E3-07 precondición) y un `ARCHIVO` es una foto, no hay a dónde escribir.
  Ponerlo en el formulario en vez de acá dejaría la regla del lado equivocado de la puerta.
- **Aplicación**: `VincularGoogleSheets` (canjea el código OAuth y crea el vínculo),
  `SubirPlanilla` (valida formato y tamaño, guarda en R2 y crea el vínculo `ARCHIVO`),
  `ListarVinculos` y `DesvincularPlanilla`. Todos exigen Administrador (HU-E2-04
  precondición) salvo `ListarVinculos`.
- **Puertos y adaptadores**: `PortRepositorioVinculo`, `PortAlmacenamientoDeArchivos` (R2) y
  `PortProveedorDePlanilla` (el ACL contra Google/Microsoft). Adaptadores reales y
  **simulados**, con la misma regla que ARCA, WhatsApp y MercadoPago: el simulado es
  rechazado en `production`.
- **Otros contextos**: `integrations` es OHS (ADR-0003) y ya guarda credenciales cifradas
  por empresa; la FK `vinculo_de_planilla.configuracion_integracion_id` del DER dice que el
  token de Google va ahí y no en una tabla propia. Se llega por servicio de aplicación.
- **Frontend**: `features/spreadsheet_sync` nuevo, con su `index.ts`. Ruta
  `(panel)/ingesta` componiendo PAN-ING-01. Rutas BFF bajo `app/api/planillas/`.

## Infraestructura

- **Migraciones**: `0012_vinculo_de_planilla`. Tabla del DER más `ARCHIVO` en el catálogo de
  proveedores. RLS por `empresa_id`. `DELETE` **sí** se otorga: desvincular una planilla es
  una operación legítima del Administrador y no destruye datos ingeridos — los `Cliente` y
  `Servicio` ya creados sobreviven, que es lo que ADR-007 protege.
- **Trabajo asíncrono**: **No aplica** en esta unidad. La primera sincronización que pide
  RN-04 la dispara `carga-y-errores`; acá el vínculo queda creado y listo.
- **Configuración**: `R2_*` (endpoint, bucket, claves) y `GOOGLE_SHEETS_ADAPTADOR` en
  `backend/.env.example`. Las credenciales de Google son de plataforma, como el login del
  épico 1 — no van a `configuracion_de_integracion`.
- **Integraciones externas**: Google Sheets y Drive, con timeout explícito, 3 reintentos con
  backoff y manejo de falla, igual que los tres adaptadores del épico 2. El scope es
  `drive.file` — permiso **sobre el archivo elegido, no sobre todo el Drive** (RN-01), que
  es la diferencia entre pedir acceso a una planilla y pedir acceso a la vida del usuario.

## Riesgos que obligan a tests

- [ ] Toca dinero — no
- [ ] Toca comprobantes fiscales / CAE — no
- [ ] Consume un webhook — no
- [x] **Agrega datos con `empresa_id`** → test de aislamiento entre empresas
- [ ] Usa salida de un LLM — no (es la unidad 3)
- [x] **Datos personales o fiscales** — el archivo subido está lleno de ellos. Va a R2 y
      nunca a un LLM. El nombre del archivo se registra; su contenido no se loguea.

## Casos de prueba

| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | Un vinculo de Google Sheets admite `LECTURA_Y_ESCRITURA` | unit | **OK** |
| 2 | Excel Online y `ARCHIVO` rechazan `LECTURA_Y_ESCRITURA` | unit | **OK** |
| 3 | Sin los permisos de lectura, no se crea el vinculo y el mensaje es el de la HU | unit | **OK** |
| 4 | Un formato no soportado se rechaza con la frase de la historia, sin tocar R2 | unit | **OK** |
| 5 | Un archivo de mas de 25 MB se rechaza con la frase de la historia | unit | **OK** |
| 6 | Un Operador no puede vincular ni subir | unit | **OK** |
| 7 | Una empresa no ve los vinculos de otra | integracion (PostgreSQL) | **OK** |
| 8 | Los adaptadores simulados son rechazados en `production` | unit | **OK** |
| 9 | El alcance pedido es `drive.file` y no uno mas ancho | unit | **OK** |
| 10 | El motor rechaza que un `ARCHIVO` se vincule para escribir | integracion (PostgreSQL) | **OK** |
| 11 | El motor rechaza un vinculo sin con que encontrar su documento | integracion (PostgreSQL) | **OK** |
| 12 | La pausa sobrevive a la ida y vuelta a la base | integracion (PostgreSQL) | **OK** |
| 13 | El front rechaza extension y tamano **sin tocar la red** | unit (vitest) | **OK** |
| 14 | El mensaje de rechazo se ve en pantalla | componente (vitest) | **OK** |
| 15 | Un rol sin permiso no recibe la zona de carga, pero si el listado | pagina (vitest) | **OK** |
| 16 | Un 422 llega al navegador con su `detalle` | ruta BFF (vitest) | **OK** |

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 - Plan | 2026-09-07 | aprobado junto con el resto del epico |
| 2 - Verificacion | 2026-09-07 | **en verde, con servicios reales** |
| 3 - PR | - | al cierre del epico |

```
ruff format --check .   314 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 314 source files
pytest --cov            873 passed - 0 skipped - cobertura 96%  (umbral 80)
frontend lint           No ESLint warnings or errors
frontend typecheck      sin errores
frontend test:coverage  366 passed - 87.61 % lineas
frontend build          compila, /ingesta y sus 5 rutas BFF registradas
```

**Esta vez la suite de integracion corrio de verdad.** PostgreSQL y Redis se levantaron con
el `docker-compose.yml` del repositorio, en los puertos 5434 y 6381 en lugar de 5433 y 6380
-los de siempre estaban ocupados por otro proyecto de la misma maquina- mediante un archivo
de override que vive fuera del repositorio. Los 155 tests que la corrida de la unidad
anterior habia salteado corrieron, incluidos los cinco de `dlq-y-tareas-asincronas`: **las
migraciones 0011 y 0012 aplican limpias y el aislamiento entre empresas esta verificado
contra el motor**, no contra un doble.

## Lo que aparecio al implementar y el plan no anticipaba

**El BFF descartaba el mensaje de todos los errores menos uno.** `respuestaDeError`
comparaba el codigo contra la cadena exacta `EntradaInvalida`, asi que las cuatro subclases
de este contexto perdian su texto en el camino y la pantalla mostraba «No se pudo completar
la operacion». HU-E3-03 escribe sus dos rechazos palabra por palabra, asi que **sus
criterios de aceptacion quedaban incumplidos de punta a punta** - el mismo defecto que
`TODO.md` seccion 10 ya habia registrado para `ClienteDuplicado`. Ahora el reenvio se decide
por el **status 422** y no por un nombre de clase: un 422 significa «lo que mandaste esta
mal, y aca esta por que», y la explicacion es el contenido entero de la respuesta. No
arregla `ClienteDuplicado`, que responde 409 - eso sigue siendo decision del epico 3.

**`boto3` llego en el epico 4 y no en el 9.** El comentario de `backend/pyproject.toml`
predecia que el primer consumidor de R2 seria el generador de reportes; resulto ser la
planilla subida de HU-E3-03. Se corrigio el comentario en lugar de borrarlo: es el registro
de una suposicion que salio mal.

**La subida es un cuerpo binario crudo, no `multipart/form-data`.** Tres razones, por peso:
base64 dentro de JSON infla un libro de 25 MB a 33 MB de string que hay que decodificar en
memoria; multipart cuesta una dependencia de parseo y volver a bufferizar el cuerpo entero
para un request que lleva exactamente una parte; y el cliente aca es nuestro propio BFF y no
un formulario de navegador, asi que no hay codificacion con la que ser compatible. El nombre
viaja en la query y no en un header porque los nombres en espanol traen acentos.

**`localhost` no sirve para conectarse a los contenedores en esta maquina.** Resuelve a IPv6
y la conexion queda colgada hasta el timeout, con un `TimeoutError` que no dice nada. Con
`127.0.0.1` anda. No es del codigo -`argumentos_de_conexion()` acepta los dos- pero cuesta
media hora la primera vez.

## Hallazgos que no son de esta unidad

Anotados en `TODO.md` seccion 14, por `CLAUDE.md` seccion 8. El que mas duele: **`Tabla`
pierde su titulo cuando no hay filas**, y eso afecta a cinco pantallas.
