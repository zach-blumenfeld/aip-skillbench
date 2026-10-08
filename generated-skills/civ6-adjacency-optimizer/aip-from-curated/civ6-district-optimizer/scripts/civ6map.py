"""Shared loader: scenario.json + .Civ6Map (SQLite) -> civ6lib Tile dict.

Imported by the step scripts; not a step on its own. Standard library only.

Coordinates: plot ID -> (x, y) with x = ID % Map.Width, y = ID // Map.Width.
Rivers: PlotRivers flags name the edge of *this* plot the river runs along
(IsWOfRiver -> east edge, IsNWOfRiver -> south-east edge, IsNEOfRiver ->
south-west edge). The map's y axis points north, so those edges are shared with
hex_utils neighbor index 0, 1 and 2 respectively; the tile across the edge gets
the opposite index (3, 4, 5). river_edges are stored as hex_utils neighbor
indexes, so `get_direction_to_neighbor` (Aqueduct No-U-Turn) and Dam's
"2+ edges" use one consistent convention.
"""

import json
import os
import sqlite3
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "civ6lib"))

from hex_utils import get_neighbors, get_neighbor_at_direction  # noqa: E402
from placement_rules import Tile  # noqa: E402

STRATEGIC = {"HORSES", "IRON", "NITER", "COAL", "OIL", "ALUMINUM", "URANIUM"}
BONUS = {"BANANAS", "CATTLE", "COPPER", "CRABS", "DEER", "FISH", "MAIZE", "RICE",
         "SHEEP", "STONE", "WHEAT"}
LUXURY = {"AMBER", "CINNAMON", "CITRUS", "CLOVES", "COCOA", "COFFEE", "COSMETICS",
          "COTTON", "DIAMONDS", "DYES", "FURS", "GOLD", "GYPSUM", "HONEY", "INCENSE",
          "IVORY", "JADE", "JEANS", "MARBLE", "MERCURY", "OLIVES", "PEARLS", "PERFUME",
          "SALT", "SILK", "SILVER", "SPICES", "SUGAR", "TEA", "TOBACCO", "TOYS",
          "TRUFFLES", "TURTLES", "WHALES", "WINE"}

# Ordinary terrain features. Any other FEATURE_* is treated as a natural wonder.
ORDINARY_FEATURES = {"FEATURE_FOREST", "FEATURE_JUNGLE", "FEATURE_MARSH", "FEATURE_OASIS",
                     "FEATURE_REEF", "FEATURE_ICE", "FEATURE_GEOTHERMAL_FISSURE",
                     "FEATURE_VOLCANIC_SOIL", "FEATURE_VOLCANO", "FEATURE_BURNING_FOREST",
                     "FEATURE_BURNT_FOREST", "FEATURE_BURNING_JUNGLE", "FEATURE_BURNT_JUNGLE"}
LAKE_MAX_TILES = 8  # enclosed water bodies (no ocean tile) up to this size are lakes


def resolve_path(p, bases=()):
    """Resolve a possibly-relative path. aip runs scripts with cwd = script folder,
    so also try the caller's $PWD and any extra bases."""
    if not p:
        return None
    cands = [p] if os.path.isabs(p) else (
        [os.path.join(b, p) for b in bases] + [os.path.join(os.environ.get("PWD", ""), p), p])
    for c in cands:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


