"""Build and solve the multi-vehicle bike-rebalancing routing MIP with PySCIPOpt.

stdin: {"currentState": {...}}; stdout: one JSON object merged into the state.
Writes the canonical solution JSON to state["solution_path"].

Model (internal indices; original station IDs only in the report):
  x[v,i,j]   binary arc, START -> stations -> END (START->END only when vehicles are optional)
  p/d[v,i]   integer pickup / dropoff by vehicle v at station i (only if v visits i)
  load[v,i]  integer truck load after servicing i, in [0, Q_v]; propagated along used arcs (big-M)
  order[v,i] MTZ order (default) or artificial connectivity flow -- truck load is NOT used for SEC
  dev[i]     |net pickup - target| (or shortfall only), penalised with penalty_weight
  min  sum dist*x  +  penalty_weight * sum dev     (distances unrounded)
"""
import json
import time

from rebalance_common import START, END, read_stdin, emit, fail, abs_path, load_instance, distance_matrix

try:
    from pyscipopt import Model, quicksum
except ImportError as exc:  # the task container ships pyscipopt; do not install another solver
    fail(f"PySCIPOpt is required: {exc}")


def set_if_available(model, name, value):
    try:
        model.setParam(name, value)
    except Exception:
        pass


def as_bool(v, default):
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return bool(v)


def max_flow_min_cut(cap, src, sink, nodes):
    """Edmonds-Karp on a small dense graph. Returns (flow value, source side of a min cut)."""
    res = {(i, j): cap.get((i, j), 0.0) for i in nodes for j in nodes if i != j}
    flow = 0.0
    while True:
        parent, queue = {src: None}, [src]
        while queue and sink not in parent:
            u = queue.pop(0)
            for w in nodes:
                if w not in parent and w != u and res[u, w] > 1e-9:
                    parent[w] = u
                    queue.append(w)
        if sink not in parent:
            return flow, set(parent)
        path, w = [], sink
        while parent[w] is not None:
            path.append((parent[w], w))
            w = parent[w]
        aug = min(res[e] for e in path)
        for (u, w) in path:
            res[u, w] -= aug
            res[w, u] += aug
        flow += aug


def separate_gsec(xval, V, N, arcs, known):
    """For each vehicle and visited station k: if the LP sends < visit_k units of connectivity from
    START to k, the min cut S (k in S, START not) gives sum_{i not in S, j in S} x_ij >= visit_k."""
    seen = {(v, frozenset(S_set), k) for (v, S_set, k) in known}
    new = []
    nodes = [START, *N]
    for v in V:
        cap = {(i, j): xval[v, i, j] for (i, j) in arcs if j != END and xval[v, i, j] > 1e-9}
        vis = {k: sum(xval[v, i, j] for (i, j) in arcs if i == k) for k in N}
        for k in N:
            if vis[k] < 1e-3:
                continue
            f, src_side = max_flow_min_cut(cap, START, k, nodes)
            if f < vis[k] - 1e-3:
                S_set = frozenset(nodes) - frozenset(src_side)
                key = (v, S_set, k)
                if key not in seen:
                    seen.add(key)
                    new.append((v, S_set, k))
    return new


