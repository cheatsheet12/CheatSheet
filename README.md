# CheatSheet

Platform for small and medium businesses in Argentina: data ingestion, electronic
invoicing (AFIP/ARCA), payment collection (MercadoPago), a conversational agent
(WhatsApp), accounting reports, and a web admin panel.

> This repository ships with **software configuration management** already in place
> (structure, branching, credential handling, environments and CI). The full plan is in
> [`docs/configuration-management.md`](docs/configuration-management.md).

> **Language policy.** Everything in this repository — code, comments, documentation,
> commit messages, branch names — is written in **English**.

## Before you write a single line

This repository has **code rules that are enforced automatically**, not by convention.
Read them before starting:

| Document | Contents |
| --- | --- |
| [`CLAUDE.md`](CLAUDE.md) | **Repository constitution.** Absolute rules, workflow and Definition of Done. Normative. |
| [`docs/code-standards.md`](docs/code-standards.md) | The detail: typing, errors, money, logging, tests, AI components, security. |
| [`docs/adr/`](docs/adr/) | Architecture decisions and the reasoning behind them. |

Three layers enforce those rules:

1. **Local hooks** (`.claude/hooks/`) — block the write *before* it happens: commits on
   protected branches, hardcoded secrets, unauthorized structure.
2. **`pre-commit`** — runs lint, types and credential detection before every commit.
3. **CI** (`.github/workflows/ci.yml`) — blocks the PR merge if anything fails.

## Structure

> **Pending definition.** The final directory layout depends on the architecture, which
> has not been decided yet. For now the repository only contains the configuration
> infrastructure (CI, templates, documentation and root files).

Planned stacks: **Python** for the backend / system modules and **Next.js** for the web
admin panel. The module split proposed in the plan (intake, billing, payments, agent,
reports, core, dashboard) will materialize once the architecture is decided.

| Directory | Contents |
| --- | --- |
| `docs/` | Internal technical documentation (including the configuration plan) |
| `.github/` | CI (GitHub Actions) and PR template |
| `.claude/` | Shared team configuration and hooks that block rule violations |

## Branching (GitFlow)

- `main` — production / formal delivery. **Nobody writes directly.**
- `develop` — continuous integration. **Nobody writes directly.**
- `feature/[module]-[description]` — new feature → PR to `develop`
- `fix/[module]-[description]` — bug fix → PR to `develop`
- `hotfix/[description]` — production emergency → PR to `main` (then to `develop`)

Every change lands **exclusively through a reviewed Pull Request**; nothing merges if CI
fails.

## Environments

| Environment | Use | External APIs |
| --- | --- | --- |
| `dev` | Each member's local machine | sandbox / homologation |
| `staging` | Integrated team validation (demos) | sandbox / homologation |
| `prod` | Real pilot businesses | production |

**Demos are always run against `staging`.**

## Local setup

```bash
# 1. Copy the environment variable template of each application and fill it in
cp backend/.env.example backend/.env              # NEVER committed
cp dashboard/.env.example dashboard/.env.local    # NEVER committed

# 2. Backend (Python 3.11)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Enable the automatic pre-commit checks (once)
pre-commit install

# 4. Verification cycle — always run before committing
ruff format .          # format
ruff check . --fix     # lint (style, security, complexity)
mypy .                 # types, strict mode
pytest                 # tests + minimum 80% coverage
```

> Real credentials are distributed over a **private, encrypted channel** — never over
> WhatsApp, Discord or plaintext email (see section 4.3 of the plan).

## Continuous integration

The [`.github/workflows/ci.yml`](.github/workflows/ci.yml) workflow runs on every PR to
`develop` or `main`. **No PR merges if any job fails.**

| Job | Checks | Fails when |
| --- | --- | --- |
| `conventions` | Branch name, target branch and commit messages | They do not follow GitFlow or Conventional Commits |
| `lint-python` | `ruff format --check` + `ruff check` | Style, security (bandit), complexity or missing annotations |
| `typecheck` | `mypy --strict` | Untyped or inconsistently typed code |
| `lint-dashboard` | ESLint + `tsc --noEmit` | Only runs once `dashboard/package.json` exists |
| `tests` | `pytest` + coverage | A test fails or coverage drops below 80% |
| `secret-scan` | `gitleaks` | A credential is detected in the code |
| `guards` | Integrity of the local hooks | A hook stopped blocking, or `settings.json` is invalid |

## Pending GitHub-side configuration

These settings live in GitHub and are applied once by the **Software Architect**
(see [`docs/configuration-management.md`](docs/configuration-management.md)):

- **Private** repository under the project's GitHub organization.
- **Branch protection** on `main` and `develop`: forbid direct pushes, require a PR with
  at least one approval, and require CI checks to pass before merging.
- Distribution of `staging` and `prod` credentials over a secure channel.