def load_scenario(state):
    """Return (scenario dict, scenario path, map path). Accepts scenario_path
    (file or directory) and an optional map_path override."""
    sp = resolve_path(state.get("scenario_path"))
    if sp and os.path.isdir(sp):
        sp = os.path.join(sp, "scenario.json")
    if not sp or not os.path.isfile(sp):
        raise SystemExit(json.dumps({"error": f"scenario not found: {state.get('scenario_path')!r} "
                                              "(pass an absolute path)"}))
    with open(sp) as f:
        scen = json.load(f)
    d = os.path.dirname(sp)
    mp = resolve_path(state.get("map_path")) if state.get("map_path") else None
    if not mp:
        mf = scen.get("map_file") or scen.get("map") or ""
        # map_file is relative to the data root (e.g. "maps/x.Civ6Map" next to scenario_N/)
        mp = resolve_path(mf, bases=(d, os.path.dirname(d), os.path.dirname(os.path.dirname(d)),
                                     "/data", "/root/data", "/root"))
        if not mp and mf:
            base = os.path.basename(mf)
            for root in (os.path.dirname(d), "/data", "/root"):
                for r, _, files in os.walk(root) if os.path.isdir(root) else []:
                    if base in files:
                        mp = os.path.join(r, base)
                        break
                if mp:
                    break
    if not mp:
        raise SystemExit(json.dumps({"error": f"map file not found for {scen.get('map_file')!r}; "
                                              "set map_path in the state"}))
    return scen, sp, mp


def _q(cur, sql):
    try:
        return cur.execute(sql).fetchall()
    except sqlite3.OperationalError:
        return []  # table missing in this map


def classify_resource(rtype):
    name = (rtype or "").replace("RESOURCE_", "")
    if name in STRATEGIC:
        return "STRATEGIC"
    if name in BONUS:
        return "BONUS"
    if name in LUXURY:
        return "LUXURY"
    return None


