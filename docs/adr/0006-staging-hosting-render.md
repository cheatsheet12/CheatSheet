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

### 3. `autoDeploy: false`, and the pipeline holds the trigger

Render's default is to deploy on every push to the tracked branch. Render does not know whether CI
passed, so that default deploys red builds. Every service declares `autoDeploy: false`, and
`.github/workflows/deploy-staging.yml` triggers on `workflow_run` of the CI workflow with
`conclusion == 'success'`.

The literal reading of the request — "every push to `develop` updates the environment" — is what
`on: push` does, and it is wrong: two workflows listening to the same push run in parallel and never
look at each other. The deploy has to be a consequence of CI succeeding.

### 4. Migrations run in the pipeline, as the owner role, and the barrier is re-verified

`alembic upgrade head` runs with `DATABASE_URL_MIGRATIONS` (the `neondb_owner` role), from the
workflow, before the new image is released. This closes the last open item of ADR-0005 §7.

Then `backend/scripts/verify_rls.py` runs **against Neon**, not against a container. It already runs
in CI against the job's PostgreSQL; running it here too is what separates *the policies were correct
when we provisioned the database* from *the policies are correct now*. A non-zero exit aborts the
job before any deploy hook is called, so the services keep serving the previous version.

## Alternatives considered

| Option | Why not |
| --- | --- |
| **Fly.io** | Offers São Paulo (`gru`), which would put compute next to the Neon region — the strongest argument any alternative had. Rejected because it requires a card up front for an academic project, and because everything, panel included, would have to be a Dockerfile, which reintroduces the `standalone` change from sub-decision 2. |
| **Railway** | Fastest to configure, provisions Redis in one click. Rejected for having no persistent free tier: the environment would stop existing when the trial credit ran out, and this environment is where the deliverable is demonstrated. |
| **Vercel (panel) + Render (API)** | Next.js on its native platform, with per-PR previews. Rejected because it doubles the number of providers, secret stores and deploy steps for an internal environment, and the workflow would have to coordinate two unrelated release APIs. |
| **Render's own PostgreSQL instead of Neon** | Would put the database next to the compute and remove the cross-region latency. Rejected because ADR-0005 is three days old and its provisioning is verified: the `cheatsheet_app` role, the RLS `FORCE` checks and the live tenant probe all exist against Neon. Re-provisioning to save latency in a demo environment would be throwing away verified work for a property nobody has complained about. |
| **`on: push` for the deploy workflow** | Deploys red builds. See sub-decision 3. |
| **Migrating on container start** | Simpler to configure, and wrong the moment there is more than one instance: two processes would run `alembic upgrade head` concurrently, which Alembic is not built for. |

## Consequences

### Accepted

- **The workers are not deployed.** Render's background workers are a paid plan, and the decision
  (R1, 2026-08-24) was to defer them. Consequences, stated so no demo discovers them: an invitation
  is created and **the email never leaves** — the flow can only be completed by copying the link out
  of the structured log; the WhatsApp verification poll never runs, so a number stays `pendiente`
  even after Meta verifies it; the daily MercadoPago credential renewal and the ARCA certificate
  expiry warning never fire. None of this blocks the environment: the API boots, the panel is
  navigable, and all three integration-connection flows can be walked end to end.
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
