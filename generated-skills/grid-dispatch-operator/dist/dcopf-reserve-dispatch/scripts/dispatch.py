#!/usr/bin/env python3
"""DC-OPF economic dispatch with spinning-reserve co-optimization (MATPOWER JSON).

Requires: python3 >= 3.9; numpy, scipy, cvxpy (with the CLARABEL solver; HiGHS/SCS
used as fallbacks when installed). `inspect` needs only the standard library.
If numpy/scipy/cvxpy are missing, the script creates a venv (default
~/.cache/dcopf-reserve-dispatch/venv, override with DCOPF_VENV), pip-installs
them there (needs network access to PyPI), and re-runs itself inside it.

Usage:
  python3 scripts/dispatch.py inspect NETWORK.json
  python3 scripts/dispatch.py solve   NETWORK.json --out report.json [--details details.json]
                                      [--top 3] [--branch-model simple|matpower]
  python3 scripts/dispatch.py check   NETWORK.json report.json [--branch-model simple|matpower]
"""
import argparse
import json
import math
import os
import subprocess
import sys

PKGS = ["numpy", "scipy", "cvxpy>=1.4", "clarabel"]


# ----------------------------------------------------------------- bootstrap
def ensure_deps():
    try:
        import numpy, scipy, cvxpy  # noqa: F401
        return
    except ImportError as exc:
        missing = str(exc)
    if os.environ.get("DCOPF_BOOTSTRAPPED"):
        sys.exit(f"ERROR: dependencies still missing inside venv ({missing}). "
                 f"Install manually: pip install {' '.join(PKGS)}")
    venv = os.environ.get("DCOPF_VENV",
                          os.path.expanduser("~/.cache/dcopf-reserve-dispatch/venv"))
    py = os.path.join(venv, "bin", "python")
    env = dict(os.environ, DCOPF_BOOTSTRAPPED="1")
    if os.path.exists(py) and subprocess.call(
            [py, "-c", "import numpy, scipy, cvxpy"], stderr=subprocess.DEVNULL) == 0:
        os.execve(py, [py, os.path.abspath(__file__), *sys.argv[1:]], env)
    print(f"[bootstrap] {missing}; preparing venv at {venv}", file=sys.stderr)
    try:
        if not os.path.exists(py):
            subprocess.check_call([sys.executable, "-m", "venv", venv])
        subprocess.check_call([py, "-m", "pip", "install", "-q",
                               "--disable-pip-version-check", *PKGS],
                              stdout=sys.stderr)
    except (subprocess.CalledProcessError, OSError) as exc:
        sys.exit(f"ERROR: bootstrap failed ({exc}). Needs python3-venv and PyPI access; "
                 f"or install manually: pip install {' '.join(PKGS)}")
    os.execve(py, [py, os.path.abspath(__file__), *sys.argv[1:]], env)


# ----------------------------------------------------------------- loading
def load_raw(path):
    with open(path) as f:
        data = json.load(f)
    for key in ("baseMVA", "bus", "gen", "branch", "gencost"):
        if key not in data:
            sys.exit(f"ERROR: {path} has no '{key}' (keys: {sorted(data)})")
    if len(data["gencost"]) < len(data["gen"]):
        sys.exit("ERROR: gencost has fewer rows than gen")
    return data


def reserve_data(data, warn):
    n_gen = len(data["gen"])
    rcap = data.get("reserve_capacity")
    req = data.get("reserve_requirement")
    if rcap is None:
        warn.append("no reserve_capacity: every generator's reserve capacity treated as 0")
        rcap = [0.0] * n_gen
    if req is None:
        warn.append("no reserve_requirement: system reserve requirement treated as 0")
        req = 0.0
    if len(rcap) != n_gen:
        sys.exit(f"ERROR: reserve_capacity has {len(rcap)} entries, gen has {n_gen}")
    return [float(r) for r in rcap], float(req)


