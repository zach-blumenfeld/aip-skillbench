# scip-opt — AIP conversion notes

Source: `original-SKILL.md` (curated Agent Skill from
`vendor/skillsbench/tasks/bike-rebalance/environment/skills/scip-opt/SKILL.md`).

## Schema choice

Reused [`procedure.schema.json`](procedure.schema.json) from the bundled AIP
schema set. The source content is a multi-step modeling workflow ending in an
extraction-and-validation pass — that is a procedure / execution graph, which
is exactly what the procedure schema captures (`purpose`, `trigger_when`,
`steps`, `anti_patterns`, `scenarios`).

No new schema was needed.

## Script vs prose decisions

Per AIP best practice, script the deterministic / mechanical bits; leave
modeling judgment as prose.

| Source content                              | Compiled as | Why |
|---------------------------------------------|-------------|-----|
| PySCIPOpt availability check                | script (`scripts/check_pyscipopt.py`) | Deterministic import probe; same code every call. |
| Reproducibility parameter set + try/except  | script (`scripts/configure_reproducibility.py`) | Fixed list of SCIP params with a known fallback rule — the canonical "lookup table + numeric/boolean settings" case. |
| Identify sets / variables / constraints     | prose step | Modeling judgment over problem-specific inputs — cannot be scripted without losing the agent's reasoning. |
| Pattern snippets (assignment, route arcs, MTZ, abs deviation, binary activation) | `references/patterns.md` | Loaded on demand based on the problem at hand; keeps body under the progressive-disclosure budget. |
| Minimal end-to-end template                 | `references/template.md` | Reference scaffold; the agent reads it when it needs a starting point. |
| Extraction + independent validation         | `references/validation.md` + prose step | The reconstruction logic is problem-specific; the file documents the pattern. |

## Content classification (every source item)

- **Mapped** — When-to-use bullets → `trigger_when`; modeling workflow steps
  1–7 → `steps`; PySCIPOpt import guard → `verify-pyscipopt` step + script;
  minimal template → `references/template.md`; common patterns (binary
  activation, assignment, absolute deviation, route arcs, MTZ) →
  `references/patterns.md`; reproducibility helper → `scripts/`;
  extraction-and-validation → `reconstruct-and-validate` step +
  `references/validation.md`; "feasibility necessary but not sufficient"
  warning → `anti_patterns`; "do not use Python abs() on solver expressions" →
  `anti_patterns`; subtour-elimination warning ("degree + continuity alone
  permit disconnected cycles") → `anti_patterns`.
- **Schema gap** — none.
- **Body drop** — none.
- **Deliberate drop** — none. The opening prose paragraph
  ("SCIP is a strong open-source optimization solver…") is folded into
  `purpose`.
