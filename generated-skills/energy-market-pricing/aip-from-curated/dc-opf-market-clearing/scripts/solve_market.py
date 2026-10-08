#!/usr/bin/env python3
"""DC-OPF market clearing with reserve co-optimization, LMPs, and counterfactual impact.

Reads one JSON object on stdin ({"currentState", "assets", "expects"}); writes one JSON
object to stdout. Full results go to `results_path` on disk (they are large: one LMP per
bus, one flow per branch); stdout carries a compact summary.

State keys used:
  network_path    MATPOWER-style network.json
  results_path    where to write the full results JSON
  counterfactual  {"enabled": bool, "modifications": [...]}; modification types:
      {"type": "line_limit", "from_bus": F, "to_bus": T, "factor": 1.2 | "limit_MW": 500,
       "match": "first" | "all"}        # direction-insensitive; "first" = lowest index
      {"type": "bus_load", "bus": B, "factor": x | "delta_MW": d | "pd_MW": p}
      {"type": "reserve_requirement", "factor": x | "value_MW": v}

Model (sources: power-flow-data, dc-power-flow, economic-dispatch, locational-marginal-prices):
  min  sum_i C_i(Pg_i)                                  C from gencost (poly or PWL), P in MW
  s.t. Cg Pg - Pd = B theta baseMVA    (per bus, MW)    LMP = -dual ($/MWh), see below
       -RATE_A <= b (theta_f - theta_t) baseMVA <= RATE_A   for RATE_A > 0
       theta_slack = 0
       PMIN <= Pg <= PMAX
       0 <= Rg <= reserve_capacity,  Pg + Rg <= PMAX,  sum Rg >= R   dual = reserve MCP
  b = 1/x (tap ratio and phase shift ignored, exactly as the source skills do).

Dependencies: numpy, scipy, cvxpy (CLARABEL). If they are missing (bare container python),
the script creates a venv (default ~/.cache/dc-opf-market-clearing/venv, override with
DCOPF_VENV), pip-installs them, and re-runs itself there.
"""
import json
import os
import subprocess
import sys

BINDING_THRESHOLD = 99.0  # percent loading at/above which a line counts as binding
DEPS = ["numpy", "scipy", "cvxpy", "clarabel"]


# ----------------------------------------------------------------------------- bootstrap
def _have_deps():
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
        import cvxpy  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _bootstrap(raw_stdin):
    venv = os.path.expanduser(os.environ.get("DCOPF_VENV", "~/.cache/dc-opf-market-clearing/venv"))
    py = os.path.join(venv, "bin", "python")
    log = []
    if not os.path.exists(py):
        r = subprocess.run([sys.executable, "-m", "venv", venv], capture_output=True, text=True)
        log.append(r.stderr[-2000:])
        if r.returncode != 0:
            return None, "venv creation failed: " + r.stderr[-2000:]
    chk = subprocess.run([py, "-c", "import numpy, scipy, cvxpy"], capture_output=True)
    if chk.returncode != 0:
        r = subprocess.run([py, "-m", "pip", "install", "-q", "--disable-pip-version-check"] + DEPS,
                           capture_output=True, text=True)
        if r.returncode != 0:
            return None, "pip install failed: " + r.stderr[-2000:]
    env = dict(os.environ, DCOPF_BOOTSTRAPPED="1")
    env.pop("PYTHONPATH", None)
    r = subprocess.run([py, os.path.abspath(__file__)], input=raw_stdin, capture_output=True,
                       text=True, env=env)
    if r.returncode != 0:
        return None, "solver child failed: " + r.stderr[-3000:]
    return r.stdout, None


# ----------------------------------------------------------------------------- model
def load_network(path):
    import numpy as np
    with open(path) as f:
        data = json.load(f)
    net = {
        "baseMVA": float(data["baseMVA"]),
        "bus": np.array(data["bus"], dtype=float),
        "gen": np.array(data["gen"], dtype=float),
        "branch": np.array(data["branch"], dtype=float),
        "gencost": [list(map(float, row)) for row in data["gencost"]],
        "has_reserves": "reserve_capacity" in data and "reserve_requirement" in data,
    }
    if net["has_reserves"]:
        net["reserve_capacity"] = np.array(data["reserve_capacity"], dtype=float)
        net["reserve_requirement"] = float(data["reserve_requirement"])
    return net


