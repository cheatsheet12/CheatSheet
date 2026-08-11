# CLAUDE.md — Repository constitution

This file is **normative**. Every agent (Claude Code or otherwise) and every person
writing code in this repository must follow it. Where this file conflicts with any
other style instruction, **this file wins**.

The long-form detail lives in [`docs/code-standards.md`](docs/code-standards.md).
This file is the executable summary: if something here says "forbidden", there is a
hook or a CI job that blocks it.

> **Language policy.** Everything in this repository — code, comments, documentation,
> commit messages, branch names, ADRs, hook output — is written in **English**.
> Spanish is used only when talking to the user.
>
> **One declared exception:** the AI-DLC work products under [`docs/aidlc/`](docs/aidlc/)
> (PRD, requisitos, historias de usuario, diseños, casos de prueba, planes, estado y
> auditoría) are written in **Spanish**, because they are academic deliverables presented
> to the cátedra. This exception covers `docs/aidlc/` and nothing else — not code, not
> commits, not branches, not ADRs, not the workflow rule files themselves. Do not
> "correct" those documents into English.

---

## 0. How work is done here — AI-DLC

Development in this repository follows **AI-DLC**, the workflow defined in
[`.claude/aidlc/AIDLC.md`](.claude/aidlc/AIDLC.md). It is the default path for any feature,
module, fix, refactor or migration — not something the user has to ask for.

@.claude/aidlc/AIDLC.md

Three gates, and nothing else stops the work: the **unit plan** before any code, the
**verification** after implementing, and the **Pull Request**. The analysis that precedes
them (architecture, requirements, user stories, prototypes, standards) is already done and
is consumed, never regenerated.

The workflow governs *how work is planned, approved and documented*. This constitution
governs *what the code may look like*. **Where the two conflict, this file wins** and the
workflow adapts.

---

## 1. What this system is

**CheatSheet** — a platform for small and medium businesses in Argentina.

Twelve bounded contexts. The five **Core** ones carry the competitive advantage and
the risk:

| Context | Responsibility | Dominant risk |
| --- | --- | --- |
| `spreadsheet_sync` | Ingestion: mapping, batch/incremental sync, write-back | Dirty data; sync loops; **never delete** |
| `billing` | Issuance of `Comprobante` with CAE against ARCA | **Legal/tax** — a wrongly issued document is irreversible |
| `payments` | `Cobro` via MercadoPago: links, webhooks, reconciliation | **Money** — duplicate webhooks, mis-rounded amounts |
| `scheduling` | `Turno` and resources: availability, recurrence, overlap | Double booking |
| `conversational` | WhatsApp agent: intent, transcription, escalation | **Non-deterministic LLM** — prompt injection, real consequences |

Supporting: `master_data`, `business_config`, `reporting`, `reference_data`.
Generic: `identity`, `integrations`, `observability`.

Most of the Core touches money, tax obligations or personal data.
**That is why the rules below are strict.**

---

## 2. Architecture and directory structure

**Modular monolith, hexagonal (Ports & Adapters) per bounded context.** Decided in
Etapa 5 (ADR-001 … ADR-012 of the design documents) and materialized by
[ADR-0001](docs/adr/0001-repository-structure.md). Working reference:
[`docs/architecture.md`](docs/architecture.md) — **read it before writing backend code.**

Stack: Python 3.11 / FastAPI / Uvicorn · PostgreSQL 16 (`pgvector`, `btree_gist`) ·
Redis 7 · 5 specialised Celery workers + Beat · Cloudflare R2 · Next.js 14.

```
backend/src/cheatsheet/
├── contexts/<context>/
│   ├── domain/           # aggregates, entities, value objects, domain events
│   ├── application/      # Application Services (one use case each) + ports.py
│   └── infrastructure/   # adapters: repositories, external clients, routers, tasks
├── shared/               # Shared Kernel: tenant_id, user_id, cross-context value objects
├── api/                  # FastAPI composition root
├── workers/              # the 5 Celery workers + Beat
└── platform/             # settings, database session, Redis, storage, telemetry
frontend/src/
├── app/                  # Next.js routes (App Router) — thin, they compose features
│   ├── (panel)/          # authenticated admin panel
│   └── (public)/         # login, token-gated accountant access
├── features/<context>/   # the same twelve names as the backend
│   ├── api/ components/ hooks/     # internal
│   └── index.ts          # the feature's PUBLIC entry point
├── shared/               # design system, common types, cross-feature utilities
└── lib/                  # BFF helpers, auth, fetch wrapper
```

