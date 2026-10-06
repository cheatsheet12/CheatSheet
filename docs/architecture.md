# Architecture

Working reference for CheatSheet. It condenses the decisions taken during
the design stage (Etapa 5) into the form an engineer — or an agent — needs while
writing code.

**Source of truth for the reasoning:** the design documents (Artefacto 2.1–2.4 and
Anexo 4), which hold the full ADR-001 … ADR-012 with their alternatives and
trade-offs. This file does not restate that reasoning; it states the resulting rules
and points at where each one was decided.

---

## 1. Style

**Modular monolith with specialised asynchronous workers.**

One FastAPI process hosts all twelve bounded contexts as internal modules. The DDD
boundaries exist **at the code level only** — folders and import rules — not as
separate processes.

Why not microservices (ADR-001): 20 companies, ~215 MB/month, a team of six over six
months. The operational cost of a distributed system is not justified. The modular
boundaries keep the option of extracting a context into its own service later.

**The cost of this choice is discipline.** ADR-001 says so explicitly: the boundaries
hold only if the dependency rules are respected. In this repository those rules are
not left to code review — see §5.

---

## 2. Containers

| # | Container | Technology | Responsibility |
| --- | --- | --- | --- |
| 1 | Browser SPA | React 18 / Next.js 14 (App Router) | Renders the admin panel |
| 2 | Web frontend | Next.js 14 on Vercel | Serves the SPA (SSR/ISR); holds JWT cookies; minimal BFF |
| 3 | **API backend** | Python 3.11+ / FastAPI / Uvicorn | REST API, use-case orchestration, authn/authz + RLS, inbound webhooks |
| 4 | Worker — sync integrations | Celery | ARCA issuance, MercadoPago links, outbound WhatsApp |
| 5 | Worker — spreadsheet processing | Celery | Batch upload, row-by-row processing, mapping |
| 6 | Worker — incremental sync | Celery | Google Sheets read + protected-sheet write-back |
| 7 | Worker — notifications | Celery | Transactional email, payment reminders, internal notices |
| 8 | Worker — AI / NLP | Celery | LLM calls (mapping + intent), audio transcription, embeddings |
| 9 | Scheduler | Celery Beat | Periodic tasks. **Singleton — never replicated** |
| 10 | Main database | PostgreSQL 16 + `pgvector`, `btree_gist` | Every aggregate; multi-tenant RLS |
| 11 | Cache / broker | Redis 7 | Celery broker; ephemeral conversation state (1 h TTL); rate limiting |
| 12 | Object storage | Cloudflare R2 (S3 API) | Batch spreadsheet files, document PDFs, generated reports |

Five workers rather than one (ADR-003) so a burst of spreadsheet processing cannot
block the issuance of a tax document, and a slow LLM call cannot starve reminders.

---

## 3. The twelve bounded contexts

| Directory | BC | Category | Root aggregates |
| --- | --- | --- | --- |
| `identity` | BC1 | Generic | `Empresa`, `Usuario` |
| `master_data` | BC2 | Supporting | `Cliente`, `Servicio`, `CategoriaEmpresa` |
| `business_config` | BC3 | Supporting | `ReglaDeNegocio`, `PlantillaDeNotificacion` |
| `integrations` | BC4 | Generic | `ConfiguracionDeIntegracion` |
| `spreadsheet_sync` | BC5 | **Core (primary)** | `Mapeo`, `VinculoDePlanilla`, `ProcesamientoDePlanilla` |
| `billing` | BC6 | Core | `Comprobante`, `PuntoDeVenta` |
| `payments` | BC7 | Core | `Cobro` |
| `scheduling` | BC8 | Core | `Turno`, `RecursoReservable` |
| `conversational` | BC9 | Core | `Conversacion`, `Mensaje`, `Escalamiento`, `FAQ` |
| `observability` | BC10 | Generic | `RegistroDeAuditoria`, `Notificacion`, `TareaAsincrona`, `SolicitudDeSoporte` |
| `reporting` | BC11 | Supporting | `Reporte`, `PaqueteContable` |
| `reference_data` | BC12 | Supporting | `ParametroFiscal` |

27 root aggregates, 7 internal entities, 111 domain events.

---

