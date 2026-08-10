# docs — Internal technical documentation

| Document | Contents |
| --- | --- |
| [`architecture.md`](./architecture.md) | Working architecture reference: style, containers, the 12 bounded contexts, Context Map, enforced dependency rules, ports and patterns. **Read before writing backend code.** |
| [`code-standards.md`](./code-standards.md) | Normative code standards: style, typing, errors, money, logging, testing, AI/LLM components, security. Each rule states how it is enforced. |
| [`configuration-management.md`](./configuration-management.md) | Software configuration management plan: version control, branching, credentials, environments, CI and responsibilities. |
| [`adr/`](./adr/) | Architecture Decision Records — what was decided, why, and what was ruled out. |

The executable summary of the rules lives in [`../CLAUDE.md`](../CLAUDE.md), which every
agent loads at the start of a session.
