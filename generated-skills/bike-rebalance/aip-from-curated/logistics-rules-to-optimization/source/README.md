# logistics-rules-to-optimization — AIP conversion notes

Source: `original-SKILL.md` (curated Agent Skill from
`vendor/skillsbench/tasks/bike-rebalance/environment/skills/logistics-rules-to-optimization/SKILL.md`).

## Schema choice

Reused [`procedure.schema.json`](procedure.schema.json) from the bundled AIP
schema set. The source content is a five-step rule-translation workflow
(list entities → choose decision state → translate each business rule →
assemble the objective → extract and validate). That is a procedure /
execution graph, which is exactly what the procedure schema captures
(`purpose`, `trigger_when`, `steps`, `anti_patterns`, `scenarios`).

No new schema was needed.

## Script vs prose decisions

Per AIP best practice, script the deterministic / mechanical bits; leave
modeling judgment as prose. Every step in this skill hinges on **judging
which pattern fits a free-text business rule** — that is not scriptable
without losing the agent's reasoning. As a result, this skill has no
`scripts/` directory; the heavy lifting is in `references/` (lookup
tables, code snippets) loaded on demand.

| Source content | Compiled as | Why |
|---|---|---|
| Five-step rule translation workflow | five prose `steps` in the body | Each step is judgment-heavy: enumerate entities, pick variable types, classify rules, name objective components, validate the extracted solution. |
| "Common Logistics Rules" master table (business rule → variable → constraint) | `references/rule-patterns.md` | Reference lookup the agent consults while classifying each rule. Too large to keep in the body; loaded on demand. |
| Variable declaration scaffolds (binary / route arcs / visit indicator / quantity / load / inventory / time) | `references/variable-snippets.md` | Code snippets, on-demand from the `choose-decision-variables` step. |
| Constraint examples (capacity, quantity-when-active, soft demand, abs deviation, depot start/end, route continuity, global single-visit, load/state transition, time windows, inventory balance) | `references/constraint-snippets.md` | Code snippets, on-demand from the `translate-business-rules` step. |
| "Inventory Pickup/Dropoff Pattern" — full worked block on signed-service variables, station inventory limits, target deviation, load propagation, extraction | `references/pickup-dropoff.md` | Highly relevant for the bike-rebalance task. Kept as its own reference so the agent only loads it when the problem is rebalancing / material movement. |
| "Objective Assembly" — named components and patterns | `references/objective-assembly.md` | On-demand from the `assemble-objective` step. |

## Content classification (every source item)

- **Mapped** — Opening framing → `purpose`; "Rule Translation Workflow"
  steps 1–5 → five prose `steps` in the body; "Variable Patterns" section
  → `references/variable-snippets.md`; "Common Logistics Rules" table →
  `references/rule-patterns.md`; "Constraint Examples" subsections →
  `references/constraint-snippets.md`; "Inventory Pickup/Dropoff Pattern"
  → `references/pickup-dropoff.md`; "Objective Assembly" →
  `references/objective-assembly.md`; "Never use Python `abs()` on solver
  expressions" → `anti_patterns` + repeated in `constraint-snippets.md`
  for proximity; "Use the tightest possible M" → `anti_patterns` + noted
  in the relevant snippets; warning on global single-visit ("Do not add
  this rule when a large pickup/dropoff target may need multiple
  vehicles") → `anti_patterns` + noted in `constraint-snippets.md`;
  warning that per-vehicle route continuity does not stop other vehicles
  visiting → noted in `constraint-snippets.md` (and motivates the
  separate global single-visit snippet); recommendation to extract
  pickup/dropoff from a signed value with `max(...)` → kept verbatim in
  `pickup-dropoff.md`; advice to keep objective components named →
  `objective-assembly.md` and the `assemble-objective` step.
- **Schema gap** — none. The procedure schema accommodated everything.
- **Body drop** — none.
- **Deliberate drop** — none. The opening prose ("The goal is not only
  routing. The same translation pattern applies to transportation,
  dispatch, rebalancing, warehouse moves, staffing, scheduling,
  assignment, capacity planning, production, and service-level problems.")
  is folded into `purpose` and `trigger_when`.

## Additions beyond the source

The AIP body adds:

- A "How to pick a row" section in `rule-patterns.md` describing the
  classification step explicitly (conservation / capacity / linking /
  assignment / sequence / compatibility / soft penalty). The source
  implies this; the AIP version states it.
- "When NOT to use the signed-service form" in `pickup-dropoff.md`,
  covering cases where separate pickup/dropoff variables are required.
- A connectivity warning in `pickup-dropoff.md` (vehicle load is not a
  connectivity flow, so MTZ / DFJ / artificial flow is still needed) —
  consistent with the sibling `routing-subtour-elimination` skill.
- A "What goes in the objective vs the constraints" section in
  `objective-assembly.md`, plus calibration guidance on penalty weights.

These additions sharpen the modeling judgment without changing the
source's intent or vocabulary.