def apply_modifications(net, mods):
    """Return a modified deep copy of net plus a log of what changed."""
    import copy
    net = copy.deepcopy(net)
    log = []
    br, bus = net["branch"], net["bus"]
    for m in mods:
        t = m["type"]
        if t == "line_limit":
            fb, tb = int(m["from_bus"]), int(m["to_bus"])
            idx = [k for k in range(len(br)) if {int(br[k, 0]), int(br[k, 1])} == {fb, tb}]
            if not idx:
                raise ValueError(f"no branch between {fb} and {tb}")
            if m.get("match", "first") == "first":
                idx = idx[:1]
            for k in idx:
                old = float(br[k, 5])
                new = old * float(m["factor"]) if "factor" in m else float(m["limit_MW"])
                br[k, 5] = new
                log.append({"type": t, "branch_index_0based": k, "from": int(br[k, 0]),
                            "to": int(br[k, 1]), "old_limit_MW": old, "new_limit_MW": new})
        elif t == "bus_load":
            k = [i for i in range(len(bus)) if int(bus[i, 0]) == int(m["bus"])][0]
            old = float(bus[k, 2])
            if "factor" in m:
                new = old * float(m["factor"])
            elif "delta_MW" in m:
                new = old + float(m["delta_MW"])
            else:
                new = float(m["pd_MW"])
            bus[k, 2] = new
            log.append({"type": t, "bus": int(m["bus"]), "old_pd_MW": old, "new_pd_MW": new})
        elif t == "reserve_requirement":
            old = net["reserve_requirement"]
            new = old * float(m["factor"]) if "factor" in m else float(m["value_MW"])
            net["reserve_requirement"] = new
            log.append({"type": t, "old_MW": old, "new_MW": new})
        else:
            raise ValueError(f"unknown modification type {t!r}")
    return net, log


