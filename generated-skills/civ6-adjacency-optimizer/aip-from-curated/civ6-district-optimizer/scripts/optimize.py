"""Step `optimize`: choose city center(s) and district placements that maximize
total adjacency bonus, then validate and score the result with civ6lib verbatim.

stdin currentState keys used:
  scenario_path (str), map_path (str, optional), district_pool (str:
  specialty_only | with_infrastructure | all), center_mode (str: free |
  start_position | existing_city | given), fixed_city_centers (list of [x, y],
  only for center_mode=given), allowed_districts (list of names, optional;
  overrides district_pool), time_limit_s (number, optional, default 240).
stdout: {"solution": {...}, "total_adjacency": int, "solution_valid": bool}

Search (map-optimization-strategy): prune tiles with civ6lib PlacementRules,
score (type, tile) pairs, then branch-and-bound over district types per
candidate center, seeded by a greedy solution. The fast scorer is built from
civ6lib's own per-neighbor rule matching, and the final answer is re-scored
with AdjacencyCalculator.calculate_total_adjacency, so reported numbers are
civ6lib's numbers.
"""

import json
import sys
import time

sys.dont_write_bytecode = True  # keep the skill folder free of __pycache__

from civ6map import load_map, load_scenario, read_stdin

from adjacency_rules import (AdjacencyCalculator, DISTRICT_ADJACENCY_RULES,  # noqa: E402
                             DISTRICTS_FOR_ADJACENCY)
from hex_utils import get_neighbors, get_tiles_in_range, hex_distance  # noqa: E402
from placement_rules import (DistrictType as DT, PlacementRules,  # noqa: E402
                             calculate_max_specialty_districts, validate_city_distances,
                             validate_district_count, validate_district_uniqueness)

SPECIALTY = [DT.CAMPUS, DT.HOLY_SITE, DT.THEATER_SQUARE, DT.COMMERCIAL_HUB, DT.HARBOR,
             DT.INDUSTRIAL_ZONE, DT.GOVERNMENT_PLAZA, DT.ENTERTAINMENT_COMPLEX, DT.WATER_PARK,
             DT.DIPLOMATIC_QUARTER, DT.ENCAMPMENT, DT.AERODROME, DT.PRESERVE]
INFRA = [DT.AQUEDUCT, DT.DAM, DT.CANAL]
EXTRA = [DT.NEIGHBORHOOD, DT.SPACEPORT]
POOLS = {"specialty_only": SPECIALTY, "with_infrastructure": SPECIALTY + INFRA,
         "all": SPECIALTY + INFRA + EXTRA}
ONE_PER_CIV = {DT.GOVERNMENT_PLAZA, DT.DIPLOMATIC_QUARTER}


