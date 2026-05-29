# Source — civ6lib AIP conversion

This folder bundles the canonical source materials used to compile this
AIP skill so the skill remains self-contained and auditable.

## Contents

- `procedure.schema.json` — the AIP schema (`procedure` family) the
  body validates against. `$id`:
  `https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json`.
- `ORIGINAL_SKILL.md` — verbatim copy of the curated Agent Skill at
  `vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/civ6lib/SKILL.md`.

## Why the procedure schema

The original skill is a reference library: domain rules encoded in
Python modules (`scripts/placement_rules.py`, `scripts/adjacency_rules.py`,
`scripts/hex_utils.py`) plus prose tables describing Civ6 game mechanics.
For use against the `civ6-adjacency-optimizer` task type, the natural
agent workflow is procedural — parse the map, generate legal candidate
placements, score each by adjacency, pick a combination that maximises
total adjacency under uniqueness and population caps.

That workflow fits the `procedure` schema cleanly: typed inputs/outputs
between steps, conditional and table-driven logic delegated to scripts
(the existing modules), and a single human-readable place for the rules
tables (under `references/`).

## Compilation logic

1. **Scripts (verbatim).** `placement_rules.py`, `adjacency_rules.py`,
   and `hex_utils.py` were copied unchanged. They are the source of
   truth for placement validation and adjacency math; the AIP body's
   script-backed steps reference them by path so the agent invokes the
   library rather than re-implementing the rules in prose.
2. **References (extracted).** The two long rule tables in
   `ORIGINAL_SKILL.md` (placement and adjacency) were split into
   `references/placement_rules.md` and `references/adjacency_rules.md`
   for progressive disclosure. `references/library_usage.md` captures
   the Python API surface — types, factory functions, conventions for
   `placements` and `existing_placements` dict shapes.
3. **Body (procedure).** The body encodes the optimisation workflow:
   load → enumerate candidates → score adjacency → search for the best
   combination → emit final placement. Conditional logic
   (placement validity, district limits, per-source floor, destruction
   effects, river bonus) all lives in the scripts, not in prose.

## Source-content classification

Every distinct chunk in `ORIGINAL_SKILL.md` was classified:

| Source content | Classification | Where it lives now |
|----------------|----------------|---------------------|
| Module overview (`placement_rules.py`, `adjacency_rules.py`) | Mapped | Body `steps[].script` + `references/library_usage.md` |
| Reference to `hex-grid-spatial` skill / `src.hex_utils` | Mapped (kept as note) | `references/library_usage.md` (hex_utils now bundled directly) |
| Usage code block | Mapped | `references/library_usage.md` (worked example) |
| City placement rules (distance, invalid tiles) | Mapped | `references/placement_rules.md` |
| Universal district rules table | Mapped | `references/placement_rules.md`, enforced in `placement_rules.py` |
| District-specific rules table | Mapped | `references/placement_rules.md`, enforced in `placement_rules.py` |
| District limit formula + table | Mapped | `references/placement_rules.md`, enforced in `placement_rules.py` |
| Non-specialty districts list | Mapped | `references/placement_rules.md` + `PlacementRules.NON_SPECIALTY_DISTRICTS` |
| Uniqueness rules | Mapped | `references/placement_rules.md` + `validate_district_uniqueness` |
| Minor-bonus "floor separately" rule | Mapped | Body anti-pattern, `references/adjacency_rules.md`, enforced in `adjacency_rules.py` |
| Per-district adjacency tables | Mapped | `references/adjacency_rules.md`, encoded as `*_RULES` lists |
| Districts with no adjacency | Mapped | `references/adjacency_rules.md` |
| Government Plaza adjacency | Mapped | `references/adjacency_rules.md`, encoded per-district |
| "+0.5 per District" list | Mapped | `references/adjacency_rules.md` + `DISTRICTS_FOR_ADJACENCY` |
| Destruction effects | Mapped | `references/adjacency_rules.md`, applied in `AdjacencyCalculator.apply_destruction` |
| Key Classes summary | Mapped | `references/library_usage.md` |
| Quick Validation Checklist | Mapped | `references/placement_rules.md` (tail) |

No content was dropped. The `hex-grid-spatial` cross-skill reference in
the original was simplified — `hex_utils.py` is bundled directly under
`scripts/` so the skill is self-contained for the optimizer task.
