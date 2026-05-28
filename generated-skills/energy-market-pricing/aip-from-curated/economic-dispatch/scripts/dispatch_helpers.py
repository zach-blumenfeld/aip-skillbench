"""Composable building blocks for generator economic dispatch.

Encapsulates the MATPOWER cost-function branching, generator limits,
system power balance, spinning-reserve co-optimization with standard
capacity coupling, operating-margin computation, and result formatting.

Designed to wire into a larger DC-OPF (compose with the dc-power-flow
skill for line flows and nodal balance). Treat this module as a library
imported from the agent's main solve script — every function returns
values, none has side effects on globals.
"""

import json

import cvxpy as cp
import numpy as np


def load_matpower(network_path):
    """Load a MATPOWER-format network.json.

    Returns a dict bundling the raw arrays plus the bus-number → index
    mapping that handles non-contiguous bus numbers, which MATPOWER
    permits and most failure modes here stem from forgetting.
    """
    with open(network_path) as f:
        data = json.load(f)
    buses = np.array(data["bus"], dtype=float)
    gens = np.array(data["gen"], dtype=float)
    gencost = np.array(data["gencost"], dtype=float)
    baseMVA = float(data["baseMVA"])
    n_bus = buses.shape[0]
    n_gen = gens.shape[0]
    bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
    gen_bus_idx = [bus_num_to_idx[int(g[0])] for g in gens]
    return {
        "data": data,
        "buses": buses,
        "gens": gens,
        "gencost": gencost,
        "baseMVA": baseMVA,
        "n_bus": n_bus,
        "n_gen": n_gen,
        "bus_num_to_idx": bus_num_to_idx,
        "gen_bus_idx": gen_bus_idx,
    }


def build_cost(Pg, gencost, baseMVA, n_gen):
    """Build the cvxpy cost expression from a MATPOWER gencost array.

    Branches on NCOST (gencost[i, 3]) — required because MATPOWER allows
    mixed polynomial orders across generators within the same case.

    - NCOST >= 3: quadratic, coeffs at indices [4, 5, 6] = [c2, c1, c0]
    - NCOST == 2: linear,   coeffs at indices [4, 5]   = [c1, c0]
    - NCOST == 1: constant, value at index [4]         = c0
    """
    cost = 0
    for i in range(n_gen):
        ncost = int(gencost[i, 3])
        Pg_MW = Pg[i] * baseMVA
        if ncost >= 3:
            c2 = gencost[i, 4]
            c1 = gencost[i, 5]
            c0 = gencost[i, 6]
            cost = cost + c2 * cp.square(Pg_MW) + c1 * Pg_MW + c0
        elif ncost == 2:
            c1 = gencost[i, 4]
            c0 = gencost[i, 5]
            cost = cost + c1 * Pg_MW + c0
        elif ncost == 1:
            cost = cost + gencost[i, 4]
    return cost


def generator_limit_constraints(Pg, gens, baseMVA, n_gen):
    """Pmin <= Pg <= Pmax, expressed in per-unit on the system base.

    Reads Pmax from gens[:, 8] and Pmin from gens[:, 9] (MATPOWER MW),
    divides by baseMVA to match Pg's per-unit scale.
    """
    constraints = []
    for i in range(n_gen):
        pmin = gens[i, 9] / baseMVA
        pmax = gens[i, 8] / baseMVA
        constraints.append(Pg[i] >= pmin)
        constraints.append(Pg[i] <= pmax)
    return constraints


def system_power_balance(Pg, buses, baseMVA, n_bus):
    """sum(Pg) == total load (per-unit).

    Use only when the problem has no network constraints. For DC-OPF
    with line flows, replace this with the nodal balance from the
    dc-power-flow skill — do NOT add both.
    """
    total_load_pu = sum(buses[i, 2] for i in range(n_bus)) / baseMVA
    return [cp.sum(Pg) == total_load_pu]


def reserve_cooptimization(
    Pg, Rg, gens, reserve_capacity, reserve_requirement, baseMVA, n_gen
):
    """Spinning-reserve constraints with standard capacity coupling.

    Pg is per-unit; Rg is in MW (reserves are conventionally in MW).
    reserve_capacity is a per-generator MW cap; reserve_requirement is
    the system-wide minimum total reserves in MW.

    Adds:
    - Rg[i] >= 0
    - Rg[i] <= reserve_capacity[i]            (per-generator cap)
    - Pg_MW[i] + Rg[i] <= Pmax[i]             (capacity coupling)
    - sum(Rg) >= reserve_requirement          (system requirement)

    The dual of the system requirement is the reserve market clearing
    price (reserve MCP) in $/MWh.
    """
    constraints = [Rg >= 0]
    for i in range(n_gen):
        constraints.append(Rg[i] <= reserve_capacity[i])
        pmax_MW = gens[i, 8]
        Pg_MW = Pg[i] * baseMVA
        constraints.append(Pg_MW + Rg[i] <= pmax_MW)
    system_reserve = cp.sum(Rg) >= reserve_requirement
    constraints.append(system_reserve)
    return constraints, system_reserve


def solve_dispatch(cost, constraints):
    """Build cp.Problem(Minimize(cost), constraints) and solve.

    CLARABEL is the default — a robust interior-point solver that handles
    both linear and quadratic costs and tends to converge on DC-OPF with
    reserves where OSQP frequently fails on ill-conditioned cases.
    """
    prob = cp.Problem(cp.Minimize(cost), constraints)
    prob.solve(solver=cp.CLARABEL)
    return prob


def operating_margin_MW(Pg_value, Rg_value, gens, baseMVA, n_gen):
    """Uncommitted system headroom: sum(Pmax - Pg - Rg) in MW.

    Capacity available beyond scheduled generation AND reserves — not
    the difference between dispatch and any single limit. If reserves
    are not modeled, pass Rg_value = np.zeros(n_gen).
    """
    Pg_MW = np.asarray(Pg_value) * baseMVA
    Rg_arr = np.asarray(Rg_value)
    return float(sum(gens[i, 8] - Pg_MW[i] - Rg_arr[i] for i in range(n_gen)))


def format_dispatch(Pg_value, Rg_value, gens, baseMVA, n_gen):
    """Per-generator dispatch list with output, reserve, Pmax in MW."""
    Pg_MW = np.asarray(Pg_value) * baseMVA
    Rg_arr = np.asarray(Rg_value)
    dispatch = []
    for i in range(n_gen):
        dispatch.append(
            {
                "id": i + 1,
                "bus": int(gens[i, 0]),
                "output_MW": round(float(Pg_MW[i]), 2),
                "reserve_MW": round(float(Rg_arr[i]), 2),
                "pmax_MW": round(float(gens[i, 8]), 2),
            }
        )
    return dispatch


def format_totals(prob_value, Pg_value, Rg_value, buses, baseMVA, n_bus):
    """System-wide totals dict in MW and $/hr, rounded to 2 decimals."""
    Pg_MW = np.asarray(Pg_value) * baseMVA
    Rg_arr = np.asarray(Rg_value)
    total_gen_MW = float(np.sum(Pg_MW))
    total_load_MW = float(sum(buses[i, 2] for i in range(n_bus)))
    total_reserve_MW = float(np.sum(Rg_arr))
    return {
        "cost_dollars_per_hour": round(float(prob_value), 2),
        "load_MW": round(total_load_MW, 2),
        "generation_MW": round(total_gen_MW, 2),
        "reserve_MW": round(total_reserve_MW, 2),
    }
