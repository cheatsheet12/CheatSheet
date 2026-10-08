# Deploying the staging environment (Render)

How the **testing (`staging`)** environment
([`configuration-management.md`](configuration-management.md) §5) is created, released and verified.
The decision and its trade-offs are in [ADR-0006](adr/0006-staging-hosting-render.md).

This document covers **the running processes**. The database they talk to is
[`staging-database.md`](staging-database.md) and has to exist first.

> **No real credential appears in this file, and none may be added to it.** Values travel over the
> private encrypted channel ([`configuration-management.md`](configuration-management.md) §4.3).
> What is written here is the *shape* of each string, never an instance of one.

---

## 0. The two things to get right

**Auto-deploy stays off.** Render's default is to deploy on every push to the tracked branch, and
Render has no idea whether CI passed. Left on, it ships red builds and the whole pipeline in §6
becomes decoration. Every service is created with **Auto-Deploy = No**.

**Nothing that is secret is typed into a file.** Secrets are entered in the Render dashboard and in
GitHub's secret store, both of which encrypt them at rest and hide them from logs. `render.yaml`
declares them as `sync: false`, which means exactly "Render asks once, and the value never appears
in the repository".

---

## 1. Create the Render account

1. Go to <https://render.com> → **Get Started**.
2. **Sign up with GitHub.** This is not a convenience: it lets Render pull the repository without
   handling a token yourself.
3. Authorize Render for the **`cheatsheet12`** account and, when it asks which repositories to grant,
   choose **Only select repositories → `CheatSheet`**. Granting all repositories is a broader
   permission than this needs.
4. When the dashboard asks for a workspace/team name, `CheatSheet` is fine. No card is required for
   the free plan.

---

## 2. Create Redis first

It goes first because the API does not boot without `REDIS_URL` — `platform/settings.py` requires it,
and the OAuth2 `state` memory, the idempotency registry and half of `/health` live there. It is not
"the workers' infrastructure".

1. **New → Key Value** (Render's current name for its managed Redis).
2. **Name**: `cheatsheet-redis`
3. **Region**: **Ohio**. Every service in this environment goes in Ohio — services in different
   regions cannot talk over the private network, which would push this traffic onto the internet.
4. **Plan**: Free.
5. **Maxmemory policy**: `noeviction`. The default (`allkeys-lru`) lets Redis silently drop keys
   under pressure, and two of the things stored here are a one-time OAuth2 `state` and the
   idempotency registry. A dropped `state` sends an Administrador back to the beginning of the
   MercadoPago flow; a dropped idempotency key allows a duplicate effect.
6. Create it, then copy the **Internal Connection String** (`redis://...`). Internal, not external:
   it never leaves Render's private network.

---

## 3. Create the API

1. **New → Web Service** → connect the **`CheatSheet`** repository.
2. **Name**: `cheatsheet-api`
3. **Region**: Ohio · **Branch**: `develop` · **Plan**: Free
4. **Language / Runtime**: **Docker**
5. **Dockerfile Path**: `./backend/Dockerfile`
6. **Docker Build Context Directory**: `./backend` — the image needs nothing from `frontend/` or
   `docs/`, and the whole context is uploaded to the builder on every build.
7. **Health Check Path**: `/health/live`. It answers 200 while the process is up and touches
   neither PostgreSQL nor Redis. Do **not** use `/health` here: Render probes every few seconds,
   and `/health` runs `SELECT 1`, which keeps Neon's compute awake around the clock and burns the
   free plan's monthly compute hours. `/health` stays the full readiness check (503 while a
   dependency is down) and is what CI polls after a deploy. `render.yaml` is not read by Render
   (§0), so **change the path in the dashboard too**: service -> Settings -> Health Check Path.
8. **Auto-Deploy**: **No**. See §0.
9. **Environment variables** — add these before the first deploy, or it will boot-loop on
   `ConfiguracionFaltante`:

