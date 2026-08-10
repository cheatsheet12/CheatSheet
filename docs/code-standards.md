# Code standards

Normative reference document. The executable summary is in
[`CLAUDE.md`](../CLAUDE.md); this is the reasoning and the examples.

Each rule states how it is enforced:

| Mark | Meaning |
| --- | --- |
| 🔒 **Hook** | Blocked locally, before the file is ever written |
| ⛔ **CI** | Breaks the pipeline and blocks the PR merge |
| 👁 **Review** | Verified during Pull Request review |

## 0. Scope — this is a monorepo, and coverage is uneven

`backend/` (Python) and `dashboard/` (Next.js) live in the same repository, but the
rules do **not** cover them equally today.

| Rule family | `backend/` | `dashboard/` |
| --- | --- | --- |
| Branch protection, branch naming, commit format, PR flow | 🔒 ⛔ | 🔒 ⛔ |
| Secrets, credential files, `.env` discipline | 🔒 ⛔ | 🔒 ⛔ |
| Top-level structure (ADR required for new root dirs) | 🔒 | 🔒 |
| File hygiene, large files, merge markers | ⛔ | ⛔ |
| Formatting and linting | ⛔ `ruff` | ⛔ ESLint — **inert until `dashboard/package.json` exists** |
| Strict typing | ⛔ `mypy --strict` | ⛔ `tsc --noEmit` — **inert, same reason** |
| Tests and 80% coverage gate | ⛔ `pytest` | ✗ no runner chosen |
| Architecture boundaries R1–R4 | 🔒 ⛔ | ✗ backend only |

Read the right-hand column honestly: **the governance layer is language-agnostic and
already protects the frontend; the quality layer is backend-only.** The
`lint-dashboard` CI job reports green today because it skips itself, not because it
checked anything.

Whoever scaffolds the dashboard scaffolds its gates in the same PR — ESLint, Prettier,
`tsconfig` with `strict: true`, and a test runner wired into CI. Landing the frontend
without them means the frontend is governed by review alone, which is the exact failure
mode this repository exists to prevent.

---

## 1. Principles

1. **Explicit over implicit.** An agent reading this repository six months from now
   does not have today's context. Long names, complete types, named errors.
2. **Fail early and loudly.** A validation error in `spreadsheet_sync` is cheap. The same error
   discovered in `billing` is a wrongly issued invoice filed with the tax authority.
3. **Module boundaries are sacred.** Modules talk to each other through explicit
   interfaces, never by importing each other's internals.
4. **The outside world is hostile.** AFIP goes down, MercadoPago sends the same webhook
   three times, WhatsApp drops the connection, the LLM returns invalid JSON. All of
   that is the normal case, not the exception.
5. **A rule that cannot be automated is not a rule, it is a wish.** That is why every
   rule in this document carries an enforcement mark.

---

## 2. Python

### 2.1 Format and style — 🔒 Hook · ⛔ CI

`ruff` is the single source of truth. Style is not debated in PRs.

```bash
ruff format .        # formatting (replaces black)
ruff check . --fix   # linting
```

Configuration lives in [`pyproject.toml`](../pyproject.toml). Relevant active rules:

| Group | What it catches |
| --- | --- |
| `E`, `W`, `F` | Syntax errors, unused imports, undefined variables |
| `I` | Import ordering |
| `UP` | Outdated Python syntax |
| `B` | Common bugs (mutable default args, overly broad `except`) |
| `S` | **Security (bandit)**: `eval`, `subprocess shell=True`, secrets, string-built SQL |
| `ANN` | Missing type annotations |
| `PT` | pytest antipatterns |
| `C90` | Cyclomatic complexity > 10 |
| `DTZ` | `datetime` without timezone (critical for tax documents) |
| `T20` | `print()` in application code |
| `BLE` | Blindly catching `Exception` |
| `RUF` | ruff-specific rules |

**Silencing rules in bulk is forbidden.** A `# noqa` must be targeted, carry the
specific code, and explain itself:

```python
# GOOD — justified and narrow
result = subprocess.run(cmd, check=True)  # noqa: S603 — cmd is a module constant

# FORBIDDEN
# ruff: noqa
```

### 2.2 Typing — ⛔ CI

`mypy --strict` must pass. Every function carries complete annotations.

```python
# GOOD
def compute_vat(net: Decimal, rate: Decimal) -> Decimal:
    return (net * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# BAD — untyped, float arithmetic, no explicit rounding
def compute_vat(net, rate):
    return net * rate
```

`Any` is forbidden except at the system boundary (parsing external JSON), and there it
is immediately converted into a concrete, validated type.

### 2.3 Size and complexity — ⛔ CI (`C90`) · 👁 Review

