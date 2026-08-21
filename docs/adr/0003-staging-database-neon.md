# ADR-0003 — Run the staging database on Neon, and prove the tenant barrier survives it

- **Status:** Proposed
- **Date:** 2026-08-21
- **Decided by:** Software Architect
- **Modules affected:** `infra` (and, indirectly, every context that stores `empresa_id`)

---

## Context

[`configuration-management.md`](../configuration-management.md) §5 settled that the project runs
three environments and that **every demonstration happens on `staging`**, never on a member's
laptop and never on production. §7 makes provisioning it, and distributing its credentials, the
Software Architect's responsibility. What was never settled is *where that database physically
lives*.

Until now there were two PostgreSQL instances and both are disposable: a local container, and the
service container CI starts and throws away per job. Staging is the first one that has to outlive
the process that created it, be reachable by more than one person, and hold data somebody cares
about between one demo and the next.

Three constraints shape the choice, and only the third is interesting.

**Cost and operations.** This is a university project. Nobody is going to patch an operating system
or rotate a backup schedule, and there is no budget line for a database.

**The engine, not a substitute for it.** The system already depends on PostgreSQL features that are
not portable: `pgvector` for semantic search over FAQs and intents (epic 8), `btree_gist` for the
exclusion constraint that stops two `Turno` overlapping (epic 7), and `SECURITY DEFINER` functions
for the lookups that happen before a tenant is known (migrations 0002 and 0003). Whatever runs
staging has to be PostgreSQL 16 with those extensions available, not something PostgreSQL-flavoured.

**The tenant barrier is a property of provisioning, not of code.** This is the one that makes the
decision non-obvious. ADR-002 put multi-tenant isolation on Row-Level Security, and
`platform/database.py` documents the two conditions that make it real: the connection announces its
company through `app.current_empresa`, and **the application connects as a role that does not own
the tables**. PostgreSQL exempts a table's owner from that table's policies, and exempts a
`BYPASSRLS` role from everyone's. Migration 0001 therefore creates `cheatsheet_app` deliberately
owning nothing, and marks every table `FORCE ROW LEVEL SECURITY`.

None of that is enforceable from inside the repository. It depends entirely on how the database was
set up, and a managed provider is exactly where that assumption gets broken by a convenience
feature — while every test in the suite keeps passing, because the suite runs against a container
that was provisioned correctly.

## Decision

**We will run the staging database on Neon** (serverless PostgreSQL 16), with the application role
created **exclusively through SQL**, and we will verify the isolation barrier against the live
database rather than assume it.

Three parts, all three required:

**1. Two roles, two URLs, one direct endpoint.**

| Variable | Role | Purpose |
| --- | --- | --- |
| `DATABASE_URL_MIGRATIONS` | the role Neon creates with the project (`neondb_owner`), member of `neon_superuser` | Alembic, `CREATE EXTENSION`, owns the tables |
| `DATABASE_URL` | `cheatsheet_app` — created with SQL, owns nothing | The application. Subject to RLS |

Both point at Neon's **direct** endpoint, not the pooled one, and **neither carries a TLS
parameter**: `platform/database.py::argumentos_de_conexion` decides TLS from the host, giving any
non-local host a verified `ssl.create_default_context()` and localhost none. That is not a style
preference — asyncpg follows libpq, where `ssl=verify-full` demands a CA file at
`~/.postgresql/root.crt` and fails without it, and `ssl=require` **silently degrades to
`CERT_NONE`**, encrypting the traffic while never identifying the server. A verified context is an
object, and an object cannot travel in a URL. A TLS parameter left in the string is rejected with a
message rather than forwarded. No new configuration variable is introduced: both URLs already exist
and only their values change.

**2. `cheatsheet_app` is created with SQL, never in the Neon console.** Every role created through
Neon's console, API or CLI is granted membership in `neon_superuser`, which carries `BYPASSRLS`. A
`cheatsheet_app` created that way inherits it, every `aislamiento_por_empresa` policy stops firing,
and the failure is completely silent. `backend/scripts/provision_app_role.py` creates the role, takes
its password from the environment so no credential enters the repository or a shell history, and
refuses to report success if the role can bypass RLS.

**3. `backend/scripts/verify_rls.py` is the acceptance test of the environment.** It checks role
attributes, inherited `BYPASSRLS`, table ownership, `FORCE` and policies on every table carrying
`empresa_id`, the append-only grants on the audit log, the two extensions, and the migration head —
and then stops describing and starts probing: the owner writes two audit rows under two throwaway
companies, and the application role must see exactly one of them when it announces a company and
none when it announces nothing.

That script also runs **in CI**, against the job's own container, together with a step that grants
`BYPASSRLS` to the role and asserts the script fails. A verifier nobody executes rots, and reports
green on the day it stopped checking anything — the same reasoning that already put the "verify the
R5 ESLint rule still fires" step in the pipeline.

