# ADR-0006 — Render hosts the staging environment, and GitHub Actions drives the deploy

- **Status**: Proposed — becomes `Accepted` when this unit's PR merges, as ADR-0003 did with PR #6
- **Date**: 2026-08-24
- **Supersedes**: nothing
- **Related**: [ADR-0005](0005-staging-database-neon.md) (the staging database),
  [`configuration-management.md`](../configuration-management.md) §5 and §7,
  [`staging-deployment.md`](../staging-deployment.md) (the runbook)

---

## Context

[ADR-0005](0005-staging-database-neon.md) left the staging **database** provisioned and verified on
Neon, and said plainly that a database is not an environment. Its §7 listed what was still missing:
Redis, somewhere for the backend and the frontend to run, the Celery workers, and automatic
migrations.

`configuration-management.md` §5 already decided that `staging` exists, that it is shared, and that
**every demonstration runs against it** — never against a laptop, never against production. §7 puts
provisioning and the pipeline on the Software Architect. So the question is not *whether* to host
staging. It is *where*, and *what releases it*.

Two constraints framed the answer:

1. **The backend is three processes, not one.** The API, the Celery workers and Beat share a code
   base and differ only in their command. Whatever hosts them has to run long-lived non-HTTP
   processes, not just a web server.
2. **The panel is a Next.js server, not a static site.** Its BFF route handlers hold the session
   cookie and are the only thing that talks to the API — `api/main.py` documents that the browser
   never does, which is why the API ships no CORS middleware. A static export would delete the
   layer the authentication design depends on.

## Decision

**Render hosts staging: the API as a Docker web service, the panel on the Node runtime, and Redis
as a managed Key Value instance — all in the `ohio` region. Releases are driven by a GitHub Actions
workflow that runs only after CI passes, applies migrations, and re-verifies the tenant barrier
before calling Render's deploy hooks.**

Four sub-decisions carry the weight.

### 1. One image for three commands

`backend/Dockerfile` builds a single image that serves `uvicorn`, `celery worker` and `celery beat`.
Today only the API is deployed (see *Consequences*), but the image is written for all three from the
start. A second image built later for the workers is a second thing that can lag behind the first,
and a worker running older code against a newer schema fails silently — it consumes a task it
half-understands rather than crashing.

### 2. The panel does not go in a container

Packaging Next.js as an image requires `output: 'standalone'` in `next.config`. That is changing the
application to suit the platform, for no gain: Render's Node runtime runs `npm ci && npm run build`
and `npm start` against the same Node 22 that `package.json` and CI already pin. Consistency between
the two services is not worth a build-mode change in the application.

### 3. `autoDeploy: false`, and the deploy is a job of the CI workflow

Render's default is to deploy on every push to the tracked branch. Render does not know whether CI
passed, so that default deploys red builds. Every service declares `autoDeploy: false`, and the
release is a **`deploy-staging` job inside `.github/workflows/ci.yml`** that declares `needs:` on all
seven gates that run on push, and runs only when `github.event_name == 'push' && github.ref ==
'refs/heads/develop'`.

The literal reading of the request — "every push to `develop` updates the environment" — is what a
standalone `on: push` workflow does, and it is wrong: two workflows listening to the same push run in
parallel and never look at each other, so the deploy would not know CI failed.

**A separate workflow triggered by `workflow_run` was the first design, and it does not work in this
repository.** GitHub only fires `workflow_run` from the copy of the workflow file on the
**default branch**, which here is `main`. A deploy workflow living on `develop` would sit there and
never run — and nothing would report an error, which is the worst shape a failure can take. It was
caught on 2026-08-24, by a Render build that failed for an unrelated reason.

As a job it is also the stronger guarantee: `needs:` is a hard dependency evaluated inside one run,
so a failed gate means the deploy never starts. There is no second workflow that has to look up
whether the first one passed.

### 4. Migrations run in the pipeline, as the owner role, and the barrier is re-verified

`alembic upgrade head` runs with `DATABASE_URL_MIGRATIONS` (the `neondb_owner` role), from the
workflow, before the new image is released. This closes the last open item of ADR-0005 §7.

Then `backend/scripts/verify_rls.py` runs **against Neon**, not against a container. It already runs
in CI against the job's PostgreSQL; running it here too is what separates *the policies were correct
when we provisioned the database* from *the policies are correct now*. A non-zero exit aborts the
job before any deploy hook is called, so the services keep serving the previous version.

### 5. Beat rides inside the worker, and object storage stops being optional

`-B` runs the scheduler in the worker process. The textbook shape is a separate Beat service, and it
is the right shape the day this scales; here it would double the only bill in the environment for a
staging where one person clicks at a time. **It is safe for exactly one reason — there is one
instance** — so `numInstances: 1` is not a default but part of the decision: two instances with `-B`
are two schedulers, two WhatsApp polls and two emails to every Administrador.

