---
entregable: correcciones
parte: arquitectura
responsable: Juan Caballero
estado: borrador
hu: []
fuentes:
  - backend/pyproject.toml
  - frontend/package.json
  - requirements-dev.txt
  - render.yaml
  - .github/workflows/ci.yml
  - backend/src/cheatsheet/workers/celery_app.py
  - backend/src/cheatsheet/workers/beat.py
  - backend/src/cheatsheet/platform/settings.py
  - backend/src/cheatsheet/contexts/
  - backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/lector.py
  - backend/migrations/versions/0020_agenda.py
  - backend/migrations/versions/0021_agente_conversacional.py
  - docs/adr/0006-staging-hosting-render.md
  - docs/adr/0007-llm-provider-anthropic.md
  - docs/adr/0008-wsfev1-cliente-propio.md
  - docs/adr/0009-review-adjustments-scope-change.md
  - docs/adr/0014-arca-web-service-delegation.md
  - docs/staging-deployment.md
observaciones: >
  Corrige la versión de Drive verificada el 25/08/2026 contra la rama develop al 12/10/2026. Las
  figuras de la sección 2 (diagrama de contenedores) y de la sección 5 (mapa de contextos) se
  tienen que volver a dibujar: el diagrama no muestra el almacenamiento de objetos, el modelo de
  lenguaje ni Google Sheets, y el mapa colorea solo tres contextos con código. Los conteos de la
  sección 8 son archivos .py sin contar __init__.py. Las tablas de versiones se conservan donde no
  cambiaron.
---

## Correcciones a «CheatSheet - Arquitectura del Sistema»

