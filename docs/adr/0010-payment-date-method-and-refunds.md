# ADR-0010 — Record how and when a payment was made, and model refunds as dated, append-only records

- **Status:** Accepted (2026-09-30, at Gate 1 of the unit `fecha-de-pago`)
- **Date:** 2026-09-30
- **Decided by:** Product owners and the development team (pending approval)
- **Modules affected:** payments, reporting, conversational, frontend

---

## Context

[ADR-0009](0009-review-adjustments-scope-change.md) amended the story catalogue and deferred one
decision: *payment methods and refunds need their own ADR before the migration*. Four epic-6 units
build on the answer (`fecha-de-pago`, `reembolsos-parciales-y-manuales`, `cobro-por-transferencia`,
`comprobante-por-whatsapp`), plus `indicadores-de-cobranza` in epic 9. If each one invents its own
columns, the same fact ends up stored twice, or in two shapes.

What the system does today (`backend/src/cheatsheet/contexts/payments/`):

- A `cobro` has a `pagado_en` timestamp. It is set to the moment the webhook was **processed**, not
  to the moment the payer paid. There is no payment method: every cobro is born from a MercadoPago
  link and nothing else can pay it.
- A refund is one nullable number, `monto_reembolsado`, plus `reembolso_solicitado_en` while a request
  is in flight. It has no date of the refund, no reference, no reason and no author. The state enum
  has no partial state, so a partial refund is stored as `REEMBOLSADO` (epic-6 `pendientes.md`, item 7).
- "Collected in a period" is computed over the creation date of the cobro, so a refund lowers the
  figure of the month in which the cobro was *created*, and a cobro paid in March but created in
  February does not appear in March.

What the amended stories require (HU-E6-01, HU-E6-02, HU-E6-05, HU-E6-08, HU-E10-01):

- "Collected" is measured by payment date; a refund subtracts in the period in which the money was
  returned (HU-E6-05 RN-11).
- The detail shows payment method, payment date and, for transfers, the operation number.
- A payment can arrive by MercadoPago link or by bank transfer confirmed against an operation number,
  and one operation number may take effect only once per company, links included (HU-E6-08 RN-03).
- Refunds may be partial, for both media. A transfer refund is registered by hand and is declarative;
  records are never deleted and a mistake is corrected by a new visible record (HU-E6-05 RN-07, RN-08).
- The identification of a payer is never persisted (HU-E6-08 RN-07).