The connection-string format, the console steps and the failure modes are in
[`docs/staging-database.md`](../staging-database.md).

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **Neon** (chosen) | Free tier sufficient for a shared demo environment; PostgreSQL 16 with `pgvector` and `btree_gist` supported; nothing to operate; database branching is a plausible future fit for per-PR test databases | — |
| **Supabase** | Also managed PostgreSQL with `pgvector`; more batteries included | The batteries are the problem: its auth, its RLS conventions and its client libraries overlap with `identity` and with the BFF, which epic 1 already built and ADR-011 already decided. Adopting it invites a second, contradictory answer to questions this project has answered |
| **Railway / Render / Fly Postgres** | Straightforward managed PostgreSQL; the compute for the API could live next to it later | No advantage over Neon for the database itself, and the free tiers for persistent databases are more restrictive or time-limited. Where the *compute* runs is a separate decision this ADR does not make |
| **Self-managed VPS with Docker** | Full control; identical to the local container; no provider-specific role model, so §2 of this decision would not exist | Somebody has to own patching, backups and uptime. Nobody on this team does, and a staging database that is down on the morning of a demo is worse than one with a quirky role model |
| **Reuse a local container as "staging"** | Free, zero setup | Contradicts §5 of the configuration plan outright: staging is shared and demos never run against a member's machine. It also hides exactly the class of bug this ADR is about, because a local container is always provisioned correctly |

## Consequences

**Positive**

- Staging exists, is shared, and demos stop depending on whose laptop is open.
- The isolation barrier is now **verified where it runs**, not assumed from a passing unit test. The
  probe in check 8 is the first evidence in this project that RLS holds on a database that was not
  created by the test suite.
- The verifier generalises: it discovers the tables to check from `empresa_id` in the catalogue, so
  a table added in a future epic is covered the day it is created, with no edit here.
- Check 2 is written against "any role with `BYPASSRLS` that this role belongs to", not against
  `neon_superuser` by name — so it keeps working if the provider changes.
- CI gains a real assertion that the isolation grants and policies are what the migrations claim.

**Negative / cost we accept**

- **A provider-specific trap is now part of the runbook.** Anyone who creates the role the obvious
  way, in the console, disables the tenant barrier. Two mechanisms fight that, and neither is the
  reviewer's memory — but the trap is real and it exists because of this decision.
- **Vendor coupling in the operational procedure**, not in the code. Moving to another provider
  means rewriting `provision_app_role.py` and step 1 of the runbook. The application, the migrations
  and the verifier move unchanged.
- **TLS is now decided in `platform/database.py`, not in configuration.** That is the right place —
  it is the only one that can hold an `SSLContext` — but it means an operator can no longer weaken
  or strengthen it by editing a URL. Doing so requires a code change and a review, which is the
  intended trade and worth stating.
- **Neon suspends idle compute**, so the first request after a quiet period is slow. Acceptable for
  staging; it is a thing to know before a demo, not during one.
- **The probe writes to the audit log.** Two rows under throwaway companies, removed immediately. If
  the script dies between the write and the cleanup, two orphan rows remain — and they cannot be
  removed by the application, because the log is append-only for it by design.
- Free-tier limits (storage, project count, history retention) are not audited here. If staging
  outgrows them, that is a new decision.

**What becomes harder from now on**

- Provisioning a new environment is no longer "start a container". It is the runbook, and the
  verifier is part of it — a database that has not passed `verify_rls.py` is not a usable
  environment, in any tier.
- Adding a table with `empresa_id` and no policy will now fail CI rather than pass review. That is
  the intent, and it will occasionally be inconvenient.
- Moving staging onto Neon's **pooled** endpoint is a deliberate change, not a URL edit: it needs
  `prepared_statement_cache_size=0` for asyncpg and it excludes the migration URL, which Neon
  requires to be direct. The application's own use of RLS survives it —
  `sesion_de_empresa` sets `app.current_empresa` with the transaction-local form of `set_config`,
  which is precisely what PgBouncer's transaction mode supports — but it is not free.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [x] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — the `tests` job runs
      `verify_rls.py` and asserts that it fails when the role is given `BYPASSRLS`
- [ ] `backend/.env.example` or `frontend/.env.example` — **no new variable**: `DATABASE_URL` and
      `DATABASE_URL_MIGRATIONS` already exist and only their values differ per environment
- [ ] None

## References

- [ADR-0001](0001-repository-structure.md) — repository layout and enforced boundaries
- ADR-002 and ADR-011 of the Etapa 5 design documents, condensed in
  [`architecture.md`](../architecture.md) — multi-tenancy by RLS, and the session model
- [`docs/staging-database.md`](../staging-database.md) — the runbook
- [`docs/aidlc/units/infra-staging-database.md`](../aidlc/units/infra-staging-database.md) — the
  unit plan and its gates
- Neon — [Manage roles](https://neon.com/docs/manage/roles),
  [Connection pooling](https://neon.com/docs/connect/connection-pooling),
  [Supported extensions](https://neon.com/docs/extensions/pg-extensions)
- PostgreSQL — [Row Security Policies](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)
