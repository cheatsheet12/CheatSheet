# backend/migrations

Alembic migrations for the single PostgreSQL 16 database (ADR-004).

One shared schema for every company, so **one set of migrations for the whole system**
(ADR-002) — there is no per-company schema to keep in step.

What a migration in this project must not forget:

- **Row-Level Security.** Any new table holding company data carries `empresa_id`
  *and* its RLS policy, in the same migration. A table without a policy is a data leak
  waiting for the first bug in the application layer.
- **Money is `NUMERIC(precision, scale)`**, never `FLOAT` or `DOUBLE PRECISION`.
- **Extensions in use:** `pgvector` (semantic search over FAQs and intents) and
  `btree_gist` (exclusion constraints — the overlap guard for `Turno`).
- **`Comprobante` is Single Table Inheritance** (ADR-010): one table with a type
  discriminator. Attributes that are mandatory only for certain types need conditional
  `CHECK` constraints; the schema alone cannot express it.
- **Never destructive on fiscal data.** The no-delete policy (ADR-007) is a constraint
  on migrations too: mark rows absent, do not drop them.