def solve_dcopf(net):
    import numpy as np
    import scipy.sparse as sp
    import cvxpy as cp

    base = net["baseMVA"]
    bus, gen, br = net["bus"], net["gen"], net["branch"]
    n_bus, n_gen, n_br = len(bus), len(gen), len(br)
    # Bus numbers may be non-contiguous: always map number -> 0-based position.
    bus_num_to_idx = {int(bus[i, 0]): i for i in range(n_bus)}
    gen_bus = np.array([bus_num_to_idx[int(g[0])] for g in gen])
    f = np.array([bus_num_to_idx[int(r[0])] for r in br])
    t = np.array([bus_num_to_idx[int(r[1])] for r in br])

    # Branch susceptance b = 1/x; out-of-service or x == 0 branches carry no flow.
    x = br[:, 3]
    active = (br[:, 10] != 0) & (x != 0)
    b = np.where(active, 1.0 / np.where(x == 0, 1.0, x), 0.0)
    rows = np.arange(n_br)
    Bf = sp.csr_matrix((np.r_[b, -b], (np.r_[rows, rows], np.r_[f, t])), shape=(n_br, n_bus))
    Cft = sp.csr_matrix((np.r_[np.ones(n_br), -np.ones(n_br)], (np.r_[rows, rows], np.r_[f, t])),
                        shape=(n_br, n_bus))
    B = (Cft.T @ Bf).tocsr()  # = sum over branches of b * (e_f - e_t)(e_f - e_t)^T
    Cg = sp.csr_matrix((np.ones(n_gen), (gen_bus, np.arange(n_gen))), shape=(n_bus, n_gen))

    slack = [i for i in range(n_bus) if int(bus[i, 1]) == 3]
    slack_idx = slack[0] if slack else 0

    on = gen[:, 7] > 0
    pmax = np.where(on, gen[:, 8], 0.0)
    pmin = np.where(on, gen[:, 9], 0.0)

    Pg = cp.Variable(n_gen)       # per-unit
    theta = cp.Variable(n_bus)    # radians
    Pg_MW = Pg * base
    cons = [Pg >= pmin / base, Pg <= pmax / base, theta[slack_idx] == 0]

    # Cost: polynomial (model 2, highest order first) or piecewise linear (model 1).
    c2 = np.zeros(n_gen); c1 = np.zeros(n_gen); c0 = np.zeros(n_gen)
    pwl = []
    for i, row in enumerate(net["gencost"]):
        model, ncost, coef = int(row[0]), int(row[3]), row[4:]
        if model == 2:
            if ncost > 3:
                raise ValueError(f"gen {i + 1}: polynomial NCOST={ncost} > 3 unsupported")
            padded = [0.0] * (3 - ncost) + list(coef[:ncost])  # -> [c2, c1, c0]
            c2[i], c1[i], c0[i] = padded
        elif model == 1:
            pts = [(coef[2 * k], coef[2 * k + 1]) for k in range(ncost)]
            pwl.append((i, pts))
        else:
            raise ValueError(f"gen {i + 1}: unknown gencost MODEL {model}")
    cost = c1 @ Pg_MW + float(c0.sum())
    if np.any(c2 != 0):
        if np.any(c2 < 0):
            raise ValueError("negative quadratic cost coefficient (non-convex)")
        cost = cost + cp.sum(cp.multiply(c2, cp.square(Pg_MW)))
    if pwl:
        tcost = cp.Variable(len(pwl))
        for j, (i, pts) in enumerate(pwl):
            for (p0, k0), (p1, k1) in zip(pts[:-1], pts[1:]):
                slope = (k1 - k0) / (p1 - p0)
                cons.append(tcost[j] >= k0 + slope * (Pg_MW[i] - p0))
        cost = cost + cp.sum(tcost)

    # Nodal balance written in MW (keep the reference: its dual is the LMP). cvxpy's
    # Lagrangian is f + y'(lhs - rhs), so d(cost)/d(Pd) = -y: LMP = -dual. Writing it in
    # per-unit instead would make LMP = -dual / baseMVA (NOT dual * baseMVA).
    balance = Cg @ Pg_MW - bus[:, 2] == base * (B @ theta)
    cons.append(balance)

    # Thermal limits on RATE_A (RATE_A <= 0 means unlimited in MATPOWER).
    lim = active & (br[:, 5] > 0)
    if lim.any():
        flow_lim = Bf[lim] @ theta * base
        cons += [flow_lim <= br[lim, 5], flow_lim >= -br[lim, 5]]

    # Reserve co-optimization.
    Rg, reserve_con = None, None
    if net["has_reserves"]:
        Rg = cp.Variable(n_gen)  # MW
        rcap = np.where(on, net["reserve_capacity"], 0.0)
        reserve_con = cp.sum(Rg) >= net["reserve_requirement"]
        cons += [Rg >= 0, Rg <= rcap, Pg_MW + Rg <= pmax, reserve_con]

    prob = cp.Problem(cp.Minimize(cost), cons)
    installed = cp.installed_solvers()
    order = [s for s in ("CLARABEL", "ECOS", "SCS") if s in installed]
    status, used, errs = None, None, []
    for s in order:
        try:
            prob.solve(solver=s)
            status, used = prob.status, s
            if status in ("optimal", "optimal_inaccurate"):
                break
        except Exception as e:  # noqa: BLE001
            errs.append(f"{s}: {e}")
    if status not in ("optimal", "optimal_inaccurate"):
        return {"status": status or "solver_error", "solver": used, "errors": errs}

    th = theta.value
    pg_mw = Pg.value * base
    rg_mw = Rg.value if Rg is not None else np.zeros(n_gen)
    # LMP ($/MWh): + means one more MW of load at the bus raises total cost.
    lmp = -np.asarray(balance.dual_value, dtype=float)
    reserve_mcp = float(reserve_con.dual_value) if reserve_con is not None else 0.0

    flow_mw = (Bf @ th) * base
    lines, binding = [], []
    for k in range(n_br):
        rate = float(br[k, 5])
        loading = abs(flow_mw[k]) / rate * 100 if rate > 0 else 0.0
        rec = {"branch_index_0based": k, "from": int(br[k, 0]), "to": int(br[k, 1]),
               "flow_MW": round(float(flow_mw[k]), 4), "limit_MW": round(rate, 4),
               "loading_pct": round(float(loading), 4)}
        lines.append(rec)
        if active[k] and rate > 0 and loading >= BINDING_THRESHOLD:
            binding.append({"from": rec["from"], "to": rec["to"], "flow_MW": round(float(flow_mw[k]), 2),
                            "limit_MW": round(rate, 2), "loading_pct": round(float(loading), 2),
                            "branch_index_0based": k})

    dispatch = [{"id": i + 1, "bus": int(gen[i, 0]), "output_MW": round(float(pg_mw[i]), 2),
                 "reserve_MW": round(float(rg_mw[i]), 2), "pmax_MW": round(float(gen[i, 8]), 2),
                 "pmin_MW": round(float(gen[i, 9]), 2)} for i in range(n_gen)]
    total_load = float(bus[:, 2].sum())
    totals = {"cost_dollars_per_hour": round(float(prob.value), 2),
              "load_MW": round(total_load, 2),
              "generation_MW": round(float(pg_mw.sum()), 2),
              "reserve_MW": round(float(rg_mw.sum()), 2)}
    op_margin = float(np.sum(pmax - pg_mw - rg_mw))
    lmp_list = [{"bus": int(bus[i, 0]), "lmp_dollars_per_MWh": round(float(lmp[i]), 2)} for i in range(n_bus)]
    return {
        "status": status, "solver": used,
        "objective_unrounded": float(prob.value),
        "totals": totals,
        "operating_margin_MW": round(op_margin, 2),
        "reserve_mcp_dollars_per_MWh": round(reserve_mcp, 2),
        "reserve_requirement_MW": net.get("reserve_requirement"),
        "lmp_by_bus": lmp_list,
        "lmp_stats": {"min": round(float(lmp.min()), 2), "max": round(float(lmp.max()), 2),
                      "mean": round(float(lmp.mean()), 2),
                      "load_weighted_mean": round(float((lmp * bus[:, 2]).sum() / total_load), 2)
                      if total_load else None,
                      "n_negative": int((lmp < -1e-6).sum())},
        "binding_lines": binding,
        "generator_dispatch": dispatch,
        "line_flows": lines,
        "checks": {
            "gen_minus_load_MW": round(float(pg_mw.sum() - total_load), 4),
            "reserve_shortfall_MW": round(float(max(0.0, (net.get("reserve_requirement") or 0) - rg_mw.sum())), 4),
            "max_line_loading_pct": round(float(max((l["loading_pct"] for l in lines), default=0)), 2),
        },
    }


