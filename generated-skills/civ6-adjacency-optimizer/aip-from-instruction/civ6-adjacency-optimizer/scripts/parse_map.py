#!/usr/bin/env python3
"""Parse a .Civ6Map SQLite file into a normalized tile grid.

Returns a dict:
    {
      "width": int,
      "height": int,
      "wrap_x": bool,
      "tiles": { (x,y): TileInfo, ... },
      "rivers": set of (x, y, edge) tuples,   # if available
    }

TileInfo fields:
    terrain   : str             # e.g. "TERRAIN_GRASS_HILLS"
    feature   : str | None      # e.g. "FEATURE_FOREST"
    resource  : str | None
    is_mountain : bool
    is_hills    : bool
    is_water    : bool          # COAST or OCEAN
    is_coast    : bool          # COAST specifically
    is_natural_wonder : bool
    river_edges : set of {'E','SE','SW'}   # which edges have a river
    raw         : dict          # original row, for debugging
"""
from __future__ import annotations
import sqlite3
import sys
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Tuple, Set, Optional


NATURAL_WONDERS = {
    "FEATURE_GALAPAGOS", "FEATURE_GREAT_BARRIER_REEF", "FEATURE_CRATER_LAKE",
    "FEATURE_DEAD_SEA", "FEATURE_EVEREST", "FEATURE_KILIMANJARO",
    "FEATURE_PANTANAL", "FEATURE_PIOPIOTAHI", "FEATURE_TORRES_DEL_PAINE",
    "FEATURE_TSINGY", "FEATURE_YOSEMITE", "FEATURE_GEOTHERMAL_FISSURE",
    "FEATURE_CLIFFS_DOVER", "FEATURE_MATO_TIPILA", "FEATURE_ULURU",
    "FEATURE_EYE_OF_THE_SAHARA", "FEATURE_LYSEFJORD", "FEATURE_BERMUDA_TRIANGLE",
    "FEATURE_FOUNTAIN_OF_YOUTH", "FEATURE_LAKE_RETBA", "FEATURE_PAITITI",
    "FEATURE_DELICATE_ARCH", "FEATURE_GIBRALTAR", "FEATURE_PAMUKKALE",
    "FEATURE_HALONG_BAY", "FEATURE_VESUVIUS", "FEATURE_KRAKATOA",
}

# Resources that host Mines (yield production via Mine improvement)
MINE_RESOURCES = {
    "RESOURCE_IRON", "RESOURCE_NITER", "RESOURCE_COAL", "RESOURCE_COPPER",
    "RESOURCE_ALUMINUM", "RESOURCE_URANIUM", "RESOURCE_DIAMONDS",
    "RESOURCE_MERCURY", "RESOURCE_SILVER", "RESOURCE_GOLD_ORE",
}

# Resources that host Quarries
QUARRY_RESOURCES = {
    "RESOURCE_STONE", "RESOURCE_MARBLE", "RESOURCE_GYPSUM", "RESOURCE_JADE",
    "RESOURCE_AMBER", "RESOURCE_SALT",
}

# Sea resources for Harbor adjacency
SEA_RESOURCES = {
    "RESOURCE_FISH", "RESOURCE_CRABS", "RESOURCE_WHALES", "RESOURCE_PEARLS",
    "RESOURCE_TURTLES", "RESOURCE_AMBER",
}


