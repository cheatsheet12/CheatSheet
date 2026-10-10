# ADR-0014 — Reach ARCA with one platform certificate, through web service delegation

- **Status:** Accepted
- **Date:** 2026-10-08
- **Decided by:** Software Architect
- **Modules affected:** integrations, billing, reference_data, identity, frontend, infra
- **Supersedes:** the per-company credential of [ADR-0004](0004-arca-wsaa-access-tickets.md)
  (§Decision points 1 and 3). ADR-0004's signing, ticket reuse and encryption stand.

---

## Context

Until now every company connected ARCA by **uploading its own X.509 certificate and private
key** (HU-E2-01 RN-01, ADR-0004). Getting one means running `openssl` to produce a key and a
CSR, requesting the certificate at ARCA with a level-3 fiscal key, and uploading two files —
and doing it again every two years. For the small companies CheatSheet is built for, that is
the hardest step of the whole onboarding, and the one most likely to be abandoned.

Argentine invoicing products solve this in one of three ways (researched 2026-10-07):

1. **A certificate per company, uploaded by the company** — what CheatSheet did. Used by
   developer libraries (PyAfipWs, AFIP SDK).
2. **A certificate per company whose key and CSR the product generates** — TusFacturasAPP.
   The company never touches `openssl`, but still requests and renews a certificate.
3. **Delegation of the web service to the product's CUIT** — SOS Contador, Facturante, and the
   "tercerizar el servicio" path of ARCA's own *Documento Técnico Delegación de Webservices*.
   The company delegates «Facturación Electrónica» to the product's CUIT in the *Administrador
   de Relaciones*; the product calls ARCA with **one certificate of its own**, putting the
   company's CUIT in `<Auth><Cuit>`. The company handles no certificate at all.

**Model 3 was verified against ARCA homologación on 2026-10-08**, with a platform certificate
issued through WSASS:

- WSASS accepts an authorization whose *CUIT representado* differs from the certificate's
  («OK. Autorización fue creada (… CUITREPRESENTADO=30000000015, SERVICIO=ws://wsfe …)»).
- With that certificate's WSAA ticket, `FECompUltimoAutorizado` with `<Cuit>30000000015</Cuit>`
  answered HTTP 200 and `CbteNro 0`, without an authorization error.

So in homologación a **fictitious** company CUIT can be represented without any real
delegation, which keeps every test company in `staging` free of real tax data.

## Decision

**CheatSheet reaches every ARCA web service with one platform certificate, acting as the
representative of each company that delegated «Facturación Electrónica» to CheatSheet's
CUIT. Companies no longer upload certificates.**

1. **The platform credential is a deployment secret,** `ARCA_CREDENCIAL_PLATAFORMA`: the PEM
   certificate followed by its PEM private key, base64-encoded so it survives an environment
   variable. Required when `ARCA_ADAPTADOR=arca`; the process refuses to boot without it. It is
   never stored in the database and never reaches a company's row.
2. **Access tickets belong to the platform, not to a company.** WSAA issues one ticket per
   certificate and service and refuses a second while the first is alive (ADR-0004 §Context 1),
   so a per-company ticket would make the second company to connect fail for twelve hours.
   They live in a new table, `ticket_de_plataforma`, keyed by service, encrypted as before.
   It has no `empresa_id` and therefore no Row-Level Security; it holds no company data.
   **Gap in the DER**, declared here: the DER models what a company gives us, and a platform
   ticket is not that.
3. **`<Auth><Cuit>` is the company's CUIT**, recorded on its ARCA integration when it connects.
   It is never taken from the request body.
4. **"Connecting ARCA" becomes "verifying the delegation".** The panel explains the delegation
   steps and offers «Verificar delegación». The API takes the company's CUIT from `identity`
   (server side), and asks WSFEv1 `FECompUltimoAutorizado` on its behalf:
   - answer without errors 600/601 → connected; the CUIT is recorded on the integration;
   - errors 600 or 601 (*ValidacionDeToken*: the CUIT is not among the certificate's
     relations) → rejected: «ARCA no registra que esta CUIT haya delegado Facturación
     Electrónica en CheatSheet».
   The integration row keeps its NOT NULL credential column with a marker, not a secret.
5. **The status check asks the same question.** A delegation revoked at ARCA shows as not
   connected on the next check. It costs one WSFE call with a reused ticket.
6. **The padrón** (`ws_sr_padron_a5`) is asked with the platform ticket and
   `cuitRepresentada` = the platform's own CUIT. It no longer requires the company to have
   connected ARCA first — which also lets step 2 of the onboarding validate the CUIT
   (difference D-08 of the identity test script).
7. **The padrón has its own switch, `ARCA_PADRON_ADAPTADOR`** (defaults to `ARCA_ADAPTADOR`,
   never `simulado` in production). Asked for real on 2026-10-08, the homologación registry
   answered «does not exist» for the fictitious test CUITs (`30000000015`, `20222222223`) and
   returned test data even for a public CUIT (`33693450239` → «PRUEBA F713 WEB 2», no VAT
   status). So `staging` runs a **simulated padrón with a real WSFE**: every test company keeps
   fictitious data and invoicing still gets a real CAE. The real padrón was proven separately
   by that query. **Confirmed on 2026-10-10:** homologación granted a CAE to `30000000015`
   on point of sale 1, although its registry does not know that CUIT. A simulated padrón
   asks WSAA for no ticket.
8. **Points of sale are checked against ARCA only in production.** Homologación keeps no
   registry of them (`FEParamGetPtosVenta` → `602 Sin Resultados` for the same company it
   then gave a CAE), so outside production the alta of a point uses the stand-in's list.
9. **Production delegation:** each company, once, in *Administrador de Relaciones de Clave
   Fiscal* › Nueva relación › ARCA › WebServices › «Facturación Electrónica» › Representante:
   CheatSheet's CUIT. CheatSheet then accepts it in «Aceptación de Designación».
   **Homologación:** the platform owner authorizes each test CUIT in WSASS › «Crear
   autorización a servicio» (service `wsfe`, CUIT representado = the test company).

### Controls the CUIT now needs

With delegation, the company's CUIT decides **on whose behalf** documents are issued.

- **Unique across companies** — already enforced (`CuitYaRegistrado`), so one company cannot
  register another customer's CUIT.
- **Taken from `identity`, never from the request**, and recorded on the integration at the
  moment the delegation is verified; later edits of the company data do not change who
  invoices until ARCA is verified again.
- **Accepting a delegation is a manual act of the platform** («Aceptación de Designación»),
  and that is the ownership check: CheatSheet accepts a delegation only for a customer whose
  account it can tie to that CUIT. The residual risk — a company registering, before its
  owner does, the CUIT of someone who delegated to CheatSheet — is closed by that acceptance
  step, and must stay closed: automating the acceptance requires an ownership proof first.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| Keep model 1 (certificate per company) | Already implemented; no platform secret | The hardest onboarding step for the target user; a renewal every two years per company |
| Model 2 (product generates key and CSR per company) | No `openssl` for the company; architecture unchanged | The company still requests and renews a certificate at ARCA; less friction removed than model 3 |
| Platform tickets in Redis instead of a table | No migration | Outside the request's transaction: a ticket minted and then lost to a Redis restart locks the platform out of ARCA for twelve hours with no record of why |
| Platform tickets in `ticket_de_acceso` with a sentinel `empresa_id` | No new table | Row-Level Security would hide the row from every company but one; a fake company id is a lie in the only multi-tenant barrier the system has |
| Accept the CUIT in the connect request | Simpler endpoint | The CUIT decides who invoices; it must come from the company's verified data |

## Consequences

**Positive**
- A company connects ARCA in one ARCA screen and one button, and never renews anything.
- One certificate to renew every two years, for the whole platform.
- Fewer WSAA calls: one ticket per service for all companies.
- The padrón works from the first onboarding step.
- `staging` tests use fictitious CUITs authorized in WSASS: no real tax data.

**Negative / cost we accept**
- **The platform certificate is the most valuable secret of the system:** with it, anyone can
  invoice for every customer. It lives only in the deployment's secret store, is rotated
  when it expires or when anyone who handled it leaves, and never touches a laptop that is
  not the platform owner's.
- **Production needs a legal entity.** Technically any CUIT can be the representative; for
  `staging` it is the Software Architect's own. For production it must be a company's
  (e.g. an SAS) with its terms of service authorizing CheatSheet to issue on the customer's
  behalf — otherwise every customer's documents flow through one person's representation.
- **HU-E2-01 RN-01 changes**: the credential is no longer the company's certificate but its
  delegation. Recorded in `docs/aidlc/inputs/historias-de-usuario.md`.
- Existing per-company ARCA integrations (only in `staging`; production has none) must be
  verified again. The per-company ticket table stays, unused by the real adapter, until a
  later migration drops it.