The frontend mirrors the backend contexts on purpose ([ADR-0002](docs/adr/0002-frontend-structure.md)):
the API is organized by bounded context, so the client is too, and both sides share one
vocabulary.

The twelve contexts: `identity` · `master_data` · `business_config` · `integrations` ·
`spreadsheet_sync` · `billing` · `payments` · `scheduling` · `conversational` ·
`observability` · `reporting` · `reference_data`.

**Do not create new directories at the repository root.** Blocked by hook. A new one
needs an approved ADR (start from `docs/adr/0000-template.md`), then
`ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`.

### 2.1 Dependency rules — enforced, not reviewed

Dependencies point inwards only: `infrastructure → application → domain`.

| # | Rule |
| --- | --- |
| **R1** | `domain/` imports nothing from `application/`, `infrastructure/`, or any framework |
| **R2** | `application/` imports nothing from `infrastructure/` |
| **R3** | No module imports another context's `domain/` or `infrastructure/` — contexts talk through `application/` or domain events |
| **R4** | `shared/` imports nothing from `contexts/` |
| **R5** | *(frontend)* a feature never imports another feature's internals — only its `index.ts`; `shared/` imports no feature |

Blocked locally by `.claude/hooks/guard_architecture.py`, and on merge by the
`architecture` CI job. Which context may depend on which is in the Context Map
([`docs/architecture.md`](docs/architecture.md) §4).

### 2.2 Naming

Everything is in English — layers, technical modules, comments, tests — **except the
ubiquitous language of the domain, which stays in Spanish, without accents**:

```python
# backend/src/cheatsheet/contexts/billing/domain/comprobante.py
class Comprobante:                      # a Comprobante is not an "invoice"
    def emitir(self, punto_de_venta: PuntoDeVenta) -> CAE: ...
```

`Comprobante`, `Cobro`, `Turno`, `Mapeo`, `CUIT`, `CAE`, `CondicionIVA` are the
business's own terms and Argentine fiscal terms. Translating them breaks traceability
with the design documents and with ARCA.

### 2.3 What lives at the root, and what lives in a package

This is a monorepo. The rule is about **scope, not language**:

> The root holds what governs the **whole repository**.
> A package's own configuration lives **inside that package**.

| At the root | Why |
| --- | --- |
| `pyproject.toml` | Configures `ruff`, `mypy`, `pytest` and coverage for **every** Python file in the repo — including the guards in `.claude/hooks/`, which are not backend code. One set of rules for all Python. |
| `requirements-dev.txt` | Pins the tooling that checks the whole repo (`ruff`, `mypy`, `pytest`, `pre-commit`). Not application dependencies. |
| `.gitignore`, `.gitleaks.toml`, `.pre-commit-config.yaml` | Repo-wide policy. |
| `CLAUDE.md`, `README.md`, `docs/`, `.claude/`, `.github/` | Govern the repository. |

| Inside its package | Why |
| --- | --- |
| `backend/pyproject.toml` | Packaging and **application** dependencies. Deliberately has no `[tool.ruff]` — ruff and mypy walk past it to the root config. |
| `backend/.env.example`, `frontend/.env.example` | An env file exists to be copied next to the process that reads it. These are two separately deployed processes. |
| `frontend/package.json`, `tsconfig.json`, ESLint/Prettier config | Configure one application. |

Creating an app-scoped config file at the root is blocked by hook. The test: **if it
only affects one of `backend/` or `frontend/`, it does not go at the root.**

---

## 3. Absolute rules (blocked by hook or CI)

1. **Never write on `main` or `develop`.** Every change is born on
   `feature/…`, `fix/…` or `hotfix/…` and lands through a reviewed Pull Request.
2. **Never hardcode credentials.** No key, token, secret, real CUIT, certificate or
   password in the code. Everything goes through environment variables.
3. **Never commit `.env`, `*.pem`, `*.key`, `*.p12`, `*.crt`.**
4. **Never use `--no-verify`, `--force` on protected branches, or bypass CI.**
5. **Never use `float` for money.** Always `Decimal`, everywhere in the system.
6. **Never send real personal or tax data to an LLM** without anonymizing it first.
7. **Never create new root directories** without an approved ADR (see §2).

When a hook blocks you, **the block message states exactly what to do**. Do not look
for ways around it: fix the cause.

---

## 4. Required workflow

