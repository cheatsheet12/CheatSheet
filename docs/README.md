# docs — Internal technical documentation

| Document | Contents |
| --- | --- |
| [`architecture.md`](./architecture.md) | Working architecture reference: style, containers, the 12 bounded contexts, Context Map, enforced dependency rules, ports and patterns. **Read before writing backend code.** |
| [`code-standards.md`](./code-standards.md) | Normative code standards: style, typing, errors, money, logging, testing, AI/LLM components, security. Each rule states how it is enforced. |
| [`configuration-management.md`](./configuration-management.md) | Software configuration management plan: version control, branching, credentials, environments, CI and responsibilities. |
| [`adr/`](./adr/) | Architecture Decision Records — what was decided, why, and what was ruled out. |
| [`aidlc/`](./aidlc/) | Work products of the AI-DLC workflow: `inputs/` (requirements, user stories and prototypes imported from Etapa 5), `units.md` (the map of units of work and their state) and `units/<unidad>.md` (one plan per unit). Written in **Spanish** (declared exception to the language policy — see `CLAUDE.md`). |

The three documents above `aidlc/` are **inputs** to that workflow and are never rewritten
by it; changing one is an ADR.

The executable summary of the rules lives in [`../CLAUDE.md`](../CLAUDE.md), which every
agent loads at the start of a session. The workflow it points to is defined in
[`../.claude/aidlc/`](../.claude/aidlc/): `AIDLC.md` (always loaded, via the CLAUDE.md
import) and `workflow.md` (the five steps and three gates, loaded when work starts).