def main():
    st = read_stdin()
    data_path = abs_path(st.get("data_path"), "data_path")
    solution_path = abs_path(st.get("solution_path"), "solution_path")
    inst = load_instance(data_path, st.get("earth_radius"), st.get("target_sign"))

    must_use = as_bool(st.get("vehicles_must_be_used"), True)
    split_ok = as_bool(st.get("split_service_allowed"), True)
    end_empty = as_bool(st.get("end_empty_required"), False)
    penalty_form = str(st.get("penalty_form") or "absolute_deviation")
    if penalty_form not in ("absolute_deviation", "shortfall_only"):
        fail(f"penalty_form {penalty_form!r} not supported; use absolute_deviation or shortfall_only")
    L0 = int(st.get("initial_vehicle_load") or 0)
    time_limit = float(st.get("time_limit_seconds") or 600.0)
    method = str(st.get("subtour_method") or "mtz")
    if method not in ("mtz", "flow"):
        method = "mtz"
    load_model = str(st.get("load_model") or "arc_flow")

    S = inst["stations"]
    n = len(S)
    V = range(inst["K"])
    N = range(n)
    caps = inst["caps"]
    if any(L0 > q for q in caps):
        fail(f"initial_vehicle_load {L0} exceeds a vehicle capacity {caps}")
    dist = distance_matrix(inst)

    frm = [START, *N]
    to = [*N, END]
    arcs = [(i, j) for i in frm for j in to if i != j and (must_use is False or (i, j) != (START, END))]
    if not must_use and (START, END) not in arcs:
        arcs.append((START, END))

    free = [s["capacity"] - s["initial_bikes"] for s in S]
    init = [s["initial_bikes"] for s in S]
    out_arcs = {i: [(a, b) for (a, b) in arcs if a == i] for i in frm}
    in_arcs = {j: [(a, b) for (a, b) in arcs if b == j] for j in to}

    def build(cuts, relax=False):
        BIN, INT = ("C", "C") if relax else ("B", "I")
        m = Model("bike_rebalancing")
        m.hideOutput()
        for name in ("randomization/randomseedshift", "randomization/permutationseed", "randomization/lpseed"):
            set_if_available(m, name, 0)
        for name in ("randomization/permutevars", "randomization/permuteconss"):
            set_if_available(m, name, False)
        set_if_available(m, "parallel/maxnthreads", 1)
        m.setParam("limits/time", time_limit)
        m.setParam("limits/gap", float(st.get("mip_gap") or 0.0))

        x = {(v, i, j): m.addVar(vtype=BIN, name=f"x_{v}_{i}_{j}") for v in V for (i, j) in arcs}
        visit = {(v, i): quicksum(x[v, a, b] for (a, b) in out_arcs[i]) for v in V for i in N}

        p = {(v, i): m.addVar(vtype=INT, lb=0, ub=min(caps[v], init[i]), name=f"pick_{v}_{i}") for v in V for i in N}
        d = {(v, i): m.addVar(vtype=INT, lb=0, ub=min(caps[v], free[i]), name=f"drop_{v}_{i}") for v in V for i in N}
        load = {(v, i): m.addVar(vtype=INT, lb=0, ub=caps[v], name=f"load_{v}_{i}") for v in V for i in N}
        load_end = {v: m.addVar(vtype=INT, lb=0, ub=caps[v], name=f"load_end_{v}") for v in V}

        use, y = {}, {}
        for v in V:
            if must_use:
                use[v] = 1
            else:
                use[v] = m.addVar(vtype=BIN, name=f"use_{v}")
            m.addCons(quicksum(x[v, a, b] for (a, b) in out_arcs[START]) == use[v])
            m.addCons(quicksum(x[v, a, b] for (a, b) in in_arcs[END]) == use[v])
            for i in N:
                m.addCons(quicksum(x[v, a, b] for (a, b) in in_arcs[i]) == visit[v, i])  # continuity
                m.addCons(visit[v, i] <= 1)  # per-vehicle: at most once
                m.addCons(p[v, i] <= min(caps[v], init[i]) * visit[v, i])  # service only if visited
                m.addCons(d[v, i] <= min(caps[v], free[i]) * visit[v, i])
                for j in N:
                    if i < j:
                        m.addCons(x[v, i, j] + x[v, j, i] <= 1)
            if load_model == "bigm":
                # load after each station propagated along used arcs; START load is the fixed initial load
                M = 2 * caps[v]
                for (i, j) in arcs:
                    li = L0 if i == START else load[v, i]
                    lj = load_end[v] if j == END else load[v, j]
                    ch = 0 if j == END else p[v, j] - d[v, j]
                    m.addCons(lj - li - ch <= M * (1 - x[v, i, j]))
                    m.addCons(lj - li - ch >= -M * (1 - x[v, i, j]))
            else:
                # arc-flow load (much tighter LP than big-M): y = bikes on board along arc (i, j)
                for (i, j) in arcs:
                    y[v, i, j] = m.addVar(lb=0, ub=caps[v], name=f"y_{v}_{i}_{j}")
                    m.addCons(y[v, i, j] <= caps[v] * x[v, i, j])
                    if i == START:
                        m.addCons(y[v, i, j] == L0 * x[v, i, j])
                for i in N:
                    inflow = quicksum(y[v, a, b] for (a, b) in in_arcs[i])
                    outflow = quicksum(y[v, a, b] for (a, b) in out_arcs[i])
                    m.addCons(outflow - inflow == p[v, i] - d[v, i])
                    m.addCons(load[v, i] == outflow)
                m.addCons(load_end[v] == quicksum(y[v, a, b] for (a, b) in in_arcs[END]))
            if end_empty:
                m.addCons(load_end[v] == 0)

        if not split_ok:
            for i in N:
                m.addCons(quicksum(visit[v, i] for v in V) <= 1)

        # station inventory: order-independent bounds (all pickups before drops and vice versa stay feasible)
        for i in N:
            m.addCons(quicksum(p[v, i] for v in V) <= init[i])
            m.addCons(quicksum(d[v, i] for v in V) <= free[i])

        # subtour elimination (degree/continuity alone allow station-only cycles)
        if method == "flow":
            fa = [(i, j) for (i, j) in arcs if j != END]
            f = {(v, i, j): m.addVar(lb=0, ub=n, name=f"f_{v}_{i}_{j}") for v in V for (i, j) in fa}
            for v in V:
                m.addCons(quicksum(f[v, START, j] for j in N if (START, j) in arcs) == quicksum(visit[v, i] for i in N))
                for (i, j) in fa:
                    m.addCons(f[v, i, j] <= n * x[v, i, j])
                for i in N:
                    m.addCons(quicksum(f[v, a, i] for a in frm if (a, i) in arcs)
                              - quicksum(f[v, i, b] for b in N if (i, b) in arcs) == visit[v, i])
        else:
            order = {(v, i): m.addVar(lb=1, ub=max(1, n), name=f"order_{v}_{i}") for v in V for i in N}
            for v in V:
                for i in N:
                    for j in N:
                        if i != j:
                            # lifted MTZ (Desrochers-Laporte)
                            m.addCons(order[v, i] - order[v, j] + n * x[v, i, j]
                                      + (n - 2) * x[v, j, i] <= n - 1)

        # symmetry breaking for identical consecutive vehicles: first-station index non-decreasing
        for v in list(V)[:-1]:
            if caps[v] == caps[v + 1]:
                m.addCons(quicksum((j + 1) * x[v, START, j] for j in N)
                          <= quicksum((j + 1) * x[v + 1, START, j] for j in N))

        dev = {i: m.addVar(lb=0, name=f"dev_{i}") for i in N}
        for i in N:
            net = quicksum(p[v, i] - d[v, i] for v in V)
            t = S[i]["target"]
            if penalty_form == "absolute_deviation":
                m.addCons(net - t <= dev[i])
                m.addCons(t - net <= dev[i])
            elif t > 0:
                m.addCons(t - net <= dev[i])
            elif t < 0:
                m.addCons(net - t <= dev[i])
            if t != 0:
                # valid cut, big LP-bound gain: an unvisited station pays its full |target|
                m.addCons(dev[i] >= abs(t) * (1 - quicksum(visit[v, i] for v in V)))

        travel = quicksum(dist[i, j] * x[v, i, j] for v in V for (i, j) in arcs)
        penalty = inst["penalty"] * quicksum(dev[i] for i in N)

        # generalized subtour cuts found on the LP relaxation (see separate_gsec)
        for (v, S_set, k) in cuts:
            for w in V:
                if w == v or caps[w] == caps[v]:  # identical vehicles share the cut
                    m.addCons(quicksum(x[w, a, b] for (a, b) in arcs if a not in S_set and b in S_set)
                              >= visit[w, k])
        m.setObjective(travel + penalty, "minimize")
        return m, x, p, d, visit

    # root cutting-plane loop: separate GSECs on the LP relaxation, then solve the MIP with them
    t_start = time.time()
    cuts, rounds = [], 0
    sep_budget = float(st.get("cut_loop_seconds") or min(60.0, 0.2 * time_limit))
    while rounds < 50 and time.time() - t_start < sep_budget:
        lp, lx, _, _, _ = build(cuts, relax=True)
        lp.setParam("limits/time", max(1.0, sep_budget))
        lp.optimize()
        if lp.getStatus() != "optimal":
            break
        new = separate_gsec({k: lp.getVal(var) for k, var in lx.items()}, V, N, arcs, cuts)
        rounds += 1
        if not new:
            break
        cuts.extend(new)
    root_lp_bound = lp.getObjVal() if rounds and lp.getStatus() == "optimal" else None

    m, x, p, d, visit = build(cuts)
    m.setParam("limits/time", max(1.0, time_limit - (time.time() - t_start)))

    t0 = time.time()
    m.optimize()
    elapsed = time.time() - t0
    status = str(m.getStatus()).lower()
    if m.getNSols() == 0:
        fail(f"SCIP found no feasible solution; status={status}")

    def val(e):
        return m.getVal(e) if not isinstance(e, (int, float)) else e

    ids = inst["ids"]
    vehicles, total_dist = [], 0.0
    net_pick = [0] * n
    for v in V:
        sel = [(i, j) for (i, j) in arcs if val(x[v, i, j]) > 0.5]
        succ = {}
        for i, j in sel:
            if i in succ:
                fail(f"vehicle {v}: two outgoing arcs from {i!r}")
            succ[i] = j
        route, cur, seen = [START], START, {START}
        while cur != END and sel:
            if cur not in succ:
                fail(f"vehicle {v}: route disconnected at {cur!r}")
            cur = succ[cur]
            if cur in seen:
                fail(f"vehicle {v}: cycle at {cur!r}")
            route.append(cur)
            seen.add(cur)
        if sel and len(seen) - 1 != len(sel):
            fail(f"vehicle {v}: {len(sel) - len(seen) + 1} arcs off the depot path (subtour)")
        if not sel:
            route = [START, END]
        vdist = sum(dist[a, b] for a, b in zip(route, route[1:]))
        total_dist += vdist
        stops, ld = [], L0
        for node in route[1:-1]:
            pk, dr = round(val(p[v, node])), round(val(d[v, node]))
            nt = pk - dr  # net out any simultaneous pick+drop
            ld += nt
            net_pick[node] += nt
            stops.append({"station_id": ids[node], "pickup": max(nt, 0), "dropoff": max(-nt, 0),
                          "net_pickup": nt, "load_after": ld})
        vehicles.append({
            "vehicle_id": v + 1,
            "route": [r if isinstance(r, str) else ids[r] for r in route],
            "stops": stops, "distance": vdist,
            "start_load": L0, "end_load": ld,
            "total_pickup": sum(s["pickup"] for s in stops),
            "total_dropoff": sum(s["dropoff"] for s in stops),
        })

    stations, total_dev = [], 0
    sign = inst["sign"]
    for i, s in enumerate(S):
        t = s["target"]
        dv = abs(net_pick[i] - t) if penalty_form == "absolute_deviation" else (
            max(t - net_pick[i], 0) if t > 0 else max(net_pick[i] - t, 0) if t < 0 else 0)
        total_dev += dv
        stations.append({
            "station_id": s["id"], "target": s["raw_target"],
            "achieved": sign * net_pick[i],  # same sign convention as the data's target
            "net_pickup": net_pick[i], "deviation": dv,
            "initial_bikes": s["initial_bikes"], "final_bikes": s["initial_bikes"] - net_pick[i],
            "station_capacity": s["capacity"],
        })
    pen = inst["penalty"] * total_dev
    sol = {
        "objective": total_dist + pen,
        "travel_distance": total_dist,
        "penalty_cost": pen,
        "total_deviation": total_dev,
        "penalty_weight": inst["penalty"],
        "distance_metric": inst["metric"],
        "earth_radius": inst["radius"],
        "vehicles": vehicles,
        "stations": stations,
        "solver": {"name": "SCIP", "status": status, "gap": m.getGap(),
                   "solver_objective": m.getObjVal(), "dual_bound": m.getDualbound(),
                   "time_seconds": elapsed, "subtour_method": method,
                   "load_model": load_model, "gsec_cuts": len(cuts), "cut_rounds": rounds,
                   "root_lp_bound_with_cuts": root_lp_bound},
        "assumptions": {"vehicles_must_be_used": must_use, "split_service_allowed": split_ok,
                        "end_empty_required": end_empty, "initial_vehicle_load": L0,
                        "penalty_form": penalty_form,
                        "target_sign": "positive=pickup" if sign == 1 else "positive=dropoff"},
    }
    if abs(sol["objective"] - m.getObjVal()) > 1e-5 * max(1.0, abs(sol["objective"])):
        fail(f"reconstructed objective {sol['objective']} != SCIP objective {m.getObjVal()}")
    with open(solution_path, "w") as fh:
        json.dump(sol, fh, indent=2)
    emit({
        "solution_path": solution_path,
        "objective": sol["objective"], "travel_distance": total_dist, "penalty_cost": pen,
        "total_deviation": total_dev, "solver_status": status, "solver_gap": m.getGap(),
        "solve_seconds": round(elapsed, 2),
        "routes": [veh["route"] for veh in vehicles],
    })


if __name__ == "__main__":
    main()
