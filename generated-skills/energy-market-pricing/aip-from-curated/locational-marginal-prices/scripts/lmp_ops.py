"""Helpers for extracting locational marginal prices, reserve clearing prices,
and binding transmission lines from a solved DC-OPF (with reserve
co-optimization) — plus the small numeric routines that the counterfactual
("what if we relax this line?") workflow depends on.

Design notes
------------
The skill is consumed inside the agent's own CVXPY problem construction. These
helpers take the *already-solved* CVXPY objects (constraints, variables) by
reference, read their `dual_value` / `value` attributes, and return plain
Python data shaped for the report.json the task asks for.

Key contract — to extract LMPs at all the agent must:
    1. Build each per-bus power-balance constraint AS A NAMED OBJECT.
    2. Append it to the problem `constraints` list AND keep a parallel list of
       those constraint objects (this module's `extract_lmps` consumes that
       parallel list).
    3. Solve.
    4. Call `extract_lmps(balance_constraints, bus_nums, baseMVA)`.

Without step (2) there is no handle to read the dual values from after solve —
this is the single most common mistake.

Sign convention
---------------
The balance constraint is written as `generation - load == net_export` (per
unit). Positive dual means "increasing load here increases system cost"
(normal). Negative duals are physically valid in congested systems and must NOT
be clipped or filtered — see `extract_lmps` docstring.

Per-unit scaling
----------------
Power-balance constraints are written in per-unit (divide by baseMVA). The dual
of a per-unit constraint is in $/per-unit-MW. Multiplying by baseMVA converts
to $/MWh. This module owns that scaling so individual skill steps don't repeat
it (and don't forget it).
"""

from __future__ import annotations

from typing import Any, Iterable

DEFAULT_BINDING_THRESHOLD_PCT = 99.0


def extract_lmps(
    balance_constraints: list[Any],
    bus_nums: list[int],
    baseMVA: float,
) -> list[dict]:
    """Read LMPs from the duals of the stored per-bus balance constraints.

    `balance_constraints[i]` MUST be the CVXPY constraint object representing
    `generation_at_bus_i - load_at_bus_i == net_export_i` (in per-unit) that
    was passed into the problem before solve.

    `bus_nums[i]` is the integer bus number (from the MATPOWER bus matrix,
    column 0) corresponding to row `i`.

    Returns: `[{"bus": int, "lmp_dollars_per_MWh": float}, ...]`, in the order
    of `bus_nums`. Negative LMPs are preserved as-is (see module docstring on
    sign convention).
    """
    if len(balance_constraints) != len(bus_nums):
        raise ValueError(
            f"balance_constraints ({len(balance_constraints)}) and bus_nums "
            f"({len(bus_nums)}) must have the same length and order."
        )
    out: list[dict] = []
    for con, bus_num in zip(balance_constraints, bus_nums):
        dual_val = getattr(con, "dual_value", None)
        if dual_val is None:
            lmp = 0.0
        else:
            # Per-unit dual → $/MWh by multiplying by baseMVA.
            lmp = float(dual_val) * float(baseMVA)
        out.append({
            "bus": int(bus_num),
            "lmp_dollars_per_MWh": round(lmp, 2),
        })
    return out


def extract_reserve_mcp(reserve_con: Any) -> float:
    """Read the system reserve market-clearing price from the dual of the
    reserve-requirement constraint.

    The reserve constraint must be written as `sum(Rg) >= reserve_requirement`
    (typically in MW directly, not per-unit — most market-clearing examples
    leave the reserve requirement and `Rg` in MW). Its dual is in $/MWh of
    reserve capacity already.

    Returns 0.0 if the dual is missing (problem unsolved or constraint not
    binding in some solver outputs).
    """
    dual_val = getattr(reserve_con, "dual_value", None)
    if dual_val is None:
        return 0.0
    return round(float(dual_val), 4)


def find_binding_lines(
    branches: Any,
    theta_value: Any,
    bus_num_to_idx: dict[int, int],
    baseMVA: float,
    threshold_pct: float = DEFAULT_BINDING_THRESHOLD_PCT,
) -> list[dict]:
    """Identify transmission lines at or near their thermal limit.

    Parameters
    ----------
    branches
        MATPOWER `branch` matrix-like (NumPy array or list of lists). Columns
        used: 0=from-bus number, 1=to-bus number, 3=reactance x (per-unit),
        5=rate_a thermal limit (MW).
    theta_value
        Array-like of bus voltage angles (radians) in the *internal* row
        ordering used during the optimization (i.e., `theta_value[bus_num_to_idx[bus]]`
        gives the angle for that bus).
    bus_num_to_idx
        Map from external bus number → internal row index.
    baseMVA
        System base MVA. Per-unit flow `b * Δθ` is scaled to MW by `* baseMVA`.
    threshold_pct
        Loading percentage at or above which a line is considered binding.
        Defaults to 99.0 — the SkillsBench task definition's threshold.

    Returns
    -------
    list[dict]
        `[{"from": int, "to": int, "flow_MW": float, "limit_MW": float}, ...]`.
        Flow is signed: positive if power flows from→to, negative if reversed.
        Limit is the (post-modification) `rate_a` value. Skips branches with
        `x == 0` (model artifacts) or `rate_a <= 0` (unlimited / undefined).
    """
    binding: list[dict] = []
    for k in range(len(branches)):
        br = branches[k]
        from_bus = int(br[0])
        to_bus = int(br[1])
        x = float(br[3])
        rate = float(br[5])
        if x == 0.0 or rate <= 0.0:
            continue
        f = bus_num_to_idx[from_bus]
        t = bus_num_to_idx[to_bus]
        b = 1.0 / x
        flow_pu = b * (float(theta_value[f]) - float(theta_value[t]))
        flow_MW = flow_pu * float(baseMVA)
        loading_pct = abs(flow_MW) / rate * 100.0
        if loading_pct >= threshold_pct:
            binding.append({
                "from": from_bus,
                "to": to_bus,
                "flow_MW": round(flow_MW, 2),
                "limit_MW": round(rate, 2),
            })
    return binding


