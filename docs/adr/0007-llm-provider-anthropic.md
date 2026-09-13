# ADR-0007 — Use Anthropic's Claude for every LLM call in the system

- **Status:** Proposed
- **Date:** 2026-09-07
- **Decided by:** Software Architect
- **Modules affected:** spreadsheet_sync, conversational, infra

---

## Context

[`docs/architecture.md`](../architecture.md) declares the port `PortModeloDeLenguaje` and assigns it
to two bounded contexts — `spreadsheet_sync` and `conversational` — and reserves worker 8 for its
calls. **No document in this repository chooses a provider.** ADR-0001 through ADR-0006 do not touch
the subject, and the Etapa 5 design documents name the capability without naming a vendor.

The decision cannot be deferred any longer: `mapeo-asistido` (HU-E3-01) is being implemented now and
is the first consumer. It is also not the important one. The consumer that will define the cost, the
latency and the risk of this choice is **epic 8 — the WhatsApp agent** (HU-E8-01 … HU-E8-05), which
runs a conversation with a real customer, and where a wrong answer books, cancels or charges
something. Choosing for the smaller consumer and discovering the choice is wrong in the larger one is
the failure mode this ADR exists to avoid.

The constraints that actually bind:

- **`CLAUDE.md` §5 governs every LLM call.** Prompts live in versioned files, never inline. Every
  output is validated against a schema before use — a model response is untrusted input, exactly like
  a submitted form. Timeout, token limit and failure handling are mandatory. No action with a real
  effect is triggered from a model output without deterministic validation first.
- **`CLAUDE.md` §3.6 is absolute:** no real personal or tax data reaches a model without
  anonymisation. Our rows are Argentine customers: name, CUIT, phone, address.
- **This is a student project on a budget.** Cost per call matters, and there is no budget for a
  self-hosted GPU.
- **`staging` must be demonstrable without credentials**, like ARCA, WhatsApp and MercadoPago
  already are: the flow has to run end to end on a laptop, and no test may touch the network.

## Decision

> We will call **Anthropic's Claude** through the official `anthropic` Python SDK for every LLM
> feature in the system, behind the existing `PortModeloDeLenguaje` port.

The details needed to implement it without asking again:

**Model.** `claude-opus-5`. One model for both consumers, so there is one prompt style, one schema
discipline and one cost line to reason about. Cost is tuned with `output_config.effort` rather than by
switching models: header mapping is a simple classification and runs at `effort: "low"`, while the
conversational agent of epic 8 will need more and can raise it without changing anything else. **The
model id carries no date suffix** — `claude-opus-5`, never a dated variant.

**Structured output, twice.** The request declares `output_config.format` with the JSON Schema of the
expected answer, so the API constrains the shape. The response is then validated **again** in our own
code before anything reads it. That is not redundancy: `CLAUDE.md` §5 says a model response is
untrusted input, and a guarantee we did not check ourselves is a guarantee we are taking on trust
from a vendor.

**Calling conventions**, all mandatory:

| Qué | Valor | Por qué |
|---|---|---|
| Timeout | explicit, from `Settings` | `CLAUDE.md` §5. The SDK's default is ten minutes; an ingestion screen cannot wait that long |
| `max_tokens` | bounded per use case | A mapping answer is a small JSON object. An unbounded cap turns a malformed answer into a bill |
| Reintentos | SDK `max_retries`, plus our own backoff at the task level | The SDK retries 429 and 5xx; a task that still fails ends in the DLQ of HS-T6 |
| Prompts | versioned files under the context's `infrastructure/prompts/` | `CLAUDE.md` §5. A prompt in the middle of business logic is a prompt nobody reviews |

**What the model is allowed to see.** For `mapeo-asistido`: **column names only, never rows** —
decision D12 of the units map. The sample value HU-E3-02 shows on screen is read from the spreadsheet
and rendered without passing through the model. For epic 8 this ADR sets the rule and not the
mechanism: that context handles a real conversation and will need its own anonymisation decision.

**Failure is a designed state, not an exception.** When the model does not answer — timeout, refusal,
malformed output that fails validation — `mapeo-asistido` degrades to «every column Sin asignar» and
lets the user map by hand. It **never blocks the ingestion**. HU-E3-01 RN-03 already defines that
state for low-confidence columns, so the failure path is a path the screen already draws.

