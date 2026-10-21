"""Check report.json against every task rule, recomputing all numbers from data.json.

Does not trust any value in the report: distance comes from coordinates, loads from the
stop quantities, station totals from the stops, penalties from the targets.
Exits non-zero listing every violation.
"""
import json
from pathlib import Path

import rebalance_core as rc

TOL = 1e-6


def close(a, b, tol=TOL):
    return abs(float(a) - float(b)) <= max(tol, tol * max(1.0, abs(float(b))))


def check(inst, report, radius, rules):
    errors = []
    Q = inst["vehicle_capacity"]
    stations = inst["stations"]
    by_id = {str(s["id"]): s for s in stations}
    picked = {k: 0.0 for k in by_id}
    dropped = {k: 0.0 for k in by_id}
    visitors = {k: 0 for k in by_id}
    travel = 0.0

    for key in ("summary", "vehicles", "stations"):
        if key not in report:
            errors.append(f"report missing top-level '{key}'")
    if errors:
        return errors, None

    vehicles = report["vehicles"]
    ids = [veh.get("vehicle_id") for veh in vehicles]
    if len(vehicles) != inst["vehicle_count"] or sorted(ids) != list(range(1, inst["vehicle_count"] + 1)):
        errors.append(f"vehicles list must hold vehicle_id 1..{inst['vehicle_count']}, got {ids}")

    for veh in vehicles:
        vid = veh.get("vehicle_id")
        route, stops = veh.get("route", []), veh.get("stops", [])
        if len(route) < 2 or route[0] != rc.START or route[-1] != rc.END:
            errors.append(f"vehicle {vid}: route must start '{rc.START}' and end '{rc.END}'")
            continue
        mid = route[1:-1]
        if rules["every_vehicle_must_visit"] and not mid:
            errors.append(f"vehicle {vid}: must visit at least one station")
        if [str(s) for s in mid] != [str(s.get("station_id")) for s in stops]:
            errors.append(f"vehicle {vid}: route stations differ from stops sequence")
        if len({str(s) for s in mid}) != len(mid):
            errors.append(f"vehicle {vid}: visits a station more than once")
        load = float(veh.get("start_load", -1))
        if not -TOL <= load <= Q + TOL:
            errors.append(f"vehicle {vid}: start_load {load} outside [0, {Q}]")
        if not rules["loaded_departure_allowed"] and not close(load, 0.0):
            errors.append(f"vehicle {vid}: start_load must be 0 under the task's rules")
        prev = inst["depot"]
        for stop in stops:
            sid = str(stop.get("station_id"))
            if sid not in by_id:
                errors.append(f"vehicle {vid}: unknown station {sid}")
                continue
            up = float(stop.get("bikes_picked_up", 0))
            down = float(stop.get("bikes_dropped_off", 0))
            for name, q in (("bikes_picked_up", up), ("bikes_dropped_off", down)):
                if q < -TOL or not close(q, round(q)):
                    errors.append(f"vehicle {vid} stop {sid}: {name} must be a non-negative integer, got {q}")
            if up > TOL and down > TOL:
                errors.append(f"vehicle {vid} stop {sid}: both picks up and drops off")
            load = load + up - down
            if not close(stop.get("load_after_stop", float("nan")), load):
                errors.append(f"vehicle {vid} stop {sid}: load_after_stop {stop.get('load_after_stop')} != {load}")
            if not -TOL <= load <= Q + TOL:
                errors.append(f"vehicle {vid} stop {sid}: load {load} outside [0, {Q}]")
            picked[sid] += up
            dropped[sid] += down
            visitors[sid] += 1
            loc = by_id[sid]["loc"]
            travel += rc.great_circle_miles(prev, loc, radius)
            prev = loc
        if stops:
            travel += rc.great_circle_miles(prev, inst["depot"], radius)
        if not close(veh.get("end_load", float("nan")), load):
            errors.append(f"vehicle {vid}: end_load {veh.get('end_load')} != final load {load}")

    rows = {str(r.get("station_id")): r for r in report["stations"]}
    if len(report["stations"]) != len(stations) or set(rows) != set(by_id):
        errors.append("stations list must hold every station in data.json exactly once")
    total_unmet = 0.0
    for sid, st in by_id.items():
        net = picked[sid] - dropped[sid]
        final = st["initial"] - picked[sid] + dropped[sid]
        if not -TOL <= final <= st["capacity"] + TOL:
            errors.append(f"station {sid}: final inventory {final} outside [0, {st['capacity']}]")
        if rules["exclusive_station_visits"] and visitors[sid] > 1:
            errors.append(f"station {sid}: visited by {visitors[sid]} vehicles")
        unmet = abs(st["target"] - net)
        total_unmet += unmet
        row = rows.get(sid)
        if row is None:
            continue
        expect = {"net_rebalancing_target": st["target"], "total_bikes_picked_up": picked[sid],
                  "total_bikes_dropped_off": dropped[sid], "net_bike_change": net,
                  "unmet_rebalancing_amount": unmet}
        for key, val in expect.items():
            if not close(row.get(key, float("nan")), val):
                errors.append(f"station {sid}: {key} {row.get(key)} != {val}")

    penalty = inst["penalty_weight"] * total_unmet
    summary = {"objective": travel + penalty, "travel_distance_miles": travel,
               "unmet_rebalancing_penalty": penalty, "total_unmet_rebalancing_amount": total_unmet}
    for key, val in summary.items():
        if not close(report["summary"].get(key, float("nan")), val):
            errors.append(f"summary.{key} {report['summary'].get(key)} != recomputed {val}")
    return errors, summary


def main():
    state = rc.read_stdin()
    radius = float(state["earth_radius_miles"])
    try:
        inst = rc.load_instance(state["data_path"])
        report = json.loads(Path(state["report_path"]).read_text())
    except Exception as exc:
        rc.fail(f"cannot read inputs: {exc}")
    errors, summary = check(inst, report, radius, rc.rules_from_state(state))
    if errors:
        rc.fail("report.json violates the task rules:\n- " + "\n- ".join(errors))
    rc.emit({
        "verified_objective": summary["objective"],
        "verified_travel_distance_miles": summary["travel_distance_miles"],
        "verified_unmet_rebalancing_penalty": summary["unmet_rebalancing_penalty"],
        "verified_total_unmet_rebalancing_amount": summary["total_unmet_rebalancing_amount"],
    })


if __name__ == "__main__":
    main()
