#!/usr/bin/env python3
"""Bike-station rebalancing VRP solved as a MIP with SCIP (PySCIPOpt).

Requires: Python >= 3.10, pyscipopt (tested with 6.1.0). Standard library otherwise.

Reads data.json (vehicle_count, vehicle_capacity, penalty_weight, depot{latitude,longitude},
stations[{id, latitude, longitude, net_rebalancing_target, initial_bikes, station_capacity}])
and writes report.json with summary / vehicles / stations. Every number in the report is
recomputed from the extracted routes, not copied from the solver objective.

Usage:
  python scripts/solve_rebalance.py --data /root/data.json --out /root/report.json \
      [--start-load free|zero] [--allow-idle-vehicles] [--no-split-service] \
      [--subtour cut|mtz|flow] [--dominance] [--radius 3960.0] [--time-limit 300] [--gap 0.0]
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

try:
    from pyscipopt import SCIP_RESULT, Conshdlr, Model, quicksum
except ImportError as exc:  # do not install another solver; the container ships pyscipopt
    sys.exit(f"ERROR: PySCIPOpt is required (pip name: pyscipopt): {exc}")

START = "depot_start"
END = "depot_end"


def fail(msg):
    sys.exit(f"ERROR: {msg}")


def parse_location(record, label):
    try:
        lat = float(record["latitude"])
        lon = float(record["longitude"])
    except (KeyError, TypeError, ValueError) as exc:
        fail(f"{label} has no usable latitude/longitude: {exc}")
    if not -90.0 <= lat <= 90.0:
        fail(f"{label} latitude out of range: {lat}")
    if not -180.0 <= lon <= 180.0:
        fail(f"{label} longitude out of range: {lon}")
    return lat, lon


def great_circle_miles(a, b, radius):
    """Spherical law of cosines on colatitudes; degrees in, miles out (unrounded)."""
    d2r = math.pi / 180.0
    phi1, phi2 = (90.0 - a[0]) * d2r, (90.0 - b[0]) * d2r
    th1, th2 = a[1] * d2r, b[1] * d2r
    c = math.sin(phi1) * math.sin(phi2) * math.cos(th1 - th2) + math.cos(phi1) * math.cos(phi2)
    return math.acos(max(-1.0, min(1.0, c))) * radius


def load_data(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path}: {exc}")
    for key in ("vehicle_count", "vehicle_capacity", "penalty_weight", "depot", "stations"):
        if key not in data:
            fail(f"data.json missing key '{key}'")
    metric = data.get("distance_metric", "great_circle_miles")
    if metric != "great_circle_miles":
        print(f"WARNING: distance_metric is {metric!r}; this script computes great_circle_miles", file=sys.stderr)
    stations = data["stations"]
    if not stations:
        fail("no stations")
    ids = [int(s["id"]) for s in stations]
    if len(ids) != len(set(ids)):
        fail("duplicate station ids")
    for s in stations:
        for key in ("net_rebalancing_target", "initial_bikes", "station_capacity"):
            if key not in s:
                fail(f"station {s.get('id')} missing '{key}'")
    return data


def build_and_solve(data, args):
    K = int(data["vehicle_count"])
    C = int(data["vehicle_capacity"])
    pw = float(data["penalty_weight"])
    st = data["stations"]
    n = len(st)
    ids = [int(s["id"]) for s in st]
    target = [int(round(float(s["net_rebalancing_target"]))) for s in st]
    init = [int(round(float(s["initial_bikes"]))) for s in st]
    cap = [int(round(float(s["station_capacity"]))) for s in st]
    if K < 1 or C < 0:
        fail(f"bad vehicle_count={K} or vehicle_capacity={C}")
    if not args.allow_idle_vehicles and K > n and args.no_split_service:
        fail(f"{K} vehicles must each visit a station but only {n} stations and no split service")

    depot = parse_location(data["depot"], "depot")
    loc = [parse_location(s, f"station {s['id']}") for s in st]
    S = range(n)
    V = range(K)

    def where(node):
        return depot if node in (START, END) else loc[node]

    from_nodes = [START, *S]
    to_nodes = [*S, END]
    arcs = [(i, j) for i in from_nodes for j in to_nodes
            if i != j and not (i == START and j == END and not args.allow_idle_vehicles)]
    dist = {(i, j): great_circle_miles(where(i), where(j), args.radius) for i, j in arcs}

    m = Model("bike_rebalancing")
    m.hideOutput()
    for name, val in [("randomization/randomseedshift", 0), ("randomization/permutationseed", 0),
                      ("randomization/lpseed", 0), ("parallel/maxnthreads", 1)]:
        try:
            m.setParam(name, val)
        except Exception:
            pass

    x = {(v, i, j): m.addVar(vtype="B", name=f"x_{v}_{i}_{j}") for v in V for i, j in arcs}
    out_arcs = {i: [j for (a, j) in arcs if a == i] for i in from_nodes}
    in_arcs = {j: [i for (i, b) in arcs if b == j] for j in to_nodes}
    visit = {(v, i): quicksum(x[v, i, j] for j in out_arcs[i]) for v in V for i in S}

    # route structure: leave and return to the depot once; continuity; per-vehicle visit at most once
    for v in V:
        m.addCons(quicksum(x[v, START, j] for j in out_arcs[START]) == 1)
        m.addCons(quicksum(x[v, i, END] for i in in_arcs[END]) == 1)
        for i in S:
            m.addCons(quicksum(x[v, h, i] for h in in_arcs[i]) == visit[v, i])
            m.addCons(visit[v, i] <= 1)
    if args.no_split_service:
        for i in S:
            m.addCons(quicksum(visit[v, i] for v in V) <= 1)

    # signed service: >0 pickup (load up, station down), <0 dropoff; only where visited.
    # Per-stop bounds are the tightest exact M: pickups <= min(C, initial bikes), dropoffs
    # <= min(C, free docks). --dominance (opt-in heuristic) restricts service to the target's
    # direction and at most the reachable target t_clip = clamp(target, initial - capacity,
    # initial). It is faster but NOT exact: an overshoot is penalty-neutral and can shorten
    # routes (start-load zero reference: exact 8.8201 vs restricted 8.8278).
    lo, hi = {}, {}
    for i in S:
        if not args.dominance:
            lo[i], hi[i] = -min(C, max(0, cap[i] - init[i])), min(C, max(0, init[i]))
        else:
            tc = max(init[i] - cap[i], min(target[i], init[i]))
            lo[i], hi[i] = (max(-C, tc), 0) if tc < 0 else (0, min(C, tc))
    s = {(v, i): m.addVar(vtype="I", lb=lo[i], ub=hi[i], name=f"s_{v}_{i}") for v in V for i in S}
    # Vehicle load carried on each arc (arc-flow form; much tighter LP than big-M load
    # propagation). Load leaving a stop = load arriving + signed service, within [0, C].
    q = {(v, i, j): m.addVar(vtype="C", lb=0, ub=C, name=f"q_{v}_{i}_{j}") for v in V for i, j in arcs}
    for v in V:
        for i, j in arcs:
            m.addCons(q[v, i, j] <= C * x[v, i, j])
        for i in S:
            m.addCons(s[v, i] <= hi[i] * visit[v, i])
            m.addCons(s[v, i] >= lo[i] * visit[v, i])
            m.addCons(quicksum(q[v, h, i] for h in in_arcs[i]) + s[v, i]
                      == quicksum(q[v, i, j] for j in out_arcs[i]))
        if args.start_load == "zero":
            m.addCons(quicksum(q[v, START, j] for j in out_arcs[START]) == 0)

    # identical vehicles: order them by travel distance to cut symmetric branches
    vdist = {v: quicksum(dist[i, j] * x[v, i, j] for i, j in arcs) for v in V}
    for v in list(V)[:-1]:
        m.addCons(vdist[v] >= vdist[v + 1])

    # station final inventory within [0, capacity]; absolute deviation from target
    dev = {i: m.addVar(vtype="C", lb=0, name=f"dev_{i}") for i in S}
    for i in S:
        net = quicksum(s[v, i] for v in V)
        m.addCons(net <= init[i])
        m.addCons(net >= init[i] - cap[i])
        if args.dominance:
            tc = max(init[i] - cap[i], min(target[i], init[i]))
            m.addCons(net <= max(0, tc))
            m.addCons(net >= min(0, tc))
        m.addCons(net - target[i] <= dev[i])
        m.addCons(target[i] - net <= dev[i])

    # subtour elimination (physical load is NOT a connectivity proof)
    station_arcs = [(i, j) for i in S for j in S if i != j]
    if args.subtour == "mtz":
        order = {(v, i): m.addVar(vtype="C", lb=1, ub=max(1, n), name=f"order_{v}_{i}") for v in V for i in S}
        for v in V:
            for i, j in station_arcs:
                m.addCons(order[v, i] - order[v, j] + n * x[v, i, j] <= n - 1)
    elif args.subtour == "flow":
        flow_arcs = [(i, j) for i in [START, *S] for j in S if i != j]
        f = {(v, i, j): m.addVar(vtype="C", lb=0, ub=n, name=f"f_{v}_{i}_{j}") for v in V for i, j in flow_arcs}
        for v in V:
            m.addCons(quicksum(f[v, START, j] for j in S) == quicksum(visit[v, i] for i in S))
            for i, j in flow_arcs:
                m.addCons(f[v, i, j] <= n * x[v, i, j])
            for i in S:
                m.addCons(quicksum(f[v, h, i] for h in [START, *S] if h != i)
                          - quicksum(f[v, i, j] for j in S if j != i) == visit[v, i])
    else:  # "cut": DFJ/GSEC cuts added lazily inside branch-and-cut by a constraint handler
        hdlr = SubtourCuts(x, V, S, arcs, out_arcs)
        m.includeConshdlr(hdlr, "subtour", "lazy DFJ subtour cuts", sepapriority=1000000,
                          enfopriority=-1000000, chckpriority=-1000000, sepafreq=1, needscons=True)
        m.addPyCons(m.createCons(hdlr, "subtour"))

    travel = quicksum(dist[i, j] * x[v, i, j] for v in V for i, j in arcs)
    penalty = pw * quicksum(dev[i] for i in S)
    m.setObjective(travel + penalty, "minimize")
    m.setParam("limits/time", float(args.time_limit))
    m.setParam("limits/gap", float(args.gap))

    t0 = time.time()
    m.optimize()
    if m.getNSols() == 0:
        status = m.getStatus()
        m.freeProb()
        fail(f"SCIP found no feasible solution; status={status}. If status is timelimit, rerun with a "
             "larger --time-limit; if infeasible, check the decision flags (e.g. --no-split-service "
             "with more vehicles than stations).")

    status = str(m.getStatus())
    gap = float(m.getGap())
    vehicles = []
    for v in V:
        succ = {i: j for (i, j) in arcs if m.getVal(x[v, i, j]) > 0.5}
        route = extract_route(succ)
        start_load = int(round(sum(m.getVal(q[v, START, j]) for j in out_arcs[START])))
        cur = start_load
        stops = []
        for node in route[1:-1]:
            sv = int(round(m.getVal(s[v, node])))
            cur += sv
            stops.append({"station_id": ids[node], "bikes_picked_up": float(max(sv, 0)),
                          "bikes_dropped_off": float(max(-sv, 0)), "load_after_stop": float(cur)})
        vehicles.append({"vehicle_id": v + 1, "start_load": float(start_load),
                         "route": [START, *[ids[i] for i in route[1:-1]], END],
                         "stops": stops, "end_load": float(cur),
                         "_internal_route": route})
    info = {"status": status, "gap": gap, "solve_seconds": round(time.time() - t0, 2),
            "solver_objective": float(m.getObjVal())}
    m.freeProb()  # free while the constraint handler can still reach the model (avoids teardown errors)
    return finalize(data, vehicles, dist, args), info


class SubtourCuts(Conshdlr):
    """Generalized subtour elimination: for station set Q and k in Q, arcs entering Q >= visit_k.
    Integral solutions: cut every station-only cycle. LP solutions (separation): max-flow from
    the depot to each visited station on the fractional support; a cut below visit_k is violated."""

    def __init__(self, x, V, S, arcs, out_arcs):
        self.x, self.V, self.S, self.arcs, self.out_arcs = x, V, S, arcs, out_arcs
        self.seen = set()

    def _vals(self, sol, v):
        return {(i, j): self.model.getSolVal(sol, self.x[v, i, j]) for i, j in self.arcs}

    def _integral_cuts(self, sol):
        cuts = []
        for v in self.V:
            xv = self._vals(sol, v)
            succ = {i: j for (i, j), val in xv.items() if val > 0.5}
            for cyc in station_cycles(succ, self.S):
                cuts.append((v, frozenset(cyc), cyc[0]))
        return cuts

    def _fractional_cuts(self, sol):
        cuts = []
        for v in self.V:
            xv = self._vals(sol, v)
            visit = {k: sum(xv[k, j] for j in self.out_arcs[k]) for k in self.S}
            for k in self.S:
                if visit[k] < 0.1:
                    continue
                value, sink_side = max_flow_min_cut(xv, START, k)
                if value < visit[k] - 1e-4:
                    Q = frozenset(i for i in sink_side if i not in (START, END))
                    cuts.append((v, Q, k))
        return cuts

    def _add(self, cuts):
        added = 0
        for v, Q, k in cuts:
            if (v, Q, k) in self.seen:
                continue
            self.seen.add((v, Q, k))
            entering = quicksum(self.x[v, i, j] for i, j in self.arcs if i not in Q and j in Q)
            visit_k = quicksum(self.x[v, k, j] for j in self.out_arcs[k])
            self.model.addCons(entering - visit_k >= 0, removable=True)
            added += 1
        return added

    def conscheck(self, constraints, solution, checkintegrality, checklprows, printreason, completely):
        return {"result": SCIP_RESULT.INFEASIBLE if self._integral_cuts(solution) else SCIP_RESULT.FEASIBLE}

    def consenfolp(self, constraints, nusefulconss, solinfeasible):
        cuts = self._integral_cuts(None)
        if not cuts:
            return {"result": SCIP_RESULT.FEASIBLE}
        return {"result": SCIP_RESULT.CONSADDED if self._add(cuts) else SCIP_RESULT.INFEASIBLE}

    def consenfops(self, constraints, nusefulconss, solinfeasible, objinfeasible):
        return {"result": SCIP_RESULT.INFEASIBLE if self._integral_cuts(None) else SCIP_RESULT.FEASIBLE}

    def conssepalp(self, constraints, nusefulconss):
        added = self._add(self._fractional_cuts(None))
        return {"result": SCIP_RESULT.CONSADDED if added else SCIP_RESULT.DIDNOTFIND}

    def conslock(self, constraint, locktype, nlockspos, nlocksneg):
        for var in self.x.values():
            self.model.addVarLocksType(var, locktype, nlockspos + nlocksneg, nlockspos + nlocksneg)


def max_flow_min_cut(cap, source, sink):
    """Edmonds-Karp on arc capacities {(i, j): c}; returns (flow value, nodes on the sink side)."""
    resid, adj = {}, {}
    for (i, j), c in cap.items():
        if c <= 1e-9:
            continue
        resid[i, j] = resid.get((i, j), 0.0) + c
        resid.setdefault((j, i), 0.0)
        adj.setdefault(i, set()).add(j)
        adj.setdefault(j, set()).add(i)
    total = 0.0
    while True:
        parent, frontier = {source: None}, [source]
        while frontier and sink not in parent:
            nxt = []
            for u in frontier:
                for w in adj.get(u, ()):
                    if w not in parent and resid[u, w] > 1e-9:
                        parent[w] = u
                        nxt.append(w)
            frontier = nxt
        if sink not in parent:
            nodes = set(adj) | {sink}
            return total, nodes - set(parent)
        path, w = [], sink
        while parent[w] is not None:
            path.append((parent[w], w))
            w = parent[w]
        push = min(resid[e] for e in path)
        for u, w in path:
            resid[u, w] -= push
            resid[w, u] += push
        total += push


def station_cycles(succ, S):
    cycles, seen = [], set()
    for start in S:
        if start in seen or start not in succ:
            continue
        path, pos, cur = [], {}, start
        while cur in succ and cur not in pos and cur not in seen:
            pos[cur] = len(path)
            path.append(cur)
            cur = succ[cur]
        seen.update(path)
        if cur in pos:
            cyc = path[pos[cur]:]
            if len(cyc) >= 2 and START not in cyc and END not in cyc:
                cycles.append(cyc)
    return cycles


def extract_route(succ):
    route, cur, seen = [START], START, {START}
    while cur != END:
        if cur not in succ:
            fail(f"route disconnected at {cur!r}")
        cur = succ[cur]
        if cur in seen:
            fail(f"cycle detected at {cur!r}")
        route.append(cur)
        seen.add(cur)
    if len(seen) - 2 != sum(1 for k in succ if k != START):
        fail("selected arcs contain a subtour disconnected from the depot")
    return route


def finalize(data, vehicles, dist, args):
    st = data["stations"]
    pw = float(data["penalty_weight"])
    ids = [int(s["id"]) for s in st]
    travel = 0.0
    picked = {sid: 0.0 for sid in ids}
    dropped = {sid: 0.0 for sid in ids}
    for veh in vehicles:
        r = veh.pop("_internal_route")
        travel += sum(dist[a, b] for a, b in zip(r, r[1:]))
        for stop in veh["stops"]:
            picked[stop["station_id"]] += stop["bikes_picked_up"]
            dropped[stop["station_id"]] += stop["bikes_dropped_off"]
    stations = []
    total_unmet = 0.0
    for s_ in st:
        sid = int(s_["id"])
        net = picked[sid] - dropped[sid]
        tgt = float(s_["net_rebalancing_target"])
        unmet = abs(tgt - net)
        total_unmet += unmet
        stations.append({"station_id": sid, "net_rebalancing_target": tgt,
                         "total_bikes_picked_up": picked[sid], "total_bikes_dropped_off": dropped[sid],
                         "net_bike_change": net, "unmet_rebalancing_amount": unmet})
    pen = pw * total_unmet
    return {"summary": {"objective": travel + pen, "travel_distance_miles": travel,
                        "unmet_rebalancing_penalty": pen, "total_unmet_rebalancing_amount": total_unmet},
            "vehicles": vehicles, "stations": stations}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="/root/data.json")
    ap.add_argument("--out", default="/root/report.json")
    ap.add_argument("--start-load", choices=["free", "zero"], default="free")
    ap.add_argument("--allow-idle-vehicles", action="store_true")
    ap.add_argument("--no-split-service", action="store_true")
    ap.add_argument("--subtour", choices=["cut", "mtz", "flow"], default="cut")
    ap.add_argument("--dominance", action="store_true",
                    help="restrict service to the target direction/size: faster, may lose optimality")
    ap.add_argument("--radius", type=float, default=3960.0)
    ap.add_argument("--time-limit", type=float, default=300.0)
    ap.add_argument("--gap", type=float, default=0.0)
    args = ap.parse_args()

    data = load_data(args.data)
    report, info = build_and_solve(data, args)
    Path(args.out).write_text(json.dumps(report, indent=2))
    optimal = info["status"] == "optimal"
    print(json.dumps({"report": str(args.out), **info, "optimal": optimal,
                      "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    main()
