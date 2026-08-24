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
7. **Health Check Path**: `/health`. It answers 503 while PostgreSQL or Redis is unreachable, so
   Render never routes traffic to an instance that cannot serve.
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
| `BACKEND_API_URL` | The API's **Internal Address**, copied from `cheatsheet-api` → Settings in the dashboard. It looks like `http://cheatsheet-api:10000` — **copy it, do not guess the port**: Render assigns `PORT` and the container binds to whatever it is given. Internal on purpose: the browser never talks to the API, only this app's own BFF route handlers do, so the traffic has no reason to leave Render. The public `https://…onrender.com` URL also works and is the fallback if the internal one is refused |

---

## 5. Cross-wire the two URLs

The two services each need the other's address, which is why this is a step of its own.

1. Copy the panel's public URL (`https://cheatsheet-panel-XXXX.onrender.com`).
2. Set it as `APP_BASE_URL` **on the API**, without a trailing slash.

`APP_BASE_URL` is the panel's URL and not the API's because that is what the MercadoPago
`redirect_uri` is derived from (`platform/settings.py`), and the OAuth2 return lands on the
integrations screen of the panel (decision D-a of `conexion-mercadopago`). It has to match what is
registered in the MercadoPago application **character for character**, or the exchange fails with
`invalid_grant` — an error whose message talks about the code, not about the URL.

---

## 6. Wire the pipeline

### 6.1 Deploy hooks, from Render

For **each** of the two web services: **Settings → Deploy Hook → copy URL**.

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
| `STAGING_API_URL` | The API's public URL, no trailing slash. Used to poll `/health` |

### 6.3 What the workflow does

`.github/workflows/deploy-staging.yml`, on every push to `develop`:

```
CI green -> alembic upgrade head -> verify_rls.py -> deploy hooks -> /health 200
            (owner role)           (app role)
```

It triggers on `workflow_run` of the CI workflow rather than on the push itself, so **a broken push
never reaches staging**. Migrations run before the release, as the owner role. The tenant-barrier
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
**Actions → Deploy to staging** wait for CI, migrate, verify and release.

---

## 8. What staging still does not have

- **The Celery workers and Beat.** Deferred by decision R1 (2026-08-24): Render's background workers
  are a paid plan. Consequences, so no demo discovers them mid-sentence:
  - An invitation is created, shows as pending, and **the email never leaves**. The flow can still be
    completed by copying the link out of the structured log — `EMAIL_ADAPTADOR=consola` writes it.
  - A WhatsApp number stays `pendiente` forever, even after Meta verifies it: nothing polls.
  - The daily MercadoPago renewal and the ARCA expiry warning never fire.

  **To add them**, when the spend is approved: two Background Workers, same repository, same
  `./backend/Dockerfile`, same environment group, differing only in command —
  `celery -A cheatsheet.workers.main:app worker -Q integrations_sync,spreadsheet_processing,incremental_sync,notifications,ai_nlp -c 4`
  and `celery -A cheatsheet.workers.main:app beat`. **Beat runs with exactly one instance.** Two
  schedulers are two WhatsApp polls and two emails to every Administrador — `workers/beat.py` warns
  about this and the warning now has teeth.
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
