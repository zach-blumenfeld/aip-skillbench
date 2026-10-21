#!/usr/bin/env python3
"""DC-OPF market clearing with spinning-reserve co-optimization, LMP / reserve-MCP
extraction, binding-line detection, and a "relax one line" counterfactual.

Requires: Python >= 3.9; pip packages numpy, scipy, cvxpy (with the bundled CLARABEL solver).
If they are missing, the script creates a virtualenv (default ~/.cache/dcopf-venv, override
with DCOPF_VENV) via `python3 -m venv`, pip-installs them there (needs network access), and
re-executes itself inside it. Set DCOPF_NO_BOOTSTRAP=1 to disable this.

Subcommands:
  inspect  --network FILE [--from-bus A --to-bus B]
           Network summary, data checks, and the branch(es) joining A and B.
  run      --network FILE --from-bus A --to-bus B [--scale 1.2] [--branch-index K]
           [--out report.json] [--binding-threshold 99] [--dispatch-out dispatch.json]
           Solves base + counterfactual and writes the report JSON.
"""
import json
import os
import subprocess
import sys

REQUIRED = ["numpy", "scipy", "cvxpy"]


def _bootstrap():
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import cvxpy  # noqa: F401
        return
    except ImportError as e:
        missing = str(e)
    if os.environ.get("DCOPF_NO_BOOTSTRAP") == "1" or os.environ.get("DCOPF_IN_VENV") == "1":
        sys.exit(f"ERROR: missing package ({missing}); install: pip install {' '.join(REQUIRED)}")
    venv = os.environ.get("DCOPF_VENV", os.path.expanduser("~/.cache/dcopf-venv"))
    py = os.path.join(venv, "bin", "python")
    ready = os.path.exists(py) and subprocess.call(
        [py, "-c", "import numpy, scipy, cvxpy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    if not ready:
        print(f"[bootstrap] {missing}; installing {REQUIRED} into venv {venv}", file=sys.stderr)
    try:
        if not os.path.exists(py):
            subprocess.check_call([sys.executable, "-m", "venv", venv])
        if not ready:
            subprocess.check_call([py, "-m", "pip", "install", "-q", "--disable-pip-version-check"] + REQUIRED,
                                  stdout=sys.stderr)
    except (subprocess.CalledProcessError, OSError) as err:
        sys.exit(f"ERROR: could not bootstrap {REQUIRED} into {venv}: {err}. "
                 f"Install them manually (pip install {' '.join(REQUIRED)}) and rerun.")
    env = dict(os.environ, DCOPF_IN_VENV="1")
    os.execve(py, [py, os.path.abspath(__file__)] + sys.argv[1:], env)


_bootstrap()

import argparse  # noqa: E402
import warnings  # noqa: E402

import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402
import cvxpy as cp  # noqa: E402


# ---------------------------------------------------------------- data loading
def load_network(path):
    with open(path) as f:
        data = json.load(f)
    for key in ("baseMVA", "bus", "gen", "branch", "gencost"):
        if key not in data:
            sys.exit(f"ERROR: network file lacks '{key}' (expected MATPOWER-style JSON)")
    net = {
        "baseMVA": float(data["baseMVA"]),
        "bus": np.array(data["bus"], dtype=float),
        "gen": np.array(data["gen"], dtype=float),
        "branch": np.array(data["branch"], dtype=float),
        "gencost": data["gencost"],  # ragged-safe: keep as list of rows
    }
    n_gen = len(net["gen"])
    if len(net["gencost"]) < n_gen:
        sys.exit(f"ERROR: gencost has {len(net['gencost'])} rows for {n_gen} generators")
    rc = data.get("reserve_capacity")
    net["reserve_capacity"] = np.array(rc, dtype=float) if rc is not None else None
    net["reserve_requirement"] = float(data.get("reserve_requirement", 0.0) or 0.0)
    if net["reserve_capacity"] is not None and len(net["reserve_capacity"]) != n_gen:
        sys.exit("ERROR: reserve_capacity length != number of generators")
    return net


def matching_branches(branch, a, b):
    return [k for k in range(len(branch))
            if {int(branch[k, 0]), int(branch[k, 1])} == {int(a), int(b)}]


# ---------------------------------------------------------------- model
def solve_market(net, rate, threshold, model="source"):
    """Solve DC-OPF + reserves. `rate` = RATE_A vector (MW) to enforce. Returns dict."""
    base = net["baseMVA"]
    bus, gen, branch = net["bus"], net["gen"], net["branch"]
    n_bus, n_gen = len(bus), len(gen)
    idx = {int(bus[i, 0]): i for i in range(n_bus)}  # bus numbers may be non-contiguous

    gen_on = gen[:, 7] > 0 if gen.shape[1] > 7 else np.ones(n_gen, bool)
    br_on = branch[:, 10] > 0 if branch.shape[1] > 10 else np.ones(len(branch), bool)
    live = [k for k in range(len(branch)) if br_on[k] and branch[k, 3] != 0]

    f = np.array([idx[int(branch[k, 0])] for k in live])
    t = np.array([idx[int(branch[k, 1])] for k in live])
    bk = 1.0 / branch[live, 3]  # model "source": susceptance 1/x; taps, phase shifts, shunts ignored
    shift = np.zeros(len(live))
    if model == "matpower":  # MATPOWER makeBdc: b = 1/(x*tap), phase-shift injections, bus Gs as load
        tap = branch[live, 8] if branch.shape[1] > 8 else np.ones(len(live))
        bk = 1.0 / (branch[live, 3] * np.where(tap == 0, 1.0, tap))
        shift = np.deg2rad(branch[live, 9]) if branch.shape[1] > 9 else shift
    nl = len(live)
    rows = np.arange(nl)
    A = sp.csr_matrix((np.r_[np.ones(nl), -np.ones(nl)], (np.r_[rows, rows], np.r_[f, t])), shape=(nl, n_bus))
    Bf = sp.diags(bk) @ A                     # branch flow (pu) = Bf @ theta
    Bbus = (A.T @ Bf).tocsr()                 # nodal susceptance matrix

    gbus = np.array([idx[int(g[0])] for g in gen])
    Cg = sp.csr_matrix((np.ones(n_gen), (gbus, np.arange(n_gen))), shape=(n_bus, n_gen))
    Pd = bus[:, 2].copy()                     # MW
    Pfinj = -bk * shift                       # pu flow offset from phase shifters (0 in "source" model)
    Pbusinj = A.T @ Pfinj
    if model == "matpower" and bus.shape[1] > 4:
        Pd = Pd + bus[:, 4]

    # Everything is posed in MW (theta in rad): same model as the source's per-unit form, but far
    # better conditioned for interior-point solvers on large grids with tiny reactances.
    Pg = cp.Variable(n_gen)   # MW
    Rg = cp.Variable(n_gen)   # MW
    theta = cp.Variable(n_bus)
    pmax = np.where(gen_on, gen[:, 8], 0.0)
    pmin = np.where(gen_on, gen[:, 9], 0.0)

    # costs
    lin_c1 = np.zeros(n_gen); quad_c2 = np.zeros(n_gen); const = 0.0
    pwl_terms = []
    for i in range(n_gen):
        if not gen_on[i]:
            continue
        row = net["gencost"][i]
        model, ncost = int(row[0]), int(row[3])
        coeffs = list(row[4:4 + (2 * ncost if model == 1 else ncost)])
        if model == 2:
            c = coeffs[::-1]  # lowest order first: c0, c1, c2, ...
            if len(c) > 3 and any(abs(x) > 0 for x in c[3:]):
                sys.exit(f"ERROR: generator {i + 1} has a polynomial cost of degree >2; not supported")
            const += c[0] if len(c) >= 1 else 0.0
            lin_c1[i] = c[1] if len(c) >= 2 else 0.0
            quad_c2[i] = c[2] if len(c) >= 3 else 0.0
            if quad_c2[i] < 0:
                sys.exit(f"ERROR: generator {i + 1} has negative c2 (non-convex)")
        elif model == 1:
            pts = np.array(coeffs, dtype=float).reshape(-1, 2)
            pwl_terms.append((i, pts))
        else:
            sys.exit(f"ERROR: generator {i + 1} has unknown cost MODEL {model}")

    Pg_MW = Pg
    cost = lin_c1 @ Pg_MW + const
    if np.any(quad_c2 > 0):
        q = np.where(quad_c2 > 0)[0]
        cost = cost + cp.sum(cp.multiply(quad_c2[q], cp.square(Pg_MW[q])))
    cons = []
    if pwl_terms:
        z = cp.Variable(len(pwl_terms))
        for j, (i, pts) in enumerate(pwl_terms):
            segs = [(p1, c1, p2, c2) for (p1, c1), (p2, c2) in zip(pts[:-1], pts[1:]) if p2 > p1]
            for p1, c1, p2, c2 in segs:  # convex PWL as epigraph: z >= each segment's line
                cons.append(z[j] >= c1 + (c2 - c1) / (p2 - p1) * (Pg_MW[i] - p1))
            if not segs:  # degenerate curve (all breakpoints at one MW): fixed cost
                cons.append(z[j] == pts[0, 1])
        cost = cost + cp.sum(z)

    balance = Cg @ Pg - Pd == (Bbus @ theta + Pbusinj) * base
    cons.append(balance)
    slack = np.where(bus[:, 1] == 3)[0]
    cons.append(theta[int(slack[0]) if len(slack) else 0] == 0)
    cons += [Pg >= pmin, Pg <= pmax]

    lim = np.array([rate[k] for k in live])
    has_lim = lim > 0  # RATE_A == 0 means unlimited in MATPOWER
    if np.any(has_lim):
        flow_MW = (Bf[has_lim] @ theta + Pfinj[has_lim]) * base
        cons += [flow_MW <= lim[has_lim], flow_MW >= -lim[has_lim]]

    reserve_con = None
    if net["reserve_capacity"] is not None:
        rcap = np.where(gen_on, net["reserve_capacity"], 0.0)
        cons += [Rg >= 0, Rg <= rcap, Pg_MW + Rg <= pmax]
        reserve_con = cp.sum(Rg) >= net["reserve_requirement"]
        cons.append(reserve_con)
    else:  # no reserve data in the file: plain DC-OPF, reserve MCP reported as 0
        Rg = None

    prob = cp.Problem(cp.Minimize(cost), cons)
    # CLARABEL first (source default, robust interior point); HIGHS (bundled with cvxpy) as fallback.
    chain = [s_ for s_ in ("CLARABEL", "HIGHS") if s_ in cp.installed_solvers()] or [None]
    used = None
    for solver in chain:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                prob.solve(solver=solver)
        except cp.error.SolverError as e:
            print(f"[warn] {solver} failed ({e})", file=sys.stderr)
            continue
        used = solver
        if prob.status == "optimal":
            break
        print(f"[warn] {solver} status {prob.status}; trying next solver", file=sys.stderr)
    if prob.status not in ("optimal", "optimal_inaccurate"):
        sys.exit(f"ERROR: market clearing status = {prob.status} (infeasible/unbounded input?)")
    if prob.status == "optimal_inaccurate":
        print("[warn] solver status optimal_inaccurate; treat prices with caution", file=sys.stderr)

    # cvxpy's dual of (gen - load == net export) is -d(cost)/d(load), so with rows in MW: LMP = -dual ($/MWh).
    # (The source's per-unit recipe `dual * baseMVA` is wrong by a factor of -baseMVA^2; see SKILL.md Gotchas.)
    lam = -np.asarray(balance.dual_value).ravel()
    # Self-check: at a generator strictly inside its limits (and not reserve-coupled), LMP == marginal cost.
    pg = Pg.value
    rg = Rg.value if Rg is not None else np.zeros(n_gen)
    tol = 1e-3 * max(1.0, float(pmax.max()))
    free = [i for i in range(n_gen) if gen_on[i] and pg[i] > pmin[i] + tol and pg[i] + rg[i] < pmax[i] - tol
            and not any(i == j for j, _ in pwl_terms)]
    mc_err = [abs(lam[gbus[i]] - (lin_c1[i] + 2 * quad_c2[i] * pg[i])) for i in free]
    th = theta.value
    flows = np.zeros(len(branch)); loading = np.zeros(len(branch))
    flows[live] = (bk * (th[f] - th[t]) + Pfinj) * base
    for k in live:
        loading[k] = abs(flows[k]) / rate[k] * 100 if rate[k] > 0 else 0.0
    binding = [k for k in live if rate[k] > 0 and loading[k] >= threshold]
    mcp = float(reserve_con.dual_value) if reserve_con is not None and reserve_con.dual_value is not None else 0.0
    return {
        "status": f"{prob.status} ({used})",
        "cost": float(prob.value),
        "lmp": {int(bus[i, 0]): float(lam[i]) for i in range(n_bus)},
        "mcp": mcp,
        "flows": flows,
        "loading": loading,
        "binding": binding,
        "gen_MW": pg,
        "res_MW": rg,
        "lmp_check": {"marginal_units": len(free),
                      "max_abs_err_vs_marginal_cost": round(float(max(mc_err)), 4) if mc_err else None},
    }


def case_block(net, res, rate):
    br = net["branch"]
    return {
        "total_cost_dollars_per_hour": round(res["cost"], 2),
        "lmp_by_bus": [{"bus": b, "lmp_dollars_per_MWh": round(v, 2)} for b, v in res["lmp"].items()],
        "reserve_mcp_dollars_per_MWh": round(res["mcp"], 2),
        "binding_lines": [{"from": int(br[k, 0]), "to": int(br[k, 1]),
                           "flow_MW": round(float(res["flows"][k]), 2),
                           "limit_MW": round(float(rate[k]), 2)} for k in res["binding"]],
    }


def dispatch_block(net, res):
    """Per-generator dispatch, totals, and operating margin (uncommitted headroom)."""
    gen = net["gen"]
    pg, rg = res["gen_MW"], res["res_MW"]
    return {
        "generator_dispatch": [{"id": i + 1, "bus": int(gen[i, 0]), "output_MW": round(float(pg[i]), 2),
                                "reserve_MW": round(float(rg[i]), 2), "pmax_MW": round(float(gen[i, 8]), 2)}
                               for i in range(len(gen))],
        "totals": {"cost_dollars_per_hour": round(res["cost"], 2),
                   "load_MW": round(float(net["bus"][:, 2].sum()), 2),
                   "generation_MW": round(float(pg.sum()), 2), "reserve_MW": round(float(rg.sum()), 2)},
        "operating_margin_MW": round(float(np.sum(np.where(gen[:, 7] > 0, gen[:, 8], 0.0) - pg - rg)), 2),
    }


# ---------------------------------------------------------------- commands
def cmd_inspect(a):
    net = load_network(a.network)
    bus, gen, br = net["bus"], net["gen"], net["branch"]
    models = {}
    for row in net["gencost"][:len(gen)]:
        models[(int(row[0]), int(row[3]))] = models.get((int(row[0]), int(row[3])), 0) + 1
    print(json.dumps({
        "baseMVA": net["baseMVA"], "buses": len(bus), "generators": len(gen), "branches": len(br),
        "slack_buses": [int(b[0]) for b in bus if b[1] == 3],
        "total_load_MW": round(float(bus[:, 2].sum()), 2),
        "gen_pmin_sum_MW": round(float(gen[:, 9].sum()), 2), "gen_pmax_sum_MW": round(float(gen[:, 8].sum()), 2),
        "gens_out_of_service": int((gen[:, 7] <= 0).sum()) if gen.shape[1] > 7 else 0,
        "branches_out_of_service": int((br[:, 10] <= 0).sum()) if br.shape[1] > 10 else 0,
        "branches_rateA_zero_unlimited": int((br[:, 5] <= 0).sum()),
        "gencost_model_ncost_counts": {f"model{m}_ncost{n}": c for (m, n), c in models.items()},
        "has_reserve_data": net["reserve_capacity"] is not None,
        "reserve_requirement_MW": net["reserve_requirement"],
        "reserve_capacity_sum_MW": round(float(net["reserve_capacity"].sum()), 2) if net["reserve_capacity"] is not None else None,
    }, indent=2))
    if a.from_bus is not None and a.to_bus is not None:
        ks = matching_branches(br, a.from_bus, a.to_bus)
        print(f"branches joining {a.from_bus} and {a.to_bus}: {len(ks)}")
        for k in ks:
            print(f"  index {k}: from {int(br[k,0])} to {int(br[k,1])} x={br[k,3]} rateA={br[k,5]} status={br[k,10]}")


def cmd_run(a):
    net = load_network(a.network)
    br = net["branch"]
    ks = matching_branches(br, a.from_bus, a.to_bus)
    if not ks:
        sys.exit(f"ERROR: no branch joins buses {a.from_bus} and {a.to_bus}")
    if a.branch_index is not None:
        if a.branch_index not in ks:
            sys.exit(f"ERROR: --branch-index {a.branch_index} is not one of the matching branches {ks}")
        targets = [a.branch_index]
    elif len(ks) > 1 and not a.all_parallel:
        sys.exit(f"ERROR: {len(ks)} parallel branches join {a.from_bus}-{a.to_bus} (indices {ks}); "
                 f"rerun with --branch-index K or --all-parallel (see SKILL.md decision)")
    else:
        targets = ks
    for k in targets:
        if br[k, 5] <= 0:
            sys.exit(f"ERROR: target branch {k} has RATE_A={br[k,5]} (unlimited); scaling is meaningless")

    rate_base = br[:, 5].copy()
    rate_cf = rate_base.copy()
    rate_cf[targets] *= a.scale

    base = solve_market(net, rate_base, a.binding_threshold, a.dc_model)
    cf = solve_market(net, rate_cf, a.binding_threshold, a.dc_model)

    deltas = []
    for b, v in base["lmp"].items():
        bl, cl = round(v, 2), round(cf["lmp"][b], 2)
        deltas.append((cf["lmp"][b] - v, b, bl, cl))
    deltas.sort(key=lambda x: (x[0], x[1]))
    top = [{"bus": b, "base_lmp": bl, "cf_lmp": cl, "delta": round(cl - bl, 2)} for _, b, bl, cl in deltas[:a.top_n]]

    binding_base = any(k in base["binding"] for k in targets)
    binding_cf = any(k in cf["binding"] for k in targets)
    report = {
        "base_case": case_block(net, base, rate_base),
        "counterfactual": case_block(net, cf, rate_cf),
        "impact_analysis": {
            "cost_reduction_dollars_per_hour": round(base["cost"] - cf["cost"], 2),
            "buses_with_largest_lmp_drop": top,
            "congestion_relieved": (not binding_cf) if a.relieved_rule == "not_binding_cf"
                                   else (binding_base and not binding_cf),
        },
    }
    with open(a.out, "w") as fh:
        json.dump(report, fh, indent=2)
    if a.dispatch_out:
        with open(a.dispatch_out, "w") as fh:
            json.dump({"base_case": dispatch_block(net, base), "counterfactual": dispatch_block(net, cf)}, fh, indent=2)

    # diagnostics (stdout only; not part of the report)
    def tgt(res, rate):
        return [{"index": k, "flow_MW": round(float(res["flows"][k]), 2), "limit_MW": round(float(rate[k]), 2),
                 "loading_pct": round(float(res["loading"][k]), 3)} for k in targets]
    lb, lc = np.array(list(base["lmp"].values())), np.array(list(cf["lmp"].values()))
    print(json.dumps({
        "report": os.path.abspath(a.out),
        "solver_status": {"base": base["status"], "counterfactual": cf["status"]},
        "target_branches": targets, "scale": a.scale,
        "target_base": tgt(base, rate_base), "target_cf": tgt(cf, rate_cf),
        "target_binding_base": binding_base, "target_binding_cf": binding_cf,
        "congestion_relieved_rule": a.relieved_rule, "dc_model": a.dc_model,
        "cost_base": round(base["cost"], 2), "cost_cf": round(cf["cost"], 2),
        "n_binding_base": len(base["binding"]), "n_binding_cf": len(cf["binding"]),
        "lmp_range_base": [round(float(lb.min()), 2), round(float(lb.max()), 2)],
        "lmp_range_cf": [round(float(lc.min()), 2), round(float(lc.max()), 2)],
        "reserve_mcp": [round(base["mcp"], 4), round(cf["mcp"], 4)],
        "lmp_check": {"base": base["lmp_check"], "counterfactual": cf["lmp_check"]},
        "balance_check_MW": [round(float(base["gen_MW"].sum() - net["bus"][:, 2].sum()), 4),
                             round(float(cf["gen_MW"].sum() - net["bus"][:, 2].sum()), 4)],
        "reserve_total_MW": [round(float(base["res_MW"].sum()), 2), round(float(cf["res_MW"].sum()), 2)],
    }, indent=2))
    load = float(net["bus"][:, 2].sum())
    if a.dc_model == "matpower" and net["bus"].shape[1] > 4:
        load += float(net["bus"][:, 4].sum())
    req = net["reserve_requirement"] if net["reserve_capacity"] is not None else 0.0
    checks = {
        "solver_optimal": all(r["status"].startswith("optimal (") for r in (base, cf)),
        "lmp_equals_marginal_cost": all((r["lmp_check"]["max_abs_err_vs_marginal_cost"] or 0.0) <= 0.05
                                        for r in (base, cf)),
        "cost_not_increased": cf["cost"] <= base["cost"] + 1e-6 * max(1.0, abs(base["cost"])),
        "power_balanced": all(abs(float(r["gen_MW"].sum()) - load) <= 1e-3 * max(1.0, load) for r in (base, cf)),
        "reserve_met": all(float(r["res_MW"].sum()) >= req - 1e-3 * max(1.0, req) for r in (base, cf)),
    }
    print(json.dumps({"checks": checks, "all_checks_pass": all(checks.values())}))
    if not all(checks.values()):
        print("[warn] a sanity check failed; see SKILL.md step 4", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("inspect")
    pi.add_argument("--network", required=True)
    pi.add_argument("--from-bus", type=int)
    pi.add_argument("--to-bus", type=int)
    pr = sub.add_parser("run")
    pr.add_argument("--network", required=True)
    pr.add_argument("--from-bus", type=int, required=True)
    pr.add_argument("--to-bus", type=int, required=True)
    pr.add_argument("--scale", type=float, default=1.20, help="multiplier on RATE_A of the target (1.20 = +20%%)")
    pr.add_argument("--branch-index", type=int, help="0-based branch row to relax when parallel circuits exist")
    pr.add_argument("--all-parallel", action="store_true", help="relax every parallel circuit joining the buses")
    pr.add_argument("--binding-threshold", type=float, default=99.0, help="loading %% at/above which a line is binding")
    pr.add_argument("--top-n", type=int, default=3, help="number of buses in buses_with_largest_lmp_drop")
    pr.add_argument("--relieved-rule", choices=["not_binding_cf", "binding_base_and_not_cf"], default="not_binding_cf")
    pr.add_argument("--dc-model", choices=["source", "matpower"], default="source",
                    help="source: b=1/x (default); matpower: b=1/(x*tap) + phase shifts + bus Gs")
    pr.add_argument("--out", default="report.json")
    pr.add_argument("--dispatch-out", help="optional JSON with per-generator dispatch, totals, operating margin")
    a = p.parse_args()
    cmd_inspect(a) if a.cmd == "inspect" else cmd_run(a)


if __name__ == "__main__":
    main()
