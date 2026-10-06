# ADR-0012 — Count FAQ uses per calendar month in Argentina time, from an append-only event table, and show each FAQ's share before and after its last edit

- **Status:** Accepted (2026-10-05, by the owner of the conversational module)
- **Date:** 2026-10-04
- **Decided by:** Luciano Oro, owner of Atención y Escalamiento (HU-E9-04) in the Etapa 6 split
- **Modules affected:** conversational, frontend (reads one existing constant of the Shared Kernel, `shared/`)

---

## Context

HU-E9-04 RN-02 says: «El sistema muestra cuántas veces fue usada cada FAQ **en el período actual**»,
and its fourth acceptance criterion repeats «en el período». The story never says which period. The
only artefact that does is the prototype of PAN-WA-02
(`docs/aidlc/inputs/prototipos/agente-whatsapp.html:301`): «Respondida 47 veces **este mes**».
HU-E8-03 RN-04 adds that «el sistema registra el uso de cada FAQ para su análisis posterior».

What the code does today does not answer either rule:

- `faq.usos` is a single integer that only grows (migration 0021, `domain/faq.py:66`). It has no
  date, so no period can be computed from it: «en el período» on PAN-WA-02 actually shows the total
  since the FAQ was created. The DER (`docs/aidlc/inputs/der.md`, table `faq`) does not even have
  that column; the code added it.
- The agent increments the counter **before** sending the WhatsApp message
  (`application/agente.py:340-341`), so a use is counted even when the send fails and the customer
  received nothing.
- The increment is a read-modify-write of the whole row (`infrastructure/repositories.py:217-222`,
  `_faq_a_fila` copies every column). Two concurrent answers lose one increment, and an agent answer
  that overlaps an administrator's edit writes the old question and answer back over the new ones.
- The administrator has no way to know whether editing an FAQ helped. The business question behind
  RN-02 —is this answer doing its job?— needs a before/after comparison that a lifetime counter
  cannot give.

Constraints that frame the answer:

- `CLAUDE.md` §0 makes the story the acceptance criterion of a unit: a period definition that lives
  only in a plan is invisible to verification. The story must say it.
- The business operates in Argentina. A month computed in UTC moves the last three hours of every
  month (21:00–24:00 Argentina time) into the next one; that bug already exists twice in the
  repository (`docs/aidlc/TODO.md` §22.5 and §22.6).
- Dependency rule R3 forbids `conversational` from importing `reporting`, where the zone constant
  `ZONA_DEL_REPORTE` lives (`reporting/infrastructure/acl.py:69`). The Shared Kernel already
  publishes the same zone as `ZONA_ARGENTINA` (`shared/zona_horaria.py`, added with the unit
  `reserva-y-cancelacion-por-whatsapp`), and `conversational` already uses it.
- Meta retries webhooks. Whatever records a use must not record it twice for one inbound message.
- An FAQ is the only entity in the system that is really deleted (HU-E9-04 RN-03).

## Decision

We will count FAQ uses from an append-only table `faq_uso`, one row per answer the agent actually
sent, and we amend HU-E9-04 so that «el período actual» is **the current calendar month in
Argentina time (`America/Argentina/Buenos_Aires`)**; the listing shows uses **this month**, **in
the previous month** and **in total since creation**, and each FAQ's detail shows its **share of
FAQ answers before and after its last edit**.

The detail needed to implement it:

1. **What a use is.** A use is recorded when the agent answered a customer with that FAQ **and** the
   WhatsApp message was sent: the channel accepted it and the outgoing `Mensaje` was stored with a
   delivery status other than `FALLIDO`. A match below the similarity threshold is not a use
   (HU-E8-03 RN-03). A delivery failure that Meta reports later through a status callback does not
   retract the use: the use measures that the agent chose and sent that answer, and a phone that
   was off says nothing about the FAQ.
2. **One use per sent message.** Each row references the outgoing message (`mensaje_id`, unique).
   A retried webhook is already discarded by `uq_mensaje_externo_id` before any answer is produced;
   the unique `mensaje_id` makes the insert idempotent on its own (`ON CONFLICT DO NOTHING`).
3. **Append-only.** The application role gets `SELECT` and `INSERT` only on `faq_uso`, the same
   grant as `reembolso` (migration 0027) and `registro_de_auditoria` (migration 0001). RLS is
   enabled and forced with the `aislamiento_por_empresa` policy used by every company-scoped table.
   No row of `faq` is written when the agent answers, which removes the lost update.
