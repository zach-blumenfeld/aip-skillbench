"""Shared DC-OPF solver for the energy-market-pricing skill.

Loads a MATPOWER-format network.json, builds the susceptance matrix, and
solves a DC-OPF with operating-reserve co-optimization. Extracts LMPs
from nodal-balance duals, the reserve MCP from the reserve-requirement
dual, and flags lines at or near their thermal limit.

Keeps everything in one module so both solve_base.py and solve_counterfactual.py
share identical formulations — the counterfactual must only differ in the
branch rating that was relaxed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any


def _ensure(pkg: str, import_name: str | None = None) -> None:
    try:
        __import__(import_name or pkg)
        return
    except ImportError:
        pass
    attempts = [
        [sys.executable, "-m", "pip", "install", "--quiet", pkg],
        ["uv", "pip", "install", "--python", sys.executable, "--quiet", pkg],
    ]
    last_err = None
    for cmd in attempts:
        try:
            subprocess.check_call(cmd, stdout=sys.stderr, stderr=sys.stderr)
            __import__(import_name or pkg)
            return
        except Exception as e:
            last_err = e
    raise RuntimeError(
        f"Could not install {pkg!r} for {sys.executable}: {last_err}. "
        "Ensure the runtime provides pip or uv."
    )


# Bootstrap at import time so caller scripts don't each repeat it. The
# reference container (source/Dockerfile) ships only python3 + pip; PGLib
# downstream agents may run us without a prepared venv.
_ensure("numpy")
_ensure("cvxpy")

import cvxpy as cp  # noqa: E402
import numpy as np  # noqa: E402

BINDING_THRESHOLD_PCT = 99.0


def load_network(path: str) -> dict[str, Any]:
    with open(path) as f:
        data = json.load(f)
    return {
        "baseMVA": float(data["baseMVA"]),
        "bus": np.array(data["bus"], dtype=float),
        "gen": np.array(data["gen"], dtype=float),
        "branch": np.array(data["branch"], dtype=float),
        "gencost": np.array(data["gencost"], dtype=float),
        "reserve_capacity": np.array(data.get("reserve_capacity", []), dtype=float),
        "reserve_requirement": float(data.get("reserve_requirement", 0.0)),
    }


def build_susceptance_matrix(branches: np.ndarray, buses: np.ndarray):
    n_bus = len(buses)
    bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
    B = np.zeros((n_bus, n_bus))
    branch_b = []
    for br in branches:
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        x = float(br[3])
        b = 1.0 / x if x != 0 else 0.0
        branch_b.append(b)
        if b:
            B[f, f] += b
            B[t, t] += b
            B[f, t] -= b
            B[t, f] -= b
    return B, branch_b, bus_num_to_idx


def find_slack_bus(buses: np.ndarray) -> int:
    for i in range(len(buses)):
        if int(buses[i, 1]) == 3:
            return i
    return 0


def _gen_cost_term(Pg_MW_i, gencost_row):
    ncost = int(gencost_row[3])
    if ncost >= 3:
        c2, c1, c0 = float(gencost_row[4]), float(gencost_row[5]), float(gencost_row[6])
        return c2 * cp.square(Pg_MW_i) + c1 * Pg_MW_i + c0
    if ncost == 2:
        c1, c0 = float(gencost_row[4]), float(gencost_row[5])
        return c1 * Pg_MW_i + c0
    return float(gencost_row[4]) if ncost >= 1 else 0.0


def solve_dcopf(net: dict[str, Any]) -> dict[str, Any]:
    """Solve DC-OPF with reserve co-optimization. Returns a result dict."""
    buses = net["bus"]
    gens = net["gen"]
    branches = net["branch"]
    gencost = net["gencost"]
    baseMVA = net["baseMVA"]
    reserve_capacity = net["reserve_capacity"]
    reserve_requirement = net["reserve_requirement"]

    n_bus = len(buses)
    n_gen = len(gens)
    n_branch = len(branches)

    B, branch_b, bus_num_to_idx = build_susceptance_matrix(branches, buses)
    gen_bus = [bus_num_to_idx[int(g[0])] for g in gens]
    slack_idx = find_slack_bus(buses)

    Pg = cp.Variable(n_gen)
    theta = cp.Variable(n_bus)
    has_reserves = n_gen > 0 and len(reserve_capacity) == n_gen and reserve_requirement > 0
    Rg = cp.Variable(n_gen) if has_reserves else None

    cost_expr = 0
    for i in range(n_gen):
        cost_expr = cost_expr + _gen_cost_term(Pg[i] * baseMVA, gencost[i])
    # Tiny quadratic regularization. For PGLib cases with real c2>0 this is
    # dominated by the actual cost; for degenerate pure-LP cases it stabilizes
    # the dual values that the LMPs are extracted from. Cost impact is <0.01%.
    cost_expr = cost_expr + 1e-4 * cp.sum_squares(Pg * baseMVA)

    constraints = []
    for i in range(n_gen):
        constraints.append(Pg[i] >= gens[i, 9] / baseMVA)
        constraints.append(Pg[i] <= gens[i, 8] / baseMVA)

    if has_reserves:
        constraints.append(Rg >= 0)
        for i in range(n_gen):
            constraints.append(Rg[i] <= float(reserve_capacity[i]))
            constraints.append(Pg[i] * baseMVA + Rg[i] <= float(gens[i, 8]))
        reserve_con = cp.sum(Rg) >= reserve_requirement
        constraints.append(reserve_con)
    else:
        reserve_con = None

    balance_cons = []
    for i in range(n_bus):
        pg_at_bus = sum((Pg[g] for g in range(n_gen) if gen_bus[g] == i), 0)
        pd_pu = float(buses[i, 2]) / baseMVA
        # Written as B@theta == pg - pd (not pg - pd == B@theta). CVXPY's
        # equality-dual sign depends on which side is lhs. This arrangement
        # makes `dual_value / baseMVA` the economically correct LMP: positive
        # at expensive buses, lowest at cheap-and-congested buses.
        con = B[i, :] @ theta == pg_at_bus - pd_pu
        balance_cons.append(con)
        constraints.append(con)

    for k, br in enumerate(branches):
        rate = float(br[5])
        b = branch_b[k]
        if rate <= 0 or b == 0:
            continue
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        flow_MW = b * (theta[f] - theta[t]) * baseMVA
        constraints.append(flow_MW <= rate)
        constraints.append(flow_MW >= -rate)

    constraints.append(theta[slack_idx] == 0)

    prob = cp.Problem(cp.Minimize(cost_expr), constraints)
    prob.solve(solver=cp.CLARABEL)

    if prob.status not in ("optimal", "optimal_inaccurate"):
        raise RuntimeError(f"DC-OPF did not solve: status={prob.status}")

    Pg_MW = (Pg.value * baseMVA).tolist()
    Rg_MW = Rg.value.tolist() if has_reserves else [0.0] * n_gen
    theta_val = theta.value

    dispatch = []
    for i in range(n_gen):
        dispatch.append({
            "id": i + 1,
            "bus": int(gens[i, 0]),
            "output_MW": round(float(Pg_MW[i]), 2),
            "reserve_MW": round(float(Rg_MW[i]), 2),
            "pmax_MW": round(float(gens[i, 8]), 2),
        })

    lmps = []
    for i in range(n_bus):
        dv = balance_cons[i].dual_value
        # Balance constraint is per-unit; cost is $/hr. dual has units
        # $/hr-per-pu = $/hr-per-100MW. Divide by baseMVA to get $/MWh.
        lmp = float(dv) / baseMVA if dv is not None else 0.0
        lmps.append({"bus": int(buses[i, 0]), "lmp_dollars_per_MWh": round(lmp, 2)})

    line_flows = []
    binding = []
    for k, br in enumerate(branches):
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        b = branch_b[k]
        rate = float(br[5])
        flow_MW = b * (theta_val[f] - theta_val[t]) * baseMVA
        loading = abs(flow_MW) / rate * 100 if rate > 0 else 0.0
        rec = {
            "from": int(br[0]),
            "to": int(br[1]),
            "flow_MW": round(float(flow_MW), 2),
            "limit_MW": round(float(rate), 2),
            "loading_pct": round(float(loading), 2),
        }
        line_flows.append(rec)
        if loading >= BINDING_THRESHOLD_PCT:
            binding.append(rec)

    total_load_MW = float(sum(buses[:, 2]))
    total_gen_MW = float(sum(Pg_MW))
    total_reserve_MW = float(sum(Rg_MW))
    operating_margin_MW = float(
        sum(float(gens[i, 8]) - Pg_MW[i] - Rg_MW[i] for i in range(n_gen))
    )
    reserve_mcp = 0.0
    if reserve_con is not None and reserve_con.dual_value is not None:
        reserve_mcp = float(reserve_con.dual_value)

    return {
        "status": prob.status,
        "cost_dollars_per_hour": round(float(prob.value), 2),
        "total_load_MW": round(total_load_MW, 2),
        "total_generation_MW": round(total_gen_MW, 2),
        "total_reserve_MW": round(total_reserve_MW, 2),
        "operating_margin_MW": round(operating_margin_MW, 2),
        "reserve_mcp_dollars_per_MWh": round(reserve_mcp, 2),
        "dispatch": dispatch,
        "lmps": lmps,
        "line_flows": line_flows,
        "binding_lines": binding,
        "n_bus": n_bus,
        "n_gen": n_gen,
        "n_branch": n_branch,
    }
