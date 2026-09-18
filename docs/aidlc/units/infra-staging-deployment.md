# Unidad: infra-staging-deployment

**HUs**: ninguna — trabajo de entorno   **Contexto dueño**: ninguno (`platform` + operaciones)
**Rama**: `feature/infra-staging-deployment`

> **Por qué esta unidad existe sin HU detrás, y por qué no está en `units.md`.**
> Mismo razonamiento que [`infra-staging-database`](infra-staging-database.md), y por los mismos dos
> insumos: [`configuration-management.md`](../../configuration-management.md) §5 declara `staging`
> como entorno compartido donde se valida y se demuestra, y §7 pone el despliegue del lado del
> Arquitecto de Software. Esto **ejecuta** esos insumos; no los re-decide.
> Tampoco se agrega fila a [`units.md`](../units.md): ese mapa ata unidades a épicos del roadmap por
> el nombre del épico, y `.claude/hooks/aidlc_next.py` lee esa correspondencia. Una fila con un épico
> inventado rompería el mapa y volvería a mentirle a cada sesión, que es lo que se acaba de arreglar.

---

## Qué hace

Deja `staging` **corriendo y navegable** —API, panel y Redis— y hace que **cada push a `develop` lo
actualice solo**: migraciones, despliegue y verificación de que quedó sano, sin que nadie toque una
consola.

Continúa donde terminó `infra-staging-database`, cuya §7 nombra cuatro bloqueantes: Redis, dónde
corren los procesos, los workers, y las migraciones automáticas. **Entran tres de los cuatro**; los
workers quedan diferidos por la decisión R1 de abajo, con sus consecuencias escritas.

**Lo que no hace:** producción. `main` no despliega nada al terminar esta unidad. El entorno de
producción tiene otro perfil de datos (reales, de negocios piloto) y otro conjunto de credenciales,
y meterlo acá sería decidirlo de paso.

---

## La decisión de fondo: una imagen para tres comandos, un solo disparador

El backend, los workers y Beat son **el mismo código con distinto comando**. La imagen se escribe
sirviendo a los tres desde hoy, aunque hoy sólo se despliegue el primero: construir después una
segunda imagen para los workers sería la oportunidad de que quede atrasada respecto de la de la API,
y un worker corriendo código viejo contra la base nueva es un modo de falla silencioso.

| Servicio en Render | Tipo | Comando | Réplicas |
|---|---|---|---|
| `cheatsheet-api` | Web Service (Docker) | `uvicorn` sobre la factory de `api/main.py` | 1 |
| `cheatsheet-panel` | Web Service (Node) | `next start` | 1 |
| `cheatsheet-redis` | Key Value | — | 1 |

> **Actualización 2026-09-18.** R1 se revirtió: el worker está desplegado, en un único servicio
> Starter con Beat embebido (`-B`, `numInstances: 1`), más R2 en su plan gratuito porque
> `GenerarPaqueteContable` corre en la API y en el worker. Es la **única línea paga** del entorno.
> Lo que sigue describe la decisión original y por qué se tomó; ver `ADR-0006` §5 y el runbook §4 bis.

**Sin workers, por decisión del 2026-08-24 (R1).** Los Background Workers de Render son pagos y el
entorno se demuestra sin ellos. La imagen del backend se construye igual sirviendo para los tres
comandos, así que sumarlos después es agregar dos servicios que apuntan a la imagen que ya existe
—no reconstruir nada—. Lo que eso cuesta hoy está más abajo, dicho con nombre y apellido.

**Redis se queda igual, y no es por Celery.** Sin `REDIS_URL` el proceso **no arranca**
(`settings.py` la exige), y además ahí viven la memoria del `state` de OAuth2
(`integrations/infrastructure/autorizaciones.py`), el registro de idempotencia y la mitad de
`/health`. Redis no es la infraestructura de los workers: es infraestructura de la API.

### El frontend va nativo y el backend va en Docker, y son razones distintas

- **Backend en Docker** porque tres servicios comparten la imagen. Es el argumento entero.
- **Panel en el runtime de Node de Render** porque empaquetar Next en Docker obliga a
  `output: 'standalone'` en `next.config`, o sea **tocar la configuración de la aplicación para
  acomodar al proveedor**. `npm ci && npm run build` + `npm start` no pide nada de eso. El repo fija
  Node 22 en `package.json` (`engines`) y en CI; Render usa lo mismo.

