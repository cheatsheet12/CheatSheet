# ADR-0011 — Share the outbound WhatsApp channel through the composition root

- **Status:** Accepted (2026-10-05, by the owner of the conversational module)
- **Date:** 2026-10-04
- **Decided by:** Luciano Oro, owner of Canal Conversacional and Configuración del Negocio (plantillas) in the Etapa 6 split
- **Modules affected:** conversational, payments, scheduling, business_config

---

## Context

Three contexts send WhatsApp messages to a company's customers:

| Context | Message | Story | Adapter today |
| --- | --- | --- | --- |
| `conversational` | Agent replies and operator messages | HS-T2, HU-E9-02 | `MensajeriaWhatsApp` (real Cloud API client) |
| `payments` | Payment reminders of the escalation chain | HS-T3 | `EnvioPorConsola` (log only, refuses production) |
| `scheduling` | Booking, cancellation and rescheduling notices, and the appointment reminder | HU-E7-02 RN-03/RN-04, HU-E7-06 RN-04, HU-E8-04 RN-02 | `AvisoPorConsola` (log only, refuses production); the reminder does not exist yet |

A fourth context does not send messages but has to talk to Meta: `business_config` owns
`PlantillaDeNotificacion` (HU-E11-02), and a WhatsApp template can only be used once Meta has
approved it (RN-03, RN-04). Outside the 24-hour customer-service window Meta only accepts
pre-approved templates (error 131047), so every message the company starts — payment reminders,
appointment notices — needs an approved template in the company's own WhatsApp Business Account.
Submitting the template and reading its approval status are calls to Meta's Business Management
API, made with the same per-company credentials.

Epic 8 built the only real client, `MensajeriaWhatsApp`, inside
`contexts/conversational/infrastructure/canal.py`, and left a note there and in pending #11 of
the epic: the other two contexts "reach it through the composition root". That intent was never
recorded in the Context Map ([`../architecture.md`](../architecture.md) §4), which has no edge
from `conversational` to `payments` or to `scheduling` — the only `conversational` row goes the
other way (the agent calls scheduling, payments and billing use cases).

Replacing the two console doubles (unit `canal-real-de-whatsapp`, Etapa 6), and then submitting
templates to Meta and receiving delivery statuses (the units that follow it), makes `payments`,
`scheduling` and `business_config` depend, at runtime, on a piece of `conversational`. The workflow requires an
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

**We will keep the single Meta client in `conversational` and hand it to `payments`,
`scheduling` and `business_config` only through the composition root
(`backend/src/cheatsheet/api/`).** No context imports another to send a message or to manage a
template.

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
4. **Templates follow the same path.** `business_config` declares, in its own
   `infrastructure/`, the narrow shape it needs to submit a template and to read its approval
   status, and the composition root hands it the Meta client. The approval status stored in
   `PlantillaDeNotificacion` is always **read from Meta**, never set by a person: outside
   production, the simulated channel reports templates as approved.
5. **Inbound callbacks are routed by `api/`.** Delivery statuses arrive at the existing
   `/webhooks/whatsapp/{empresa}` route. Template status updates cannot: Meta does not allow a
   per-account callback override for the `message_template_status_update` field, so they arrive
   at the app-level webhook URL and are routed to the company by its WhatsApp Business Account id
   (a lookup published by `integrations`), with a periodic reconciliation against Meta as the
   safety net. The claim that Meta offers no per-account override for this field was not
   re-verified when this ADR was accepted: Gate 1 of `entregas-de-whatsapp` checks it against
   Meta's current documentation. If an override exists, only the mechanism changes (the status
   still reaches the context through the composition root); the decision does not.
   Either way, routing a status to a payments reminder or to a template is a call
   from the composition root to that context's `application/`, not from `conversational` to
   another context.