def inspect(path):
    data = load_raw(path)
    warn = []
    bus, gen, br, gc = data["bus"], data["gen"], data["branch"], data["gencost"]
    rcap, req = reserve_data(data, warn)
    on = [len(g) <= 7 or g[7] > 0 for g in gen]
    br_on = [len(b) <= 10 or b[10] > 0 for b in br]
    bus_nums = [int(b[0]) for b in bus]
    num_set = set(bus_nums)
    bad = [int(g[0]) for g in gen if int(g[0]) not in num_set] + \
          [int(b[k]) for b in br for k in (0, 1) if int(b[k]) not in num_set]
    if bad:
        warn.append(f"generator/branch rows reference unknown buses: {sorted(set(bad))[:10]}")
    load = sum(b[2] for b in bus)
    pmax = sum(g[8] for g, o in zip(gen, on) if o)
    pmin = sum(g[9] for g, o in zip(gen, on) if o)
    rmax = sum(min(r, g[8]) for r, g, o in zip(rcap, gen, on) if o)
    models = {}
    for row in gc[:len(gen)]:
        k = f"model{int(row[0])}_n{int(row[3])}"
        models[k] = models.get(k, 0) + 1
    quad_neg = sum(1 for row in gc[:len(gen)] if int(row[0]) == 2 and int(row[3]) >= 3 and row[4] < 0)
    if quad_neg:
        warn.append(f"{quad_neg} generators have negative quadratic coefficient (non-convex)")
    if any(int(r[0]) == 2 and int(r[3]) > 3 for r in gc[:len(gen)]):
        warn.append("polynomial cost above degree 2 present: not supported by solve")
    slack = [int(b[0]) for b in bus if int(b[1]) == 3]
    if len(slack) != 1:
        warn.append(f"{len(slack)} slack (type 3) buses: {slack[:5]}; one angle reference "
                    "per connected island is fixed automatically")
    iso = [int(b[0]) for b in bus if int(b[1]) == 4]
    if iso:
        warn.append(f"{len(iso)} isolated (type 4) buses; their load still counts")
    shift = sum(1 for b, o in zip(br, br_on) if o and len(b) > 9 and b[9] != 0)
    tap = sum(1 for b, o in zip(br, br_on) if o and len(b) > 8 and b[8] not in (0, 1))
    rate0 = sum(1 for b, o in zip(br, br_on) if o and b[5] == 0)
    x0 = sum(1 for b, o in zip(br, br_on) if o and b[3] == 0)
    if x0:
        warn.append(f"{x0} in-service branches with x=0: no DC flow modeled on them")
    if pmin > load:
        warn.append("sum Pmin of online units exceeds load: infeasible")
    if load > pmax:
        warn.append("load exceeds online Pmax: infeasible")
    if load + req > pmax + 1e-6:
        warn.append("load + reserve requirement exceeds online Pmax: infeasible")
    if req > rmax + 1e-6:
        warn.append("reserve requirement exceeds sum of min(reserve_capacity, Pmax): infeasible")
    out = {
        "file": path, "baseMVA": data["baseMVA"],
        "n_bus": len(bus), "n_gen": len(gen), "n_gen_online": sum(on),
        "n_branch": len(br), "n_branch_in_service": sum(br_on),
        "bus_numbers_contiguous": bus_nums == list(range(1, len(bus) + 1)),
        "slack_buses": slack,
        "total_load_MW": round(load, 3),
        "online_pmax_MW": round(pmax, 3), "online_pmin_MW": round(pmin, 3),
        "reserve_requirement_MW": req, "max_deliverable_reserve_MW": round(rmax, 3),
        "gencost_models": models,
        "branches_rateA_0_unlimited": rate0, "branches_phase_shift": shift,
        "branches_offnominal_tap": tap,
        "extra_keys": sorted(set(data) - {"name", "description", "baseMVA", "bus", "gen",
                                          "branch", "gencost", "reserve_capacity",
                                          "reserve_requirement", "column_info"}),
        "warnings": warn,
    }
    print(json.dumps(out, indent=2))