### El disparador: un job de CI con `needs:`, no un workflow aparte

El pedido es «cada push a `develop` actualiza el ambiente». La forma ingenua —`on: push: branches:
[develop]`— despliega **también cuando CI está en rojo**, porque los dos workflows arrancan en
paralelo y no se miran.

El despliegue es el job `deploy-staging` **dentro de `ci.yml`**, con `needs:` sobre los siete gates que
corren en un push y
`if: github.event_name == 'push' && github.ref == 'refs/heads/develop'`. Efecto neto: cada push a
`develop` actualiza staging, **salvo que el push esté roto**. Que es lo que se pidió, dicho con
precisión.

**La primera versión usaba un workflow aparte con `workflow_run`, y no funcionaba** — ver desvío D6.

### El orden dentro del despliegue, que es donde esto se rompe

```
CI verde  →  alembic upgrade head  →  verify_rls.py  →  deploy api + panel  →  /health
             (rol dueño)              (rol app)                                  (200)
```

**Las migraciones van antes del código, y eso tiene un costo que se acepta explícitamente:** entre
la migración y el despliegue hay una ventana de segundos donde el código viejo corre contra el
esquema nuevo. Es tolerable porque las tres migraciones existentes sólo agregan, y porque staging no
tiene usuarios reales. El día que haya una migración destructiva, el patrón es expand/contract y no
este orden — queda escrito en el runbook, no resuelto acá.

**`verify_rls.py` corre en cada despliegue, no una vez.** Ya existe y ya corre en CI contra el
contenedor del job; acá corre contra **Neon**, después de migrar. Es lo que convierte «las políticas
estaban bien el día que lo provisionamos» en «las políticas están bien ahora». Si el verificador
sale distinto de cero, el despliegue se aborta y los servicios siguen con la versión anterior.

---

## Infraestructura

- **Migraciones**: ninguna nueva. Se **aplican** las tres existentes, ahora automáticamente.
- **Trabajo asíncrono**: **no se despliega** (R1). Las tareas se encolan en Redis y nadie las toma.
- **Configuración**: ninguna variable nueva en el código. Cambian los **valores** en staging.
  Lo que la API necesita para arrancar —`platform/settings.py` las exige o el proceso no levanta—:
  `REDIS_URL`, `DATABASE_URL`, `DATABASE_URL_MIGRATIONS`, `JWT_SECRET`, `SECRETS_ENCRYPTION_KEY`.
  Más `APP_ENV=staging` y `APP_BASE_URL` apuntando al panel, que es de donde sale la `redirect_uri`
  de MercadoPago. El panel necesita `BACKEND_API_URL`, y nada más.
- **Integraciones externas**: Render como plataforma de ejecución y proveedor de Redis. Se registra
  en un ADR, igual que Neon.

**Los adaptadores siguen simulados y eso es correcto.** El rechazo del simulado dispara en
`production`, no en `staging`. El entorno levanta entero sin una sola credencial real de ARCA, Meta
o MercadoPago — que es justo lo que permite demostrarlo antes de que existan
([`TODO.md`](../TODO.md) §5).

### Los secretos, y dónde vive cada uno

| Secreto | Dónde vive | Por qué ahí |
|---|---|---|
| `DATABASE_URL_MIGRATIONS` (rol dueño) | **GitHub Actions secret** | Sólo el workflow migra. Los servicios no lo necesitan y no lo reciben |
| `RENDER_DEPLOY_HOOK_*` (uno por servicio) | **GitHub Actions secret** | Es lo que dispara cada despliegue |
| `DATABASE_URL` (rol app), `REDIS_URL`, `JWT_SECRET`, `SECRETS_ENCRYPTION_KEY` | **Render Environment Group** | Hoy lo lee un solo servicio, pero el grupo existe desde el principio: el día que se sumen worker y Beat leen los mismos valores sin copiarlos |
| `BACKEND_API_URL` | Variable del panel, **URL interna** de Render | El navegador nunca habla con la API: sólo el BFF. Ver abajo |

Ningún valor real entra al repositorio, ni a este documento, ni al runbook
([`configuration-management.md`](../../configuration-management.md) §4.1). Viajan por el canal
privado de §4.3.

