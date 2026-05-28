"""Economic dispatch building blocks for MATPOWER-format networks.

Helpers compose into a CVXPY problem. The agent imports the functions it needs
and assembles them — this module does not enforce a fixed top-level solve flow,
because the network constraints (DC-OPF nodal balance, branch limits) come from
a sibling skill (`dc-power-flow`) and must be mixed in by the agent.

All functions assume MATPOWER conventions:
  * gens, gencost, buses are numpy arrays
  * power values in arrays are in MW
  * CVXPY decision variables Pg are in per-unit (Pg_MW = Pg * baseMVA)
  * Reserve variable Rg is in MW directly

See `references/matpower-arrays.md` for column indices and the bus-numbering rule.
"""

from __future__ import annotations

from typing import Optional

import cvxpy as cp
import numpy as np


# --- indexing --------------------------------------------------------------

def build_bus_index(buses: np.ndarray) -> dict[int, int]:
    """Map MATPOWER bus number (column 0) to numpy row index.

    Bus numbers may be non-contiguous; never use the bus number directly as an
    array index.
    """
    n_bus = buses.shape[0]
    return {int(buses[i, 0]): i for i in range(n_bus)}


def gen_bus_rows(gens: np.ndarray, bus_num_to_idx: dict[int, int]) -> list[int]:
    """Row index in `buses` for each generator (preserves generator order)."""
    return [bus_num_to_idx[int(g[0])] for g in gens]


# --- cost objective --------------------------------------------------------

def build_cost_objective(
    gencost: np.ndarray,
    Pg: cp.Variable,
    baseMVA: float,
) -> cp.Expression:
    """Build CVXPY cost expression $/hr, handling variable NCOST.

    Supports polynomial type 2 with NCOST in {1, 2, 3}:
      * NCOST=3 quadratic: c2·P^2 + c1·P + c0
      * NCOST=2 linear:    c1·P + c0
      * NCOST=1 constant:  c0
    P is in MW. Caller passes Pg as per-unit decision variable; this function
    multiplies by baseMVA internally.
    """
    n_gen = gencost.shape[0]
    cost: cp.Expression = 0
    for i in range(n_gen):
        ncost = int(gencost[i, 3])
        Pg_MW = Pg[i] * baseMVA
        if ncost >= 3:
            c2, c1, c0 = gencost[i, 4], gencost[i, 5], gencost[i, 6]
            cost = cost + c2 * cp.square(Pg_MW) + c1 * Pg_MW + c0
        elif ncost == 2:
            c1, c0 = gencost[i, 4], gencost[i, 5]
            cost = cost + c1 * Pg_MW + c0
        elif ncost == 1:
            c0 = gencost[i, 4]
            cost = cost + c0
        # NCOST=0 contributes nothing.
    return cost


# --- generator limits ------------------------------------------------------

def build_generator_limit_constraints(
    gens: np.ndarray,
    Pg: cp.Variable,
    baseMVA: float,
) -> list:
    """Pmin ≤ Pg ≤ Pmax constraints (per-unit) from the MW values in gens."""
    constraints = []
    n_gen = gens.shape[0]
    for i in range(n_gen):
        pmin = gens[i, 9] / baseMVA
        pmax = gens[i, 8] / baseMVA
        constraints.append(Pg[i] >= pmin)
        constraints.append(Pg[i] <= pmax)
    return constraints


# --- power balance ---------------------------------------------------------

def build_simple_power_balance(
    buses: np.ndarray,
    Pg: cp.Variable,
    baseMVA: float,
) -> list:
    """Single-bus / aggregate balance: cp.sum(Pg) == total_load_pu.

    Use only when transmission topology is out of scope. For DC-OPF with
    network, replace this with the nodal balance from `dc-power-flow`.
    """
    total_load_pu = float(sum(buses[i, 2] for i in range(buses.shape[0]))) / baseMVA
    return [cp.sum(Pg) == total_load_pu]


# --- reserves --------------------------------------------------------------

