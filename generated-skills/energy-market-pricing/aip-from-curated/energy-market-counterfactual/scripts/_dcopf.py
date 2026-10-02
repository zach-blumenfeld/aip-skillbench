"""DC-OPF with reserve co-optimization for the energy-market-counterfactual skill.

Shared solver used by scripts/solve_base.py and scripts/solve_counterfactual.py.
Not a driver — no stdin/stdout contract.
"""
from __future__ import annotations

import importlib
import subprocess
import sys


def _have_pip() -> bool:
    try:
        importlib.import_module("pip")
        return True
    except ImportError:
        return False


def _pip_install(pkg: str) -> None:
    if not _have_pip():
        # Bootstrap pip in interpreters (uv-managed venvs, some minimal images) that lack it.
        try:
            subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
        except subprocess.CalledProcessError:
            pass
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q", pkg]
    )


def _ensure(pkg: str, module: str | None = None) -> None:
    mod = module or pkg.split("==")[0]
    try:
        importlib.import_module(mod)
    except ImportError:
        _pip_install(pkg)
        importlib.invalidate_caches()
        importlib.import_module(mod)


def bootstrap() -> None:
    """Install pinned numeric stack when missing (Ubuntu 24.04 container has only python3)."""
    _ensure("numpy==1.26.4", "numpy")
    _ensure("scipy==1.11.4", "scipy")
    _ensure("cvxpy==1.4.2", "cvxpy")


BINDING_THRESHOLD = 99.0  # percent loading


def load_network(path: str):
    import json
    import numpy as np

    with open(path) as f:
        data = json.load(f)
    return {
        "baseMVA": float(data["baseMVA"]),
        "bus": np.array(data["bus"]),
        "gen": np.array(data["gen"]),
        "branch": np.array(data["branch"]),
        "gencost": np.array(data["gencost"]),
        "reserve_capacity": np.array(data["reserve_capacity"]),
        "reserve_requirement": float(data["reserve_requirement"]),
    }


def apply_line_limit_change(branches, from_bus: int, to_bus: int, delta_pct: float):
    """Return a copy of branches with the (from,to) line's RATE_A scaled by (1 + delta_pct/100).

    Matches either direction. Raises ValueError if the line is not found.
    """
    import numpy as np

    cf = branches.copy()
    factor = 1.0 + delta_pct / 100.0
    for k in range(len(cf)):
        f_b = int(cf[k, 0])
        t_b = int(cf[k, 1])
        if (f_b == from_bus and t_b == to_bus) or (f_b == to_bus and t_b == from_bus):
            cf[k, 5] = float(cf[k, 5]) * factor
            return cf, k, float(branches[k, 5]), float(cf[k, 5])
    raise ValueError(f"Line {from_bus}->{to_bus} not found in network")


