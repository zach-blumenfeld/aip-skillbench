"""Economic dispatch solver (energy + optional operating reserves).

Solves a convex (LP/QP) economic-dispatch problem over MATPOWER-shaped data:
  minimize total polynomial generator cost
  subject to
    generator P_min / P_max limits,
    system-wide power balance,
    optional operating-reserve capacity, coupling, and requirement.

Network constraints (line limits / PTDF) are NOT modeled — pair with the
`dc-power-flow` skill if branch flow limits must be enforced.

Usage from another script or notebook:

    from economic_dispatch import solve_economic_dispatch
    result = solve_economic_dispatch(
        gens=gens,            # np.ndarray, shape (n_gen, >=10), MATPOWER `gen`
        gencost=gencost,      # np.ndarray, MATPOWER `gencost`, MODEL==2
        buses=buses,          # np.ndarray, shape (n_bus, >=3), MATPOWER `bus`
        baseMVA=baseMVA,      # float
        reserve_capacity=...  # optional list/array, length n_gen, MW
        reserve_requirement=. # optional float, MW
    )

Returns a dict with `generator_dispatch`, `totals`, and solver metadata.
"""

from __future__ import annotations

from typing import Any

import cvxpy as cp
import numpy as np


PMAX_COL = 8
PMIN_COL = 9
GEN_BUS_COL = 0
BUS_PD_COL = 2

NCOST_COL = 3
COEFF_START_COL = 4


def _build_cost(Pg: cp.Variable, gencost: np.ndarray, baseMVA: float) -> cp.Expression:
    """Polynomial cost (MATPOWER MODEL=2). Handles constant/linear/quadratic NCOST."""
    n_gen = gencost.shape[0]
    cost = 0
    for i in range(n_gen):
        ncost = int(gencost[i, NCOST_COL])
        Pg_MW = Pg[i] * baseMVA
        if ncost >= 3:
            c2 = float(gencost[i, COEFF_START_COL])
            c1 = float(gencost[i, COEFF_START_COL + 1])
            c0 = float(gencost[i, COEFF_START_COL + 2])
            cost = cost + c2 * cp.square(Pg_MW) + c1 * Pg_MW + c0
        elif ncost == 2:
            c1 = float(gencost[i, COEFF_START_COL])
            c0 = float(gencost[i, COEFF_START_COL + 1])
            cost = cost + c1 * Pg_MW + c0
        elif ncost == 1:
            cost = cost + float(gencost[i, COEFF_START_COL])
        # ncost == 0: no cost contribution
    return cost


def solve_economic_dispatch(
    gens: np.ndarray,
    gencost: np.ndarray,
    buses: np.ndarray,
    baseMVA: float,
    reserve_capacity: Any | None = None,
    reserve_requirement: float | None = None,
    solver: str = "CLARABEL",
) -> dict:
    """Solve economic dispatch; return dispatch, totals, solver status.

    Reserve co-optimization is enabled when BOTH `reserve_capacity` and
    `reserve_requirement` are provided. Otherwise reserves are omitted and
    reported as zero in the output (preserving a stable output shape).

    Per-unit convention follows MATPOWER: Pg is per-unit on baseMVA; bus loads
    (`buses[:, 2]`) and Pmin/Pmax (`gens[:, 9]` / `gens[:, 8]`) are MW.
    Reserve quantities are in MW throughout.
    """
    gens = np.asarray(gens, dtype=float)
    gencost = np.asarray(gencost, dtype=float)
    buses = np.asarray(buses, dtype=float)
    baseMVA = float(baseMVA)
    n_gen = gens.shape[0]
    n_bus = buses.shape[0]

    Pg = cp.Variable(n_gen, name="Pg_pu")
    cost = _build_cost(Pg, gencost, baseMVA)
    constraints: list[cp.Constraint] = []

    for i in range(n_gen):
        pmin_pu = float(gens[i, PMIN_COL]) / baseMVA
        pmax_pu = float(gens[i, PMAX_COL]) / baseMVA
        constraints.append(Pg[i] >= pmin_pu)
        constraints.append(Pg[i] <= pmax_pu)

    total_load_MW = float(np.sum(buses[:, BUS_PD_COL]))
    total_load_pu = total_load_MW / baseMVA
    constraints.append(cp.sum(Pg) == total_load_pu)

    include_reserves = (
        reserve_capacity is not None and reserve_requirement is not None
    )
    Rg = None
    if include_reserves:
        reserve_capacity = np.asarray(reserve_capacity, dtype=float).reshape(-1)
        if reserve_capacity.shape[0] != n_gen:
            raise ValueError(
                f"reserve_capacity length {reserve_capacity.shape[0]} != n_gen {n_gen}"
            )
        Rg = cp.Variable(n_gen, name="Rg_MW")
        constraints.append(Rg >= 0)
        for i in range(n_gen):
            pmax_MW = float(gens[i, PMAX_COL])
            constraints.append(Rg[i] <= float(reserve_capacity[i]))
            constraints.append(Pg[i] * baseMVA + Rg[i] <= pmax_MW)
        constraints.append(cp.sum(Rg) >= float(reserve_requirement))

    prob = cp.Problem(cp.Minimize(cost), constraints)
    prob.solve(solver=getattr(cp, solver))

    if prob.status not in ("optimal", "optimal_inaccurate"):
        raise RuntimeError(
            f"Economic dispatch did not solve: status={prob.status}"
        )

    Pg_MW = np.asarray(Pg.value, dtype=float) * baseMVA
    if include_reserves:
        Rg_MW = np.asarray(Rg.value, dtype=float)
    else:
        Rg_MW = np.zeros(n_gen, dtype=float)

    generator_dispatch = []
    for i in range(n_gen):
        generator_dispatch.append(
            {
                "id": i + 1,
                "bus": int(gens[i, GEN_BUS_COL]),
                "output_MW": round(float(Pg_MW[i]), 2),
                "reserve_MW": round(float(Rg_MW[i]), 2),
                "pmax_MW": round(float(gens[i, PMAX_COL]), 2),
            }
        )

    total_gen_MW = float(np.sum(Pg_MW))
    total_reserve_MW = float(np.sum(Rg_MW))
    operating_margin_MW = float(
        np.sum(gens[:, PMAX_COL] - Pg_MW - Rg_MW)
    )

    totals = {
        "cost_dollars_per_hour": round(float(prob.value), 2),
        "load_MW": round(total_load_MW, 2),
        "generation_MW": round(total_gen_MW, 2),
        "reserve_MW": round(total_reserve_MW, 2),
        "operating_margin_MW": round(operating_margin_MW, 2),
    }

    return {
        "generator_dispatch": generator_dispatch,
        "totals": totals,
        "solver_status": prob.status,
        "reserves_enabled": include_reserves,
    }


def marginal_cost(gencost_row: np.ndarray, P_MW: float) -> float:
    """Marginal cost ($/MWh) at output P_MW for a polynomial MATPOWER row."""
    ncost = int(gencost_row[NCOST_COL])
    if ncost >= 3:
        c2 = float(gencost_row[COEFF_START_COL])
        c1 = float(gencost_row[COEFF_START_COL + 1])
        return 2.0 * c2 * P_MW + c1
    if ncost == 2:
        return float(gencost_row[COEFF_START_COL])
    return 0.0
