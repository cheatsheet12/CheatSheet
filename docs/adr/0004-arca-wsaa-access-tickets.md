# ADR-0004 — Sign WSAA login tickets in `integrations`, and publish the access ticket

- **Status:** Accepted
- **Date:** 2026-08-19
- **Decided by:** Software Architect
- **Modules affected:** integrations, billing, reference_data, identity, platform, infra

---

## Context

Every ARCA web service — WSFEv1 for issuing documents, `ws_sr_padron_a5` for looking up a
CUIT — is reached the same way. The caller signs a short XML **login ticket request** with the
company's X.509 certificate and private key, base64-encodes the resulting CMS/PKCS#7 blob,
posts it to **WSAA**, and receives an **access ticket (TA)**: a `token` and a `sign` that
authenticate every subsequent call. Nothing at ARCA can be reached without one.

Four constraints shape everything below, and each of them is a hard fact about the provider
rather than a preference:

1. **A TA is valid for 12 hours, and WSAA refuses to issue a second one while the first is
   alive.** Asking again returns a fault — *"El CEE ya posee un TA valido para el acceso al WSN
   solicitado"*. A system that does not keep the ticket it was given cannot authenticate again
   for up to twelve hours. This makes ticket storage a correctness requirement, not a
   performance optimisation.
2. **A TA is per `(CUIT, service)`.** The ticket that authenticates invoicing does not
   authenticate the padrón lookup. One company holds several at once.
3. **The credential is per company**, unlike the platform-wide Google OAuth client of epic 1.
   It is the company's fiscal identity: whoever holds the certificate and its private key can
   issue tax documents in that company's name, irreversibly.
4. **[ADR-0003](0003-integrations-open-host-service.md) point 3 forbids the decryption from
   leaving `integrations`.** The service returns something usable, never ciphertext and never
   the key.

Constraints 3 and 4 together create the problem this ADR exists to settle: `billing` needs to
call WSFE, calling WSFE needs a TA, and getting a TA needs the private key — which `billing`
is not allowed to have. Somebody has to hold that seam, and deciding it after epic 5 starts
means discovering it as a blocker.

There is also a tooling question. The Etapa 5 design documents recorded **ADR-012 — ARCA via
PyAfipWs (WSFEv1, SOAP)**, and `backend/pyproject.toml` notes PyAfipWs as arriving with this
epic. WSFEv1 is a large surface with real fiscal semantics, and that decision is about issuing
documents. WSAA is a different service: one operation, one XML document, one signature.

## Decision

> We will **obtain and hold ARCA access tickets inside `integrations`**, sign the login ticket
> request with the `cryptography` library already in the dependency list, persist each ticket
> encrypted in its own table keyed by `(empresa_id, servicio)`, and **publish a use case that
> returns a valid ticket** to any context that needs one.

Six points of detail, so no one has to ask again:

1. **The CMS signature is produced by `cryptography`, not by PyAfipWs.** A login ticket request
   is a fifteen-line XML document signed once with `PKCS7SignatureBuilder(...).sign(DER,
   [PKCS7Options.Binary])`. `cryptography` 43 is already a runtime dependency — it is what
   encrypts the credentials at rest — and it does this natively, in-process.

2. **ADR-012 stands and is not superseded.** It decides how `billing` talks to **WSFEv1**, and
   epic 5 makes that call. This ADR decides how anything authenticates to **WSAA**, which is a
   separate service. If epic 5 adopts PyAfipWs for WSFEv1, it receives a ready TA from here and
   supplies it; PyAfipWs accepts an externally obtained ticket.

3. **The ticket is persisted, encrypted, in a new table `ticket_de_acceso`.** This is **gap
   H11** — the DER has no such entity, because it models the credential and not the session
   derived from it. Columns: `empresa_id`, `servicio`, `contenido_cifrado`, `algoritmo`,
   `expira_en`, unique on `(empresa_id, servicio)`. Row-Level Security by `empresa_id` like
   every other company-scoped table. The token and sign are secrets, so they are encrypted with
   the same AES-256-GCM adapter and the same key generation marker as the credentials.

4. **Redis is not the store.** A Redis restart loses a ticket that ARCA still considers alive,
   and the company is locked out of ARCA until it expires — an infrastructure restart turned
   into a functional outage of up to twelve hours. Durability here is not about speed.

