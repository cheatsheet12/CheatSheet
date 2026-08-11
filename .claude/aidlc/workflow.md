# AI-DLC — CheatSheet workflow (minimal)

Five steps, three gates, two documents. Load this file when development work starts.

## Insumos — what already exists and is NEVER regenerated

| Input | Where | Status |
|---|---|---|
| Architecture, Context Map, dependency rules | `docs/architecture.md` | Decided (Etapa 5) |
| Architecture decisions | `docs/adr/` | Decided |
| Code standards | `CLAUDE.md` §5 · `docs/code-standards.md` | Decided |
| Branching, environments, credentials, CI | `docs/configuration-management.md` | Decided |
| Requirements, user stories (`HU-ID`), prototypes | Etapa 5 — imported into `docs/aidlc/inputs/` | Written |

This workflow **consumes** these. It never rewrites them, never re-elicits requirements, never
re-derives the architecture, and never asks a question they already answer (which database, which
architecture style, which branch naming). Changing any of them is an **ADR**, not a workflow step.

**One-time import**: if `docs/aidlc/inputs/` does not exist yet, ask the user where the Etapa 5
material lives, copy it in preserving every `HU-ID` and screen code verbatim, and commit that import
on its own. Never guess the location, never scan the filesystem for it, and never rewrite a story
while importing. From then on this repository is the working copy.

## The two documents

```
docs/aidlc/
├── inputs/            # imported once from Etapa 5 — read-only from here on
├── roadmap.md         # THE ORDER: the whole HU catalogue split into epics, once per system
├── units.md           # THE MAP: every unit, its owner context, its HUs, dependencies, state
└── units/<unidad>.md  # THE PLAN of one unit + the record of its gates
```

`units.md` is also the state tracker: there is no separate state file and no separate audit file.

Three planning moments, each with a different frequency:

| Documento | Cuándo | Quién |
|---|---|---|
| `roadmap.md` | **Una vez para todo el sistema** | El equipo, al arrancar |
| `units.md` | **Una vez por épico**, antes de que nadie codee | Quien lidera el épico |
| `units/<unidad>.md` | **Por unidad**, al tomarla | Quien la implementa |

---

# Paso previo — Roadmap (una sola vez, si `roadmap.md` no existe)

When the full HU catalogue exists and the system is at zero, the missing decision is not *what* to
build — it is **in what order**, and *where each epic ends*. That is this step, and it happens once.

It is not analysis: requirements and stories are already written. It is sequencing.

## How to split the catalogue into epics

1. **Read every story** in `docs/aidlc/inputs/` and the Context Map (`docs/architecture.md` §4).
2. **Cut vertically, not by context.** An epic is a thin end-to-end slice that ends in something
   demoable on `staging` — not "build `identity` completely, then `master_data`". Horizontal layers
   produce months with nothing to show; this project demos to the cátedra on `staging`.
3. **Order by dependency first, risk second.** Whatever every other story presupposes (a tenant, a
   logged-in user, business configuration) comes first. Among the rest, the riskiest Core contexts
   (`billing`, `payments`, `conversational`) come earlier rather than later — a surprise there is
   cheaper to absorb early.
4. **Every story lands in exactly one epic.** The roadmap doubles as the coverage matrix: a story in
   no epic is work nobody will do, and a story in two is a boundary that is wrong.
5. **Name what each epic makes demoable.** If an epic ends with nothing observable, it is a layer,
   not an epic — merge it into the one that consumes it.

```markdown
# Roadmap — CheatSheet

> Todas las HUs del sistema, repartidas en épicos ordenados. Cada épico termina en algo
> demostrable en `staging`. Ninguna HU queda afuera.

| # | Épico | HUs | Contextos | Termina en (demo) |
|---|---|---|---|---|
| 1 | [nombre] | HU-… | identity, business_config | [qué se puede mostrar funcionando] |
| 2 | … | | | |

## Cobertura
- HUs totales: [N] · asignadas: [N] · sin asignar: [ninguna / lista]

## Orden — por qué este y no otro
- [Qué presupone qué. Qué riesgo se adelantó deliberadamente y por qué.]

## Unidades técnicas (sin HU detrás)
- [Trabajo de cimientos que ninguna HU pide pero todo el resto necesita: arranque de la app,
  sesión de base de datos, infraestructura de migraciones, esqueleto de tests. Va dentro del
  épico 1, justificado por lo que habilita — nunca como épico propio ni como cajón de sastre.]
```

