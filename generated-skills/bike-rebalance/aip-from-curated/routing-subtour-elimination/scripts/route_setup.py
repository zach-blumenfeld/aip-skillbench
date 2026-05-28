"""Canonical base notation for routing MIPs with binary arc variables.

The curated SKILL.md establishes a fixed convention:

    START = "depot_start"
    END   = "depot_end"
    vehicles, stations
    arcs  = all (i, j) pairs except self-loops and the START->END direct edge
    x[v, i, j]  : binary, 1 iff vehicle v traverses arc (i, j)

Subtour-elimination methods downstream assume that exact shape. Build the
arc set and `x` variable dictionary through this module so the rest of the
skill (MTZ, single-commodity flow, DFJ, lazy separation, route extraction)
plugs into a structure it can rely on.

`add_base_route_constraints` adds the degree-and-continuity rules that
every subtour formulation builds on top of. Without these constraints the
model has neither one-trip-per-vehicle nor flow conservation at each
visited station — subtour elimination alone does NOT make the routes
well-formed.

All helpers import PySCIPOpt lazily so this module is importable even when
the solver is missing; the import error surfaces at the first call.
"""

from __future__ import annotations

DEPOT_START = "depot_start"
DEPOT_END = "depot_end"


def build_arc_set(stations, *, start=DEPOT_START, end=DEPOT_END):
    """Return the canonical arc list for a routing MIP.

    Includes every (i, j) where i is in {start} U stations, j is in
    stations U {end}, i != j, and excludes the direct (start, end) edge
    (no-visit trip).
    """
    from_nodes = [start, *stations]
    to_nodes = [*stations, end]
    return [
        (i, j)
        for i in from_nodes
        for j in to_nodes
        if i != j and not (i == start and j == end)
    ]


def add_arc_variables(model, vehicles, stations, *, start=DEPOT_START, end=DEPOT_END):
    """Add the binary `x[v, i, j]` variable family and return the dict.

    Variable names follow the curated convention `x_{v}_{i}_{j}` so logs
    and debug output read uniformly across the skill's helpers.
    """
    arcs = build_arc_set(stations, start=start, end=end)
    x = {
        (v, i, j): model.addVar(vtype="B", name=f"x_{v}_{i}_{j}")
        for v in vehicles
        for (i, j) in arcs
    }
    return x, arcs


def add_base_route_constraints(
    model, x, vehicles, stations, *, start=DEPOT_START, end=DEPOT_END
):
    """Add degree + continuity + at-most-one-visit constraints.

    For each vehicle:
      * exactly one arc leaves `start` toward a station
      * exactly one arc arrives at `end` from a station
      * for each station: incoming arcs == outgoing arcs
      * for each station: outgoing arcs <= 1 (no revisits in the same trip)

    Subtour elimination assumes this structure. Adding subtour cuts on top
    of an unbalanced or revisit-allowing model produces nonsense; add this
    block first.
    """
    from pyscipopt import quicksum

    from_nodes = [start, *stations]
    to_nodes = [*stations, end]

    for v in vehicles:
        model.addCons(quicksum(x[v, start, j] for j in stations) == 1)
        model.addCons(quicksum(x[v, i, end] for i in stations) == 1)
        for i in stations:
            incoming = quicksum(x[v, j, i] for j in from_nodes if j != i)
            outgoing = quicksum(x[v, i, j] for j in to_nodes if j != i)
            model.addCons(incoming == outgoing)
            model.addCons(outgoing <= 1)
