"""Route conversions, distance reconstruction, and structural checks.

Routes appear in two forms:
  - internal  — list like [DEPOT_START, 3, 7, 2, DEPOT_END] where ints are
                station INDICES (0..n-1). Used by optimization variables.
  - reported  — list like [DEPOT_START, 393, 871, 240, DEPOT_END] where ints
                are user-facing station IDs. Used in report.json.

Convert at the boundary. Never mix the two inside one list.
"""

from __future__ import annotations

from typing import Any, Iterable

from distance import DEPOT_END, DEPOT_START  # type: ignore[import-not-found]


# ---------- conversions ----------------------------------------------------


def internal_to_reported(route_nodes: list[Any], idx_to_id: dict[int, int]) -> list[Any]:
    """Convert an internal route (indices) to a reported route (station IDs).

    String depot labels pass through unchanged.
    """
    return [
        node if isinstance(node, str) else idx_to_id[int(node)]
        for node in route_nodes
    ]


def parse_report_route(
    route: list[Any], id_to_idx: dict[int, int]
) -> list[Any]:
    """Parse a reported route back to internal indices.

    Raises ValueError if the route does not start at DEPOT_START, end at
    DEPOT_END, or references an unknown station ID. Use this before any
    cost / load reconstruction so a malformed report fails fast.
    """
    if not route or route[0] != DEPOT_START or route[-1] != DEPOT_END:
        raise ValueError(
            f"route must start at {DEPOT_START!r} and end at {DEPOT_END!r}; "
            f"got first={route[0] if route else None!r}, "
            f"last={route[-1] if route else None!r}"
        )

    parsed: list[Any] = [DEPOT_START]
    for raw in route[1:-1]:
        sid = int(raw)
        if sid not in id_to_idx:
            raise ValueError(f"unknown station id {sid}")
        parsed.append(id_to_idx[sid])
    parsed.append(DEPOT_END)
    return parsed


# ---------- distance reconstruction ----------------------------------------


def pairwise(items: Iterable[Any]) -> list[tuple[Any, Any]]:
    items = list(items)
    return list(zip(items, items[1:]))


def route_distance_internal(
    route_nodes: list[Any],
    distances: dict[tuple[Any, Any], float],
) -> float:
    """Sum pairwise arc distances over an internal-index route."""
    total = 0.0
    for i, j in pairwise(route_nodes):
        total += distances[i, j]
    return total


def route_distance_reported(
    route: list[Any],
    id_to_idx: dict[int, int],
    distances: dict[tuple[Any, Any], float],
) -> float:
    """Reconstruct the travel distance from a reported (IDs) route.

    Sequence: parse_report_route -> route_distance_internal. Always do BOTH —
    skipping the parse means an unknown station ID would be silently dropped
    when the distance dict raises KeyError, masking the real bug.
    """
    internal = parse_report_route(route, id_to_idx)
    return route_distance_internal(internal, distances)


def total_travel_distance_reported(
    report: dict,
    id_to_idx: dict[int, int],
    distances: dict[tuple[Any, Any], float],
) -> float:
    """Sum reported route distance across every vehicle in a report.json."""
    return sum(
        route_distance_reported(vehicle["route"], id_to_idx, distances)
        for vehicle in report["vehicles"]
    )


def assert_close(actual: float, expected: float, tol: float = 1e-6) -> None:
    """Tolerance-based float compare.

    Uses relative tolerance scaled by max(1, |expected|). Use this — never
    `actual == expected` — when comparing reconstructed distances to
    reported values; rounding to a few decimals introduces drift that
    exact compare flags as a bug.
    """
    if abs(actual - expected) > max(tol, tol * max(1.0, abs(expected))):
        raise AssertionError(f"{actual} != {expected}")


# ---------- structural checks ----------------------------------------------


def check_route_structure(
    route: list[Any],
    id_to_idx: dict[int, int],
    *,
    require_visit: bool = True,
    no_repeat: bool = True,
) -> list[str]:
    """Validate a REPORTED route end-to-end. Returns a list of problems found.

    Empty list = route is structurally sound. Caller decides whether to raise
    or aggregate across vehicles.

    Checks performed:
      - first node is DEPOT_START
      - last node is DEPOT_END
      - every non-depot node is a known station ID
      - stop list is non-empty when require_visit=True (the task's rule that
        a vehicle cannot stay at the depot)
      - no repeated station within the route when no_repeat=True (the task's
        "a vehicle can visit a station no more than once" rule)
    """
    problems: list[str] = []
    if not route:
        return ["empty route"]
    if route[0] != DEPOT_START:
        problems.append(f"first node is {route[0]!r}, expected {DEPOT_START!r}")
    if route[-1] != DEPOT_END:
        problems.append(f"last node is {route[-1]!r}, expected {DEPOT_END!r}")

    middle = route[1:-1]
    if require_visit and len(middle) == 0:
        problems.append("route visits no stations; vehicle cannot stay at depot")

    seen: set[int] = set()
    for raw in middle:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            problems.append(f"non-integer station node {raw!r}")
            continue
        if sid not in id_to_idx:
            problems.append(f"unknown station id {sid}")
        if no_repeat and sid in seen:
            problems.append(f"station {sid} visited more than once")
        seen.add(sid)

    return problems


def check_stops_match_route(route: list[Any], stops: list[dict]) -> list[str]:
    """Ensure the station-stop list aligns with the non-depot nodes in `route`.

    `route` lists all visited nodes (including depots); `stops` carries the
    per-stop quantities. Their non-depot portion must be the same sequence —
    otherwise downstream load reconstruction silently uses the wrong stop.
    """
    problems: list[str] = []
    middle_ids = [int(n) for n in route[1:-1] if not isinstance(n, str)]
    stop_ids = [int(s["station_id"]) for s in stops]
    if middle_ids != stop_ids:
        problems.append(
            f"route non-depot sequence {middle_ids} does not match "
            f"stops sequence {stop_ids}"
        )
    return problems