4. **Months.** Month boundaries are computed from the injected clock in
   `America/Argentina/Buenos_Aires` and converted to UTC instants before querying. «This month» is
   `[first day of the current month 00:00 ART, first day of next month 00:00 ART)`; «previous
   month» is the month before it. The zone is the Shared Kernel's `ZONA_ARGENTINA`
   (`shared/zona_horaria.py`); no new constant is created.
5. **Total since creation.** Uses recorded before this decision cannot be dated. The existing
   counter is frozen as a baseline (`faq.usos_anteriores`, never written again) and the total is
   `usos_anteriores + rows in faq_uso`. The baseline is honest about what it is: it includes the
   uses counted under the old rule, failed sends among them, and it never counts towards a month.
6. **Share before and after the last edit.** For an FAQ last edited at instant `E`:
   - `L` = the smallest of 30 days, the whole days elapsed since `E`, and the whole days between
     the start of tracking for that FAQ and `E` (tracking starts at its creation, or when this
     decision was deployed for FAQs that already existed).
   - Window before: `[E − L, E)`. Window after: `[E, E + L)`.
   - Share in a window = the FAQ's uses in that window ÷ all uses of **any** FAQ of the company in
     that window (uses of FAQs deleted since then included), shown as a percentage with one
     decimal, rounded half up.
   - Edge cases: an FAQ **never edited** shows no comparison and says so; an FAQ edited **less
     than one day ago** shows no comparison yet; an FAQ edited **during its first day of tracking**
     has no history before the edit and says so; a window in which the company had **no FAQ
     answers at all** shows «sin consultas respondidas por FAQ» instead of a percentage (never
     0 % and never a division by zero).
   - «Edit» means a change to the question or the answer text. Saving the same text, or the
     background re-indexing of the vector, is not an edit; `faq.updated_at` is therefore not used
     (re-indexing writes it, `domain/faq.py:93`) and a dedicated `faq.editada_en` is.
7. **Deleted FAQs.** Deleting an FAQ keeps its rows in `faq_uso` with `faq_id` set to `NULL`
   (`ON DELETE SET NULL`), so the company-wide denominator of every other FAQ's share does not change
   retroactively when an unrelated FAQ is removed.

### Amended story

HU-E9-04 is amended in place and carries the marker `> Modificada por ADR-0012 (2026-10-04).`
under its heading, as ADR-0009 did. The exact text is in the appendix. That amendment is part of the
PR that accepts this ADR; the documents below change with the unit, together with the migration
and the code they describe.

### Other documents that change with the unit `usos-de-faq-por-periodo`

| Document | Change |
| --- | --- |
| `docs/aidlc/inputs/der.md` | Table `faq`: add `usos_anteriores`, `editada_en`, `seguimiento_desde`. New table `faq_uso` (BC9 section), with a note on append-only and `ON DELETE SET NULL` |
| `docs/aidlc/epicas/08-agente-de-whatsapp/pendientes.md` | New item: «El contador de usos de FAQ no tenía período» → resolved by unit `usos-de-faq-por-periodo` (ADR-0012) |
| `docs/aidlc/units.md` | The unit `usos-de-faq-por-periodo` (state `pendiente`), in the epic «Agente de WhatsApp y atención humana» |
| `docs/aidlc/TODO.md` §22 | New finding without a unit: besides the Shared Kernel's `ZONA_ARGENTINA`, the Argentina zone is still declared three more times (`reporting/infrastructure/acl.py:69`, `scheduling/domain/recurso.py:46`, `identity/domain/usuario.py:30`); those can point to the Shared Kernel. §22.5 and §22.6 gain the note that the constant they need is importable from `payments` |

The prototype (`docs/aidlc/inputs/prototipos/agente-whatsapp.html`) is an Etapa 5 input and is not
edited. It stays the source of «este mes»; the previous-month and total columns and the share
detail are an extension it does not draw, and the amended story is what describes them.

## Alternatives considered

