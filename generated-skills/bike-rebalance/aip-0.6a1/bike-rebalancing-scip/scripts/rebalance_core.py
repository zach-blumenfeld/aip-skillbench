"""Shared model, extraction, and checking code for the bike-rebalancing scripts.

Imported by inspect_instance.py, solve.py, polish.py, and verify.py (all run with
cwd = this folder, so a plain import works).
"""
import json
import math
import sys
from pathlib import Path

START = "depot_start"
END = "depot_end"
TOL = 1e-6


# ----------------------------------------------------------------------------- I/O

def read_stdin():
    payload = json.loads(sys.stdin.read() or "{}")
    return payload.get("state", {})


def emit(outputs):
    sys.stdout.write(json.dumps(outputs))
    sys.stdout.write("\n")


def fail(message):
    sys.stderr.write(message.rstrip() + "\n")
    sys.exit(1)


# ----------------------------------------------------------------------- instance

def _num(record, key, label):
    if key not in record:
        raise ValueError(f"{label} is missing '{key}'")
    try:
        value = float(record[key])
    except (TypeError, ValueError):
        raise ValueError(f"{label} has non-numeric '{key}': {record[key]!r}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{label} has non-finite '{key}'")
    return value


def _int(record, key, label):
    value = _num(record, key, label)
    if abs(value - round(value)) > TOL:
        raise ValueError(f"{label} '{key}' must be an integer, got {record[key]!r}")
    return int(round(value))


def _location(record, label):
    lat = _num(record, "latitude", label)
    lon = _num(record, "longitude", label)
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"{label} latitude out of range: {lat}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"{label} longitude out of range: {lon}")
    return lat, lon


def load_instance(path):
    """Parse data.json into plain Python structures; station ids keep their original value."""
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"data file not found: {path}")
    data = json.loads(p.read_text())
    inst = {
        "vehicle_count": _int(data, "vehicle_count", "data"),
        "vehicle_capacity": _int(data, "vehicle_capacity", "data"),
        "penalty_weight": _num(data, "penalty_weight", "data"),
        "distance_metric": str(data.get("distance_metric", "great_circle_miles")),
        "sign_convention": data.get("net_rebalancing_target_sign_convention"),
        "depot": _location(data.get("depot") or {}, "depot"),
        "stations": [],
    }
    if inst["vehicle_count"] < 0 or inst["vehicle_capacity"] < 0:
        raise ValueError("vehicle_count and vehicle_capacity must be >= 0")
    seen = set()
    for k, s in enumerate(data.get("stations") or []):
        if "id" not in s:
            raise ValueError(f"station #{k} has no 'id'")
        sid = s["id"]
        label = f"station {sid}"
        key = str(sid)
        if key in seen:
            raise ValueError(f"duplicate station id {sid}")
        seen.add(key)
        st = {
            "id": sid,
            "loc": _location(s, label),
            "target": _int(s, "net_rebalancing_target", label),
            "initial": _int(s, "initial_bikes", label),
            "capacity": _int(s, "station_capacity", label),
        }
        if st["capacity"] < 0 or not 0 <= st["initial"] <= st["capacity"]:
            raise ValueError(f"{label}: need 0 <= initial_bikes <= station_capacity")
        inst["stations"].append(st)
    return inst


def great_circle_miles(a, b, radius):
    """Spherical law of cosines on colatitudes, as the task's metric defines it."""
    (lat1, lon1), (lat2, lon2) = a, b
    d2r = math.pi / 180.0
    phi1 = (90.0 - lat1) * d2r
    phi2 = (90.0 - lat2) * d2r
    cos_arc = (math.sin(phi1) * math.sin(phi2) * math.cos(lon1 * d2r - lon2 * d2r)
               + math.cos(phi1) * math.cos(phi2))
    cos_arc = max(-1.0, min(1.0, cos_arc))
    return math.acos(cos_arc) * radius


def node_loc(inst, node):
    return inst["depot"] if node in (START, END) else inst["stations"][node]["loc"]