def build_reserve_constraints(
    gens: np.ndarray,
    reserve_capacity: np.ndarray,
    reserve_requirement: float,
    Pg: cp.Variable,
    Rg: cp.Variable,
    baseMVA: float,
) -> list:
    """Spinning-reserve constraints with standard capacity coupling.

    Rg is in MW (not per-unit). Constraints added:
      * Rg >= 0
      * Rg[i] <= reserve_capacity[i]                     (per-generator cap)
      * Pg_MW[i] + Rg[i] <= Pmax[i]                      (capacity coupling)
      * sum(Rg) >= reserve_requirement                   (system requirement)
    """
    constraints = [Rg >= 0]
    n_gen = gens.shape[0]
    for i in range(n_gen):
        constraints.append(Rg[i] <= float(reserve_capacity[i]))
        pmax_MW = float(gens[i, 8])
        Pg_MW = Pg[i] * baseMVA
        constraints.append(Pg_MW + Rg[i] <= pmax_MW)
    constraints.append(cp.sum(Rg) >= float(reserve_requirement))
    return constraints


# --- solve -----------------------------------------------------------------

def solve_problem(cost: cp.Expression, constraints: list, *, solver: str = "CLARABEL"):
    """Build cp.Problem and solve. Returns the problem instance.

    CLARABEL is robust on DC-OPF + reserves. If status is not optimal,
    callers can retry with cp.ECOS per `references/solver-selection.md`.
    """
    prob = cp.Problem(cp.Minimize(cost), constraints)
    prob.solve(solver=getattr(cp, solver))
    return prob


# --- formatting ------------------------------------------------------------

def format_generator_dispatch(
    Pg_value: np.ndarray,
    Rg_value: Optional[np.ndarray],
    gens: np.ndarray,
    baseMVA: float,
) -> list[dict]:
    """Build the `generator_dispatch` list of dicts per the task report schema.

    Pg_value is per-unit (CVXPY .value). Rg_value is MW or None when reserves
    were not co-optimized — in that case reserve_MW is reported as 0.0.
    """
    n_gen = gens.shape[0]
    Pg_MW = np.asarray(Pg_value) * baseMVA
    if Rg_value is None:
        Rg_MW = np.zeros(n_gen)
    else:
        Rg_MW = np.asarray(Rg_value)
    out = []
    for i in range(n_gen):
        out.append({
            "id": i + 1,
            "bus": int(gens[i, 0]),
            "output_MW": round(float(Pg_MW[i]), 2),
            "reserve_MW": round(float(Rg_MW[i]), 2),
            "pmax_MW": round(float(gens[i, 8]), 2),
        })
    return out


def compute_totals(
    Pg_value: np.ndarray,
    Rg_value: Optional[np.ndarray],
    buses: np.ndarray,
    baseMVA: float,
    prob_value: float,
) -> dict:
    """Build the `totals` block (cost / load / generation / reserves) in MW and $/hr."""
    Pg_MW = np.asarray(Pg_value) * baseMVA
    total_gen_MW = float(np.sum(Pg_MW))
    total_load_MW = float(sum(buses[i, 2] for i in range(buses.shape[0])))
    if Rg_value is None:
        total_reserve_MW = 0.0
    else:
        total_reserve_MW = float(np.sum(np.asarray(Rg_value)))
    return {
        "cost_dollars_per_hour": round(float(prob_value), 2),
        "load_MW": round(total_load_MW, 2),
        "generation_MW": round(total_gen_MW, 2),
        "reserve_MW": round(total_reserve_MW, 2),
    }


def compute_operating_margin(
    Pg_value: np.ndarray,
    Rg_value: Optional[np.ndarray],
    gens: np.ndarray,
    baseMVA: float,
) -> float:
    """Uncommitted headroom: sum(Pmax_i - Pg_i - Rg_i) in MW.

    Capacity above what is scheduled for energy and reserves. Pg_value is
    per-unit; converted to MW internally.
    """
    n_gen = gens.shape[0]
    Pg_MW = np.asarray(Pg_value) * baseMVA
    if Rg_value is None:
        Rg_MW = np.zeros(n_gen)
    else:
        Rg_MW = np.asarray(Rg_value)
    margin = sum(float(gens[i, 8]) - float(Pg_MW[i]) - float(Rg_MW[i]) for i in range(n_gen))
    return round(float(margin), 2)
