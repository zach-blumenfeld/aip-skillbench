#!/usr/bin/env python3
"""Greedy solver for the Civ6 adjacency-bonus task.

Strategy:
  1. Parse map and scenario.
  2. Pick the best city-center tile(s): land tile that maximizes the
     total adjacency potential of nearby high-value tiles (mountains,
     rivers, sea resources).
  3. Enumerate candidate district tiles within range-3 of each center.
  4. Greedy / beam-search over district choices: at each step, pick
     the (district, tile) pair with the highest *marginal* adjacency,
     respecting placement constraints. Stop at the population cap.
  5. Emit JSON in the format from instruction.md.

This is a starting point. For small maps (≤ ~25 candidate tiles per
city) consider replacing the greedy with full enumeration of district
permutations across candidate tiles — often only a few thousand states.
"""
from __future__ import annotations
import json
import sys
import argparse
from pathlib import Path
from itertools import combinations, permutations

sys.path.insert(0, str(Path(__file__).parent))
from hex_utils import hex_neighbors, hex_distance, tiles_within
from parse_map import parse_map, TileInfo
from compute_adjacency import score_placement, DISTRICT_FUNCS


# Districts ordered by typical adjacency ceiling (high → low).
DISTRICT_PRIORITY = [
    "CAMPUS", "HOLY_SITE", "COMMERCIAL_HUB", "HARBOR",
    "INDUSTRIAL_ZONE", "THEATER_SQUARE",
]


def population_cap(pop: int) -> int:
    return max(1, (pop + 2) // 3)


def is_valid_district_tile(name, pos, tiles, city_centers, wrap_x, width):
    t = tiles.get(pos)
    if t is None:
        return False
    if pos in city_centers:
        return False
    if name == "HARBOR":
        if not t.is_coast:
            return False
        # Must be adjacent to one city center and to land
        nbr_set = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
        if not any(c in nbr_set for c in city_centers):
            return False
        if not any((tiles.get(n) and not tiles[n].is_water) for n in nbr_set):
            return False
        return True
    if name == "AERODROME" or name == "SPACEPORT":
        if t.is_water or t.is_mountain or t.is_hills or t.is_natural_wonder:
            return False
        return True
    # Standard land district
    if t.is_water or t.is_mountain or t.is_natural_wonder:
        return False
    if name == "ENCAMPMENT":
        nbr_set = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
        if any(c in nbr_set for c in city_centers):
            return False
    return True


def is_valid_city_center(pos, tiles, existing_centers):
    t = tiles.get(pos)
    if t is None or not t.is_settleable:
        return False
    for c in existing_centers:
        if hex_distance(pos, c) < 4:
            return False
    return True


def candidate_centers(tiles, top_k=12):
    """Score every land tile by a cheap heuristic that approximates how
    much district potential it unlocks (sum of mountain/river/sea-
    resource counts within range 3)."""
    scores = []
    for pos, t in tiles.items():
        if not t.is_settleable:
            continue
        score = 0
        for q in tiles_within(pos, 3,
                              in_bounds=lambda x, y: (x, y) in tiles):
            qt = tiles[q]
            if qt.is_mountain:
                score += 2
            if qt.is_reef or qt.is_natural_wonder:
                score += 3
            if qt.resource:
                score += 1
            if qt.is_woods or qt.is_rainforest:
                score += 0.5
            if qt.river_edges:
                score += 1
        scores.append((score, pos))
    scores.sort(reverse=True)
    return [p for _, p in scores[:top_k]]


def greedy_place(tiles, wrap_x, width, city_centers, pop_caps, civilization=""):
    """For each city, build candidate set and greedily fill up to its
    population cap with the marginally best district choice."""
    placements = {}  # district_name -> (x, y)  (single-city style)
    multi_placements = {}  # district_name -> list of (x, y) when needed
    chosen_positions = set(city_centers)
    bonuses = {}

    # Per-city candidate pool
    city_pools = []
    for c in city_centers:
        pool = [t for t in tiles_within(c, 3,
                                        in_bounds=lambda x, y: (x, y) in tiles)
                if t not in city_centers]
        city_pools.append(pool)

    total_districts_remaining = list(pop_caps)
    total_to_place = sum(pop_caps)

    while total_to_place > 0:
        best = None  # (bonus, district_name, pos, city_idx)
        for city_idx, pool in enumerate(city_pools):
            if total_districts_remaining[city_idx] <= 0:
                continue
            for d in DISTRICT_PRIORITY:
                if d in placements:
                    continue  # already placed; skip for simplicity (per-name unique)
                for pos in pool:
                    if pos in chosen_positions:
                        continue
                    if not is_valid_district_tile(d, pos, tiles,
                                                  city_centers, wrap_x, width):
                        continue
                    trial = dict(placements)
                    trial[d] = pos
                    _, total = score_placement(tiles, wrap_x, width,
                                               city_centers, trial,
                                               civilization=civilization)
                    if best is None or total > best[0]:
                        best = (total, d, pos, city_idx)
        if best is None:
            break
        _, d, pos, city_idx = best
        placements[d] = pos
        chosen_positions.add(pos)
        total_districts_remaining[city_idx] -= 1
        total_to_place -= 1

    per_district, total = score_placement(tiles, wrap_x, width,
                                          city_centers, placements,
                                          civilization=civilization)
    return placements, per_district, total


def solve(scenario_path, output_path):
    scenario = json.loads(Path(scenario_path).read_text())
    map_path = scenario["map_file"]
    if not Path(map_path).is_absolute():
        # Resolve relative to scenario dir
        map_path = str(Path(scenario_path).parent / map_path)

    parsed = parse_map(map_path)
    tiles = parsed["tiles"]
    wrap_x = parsed["wrap_x"]
    width = parsed["width"]
    num_cities = scenario["num_cities"]
    pop = scenario["population"]
    civ = scenario.get("civilization", "")

    pop_caps = [population_cap(pop)] * num_cities

    # Pick city centers
    cand = candidate_centers(tiles, top_k=20)
    city_centers = []
    for c in cand:
        if is_valid_city_center(c, tiles, city_centers):
            city_centers.append(c)
            if len(city_centers) == num_cities:
                break
    assert len(city_centers) == num_cities, "Failed to place all city centers"

    placements, per_district, total = greedy_place(
        tiles, wrap_x, width, city_centers, pop_caps, civilization=civ
    )

    # Format output
    if num_cities == 1:
        out = {
            "city_center": list(city_centers[0]),
            "placements": {k: list(v) for k, v in placements.items()},
            "adjacency_bonuses": per_district,
            "total_adjacency": int(total),
        }
    else:
        out = {
            "cities": [{"center": list(c)} for c in city_centers],
            "placements": {k: list(v) for k, v in placements.items()},
            "adjacency_bonuses": per_district,
            "total_adjacency": int(total),
        }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    result = solve(args.scenario, args.output)
    print(json.dumps(result, indent=2))
