# ADR-0009 — Amend the story catalogue after the 2026-09 review, and register its units in the existing epics

- **Status:** Proposed
- **Date:** 2026-09-29
- **Decided by:** Product owners and the development team (pending approval)
- **Modules affected:** identity, master_data, spreadsheet_sync, billing, payments, scheduling, conversational, reporting, frontend

---

## Context

The professor's review of 2026-09, together with the team's own analysis of it, found that the
Etapa 5 story catalogue (`docs/aidlc/inputs/historias-de-usuario.md`) no longer describes what the
system must do, or is silent where it must not be:

- Legal consent is under-specified: terms are versioned on the company, and there is no privacy
  policy or per-user consent record (Ley 25.326).
- Two stories promise immediate effect (role change, access deactivation), while the short-lived
  access token currently leaves a window of up to 15 minutes.
- Catalogue data has no uniform format, and a service duration has no bounds.
- The invoice type depends on the receiver's tax condition, and the catalogue only states it in one
  sentence. Facturas C do not itemise VAT, yet the catalogue stores a rate per service.
- A payment has no payment date; "collected in the period" is measured by creation date and the
  collection rate can exceed 100 %. Refunds are all-or-nothing and assume the MercadoPago API,
  which does not apply to bank transfers.
- Customers pay by bank transfer and send a receipt through WhatsApp, and nothing describes how
  that payment is verified.
- The agenda accepts turnos in the past, has no gap between turnos, and does not say whether the
  service or the resource defines a turno's duration.
- The home screen has no story, and the dashboard story has a precondition that contradicts its own
  empty state.

Two constraints frame the answer. `CLAUDE.md` §0 makes the story the acceptance criterion of a
unit, so a rule that lives only in a plan is invisible to verification. And the roadmap requires
that every story lands in exactly one epic and that every epic ends in something demonstrable on
`staging`. Epics 1 to 10 are already mapped, and most are merged.

## Decision

We amend the story catalogue in place and register the resulting units inside the existing epics of
`docs/aidlc/roadmap.md`; we do not create a new epic.

**New stories (4):** HU-E1-08 (privacy policy), HU-E4-05 (normalisation of catalogue data),
HU-E6-08 (payment by bank transfer), HU-E8-06 (payment receipt through WhatsApp).

**Modified stories (22):** HU-E1-03, HU-E1-05, HU-E1-06, HU-E3-03, HU-E3-04, HU-E3-07, HU-E4-01,
HU-E4-02, HU-E5-02, HU-E5-03, HU-E5-04, HU-E6-01, HU-E6-02, HU-E6-03, HU-E6-05, HU-E6-06, HU-E7-02,
HU-E7-04, HU-E7-06, HU-E8-01, HU-E8-05, HU-E10-01. HU-E1-05 and HU-E1-06 change only by gaining
verifiable acceptance criteria. Each touched story carries a marker line under its heading pointing
to this ADR.

**Units:** fourteen units are appended to `docs/aidlc/units.md` under the existing epic names, in
state `pendiente`. Their decisions are D83 to D98, recorded in the epic block of `units.md` for
epics 1 to 5 and in `docs/aidlc/epicas/NN-*/decisiones.md` for epics 6 to 10.

Rules that shape the units and are recorded as decisions:

- Terms are accepted by the company through an Administrator; the privacy policy is accepted by each
  user.
- Access is revoked on the next request, not when the token expires.
- Catalogue data is normalised once, at the common entry point of `master_data`.
- The invoice type follows the receiver's condition, with the ARCA taxpayer registry as the source of
  truth.
- "Collected" is measured by payment date.
- Refunds are partial-capable for both payment media, and refunds of transfers are registered
  manually and declaratively.