def solve_dcopf_with_reserves(network, branches_array):
    """Solve DC-OPF + reserve co-optimization on the given branches array.

    Returns a dict shaped for the report:
      total_cost_dollars_per_hour, lmp_by_bus, reserve_mcp_dollars_per_MWh, binding_lines.
    """
    import cvxpy as cp
    import numpy as np

    baseMVA = network["baseMVA"]
    buses = network["bus"]
    gens = network["gen"]
    gencost = network["gencost"]
    reserve_capacity = network["reserve_capacity"]
    reserve_requirement = network["reserve_requirement"]

    n_bus = len(buses)
    n_gen = len(gens)

    bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
    slack_idx = next(i for i in range(n_bus) if buses[i, 1] == 3)
    gen_bus = [bus_num_to_idx[int(g[0])] for g in gens]

    # Susceptance matrix (see source/dc-power-flow/scripts/build_b_matrix.py)
    B = np.zeros((n_bus, n_bus))
    branch_susceptances = []
    for br in branches_array:
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        x = float(br[3])
        if x != 0:
            b = 1.0 / x
            B[f, f] += b
            B[t, t] += b
            B[f, t] -= b
            B[t, f] -= b
            branch_susceptances.append(b)
        else:
            branch_susceptances.append(0.0)

    Pg = cp.Variable(n_gen)
    Rg = cp.Variable(n_gen)
    theta = cp.Variable(n_bus)

    # Objective: variable-NCOST polynomial cost (handles linear or constant)
    cost = 0
    for i in range(n_gen):
        ncost = int(gencost[i, 3])
        Pg_MW = Pg[i] * baseMVA
        if ncost >= 3:
            c2, c1, c0 = gencost[i, 4], gencost[i, 5], gencost[i, 6]
            cost += c2 * cp.square(Pg_MW) + c1 * Pg_MW + c0
        elif ncost == 2:
            c1, c0 = gencost[i, 4], gencost[i, 5]
            cost += c1 * Pg_MW + c0
        elif ncost == 1:
            cost += gencost[i, 4]

    constraints = []
    balance_constraints = []

    # Nodal power balance (duals become LMPs after baseMVA scaling)
    for i in range(n_bus):
        pg_at_bus = sum(Pg[g] for g in range(n_gen) if gen_bus[g] == i)
        pd = buses[i, 2] / baseMVA
        con = pg_at_bus - pd == B[i, :] @ theta
        balance_constraints.append(con)
        constraints.append(con)

    # Generator PMIN / PMAX (per-unit)
    for i in range(n_gen):
        pmin = gens[i, 9] / baseMVA
        pmax = gens[i, 8] / baseMVA
        constraints.append(Pg[i] >= pmin)
        constraints.append(Pg[i] <= pmax)

    # Reserves: non-negative, per-gen cap, capacity coupling P + R <= PMAX
    constraints.append(Rg >= 0)
    for i in range(n_gen):
        constraints.append(Rg[i] <= reserve_capacity[i])
        constraints.append(Pg[i] * baseMVA + Rg[i] <= gens[i, 8])

    # System reserve requirement (dual = reserve MCP)
    reserve_con = cp.sum(Rg) >= reserve_requirement
    constraints.append(reserve_con)

    # Slack bus angle
    constraints.append(theta[slack_idx] == 0)

    # Line thermal limits
    for k, br in enumerate(branches_array):
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        x = float(br[3])
        rate = float(br[5])
        if x != 0 and rate > 0:
            b = branch_susceptances[k]
            flow = b * (theta[f] - theta[t]) * baseMVA
            constraints.append(flow <= rate)
            constraints.append(flow >= -rate)

    prob = cp.Problem(cp.Minimize(cost), constraints)
    prob.solve(solver=cp.CLARABEL)
    if prob.status != "optimal":
        raise RuntimeError(f"CLARABEL failed: status={prob.status}")

    theta_val = theta.value

    # LMPs from balance-constraint duals, scaled by baseMVA (constraint is in per-unit)
    lmp_by_bus = []
    for i in range(n_bus):
        dv = balance_constraints[i].dual_value
        lmp = float(dv) * baseMVA if dv is not None else 0.0
        lmp_by_bus.append({"bus": int(buses[i, 0]), "lmp_dollars_per_MWh": round(lmp, 2)})

    reserve_mcp = float(reserve_con.dual_value) if reserve_con.dual_value is not None else 0.0

    # Binding lines: loading >= 99%
    binding_lines = []
    for k, br in enumerate(branches_array):
        x = float(br[3])
        rate = float(br[5])
        if x == 0 or rate <= 0:
            continue
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        b = branch_susceptances[k]
        flow_MW = b * (theta_val[f] - theta_val[t]) * baseMVA
        loading_pct = abs(flow_MW) / rate * 100
        if loading_pct >= BINDING_THRESHOLD:
            binding_lines.append({
                "from": int(br[0]),
                "to": int(br[1]),
                "flow_MW": round(float(flow_MW), 2),
                "limit_MW": round(float(rate), 2),
            })

    return {
        "total_cost_dollars_per_hour": round(float(prob.value), 2),
        "lmp_by_bus": lmp_by_bus,
        "reserve_mcp_dollars_per_MWh": round(reserve_mcp, 2),
        "binding_lines": binding_lines,
    }