| Key | Value |
| --- | --- |
| `APP_ENV` | `staging` |
| `DATABASE_URL` | The `cheatsheet_app` URL from [`staging-database.md`](staging-database.md) §2. **No query string** — `sslmode` and `channel_binding` are rejected on purpose |
| `DATABASE_URL_MIGRATIONS` | The `neondb_owner` URL, same format |
| `REDIS_URL` | The internal connection string from §2 |
| `JWT_SECRET` | Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SECRETS_ENCRYPTION_KEY` | 32 bytes base64. Generate with the command in `backend/.env.example` line 59 |
| `APP_BASE_URL` | The **panel's** public URL — filled in at §5, not now |
| `WHATSAPP_ADAPTADOR` | `simulado` on staging (no real Meta credentials, §8). Production must be `meta`; `simulado` is refused there |
| `WHATSAPP_WEBHOOK_SECRET` | The **App Secret** of the Meta app, which signs `X-Hub-Signature-256` on every inbound notification |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | The token typed when the webhook URL is registered in the Meta app |

> **Without `WHATSAPP_WEBHOOK_SECRET` every WhatsApp notification is discarded with a 200** (D49,
> pending #3 of epic 8): the signature can never match an empty secret, and the 200 stops Meta from
> retrying. The two `WHATSAPP_WEBHOOK_*` values are only needed once a Meta app exists
> ([`aidlc/TODO.md`](aidlc/TODO.md) §22.30 and §22.39). The company's own WhatsApp token and number are
> **not** environment variables: they live in `integrations`, per company.

> **`SECRETS_ENCRYPTION_KEY` is not a password you can change your mind about.** It encrypts every
> integration credential at rest. Rotating it later means re-encrypting `configuracion_de_integracion`
> **and** `ticket_de_acceso` ([`aidlc/TODO.md`](aidlc/TODO.md) §7). Generate it once, store it in the
> team's password manager the same day, and never regenerate it to "start clean".

Deploy will fail until `APP_BASE_URL` exists. That is expected; continue.

---

## 4. Create the panel

1. **New → Web Service** → the same repository.
2. **Name**: `cheatsheet-panel`
3. **Region**: Ohio · **Branch**: `develop` · **Plan**: Free
4. **Language / Runtime**: **Node**
5. **Root Directory**: `frontend`
6. **Build Command**: `npm ci && npm run build`
7. **Start Command**: `npm start`
8. **Auto-Deploy**: **No**
9. **Environment variables**:

| Key | Value |
| --- | --- |
| `NODE_VERSION` | `22` — what `package.json` `engines` and CI both pin |
| `APP_BASE_URL` | This service's own public URL, filled in at §5. The panel builds the Google OAuth redirect from it and silently falls back to `http://localhost:3000`, which sends the user to their own machine instead of failing |
| `BACKEND_API_URL` | The API's **Internal Address**, copied from `cheatsheet-api` → Settings in the dashboard. It looks like `http://cheatsheet-api:10000` — **copy it, do not guess the port**: Render assigns `PORT` and the container binds to whatever it is given. Internal on purpose: the browser never talks to the API, only this app's own BFF route handlers do, so the traffic has no reason to leave Render. The public `https://…onrender.com` URL also works and is the fallback if the internal one is refused |

---

## 4 bis. Create the worker, and give it somewhere to put files

This is **the only service that costs money**: Render's free plan has no background workers. One
Starter instance, ~USD 7/month, and nothing else in this environment leaves its free tier.

### 4 bis.1 Object storage first (Cloudflare R2, free tier)

Do this before the worker, because the worker needs the four values.

`GenerarPaqueteContable` runs in the API **and** in the worker. With `ALMACENAMIENTO_ADAPTADOR`
unset it defaults to the in-memory adapter, and the package one process builds is invisible to the
other: the download returns a file nobody can find. R2's free tier (10 GB, 1 M writes, 10 M reads,
no egress charge) covers staging comfortably.

1. <https://dash.cloudflare.com> → **R2** → create a bucket, e.g. `cheatsheet-staging`.
2. **Manage R2 API Tokens** → create a token with **Object Read & Write** limited to that bucket.
3. Keep the four values: the S3 endpoint `https://<account_id>.r2.cloudflarestorage.com`, the bucket
   name, the access key id and the secret access key.

### 4 bis.2 The worker service

**New → Background Worker** → the `CheatSheet` repository:

| Field | Value |
| --- | --- |
| **Name** | `cheatsheet-worker` |
| **Region** | Ohio · **Branch**: `develop` · **Instance Type**: Starter |
| **Language / Runtime** | Docker |
| **Dockerfile Path** | `./backend/Dockerfile` · **Context**: `./backend` |
| **Auto-Deploy** | **No** — same reason as every other service |
| **Start Command** | `celery -A cheatsheet.workers.main:app worker -B -s /tmp/celerybeat-schedule -Q integrations_sync,spreadsheet_processing,incremental_sync,notifications,ai_nlp -c 2` |

Environment variables: the same seven the API has — `APP_ENV`, `DATABASE_URL`,
`DATABASE_URL_MIGRATIONS`, `JWT_SECRET`, `SECRETS_ENCRYPTION_KEY`, `APP_BASE_URL`, `REDIS_URL` —
plus `ALMACENAMIENTO_ADAPTADOR=r2` and the four `R2_*` values from §4 bis.1. **Add those five to the
API as well**, or it will keep writing reports into its own memory.

