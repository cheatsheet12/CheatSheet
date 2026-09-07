# ADR-0008 — Talk to WSFEv1 with our own SOAP client, superseding ADR-012

- **Status:** Proposed
- **Date:** 2026-09-07
- **Decided by:** Software Architect
- **Modules affected:** billing, reference_data, integrations, infra

---

## Context

[ADR-0004](0004-arca-wsaa-access-tickets.md) settled how anything authenticates to ARCA and
explicitly left one question open, with a name on it:

> «ADR-012 stands and is not superseded. It decides how `billing` talks to **WSFEv1**, and
> **epic 5 makes that call**.»

This is that call. ADR-012, from the Etapa 5 design documents, records **ARCA via PyAfipWs
(WSFEv1, SOAP)**, and `backend/pyproject.toml` still carries a comment saying PyAfipWs
arrives with this epic.

**What has changed since ADR-012 was written is that we now have evidence.** Epic 2
implemented WSAA without PyAfipWs: the CMS signature turned out to be about forty lines of
`cryptography`, and parsing ARCA's SOAP responses turned out to be `defusedxml`, which is
already a dependency. ADR-0004 recorded that as a deliberate departure and was careful to
say it did not extend to WSFEv1 — because WSFEv1 is genuinely different.

The constraints that bind this decision:

1. **WSFEv1 is a large surface with real fiscal semantics.** `FECAESolicitar`,
   `FECompUltimoAutorizado`, `FEParamGetTiposCbte`, `FEParamGetTiposIva`,
   `FEParamGetPtosVenta` and a dozen more. Getting a field wrong does not raise: it
   produces a document ARCA authorises with the wrong content, or rejects with a numeric
   code that does not say what is missing.
2. **A wrongly issued document is irreversible** (`CLAUDE.md` §1). The only thing that
   reverses a CAE is a credit note, which is itself a fiscal document. There is no
   rollback, no `DELETE`, and no way to make it not have happened.
3. **Every amount is `Decimal` with explicit `ROUND_HALF_UP`** (`CLAUDE.md` §3.5 and §5).
   Whatever crosses the wire has to preserve that, and whatever comes back has to be read
   without going through a float.
4. **This is a student project that has to be demonstrable on `staging` without
   credentials**, like ARCA, WhatsApp and MercadoPago already are. Every test in the
   repository is forbidden from touching the network.
5. **`mypy --strict` must pass on every Python file in the repository** (`CLAUDE.md` §5),
   and no file may be excluded from the linter (§8).

## Decision

> We will call WSFEv1 with **our own SOAP client**, built on `httpx` and `defusedxml`,
> behind the `PortFacturacionElectronica` port of `billing`. **ADR-012 is superseded.**

The detail needed to implement it without asking again:

**Scope.** Only the WSFEv1 operations the six stories of epic 5 need — issuing
(`FECAESolicitar`), the last authorised number (`FECompUltimoAutorizado`), the points of
sale (`FEParamGetPtosVenta`) and the parameter catalogues HS-T4 syncs. Every other
operation is out of scope until a story asks for it.

**The ticket comes from `integrations`**, exactly as ADR-0004 publishes it. This ADR adds
nothing to authentication.

**Amounts never become floats.** The request is built by formatting `Decimal` to string with
the two decimals ARCA expects; the response is read back into `Decimal` from its string.
`float` does not appear on either side, which is the one thing PyAfipWs would also have had
to promise and does not.

**The response is validated before it is believed.** `FECAESolicitar` answers with a result
code (`A` approved, `R` rejected, `P` partial), a list of `Observaciones` and a list of
`Errores`. All three are read; an approval carrying observations is still an approval and
the observations are stored, because they are what the user is shown when ARCA authorises
something it did not like.

**Two adapters, as everywhere else here.** The real one and a simulated one that `Settings`
refuses in `production`, so the whole issuing flow is walkable on a laptop with no fiscal
certificate and no test opens a socket.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **PyAfipWs** (what ADR-012 chose) | Encodes years of accumulated knowledge about ARCA's quirks — exactly the knowledge we do not have. Widely used in Argentina | Three reasons, in order of weight. **It is GPL**, which is a licensing decision this project has never made and should not make as a side effect of an epic. **It is not typed**, so `mypy --strict` would need a per-module `ignore_missing_imports` for the one library that handles fiscal documents — the place where types are worth the most. And it carries **its own state and its own I/O**: it manages tickets, files and configuration itself, which collides with ADR-0004, where `integrations` owns the ticket and hands it over |
| **`zeep`** (a generic typed SOAP client) | Reads the WSDL and generates the calls; less hand-written XML | The WSDL is fetched at runtime by default, which means an outage at ARCA breaks a process that had nothing to ask ARCA yet. Pinning a local WSDL is possible and then the advantage mostly evaporates. It also drags in `lxml`, next to the `defusedxml` already here for the same job |
| **Delay the decision and start with the screens** | Lets epic 5 begin today | The seam is the whole risk of the epic. Building three screens against an interface nobody has decided is how the interface ends up being whatever the screens happened to need |

**The honest counter-argument, stated rather than hidden:** PyAfipWs knows things about ARCA
that we are going to learn by being rejected. A hand-written client will meet edge cases —
the shape of `Observaciones`, how `FECAEDetResponse` behaves on a partial approval, the
exact date format — that PyAfipWs already handles. We are trading somebody else's accumulated
experience for a typed, dependency-light, testable seam. That trade is defensible because the
surface is small (four operations) and because the alternative's costs are structural rather
than temporary; it is **not** free, and the first weeks against ARCA homologación will show it.

## Consequences

**Positive**
- `mypy --strict` covers the fiscal path end to end, which is where it earns the most.
- No new licence obligations, and no library that wants to own the ticket ADR-0004 already
  owns.
- The issuing flow is demonstrable with no certificate, like every other integration here.
- Four operations of hand-written SOAP is a surface a reviewer can read in one sitting.

**Negative / cost we accept**
- **We will learn ARCA's edge cases the hard way**, in homologación, one rejection code at
  a time. That is the real price and it is not small.
- Every WSFEv1 operation a later epic needs is written by us. There is no `import` that
  makes the next one free.
- A change on ARCA's side is our problem to notice and fix.

**What becomes harder from now on**
- Adding a fiscal document type is code, not configuration.
- Nobody can validate our XML against a reference implementation without writing one.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — no change: §5's rules on external calls already govern this
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [x] [`backend/pyproject.toml`](../../backend/pyproject.toml) — **remove** the comment announcing PyAfipWs; no dependency is added, since `httpx` and `defusedxml` are already there
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) — no change: no test calls ARCA
- [x] `backend/.env.example` — the WSFEv1 URLs (homologación and producción) and the adapter switch
- [ ] None

## References

- [ADR-0004](0004-arca-wsaa-access-tickets.md) — the access ticket this client consumes, and
  the ADR that deferred this decision to epic 5
- ADR-012 (Etapa 5) — **superseded by this ADR**
- HU-E5-03, HU-E5-04, HU-E5-05 and HS-T4 — the four operations that define the scope
- [`docs/aidlc/units.md`](../aidlc/units.md) — decision D13 of the epic 5 map