## 4. Context Map — who may depend on whom

`SK` Shared Kernel · `C/S` Customer/Supplier · `OHS` Open Host Service.

| Upstream | Downstream | Type | What flows |
| --- | --- | --- | --- |
| `identity` | all | SK | `empresa_id`, `usuario_id` |
| `master_data` | billing, payments, scheduling, conversational | C/S | `Cliente`, `Servicio` as reference data |
| `reference_data` | billing, reporting | C/S | Effective `ParametroFiscal` for issuance validation |
| `business_config` | payments, scheduling, conversational | C/S | `ReglaDeNegocio`, `PlantillaDeNotificacion` |
| `spreadsheet_sync` | master_data | C/S | Requests creating/updating `Cliente` and `Servicio` |
| `spreadsheet_sync` | billing | C/S | Requests historical documents on initial load |
| `billing` | payments | C/S | `Comprobante` data a `Cobro` may reference (optional) |
| `payments` | billing | C/S via events | `PagoConfirmado`; billing updates the derived balance |
| `scheduling` | billing | C/S | A completed `Turno` may request issuance |
| `conversational` | scheduling, payments, billing | C/S | The agent translates intents into use-case calls |
| `conversational` | payments, scheduling, business_config | C/S, wired only in the composition root | The WhatsApp channel to Meta: send a text or an approved template and get Meta's message id back; submit a template and read its approval status ([ADR-0011](adr/0011-outbound-whatsapp-channel-via-composition-root.md)) |
| all | `observability` | OHS | Auditable events and notifications |
| `integrations` | identity, master_data, spreadsheet_sync, billing, payments, conversational | OHS | Validated external credentials and connection status ([ADR-0003](adr/0003-integrations-open-host-service.md)) |
| Core contexts | `reporting` | C/S | Consolidated data for reports and accounting packages |

`billing` ↔ `payments` is **one-directional Customer/Supplier, not a Partnership**.
`payments` does not need `billing` to exist. `billing` reacts to `PagoConfirmado` to
keep the document's derived balance; `payments` never writes into the billing
aggregate.

The two **OHS** rows describe opposite flows, which is worth reading twice.
`observability` is written into: audit events travel one way and nothing comes back.
`integrations` is read from: a context asks for a credential and gets a usable one —
never the ciphertext, never the key, which stay inside that context. Both are Generic,
both depend on nobody, and neither knows who its clients are. The downstream list on
the `integrations` row is informative, not a whitelist ([ADR-0003](adr/0003-integrations-open-host-service.md)).

---

## 5. Dependency rules — enforced, not reviewed

Five rules, checked by `.claude/hooks/guard_architecture.py` (blocks the write locally)
and by the `architecture` CI job (`--scan`, blocks the merge):

| # | Rule | Why |
| --- | --- | --- |
| **R1** | `domain/` imports nothing from `application/`, `infrastructure/`, or any framework | The domain describes the business, not how data is stored, served or transported. Keeps it testable with no I/O. |
| **R2** | `application/` imports nothing from `infrastructure/` | Application defines ports; infrastructure implements them. Dependency Inversion. |
| **R3** | No module imports another context's `domain/` or `infrastructure/` | Contexts talk through the other's `application/` layer or through domain events. This is the boundary that makes extraction possible later. |
| **R4** | `shared/` imports nothing from `contexts/` | Everyone depends on the Shared Kernel, so it must depend on nobody. |
| **R5** | *(frontend)* `frontend/src/features/X` never imports the internals of `features/Y` — only its `index.ts`; `shared/` imports no feature | The frontend counterpart of R3/R4. A screen composing several contexts does so in the route, not through a cross-feature import (ADR-0002). |

Dependencies point inwards only: `infrastructure → application → domain`.

R1–R4 apply to `backend/src/cheatsheet/**`, R5 to `frontend/src/**`.

ESLint carries a `no-restricted-imports` rule so the **alias** form
(`@/features/x/...`) also surfaces in the editor. It cannot catch the **relative**
form (`../../payments/hooks/x`): ESLint matches the literal specifier, and a relative
path into another feature contains no marker to match on. The hook and the CI scan
resolve the path, so they catch both — ESLint is a convenience, not the gate.