# ----------------------------------------------------------------- network model
def build_model(data, branch_model):
    import numpy as np
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components

    base = float(data["baseMVA"])
    bus = np.array(data["bus"], dtype=float)
    gen = np.array(data["gen"], dtype=float)
    br = np.array(data["branch"], dtype=float)
    n_bus, n_gen = len(bus), len(gen)
    idx = {int(bus[i, 0]): i for i in range(n_bus)}          # bus number -> position
    gen_on = gen[:, 7] > 0 if gen.shape[1] > 7 else np.ones(n_gen, bool)
    br_on = br[:, 10] > 0 if br.shape[1] > 10 else np.ones(len(br), bool)
    keep = np.where(br_on & (br[:, 3] != 0))[0]               # modeled branches
    f = np.array([idx[int(v)] for v in br[:, 0]])
    t = np.array([idx[int(v)] for v in br[:, 1]])
    x = br[:, 3]
    b = np.zeros(len(br))
    if branch_model == "matpower":
        tap = br[:, 8].copy() if br.shape[1] > 8 else np.ones(len(br))
        tap[tap == 0] = 1.0
        b[keep] = 1.0 / (x[keep] * tap[keep])
        shift = np.deg2rad(br[:, 9]) if br.shape[1] > 9 else np.zeros(len(br))
    else:  # simple: b = 1/x, taps and phase shifts ignored
        b[keep] = 1.0 / x[keep]
        shift = np.zeros(len(br))
    k = keep
    A = sp.csr_matrix((np.r_[np.ones(len(k)), -np.ones(len(k))],
                       (np.r_[np.arange(len(k)), np.arange(len(k))], np.r_[f[k], t[k]])),
                      shape=(len(k), n_bus))                  # incidence of modeled branches
    Bf = sp.diags(b[k]) @ A                                   # flow_pu = Bf theta + Pfinj
    Bbus = (A.T @ Bf).tocsr()
    pfinj = -b[k] * shift[k]                                  # MATPOWER phase-shift injection
    pbusinj = A.T @ pfinj
    gbus = np.array([idx[int(v)] for v in gen[:, 0]])
    Cg = sp.csr_matrix((np.ones(n_gen), (gbus, np.arange(n_gen))), shape=(n_bus, n_gen))
    # one angle reference per island: the slack bus if inside, else the island's first bus
    ncomp, labels = connected_components(abs(A.T @ A) if len(k) else sp.eye(n_bus), directed=False)
    slack = [i for i in range(n_bus) if int(bus[i, 1]) == 3]
    refs = []
    for c in range(ncomp):
        members = np.where(labels == c)[0]
        s = [i for i in slack if labels[i] == c]
        refs.append(s[0] if s else int(members[0]))
    return dict(base=base, bus=bus, gen=gen, br=br, n_bus=n_bus, n_gen=n_gen,
                gen_on=gen_on, keep=keep, b=b, Bf=Bf, Bbus=Bbus, pfinj=pfinj,
                pbusinj=pbusinj, Cg=Cg, refs=refs, n_islands=ncomp, labels=labels)


def gen_cost_expr(row, P, cp):
    """cvxpy cost ($/hr) of one generator at output P (MW)."""
    model, n = int(row[0]), int(row[3])
    c = list(row[4:4 + (2 * n if model == 1 else n)])
    if model == 2:
        if n >= 4:
            raise SystemExit("ERROR: polynomial cost above degree 2 is not supported")
        if n == 3:
            if c[0] < 0:
                raise SystemExit("ERROR: negative quadratic coefficient (non-convex cost)")
            return c[0] * cp.square(P) + c[1] * P + c[2], None
        if n == 2:
            return c[0] * P + c[1], None
        return (c[0] if n == 1 else 0.0), None
    if model == 1:  # piecewise linear: epigraph over segments
        pts = [(c[2 * j], c[2 * j + 1]) for j in range(n)]
        z = cp.Variable()
        cons = []
        for (p1, c1), (p2, c2) in zip(pts, pts[1:]):
            m = (c2 - c1) / (p2 - p1)
            cons.append(z >= m * (P - p1) + c1)
        return z, cons + [P >= pts[0][0], P <= pts[-1][0]]
    raise SystemExit(f"ERROR: unknown gencost model {model}")