6. **Notices the company sends are recorded in the customer's conversation.** An appointment
   notice or reminder is stored as an outgoing `Mensaje` with origin `SISTEMA` through a
   `conversational` use case that the composition root wires into `scheduling`'s adapter. That
   gives the notice a delivery status (HU-E8-04 RN-04) and gives the agent the context when the
   customer answers it. Before the history reaches the language model, a `SISTEMA` message is
   replaced by a descriptor without personal data (`CLAUDE.md` §3.6).
7. **A failure of the channel never undoes what was already sent.** The consumer adapters never
   raise: a failed send is recorded as `FALLIDO`. A sweep that sends several messages in one
   transaction isolates each one (a savepoint per item), so a failure on item K does not roll
   back the rows of items 1..K-1 whose messages already left — otherwise the next sweep would
   send them again. A read timeout counts as a failure and is **not retried**: Meta may have
   accepted the message, and the Cloud API offers no idempotency key, so a duplicate is worse
   than a missing reminder.
8. **The Context Map gains one row**, added in the same PR as this ADR's acceptance:

| Upstream | Downstream | Type | What flows |
| --- | --- | --- | --- |
| `conversational` | payments, scheduling, business_config | C/S, wired only in the composition root | The WhatsApp channel to Meta: send a text or an approved template and get Meta's message id back; submit a template and read its approval status |

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **A. Each context keeps its own Meta HTTP client** | No cross-context runtime dependency at all | Three copies of the same ACL: timeouts, retries, 4xx handling and the template contract drift apart. Contradicts ADR-008 (one ACL per provider) |
| **B. Move the outbound client to `integrations` (OHS, any downstream)** | The OHS row already allows every context; no new edge | `integrations` publishes *credentials and connection status* (ADR-0003 §Decision); sending customer messages is a new responsibility that would make the Generic credential service a messaging hub and would itself need to supersede ADR-0003. It also moves working, tested code out of the context that owns the conversation |
| **C. `payments` / `scheduling` import `conversational/application.PortMensajeria`** | Explicit typed edge, enforceable by the hook | Same Context Map change, plus a compile-time coupling to another context's port, which changes whenever the agent's needs change. The structural protocol in the consumer gives the same safety without the import |
| **D. Emit domain events (`RecordatorioSolicitado`, `TurnoCancelado`) and let `conversational` send** | Fully decoupled, natural fit for the "sync integrations" worker | Requires an outbox or a broker contract plus a way to report the delivery state back to the sender (`payments`, HS-T3 RN-04). Reconsider if the in-request sending becomes a latency problem |
| **E. Templates are registered by hand in WhatsApp Manager, and an administrator marks them approved in the panel** | No Business Management API calls | The same text lives in two places and drifts at the first edit; an approval typed by a person is an invented provider answer, and a template Meta rejected would be sent anyway. HU-E11-02 places template administration in PAN-CFG-NOT, with the approval status reflected there |

## Consequences

**Positive**
- One Meta client, one place to add template messages and to read error codes.
- No new import edge: R1–R5 and `guard_architecture.py` are unchanged and keep passing.
- The dependency is visible in the Context Map instead of living in a docstring.

**Negative / cost we accept**
- `payments` and `scheduling` now fail (best effort, never raising) when Meta or the
  `conversational` client fail, and `business_config` cannot change a template's status while
  Meta is unreachable.
- Without a Meta test number the real behaviour (error codes, number format, template payload)
  can only be checked against recorded contracts; it stays listed in `docs/aidlc/TODO.md`.
- The composition root grows: the channel builder is `async` because reading the credential
  is, and the adapters' builders receive the channel already built for the unit of work, so the
  credential is read once per request or sweep.

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
- [`../aidlc/units.md`](../aidlc/units.md) — the units that depend on this decision: `canal-real-de-whatsapp`, `plantillas-de-whatsapp-en-meta`, `entregas-de-whatsapp`, `recordatorio-de-turno`
- Meta: [send messages](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages) (24-hour window), [error codes](https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes) (131047), [message templates](https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates)
- [`../aidlc/epicas/08-agente-de-whatsapp/pendientes.md`](../aidlc/epicas/08-agente-de-whatsapp/pendientes.md) #11, #13
