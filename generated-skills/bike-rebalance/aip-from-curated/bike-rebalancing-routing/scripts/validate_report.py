"""Independently validate the deliverable report against the raw data (no solver involved).

Re-parses routes and per-stop pickups/dropoffs from state["output_path"], maps station IDs back to
indices, recomputes great-circle distance from coordinates, truck loads, station inventory,
target deviation, penalty, and objective, and compares them with the values the report states and
with the solver's canonical solution (state["solution_path"]). With state["custom_objective"] true
(set by adapt-model) penalty/objective comparisons are skipped; routes, loads, inventory, and
distance are still checked.

stdout: {"verdict": "pass"|"fail"|"unparsed", "issues": [...], "recomputed": {...}}
"""
import json

from rebalance_common import START, END, read_stdin, emit, abs_path, load_instance, distance_matrix

ROUTE_KEYS = ("route", "path", "sequence", "route_nodes", "nodes", "tour")
STOP_KEYS = ("stops", "visits", "actions", "services", "operations", "station_visits")
SID_KEYS = ("station_id", "station", "id", "node", "station_name")
PICK_KEYS = ("pickup", "picked_up", "pick_up", "pickups", "bikes_picked_up", "collected")
DROP_KEYS = ("dropoff", "dropped_off", "drop_off", "dropoffs", "bikes_dropped_off", "delivered")
SIGNED_KEYS = ("net_pickup", "service", "quantity", "load_change", "change", "net_change", "bikes_moved")
DIST_KEYS = ("travel_distance", "total_distance", "total_travel_distance", "distance_total",
             "total_distance_miles", "travel_distance_miles", "distance")
PEN_KEYS = ("penalty_cost", "total_penalty", "penalty", "imbalance_penalty", "deviation_penalty")
OBJ_KEYS = ("objective", "objective_value", "total_cost", "total_objective", "cost")


def close(a, b, tol=1e-4):
    return abs(a - b) <= max(tol, tol * max(1.0, abs(b)))


def first(d, keys):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return k, d[k]
    return None, None


def find_vehicle_list(obj, depth=0):
    """Locate the per-vehicle records: a list (or id-keyed dict) of dicts carrying a route or stops."""
    if depth > 4:
        return None
    if isinstance(obj, list) and obj and all(isinstance(e, dict) for e in obj):
        if any(first(e, ROUTE_KEYS)[0] or first(e, STOP_KEYS)[0] for e in obj):
            return obj
    if isinstance(obj, dict):
        for k in ("vehicles", "routes", "vehicle_routes", "trucks", "solution", "plan"):
            if k in obj:
                got = find_vehicle_list(obj[k], depth + 1)
                if got:
                    return got
        vals = list(obj.values())
        if vals and all(isinstance(v, dict) for v in vals) and any(
                first(v, ROUTE_KEYS)[0] or first(v, STOP_KEYS)[0] for v in vals):
            return vals
        if vals and all(isinstance(v, list) for v in vals) and any(vals):
            return [{"route": v} for v in vals]
        for v in obj.values():
            if isinstance(v, (dict, list)):
                got = find_vehicle_list(v, depth + 1)
                if got:
                    return got
    if isinstance(obj, list) and obj and all(isinstance(e, list) for e in obj):
        return [{"route": e} for e in obj]
    return None


def to_number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stop_qty(rec):
    k, v = first(rec, PICK_KEYS)
    pk = to_number(v) if k else None
    k2, v2 = first(rec, DROP_KEYS)
    dr = to_number(v2) if k2 else None
    if pk is not None or dr is not None:
        return (pk or 0.0) - (dr or 0.0)
    k3, v3 = first(rec, SIGNED_KEYS)
    if k3:
        q = to_number(v3)
        return q
    return None