**A simulated adapter, rejected in production.** Same shape as ARCA, WhatsApp and MercadoPago:
`LLM_ADAPTADOR=simulado` returns a deterministic mapping built by string similarity, so the whole
ingestion flow is walkable on a laptop with no API key and no test touches the network. `Settings`
refuses it when `APP_ENV=production`.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **OpenAI (GPT family)** | Comparable quality; the largest ecosystem of examples | No decisive advantage for either consumer, and choosing it would mean the same work with a different vendor. Nothing in the requirements distinguishes them, so the tie is broken by the second-order reasons below |
| **A self-hosted open model** (Llama, Mistral) | No per-call cost; the data never leaves the infrastructure — which would make §3.6 moot | Needs a GPU that this project does not have and cannot rent. `staging` runs on Render's free tier and the database on Neon; adding an inference host is a cost jump of a different order. Revisit if the anonymisation rule ever becomes the binding constraint rather than the budget |
| **No LLM: mapping by string similarity only** | Zero cost, deterministic, no §3.6 problem at all | HU-E3-01 asks for a *confidence level* per column and for recognising headers «en cualquier orden o nombre». Similarity handles `Nombre` → `nombre` and fails on `Razon Soc.`, `Cli`, `Denominación`, which is most of what a real spreadsheet contains. It survives as the **simulated adapter**, which is the right place for it |
| **A managed abstraction layer** (LangChain, LiteLLM) | Swapping providers becomes a config change | `PortModeloDeLenguaje` already is that abstraction, and it is ours. A framework in this position adds a dependency, a second set of failure modes and a layer between us and the provider's error messages, to solve a problem the hexagonal architecture solved in Etapa 5 |

**Why Claude and not OpenAI, said plainly.** On capability the two are close enough that the choice
is not technical. Three second-order reasons decide it: the structured-output path validates against
a supplied JSON Schema, which is exactly the shape `CLAUDE.md` §5 already demands; `effort` gives a
cost lever that does not require maintaining two models and two prompt styles; and the same model
serves both the trivial consumer and the hard one, so epic 8 inherits a decision it can tune rather
than one it has to revisit. **This is a preference, not a proof.** If it turns out wrong, the port is
the seam: one adapter changes and nothing else does.

## Consequences

**Positive**
- The first LLM of the system arrives with its rules already written, instead of a convention that
  each context invents for itself.
- Epic 8 inherits provider, prompt location, schema discipline and failure policy. Its Gate 1 gets to
  be about the agent rather than about infrastructure.
- The whole ingestion flow stays demonstrable with no API key, like the three integrations of epic 2.

**Negative / cost we accept**
- **A per-call cost that grows with use**, and a vendor that can change it. Bounded by `max_tokens`,
  `effort` and by sending headers rather than data — but real.
- **A dependency on somebody else's availability.** Mitigated, not removed: the degradation path
  means an outage costs manual mapping, not a stopped ingestion.
- **Company data leaves the infrastructure**, even reduced to column names. `Facturación mayo`,
  `Deuda cliente` and `Obra social` are business information, and a header can carry a customer's
  name if the spreadsheet was built badly. D12 bounds the exposure; it does not eliminate it.

**What becomes harder from now on**
- Changing provider stops being free the moment the prompts are tuned for one model. The port keeps
  the code change small; the prompt work does not transfer.
- The tests never call the real model, so **a regression in mapping quality is invisible to CI**.
  Whoever tunes the prompt needs a fixture set of real headers and a manual comparison — that is
  epic 8's problem before it is anyone else's, and it is not solved here.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — no change: §5 already governs LLM use, and this ADR obeys it
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [x] [`backend/pyproject.toml`](../../backend/pyproject.toml) — adds the `anthropic` dependency
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — no change: no test calls the model
- [x] `backend/.env.example` — `LLM_ADAPTADOR`, `ANTHROPIC_API_KEY`, `LLM_MODELO`, `LLM_TIMEOUT_SEGUNDOS`, `LLM_MAX_TOKENS`
- [ ] None

## References

- [`docs/architecture.md`](../architecture.md) — `PortModeloDeLenguaje`, worker 8
- [`docs/aidlc/units.md`](../aidlc/units.md) — decisions D11 (this ADR) and D12 (headers only)
- [`docs/aidlc/TODO.md`](../aidlc/TODO.md) §11.1 — the credentials this decision still needs
- HU-E3-01, HU-E3-02 (mapping) and HU-E8-01 … HU-E8-05 (the agent that inherits the decision)
- [ADR-0003](0003-integrations-open-host-service.md) — the simulated-adapter pattern this reuses
