# ADR-0003 — Publish `integrations` as an Open Host Service

- **Status:** Proposed
- **Date:** 2026-08-18
- **Decided by:** Software Architect
- **Modules affected:** integrations, identity, spreadsheet_sync, billing, payments, conversational

---

## Context

The Context Map ([`../architecture.md`](../architecture.md) §4) lists twelve dependency
edges. `integrations` (BC4, Generic, root aggregate `ConfiguracionDeIntegracion`) appears
in none of them — neither as upstream nor as downstream. As written, the map says no
context may depend on it and it may depend on nobody, which would make it unreachable.

That gap was harmless while the context was empty. Epic 2 fills it, and it stops being
harmless immediately: the `padron-y-datos-fiscales` unit lives in `identity` and has to
read the company's ARCA credential to query the padrón. There is no sanctioned edge for
that call.

The gap is not a one-off. `ConfiguracionDeIntegracion` is where every external credential
in the system lives, and five contexts need one:

| Context | Needs | Epic |
| --- | --- | --- |
| `identity` | ARCA credential, to validate a CUIT against the padrón | 2 |
| `spreadsheet_sync` | Google Sheets / Excel Online OAuth token | 4 |
| `billing` | ARCA certificate and key, to obtain a CAE | 5 |
| `payments` | MercadoPago access token, to create a payment link | 6 |
| `conversational` | WhatsApp Business token, to send and receive messages | 8 |

Deciding this per-epic, as each consumer appears, means deciding it five times and
discovering on the fifth that the first four disagreed.

Three constraints shape the answer, and all three are already binding:

1. **R3 is enforced by hook and by CI.** No context may import another's `domain/` or
   `infrastructure/`. So the question is not whether a consumer may reach inside
   `integrations` — that is already blocked — but what shape the *permitted* edge takes.
2. **The credentials are secrets at rest.** The DER stores
   `credencial_contenido_cifrado` with its `credencial_algoritmo` alongside, encrypted
   with AES-256-GCM. Whatever crosses the boundary must not be the ciphertext, or every
   consumer learns to decrypt and the key material spreads to five modules.
3. **Revocation has to bite.** HU-E2-01 RN-04 and HU-E2-02 RN-03 require an expired or
   revoked credential to deactivate the integration. Any design that lets a consumer keep
   its own copy fights that requirement.

## Decision

**We will declare `integrations` an Open Host Service.** It publishes one contract in
`contexts/integrations/application/` that **any** context may call; it knows none of its
consumers and calls into none of them. It is the second OHS in the system, after
`observability`.

The detail needed to implement it without asking again:

**1. The published contract is the application layer, and nothing else.** Consumers import
from `cheatsheet.contexts.integrations.application`. `domain/` and `infrastructure/` stay
private — R3 already blocks the alternative, so this adds no new enforcement, only the
edge that makes the permitted import legal.

**2. The dependency is one-directional: consumer → `integrations`.** `integrations` imports
nothing from any context. It receives `empresa_id` from the Shared Kernel like everyone
else, and it is Generic precisely because it has no opinion about who is asking.

**3. Decryption never leaves the context.** The service hands back a *usable* credential —
an authenticated client, or a secret materialised for the duration of one call — never the
ciphertext and never the key. This is the load-bearing reason to make this a service rather
than a library: a library would have to be given the key, which puts the key wherever the
library is imported.

**4. No caching of credentials in the consumer.** A consumer asks each time it needs one.
That is what makes revocation take effect on the next call instead of whenever a cache
happens to expire.

**5. The contract is provider-agnostic.** If ARCA needs something MercadoPago does not, it
goes behind that provider's own port *inside* `integrations`. Nothing provider-specific
enters the published contract.

**6. `observability` and `integrations` are mirror images**, which is worth stating because
the same three letters describe opposite flows. `observability` is an OHS everyone *writes
into*: audit events go one way and nothing comes back. `integrations` is an OHS everyone
*reads from*: a request goes out and a credential comes back. Both are Generic, both depend
on nobody, and neither knows who its clients are.

The Context Map in [`../architecture.md`](../architecture.md) §4 gains one row, added in
this same PR:

| Upstream | Downstream | Type | What flows |
| --- | --- | --- | --- |
| `integrations` | identity, spreadsheet_sync, billing, payments, conversational | OHS | Validated external credentials and connection status |