| Alternative | Advantages | Why it was ruled out |
| --- | --- | --- |
| **Relabel only**: keep the lifetime counter and change «en el período» to «en total» | Zero schema change; one-line UI change | Contradicts the prototype («este mes»), leaves HU-E8-03 RN-04 («para su análisis posterior») without data to analyse, and keeps both bugs: failed sends counted and lost concurrent increments |
| **Two or three counter columns** (`usos_mes`, `usos_mes_anterior`, total) with a monthly rollover | Cheap reads; no new table | Needs a scheduled job exactly at 00:00 ART on the 1st; a missed or late run silently mixes two months; a counter incremented by the agent between the job's read and write is lost; still a read-modify-write on `faq`. It also cannot answer «N days before and after an edit», which needs arbitrary windows |
| **Monthly buckets table** (`faq_uso_mensual`: empresa, faq, month, count) with an upsert per use | Bounded growth (one row per FAQ per month); month queries are trivial | The upsert is still a counter (hot row under concurrency, idempotency per message impossible without a second structure); the month boundary is frozen at write time, so a zone mistake cannot be corrected afterwards; the before/after share needs day-level windows the buckets do not hold |
| **Rolling 30 days** instead of calendar months | No month boundary to get wrong | Contradicts the prototype («este mes») and HU-E10-01, which uses calendar months by default; the number changes every day without anything happening, which an administrator reads as an error. It still needs dated events underneath |
| **Append-only events table `faq_uso`** (chosen) | Any period or window is a query, computed in the right zone at read time; idempotent per sent message; no row is updated, so no lost update; traceable to the message that carried the answer | The table grows without a ceiling (one row per FAQ answer); the total is a count, not a column. Accepted: an SME answers in the thousands per month, and an index on `(empresa_id, faq_id, usado_en)` keeps the count an index scan |

## Consequences

**Positive**
- HU-E9-04 states a checkable period, and the screen shows what the prototype promised.
- A use means a message the customer could receive; failed sends no longer inflate the number.
- Concurrent answers never lose a count, and an agent answer can no longer overwrite an
  administrator's edit.
- The administrator can see whether an edit changed how often the agent picks that answer.
- Months are computed with the Shared Kernel's `ZONA_ARGENTINA`, the same constant the fixes of
  TODO §22.5 and §22.6 can use (payments cannot import reporting either).

**Negative / cost we accept**
- Uses before the deployment are a baseline without dates: they appear in the total and never in a
  month or in a share window.
- The baseline keeps the uses the old rule over-counted (failed sends). They cannot be told apart
  after the fact.
- A new table that grows with traffic and is never pruned.
- The HTTP field `usos` is replaced by three fields; its only consumer is the panel, deployed together
  with the API.

**What becomes harder from now on**
- Changing what counts as a use, or the comparison window, requires amending HU-E9-04 and citing the
  ADR that authorised it.
- Any future pruning of `faq_uso` must preserve the total, for example by folding pruned rows into
  `usos_anteriores` in the same transaction.

## Impact on repository rules