## ⛔ Aprobación del roadmap

Present it and wait. This decides the order of the whole project, so it is worth one careful pass.
Once approved it is stable: an epic may be re-cut later, but the catalogue is not re-split every
sprint.

From here on, each epic enters the flow through its own units map (1a).

---

# Paso 0 — Encuadre (no gate)

Before proposing anything:

1. Read the user story being implemented (`docs/aidlc/inputs/`), plus `docs/architecture.md` §3/§4/§5.
2. Read `docs/aidlc/units.md` if it exists — the unit may already be mapped, or may depend on one that
   is not finished.
3. Look at the code that already exists in the contexts involved.
4. State in **three lines**: which bounded context owns the change, which layers it touches, and which
   external integrations or migrations it implies.

If the story is ambiguous, or you cannot tell which context owns it, **ask now** — one interactive
question, in Spanish, with concrete options. A wrong ownership decision is expensive to undo later.

---

# Paso 1 — Plan de unidad — ⛔ GATE 1

## 1a. The units map (only when starting an epic, or when the map is missing the unit)

Create or update `docs/aidlc/units.md`. Good unit boundaries:

- owned by **one** bounded context wherever possible (a unit spanning contexts names the one that
  owns the write and how the others are reached: application service call or domain event);
- **vertical**: domain + application + infrastructure + tests for its slice, plus the frontend feature
  work when the story includes a screen. Never "the domain unit" and "the API unit" separately —
  those produce branches that cannot be verified on their own;
- **independently verifiable**: it can pass the gates without its siblings being finished;
- one unit = one `feature/<module>-<kebab-description>` branch = one PR to `develop`.

There is **one** `units.md` for the whole project: each mapping session appends its epic's rows. The
`Épico` column must match the epic's name in `roadmap.md` exactly — that is what ties the two
documents together.

```markdown
# Mapa de unidades

| Épico | Unidad | Contexto dueño | HUs | Depende de | Responsable | Rama | Estado |
|---|---|---|---|---|---|---|---|
| Facturación electrónica | emision-comprobante | billing | HU-12, HU-13 | — | Ana | feature/billing-emision-comprobante | en curso |
| Facturación electrónica | conciliacion-cobros | payments | HU-20 | emision-comprobante | Bruno | — | pendiente |

## Notas
- [Decisiones de descomposición que no son obvias, y por qué]
- [Trabajo requerido pero fuera de alcance de este épico]
```

Estados: `pendiente` · `en curso` · `en revisión` (PR abierto) · `mergeada`.

**Epic state is derived, never written down.** An epic with no rows has not been mapped; an epic whose
rows are all `mergeada` is finished; anything else is in progress. `.claude/hooks/aidlc_next.py` reads
both documents at session start and reports the current epic, who is on what, and the next unit whose
dependencies are already merged. Keeping a unit's `Estado` current is therefore not bookkeeping — it
is what the next developer sees when they open a session.

The map is built **once per epic**, in its own session, before anyone starts coding. That session is
the only planning ceremony left: it reads the stories, groups them into units, assigns an owner
context to each, and stops. It does not design them — each unit is designed in its own Gate 1, by
whoever takes it.

## 1c. Trabajo en paralelo

Several units run at the same time, one developer each. The rules that keep that from colliding:

- **`units.md` lives on `develop`.** A developer touches **only their own row** — claiming it
  (`Responsable`, `Rama`, state → `en curso`) and closing it (state → `en revisión`, then `mergeada`).
  Distinct rows are distinct lines, so git merges them without conflict. Two people editing the same
  row means two people took the same unit: that is the conflict surfacing correctly.