Adding the worker also forces `ALMACENAMIENTO_ADAPTADOR=r2`. `GenerarPaqueteContable` runs in the API
*and* in the worker, so with the in-memory adapter the package one process builds is invisible to the
other, and a download returns a file nobody can find. R2's free tier covers this at no cost, so the
constraint is a setup step rather than a second line on the invoice.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Fly.io** | Offers São Paulo (`gru`), which would put compute next to the Neon region — the strongest argument any alternative had. Rejected because it requires a card up front for an academic project, and because everything, panel included, would have to be a Dockerfile, which reintroduces the `standalone` change from sub-decision 2. |
| **Railway** | Fastest to configure, provisions Redis in one click. Rejected for having no persistent free tier: the environment would stop existing when the trial credit ran out, and this environment is where the deliverable is demonstrated. |
| **Vercel (panel) + Render (API)** | Next.js on its native platform, with per-PR previews. Rejected because it doubles the number of providers, secret stores and deploy steps for an internal environment, and the workflow would have to coordinate two unrelated release APIs. |
| **Render's own PostgreSQL instead of Neon** | Would put the database next to the compute and remove the cross-region latency. Rejected because ADR-0005 is three days old and its provisioning is verified: the `cheatsheet_app` role, the RLS `FORCE` checks and the live tenant probe all exist against Neon. Re-provisioning to save latency in a demo environment would be throwing away verified work for a property nobody has complained about. |
| **`on: push` for the deploy workflow** | Deploys red builds. See sub-decision 3. |
| **A separate `cheatsheet-beat` service** | The shape the Celery docs recommend, and what this blueprint declared between 2026-09-15 and 2026-09-18. Rejected for staging because it doubles the only paid instance to run a scheduler that fires ten tasks a day. It returns the moment the worker needs a second instance. |
| **Keeping `ALMACENAMIENTO_ADAPTADOR=memoria`** | Free, and broken as soon as the worker exists: the accounting package is built in one process and downloaded from another. |
| **Migrating on container start** | Simpler to configure, and wrong the moment there is more than one instance: two processes would run `alembic upgrade head` concurrently, which Alembic is not built for. |

## Consequences

### Accepted

- **One paid instance, and only one.** Decision R1 (2026-08-24) deferred the workers because they
  are the only part of this environment that is not free. On **2026-09-18** that cost was accepted at
  its minimum: a single Starter worker with **Beat embedded** (`-B`), rather than the textbook two
  services. Everything else stays free — API, panel, Key Value, Neon, and R2 within its free tier.
  What the deferral had cost, and what this restores: invitations whose email never left, a WhatsApp
  number stuck at `pendiente` because nothing polled, a spreadsheet that never finished processing,
  a document that never got its CAE, and the accounting package that was never assembled.
- **Cross-region latency.** Neon is in `sa-east-1` (São Paulo) and Render has no São Paulo region;
  `ohio` is the nearest of the five. Every query crosses that distance and it is visible in the
  panel. The fix, if it ever matters, is moving the database next to the compute — not moving the
  compute.
- **The free plan suspends idle services.** The first request after a quiet period is slow, and it
  compounds with Neon waking its own suspended compute. The deploy workflow's health check budgets
  ten minutes for exactly this.
- **A window where old code meets a new schema.** Migrations precede the release by seconds.
  Tolerable while migrations only add and staging has no real users; the day a destructive migration
  exists, the answer is expand/contract, not reordering these two steps.
- **This diverges from `architecture.md`, which says the panel runs on Vercel.** That document
  (row 2 of its container table) describes the *target production* architecture decided in Etapa 5,
  and it is an input this unit consumes rather than rewrites. The divergence is real and is recorded
  here instead: **staging runs the panel on Render**, and whether production follows Vercel or Render
  is a decision that belongs to whoever provisions production. Two stale comments point the same way
  and were deliberately left alone — the header of `frontend/.env.example` was corrected because it
  describes *this* environment's deployment, while the one in `api/main.py` ("the panel is served
  from another origin (Vercel)") is making a point about origins that is still true.
- **A second place where deploy state lives.** Render's dashboard knows things the repository does
  not (which deploy is live, why one failed). `render.yaml` keeps the *shape* of the environment
  reviewable; it does not make the console redundant.

### Rejected consequences — things that are explicitly not true

- **This is not production.** `main` deploys nothing when this unit closes. Production has real
  pilot-business data and a different credential set, and deciding it in passing is how an
  environment ends up with staging's guarantees and production's data.
- **This does not make the providers real.** ARCA, Meta and MercadoPago still run simulated in
  staging. The simulated adapters refuse to be constructed in `production`, not in `staging`, which
  is precisely what lets the environment be demonstrated before any real credential exists
  ([`aidlc/TODO.md`](../aidlc/TODO.md) §5).