- [ ] [`CLAUDE.md`](../../CLAUDE.md) — directory structure or absolute rules
- [ ] [`docs/code-standards.md`](../code-standards.md)
- [ ] `ALLOWED_TOPLEVEL` in `.claude/hooks/guard_edit.py`
- [ ] [`pyproject.toml`](../../pyproject.toml) or the linter configuration
- [ ] [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [ ] `backend/.env.example` or `frontend/.env.example`
- [x] None

## References

- Story catalogue: [`docs/aidlc/inputs/historias-de-usuario.md`](../aidlc/inputs/historias-de-usuario.md)
  (HU-E9-04, HU-E8-03 RN-04, HU-E10-01)
- Prototype PAN-WA-02: `docs/aidlc/inputs/prototipos/agente-whatsapp.html:301`
- Unit plan: `docs/aidlc/units/usos-de-faq-por-periodo.md`
- Append-only precedent: migration `0027_reembolsos.py`; RLS check: `backend/scripts/verify_rls.py`
- [ADR-0009](0009-review-adjustments-scope-change.md) (precedent for amending the catalogue in place),
  [ADR-0001](0001-repository-structure.md) (rules R1–R5)
- `docs/aidlc/TODO.md` §22.5 and §22.6 (months computed in UTC)

---

## Appendix — amended HU-E9-04 (Spanish, to paste into `historias-de-usuario.md`)

The block replaces lines from `## **HU-E9-04 — Administrar el repositorio de FAQ**` up to (not
including) `# **Épica 10 — Reportería y Análisis**`.

```markdown
## **HU-E9-04 — Administrar el repositorio de FAQ**

> Modificada por ADR-0012 (2026-10-04).

| ID | HU-E9-04 |
| :---- | :---- |
| **Actor** | Administrador |
| **Acción Bloque K** | (métodos sobre FAQ) |
| **Descripción** | Como administrador, quiero agregar, editar y eliminar preguntas frecuentes del agente y ver cuánto se usa cada una, para que responda automáticamente las consultas más comunes de mis clientes y saber si mis cambios mejoran esas respuestas. |
| **Prioridad** | Media |
| **Complejidad** | Baja |
| **Pantalla** | PAN-WA-02 (Agente WhatsApp — Configuración) |

**Precondiciones**

* El usuario tiene sesión iniciada con rol Administrador.
* El agente está configurado y activo.

**Reglas de negocio**

* RN-01: Cada FAQ tiene una pregunta disparadora y una respuesta; ambos campos son obligatorios, conforme a la entidad FAQ.
* RN-02: El sistema muestra, por cada FAQ, cuántas veces fue usada **en el mes calendario en curso** («Este mes»), **en el mes calendario anterior** («Mes anterior») y **desde su creación** («Total»). Los meses se cuentan en hora de Argentina (America/Argentina/Buenos_Aires): un uso a las 23:30 del último día del mes pertenece a ese mes. Los usos registrados antes de esta modificación no tienen fecha: suman al total y no a ningún mes.
* RN-03: Una FAQ eliminada deja de estar disponible para el agente de forma inmediata.
* RN-04: No existe un límite en la cantidad de FAQ que una empresa puede configurar. De definirse a futuro un modelo de planes, podría incorporarse una restricción; en el alcance actual no aplica.
* RN-05: Un uso se cuenta una sola vez, cuando el agente respondió la consulta con esa FAQ **y** el mensaje de WhatsApp salió (no quedó como fallido). Una coincidencia por debajo del umbral de HU-E8-03 RN-03 no es un uso. Un mismo mensaje entrante reenviado por WhatsApp no genera un segundo uso.
* RN-06: El detalle de cada FAQ muestra su **participación** antes y después de su última edición: los usos de esa FAQ divididos por todas las consultas que el agente respondió con alguna FAQ de la empresa, en la misma cantidad de días antes y después de la edición (como máximo 30 días; menos si la edición o la FAQ son más recientes). Se informa como porcentaje con un decimal. Editar es cambiar el texto de la pregunta o de la respuesta.
* RN-07: Cuando la comparación no puede hacerse, el detalle lo dice en lugar de mostrar un porcentaje: si la FAQ nunca se editó, si se editó hace menos de un día, si se editó durante su primer día (no hay historia previa), o si en uno de los dos lapsos la empresa no tuvo consultas respondidas por FAQ.
* RN-08: Los usos de una FAQ eliminada siguen contando en el total de consultas respondidas de la empresa, para que la participación de las demás no cambie hacia atrás.

**Criterios de Aceptación**

| Cuando | Espero | Referencia |
| :---- | :---- | :---- |
| Agrego una FAQ nueva | Aparece en el listado con «Este mes», «Mes anterior» y «Total» en cero y disponible para el agente | PAN-WA-02 |
| Intento guardar una FAQ sin pregunta o sin respuesta | El sistema muestra “La pregunta y la respuesta son obligatorias.” y no permite guardar | PAN-WA-02 |
| Elimino una FAQ | El sistema solicita confirmación y, al confirmar, el agente deja de usarla de inmediato | PAN-WA-02 |
| Reviso el listado de FAQ | Cada una muestra cuántas veces fue respondida este mes, el mes anterior y en total | PAN-WA-02 |
| El agente responde con una FAQ el último día del mes a las 22:00 (hora de Argentina) | Ese uso cuenta en «Este mes» de ese mes y, desde el día 1, en «Mes anterior» | PAN-WA-02 |
| El agente encuentra la FAQ pero el WhatsApp no sale | El uso no se cuenta | PAN-WA-02 |
| WhatsApp reenvía el mismo mensaje entrante | La FAQ suma un solo uso | PAN-WA-02 |
| Abro el detalle de una FAQ editada hace 10 días | Veo su participación en los 10 días previos y en los 10 días posteriores a la edición | PAN-WA-02 |
| Abro el detalle de una FAQ que nunca edité | Veo que no hay una edición con la cual comparar | PAN-WA-02 |
| Abro el detalle de una FAQ editada en un lapso sin consultas respondidas por FAQ | Veo «Sin consultas respondidas por FAQ» en ese lapso, no un porcentaje | PAN-WA-02 |
```