def compare(base_res, cf_res, mod_log):
    lmp_b = {r["bus"]: r["lmp_dollars_per_MWh"] for r in base_res["lmp_by_bus"]}
    lmp_c = {r["bus"]: r["lmp_dollars_per_MWh"] for r in cf_res["lmp_by_bus"]}
    deltas = [{"bus": b, "base_lmp": lmp_b[b], "cf_lmp": lmp_c[b], "delta": round(lmp_c[b] - lmp_b[b], 2)}
              for b in lmp_b]
    by_abs = sorted(deltas, key=lambda d: abs(d["delta"]), reverse=True)
    key = lambda l: (min(l["from"], l["to"]), max(l["from"], l["to"]))  # noqa: E731
    base_bind = {l["branch_index_0based"] for l in base_res["binding_lines"]}
    cf_bind = {l["branch_index_0based"] for l in cf_res["binding_lines"]}
    targets = []
    for m in mod_log:
        if m["type"] != "line_limit":
            continue
        k = m["branch_index_0based"]
        bl, cl = base_res["line_flows"][k], cf_res["line_flows"][k]
        targets.append({"from": m["from"], "to": m["to"], "branch_index_0based": k,
                        "base_flow_MW": bl["flow_MW"], "base_limit_MW": bl["limit_MW"],
                        "base_loading_pct": bl["loading_pct"],
                        "cf_flow_MW": cl["flow_MW"], "cf_limit_MW": cl["limit_MW"],
                        "cf_loading_pct": cl["loading_pct"],
                        "binding_in_base": k in base_bind, "binding_in_cf": k in cf_bind,
                        # congestion relieved: binding in base, not binding in counterfactual
                        "congestion_relieved": (k in base_bind) and (k not in cf_bind)})
    cost_red = base_res["objective_unrounded"] - cf_res["objective_unrounded"]
    return {
        "modifications_applied": mod_log,
        "base_cost_dollars_per_hour": base_res["totals"]["cost_dollars_per_hour"],
        "cf_cost_dollars_per_hour": cf_res["totals"]["cost_dollars_per_hour"],
        "cost_reduction_dollars_per_hour": round(cost_red, 2),
        "cost_change_dollars_per_hour": round(-cost_red, 2),  # cf - base; > 0 = counterfactual costs more
        "cost_reduction_pct": round(100 * cost_red / base_res["objective_unrounded"], 4)
        if base_res["objective_unrounded"] else None,
        "target_lines": targets,
        "congestion_relieved": all(t["congestion_relieved"] for t in targets) if targets else None,
        "reserve_mcp_base": base_res["reserve_mcp_dollars_per_MWh"],
        "reserve_mcp_cf": cf_res["reserve_mcp_dollars_per_MWh"],
        "n_buses_lmp_changed": sum(1 for d in deltas if abs(d["delta"]) >= 0.01),
        "n_buses_lmp_decreased": sum(1 for d in deltas if d["delta"] <= -0.01),
        "n_buses_lmp_increased": sum(1 for d in deltas if d["delta"] >= 0.01),
        "largest_lmp_changes": by_abs[:10],
        "largest_lmp_drops": sorted(deltas, key=lambda d: d["delta"])[:10],
        "largest_lmp_rises": sorted(deltas, key=lambda d: d["delta"], reverse=True)[:10],
        "lmp_changes": deltas,
        "binding_lines_removed": sorted({key(l) for l in base_res["binding_lines"]}
                                        - {key(l) for l in cf_res["binding_lines"]}),
        "binding_lines_added": sorted({key(l) for l in cf_res["binding_lines"]}
                                      - {key(l) for l in base_res["binding_lines"]}),
    }


