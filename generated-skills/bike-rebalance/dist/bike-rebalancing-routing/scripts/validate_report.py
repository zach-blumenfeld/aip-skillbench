#!/usr/bin/env python3
"""Independent validator for a bike-rebalancing report.json against its data.json.

Requires: Python >= 3.10, standard library only (no solver needed).

Recomputes every rule from the report and the data alone: route shape, known station IDs,
per-vehicle no-repeat, stops == route, load chain within [0, vehicle_capacity], no mixed
pickup/dropoff at one stop, station totals, final inventory within [0, station_capacity],
unmet amounts, penalty, great-circle travel distance and objective arithmetic.

Usage:
  python scripts/validate_report.py --data /root/data.json --report /root/report.json \
      [--radius 3960.0] [--allow-idle-vehicles] [--no-split-service]
Exit 0 and prints "VALID" when every check passes; exit 1 and lists each violation otherwise.
"""
import argparse
import json
import math
import sys
from pathlib import Path

START, END = "depot_start", "depot_end"
TOL = 1e-6


def gc_miles(a, b, radius):
    d2r = math.pi / 180.0
    phi1, phi2 = (90.0 - a[0]) * d2r, (90.0 - b[0]) * d2r
    th1, th2 = a[1] * d2r, b[1] * d2r
    c = math.sin(phi1) * math.sin(phi2) * math.cos(th1 - th2) + math.cos(phi1) * math.cos(phi2)
    return math.acos(max(-1.0, min(1.0, c))) * radius


def close(a, b):
    return abs(float(a) - float(b)) <= max(TOL, TOL * max(1.0, abs(float(b))))


def is_int(v):
    return close(v, round(float(v)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="/root/data.json")
    ap.add_argument("--report", default="/root/report.json")
    ap.add_argument("--radius", type=float, default=3960.0)
    ap.add_argument("--allow-idle-vehicles", action="store_true")
    ap.add_argument("--no-split-service", action="store_true")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text())
    rep = json.loads(Path(args.report).read_text())
    errs = []
    C = float(data["vehicle_capacity"])
    pw = float(data["penalty_weight"])
    depot = (float(data["depot"]["latitude"]), float(data["depot"]["longitude"]))
    st = {int(s["id"]): s for s in data["stations"]}
    loc = {sid: (float(s["latitude"]), float(s["longitude"])) for sid, s in st.items()}

    for key in ("summary", "vehicles", "stations"):
        if key not in rep:
            errs.append(f"report missing '{key}'")
    if errs:
        print("\n".join(errs))
        sys.exit(1)

    vehicles = rep["vehicles"]
    vids = [v.get("vehicle_id") for v in vehicles]
    if len(vehicles) != int(data["vehicle_count"]):
        errs.append(f"{len(vehicles)} vehicles reported, vehicle_count={data['vehicle_count']}")
    if len(set(vids)) != len(vids):
        errs.append(f"duplicate vehicle_id in {vids}")

    picked = {sid: 0.0 for sid in st}
    dropped = {sid: 0.0 for sid in st}
    visitors = {sid: 0 for sid in st}
    travel = 0.0
    for veh in vehicles:
        tag = f"vehicle {veh.get('vehicle_id')}"
        route = veh.get("route", [])
        if not route or route[0] != START or route[-1] != END:
            errs.append(f"{tag}: route must start with '{START}' and end with '{END}'")
            continue
        mid = route[1:-1]
        if any(isinstance(r, str) for r in mid):
            errs.append(f"{tag}: depot label inside route")
            continue
        mid = [int(r) for r in mid]
        if not mid and not args.allow_idle_vehicles:
            errs.append(f"{tag}: visits no station")
        unknown = [r for r in mid if r not in st]
        if unknown:
            errs.append(f"{tag}: unknown station ids {unknown}")
            continue
        if len(set(mid)) != len(mid):
            errs.append(f"{tag}: visits a station more than once")
        stops = veh.get("stops", [])
        if [int(s["station_id"]) for s in stops] != mid:
            errs.append(f"{tag}: stops do not match route order")
        pts = [depot, *[loc[r] for r in mid], depot]
        travel += sum(gc_miles(a, b, args.radius) for a, b in zip(pts, pts[1:]))
        load = float(veh.get("start_load", 0.0))
        if not (-TOL <= load <= C + TOL) or not is_int(load):
            errs.append(f"{tag}: start_load {load} outside [0, {C}] or not integer")
        for stop in stops:
            sid = int(stop["station_id"])
            p, d = float(stop["bikes_picked_up"]), float(stop["bikes_dropped_off"])
            if p < -TOL or d < -TOL or not is_int(p) or not is_int(d):
                errs.append(f"{tag} @ {sid}: quantities must be non-negative integers ({p}, {d})")
            if p > TOL and d > TOL:
                errs.append(f"{tag} @ {sid}: both picks up and drops off")
            load = load + p - d
            if not close(stop["load_after_stop"], load):
                errs.append(f"{tag} @ {sid}: load_after_stop {stop['load_after_stop']} != {load}")
            if not (-TOL <= load <= C + TOL):
                errs.append(f"{tag} @ {sid}: load {load} outside [0, {C}]")
            if sid in picked:
                picked[sid] += p
                dropped[sid] += d
                visitors[sid] += 1
        if not close(veh.get("end_load", float("nan")), load):
            errs.append(f"{tag}: end_load {veh.get('end_load')} != {load}")

    if args.no_split_service:
        for sid, k in visitors.items():
            if k > 1:
                errs.append(f"station {sid} visited by {k} vehicles (split service forbidden)")

    rep_st = {int(s["station_id"]): s for s in rep["stations"]}
    if sorted(rep_st) != sorted(st) or len(rep["stations"]) != len(st):
        errs.append("stations list must contain every data.json station exactly once")
    total_unmet = 0.0
    for sid, s in st.items():
        net = picked[sid] - dropped[sid]
        unmet = abs(float(s["net_rebalancing_target"]) - net)
        total_unmet += unmet
        final = float(s["initial_bikes"]) - picked[sid] + dropped[sid]
        if not (-TOL <= final <= float(s["station_capacity"]) + TOL):
            errs.append(f"station {sid}: final inventory {final} outside [0, {s['station_capacity']}]")
        r = rep_st.get(sid)
        if r is None:
            continue
        for key, want in [("net_rebalancing_target", float(s["net_rebalancing_target"])),
                          ("total_bikes_picked_up", picked[sid]), ("total_bikes_dropped_off", dropped[sid]),
                          ("net_bike_change", net), ("unmet_rebalancing_amount", unmet)]:
            if key not in r or not close(r[key], want):
                errs.append(f"station {sid}: {key}={r.get(key)} expected {want}")

    pen = pw * total_unmet
    summ = rep["summary"]
    for key, want in [("travel_distance_miles", travel), ("total_unmet_rebalancing_amount", total_unmet),
                      ("unmet_rebalancing_penalty", pen), ("objective", travel + pen)]:
        if key not in summ or not close(summ[key], want):
            errs.append(f"summary.{key}={summ.get(key)} expected {want}")

    if errs:
        print("INVALID")
        print("\n".join(f"- {e}" for e in errs))
        sys.exit(1)
    print(f"VALID objective={travel + pen:.6f} travel={travel:.6f} unmet={total_unmet:g} penalty={pen:.6f}")


if __name__ == "__main__":
    main()
