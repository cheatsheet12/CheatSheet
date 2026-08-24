# Software configuration management

## 1. Version control tool

The team uses **Git** as its distributed version control system, with **GitHub** as the
centralized hosting platform for the repository.

| Item | Definition |
| ----- | ----- |
| **Platform** | GitHub |
| **Repository type** | Private, under a GitHub organization created for the project |
| **Access** | Every team member has collaborator access with write permission on working branches |
| **Administration owner** | Software Architect |

---

## 2. Repository structure

A **monorepo** holding both applications, organised by bounded context per
[ADR-0001](adr/0001-repository-structure.md). The reasoning is in
[`architecture.md`](architecture.md); the rules are in [`../CLAUDE.md`](../CLAUDE.md) §2.

```
cheatsheet/
├── backend/                    # Python 3.11 / FastAPI — API and workers
│   ├── src/cheatsheet/
│   │   ├── contexts/<context>/{domain,application,infrastructure}/
│   │   ├── shared/             # Shared Kernel
│   │   ├── api/                # FastAPI composition root
│   │   ├── workers/            # 5 Celery workers + Beat
│   │   └── platform/           # settings, database, Redis, storage, telemetry
│   ├── migrations/             # Alembic
│   ├── tests/
│   ├── pyproject.toml          # packaging + application dependencies
│   └── .env.example
├── frontend/                  # Next.js 14 admin panel
│   └── .env.example
├── docs/                       # Internal technical documentation, ADRs
├── .claude/                    # Shared agent configuration and enforcement hooks
├── .github/                    # GitHub Actions and PR template
├── pyproject.toml              # ruff / mypy / pytest for ALL Python in the repo
├── requirements-dev.txt        # repo-wide tooling, pinned
└── .pre-commit-config.yaml
```

The twelve contexts: `identity`, `master_data`, `business_config`, `integrations`,
`spreadsheet_sync`, `billing`, `payments`, `scheduling`, `conversational`,
`observability`, `reporting`, `reference_data`.

**Root versus package.** The root holds what governs the whole repository (tooling
configuration, repo-wide policy, documentation); an application's own configuration
lives inside its directory. Both rules — no new root directories, and no app-scoped
config file at the root — are enforced by the `guard_edit.py` hook.

---

## 3. Branching strategy

The team adopts **GitFlow**, with the following permanent and temporary branches:

### 3.1 Permanent branches

| Branch | Purpose | Who may write directly |
| ----- | ----- | ----- |
| `main` | Production or formally delivered code. Represents the stable version of the system. | Nobody — only accepts merges from `develop` through an approved Pull Request |
| `develop` | Continuous integration branch. Holds the integrated, working output of the current sprint. | Nobody — only accepts merges from working branches through an approved Pull Request |

### 3.2 Temporary branches

| Type | Naming | Example | Created when | Deleted when |
| ----- | ----- | ----- | ----- | ----- |
| New feature | `feature/[module]-[description]` | `feature/intake-semantic-mapping` | A new task starts | Merged into `develop` |
| Bug fix | `fix/[module]-[description]` | `fix/billing-cuit-validation` | A bug is found in `develop` | Merged into `develop` |
| Production emergency | `hotfix/[description]` | `hotfix/mercadopago-webhook-error` | Only on critical production failures | Merged into `main` and `develop` |

**Absolute rule:** no team member writes code directly on `main` or `develop`. Every
change is born on a working branch and is incorporated exclusively through a reviewed
Pull Request.

---

## 4. Credential and environment variable management

The system interacts with external services that require sensitive credentials:
AFIP/ARCA, MercadoPago, WhatsApp Business and AI models. Mishandling these credentials
is a critical legal and security risk.

### 4.1 Security rules

* **Absolute prohibition on credentials in code:** no key, token, secret or password may
  appear written directly in the source (*hardcoded*). Any Pull Request containing
  credentials is rejected immediately.
* **`.env` file excluded from the repository:** the repository `.gitignore` explicitly
  includes `.env` and every variant (`*.env`, `.env.local`, `.env.production`) to prevent
  accidental upload.
* **Per-environment variables:** each environment (development, testing, production) has
  its own set of environment variables, managed separately and never shared across
  environments.

### 4.2 Environment variable structure

Each application carries its own versioned `.env.example`, listing the required
variables without their real values: `backend/.env.example` for the API and the
workers, and `frontend/.env.example` for the panel. An env file lives next to the
process that reads it, and these are two separately deployed processes.

The backend template covers:

```bash
# AFIP/ARCA integration
AFIP_CUIT=
AFIP_CERT_PATH=
AFIP_KEY_PATH=
AFIP_WSAA_URL=
AFIP_WSFE_URL=

# MercadoPago integration
MP_ACCESS_TOKEN=
MP_WEBHOOK_SECRET=

# WhatsApp Business integration
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
WHATSAPP_WEBHOOK_VERIFY_TOKEN=

# AI models
AI_API_KEY=
AI_MODEL=

# Database
DATABASE_URL=
```

### 4.3 Secure credential distribution

Real credentials for each environment are shared among authorized members over a private,
encrypted channel — **never over WhatsApp, Discord or plaintext email**. The Software
Architect is responsible for managing and distributing the testing and production
environment credentials.

---

## 5. Environment definitions

The project runs three clearly separated environments, each with a specific purpose and
an independent configuration:

| Environment | Purpose | External integrations | Data |
| ----- | ----- | ----- | ----- |
| **Development** (`dev`) | Each member's day-to-day work on their local machine | APIs in sandbox/homologation mode (AFIP homologation, MercadoPago sandbox, WhatsApp test number, AI development account) | Synthetic data generated by the team |
| **Testing** (`staging`) | Integrated system validation before each delivery or demo. Shared team environment. | APIs in sandbox/homologation mode | Controlled test data owned by the QA Analyst |
| **Production** (`prod`) | System running with real pilot businesses | APIs in production mode (AFIP production, MercadoPago production, real WhatsApp number) | Real data — restricted access |

**Demo rule:** every demonstration is run against the **testing (staging)** environment,
never against a member's local development environment nor against production.

---

## 6. Continuous integration (CI)

The repository has a continuous integration pipeline configured in **GitHub Actions**
that runs automatically on every Pull Request targeting `develop` or `main`.

| Check | Description | Fails when |
| ----- | ----- | ----- |
| Repository conventions | Branch name, target branch and commit message format | They do not follow GitFlow or Conventional Commits |
| Static analysis | `ruff format --check` and `ruff check` over the PR code | The code does not meet the defined style, security or complexity rules |
| Type checking | `mypy --strict` over the whole codebase | There is untyped code or inconsistent types |
| Frontend gates | Prettier, ESLint, `tsc --noEmit` and Vitest on `frontend/` | Formatting, lint, types or the 80% coverage threshold fail |
| Automated tests | The test suite for the affected module, with coverage | At least one test fails, or coverage drops below 80% |
| Credential detection | `gitleaks` scanning for hardcoded credentials | A credential pattern is detected in the code |
| Architecture boundaries | Rules R1–R5 across both applications | A module reaches across a boundary the Context Map forbids |
| Guard integrity | The local hooks still block what they should | A hook stopped blocking, or `.claude/settings.json` became invalid |

**A Pull Request cannot be merged if the pipeline fails.** This rule is automatic and
cannot be bypassed manually.

---

## 6 bis. Continuous deployment (CD) to staging

Since **2026-08-24**, every push to `develop` updates the testing (`staging`) environment on its own
— provided the push is not broken. The pipeline is the `deploy-staging` job of
`.github/workflows/ci.yml`; the decision and its alternatives are [ADR-0006](adr/0006-staging-hosting-render.md), and the operating
manual is [`staging-deployment.md`](staging-deployment.md).

| Step | What it does | Stops the release when |
| ----- | ----- | ----- |
| Trigger | A push to `develop`, with `needs:` on all eight gates above | Any gate is red — the job never starts |
| Migrations | `alembic upgrade head` with the database **owner** role | A migration fails |
| Tenant barrier | `backend/scripts/verify_rls.py` against the live database | The application role can read across companies, or a policy is missing |
| Release | Calls one Render deploy hook per web service | The hook is rejected |
| Health | Polls `/health` until it answers 200 | The new version does not become healthy within ten minutes |

**The deploy is a consequence of CI passing, not of the push.** Auto-deploy is disabled on every
Render service on purpose: the platform does not know whether the pipeline was green, so leaving its
default on would publish red builds.

**`main` deploys nothing.** Production is a separate decision, with a different data profile and a
different credential set.

---

## 7. Responsibilities

| Responsibility | Role |
| ----- | ----- |
| Repository creation and administration | Software Architect |
| CI pipeline configuration and maintenance | Software Architect |
| Staging provisioning and the CD pipeline | Software Architect |
| Auditing compliance with the configuration policies | QA Analyst |
| Managing and distributing environment credentials | Software Architect |
| Updating the relevant `.env.example` when integrations are added | Integrations Analyst |
| Periodically verifying that no credential was pushed to the repository | QA Analyst |