def gen_cost_value(row, p):
    model, n = int(row[0]), int(row[3])
    if model == 2:
        c = list(row[4:4 + n])
        return sum(ci * p ** (n - 1 - j) for j, ci in enumerate(c))
    pts = [(row[4 + 2 * j], row[5 + 2 * j]) for j in range(n)]
    for (p1, c1), (p2, c2) in zip(pts, pts[1:]):
        if p <= p2 + 1e-9:
            return c1 + (c2 - c1) / (p2 - p1) * (p - p1)
    (p1, c1), (p2, c2) = pts[-2], pts[-1]
    return c1 + (c2 - c1) / (p2 - p1) * (p - p1)


# ----------------------------------------------------------------- solve
def solve_problem(data, M, rcap, req, line_limits=True):
    import numpy as np
    import cvxpy as cp
    gen, br, base = M["gen"], M["br"], M["base"]
    n_gen, n_bus = M["n_gen"], M["n_bus"]
    Pg = cp.Variable(n_gen)            # MW
    Rg = cp.Variable(n_gen)            # MW
    th = cp.Variable(n_bus)            # rad
    on = M["gen_on"]
    pmax = np.where(on, gen[:, 8], 0.0)
    pmin = np.where(on, gen[:, 9], 0.0)
    rc = np.where(on, np.array(rcap), 0.0)
    pd = M["bus"][:, 2]
    cost, cons = 0, []
    for i in range(n_gen):
        if not on[i]:
            continue
        e, extra = gen_cost_expr(data["gencost"][i], Pg[i], cp)
        cost = cost + e
        if extra:
            cons += extra
    balance = M["Cg"] @ Pg - pd == base * (M["Bbus"] @ th + M["pbusinj"])
    cons += [balance, Pg >= pmin, Pg <= pmax, Rg >= 0, Rg <= rc, Pg + Rg <= pmax,
             cp.sum(Rg) >= req, th[M["refs"]] == 0]
    lim_rows = np.array([], dtype=int)
    if line_limits:
        rate = br[M["keep"], 5]
        lim_rows = np.where(rate > 0)[0]       # RATE_A == 0 means unlimited
        if len(lim_rows):
            flow = base * (M["Bf"][lim_rows] @ th + M["pfinj"][lim_rows])
            cons += [flow <= rate[lim_rows], flow >= -rate[lim_rows]]
    prob = cp.Problem(cp.Minimize(cost), cons)
    is_lp = prob.is_dcp() and not any(
        int(data["gencost"][i][0]) == 2 and int(data["gencost"][i][3]) >= 3
        and data["gencost"][i][4] != 0 for i in range(n_gen) if on[i])
    order = ["CLARABEL"] + (["HIGHS"] if is_lp else []) + ["ECOS", "SCS"]
    tried = []
    for s in order:
        if s not in cp.installed_solvers():
            continue
        try:
            prob.solve(solver=s)
        except Exception as exc:  # solver failure: try the next one
            tried.append(f"{s}: {exc.__class__.__name__}")
            continue
        tried.append(f"{s}: {prob.status}")
        if prob.status in ("optimal", "optimal_inaccurate"):
            return dict(prob=prob, Pg=Pg.value, Rg=Rg.value, th=th.value, solver=s,
                        status=prob.status, tried=tried, balance=balance)
        if prob.status in ("infeasible", "unbounded"):
            break
    return dict(prob=prob, status=prob.status, tried=tried)


