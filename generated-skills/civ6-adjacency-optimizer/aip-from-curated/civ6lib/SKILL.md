---
name: civ6lib
description: Civilization 6 (Gathering Storm) district mechanics library. Use when working with district placement validation, adjacency bonus calculations, or solving Civ6 adjacency-optimisation tasks where the agent must pick district tiles to maximise total bonus subject to placement rules, district population caps, and uniqueness constraints.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+. Bundled `scripts/` modules are pure Python with no third-party dependencies.
---

```yaml
purpose: >
  Civilization VI (Gathering Storm) district placement and adjacency
  bonus reference library. Encapsulates the placement constraints,
  per-source-floor adjacency math, destruction effects, and uniqueness
  rules, exposing them as a Python API
  (`scripts/placement_rules.py`, `scripts/adjacency_rules.py`,
  `scripts/hex_utils.py`) the agent calls directly when solving
  adjacency-optimisation tasks — picking district tiles that maximise
  the integer total adjacency bonus subject to game rules.

trigger_when:
  - Validating proposed Civ6 district placements against game rules.
  - Computing adjacency bonuses for one district or a full city layout.
  - Solving a Civ6 adjacency-optimisation task — given a map, city
    centre, population, and a set of districts to place, choose tiles
    that maximise total adjacency.
  - Reasoning about Civ6 mechanics — placement constraints, district
    limits, feature/resource destruction, uniqueness across cities.

do_not_use_when:
  - Game is not Civilization VI Gathering Storm (older expansions and
    other titles differ in adjacency formulas and placement rules).
  - Generic hex-grid math unrelated to Civ6 — prefer a dedicated
    hex-grid utility.

scope_and_approval: >
  Read-only. The library validates placements and computes scores; it
  does not mutate external state. The agent decides which final
  placement to recommend.

steps:
  - name: parse-input
    description: >
      Parse the task input into a tile dict, city centre coordinate,
      city population, the districts to place, and any districts
      already on the map. Civ6 uses odd-r offset coordinates; the tile
      dict is keyed by (x, y).
    outputs:
      - name: tiles
        type: object
        description: Dict[(x, y), Tile] — every map tile, keyed by coord.
      - name: city-center
        type: object
        description: Tuple (x, y) of the city centre tile.
      - name: population
        type: integer
      - name: districts-to-place
        type: list[string]
        description: District names (e.g. ["CAMPUS", "HOLY_SITE", "INDUSTRIAL_ZONE"]).
      - name: existing-placements
        type: object
        description: Dict[(x, y), DistrictType] of districts already on the map (always includes CITY_CENTER).

  - name: load-rule-references
    description: >
      Read the rule tables on demand when the agent needs to reason
      about edge cases or explain a computed bonus. The Python modules
      are the source of truth; references are the human-readable
      lookup. Load `references/placement_rules.md` for placement
      constraints, `references/adjacency_rules.md` for bonus tables
      and the per-source-floor rule, and `references/library_usage.md`
      for the Python API surface and calling conventions.

  - name: enumerate-candidates
    description: >
      For each district to place, enumerate every legal tile within 3
      of the city centre. Uses `PlacementRules.validate_placement`
      from `scripts/placement_rules.py`, which applies the universal
      rules (distance, mountains, natural wonders, resources, occupancy)
      and the district-specific rules (water districts on coast/lake
      adjacent to land, Aerodrome/Spaceport on flat land,
      Encampment/Preserve not adjacent to city centre, Aqueduct on
      city-centre-adjacent fresh-water tile, Dam on floodplains with
      2+ river edges, Canal connecting water bodies or to city centre).
    script: scripts/placement_rules.py
    inputs:
      - name: tiles
        type: object
      - name: city-center
        type: object
      - name: population
        type: integer
      - name: districts-to-place
        type: list[string]
      - name: existing-placements
        type: object
    outputs:
      - name: candidates-by-district
        type: object
        description: Dict[district_name, list[(x, y)]] — legal tiles per district.

  - name: score-candidates
    description: >
      For each candidate, compute the adjacency bonus using
      `AdjacencyCalculator.calculate_district_adjacency` in
      `scripts/adjacency_rules.py`. Destruction is applied first
      (`apply_destruction`) so Woods/Rainforest/Marsh/Bonus resources
      lost to already-fixed placements don't count. Minor (+0.5)
      bonuses are floored SEPARATELY per source type and summed; major
      and minor bonuses ARE additive (an IZ adjacent to an Aqueduct
      gets +2 AND counts that Aqueduct toward the "+0.5 per district"
      pool).
    script: scripts/adjacency_rules.py
    inputs:
      - name: tiles
        type: object
      - name: candidates-by-district
        type: object
      - name: existing-placements
        type: object
    outputs:
      - name: scored-candidates
        type: object
        description: Dict[district_name, list[{position, bonus, breakdown}]] sorted by bonus desc.

  - name: search-best-combination
    description: >
      Search assignments of districts to tiles that maximise total
      adjacency subject to feasibility filters from the library —
      specialty-district population cap
      (`calculate_max_specialty_districts`), per-city uniqueness and
      per-civilisation uniqueness for Government Plaza /
      Diplomatic Quarter (`validate_district_uniqueness`), no two
      districts on the same tile, and the order-of-placement
      destruction effect on adjacency. Choose strategy via `modes`.
    script: scripts/placement_rules.py
    inputs:
      - name: scored-candidates
        type: object
      - name: districts-to-place
        type: list[string]
      - name: population
        type: integer
      - name: existing-placements
        type: object
    outputs:
      - name: best-placements
        type: object
        description: Dict[(x, y), DistrictType] of the optimised layout including the city centre.
      - name: best-total-bonus
        type: integer

  - name: validate-final
    description: >
      Re-run `validate_placement` on every chosen tile against the
      final layout to confirm legality end-to-end, then call
      `calculate_total_adjacency` once on the final layout to confirm
      the headline total. Catches search-side bugs and
      destruction-order mistakes.
    script: scripts/adjacency_rules.py
    inputs:
      - name: best-placements
        type: object
      - name: tiles
        type: object
    outputs:
      - name: verified-total
        type: integer
      - name: per-district-breakdown
        type: object
        description: Per-district `AdjacencyResult.breakdown` showing which sources contributed.

  - name: emit-result
    description: >
      Emit the final placements dict, the verified total bonus, and
      the per-district breakdown. The breakdown is the artefact a
      reviewer uses to spot-check the answer.
    inputs:
      - name: best-placements
        type: object
      - name: verified-total
        type: integer
      - name: per-district-breakdown
        type: object
    outputs:
      - name: result
        type: object

modes:
  - name: exhaustive
    body: >
      Enumerate the full combinatorial space of district→tile
      assignments and pick the global max. Tractable when
      districts × candidate tiles is small — typical
      adjacency-optimiser inputs. Default when feasible.
  - name: beam-search
    body: >
      Sort each district's candidates by standalone adjacency, then
      explore the top-K combinations breadth-first, pruning infeasible
      ones (uniqueness, population cap, occupied tile). Use when
      exhaustive search would be too large.
  - name: greedy
    body: >
      Place districts one at a time in decreasing order of their best
      standalone bonus, apply destruction, re-score remaining
      candidates, repeat. Fast but myopic — use as a lower bound or
      sanity check, not as the final answer when an optimum exists.

search_shortcuts:
  - category: Library API
    body: >
      `placement_rules.py`: DistrictType, Tile, PlacementRules,
      PlacementResult, get_placement_rules,
      validate_city_distances, validate_district_count,
      validate_district_uniqueness,
      calculate_max_specialty_districts.
      `adjacency_rules.py`: AdjacencyCalculator, AdjacencyRule,
      AdjacencyResult, DISTRICT_ADJACENCY_RULES,
      DISTRICTS_FOR_ADJACENCY, get_adjacency_calculator.
      `hex_utils.py`: get_neighbors, hex_distance, is_adjacent,
      get_direction_to_neighbor, get_tiles_in_range,
      get_opposite_direction.
  - category: Rule tables (references)
    body: >
      `references/placement_rules.md` — city distance, universal
      district rules, district-specific rules, population formula,
      uniqueness, destruction effects, quick checklist.
      `references/adjacency_rules.md` — per-district bonus tables,
      per-source-floor math, Government Plaza adjacency,
      "+0.5 per district" pool, destruction interaction,
      Commercial Hub river special.
      `references/library_usage.md` — Python API surface, dataclasses,
      calling conventions for placements/existing_placements dicts.

scenarios:
  - need: >
      Maximise adjacency for a Campus, Holy Site, and Industrial Zone
      at a pop-7 city next to a small mountain range and a river.
    context: >
      `enumerate-candidates` returns ~6–8 legal tiles per district
      within 3 of the city centre. Mountains cluster on the north
      edge; a river runs south of the city centre.
    action: >
      Score each candidate. Campus and Holy Site both prefer
      mountain-adjacent tiles (Campus +1 per mountain, Holy Site +1
      per mountain). Pop-7 caps specialty districts at 3
      (1 + floor((7-1)/3)), so all three fit. Run `exhaustive` mode
      over the combined assignment space. The optimiser picks Campus
      on a tile adjacent to 2 mountains, Holy Site on a different
      mountain-adjacent tile (one-per-city respected), and IZ
      adjacent to an Aqueduct candidate slot.
    outcome: >
      Verified total adjacency reported with per-district breakdown.
      Layout passes `validate_district_count` and
      `validate_district_uniqueness`.

  - need: >
      Score an Industrial Zone with 1 adjacent Mine, 1 adjacent Lumber
      Mill, and 1 adjacent District.
    context: >
      Naïve pooling would give floor((1+1+1)/2) = 1, the most common
      manual-math bug.
    action: >
      Use `AdjacencyCalculator.calculate_district_adjacency`. It
      applies the per-source floor: Mine floor(1/2)=0,
      Lumber Mill floor(1/2)=0, District floor(1/2)=0.
    outcome: >
      Total bonus = 0. Matches in-game behaviour.

  - need: Validate an Aqueduct placement.
    context: >
      Candidate tile is adjacent to the city centre and has a Mountain
      neighbour but the only fresh-water source is the city-centre
      edge.
    action: >
      `validate_placement(DistrictType.AQUEDUCT, ...)` checks fresh
      water on neighbours (Mountain, River, Lake, Oasis) AND applies
      the "No U-Turn" rule rejecting placements where fresh water is
      only on the city-centre edge.
    outcome: >
      Result valid because the adjacent Mountain provides fresh water
      from a non-city-centre direction.

anti_patterns:
  - Pooling minor (+0.5) sources before flooring. Each source type is
    floored SEPARATELY then summed; Mine, Lumber Mill, and District
    bonuses to an Industrial Zone are three independent buckets.
  - Forgetting that placing a non-City-Center district destroys Woods,
    Rainforest, Marsh, and Bonus Resources on its tile, removing
    those sources from neighbouring districts' adjacency. Use
    `apply_destruction` before scoring.
  - Treating City Center as a destructor. City Center preserves
    features and resources on its own tile (Geothermal Fissure,
    luxury/strategic resources still contribute to neighbours).
  - Skipping per-civilisation uniqueness for Government Plaza and
    Diplomatic Quarter — these are one-per-civ, not one-per-city.
  - Allowing Encampment or Preserve adjacent to City Center, Aqueduct
    without a non-city-centre fresh-water neighbour, or Dam off
    Floodplains / with fewer than 2 river edges.
  - Double-counting Commercial Hub's river bonus. +2 once when the
    tile is ON a river, not +2 per river edge or per adjacent river
    tile.
  - Treating major and minor adjacency bonuses as mutually exclusive.
    They are additive — a major +2 from an Aqueduct does NOT exclude
    that Aqueduct from the "+0.5 per district" pool.
  - Exceeding the specialty cap — max specialty districts equals
    1 + floor((population - 1) / 3). Non-specialty districts
    (Aqueduct, Dam, Canal, Spaceport, Neighborhood) do NOT count
    toward the cap.
```