def modify_line_limit(
    branches: Any,
    target_from: int,
    target_to: int,
    scale_factor: float,
) -> int:
    """Multiply the thermal limit (column 5, `rate_a`) of the line connecting
    `target_from` and `target_to` by `scale_factor`. Matches in either
    direction (`from→to` or `to→from`) — MATPOWER branches are directed in the
    matrix but the underlying conductor is bidirectional.

    Mutates `branches` IN PLACE. Returns the row index of the modified branch
    so the caller can record what changed; raises `LookupError` if no matching
    branch was found.
    """
    for k in range(len(branches)):
        br = branches[k]
        br_from = int(br[0])
        br_to = int(br[1])
        if (br_from == target_from and br_to == target_to) or (
            br_from == target_to and br_to == target_from
        ):
            branches[k][5] = float(branches[k][5]) * float(scale_factor)
            return k
    raise LookupError(
        f"No branch found connecting buses {target_from} <-> {target_to}."
    )


def _is_target_line(line: dict, target_from: int, target_to: int) -> bool:
    f, t = int(line["from"]), int(line["to"])
    return (f == target_from and t == target_to) or (
        f == target_to and t == target_from
    )


def compute_impact(
    base_cost: float,
    cf_cost: float,
    base_lmp_by_bus: list[dict],
    cf_lmp_by_bus: list[dict],
    base_binding_lines: list[dict],
    cf_binding_lines: list[dict],
    target_from: int,
    target_to: int,
    top_n: int = 3,
) -> dict:
    """Build the `impact_analysis` block of the report.

    - `cost_reduction_dollars_per_hour` = base_cost - cf_cost.
      Relaxing a binding constraint *cannot* increase cost, so this should be
      >= 0 in expectation. A small negative value (<= ~1e-3) is treated as
      solver noise and clamped to 0; a meaningfully negative value is left
      visible so the caller can investigate (e.g., misnamed line, wrong
      scale factor).
    - `buses_with_largest_lmp_drop` is the `top_n` buses with the most
      *negative* delta (cf - base). Ties broken by bus number ascending so
      output is deterministic.
    - `congestion_relieved` is True iff the *target* line was binding in the
      base case and not binding in the counterfactual.

    Parameters
    ----------
    base_lmp_by_bus / cf_lmp_by_bus
        Lists of `{"bus": int, "lmp_dollars_per_MWh": float}` as produced by
        `extract_lmps`. Bus orderings between the two lists do not need to
        match — they are matched by bus number.
    base_binding_lines / cf_binding_lines
        Lists as produced by `find_binding_lines`.
    target_from / target_to
        The pair of bus numbers identifying the line whose limit was changed.
    top_n
        Default 3, matching the task's report schema. Pass a different value
        only if a different report format is needed.
    """
    cost_reduction = float(base_cost) - float(cf_cost)
    if -1e-3 < cost_reduction < 0.0:
        cost_reduction = 0.0

    base_map = {int(r["bus"]): float(r["lmp_dollars_per_MWh"])
                for r in base_lmp_by_bus}
    cf_map = {int(r["bus"]): float(r["lmp_dollars_per_MWh"])
              for r in cf_lmp_by_bus}
    common_buses = sorted(set(base_map) & set(cf_map))
    deltas = [
        {
            "bus": bus,
            "base_lmp": round(base_map[bus], 2),
            "cf_lmp": round(cf_map[bus], 2),
            "delta": round(cf_map[bus] - base_map[bus], 2),
        }
        for bus in common_buses
    ]
    # Most negative delta first; tie-break by bus number ascending.
    deltas.sort(key=lambda r: (r["delta"], r["bus"]))
    top = deltas[: int(top_n)]

    was_binding_in_base = any(
        _is_target_line(line, target_from, target_to)
        for line in base_binding_lines
    )
    is_binding_in_cf = any(
        _is_target_line(line, target_from, target_to)
        for line in cf_binding_lines
    )
    congestion_relieved = bool(was_binding_in_base and not is_binding_in_cf)

    return {
        "cost_reduction_dollars_per_hour": round(cost_reduction, 2),
        "buses_with_largest_lmp_drop": top,
        "congestion_relieved": congestion_relieved,
    }


def assemble_report(
    base_case: dict,
    counterfactual: dict,
    impact_analysis: dict,
) -> dict:
    """Pack the three blocks into the final report shape expected by the
    `energy-market-pricing` task. Trivial but kept here so the field-name
    contract lives in one place.
    """
    return {
        "base_case": base_case,
        "counterfactual": counterfactual,
        "impact_analysis": impact_analysis,
    }


__all__ = [
    "DEFAULT_BINDING_THRESHOLD_PCT",
    "extract_lmps",
    "extract_reserve_mcp",
    "find_binding_lines",
    "modify_line_limit",
    "compute_impact",
    "assemble_report",
]