def line_flows(M, th):
    import numpy as np
    br, keep, base = M["br"], M["keep"], M["base"]
    flows = np.zeros(len(br))
    flows[keep] = base * (M["Bf"] @ th + M["pfinj"])
    out = []
    for j in range(len(br)):
        rate = br[j, 5]
        pct = abs(flows[j]) / rate * 100 if rate > 0 else 0.0
        out.append({"from": int(br[j, 0]), "to": int(br[j, 1]), "branch_index": j,
                    "flow_MW": float(flows[j]), "limit_MW": float(rate),
                    "loading_pct": float(pct)})
    return out


def verify(data, M, rcap, req, Pg, Rg, flows, tol=1e-3):
    """Independent feasibility checks on an MW dispatch. Returns (checks, ok)."""
    import numpy as np
    gen, on = M["gen"], M["gen_on"]
    pmax = np.where(on, gen[:, 8], 0.0)
    pmin = np.where(on, gen[:, 9], 0.0)
    rc = np.where(on, np.array(rcap), 0.0)
    fl = np.zeros(len(M["br"]))
    for r in flows:
        fl[r["branch_index"]] = r["flow_MW"]
    # nodal injection implied by flows must equal generation - load at every bus
    inj = np.zeros(M["n_bus"])
    idx = {int(M["bus"][i, 0]): i for i in range(M["n_bus"])}
    for j, r in enumerate(M["br"]):
        inj[idx[int(r[0])]] += fl[j]
        inj[idx[int(r[1])]] -= fl[j]
    mis = M["Cg"] @ Pg - M["bus"][:, 2] - inj
    lim = [r for r in flows if r["limit_MW"] > 0]
    checks = {
        "max_bus_mismatch_MW": float(np.max(np.abs(mis))),
        "gen_limit_violation_MW": float(max(0, np.max(pmin - Pg), np.max(Pg - pmax))),
        "reserve_cap_violation_MW": float(max(0, np.max(Rg - rc), np.max(-Rg))),
        "coupling_violation_MW": float(max(0, np.max(Pg + Rg - pmax))),
        "reserve_shortfall_MW": float(max(0, req - Rg.sum())),
        "max_loading_pct": float(max((r["loading_pct"] for r in lim), default=0.0)),
        "gen_minus_load_MW": float(Pg.sum() - M["bus"][:, 2].sum()),
    }
    ok = (checks["max_bus_mismatch_MW"] < 1e-2 and checks["gen_limit_violation_MW"] < tol
          and checks["reserve_cap_violation_MW"] < tol and checks["coupling_violation_MW"] < tol
          and checks["reserve_shortfall_MW"] < tol and checks["max_loading_pct"] < 100 + 1e-2)
    return checks, ok


def rank_lines(flows):
    """Rated lines by loading, highest first; ties at 2 decimals keep branch-file order."""
    return sorted((r for r in flows if r["limit_MW"] > 0),
                  key=lambda r: (-round(r["loading_pct"], 2), r["branch_index"]))


def build_report(data, M, Pg, Rg, flows, top):
    import numpy as np
    gen, on = M["gen"], M["gen_on"]
    r2 = lambda v: round(float(v), 2) + 0.0   # + 0.0 turns -0.0 into 0.0
    dispatch = [{"id": i + 1, "bus": int(gen[i, 0]), "output_MW": r2(Pg[i]),
                 "reserve_MW": r2(Rg[i]), "pmax_MW": r2(gen[i, 8])} for i in range(M["n_gen"])]
    cost = sum(gen_cost_value(data["gencost"][i], Pg[i]) for i in range(M["n_gen"]) if on[i])
    ranked = rank_lines(flows)[:top]
    margin = float(np.sum(np.where(on, gen[:, 8], 0.0) - Pg - Rg))
    return {
        "generator_dispatch": dispatch,
        "totals": {"cost_dollars_per_hour": r2(cost),
                   "load_MW": r2(M["bus"][:, 2].sum()),
                   "generation_MW": r2(Pg.sum()),
                   "reserve_MW": r2(Rg.sum())},
        "most_loaded_lines": [{"from": r["from"], "to": r["to"],
                               "loading_pct": r2(r["loading_pct"])} for r in ranked],
        "operating_margin_MW": r2(margin),
    }


