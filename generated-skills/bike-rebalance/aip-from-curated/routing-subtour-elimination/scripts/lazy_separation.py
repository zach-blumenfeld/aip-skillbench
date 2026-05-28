"""Iterative DFJ-cut separation for routing MIPs.

The strongest practical pattern from the curated source: solve with only
base route constraints, look at the incumbent for any station-only
cycles disconnected from the depot, add ONLY the DFJ cuts that those
cycles violate, and re-solve. Continue until no incumbent has a
disconnected cycle.

This module is the *portable* variant that does not depend on solver
callback APIs. Use it when:

  * The solver's lazy-callback interface is not convenient (e.g.,
    PySCIPOpt without constraint handler plumbing), or
  * You want the cut-generation logic visible and unit-testable.

For solvers with simple lazy callbacks, the same cycle detection can be
called from inside a callback for tighter performance.
"""

from __future__ import annotations

from typing import Iterable


def selected_arcs(model, x, v, arcs):
    """Return the arcs (i, j) where `x[v, i, j]` is set in the incumbent.

    Uses the curated 0.5 binary threshold — SCIP returns floats for
    binaries and reading them with `== 1` will miss numerically-noisy
    ones.
    """
    return [(i, j) for (i, j) in arcs if model.getVal(x[v, i, j]) > 0.5]


def station_cycles_without_start(selected, stations, *, start, end):
    """Find closed cycles among stations in the selected-arc set.

    Walks successor links from each station. A closed cycle that does
    not touch `start` or `end` is a subtour and must be cut. Cycles that
    contain `start` or `end` are the legitimate depot-to-depot route and
    are skipped.

    Returns a list of cycles, each a list of station ids in traversal
    order.
    """
    succ = dict(selected)
    cycles: list[list] = []
    seen: set = set()

    for s in stations:
        if s in seen or s not in succ:
            continue
        path: list = []
        pos: dict = {}
        cur = s
        while cur in succ and cur not in pos and cur not in seen:
            pos[cur] = len(path)
            path.append(cur)
            cur = succ[cur]
        seen.update(path)
        if cur in pos:
            cycle = path[pos[cur]:]
            if start not in cycle and end not in cycle:
                cycles.append(cycle)
    return cycles


def add_subtour_cut(model, x, v, cycle: Iterable):
    """Add a DFJ cut forbidding the given subtour for vehicle `v`.

    Caller is responsible for `model.freeTransform()` before adding cuts
    after a solve — SCIP requires it to re-enter the construction stage.
    """
    from pyscipopt import quicksum

    S = set(cycle)
    model.addCons(
        quicksum(x[v, i, j] for i in S for j in S if i != j) <= len(S) - 1
    )


def iterative_subtour_cuts(
    model, x, vehicles, stations, arcs, *, start, end, max_iterations: int = 100
):
    """Solve-detect-cut loop. Returns the number of iterations run.

    On each iteration:
      1. `model.optimize()`
      2. Fail loudly if no incumbent exists (status surfaces in the error).
      3. For each vehicle, find station-only cycles in the incumbent.
      4. For each cycle of size >= 2, call `freeTransform` and add the
         DFJ cut.
      5. Stop when no new cuts were added (incumbent is subtour-free).

    Raises after `max_iterations` to prevent runaway loops if the cut
    set somehow does not converge — convergence is guaranteed in theory
    but a bug elsewhere (e.g., wrong cycle detection) could mask itself
    as endless re-solving.
    """
    for iteration in range(1, max_iterations + 1):
        model.optimize()
        if model.getNSols() == 0:
            raise RuntimeError(
                f"no feasible solution; status={model.getStatus()}"
            )

        cuts_added = 0
        for v in vehicles:
            selected = selected_arcs(model, x, v, arcs)
            for cycle in station_cycles_without_start(
                selected, stations, start=start, end=end
            ):
                if len(cycle) >= 2:
                    model.freeTransform()
                    add_subtour_cut(model, x, v, cycle)
                    cuts_added += 1

        if cuts_added == 0:
            return iteration

    raise RuntimeError(
        f"iterative subtour separation did not converge in "
        f"{max_iterations} iterations"
    )
