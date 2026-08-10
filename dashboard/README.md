# dashboard — Admin panel (Next.js 14)

**Not scaffolded yet.** This directory exists because the repository layout is decided
(ADR-0001) and the structure should be visible before the code arrives.

Planned per the design documents: React 18 / Next.js 14 (App Router) on Vercel, serving
the SPA with SSR/ISR and acting as a minimal BFF — it holds the JWT in HttpOnly cookies
and is the only thing that talks to the API backend (ADR-011).

## Which repository rules already apply here

Everything in [`../CLAUDE.md`](../CLAUDE.md) that is not language-specific applies to
this directory **today**, before a single line of TypeScript exists:

| Rule | Applies | Enforced by |
| --- | --- | --- |
| No writing on `main` / `develop` | Yes | `guard_edit.py` hook |
| Branch naming, commit format, PR flow | Yes | `guard_bash.py` hook + `conventions` CI job |
| No hardcoded secrets, no credential files | Yes | `guard_edit.py` hook + `gitleaks` (CI and pre-commit) |
| No new top-level directories without an ADR | Yes | `guard_edit.py` hook |
| PR template and Definition of Done | Yes | GitHub |
| File hygiene (trailing whitespace, large files, merge markers) | Yes | `pre-commit` |

## Which rules do NOT apply yet — the honest part

| Rule | Status |
| --- | --- |
| ESLint + `tsc --noEmit` | The `lint-dashboard` CI job exists but **skips itself** while `dashboard/package.json` is absent. It reports green without checking anything. |
| Prettier on save | The `format_file.sh` hook is wired for `.ts/.tsx/.js/.jsx/.css/.json` but does nothing until `dashboard/node_modules/.bin/prettier` exists. |
| Test coverage ≥ 80% | Backend only (`pytest`). No frontend test runner is chosen yet. |
| Architecture boundaries (R1–R4) | Backend only. `guard_architecture.py` ignores everything outside `backend/src/cheatsheet/`. The frontend has **no** structural enforcement. |
| Strict typing | The `tsconfig.json` rules in [`../docs/code-standards.md`](../docs/code-standards.md) §3 are written but unenforced until the project exists. |

**Read that as a gap, not as permission.** Until the scaffold lands with its ESLint,
Prettier, `tsconfig` (`strict: true`) and test runner wired into CI, frontend code is
held to the standards by review alone — which is exactly the failure mode this
repository was built to avoid. Scaffolding the dashboard means scaffolding its gates in
the same PR.

## Non-negotiable once it exists

- `"strict": true`, plus `noUncheckedIndexedAccess` and `noImplicitOverride`.
- No `any`, no `@ts-ignore`. Unknown shapes use `unknown` + schema validation.
- **No business logic here.** Taxes, totals, fiscal validation and payment rules live
  in the backend, which is the only auditable side. The panel renders what the API
  returns.
- No secrets in `NEXT_PUBLIC_*` — those are inlined into the browser bundle.
  Variables live in [`.env.example`](./.env.example); anything secret belongs in
  `backend/.env.example` and is read only by the backend.
