#!/usr/bin/env python3
"""Economic dispatch / DC-OPF with optional reserve co-optimization on a MATPOWER-style network.json.

AIP execution step. stdin: {"currentState", "assets", "expects"}; stdout: one JSON object.
Can also run by hand: `python3 solve_dispatch.py --network network.json [--out report.json]
[--no-reserves] [--copper-plate] [--top-n 3]`.

Needs numpy, scipy, cvxpy. When they are missing the script bootstraps a venv
(default ~/.cache/grid-dispatch/venv, override with GRID_DISPATCH_VENV), pip-installs
them there, and re-runs itself with that interpreter. Install chatter goes to stderr.
"""

import json
import os
import subprocess
import sys

REQUIREMENTS = ["numpy", "scipy", "cvxpy"]


# ---------------------------------------------------------------- bootstrap

def _have_deps():
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import cvxpy  # noqa: F401
        return True
    except Exception:  # ImportError, or a broken binary wheel on PYTHONPATH
        return False


def _bootstrap_and_rerun(payload):
    venv = os.environ.get("GRID_DISPATCH_VENV") or os.path.join(
        os.path.expanduser("~"), ".cache", "grid-dispatch", "venv")
    vpy = os.path.join(venv, "bin", "python")
    if os.path.abspath(sys.prefix) == os.path.abspath(venv):
        raise RuntimeError(f"dependencies {REQUIREMENTS} still missing inside {venv}")
    log = sys.stderr
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # a foreign site-packages would mask what the venv really has
    if not os.path.exists(vpy):
        print(f"[grid-dispatch] creating venv at {venv}", file=log)
        r = subprocess.run([sys.executable, "-m", "venv", venv], stdout=log, stderr=log)
        if r.returncode != 0:
            # python3-venv missing: try a user install instead and re-check in-process
            subprocess.run([sys.executable, "-m", "pip", "install", "--user", "-q",
                            "--break-system-packages", *REQUIREMENTS], stdout=log, stderr=log)
            if _have_deps():
                return None
            raise RuntimeError("could not create a venv or pip-install " + " ".join(REQUIREMENTS))
    chk = subprocess.run([vpy, "-c", "import numpy, scipy, cvxpy"], stdout=log,
                         stderr=subprocess.DEVNULL, env=env)
    if chk.returncode != 0:
        print(f"[grid-dispatch] installing {REQUIREMENTS}", file=log)
        r = subprocess.run([vpy, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                            *REQUIREMENTS], stdout=log, stderr=log, env=env)
        if r.returncode != 0:
            raise RuntimeError("pip install failed for " + " ".join(REQUIREMENTS))
    r = subprocess.run([vpy, os.path.abspath(__file__), *sys.argv[1:]], input=payload,
                       stdout=subprocess.PIPE, env=env)
    sys.stdout.buffer.write(r.stdout)
    sys.exit(r.returncode)


# ---------------------------------------------------------------- model

def _cost_expr(cp, gc_row, p):
    """Cost of one generator ($/hr) for MW expression/value p; returns (expr, aux_constraints)."""
    model, ncost = int(gc_row[0]), int(gc_row[3])
    c = gc_row[4:]
    if model == 2:  # polynomial, highest order first
        if ncost >= 3:
            c2, c1, c0 = c[ncost - 3], c[ncost - 2], c[ncost - 1]
            if ncost > 3 and any(abs(x) > 0 for x in c[:ncost - 3]):
                raise ValueError("polynomial costs above quadratic are not supported")
            expr = c1 * p + c0
            if c2 != 0:
                expr = c2 * cp.square(p) + expr
            return expr, []
        if ncost == 2:
            return c[0] * p + c[1], []
        return (c[0] if ncost >= 1 else 0.0), []
    if model == 1:  # piecewise linear: N breakpoints (P1,C1)...(Pn,Cn), convex epigraph
        pts = [(c[2 * k], c[2 * k + 1]) for k in range(ncost)]
        t = cp.Variable()
        cons = []
        for (pa, ca), (pb, cb) in zip(pts[:-1], pts[1:]):
            slope = (cb - ca) / (pb - pa) if pb != pa else 0.0
            cons.append(t >= ca + slope * (p - pa))
        return t, cons
    raise ValueError(f"unknown gencost MODEL {model}")


