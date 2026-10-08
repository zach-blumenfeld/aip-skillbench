"""Step `verify-answer`: re-read the answer file the agent wrote, re-score and
re-validate it with civ6lib, and compare with the optimizer's solution.

stdin currentState keys used: answer_path (str), scenario_path (str),
map_path (str, optional), solution (object).
stdout: {"answer_ok": bool, "answer_check": {...}}

answer_ok is false only when the file is missing, or when it parses into
placements that are invalid, score differently from what the file claims, or
score below the optimizer's total. An unrecognized but readable format passes
with a warning (the task may require a shape this script does not know).
"""

import json
import sys
import os

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

from civ6map import load_map, load_scenario, read_stdin, resolve_path

from adjacency_rules import AdjacencyCalculator  # noqa: E402
from placement_rules import (DistrictType as DT, PlacementRules,  # noqa: E402
                             validate_city_distances, validate_district_count,
                             validate_district_uniqueness)


def xy(v):
    if isinstance(v, dict):
        if "x" in v and "y" in v:
            return (int(v["x"]), int(v["y"]))
        for k in ("coords", "coordinates", "position", "tile", "location"):
            if k in v:
                return xy(v[k])
        return None
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(a, (int, float)) for a in v):
        return (int(v[0]), int(v[1]))
    if isinstance(v, str) and "," in v:
        a, b = v.strip("()[] ").split(",")[:2]
        return (int(a), int(b))
    return None


def dname(s):
    n = str(s).strip().upper().replace(" ", "_").replace("-", "_")
    n = n[len("DISTRICT_"):] if n.startswith("DISTRICT_") else n
    return n if n in DT.__members__ else None


def parse_city(obj):
    center = None
    for k in ("city_center", "cityCenter", "center", "city_center_location", "city"):
        if k in obj and xy(obj[k]):
            center = xy(obj[k])
            break
    places = {}
    raw = None
    for k in ("placements", "districts", "district_placements", "placement"):
        if k in obj:
            raw = obj[k]
            break
    if isinstance(raw, dict):
        for k, v in raw.items():
            n, c = dname(k), xy(v)
            if n and c:
                places[n] = c
            elif dname(v if isinstance(v, str) else "") and xy(k):  # {"x,y": "CAMPUS"}
                places[dname(v)] = xy(k)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                n = None
                for k in ("district", "type", "district_type", "name"):
                    if k in item and dname(item[k]):
                        n = dname(item[k])
                        break
                c = xy(item)
                if n and c:
                    places[n] = c
    places.pop("CITY_CENTER", None) if center else None
    if center is None and "CITY_CENTER" in places:
        center = places.pop("CITY_CENTER")
    return center, places


def main():
    state = read_stdin()
    path = resolve_path(state.get("answer_path"))
    check = {"answer_path": state.get("answer_path"), "warnings": [], "errors": []}
    if not path or not os.path.isfile(path):
        check["errors"].append("answer file not found (write it, and pass an absolute path)")
        print(json.dumps({"answer_ok": False, "answer_check": check}))
        return
    try:
        with open(path) as f:
            ans = json.load(f)
    except (ValueError, UnicodeDecodeError):
        check["warnings"].append("answer is not JSON; not machine-checked - compare it to the solution by hand")
        print(json.dumps({"answer_ok": True, "answer_check": check}))
        return

    objs = ans.get("cities") if isinstance(ans, dict) and isinstance(ans.get("cities"), list) else [ans]
    cities = [parse_city(o) for o in objs if isinstance(o, dict)]
    cities = [c for c in cities if c[0] is not None]
    if not cities:
        check["warnings"].append("could not find a city center + placements in the answer; "
                                 "not machine-checked - compare it to the solution by hand")
        print(json.dumps({"answer_ok": True, "answer_check": check}))
        return

    scen, _, mp = load_scenario(state)
    tiles = load_map(mp)["tiles"]
    pop = int(scen.get("population", 1) or 1)
    allp = {}
    for center, places in cities:
        allp[center] = DT.CITY_CENTER
        for n, c in places.items():
            allp[c] = DT[n]
    errors = check["errors"]
    named_all = {}
    for i, (center, places) in enumerate(cities):
        rules = PlacementRules(tiles, center, pop)
        for n, c in places.items():
            others = {cc: tt for cc, tt in allp.items() if cc != c}
            res = rules.validate_placement(DT[n], c[0], c[1], others)
            errors += [f"{n}@{c}: {e}" for e in res.errors]
        errors += validate_district_count(places, pop)[1]
        errors += validate_district_uniqueness(places, f"city_{i + 1}")[1]
        named_all[f"city_{i + 1}"] = places
    if len(cities) > 1:
        errors += validate_city_distances([c for c, _ in cities], tiles)[1]
        errors += validate_district_uniqueness({}, "civ", named_all)[1]
    total, _ = AdjacencyCalculator(tiles).calculate_total_adjacency(allp)
    check["recomputed_total"] = total
    claimed = None
    if isinstance(ans, dict):
        for k in ("total_adjacency", "total_adjacency_bonus", "total_bonus", "adjacency_total", "total"):
            if isinstance(ans.get(k), (int, float)):
                claimed = ans[k]
                break
    check["claimed_total"] = claimed
    if claimed is not None and claimed != total:
        errors.append(f"file claims total {claimed} but civ6lib computes {total}")
    sol_total = (state.get("solution") or {}).get("total_adjacency")
    check["optimizer_total"] = sol_total
    if isinstance(sol_total, (int, float)) and total < sol_total:
        errors.append(f"answer scores {total}, below the optimizer's {sol_total}: placements were not copied faithfully")
    print(json.dumps({"answer_ok": not errors, "answer_check": check}))


if __name__ == "__main__":
    main()
