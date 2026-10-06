# ADR-0013 — Require a client-generated idempotency key on requests with irreversible external effects

- **Status:** Accepted (2026-10-06, by the owner of the payments module)
- **Date:** 2026-10-06
- **Decided by:** Luciano Oro, owner of the unit `cobro-con-clave-de-idempotencia` (Gate 1 approved 2026-10-06)
- **Modules affected:** payments, billing, frontend

---

## Context

Some HTTP requests of the panel cause an effect outside the system that cannot be taken back:

- `POST /cobros` (HU-E6-03) creates a `cobro` and asks MercadoPago for a new payable preference
  (`api/routers/cobros.py:272`). It answers 201 only after MercadoPago returned the link.
- `POST /comprobantes` and `POST /comprobantes/{id}/notas-de-credito` (HU-E5-03, HU-E5-04,
  `api/routers/comprobantes.py:412` and `:263`) take a document number and enqueue its authorization
  with ARCA. A `Comprobante` with CAE is irreversible (issue #97).

None of them carries an identity of *the request*. Every call is a new effect. The panel no longer
allows a double click (#90), but a network retry, a BFF timeout while the backend is still working
(the BFF gives up at 10 s, `frontend/src/lib/api.ts:20`, while MercadoPago may take up to 15 s × 3
attempts, `payments/infrastructure/pasarela.py:50-51`), two browser tabs or a client that is not the
panel all produce **two cobros with two payable links**, or **two comprobantes with CAE**, for one
intention. Only the backend can close that gap.

The repository already has two idempotency mechanisms, and neither covers this case:

- **`shared/idempotencia.py::ClaveDeIdempotencia`** (ADR-009 of the design documents,
  `docs/architecture.md` §"Processing guarantees") derives the key from content: company + type +
  SHA-256 of the canonical payload (`shared/idempotencia.py:37-46`), recorded in Redis with a single
  `SET NX EX` and a 7-day TTL (`platform/cache.py:48-52`). It is right for tasks and webhooks, where
  two deliveries with identical content *are* the same event. For a user request it is wrong: two
  legitimate cobros with the same customer, amount and description, made on different days, have the
  same fingerprint, and the second would be silently dropped. Only the client knows whether a request
  is "the same one again" or "another identical one".
- **The refund key** (`cobro.reembolso_clave_idempotencia`, `api/routers/reembolsos.py:5-14`) is
  committed in its own transaction before calling MercadoPago and reused on every retry. It protects
  the call **to MercadoPago** (the `X-Idempotency-Key` sent at `pasarela.py:266-274`), not the user's
  request to us.

Issue #97 already proposes the same header and the same storage for billing, so the shape must be
fixed once, before two modules implement it twice.

## Decision

We will require a client-generated request idempotency key, sent as `X-Idempotency-Key`, on every
endpoint whose effect reaches an external provider and cannot be undone, and store it with the
aggregate the request creates.

1. **Coverage.** Mandatory now on `POST /cobros`. `billing` adopts the same contract for issuing a
   comprobante and a credit note in #97. A new endpoint with an irreversible external effect adopts
   it as part of its unit; one that is already idempotent by state (`regenerar`, `cancelar`) does not.
2. **Format.** The header carries a UUID (any version; the panel uses v4). A missing header is a
   **422** ("Falta la clave de idempotencia del pedido (encabezado X-Idempotency-Key)."); a value
   that is not a UUID is a **422** ("La clave de idempotencia del pedido no es valida."). Both are
   checked in the router: they are the shape of the HTTP request, not a rule of the use case.
3. **Storage.** The key lives on the aggregate it created, as a nullable `UUID` column
   (`cobro.clave_idempotencia`; `comprobante.clave_idempotencia` in #97), with a partial unique index
   `(empresa_id, clave_idempotencia) WHERE clave_idempotencia IS NOT NULL`. Existing rows stay `NULL`:
   no key is invented, no backfill. The table's existing RLS policy covers the column, so the same key
   in two companies is two independent requests and one company can never retrieve another's
   resource by guessing its key.
4. **Replay.** Same key and same request → the **same success status as the original response**
   (201 for a cobro; 202 for a comprobante) with the original resource **in its current state**,
   without calling the provider again and without a new audit event (a structured log line records
   the replay, without personal data). Same key and **different** data → **422**
   (`ClaveDeIdempotenciaReusada`: "Esta clave ya se uso para generar un cobro con otros datos.
   Revise el listado de cobros antes de reintentar.").
5. **"Same request"** is decided by the aggregate's own fields, never by a stored fingerprint. For a
   cobro: customer, amount **after** `redondear` (`ROUND_HALF_UP`, so `"1210.005"` and `"1210.01"`
   are the same request), description and associated comprobante, through a pure domain method
   `Cobro.es_el_mismo_pedido(...)`. These fields are immutable after creation. Each module names the
   fields of its own aggregate in its unit plan.
6. **Concurrency.** The lookup takes a **transaction-scoped PostgreSQL advisory lock** on
   `(empresa_id, key)` before reading:
   `pg_advisory_xact_lock(<namespace>, hashtext(empresa_id || ':' || key))`, with a per-aggregate
   namespace constant, exactly like `ESPACIO_FAMILIA_REFRESH` and `tomar_con_familia_bloqueada` in
   `identity/infrastructure/refresh_tokens.py:20-23` and `:57-78`. The lock is released when the unit
   of work commits or rolls back. A second concurrent request with the same key **waits** for the
   first and then finds its resource, so the provider (MercadoPago, ARCA) is called once. If the first
   failed (provider down), nothing was stored and the second tries again. A hash collision only makes
   two different keys wait for each other; it exposes nothing.
7. **Order inside the use case.** Role check → lock and lookup by key → (if found: compare and
   return) → every other validation → external call → persist with the key. The lookup precedes the
   business validations on purpose: a replay after, say, the customer was deactivated must still
   return the resource that exists.
8. **Backstop.** With the lock, two inserts with the same key cannot race. If the unique constraint
   fires anyway, the repository translates that `IntegrityError` — for that constraint only, matched
   by name — into `PedidoEnCurso` (`InvarianteViolada`, 409: "Ese pedido ya se esta procesando.
   Intente nuevamente."). Never a 500, never a blanket `except`.
9. **Client.** The panel generates the key **once per form** (`crypto.randomUUID()`), reuses it on
   every submit, retry or double click, and **renews it only after a success** — never after an error
   or an edit following an error, because the first request may have arrived although its response
   did not. The BFF forwards the incoming header unchanged and never invents one:
   `app/api/usuarios/_proxy.ts::reenviarAlBackend` (`:21-33`) gains an optional headers parameter
   that reaches `llamarApi({ headers })`, which already supports it (`frontend/src/lib/api.ts:50`,
   `:81-84`). The other routes do not change.

**How the mechanisms coexist.** Three keys, three jobs, no overlap:

| Key | Generated by | Protects | Stored in |
| --- | --- | --- | --- |
| Request key (this ADR) | The client, once per intention | Our endpoint against a repeated user request | Column on the created aggregate, unique per company |
| `ClaveDeIdempotencia` (ADR-009) | The system, from content | A task or webhook against redelivery | Redis, `SET NX EX`, 7 days |
| Provider key (`pasarela.py:266-274`) | The system, per call | MercadoPago against our own HTTP retries | Refunds: `cobro.reembolso_clave_idempotencia` |

A request key never feeds `ClaveDeIdempotencia`, and the work a covered request enqueues (the ARCA
authorization in billing) keeps its own task key.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| Content fingerprint (reuse `ClaveDeIdempotencia` over the request body) | No client change; one mechanism | Two legitimate identical requests on different days would collapse into one; the second cobro or comprobante would be lost without an error. |
| Store a SHA-256 of the canonical body next to the key (IETF `Idempotency-Key` draft) | Generic comparison; no per-aggregate method | One more column, and a canonicalization rule that can diverge from the domain (`"1210.005"` vs `"1210.01"` are different bytes and the same amount). The aggregate's fields are immutable and already say what the request was. |
| Keys in Redis with a TTL | No migration; shared store with ADR-009 | A replay after the TTL creates a second effect; the record is not in the same transaction as the aggregate, so a crash between them leaves one without the other; Redis holds no RLS barrier. |
| Optional key (protect only when present) | Backward compatible for any other client | Leaves open exactly the case the protection exists for: a client that is not the panel. The panel is today the only caller, so making it mandatory costs nothing now. |
| 409 "in progress" for a concurrent duplicate (`pg_try_advisory_xact_lock`, as in `master_data/infrastructure/correccion.py:50-52`) | Releases the connection sooner | Forces every client to implement a retry loop for a case the server can resolve by waiting; the wait is bounded by the provider timeouts that already exist. 409 stays only as the backstop of point 8. |
| 409 for "same key, different data" | Common in some public APIs | In this system 409 means a business-state conflict (`InvarianteViolada`); this is a malformed request. The IETF draft uses 422, and the BFF already forwards the text of a 422 (`respuestaDeError`), so no client-side change is needed. |
| 200 instead of 201 on a replay | Tells "created" from "already existed" | The point of the key is that the client need not distinguish; the BFF flattens both to 200 anyway (`_proxy.ts:34`). |
| Header name `Idempotency-Key` (IETF draft) | The emerging standard | `X-Idempotency-Key` is what MercadoPago uses and what #97 already proposed; one name across the system matters more than the prefix. |

## Consequences

**Positive**
- A repeated or concurrent request produces one cobro and one MercadoPago preference; in billing, one
  comprobante and one CAE. Retrying after a timeout becomes safe.
- The key commits in the same transaction as the aggregate, so "the key exists" and "the effect
  exists" can never disagree.
- `billing` (#97) implements a written contract instead of copying code, and both modules answer the
  same cases with the same codes.

**Negative / cost we accept**
- Every client of a covered endpoint must send a UUID; a call without it is rejected (documented
  here, the only current caller is the panel).
- The second of two concurrent requests holds a database connection while the first talks to the
  provider (bounded by the existing timeouts, at most about 45 s for MercadoPago).
- A user who corrects the amount after a 504 sees the "key already used" message and a link to the
  list, instead of a new cobro. That is deliberate: the first one may exist.
- The migration is reversible with declared loss: the downgrade drops the keys, and a later retry with
  an old key would create a new resource.

**What becomes harder from now on**
- A new endpoint with an irreversible external effect must adopt this contract, and its aggregate
  must expose a pure "same request" comparison over immutable fields. A future use case that edits
  one of those fields must revisit that comparison.
- Covered endpoints cannot be called by hand without generating a key.

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

- Unit plan: `docs/aidlc/units/cobro-con-clave-de-idempotencia.md` (Gate 1, questions 1–10).
- Issue [#97](https://github.com/cheatsheet12/CheatSheet/issues/97) — the same protection for issuing
  a comprobante and a credit note in `billing`.
- PR #90 (`navegacion-pendiente`) — the panel-side double-click protection this complements.
- ADR-009 of the design documents (processing guarantees), condensed in `docs/architecture.md`.
- Precedents: `identity/infrastructure/refresh_tokens.py` (advisory lock),
  `api/routers/reembolsos.py` (key committed before the provider call), `shared/idempotencia.py`.
- IETF HTTPAPI draft *The Idempotency-Key HTTP Header Field*:
  <https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/>
