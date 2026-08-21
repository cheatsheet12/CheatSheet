# The staging database (Neon)

How the PostgreSQL database of the **testing (`staging`)** environment
([`configuration-management.md`](configuration-management.md) §5) is created, connected to and
verified. The decision to use Neon and its trade-offs are in
[ADR-0005](adr/0005-staging-database-neon.md).

This document covers the **database only**. What staging still needs in order to actually run is
listed in §7.

> **No real credential appears in this file, and none may be added to it.** Values travel over a
> private encrypted channel (§4.3 of the configuration plan). What is written here is the *shape* of
> each string, never an instance of one.

Everything below runs with the repository's Python environment — the same one Alembic needs. No
`psql` and no PostgreSQL client installation are required.

---

## 0. The one thing to get right

PostgreSQL exempts a table's owner from that table's Row-Level Security policies, and it exempts
`BYPASSRLS` roles from everyone's. The whole multi-tenant barrier of this system (ADR-002,
`platform/database.py`) rests on the application connecting as a role that is neither.

**On Neon, every role created through the console, the API or the CLI is granted membership in
`neon_superuser`, and `neon_superuser` carries `BYPASSRLS`.**

So: **`cheatsheet_app` is created with SQL, never in the console.** A role created the other way
inherits the exemption, every `aislamiento_por_empresa` policy stops firing, and nothing at all
looks broken — the application works, the local suite stays green against its own container, and
staging serves one company's rows to another. Steps 3 and 5 both check for it.

---

## 1. Create the project (Neon console)

| Field | Value | Why |
| --- | --- | --- |
| Project name | e.g. `CheatSheet - staging` | — |
| Postgres version | **16** | The same major as the local container and as CI. With different majors the SQL stops being comparable across environments. |
| Region | The closest one offered to Argentina — `AWS South America East 1 (São Paulo)` | Latency of the demo. |
| **Neon Auth** | **OFF** | It installs authentication with its own user and session tables inside the database. The `identity` context already answers that question — Argon2id, short JWT, rotating refresh with reuse detection (ADR-011). Two contradictory answers to one question is exactly why Supabase was ruled out in ADR-0005. |

Neon's onboarding does not ask for a database or role name; it creates **`neondb`** owned by
**`neondb_owner`**. Leave them. Nothing in the code hardcodes the database name, and the property
that matters is not the naming — it is the two-role split, which step 3 establishes.

`neondb_owner` is the **owner**: it runs migrations, installs extensions and owns the tables. It is
a member of `neon_superuser`, and that is correct for this role — installing `pgvector` requires
privileges the application must never have.

Neon shows the owner's password exactly once. Store it in the team's private channel before closing
the dialog. If it is ever exposed, reset it under **Roles → `neondb_owner` → Reset password**; it
appears nowhere in this repository, so nothing here needs updating.

Then **stop**. Do not create a second role in the console — that is step 3.

---

## 2. Build the two connection strings

Neon offers a string that looks like this:

```
postgresql://neondb_owner:PASSWORD@ep-xxxx-yyyy-123456.sa-east-1.aws.neon.tech/neondb?sslmode=require
```

**It cannot be pasted as-is into `DATABASE_URL`.** The `asyncpg` dialect of SQLAlchemy forwards
every URL query parameter as a keyword argument to `asyncpg.connect()`, which accepts neither
`sslmode` nor `channel_binding`. The repository refuses such a URL with a message naming the
offending parameters — in the application and in Alembic alike, since `migrations/env.py` uses the
same driver and the same check.

Two edits turn it into the form this repository uses:

1. `postgresql://` → **`postgresql+asyncpg://`**
2. **Delete the query string entirely** — `?sslmode=require`, `&channel_binding=require`, all of it.

```bash
# Migrations only. Owns the tables, installs extensions.
DATABASE_URL_MIGRATIONS=postgresql+asyncpg://neondb_owner:OWNER_PASSWORD@ep-xxxx-yyyy-123456.sa-east-1.aws.neon.tech/neondb

# The application. Subject to RLS — this is the role that must NOT be the owner.
DATABASE_URL=postgresql+asyncpg://cheatsheet_app:APP_PASSWORD@ep-xxxx-yyyy-123456.sa-east-1.aws.neon.tech/neondb
```

Same host, same database, two different roles. That is the whole point.

### The URL says nothing about TLS, and that is deliberate

The connection is still encrypted **and verified** — the decision just does not live in the string.
`platform/database.py::argumentos_de_conexion` gives any non-local host an
`ssl.create_default_context()`: the platform's own CA store, `check_hostname` on, `CERT_REQUIRED`.
Localhost — a laptop container, a CI job — gets none.

It is done there because every way of expressing it in the URL is a trap. asyncpg follows libpq's
semantics rather than Python's:

- **`?ssl=verify-full` does not use the system trust store.** It looks for a CA at
  `~/.postgresql/root.crt` or `PGSSLROOTCERT` and raises `ClientConfigurationError` when neither
  exists — so it works on the machine that happened to be set up, and nowhere else.
- **`?ssl=require` is worse.** With no CA file it silently falls back to `CERT_NONE`
  (`asyncpg/connect_utils.py`, the `sslmode == SSLMode.require` branch). The traffic is encrypted
  and the server is never identified, which is the failure that looks exactly like success.

A verified context can only be handed to asyncpg as an object, through `connect_args`, and an object
does not fit in a URL. So if a TLS parameter is left in the string, `argumentos_de_conexion`
**refuses to build the connection** and names it — rather than letting SQLAlchemy forward it and
produce a `TypeError` from inside the driver.

