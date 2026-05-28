#!/usr/bin/env python3
"""Compute the per-district adjacency bonus for a placement.

The functions here implement the base-game Civ6 rules described in
references/adjacency-rules.md. They are intentionally explicit per
district type so you can override one rule without breaking the others.

Usage:
    from compute_adjacency import score_placement
    score_placement(
        tiles=parsed["tiles"],
        wrap_x=parsed["wrap_x"],
        width=parsed["width"],
        city_centers=[(x, y), ...],
        placements={"CAMPUS": (x, y), "COMMERCIAL_HUB": (x, y), ...},
        civilization="GREECE",
    )
returns:
    {"CAMPUS": 3, "COMMERCIAL_HUB": 4, ...}, total_int
"""
from __future__ import annotations
from typing import Dict, Iterable, Tuple, Optional

from hex_utils import hex_neighbors
from parse_map import (
    TileInfo, has_river_adjacency, MINE_RESOURCES, QUARRY_RESOURCES,
    SEA_RESOURCES,
)


def _neighbors_of(pos, tiles, wrap_x, width):
    return {p: tiles.get(p) for p in hex_neighbors(*pos, width=width, wrap_x=wrap_x)}


def _district_neighbor_count(pos, district_positions, wrap_x, width):
    """Count how many other districts (including city centers) are
    adjacent to pos. pos itself is excluded."""
    nbrs = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
    return sum(1 for p in district_positions if p != pos and p in nbrs)


def campus_adjacency(pos, tiles, district_positions, wrap_x, width):
    nbrs = _neighbors_of(pos, tiles, wrap_x, width)
    bonus = 0
    rainforest = 0
    for n in nbrs.values():
        if n is None:
            continue
        if n.is_mountain:
            bonus += 1
        if n.is_reef:
            bonus += 1
        if n.feature == "FEATURE_GEOTHERMAL_FISSURE":
            bonus += 1
        if n.is_rainforest:
            rainforest += 1
    bonus += rainforest // 2
    bonus += _district_neighbor_count(pos, district_positions, wrap_x, width) // 2
    return bonus


def commercial_hub_adjacency(pos, tiles, district_positions, wrap_x, width,
                             harbor_positions=()):
    bonus = 0
    nbrs = _neighbors_of(pos, tiles, wrap_x, width)
    tile = tiles.get(pos)
    if tile and has_river_adjacency(tile, nbrs):
        bonus += 2
    nbr_set = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
    if any(h in nbr_set for h in harbor_positions):
        bonus += 2
    bonus += _district_neighbor_count(pos, district_positions, wrap_x, width) // 2
    return bonus


def harbor_adjacency(pos, tiles, district_positions, wrap_x, width,
                     city_centers=()):
    nbrs = _neighbors_of(pos, tiles, wrap_x, width)
    bonus = 0
    for n in nbrs.values():
        if n is None:
            continue
        if n.is_water and n.resource in SEA_RESOURCES:
            bonus += 1
    nbr_set = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
    if any(c in nbr_set for c in city_centers):
        bonus += 2
    bonus += _district_neighbor_count(pos, district_positions, wrap_x, width) // 2
    return bonus


def holy_site_adjacency(pos, tiles, district_positions, wrap_x, width):
    nbrs = _neighbors_of(pos, tiles, wrap_x, width)
    bonus = 0
    woods = 0
    for n in nbrs.values():
        if n is None:
            continue
        if n.is_mountain:
            bonus += 1
        if n.is_natural_wonder:
            bonus += 2
        if n.is_woods:
            woods += 1
    bonus += woods // 2
    bonus += _district_neighbor_count(pos, district_positions, wrap_x, width) // 2
    return bonus


def industrial_zone_adjacency(pos, tiles, district_positions, wrap_x, width,
                              aqueduct_positions=()):
    nbrs = _neighbors_of(pos, tiles, wrap_x, width)
    bonus = 0
    for n in nbrs.values():
        if n is None:
            continue
        if n.resource in MINE_RESOURCES:
            bonus += 1
        if n.resource in QUARRY_RESOURCES:
            bonus += 1
    nbr_set = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
    if any(a in nbr_set for a in aqueduct_positions):
        bonus += 2
    bonus += _district_neighbor_count(pos, district_positions, wrap_x, width) // 2
    return bonus


