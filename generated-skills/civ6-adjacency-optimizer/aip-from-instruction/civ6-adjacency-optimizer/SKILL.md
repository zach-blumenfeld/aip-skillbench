---
name: civ6-adjacency-optimizer
description: Solve the Civilization VI district adjacency optimization task. Use when asked to place a city center and districts on a .Civ6Map scenario to maximize total adjacency bonus, or when the task references /data/scenario_*/scenario.json with a `map_file`, `num_cities`, `population`, and `civilization` field and expects output at /output/scenario_*.json. Covers .Civ6Map (SQLite) parsing, hex-grid adjacency math, per-district terrain rules, population-based district caps, civ-unique district overrides, and end-to-end greedy placement with validation before emit.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Produce a valid, high-adjacency district placement for a Civ6
  scenario. The grader awards 0 points for any invalid placement, so
  validation matters more than raw optimization. Treat the task as:
  (1) understand the map, (2) compute adjacency faithfully, (3) place
  greedily under constraints, (4) validate before emit.

trigger_when:
  - The task instruction references `/data/scenario_*/scenario.json` and a `.Civ6Map` map_file.
  - User asks to "optimize Civ6 adjacency bonuses" or "place districts to maximize adjacency".
  - Output must be written to `/output/scenario_*.json` in the single-city or multi-city schema from instruction.md.

do_not_use_when:
  - The task is about Civ6 gameplay strategy, not adjacency math (no scenario.json present).
  - The map format is not `.Civ6Map` (different game, different version).

scope_and_approval: >
  Read-only on the scenario and map. Write only to `/output/scenario_*.json`.
  No approval gates — emit the solution directly once validation passes.
  Never overwrite the scenario file or the .Civ6Map file.

steps:
  - name: read-scenario
    description: >
      Open `/data/scenario_N/scenario.json`. Capture `map_file`,
      `num_cities`, `population`, `civilization`. Strip any
      `CIVILIZATION_` prefix when comparing. If `map_file` is a
      relative path, resolve it against the scenario directory.

  - name: locate-grader-rules
    description: >
      Before trusting the default adjacency rules, search the task
      environment for any oracle, scoring, or solution-checker code
      (e.g. `grader.py`, `score.py`, `oracle.py`, a `tests/` folder).
      If found, read it and align the formulas in
      `scripts/compute_adjacency.py` to match. The base-game rules in
      `references/adjacency-rules.md` are the default, not the
      authority.

  - name: inspect-map
    description: >
      Run `python scripts/inspect_map.py <map_file>` to confirm the
      file is SQLite, list tables, and dump column names + sample
      rows. Verify Plots has TerrainType, FeatureType, ResourceType,
      and at least one of `RiverEast/RiverSouthEast/RiverSouthWest`
      OR a separate `Rivers` table.
    depends_on: [read-scenario]

  - name: parse-map
    description: >
      Import `parse_map.parse_map(path)` and load the tile grid.
      Confirm `width`, `height`, `wrap_x`. Spot-check a few tiles
      against the inspect output. See references/civ6map-format.md
      for column variants across Civ6 versions.
    depends_on: [inspect-map]

  - name: verify-hex-layout
    description: >
      Pick two tiles the map data implies are neighbors (e.g., a tile
      with a `RiverEast` flag and the tile at (x+1, y)) and confirm
      one appears in `hex_neighbors` of the other. If not, swap to
      even-r / odd-q. The default in `hex_utils.py` is odd-r. See
      references/hex-grid.md.
    depends_on: [parse-map]

  - name: pick-city-centers
    description: >
      Score every settleable land tile by the heuristic in
      `solve.candidate_centers`: sum of mountains, natural wonders,
      rivers, resources, woods/rainforest within range 3. Choose the
      top `num_cities` tiles such that any two centers are at least
      4 hexes apart and each tile passes `is_valid_city_center`.
    depends_on: [verify-hex-layout]

  - name: compute-district-cap
    description: >
      Compute specialty-district cap per city using
      `solve.population_cap(population)`. The cap is
      `max(1, (pop + 2) // 3)`. Build at most this many specialty
      districts per city. Uncapped districts (Aqueduct, Neighborhood,
      Spaceport, Canal, Dam) don't count and rarely add adjacency, so
      skip them by default.
    depends_on: [pick-city-centers]

  - name: place-districts
    description: >
      Run `solve.greedy_place(...)`. For each remaining slot, iterate
      over (district_type, candidate_tile) and pick the pair that
      maximizes marginal `score_placement` total. Skip tiles that
      fail `is_valid_district_tile` for that district (terrain,
      Harbor=coast-and-city-adjacent, Encampment=not-adjacent-to-CC,
      Aerodrome/Spaceport=flat-land-only). District names follow the
      enum: CAMPUS, COMMERCIAL_HUB, HARBOR, HOLY_SITE,
      INDUSTRIAL_ZONE, THEATER_SQUARE.
    depends_on: [compute-district-cap, locate-grader-rules]

  - name: apply-civ-overrides
    description: >
      If `civilization` resolves to a civ with a unique district that
      changes adjacency (Greece → Acropolis, Germany → Hansa, etc.),
      route those districts through the override functions in
      `compute_adjacency.py`. See references/adjacency-rules.md for
      the list.
    depends_on: [place-districts]

  - name: emit-json
    description: >
      Write `/output/scenario_N.json` in the format from instruction.md.
      Single-city schema uses `city_center` (single coord) and a flat
      `placements` map. Multi-city uses `cities: [{center: [x,y]}]`.
      `adjacency_bonuses` is `{DISTRICT: int}`. `total_adjacency` must
      equal the sum of `adjacency_bonuses.values()`. Coordinates are
      `[x, y]` integer pairs.
    depends_on: [apply-civ-overrides]

  - name: validate
    description: >
      Run `python scripts/validate_solution.py --scenario <s> --solution <out>`.
      Fix any reported error and re-emit. Do not submit until
      validation exits 0. A single invalid placement → 0 points.
    depends_on: [emit-json]