**Use the direct endpoint, not the pooled one.** Neon's pooled host has `-pooler` in it; the plain
one does not. Neon's documentation asks for a direct connection for schema migrations, and the
interaction between transaction pooling and asyncpg's prepared statements is a problem class not
worth meeting for the first time in the environment where the demo runs. See ADR-0005 for what
changes if staging later needs the pooler.

---

## 3. Provision the application role

Generate a password that survives being placed inside a URL:

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

That alphabet (`A-Z a-z 0-9 - _`) is safe in the userinfo part of a URL, and the script rejects
anything outside it. A password containing `@`, `/`, `:` or `#` silently truncates the host and
produces an error that looks like anything but a quoting problem.

Then, from the repository root, with the **owner** URL in the environment:

```bash
export DATABASE_URL_MIGRATIONS='postgresql+asyncpg://neondb_owner:...@ep-....neon.tech/neondb'
export APP_ROLE_PASSWORD='<the generated password>'
python backend/scripts/provision_app_role.py
```

Both values are read from the environment and never from the command line, because arguments show
up in the process list and in shell history.

The script creates `cheatsheet_app` if it is missing, gives it `LOGIN` with that password plus
`CONNECT` on the database and `USAGE` on the schema, and then **refuses to report success if the
role can bypass RLS** — which is what happens when the role was created in the console instead. It
is idempotent: running it again rotates the password and re-checks everything.

Save the password in the private channel and put it in `DATABASE_URL`. It is stored nowhere else,
and there is no way to read it back out of PostgreSQL.

---

## 4. Apply the migrations

```bash
alembic -c backend/alembic.ini upgrade head
```

`DATABASE_URL_MIGRATIONS` is already exported from step 3, and Alembic reads only that one — never
`DATABASE_URL`.

This installs `vector` and `btree_gist`, creates the tables, enables and **forces** RLS on each one,
creates the isolation policies, and grants `cheatsheet_app` exactly the privileges each table needs
— `SELECT, INSERT` and nothing else on `registro_de_auditoria`, because the audit log is append-only
in the engine and not merely in Python (HS-T5 RN-03).

Migrations are applied **by hand** in staging, from a machine that has `DATABASE_URL_MIGRATIONS` in
its environment. There is deliberately no deployment workflow yet.

---

## 5. Verify — do not skip this

```bash
export DATABASE_URL='postgresql+asyncpg://cheatsheet_app:...@ep-....neon.tech/neondb'
python backend/scripts/verify_rls.py
```

Both scripts write their report to stdout and signal the outcome with the **exit code** — `echo $?`
in bash, `$LASTEXITCODE` in PowerShell. Nothing is written to stderr on success, because PowerShell
renders a native command's stderr as a red `NativeCommandError` and a successful run would read as a
failure.

Eight checks, exit code 0 only if all of them pass:

| # | Check |
| --- | --- |
| 1 | `cheatsheet_app` holds neither `SUPERUSER` nor `BYPASSRLS` |
| 2 | …and inherits `BYPASSRLS` from no group either (this is the one that catches a console-created role) |
| 3 | …and owns no table in `public` |
| 4 | Every table with an `empresa_id` column has RLS **enabled, forced, and a policy** |
| 5 | On `registro_de_auditoria` the application has `SELECT`/`INSERT` and no `UPDATE`/`DELETE` |
| 6 | `vector` and `btree_gist` are installed |
| 7 | `alembic_version` matches the head of the local migration history |
| 8 | **A live probe**: the owner writes two audit rows under two throwaway companies; the application, announcing one of them, sees exactly one; announcing none, sees zero. Both rows are then removed. |

Checks 1–7 read the catalogue. Check 8 is the one that matters, because it exercises the behaviour
rather than its description. The same script runs in CI against the job's container, together with a
step that grants `BYPASSRLS` to the role and asserts the script fails — so it cannot quietly stop
checking.

If check 2 fails naming `neon_superuser`, the fix is to drop the role and redo step 3 — not to
adjust the policies.

---

## 6. Rotating the application password

Re-run step 3 with a new `APP_ROLE_PASSWORD`, then update `DATABASE_URL` wherever staging reads it
and restart the process. Nothing else changes.

---

## 7. What staging still needs before it can run

The database is not the environment. As of this document:

- **Redis.** `Settings.desde_entorno` requires `REDIS_URL`; without it the process does not start at
  all. Nothing has been provisioned.
- **Somewhere for the backend and the frontend to run.** This document ends at the database.
- **The Celery workers**, and therefore the invitation email
  ([`aidlc/TODO.md`](aidlc/TODO.md) §2.3). An invitation created with no worker on the
  `notifications` queue is stored and never sent, by design.
- **Automatic migrations.** Applied by hand, see step 4.

Test data in staging is controlled by the QA Analyst. **No real data from a pilot business goes into
this database.**

---

## 8. When something fails

| Symptom | Cause |
| --- | --- |
| `ConfiguracionDeConexionInvalida: La URL de la base declara sslmode, channel_binding` | The Neon string was pasted verbatim, query string and all. Step 2. |
| `ConfiguracionFaltante: Falta la variable de entorno DATABASE_URL_MIGRATIONS` | Alembic never reads `DATABASE_URL`; the owner URL is a separate variable, on purpose. |
| Connection refused / host not found, and the password contains punctuation | The password is breaking the URL. Regenerate it with `token_urlsafe`. Step 3. |
| `permission denied for table …` from the application | A migration granted less than the code needs, or was not applied. Step 4, then check 7. |
| Verification check 2 names `neon_superuser` | `cheatsheet_app` was created in the Neon console. Drop it and redo step 3. |
| The first request after a while is slow | Neon suspends idle compute; the first connection wakes it. `pool_pre_ping` already handles the stale-connection half of this. |
