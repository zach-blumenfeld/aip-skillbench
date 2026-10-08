# Provenance: civ6-district-optimizer

Compiled from four curated Agent Skills that together describe one workflow: parse a Civ6 map,
apply Civ6 district rules, and optimize placements for adjacency. The originals are copied
verbatim in this folder:

| Source | What it contributed |
|---|---|
| `sqlite-map-parser/SKILL.md` | Explore the SQLite schema first, join plot tables by ID, `x = id % width, y = id // width`, tolerate missing tables, emit structured JSON |
| `hex-grid-spatial/SKILL.md`, `hex-grid-spatial/scripts/hex_utils.py` | Odd-r offset neighbors, cube-coordinate distance, tiles-in-range (identical to civ6lib's `hex_utils.py`) |
| `civ6lib/SKILL.md`, `civ6lib/scripts/{placement_rules,adjacency_rules,hex_utils}.py` | Placement rules, district limits, uniqueness, adjacency tables, destruction, validation and scoring engine |
| `map-optimization-strategy/SKILL.md` | Prune / score / anchor-search strategy, greedy + local improvement, pitfalls |

The three civ6lib scripts are copied **unchanged** into `scripts/civ6lib/` and imported by every
step script, so placements are validated and scored by exactly the engine the sources define.

## Procedure and step-kind choices

| Step | Kind | Why |
|---|---|---|
| `inspect-map` | execution | Schema exploration, parsing, coordinate math and the population formula are deterministic. Surfaces the map facts (start positions, existing cities, warnings) the decision needs. |
| `read-task` | decision | Which district pool the task permits, how centers are chosen, and whether it states explicit values are judgments over the task text with a fixed answer space (choice / choice / noul). |
| `by-constraints` | router | Branches on the noul. |
| `record-constraints` | client_task | Copying coordinates, plot IDs or a district list out of free text into typed state is generation, not a fixed-label judgment. |
| `optimize` | execution | All rules, lookups, thresholds, scoring and the search are code (civ6lib + branch-and-bound). Nothing about placement is left to free-form reasoning. |
| `write-answer` | client_task | The output path and JSON shape are defined by each task's instructions; the agent must render the solution in that shape. |
| `verify-answer` | execution | Re-parses the written file and re-validates/re-scores it with civ6lib; deterministic. |
| `answer-check` | router | A failed check loops back to `write-answer`. |

### Design decisions made while compiling

- **Map parsing details the sources left open** (all in `scripts/civ6map.py`, documented in
  `references/map-format.md`): `TERRAIN_*_HILLS` / `_MOUNTAIN` split into terrain + flags;
  floodplains features become `is_floodplains`; unknown features are natural wonders, renamed
  `NATURAL_WONDER_<NAME>` because civ6lib detects wonders by that substring; resources
  classed STRATEGIC / LUXURY / BONUS by a Gathering Storm lookup (unknown -> LUXURY,
  unbuildable, with a warning); improvements lose the `IMPROVEMENT_` prefix; small enclosed
  water bodies become `LAKE`; ice / impassable tiles are blocked.
- **River edges.** `PlotRivers` flags name an edge of the plot (W-of -> east edge, NW-of ->
  south-east, NE-of -> south-west; confirmed against `NamedRiverPlot`'s Civ6 edge enum).
  The map's y axis points north while hex_utils labels its directions as if y pointed south;
  a connectivity check on the test map's river segments confirmed y-up. Edges are stored as
  hex_utils neighbor indexes (0, 1, 2) and mirrored to the tile across the edge.
- **District pool** is a decision because the sources allow non-specialty districts outside
  the population limit and reward Aqueduct / Dam / Canal in the IZ table, but a task may
  restrict types. Default when silent: `with_infrastructure`.
- **One district per type**, because the answer format (`{name: [x, y]}`) and civ6lib's
  `validate_district_count` / `validate_district_uniqueness` take a name-keyed dict.
- **Search.** The strategy skill recommends greedy + local search; the compiled optimizer
  keeps the greedy seed and adds branch-and-bound on top, so the result is provably optimal
  for the pool unless the time limit hits (reported as `search.exact`). Encampment, Aerodrome
  and Preserve are pruned as dominated by the Diplomatic Quarter.
  The fast scorer is built from civ6lib's own `count_rule_sources` per neighbor; it agreed
  with `calculate_total_adjacency` on 3,000 random placements, and the optimizer's optima
  matched brute force on the test map. Final numbers are always civ6lib's.
- **Multi-city** is solved city by city with minimum city distance, shared-tile exclusion and
  one-per-civilization districts.

## Deliberate-drop log

| Source item | Why dropped |
|---|---|
| civ6lib "Usage" Python snippet and "Key Classes" section | API how-to; the step scripts call these classes directly. |
| civ6lib note "import from `src.hex_utils`" | Path from the original project layout; the pack ships its own copy. |
| hex-grid-spatial code listings (`get_neighbors`, `hex_distance`, `get_tiles_in_range`) | Shipped verbatim as `scripts/civ6lib/hex_utils.py`; offsets, formulas and examples are restated in `references/map-format.md`. |
| map-optimization-strategy "Algorithm Skeleton" code | Implemented concretely in `scripts/optimize.py`. |
| map-optimization-strategy "Isolated tiles" pruning | Subsumed by the center radius and the branch-and-bound bounds. |
| sqlite-map-parser generic `parse_sqlite_to_json` example, hierarchical-data and enum-lookup patterns | Generic patterns; the Civ6Map-specific loader is `scripts/civ6map.py`, and the exploration queries are in `references/map-format.md`. |
| sqlite-map-parser JSON output examples (map vs array form) | The pack's JSON output is the `solution` object; the answer file shape comes from the task. |
| civ6lib "Different landmasses" heuristic detail (BFS vs game area IDs) | Kept as code (civ6lib verbatim) and one line in the rules reference; the rationale itself is background. |
| civ6lib wiki URLs in script docstrings | Background references; scripts unchanged. |

## Functional test record

- `aip run` on scenario_3 (real map): free center, with_infrastructure -> total 18, exact; a
  deliberately wrong answer file was caught by `verify-answer` and looped back to
  `write-answer`; the corrected file ended the run.
- `aip run` on a synthetic two-city, population-10 map (resources, improvements, hills, marsh,
  a natural wonder, an unknown resource): given centers + an explicit allowed-district list
  (record-constraints branch), custom output shape parsed and verified -> total 34.
- Optimizer optima on the real map for every pool and population 3/6/9 matched brute force;
  each solved exactly in under 7 s.
- Two fresh agents ran the skill cold (scenario_1 default pool -> 8; scenario_2 start position,
  specialty only -> 10) with no script errors. Their feedback led to the start-position note
  and the excluded-districts wording.