```bash
# 1. Always start from an up-to-date develop
git checkout develop && git pull

# 2. Branch with a valid name (validated by hook and by CI)
git checkout -b feature/billing-cuit-validation

# 3. Work. Before committing:
ruff format . && ruff check . && mypy . && pytest

# 4. Commit in Conventional Commits format (see §6)
git commit -m "feat(billing): validate CUIT before issuing a document"

# 5. PR to develop, filling in the template
```

Branch naming — the hook rejects anything else:

| Type | Pattern | Target |
| --- | --- | --- |
| Feature | `feature/<module>-<kebab-description>` | `develop` |
| Bug fix | `fix/<module>-<kebab-description>` | `develop` |
| Production emergency | `hotfix/<kebab-description>` | `main` + `develop` |

---

## 5. Code standards — summary

**Python 3.11+**

- Typing is **mandatory and complete**. `mypy --strict` must pass. No `Any` without a
  justified `# type: ignore[code]` and a comment explaining why.
- `ruff` is the single source of truth for style. Line length 100.
- Functions ≤ 50 lines, files ≤ 400 lines, cyclomatic complexity ≤ 10.
  If it does not fit, the design is wrong.
- **Module-specific exceptions**, never `except Exception: pass`.
- **`Decimal` for money.** Explicit rounding with `quantize` and `ROUND_HALF_UP`.
- **Structured logging**, never `print()`. Never log secrets or personal data.
- Every call to an external service: **explicit timeout + retry with backoff +
  failure handling**. No exceptions.

**TypeScript / Next.js (frontend)**

- `strict: true` in `tsconfig.json`. `any` and `@ts-ignore` are forbidden.
- Typed functional components. No business logic in the frontend: the panel
  consumes the API, it does not compute taxes.

**Testing**

- Every new module ships with tests. Minimum coverage **80%**, gated in CI.
- Tests **never touch the network**. External integrations (AFIP, MercadoPago,
  WhatsApp, LLM) are always mocked or faked.
- Every fixed bug starts with a test that reproduces it.

**AI / LLM**

- Prompts live in versioned files, never embedded in the middle of business logic.
- Every LLM output is **validated against a schema** before use. A model response is
  untrusted input, exactly like a user-submitted form.
- No action with real effect (issuing an invoice, charging, moving money) is triggered
  straight from an LLM output without deterministic validation first.
- Timeout, token limit and failure handling are mandatory on every call.

Full detail, with right-and-wrong examples:
[`docs/code-standards.md`](docs/code-standards.md).

---

## 6. Commits

**Conventional Commits** format, in English, imperative mood, no trailing period:

```
<type>(<module>): <what this commit does>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`.
Modules: the twelve context names (§2), plus `frontend` and `infra`.

```
GOOD  feat(payments): handle duplicate MercadoPago webhooks
GOOD  fix(billing): round VAT with ROUND_HALF_UP
BAD   various changes
BAD   WIP
```

---

## 7. Definition of Done

A change is **not finished** until:

- [ ] `ruff format --check . && ruff check .` passes
- [ ] `mypy .` passes with no new errors
- [ ] `pytest` passes and coverage for the touched module did not drop
- [ ] No secrets or personal data in the diff (`gitleaks` green)
- [ ] If an external integration was added: the right `.env.example` updated (`backend/` or `frontend/`)
- [ ] If an architectural decision was made: ADR written in `docs/adr/`
- [ ] The PR template is filled in

---

## 8. Rules for agents specifically

- **Do not invent structure.** If you do not know where a file goes, ask or write an
  ADR. A misplaced new directory propagates into all downstream work.
- **Do not widen the scope.** Do what was asked. If you spot another problem, report
  it; do not fix it in the same PR.
- **Do not disable rules to make CI pass.** No blanket `# noqa`, no `--no-verify`, no
  lowering the coverage threshold, no excluding files from the linter. Fix the code.
- **Read before writing.** Before creating a helper, search for an existing one.
- **Report honestly.** If tests fail, say so with the output. Never declare "done"
  without having run the checks in §7.

### Emergency escape hatch

The hooks can be bypassed with `CHEATSHEET_UNSAFE=1` in the environment. It exists for
repository bootstrap and for genuine production emergencies.
**Using it requires explicit authorization from the person in charge and must be noted
in the PR.** An agent never turns it on by itself.

---

## 9. Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install

# Verification cycle (always run before committing)
ruff format .          # format
ruff check . --fix     # lint with autofix
mypy .                 # types
pytest                 # tests + coverage

# Verify the local guards still block what they should
bash .claude/hooks/test_guards.sh
```