def distance_matrix(inst, radius):
    n = len(inst["stations"])
    nodes_from = [START, *range(n)]
    nodes_to = [*range(n), END]
    return {(i, j): great_circle_miles(node_loc(inst, i), node_loc(inst, j), radius)
            for i in nodes_from for j in nodes_to if i != j}


# -------------------------------------------------------------------------- model

def _set_param(model, name, value):
    try:
        model.setParam(name, value)
    except Exception:
        pass


def build_model(inst, radius, rules):
    """MIP: per-vehicle arc binaries, signed integer service per stop, arc-load flow
    (vehicle load carried on the arc it travels), lifted MTZ order, absolute-deviation
    unmet slack. Returns (model, handles)."""
    from pyscipopt import Model, quicksum

    n = len(inst["stations"])
    K = inst["vehicle_count"]
    Q = inst["vehicle_capacity"]
    must_visit = rules["every_vehicle_must_visit"]
    if K > 0 and n == 0 and must_visit:
        raise ValueError("vehicles must visit a station but data.json has no stations")

    S = list(range(n))
    V = list(range(K))
    nodes_from = [START, *S]
    nodes_to = [*S, END]
    # START->END only exists when a vehicle may stay home; it then models "unused vehicle".
    arcs = [(i, j) for i in nodes_from for j in nodes_to
            if i != j and not (i == START and j == END and must_visit)]
    dist = distance_matrix(inst, radius)
    dist[START, END] = 0.0

    m = Model("bike_rebalancing")
    m.hideOutput()
    for name in ("randomization/randomseedshift", "randomization/permutationseed",
                 "randomization/lpseed"):
        _set_param(m, name, 0)
    _set_param(m, "parallel/maxnthreads", 1)

    x = {(v, i, j): m.addVar(vtype="B", name=f"x_{v}_{i}_{j}") for v in V for i, j in arcs}
    flow = {(v, i, j): m.addVar(vtype="C", lb=0, ub=Q, name=f"load_{v}_{i}_{j}")
            for v in V for i, j in arcs}
    svc = {(v, i): m.addVar(vtype="I", lb=-Q, ub=Q, name=f"svc_{v}_{i}") for v in V for i in S}
    start_ub = Q if rules["loaded_departure_allowed"] else 0
    start_load = {v: m.addVar(vtype="I", lb=0, ub=start_ub, name=f"start_load_{v}") for v in V}
    order = {(v, i): m.addVar(vtype="C", lb=1, ub=max(1, n), name=f"order_{v}_{i}")
             for v in V for i in S}
    unmet = {i: m.addVar(vtype="C", lb=0, name=f"unmet_{i}") for i in S}

    def out_of(v, i, var):
        return [var[v, i, j] for j in nodes_to if (v, i, j) in var]

    def into(v, i, var):
        return [var[v, j, i] for j in nodes_from if (v, j, i) in var]

    for v in V:
        m.addCons(quicksum(out_of(v, START, x)) == 1)
        m.addCons(quicksum(into(v, END, x)) == 1)
        m.addCons(quicksum(out_of(v, START, flow)) == start_load[v])
        for i, j in arcs:
            m.addCons(flow[v, i, j] <= Q * x[v, i, j])        # load only on a travelled arc
        for i in S:
            outgoing = quicksum(out_of(v, i, x))
            m.addCons(quicksum(into(v, i, x)) == outgoing)
            m.addCons(outgoing <= 1)                          # a vehicle visits a station at most once
            m.addCons(svc[v, i] <= Q * outgoing)              # service only where the vehicle stops
            m.addCons(svc[v, i] >= -Q * outgoing)
            # load leaving = load arriving + pickups - dropoffs
            m.addCons(quicksum(out_of(v, i, flow)) - quicksum(into(v, i, flow)) == svc[v, i])
        # lifted MTZ subtour elimination (station-only cycles detached from the depot)
        for i in S:
            for j in S:
                if i < j:
                    m.addCons(x[v, i, j] + x[v, j, i] <= 1)
                if i != j:
                    m.addCons(order[v, i] - order[v, j] + n * x[v, i, j]
                              + max(0, n - 2) * x[v, j, i] <= n - 1)

    # identical vehicles: order them by first station to cut symmetric branches
    for a, b in zip(V, V[1:]):
        first_a = quicksum((j + 1) * x[a, START, j] for j in S)
        first_b = quicksum((j + 1) * x[b, START, j] for j in S)
        m.addCons(first_a <= first_b)

    for i in S:
        st = inst["stations"][i]
        if rules["exclusive_station_visits"]:
            m.addCons(quicksum(x[v, i, j] for v in V for j in nodes_to if (v, i, j) in x) <= 1)
        net = quicksum(svc[v, i] for v in V)                 # pickups minus dropoffs
        m.addCons(net <= st["initial"])                      # final inventory >= 0
        m.addCons(net >= st["initial"] - st["capacity"])     # final inventory <= capacity
        m.addCons(net - st["target"] <= unmet[i])
        m.addCons(st["target"] - net <= unmet[i])

    travel = quicksum(dist[i, j] * x[v, i, j] for v in V for i, j in arcs)
    penalty = inst["penalty_weight"] * quicksum(unmet[i] for i in S)
    m.setObjective(travel + penalty, "minimize")

    return m, {"x": x, "flow": flow, "svc": svc, "start_load": start_load, "order": order,
               "unmet": unmet, "arcs": arcs, "S": S, "V": V,
               "targets": [st["target"] for st in inst["stations"]]}