The worker also needs `WHATSAPP_ADAPTADOR`, with **the same value as the API**: the payment-reminder
sweep runs here and has to pick the same channel the API does (`simulado` on staging). It does not
need the two `WHATSAPP_WEBHOOK_*` values, which only the API reads.

> **`SECRETS_ENCRYPTION_KEY` must be character-for-character the same as the API's.** Integration
> credentials are encrypted with it. A worker with a different key fails every ARCA authorisation
> with `CredencialIlegible` while the stored row looks perfectly healthy.

### 4 bis.3 Two things that are part of the decision, not defaults

**`-B` embeds Beat in this worker**, instead of paying for a second service to run a scheduler that
fires ten tasks a day. It is safe because **there is exactly one instance**. Scale this service and
you get two schedulers — two WhatsApp polls and two emails to every Administrador. If it ever needs
a second instance, Beat moves out to its own `numInstances: 1` service *first*.

**`-s /tmp/celerybeat-schedule` is required, not decoration.** With `-B`, Beat persists its
schedule to a file whose default path is the working directory. The image copies everything as root
and then drops to an unprivileged user, so `/app` is not writable and the worker dies on boot. The
schedule is rebuilt from `workers/beat.py` at every start, so an ephemeral `/tmp` loses nothing.

**`-c 2`, not 4.** The image measures ~82 MB per process, so a parent and two children fit a
Starter's 512 MB with room. Four children do not, and the failure is an out-of-memory kill in the
middle of a task.

**No `-l`: `LOG_LEVEL` sets the worker's log level**, as it does the API's. The worker answers
Celery's `setup_logging` signal (`workers/celery_app.py`, `conservar_el_logging_propio`), so Celery
leaves the logging that `configurar_logging` installed alone, and `-l` has no effect. Before that,
a worker without `-l` dropped every `info` line. That includes `invitacion_no_enviada_modo_consola`,
the line that carries the invitation link while `EMAIL_ADAPTADOR` is unset (console mode). **That
line is in the worker's logs, not the API's**, because the worker sends the invitations.

---

### 4 bis.4 Let the database sleep (Neon compute budget)

Neon's Free plan gives 100 compute-unit hours per project per month, and suspends the compute
after five idle minutes. A compute that never sleeps costs 0.25 CU x 24 h = 6 CU-h per day, which
exhausts the month in about 17 days. Two things kept it awake, and both are fixed in code:

- the Render health check ran `SELECT 1` every few seconds -> use `/health/live` (§3, step 7);
- every periodic task fired at its own offset from Beat's boot -> they now fire at the same
  wall-clock instants (minute 0 of the hour), so the database wakes once per period. Intervals must
  tile the hour or the day exactly (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60, 120, 180, 240, 360,
  480, 720 or 1440 minutes); anything else, such as 45, stops the process at boot with a message
  naming the variable.

The remaining lever is how often the tasks fire. Set these on the **worker** (the only service
running Beat) in the Render dashboard:

| Variable | Default | Staging | What you give up |
| --- | --- | --- | --- |
| `BILLING_RECONCILIACION_MINUTOS` | 5 | 60 | A voucher whose ARCA answer was lost waits up to an hour to be reconciled instead of five minutes |
| `DLQ_BARRIDO_MINUTOS` | 15 | 120 | A task that ran out of retries is retired to the dead-letter state up to two hours later |
| `WHATSAPP_SONDEO_MINUTOS` | 30 | 120 | A WhatsApp number's Meta verification result is noticed up to two hours later |
| `SYNC_PLANILLAS_MINUTOS` | 60 | 240 | A live spreadsheet is re-read every four hours instead of every hour |

With these values every sweep lands on an even hour or on a multiple of four, so the compute wakes
roughly once an hour (the hourly payment sweep) and for about five minutes each time: well under
1 CU-h per day. Production keeps the defaults. Any value that does not divide the hour or the day
is refused at boot, so a typo cannot silently change how often a billing sweep runs.

---

## 5. Cross-wire the two URLs

The two services each need the other's address, which is why this is a step of its own.

1. Copy the panel's public URL (`https://cheatsheet-panel-XXXX.onrender.com`).
2. Set it as `APP_BASE_URL` **on both services**, without a trailing slash. Same name, same
   value, two different reasons: on the API it is what the MercadoPago `redirect_uri` derives
   from; on the panel it is what the Google OAuth redirect is built from.