**La API no expone CORS y no hay que agregarlo.** `api/main.py` lo dice: el panel se sirve de otro
origen y **su BFF** es quien habla con la API; el navegador nunca. Con los dos servicios en Render
eso mejora — se pueden hablar por la red interna, sin salir a internet.

---

## Archivos a tocar

- [x] `backend/Dockerfile` — imagen única, válida para los tres comandos (API hoy; worker y Beat
      cuando se sumen). Python 3.11 (el de CI), `pip install -e backend/`, usuario sin privilegios,
      sin secretos en capas.
- [x] `backend/.dockerignore` — que `.env`, los tests y los artefactos locales no entren a la imagen.
      **Va en `backend/` y no en la raíz**, y eso cambió durante la implementación: ver desvío D1.
- [x] `render.yaml` — los cinco servicios como Blueprint. Infraestructura versionada y revisable en
      un PR, en lugar de clicks que nadie puede auditar. Es el equivalente de esta unidad a lo que
      `provision_app_role.py` fue para la anterior.
- [x] `.github/workflows/ci.yml` — el job `deploy-staging`: migraciones, verificador, despliegue y
      espera de `/health`, con `needs:` sobre los siete gates que corren en push. **Empezó siendo un
      workflow aparte y
      no podía funcionar**: ver desvío D6.
- [x] `docs/adr/0006-staging-hosting-render.md` — la decisión, sus alternativas y su costo.
- [x] `docs/staging-deployment.md` — el runbook, en inglés: qué se crea en Render, qué secreto va
      dónde, cómo se dispara un despliegue a mano, y la tabla de síntomas→causa.
- [x] `docs/staging-database.md` — §7 pierde tres de sus cuatro bloqueantes. Se actualiza, no se
      reescribe.
- [x] `frontend/.env.example` — su cabecera dice «Vercel for the panel, a container service for the
      API». Ya no es cierto. **Es un comentario, no un contrato**: no cambia ninguna variable.
- [x] `docs/configuration-management.md` §6 — hoy describe CI y no menciona despliegue continuo.

**Ni una línea dentro de `contexts/`.** Si esta unidad necesita tocar código de aplicación, es señal
de que algo está mal planteado — y si aparece igual, como le pasó a la unidad anterior con el TLS,
se para y se decide con vos antes de escribirlo.

---

## Riesgos que obligan a verificación

| # | Riesgo | Cómo se prueba |
|---|---|---|
| 1 | Beat se despliega por error, o replicado el día que se sume | No se crea ahora. El runbook deja escrito `numInstances: 1` como condición de su alta |
| 2 | El despliegue corre con CI en rojo | Un push que rompe un test **no** dispara despliegue |
| 3 | Una migración falla y el código nuevo sale igual | Migración que falla ⇒ workflow rojo ⇒ ningún deploy hook llamado |
| 4 | El RLS se degrada y nadie se entera | `verify_rls.py` contra Neon en cada despliegue, aborta si sale ≠ 0 |
| 5 | Un secreto aparece en los logs del workflow | Revisión del log del primer despliegue real, a ojo, buscando la URL de la base |
| 6 | El panel no encuentra la API | `/health` del panel y un login real en el navegador |
| 7 | El primer request tras la inactividad falla en vez de tardar | Neon suspende el compute y Render duerme el free tier: se prueba a propósito tras dejarlo dormir |
| 8 | La imagen queda con `.env` adentro | `docker history` / inspección del contexto de build |

---

## Casos de prueba

| # | Caso | Cómo |
|---|---|---|
| 1 | Push a `develop` con CI verde → staging queda actualizado | end-to-end, de verdad |
| 2 | Push con CI roja → staging **no** se toca | end-to-end |
| 3 | Las tres migraciones quedan aplicadas en Neon | `alembic_version` en la última revisión (check 7 del verificador) |
| 4 | El aislamiento entre empresas sigue vivo tras el despliegue | sonda viva del verificador, contra Neon |
| 5 | `/health` devuelve 200 con base y Redis en verde | curl al servicio desplegado |
| 6 | Con Redis caído, `/health` devuelve 503 | apagar Redis y mirar |
| 7 | Una invitación se encola y **queda pendiente sin worker** | se comprueba que es eso y no un error: fila pendiente en pantalla, tarea en Redis, log sin envío |
| 8 | *(diferido con R1: exige Beat desplegado)* | — |
| 9 | Un login completo en el navegador contra staging | manual, y es el criterio de que el entorno existe |

