---
name: civ6lib
description: Civilization 6 (Gathering Storm) district mechanics library. Use when validating district placements, computing adjacency bonuses, deciding which districts a city may build, or reasoning about Civ6 city / district / adjacency rules — including for the civ6-adjacency-optimizer task. Wraps the placement-rules and adjacency-bonus engines and points to detailed reference tables.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Encode Civilization 6 (Gathering Storm) district mechanics so an agent
  can validate placements and compute adjacency bonuses deterministically,
  using the bundled rule engines in `scripts/`. The library handles
  district-distance, terrain, water, flat-land, uniqueness, population-cap
  and feature/resource destruction rules; the adjacency engine handles
  Civ6's separate-flooring rule for minor +0.5 bonuses, additive
  major + minor stacking, and destruction-aware neighbour counting.

trigger_when:
  - User asks to validate a Civ6 district placement (single tile, single district).
  - User asks to compute adjacency bonus for a Civ6 district or a full placement plan.
  - Agent is searching/optimising district placements (e.g. the civ6-adjacency-optimizer task) and needs an authoritative scoring + legality check.
  - Agent needs to know which districts are non-specialty (no population cap) or unique-per-civilization.
  - Agent needs to know which features/resources are destroyed by district placement and how that cascades through adjacency.
  - User asks "what bonus does a Campus next to {feature} get?" or any Civ6 adjacency-rule question.

do_not_use_when:
  - User is asking about a Civ game other than Civ6, or a Civ6 ruleset other than Gathering Storm (rules differ).
  - Task is purely about hex-grid math (neighbours, distance) with no district semantics — use the `hex-grid-spatial` skill.
  - Task is parsing a `.Civ6Map` SQLite file into tile data — use the `sqlite-map-parser` skill, then feed its output into this one.
  - Task is choosing WHICH placements to try (search strategy) — that is `map-optimization-strategy`. This skill scores and validates; it does not search.

scope_and_approval: >
  Read-only and pure-computation. All scripts are deterministic library
  modules importable as Python; no filesystem writes, no network, no
  subprocess. Safe to call repeatedly inside an optimisation loop.

