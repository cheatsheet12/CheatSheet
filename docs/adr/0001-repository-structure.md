# ADR-0001 — Lay the repository out by bounded context, with enforced boundaries

- **Status:** Accepted
- **Date:** 2026-08-10
- **Decided by:** Software Architect
- **Modules affected:** all

---

## Context

The design stage (Etapa 5) settled the architecture: a **modular monolith** with
**hexagonal (Ports & Adapters)** structure per bounded context, twelve contexts,
FastAPI + PostgreSQL 16 + Redis + five specialised Celery workers, and a Next.js 14
panel. Those decisions are recorded as ADR-001 … ADR-012 in the design documents and
condensed in [`../architecture.md`](../architecture.md).

What the design stage did **not** settle is how that architecture maps onto
directories and Python packages, and how the boundaries are kept from eroding.

The second half matters more than it looks. ADR-001 lists, under its negative
consequences:

> Discipline required: the boundaries between modules only hold if the team respects
> the dependency rules (internals of another context are not imported; communication
> between contexts goes through interfaces or events). **This must be verified in code
> review.**

Code review does not catch import violations reliably. It catches them on a good day,
from a reviewer who happens to remember the Context Map. Six people over six months,
with agents writing a share of the code, will erode those boundaries — and the day the
monolith stops being modular is the day extracting a context becomes impossible.

The repository already commits `main` and `develop` protection, secret scanning and
strict typing to hooks plus CI rather than convention. The architecture boundaries
deserve the same treatment.

## Decision

**1. Two top-level stacks.** `backend/` (Python) and `dashboard/` (Next.js). They are
different runtimes with different tooling; a shared root would force one to bend.

**2. One `src/` package for the backend**, so tests import the installed package
rather than relative paths:

```
backend/src/cheatsheet/
├── contexts/<context>/{domain,application,infrastructure}/   # the 12 bounded contexts
├── shared/        # Shared Kernel: tenant_id, user_id, cross-context value objects
├── api/           # FastAPI composition root: app, routers, middlewares, webhooks
├── workers/       # the 5 Celery workers + Beat
└── platform/      # settings, database session, Redis, object storage, telemetry
```

`api/`, `workers/` and `platform/` are the composition root: they are allowed to
import adapters in order to wire them, which is exactly what a composition root is
for.

**3. Context directories are named in English; the ubiquitous language stays in
Spanish.** `contexts/billing/domain/comprobante.py` defines `class Comprobante`.
Structure is technical vocabulary, so English; `Comprobante`, `CAE`, `CUIT`,
`CondicionIVA`, `PuntoDeVenta` are the business's own terms and Argentine fiscal
terms. Accents are dropped for identifier safety.

**4. The four dependency rules are enforced automatically**, by
`.claude/hooks/guard_architecture.py` locally and the `architecture` CI job on merge:

| # | Rule |
| --- | --- |
| R1 | `domain/` imports nothing from `application/`, `infrastructure/`, or any framework |
| R2 | `application/` imports nothing from `infrastructure/` |
| R3 | No module imports another context's `domain/` or `infrastructure/` |
| R4 | `shared/` imports nothing from `contexts/` |

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **Layout by technical layer** (`domain/`, `services/`, `repositories/` at the top, contexts inside) | Familiar to anyone coming from layered MVC | Puts the layer first and the business second. Everything about one context ends up scattered across four trees, which is precisely what makes extracting a context later impossible. Contradicts DDD. |
| **Flat `cheatsheet/<context>/`, no `contexts/` folder** | One level shallower | Mixes bounded contexts with the technical packages (`api`, `workers`, `platform`) in the same namespace, so "is this a context?" stops being answerable from the path — and the enforcement rules key off the path. |
| **No `src/` layout** (package at `backend/cheatsheet/`) | Slightly shorter paths | Lets tests import the local directory instead of the installed package, so packaging errors surface in production rather than in CI. |
| **Boundaries by convention, checked in review** (what the design ADR-001 assumed) | Zero tooling to build or maintain | This is the alternative the decision exists to reject. It relies on every reviewer remembering the Context Map. The failure is silent and only becomes visible once it is expensive. |
| **`import-linter` instead of a custom hook** | Off-the-shelf, declarative contracts | Runs at CI only, so a violation is discovered after the code is written. The custom hook blocks the write and explains the specific rule with the allowed alternative, which is what an agent needs to self-correct. Reconsider if the rules grow beyond these four. |

## Consequences

**Positive**

- Everything about one bounded context lives in one directory: its domain, its ports,
  its adapters, its tests. Extracting it into a service is a move, not an excavation.
- The boundaries cannot erode silently. An agent that tries to import across a
  boundary is stopped and told which import is allowed instead.
- The layout is legible without reading documentation: the path states the context and
  the layer.

**Negative / cost we accept**

- Deep paths (`backend/src/cheatsheet/contexts/spreadsheet_sync/infrastructure/...`).
- The enforcement rules must be kept in step with the layout. If a context is renamed
  or the tree moves, `guard_architecture.py` moves with it.
- The rules are import-based, so they catch structural coupling, not semantic
  coupling. A context can still know too much about another through a badly shaped
  application interface. That remains a review concern.
- Mixed-language identifiers (`class Comprobante` inside `billing/domain/`) look odd
  at first read. The alternative — translating fiscal terms — was judged worse.

## Impact on repository rules

- [x] [`CLAUDE.md`](../../CLAUDE.md) — §2 replaced with the real structure and the four rules
- [x] [`docs/code-standards.md`](../code-standards.md) — naming rule for domain terms
- [x] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py` — `backend`, `dashboard` added
- [x] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — `architecture` job added
- [x] `.env.example` split into [`backend/`](../../backend/.env.example) and [`dashboard/`](../../dashboard/.env.example)
- [x] New: [`docs/architecture.md`](../architecture.md), `.claude/hooks/guard_architecture.py`

## References

- Design documents, Anexo 4 / Artefacto 2.1–2.4: ADR-001 … ADR-012, C4 levels 1 and 2,
  Context Map, applied design patterns.
- Design documents §20.3: module catalogue and technical view per module.