5. **`ObtenerTicketDeAcceso` is part of the published contract of the Open Host Service.** It
   takes an `empresa_id` and a service name and returns a token, a sign and an expiry — never
   the certificate, never the private key, never the ciphertext. It refreshes transparently
   when the stored ticket is within its renewal margin, and returns the stored one otherwise.
   This is the same shape as point 3 of ADR-0003, applied to a derived credential.

6. **Expiry is read locally whenever possible.** An X.509 certificate carries its own
   `notAfter`, so answering "is this integration still valid?" costs no network call and burns
   no ticket. WSAA is consulted when the credential is first connected and when a ticket
   actually has to be minted — not every time a screen is refreshed.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **PyAfipWs for WSAA as well** | Consistent with ADR-012; one library for everything ARCA | It performs the CMS signature by shelling out to the `openssl` binary or through `M2Crypto`, depending on version. Both put a private key on a command line or into a C extension we do not otherwise carry, for a signature `cryptography` already performs in-process. The dependency is worth its weight for WSFEv1's fifty operations; for one XML document it is not |
| **Redis with a 12-hour TTL** | No migration, no table, naturally expiring | Loses tickets ARCA still considers valid. The failure is silent and lasts up to twelve hours, and it is triggered by an ordinary infrastructure restart rather than by anything the user did |
| **No cache: request a ticket per operation** | Simplest possible code | Breaks against the provider's own rule. The second live check within twelve hours fails with an ARCA fault that has nothing to do with what the user pressed |
| **Two extra columns on `configuracion_de_integracion`** | No new table | A ticket is per service and a configuration is per system: one company holds a WSFE ticket and a padrón ticket at once. Columns force a 1:1 that the provider does not have, and the padrón unit is the very next one to need the second row |
| **`billing` obtains its own ticket** | No new published operation; each context self-sufficient | Requires the private key to reach `billing`, which contradicts ADR-0003 point 3 and puts the company's fiscal identity in a second place. The whole reason `integrations` is an Open Host Service is that this seam exists once |
| **A shared `platform/arca.py`** | Reusable by any context | `platform/` is importable by everything, so a signer living there means the capability to authenticate as a company is reachable from anywhere. Same reasoning that kept the cipher inside `integrations/infrastructure/` |

## Consequences

**Positive**

- The private key has exactly one home, and the number of modules that can decrypt it stays at
  one. That claim is enforced by rule R3 rather than by convention.
- Epic 5 starts with the authentication problem already solved: it asks for a ticket and calls
  WSFE.
- The padrón unit — the next one — gets its ticket from the same place with a different service
  name, and needs no new mechanism.
- No new runtime dependency. `cryptography` was already there for the credentials at rest.

**Negative / cost we accept**

- A new table the DER does not have (gap H11), which has to be justified to whoever reads the
  DER alongside the code.
- Tickets are secrets living in the database, so a second kind of encrypted material now
  depends on `SECRETS_ENCRYPTION_KEY`. Rotating that key means re-encrypting them too — though
  unlike credentials, tickets can simply be discarded and re-minted after expiry.
- Writing the CMS signature ourselves means owning it. It is about forty lines and it is
  covered by contract tests, but it is ours.

**What becomes harder from now on**

- Adding an ARCA service is no longer only an adapter: it also means naming a service in the
  ticket table's vocabulary.
- Any change to how tickets are stored touches a published operation of the Open Host Service,
  so it needs the same care as any other contract change.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [x] `backend/.env.example` — the WSAA endpoints per environment, and the removal of
      `AFIP_CERT_PATH` / `AFIP_KEY_PATH`, which describe a platform-wide certificate this
      decision confirms does not exist
- [ ] None

## References

- [ADR-0003](0003-integrations-open-host-service.md) — `integrations` as an Open Host Service;
  point 3 is what this ADR extends to a derived credential.
- **ADR-012** of the Etapa 5 design documents — ARCA via PyAfipWs (WSFEv1). Complemented, not
  superseded: see point 2.
- HU-E2-01 (RN-01 … RN-04) and the D1 debt of HU-E1-02, which the padrón unit closes using the
  ticket this ADR publishes.
- [`docs/architecture.md`](../architecture.md) §7 — the port and adapter table.