def _max_flow_min_cut(cap, source, sink, nodes):
    """Edmonds-Karp on a small dense graph; returns (flow value, sink-side node set)."""
    res = {(a, b): cap.get((a, b), 0.0) for a in nodes for b in nodes if a != b}
    total = 0.0
    while True:
        parent = {source: None}
        queue = [source]
        while queue and sink not in parent:
            a = queue.pop(0)
            for b in nodes:
                if b not in parent and a != b and res[a, b] > 1e-9:
                    parent[b] = a
                    queue.append(b)
        if sink not in parent:
            reach = set(parent)
            return total, {b for b in nodes if b not in reach}
        push, b = float("inf"), sink
        while parent[b] is not None:
            push = min(push, res[parent[b], b])
            b = parent[b]
        b = sink
        while parent[b] is not None:
            res[parent[b], b] -= push
            res[b, parent[b]] += push
            b = parent[b]
        total += push


def add_subtour_separator(m, h, freq=1):
    """Exact separation of generalized subtour cuts x_v(in(S)) >= y_vk, k in S, START not in S.
    Only strengthens the LP bound; MTZ in the model already guarantees connected routes."""
    from pyscipopt import Sepa, SCIP_RESULT

    x, S, V = h["x"], h["S"], h["V"]
    nodes = [START, *S]

    class SubtourSepa(Sepa):
        def sepaexeclp(self):
            model = self.model
            found = 0
            for v in V:
                val = {(i, j): model.getSolVal(None, var) for (vv, i, j), var in x.items()
                       if vv == v and j != END}
                y = {k: sum(model.getSolVal(None, var) for (vv, i, j), var in x.items()
                            if vv == v and i == k) for k in S}
                cap = {a: w for a, w in val.items() if w > 1e-6}
                done = []
                for k in sorted(S, key=lambda k: -y[k]):
                    if y[k] < 1e-3 or any(k in cut for cut in done):
                        continue
                    flow_val, sink_side = _max_flow_min_cut(cap, START, k, nodes)
                    if flow_val >= y[k] - 1e-4:
                        continue
                    done.append(sink_side)
                    row = model.createEmptyRowSepa(self, f"gsec_{v}_{k}_{model.getNLPs()}",
                                                   lhs=0.0, rhs=None, local=False, removable=True)
                    model.cacheRowExtensions(row)
                    for i in nodes:
                        if i in sink_side:
                            continue
                        for j in sink_side:
                            if (v, i, j) in x:
                                model.addVarToRow(row, x[v, i, j], 1.0)
                    for j in [*S, END]:
                        if (v, k, j) in x:
                            model.addVarToRow(row, x[v, k, j], -1.0)
                    model.flushRowExtensions(row)
                    model.addCut(row, forcecut=False)
                    found += 1
            return {"result": SCIP_RESULT.SEPARATED if found else SCIP_RESULT.DIDNOTFIND}

    m.includeSepa(SubtourSepa(), "gsec", "generalized subtour elimination cuts",
                  priority=1000, freq=freq, maxbounddist=1.0, usessubscip=False, delay=False)