---

## Respuestas del Gate 1 (2026-08-24)

**R1 — Sin workers por ahora.** Los Background Workers de Render son pagos; se difieren hasta que
haya decisión de gasto. `cheatsheet-worker` y `cheatsheet-beat` no se crean.

**Lo que eso apaga, para que no se descubra en una demo:**

| Queda apagado | Consecuencia visible |
|---|---|
| Cola `notifications` sin consumidor | El Administrador invita a un usuario, la invitación **se crea** y aparece pendiente en la pantalla, y **el mail nunca sale**. Es el modo de falla elegido a propósito ([`TODO.md`](../TODO.md) §2.3), pero en staging significa que la aceptación de invitación sólo se puede recorrer copiando el link del log |
| Beat sin correr | El sondeo de WhatsApp cada 30 min no ocurre: un número queda en `pendiente` para siempre aunque Meta lo haya verificado |
| Beat sin correr | La renovación diaria de la credencial de MercadoPago no ocurre. Irrelevante hoy —el token dura 180 días y staging es simulado—, no el día que haya una credencial real |
| Beat sin correr | El aviso de vencimiento del certificado de ARCA no se dispara |

Nada de esto rompe el entorno: la API arranca, el panel navega, y los tres flujos de conexión de
integraciones se recorren enteros. Se declara como **deuda de esta unidad**, con dueño (vos, cuando
decidas el gasto) y con el camino de salida escrito en el runbook.

**R2 — No hay cuenta de Render.** La provisión se hace por consola, guiada paso a paso, igual que
Neon en la unidad anterior. El repositorio aporta los artefactos (`Dockerfile`, `render.yaml`, el
workflow); la consola la manejás vos, porque ahí adentro van los secretos.

**R3 — Región: Ohio.** Render no ofrece São Paulo, donde quedó Neon (`sa-east-1`). De las cinco
disponibles, Ohio es la más cercana. **Cada consulta a la base cruza São Paulo–Ohio**, así que la
latencia de red se suma a cada request del panel: es el precio de que el motor y el cómputo estén en
proveedores distintos, y es visible pero tolerable en un entorno de demostración. Si algún día
molesta, la respuesta no es mover Render: es mover la base al mismo lado que el cómputo.

## Verificación — Gate 2 (2026-08-24)

```
ruff format --check .   246 files already formatted
ruff check .            All checks passed!
mypy .                  Success: no issues found in 241 source files
guard_architecture      257 file(s) checked — architecture boundaries intact
test_guards.sh          54 cases, all correct — the guards are active
pytest                  496 passed · 1 failed · 85 skipped · cobertura 80.79 % (umbral 80)
frontend lint           No ESLint warnings or errors
frontend typecheck      sin errores
frontend test           230 passed
docker build            imagen construida, sin advertencias
```

**El test que falla es preexistente y no es de esta unidad.**
`backend/tests/platform/test_database_tls.py::test_el_contexto_confia_en_alguna_autoridad` afirma
que `ssl.create_default_context()` trae al menos una autoridad certificante. En esta laptop el
almacén de CA de Python está vacío y devuelve cero. Se comprobó guardando los cambios y corriendo el
test sobre `develop` limpio: **falla igual**. Es de `infra-staging-database`, pasa en CI (Ubuntu trae
`ca-certificates`) y falla en cualquier macOS donde no se haya corrido `Install Certificates.command`.
No se arregla acá: `CLAUDE.md` §8 manda reportarlo, no corregirlo en este PR.

Lo demás corrió sin PostgreSQL ni Redis levantados, así que los 85 saltados son los de integración.

### Lo que se verificó de verdad, y no sólo se afirmó

La parte nueva de esta unidad no la cubre ningún test del repositorio, así que se ejercitó a mano
contra Docker:

| Qué | Resultado |
|---|---|
| La imagen construye | Sí, sin advertencias |
| No lleva `.env` ni los tests adentro | `/app` contiene sólo `src`, `migrations`, `scripts`, `alembic.ini`, `pyproject.toml` |
| No corre como root | El proceso es del usuario `cheatsheet` |
| Sin variables, falla nombrando cuál | `ConfiguracionFaltante: Falta la variable de entorno REDIS_URL` |
| Con la base inalcanzable, `/health` responde 503 | `{"estado":"degradado","base_de_datos":false,"redis":false}` — que es lo que Render y el paso final del workflow esperan |
| El `SIGTERM` del deploy llega a uvicorn | `docker stop` apaga en 0 s y el log dice `api_detenida`: el `lifespan` cerró los recursos |

## Desvíos del plan

**D1 — El `.dockerignore` vive en `backend/`, no en la raíz, y con él el contexto de build.**
El plan decía «`.dockerignore` (raíz)» y `dockerContext: .`. Al escribirlo, la regla §2.3 del propio
`CLAUDE.md` —«si sólo afecta a `backend/` o a `frontend/`, no va en la raíz»— aplicaba de lleno: la
imagen no copia nada fuera de `backend/`. El contexto pasó a `./backend`, el archivo se mudó adentro,
y de paso el contexto que se sube al builder dejó de incluir `frontend/`, `docs/` y `.git`.
`render.yaml` sí se queda en la raíz: describe las dos aplicaciones a la vez, que es exactamente el
test que pone §2.3.

**D2 — El `CMD` es `["sh", "-c", "exec …"]` y no forma shell.** La forma shell dejaba `sh` como
PID 1, y el `SIGTERM` que Render manda en cada despliegue le habría llegado al shell y no a uvicorn:
la aplicación moriría matada en lugar de cerrada, y `ciclo_de_vida` —que hace `await
recursos.cerrar()`— nunca correría, perdiendo el pool de la base y la conexión a Redis en cada
release. Lo señaló el propio `docker build` con `JSONArgsRecommended`, y se verificó que ahora sí:
`docker stop` apaga en 0 s y deja `api_detenida` en el log.

**D3 — La factory se llama `create_app`, no `crear_app`.** El plan y el primer `CMD` la nombraban en
español por analogía con el resto del dominio, y el contenedor arrancó con `Error loading ASGI app.
Attribute "crear_app" not found`. Es el tipo de error que sólo aparece corriendo la imagen: ningún
linter lo ve, porque para el Dockerfile es una cadena de texto.

**D4 — `ADR-0006` nace `Proposed`, no `Accepted`.** El plan no decía nada; se sigue la convención que
usó ADR-0003, que pasó a `Accepted` con el merge de su PR.

**D5 — `docs/architecture.md` NO se tocó**, aunque dice que el panel corre en Vercel. Es un insumo de
Etapa 5 que describe la arquitectura de **producción**, y esta unidad decide **staging**. La
divergencia queda registrada en el ADR en lugar de reescribir el insumo.

**D6 — El deploy es un job de `ci.yml`, no un workflow aparte con `workflow_run`. Lo escrito en el
plan no podía funcionar.** GitHub sólo dispara `workflow_run` desde la copia del archivo que está en
la **rama por defecto** del repositorio, que en este repo es `main`. Un workflow de deploy viviendo
en `develop` **jamás se habría ejecutado**, y —lo peor— sin ningún error: el archivo estaría ahí,
correcto, y nada pasaría nunca.

Se descubrió el 2026-08-24, de rebote: el primer build en Render falló por otra razón (el
`Dockerfile` todavía no estaba en `develop`), y al mirar de qué commit clonaba apareció la pregunta
de qué rama mira GitHub para los triggers.

El arreglo simplifica y endurece a la vez: como job con `needs:` sobre los gates, la dependencia
se evalúa **dentro de una sola corrida** —si un gate falla, el job no arranca—, y los triggers `push`
sí funcionan desde la propia rama, así que desaparece la dependencia de `main`.

**Lección, y no es sobre GitHub Actions:** todo lo demás de esta unidad se verificó ejecutándolo
—la imagen se construyó, el contenedor arrancó, `/health` contestó, el `SIGTERM` cerró bien—. El
disparador fue la única pieza que no se podía ejercitar localmente, y fue la única que estaba mal.

## Registro

| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | 2026-08-24 | **aprobado**, con las tres preguntas contestadas (R1, R2, R3) |
| 2 · Verificación | 2026-08-24 | **en verde**, con un fallo preexistente ajeno a la unidad. Detalle arriba |
| 3 · PR | | |
