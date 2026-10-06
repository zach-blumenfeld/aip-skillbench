#!/usr/bin/env python3
"""Solve DC-OPF with reserve co-optimization and extract LMPs.

Reads one JSON object from stdin:
  {"currentState": {"network_path": "<path to MATPOWER-format network.json>"},
   "assets": {...}, "expects": {...}}

Writes one JSON object to stdout with keys:
  generator_dispatch, lmp_by_bus, binding_lines, totals,
  reserve_mcp_dollars_per_MWh.
"""

import json
import subprocess
import sys


def _ensure_deps():
    try:
        import numpy  # noqa: F401
        import cvxpy  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "--break-system-packages",
             "numpy", "cvxpy", "clarabel"],
        )


_ensure_deps()

import numpy as np  # noqa: E402
import cvxpy as cp  # noqa: E402


BINDING_THRESHOLD = 99.0  # percent loading


def load_network(path):
    with open(path) as f:
        data = json.load(f)
    return {
        "baseMVA": float(data["baseMVA"]),
        "bus": np.array(data["bus"], dtype=float),
        "gen": np.array(data["gen"], dtype=float),
        "branch": np.array(data["branch"], dtype=float),
        "gencost": [list(map(float, row)) for row in data["gencost"]],
        "reserve_capacity": np.array(data["reserve_capacity"], dtype=float),
        "reserve_requirement": float(data["reserve_requirement"]),
    }


def build_b_matrix(branches, bus_num_to_idx, n_bus):
    B = np.zeros((n_bus, n_bus))
    susceptances = []
    for br in branches:
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        x = br[3]
        if x != 0:
            b = 1.0 / x
            B[f, f] += b
            B[t, t] += b
            B[f, t] -= b
            B[t, f] -= b
        else:
            b = 0.0
        susceptances.append(b)
    return B, susceptances


