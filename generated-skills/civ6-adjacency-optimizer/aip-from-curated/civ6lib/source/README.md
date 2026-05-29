# civ6lib — conversion notes

This folder holds the canonical human-readable source for the `civ6lib`
AIP skill (the original `SKILL.md` from the curated skill plus the
schema it validates against). The compiled artifact is at
`../SKILL.md`; reference tables are in `../references/`; the rule
engines themselves are in `../scripts/`.

## Source

- `SKILL.md` — verbatim copy of the curated skill at
  `vendor/skillsbench/tasks/civ6-adjacency-optimizer/environment/skills/civ6lib/SKILL.md`.
- `procedure.schema.json` — AIP procedure schema v0.3a3 (bundled so the
  skill is self-contained even though `$id` points to the canonical URL).

## Schema choice

The source skill is a domain library: a Python codebase that validates
placements and computes adjacency bonuses for Civ6 (Gathering Storm).
Consumers invoke it through library imports (steps in an optimisation
loop), so the work decomposes naturally into a graph of script-backed
nodes — `import → tiles → enforce limits → enforce uniqueness →
validate placement → validate distances → compute adjacency → report`.
This matches `procedure.schema.json`'s shape exactly: typed inputs and
outputs between nodes, `script:` paths pointing at the source-of-truth
modules, prose-only nodes for steps where the caller must judge data
shape (constructing the tiles dict). No new schema needed.

## Script vs. prose decisions

- `import-library`, `construct-tiles`, `report` — **prose**. These hinge
  on the agent interpreting external input (which symbols to wire up,
  how to map an arbitrary map source onto the `Tile` dataclass, what
  the consumer wants reported). No deterministic if/then/else over
  structured inputs.
- `enforce-district-limits`, `enforce-uniqueness`,
  `validate-placement`, `validate-city-distances`, `compute-adjacency`
  — **script-backed**. Every rule encoded is deterministic: fixed
  thresholds (max-district formula, 3-tile city-distance), fixed
  lookup tables (which districts are non-specialty, which are
  one-per-civ), terrain/feature checks, and the separate-flooring
  arithmetic on minor adjacency bonuses. These belong in code and are
  already implemented in `scripts/placement_rules.py` and
  `scripts/adjacency_rules.py`. The `script:` field points at the
  module that owns each rule.

## Library files copied verbatim

- `scripts/placement_rules.py`
- `scripts/adjacency_rules.py`
- `scripts/hex_utils.py`

No code changes — these encode the game rules and are the source of
truth. Hex math (`hex_utils.py`) is kept locally because both
`placement_rules.py` and `adjacency_rules.py` import it directly; the
sibling `hex-grid-spatial` skill is the recommended dependency for any
agent code outside `civ6lib`.

## Reference offloading

The source `SKILL.md` carries large tables (placement rules, adjacency
sources, destruction effects). These would bloat the body past the
~5000-token target on every activation, so they are offloaded to:

- `../references/placement-rules.md` — universal + per-district placement
  rules, distance / uniqueness / population formulas.
- `../references/adjacency-rules.md` — per-district adjacency tables,
  the separate-flooring rule, additive major+minor stacking, destruction
  caveats.

The compiled `SKILL.md` summarises each rule sheet in one or two lines
and tells the agent when to open the reference file.

## Frontmatter

- `name`: kept exactly as `civ6lib` per the task constraint — the
  benchmarked task mounts this skill by that directory name.
- `description`: rewritten to widen activation (mentions adjacency,
  validation, optimisation, the civ6-adjacency-optimizer task by name)
  while staying within 1024 chars.
- `metadata.aip.spec` / `metadata.aip.schemaId`: v0.3a3 procedure schema.

## Source-content classification (completeness check)

Every distinct piece of the source `SKILL.md` mapped as follows:

| Source content                                | Disposition                                   |
| --------------------------------------------- | --------------------------------------------- |
| Library overview & module list                | Mapped — `purpose`, `import-library` step     |
| Usage code snippet                            | Mapped — `import-library` step describes it; `scenarios` show the call shape |
| City-placement min distances                  | Mapped — `validate-city-distances` step + `references/placement-rules.md` |
| Invalid settlement tiles                      | Mapped — `references/placement-rules.md`      |
| City-Center-preserves-features note           | Mapped — `references/placement-rules.md`; anti-pattern about City Center destruction exception |
| Universal district placement rules            | Mapped — `validate-placement` step + reference |
| District-specific rules (Harbor, Aerodrome…)  | Mapped — `validate-placement` step + reference |
| Population formula + table                    | Mapped — `enforce-district-limits` step + reference |
| Non-specialty district list                   | Mapped — `enforce-district-limits` step + reference; anti-pattern explicit |
| Uniqueness rules                              | Mapped — `enforce-uniqueness` step + reference; anti-pattern explicit |
| Separate-flooring critical rule               | Mapped — `compute-adjacency` step + reference + anti-pattern |
| Per-district adjacency tables                 | Mapped — `references/adjacency-rules.md`     |
| Districts with no adjacency                   | Mapped — reference                           |
| Government Plaza +1 adjacency                 | Mapped — reference                           |
| "+0.5 per District" eligible list             | Mapped — reference                           |
| Destruction effects                           | Mapped — `compute-adjacency` step + reference + anti-pattern |
| Key classes section                           | Mapped — `import-library` step lists symbols |
| Quick validation checklist                    | Mapped — `references/placement-rules.md` § Validation checklist |

No deliberate drops — all source content is captured either in the
compiled body or behind a referenced doc the body tells the agent when
to open.