decisions:
  - signal: Grader / oracle code is visible in the environment.
    action: Read it and align compute_adjacency.py before running solve.py. Treat the grader's formula as authoritative.
  - signal: inspect_map reports the file is not SQLite (header != "SQLite format 3").
    action: Stop. Report the file header to the user. Do not guess a binary layout — that risks invalid placements. See references/civ6map-format.md.
  - signal: verify-hex-layout fails for odd-r.
    action: Swap to even-r in hex_utils.hex_neighbors and re-verify with another pair. Update the comment for future runs.
  - signal: Greedy solution has < 10 candidate tiles per city after filtering.
    action: Replace greedy with exhaustive enumeration — try every district-to-tile permutation within the cap and pick the global maximum.
  - signal: validate_solution.py reports "adjacency_bonuses mismatch".
    action: The agent's local formula and emitted JSON disagree. Re-run score_placement and copy its output verbatim into adjacency_bonuses — don't hand-compute.
  - signal: No city center candidate passes is_valid_city_center.
    action: Loosen the 4-hex spacing only if num_cities > 1 forces it; otherwise inspect the map again — likely a misread of TerrainType (snow/desert is still settleable).
  - signal: A placement is on a tile with a feature (Woods/Rainforest/Marsh).
    action: That feature is destroyed when the district is built — do not count it in adjacency for the district's own tile, only for *neighboring* tiles' adjacency. Prefer feature-free tiles for the district itself; keep feature tiles as neighbors.

scenarios:
  - need: Single city, population 6, civilization Greece, mountainous map.
    context: pop 6 → cap 3 specialty districts. Greece replaces Theater Square with Acropolis (+1/district, +2/wonder, +1/CC).
    action: Place city center next to 2–3 mountains. Campus on mountain-adjacent tile (+1/mountain). Acropolis adjacent to City Center (+1) and Campus (+1). Holy Site near remaining mountains.
    outcome: Often 8–12 total adjacency. Validate before emit.

  - need: Two cities, population 3 each, coastal map.
    context: cap 2 specialty per city. Likely Harbor + Commercial Hub combo.
    action: Centers ≥ 4 apart, both on coast. Harbor adjacent to each CC (+2 each), Commercial Hub adjacent to Harbor (+2 each) and river if present (+2).
    outcome: 8+ total adjacency without exotic placement.

  - need: Inland map, no coast, no mountains, civilization Egypt.
    context: River-heavy maps suit Commercial Hub. Egypt has no unique adjacency-changing district.
    action: Center on river. Commercial Hub on river-adjacent tile (+2). Industrial Zone next to resource tiles (Iron/Stone → +1 each). Theater Square between districts (+1/2 districts).
    outcome: 4–7 adjacency. Lower ceiling but valid placements are abundant.

anti_patterns:
  - Trusting the default adjacency rules without checking for a grader/oracle in the task environment. The grader's formula wins.
  - Letting `total_adjacency` drift from `sum(adjacency_bonuses.values())`. Always assign `total = sum(per_district.values())` and copy `per_district` verbatim into the JSON.
  - Placing a Harbor on a non-coast tile or non-adjacent to City Center. Both invalidate the entire submission.
  - Building more specialty districts than `population_cap(pop)` allows. The cap silently invalidates anything beyond it.
  - Counting the district's own tile in its adjacency. Adjacency is the 6 neighbors only.
  - Forgetting that the City Center counts as a district for "per 2 districts" bonuses on other districts.
  - Counting Woods/Rainforest on the district's own tile as adjacency — they're destroyed by the district build.
  - Guessing the hex layout (odd-r vs even-r) without verification. One swap silently undercounts every adjacency.
  - Writing the solution before `validate_solution.py` exits 0.
```