def load_map(map_path):
    """Parse the .Civ6Map SQLite file. Returns dict with width, height, wrap_x,
    tiles {(x,y): Tile}, blocked {(x,y)} (ice / impassable non-mountain),
    start_positions, cities, districts, warnings, schema."""
    conn = sqlite3.connect(f"file:{map_path}?mode=ro", uri=True)
    cur = conn.cursor()
    tables = [r[0] for r in _q(cur, "SELECT name FROM sqlite_master WHERE type='table'")]
    m = _q(cur, "SELECT Width, Height, WrapX FROM Map LIMIT 1")
    plots = _q(cur, "SELECT ID, TerrainType, IsImpassable FROM Plots ORDER BY ID")
    if m:
        width, height, wrap_x = int(m[0][0]), int(m[0][1]), bool(m[0][2])
    else:  # no Map table: assume the duel-size default only if the plot count fits
        width, height, wrap_x = 44, max(1, len(plots) // 44), False
    warnings = []
    feats = dict(_q(cur, "SELECT ID, FeatureType FROM PlotFeatures"))
    res = {r[0]: r[1] for r in _q(cur, "SELECT ID, ResourceType FROM PlotResources") if r[1]}
    imps = {r[0]: r[1] for r in _q(cur, "SELECT ID, ImprovementType FROM PlotImprovements") if r[1]}
    rivers = _q(cur, "SELECT ID, IsNEOfRiver, IsWOfRiver, IsNWOfRiver FROM PlotRivers")
    starts = _q(cur, "SELECT Plot, Type, Value FROM StartPositions")
    cities = _q(cur, "SELECT Owner, Plot, Name FROM Cities")
    dists = _q(cur, "SELECT DistrictType, CityID, Plot FROM Districts")
    conn.close()

    xy = lambda pid: (pid % width, pid // width)
    raw = {}
    blocked = set()
    unknown_terrain, unknown_res, wonders = set(), set(), set()
    for pid, ttype, impass in plots:
        x, y = xy(pid)
        t = (ttype or "").replace("TERRAIN_", "")
        is_hills = t.endswith("_HILLS")
        if t.endswith("_MOUNTAIN"):
            terrain = "MOUNTAIN"
        elif is_hills:
            terrain = t[:-6]
        else:
            terrain = t
        if terrain not in ("GRASS", "PLAINS", "DESERT", "TUNDRA", "SNOW", "COAST", "OCEAN", "MOUNTAIN"):
            unknown_terrain.add(ttype)
        feature = feats.get(pid)
        is_flood = False
        if feature and feature.startswith("FEATURE_FLOODPLAINS"):
            is_flood, feature = True, None
        elif feature and feature not in ORDINARY_FEATURES:
            wonders.add(feature)
            # civ6lib detects wonders by the substring "NATURAL_WONDER"; Campus matches
            # Great Barrier Reef by the substring "GREAT_BARRIER_REEF".
            core = feature.replace("FEATURE_", "")
            if core == "BARRIER_REEF":
                core = "GREAT_BARRIER_REEF"
            feature = "NATURAL_WONDER_" + core
        rtype = res.get(pid)
        rclass = classify_resource(rtype)
        if rtype and rclass is None:
            unknown_res.add(rtype)
            rclass = "LUXURY"  # unknown: treat as unbuildable (conservative)
        imp = imps.get(pid)
        if imp:
            imp = imp.replace("IMPROVEMENT_", "")
        raw[(x, y)] = dict(x=x, y=y, terrain=terrain, feature=feature, is_hills=is_hills,
                           is_floodplains=is_flood, river_edges=set(),
                           resource=(rtype.replace("RESOURCE_", "") if rtype else None),
                           resource_type=rclass, improvement=imp)
        if feature == "FEATURE_ICE" or (impass and terrain != "MOUNTAIN"):
            blocked.add((x, y))

    for pid, ne, w, nw in rivers:
        x, y = xy(pid)
        for flag, d in ((w, 0), (nw, 1), (ne, 2)):
            if flag:
                raw[(x, y)]["river_edges"].add(d)
                n = get_neighbor_at_direction(x, y, d)
                if n in raw:
                    raw[n]["river_edges"].add((d + 3) % 6)

    # Lakes: enclosed water bodies with no ocean tile and <= LAKE_MAX_TILES tiles.
    seen = set()
    for c, r in raw.items():
        if c in seen or r["terrain"] not in ("COAST", "OCEAN"):
            continue
        body, dq = [], deque([c])
        seen.add(c)
        while dq:
            cur_c = dq.popleft()
            body.append(cur_c)
            for n in get_neighbors(*cur_c):
                if n in raw and n not in seen and raw[n]["terrain"] in ("COAST", "OCEAN"):
                    seen.add(n)
                    dq.append(n)
        if len(body) <= LAKE_MAX_TILES and all(raw[b]["terrain"] == "COAST" for b in body):
            for b in body:
                raw[b]["terrain"] = "LAKE"

    tiles = {}
    for c, r in raw.items():
        r["river_edges"] = sorted(r["river_edges"])
        tiles[c] = Tile(**r)

    if unknown_terrain:
        warnings.append(f"unrecognized terrain types (kept as-is): {sorted(unknown_terrain)}")
    if unknown_res:
        warnings.append(f"unrecognized resources treated as LUXURY (unbuildable): {sorted(unknown_res)}")
    if wonders:
        warnings.append(f"natural wonder features found: {sorted(wonders)}")
    if wrap_x:
        land_x = [c[0] for c, t in tiles.items() if not t.is_water]
        if land_x and (min(land_x) <= 3 or max(land_x) >= width - 4):
            warnings.append("map wraps on X and land lies within 3 tiles of the seam; "
                            "civ6lib hex math does not wrap, so seam adjacency is ignored")

    return dict(width=width, height=height, wrap_x=wrap_x, tiles=tiles, blocked=blocked,
                tables=tables,
                start_positions=[{"plot": p, "xy": list(xy(p)), "type": t, "value": v}
                                 for p, t, v in starts],
                cities=[{"owner": o, "plot": p, "xy": list(xy(p)), "name": n} for o, p, n in cities],
                districts=[{"type": t, "city_id": c, "plot": p, "xy": list(xy(p))}
                           for t, c, p in dists],
                warnings=warnings)


def read_stdin():
    data = sys.stdin.read()
    payload = json.loads(data) if data.strip() else {}
    return payload.get("currentState", payload)
