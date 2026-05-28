---
name: civ6lib
description: Civilization 6 district mechanics library. Use when working with district placement validation, adjacency bonus calculations, or understanding Civ6 game rules.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Civilization 6 (Gathering Storm) district mechanics library covering placement
  validation and adjacency bonus calculation. Wraps the standard ruleset for
  district legality (distance, terrain, resources, uniqueness, population limits)
  and adjacency math (per-source bonuses, minor-bonus flooring, Government Plaza,
  feature destruction). Use for district planning, optimization, validation, and
  any analysis grounded in Civ6 game rules.

trigger_when:
  - User asks to validate a Civ6 district placement.
  - User asks to compute or optimize adjacency bonuses for Civ6 districts.
  - Building tooling that reasons about Civ6 district legality, city/district limits, or feature destruction.
  - Answering questions about Civ6 placement rules, adjacency formulas, or related mechanics.

do_not_use_when:
  - Question concerns hex grid geometry only (neighbors, distance) — use the `hex-grid-spatial` skill or `scripts/hex_utils.py`.
  - Question concerns a different Civ6 expansion ruleset or a different Civilization title — this library encodes Gathering Storm.

steps:
  - name: import-library
    description: >
      Import the relevant entry points. Placement: `DistrictType`, `Tile`,
      `PlacementRules`, `get_placement_rules`, `validate_district_count`,
      `validate_district_uniqueness` from `scripts/placement_rules.py`.
      Adjacency: `AdjacencyCalculator`, `get_adjacency_calculator` from
      `scripts/adjacency_rules.py`. See `references/key-classes.md` for the
      full usage pattern.
  - name: tile-within-range
    description: Verify the candidate tile is within 3 tiles of the City Center (universal rule for every district).
  - name: tile-eligibility
    description: >
      Confirm the tile is not a Mountain, Natural Wonder, Strategic Resource
      (Iron, Horses, Niter, Coal, Oil, Aluminum, Uranium), Luxury Resource, or
      already-occupied tile. Bonus Resources and Woods/Rainforest/Marsh are
      placeable (the resource/feature is destroyed). Full table in
      `references/placement-rules.md`.
  - name: district-specific-requirements
    description: >
      Check district-specific constraints — Harbor/Water Park on Coast or Lake
      adjacent to land; Aerodrome and Spaceport on flat land; Encampment and
      Preserve not adjacent to City Center; Aqueduct adjacent to City Center
      and fresh water (Mountain, River, Lake, Oasis); Dam on Floodplains with
      a river crossing 2+ edges. Full table in `references/placement-rules.md`.
  - name: district-slots-available
    description: >
      Confirm the city has a specialty-district slot available given its
      population (`max = 1 + floor((population - 1) / 3)`). Non-specialty
      districts (Aqueduct/Bath, Neighborhood/Mbanza, Canal, Dam, Spaceport)
      do not count against this limit.
  - name: uniqueness-check
    description: >
      Confirm the district is not already built. Most specialty districts are
      one-per-city; Neighborhood is multi-per-city; Government Plaza and
      Diplomatic Quarter are one-per-civilization. Use
      `validate_district_uniqueness` for this.
  - name: calculate-adjacency
    description: >
      Compute adjacency via `AdjacencyCalculator.calculate_total_adjacency(placements)`.
      Apply per-district bonus rules from `references/adjacency-rules.md`.
      CRITICAL: every +0.5 source type floors SEPARATELY before summing —
      do not sum +0.5 sources and then floor.

decisions:
  - signal: Need to validate a single district placement.
    action: >
      Call `get_placement_rules(tiles, city_center, population).validate_placement(district, q, r, placements)`
      from `scripts/placement_rules.py`. Inspect `.valid` and reason on the
      returned failure data.
  - signal: Need to compute total adjacency across a placement set.
    action: >
      Call `get_adjacency_calculator(tiles).calculate_total_adjacency(placements)`
      from `scripts/adjacency_rules.py`; it returns `(total, per_district)`.
  - signal: Industrial Zone surrounded by 1 Mine + 1 Lumber Mill + 1 adjacent District.
    action: >
      Floor each +0.5 type separately — Mine `floor(1/2)=0`, Lumber Mill
      `floor(1/2)=0`, District `floor(1/2)=0` — for a minor-bonus total of 0.
      Do NOT sum 1+1+1 and floor(3/2)=1.
  - signal: A placement destroys a Woods, Rainforest, Marsh, or Bonus Resource tile.
    action: >
      Recalculate adjacency for every OTHER district whose bonus depended on
      that feature/resource. Destruction is permanent and shifts neighbor math.
  - signal: A district is adjacent to Government Plaza.
    action: >
      Add +1 from Government Plaza for Campus, Holy Site, Theater Square,
      Commercial Hub, Harbor, or Industrial Zone. Government Plaza ALSO counts
      toward the "+0.5 per district" minor bonus.
  - signal: Hex-grid geometry needed (neighbor lookup, distance, ring).
    action: >
      Use the `hex-grid-spatial` skill or import from `scripts/hex_utils.py` /
      `src.hex_utils` — civ6lib does not duplicate hex math.

scenarios:
  - need: Validate a Campus placement at offset (21,14) for a population-7 city centered at (21,13).
    action: |
      from civ6lib import DistrictType, get_placement_rules
      rules = get_placement_rules(tiles, city_center=(21, 13), population=7)
      result = rules.validate_placement(DistrictType.CAMPUS, 21, 14, {})
      if result.valid:
          print("Valid placement!")
    outcome: Returns a result object indicating placement legality plus reasons if invalid.
  - need: Compute total adjacency yield across a candidate set of district placements.
    action: |
      from civ6lib import get_adjacency_calculator
      calculator = get_adjacency_calculator(tiles)
      total, per_district = calculator.calculate_total_adjacency(placements)
    outcome: Total adjacency yield plus a per-district breakdown.
  - need: Quick rule lookup — "Can I place a Holy Site on a Luxury Resource tile?"
    context: Universal placement rules in `references/placement-rules.md`.
    action: Consult the Universal Rules table — Luxury Resources block all district placements.
    outcome: No — block placement.

anti_patterns:
  - Summing +0.5 adjacency sources and then flooring once (e.g., 1 Mine + 1 Lumber Mill + 1 District → floor(3/2)=1). Each +0.5 type floors separately; the correct minor-bonus total is 0.
  - Placing a district on a Strategic or Luxury Resource tile — both block district placement (only Bonus Resources are placeable, and they get destroyed).
  - Counting Aqueduct, Neighborhood, Canal, Dam, or Spaceport against the population-based specialty-district limit. These are non-specialty and don't count.
  - Forgetting that Government Plaza both grants +1 to adjacent specialty districts AND counts toward the "+0.5 per district" bonus.
  - Forgetting that placing a district destroys Woods, Rainforest, Marsh, and Bonus Resources — recalculate neighbor adjacency after any placement.
  - Placing Encampment or Preserve adjacent to the City Center — both explicitly forbid that adjacency.
  - Duplicating hex math inside civ6lib. Use `hex-grid-spatial` or `scripts/hex_utils.py` for neighbors/distance/rings.
```