def cmd_solve(a):
    import numpy as np
    data = load_raw(a.network)
    warn = []
    rcap, req = reserve_data(data, warn)
    M = build_model(data, a.branch_model)
    res = solve_problem(data, M, rcap, req)
    if res["status"] not in ("optimal", "optimal_inaccurate"):
        diag = {"status": res["status"], "solvers_tried": res["tried"]}
        relaxed = solve_problem(data, M, rcap, req, line_limits=False)
        diag["feasible_without_line_limits"] = relaxed["status"] in ("optimal", "optimal_inaccurate")
        print(json.dumps({"error": "dispatch not solved", **diag, "warnings": warn}, indent=2))
        sys.exit(2)
    Pg, Rg = np.asarray(res["Pg"]), np.asarray(res["Rg"])
    Rg = np.maximum(Rg, 0.0)                     # clip solver noise like -1e-9
    flows = line_flows(M, res["th"])
    checks, ok = verify(data, M, rcap, req, Pg, Rg, flows)
    report = build_report(data, M, Pg, Rg, flows, a.top)
    with open(a.out, "w") as f:
        json.dump(report, f, indent=2)
    if a.details:
        lam = res["balance"].dual_value
        det = {"solver": res["solver"], "status": res["status"],
               "lmp_dollars_per_MWh": {int(M["bus"][i, 0]): float(-lam[i])
                                       for i in range(M["n_bus"])} if lam is not None else None,
               "binding_lines": [r for r in flows if r["limit_MW"] > 0 and r["loading_pct"] > 99.9],
               "line_flows": flows}
        with open(a.details, "w") as f:
            json.dump(det, f)
    print(json.dumps({"wrote": a.out, "solver": res["solver"], "status": res["status"],
                      "objective": float(res["prob"].value), "islands": M["n_islands"],
                      "branch_model": a.branch_model, "totals": report["totals"],
                      "most_loaded_lines": report["most_loaded_lines"],
                      "lines_tied_at_top_loading": sum(
                          1 for r in flows if r["limit_MW"] > 0 and round(r["loading_pct"], 2)
                          == report["most_loaded_lines"][0]["loading_pct"])
                      if report["most_loaded_lines"] else 0,
                      "operating_margin_MW": report["operating_margin_MW"],
                      "checks": checks, "checks_pass": ok, "warnings": warn}, indent=2))
    sys.exit(0 if ok else 3)