def theater_square_adjacency(pos, tiles, district_positions, wrap_x, width,
                             wonder_positions=()):
    bonus = 0
    nbr_set = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
    for w in wonder_positions:
        if w in nbr_set:
            bonus += 2
    bonus += _district_neighbor_count(pos, district_positions, wrap_x, width) // 2
    return bonus


# Civilization-specific overrides
def acropolis_adjacency(pos, tiles, district_positions, wrap_x, width,
                        wonder_positions=(), city_centers=()):
    """Greece: replaces Theater Square. +1 per adjacent district,
    +2 per adjacent Wonder, +1 per adjacent City Center."""
    bonus = 0
    nbr_set = set(hex_neighbors(*pos, width=width, wrap_x=wrap_x))
    for w in wonder_positions:
        if w in nbr_set:
            bonus += 2
    for c in city_centers:
        if c in nbr_set:
            bonus += 1
    bonus += _district_neighbor_count(pos, district_positions, wrap_x, width)
    return bonus


DISTRICT_FUNCS = {
    "CAMPUS": campus_adjacency,
    "COMMERCIAL_HUB": commercial_hub_adjacency,
    "HARBOR": harbor_adjacency,
    "HOLY_SITE": holy_site_adjacency,
    "INDUSTRIAL_ZONE": industrial_zone_adjacency,
    "THEATER_SQUARE": theater_square_adjacency,
    "ENCAMPMENT": lambda *a, **k: 0,
    "ENTERTAINMENT_COMPLEX": lambda *a, **k: 0,
    "AERODROME": lambda *a, **k: 0,
    "SPACEPORT": lambda *a, **k: 0,
    "AQUEDUCT": lambda *a, **k: 0,
    "NEIGHBORHOOD": lambda *a, **k: 0,
}


def score_placement(tiles, wrap_x, width, city_centers, placements,
                    civilization=""):
    """Compute adjacency bonus per district.

    placements: dict[district_name -> (x,y)] OR
                dict[district_name -> list of (x,y)] for multi-district per city
    """
    # Normalize placements into list[(name, pos)]
    items = []
    for name, val in placements.items():
        if val is None:
            continue
        if isinstance(val, (list, tuple)) and val and isinstance(val[0], (list, tuple)):
            for pos in val:
                items.append((name, tuple(pos)))
        else:
            items.append((name, tuple(val)))

    district_positions = set(tuple(c) for c in city_centers) | {pos for _, pos in items}
    harbor_positions = [pos for n, pos in items if n == "HARBOR"]
    aqueduct_positions = [pos for n, pos in items if n == "AQUEDUCT"]

    civ = (civilization or "").replace("CIVILIZATION_", "").upper()
    results = {}
    for name, pos in items:
        fn = DISTRICT_FUNCS.get(name, lambda *a, **k: 0)
        if name == "THEATER_SQUARE" and civ == "GREECE":
            score = acropolis_adjacency(pos, tiles, district_positions, wrap_x,
                                        width, city_centers=city_centers)
        elif name == "CAMPUS":
            score = fn(pos, tiles, district_positions, wrap_x, width)
        elif name == "COMMERCIAL_HUB":
            score = fn(pos, tiles, district_positions, wrap_x, width,
                       harbor_positions=harbor_positions)
        elif name == "HARBOR":
            score = fn(pos, tiles, district_positions, wrap_x, width,
                       city_centers=city_centers)
        elif name == "HOLY_SITE":
            score = fn(pos, tiles, district_positions, wrap_x, width)
        elif name == "INDUSTRIAL_ZONE":
            score = fn(pos, tiles, district_positions, wrap_x, width,
                       aqueduct_positions=aqueduct_positions)
        elif name == "THEATER_SQUARE":
            score = fn(pos, tiles, district_positions, wrap_x, width)
        else:
            score = fn(pos, tiles, district_positions, wrap_x, width)
        # Aggregate if multiple of the same district appear
        results[name] = results.get(name, 0) + score

    total = sum(results.values())
    return results, total
