"""Economic dispatch helpers for MATPOWER-format networks.

Import these into a cvxpy problem alongside dc-power-flow's network constraints.
All functions assume `gens` and `gencost` are 2-D numpy arrays in MATPOWER layout
and `Pg_var` is a cvxpy Variable in per-unit (not MW).

Exports:
- build_cost(Pg_var, gencost, baseMVA) -> cvxpy expression in $/hr
- build_gen_limits(Pg_var, gens, baseMVA) -> list[Constraint]
- build_reserves(Pg_var, Rg_var, gens, baseMVA, reserve_capacity, reserve_requirement)
        -> list[Constraint]
- build_dispatch_report(Pg_value, Rg_value, gens, buses, baseMVA, total_cost)
        -> dict with generator_dispatch, totals, operating_margin_MW
"""

from __future__ import annotations

import cvxpy as cp
import numpy as np


# MATPOWER column indices (0-based) used here.
GEN_BUS = 0
GEN_PMAX = 8
GEN_PMIN = 9

GENCOST_NCOST = 3
GENCOST_COEFFS_START = 4


def build_cost(Pg_var, gencost, baseMVA):
    """Total generation cost ($/hr) over all generators.

    Handles polynomial cost (MODEL=2) with variable NCOST per generator:
      NCOST=3 -> quadratic c2*P^2 + c1*P + c0
      NCOST=2 -> linear    c1*P + c0
      NCOST=1 -> constant  c0
    Pg_var is per-unit; the cost is evaluated in MW (Pg_MW = Pg_var * baseMVA).
    """
    gencost = np.asarray(gencost)
    n_gen = gencost.shape[0]
    cost = 0
    for i in range(n_gen):
        ncost = int(gencost[i, GENCOST_NCOST])
        Pg_MW = Pg_var[i] * baseMVA
        if ncost >= 3:
            c2 = gencost[i, GENCOST_COEFFS_START]
            c1 = gencost[i, GENCOST_COEFFS_START + 1]
            c0 = gencost[i, GENCOST_COEFFS_START + 2]
            cost = cost + c2 * cp.square(Pg_MW) + c1 * Pg_MW + c0
        elif ncost == 2:
            c1 = gencost[i, GENCOST_COEFFS_START]
            c0 = gencost[i, GENCOST_COEFFS_START + 1]
            cost = cost + c1 * Pg_MW + c0
        elif ncost == 1:
            cost = cost + gencost[i, GENCOST_COEFFS_START]
    return cost


def build_gen_limits(Pg_var, gens, baseMVA):
    """Pmin <= Pg <= Pmax (in per-unit) for each generator."""
    gens = np.asarray(gens)
    constraints = []
    for i in range(gens.shape[0]):
        pmin_pu = gens[i, GEN_PMIN] / baseMVA
        pmax_pu = gens[i, GEN_PMAX] / baseMVA
        constraints.append(Pg_var[i] >= pmin_pu)
        constraints.append(Pg_var[i] <= pmax_pu)
    return constraints


def build_reserves(Pg_var, Rg_var, gens, baseMVA, reserve_capacity, reserve_requirement):
    """Reserve co-optimization constraints (MISO-style):

      Rg >= 0
      Rg[i] <= reserve_capacity[i]                  (per-gen reserve cap, MW)
      Pg_MW[i] + Rg[i] <= Pmax[i]                   (capacity coupling)
      sum(Rg) >= reserve_requirement                 (system reserve floor)
    """
    gens = np.asarray(gens)
    reserve_capacity = np.asarray(reserve_capacity)
    constraints = [Rg_var >= 0]
    for i in range(gens.shape[0]):
        constraints.append(Rg_var[i] <= float(reserve_capacity[i]))
        pmax_MW = float(gens[i, GEN_PMAX])
        Pg_MW = Pg_var[i] * baseMVA
        constraints.append(Pg_MW + Rg_var[i] <= pmax_MW)
    constraints.append(cp.sum(Rg_var) >= float(reserve_requirement))
    return constraints


def build_dispatch_report(Pg_value, Rg_value, gens, buses, baseMVA, total_cost):
    """Assemble the dispatch sub-report.

    Returns a dict with keys: generator_dispatch, totals, operating_margin_MW.
    The caller is expected to add `most_loaded_lines` (computed by dc-power-flow)
    before writing report.json.

    Pg_value is per-unit (the cvxpy variable's .value); Rg_value is already in MW.
    Pass Rg_value=None when no reserves were modelled — reserves report as 0.
    """
    gens = np.asarray(gens)
    buses = np.asarray(buses)
    n_gen = gens.shape[0]

    Pg_MW = np.asarray(Pg_value, dtype=float) * baseMVA
    if Rg_value is None:
        Rg_MW = np.zeros(n_gen, dtype=float)
    else:
        Rg_MW = np.asarray(Rg_value, dtype=float)

    generator_dispatch = []
    for i in range(n_gen):
        generator_dispatch.append({
            "id": i + 1,
            "bus": int(gens[i, GEN_BUS]),
            "output_MW": round(float(Pg_MW[i]), 2),
            "reserve_MW": round(float(Rg_MW[i]), 2),
            "pmax_MW": round(float(gens[i, GEN_PMAX]), 2),
        })

    total_gen_MW = float(np.sum(Pg_MW))
    total_load_MW = float(np.sum(buses[:, 2]))
    total_reserve_MW = float(np.sum(Rg_MW))

    totals = {
        "cost_dollars_per_hour": round(float(total_cost), 2),
        "load_MW": round(total_load_MW, 2),
        "generation_MW": round(total_gen_MW, 2),
        "reserve_MW": round(total_reserve_MW, 2),
    }

    operating_margin_MW = float(
        sum(gens[i, GEN_PMAX] - Pg_MW[i] - Rg_MW[i] for i in range(n_gen))
    )

    return {
        "generator_dispatch": generator_dispatch,
        "totals": totals,
        "operating_margin_MW": round(operating_margin_MW, 2),
    }