---

## 6. Layout of a bounded context

```
backend/src/cheatsheet/contexts/billing/
├── domain/              # Comprobante, PuntoDeVenta, value objects, domain events
├── application/         # Application Services (one use case each) + ports.py
└── infrastructure/      # ARCA adapter, PostgreSQL repositories, routers, Celery tasks
```

**Naming.** Everything is in English — layers, technical modules, comments — **except
the ubiquitous language of the domain, which stays in Spanish and without accents**:
`Comprobante`, `Cobro`, `Turno`, `Mapeo`, `CUIT`, `CAE`, `CondicionIVA`,
`PuntoDeVenta`. A `Comprobante` is not an "invoice": it is an Argentine fiscal
document type, and `CAE`/`CUIT` are legal terms. Translating them would break
traceability with the design documents and with ARCA itself.

---

## 7. Ports and adapters

| Port (declared in `application/`) | Adapter (in `infrastructure/`) | Context |
| --- | --- | --- |
| `PortEmisionFiscal` | ARCA via PyAfipWs (WSFEv1, SOAP) — ADR-012 | `billing` |
| `PortCobro` | MercadoPago (REST) | `payments` |
| `PortMensajeria` | WhatsApp Cloud API. Also consumed by `payments` (`EnvioPorWhatsApp`) and `scheduling` (`AvisoPorWhatsApp`) through a local structural `Protocol`, wired only in the composition root (`api/mensajeria.py`) — [ADR-0011](adr/0011-outbound-whatsapp-channel-via-composition-root.md) | `conversational` |
| `PortPlanilla` (read + write-back) | Google Sheets / Excel Online | `spreadsheet_sync` |
| `PortModeloDeLenguaje` | LLM provider (mapping, intent, embeddings) | `spreadsheet_sync`, `conversational` |
| `PortTranscripcion` | Audio transcription service | `conversational` |
| `PortNotificacionEmail` | Transactional email provider | `reporting`, `payments` |
| `PortEmisorDeTickets` | ARCA WSAA (SOAP, CMS signed with `cryptography`) — [ADR-0004](adr/0004-arca-wsaa-access-tickets.md) | `integrations` |
| `PortConsultaDePadron` | ARCA padrón A5 (SOAP, `getPersona`) | `integrations` |
| `PortPadron` | The integrations Open Host Service, behind an ACL | `identity` |
| `PortAutorizacionOAuth` | MercadoPago OAuth2 authorization URL (PKCE S256) | `integrations` |
| `PortMemoriaDeAutorizacion` | Redis, with a ten-minute TTL — where a `state` waits out the round trip | `integrations` |
| `PortRenovacionDeCredencial` | MercadoPago `/oauth/token` with `grant_type=refresh_token` | `integrations` |
| `PortRepositorio<Aggregate>` | PostgreSQL repository (asyncpg) | all |

Every external integration sits behind its own **Anti-Corruption Layer** (ADR-008):
one per provider, never a generic one. The domain never sees a provider's types,
names or protocols.

---

## 8. Rules that constrain everyday code

**Multi-tenancy (ADR-002).** Shared schema + PostgreSQL Row-Level Security by
`empresa_id` — the column name the DER uses, and the word the business uses. Every
request and every task sets `app.current_empresa` from the authenticated context, for
the duration of that transaction only. RLS is the second barrier: application
authorization can have a bug and one company's data still will not reach another.

Two conditions have to hold or the policies are decorative, and both are easy to get
silently wrong:

- **The application must not own the tables.** PostgreSQL exempts a table's owner from
  its own policies, so migrations run as the owner and the application connects as
  `cheatsheet_app`. Tables also carry `FORCE ROW LEVEL SECURITY`.
- **The failure must be closed.** A session that never announces its company sees no
  rows at all, rather than erroring in a way somebody is tempted to "fix" by disabling
  the policy.

Of the 34 tables, **25 carry `empresa_id` and a policy**; the 7 internal entities are
protected through their parent; `empresa` is the tenant itself and `parametro_fiscal` is
ARCA's global catalogue.

**Source of truth is partitioned (ADR-006).**

