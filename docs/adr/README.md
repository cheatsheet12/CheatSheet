# ADR — Architecture Decision Records

An **ADR** documents an important technical decision: what was decided, why, and what
was ruled out.

It exists so that six months from now — or when a new agent opens the repository —
nobody has to guess why things are the way they are, or relive an argument that was
already settled.

## When to write one

If the decision **affects more than one module** or **is costly to reverse**, it needs
an ADR.

- Choosing a framework, an ORM, a database engine
- Architectural pattern and directory structure
- LLM provider and prompting strategy
- Authentication and authorization scheme
- Queueing, retry or idempotency strategy
- Creating a new directory at the repository root
- Changing a rule in [`../code-standards.md`](../code-standards.md)

No ADR needed for: naming a function, adding a test, fixing a bug.

## How

1. Copy [`0000-template.md`](0000-template.md) to `NNNN-title-in-kebab.md`, where
   `NNNN` is the next free sequential number.
2. Write it in `Proposed` status and open the PR.
3. When the PR is approved, it becomes `Accepted`.

## Rules

- **An accepted ADR is never edited or deleted.** If the decision changes, write a new
  one that *supersedes* it, and link both to each other.
- An ADR describes the **context and the why**, not the how. The how lives in the code.
- If you cannot name at least one alternative you ruled out, you probably did not make
  a decision — you collected an assumption.

## Index

| # | Title | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-repository-structure.md) | Lay the repository out by bounded context, with enforced boundaries | Accepted | 2026-08-10 |
| [0002](0002-frontend-structure.md) | Organize the frontend by bounded context, and gate it like the backend | Accepted | 2026-08-10 |
| [0003](0003-integrations-open-host-service.md) | Publish `integrations` as an Open Host Service | Accepted | 2026-08-18 |
| [0004](0004-arca-wsaa-access-tickets.md) | Sign WSAA login tickets in `integrations`, and publish the access ticket | Accepted | 2026-08-19 |
| [0005](0005-staging-database-neon.md) | Run the staging database on Neon, and prove the tenant barrier survives it | Proposed | 2026-08-21 |
| [0006](0006-staging-hosting-render.md) | Host staging on Render, and let CI — not the push — release it | Proposed | 2026-08-24 |
| [0009](0009-review-adjustments-scope-change.md) | Amend the story catalogue after the 2026-09 review, and register its units in the existing epics | Proposed | 2026-09-29 |
| [0010](0010-payment-date-method-and-refunds.md) | Record how and when a payment was made, and model refunds as dated, append-only records | Accepted | 2026-09-30 |
| [0011](0011-outbound-whatsapp-channel-via-composition-root.md) | Share the outbound WhatsApp channel through the composition root | Accepted | 2026-10-05 |
| [0012](0012-faq-uses-per-month-and-share.md) | Count FAQ uses per calendar month in Argentina time, and show each FAQ's share before and after its last edit | Accepted | 2026-10-05 |
| [0013](0013-request-idempotency-key.md) | Require a client-generated idempotency key on requests with irreversible external effects | Accepted | 2026-10-06 |
| [0015](0015-local-ci-verification.md) | Verify locally with the full CI summary while hosted CI is unavailable | Proposed | 2026-10-08 |

> The architecture itself (modular monolith, hexagonal, multi-tenancy, sync model,
> ACLs, processing guarantees, security) was decided during Etapa 5 and is recorded as
> ADR-001 … ADR-012 **in the design documents**, condensed in
> [`../architecture.md`](../architecture.md). Those are not restated here.
> ADR-0001 above is what maps those decisions onto this repository.