def cmd_check(a):
    """Re-verify a report.json against the network (e.g. after hand edits)."""
    import numpy as np
    import scipy.sparse.linalg as spla
    data = load_raw(a.network)
    warn = []
    rcap, req = reserve_data(data, warn)
    M = build_model(data, a.branch_model)
    with open(a.report) as f:
        rep = json.load(f)
    errs = []
    for key in ("generator_dispatch", "totals", "most_loaded_lines", "operating_margin_MW"):
        if key not in rep:
            errs.append(f"missing key {key}")
    gd = rep.get("generator_dispatch", [])
    if len(gd) != M["n_gen"]:
        errs.append(f"generator_dispatch has {len(gd)} rows, network has {M['n_gen']}")
    if errs:
        print(json.dumps({"checks_pass": False, "errors": errs}, indent=2))
        sys.exit(3)
    gd = sorted(gd, key=lambda r: r["id"])
    Pg = np.array([r["output_MW"] for r in gd], float)
    Rg = np.array([r["reserve_MW"] for r in gd], float)
    for i, r in enumerate(gd):
        if r["id"] != i + 1 or r["bus"] != int(M["gen"][i, 0]):
            errs.append(f"row id={r['id']} bus={r['bus']} does not match gen row {i}")
            break
    # DC power flow from the reported dispatch (angles fixed at each island reference)
    P = (M["Cg"] @ Pg - M["bus"][:, 2]) / M["base"] - M["pbusinj"]
    free = np.setdiff1d(np.arange(M["n_bus"]), M["refs"])
    th = np.zeros(M["n_bus"])
    B = M["Bbus"].tocsc()
    th[free] = spla.spsolve(B[free][:, free], P[free])
    flows = line_flows(M, th)
    # island balance (spsolve drops the reference rows; check them separately)
    for c in range(M["n_islands"]):
        m = M["labels"] == c
        s = float((M["Cg"] @ Pg)[m].sum() - M["bus"][m, 2].sum())
        if abs(s) > 0.05 * max(1, m.sum()) ** 0.5:
            errs.append(f"island {c} generation-load mismatch {s:.3f} MW")
    checks, ok = verify(data, M, rcap, req, Pg, Rg, flows, tol=0.011)
    checks["max_bus_mismatch_MW"] = "n/a (rounded dispatch; island balance checked instead)"
    ok = (checks["gen_limit_violation_MW"] < 0.011 and checks["reserve_cap_violation_MW"] < 0.011
          and checks["coupling_violation_MW"] < 0.011 and checks["reserve_shortfall_MW"] < 0.011
          and checks["max_loading_pct"] < 100.05)
    T = rep["totals"]
    cost = sum(gen_cost_value(data["gencost"][i], Pg[i]) for i in range(M["n_gen"]) if M["gen_on"][i])
    expect = {"load_MW": M["bus"][:, 2].sum(), "generation_MW": Pg.sum(), "reserve_MW": Rg.sum()}
    for k, v in expect.items():
        if abs(T.get(k, float("nan")) - v) > 0.01 * M["n_gen"] ** 0.5 + 0.01:
            errs.append(f"totals.{k}={T.get(k)} but rows give {v:.2f}")
    if abs(T.get("cost_dollars_per_hour", float("nan")) - cost) > max(1.0, 1e-5 * abs(cost)):
        errs.append(f"totals.cost={T.get('cost_dollars_per_hour')} but dispatch costs {cost:.2f}")
    margin = float(np.sum(np.where(M["gen_on"], M["gen"][:, 8], 0.0) - Pg - Rg))
    if abs(rep["operating_margin_MW"] - margin) > 0.01 * M["n_gen"] ** 0.5 + 0.01:
        errs.append(f"operating_margin_MW={rep['operating_margin_MW']} but rows give {margin:.2f}")
    top = rank_lines(flows)
    rep_top = rep["most_loaded_lines"]
    if rep_top and abs(rep_top[0]["loading_pct"] - top[0]["loading_pct"]) > 0.5:
        errs.append(f"most_loaded_lines[0] {rep_top[0]} vs recomputed "
                    f"{top[0]['from']}-{top[0]['to']} {top[0]['loading_pct']:.2f}%")
    ok = ok and not errs
    print(json.dumps({"checks": checks, "errors": errs, "checks_pass": ok,
                      "recomputed_top_lines": [{"from": r["from"], "to": r["to"],
                                                "loading_pct": round(r["loading_pct"], 2)}
                                               for r in top[:len(rep_top) or 3]],
                      "warnings": warn}, indent=2))
    sys.exit(0 if ok else 3)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("inspect"); s.add_argument("network")
    s = sub.add_parser("solve"); s.add_argument("network"); s.add_argument("--out", required=True)
    s.add_argument("--details"); s.add_argument("--top", type=int, default=3)
    s.add_argument("--branch-model", choices=["simple", "matpower"], default="simple")
    s = sub.add_parser("check"); s.add_argument("network"); s.add_argument("report")
    s.add_argument("--branch-model", choices=["simple", "matpower"], default="simple")
    a = p.parse_args()
    if a.cmd == "inspect":
        return inspect(a.network)
    ensure_deps()
    return cmd_solve(a) if a.cmd == "solve" else cmd_check(a)


if __name__ == "__main__":
    main()