def solve(network_path, co_optimize_reserves=True, network_constrained=True, top_n_lines=3,
          output_path="", matpower_taps=False):
    import numpy as np
    import scipy.sparse as sp
    import cvxpy as cp

    with open(network_path) as f:
        data = json.load(f)

    baseMVA = float(data["baseMVA"])
    buses = np.array(data["bus"], dtype=float)
    gens = np.array(data["gen"], dtype=float)
    branches = np.array(data["branch"], dtype=float)
    gencost = data["gencost"]  # rows may differ in length; keep as lists
    n_bus, n_gen, n_br = len(buses), len(gens), len(branches)

    has_reserve_data = "reserve_capacity" in data and "reserve_requirement" in data
    use_reserves = bool(co_optimize_reserves and has_reserve_data)
    notes = []
    if co_optimize_reserves and not has_reserve_data:
        notes.append("reserves requested but network file has no reserve_capacity/reserve_requirement; solved without reserves")

    # bus number -> 0-indexed position (bus numbers may be non-contiguous)
    bus_num_to_idx = {int(buses[i, 0]): i for i in range(n_bus)}
    gen_bus = np.array([bus_num_to_idx[int(g[0])] for g in gens], dtype=int)
    gen_on = gens[:, 7] > 0 if gens.shape[1] > 7 else np.ones(n_gen, bool)
    pmax = gens[:, 8]
    pmin = gens[:, 9]
    pd = buses[:, 2]
    total_load = float(pd.sum())

    br_on = branches[:, 10] > 0 if branches.shape[1] > 10 else np.ones(n_br, bool)
    f_idx = np.array([bus_num_to_idx[int(b[0])] for b in branches], dtype=int)
    t_idx = np.array([bus_num_to_idx[int(b[1])] for b in branches], dtype=int)
    x = branches[:, 3]
    # b = 1/X as in the curated sources; matpower_taps=True uses MATPOWER's DC model
    # (b = 1/(X*TAP), TAP 0 -> 1, plus phase-shift injections from SHIFT)
    tap = np.where(branches[:, 8] == 0, 1.0, branches[:, 8]) if matpower_taps else np.ones(n_br)
    phi = np.deg2rad(branches[:, 9]) if matpower_taps else np.zeros(n_br)
    bsus = np.where((x != 0) & br_on, 1.0 / np.where(x != 0, x * tap, 1.0), 0.0)
    pshift = bsus * phi  # pu flow offset per branch
    rate = branches[:, 5]  # RATE_A, MW; 0 = unlimited

    slack = [i for i in range(n_bus) if buses[i, 1] == 3]
    slack_idx = slack[0] if slack else 0
    if not slack:
        notes.append("no type-3 slack bus; used first bus as angle reference")

    # sparse incidence A (n_br x n_bus) and generator map Cg (n_bus x n_gen)
    rows = np.arange(n_br)
    A = sp.csr_matrix((np.r_[np.ones(n_br), -np.ones(n_br)], (np.r_[rows, rows], np.r_[f_idx, t_idx])),
                      shape=(n_br, n_bus))
    Cg = sp.csr_matrix((np.ones(n_gen), (gen_bus, np.arange(n_gen))), shape=(n_bus, n_gen))
    Bf = sp.diags(bsus) @ A  # flow_pu = Bf @ theta

    Pg = cp.Variable(n_gen)  # MW
    lo = np.where(gen_on, pmin, 0.0)
    hi = np.where(gen_on, pmax, 0.0)
    cons = [Pg >= lo, Pg <= hi]

    cost = 0
    for i in range(n_gen):
        expr, aux = _cost_expr(cp, gencost[i], Pg[i])
        cost = cost + expr
        cons += aux

    theta = None
    if network_constrained:
        theta = cp.Variable(n_bus)  # radians
        flow = baseMVA * (Bf @ theta - pshift)  # MW
        # nodal balance: Pg - Pd = B theta  (B = A^T diag(b) A)
        cons += [Cg @ Pg - pd == A.T @ flow, theta[slack_idx] == 0]
        lim = np.where(br_on & (rate > 0))[0]
        if len(lim):
            cons += [flow[lim] <= rate[lim], flow[lim] >= -rate[lim]]
    else:
        cons.append(cp.sum(Pg) == total_load)

    Rg = None
    if use_reserves:
        rcap = np.array(data["reserve_capacity"], dtype=float)
        rreq = float(data["reserve_requirement"])
        Rg = cp.Variable(n_gen)  # MW
        cons += [Rg >= 0, Rg <= np.where(gen_on, rcap, 0.0), Pg + Rg <= hi, cp.sum(Rg) >= rreq]

    # reserves are free; a negligible price makes the solver procure exactly what is required,
    # so total reserve and operating margin are unique (reported cost excludes this term)
    objective = cost + (1e-6 * cp.sum(Rg) if Rg is not None else 0)
    prob = cp.Problem(cp.Minimize(objective), cons)
    status, solver_used, errors = None, None, []
    # quadratic costs: CLARABEL (robust interior point, per the sources). All-linear costs make an LP:
    # HiGHS first, whose vertex solution is exact (reserves land exactly on the requirement).
    is_lp = all(not (int(r[0]) == 2 and int(r[3]) >= 3 and r[4 + int(r[3]) - 3] != 0) for r in gencost)
    order = ["HIGHS", "CLARABEL"] if is_lp else ["CLARABEL", "HIGHS"]
    for solver in order + ["ECOS", "SCS", "OSQP"]:
        if solver not in cp.installed_solvers():
            continue
        try:
            prob.solve(solver=solver)
            status, solver_used = prob.status, solver
            if status in ("optimal", "optimal_inaccurate"):
                break
        except Exception as e:  # solver failure: try next
            errors.append(f"{solver}: {e}")
    if status not in ("optimal", "optimal_inaccurate"):
        return {
            "solve_status": "failed",
            "solver_status": status or "error",
            "solver_errors": errors,
            "diagnostics": {
                "load_MW": round(total_load, 2),
                "sum_pmax_MW": round(float(hi.sum()), 2),
                "sum_pmin_MW": round(float(lo.sum()), 2),
                "reserve_requirement_MW": data.get("reserve_requirement"),
                "sum_reserve_capacity_MW": round(float(sum(data.get("reserve_capacity", []))), 2),
                "network_constrained": network_constrained,
                "co_optimize_reserves": use_reserves,
            },
            "notes": notes,
        }

    # clip solver tolerance noise so rounded values never cross a limit
    Pg_MW = np.clip(np.asarray(Pg.value, dtype=float), lo, hi)
    if Rg is not None:
        rcap_on = np.where(gen_on, np.array(data["reserve_capacity"], dtype=float), 0.0)
        Rg_MW = np.clip(np.asarray(Rg.value, dtype=float), 0.0, np.minimum(rcap_on, hi - Pg_MW))
    else:
        Rg_MW = np.zeros(n_gen)

    # bus angles: from the OPF, or a DC power flow of the dispatch on the copper-plate path
    if theta is not None:
        th = np.asarray(theta.value, dtype=float)
    else:
        import scipy.sparse.linalg as spla
        B = (A.T @ sp.diags(bsus) @ A).tocsc()
        pinj = (Cg @ Pg_MW - pd) / baseMVA + A.T @ pshift
        keep = np.array([i for i in range(n_bus) if i != slack_idx])
        th = np.zeros(n_bus)
        th[keep] = spla.spsolve(B[keep][:, keep], pinj[keep])
    flow_MW = baseMVA * (Bf @ th - pshift)

    line_rows = []
    for k in range(n_br):
        if not br_on[k]:
            continue
        lp = abs(flow_MW[k]) / rate[k] * 100 if rate[k] > 0 else 0.0
        line_rows.append((lp, k))
    line_rows.sort(key=lambda r: (-round(r[0], 2), r[1]))  # ties (e.g. many at 100%) by branch order

    def line(k, lp):
        return {"branch_index": k + 1, "from": int(branches[k, 0]), "to": int(branches[k, 1]),
                "flow_MW": round(float(flow_MW[k]), 2), "limit_MW": round(float(rate[k]), 2),
                "loading_pct": round(float(lp), 2)}

    most_loaded = [line(k, lp) for lp, k in line_rows[:max(int(top_n_lines), 0)]]
    # binding = at a thermal limit the OPF enforced; only meaningful when network-constrained
    binding = [line(k, lp) for lp, k in line_rows if lp >= 99.9] if network_constrained else []
    overloaded = [line(k, lp) for lp, k in line_rows if lp > 100.5]

    def poly_cost(row, p):  # numeric check of the objective for polynomial costs
        n = int(row[3])
        return sum(row[4 + j] * p ** (n - 1 - j) for j in range(n))

    gen_cost = sum(poly_cost(gencost[i], Pg_MW[i]) for i in range(n_gen) if int(gencost[i][0]) == 2)
    cost_value = float(cost.value) if hasattr(cost, "value") else float(cost)

    generator_dispatch = [{
        "id": i + 1,
        "bus": int(gens[i, 0]),
        "output_MW": round(float(Pg_MW[i]), 2),
        "reserve_MW": round(float(Rg_MW[i]), 2),
        "pmax_MW": round(float(pmax[i]), 2),
    } for i in range(n_gen)]

    total_gen = float(Pg_MW.sum())
    total_res = float(Rg_MW.sum())
    operating_margin = float(np.sum(hi - Pg_MW - Rg_MW))

    report = {
        "generator_dispatch": generator_dispatch,
        "totals": {
            "cost_dollars_per_hour": round(cost_value, 2),
            "load_MW": round(total_load, 2),
            "generation_MW": round(total_gen, 2),
            "reserve_MW": round(total_res, 2),
        },
        "most_loaded_lines": [{"from": l["from"], "to": l["to"], "loading_pct": l["loading_pct"]}
                              for l in most_loaded],
        "operating_margin_MW": round(operating_margin, 2),
    }

    checks = {
        "power_balance_residual_MW": round(total_gen - total_load, 4),
        "max_gen_limit_violation_MW": round(float(max(0.0, np.max(lo - Pg_MW), np.max(Pg_MW - hi))), 4),
        "max_capacity_coupling_violation_MW": round(float(max(0.0, np.max(Pg_MW + Rg_MW - hi))), 4),
        "reserve_requirement_MW": float(data["reserve_requirement"]) if use_reserves else None,
        "reserve_shortfall_MW": round(max(0.0, float(data["reserve_requirement"]) - total_res), 4) if use_reserves else None,
        "max_line_loading_pct": round(float(line_rows[0][0]), 2) if line_rows else 0.0,
        "n_binding_lines": len(binding),
        "n_overloaded_lines": len(overloaded),
        "recomputed_poly_cost": round(gen_cost, 2) if all(int(r[0]) == 2 for r in gencost) else None,
    }

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

    return {
        "solve_status": "optimal",
        "solver_status": f"{status} ({solver_used})",
        "report_summary": {
            "totals": report["totals"],
            "most_loaded_lines": most_loaded,
            "operating_margin_MW": report["operating_margin_MW"],
            "n_generators": n_gen, "n_buses": n_bus, "n_branches": n_br,
            "binding_lines": binding[:20],  # first 20; full count in checks.n_binding_lines
            "overloaded_lines": overloaded[:20],
            "network_constrained": network_constrained,
            "co_optimize_reserves": use_reserves,
            "dc_model": "matpower_taps" if matpower_taps else "b=1/X (sources)",
            "n_lines_tied_at_top_loading": sum(1 for lp, _ in line_rows
                                               if line_rows and round(lp, 2) == round(line_rows[0][0], 2)),
        },
        "checks": checks,
        "report_written_to": os.path.abspath(output_path) if output_path else "",
        "notes": notes,
    }