- **Adding or re-cutting units is not a developer's call mid-flight.** If the decomposition turns out
  wrong, say so and update the map deliberately, with the team — do not split a unit inside a feature
  branch.
- **The unit plan is per-unit** (`docs/aidlc/units/<unidad>.md`), created on the unit's own branch. It
  never conflicts with anyone else's.
- **A unit that depends on another** does not start until the dependency is merged into `develop`,
  unless the plan states exactly which interface it assumes and what it stubs meanwhile. Write that
  assumption in the plan; it is the first thing to re-check when the dependency lands.
- **Sync with `develop`** whenever a sibling unit merges: rebase or merge before continuing, so
  verification runs against what actually exists.

## 1b. The unit plan

Create `docs/aidlc/units/<unidad>.md`, in Spanish. This single document replaces application design,
functional design, NFR requirements, NFR design, infrastructure design and the code-generation plan.
Fill only the sections that apply, and write "No aplica" on the rest — explicitly, so the reader knows
it was considered.

```markdown
# Unidad: [nombre]

**HUs**: [HU-ID, …]   **Contexto dueño**: [uno de los doce]   **Rama**: feature/<módulo>-<desc>

## Qué hace
[2–4 líneas: el comportamiento observable que agrega esta unidad]

## Diseño
- **Dominio**: agregados, entidades, value objects y eventos que se crean o cambian
- **Aplicación**: el caso de uso (uno por servicio de aplicación) — entrada, salida, qué garantiza
- **Puertos y adaptadores**: qué puerto necesita el caso de uso y qué adaptador lo implementa
- **Otros contextos**: a cuáles se llega y cómo (servicio de aplicación o evento de dominio).
  ¿Es un edge que el Context Map ya permite? Si no → ADR primero (ver Escaladas)
- **Frontend**: qué `features/<contexto>` se tocan, qué expone su `index.ts`, qué ruta los compone

## Infraestructura
- **Migraciones**: tablas, columnas, índices; ¿reversible?; ¿backfill?
- **Trabajo asíncrono**: tarea, worker dueño, reintentos, qué la hace idempotente, schedule en Beat
- **Configuración**: variables nuevas y en qué `.env.example` (backend o frontend)
- **Integraciones externas**: proveedor, timeout, reintentos con backoff, manejo de falla,
  diferencia sandbox vs producción

## Riesgos que obligan a tests (marcar los que apliquen)
- [ ] Toca dinero (`Decimal`, redondeo `ROUND_HALF_UP`) → test de redondeo
- [ ] Toca comprobantes fiscales / CAE → irreversible en producción; test contra fixtures de ARCA
- [ ] Consume un webhook → test de entrega duplicada (un mismo evento, un solo efecto)
- [ ] Agrega datos con `tenant_id` → test de aislamiento entre tenants
- [ ] Usa salida de un LLM → test de validación por schema antes de cualquier efecto real
- [ ] Datos personales o fiscales → nunca se envían a un LLM sin anonimizar

## Archivos a tocar
- [ ] backend/src/cheatsheet/contexts/<contexto>/domain/…
- [ ] backend/tests/…
- [ ] frontend/src/features/<contexto>/…

## Casos de prueba
| # | Caso | Tipo | Estado |
|---|---|---|---|
| 1 | [qué valida] | unit / integración / contrato | pendiente |

## Registro
| Gate | Fecha | Resultado |
|---|---|---|
| 1 · Plan | [ISO] | aprobado / cambios pedidos: [cuáles] |
| 2 · Verificación | | |
| 3 · PR | | |

## Decisiones tomadas durante la unidad
- [Pregunta hecha al usuario → respuesta, en una línea. Solo lo que cambia el resultado.]
```

## ⛔ GATE 1 — approval before any code

Present the plan (and the map, if it changed) and **wait**. Do not write into `backend/` or
`frontend/` until the user approves. If changes are requested, update and re-present.

Record the outcome in the plan's Registro table.

---

# Paso 2 — Implementación (no gate)

Execute the approved plan. No further approval points: that is what Gate 1 bought.