steps:
  - name: import-library
    description: >
      Import the rule engines. From `scripts/`: `DistrictType`,
      `DISTRICT_NAME_MAP`, `Tile`, `PlacementRules`, `PlacementResult`,
      `get_placement_rules`, `calculate_max_specialty_districts`,
      `validate_district_count`, `validate_district_uniqueness` (from
      `placement_rules`); `AdjacencyCalculator`, `AdjacencyResult`,
      `get_adjacency_calculator` (from `adjacency_rules`). Hex math
      (`hex_distance`, `get_neighbors`, `is_adjacent`) lives in
      `hex_utils.py` and is consumed internally — prefer the
      `hex-grid-spatial` skill for hex math the agent does itself.
    outputs:
      - name: api
        type: object
        description: Imported symbols ready for use in subsequent steps.

  - name: construct-tiles
    description: >
      Build a `dict[(x, y) -> Tile]` covering every map tile the agent
      may reason about. Required fields per Tile: `x`, `y`, `terrain`
      (GRASS / PLAINS / DESERT / TUNDRA / SNOW / COAST / OCEAN / LAKE /
      MOUNTAIN). Optional but commonly load-bearing fields: `feature`
      (e.g. `FEATURE_FOREST`, `FEATURE_JUNGLE`, `FEATURE_MARSH`,
      `FEATURE_GEOTHERMAL_FISSURE`, `FEATURE_REEF`, `FEATURE_OASIS`,
      natural-wonder feature strings containing `NATURAL_WONDER`),
      `is_hills`, `is_floodplains`, `river_edges` (list of edge indices
      0–5), `resource` + `resource_type` (`STRATEGIC` / `LUXURY` /
      `BONUS`), `improvement` (`MINE`, `QUARRY`, `LUMBER_MILL`). Source
      this from `sqlite-map-parser` output or scenario JSON; the shape
      is fixed by the `Tile` dataclass in `scripts/placement_rules.py`.
    inputs:
      - name: api
        type: object
    outputs:
      - name: tiles
        type: object
        description: dict[(x, y) -> Tile] for all known map tiles.

  - name: enforce-district-limits
    description: >
      Check the city's specialty-district population cap before
      validating individual placements. `calculate_max_specialty_districts(pop)`
      returns `1 + floor((pop - 1) / 3)`. Non-specialty districts
      (Aqueduct, Dam, Canal, Spaceport, Neighborhood) DO NOT count
      against the cap and can be added freely on top.
    script: scripts/placement_rules.py
    inputs:
      - name: placements
        type: object
        description: dict[district_name_str -> (x, y)] for this city.
      - name: population
        type: integer
    outputs:
      - name: count_result
        type: object
        description: (valid, errors) tuple from `validate_district_count`.

  - name: enforce-uniqueness
    description: >
      Check intra-city and per-civilization uniqueness. Most specialty
      districts are one-per-city; Neighborhood and the non-specialty
      districts may stack; Government Plaza and Diplomatic Quarter are
      one-per-civilization (pass `all_placements` to enforce that).
    script: scripts/placement_rules.py
    inputs:
      - name: placements
        type: object
      - name: all_placements
        type: object
        nullable: true
        description: Optional dict[city_id -> placements] for multi-city checks.
    outputs:
      - name: uniqueness_result
        type: object

  - name: validate-placement
    description: >
      Validate a single (district, x, y) against all rules — distance ≤3,
      terrain, water/flat-land requirements, no-adjacent-to-CC for
      Encampment/Preserve, Aqueduct fresh-water + No-U-Turn, Dam
      floodplains + ≥2-river-edges, Canal connectivity, no stacking on
      existing district, no strategic/luxury resources, no mountain/
      natural-wonder/geothermal. Use `PlacementRules.validate_placement`;
      see `references/placement-rules.md` for the full rule sheet behind
      each error message.
    script: scripts/placement_rules.py
    inputs:
      - name: tiles
        type: object
      - name: city_center
        type: object
        description: (x, y) tuple.
      - name: population
        type: integer
      - name: district_type
        type: object
        description: DistrictType enum value.
      - name: target
        type: object
        description: (x, y) target tile.
      - name: existing_placements
        type: object
        description: dict[(x, y) -> DistrictType] of already-placed districts.
    outputs:
      - name: placement_result
        type: object
        description: PlacementResult(valid, errors, warnings).

  - name: validate-city-distances
    description: >
      For multi-city scenarios, verify city centers respect
      minimum-distance rules — 4 tiles same landmass, 3 tiles different
      landmasses. Landmass membership is determined by BFS through land
      tiles in the provided `tiles` dict.
    script: scripts/placement_rules.py
    inputs:
      - name: city_centers
        type: list[object]
        description: List of (x, y) tuples.
      - name: tiles
        type: object
    outputs:
      - name: distance_result
        type: object

  - name: compute-adjacency
    description: >
      Score one or more districts. For a full plan, call
      `AdjacencyCalculator.calculate_total_adjacency(placements)` — it
      applies destruction (Woods / Rainforest / Marsh / Bonus resources
      removed from tiles a non-City-Center district was placed on), then
      computes per-district bonuses honouring the separate-flooring rule
      for every +0.5-per-source type and the additive major + minor
      stacking rule. For a single district under a hypothetical
      placement, call `calculate_district_adjacency(district, x, y,
      tiles_after_destruction, placements)` directly — agents doing
      placement search should `apply_destruction` once per candidate
      `placements` snapshot, not per district. Detailed adjacency tables
      are in `references/adjacency-rules.md`.
    script: scripts/adjacency_rules.py
    inputs:
      - name: tiles
        type: object
      - name: placements
        type: object
        description: dict[(x, y) -> DistrictType] including City Center.
    outputs:
      - name: total
        type: integer
      - name: per_district
        type: object
        description: dict["DISTRICT@(x,y)" -> AdjacencyResult(total_bonus, breakdown)].

  - name: report
    description: >
      Surface results in the form the consumer expects. For the
      civ6-adjacency-optimizer task: write a JSON file with `city_center`
      (or `cities`), `placements` (district name → [x, y]),
      `adjacency_bonuses` (district name → integer), `total_adjacency`,
      where the sum of `adjacency_bonuses` MUST equal `total_adjacency`.
      For free-form queries, emit the per-district `breakdown` as a
      human-readable table.

