---
name: run-local
description: Launch the CheatSheet API and panel locally, against the local disposable containers or against the Neon staging database, and prove they work. Use when asked to run, start, serve or smoke-test the app.
---

# Running CheatSheet locally

Two processes and two backing services. The API is FastAPI under `uvicorn`; the panel is
Next.js. They talk to PostgreSQL and Redis, and **either can point at a local throwaway
container or at the shared staging instances** — the choice is made entirely by
environment variables, never by code.

Written after doing it the first time on 2026-08-25. Every trap below cost real time.

---

## The four things that are not guessable

**1. Nothing in this repository loads a `.env` file.** There is no `python-dotenv`
dependency and no loader in `platform/settings.py`, in `migrations/env.py` or in the
scripts. Creating `backend/.env` and running `uvicorn` gets you
`ConfiguracionFaltante: Falta la variable de entorno REDIS_URL`. The file has to be
loaded into the process environment explicitly:

```bash
set -a && source backend/.env && set +a
```

The panel is the opposite: Next.js reads `frontend/.env.local` by itself. Its startup
banner says so — `Environments: .env.local`.

**2. The local containers do not use the default ports.** `backend/docker-compose.yml`
maps PostgreSQL to **5433** and Redis to **6380**, so that a natively installed
PostgreSQL or Redis on the standard port cannot be hit by accident. That failure is
nasty: `localhost` resolves, something answers, and it is the wrong database.

**3. On macOS, Python's CA store is very likely empty**, and every TLS connection to a
managed provider fails with `SSLCertVerificationError: unable to get local issuer
certificate`. The python.org build does not use the system keychain: it wants a CA
bundle at `.../etc/openssl/cert.pem`, which the installer only creates when someone runs
`Install Certificates.command`. Check with:

```bash
python -c "import ssl; print(len(ssl.create_default_context().get_ca_certs()))"
```

`0` means broken. The permanent fix is `open "/Applications/Python 3.11/Install
Certificates.command"`. The per-shell escape is `export SSL_CERT_FILE=$(python -m
certifi)`. `backend/tests/platform/test_database_tls.py::test_el_contexto_confia_en_alguna_autoridad`
asserts exactly this and is the canary — if it fails and nothing else does, this is why.
Do not weaken that test; fix the machine.

**4. The database URLs have three rules, and a pasted provider string breaks all three.**
`postgresql+asyncpg://` (not `postgresql://`), no query string at all, and the direct
host rather than the `-pooler` one. `argumentos_de_conexion` rejects the first two by
name; the pooler one it cannot see. Details and reasoning:
[`docs/staging-database.md`](../../../docs/staging-database.md) §2.

---

## A. Against the local containers — the default

Nothing shared, nothing to lose, no credentials.

```bash
docker compose -f backend/docker-compose.yml up -d      # postgres:5433, redis:6380
source .venv/bin/activate

export APP_ENV=local          # 'dev' is not a valid Entorno: local | test | staging | production
export DATABASE_URL=postgresql+asyncpg://cheatsheet_app:test-only-local-container@localhost:5433/cheatsheet
export DATABASE_URL_MIGRATIONS=postgresql+asyncpg://cheatsheet_owner:test-only-local-container@localhost:5433/cheatsheet
export REDIS_URL=redis://localhost:6380/0
export JWT_SECRET=local-only
export SECRETS_ENCRYPTION_KEY=$(python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")

alembic -c backend/alembic.ini upgrade head
```

That password is `test-only-local-container`, literally, in both
`backend/docker-compose.yml` and `backend/scripts/init-db.sql`. It is named that way so
that nobody mistakes it for a secret and so that finding it in a log is unremarkable. If
these lines ever stop working, those two files are the source of truth.

## B. Against the Neon staging database

Same processes, real data. **What you create from here lands in staging**, which
[`configuration-management.md`](../../../docs/configuration-management.md) §5 says is QA's
controlled test data — not a throwaway.

Put the values in `backend/.env` (gitignored) and load it. Redis still comes from the
local container: Render's instance has no public access, on purpose.

```bash
source .venv/bin/activate
export SSL_CERT_FILE=$(python -m certifi)          # see trap 3
docker compose -f backend/docker-compose.yml up -d redis
set -a && source backend/.env && set +a
```

`SECRETS_ENCRYPTION_KEY` **must be the same value the deployed API uses** if you intend
to touch the integrations screen: both processes write to the same database, and
integration credentials are encrypted with it. Two different keys mean whatever you
connect here is unreadable there — `CredencialIlegible` — and the row looks fine.

### If the application role's password is unknown

It cannot be read back from PostgreSQL. Rotate it; the script is idempotent and refuses
to report success if the role can bypass RLS:

```bash
export APP_ROLE_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
python backend/scripts/provision_app_role.py
```

Then put that password into `DATABASE_URL`. **Generating a password does not assign it** —
only this script does. That mistake looks identical to a wrong password.

---

## Launch, and then drive it

```bash
uvicorn cheatsheet.api.main:create_app --factory --host 127.0.0.1 --port 8000 \
        --app-dir backend/src &
( cd frontend && npm run dev & )
```

The factory is `create_app` (English), unlike most of the domain. `--app-dir
backend/src` is what makes the package importable without installing it.

Launching proves nothing on its own. Three checks, in order — each one fails differently:

```bash
# 1. The API and both its dependencies.
curl -s localhost:8000/health
#    {"estado":"ok","base_de_datos":true,"redis":true}   <- what you want
#    503 with base_de_datos:false  -> the URLs; redis:false -> port 6380 or a dead container

# 2. The panel renders.
curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/     # 200

# 3. The panel reaches the API. This is the one people forget.
curl -s -o /dev/null -D - localhost:3000/api/auth/google | grep -i '^location'
#    location: http://localhost:3000/api/auth/google/callback?state=...&simulado=1  <- reached
#    location: http://localhost:3000/?error=ErrorInterno   <- the panel could NOT reach the API
```

Check 3 matters because the browser never talks to the API — only the panel's BFF route
handlers do, which is why the API ships no CORS middleware (`api/main.py` says so). A
green `/health` says nothing about whether the panel can reach it.

Why this route and not another: most BFF routes answer on their own when there is no session.
`/api/auth/empresa`, for instance, returns `401 NoAutenticado` **before** calling the API
(`app/api/auth/empresa/route.ts`), so a 401 there proves only that Next.js is running — it looks
exactly like success while the panel cannot reach the API at all. `/api/auth/google` needs no
session and always calls the API (`/auth/google/url`), so its answer is the only unauthenticated
one that proves the round trip. Two signals in its `Location` header:

- **The host** comes from the panel's `APP_BASE_URL` (on error) or from the API's (on success). If it
  names the API's domain, the two variables were swapped.
- **`?error=ErrorInterno`** means the fetch itself failed — `BACKEND_API_URL` unset, wrong, or the API
  asleep for longer than the BFF's 10-second timeout. An `?error=<Codigo>` with any other code means
  the API was reached and refused.

An earlier version of this skill used `/api/auth/empresa` and read its 401 as proof. It was wrong,
and it reported a healthy staging panel that could not log anyone in (2026-09-14).

Before trusting a run against Neon, `python backend/scripts/verify_rls.py` answers in one
command whether both URLs work, the migrations are applied and one company cannot read
another's rows. Its exit code is the whole answer.

---

## Stopping

```bash
docker compose -f backend/docker-compose.yml down
```

plus killing the two foreground processes. Note that `pytest` drops the local database at
the end of the integration suite: running the tests in the middle of manual QA takes the
test data with it.