- Work on the unit's branch, cut from an up-to-date `develop`. Writing while standing on `main` or
  `develop` is blocked by hook (`CLAUDE.md` §4).
- Respect the fixed layout and the dependency rules **R1–R5** — enforced by
  `.claude/hooks/guard_architecture.py` and by the `architecture` CI job.
- Apply the standards of `CLAUDE.md` §5: complete typing (`mypy --strict`), functions ≤ 50 lines,
  files ≤ 400, specific exceptions, `Decimal` for money, structured logging, timeout + retry +
  failure handling on every external call, tests with every module.
- Naming in English, except the domain's ubiquitous language in Spanish without accents
  (`Comprobante`, `Cobro`, `Turno`, `Mapeo`, `CUIT`, `CAE`, `CondicionIVA`).
- Tick the checkboxes in the plan **in the same interaction** in which the work is done.
- If the plan turns out to be wrong — a boundary does not hold, a hook blocks a step, the design does
  not survive contact with the code — **stop and say so**. Do not improvise around it and do not
  silently widen the scope.

---

# Paso 3 — Verificación — ⛔ GATE 2

Run the repository's real gates and read the output:

```bash
ruff format --check . && ruff check . && mypy . && pytest
cd frontend && npm run format:check && npm run lint && npm run typecheck && npm run test:coverage
```

Rules:
- **Never weaken a gate to make it pass**: no blanket `# noqa`, no `eslint-disable`, no lowering the
  coverage threshold, no excluding files, no `--no-verify`, never `CHEATSHEET_UNSAFE=1`. Fix the code.
- **Never report a result you did not observe.** If something fails, say so with the output.
- Tests never touch the network: ARCA/AFIP, MercadoPago, WhatsApp, the LLM provider and R2 are mocked.

Then complete the plan's Casos de prueba table and check the Definition of Done (`CLAUDE.md` §7),
including the two that are easy to forget: the right `.env.example` updated if an integration was
added, and an ADR written if an architectural decision was made.

**⛔ GATE 2**: present the real results and wait for the user before closing the unit.

---

# Paso 4 — Pull Request — ⛔ GATE 3

- `feature/<module>-<desc>` → **`develop`**, with `.github/pull_request_template.md` filled in and a
  link to the unit plan.
- CI green — lint, tests, `gitleaks`. A PR whose pipeline fails is not merged; the rule is automatic.
- **⛔ GATE 3**: `git push` and PR creation happen **only when the user explicitly asks**.
- Update `units.md`: state → `en revisión`, then `mergeada`. Close the Registro table in the plan.

Integrated validation and demos happen on **`staging`**, never on `prod` and never on a local
environment (`docs/configuration-management.md` §5).

---

# Escaladas — the only things that add ceremony

Each of these is triggered by evidence, never by default:

| Trigger | What it adds |
|---|---|
| The design needs a dependency edge the Context Map does not allow, or moves an aggregate between contexts | **ADR** approved before Gate 1 closes (`docs/adr/0000-template.md`). The rules are hook- and CI-enforced, so an undocumented edge blocks the code, not the review |
| A new external integration (a provider not already in `.env.example`) | A contracts section in the plan: endpoints per environment, auth, failure modes; plus contract tests |
| The work does not fit in one unit | Update `units.md` first, splitting it — then plan only the first unit |
| A new bounded context, or work with no user story behind it | Stop: that is analysis, not construction. Bring it back to Etapa 5 material or write the story first, with the user. **One exception**: a *unidad técnica* already declared in `roadmap.md` — foundation work no story asks for but everything needs. It must be in the roadmap, justified by what it enables; it is never invented mid-epic |
| Production emergency | `hotfix/<desc>` → `main`, then into `develop`. One-line plan, same gates 2 and 3 |

---

# Registro mínimo

The only record kept is inside the two documents:

- `units.md` — the state of every unit
- `docs/aidlc/units/<unidad>.md` — the Registro table (one line per gate) and the Decisiones list
  (one line per question that changed the outcome)

No `audit.md`, no verbatim transcription of every message, no question files. Git history and the PRs
carry the rest.