External facts, from the MercadoPago developer reference for *Get payment*
(<https://www.mercadopago.com.ar/developers/en/reference/online-payments/checkout-pro/get-payment/get>):
`date_approved` is an ISO 8601 string and can be `null`; `payment_type_id` and `payment_method_id`
exist and describe the instrument (for example `credit_card`, `master`). **Not verified:** the full
list of `payment_type_id` values, and whether an incoming bank transfer exposes `date_approved` and the
payer identification. The last two are already listed in ADR-0009 as pending sandbox verifications.

## Decision

We will record payment method, payment date and operation number on the `cobro` with our own closed
vocabulary, and we will model every refund as an immutable row in its own table, with the cobro
keeping only the derived accumulated amount.

1. **Payment method.** `cobro.medio_de_pago` is a closed set, `LINK_MERCADOPAGO` or `TRANSFERENCIA`,
   `NOT NULL`, default `LINK_MERCADOPAGO`, enforced by a `CHECK`. A cobro is born as a link and becomes
   `TRANSFERENCIA` only when a transfer confirms it. We do **not** store MercadoPago's
   `payment_type_id` or `payment_method_id`: the provider's vocabulary stays in the ACL.
2. **Payment date.** `cobro.fecha_pago` (`timestamptz`, stored in UTC) replaces `pagado_en`. It is
   written once, in the same transition that moves the cobro to `APROBADO`, and never overwritten.
   Its source is the approval date reported by MercadoPago (link) or the date of the verified operation
   (transfer). When that date is missing or implausible (no offset, in the future, or earlier than the
   creation of the cobro) the system uses the moment it confirmed the payment and sets
   `cobro.fecha_pago_aproximada = true`. Rows that existed before this decision keep their old value
   and are marked approximate; no network call is made to improve them.
3. **Operation number.** `cobro.numero_de_operacion` (nullable) is filled only for transfers. One
   unique index per company over `COALESCE(numero_de_operacion, mp_payment_id)` guarantees that a
   given operation takes effect once regardless of the route it arrived by. The payer identification
   is not stored anywhere.
4. **Refunds.** One append-only table, `reembolso`, with one row per refund or per correction:
   `empresa_id`, `cobro_id`, `monto` (`Decimal`, `NUMERIC(14,2)`, non-zero; a correction is a negative
   row that points to the row it corrects), `fecha_devolucion` (when the money was returned),
   `origen` (`API_MERCADOPAGO` or `MANUAL`), optional `referencia`, `motivo`, `registrado_por`
   (`NULL` when the system records a confirmation) and `created_at`. The application role gets `SELECT`
   and `INSERT` only. The cobro keeps `monto_reembolsado` as the running sum, updated in the same
   transaction that inserts the row, with `0 <= monto_reembolsado <= monto`. The exact column list is
   closed in the Gate 1 of `reembolsos-parciales-y-manuales`, inside these constraints.
5. **States.** `estado_cobro` gains `REEMBOLSADO_PARCIAL`. The state after a refund or a correction is a
   pure function of the accumulated amount (`0 < acumulado < monto` is partial, `acumulado = monto` is
   fully refunded, `0` returns to `APROBADO`), so a correction may lower it. A refund still in flight
   remains `reembolso_solicitado_en`, not a state (D27 stands).
6. **Reporting.** "Collected" is the sum of `monto` by `fecha_pago` minus the sum of
   `reembolso.monto` by `fecha_devolucion`. `reembolso` carries `empresa_id` and its own date, so
   `payments` can answer without a join against `cobro`, and `reporting` reaches it through the
   application layer of `payments` (R3).
7. **Delivery.** Points 1 to 3 ship in the migration of `fecha-de-pago` (0026). Points 4 and 5 ship in
   the migration of `reembolsos-parciales-y-manuales`, so no table or state exists before code that
   uses and tests it.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| Keep `pagado_en` and reinterpret it as the payment date | No migration | It holds the processing time of the webhook; a late or retried notification would move the payment to the wrong period, and the value can never be distinguished from a real payment date. |
| Store MercadoPago's `payment_type_id` as the method | Richer detail (card, account balance) | The list of values is not verified, it does not describe a transfer registered by number, and it puts the provider's vocabulary in the domain. |
| Refund fields on `cobro` only (accumulated amount, last date, last reference) | No new table | It cannot hold a history, cannot express a correction without overwriting, and cannot report by the date each refund was made. HU-E6-05 RN-08 forbids deleting records. |
| A separate `pago` entity (one cobro, many payments) | Models partial payments per cobro | A cobro is terminal once `APROBADO` (one payment per cobro, partial payment is a comprobante-level concept through several cobros, HU-E6-06 RN-04). Heavier than needed now; revisit if a cobro must accept several payments. |
| A `REEMBOLSO_EN_PROCESO` state | Explicit in the enum | Already rejected in D27: a rejected refund would force a transition back to `APROBADO`. |
| Ship refund table and columns together with the payment columns | One migration | Dead schema with no code and no tests behind it until the refund unit lands, and its RLS and grants would go untested. |

## Consequences

**Positive**
- One source of truth for when a payment happened, with an explicit marker where that date is an
  estimate. Reports stop depending on creation dates.
- A single unique index protects an operation number across links and transfers, so the transfer
  unit needs no application-level race handling for that rule.
- The refund model is fixed once; the two refund units and the reporting unit consume it without
  redesign.
- The provider's vocabulary stays inside `infrastructure/pasarela.py`.

**Negative / cost we accept**
- Two migrations for one model (0026 and the refund one); between them the system has the payment
  columns and the old single-number refund.
- Until the refund unit lands, a fully refunded cobro is left out of "collected" altogether (as it is
  today), so a refund of a payment made in another period is not yet placed in the period of the
  refund.
- Existing paid cobros carry an approximate payment date.
- Renaming `pagado_en` changes the HTTP field of the cobro (`fecha_pago`); the only consumer is the
  panel, deployed together with the API.

**What becomes harder from now on**
- Correcting a refund never edits a row; it always appends one.
- Adding a payment method means extending a `CHECK` and a domain enum, not just a value from the
  provider.
- A third payment route must respect the cross-route uniqueness index or replace it deliberately.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [ ] `backend/.env.example` or `frontend/.env.example`
- [x] None

(The index in [`README.md`](README.md) gets one row, in the same PR.)

## References

- [ADR-0009](0009-review-adjustments-scope-change.md) — defers this decision.
- Decisions D20, D26, D27, D91, D93, D94, D98 in `docs/aidlc/epicas/06-cobros-y-recordatorios/decisiones.md`
  and `docs/aidlc/epicas/09-reporteria-y-paquete-contable/decisiones.md`.
- Stories HU-E6-01, HU-E6-02, HU-E6-05, HU-E6-08, HU-E10-01 in `docs/aidlc/inputs/historias-de-usuario.md`.
- MercadoPago, *Get payment*: <https://www.mercadopago.com.ar/developers/en/reference/online-payments/checkout-pro/get-payment/get>
- Unit plan: `docs/aidlc/units/fecha-de-pago.md`.