# ---------------------------------------------------------------- entry

def main():
    argv = sys.argv[1:]
    payload = b"" if argv else sys.stdin.buffer.read()
    if not _have_deps():
        _bootstrap_and_rerun(payload)
    if argv:
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--network", required=True)
        ap.add_argument("--out", default="")
        ap.add_argument("--no-reserves", action="store_true")
        ap.add_argument("--copper-plate", action="store_true")
        ap.add_argument("--top-n", type=int, default=3)
        ap.add_argument("--matpower-taps", action="store_true",
                        help="use b=1/(X*TAP) and SHIFT injections instead of the sources' b=1/X")
        a = ap.parse_args(argv)
        args = dict(network_path=a.network, output_path=a.out, co_optimize_reserves=not a.no_reserves,
                    network_constrained=not a.copper_plate, top_n_lines=a.top_n,
                    matpower_taps=a.matpower_taps)
    else:
        st = json.loads(payload.decode() or "{}").get("currentState", {})
        missing = [k for k in ("network_path", "output_path", "co_optimize_reserves",
                               "network_constrained", "top_n_lines") if k not in st]
        if missing:
            print(json.dumps({"solve_status": "failed", "solver_status": "error",
                              "solver_errors": [f"missing state keys: {missing}"],
                              "diagnostics": {}, "notes": []}))
            return
        # no silent defaults: the scope decision must have answered both flags
        args = dict(network_path=st["network_path"], output_path=st["output_path"],
                    co_optimize_reserves=bool(st["co_optimize_reserves"]),
                    network_constrained=bool(st["network_constrained"]),
                    top_n_lines=int(st["top_n_lines"]),
                    matpower_taps=bool(st.get("matpower_taps", False)))
    try:
        out = solve(**args)
    except Exception as e:
        out = {"solve_status": "failed", "solver_status": "error", "solver_errors": [repr(e)],
               "diagnostics": {}, "notes": []}
    print(json.dumps(out))


if __name__ == "__main__":
    main()
