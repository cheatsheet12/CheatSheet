# ADR-0014 — Keep Celery Beat state in Redis with RedBeat, and schedule calendar-daily entries with crontab

- **Status:** Proposed
- **Date:** 2026-10-06
- **Decided by:** Software Architect — Luciano Oro, owner of the unit `temporizadores-de-beat` (Gate 1 approved 2026-10-06)
- **Modules affected:** infra (`workers/`, transversal); indirectly integrations, reporting and reference_data, whose daily sweeps are the entries that stop being lost

---

## Context

Finding **H-W2**: the daily periodic tasks of the staging worker never run.

**Beat's state does not survive a deploy.** The worker starts as
`celery … worker -B -s /tmp/celerybeat-schedule` (`render.yaml:157-161`). The comment above it
(`render.yaml:151-156`, repeated in `docs/staging-deployment.md:164-167`) justifies `/tmp` by saying
"the schedule is rebuilt from `workers/beat.py` at every start, so there is nothing worth keeping
across one". That premise is the defect. The *definition* of the schedule is indeed in code
(`backend/src/cheatsheet/workers/beat.py:39-117`); what the file holds is each entry's
**`last_run_at`**, and that is exactly what has to be kept. Without it, Celery creates every entry
with `last_run_at = now`, so a `timedelta(days=1)` entry fires 24 hours after the **boot**, not 24
hours after its last run.

**And the worker boots several times a day.** The `deploy-staging` job of
`.github/workflows/ci.yml:411` runs on every push to `develop` with green CI (`ci.yml:431`) and
releases the worker through its deploy hook (`ci.yml:484-491`). With several merges a day, the
24-hour countdown restarts before it ever completes. The entries affected:

| Entry | Interval today | Where |
| --- | --- | --- |
| `revisar-vencimientos-de-credenciales` (HU-E2-01 RN-04) | `timedelta(days=1)` | `beat.py:47-51` |
| `renovar-credenciales-oauth` (HU-E2-02 RN-03) | `timedelta(days=1)` | `beat.py:54-58` |
| `armar-paquetes-contables` (HU-E10-04) | `timedelta(days=1)` | `beat.py:107-111` |
| `sincronizar-parametros-fiscales` (HS-T4) | `PARAMETROS_FISCALES_HORAS`, 24 h by default | `beat.py:68-72` |
| `reindexar-faqs` | `timedelta(hours=6)` | `beat.py:99-103` |

For the accounting package the loss is worse than a day: `barrer_paquetes` selects the companies
whose configured day is *today* (`workers/tasks_reporting.py:58`), so a day without a run is a
month without a package.

**The single-instance premise of ADR-0006 is already broken.** ADR-0006 §5 says `-B` "is safe for
exactly one reason — there is one instance" (`docs/adr/0006-staging-hosting-render.md:95-97`;
`render.yaml:125-129` and `:147`). Render deploys background workers with **zero downtime**: the new
instance starts, and the old one receives `SIGTERM` only 60 seconds later (plus 30 seconds of grace
before `SIGKILL`). For at least a minute per deploy there are **two schedulers**. Today this causes
no duplicates only by accident — a freshly booted Beat fires nothing until a full interval elapses.
Any fix that makes Beat remember its state, or fire at a fixed time, turns that minute into a
double-firing window. `celery_app.py:7-9` and `beat.py:19-21` state why that matters: two reminder
chains, two polls, two emails to every Administrador.

Constraints that frame the answer:

- The pinned stack is `celery[redis]==5.4.0` and `redis==5.2.0` (`backend/pyproject.toml:40-41`).
  There is no synchronous PostgreSQL driver — only `asyncpg`.
- Redis already exists in every environment as the broker (`REDIS_URL`,
  `platform/settings.py:401` and `:516`); CI's integration job already runs a local `redis:7-alpine`.
- Staging's Redis is Render's **free** Key Value instance, which does not persist to disk.
- The two daily sweeps of `integrations` name their run with the **UTC** date
  (`workers/tasks_integrations.py:312-319`) and the package sweep uses the UTC day of month
  (`tasks_reporting.py:58`). Whatever fixes the time of day must keep the Argentina day and the UTC
  day equal at firing time.
- Celery is configured with `timezone="UTC"`, `enable_utc=True` (`workers/celery_app.py:44-45`).

## Decision

> We will run Celery Beat with **`redbeat.RedBeatScheduler`** (`celery-redbeat==2.4.2`), keeping
> the scheduler state and a distributed lock in the existing Redis, and we will schedule the three
> calendar-daily entries with **`crontab` at fixed Argentina times**.

Detail needed to implement it without asking again:

1. **Dependency.** `celery-redbeat==2.4.2` (released 2026-07-27, Apache-2.0), pinned in
   `backend/pyproject.toml` with a comment naming this ADR, following that file's convention. Its
   declared requirements are `celery>=5.0`, `redis>=3.2`, `python-dateutil`, `tenacity`
   (PyPI metadata), all satisfied by the pins above; `python-dateutil` already comes with
   `celery==5.4.0`, so the only new transitive package is `tenacity`.
