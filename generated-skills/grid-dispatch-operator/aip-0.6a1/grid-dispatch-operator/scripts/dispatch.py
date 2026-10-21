#!/usr/bin/env python3
"""DC-OPF economic dispatch with spinning-reserve co-optimization (MATPOWER JSON).

Modes (argv[1]):
  solve   stdin {"state": {network_path}} -> stdout {solve_status, dispatch, diagnostics}
  verify  stdin {"state": {network_path, report_path, dispatch}} -> stdout {verification}
          Recomputes DC flows independently, checks every constraint, writes report.json.
          Exits 1 (and writes nothing) if any check fails.

Needs numpy, scipy, cvxpy (Clarabel). On a bare python3 (e.g. ubuntu:24.04 with only
python3/pip/venv) it bootstraps a venv at $GRID_DISPATCH_VENV (default
~/.cache/grid-dispatch-venv), pip-installs them there, and re-execs itself; pip output
goes to stderr so stdout stays one JSON object.
"""

import json
import os
import subprocess
import sys

PACKAGES = ["numpy", "scipy", "cvxpy", "clarabel"]


def _ensure_packages():
    try:
        import numpy, scipy, cvxpy  # noqa: F401
        return
    except ImportError:
        pass
    if os.environ.get("GRID_DISPATCH_BOOTSTRAPPED"):
        sys.exit("numpy/scipy/cvxpy still missing after venv bootstrap; install them: "
                 "python3 -m pip install --break-system-packages " + " ".join(PACKAGES))
    venv = os.environ.get("GRID_DISPATCH_VENV",
                          os.path.join(os.path.expanduser("~"), ".cache", "grid-dispatch-venv"))
    py = os.path.join(venv, "bin", "python")
    try:
        if not os.path.exists(py):
            subprocess.run([sys.executable, "-m", "venv", venv], check=True,
                           stdout=sys.stderr, stderr=sys.stderr)
        ready = subprocess.run([py, "-c", "import numpy, scipy, cvxpy, clarabel"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if not ready:
            subprocess.run([py, "-m", "pip", "install", "-q", *PACKAGES], check=True,
                           stdout=sys.stderr, stderr=sys.stderr)
    except (subprocess.CalledProcessError, OSError) as e:
        sys.exit(f"could not bootstrap solver venv at {venv}: {e}. Install manually: "
                 "python3 -m pip install --break-system-packages " + " ".join(PACKAGES))
    os.environ["GRID_DISPATCH_BOOTSTRAPPED"] = "1"
    os.execv(py, [py, os.path.abspath(__file__), *sys.argv[1:]])


_ensure_packages()

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import scipy.sparse.linalg as spla  # noqa: E402

TOL_MW = 1e-3  # feasibility tolerance for verification (MW)


def _path(p):
    # aip runs scripts from their own folder; relative paths are relative to the run's workdir.
    return p if os.path.isabs(p) else os.path.join(os.environ.get("AIP_WORKDIR", os.getcwd()), p)


def load_network(path):
    path = _path(path)
    if not os.path.exists(path):
        raise SystemExit(f"network file not found: {path}")
    with open(path) as f:
        data = json.load(f)
    for key in ("baseMVA", "bus", "gen", "branch", "gencost"):
        if key not in data:
            raise SystemExit(f"{path}: missing MATPOWER field '{key}'")
    net = {
        "baseMVA": float(data["baseMVA"]),
        "bus": np.array(data["bus"], dtype=float),
        "gen": np.array(data["gen"], dtype=float),
        "branch": np.array(data["branch"], dtype=float),
        "gencost": np.array(data["gencost"], dtype=float) if _rectangular(data["gencost"])
        else data["gencost"],
    }
    n_gen = len(net["gen"])
    gen = net["gen"]
    # Reserve fields are optional: absent -> no requirement, capacity limited only by Pmax.
    if "reserve_capacity" in data:
        rc = np.array(data["reserve_capacity"], dtype=float)
        if len(rc) != n_gen:
            raise SystemExit(f"reserve_capacity has {len(rc)} entries for {n_gen} generators")
    else:
        rc = gen[:, 8].copy() if gen.ndim == 2 and gen.shape[1] > 8 else np.zeros(n_gen)
    net["reserve_capacity"] = rc
    net["reserve_requirement"] = float(data.get("reserve_requirement", 0.0) or 0.0)
    net["reserve_fields_present"] = "reserve_capacity" in data and "reserve_requirement" in data
    return net


def _rectangular(rows):
    return len({len(r) for r in rows}) <= 1


def topology(net):
    bus, gen, br = net["bus"], net["gen"], net["branch"]
    n_bus = len(bus)
    # Bus numbers can be non-contiguous: always map number -> row index.
    idx = {int(bus[i, 0]): i for i in range(n_bus)}
    gen_on = gen[:, 7] > 0 if gen.shape[1] > 7 else np.ones(len(gen), bool)
    br_on = br[:, 10] > 0 if br.shape[1] > 10 else np.ones(len(br), bool)
    x = br[:, 3]
    active = br_on & (x != 0)  # x == 0 branches carry no DC flow (source convention: b = 0)
    b = np.where(active, 1.0 / np.where(x != 0, x, 1.0), 0.0)
    f = np.array([idx[int(v)] for v in br[:, 0]])
    t = np.array([idx[int(v)] for v in br[:, 1]])
    gbus = np.array([idx[int(v)] for v in gen[:, 0]])
    n_br = len(br)
    A = sp.csr_matrix((np.r_[np.ones(n_br), -np.ones(n_br)],
                       (np.r_[np.arange(n_br), np.arange(n_br)], np.r_[f, t])),
                      shape=(n_br, n_bus))
    Bf = sp.diags(b) @ A            # branch flow (pu) = Bf @ theta
    Bbus = (A.T @ Bf).tocsr()       # nodal injection (pu) = Bbus @ theta
    slack = np.where(bus[:, 1] == 3)[0]
    slack = int(slack[0]) if len(slack) else 0
    Cg = sp.csr_matrix((np.ones(len(gen)), (gbus, np.arange(len(gen)))),
                       shape=(n_bus, len(gen)))
    return dict(idx=idx, gen_on=gen_on, br_on=br_on, active=active, b=b, f=f, t=t,
                Bf=Bf.tocsr(), Bbus=Bbus, slack=slack, Cg=Cg, slack_found=bool(len(bus) and (bus[:, 1] == 3).any()))


def gen_cost_terms(gc_row):
    """Return ('poly', [c_high..c0]) or ('pwl', [(p, c), ...]) for one gencost row."""
    model, ncost = int(gc_row[0]), int(gc_row[3])
    if model == 2:
        return "poly", [float(c) for c in gc_row[4:4 + ncost]]
    if model == 1:
        pts = [(float(gc_row[4 + 2 * k]), float(gc_row[5 + 2 * k])) for k in range(ncost)]
        return "pwl", pts
    raise SystemExit(f"unsupported gencost MODEL {model}")


def eval_cost(gc_row, p):
    kind, c = gen_cost_terms(gc_row)
    if kind == "poly":
        return float(sum(ci * p ** (len(c) - 1 - k) for k, ci in enumerate(c)))
    # Convex piecewise linear: the max over segment lines (matches the epigraph in solve).
    return float(max(y0 + (y1 - y0) / (x1 - x0) * (p - x0)
                     for (x0, y0), (x1, y1) in zip(c[:-1], c[1:])))


def prechecks(net, topo):
    gen, bus = net["gen"], net["bus"]
    on = topo["gen_on"]
    load = float(bus[:, 2].sum())
    pmax = float(gen[on, 8].sum())
    pmin = float(gen[on, 9].sum())
    rc = net["reserve_capacity"]
    R = net["reserve_requirement"]
    max_res = float(np.minimum(np.maximum(rc[on], 0), np.maximum(gen[on, 8] - gen[on, 9], 0)).sum())
    return {
        "n_bus": int(len(bus)), "n_gen": int(len(gen)), "n_gen_in_service": int(on.sum()),
        "n_branch": int(len(net["branch"])), "n_branch_in_service": int(topo["br_on"].sum()),
        "n_branch_zero_x": int((topo["br_on"] & (net["branch"][:, 3] == 0)).sum()),
        "n_branch_unlimited_rateA": int((topo["active"] & (net["branch"][:, 5] <= 0)).sum()),
        "slack_bus": int(bus[topo["slack"], 0]), "slack_bus_type3_found": topo["slack_found"],
        "reserve_fields_present": net["reserve_fields_present"],
        "load_MW": round(load, 2), "pmax_total_MW": round(pmax, 2), "pmin_total_MW": round(pmin, 2),
        "reserve_requirement_MW": round(R, 2), "reserve_capacity_total_MW": round(float(rc[on].sum()), 2),
        "max_deliverable_reserve_MW": round(max_res, 2),
        "check_pmin_le_load": pmin <= load + TOL_MW,
        "check_load_le_pmax": load <= pmax + TOL_MW,
        "check_reserve_capacity_ge_requirement": max_res >= R - TOL_MW,
        "check_pmax_ge_load_plus_reserve": pmax >= load + R - TOL_MW,
    }


def data_errors(net):
    """Problems that make the model meaningless; reported as solve_status 'failed'."""
    errs = []
    for key, ncol in (("bus", 3), ("gen", 10), ("branch", 6)):
        a = net[key]
        if a.ndim != 2 or not len(a) or a.shape[1] < ncol:
            errs.append(f"{key}: empty, ragged, or fewer than {ncol} MATPOWER columns")
        elif not np.isfinite(a).all():
            rows = sorted({int(r) for r in np.argwhere(~np.isfinite(a))[:, 0]})
            errs.append(f"{key}: non-finite or null values in rows {rows[:10]}")
    if not np.isfinite(net["reserve_capacity"]).all() or not np.isfinite(net["reserve_requirement"]):
        errs.append("reserve data: non-finite or null values")
    gc = net["gencost"]
    if len(gc) < len(net["gen"]):
        errs.append(f"gencost has {len(gc)} rows for {len(net['gen'])} generators")
    if errs:
        return errs
    nums = {int(v) for v in net["bus"][:, 0]}
    for key, cols in (("gen", (0,)), ("branch", (0, 1))):
        bad = sorted({int(r[c]) for r in net[key] for c in cols if int(r[c]) not in nums})
        if bad:
            errs.append(f"{key} references unknown bus numbers {bad[:10]}")
    if not (net["bus"][:, 1] == 3).any():
        errs.append("no slack bus (BUS_TYPE 3); first bus would be used as reference")
    return errs


def solve(state):
    import cvxpy as cp
    import time

    net = load_network(state["network_path"])
    errs = data_errors(net)
    fatal = [e for e in errs if not e.startswith("no slack bus")]
    if fatal:
        return {"solve_status": "failed", "dispatch": {},
                "diagnostics": {"data_errors": errs, "solver": None, "solver_attempts": []}}
    topo = topology(net)
    diag = prechecks(net, topo)
    diag["data_errors"] = errs
    gen, bus, br, gc = net["gen"], net["bus"], net["branch"], net["gencost"]
    base = net["baseMVA"]
    n_bus, n_gen = len(bus), len(gen)
    on = topo["gen_on"]

    # Scaling follows the source skills: Pg in per-unit, Rg in MW, theta in rad.
    # Reserves are unpriced, so reserve above the requirement is degenerate; keeping the
    # sources' scaling keeps CLARABEL on the same (interior) point they produce.
    Pg = cp.Variable(n_gen)      # pu
    Rg = cp.Variable(n_gen)      # MW
    th = cp.Variable(n_bus)      # rad
    Pg_MW = Pg * base
    pmax = np.where(on, gen[:, 8], 0.0)
    pmin = np.where(on, gen[:, 9], 0.0)
    rcap = np.where(on, np.maximum(net["reserve_capacity"], 0.0), 0.0)

    cons = [Pg >= pmin / base, Pg <= pmax / base,
            Rg >= 0, Rg <= rcap,
            Pg_MW + Rg <= pmax,                               # capacity coupling
            cp.sum(Rg) >= net["reserve_requirement"],
            topo["Cg"] @ Pg - bus[:, 2] / base == topo["Bbus"] @ th,  # DC nodal balance (pu)
            th[topo["slack"]] == 0]
    rate = br[:, 5]
    lim = topo["active"] & (rate > 0)  # RATE_A == 0 means unlimited (MATPOWER)
    if lim.any():
        flow = (topo["Bf"][lim] @ th) * base
        cons += [flow <= rate[lim], flow >= -rate[lim]]

    # Objective: in-service generators only; first n_gen gencost rows are the P costs.
    gcr = [gc[i] for i in range(n_gen)]
    quad, lin, const, pwl_terms = np.zeros(n_gen), np.zeros(n_gen), 0.0, []
    for i in np.where(on)[0]:
        kind, c = gen_cost_terms(gcr[i])
        if kind == "poly":
            n = len(c)
            if n > 3:
                raise SystemExit(f"generator {i + 1}: polynomial cost of degree {n - 1} unsupported")
            if n == 3:
                quad[i], lin[i], const = c[0], c[1], const + c[2]
            elif n == 2:
                lin[i], const = c[0], const + c[1]
            elif n == 1:
                const += c[0]
        else:
            pwl_terms.append((i, c))
    if (quad < 0).any():
        raise SystemExit("negative quadratic cost coefficient: problem is non-convex")
    obj = quad @ cp.square(Pg_MW) + lin @ Pg_MW + const
    if pwl_terms:
        z = cp.Variable(len(pwl_terms))
        for k, (i, pts) in enumerate(pwl_terms):
            for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
                cons.append(z[k] >= y0 + (y1 - y0) / (x1 - x0) * (Pg_MW[i] - x0))
        obj = obj + cp.sum(z)

    prob = cp.Problem(cp.Minimize(obj), cons)
    status, used, t0 = None, None, time.time()
    order = ["CLARABEL", "HIGHS", "OSQP", "SCS"]
    attempts = []
    for s in [s for s in order if s in cp.installed_solvers()]:
        try:
            prob.solve(solver=s)
        except Exception as e:  # solver crash: try the next one
            attempts.append(f"{s}: {type(e).__name__}: {e}"[:300])
            continue
        attempts.append(f"{s}: {prob.status}")
        if prob.status in ("optimal", "optimal_inaccurate"):
            status, used = "optimal", s
            break
        if prob.status in ("infeasible", "infeasible_inaccurate"):
            status, used = "infeasible", s
            break
    diag.update(solver=used, solver_attempts=attempts, solve_seconds=round(time.time() - t0, 2))
    if status is None:
        status = "failed"
    if status != "optimal":
        return {"solve_status": status, "dispatch": {}, "diagnostics": diag}

    pg = np.where(on, Pg.value * base, 0.0)
    rg = np.where(on, np.maximum(Rg.value, 0.0), 0.0)
    dispatch = {"Pg_MW": [float(v) for v in pg], "Rg_MW": [float(v) for v in rg],
                "objective_dollars_per_hour": float(prob.value)}
    return {"solve_status": "optimal", "dispatch": dispatch, "diagnostics": diag}


def build_report(net, topo, pg, rg, flows):
    gen, bus, br = net["gen"], net["bus"], net["branch"]
    on = topo["gen_on"]
    cost = sum(eval_cost(net["gencost"][i], pg[i]) for i in np.where(on)[0])
    rate = br[:, 5]
    loading = np.where(topo["active"] & (rate > 0), np.abs(flows) / np.where(rate > 0, rate, 1) * 100, 0.0)
    top = np.argsort(-loading, kind="stable")[:3]
    return {
        "generator_dispatch": [
            {"id": i + 1, "bus": int(gen[i, 0]), "output_MW": round(float(pg[i]), 2),
             "reserve_MW": round(float(rg[i]), 2), "pmax_MW": round(float(gen[i, 8]), 2)}
            for i in range(len(gen))],
        "totals": {
            "cost_dollars_per_hour": round(float(cost), 2),
            "load_MW": round(float(bus[:, 2].sum()), 2),
            "generation_MW": round(float(pg.sum()), 2),
            "reserve_MW": round(float(rg.sum()), 2),
        },
        "most_loaded_lines": [
            {"from": int(br[k, 0]), "to": int(br[k, 1]), "loading_pct": round(float(loading[k]), 2)}
            for k in top],
        "operating_margin_MW": round(float((gen[on, 8] - pg[on] - rg[on]).sum()), 2),
    }, loading


def verify(state):
    net = load_network(state["network_path"])
    topo = topology(net)
    gen, bus, br = net["gen"], net["bus"], net["branch"]
    base = net["baseMVA"]
    d = state["dispatch"]
    pg, rg = np.array(d["Pg_MW"], float), np.array(d["Rg_MW"], float)
    on = topo["gen_on"]

    # Independent DC power flow: reduce out the slack row/col and solve B' theta = P.
    inj = (topo["Cg"] @ pg - bus[:, 2]) / base
    keep = np.array([i for i in range(len(bus)) if i != topo["slack"]])
    th = np.zeros(len(bus))
    th[keep] = spla.spsolve(topo["Bbus"][keep][:, keep].tocsc(), inj[keep])
    flows = base * (topo["Bf"] @ th)
    mismatch = base * (topo["Bbus"] @ th) - (topo["Cg"] @ pg - bus[:, 2])

    report, loading = build_report(net, topo, pg, rg, flows)
    rate = br[:, 5]
    lim = topo["active"] & (rate > 0)
    over = np.abs(flows[lim]) - rate[lim]
    tol_pct = 0.01
    checks = {
        "system_balance_MW": float(pg.sum() - bus[:, 2].sum()),
        "max_nodal_mismatch_MW": float(np.abs(mismatch).max()),
        "max_pmin_violation_MW": float(np.maximum(gen[on, 9] - pg[on], 0).max(initial=0)),
        "max_pmax_coupling_violation_MW": float(np.maximum(pg[on] + rg[on] - gen[on, 8], 0).max(initial=0)),
        "max_reserve_cap_violation_MW": float(np.maximum(rg[on] - net["reserve_capacity"][on], 0).max(initial=0)),
        "reserve_shortfall_MW": float(max(net["reserve_requirement"] - rg.sum(), 0)),
        "max_line_overload_MW": float(max(over.max(initial=-np.inf), 0)),
        "max_loading_pct": float(loading.max(initial=0)),
        "n_lines_at_or_above_99pct": int((loading >= 99.0).sum()),
        "solver_objective_minus_report_cost": float(d.get("objective_dollars_per_hour", np.nan)
                                                    - report["totals"]["cost_dollars_per_hour"]),
    }
    failed = [k for k, v in [
        ("system_balance_MW", abs(checks["system_balance_MW"]) <= 0.05),
        ("max_nodal_mismatch_MW", checks["max_nodal_mismatch_MW"] <= 0.05),
        ("max_pmin_violation_MW", checks["max_pmin_violation_MW"] <= 0.01),
        ("max_pmax_coupling_violation_MW", checks["max_pmax_coupling_violation_MW"] <= 0.01),
        ("max_reserve_cap_violation_MW", checks["max_reserve_cap_violation_MW"] <= 0.01),
        ("reserve_shortfall_MW", checks["reserve_shortfall_MW"] <= 0.01),
        ("max_loading_pct", checks["max_loading_pct"] <= 100 + tol_pct),
    ] if not v]
    if failed:
        sys.stderr.write(json.dumps({"failed_checks": failed, "checks": checks}, indent=1) + "\n")
        sys.exit(f"verification failed ({', '.join(failed)}); report not written")
    out_path = _path(state["report_path"])
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    return {"verification": {"report_path": os.path.abspath(out_path),
                             "checks": checks, "totals": report["totals"],
                             "most_loaded_lines": report["most_loaded_lines"],
                             "operating_margin_MW": report["operating_margin_MW"]}}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "solve"
    payload = json.load(sys.stdin)
    state = payload.get("state", payload)
    if mode == "solve":
        out = solve(state)
    elif mode == "verify":
        out = verify(state)
    else:
        sys.exit(f"unknown mode {mode!r}; use solve or verify")
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