def plan_from_model(m, h):
    """Read the incumbent into a plan: per vehicle, start_load and [(station_idx, signed_service)]."""
    plan = []
    for v in h["V"]:
        succ = {}
        for (vv, i, j), var in h["x"].items():
            if vv == v and m.getVal(var) > 0.5:
                succ[i] = j
        route, cur, seen = [], START, set()
        while True:
            if cur not in succ:
                raise RuntimeError(f"vehicle {v + 1}: route disconnected at {cur!r}")
            cur = succ[cur]
            if cur == END:
                break
            if cur in seen:
                raise RuntimeError(f"vehicle {v + 1}: cycle at station index {cur}")
            seen.add(cur)
            route.append((cur, int(round(m.getVal(h["svc"][v, cur])))))
        start_load = int(round(m.getVal(h["start_load"][v])))
        plan.append({"start_load": start_load, "stops": route})
    return plan


def plan_from_report(inst, report):
    """Inverse of build_report: recover the plan from a written report.json."""
    id_to_idx = {str(s["id"]): k for k, s in enumerate(inst["stations"])}
    plan = []
    for veh in report["vehicles"]:
        stops = []
        for stop in veh["stops"]:
            idx = id_to_idx[str(stop["station_id"])]
            stops.append((idx, int(round(stop["bikes_picked_up"] - stop["bikes_dropped_off"]))))
        plan.append({"start_load": int(round(veh["start_load"])), "stops": stops})
    return plan


def trivial_plan(inst, radius, rules):
    """Always-feasible start: each vehicle visits its nearest station and moves no bikes
    (or stays home when vehicles may be unused)."""
    n = len(inst["stations"])
    plan = []
    for v in range(inst["vehicle_count"]):
        if not rules["every_vehicle_must_visit"] or n == 0:
            plan.append({"start_load": 0, "stops": []})
            continue
        used = {p["stops"][0][0] for p in plan if p["stops"]} if rules["exclusive_station_visits"] else set()
        cands = [i for i in range(n) if i not in used] or list(range(n))
        best = min(cands, key=lambda i: great_circle_miles(inst["depot"], inst["stations"][i]["loc"], radius))
        plan.append({"start_load": 0, "stops": [(best, 0)]})
    return plan


# ---------------------------------------------------------------------- heuristic

