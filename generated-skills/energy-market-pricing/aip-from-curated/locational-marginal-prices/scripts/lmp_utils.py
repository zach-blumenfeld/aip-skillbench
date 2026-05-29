"""Locational marginal price (LMP) and counterfactual-impact utilities.

All functions operate on the artifacts of a solved CVXPY DC-OPF + reserve
co-optimization:

  - balance_constraints  : list[cp.Constraint], one per bus, in the SAME order
                           as `bus_numbers` (typically the row order of the
                           network's `bus` array).
  - bus_numbers          : list[int], the MATPOWER bus numbers (column 0 of
                           the `bus` array) corresponding to each balance
                           constraint.
  - reserve_con          : cp.Constraint, the system-wide reserve requirement
                           constraint (cp.sum(Rg) >= reserve_requirement).
  - branches             : numpy array, the MATPOWER branch table.
  - theta_values         : numpy array, the solved bus-angle values
                           (i.e. `theta.value` after `prob.solve()`).
  - baseMVA              : float, the per-unit base from the network file.
  - bus_num_to_idx       : dict[int, int], bus-number -> 0-indexed row.

These helpers are deliberately small and side-effect-free. They are designed
to be called AFTER `prob.solve()` has populated `.value` / `.dual_value`
attributes; calling them on an unsolved problem returns zeros (we coerce
`None` -> 0.0 rather than raise, so the caller's report assembly never
crashes mid-stream).
"""
from __future__ import annotations

from typing import Any

import numpy as np


BINDING_THRESHOLD_PCT = 99.0  # Loading percentage at/above which a line is "binding".


def extract_lmps(
    balance_constraints: list,
    bus_numbers: list[int],
    baseMVA: float,
) -> list[dict[str, Any]]:
    """Per-bus LMPs in $/MWh, in the report.json shape.

    LMP at bus i = dual_value of the bus-i power-balance equality
    constraint, scaled by baseMVA because the constraint was written in
    per-unit. Sign is preserved (negative LMPs are physically valid in
    congested networks — see references/pricing-concepts.md).

    Returns one dict per bus: {"bus": int, "lmp_dollars_per_MWh": float}.
    Values are rounded to 2 decimals to match the task's report schema.
    """
    if len(balance_constraints) != len(bus_numbers):
        raise ValueError(
            f"balance_constraints ({len(balance_constraints)}) and bus_numbers "
            f"({len(bus_numbers)}) must be the same length and in the same order."
        )

    out = []
    for con, bus_num in zip(balance_constraints, bus_numbers):
        dual_val = con.dual_value
        lmp = float(dual_val) * baseMVA if dual_val is not None else 0.0
        out.append({
            "bus": int(bus_num),
            "lmp_dollars_per_MWh": round(lmp, 2),
        })
    return out


def extract_reserve_mcp(reserve_con) -> float:
    """System-wide reserve clearing price in $/MWh.

    Dual of `cp.sum(Rg) >= reserve_requirement`. Both `Rg` and
    `reserve_requirement` are conventionally in MW (not per-unit), so no
    baseMVA scaling is needed — return the raw dual.
    """
    dual_val = reserve_con.dual_value if reserve_con is not None else None
    return round(float(dual_val), 2) if dual_val is not None else 0.0


def find_binding_lines(
    branches: np.ndarray,
    theta_values: np.ndarray,
    baseMVA: float,
    bus_num_to_idx: dict[int, int],
    threshold_pct: float = BINDING_THRESHOLD_PCT,
) -> list[dict[str, Any]]:
    """Lines loaded at >= threshold_pct of their thermal rating.

    Computes DC line flow from solved bus angles:
        flow_MW = (1/x) * (theta[f] - theta[t]) * baseMVA
    Skips branches with x == 0, rateA == 0, or status == 0 (out of service).

    Returns one dict per binding line, in the report.json shape:
        {"from": int, "to": int, "flow_MW": float, "limit_MW": float}
    """
    binding = []
    n_branch = branches.shape[0]
    for k in range(n_branch):
        br = branches[k]
        # Skip out-of-service lines if a status column is present (col 10).
        if br.shape[0] > 10 and int(br[10]) == 0:
            continue

        from_bus = int(br[0])
        to_bus = int(br[1])
        f = bus_num_to_idx[from_bus]
        t = bus_num_to_idx[to_bus]
        x = float(br[3])
        rate = float(br[5])

        if x == 0 or rate <= 0:
            continue

        b = 1.0 / x
        flow_MW = b * (float(theta_values[f]) - float(theta_values[t])) * baseMVA
        loading_pct = abs(flow_MW) / rate * 100.0

        if loading_pct >= threshold_pct:
            binding.append({
                "from": from_bus,
                "to": to_bus,
                "flow_MW": round(float(flow_MW), 2),
                "limit_MW": round(float(rate), 2),
            })
    return binding


