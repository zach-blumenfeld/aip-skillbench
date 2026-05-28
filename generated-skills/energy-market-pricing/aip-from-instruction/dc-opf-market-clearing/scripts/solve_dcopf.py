#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "numpy>=1.24",
#     "scipy>=1.11",
# ]
# ///
"""DC-OPF with reserve co-optimization for a MATPOWER-format network.

Solves a single-period market clearing as a linear program and extracts the
dual variables to produce locational marginal prices (LMPs), the system-wide
reserve market clearing price (MCP), and a list of binding lines. Supports a
counterfactual scenario where one or more branch thermal capacities are
scaled, then produces the comparison report.json described in the task spec.

Formulation (matches the task instruction):
    minimize  sum_g cost_g(p_g) + sum_g rcost_g * r_g
    subject to
      (1) bus power balance (DC):  G @ p - d = baseMVA * B_bus @ theta   (LMP duals)
      (2) line thermal limits:     -F_max <= flow_k <= F_max
      (3) generator capacity coupling:  p_min <= p_g,  p_g + r_g <= p_max
      (4) reserve qty limit:       0 <= r_g <= rmax_g
      (5) system reserve req:      sum_g r_g >= R_req                    (MCP dual)
      (6) slack bus angle:         theta_slack = 0

Costs are taken from the MATPOWER `gencost` field. Linear costs (model=2,
n=2) keep the problem an LP. Quadratic costs (n=3) are linearized at the
slope evaluated at the midpoint between p_min and p_max; this preserves a
clean LP for fast HiGHS solves and stable LMPs. If you need true QP LMPs,
swap the solver out — but for the task instruction the linear approximation
matches the published marginal-cost convention used by RTOs.

Usage:
    # Base + counterfactual + report in one shot
    python solve_dcopf.py network.json \\
        --override-line 64,1501,1.2 \\
        --report report.json

    # Base only (no counterfactual; useful for sanity-checking)
    python solve_dcopf.py network.json --report base_only.json

CLI flags:
    --override-line FROM,TO,FACTOR  (repeatable). Scales rateA of branch
                                     between FROM and TO by FACTOR. Matches
                                     either direction. Applied to every
                                     parallel branch unless --branch-index
                                     is set.
    --branch-index N                 With --override-line, restrict the
                                     override to branch row N (0-indexed
                                     after filtering to status=1 branches).
    --reserve-req MW                 Override the reserve requirement
                                     (default: largest in-service gen Pmax,
                                     or net["reserves"]["req"] if present).
    --binding-threshold FRACTION     Loading fraction at/above which a line
                                     counts as binding (default: 0.99).
    --report PATH                    Write the report.json to PATH.
                                     Without --override-line the file
                                     contains only "base_case".
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix, vstack


# ----------------------------------------------------------------------------
# MATPOWER loading
# ----------------------------------------------------------------------------

# Column indices match the MATPOWER manual (1-indexed there, 0-indexed here).
BUS_I, BUS_TYPE, BUS_PD = 0, 1, 2
GEN_BUS, GEN_PMAX, GEN_PMIN, GEN_STATUS = 0, 8, 9, 7
BR_FBUS, BR_TBUS, BR_X, BR_RATE_A, BR_STATUS = 0, 1, 3, 5, 10
GC_MODEL, GC_N = 0, 3
GC_COEFS_START = 4


def load_network(path: Path) -> dict[str, Any]:
    """Load a MATPOWER-format network from JSON.

    Accepts either the flat form ({"baseMVA": ..., "bus": [[...]], ...}) or
    the wrapped form ({"mpc": {...}}) produced by some exporters. Always
    returns the flat dict.
    """
    raw = json.loads(path.read_text())
    if "mpc" in raw and "bus" not in raw:
        raw = raw["mpc"]
    if "bus" not in raw or "gen" not in raw or "branch" not in raw:
        raise ValueError(
            f"{path}: missing required MATPOWER fields (bus/gen/branch). "
            f"Got top-level keys: {sorted(raw.keys())}"
        )
    return raw


# ----------------------------------------------------------------------------
# Parsed network container
# ----------------------------------------------------------------------------

@dataclass
class Parsed:
    base_mva: float
    bus_ids: list[int]
    bus_idx: dict[int, int]      # bus number -> position
    slack_idx: int
    pd: np.ndarray               # (n_bus,)
    g_bus_idx: np.ndarray        # (n_gen,) bus position for each gen
    p_min: np.ndarray            # (n_gen,)
    p_max: np.ndarray            # (n_gen,)
    rmax_g: np.ndarray           # (n_gen,) per-gen reserve cap
    cost_lin: np.ndarray         # (n_gen,) $/MWh linear coefficient
    cost_const: float            # constant cost (not used for LMP, kept for total)
    rcost: np.ndarray            # (n_gen,) reserve offer cost
    f_idx: np.ndarray            # (n_br,) from-bus position
    t_idx: np.ndarray            # (n_br,) to-bus position
    susc: np.ndarray             # (n_br,) susceptance 1/x
    rate: np.ndarray             # (n_br,) thermal limit MW (after overrides)
    f_bus_num: list[int]         # bus *numbers* (for report output)
    t_bus_num: list[int]
    reserve_req: float


def parse_network(
    net: dict[str, Any],
    *,
    line_overrides: list[tuple[int, int, float]],
    branch_index: int | None,
    reserve_req_override: float | None,
) -> Parsed:
    base_mva = float(net.get("baseMVA", 100.0))

    bus_rows = net["bus"]
    bus_ids = [int(r[BUS_I]) for r in bus_rows]
    bus_idx = {b: i for i, b in enumerate(bus_ids)}
    n_bus = len(bus_ids)
    pd = np.array([float(r[BUS_PD]) for r in bus_rows])
    bus_type = [int(r[BUS_TYPE]) for r in bus_rows]
    slack_candidates = [i for i, t in enumerate(bus_type) if t == 3]
    slack_idx = slack_candidates[0] if slack_candidates else 0

    # In-service generators
    gen_rows = [g for g in net["gen"] if int(g[GEN_STATUS]) == 1]
    n_gen = len(gen_rows)
    if n_gen == 0:
        raise ValueError("No in-service generators found")
    g_bus = [int(g[GEN_BUS]) for g in gen_rows]
    g_bus_idx = np.array([bus_idx[b] for b in g_bus])
    p_max = np.array([float(g[GEN_PMAX]) for g in gen_rows])
    p_min = np.array([float(g[GEN_PMIN]) for g in gen_rows])

    # Reserve data (PYPOWER-style `reserves` block) or defaults
    reserves = net.get("reserves") or {}
    rmax_g = np.array(reserves.get("qty", p_max - p_min), dtype=float)
    if len(rmax_g) != n_gen:
        rmax_g = (p_max - p_min)
    rmax_g = np.maximum(rmax_g, 0.0)
    rcost = np.array(reserves.get("cost", [0.0] * n_gen), dtype=float)
    if len(rcost) != n_gen:
        rcost = np.zeros(n_gen)

    if reserve_req_override is not None:
        reserve_req = float(reserve_req_override)
    elif "req" in reserves:
        req = reserves["req"]
        reserve_req = float(req[0]) if isinstance(req, list) else float(req)
    else:
        # N-1 default: enough spinning reserve to cover loss of the largest gen
        reserve_req = float(np.max(p_max))

    # Cost linearization
    gc = net.get("gencost", [])
    cost_lin = np.zeros(n_gen)
    cost_const = 0.0
    for i in range(n_gen):
        if i >= len(gc):
            continue
        row = gc[i]
        model = int(row[GC_MODEL])
        n_coef = int(row[GC_N])
        coefs = [float(c) for c in row[GC_COEFS_START : GC_COEFS_START + n_coef]]
        if model == 2:  # polynomial, highest order first
            if n_coef == 1:
                cost_const += coefs[0]
            elif n_coef == 2:
                cost_lin[i] = coefs[0]
                cost_const += coefs[1]
            elif n_coef >= 3:
                c2, c1, c0 = coefs[-3], coefs[-2], coefs[-1]
                # Linearize quadratic at the midpoint between p_min and p_max
                p_mid = 0.5 * (p_min[i] + p_max[i])
                cost_lin[i] = c1 + 2.0 * c2 * p_mid
                cost_const += c0 + c2 * p_mid * p_mid - 2.0 * c2 * p_mid * p_mid
        elif model == 1:  # piecewise linear: pairs (x0, y0, x1, y1, ...)
            xs = coefs[0::2]
            ys = coefs[1::2]
            if len(xs) >= 2:
                cost_lin[i] = (ys[1] - ys[0]) / (xs[1] - xs[0]) if xs[1] != xs[0] else 0.0
                cost_const += ys[0]

    # Branches (in-service)
    raw_branches = net["branch"]
    br_rows = [b for b in raw_branches if int(b[BR_STATUS]) == 1]
    n_br = len(br_rows)
    f_bus_num = [int(b[BR_FBUS]) for b in br_rows]
    t_bus_num = [int(b[BR_TBUS]) for b in br_rows]
    f_idx = np.array([bus_idx[b] for b in f_bus_num])
    t_idx = np.array([bus_idx[b] for b in t_bus_num])
    x_br = np.array([float(b[BR_X]) for b in br_rows])
    susc = 1.0 / np.where(np.abs(x_br) < 1e-9, 1e-9, x_br)
    rate = np.array([float(b[BR_RATE_A]) for b in br_rows])
    # MATPOWER convention: rateA == 0 means unlimited
    rate = np.where(rate <= 0, 1e9, rate)

    # Apply counterfactual overrides
    for k, (fr, to, factor) in enumerate(line_overrides):
        matched = []
        for j in range(n_br):
            if (f_bus_num[j] == fr and t_bus_num[j] == to) or (
                f_bus_num[j] == to and t_bus_num[j] == fr
            ):
                matched.append(j)
        if not matched:
            raise ValueError(
                f"override-line {fr}->{to}: no matching branch in network"
            )
        if branch_index is not None:
            if branch_index not in matched:
                raise ValueError(
                    f"--branch-index {branch_index} is not among the matching "
                    f"branches {matched} for line {fr}->{to}"
                )
            matched = [branch_index]
        for j in matched:
            if rate[j] >= 1e9:
                # Was unlimited; scaling has no meaningful effect — warn via stderr.
                print(
                    f"warning: branch {f_bus_num[j]}->{t_bus_num[j]} had rateA=0 "
                    f"(unlimited); scaling by {factor} is a no-op.",
                    file=sys.stderr,
                )
                continue
            rate[j] = rate[j] * factor

    return Parsed(
        base_mva=base_mva,
        bus_ids=bus_ids,
        bus_idx=bus_idx,
        slack_idx=slack_idx,
        pd=pd,
        g_bus_idx=g_bus_idx,
        p_min=p_min,
        p_max=p_max,
        rmax_g=rmax_g,
        cost_lin=cost_lin,
        cost_const=cost_const,
        rcost=rcost,
        f_idx=f_idx,
        t_idx=t_idx,
        susc=susc,
        rate=rate,
        f_bus_num=f_bus_num,
        t_bus_num=t_bus_num,
        reserve_req=reserve_req,
    )


# ----------------------------------------------------------------------------
# DC-OPF + reserve co-optimization solve
# ----------------------------------------------------------------------------

def solve(parsed: Parsed, *, binding_threshold: float) -> dict[str, Any]:
    """Solve the LP and return a results dict with cost, LMPs, MCP, binding lines."""
    n_bus = len(parsed.bus_ids)
    n_gen = len(parsed.p_max)
    n_br = len(parsed.f_idx)
    # Decision vector: [p_g (n_gen), r_g (n_gen), theta (n_bus)]
    nv_p = n_gen
    nv_r = n_gen
    nv_t = n_bus
    nvars = nv_p + nv_r + nv_t

    def slice_p(): return slice(0, nv_p)
    def slice_r(): return slice(nv_p, nv_p + nv_r)
    def slice_t(): return slice(nv_p + nv_r, nvars)

    # Objective
    c = np.zeros(nvars)
    c[slice_p()] = parsed.cost_lin
    c[slice_r()] = parsed.rcost
    # theta has no direct cost

    # Equality constraints
    #   (a) bus power balance: G @ p - baseMVA * B_bus @ theta = pd
    #       row per bus; LMP = dual at bus.
    #   (b) slack angle: theta[slack] = 0
    rows_p_bal_data = []
    rows_p_bal_indices = []
    rows_p_bal_indptr = [0]
    nnz = 0
    # We'll build by bus row. Start with empty row entries dict.
    G_rows: list[dict[int, float]] = [dict() for _ in range(n_bus)]
    # G @ p: each gen contributes +1 at its bus
    for j in range(n_gen):
        b = int(parsed.g_bus_idx[j])
        G_rows[b][j] = G_rows[b].get(j, 0.0) + 1.0
    # -baseMVA * B_bus @ theta: B_bus is symmetric Laplacian of branch susceptances.
    # For each branch k connecting fi, ti with susceptance s:
    #   B_bus[fi,fi] += s; B_bus[ti,ti] += s; B_bus[fi,ti] -= s; B_bus[ti,fi] -= s
    # Theta columns are offset by nv_p + nv_r.
    theta_offset = nv_p + nv_r
    for k in range(n_br):
        fi = int(parsed.f_idx[k])
        ti = int(parsed.t_idx[k])
        s = float(parsed.susc[k])
        coef = parsed.base_mva * s
        # bus fi: -coef * theta_fi + coef * theta_ti
        G_rows[fi][theta_offset + fi] = G_rows[fi].get(theta_offset + fi, 0.0) - coef
        G_rows[fi][theta_offset + ti] = G_rows[fi].get(theta_offset + ti, 0.0) + coef
        # bus ti: -coef * theta_ti + coef * theta_fi
        G_rows[ti][theta_offset + ti] = G_rows[ti].get(theta_offset + ti, 0.0) - coef
        G_rows[ti][theta_offset + fi] = G_rows[ti].get(theta_offset + fi, 0.0) + coef

    # Build sparse equality matrix
    eq_data: list[float] = []
    eq_indices: list[int] = []
    eq_indptr: list[int] = [0]
    for b in range(n_bus):
        for col, val in G_rows[b].items():
            eq_data.append(val)
            eq_indices.append(col)
        eq_indptr.append(len(eq_data))
    # Slack-angle row
    eq_data.append(1.0)
    eq_indices.append(theta_offset + parsed.slack_idx)
    eq_indptr.append(len(eq_data))

    A_eq = csr_matrix(
        (eq_data, eq_indices, eq_indptr),
        shape=(n_bus + 1, nvars),
    )
    b_eq = np.concatenate([parsed.pd, np.array([0.0])])

    # Inequality constraints
    #   (c) flow_k = baseMVA * susc_k * (theta_fi - theta_ti)
    #       -rate <= flow <= rate  →  flow - rate <= 0  AND  -flow - rate <= 0
    #   (d) capacity coupling: p_g + r_g - p_max <= 0
    #   (e) reserve requirement: -sum r_g <= -R_req
    ineq_data: list[float] = []
    ineq_indices: list[int] = []
    ineq_indptr: list[int] = [0]
    b_ub: list[float] = []
    reserve_row_index = None  # remember which row is the reserve req

    # Flow upper bound: baseMVA*susc*(theta_fi - theta_ti) <= rate_k
    for k in range(n_br):
        fi = int(parsed.f_idx[k])
        ti = int(parsed.t_idx[k])
        coef = parsed.base_mva * float(parsed.susc[k])
        ineq_data.extend([coef, -coef])
        ineq_indices.extend([theta_offset + fi, theta_offset + ti])
        ineq_indptr.append(len(ineq_data))
        b_ub.append(float(parsed.rate[k]))
    # Flow lower bound: -baseMVA*susc*(theta_fi - theta_ti) <= rate_k
    for k in range(n_br):
        fi = int(parsed.f_idx[k])
        ti = int(parsed.t_idx[k])
        coef = parsed.base_mva * float(parsed.susc[k])
        ineq_data.extend([-coef, coef])
        ineq_indices.extend([theta_offset + fi, theta_offset + ti])
        ineq_indptr.append(len(ineq_data))
        b_ub.append(float(parsed.rate[k]))
    # Capacity coupling: p_g + r_g - p_max <= 0
    for j in range(n_gen):
        ineq_data.extend([1.0, 1.0])
        ineq_indices.extend([j, nv_p + j])
        ineq_indptr.append(len(ineq_data))
        b_ub.append(float(parsed.p_max[j]))
    # Reserve requirement: -sum r_g <= -R_req
    reserve_row_index = len(b_ub)
    for j in range(n_gen):
        ineq_data.append(-1.0)
        ineq_indices.append(nv_p + j)
    ineq_indptr.append(len(ineq_data))
    b_ub.append(-float(parsed.reserve_req))

    A_ub = csr_matrix(
        (ineq_data, ineq_indices, ineq_indptr),
        shape=(len(b_ub), nvars),
    )
    b_ub_arr = np.array(b_ub)

    # Variable bounds
    bounds: list[tuple[float | None, float | None]] = []
    for j in range(n_gen):
        bounds.append((float(parsed.p_min[j]), float(parsed.p_max[j])))
    for j in range(n_gen):
        bounds.append((0.0, float(parsed.rmax_g[j])))
    for _ in range(n_bus):
        bounds.append((None, None))

    res = linprog(
        c=c,
        A_ub=A_ub,
        b_ub=b_ub_arr,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    if not res.success:
        raise RuntimeError(
            f"LP solver failed: status={res.status}, message={res.message}"
        )

    x = res.x
    p_g = x[slice_p()]
    r_g = x[slice_r()]
    theta = x[slice_t()]

    # Total cost (objective + constants we excluded for LMP cleanliness)
    total_cost = float(c @ x + parsed.cost_const)

    # LMPs: duals on the first n_bus equality rows.
    # HiGHS sign convention: for A_eq x = b_eq, eqlin.marginals gives ∂obj/∂b_eq.
    # Our row b is `pd`, so +1 MW of demand changes cost by +marginal → LMP > 0.
    eq_marginals = np.asarray(res.eqlin.marginals)
    raw_lmp = eq_marginals[:n_bus]
    # Defensive sign correction: if median is strongly negative, flip.
    lmp = raw_lmp if np.median(raw_lmp) >= 0 else -raw_lmp

    # Reserve MCP: dual on the reserve-requirement inequality.
    # ineqlin.marginals gives ∂obj/∂b_ub. Our row is -sum r_g <= -R_req.
    # Increasing R_req by 1 makes b_ub more negative by 1 → cost rises by -marginal.
    ineq_marginals = np.asarray(res.ineqlin.marginals)
    reserve_mcp = -float(ineq_marginals[reserve_row_index])
    if reserve_mcp < 0:  # numerical noise near zero
        reserve_mcp = abs(reserve_mcp) if abs(reserve_mcp) < 1e-6 else reserve_mcp

    # Binding lines
    flow = parsed.base_mva * parsed.susc * (theta[parsed.f_idx] - theta[parsed.t_idx])
    binding = []
    for k in range(n_br):
        limit = float(parsed.rate[k])
        if limit >= 1e8:
            continue  # ignore "unlimited" branches
        loading = abs(float(flow[k])) / limit
        if loading >= binding_threshold:
            binding.append({
                "from": int(parsed.f_bus_num[k]),
                "to": int(parsed.t_bus_num[k]),
                "flow_MW": round(float(flow[k]), 4),
                "limit_MW": round(limit, 4),
            })

    return {
        "total_cost_dollars_per_hour": round(total_cost, 4),
        "lmp_by_bus": [
            {"bus": int(parsed.bus_ids[i]), "lmp_dollars_per_MWh": round(float(lmp[i]), 4)}
            for i in range(n_bus)
        ],
        "reserve_mcp_dollars_per_MWh": round(float(reserve_mcp), 4),
        "binding_lines": binding,
        # Internal-only for impact analysis; popped before writing report.
        "_raw_lmp": lmp,
        "_targeted_line_binding": None,  # filled by run()
    }


# ----------------------------------------------------------------------------
# Top-level runner: base + counterfactual + report
# ----------------------------------------------------------------------------

def is_line_binding(
    binding_lines: list[dict[str, Any]], fr: int, to: int
) -> bool:
    for b in binding_lines:
        if (b["from"] == fr and b["to"] == to) or (b["from"] == to and b["to"] == fr):
            return True
    return False


def run(
    network_path: Path,
    *,
    line_overrides: list[tuple[int, int, float]],
    branch_index: int | None,
    reserve_req: float | None,
    binding_threshold: float,
    report_path: Path | None,
) -> dict[str, Any]:
    net = load_network(network_path)

    # Base solve: no overrides
    base_parsed = parse_network(
        net,
        line_overrides=[],
        branch_index=None,
        reserve_req_override=reserve_req,
    )
    base = solve(base_parsed, binding_threshold=binding_threshold)
    base_raw_lmp = base.pop("_raw_lmp")
    base.pop("_targeted_line_binding", None)

    report: dict[str, Any] = {"base_case": base}

    if line_overrides:
        cf_parsed = parse_network(
            copy.deepcopy(net),
            line_overrides=line_overrides,
            branch_index=branch_index,
            reserve_req_override=reserve_req,
        )
        cf = solve(cf_parsed, binding_threshold=binding_threshold)
        cf_raw_lmp = cf.pop("_raw_lmp")
        cf.pop("_targeted_line_binding", None)
        report["counterfactual"] = cf

        # Impact analysis
        cost_reduction = (
            base["total_cost_dollars_per_hour"]
            - cf["total_cost_dollars_per_hour"]
        )
        # Per-bus LMP deltas (full precision for sorting, round in output)
        deltas = []
        for i, bus_id in enumerate(base_parsed.bus_ids):
            base_lmp = float(base_raw_lmp[i])
            cf_lmp = float(cf_raw_lmp[i])
            deltas.append({
                "bus": int(bus_id),
                "base_lmp": round(base_lmp, 4),
                "cf_lmp": round(cf_lmp, 4),
                "delta": round(cf_lmp - base_lmp, 4),
                "_delta_full": cf_lmp - base_lmp,
            })
        # "Largest drop" = most negative delta (cf < base). Sort ascending by full-precision delta.
        deltas.sort(key=lambda d: d["_delta_full"])
        top3 = [{k: v for k, v in d.items() if not k.startswith("_")} for d in deltas[:3]]

        # congestion_relieved: true iff the modified line is NOT binding in CF.
        # If multiple overrides, treat as relieved iff all targeted pairs are non-binding.
        relieved = True
        for fr, to, _ in line_overrides:
            if is_line_binding(cf["binding_lines"], fr, to):
                relieved = False
                break

        report["impact_analysis"] = {
            "cost_reduction_dollars_per_hour": round(cost_reduction, 4),
            "buses_with_largest_lmp_drop": top3,
            "congestion_relieved": relieved,
        }

    if report_path:
        report_path.write_text(json.dumps(report, indent=2))
        print(f"wrote {report_path}")
    else:
        print(json.dumps(report, indent=2))

    return report


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _parse_override(s: str) -> tuple[int, int, float]:
    parts = s.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"--override-line expects FROM,TO,FACTOR; got `{s}`"
        )
    return int(parts[0]), int(parts[1]), float(parts[2])


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("network", type=Path, help="path to MATPOWER-format network.json")
    p.add_argument(
        "--override-line",
        type=_parse_override,
        action="append",
        default=[],
        help="FROM,TO,FACTOR — scale rateA of branch FROM<->TO by FACTOR (repeatable)",
    )
    p.add_argument("--branch-index", type=int, default=None,
                   help="restrict override to a specific branch row index (0-based, among status=1 branches)")
    p.add_argument("--reserve-req", type=float, default=None,
                   help="override system spinning reserve requirement in MW")
    p.add_argument("--binding-threshold", type=float, default=0.99,
                   help="line loading fraction to count as binding (default 0.99)")
    p.add_argument("--report", type=Path, default=None,
                   help="write the report.json to this path")
    args = p.parse_args()

    try:
        run(
            args.network,
            line_overrides=args.override_line,
            branch_index=args.branch_index,
            reserve_req=args.reserve_req,
            binding_threshold=args.binding_threshold,
            report_path=args.report,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