def summarize(res):
    return {k: res[k] for k in ("status", "solver", "totals", "operating_margin_MW",
                                "reserve_mcp_dollars_per_MWh", "lmp_stats", "checks")} | {
        "n_binding_lines": len(res["binding_lines"]),
        "binding_lines_first_10": [{k: l[k] for k in ("from", "to", "flow_MW", "limit_MW", "loading_pct")}
                                   for l in res["binding_lines"][:10]]}


def self_check(net, base_res):
    """Finite-difference check of dual-based prices: +1 MW load at the largest-load bus and
    +1 MW reserve requirement, re-solve, compare the cost change with the LMP / reserve MCP.
    Duals can be non-unique in degenerate LPs, so a mismatch is a warning, not an error."""
    import numpy as np
    bus = net["bus"]
    k = int(np.argmax(bus[:, 2]))
    bn = int(bus[k, 0])
    res = {}
    n2, _ = apply_modifications(net, [{"type": "bus_load", "bus": bn, "delta_MW": 1.0}])
    r2 = solve_dcopf(n2)
    if r2["status"] in ("optimal", "optimal_inaccurate"):
        fd = r2["objective_unrounded"] - base_res["objective_unrounded"]
        lmp = next(x["lmp_dollars_per_MWh"] for x in base_res["lmp_by_bus"] if x["bus"] == bn)
        res["lmp"] = {"bus": bn, "dual_lmp": lmp, "finite_difference": round(fd, 2),
                      "agrees": abs(fd - lmp) <= max(0.05 * abs(lmp), 0.5)}
    if net["has_reserves"]:
        n3, _ = apply_modifications(net, [{"type": "reserve_requirement",
                                           "value_MW": net["reserve_requirement"] + 1.0}])
        r3 = solve_dcopf(n3)
        if r3["status"] in ("optimal", "optimal_inaccurate"):
            fd = r3["objective_unrounded"] - base_res["objective_unrounded"]
            mcp = base_res["reserve_mcp_dollars_per_MWh"]
            res["reserve_mcp"] = {"dual_mcp": mcp, "finite_difference": round(fd, 2),
                                  "agrees": abs(fd - mcp) <= max(0.05 * abs(mcp), 0.5)}
    return res