class RouteSearch:
    """Iterated local search over routes; services are filled greedily per route.

    For a fixed start load, greedily picking (dropping) as much as is useful at each stop is
    optimal for one route: one extra bike on board changes later moves by at most one.
    Every allowed start load is tried. Shared stations are split in vehicle order, so the
    value is a lower bound on what the exact fixed-route model (exact_plan) achieves.
    """

    def __init__(self, inst, radius, rules, seed=0):
        import random
        self.rng = random.Random(seed)
        self.n = len(inst["stations"])
        self.K = inst["vehicle_count"]
        self.Q = inst["vehicle_capacity"]
        self.pen = inst["penalty_weight"]
        self.rules = rules
        self.locs = [s["loc"] for s in inst["stations"]] + [inst["depot"]]
        self.D = [[great_circle_miles(a, b, radius) for b in self.locs] for a in self.locs]
        self.pick = [max(0, min(s["target"], s["initial"])) if s["target"] > 0 else 0
                     for s in inst["stations"]]
        self.drop = [max(0, min(-s["target"], s["capacity"] - s["initial"])) if s["target"] < 0 else 0
                     for s in inst["stations"]]
        self.base = sum(abs(s["target"]) for s in inst["stations"])
        self.starts = range(self.Q + 1) if rules["loaded_departure_allowed"] else range(1)

    def _route_moves(self, route, pick, drop):
        best = (-1, 0)
        for s0 in self.starts:
            load, moved = s0, 0
            for i in route:
                if pick[i]:
                    q = min(pick[i], self.Q - load)
                    load += q
                elif drop[i]:
                    q = min(drop[i], load)
                    load -= q
                else:
                    q = 0
                moved += q
            if moved > best[0]:
                best = (moved, s0)
        return best

    def services(self, routes):
        pick, drop = list(self.pick), list(self.drop)
        plan, moved_total = [], 0
        for route in routes:
            moved, s0 = self._route_moves(route, pick, drop)
            load, stops = s0, []
            for i in route:
                if pick[i]:
                    q = min(pick[i], self.Q - load)
                    pick[i] -= q
                    load += q
                    stops.append((i, q))
                elif drop[i]:
                    q = min(drop[i], load)
                    drop[i] -= q
                    load -= q
                    stops.append((i, -q))
                else:
                    stops.append((i, 0))
            moved_total += moved
            plan.append({"start_load": s0, "stops": stops})
        return plan, moved_total

    def cost(self, routes):
        dist = 0.0
        depot = self.n
        for route in routes:
            prev = depot
            for i in route:
                dist += self.D[prev][i]
                prev = i
            if route:
                dist += self.D[prev][depot]
        pick, drop = list(self.pick), list(self.drop)
        moved = 0
        for route in routes:
            m, s0 = self._route_moves(route, pick, drop)
            moved += m
            load = s0
            for i in route:          # consume shared capacity in vehicle order
                if pick[i]:
                    q = min(pick[i], self.Q - load)
                    pick[i] -= q
                    load += q
                elif drop[i]:
                    q = min(drop[i], load)
                    drop[i] -= q
                    load -= q
        return dist + self.pen * (self.base - moved)

    def _ok(self, routes):
        if self.rules["every_vehicle_must_visit"] and any(not r for r in routes):
            return False
        if self.rules["exclusive_station_visits"]:
            flat = [i for r in routes for i in r]
            return len(flat) == len(set(flat))
        return True

    def _neighbours(self, routes):
        K, rng = len(routes), self.rng
        moves = []
        for a in range(K):
            for p in range(len(routes[a])):
                moves.append(("remove", a, p))
                for b in range(K):
                    for q in range(len(routes[b]) + (0 if a == b else 1)):
                        moves.append(("move", a, p, b, q))
            for p in range(len(routes[a])):
                for q in range(p + 2, len(routes[a]) + 1):
                    moves.append(("rev", a, p, q))
        for i in range(self.n):
            if not (self.pick[i] or self.drop[i]):
                continue
            for b in range(K):
                if i in routes[b]:
                    continue
                for q in range(len(routes[b]) + 1):
                    moves.append(("add", i, b, q))
        for a in range(K):
            for b in range(a + 1, K):
                for p in range(len(routes[a])):
                    for q in range(len(routes[b])):
                        moves.append(("swap", a, p, b, q))
        rng.shuffle(moves)
        for mv in moves:
            r = [list(x) for x in routes]
            kind = mv[0]
            if kind == "remove":
                r[mv[1]].pop(mv[2])
            elif kind == "move":
                _, a, p, b, q = mv
                i = r[a].pop(p)
                if a != b and i in r[b]:
                    continue
                r[b].insert(q, i)
            elif kind == "rev":
                _, a, p, q = mv
                r[a][p:q] = reversed(r[a][p:q])
            elif kind == "add":
                _, i, b, q = mv
                r[b].insert(q, i)
            else:
                _, a, p, b, q = mv
                if r[a][p] in r[b] or r[b][q] in r[a]:
                    continue
                r[a][p], r[b][q] = r[b][q], r[a][p]
            if self._ok(r):
                yield r

    def local_search(self, routes, deadline):
        import time
        cur = self.cost(routes)
        improved = True
        while improved and time.time() < deadline:
            improved = False
            for cand in self._neighbours(routes):
                c = self.cost(cand)
                if c < cur - 1e-9:
                    routes, cur, improved = cand, c, True
                    break
                if time.time() >= deadline:
                    break
        return routes, cur

    def initial(self):
        """Angular sweep around the depot into K contiguous groups."""
        dep = self.n
        (dlat, dlon) = self.locs[dep]
        active = [i for i in range(self.n) if self.pick[i] or self.drop[i]] or list(range(self.n))
        active.sort(key=lambda i: math.atan2(self.locs[i][0] - dlat, self.locs[i][1] - dlon))
        size = max(1, -(-len(active) // max(1, self.K)))
        routes = [active[k * size:(k + 1) * size] for k in range(self.K)]
        for r in routes:
            if not r and self.rules["every_vehicle_must_visit"] and self.n:
                used = {i for x in routes for i in x}
                free = [i for i in range(self.n) if i not in used] or list(range(self.n))
                r.append(min(free, key=lambda i: self.D[dep][i]))
        return routes

    def run(self, time_budget, start=None):
        import time
        deadline = time.time() + time_budget
        first = start if start is not None and self._ok(start) else self.initial()
        best, best_cost = self.local_search(first, deadline)
        cur, cur_cost = best, best_cost
        while time.time() < deadline:
            r = [list(x) for x in cur]
            for _ in range(self.rng.randint(2, 4)):      # perturb: random relocations
                a = self.rng.randrange(len(r))
                if not r[a]:
                    continue
                i = r[a].pop(self.rng.randrange(len(r[a])))
                b = self.rng.randrange(len(r))
                if i not in r[b]:
                    r[b].insert(self.rng.randint(0, len(r[b])), i)
            if not self._ok(r):
                continue
            r, c = self.local_search(r, deadline)
            if c < best_cost - 1e-9:
                best, best_cost = r, c
            cur, cur_cost = (r, c) if c < cur_cost + 0.02 * abs(cur_cost) else (best, best_cost)
        return best, best_cost


def heuristic_routes(inst, radius, rules, time_budget, seed=0, start=None):
    if inst["vehicle_count"] == 0 or not inst["stations"]:
        return [[] for _ in range(inst["vehicle_count"])]
    search = RouteSearch(inst, radius, rules, seed)
    routes, _ = search.run(time_budget, start)
    return routes


def heuristic_budget(time_limit):
    """Share of a time limit spent on route search before SCIP gets the rest."""
    return max(3.0, min(15.0, 0.1 * float(time_limit)))


def warm_start(m, h, inst, radius, rules, time_limit, seed=0, start_routes=None):
    """Seed SCIP with the always-feasible trivial plan and the route-search plan.
    Returns the SCIP time left."""
    import time
    t0 = time.time()
    add_plan_as_solution(m, h, trivial_plan(inst, radius, rules))
    budget = heuristic_budget(time_limit)
    routes = heuristic_routes(inst, radius, rules, budget, seed, start_routes)
    plan = exact_plan(inst, radius, rules, routes, time_limit=max(5.0, 0.1 * float(time_limit)))
    if plan is not None:
        add_plan_as_solution(m, h, plan)
    return max(1.0, float(time_limit) - (time.time() - t0))


def exact_plan(inst, radius, rules, routes, time_limit=30.0):
    """Optimal services and start loads for fixed routes (all arc binaries fixed)."""
    # match the model's symmetry cut: vehicles ordered by first station index
    routes = sorted(routes, key=lambda r: r[0] + 1 if r else 0)
    m, h = build_model(inst, radius, rules)
    used = set()
    for v, route in enumerate(routes):
        nodes = [START, *route, END]
        used.update((v, a, b) for a, b in zip(nodes, nodes[1:]))
    for key, var in h["x"].items():
        val = 1.0 if key in used else 0.0
        m.chgVarLb(var, val)
        m.chgVarUb(var, val)
    for (v, i), var in h["order"].items():
        if i in routes[v]:
            pos = routes[v].index(i) + 1
            m.chgVarLb(var, pos)
            m.chgVarUb(var, pos)
    m.setParam("limits/time", float(time_limit))
    m.optimize()
    if m.getNSols() == 0:
        return None
    return plan_from_model(m, h)


def add_plan_as_solution(m, h, plan):
    """Hand a plan to SCIP as a primal solution. Returns True if SCIP accepted it."""
    # match the model's symmetry cut: vehicles ordered by first station index
    plan = sorted(plan, key=lambda veh: veh["stops"][0][0] + 1 if veh["stops"] else 0)
    sol = m.createSol()
    order_pos = {}
    net = {}
    for v, veh in enumerate(plan):
        nodes = [START, *[i for i, _ in veh["stops"]], END]
        cur = veh["start_load"]
        m.setSolVal(sol, h["start_load"][v], cur)
        for pos, (a, b) in enumerate(zip(nodes, nodes[1:])):
            if (v, a, b) not in h["x"]:
                return False
            m.setSolVal(sol, h["x"][v, a, b], 1.0)
            m.setSolVal(sol, h["flow"][v, a, b], cur)
            if b != END:
                change = veh["stops"][pos][1]
                cur += change
                m.setSolVal(sol, h["svc"][v, b], change)
                order_pos[v, b] = pos + 1
                net[b] = net.get(b, 0) + change
    for (v, i), var in h["order"].items():
        m.setSolVal(sol, var, order_pos.get((v, i), 1))
    for i, var in h["unmet"].items():
        m.setSolVal(sol, var, abs(h["targets"][i] - net.get(i, 0)))
    return bool(m.addSol(sol, free=True))


def solve(m, time_limit):
    m.setParam("limits/time", float(time_limit))
    m.optimize()
    status = str(m.getStatus()).lower()
    if m.getNSols() == 0:
        raise RuntimeError(f"SCIP found no feasible solution; status={status}")
    gap = float(m.getGap())
    if math.isinf(gap) or math.isnan(gap):
        gap = 1e9
    return ("optimal" if status == "optimal" else "incumbent"), float(m.getObjVal()), gap


# ------------------------------------------------------------------------- report

def build_report(inst, radius, plan):
    stations = inst["stations"]
    vehicles = []
    picked = [0] * len(stations)
    dropped = [0] * len(stations)
    travel = 0.0
    for v, veh in enumerate(plan):
        cur = veh["start_load"]
        stops = []
        prev = inst["depot"]
        for i, change in veh["stops"]:
            loc = stations[i]["loc"]
            travel += great_circle_miles(prev, loc, radius)
            prev = loc
            up, down = max(change, 0), max(-change, 0)
            cur += change
            picked[i] += up
            dropped[i] += down
            stops.append({"station_id": stations[i]["id"], "bikes_picked_up": float(up),
                          "bikes_dropped_off": float(down), "load_after_stop": float(cur)})
        if veh["stops"]:
            travel += great_circle_miles(prev, inst["depot"], radius)
        vehicles.append({
            "vehicle_id": v + 1,
            "start_load": float(veh["start_load"]),
            "route": [START, *[stations[i]["id"] for i, _ in veh["stops"]], END],
            "stops": stops,
            "end_load": float(cur),
        })
    station_rows = []
    total_unmet = 0
    for i, st in enumerate(stations):
        net = picked[i] - dropped[i]
        un = abs(st["target"] - net)
        total_unmet += un
        station_rows.append({
            "station_id": st["id"], "net_rebalancing_target": float(st["target"]),
            "total_bikes_picked_up": float(picked[i]), "total_bikes_dropped_off": float(dropped[i]),
            "net_bike_change": float(net), "unmet_rebalancing_amount": float(un),
        })
    penalty = inst["penalty_weight"] * total_unmet
    return {
        "summary": {
            "objective": travel + penalty,
            "travel_distance_miles": travel,
            "unmet_rebalancing_penalty": float(penalty),
            "total_unmet_rebalancing_amount": float(total_unmet),
        },
        "vehicles": vehicles,
        "stations": station_rows,
    }


def write_report(path, report):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2) + "\n")


def rules_from_state(state):
    return {
        "loaded_departure_allowed": bool(state["loaded_departure_allowed"]),
        "every_vehicle_must_visit": bool(state["every_vehicle_must_visit"]),
        "exclusive_station_visits": bool(state["exclusive_station_visits"]),
    }
