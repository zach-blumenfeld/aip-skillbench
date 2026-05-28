# Source notes — pareto-optimization (AIP)

## Origin
Compiled from the curated Agent Skill at
`vendor/skillsbench/tasks/mars-clouds-clustering/environment/skills/pareto-optimization/SKILL.md`.
A verbatim copy is preserved at `source/original-SKILL.md`.

## Schema choice
`procedure.schema.json` — Pareto frontier extraction is a short, linear
procedure with script-backed numeric logic. The schema's `steps` graph fits
the pipeline (define objectives → optionally filter → compute mask → emit
frontier). Concepts and properties move to `references/` so the body stays
lean.

## Compilation map
- Concept sections ("Pareto Dominance", "Pareto Frontier", "Properties") →
  `references/pareto-concepts.md` (loaded on demand, not on every run).
- `paretoset` usage and the worked model-selection example →
  `scripts/compute_pareto.py` (canonical implementation + CLI).
- Manual numpy implementation (fallback if `paretoset` unavailable) →
  embedded as `_manual_pareto_mask` inside `scripts/compute_pareto.py`,
  so the script degrades gracefully when the library is missing.
- Visualization snippet → `references/visualization.md` (loaded only when
  the user asks for a plot).

## Deliberate drops
None. Every distinct piece of the source content is mapped above.