`APP_BASE_URL` is the panel's URL and not the API's because that is what the MercadoPago
`redirect_uri` is derived from (`platform/settings.py`), and the OAuth2 return lands on the
integrations screen of the panel (decision D-a of `conexion-mercadopago`). It has to match what is
registered in the MercadoPago application **character for character**, or the exchange fails with
`invalid_grant` — an error whose message talks about the code, not about the URL.

---

## 6. Wire the pipeline

### 6.1 Deploy hooks, from Render

For **each of the three services** — API, panel and worker: **Settings → Deploy Hook → copy URL**.

A deploy hook is a secret URL: anyone holding it can trigger a deploy. Treat it as a credential —
the workflow never echoes it, not even when curl fails.

### 6.2 Secrets, into GitHub

Repository → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
| --- | --- |
| `DATABASE_URL_MIGRATIONS` | The `neondb_owner` URL. Only the workflow migrates; the services never receive it |
| `DATABASE_URL` | The `cheatsheet_app` URL. The verifier needs both roles to try crossing the barrier |
| `RENDER_DEPLOY_HOOK_API` | From §6.1 |
| `RENDER_DEPLOY_HOOK_PANEL` | From §6.1 |
| `RENDER_DEPLOY_HOOK_WORKER` | From §6.1. Without it the worker keeps running the code of its last boot while the API moves ahead, and a task is half-understood rather than rejected |
| `STAGING_API_URL` | The API's public URL, no trailing slash. Used to poll `/health` |

### 6.3 What the workflow does

The `deploy-staging` job of `.github/workflows/ci.yml`, on every push to `develop`:

```
CI green -> alembic upgrade head -> verify_rls.py -> deploy hooks -> /health 200
            (owner role)           (app role)
```

It is a job of the CI workflow with `needs:` on the seven gates that run on push, so **a broken push never reaches
staging**: a failed gate means the job never starts. (It is not a separate workflow on
`workflow_run` — GitHub only fires those from the default branch, `main`, so such a workflow living
on `develop` would never run.) Migrations run before the release, as the owner role. The tenant-barrier
verifier then runs against Neon — not against a container — and a non-zero exit aborts the job
before any deploy hook is called, leaving the previous version serving.

---

## 7. Verify

```bash
curl -i https://<api>.onrender.com/health      # 200, estado "ok", base y redis en true
```

Then, in a browser: open the panel, register a company, complete the onboarding, and open
**Configuración → Integraciones**. The four cards should render and **Verificar** should work. That
is the environment existing.

To confirm the pipeline rather than the environment, push a trivial commit to `develop` and watch
the **Deploy to staging** job of the CI run migrate, verify and release after the other eight jobs
go green.

---

## 8. What staging still does not have

- ~~**The Celery workers and Beat.**~~ Deployed on **2026-09-18** as one Starter worker with Beat
  embedded — see §4 bis. This is the only paid instance of the environment.
- **Real provider credentials.** ARCA, Meta and MercadoPago run simulated, on purpose: the simulated
  adapters refuse to be constructed in `production`, not in `staging`
  ([`aidlc/TODO.md`](aidlc/TODO.md) §5).
- **Production.** `main` deploys nothing. That is a separate decision with a different data profile.

---

## 9. When something fails

| Symptom | Cause |
| --- | --- |
| The API boot-loops with `ConfiguracionFaltante: Falta la variable de entorno …` | One of the five required variables is missing. The message names it. §3 |
| `ConfiguracionDeConexionInvalida: La URL de la base declara sslmode, channel_binding` | The Neon string was pasted with its query string. TLS is decided in code, not in the URL — [`staging-database.md`](staging-database.md) §2 |
| The deploy workflow never runs | It waits for CI. A red CI means no deploy, by design. Check **Actions → CI** first |
| The workflow runs but `/health` never returns 200 | The deploy hook only *requests* a deploy. Look at the service's log in Render: the failure is there, not in Actions |
| `/health` returns 503 with `redis: false` | The Key Value instance is in another region, or the external connection string was used instead of the internal one. §2 |
| The panel loads but every action fails | `BACKEND_API_URL` is wrong, or points at the public URL of a suspended service. §4 |
| MercadoPago returns `invalid_grant` on the first connection attempt | `APP_BASE_URL` does not match the `redirect_uri` registered in the MercadoPago application, character for character. §5 |
| The first request after a quiet period takes ~30 s | The free plan suspends idle services and Neon suspends idle compute. Both are waking. Not a fault |
| A migration failed and the services still serve the old version | That is the design: the job aborts before the deploy hooks. Fix the migration and push again |
