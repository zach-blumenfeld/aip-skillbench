"""Reconstruct and validate routes from a solved routing model.

The curated SKILL.md treats route extraction as the final guardrail:
even an optimal SCIP solve with a chosen subtour formulation can be
buggy if variables were keyed wrong or the wrong arcs were selected by
floating-point noise. Walking the successor map from `start` to `end`
detects disconnection, repeated stations, and missing endpoints.

`selected_arcs_for_vehicle` mirrors the convention from
`lazy_separation.py` and uses the same 0.5 binary threshold.
"""

from __future__ import annotations

DEPOT_START = "depot_start"
DEPOT_END = "depot_end"


def selected_arcs_for_vehicle(model, x, v, arcs):
    """Return list of arcs (i, j) selected for vehicle v in the incumbent."""
    return [(i, j) for (i, j) in arcs if model.getVal(x[v, i, j]) > 0.5]


def extract_route(selected, *, start=DEPOT_START, end=DEPOT_END):
    """Return the ordered station/depot sequence for a single vehicle.

    `selected` is the list of (i, j) arcs for the vehicle.

    Walks the successor map from `start` until `end`. Raises
    `RuntimeError` on the canonical failure modes the curated source
    flags:

      * route disconnected at a node (`outgoing[cur]` missing)
      * cycle detected (a node revisited before `end` is reached)

    A caller should also confirm:
      * route starts with `start` (true by construction here)
      * route ends with `end` (true by construction here)
      * every required station appears exactly the required number of
        times (problem-specific; not enforced here)
    """
    outgoing = dict(selected)
    route = [start]
    cur = start
    seen: set = {start}
    while cur != end:
        if cur not in outgoing:
            raise RuntimeError(f"route disconnected at {cur!r}")
        cur = outgoing[cur]
        if cur in seen and cur != end:
            raise RuntimeError(f"cycle detected at {cur!r}")
        route.append(cur)
        seen.add(cur)
    return route


def extract_all_routes(model, x, vehicles, arcs, *, start=DEPOT_START, end=DEPOT_END):
    """Convenience: extract one route per vehicle.

    Returns a dict {vehicle: [start, ..., end]}.
    """
    return {
        v: extract_route(
            selected_arcs_for_vehicle(model, x, v, arcs), start=start, end=end
        )
        for v in vehicles
    }