| Sección | Dice | Debe decir | Fuente |
|---|---|---|---|
| §2, Relaciones y protocolos | La tabla no tiene filas para el almacenamiento de objetos, el modelo de lenguaje ni Google Sheets | Agregar tres filas: «API y Workers → Cloudflare R2 · HTTPS · API compatible con S3 vía boto3 · Síncrono»; «API y Workers → Anthropic · HTTPS · JSON vía SDK anthropic · Síncrono»; «Workers → Google Sheets · REST / HTTPS · JSON · OAuth2 · Síncrono» | `backend/pyproject.toml`; `docs/adr/0007-llm-provider-anthropic.md`; `docs/staging-deployment.md` §4 bis y §10 |
| §2, Las cinco colas | «Las cinco colas están declaradas en el código; dos tienen tareas registradas hoy.» | «Las cinco colas están declaradas en el código; cuatro tienen tareas registradas: integrations_sync, notifications, spreadsheet_processing e incremental_sync. ai_nlp sigue declarada sin tareas propias.» | `backend/src/cheatsheet/workers/celery_app.py`; tareas con `queue=Cola.…` en `backend/src/cheatsheet/` |
| §2, tabla de colas, fila spreadsheet_processing | «Declarada · sin tareas» | «En uso» | Tareas con `queue=Cola.SPREADSHEET_PROCESSING` |
| §2, tabla de colas, fila incremental_sync | «Declarada · sin tareas» | «En uso: escritura de vuelta y control de estructura; la relectura de la hoja viva sigue pendiente del cliente OAuth2 de Google» | Tareas con `queue=Cola.INCREMENTAL_SYNC`; `docs/aidlc/TODO.md` §15.1 |
| §2, tabla de colas, fila notifications | «Correo transaccional — invitaciones de usuario» | «Correo transaccional, recordatorios de cobro y de turno, armado del paquete contable, reindexación de las preguntas frecuentes y retiro de las tareas que agotaron sus reintentos» | `backend/src/cheatsheet/workers/beat.py` |
| §2, Celery Beat | «Celery Beat corre como instancia única con tres entradas periódicas, todas sobre integrations_sync.» | «Celery Beat corre como instancia única con doce entradas periódicas: seis en integrations_sync, cinco en notifications y una en incremental_sync.» | `backend/src/cheatsheet/workers/beat.py` |
| §3, tabla Backend | La tabla termina en defusedxml 0.7.1 | Agregar: «Almacenamiento de objetos — boto3 — 1.35.54»; «Cliente del modelo de lenguaje — anthropic — 1.4.0»; «Lectura de planillas Excel — openpyxl — 3.1.5»; «Generación de PDF — reportlab — 5.0.1» | `backend/pyproject.toml` |
| §3, recuadro «Precisión necesaria» | «Las dos extensiones de PostgreSQL están instaladas pero todavía no se usan. No existe ninguna columna Vector ni ninguna restricción EXCLUDE USING gist en el código actual.» | «Las dos extensiones están en uso: pgvector guarda los embeddings de las preguntas frecuentes del agente conversacional, y btree_gist sostiene la restricción de exclusión que impide superponer dos turnos de un mismo recurso.» | `backend/migrations/versions/0020_agenda.py`, `0021_agente_conversacional.py`, `0024_…`, `0028_…`; `contexts/conversational/infrastructure/models.py` |
| §4, tabla de entornos, fila Workers Celery | Staging: «No desplegados» | Staging: «Render · Docker · Ohio · un worker Starter que consume las cinco colas (desde el 18/09/2026)» | `render.yaml`; `docs/adr/0006-staging-hosting-render.md`, enmienda del 18/09/2026 |
| §4, tabla de entornos, fila Celery Beat | Staging: «No desplegado» | Staging: «Embebido en el worker (`-B`), una sola instancia» | `render.yaml`; `docs/staging-deployment.md` §4 bis |
| §4, tabla de entornos, fila Object storage | Staging: «No provisto» | Staging: «Cloudflare R2 · plan gratuito» | `render.yaml` (`ALMACENAMIENTO_ADAPTADOR=r2`); `docs/staging-deployment.md` §4 bis.1 |
| §4, debajo de la tabla de entornos | «Los tres servicios gestionados de staging corren en plan gratuito.» | «La API, el panel y Redis corren en plan gratuito; el worker es la única instancia paga (plan Starter).» | `render.yaml` |
| §4, «La infraestructura de staging está versionada» | «los tres servicios, sus regiones, sus planes…» | «los cuatro servicios (API, worker, panel y Redis), sus regiones, sus planes…» | `render.yaml` |
| §4, recuadro «Y lo que el archivo declara que falta» | «El propio render.yaml documenta la ausencia de cheatsheet-worker y cheatsheet-beat…» | Reemplazar por: «El worker está desplegado desde el 18/09/2026, con Beat embebido. Es seguro solo porque hay una instancia: si el worker necesita escalar, Beat pasa primero a un servicio propio de una instancia.» | `render.yaml`; `docs/adr/0006-staging-hosting-render.md` |
| §4, «Cómo se distingue un entorno de otro en el código» | «Los cuatro adaptadores simulados —ARCA, MercadoPago, WhatsApp y correo por consola— se niegan a construirse si el entorno es producción» | «Los adaptadores simulados de ARCA (facturación y padrón), catálogos fiscales, MercadoPago, WhatsApp, correo por consola, planillas, modelo de lenguaje y almacenamiento en memoria se niegan a construirse si el entorno es producción» | `backend/src/cheatsheet/platform/settings.py` |
| §5, título y epígrafe del mapa de contextos | «Doce contextos acotados, tres con código» · «En color sólido, los tres contextos que tienen código hoy.» | «Doce contextos acotados, todos con código». Volver a dibujar el mapa con los doce contextos en color sólido | `backend/src/cheatsheet/contexts/` |
| §6, fila «PyAfipWs como cliente de ARCA (ADR-012)» | «No se usa. La firma CMS se resuelve con cryptography» | «No se usa. WSAA firma con cryptography y WSFEv1 usa un cliente SOAP propio (ADR-0008, que reemplaza a ADR-012)» | `docs/adr/0008-wsfev1-cliente-propio.md`; `backend/pyproject.toml` |
| §6, fila «Pandas para manipulación tabular» | «Todavía no incorporado — llega con el procesamiento de planillas» · Pendiente | «No se incorporó: las planillas se leen con openpyxl (.xlsx) y con el módulo csv de la biblioteca estándar» · Desvío | `contexts/spreadsheet_sync/infrastructure/lector.py`; `backend/pyproject.toml` |
| §6, fila «Cloudflare R2 como object storage» | «boto3 ausente a propósito — llega con su primer llamador» · Pendiente | «boto3 1.35.54, adaptador R2 en uso en staging» · Coincide | `backend/pyproject.toml`; `render.yaml` |
| §6, fila «Proveedor de modelo de lenguaje» | «Sin dependencia ni adaptador — el contexto conversacional está vacío» · Pendiente | «Anthropic Claude (ADR-0007), SDK anthropic 1.4.0; usado por el mapeo de planillas y por el agente conversacional» · Resuelto | `docs/adr/0007-llm-provider-anthropic.md`; `backend/pyproject.toml` |
| §6, recuadro «Un detalle que la Etapa 3 no podía anticipar» | «La factibilidad nunca nombró al proveedor del modelo de lenguaje, ni al servicio de transcripción de audio, ni al de correo transaccional» | Agregar al final: «El proveedor del modelo de lenguaje quedó elegido en ADR-0007. La transcripción de audio y los embeddings siguen con adaptadores simulados, a la espera de su ADR.» | `docs/adr/0007-llm-provider-anthropic.md`; `docs/aidlc/etapa-6/reparto.md` §2 |
| §7, Desvío 01, última oración | «El desvío está acotado a la autenticación: la decisión sobre la emisión de comprobantes queda abierta.» | «ADR-0008 extendió el desvío a la emisión: WSFEv1 también usa un cliente SOAP propio y ADR-012 quedó reemplazado. ADR-0014 cambió además el modelo de credencial: un único certificado de la plataforma, al que cada empresa delega «Facturación Electrónica», en lugar de un certificado por empresa.» | `docs/adr/0008-wsfev1-cliente-propio.md`; `docs/adr/0014-arca-web-service-delegation.md` |
| §7, encabezado | «Los cuatro desvíos están documentados…» | «Los seis desvíos están documentados…», agregando los desvíos 05 y 06 de las dos filas siguientes | — |
| §7, desvío nuevo | No existe | «Desvío 05 · ADR-0006 — Un solo worker para las cinco colas. ADR-003 fijó cinco workers especializados. En staging un único worker consume las cinco colas, con Beat embebido, para no pagar cinco instancias en un entorno de pruebas. Las colas siguen separadas en el código, de modo que repartirlas en workers distintos es un cambio de despliegue y no de código.» | `render.yaml`; `docs/adr/0006-staging-hosting-render.md` |
| §7, desvío nuevo | No existe | «Desvío 06 · ADR-0009 — El catálogo de historias se ajustó después de la revisión de 09/2026. Las historias modificadas llevan la marca «Modificada por ADR-0009» y sus unidades se registraron en los épicos existentes.» | `docs/adr/0009-review-adjustments-scope-change.md`; `docs/aidlc/inputs/historias-de-usuario.md` |
| §8, párrafo inicial | «La arquitectura está definida para doce contextos acotados. Tres tienen código. Los otros nueve existen como estructura de carpetas vacía, esperando su épico.» | «La arquitectura está definida para doce contextos acotados, y los doce tienen código.» | `backend/src/cheatsheet/contexts/` |
| §8, tabla de contextos | integrations 38 · identity 25 · observability 7 · los nueve restantes 0 · Andamiaje | integrations 42 · identity 34 · observability 18 · conversational 40 · payments 33 · master_data 21 · scheduling 21 · billing 19 · spreadsheet_sync 19 · business_config 18 · reporting 14 · reference_data 8. Los doce en estado «Construido» | Conteo de `backend/src/cheatsheet/contexts/*/` sobre develop al 12/10/2026 |
| §8, nota de la tabla | «verificado el 25/08/2026 sobre develop» | «verificado el 12/10/2026 sobre develop» | — |
| §8, «Qué no funciona hoy en staging, y por qué» | «Los workers y el planificador no están desplegados…», seguido de las cuatro consecuencias | Reemplazar por: «Los workers y el planificador están desplegados desde el 18/09/2026, por lo que la verificación del número de WhatsApp, la renovación de credenciales de MercadoPago y el aviso de vencimiento del certificado de ARCA corren. Las invitaciones de usuario siguen sin enviar correo porque el correo corre en modo consola: el enlace queda en el registro del worker.» | `render.yaml`; `docs/staging-deployment.md` §4 bis.3 |
| §8, último párrafo | «los cuatro proveedores externos corren contra adaptadores simulados en los dos entornos: nunca hay una credencial real involucrada» | «En staging, ARCA, WhatsApp y Google Sheets corren con adaptadores simulados y el correo en modo consola. MercadoPago usa el adaptador real contra cuentas de prueba, y el modelo de lenguaje usa una credencial real de Anthropic.» | `render.yaml`; `docs/staging-deployment.md` §8 y §10; `docs/aidlc/TODO.md` §29.1 |
| Fuentes y trazabilidad | «ADR-0001 a ADR-0006» · «verificados … el 25 de agosto de 2026» | «ADR-0001 a ADR-0014» · «verificados … el 12 de octubre de 2026» | `docs/adr/` |