| Limit | Value | What to do when exceeded |
| --- | --- | --- |
| Lines per function | 50 | Extract named functions |
| Lines per file | 400 | Split the module |
| Cyclomatic complexity | 10 | Replace `if` chains with a dispatch table or polymorphism |
| Parameters per function | 5 | Group them into a dataclass |
| Nesting levels | 3 | Guard clauses and early returns |

### 2.4 Errors — 👁 Review

Each module defines its own exception hierarchy, with its own root:

```python
# billing/errors.py
class BillingError(Exception):
    """Root of every error raised by the billing module."""

class InvalidCuit(BillingError): ...
class AfipUnavailable(BillingError): ...
class DocumentRejected(BillingError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"AFIP rejected the document [{code}]: {detail}")
        self.code = code
        self.detail = detail
```

Rules:

- **Never** `except Exception: pass`. Swallowing an error in `payments` means losing
  a payment.
- Catch the **most specific** exception possible.
- When re-raising, preserve the cause: `raise BillingError(...) from exc`.
- Error messages **never** contain tokens, keys or personal data.

### 2.5 Money — 🔒 Hook (partial) · 👁 Review

**Absolute rule: `float` never touches money.**

```python
# BAD — this issues documents with miscalculated cents
total = 1000.0 * 1.21          # 1210.0000000000002

# GOOD
from decimal import Decimal, ROUND_HALF_UP
VAT_21 = Decimal("0.21")
CENTS = Decimal("0.01")

net = Decimal("1000.00")
total = (net * (Decimal(1) + VAT_21)).quantize(CENTS, rounding=ROUND_HALF_UP)
```

- Amounts are persisted as `NUMERIC(precision, scale)`, never as `FLOAT`.
- `Decimal` values are built **from strings**: `Decimal("0.1")`, never from a float
  literal.
- Rounding is always explicit, with `quantize` and a declared mode.
- Any function returning an amount declares its currency in the type or the name.

> **Scope of automatic enforcement.** The `guard_edit.py` hook blocks, in `.py` files,
> the most frequent and hardest-to-spot case: a `Decimal` built from a float literal.
> Using `float` for money in general is **not tool-detectable** and is verified during
> PR review. It is the only critical rule in this document that depends on a human —
> pay attention to it.

### 2.6 Logging — 👁 Review

- `print()` is forbidden outside command-line scripts.
- Structured logging, with the module as a field:

```python
logger.info(
    "document_issued",
    extra={"module": "billing", "cae": cae, "cuit_hash": hash_cuit(cuit)},
)
```

- **Never log**: tokens, private keys, full CUITs, phone numbers, or amounts tied to an
  identifiable customer. When tracing is needed, use a hash or the last four digits.
- Levels: `DEBUG` diagnostics, `INFO` business facts, `WARNING` recovered degradation,
  `ERROR` failed operation, `CRITICAL` compromised system.

### 2.7 External services — 👁 Review

Every outbound call (AFIP, MercadoPago, WhatsApp, LLM, remote database) satisfies:

1. **Explicit timeout.** Without one, a slow service hangs the entire system.
2. **Retries with exponential backoff**, only for transient errors (timeout, 5xx, rate
   limit). **Never** retry a 4xx.
3. **Idempotency.** Retries and duplicate webhooks must not charge twice or issue two
   invoices. Use an idempotency key and record what has already been processed.
4. **Handled failure.** Define what happens when the service does not answer: queued?
   rejected? user notified? Never end up in an undefined state.
5. **Webhook signature verification.** An unverified webhook is a payment order from
   a stranger.

```python
# GOOD — minimum acceptable pattern
resp = await client.post(
    url,
    json=payload,
    timeout=httpx.Timeout(10.0, connect=5.0),
    headers={"Idempotency-Key": idempotency_key},
)
```

---

## 3. TypeScript / Next.js (dashboard)

> Applies once the dashboard is scaffolded. The ESLint CI job is already in place and
> activates itself as soon as `dashboard/package.json` appears.

- `tsconfig.json` with `"strict": true`, `noUncheckedIndexedAccess`,
  `noImplicitOverride`.
- `any` and `@ts-ignore` are forbidden. If something cannot be typed, use `unknown` and
  validate it against a schema (zod or equivalent).
- ESLint + Prettier, with the same policy as `ruff`: no style debate in PRs.
- **No business logic in the frontend.** The dashboard renders what the API gives it.
  Taxes, totals, tax validations and payment rules live in the backend, which is the
  only auditable side.
- Sensitive data (tokens, API keys) never reaches the client bundle. No secrets in
  `NEXT_PUBLIC_*` variables.

---

## 4. Testing — ⛔ CI

### 4.1 Rules

- **Minimum coverage 80%**, gated in CI. Lowering the threshold is forbidden.
- **Tests never touch the network.** Not one. Every external integration is replaced by
  a fake or a mock. A test that calls the AFIP homologation environment is not a test,
  it is a source of flaky failures.