def solve(net):
    baseMVA = net["baseMVA"]
    buses = net["bus"]
    gens = net["gen"]
    branches = net["branch"]
    gencost = net["gencost"]
    reserve_capacity = net["reserve_capacity"]
    reserve_requirement = net["reserve_requirement"]

    n_bus = len(buses)
    n_gen = len(gens)
    n_branch = len(branches)

    bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
    gen_bus = [bus_num_to_idx[int(g[0])] for g in gens]

    B, susceptances = build_b_matrix(branches, bus_num_to_idx, n_bus)

    Pg = cp.Variable(n_gen)   # per-unit
    Rg = cp.Variable(n_gen)   # MW
    theta = cp.Variable(n_bus)

    constraints = []

    # Slack bus reference angle
    slack_idx = None
    for i in range(n_bus):
        if buses[i, 1] == 3:
            slack_idx = i
            break
    if slack_idx is None:
        slack_idx = 0
    constraints.append(theta[slack_idx] == 0)

    # Objective
    cost = 0
    for i in range(n_gen):
        row = gencost[i]
        ncost = int(row[3])
        Pg_MW = Pg[i] * baseMVA
        if ncost >= 3:
            c2, c1, c0 = row[4], row[5], row[6]
            cost += c2 * cp.square(Pg_MW) + c1 * Pg_MW + c0
        elif ncost == 2:
            c1, c0 = row[4], row[5]
            cost += c1 * Pg_MW + c0
        elif ncost == 1:
            cost += row[4]

    # Generator energy limits (per-unit)
    for i in range(n_gen):
        pmin = gens[i, 9] / baseMVA
        pmax = gens[i, 8] / baseMVA
        constraints.append(Pg[i] >= pmin)
        constraints.append(Pg[i] <= pmax)

    # Reserve constraints
    constraints.append(Rg >= 0)
    for i in range(n_gen):
        constraints.append(Rg[i] <= reserve_capacity[i])
        pmax_MW = gens[i, 8]
        Pg_MW = Pg[i] * baseMVA
        constraints.append(Pg_MW + Rg[i] <= pmax_MW)
    reserve_con = cp.sum(Rg) >= reserve_requirement
    constraints.append(reserve_con)

    # Nodal power balance (DC): generation - load = B[i,:] @ theta  (per-unit)
    balance_constraints = []
    for i in range(n_bus):
        pg_at_bus = sum((Pg[g] for g in range(n_gen) if gen_bus[g] == i), 0)
        pd = buses[i, 2] / baseMVA
        bc = pg_at_bus - pd == B[i, :] @ theta
        balance_constraints.append(bc)
        constraints.append(bc)

    # Line thermal limits
    for k in range(n_branch):
        br = branches[k]
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        b = susceptances[k]
        rate = br[5]
        if rate > 0 and b != 0:
            flow_MW = b * (theta[f] - theta[t]) * baseMVA
            constraints.append(flow_MW <= rate)
            constraints.append(flow_MW >= -rate)

    prob = cp.Problem(cp.Minimize(cost), constraints)
    prob.solve(solver=cp.CLARABEL)

    if Pg.value is None or theta.value is None:
        raise RuntimeError(
            f"DC-OPF failed to solve (status={prob.status}, value={prob.value})"
        )

    Pg_MW = Pg.value * baseMVA
    Rg_MW = Rg.value

    generator_dispatch = []
    for i in range(n_gen):
        generator_dispatch.append({
            "id": i + 1,
            "bus": int(gens[i, 0]),
            "output_MW": round(float(Pg_MW[i]), 2),
            "reserve_MW": round(float(Rg_MW[i]), 2),
            "pmax_MW": round(float(gens[i, 8]), 2),
        })

    lmp_by_bus = []
    for i in range(n_bus):
        dv = balance_constraints[i].dual_value
        # The balance constraint is written in per-unit (Pg_pu - Pd_pu = B@theta)
        # while the objective is a function of Pg_MW = Pg_pu * baseMVA. By KKT,
        # the dual value is in $/(pu·hr) = baseMVA × $/(MWh), so divide by
        # baseMVA to recover an LMP in $/MWh.
        lmp = float(dv) / baseMVA if dv is not None else 0.0
        lmp_by_bus.append({
            "bus": int(buses[i, 0]),
            "lmp_dollars_per_MWh": round(lmp, 2),
        })

    binding_lines = []
    for k in range(n_branch):
        br = branches[k]
        f = bus_num_to_idx[int(br[0])]
        t = bus_num_to_idx[int(br[1])]
        b = susceptances[k]
        rate = br[5]
        if rate > 0 and b != 0:
            flow_MW = b * (theta.value[f] - theta.value[t]) * baseMVA
            loading_pct = abs(flow_MW) / rate * 100.0
            if loading_pct >= BINDING_THRESHOLD:
                binding_lines.append({
                    "from": int(br[0]),
                    "to": int(br[1]),
                    "flow_MW": round(float(flow_MW), 2),
                    "limit_MW": round(float(rate), 2),
                })

    total_gen_MW = float(sum(Pg_MW))
    total_load_MW = float(sum(buses[i, 2] for i in range(n_bus)))
    total_reserve_MW = float(sum(Rg_MW))

    totals = {
        "cost_dollars_per_hour": round(float(prob.value), 2),
        "load_MW": round(total_load_MW, 2),
        "generation_MW": round(total_gen_MW, 2),
        "reserve_MW": round(total_reserve_MW, 2),
    }

    reserve_mcp = (
        float(reserve_con.dual_value) if reserve_con.dual_value is not None else 0.0
    )

    return {
        "generator_dispatch": generator_dispatch,
        "lmp_by_bus": lmp_by_bus,
        "binding_lines": binding_lines,
        "totals": totals,
        "reserve_mcp_dollars_per_MWh": round(reserve_mcp, 2),
    }


def main():
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    path = state["network_path"]
    net = load_network(path)
    result = solve(net)
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