@dataclass
class TileInfo:
    x: int
    y: int
    terrain: str = ""
    feature: Optional[str] = None
    resource: Optional[str] = None
    river_edges: Set[str] = field(default_factory=set)
    raw: dict = field(default_factory=dict)

    @property
    def is_mountain(self) -> bool:
        return self.terrain.endswith("_MOUNTAIN")

    @property
    def is_hills(self) -> bool:
        return self.terrain.endswith("_HILLS")

    @property
    def is_water(self) -> bool:
        return self.terrain in ("TERRAIN_COAST", "TERRAIN_OCEAN")

    @property
    def is_coast(self) -> bool:
        return self.terrain == "TERRAIN_COAST"

    @property
    def is_natural_wonder(self) -> bool:
        return self.feature in NATURAL_WONDERS

    @property
    def is_woods(self) -> bool:
        return self.feature == "FEATURE_FOREST"

    @property
    def is_rainforest(self) -> bool:
        return self.feature == "FEATURE_JUNGLE"

    @property
    def is_reef(self) -> bool:
        return self.feature == "FEATURE_REEF"

    @property
    def is_floodplains(self) -> bool:
        return self.feature == "FEATURE_FLOODPLAINS"

    @property
    def is_marsh(self) -> bool:
        return self.feature == "FEATURE_MARSH"

    @property
    def is_oasis(self) -> bool:
        return self.feature == "FEATURE_OASIS"

    @property
    def is_lake(self) -> bool:
        return self.feature == "FEATURE_LAKE"

    @property
    def is_settleable(self) -> bool:
        return (not self.is_water and not self.is_mountain
                and not self.is_natural_wonder)


def parse_map(path: str) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    m = conn.execute("SELECT * FROM Map LIMIT 1").fetchone()
    if m is None:
        raise RuntimeError("Map table empty")
    m = dict(m)
    width = m.get("Width") or m.get("MapWidth") or m.get("width")
    height = m.get("Height") or m.get("MapHeight") or m.get("height")
    wrap_x = bool(m.get("WrapX") or m.get("Wrap_X") or 0)

    tiles: Dict[Tuple[int, int], TileInfo] = {}
    for row in conn.execute("SELECT * FROM Plots"):
        r = dict(row)
        x = r.get("X") if "X" in r else r.get("PlotX")
        y = r.get("Y") if "Y" in r else r.get("PlotY")
        if x is None or y is None:
            continue
        t = TileInfo(x=x, y=y,
                     terrain=r.get("TerrainType") or "",
                     feature=r.get("FeatureType"),
                     resource=r.get("ResourceType"),
                     raw=r)
        # River edges on Plots
        for edge_col, edge_name in (
            ("RiverEast", "E"), ("RiverEW", "E"),
            ("RiverSouthEast", "SE"), ("RiverSE", "SE"),
            ("RiverSouthWest", "SW"), ("RiverSW", "SW"),
        ):
            if r.get(edge_col):
                t.river_edges.add(edge_name)
        tiles[(x, y)] = t

    # Rivers table fallback
    rivers = set()
    try:
        for row in conn.execute("SELECT * FROM Rivers"):
            r = dict(row)
            rivers.add((r.get("PlotX") or r.get("X"),
                        r.get("PlotY") or r.get("Y"),
                        r.get("EdgeDirection") or r.get("Direction")))
    except sqlite3.OperationalError:
        pass

    return {
        "width": width,
        "height": height,
        "wrap_x": wrap_x,
        "tiles": tiles,
        "rivers": rivers,
    }


def has_river_adjacency(tile: TileInfo, neighbors: dict) -> bool:
    """A district tile is river-adjacent if it has any river edge OR
    any neighbor has a complementary river edge facing it."""
    if tile.river_edges:
        return True
    # If neighbor has river edge facing this tile, treat as adjacent.
    # Without precise edge directionality across versions, treat any
    # river edge on any neighbor as adjacency (conservative but matches
    # the in-game "next to river" check most of the time).
    for n in neighbors.values():
        if n and n.river_edges:
            return True
    return False


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: parse_map.py <map.Civ6Map>", file=sys.stderr)
        sys.exit(64)
    out = parse_map(sys.argv[1])
    tiles = out["tiles"]
    print(json.dumps({
        "width": out["width"],
        "height": out["height"],
        "wrap_x": out["wrap_x"],
        "tile_count": len(tiles),
        "sample_tile": asdict(next(iter(tiles.values()))),
    }, default=str, indent=2))