- A transfer confirms a Cobro only if the payer's identity matches the customer's CUIT.
- A turno's duration is its service's standard duration.
- A payment receipt never reaches an external LLM.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| A new epic 11 for "review adjustments" | One place to see all the work | It would be a horizontal layer with no demo of its own, and it would split each rule from the epic whose context owns it. The roadmap cuts vertically. |
| Leave the catalogue untouched and record the rules only in each unit plan | No edit to an imported input | Stories are the acceptance criteria. A rule that lives only in a plan is not verified against the story and is lost when the plan is archived. |
| A separate addendum document next to the catalogue | The original stays pristine | Two sources of truth for the same story; the reader must reconcile them. |
| Amend the catalogue in place, marker on each story, units in existing epics | One source of truth; each unit stays with its owner context and epic | Reopens epics that were already finished (see Consequences). |

## Consequences

**Positive**
- The catalogue again describes the intended behaviour, with checkable acceptance criteria.
- Each unit is owned by one bounded context and lands in the epic whose demo it extends.
- The amended stories name their model changes explicitly, so the DER is not changed by surprise.

**Negative / cost we accept**
- Epics already finished gain `pendiente` units, so their derived state returns to "in progress".
- The imported catalogue is no longer identical to the Etapa 5 delivery. The marker lines are what
  keeps the difference traceable.
- The DER delivered with Etapa 5 becomes outdated in several tables. It is not rewritten here.

**What becomes harder from now on**
- Changing a rule that is now in a story requires amending the story and citing the ADR that
  authorised it.

### Deferred to each unit's Gate 1

This ADR decides scope, not schema. The DER changes below are resolved in the Gate 1 of the unit that
needs them:

- `cobro`: `fecha_pago`, `medio_de_pago`, `numero_de_operacion` (unique per company).
- Refunds, for both media: accumulated refunded amount, date, reference and registering user, plus the
  state `REEMBOLSADO_PARCIAL`. **Payment methods and refunds need their own ADR** before the
  migration, written once at the Gate 1 of the first unit of epic 6 that needs it.
- `condicion_iva`: `IVA_NO_ALCANZADO`.
- `comprobante`: concept, service period, payment due date, and origin and date of the receiver's
  tax condition.
- `cliente`: date of the last confirmation by the taxpayer registry.
- `recurso_reservable`: gap between turnos. The `btree_gist` exclusion constraint over start and
  duration cannot express a per-resource gap, so the unit decides between storing the applied gap on
  the turno and moving the check to the domain.
- Per-user legal acceptances (for example an `aceptacion_legal` table without IP).
- `tipo_contenido_mensaje`: `DOCUMENTO`, and a temporary private store for escalated receipts.

### Verifications pending in sandbox

None of these is assumed to hold:

- That MercadoPago returns the payer identification for incoming bank transfers, not only for link
  payments.
- Whether transfer operations can be queried with the seller's credentials. Transfers from external
  banks to a CVU may not be queryable, and those cases fall back to human escalation.
- The MercadoPago refunds API for partial refunds.
- The codes ARCA accepts in WSFEv1 homologación for each combination of issuer and receiver,
  including a receiver "IVA No Alcanzado" and the receiver condition field per invoice type.

### Fiscal facts and their sources

- Factura A to a receiver registered as Monotributo: RG 5003/2021, with the legend of Ley 27.618 on
  the document.
- Reporting the receiver's tax condition (`CondicionIVAReceptorId`) on every invoice and credit
  note: RG 5616/2024.
- WSFEv1 field and method reference: manual WSFEv1 v4.7, dated 2026-09-01.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [ ] `backend/.env.example` or `frontend/.env.example`
- [x] None

## References

- Amended catalogue: [`docs/aidlc/inputs/historias-de-usuario.md`](../aidlc/inputs/historias-de-usuario.md)
- Units and decisions D83 to D98: [`docs/aidlc/units.md`](../aidlc/units.md) and
  [`docs/aidlc/epicas/`](../aidlc/epicas/)
- [ADR-0003](0003-integrations-open-host-service.md), [ADR-0008](0008-wsfev1-cliente-propio.md)