2. **Scheduler configuration**, in `configurar_beat` (`beat.py:120-124`):
   - `beat_scheduler = "redbeat.RedBeatScheduler"`;
   - `redbeat_redis_url = settings.redis_url` — set explicitly; otherwise RedBeat falls back to the
     broker URL and logs a warning;
   - `redbeat_key_prefix = "cheatsheet:beat"`;
   - `redbeat_lock_timeout = 300` — explicit, equal to 5 × `beat_max_loop_interval` (60 s,
     `beat.py:123`), which is also RedBeat's computed default. It bounds how long a successor waits
     for a lock whose owner died without releasing it.
   - The lock is acquired on Celery's `beat_init` signal, which Celery 5.4.0 also sends for the
     embedded scheduler of `worker -B` (`celery/beat.py:636`, before `beat_embedded_init`). The
     acquire **blocks** until the lock is free, polling every `max_interval`; with `-B` the embedded
     Beat runs in its own child process (`celery/beat.py:703-718`), so the waiting does not stop the
     worker from consuming tasks.
3. **Calendar-daily entries move to `crontab`**, in `America/Argentina/Buenos_Aires`, with named
   constants and a docstring explaining the choice:
   - `revisar-vencimientos-de-credenciales` → `crontab(hour=5, minute=0)`;
   - `renovar-credenciales-oauth` → `crontab(hour=5, minute=15)`;
   - `armar-paquetes-contables` → `crontab(hour=6, minute=0)`.

   These hours are outside the time anyone merges, staggered so they do not compete for a `-c 2`
   worker, and inside the 00:00–20:59 ART window in which the Argentina date equals the UTC date
   (UTC−3, no daylight saving), which keeps `_dia()` and `barrer_paquetes` consistent with the
   company's day.
4. **Celery timezone.** `timezone` becomes `ZONA_ARGENTINA.key` (`shared/zona_horaria.py:13`);
   **`enable_utc` stays `True`**. Messages and ETAs remain UTC; only the frame in which `crontab`
   is read changes.
5. **Interval entries keep `timedelta`.** `sincronizar-parametros-fiscales` and `reindexar-faqs`, and
   every shorter entry (5 min to 1 h), have interval semantics. With persisted state their countdown
   no longer restarts on deploy, and converting them would empty `PARAMETROS_FISCALES_HORAS` of
   meaning.
6. **Start command.** `-s /tmp/celerybeat-schedule` is removed from the worker's `startCommand`:
   RedBeat keeps no file. The change is applied by hand in the Render console, which is the source
   of truth (`render.yaml:13-28`), and mirrored in `render.yaml` and `docs/staging-deployment.md`.
7. **Redis durability per environment.** Staging accepts the free, non-persistent Key Value: a Redis
   restart loses Beat's state exactly as it already loses the broker queue. **Production requires a
   Redis with persistence enabled and `maxmemory-policy noeviction`**; RedBeat's keys carry no TTL,
   and an evicting policy could drop the schedule or the lock.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **`crontab` alone**, no persisted state | No new dependency; a restart no longer resets the clock to "24 h from boot" | Still stateless: a deploy or outage at the firing minute loses that day, which for the accounting package is a lost month. Inside the 60 s deploy overlap both Beats would fire. Does not serve interval or hour-configurable entries. Kept as half of the decision, not as all of it |
| **Render persistent disk** for the `celerybeat-schedule` file | No code; cheap; keeps `last_run_at`. Attaching a disk disables zero-downtime deploy, so the overlap disappears | Ties the fix to a Render feature while production hosting is undecided (ADR-0006 covers staging only). Every worker deploy gains a window with no worker. The unprivileged image user must be able to write the mount. `shelve` can be left corrupt by a `SIGKILL`, and Celery then recreates it empty. Gives no mutual exclusion the day Beat is split out or the worker scales |
| **Own PostgreSQL-backed scheduler** (subclass of `celery.beat.Scheduler`, a schedule table, a leased row lock) | Real durability on Neon; no third-party dependency | Builds on Celery internals (`Scheduler`, `ScheduleEntry`) that are not a public contract. No synchronous driver exists, so every `tick` would bridge into `asyncpg`; a session advisory lock does not survive one event loop per call, so a lease has to be built. Needs a migration, grants to `cheatsheet_app` and a global table outside RLS. Estimated 250–400 lines with tests against ~40 for RedBeat, for the same guarantee |
| **Render Cron Jobs** enqueuing each task | Timing lives outside the worker and is immune to its deploys | One paid service per entry, or a dispatcher of our own; the schedule leaves the code for `render.yaml`; a container boot per firing. Same Render coupling as the disk |
| **Shorter intervals** (run "daily" sweeps hourly and let per-day idempotency absorb the extra runs) | No dependency, no infrastructure | A patch, not a fix: still depends on deploys being further apart than the interval, does 24× the work, and `armar_paquete` has no per-day key, so it would rebuild the package every hour of the configured day |

## Consequences

