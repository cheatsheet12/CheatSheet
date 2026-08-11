# ADR-0002 — Organize the frontend by bounded context, and gate it like the backend

- **Status:** Accepted
- **Date:** 2026-08-10
- **Decided by:** Software Architect
- **Modules affected:** `frontend` (all twelve contexts, from the client side)

---

## Context

The design stage settled the frontend as **one container**: Next.js 14 (App Router) on
Vercel, serving the SPA and acting as a minimal BFF that holds the JWT in HttpOnly
cookies (C4 level 2, containers 1 and 2; ADR-011). It listed roughly seventeen screens
across the twelve bounded contexts, including the token-gated public page for the
external accountant.

What it did **not** settle is how that single application is organized internally. For
the backend there are twelve ADRs with alternatives and trade-offs; for the frontend
there is a container, a framework and a screen list.

That left two problems, both already documented as gaps in `frontend/README.md`:

1. **No structure.** Nothing said where a feature's code belongs, so the first person
   to write a screen would decide it by accident for everyone.
2. **No gates.** `lint-frontend` reported green because it skipped itself while
   `frontend/package.json` was absent. Coverage, strict typing and the architecture
   rules did not reach the frontend at all. The frontend was governed by review alone —
   the exact failure mode [ADR-0001](0001-repository-structure.md) exists to prevent.

The second problem is the urgent one. A structure decision can be revisited; a codebase
that grew for three months without a type checker cannot be retrofitted cheaply.

## Decision

**1. `frontend/src/features/<context>/` mirrors the twelve backend bounded contexts**,
using the same names:

```
frontend/src/
├── app/                        # Next.js routes (App Router) — thin
│   ├── (panel)/…               # authenticated admin panel
│   └── (public)/…              # token-gated accountant access, login
├── features/<context>/         # identity, master_data, …, reference_data
│   ├── api/                    # typed client for that context's endpoints
│   ├── components/
│   ├── hooks/
│   └── index.ts                # the feature's public entry point
├── shared/                     # design system, shared types, cross-feature utilities
└── lib/                        # BFF helpers, auth, fetch wrapper
```

Routes stay thin: a page composes from a feature, it does not hold business logic.

**2. R5 — a feature does not import another feature's internals.** Cross-feature use
goes through the other feature's `index.ts`, and anything genuinely common moves to
`shared/`. `shared/` imports nothing from `features/`.

This is the frontend counterpart of R3/R4, blocked locally by
`.claude/hooks/guard_architecture.py` and scanned in CI. ESLint adds a
`no-restricted-imports` rule that surfaces the alias form in the editor; it cannot see
the relative form, so it is a convenience rather than the gate.

**3. The gates land with this ADR, not later.** `package.json`, `tsconfig.json` with
`strict` plus `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`, ESLint
(including a ban on `any`), Prettier, and Vitest with the same 80% coverage threshold as
the backend. `lint-frontend` now runs lint, format check and `tsc --noEmit` for real.

**4. No application code in this ADR.** No pages, no components, no layout. The scaffold
is the rules and the toolchain; the screens are built by whoever owns each one, already
inside the gates.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **Conventional Next.js** (`app/` + `components/` + `lib/`, organized by route) | What `create-next-app` produces; familiar to anyone; zero explanation needed | Ties structure to URLs rather than to the domain. A screen touching two contexts has no obvious home, `components/` becomes a dumping ground, and there is no boundary to automate — the frontend would stay ungoverned. |
| **By screen group** (the mockup codes: ONB, FAC, COB, AGE, WA, REP, LOG) | Closest to the UX design and the user stories | Introduces a third vocabulary that exists neither in the backend nor in the URLs, so every developer maintains the mapping mentally. Screen groupings also change with UX iterations; bounded contexts do not. |
| **A separate app for the accountant's public page** | Isolates unauthenticated access | Two deployables, two pipelines, two dependency sets for a single token-gated read-only page. A `(public)` route group in the same app gives the same isolation at a fraction of the cost. |
| **Ship the structure now, the gates later** | Smaller PR | This is the alternative the decision exists to reject. "Later" is after the code that needed checking was already written. |

## Consequences

**Positive**

- One vocabulary end to end. The API is organized by bounded context, so the client is
  too: a developer moving between `backend/contexts/billing/` and
  `frontend/src/features/billing/` carries the same mental model.
- The frontend stops being the ungoverned half of the monorepo. `lint-frontend` now
  fails on a real problem instead of passing on an absent one.
- R5 gives the frontend a boundary that can actually be checked, so feature coupling
  surfaces at write time rather than during a refactor.

**Negative / cost we accept**

- Deviates from the layout most Next.js examples use, so newcomers need this ADR.
- Twelve feature directories will stay mostly empty for a while; `identity` and
  `spreadsheet_sync` will carry weight long before `reference_data` does.
- Mirroring the backend invites assuming the two sides map one to one. They do not: a
  screen may compose several contexts. That composition belongs in the route, not in a
  cross-feature import.
- Vitest and the 80% threshold apply from the first test. Until components exist there
  is nothing to cover, so the gate is armed but idle.

## Impact on repository rules

- [x] [`CLAUDE.md`](../../CLAUDE.md) — §2 frontend structure and R5
- [x] [`docs/architecture.md`](../architecture.md) — R5 added to the dependency rules
- [x] [`docs/code-standards.md`](../code-standards.md) — §0 scope table updated: the frontend column is no longer empty
- [x] `.claude/hooks/guard_architecture.py` — R5 for `frontend/src/`
- [x] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — `lint-frontend` runs for real; `architecture` scans the frontend
- [x] [`frontend/README.md`](../../frontend/README.md) — the gap table replaced by what is now enforced

## References

- [ADR-0001](0001-repository-structure.md) — repository layout and rules R1–R4.
- Design documents, Artefacto 2.2: C4 level 2, containers 1 and 2.
- Design documents §20.3: module catalogue with the screens per context.
- Design documents ADR-011: the BFF is the only thing that talks to the API; the JWT
  travels in an HttpOnly cookie the browser JavaScript cannot read.
