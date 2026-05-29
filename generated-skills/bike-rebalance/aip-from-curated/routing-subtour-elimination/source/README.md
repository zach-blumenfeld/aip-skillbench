# Authoring notes — routing-subtour-elimination (AIP conversion)

## Source

Curated Agent Skill at:
`vendor/skillsbench/tasks/bike-rebalance/environment/skills/routing-subtour-elimination/SKILL.md`

Bundled here as `source/SKILL.md`.

## Schema choice

`procedure.schema.json` (reused, not drafted). The original skill is a small execution graph: enforce base route constraints, choose a subtour method, apply the chosen method, validate routes. The procedure schema's `steps` + `one_of` covers the method-choice branching cleanly, and the freeform `anti_patterns` captures the original's "do not use physical load as connectivity flow" warnings.

## Script vs prose

No `scripts/` directory. Every numeric pattern in the source skill is a **code template the agent splices into the user's MIP model** — variable names, solver API, vehicles/stations notation all depend on the surrounding code the agent is writing. A standalone script that tried to bake those names in would either misfire on different naming conventions or just re-emit the same string the prose already shows. Method selection itself hinges on judgment (instance size, solver behavior, observed bound quality) — explicitly the kind of conditional the AIP guide says belongs in prose.

The single mechanically-deterministic helper — `station_cycles_without_start` for lazy cut separation — operates on solver state in memory, not on data files, so it cannot run as a standalone script either. It's documented as a code template in `references/lazy-cuts.md`.

## Body layout

The body holds the execution graph and decision logic. The four method bodies + base constraints + validation live in `references/` so they load on demand:

- `references/base-route-constraints.md`
- `references/mtz.md`
- `references/single-commodity-flow.md`
- `references/dfj-static.md`
- `references/lazy-cuts.md`
- `references/validation.md`
- `references/method-choice.md`

This keeps `SKILL.md` lean while preserving every code block from the source verbatim.

## Source coverage

Every section of the source SKILL.md is mapped:

| Source section | Destination |
| --- | --- |
| Base notation + binary arc vars | `references/base-route-constraints.md` |
| Required base route constraints | `references/base-route-constraints.md` (step `add-base-route-constraints`) |
| MTZ order constraints + pros/cons | `references/mtz.md` (step `apply-method` one_of `mtz`) |
| Single-commodity flow + pros/cons + pickup/dropoff warning | `references/single-commodity-flow.md` (step `apply-method` one_of `single-commodity-flow`) |
| DFJ subset cuts (static) + pros/cons | `references/dfj-static.md` (step `apply-method` one_of `static-dfj`) |
| Lazy/iterative cut separation + helpers | `references/lazy-cuts.md` (step `apply-method` one_of `lazy-iterative-dfj`) |
| Method-choice table + pickup/dropoff guidance | `references/method-choice.md` (step `choose-method`) + body `anti_patterns` |
| Validation `extract_route` | `references/validation.md` (step `validate-routes`) |

No deliberate drops. No schema gaps.

## Name preserved

Per task requirements, the `name:` frontmatter is unchanged: `routing-subtour-elimination`. The destination folder name matches.