- Master data (`Cliente`, `Servicio`): **the company's spreadsheet wins**. CheatSheet
  reflects; it does not invent. Each record carries `origen` (PLANILLA/PANEL/AGENTE)
  and `presente_en_planilla`.
- Transactional data (`Comprobante`, `Cobro`, `Turno`): **CheatSheet wins**. The CAE,
  MercadoPago identifiers and lifecycle states are governed by the system.

**Never delete (ADR-007).** A record that disappears from the spreadsheet is marked
`presente_en_planilla = false`, never removed. A `Cliente` with issued documents must
survive. This is a fiscal traceability requirement, not a preference.

**Processing guarantees (ADR-009).** Every async task and inbound webhook carries a
`ClaveDeIdempotencia` (company + type + payload fingerprint). Retries use exponential
backoff with jitter. After N failures the task goes to the DLQ and emits
`TareaAsincronaDerivadaADLQ`. Webhooks are received by the API, which validates the
signature, persists the event, and only then enqueues the real work.

**Single Table Inheritance for `Comprobante` (ADR-010).** One table, one type
discriminator. Type-specific columns are nullable, so "required for this type" must be
imposed with conditional `CHECK` constraints or inside the aggregate — the schema
alone cannot guarantee it.

**Security (ADR-011).** OWASP ASVS Level 2. Argon2id for passwords, AES-256-GCM for
integration secrets (key held outside the database), short-lived JWT access tokens in
HttpOnly cookies issued by the BFF, opaque rotating refresh tokens with reuse
detection, RBAC with three fixed roles, HMAC validation on every inbound webhook.

**The conversational agent proposes; the code decides.** The LLM can only trigger the
closed catalogue of domain intents. Every action goes through the corresponding
Application Service, which re-validates permissions and invariants. Model output that
leads to an action is validated against the domain first.

---

## 9. Design patterns

Backbone patterns, in the order you will meet them:

- **State** — the transactional machines: `Comprobante` (BORRADOR → VALIDADO →
  ENVIADO_A_ARCA → AUTORIZADO / RECHAZADO → ANULADO), `Turno`, `Cobro`,
  `TareaAsincrona`. Implemented as an enum plus transition methods validated inside
  the aggregate, not one class per state.
- **Strategy** — batch vs incremental sync, mapping per spreadsheet format, retry
  policy per task type, report output format, authorization policies.
- **Observer** — delivery of domain events between contexts.
- **Command** — every Celery task, carrying its idempotency key.
- **Adapter** — the building block of every ACL.

Supporting: Factory Method (STI subtype resolution), Abstract Factory (provider
adapter families), Builder (report assembly), Template Method (spreadsheet pipeline),
Chain of Responsibility (inbound message handling, fiscal rule engine), Decorator
(FastAPI middlewares), Proxy (Redis read cache), Snapshot (fiscal snapshots).

**Deliberately rejected:** Singleton, Event Sourcing, Saga / Process Manager, full
CQRS, Visitor, Microkernel, Flyweight, Specification, and the textbook class-per-state
State pattern. Each rejection is argued in the design documents — do not reintroduce
them without an ADR.

**Outbox vs state reconciliation.** Outbox is used only where the event is the sole
durable carrier of a cross-context intent (`PagoConfirmado` → balance;
`ComprobanteAutorizado` → write-back + notification). Where the aggregate already
persists the intent in its state machine, a periodic sweeper re-enqueues instead
(ARCA issuance from `VALIDADO`). There is no universal Outbox.

---

## 10. Open questions carried into implementation

These were explicitly deferred by the design stage. They are not oversights — do not
resolve them silently in a PR; each needs its own decision.

| # | Question |
| --- | --- |
| 8.1 | Field mutability rules for `Cliente`/`Servicio` after transactional use |
| 8.3 | Sheet-to-sheet links when write-back uses a separate sheet |
| 8.4 | Reconciliation when the company edits a row marked as written by CheatSheet |
| 8.5 | Google Sheets range protection via Service Account |
| 8.7 | Versioning strategy for `Mapeo` |
| 8.8 | Frequency and trigger for `SincronizarParametrosFiscales` from ARCA |
| — | N (retry threshold) and backoff parameters per task type |
| — | Circuit Breaker library and configuration (ARCA first, then MP/WhatsApp) |
