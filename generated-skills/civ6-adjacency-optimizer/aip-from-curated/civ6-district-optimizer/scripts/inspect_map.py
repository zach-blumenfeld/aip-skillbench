"""Step `inspect-map`: load the scenario and its .Civ6Map, report what is there.

stdin: {"currentState": {"scenario_path": str, "map_path"?: str}, ...}
stdout: {"scenario", "scenario_file", "map_path", "population", "num_cities",
         "max_specialty_districts", "map_summary"}
"""

import json
import sys
from collections import Counter

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

from civ6map import load_map, load_scenario, read_stdin


def main():
    state = read_stdin()
    scen, sp, mp = load_scenario(state)
    m = load_map(mp)
    tiles = m["tiles"]
    pop = int(scen.get("population", state.get("population", 1)) or 1)
    ncities = int(scen.get("num_cities", 1) or 1)
    land = [t for t in tiles.values() if not t.is_water]
    summary = {
        "tables": m["tables"],
        "width": m["width"], "height": m["height"], "wrap_x": m["wrap_x"],
        "tile_count": len(tiles), "land_tiles": len(land),
        "terrain": dict(Counter(("HILLS_" if t.is_hills else "") + t.terrain for t in tiles.values())),
        "features": dict(Counter(t.feature for t in tiles.values() if t.feature)),
        "floodplains": sum(t.is_floodplains for t in tiles.values()),
        "resources": dict(Counter(f"{t.resource}({t.resource_type})" for t in tiles.values() if t.resource)),
        "improvements": dict(Counter(t.improvement for t in tiles.values() if t.improvement)),
        "river_tiles": sum(t.has_river for t in tiles.values()),
        "blocked_tiles": len(m["blocked"]),
        "start_positions": m["start_positions"],
        "existing_cities": m["cities"],
        "existing_districts": m["districts"],
        "warnings": m["warnings"],
    }
    print(json.dumps({
        "scenario": scen,
        "scenario_file": sp,
        "map_path": mp,
        "population": pop,
        "num_cities": ncities,
        "max_specialty_districts": 1 + (pop - 1) // 3,
        "map_summary": summary,
    }))


if __name__ == "__main__":
    main()
