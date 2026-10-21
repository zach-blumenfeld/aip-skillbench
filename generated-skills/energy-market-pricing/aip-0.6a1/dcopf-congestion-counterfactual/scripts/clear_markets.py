#!/usr/bin/env python3
"""Clear a DC-OPF energy + spinning-reserve market twice: base case and a
counterfactual with one line's thermal limit (RATE_A) scaled up.

stdin : {"state": {network_path, line_from_bus, line_to_bus, capacity_increase_pct}, ...}
stdout: {"status", "status_detail", "base_case", "counterfactual",
         "impact_analysis", "target_line", "diagnostics"}

The entry point is stdlib-only. If numpy/scipy/cvxpy/clarabel are not importable
(the task container ships bare python3), it builds a venv once at
$DCOPF_CF_VENV (default ~/.cache/dcopf-congestion-counterfactual/venv), pip-installs
them there, and re-runs itself under that venv's python. All pip/log output goes to
stderr; stdout carries only the result object.
"""

import json
import os
import subprocess
import sys

PACKAGES = ["numpy", "scipy", "cvxpy", "clarabel"]
BINDING_THRESHOLD_PCT = 99.0  # loading >= 99% of RATE_A counts as binding
CHILD_FLAG = "DCOPF_CF_CHILD"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def packages_importable():
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import cvxpy  # noqa: F401
        import clarabel  # noqa: F401
        return True
    except ImportError:
        return False