modes:
  - name: score-one
    body: >
      Single placement check — call `validate_placement` then, if valid,
      `calculate_district_adjacency`. Skip `apply_destruction` only if
      no destructible features sit adjacent.
  - name: score-plan
    body: >
      Full placement plan — run `validate_district_count`,
      `validate_district_uniqueness`, per-district `validate_placement`,
      then `calculate_total_adjacency` (which handles destruction).
  - name: search-loop
    body: >
      Optimisation loop driven by an external strategy skill
      (`map-optimization-strategy`). Reuse one `AdjacencyCalculator`
      across candidates; rebuild the `placements` dict per candidate.
      Cache `apply_destruction` output if the candidate's tile-set is
      unchanged.

integrations:
  - partner: hex-grid-spatial
    body: >
      Source of truth for hex math (neighbours, distance, ranges).
      `civ6lib` consumes it internally via `scripts/hex_utils.py`; agent
      code that needs raw hex math should import from `hex-grid-spatial`
      to avoid duplication.
  - partner: sqlite-map-parser
    body: >
      Reads `.Civ6Map` SQLite files and produces tile records. Feed its
      output through a thin adapter into the `Tile` dataclass to build
      the `tiles` dict required by every step here.
  - partner: map-optimization-strategy
    body: >
      Defines HOW to search the placement space (prune → score → anchor).
      `civ6lib` is the scoring + legality oracle that strategy calls per
      candidate; this skill does not pick candidates.

scenarios:
  - need: Validate a single Campus placement at (21, 14) for a population-7 city centred at (21, 13).
    action: >
      `rules = get_placement_rules(tiles, (21, 13), 7); result =
      rules.validate_placement(DistrictType.CAMPUS, 21, 14, {})`. Reject
      if `result.valid` is False; show `result.errors`. Warnings
      (feature/resource destruction) are informational.
    outcome: Boolean valid + structured errors/warnings.
  - need: Score a 3-district plan (Campus, Holy Site, Commercial Hub) around a city centre and produce the optimizer-task output JSON.
    action: >
      Build the `placements` dict (including CITY_CENTER); call
      `AdjacencyCalculator.calculate_total_adjacency(placements)`; sum
      per-district `total_bonus` values into `adjacency_bonuses` and the
      grand total; write the task's `output/scenario_N.json` shape.
    outcome: total_adjacency (int) and per-district breakdown matching the task's required output schema.
  - need: Decide whether the city can build a 4th specialty district at population 9.
    action: >
      `calculate_max_specialty_districts(9)` → 3. Reject the 4th
      specialty district. Suggest Neighborhood / Aqueduct / Dam / Canal /
      Spaceport instead — these don't count against the cap.
    outcome: Cap = 3 specialty districts; non-specialty options listed.

anti_patterns:
  - "Summing minor +0.5-per-source counts before flooring. Industrial Zone with 1 Mine + 1 Lumber Mill + 1 District is 0, not 1 — floor each source type separately, then add. `AdjacencyCalculator` already does this; do not re-implement."
  - "Computing adjacency on the pristine tiles dict. Placing a non-City-Center district destroys Woods, Rainforest, Marsh and Bonus resources on that tile, which can erase neighbour bonuses for OTHER districts in the same plan. Always go through `apply_destruction` (or call `calculate_total_adjacency`)."
  - "Treating City Center like other districts for destruction. City Center preserves features and resources on its own tile (Geothermal Fissure, Reef, luxury/strategic resources stay). The library encodes this exception; manual implementations routinely miss it."
  - "Forgetting major + minor are additive. Aqueduct adjacent to Industrial Zone gives both +2 (major) AND counts toward +0.5 per district (minor). Do not double-exclude."
  - "Building Encampment or Preserve adjacent to the City Center. Both are explicitly forbidden adjacent to CC even though they meet other requirements."
  - "Counting specialty-district cap against non-specialty districts. Aqueduct / Dam / Canal / Spaceport / Neighborhood do NOT consume a specialty slot."
  - "Treating Government Plaza or Diplomatic Quarter as one-per-city when they are one-per-civilization. In multi-city scenarios pass `all_placements` to `validate_district_uniqueness`."
  - "Using these rules for a Civ6 ruleset other than Gathering Storm. Pre-GS rulesets differ (e.g. no Dam, no Preserve, different Industrial Zone sources). Confirm Gathering Storm before applying."
```