def run(state):
    net = load_network(os.path.expanduser(state["network_path"]))
    results_path = os.path.abspath(os.path.expanduser(state["results_path"]))
    out = {"network_path": state["network_path"], "binding_threshold_pct": BINDING_THRESHOLD}
    base_res = solve_dcopf(net)
    out["base_case"] = base_res
    ok = base_res["status"] in ("optimal", "optimal_inaccurate")
    summary = {"base_case": summarize(base_res) if ok else base_res}
    if ok and state.get("self_check", True):
        out["self_check"] = summary["self_check"] = self_check(net, base_res)
    cf = state.get("counterfactual") or {}
    if ok and cf.get("enabled"):
        cf_net, mod_log = apply_modifications(net, cf.get("modifications") or [])
        cf_res = solve_dcopf(cf_net)
        out["counterfactual"] = cf_res
        if cf_res["status"] in ("optimal", "optimal_inaccurate"):
            if state.get("self_check", True):
                out["self_check_cf"] = summary["self_check_cf"] = self_check(cf_net, cf_res)
            out["impact"] = compare(base_res, cf_res, mod_log)
            summary["counterfactual"] = summarize(cf_res)
            summary["impact"] = {k: (v[:5] if k.startswith("largest_") else v)
                                 for k, v in out["impact"].items() if k != "lmp_changes"}
            if out["impact"]["cost_reduction_dollars_per_hour"] < -0.01 and all(
                    m["type"] == "line_limit" and m["new_limit_MW"] >= m["old_limit_MW"] for m in mod_log):
                summary["warning"] = "relaxing a limit increased cost: solver tolerance issue, inspect"
        else:
            ok = False
            summary["counterfactual"] = cf_res
    os.makedirs(os.path.dirname(results_path) or ".", exist_ok=True)
    with open(results_path, "w") as fh:
        json.dump(out, fh, indent=1)
    ret = {"solve_status": "optimal" if ok else "failed", "results_path": results_path,
           "solve_summary": summary}
    if ok:
        draft_path = os.path.join(os.path.dirname(results_path), "report_draft.json")
        with open(draft_path, "w") as fh:
            json.dump(draft_report(out), fh, indent=2)
        ret["report_draft_path"] = draft_path
    return ret


def _case_block(res):
    return {
        "total_cost_dollars_per_hour": res["totals"]["cost_dollars_per_hour"],
        "lmp_by_bus": res["lmp_by_bus"],
        "reserve_mcp_dollars_per_MWh": res["reserve_mcp_dollars_per_MWh"],
        "binding_lines": [{k: l[k] for k in ("from", "to", "flow_MW", "limit_MW")} for l in res["binding_lines"]],
        "totals": res["totals"],
        "operating_margin_MW": res["operating_margin_MW"],
        "generator_dispatch": res["generator_dispatch"],
    }


def draft_report(out):
    """Canonical report in the source skills' field names; reshape to the task's schema."""
    rep = {"base_case": _case_block(out["base_case"])}
    if "impact" in out:
        imp = out["impact"]
        rep["counterfactual"] = _case_block(out["counterfactual"])
        rep["impact_analysis"] = {
            "cost_reduction_dollars_per_hour": imp["cost_reduction_dollars_per_hour"],
            "buses_with_largest_lmp_drop": [{"bus": d["bus"], "base_lmp": d["base_lmp"], "cf_lmp": d["cf_lmp"],
                                             "delta": d["delta"]} for d in imp["largest_lmp_drops"][:3]],
            "congestion_relieved": imp["congestion_relieved"],
        }
    return rep


def main():
    raw = sys.stdin.read()
    payload = json.loads(raw)
    state = payload.get("currentState", payload)
    if not _have_deps():
        if os.environ.get("DCOPF_BOOTSTRAPPED"):
            print(json.dumps({"solve_status": "failed", "results_path": "",
                              "solve_summary": {"error": "numpy/scipy/cvxpy unavailable after bootstrap"}}))
            return
        stdout, err = _bootstrap(raw)
        if err:
            print(json.dumps({"solve_status": "failed", "results_path": "",
                              "solve_summary": {"error": err}}))
        else:
            sys.stdout.write(stdout)
        return
    try:
        result = run(state)
    except Exception as e:  # noqa: BLE001
        import traceback
        result = {"solve_status": "failed", "results_path": "",
                  "solve_summary": {"error": f"{type(e).__name__}: {e}",
                                    "traceback": traceback.format_exc()[-3000:]}}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
