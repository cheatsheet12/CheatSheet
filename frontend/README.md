# frontend — Admin panel (Next.js 14)

The whole frontend lives here: one Next.js 14 application (App Router) deployed on
Vercel, serving the SPA and acting as the BFF that holds the JWT in HttpOnly cookies.
It is containers 1 and 2 of the C4 level 2 diagram — the browser runtime and the Vercel
deployable are the same app. There is no second frontend.

Structure and rules: [ADR-0002](../docs/adr/0002-frontend-structure.md).

## Structure

```
src/
├── app/                  # routes (App Router) — thin, they compose features
│   ├── (panel)/          # authenticated admin panel
│   └── (public)/         # login, token-gated accountant access
├── features/<context>/   # the same twelve names as the backend
│   ├── api/              # typed client for that context's endpoints
│   ├── components/
│   ├── hooks/
│   └── index.ts          # PUBLIC entry point — the only thing other features may import
├── shared/               # design system, common types, cross-feature utilities
└── lib/                  # BFF helpers, auth, fetch wrapper
```

The twelve features mirror the backend bounded contexts on purpose: the API is organized
by context, so the client is too, and both sides share one vocabulary. `identity`,
`master_data`, `business_config`, `integrations`, `spreadsheet_sync`, `billing`,
`payments`, `scheduling`, `conversational`, `observability`, `reporting`,
`reference_data`.

**Screens** (design documents §20.3): ONB · CFG · DM · ING-CARGA · ING-MAPEO · FAC ·
COB-LIST · COB-DET · AGE · WA-CONV · WA-CONFIG · LOG-LIST · LOG-DET · REP-DASH ·
REP-CONFIG · REP-IVA · DSH, plus the public PAN-REP pages for the external accountant.

## R5 — the one boundary

> A feature never imports another feature's internals. Cross-feature use goes through
> the other feature's `index.ts`. `shared/` imports no feature.

```ts
// BLOCKED — reaching into another feature
import { useCobro } from "@/features/payments/hooks/useCobro";

// ALLOWED — the public entry point
import { useCobro } from "@/features/payments";
```

A screen that composes several contexts does that **in the route**, not through a
cross-feature import. If code is genuinely common, it belongs in `@/shared`.

Enforced by `.claude/hooks/guard_architecture.py` (blocks the write), the `architecture`
CI job, and an ESLint `no-restricted-imports` rule so it also surfaces in the editor.

## Gates

Every one of these blocks the merge. `npm run <script>`:

| Script | What it enforces |
| --- | --- |
| `format:check` | Prettier. Markdown is excluded — prose keeps its hand-authored line breaks. |
| `lint` | ESLint with `--max-warnings=0`. `any` is banned, so is `console.log`, so are cross-feature imports. |
| `typecheck` | `tsc --noEmit` with `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noUnusedLocals`. |
| `test:coverage` | Vitest, 80% threshold — the same as the backend. |

Loosening any of them is an ADR, not a convenience. They are the frontend equivalent of
`ruff` + `mypy --strict` + the backend coverage gate.

The coverage threshold is armed but idle: there is nothing to measure until the first
component exists.

## Non-negotiable

- **No business logic here.** Taxes, totals, fiscal validation and payment rules live in
  the backend, which is the only auditable side. The panel renders what the API returns.
- **No secrets in `NEXT_PUBLIC_*`** — Next.js inlines those into the browser bundle.
  Variables live in [`.env.example`](./.env.example); anything secret belongs in
  `backend/.env.example` and is read only by the backend.
- **The JWT is never read from client JavaScript.** It travels in an HttpOnly cookie
  issued by the BFF, which is the only thing that talks to the API (design ADR-011).

## Local setup

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```
