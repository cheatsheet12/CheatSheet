# AI-DLC — the development workflow of this repository

**This is how work is done here. It is not optional and it is not something the user has to ask for.**

The analysis is already done: architecture, requirements, user stories, prototypes and code standards
exist (see "Insumos" in the workflow file). So this workflow does not re-plan the product — it takes a
user story and carries it to a merged Pull Request through **three gates**.

When the user requests any software development work — a feature, a fix, a refactor, a migration, a
screen — say in one line which unit of work it is, then load and follow:

- **`.claude/aidlc/workflow.md`** — the five steps, the three gates, the two document templates and
  the escalation rules.

## The three gates (nothing else stops the work)

1. **GATE 1 — Plan de unidad.** Nothing is written into `backend/` or `frontend/` until the user
   approves the unit plan. The first unit of an epic also approves the units map.
2. **GATE 2 — Verificación.** After implementing, run the repository's real gates and report the
   actual output. Wait for the user before closing the unit.
3. **GATE 3 — Pull Request.** `git push` and PR creation happen only when the user asks for them.

Between gates, work without stopping. Do not invent extra approval points, do not ask permission to
continue an approved plan.

## Non-negotiables

1. **`CLAUDE.md` outranks this workflow.** It decides what the code may look like; this decides how
   work is planned and approved. On conflict, the constitution wins.
2. **A gate is a real stop.** Never infer approval from silence or from an unrelated instruction.
3. **Never work around a hook.** If a plan can only be executed by breaking an enforced rule, the plan
   is wrong: stop, report, re-plan.
4. **Work products live in `docs/aidlc/`** and are written in **Spanish** (declared exception —
   `CLAUDE.md` §0). Code, commits, branches and ADRs stay in English.
5. **Ask interactively, in Spanish**, and record the answer in the unit plan. There are no question
   files to fill in.

## Where the work comes from

Two planning documents precede the gates, and each is written once:

- **`docs/aidlc/roadmap.md`** — the whole story catalogue split into ordered epics. Written **once for
  the system**. If it does not exist and the user asks to start building, that is the first thing to
  produce (Paso previo).
- **`docs/aidlc/units.md`** — the units of one epic, with their owner context, stories, dependencies
  and assignee. Written **once per epic**, before anyone codes.

Neither is analysis: requirements, stories, architecture and prototypes already exist and are
consumed, never regenerated.

## Resuming

If `docs/aidlc/units.md` exists, read it first: it is the map and the state. Pick up the unit marked
in progress and read its plan under `docs/aidlc/units/`. Resume — do not restart, and do not re-ask
what the plan already records.

## Trivial work

Conversation that produces no change — answering a question, explaining code, exploring the
repository — is not development work and needs no plan and no gates.

A change so small that the plan would be longer than the diff (a typo, a log message, a version bump)
is stated in one line and implemented directly, still on a correctly named branch and still through a
PR. When in doubt, write the plan: it is cheap.