The downstream column is **informative, not a whitelist**. An Open Host Service that
enumerates its clients is not one; the list records the consumers planned as of epic 2 so
that an unexpected sixth is visible in review, not so that it is forbidden.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **A. Each context stores its own credentials** | No new edge at all. `billing` owns its ARCA certificate outright, with no indirection | Five independent implementations of encryption, key handling and rotation — the one thing that must not be reimplemented five times. `ConfiguracionDeIntegracion` would have no owner, contradicting the DER, and PAN-CFG-INT would have to aggregate five tables to answer HU-E2-05 |
| **B. Put credential access in `shared/`** | Everyone may already import `shared/`, so the Context Map needs no change | `shared/` is a value-object kernel — `EmpresaId`, `UsuarioId`, cross-context values — and R4 forbids it importing from `contexts/`. This would give it a database session, a repository and a cipher, making the kernel the largest module in the system. Worse, the key material would be reachable from every module **by construction**, which is the opposite of constraint 2 |
| **C. One Customer/Supplier edge per consumer** | Matches how `master_data` and `reference_data` are already declared; each edge is explicit | Five rows saying the same sentence, plus a sixth every time a context talks to a new provider. C/S means the supplier accommodates each customer's particular needs; here the contract is byte-for-byte identical for all five consumers, and "identical contract, many clients" is the definition of OHS |
| **D. Publish credentials as domain events; consumers cache** | Fully decoupled — no runtime dependency on `integrations` at all | Broadcasting secrets to every subscriber's storage multiplies the places a leak can originate, and a cached token that has been revoked is worse than no token: the consumer believes it is connected. Directly fights constraint 3 |

## Consequences

**Positive**

- One place stores, encrypts, validates, rotates and revokes every external credential in
  the system. The blast radius of a mistake in that code is large, but the code is one file
  rather than five.
- HU-E2-05's consolidated status is a plain read over one aggregate instead of a fan-out
  across five contexts.
- Key material stays inside one module, so "who can decrypt a credential" has an answer
  short enough to audit.
- Extraction stays possible. An OHS with a provider-agnostic contract is exactly the shape
  a context is in when it is ready to become a separate service.

**Negative / cost we accept**

- Every context that touches an external system now has a **runtime** dependency on
  `integrations`. A bug in the credential service is simultaneously a bug in billing, in
  payments and in the agent.
- The published contract gets expensive to change once five contexts consume it. That is
  not a side effect of the choice — it is what "open host" means, and it is why point 5
  above is a rule and not a preference.
- One more indirection sits between `billing` and the ARCA certificate it needs.

**What becomes harder from now on**

- Adding anything provider-specific to the published contract. The pull to do it will be
  real — the first time WhatsApp's line-quality field has nowhere natural to go — and
  resisting it is a reviewer's job, not a hook's.
- Testing a consumer: it now needs a double for the integrations service. Cheap, because
  the contract is a `Protocol`, but it is one more fixture in five contexts.
- Any future need for `integrations` to call *back* into a context. It has none today and
  must not acquire one: that would turn the one-directional edge into a cycle, and the
  Generic context into a hub that knows about the whole system.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [ ] `backend/.env.example` or `frontend/.env.example`
- [x] **[`docs/architecture.md`](../architecture.md) §4** — the Context Map gains the row
      above. Done in this same PR. `CLAUDE.md` §2.1 needs no change: it already delegates
      "which context may depend on which" to that table.

R1–R5 are unchanged, and `.claude/hooks/guard_architecture.py` needs no change either: it
enforces R3 (nobody reaches into another context's internals), which this decision relies
on rather than relaxes.

## References

- [`docs/architecture.md`](../architecture.md) §3 (the twelve contexts), §4 (Context Map),
  §5 (rules R1–R5)
- [`docs/aidlc/units.md`](../aidlc/units.md) § Épico 2 — the decision was raised while
  mapping the epic's units, and blocks Gate 1 of `mecanismo-de-integraciones`
- [`docs/aidlc/inputs/der.md`](../aidlc/inputs/der.md) § BC4 — `configuracion_de_integracion`
- [`docs/aidlc/inputs/historias-de-usuario.md`](../aidlc/inputs/historias-de-usuario.md) —
  HU-E2-01 RN-04, HU-E2-02 RN-03, HU-E2-05
- [ADR-0001](0001-repository-structure.md) — the layout and the enforced boundaries this
  decision works within
