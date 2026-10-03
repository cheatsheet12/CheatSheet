# ADR-0011 — Share the outbound WhatsApp channel through the composition root

- **Status:** Proposed
- **Date:** 2026-10-03
- **Decided by:** Software Architect
- **Modules affected:** conversational, payments, scheduling

---

## Context

Three contexts send WhatsApp messages to a company's customers:

| Context | Message | Story | Adapter today |
| --- | --- | --- | --- |
| `conversational` | Agent replies and operator messages | HS-T2, HU-E9-02 | `MensajeriaWhatsApp` (real Cloud API client) |
| `payments` | Payment reminders of the escalation chain | HS-T3 | `EnvioPorConsola` (log only, refuses production) |
| `scheduling` | Booking, cancellation and rescheduling notices | HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04 | `AvisoPorConsola` (log only, refuses production) |

Epic 8 built the only real client, `MensajeriaWhatsApp`, inside
`contexts/conversational/infrastructure/canal.py`, and left a note there and in pending #11 of
the epic: the other two contexts "reach it through the composition root". That intent was never
recorded in the Context Map ([`../architecture.md`](../architecture.md) §4), which has no edge
from `conversational` to `payments` or to `scheduling` — the only `conversational` row goes the
other way (the agent calls scheduling, payments and billing use cases).

Replacing the two console doubles now (unit `canal-real-de-whatsapp`, Etapa 6) makes `payments`
and `scheduling` depend, at runtime, on a piece of `conversational`. The workflow requires an
ADR before Gate 1 closes for any dependency the Context Map does not allow, so the shape of
that dependency has to be decided — and written down — before the code exists.

Constraints already binding:

1. **R3 is enforced by hook and CI.** `payments` and `scheduling` cannot import
   `conversational/infrastructure/`. Importing `conversational/application/` would be legal only
   with a Context Map edge.
2. **ADR-008 (design stage): one Anti-Corruption Layer per provider.** Meta's Cloud API must not
   be re-implemented in three contexts.
3. **ADR-0003:** credentials (token, `phone_number_id`, `waba_id`) live in `integrations` and are
   read per call, never cached by a consumer.
4. **Each context already declared its own outbound port** — `PortEnvioDeRecordatorio`
   (`payments`) and `PortNotificadorDeTurnos` (`scheduling`) — and both are consumer-owned
   contracts that do not mention WhatsApp's types.

## Decision

**We will keep the single Meta client in `conversational` and hand it to `payments` and
`scheduling` only through the composition root (`backend/src/cheatsheet/api/`).** No context
imports another to send a message.

The detail needed to implement it without asking again:

1. **Each consumer's infrastructure declares the narrow shape it needs** — a structural
   `Protocol` with `enviar(*, telefono, texto) -> str` (and, later, the template variant) —
   inside its own `infrastructure/` adapter module. `EnvioPorWhatsApp` (`payments`) and
   `AvisoPorWhatsApp` (`scheduling`) depend on that local protocol, not on `conversational`.
2. **The composition root builds the channel once per unit of work** (`api/mensajeria.py`,
   extracted from `api/conversacional.py` to avoid an import cycle with `api/agenda.py`) and
   passes it into the three adapters. `MensajeriaWhatsApp` satisfies the protocols
   structurally.
3. **Credentials stay as ADR-0003 says:** the composition root asks `integrations` for the
   company's WhatsApp configuration on each unit of work. Without a connected integration it
   returns the simulated channel outside production and a "no channel" adapter in production,
   which reports the message as not sent instead of raising.
4. **Inbound delivery callbacks** (a later unit) arrive at the existing
   `/webhooks/whatsapp/{empresa}` route, which already lives in `api/`. Routing a status to a
   payments reminder is a call from the composition root to `payments/application`, not from
   `conversational` to `payments`.
5. **The Context Map gains one row**, added in the same PR as this ADR's acceptance:

| Upstream | Downstream | Type | What flows |
| --- | --- | --- | --- |
| `conversational` | payments, scheduling | C/S, wired only in the composition root | The outbound WhatsApp channel: send a text (and, later, an approved template) and get Meta's message id back |

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **A. Each context keeps its own Meta HTTP client** | No cross-context runtime dependency at all | Three copies of the same ACL: timeouts, retries, 4xx handling and the template contract drift apart. Contradicts ADR-008 (one ACL per provider) |
| **B. Move the outbound client to `integrations` (OHS, any downstream)** | The OHS row already allows every context; no new edge | `integrations` publishes *credentials and connection status* (ADR-0003 §Decision); sending customer messages is a new responsibility that would make the Generic credential service a messaging hub and would itself need to supersede ADR-0003. It also moves working, tested code out of the context that owns the conversation |
| **C. `payments` / `scheduling` import `conversational/application.PortMensajeria`** | Explicit typed edge, enforceable by the hook | Same Context Map change, plus a compile-time coupling to another context's port, which changes whenever the agent's needs change. The structural protocol in the consumer gives the same safety without the import |
| **D. Emit domain events (`RecordatorioSolicitado`, `TurnoCancelado`) and let `conversational` send** | Fully decoupled, natural fit for the "sync integrations" worker | Requires an outbox or a broker contract plus a way to report the delivery state back to `payments` (HS-T3 RN-04). Far larger than the 10 h budget of the unit; reconsider if the in-request sending becomes a latency problem |

## Consequences

**Positive**
- One Meta client, one place to add template messages and to read error codes.
- No new import edge: R1–R5 and `guard_architecture.py` are unchanged and keep passing.
- The dependency is visible in the Context Map instead of living in a docstring.

**Negative / cost we accept**
- `payments` and `scheduling` now fail (best effort, never raising) when Meta or the
  `conversational` client fail.
- The composition root grows: three builders become `async` because reading the credential is.

**What becomes harder from now on**
- Changing `MensajeriaWhatsApp`'s method signatures: two structural protocols must keep
  matching it. A mismatch is caught by `mypy --strict` at the composition root, not by the hook.
- Moving outbound sending to a worker (alternative D) later means touching the three adapters.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [ ] `backend/.env.example` or `frontend/.env.example`
- [x] **[`docs/architecture.md`](../architecture.md) §4** — the Context Map gains the row above.

## References

- [`../architecture.md`](../architecture.md) §4 (Context Map), §5 (R1–R5), §7 (ports and adapters)
- [ADR-0003](0003-integrations-open-host-service.md) — credentials through `integrations`
- [`../aidlc/units/canal-real-de-whatsapp.md`](../aidlc/units/canal-real-de-whatsapp.md) — the unit that needs this decision
- [`../aidlc/epicas/08-agente-de-whatsapp/pendientes.md`](../aidlc/epicas/08-agente-de-whatsapp/pendientes.md) #11, #13
