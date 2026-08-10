## Description

<!-- What does this PR solve? Brief context and motivation. -->

## Module affected

<!-- Tick the module(s) touched. -->

Core: · Supporting: · Generic:

- [ ] `spreadsheet_sync` (Core) — [ ] `billing` (Core) — [ ] `payments` (Core)
- [ ] `scheduling` (Core) — [ ] `conversational` (Core)
- [ ] `master_data` — [ ] `business_config` — [ ] `reporting` — [ ] `reference_data`
- [ ] `identity` — [ ] `integrations` — [ ] `observability`
- [ ] `shared` / `api` / `workers` / `platform`
- [ ] `dashboard`
- [ ] tests / docs / infra

## Type of change

- [ ] `feature/` — new functionality
- [ ] `fix/` — bug fix on `develop`
- [ ] `hotfix/` — urgent fix on `main`

## Definition of Done (required)

Run locally before requesting review:

- [ ] `ruff format --check . && ruff check .` — no errors
- [ ] `mypy .` — no new errors
- [ ] `pytest` — green, and coverage for the touched module **did not drop**
- [ ] The branch follows the `feature/` · `fix/` · `hotfix/` naming and targets the right base
- [ ] Commit messages follow Conventional Commits (`<type>(<module>): <description>`)

Configuration and security:

- [ ] **No hardcoded credentials, tokens or secrets**
- [ ] No real personal or tax data added (not in code, not in tests, not in logs)
- [ ] If an external integration was added, the right **`.env.example` was updated** (`backend/` or `dashboard/`, empty values)
- [ ] Every new external call defines **timeout, retry and idempotency**

Architecture (see [`docs/architecture.md`](../docs/architecture.md)):

- [ ] The `architecture` CI job passes — no boundary crossed that the Context Map forbids
- [ ] New external calls sit behind a **port**, with their adapter in `infrastructure/`
- [ ] The domain stays free of frameworks and I/O
- [ ] Domain terms keep the ubiquitous language (`Comprobante`, `Cobro`, `Turno`, …)

Quality and decisions:

- [ ] Added/updated **tests** for the affected module
- [ ] If this fixes a bug, it includes the **test that reproduces it** first
- [ ] If an architectural decision was made, the **ADR** is written in `docs/adr/`
- [ ] **No rule was disabled** to make CI pass (blanket `# noqa`, `--no-verify`,
      lowering the coverage threshold, excluding files from the linter)

## If this touches AI / LLM code

- [ ] The prompt lives in a versioned file, not embedded in the logic
- [ ] The model output is **validated against a schema** before use
- [ ] No irreversible action is triggered straight from a model output
- [ ] No real personal or tax data is sent to the model without anonymizing
- [ ] The evaluations for the affected prompt were run

---

> Nobody writes directly to `main` or `develop`. Every change lands through a reviewed,
> approved PR, and cannot be merged if CI fails.
>
> The full rules are in [`CLAUDE.md`](../CLAUDE.md) and
> [`docs/code-standards.md`](../docs/code-standards.md).
