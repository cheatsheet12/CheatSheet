# backend/tests

Mirrors the structure of `backend/src/cheatsheet/`, so a test sits where its subject
does:

```
tests/
├── contexts/<context>/{domain,application,infrastructure}/
├── shared/
└── api/
```

Rules ([`../../docs/code-standards.md`](../../docs/code-standards.md) §4):

- **No test touches the network.** ARCA, MercadoPago, WhatsApp, Google Sheets and the
  LLM are always faked or mocked. A test hitting AFIP homologation is not a test, it is
  a source of flaky failures.
- Domain tests need no fixtures beyond the aggregate itself — that is the point of
  keeping the domain free of I/O (R1).
- Date and time are injected, never read from the clock inside business logic.
- Minimum coverage 80%, gated in CI. Lowering the threshold is forbidden.
- Naming: `test_<what>_<condition>_<expected>()`.

Every fixed bug starts with the test that reproduces it.

## PostgreSQL integration suite (`tests/integracion/`)

These tests need a real PostgreSQL (Row-Level Security has no fake). They are
**destructive**: after every test they `DELETE` from every table, and some downgrade the
migrations to `base` and back. They are skipped unless `DATABASE_URL` and
`DATABASE_URL_MIGRATIONS` are both set.

- **Local / CI**: the Docker container or the CI service on `localhost`; any database name.
- **Neon**: a dedicated branch (`integracion`) with a database named exactly
  `cheatsheet_integracion`. **Never the staging database** (`neondb`).

### The guard

`tests/integracion/guarda.py` checks the destination before any migration, downgrade or
connection (autouse session fixture `destino_verificado` in `conftest.py`). The session
aborts with exit code 2 unless:

1. both URLs name the same host, port and database, and
2. the host is local, **or** the database is named `cheatsheet_integracion`.

The error message prints host, port and database only, never credentials. The rule is
tested without a database in `tests/platform/test_guarda_de_integracion.py`.

### Running it against the Neon branch

Keep the credentials in a file **outside the repository** and load it into the shell:

```bash
set -a; source ~/.cheatsheet-integracion.env; set +a   # never commit this file
pytest backend/tests/integracion -q -p no:cacheprovider
```

```
DATABASE_URL=postgresql+asyncpg://cheatsheet_app:APP_PASSWORD@ep-xxxx.region.aws.neon.tech/cheatsheet_integracion
DATABASE_URL_MIGRATIONS=postgresql+asyncpg://neondb_owner:OWNER_PASSWORD@ep-xxxx.region.aws.neon.tech/cheatsheet_integracion
```

URL rules (enforced by `argumentos_de_conexion`, see `docs/staging-database.md`):

- Driver `postgresql+asyncpg://`.
- The **direct** endpoint, without `-pooler`.
- **No query string**: no `sslmode`, no `ssl`, no `channel_binding`. TLS is decided from the
  host and is verified for any non-local host; a connection timeout is always set.

Some tests also need Redis and skip without `REDIS_URL`. Expect each test to be slower than
locally: the cleanup issues about fifty `DELETE`s over the network after every test.

### Resetting the database

The schema is migrated to the current head on every session. If you switch git branches
whose migration heads differ, Alembic cannot walk a revision it does not know. Reset the
database, connected to the `integracion` branch as `neondb_owner`:

```sql
DROP DATABASE cheatsheet_integracion;
CREATE DATABASE cheatsheet_integracion;
GRANT CONNECT ON DATABASE cheatsheet_integracion TO cheatsheet_app;
```

Run these from a connection to another database of the branch (for example `neondb`) of the
`integracion` branch, not the staging branch. The suite never runs against staging.