def run_in_venv(raw_stdin):
    """Create/reuse a venv holding PACKAGES and re-run this script inside it."""
    venv = os.environ.get("DCOPF_CF_VENV") or os.path.join(
        os.path.expanduser("~"), ".cache", "dcopf-congestion-counterfactual", "venv")
    vpy = os.path.join(venv, "bin", "python")
    if not os.path.exists(vpy):
        log(f"[bootstrap] creating venv at {venv}")
        r = subprocess.run([sys.executable, "-m", "venv", venv], stdout=sys.stderr)
        if r.returncode != 0:
            sys.exit(f"venv creation failed (is python3-venv installed?) at {venv}")
    check = subprocess.run([vpy, "-c", "import numpy, scipy, cvxpy, clarabel"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if check.returncode != 0:
        log(f"[bootstrap] pip install {' '.join(PACKAGES)} into {venv}")
        r = subprocess.run([vpy, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                            *PACKAGES], stdout=sys.stderr)
        if r.returncode != 0:
            sys.exit("pip install of numpy/scipy/cvxpy/clarabel failed; "
                     "network access to PyPI is needed for the first run")
    env = dict(os.environ, **{CHILD_FLAG: "1"})
    env.pop("PYTHONPATH", None)
    r = subprocess.run([vpy, os.path.abspath(__file__)], input=raw_stdin, env=env,
                       stdout=subprocess.PIPE)
    sys.stdout.buffer.write(r.stdout)
    sys.exit(r.returncode)


class ModelError(Exception):
    """Data or model problem the agent should diagnose (routes to the failure branch)."""


# ---------------------------------------------------------------- market model
def load_network(path):
    import numpy as np
    if not os.path.exists(path):
        raise ModelError(f"network file not found: {path}")
    with open(path) as f:
        data = json.load(f)
    for key in ("baseMVA", "bus", "gen", "branch", "gencost"):
        if key not in data:
            raise ModelError(f"network file lacks '{key}' (expected MATPOWER-style JSON)")
    net = {
        "baseMVA": float(data["baseMVA"]),
        "bus": np.array(data["bus"], dtype=float),
        "gen": np.array(data["gen"], dtype=float),
        "branch": np.array(data["branch"], dtype=float),
        "gencost": data["gencost"],  # rows may differ in length (NCOST varies)
    }
    n_gen = len(net["gen"])
    rc = data.get("reserve_capacity")
    net["reserve_capacity"] = (np.array(rc, dtype=float) if rc is not None
                               else np.zeros(n_gen))
    net["reserve_requirement"] = float(data.get("reserve_requirement") or 0.0)
    net["has_reserve_data"] = rc is not None and "reserve_requirement" in data
    if len(net["reserve_capacity"]) != n_gen:
        raise ModelError(f"reserve_capacity has {len(net['reserve_capacity'])} entries "
                         f"for {n_gen} generators")
    if len(net["gencost"]) < n_gen:
        raise ModelError(f"gencost has {len(net['gencost'])} rows for {n_gen} generators")
    return net


def build_cost(Pg_MW, gencost_rows, cp):
    """Total cost expression (and extra constraints for piecewise-linear rows)."""
    terms, extra = [], []
    for i, row in enumerate(gencost_rows):
        model, ncost = int(row[0]), int(row[3])
        coeffs = [float(c) for c in row[4:]]
        if model == 2:  # polynomial, highest order first
            c = coeffs[:ncost]
            if ncost >= 4 and any(abs(x) > 0 for x in c[:-3]):
                raise ModelError(f"gen {i + 1}: polynomial cost of order {ncost - 1} "
                                 "is not supported (max quadratic)")
            c = c[-3:] if ncost >= 3 else c
            if len(c) == 3:
                c2, c1, c0 = c
                if c2 < 0:
                    raise ModelError(f"gen {i + 1}: negative quadratic cost (non-convex)")
                if c2:
                    terms.append(c2 * cp.square(Pg_MW[i]))
                terms.append(c1 * Pg_MW[i] + c0)
            elif len(c) == 2:
                terms.append(c[0] * Pg_MW[i] + c[1])
            elif len(c) == 1:
                terms.append(cp.Constant(c[0]))
        elif model == 1:  # piecewise linear: (P1,C1),...,(Pn,Cn); epigraph form
            pts = [(coeffs[2 * k], coeffs[2 * k + 1]) for k in range(ncost)]
            t = cp.Variable()
            for (p0, c0), (p1, c1) in zip(pts[:-1], pts[1:]):
                if p1 == p0:
                    continue
                slope = (c1 - c0) / (p1 - p0)
                extra.append(t >= c0 + slope * (Pg_MW[i] - p0))
            terms.append(t)
        else:
            raise ModelError(f"gen {i + 1}: unknown gencost MODEL {model}")
    return cp.sum(cp.hstack(terms)) if terms else cp.Constant(0.0), extra


def solve_market(net, rate_a):
    """One DC-OPF with reserve co-optimization. rate_a: per-branch MW limits."""
    import numpy as np
    import scipy.sparse as sp
    import cvxpy as cp

    base = net["baseMVA"]
    bus, gen, br = net["bus"], net["gen"], net["branch"]
    n_bus = len(bus)
    idx = {int(bus[i, 0]): i for i in range(n_bus)}  # bus numbers are non-contiguous

    gon = np.where(gen[:, 7] > 0)[0] if gen.shape[1] > 7 else np.arange(len(gen))
    bon = np.where(br[:, 10] > 0)[0] if br.shape[1] > 10 else np.arange(len(br))
    try:
        gbus = np.array([idx[int(gen[g, 0])] for g in gon], dtype=int)
        f = np.array([idx[int(br[k, 0])] for k in bon], dtype=int)
        t = np.array([idx[int(br[k, 1])] for k in bon], dtype=int)
    except KeyError as e:
        raise ModelError(f"generator or branch references unknown bus {e}")
    x = br[bon, 3]
    b = np.where(x != 0, 1.0 / np.where(x != 0, x, 1.0), 0.0)  # susceptance 1/X
    nl, ng = len(bon), len(gon)

    A = sp.csr_matrix((np.r_[np.ones(nl), -np.ones(nl)], (np.r_[np.arange(nl), np.arange(nl)],
                       np.r_[f, t])), shape=(nl, n_bus))
    Bf = sp.diags(b) @ A                      # branch flow (pu) = Bf @ theta
    Bbus = (A.T @ Bf).tocsr()                 # nodal susceptance matrix
    Cg = sp.csr_matrix((np.ones(ng), (gbus, np.arange(ng))), shape=(n_bus, ng))

    Pg = cp.Variable(ng)       # per-unit
    Rg = cp.Variable(ng)       # MW
    theta = cp.Variable(n_bus)  # radians
    Pg_MW = Pg * base

    cost, cons = build_cost(Pg_MW, [net["gencost"][g] for g in gon], cp)
    # Nodal balance written in MW, so its dual is $/MWh directly. cvxpy's equality
    # dual is the NEGATIVE of d(cost)/d(load) for "gen - load == B theta":
    # LMP = -dual (verified by a +1 MW finite-difference check below).
    balance = Cg @ Pg_MW - bus[:, 2] == base * (Bbus @ theta)
    cons.append(balance)
    pmax, pmin = gen[gon, 8], gen[gon, 9]
    cons += [Pg >= pmin / base, Pg <= pmax / base]
    cons += [Rg >= 0, Rg <= net["reserve_capacity"][gon], Pg_MW + Rg <= pmax]
    reserve_con = cp.sum(Rg) >= net["reserve_requirement"]
    cons.append(reserve_con)
    lim = rate_a[bon]
    lk = np.where(lim > 0)[0]                 # RATE_A == 0 means unlimited
    if len(lk):
        flow_MW = base * (Bf[lk] @ theta)
        cons += [flow_MW <= lim[lk], flow_MW >= -lim[lk]]
    slack = np.where(bus[:, 1] == 3)[0]
    ref = int(slack[0]) if len(slack) else 0
    cons.append(theta[ref] == 0)

    prob = cp.Problem(cp.Minimize(cost), cons)
    solver_used, status = None, None
    for solver in ("CLARABEL", "HIGHS", "SCS"):
        if solver not in cp.installed_solvers():
            continue
        try:
            prob.solve(solver=solver)
        except cp.error.SolverError as e:
            log(f"[solve] {solver} failed: {e}")
            continue
        solver_used, status = solver, prob.status
        if status in ("optimal", "optimal_inaccurate"):
            break
        if status in ("infeasible", "unbounded"):
            break
    if status not in ("optimal", "optimal_inaccurate"):
        raise ModelError(f"market clearing did not solve: status={status} "
                         f"(solver {solver_used}); total load {bus[:, 2].sum():.1f} MW, "
                         f"online Pmax {pmax.sum():.1f} MW, reserve requirement "
                         f"{net['reserve_requirement']:.1f} MW vs reserve capacity "
                         f"{net['reserve_capacity'][gon].sum():.1f} MW")

    lmp = -np.asarray(balance.dual_value).ravel()   # $/MWh
    mcp = float(reserve_con.dual_value) if reserve_con.dual_value is not None else 0.0
    th = np.asarray(theta.value).ravel()
    flows = base * (Bf @ th)
    line_rows = []
    for j, k in enumerate(bon):
        rate = float(rate_a[k])
        loading = abs(flows[j]) / rate * 100.0 if rate > 0 else 0.0
        line_rows.append({"k": int(k), "from": int(br[k, 0]), "to": int(br[k, 1]),
                          "flow_MW": float(flows[j]), "limit_MW": rate, "loading_pct": loading})
    return {
        "total_cost": float(prob.value),
        "lmp": {int(bus[i, 0]): float(lmp[i]) for i in range(n_bus)},
        "mcp": mcp,
        "lines": line_rows,
        "solver": solver_used,
        "status": status,
        "gen_MW": float(np.sum(Pg.value) * base),
        "reserve_MW": float(np.sum(Rg.value)),
    }


def case_block(res, bus_order):
    binding = [{"from": r["from"], "to": r["to"], "flow_MW": round(r["flow_MW"], 2),
                "limit_MW": round(r["limit_MW"], 2)}
               for r in res["lines"] if r["limit_MW"] > 0 and r["loading_pct"] >= BINDING_THRESHOLD_PCT]
    return {
        "total_cost_dollars_per_hour": round(res["total_cost"], 2),
        "lmp_by_bus": [{"bus": b, "lmp_dollars_per_MWh": round(res["lmp"][b], 2)} for b in bus_order],
        "reserve_mcp_dollars_per_MWh": round(res["mcp"], 2),
        "binding_lines": binding,
    }


def analyse(state):
    import numpy as np

    path = state["network_path"]
    fb, tb = int(state["line_from_bus"]), int(state["line_to_bus"])
    pct = float(state["capacity_increase_pct"])
    if pct <= -100:
        raise ModelError(f"capacity_increase_pct={pct} would make the limit non-positive")
    scale = 1.0 + pct / 100.0

    net = load_network(path)
    br = net["branch"]
    in_service = br[:, 10] > 0 if br.shape[1] > 10 else np.ones(len(br), bool)
    target = [k for k in range(len(br)) if in_service[k] and
              {int(br[k, 0]), int(br[k, 1])} == {fb, tb} and int(br[k, 0]) != int(br[k, 1])]
    if not target:
        near = [[int(r[0]), int(r[1])] for r in br
                if int(r[0]) in (fb, tb) or int(r[1]) in (fb, tb)][:20]
        raise ModelError(f"no in-service branch connects bus {fb} and bus {tb} (either "
                         f"orientation). Branches touching those buses: {near}")
    if any(br[k, 5] <= 0 for k in target):
        raise ModelError(f"branch {fb}-{tb} has RATE_A <= 0 (unlimited); scaling it "
                         "changes nothing")

    base_rate = br[:, 5].copy()
    cf_rate = base_rate.copy()
    cf_rate[target] *= scale   # every parallel circuit between the two buses

    bus_order = [int(b) for b in net["bus"][:, 0]]
    base = solve_market(net, base_rate)
    cf = solve_market(net, cf_rate)
    base_block, cf_block = case_block(base, bus_order), case_block(cf, bus_order)

    # Price sanity check: re-solve with +/-1 MW of load at the largest-load bus and
    # +/-1 MW of reserve requirement. The dual must lie between the left and right
    # finite differences (they differ only at a degenerate LP vertex). A sign flip or
    # a 100x/10000x gap means the dual convention is wrong -> fail rather than report.
    probe = int(np.argmax(net["bus"][:, 2]))
    probe_bus = bus_order[probe]

    def load_fd(step):
        n = dict(net, bus=net["bus"].copy())
        n["bus"][probe, 2] += step
        return (solve_market(n, base_rate)["total_cost"] - base["total_cost"]) / step

    def res_fd(step):
        n = dict(net, reserve_requirement=max(0.0, net["reserve_requirement"] + step))
        return (solve_market(n, base_rate)["total_cost"] - base["total_cost"]) / step

    def bracketed(val, a, b):
        lo, hi = min(a, b), max(a, b)
        tol = 0.02 * max(1.0, abs(lo), abs(hi))
        return lo - tol <= val <= hi + tol

    lmp_fd = (load_fd(-1.0), load_fd(1.0))
    mcp_fd = (res_fd(-1.0) if net["reserve_requirement"] >= 1.0 else res_fd(1.0), res_fd(1.0))
    price_check = {
        "probe_bus": probe_bus, "lmp_dual": round(base["lmp"][probe_bus], 4),
        "lmp_finite_diff_left_right": [round(v, 4) for v in lmp_fd],
        "mcp_dual": round(base["mcp"], 4),
        "mcp_finite_diff_left_right": [round(v, 4) for v in mcp_fd],
    }
    price_check["consistent"] = (bracketed(base["lmp"][probe_bus], *lmp_fd)
                                 and bracketed(base["mcp"], *mcp_fd))
    if not price_check["consistent"]:
        raise ModelError("dual prices disagree with finite-difference re-solves "
                         f"(sign/scale convention problem): {json.dumps(price_check)}")

    deltas = sorted(((cf["lmp"][b] - base["lmp"][b], b) for b in bus_order),
                    key=lambda d: (d[0], d[1]))
    drops = [{"bus": b, "base_lmp": round(base["lmp"][b], 2), "cf_lmp": round(cf["lmp"][b], 2),
              "delta": round(d, 2)} for d, b in deltas[:3]]

    def target_rows(res):
        return [r for r in res["lines"] if r["k"] in target]

    def is_binding(res):
        return any(r["loading_pct"] >= BINDING_THRESHOLD_PCT for r in target_rows(res))

    impact = {
        "cost_reduction_dollars_per_hour": round(base["total_cost"] - cf["total_cost"], 2),
        "buses_with_largest_lmp_drop": drops,
        # task definition: true when the adjusted line is NOT binding in the counterfactual
        "congestion_relieved": not is_binding(cf),
    }
    target_line = {
        "from_bus": fb, "to_bus": tb, "circuits": len(target),
        "branch_rows_1_indexed": [k + 1 for k in target],
        "scale_factor": scale,
        "base_limit_MW": [round(float(base_rate[k]), 4) for k in target],
        "cf_limit_MW": [round(float(cf_rate[k]), 4) for k in target],
        "base_flow_MW": [round(r["flow_MW"], 4) for r in target_rows(base)],
        "cf_flow_MW": [round(r["flow_MW"], 4) for r in target_rows(cf)],
        "base_loading_pct": [round(r["loading_pct"], 3) for r in target_rows(base)],
        "cf_loading_pct": [round(r["loading_pct"], 3) for r in target_rows(cf)],
        "binding_in_base": is_binding(base),
        "binding_in_cf": is_binding(cf),
    }
    bus = net["bus"]
    diagnostics = {
        "n_bus": len(bus), "n_gen": len(net["gen"]), "n_branch": len(br),
        "total_load_MW": round(float(bus[:, 2].sum()), 2),
        "reserve_requirement_MW": net["reserve_requirement"],
        "reserve_data_present": net["has_reserve_data"],
        "slack_buses": [int(v) for v in bus[bus[:, 1] == 3, 0]],
        "solver": {"base": f"{base['solver']}:{base['status']}", "cf": f"{cf['solver']}:{cf['status']}"},
        "base_generation_MW": round(base["gen_MW"], 2),
        "base_reserve_MW": round(base["reserve_MW"], 2),
        "n_binding_base": len(base_block["binding_lines"]),
        "n_binding_cf": len(cf_block["binding_lines"]),
        "max_abs_lmp_base": round(max(abs(v) for v in base["lmp"].values()), 2),
        "price_check": price_check,
        "cost_increased_after_relaxation":cf["total_cost"] > base["total_cost"] + 1e-6 * max(1.0, abs(base["total_cost"])),
    }
    return {
        "status": "ok", "status_detail": "both markets cleared",
        "base_case": base_block, "counterfactual": cf_block,
        "impact_analysis": impact, "target_line": target_line, "diagnostics": diagnostics,
    }


def main():
    raw = sys.stdin.buffer.read()
    if not packages_importable():
        if os.environ.get(CHILD_FLAG):
            sys.exit("bootstrapped venv still cannot import numpy/scipy/cvxpy/clarabel")
        run_in_venv(raw)
    state = json.loads(raw or b"{}").get("state", {})
    missing = [k for k in ("network_path", "line_from_bus", "line_to_bus",
                           "capacity_increase_pct") if k not in state]
    if missing:
        sys.exit(f"missing state keys: {missing}")
    try:
        out = analyse(state)
    except ModelError as e:
        out = {"status": "failed", "status_detail": str(e), "base_case": {},
               "counterfactual": {}, "impact_analysis": {}, "target_line": {},
               "diagnostics": {}}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
