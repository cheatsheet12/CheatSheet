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

> **Pending definition.** The final directory layout depends on the architecture, which
> has not been decided yet. Until an approved ADR in [`adr/`](adr/) defines it, the only
> valid root directories are `docs/`, `.github/` and `.claude/`, and this is enforced by
> the `guard_edit.py` hook (see [`../CLAUDE.md`](../CLAUDE.md) §2).

The intended organization is by functional module, mirroring the split of
responsibilities across the team:

```
cheatsheet/
├── intake/            # Data ingestion module (Excel, Google Sheets, AI)
├── billing/           # Electronic invoicing module (AFIP/ARCA)
├── payments/          # Payment collection module (MercadoPago)
├── agent/             # Conversational agent (WhatsApp)
├── dashboard/         # Web admin panel (frontend)
├── reports/           # Reporting and accounting packages module
├── core/              # Orchestration engine and central logic
├── tests/             # Test cases per module
├── docs/              # Internal technical documentation
├── .claude/           # Shared agent configuration and enforcement hooks
└── .github/           # GitHub Actions configuration and PR templates
```

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

Every member working on an external integration has a versioned `.env.example` file in
the repository, listing the required variables without their real values:

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
| Frontend analysis | ESLint and `tsc --noEmit` on the dashboard | Only runs once `dashboard/package.json` exists |
| Automated tests | The test suite for the affected module, with coverage | At least one test fails, or coverage drops below 80% |
| Credential detection | `gitleaks` scanning for hardcoded credentials | A credential pattern is detected in the code |
| Guard integrity | The local hooks still block what they should | A hook stopped blocking, or `.claude/settings.json` became invalid |

**A Pull Request cannot be merged if the pipeline fails.** This rule is automatic and
cannot be bypassed manually.

---

## 7. Responsibilities

| Responsibility | Role |
| ----- | ----- |
| Repository creation and administration | Software Architect |
| CI pipeline configuration and maintenance | Software Architect |
| Auditing compliance with the configuration policies | QA Analyst |
| Managing and distributing environment credentials | Software Architect |
| Updating `.env.example` when integrations are added | Integrations Analyst |
| Periodically verifying that no credential was pushed to the repository | QA Analyst |