- **Tests do not depend on ordering or on the clock.** Date and time are injected,
  never called directly inside business logic.
- **Every bug fix starts with a test that reproduces it.** The test is written first,
  it fails, and only then is the code fixed.

### 4.2 Naming

```python
def test_<what_is_tested>_<under_what_condition>_<expected_outcome>() -> None: ...

# Examples
def test_compute_vat_with_21_percent_rate_rounds_to_two_decimals() -> None: ...
def test_issue_document_with_invalid_cuit_raises_InvalidCuit() -> None: ...
def test_duplicate_mercadopago_webhook_does_not_record_second_payment() -> None: ...
```

Each test is structured **Arrange / Act / Assert**, in that order, separated by blank
lines.

### 4.3 What must always be tested

| Module | Mandatory cases |
| --- | --- |
| `billing` | VAT computation and rounding, CUIT validation, AFIP rejection, retry after outage |
| `payments` | Duplicate webhook, invalid signature, mismatched amount, partial payment |
| `spreadsheet_sync` | Malformed file, missing columns, unexpected types, sync loop, row deleted from the sheet |
| `conversational` | LLM response with invalid JSON, timeout, unauthorized action attempt, prompt injection |
| `scheduling` | Overlapping appointments, recurrence edge cases, timezone handling |

---

## 5. AI / LLM components

The `conversational` context and the AI features of `spreadsheet_sync` are non-deterministic code
real data. They get their own rules:

### 5.1 Prompts

- Prompts live in **versioned files** (`prompts/<name>.md` inside the module), never
  embedded as a long string in the middle of the logic.
- Every prompt is versioned. Changing a prompt changes system behavior, so it gets its
  own commit along with its evaluation.

### 5.2 Outputs

- **Every LLM output is untrusted input.** It is validated against a schema (Pydantic or
  equivalent) before it touches any other part of the system.
- If validation fails: bounded retry, and if it fails again, an explicit error.
  **Never** use a partially parsed output.

```python
# GOOD
raw_response = await llm.complete(prompt)
try:
    data = InvoiceExtraction.model_validate_json(raw_response)
except ValidationError as exc:
    raise InvalidLlmOutput("The model returned JSON that does not match the schema") from exc

# BAD — trusting the model
data = json.loads(raw_response)
issue_invoice(data["cuit"], data["amount"])
```

### 5.3 Actions with real effects

**No irreversible action is triggered straight from an LLM output.** Issuing an invoice,
executing a payment or moving money requires a deterministic validation layer between
the model and the action — and, where appropriate, human confirmation. The LLM
proposes; the code decides.

### 5.4 Data

- **Never send the model** real CUITs, customer names, phone numbers, addresses or
  amounts tied to an identifiable person, without anonymizing them first.
- What is sent to the model is logged auditably (with the data already anonymized),
  because after a tax error you have to be able to reconstruct what happened.

### 5.5 Operations

- Explicit timeout and token limit on every call.
- A monitored cost budget per operation.
- The model and its version come from configuration, never hardcoded. Changing models
  is treated like changing a dependency: it is tested before adoption.
- **Evaluations**: every production prompt has a set of test cases with expected
  outputs. Changing the prompt or the model without running them is forbidden.

---

## 6. Security — 🔒 Hook · ⛔ CI (`gitleaks`)

- No secrets in the code. Blocked by the local hook and by `gitleaks` in CI.
- No `.env`, `*.pem`, `*.key`, `*.p12`, `*.crt` file is ever committed.
- Every user or external-service input is validated before use.
- Database queries are always parameterized. Concatenating SQL is forbidden
  (`ruff S608` catches it).
- AFIP certificates are referenced by path from an environment variable; they are never
  included in the repository.
- When adding an integration: update the `.env.example` of the application that reads it (`backend/` or `dashboard/`) **with the variable empty**, in the same PR.
- Never put a secret behind `NEXT_PUBLIC_*`: Next.js inlines those into the browser bundle.

---

## 7. Architecture decisions (ADR)

Every decision affecting more than one module, or costly to reverse, is documented as an
ADR in [`docs/adr/`](adr/), starting from [`0000-template.md`](adr/0000-template.md).

Requiring an ADR, among others: choosing a framework, a database engine, an
architectural pattern, an LLM provider, a queueing strategy, an authentication scheme,
or creating a new directory at the repository root.

An accepted ADR is never deleted or edited: it is **superseded** by a new one that
references it.

---

## 8. How these rules evolve

These rules change through a PR, like anything else, and the PR must explain the real
problem that motivated the change. **Loosening a rule because the code does not comply
is forbidden**: fix the code.

The legitimate exception is a rule that turned out to be wrong or inapplicable in
practice. That case is documented as an ADR, not as a `# noqa`.
