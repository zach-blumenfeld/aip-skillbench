"""Great-circle distance and the arc-distance matrix over depot+stations.

`great_circle_miles` is the canonical metric: spherical-law-of-cosines in
miles with Earth radius 3960.0 by default — matches the bike-rebalance task's
declared metric. Override `radius` when the task declares a different value.

Do NOT mix this with Euclidean-on-degrees, haversine with a different radius,
miles + meters, or rounded distances inside an optimization objective.
"""

from __future__ import annotations

import math
from typing import Any, Hashable, Iterable

DEPOT_START = "depot_start"
DEPOT_END = "depot_end"

EARTH_RADIUS_MILES_DEFAULT = 3960.0


def great_circle_miles(a: dict, b: dict, radius: float = EARTH_RADIUS_MILES_DEFAULT) -> float:
    """Great-circle distance between two {latitude, longitude} points, in miles.

    Spherical law of cosines (the formulation the curated source uses).
    `cos_arc` is clamped into [-1, 1] to avoid floating-point domain errors
    that would otherwise raise from `math.acos`.
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


def build_node_resolver(depot: dict, station_locations: list[dict]):
    """Return a function mapping internal node label -> {latitude, longitude}.

    Internal nodes are either the string labels DEPOT_START / DEPOT_END, or
    integer station indices in `[0, len(station_locations))`.
    """

    def node_location(node: Hashable) -> dict:
        if node in (DEPOT_START, DEPOT_END):
            return depot
        return station_locations[int(node)]

    return node_location


def build_arc_distances(
    depot: dict,
    station_locations: list[dict],
    *,
    radius: float = EARTH_RADIUS_MILES_DEFAULT,
    allow_depot_to_depot: bool = False,
) -> dict[tuple[Any, Any], float]:
    """Build the (from_node, to_node) -> distance map over the canonical arc set.

    Arc set conventions:
      from_nodes = [DEPOT_START, 0, 1, ..., n-1]
      to_nodes   = [0, 1, ..., n-1, DEPOT_END]
      - no self-loops
      - direct (DEPOT_START, DEPOT_END) arc EXCLUDED by default — vehicles
        must visit at least one station (matches the bike-rebalance rule).
        Set allow_depot_to_depot=True if the task permits empty routes.

    The result is a plain dict so callers can plug it into any modeling
    library without coupling to a specific solver type.
    """
    stations = list(range(len(station_locations)))
    from_nodes = [DEPOT_START, *stations]
    to_nodes = [*stations, DEPOT_END]
    node_location = build_node_resolver(depot, station_locations)

    distances: dict[tuple[Any, Any], float] = {}
    for i in from_nodes:
        for j in to_nodes:
            if i == j:
                continue
            if (not allow_depot_to_depot) and i == DEPOT_START and j == DEPOT_END:
                continue
            distances[i, j] = great_circle_miles(
                node_location(i), node_location(j), radius=radius
            )
    return distances


def iter_arcs(distances: dict[tuple[Any, Any], float]) -> Iterable[tuple[Any, Any]]:
    """Iterate the arc keys — convenience for optimization-model loops."""
    return distances.keys()
