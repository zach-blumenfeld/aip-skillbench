"""Geospatial routing data helpers for depot + station problems.

Library functions for parsing the task data file, validating coordinates,
mapping between user-facing station IDs and internal array indices,
computing great-circle distances, building the arc-set distance dictionary
used by routing optimization, converting routes between the two ID
spaces, and reconstructing travel distance from a reported route.

CLI:
    python routing_data.py validate <path/to/data.json>
runs the load + coordinate-validation pass and prints a summary.
"""

import json
import math
import sys
from pathlib import Path


START = "depot_start"
END = "depot_end"

# Default Earth radius used by the bike-rebalance task family.
# ALWAYS confirm from the task statement and pass `radius=` explicitly
# when it differs.
DEFAULT_EARTH_RADIUS_MILES = 3960.0


def parse_location(record, label):
    """Validate a {latitude, longitude} record and return floats."""
    lat = float(record["latitude"])
    lon = float(record["longitude"])
    if not (-90.0 <= lat <= 90.0):
        raise ValueError(f"{label} latitude out of range: {lat}")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError(f"{label} longitude out of range: {lon}")
    return {"latitude": lat, "longitude": lon}


def load_routing_data(path):
    """Parse the task data JSON and build ID / index mappings.

    Returns a dict with:
      depot              — validated {latitude, longitude}
      stations           — raw station records, input order (preserves extra fields)
      station_locations  — validated {latitude, longitude}, input order
      station_ids        — list[int] of station IDs, input order
      id_to_idx          — {station_id: internal_index}
      idx_to_id          — {internal_index: station_id}
    """
    data = json.loads(Path(path).read_text())
    if "stations" not in data:
        raise ValueError("data is missing 'stations' array")
    if "depot" not in data:
        raise ValueError("data is missing 'depot' object")

    stations_raw = data["stations"]
    station_ids = [int(s["id"]) for s in stations_raw]
    if len(station_ids) != len(set(station_ids)):
        raise ValueError("duplicate station ids in input data")

    depot = parse_location(data["depot"], "depot")
    station_locations = [
        parse_location(s, f"station {s['id']}") for s in stations_raw
    ]

    id_to_idx = {sid: idx for idx, sid in enumerate(station_ids)}
    idx_to_id = {idx: sid for sid, idx in id_to_idx.items()}

    return {
        "depot": depot,
        "stations": stations_raw,
        "station_locations": station_locations,
        "station_ids": station_ids,
        "id_to_idx": id_to_idx,
        "idx_to_id": idx_to_id,
    }


def great_circle_miles(a, b, radius=DEFAULT_EARTH_RADIUS_MILES):
    """Great-circle distance between two {latitude, longitude} points.

    Pass `radius` that matches the task statement. The cosine of the
    central angle is clamped to [-1, 1] before acos to avoid floating
    point domain errors on near-identical points.
    """
    lat1 = float(a["latitude"])
    lon1 = float(a["longitude"])
    lat2 = float(b["latitude"])
    lon2 = float(b["longitude"])

    deg_to_rad = math.pi / 180.0
    phi1 = (90.0 - lat1) * deg_to_rad
    phi2 = (90.0 - lat2) * deg_to_rad
    theta1 = lon1 * deg_to_rad
    theta2 = lon2 * deg_to_rad

    cos_arc = (
        math.sin(phi1) * math.sin(phi2) * math.cos(theta1 - theta2)
        + math.cos(phi1) * math.cos(phi2)
    )
    cos_arc = max(-1.0, min(1.0, cos_arc))
    return math.acos(cos_arc) * radius


def node_location(node, depot, station_locations):
    """Look up the {lat, lon} for a routing node (START / END / int index)."""
    if node in (START, END):
        return depot
    return station_locations[int(node)]


