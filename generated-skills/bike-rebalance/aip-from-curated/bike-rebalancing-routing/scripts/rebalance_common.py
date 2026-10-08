"""Shared data loading, ID mapping, and great-circle distances for the rebalancing scripts.

Stdlib only. Internal indices are used inside the model; original station IDs in every report.
"""
import json
import math
import os
import re
import sys

START = "depot_start"
END = "depot_end"
DEPOT_LABELS = {START, END, "depot", "Depot", "DEPOT", "depot_end", "depot_start"}

# Radius used by the spherical-law-of-cosines great-circle formula, per unit.
DEFAULT_RADIUS = {"miles": 3960.0, "km": 6371.0}


def read_stdin():
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    return payload.get("currentState", payload)


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def fail(msg, **extra):
    emit({"error": msg, **extra})
    sys.exit(1)


def abs_path(path, label):
    if not path:
        fail(f"{label} is empty")
    path = os.path.expanduser(str(path))
    if not os.path.isabs(path):
        fail(f"{label} must be an absolute path (scripts run with cwd=scripts/): {path!r}")
    return path


def _num(rec, keys, label, cast=float, default=None):
    for k in keys:
        if k in rec and rec[k] is not None:
            return cast(rec[k])
    if default is not None:
        return default
    fail(f"{label}: none of {keys} present; keys are {sorted(rec)}")


def parse_location(rec, label):
    lat = _num(rec, ["latitude", "lat"], label)
    lon = _num(rec, ["longitude", "lon", "lng"], label)
    if not -90.0 <= lat <= 90.0:
        fail(f"{label} latitude out of range: {lat}")
    if not -180.0 <= lon <= 180.0:
        fail(f"{label} longitude out of range: {lon}")
    return {"latitude": lat, "longitude": lon}


def target_sign(data, override=None):
    """+1 when a positive target means pick up bikes FROM the station, -1 when it means drop off."""
    if override in (1, -1):
        return override
    conv = str(data.get("net_rebalancing_target_sign_convention", "")).lower()
    if not conv:
        return 1  # recommended convention: positive = pickup
    m = re.search(r"positive[^;.]*", conv)
    clause = m.group(0) if m else conv
    pick = re.search(r"pick|remove|take|collect|surplus", clause)
    drop = re.search(r"drop|deliver|add|bring|deficit", clause)
    if pick and not drop:
        return 1
    if drop and not pick:
        return -1
    fail(f"cannot read target sign convention: {conv!r}; pass target_sign (+1 pickup / -1 dropoff)")


def great_circle(a, b, radius):
    d2r = math.pi / 180.0
    phi1 = (90.0 - a["latitude"]) * d2r
    phi2 = (90.0 - b["latitude"]) * d2r
    th1 = a["longitude"] * d2r
    th2 = b["longitude"] * d2r
    c = math.sin(phi1) * math.sin(phi2) * math.cos(th1 - th2) + math.cos(phi1) * math.cos(phi2)
    c = max(-1.0, min(1.0, c))  # clamp floating-point drift
    return math.acos(c) * radius


def resolve_radius(data, earth_radius):
    metric = str(data.get("distance_metric", "great_circle_miles")).lower()
    if "great_circle" not in metric and "haversine" not in metric and "spherical" not in metric:
        fail(f"unsupported distance_metric {metric!r}; this pack computes great-circle distances only")
    for k in ("earth_radius", "earth_radius_miles", "earth_radius_km", "radius"):
        if k in data:
            return float(data[k]), metric
    if earth_radius and float(earth_radius) > 0:
        return float(earth_radius), metric
    unit = "km" if ("km" in metric or "kilomet" in metric) else "miles"
    return DEFAULT_RADIUS[unit], metric


def load_instance(data_path, earth_radius=None, sign_override=None):
    with open(data_path) as fh:
        data = json.load(fh)
    stations_raw = data.get("stations")
    if not isinstance(stations_raw, list) or not stations_raw:
        fail(f"data has no 'stations' list; top-level keys are {sorted(data)}")
    sign = target_sign(data, sign_override)
    stations = []
    for s in stations_raw:
        sid = s.get("id", s.get("station_id"))
        label = f"station {sid}"
        if sid is None:
            fail(f"station record without id: {s}")
        init = _num(s, ["initial_bikes", "bikes", "inventory", "initial_inventory"], label, int)
        cap = _num(s, ["station_capacity", "capacity", "docks"], label, int)
        tgt = _num(s, ["net_rebalancing_target", "target", "net_target"], label, int)
        if not 0 <= init <= cap:
            fail(f"{label}: initial_bikes {init} outside [0, capacity {cap}]")
        stations.append({
            "id": sid, **parse_location(s, label),
            "initial_bikes": init, "capacity": cap,
            "target": sign * tgt,  # internal: positive = net pickup
            "raw_target": tgt,
        })
    ids = [s["id"] for s in stations]
    if len(set(map(str, ids))) != len(ids):
        fail("duplicate station ids")
    K = int(_num(data, ["vehicle_count", "num_vehicles", "vehicles"], "data"))
    capq = data.get("vehicle_capacity", data.get("capacity"))
    caps = [int(c) for c in capq] if isinstance(capq, list) else [int(capq)] * K
    if len(caps) != K:
        fail(f"vehicle_capacity list length {len(caps)} != vehicle_count {K}")
    penalty = float(data.get("penalty_weight", data.get("penalty", 1.0)))
    depot = parse_location(data["depot"], "depot")
    radius, metric = resolve_radius(data, earth_radius)
    return {
        "data": data, "stations": stations, "ids": ids,
        "id_to_idx": {str(sid): i for i, sid in enumerate(ids)},
        "K": K, "caps": caps, "penalty": penalty, "depot": depot,
        "radius": radius, "metric": metric, "sign": sign,
    }


def node_loc(inst, node):
    return inst["depot"] if node in (START, END) else inst["stations"][int(node)]


def distance_matrix(inst):
    n = len(inst["stations"])
    nodes = [START, *range(n), END]
    return {(i, j): great_circle(node_loc(inst, i), node_loc(inst, j), inst["radius"])
            for i in nodes for j in nodes if i != j}