def main():
    st = read_stdin()
    issues = []
    inst = load_instance(abs_path(st.get("data_path"), "data_path"), st.get("earth_radius"), st.get("target_sign"))
    out_path = abs_path(st.get("output_path"), "output_path")
    try:
        with open(out_path) as fh:
            rep = json.load(fh)
    except Exception as exc:
        emit({"verdict": "fail", "issues": [f"cannot read deliverable {out_path}: {exc}"], "recomputed": {}})
        return

    must_use = st.get("vehicles_must_be_used", True)
    split_ok = st.get("split_service_allowed", True)
    end_empty = st.get("end_empty_required", False)
    penalty_form = st.get("penalty_form") or "absolute_deviation"
    L0 = int(st.get("initial_vehicle_load") or 0)

    S, ids, id_to_idx = inst["stations"], inst["ids"], inst["id_to_idx"]
    n = len(S)
    dist = distance_matrix(inst)
    vehs = find_vehicle_list(rep)
    if not vehs:
        emit({"verdict": "unparsed", "issues": ["no per-vehicle route/stop records found in deliverable"],
              "recomputed": {}})
        return

    def to_idx(node):
        if isinstance(node, dict):
            _, node = first(node, SID_KEYS)
        if isinstance(node, str) and ("depot" in node.lower()):
            return "depot"
        key = str(node)
        if key not in id_to_idx:
            f = to_number(node)
            key = str(int(f)) if f is not None and f == int(f) else key
        if key not in id_to_idx:
            raise KeyError(node)
        return id_to_idx[key]

    if len(vehs) > inst["K"]:
        issues.append(f"{len(vehs)} vehicle routes but only {inst['K']} vehicles")
    total_dist, net = 0.0, [0.0] * n
    visits = [0] * n
    per_vehicle = []
    for vi, rec in enumerate(vehs):
        rk, route = first(rec, ROUTE_KEYS)
        sk, stops = first(rec, STOP_KEYS)
        qty_by_idx, order_from_stops = {}, []
        try:
            for s in (stops or []):
                if not isinstance(s, dict):
                    continue
                idx = to_idx(s)
                if idx == "depot":
                    continue
                q = stop_qty(s)
                order_from_stops.append(idx)
                if q is not None:
                    qty_by_idx[idx] = qty_by_idx.get(idx, 0.0) + q
            # vehicle-level quantity maps: {"pickups": {"<id>": n}, "dropoffs": {...}} or lists of records
            vehicle_maps = False
            for keys, sgn in ((PICK_KEYS, 1.0), (DROP_KEYS, -1.0)):
                for k in keys:
                    val = rec.get(k)
                    items = []
                    if isinstance(val, dict):
                        items = list(val.items())
                    elif isinstance(val, list) and val and all(isinstance(e, dict) for e in val):
                        for e in val:
                            _, sid = first(e, SID_KEYS)
                            qk, qv = first(e, ("quantity", "qty", "bikes", "amount", "count", *keys))
                            items.append((sid, qv))
                    for sid, q in items:
                        if to_number(q) is None:
                            continue
                        idx = to_idx(sid)
                        if idx != "depot":
                            vehicle_maps = True
                            qty_by_idx[idx] = qty_by_idx.get(idx, 0.0) + sgn * float(q)
            seq = []
            for node in (route or []):
                idx = to_idx(node)
                seq.append(idx)
                if isinstance(node, dict) and idx != "depot" and stop_qty(node) is not None and not stops:
                    qty_by_idx[idx] = qty_by_idx.get(idx, 0.0) + stop_qty(node)
        except KeyError as exc:
            issues.append(f"vehicle {vi + 1}: unknown station id {exc.args[0]!r}")
            continue
        if not seq:
            seq = ["depot", *order_from_stops, "depot"]
        if seq[0] != "depot" or seq[-1] != "depot":
            issues.append(f"vehicle {vi + 1}: route must start and end at the depot (got {seq[0]!r} .. {seq[-1]!r})")
            seq = [x for x in seq if x != "depot"]
            seq = ["depot", *seq, "depot"]
        mid = seq[1:-1]
        if "depot" in mid:
            issues.append(f"vehicle {vi + 1}: depot appears mid-route")
            mid = [x for x in mid if x != "depot"]
        if len(set(mid)) != len(mid):
            issues.append(f"vehicle {vi + 1}: repeats a station within one route")
        if must_use and not mid:
            issues.append(f"vehicle {vi + 1}: visits no station but every vehicle must be used")
        if stops and order_from_stops and order_from_stops != mid:
            issues.append(f"vehicle {vi + 1}: stop list order/length differs from route sequence")
        nodes = [START, *mid, END]
        vd = sum(dist[a, b] for a, b in zip(nodes, nodes[1:])) if mid else 0.0
        total_dist += vd
        missing = [ids[i] for i in mid if i not in qty_by_idx]
        if missing and (stops or any(isinstance(x, dict) for x in (route or []))) and not vehicle_maps:
            issues.append(f"vehicle {vi + 1}: no pickup/dropoff quantity for stations {missing}")
        if mid and not stops and not vehicle_maps and not any(isinstance(x, dict) for x in (route or [])):
            issues.append(f"vehicle {vi + 1}: no per-stop pickup/dropoff quantities in the report")
        ld = L0
        cap = inst["caps"][min(vi, len(inst["caps"]) - 1)]
        for i in mid:
            q = qty_by_idx.get(i, 0.0)
            if q != int(q):
                issues.append(f"vehicle {vi + 1}: non-integer quantity {q} at station {ids[i]}")
            ld += q
            net[i] += q
            visits[i] += 1
            if ld < -1e-9 or ld > cap + 1e-9:
                issues.append(f"vehicle {vi + 1}: load {ld} outside [0, {cap}] after station {ids[i]}")
        if end_empty and abs(ld) > 1e-9:
            issues.append(f"vehicle {vi + 1}: ends with load {ld} but must return empty")
        rd = first(rec, DIST_KEYS)[1]
        if rd is not None and to_number(rd) is not None and not close(float(rd), vd):
            issues.append(f"vehicle {vi + 1}: reported distance {rd} != recomputed {vd:.6f}")
        per_vehicle.append({"vehicle": vi + 1, "route_ids": [ids[i] for i in mid], "distance": vd, "end_load": ld})
    if must_use and len(vehs) < inst["K"]:
        issues.append(f"only {len(vehs)} routes reported for {inst['K']} vehicles that must all be used")

    total_dev = 0.0
    for i, s in enumerate(S):
        if not split_ok and visits[i] > 1:
            issues.append(f"station {s['id']} served by {visits[i]} vehicles but split service is not allowed")
        if net[i] > s["initial_bikes"] + 1e-9:
            issues.append(f"station {s['id']}: net pickup {net[i]} exceeds initial bikes {s['initial_bikes']}")
        if s["initial_bikes"] - net[i] > s["capacity"] + 1e-9:
            issues.append(f"station {s['id']}: final bikes {s['initial_bikes'] - net[i]} exceed capacity {s['capacity']}")
        t = s["target"]
        if penalty_form == "absolute_deviation":
            total_dev += abs(net[i] - t)
        elif t > 0:
            total_dev += max(t - net[i], 0)
        elif t < 0:
            total_dev += max(net[i] - t, 0)
    pen = inst["penalty"] * total_dev
    obj = total_dist + pen

    custom = bool(st.get("custom_objective", False))  # adapt-model changed the penalty/objective
    checks = [(DIST_KEYS, total_dist, "travel distance")]
    if not custom:
        checks += [(PEN_KEYS, pen, "penalty"), (OBJ_KEYS, obj, "objective")]
    for keys, val, label in checks:
        k, v = first(rep, keys)
        if k is None and isinstance(rep, dict) and isinstance(rep.get("summary"), dict):
            k, v = first(rep["summary"], keys)
        if k is not None and to_number(v) is not None and not close(float(v), val):
            issues.append(f"reported {label} ({k}={v}) != recomputed {val:.6f}")

    sol_path = st.get("solution_path")
    if sol_path and not custom:
        try:
            with open(sol_path) as fh:
                sol = json.load(fh)
            if not close(sol["objective"], obj):
                issues.append(f"deliverable objective {obj:.6f} differs from solver solution {sol['objective']:.6f}"
                              " (transcription drift or different assumptions)")
        except Exception as exc:
            issues.append(f"cannot read solution_path for cross-check: {exc}")

    # fix-deliverable may waive validator blind spots (substring match), each with a justification
    waivers = [str(w) for w in (st.get("waived_issues") or [])]
    waived = [i for i in issues if any(w and w in i for w in waivers)]
    issues = [i for i in issues if i not in waived]
    emit({"verdict": "fail" if issues else "pass", "issues": issues, "waived": waived,
          "custom_objective_unchecked": custom,
          "recomputed": {"travel_distance": total_dist, "total_deviation": total_dev, "penalty_cost": pen,
                         "objective": obj, "vehicles": per_vehicle}})


if __name__ == "__main__":
    main()