def build_node_distances(
    depot,
    station_locations,
    radius=DEFAULT_EARTH_RADIUS_MILES,
    allow_direct_depot_to_depot=False,
):
    """Build the (from_node, to_node) -> miles dict for the routing arc set.

    Nodes are START ("depot_start"), int station indices 0..n-1, and END
    ("depot_end"). The direct (START, END) arc is omitted by default —
    vehicles must visit at least one station. Pass
    allow_direct_depot_to_depot=True if the model permits empty routes.
    """
    n = len(station_locations)
    stations = range(n)
    from_nodes = [START, *stations]
    to_nodes = [*stations, END]

    distances = {}
    for i in from_nodes:
        for j in to_nodes:
            if i == j:
                continue
            if i == START and j == END and not allow_direct_depot_to_depot:
                continue
            distances[i, j] = great_circle_miles(
                node_location(i, depot, station_locations),
                node_location(j, depot, station_locations),
                radius=radius,
            )
    return distances


def route_to_report_ids(route_nodes, idx_to_id):
    """Convert an internal-index route to reported (station ID) form.

    String nodes (START / END) are passed through; ints are translated
    via idx_to_id.
    """
    return [
        node if isinstance(node, str) else idx_to_id[int(node)]
        for node in route_nodes
    ]


def parse_report_route(route, id_to_idx):
    """Convert a reported route (station IDs) to internal-index form.

    The route must start with START and end with END. Each intermediate
    entry must be a station ID present in id_to_idx. Raises ValueError
    on malformed routes.
    """
    if len(route) < 2 or route[0] != START or route[-1] != END:
        raise ValueError(f"route must start at {START!r} and end at {END!r}")
    parsed = [START]
    for raw in route[1:-1]:
        sid = int(raw)
        if sid not in id_to_idx:
            raise ValueError(f"unknown station id {sid}")
        parsed.append(id_to_idx[sid])
    parsed.append(END)
    return parsed


def pairwise(items):
    return list(zip(items, items[1:]))


def route_distance_internal(route_nodes, distances):
    """Sum distances along an internal-index route. KeyError on a missing arc."""
    total = 0.0
    for i, j in pairwise(route_nodes):
        if (i, j) not in distances:
            raise KeyError(
                f"no distance for arc ({i!r}, {j!r}) — "
                "check that build_node_distances included it"
            )
        total += distances[i, j]
    return total


def route_distance_reported_ids(route, distances, id_to_idx):
    """Sum distances along a reported (station-ID) route."""
    internal = parse_report_route(route, id_to_idx)
    return route_distance_internal(internal, distances)


def check_route_structure(
    route,
    id_to_idx,
    require_at_least_one_station=True,
    no_repeated_stations=True,
):
    """Run structural checks on a reported route.

    Returns a list of error strings (empty when the route passes). Does
    not raise — callers decide how to fail.
    """
    errors = []
    if len(route) < 2:
        errors.append("route has fewer than 2 nodes")
        return errors
    if route[0] != START:
        errors.append(f"route must start with {START!r}, got {route[0]!r}")
    if route[-1] != END:
        errors.append(f"route must end with {END!r}, got {route[-1]!r}")
    middle = route[1:-1]
    if require_at_least_one_station and len(middle) == 0:
        errors.append("route has no stations between depot endpoints")
    seen = set()
    for raw in middle:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            errors.append(f"non-integer station entry: {raw!r}")
            continue
        if sid not in id_to_idx:
            errors.append(f"unknown station id {sid}")
        if no_repeated_stations:
            if sid in seen:
                errors.append(f"repeated station id {sid}")
            seen.add(sid)
    return errors


def assert_close(actual, expected, tol=1e-6):
    """Compare floats with absolute + relative tolerance."""
    if abs(actual - expected) > max(tol, tol * max(1.0, abs(expected))):
        raise AssertionError(
            f"distance mismatch: actual={actual!r} expected={expected!r}"
        )


def _cli_validate(path):
    bundle = load_routing_data(path)
    summary = {
        "ok": True,
        "n_stations": len(bundle["station_ids"]),
        "depot": bundle["depot"],
        "first_station_id": (
            bundle["station_ids"][0] if bundle["station_ids"] else None
        ),
        "id_range": (
            [min(bundle["station_ids"]), max(bundle["station_ids"])]
            if bundle["station_ids"]
            else None
        ),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "validate":
        _cli_validate(sys.argv[2])
    else:
        sys.stderr.write(
            "Usage: python routing_data.py validate <path/to/data.json>\n"
            "Library functions are importable; this CLI runs the load + "
            "coordinate-validation pass.\n"
        )
        sys.exit(2)