**Positive**
- H-W2 is fixed at the root: `last_run_at` lives outside the container, so a deploy no longer
  resets any entry. A run missed while the worker was down is recovered once when it comes back.
- The 60-second deploy overlap becomes harmless: the new Beat waits on the lock until the old one
  releases it on `SIGTERM`, or until the lock expires (≤ 300 s) if it was killed.
- Calendar-daily work happens at a known Argentina time, independent of when the last deploy was.
- Beat can later be split into its own service, or the worker scaled, without double firing — the
  move ADR-0006 §5 anticipated no longer needs `numInstances: 1` as its only guard.
- No new environment variable and no `.env.example` change: RedBeat reuses `REDIS_URL`.

**Negative / cost we accept**
- A new runtime dependency (`celery-redbeat`) plus `tenacity`. Compatibility with `celery==5.4.0`
  and `redis==5.2.0` is established from declared metadata and from reading the 2.4.2 source; it
  must be confirmed by installing it and running the suite before the pin is merged.
- Beat's state is only as durable as Redis. On staging's free Key Value a Redis restart wipes it.
  An entry with no stored state is treated by RedBeat as never run and therefore **due at once**
  (`redbeat/schedulers.py:376-378`): after a wipe — and on the very first deploy of this change —
  every entry, the three `crontab` ones included, fires once immediately, and then settles on its
  schedule. Every task tolerates a duplicate firing (per-company `dia-<date>` key for expiry and
  renewal, `paso` for payment reminders, state-driven sweeps elsewhere, rebuild-without-duplicate for
  the package, upsert by validity for the fiscal parameters), so this costs work, not correctness.
- The day a deploy's old instance is `SIGKILL`ed instead of exiting cleanly, the scheduler is silent
  for up to `redbeat_lock_timeout` (300 s). Entries due in that gap fire late, not never.
- The schedule docs this ADR contradicts must be corrected in the same PR: the comment at
  `render.yaml:151-156`, `docs/staging-deployment.md` §4 bis.3, the "singleton" wording at
  `beat.py:19-21` and `celery_app.py:7-9`, row 9 of `docs/architecture.md` (`:44`), and the
  "Beat holds no state" remark at `tasks_integrations.py:315`.
- **ADR-0006 is amended, not edited.** Its body stays as accepted; a single line
  "Amended by [ADR-0014](0014-persistent-beat-schedule.md)" is added to its header, and this ADR is
  where the reason lives: the single-instance premise of its §5 never held during a deploy, and the
  distributed lock replaces it as the guard against duplicate scheduling.

**What becomes harder from now on**
- Provisioning production: its Redis is no longer "just a broker"; it must persist and must not
  evict. Choosing a managed Redis now has a non-negotiable configuration line.
- Changing the time of a daily entry, or adding one, means choosing an Argentina hour inside
  00:00–20:59 for as long as `_dia()` and `barrer_paquetes` use the UTC day. Fixing those two to use
  the Argentina day is a separate correction in `integrations` and `reporting`.
- Inspecting or resetting the schedule is now done in Redis (`cheatsheet:beat:*` keys), not by
  deleting a file. Removing an entry from `beat.py` is cleaned up by RedBeat at the next start.
- Beat's correctness now depends on a third-party scheduler's lock semantics; upgrades of Celery or
  RedBeat must re-run the lock and persistence integration tests.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [ ] `backend/.env.example` or `frontend/.env.example`
- [x] None

None of R1–R5 is affected and no root directory is created. The dependency goes into
`backend/pyproject.toml` (application dependencies), not the root one; the integration tests reuse
the Redis service CI already runs.

## References

- [ADR-0006](0006-staging-hosting-render.md) — §5, the single-instance premise this ADR amends.
- Unit plan `docs/aidlc/units/temporizadores-de-beat.md` (branch `fix/infra-temporizadores-de-beat`),
  Gate 1 approved 2026-10-06; finding H-W2 in `docs/aidlc/units/navegacion-pendiente.md`.
- `render.yaml:125-161`, `docs/staging-deployment.md` §4 bis.3, `.github/workflows/ci.yml:411-491`.
- `backend/src/cheatsheet/workers/beat.py`, `workers/celery_app.py`, `workers/tasks_integrations.py`,
  `workers/tasks_reporting.py`, `shared/zona_horaria.py`.
- celery-redbeat 2.4.2 — <https://pypi.org/project/celery-redbeat/2.4.2/>,
  <https://redbeat.readthedocs.io/en/latest/> (configuration, design: lock and timezone);
  source read: `redbeat/schedulers.py` (`acquire_distributed_beat_lock`, `RedBeatScheduler.__init__`,
  `update_from_dict`, `due_at`).
- Celery 5.4.0 source: `celery/beat.py` (`Service.start`, `EmbeddedService`).
- Render docs: <https://render.com/docs/deploys> (zero-downtime deploys, shutdown timing),
  <https://render.com/docs/disks> (a disk disables zero-downtime deploy),
  <https://render.com/docs/key-value> (free instances do not persist).