def perturb_line_limit(
    branches: np.ndarray,
    target_from: int,
    target_to: int,
    factor: float,
) -> tuple[np.ndarray, int]:
    """Return a copy of `branches` with the target line's rateA scaled by `factor`.

    Matches the target line in EITHER orientation (from->to OR to->from).
    Raises ValueError if no matching branch is found, so a typo in the
    target bus numbers cannot silently no-op the counterfactual.

    Returns (new_branches, row_index_modified). The caller passes
    `new_branches` to the next DC-OPF build; the original array is left
    untouched so the base case can be reused or re-solved later.
    """
    new = branches.copy()
    for k in range(new.shape[0]):
        f = int(new[k, 0])
        t = int(new[k, 1])
        if (f == target_from and t == target_to) or (f == target_to and t == target_from):
            new[k, 5] = float(new[k, 5]) * float(factor)
            return new, k
    raise ValueError(
        f"No branch found between bus {target_from} and bus {target_to} "
        f"(checked both orientations)."
    )


def _is_line_binding(
    binding_lines: list[dict[str, Any]],
    target_from: int,
    target_to: int,
) -> bool:
    """True iff a binding-line entry matches (target_from, target_to) in either orientation."""
    for line in binding_lines:
        f, t = int(line["from"]), int(line["to"])
        if (f == target_from and t == target_to) or (f == target_to and t == target_from):
            return True
    return False


def compute_impact_analysis(
    base_case: dict[str, Any],
    counterfactual: dict[str, Any],
    target_from: int,
    target_to: int,
    top_n_lmp_drops: int = 3,
) -> dict[str, Any]:
    """Build the report.json `impact_analysis` block.

    base_case / counterfactual must each carry:
        - total_cost_dollars_per_hour : float
        - lmp_by_bus                  : list of {bus, lmp_dollars_per_MWh}
        - binding_lines               : list of {from, to, flow_MW, limit_MW}

    Returns:
        {
          "cost_reduction_dollars_per_hour": float,   # base - cf (>= 0 expected)
          "buses_with_largest_lmp_drop": [             # top_n by most-negative delta
              {"bus": int, "base_lmp": float, "cf_lmp": float, "delta": float},
              ...
          ],
          "congestion_relieved": bool                  # binding in base, not in cf
        }

    "Largest drop" means the most-negative `delta = cf - base`, NOT the
    largest absolute change. Ties are broken by bus number ascending so the
    output is deterministic across re-runs.
    """
    cost_reduction = round(
        float(base_case["total_cost_dollars_per_hour"])
        - float(counterfactual["total_cost_dollars_per_hour"]),
        2,
    )

    base_lmp_map = {int(row["bus"]): float(row["lmp_dollars_per_MWh"]) for row in base_case["lmp_by_bus"]}
    cf_lmp_map = {int(row["bus"]): float(row["lmp_dollars_per_MWh"]) for row in counterfactual["lmp_by_bus"]}

    deltas = []
    for bus_num, base_lmp in base_lmp_map.items():
        if bus_num not in cf_lmp_map:
            continue
        cf_lmp = cf_lmp_map[bus_num]
        deltas.append({
            "bus": bus_num,
            "base_lmp": round(base_lmp, 2),
            "cf_lmp": round(cf_lmp, 2),
            "delta": round(cf_lmp - base_lmp, 2),
        })

    # Most-negative delta = largest price drop.
    deltas.sort(key=lambda r: (r["delta"], r["bus"]))
    top_drops = deltas[:top_n_lmp_drops]

    was_binding_in_base = _is_line_binding(base_case["binding_lines"], target_from, target_to)
    is_binding_in_cf = _is_line_binding(counterfactual["binding_lines"], target_from, target_to)
    congestion_relieved = bool(was_binding_in_base and not is_binding_in_cf)

    return {
        "cost_reduction_dollars_per_hour": cost_reduction,
        "buses_with_largest_lmp_drop": top_drops,
        "congestion_relieved": congestion_relieved,
    }
