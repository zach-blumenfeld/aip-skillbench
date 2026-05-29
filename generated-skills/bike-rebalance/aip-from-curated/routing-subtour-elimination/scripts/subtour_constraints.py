"""Static subtour-elimination constraint families.

Each function adds one of the three statically-enumerable subtour
formulations from the curated SKILL.md directly to the model. All assume
the base notation and base route constraints from `route_setup.py` are
already in place. Pick exactly ONE family per model — they overlap and
stacking them only wastes constraints.

Method choice:
  * `add_mtz_constraints`            — default; compact O(K n^2) and
                                       easy to debug. LP relaxation is
                                       weaker than flow-based.
  * `add_single_commodity_flow`      — stronger relaxation, supports
                                       optional station visits; adds
                                       O(K n^2) continuous flow vars.
                                       NEVER reuse physical vehicle load
                                       as the connectivity flow when
                                       pickup/dropoff is allowed.
  * `add_static_dfj_cuts`            — only for tiny `n` (curated source
                                       caps around 15-18 stations).
                                       Enumerates all subset cuts.

For larger instances where static DFJ blows up, use `lazy_separation.py`
instead.
"""

from __future__ import annotations

from itertools import combinations

DEPOT_START = "depot_start"
DEPOT_END = "depot_end"


def add_mtz_constraints(model, x, vehicles, stations):
    """Miller-Tucker-Zemlin subtour elimination.

    Adds a continuous order variable `order[v, i]` per (vehicle, station)
    with bounds [1, max(1, n)]. The classic MTZ inequality
    `order[v,i] - order[v,j] + n * x[v,i,j] <= n - 1` enforces a strict
    order along each used arc, which is incompatible with any cycle not
    touching the depot.

    Returns the order-variable dictionary so the caller can debug or
    inspect post-solve. The order values are artificial and must NOT be
    interpreted as service times — that requires a separate time model.
    """
    n = len(stations)
    upper = max(1, n)

    order = {
        (v, i): model.addVar(vtype="C", lb=1, ub=upper, name=f"order_{v}_{i}")
        for v in vehicles
        for i in stations
    }

    for v in vehicles:
        for i in stations:
            for j in stations:
                if i != j:
                    model.addCons(order[v, i] - order[v, j] + n * x[v, i, j] <= n - 1)

    return order


def add_single_commodity_flow(
    model, x, vehicles, stations, *, start=DEPOT_START, end=DEPOT_END
):
    """Single-commodity artificial-flow connectivity.

    Injects one unit of an artificial commodity at `start` per visited
    station, and forces the flow to reach every visited station along
    arcs the route actually uses (`f[v,i,j] <= n * x[v,i,j]`). Because
    `start` is the only source, any closed station-only cycle is starved
    and infeasible.

    The connectivity flow is NOT vehicle load. With pickup/dropoff,
    physical load can rise and fall along the route and so cannot prove
    connectivity. Keep this as a separate `f` variable family.

    Returns the flow variable dictionary.
    """
    from pyscipopt import quicksum

    n = max(1, len(stations))

    visit = {
        (v, i): quicksum(
            x[v, i, j] for j in (*stations, end) if j != i
        )
        for v in vehicles
        for i in stations
    }

    flow_arcs = [
        (i, j) for i in [start, *stations] for j in stations if i != j
    ]
    f = {
        (v, i, j): model.addVar(vtype="C", lb=0, ub=n, name=f"conn_flow_{v}_{i}_{j}")
        for v in vehicles
        for (i, j) in flow_arcs
    }

    for v in vehicles:
        total_visits = quicksum(visit[v, i] for i in stations)
        model.addCons(quicksum(f[v, start, j] for j in stations) == total_visits)

        for (i, j) in flow_arcs:
            model.addCons(f[v, i, j] <= n * x[v, i, j])

        for i in stations:
            incoming_flow = quicksum(
                f[v, h, i] for h in [start, *stations] if h != i
            )
            outgoing_flow = quicksum(
                f[v, i, j] for j in stations if j != i
            )
            model.addCons(incoming_flow - outgoing_flow == visit[v, i])

    return f


def add_static_dfj_cuts(model, x, vehicles, stations, *, max_n: int = 18):
    """Dantzig-Fulkerson-Johnson subset cuts, fully enumerated.

    For every nonempty proper subset S of stations:
        sum_{i in S, j in S, i != j} x[v,i,j] <= |S| - 1

    The number of constraints grows as O(K * 2^n), so the curated source
    caps usable n around 15-18. The hard guard here raises when
    `len(stations) > max_n` rather than silently emitting millions of
    constraints — bump `max_n` only after you have read the warning.

    Use for tiny instances or as a debugging baseline. Prefer
    `lazy_separation.iterative_subtour_cuts` for anything bigger.
    """
    from pyscipopt import quicksum

    n = len(stations)
    if n > max_n:
        raise RuntimeError(
            f"static DFJ enumeration is exponential; n={n} exceeds max_n={max_n}. "
            "Use lazy_separation.iterative_subtour_cuts instead, "
            "or pass max_n=<larger> if you are intentionally accepting the cost."
        )

    for v in vehicles:
        for r in range(2, n):
            for S_tuple in combinations(stations, r):
                S = set(S_tuple)
                model.addCons(
                    quicksum(x[v, i, j] for i in S for j in S if i != j)
                    <= len(S) - 1
                )
