"""End-to-end route validation CLI.

Given the task data file and a route report, recomputes travel distance
from coordinates, runs structural checks per vehicle, and prints a JSON
summary. Exits 0 on success, 1 on any validation failure.

Usage:
    python scripts/validate_route.py \\
        --data /root/data.json \\
        --report path/to/report.json \\
        [--earth-radius 3960.0] \\
        [--allow-depot-to-depot] \\
        [--allow-repeat-stations] \\
        [--allow-empty-route] \\
        [--expected-distance VALUE] \\
        [--tol 1e-6]

The report file is JSON of the form:
    {
      "vehicles": [
        {"route": ["depot_start", <station_id>, ..., "depot_end"], ...},
        ...
      ],
      "travel_distance": <float>?
    }
"""

import argparse
import json
import sys
from pathlib import Path

# Allow this script to import its sibling library when invoked directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from routing_data import (  # noqa: E402
    DEFAULT_EARTH_RADIUS_MILES,
    assert_close,
    build_node_distances,
    check_route_structure,
    load_routing_data,
    route_distance_reported_ids,
)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", required=True, help="Path to task data JSON")
    p.add_argument("--report", required=True, help="Path to route report JSON")
    p.add_argument(
        "--earth-radius",
        type=float,
        default=DEFAULT_EARTH_RADIUS_MILES,
        help="Earth radius for great-circle distance (default: 3960.0).",
    )
    p.add_argument(
        "--allow-depot-to-depot",
        action="store_true",
        help="Permit the direct (depot_start, depot_end) arc.",
    )
    p.add_argument(
        "--allow-repeat-stations",
        action="store_true",
        help="Permit the same station ID to appear twice in one route.",
    )
    p.add_argument(
        "--allow-empty-route",
        action="store_true",
        help="Permit a vehicle route with no stations between depots.",
    )
    p.add_argument(
        "--expected-distance",
        type=float,
        default=None,
        help="If supplied, compare summed recomputed distance against this value.",
    )
    p.add_argument("--tol", type=float, default=1e-6)
    args = p.parse_args(argv)

    bundle = load_routing_data(args.data)
    distances = build_node_distances(
        bundle["depot"],
        bundle["station_locations"],
        radius=args.earth_radius,
        allow_direct_depot_to_depot=args.allow_depot_to_depot,
    )
    report = json.loads(Path(args.report).read_text())
    if "vehicles" not in report:
        sys.stderr.write("report missing 'vehicles' array\n")
        return 1

    total = 0.0
    all_errors = []
    per_vehicle = []
    for vi, vehicle in enumerate(report["vehicles"]):
        route = vehicle.get("route")
        if route is None:
            all_errors.append(f"vehicle {vi}: missing 'route'")
            per_vehicle.append(
                {"vehicle": vi, "distance": None, "errors": ["missing route"]}
            )
            continue
        errs = check_route_structure(
            route,
            bundle["id_to_idx"],
            require_at_least_one_station=not args.allow_empty_route,
            no_repeated_stations=not args.allow_repeat_stations,
        )
        if errs:
            all_errors.extend(f"vehicle {vi}: {e}" for e in errs)
            per_vehicle.append({"vehicle": vi, "distance": None, "errors": errs})
            continue
        dist = route_distance_reported_ids(route, distances, bundle["id_to_idx"])
        per_vehicle.append({"vehicle": vi, "distance": dist, "errors": []})
        total += dist

    summary = {
        "ok": not all_errors,
        "n_vehicles": len(report["vehicles"]),
        "n_stations": len(bundle["station_ids"]),
        "earth_radius": args.earth_radius,
        "recomputed_travel_distance": total,
        "reported_travel_distance": report.get("travel_distance"),
        "per_vehicle": per_vehicle,
        "errors": all_errors,
    }

    if args.expected_distance is not None:
        try:
            assert_close(total, args.expected_distance, tol=args.tol)
            summary["expected_distance_check"] = "pass"
        except AssertionError as exc:
            summary["expected_distance_check"] = f"fail: {exc}"
            summary["ok"] = False

    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