class Scorer:
    """Exact re-implementation of AdjacencyCalculator totals, decomposed per
    neighbor. Each (rule, neighbor, district-on-neighbor) match is computed by
    civ6lib's count_rule_sources on a one-tile map and cached."""

    def __init__(self, tiles):
        self.tiles = tiles
        self.calc = AdjacencyCalculator(tiles)
        self.rules = {t: list(r) for t, r in DISTRICT_ADJACENCY_RULES.items()}
        self._nm = {}
        self._destroyed = {}
        self._ds = {}

    def destroyed(self, n, t):
        key = (n, t)
        if key not in self._destroyed:
            mini = AdjacencyCalculator({n: self.tiles[n]})
            self._destroyed[key] = mini.apply_destruction({n: t})[n]
        return self._destroyed[key]

    def nm(self, rule, d, n, ptype):
        """1 if neighbor n (holding ptype or nothing) matches `rule` for a district at d."""
        key = (id(rule), n, ptype)
        v = self._nm.get(key)
        if v is None:
            if n not in self.tiles:
                v = 0
            else:
                tile = self.tiles[n] if ptype is None else self.destroyed(n, ptype)
                v, _ = self.calc.count_rule_sources(d[0], d[1], rule, {n: tile},
                                                    {n: ptype} if ptype is not None else {})
            self._nm[key] = v
        return v

    def district_score(self, c, t, P):
        rules = self.rules.get(t)
        if not rules:
            return 0
        nbrs = get_neighbors(*c)
        key = (c, t, tuple(P.get(n) for n in nbrs))
        v = self._ds.get(key)
        if v is None:
            v = self._ds[key] = self._district_score(c, t, P, rules, nbrs)
        return v

    def _district_score(self, c, t, P, rules, nbrs):
        s = 2 if (t == DT.COMMERCIAL_HUB and self.tiles[c].has_river) else 0
        for r in rules:
            cnt = 0
            for n in nbrs:
                cnt += self.nm(r, c, n, P.get(n))
            s += cnt * r.bonus_per if r.count_required == 1 else (cnt // r.count_required) * r.bonus_per
        return s

    def total(self, P):
        return sum(self.district_score(c, t, P) for c, t in P.items() if t != DT.CITY_CENTER)


def valid_center(tile, c, blocked, occupied):
    return (tile is not None and not tile.is_water and not tile.is_mountain
            and not tile.is_natural_wonder and c not in blocked and c not in occupied)


# Districts whose contributions are identical (no own adjacency; same effect on
# neighbors), so swapping two of them never changes the total.
SYMMETRIC = [{DT.AQUEDUCT, DT.DAM, DT.CANAL}, {DT.NEIGHBORHOOD, DT.SPACEPORT}]


class CitySearch:
    """Branch-and-bound for one city center. fixed: {coord: DT} already on the
    map (this city's center included)."""

    def __init__(self, sc, tiles, blocked, center, fixed, pool, k):
        self.sc, self.tiles, self.center, self.fixed, self.k = sc, tiles, center, fixed, k
        rules_obj = PlacementRules(tiles, center, 0)
        in_range = [c for c in get_tiles_in_range(center[0], center[1], 3)
                    if c in tiles and c not in blocked and c not in fixed]
        cand = {}
        for t in pool:
            cs = [c for c in in_range if rules_obj.validate_placement(t, c[0], c[1], fixed).valid]
            if cs:
                cand[t] = cs
        # Dominance: a Diplomatic Quarter is valid wherever an Encampment, Aerodrome or
        # Preserve is and contributes the same (a +0.5 district, no own adjacency).
        if DT.DIPLOMATIC_QUARTER in cand:
            for t in (DT.ENCAMPMENT, DT.AERODROME, DT.PRESERVE):
                cand.pop(t, None)
        self.cand = cand
        self.cset = {t: set(cs) for t, cs in cand.items()}
        self.types = types = list(cand)
        self.base = base = sc.total(fixed)
        self.nodes = 0
        self.exact = True
        if not types:
            self.root_ub, self.best = base, [base, {}]
            return
        n_spec_types = sum(1 for t in types if t not in INFRA + EXTRA)
        self.d_max = min(k, n_spec_types) + sum(1 for t in types if t in INFRA + EXTRA)
        on_tile = {}
        for t, cs in cand.items():
            for c in cs:
                on_tile.setdefault(c, []).append(t)
        self.on_tile = on_tile
        self.tile_ub = {t: {c: self.self_ub(t, c) for c in cand[t]} for t in types}
        self.sub = {t: max(self.tile_ub[t].values()) for t in types}
        # inc[x][d]: most a district of type x can add to an adjacent district of type d.
        self.inc = {x: {d: sum(r.bonus_per for r in rules
                               if any(s == x.name or (s == "DISTRICT" and x in DISTRICTS_FOR_ADJACENCY)
                                      for s in r.sources))
                        for d, rules in sc.rules.items()} for x in types}
        static = {t: {c: sc.total({**fixed, c: t}) - base for c in cand[t]} for t in types}
        self.by_ub = {t: sorted(cand[t], key=lambda c: (-self.tile_ub[t][c], -static[t][c], c))
                      for t in types}
        self.order = sorted(types, key=lambda t: -self.sub[t])  # stable: GP, EC before DQ
        self.reach = {x: {n for c in cand[x] for n in get_neighbors(*c)} for x in types}
        self.near_fixed = [(c, t) for c, t in fixed.items()
                           if t in sc.rules and hex_distance(*c, *center) <= 4]
        self.A = dict(fixed)
        self.best = list(self.greedy())
        self.root_ub = base + self.ub_rest(0, {}, 0)

    def rule_cap(self, r, t):
        """Neighbors that can gain a match for rule r from districts still to place:
        any district for "DISTRICT", otherwise one per matching type (one of each)."""
        if "DISTRICT" in r.sources:
            return max(0, self.d_max - 1)
        return sum(1 for u in self.types if u != t and u.name in r.sources)

    def self_ub(self, t, c):
        sc = self.sc
        rules = sc.rules.get(t)
        if not rules:
            return 0
        s = 2 if (t == DT.COMMERCIAL_HUB and self.tiles[c].has_river) else 0
        for r in rules:
            cnt, gains = 0, []
            for n in get_neighbors(*c):
                if n in self.fixed:
                    cnt += sc.nm(r, c, n, self.fixed[n])
                    continue
                v0 = sc.nm(r, c, n, None)
                vb = max([sc.nm(r, c, n, u) for u in self.on_tile.get(n, []) if u != t] or [0])
                cnt += v0
                if vb > v0:
                    gains.append(vb - v0)
            cnt += sum(sorted(gains, reverse=True)[:self.rule_cap(r, t)])
            s += cnt * r.bonus_per if r.count_required == 1 else (cnt // r.count_required) * r.bonus_per
        return s

    def greedy(self):
        """Seed: repeatedly add the (type, tile) with the best total while it helps."""
        sc, fixed, k = self.sc, self.fixed, self.k
        P, spec, cur = {}, 0, self.base
        while True:
            mv = None
            for t in self.types:
                if t in P.values() or (t not in INFRA + EXTRA and spec >= k):
                    continue
                for c in self.cand[t]:
                    if c not in P:
                        v = sc.total({**fixed, **P, c: t})
                        if v > cur and (mv is None or v > mv[0]):
                            mv = (v, t, c)
            if not mv:
                return cur, P
            cur, t, c = mv
            P[c] = t
            spec += t not in INFRA + EXTRA

    def ub_rest(self, i, P, spec, tight=False):
        """Optimistic value still obtainable from types order[i:]."""
        sc = self.sc
        placed = [(c, t) for c, t in P.items() if t in sc.rules] + self.near_fixed
        spec_vals, free_vals = [], []
        for t in self.order[i:]:
            inc = self.inc[t]
            if tight:  # best single tile: own bound plus what it adds to placed neighbors
                A = self.A
                g = 0
                for c in self.cand[t]:
                    if c in A:
                        continue
                    v = self.tile_ub[t][c] + sum(inc[A[n]] for n in get_neighbors(*c) if A.get(n) in sc.rules)
                    g = max(g, v)
            else:
                g = self.sub[t] + sum(sorted((inc[d] for c, d in placed if c in self.reach[t]),
                                             reverse=True)[:6])
            if g > 0:
                (free_vals if t in INFRA + EXTRA else spec_vals).append(g)
        spec_vals.sort(reverse=True)
        return sum(spec_vals[:max(0, self.k - spec)]) + sum(free_vals)

    def local(self, c):
        """Score of c and its scoring neighbors under A."""
        tot = 0
        A, sc = self.A, self.sc
        for d in [c] + get_neighbors(*c):
            t = A.get(d)
            if t is not None and t in sc.rules:
                tot += sc.district_score(d, t, A)
        return tot

    def allowed_here(self, t, c, P):
        if t == DT.DIPLOMATIC_QUARTER:  # Government Plaza and Entertainment Complex dominate it
            for u in (DT.GOVERNMENT_PLAZA, DT.ENTERTAINMENT_COMPLEX):
                if u in self.cand and u not in P.values():
                    return False
        for grp in SYMMETRIC:
            if t in grp:
                for cu, u in P.items():
                    if u in grp and u != t and c in self.cset[u] and cu in self.cset[t] and c < cu:
                        return False
        return True

    def run(self, deadline, floor_score):
        if not self.types:
            return
        self.deadline, self.floor = deadline, floor_score
        try:
            self.dfs(0, {}, 0, self.base)
        except TimeoutError:
            self.exact = False

    def target(self):
        return max(self.best[0], self.floor)

    def dfs(self, i, P, spec, cur_total):
        self.nodes += 1
        if self.nodes % 1024 == 0 and time.time() > self.deadline:
            raise TimeoutError
        if cur_total > self.best[0]:
            self.best = [cur_total, dict(P)]
        if i == len(self.order):
            return
        if cur_total + self.ub_rest(i, P, spec) <= self.target():
            return
        if cur_total + self.ub_rest(i, P, spec, tight=True) <= self.target():
            return
        t = self.order[i]
        is_free = t in INFRA + EXTRA
        spec2 = spec + (0 if is_free else 1)
        if is_free or spec < self.k:
            A, sc, inc = self.A, self.sc, self.inc[t]
            rest = self.ub_rest(i + 1, P, spec2)
            for c in self.by_ub[t]:
                if c in A or not self.allowed_here(t, c, P):
                    continue
                give = sum(inc[A[n]] for n in get_neighbors(*c) if A.get(n) in sc.rules)
                if cur_total + self.tile_ub[t][c] + give + rest <= self.target():
                    continue
                before = self.local(c)
                A[c] = t
                P[c] = t
                child = cur_total + self.local(c) - before
                self.dfs(i + 1, P, spec2, child)
                del A[c]
                del P[c]
        self.dfs(i + 1, P, spec, cur_total)

    def result(self):
        """Best placements, with unused specialty slots filled by districts that do
        not lower the total."""
        sc, fixed = self.sc, self.fixed
        score, P = self.best[0], dict(self.best[1])
        spec = sum(1 for t in P.values() if t not in INFRA + EXTRA)
        while spec < self.k:
            mv = None
            for t in self.types:
                if t in INFRA + EXTRA or t in P.values():
                    continue
                for c in self.cand[t]:
                    if c not in P:
                        v = sc.total({**fixed, **P, c: t})
                        if v >= score and (mv is None or v > mv[0]):
                            mv = (v, t, c)
            if not mv:
                break
            score, t, c = mv
            P[c] = t
            spec += 1
        return score, P


def main():
    state = read_stdin()
    t0 = time.time()
    scen, sp, mp = load_scenario(state)
    m = load_map(mp)
    tiles, blocked = m["tiles"], m["blocked"]
    pop = int(scen.get("population", state.get("population", 1)) or 1)
    ncities = int(scen.get("num_cities", 1) or 1)
    k = calculate_max_specialty_districts(pop)
    pool_name = state.get("district_pool") or "with_infrastructure"
    if pool_name not in POOLS:
        raise SystemExit(json.dumps({"error": f"district_pool must be one of {list(POOLS)}"}))
    allowed = state.get("allowed_districts") or []
    if allowed:  # an explicit list from the task overrides the pool
        names = {str(a).strip().upper().replace(" ", "_").replace("DISTRICT_", "") for a in allowed}
        unknown = sorted(n for n in names if n not in DT.__members__)
        if unknown:
            raise SystemExit(json.dumps({"error": f"unknown district names in allowed_districts: {unknown}"}))
        POOLS["custom"] = [t for t in POOLS["all"] if t.name in names]
        pool_name = "custom"
    mode = state.get("center_mode") or "free"
    limit = float(state.get("time_limit_s") or 240)
    deadline = t0 + limit
    sc = Scorer(tiles)

    # Pre-existing districts on the map stay where they are and count as neighbors.
    fixed = {}
    for d in m["districts"]:
        name = d["type"].replace("DISTRICT_", "")
        if name in DT.__members__:
            fixed[tuple(d["xy"])] = DT[name]

    start_note = None
    if mode == "given":
        forced = [tuple(c) for c in (state.get("fixed_city_centers") or [])]
        if not forced:
            raise SystemExit(json.dumps({"error": "center_mode=given needs fixed_city_centers [[x,y],...]"}))
    elif mode == "start_position":
        sps = sorted(m["start_positions"], key=lambda s: str(s["value"]))
        forced = [tuple(s["xy"]) for s in sps]
        if len(forced) > ncities:
            start_note = (f"{len(forced)} start positions for {ncities} city(ies); used them in player "
                          f"order: {[list(c) for c in forced[:ncities]]} (set center_mode=given to pick others)")
    elif mode == "existing_city":
        forced = [tuple(c["xy"]) for c in m["cities"]]
    else:
        forced = []
    start_xy = {tuple(s["xy"]) for s in m["start_positions"]}

    cities = []
    notes = [start_note] if start_note else []
    center_errors = []
    used_civ = set()
    all_exact = True
    total_nodes = 0
    for ci in range(ncities):
        pool = [t for t in POOLS[pool_name] if t not in used_civ]
        if ci < len(forced):
            centers = [forced[ci]]
            fc = forced[ci]
            if not valid_center(tiles.get(fc), fc, blocked, fixed):
                notes.append(f"city {ci + 1}: forced center {list(fc)} is not a valid settle tile "
                             "(water, mountain, natural wonder, ice, occupied or off-map)")
                center_errors.append(f"invalid city center {list(fc)}")
                continue
        else:
            if mode != "free":
                notes.append(f"only {len(forced)} centers available for mode {mode}; "
                             f"choosing city {ci + 1} freely")
            centers = [c for c, t in tiles.items()
                       if valid_center(t, c, blocked, fixed)
                       and validate_city_distances([cc["center"] for cc in cities] + [c], tiles)[0]]
        city_deadline = time.time() + max(5.0, (deadline - time.time()) / (ncities - ci))
        searches = [CitySearch(sc, tiles, blocked, c, {**fixed, c: DT.CITY_CENTER}, pool, k)
                    for c in centers]
        # Best-first over anchors: highest optimistic bound first, start position on ties.
        searches.sort(key=lambda s_: (-s_.root_ub, s_.center not in start_xy, s_.center[1], s_.center[0]))
        best_score = max((s_.best[0] for s_ in searches), default=-1)
        for s_ in searches:
            if s_.root_ub <= best_score:
                continue  # cannot beat the best total found so far
            if time.time() > city_deadline:
                all_exact = False
                notes.append(f"city {ci + 1}: time limit reached; remaining centers kept their greedy result")
                break
            s_.run(city_deadline, best_score)
            all_exact &= s_.exact
            best_score = max(best_score, s_.best[0])
        best = None
        per_center = []
        for s_ in searches:
            total_nodes += s_.nodes
            score, P = s_.result()
            per_center.append((score, s_.center))
            nspec = sum(1 for t in P.values() if t not in INFRA + EXTRA)
            cand_key = (score, nspec, -len(P), s_.center in start_xy, -s_.center[1], -s_.center[0])
            if best is None or cand_key > best[3]:
                best = (score, s_.center, P, cand_key)
        if best is None:
            notes.append(f"no valid city center for city {ci + 1}")
            break
        score, center, P, _ = best
        fixed = {**fixed, center: DT.CITY_CENTER, **P}
        used_civ |= {t for t in P.values() if t in ONE_PER_CIV}
        per_center.sort(key=lambda x: (-x[0], x[1][1], x[1][0]))
        cities.append({"center": center, "placements": P,
                       "top_centers": [{"city_center": list(c), "total_at_least": s_} for s_, c in per_center[:5]]})

    # Re-score and validate everything with civ6lib verbatim.
    calc = AdjacencyCalculator(tiles)
    total, per = calc.calculate_total_adjacency(fixed)
    errors = list(center_errors)
    out_cities = []
    all_named = {}
    for i, city in enumerate(cities):
        rules_obj = PlacementRules(tiles, city["center"], pop)
        named = {}
        for c, t in city["placements"].items():
            others = {cc: tt for cc, tt in fixed.items() if cc != c}
            res = rules_obj.validate_placement(t, c[0], c[1], others)
            if not res.valid:
                errors.extend(f"{t.name}@{c}: {e}" for e in res.errors)
            named[t.name] = list(c)
        ok, errs = validate_district_count({n: tuple(v) for n, v in named.items()}, pop)
        errors += errs
        ok, errs = validate_district_uniqueness({n: tuple(v) for n, v in named.items()}, f"city_{i + 1}")
        errors += errs
        all_named[f"city_{i + 1}"] = {n: tuple(v) for n, v in named.items()}
        adj = {t.name: per[f"{t.name}@({c[0]},{c[1]})"].total_bonus
               for c, t in city["placements"].items() if f"{t.name}@({c[0]},{c[1]})" in per}
        out_cities.append({"city_center": list(city["center"]), "placements": named,
                           "district_adjacency": adj, "total_adjacency": sum(adj.values()),
                           "top_centers": city["top_centers"]})
    if len(cities) > 1:
        ok, errs = validate_city_distances([c["center"] for c in cities], tiles)
        errors += errs
        ok, errs = validate_district_uniqueness({}, "civ", all_named)
        errors += errs

    per_out = {k_: {"total_bonus": v.total_bonus,
                    "breakdown": {bk: {kk: vv for kk, vv in bv.items()} for bk, bv in v.breakdown.items()}}
               for k_, v in per.items()}
    solution = {
        "scenario_id": scen.get("id"),
        "population": pop,
        "num_cities": ncities,
        "max_specialty_districts": k,
        "district_pool": pool_name,
        "center_mode": mode,
        "city_center": out_cities[0]["city_center"] if out_cities else None,
        "placements": out_cities[0]["placements"] if out_cities else {},
        "total_adjacency": total,
        "cities": out_cities,
        "per_district": per_out,
        "validation_errors": errors,
        "search": {"exact": all_exact, "nodes": total_nodes,
                   "seconds": round(time.time() - t0, 2), "notes": notes},
    }
    print(json.dumps({"solution": solution, "total_adjacency": total,
                      "solution_valid": not errors and bool(out_cities)}))


if __name__ == "__main__":
    main()
