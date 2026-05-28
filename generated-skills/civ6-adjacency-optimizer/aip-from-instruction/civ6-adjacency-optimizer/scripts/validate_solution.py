#!/usr/bin/env python3
"""Validate a solution JSON against scenario + map.

Checks (all must pass for the scorer to give non-zero credit):
  - Required keys present (single-city vs multi-city format).
  - sum(adjacency_bonuses) == total_adjacency.
  - All placements are unique tiles.
  - All placements are within range 3 of some city center.
  - num_cities matches.
  - Each placement passes per-district terrain rules.
  - Per-city specialty district count ≤ population cap.

Exits 0 on success, 1 on failure (prints reasons to stderr).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hex_utils import hex_distance
from parse_map import parse_map
from solve import is_valid_district_tile, is_valid_city_center, population_cap
from compute_adjacency import score_placement


SPECIALTY_DISTRICTS = {
    "CAMPUS", "COMMERCIAL_HUB", "HARBOR", "HOLY_SITE",
    "INDUSTRIAL_ZONE", "THEATER_SQUARE", "ENCAMPMENT",
    "ENTERTAINMENT_COMPLEX", "AERODROME",
}


def _err(errors, msg):
    errors.append(msg)


def validate(scenario_path, solution_path):
    scenario = json.loads(Path(scenario_path).read_text())
    solution = json.loads(Path(solution_path).read_text())
    map_path = scenario["map_file"]
    if not Path(map_path).is_absolute():
        map_path = str(Path(scenario_path).parent / map_path)
    parsed = parse_map(map_path)
    tiles = parsed["tiles"]
    wrap_x = parsed["wrap_x"]
    width = parsed["width"]
    num_cities = scenario["num_cities"]
    pop = scenario["population"]
    civ = scenario.get("civilization", "")

    errors = []

    # Format
    if num_cities == 1:
        if "city_center" not in solution:
            _err(errors, "missing city_center")
            city_centers = []
        else:
            city_centers = [tuple(solution["city_center"])]
    else:
        if "cities" not in solution:
            _err(errors, "missing cities[] array")
            city_centers = []
        else:
            city_centers = [tuple(c["center"]) for c in solution["cities"]]

    if len(city_centers) != num_cities:
        _err(errors, f"expected {num_cities} city centers, got {len(city_centers)}")

    placements = solution.get("placements", {})
    pos_list = []
    for name, val in placements.items():
        if val and isinstance(val[0], (list, tuple)):
            for v in val:
                pos_list.append((name, tuple(v)))
        else:
            pos_list.append((name, tuple(val)))

    # Uniqueness
    all_positions = list(city_centers) + [p for _, p in pos_list]
    if len(set(all_positions)) != len(all_positions):
        _err(errors, "duplicate tile in placements (a tile is used twice)")

    # City center validity
    for i, c in enumerate(city_centers):
        if c not in tiles:
            _err(errors, f"city center {c} not on map")
            continue
        if not is_valid_city_center(c, tiles, city_centers[:i]):
            _err(errors, f"city center {c} invalid (terrain or too close)")

    # District placement validity
    cap = population_cap(pop)
    specialty_count_per_city = [0] * len(city_centers)
    for name, pos in pos_list:
        if pos not in tiles:
            _err(errors, f"{name} {pos} not on map")
            continue
        if not is_valid_district_tile(name, pos, tiles, city_centers,
                                      wrap_x, width):
            _err(errors, f"{name} at {pos} fails terrain/placement rules")
        # Find a city within range 3
        within = [i for i, c in enumerate(city_centers)
                  if hex_distance(pos, c) <= 3]
        if not within:
            _err(errors, f"{name} at {pos} > 3 hexes from any city center")
        else:
            if name in SPECIALTY_DISTRICTS:
                # Assign to nearest city
                i_min = min(within, key=lambda i: hex_distance(pos, city_centers[i]))
                specialty_count_per_city[i_min] += 1

    for i, n in enumerate(specialty_count_per_city):
        if n > cap:
            _err(errors, f"city {i} has {n} specialty districts, cap {cap}")

    # Adjacency math
    per_district, total = score_placement(tiles, wrap_x, width, city_centers,
                                          placements, civilization=civ)
    claimed_bonuses = solution.get("adjacency_bonuses", {})
    claimed_total = solution.get("total_adjacency", -1)
    if sum(claimed_bonuses.values()) != claimed_total:
        _err(errors, f"sum(adjacency_bonuses)={sum(claimed_bonuses.values())} "
                     f"!= total_adjacency={claimed_total}")
    if per_district != claimed_bonuses:
        _err(errors, f"adjacency_bonuses mismatch: computed={per_district}, claimed={claimed_bonuses}")

    if errors:
        print("INVALID:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"VALID — total_adjacency={total}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--solution", required=True)
    args = ap.parse_args()
    sys.exit(validate(args.scenario, args.solution))
