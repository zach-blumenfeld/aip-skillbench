"""Build and solve the unit commitment MILP with HiGHS (scipy.optimize.milp); write the solution JSON.

Internal convention: p = output ABOVE minimum; actual MW = pmin*u + p. Converted once at extraction.
Constraint families (each has a matching check in validate_uc.py):
  transition linking, must-run, initial min up/down, min up/down windows, online capacity with
  joint production+reserve and startup capability, shutdown capability, ramp up (production+reserve)
  and ramp down incl. first period from power_output_t0, piecewise production cost, startup tiers by
  prior offline duration, demand balance, system reserve, renewable bounds.
"""
import json
import os
import sys
import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from uc_common import load_case, read_stdin

INF = np.inf


class Model:
    def __init__(self):
        self.n = 0
        self.lb, self.ub, self.integ, self.c = [], [], [], []
        self.rows, self.cols, self.vals, self.rlo, self.rhi = [], [], [], [], []
        self.r = 0

    def alloc(self, shape, lb=0.0, ub=INF, integer=False, cost=0.0):
        size = int(np.prod(shape))
        idx = np.arange(self.n, self.n + size).reshape(shape)
        self.n += size
        self.lb += [lb] * size
        self.ub += [ub] * size
        self.integ += [1 if integer else 0] * size
        self.c += [cost] * size
        return idx

    def add_row(self, terms, lo, hi):
        for j, a in terms:
            if a != 0:
                self.rows.append(self.r)
                self.cols.append(int(j))
                self.vals.append(float(a))
        self.rlo.append(float(lo))
        self.rhi.append(float(hi))
        self.r += 1


def build_and_solve(case, opts):
    T, G = case["T"], len(case["thermal"])
    th, rn = case["thermal"], case["renewable"]
    R = len(rn)
    m = Model()
    u = m.alloc((G, T), 0, 1, True)
    v = m.alloc((G, T), 0, 1, True)   # startup
    w = m.alloc((G, T), 0, 1, True)   # shutdown
    p = m.alloc((G, T))               # above-minimum output
    r = m.alloc((G, T))               # spinning reserve
    seg, tier = [], []
    for gi, g in enumerate(th):
        pts = g["curve"]
        pmin, pmax = g["power_output_minimum"], g["power_output_maximum"]
        c0 = pts[0][1]
        for t in range(T):
            m.c[u[gi, t]] = c0                     # cost at minimum output while online
        # segments of the total-cost curve
        widths = [b[0] - a[0] for a, b in zip(pts, pts[1:])]
        slopes = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(pts, pts[1:])]
        s_idx = [m.alloc((T,), 0, wd, False, sl) for wd, sl in zip(widths, slopes)]
        seg.append(s_idx)
        for t in range(T):
            m.add_row([(p[gi, t], 1.0)] + [(s[t], -1.0) for s in s_idx], 0, 0)
            for s, wd in zip(s_idx, widths):
                m.add_row([(s[t], 1.0), (u[gi, t], -wd)], -INF, 0)
        if not g["convex"] and len(s_idx) > 1:          # fill segments in order
            for k in range(len(s_idx) - 1):
                z = m.alloc((T,), 0, 1, True)
                for t in range(T):
                    m.add_row([(s_idx[k][t], 1.0), (z[t], -widths[k])], 0, INF)
                    m.add_row([(s_idx[k + 1][t], 1.0), (z[t], -widths[k + 1])], -INF, 0)
        # startup tiers
        tiers = g["startup"]
        if len(tiers) == 1:
            for t in range(T):
                m.c[v[gi, t]] = tiers[0][1]
            tier.append(None)
        else:
            d = m.alloc((len(tiers), T), 0, 1, False)
            for s, (_, cost) in enumerate(tiers):
                for t in range(T):
                    m.c[d[s, t]] = cost
            for t in range(T):
                m.add_row([(v[gi, t], 1.0)] + [(d[s, t], -1.0) for s in range(len(tiers))], 0, 0)
                for s in range(len(tiers) - 1):       # coldest tier is always allowed
                    lo = 1 if s == 0 else tiers[s][0]
                    hi = tiers[s + 1][0] - 1
                    terms = [(d[s, t], 1.0)]
                    terms += [(w[gi, t - dd], -1.0) for dd in range(lo, hi + 1) if t - dd >= 0]
                    init = 1.0 if (g["unit_on_t0"] == 0 and lo <= g["time_down_t0"] + t <= hi) else 0.0
                    m.add_row(terms, -INF, init)
            tier.append(d)

        on0, p0 = g["unit_on_t0"], g["power_output_t0"]
        prev_above = on0 * (p0 - pmin)
        cap = pmax - pmin
        su_red = max(pmax - g["ramp_startup_limit"], 0.0)
        sd_red = max(pmax - g["ramp_shutdown_limit"], 0.0)
        UT, DT = max(1, g["time_up_minimum"]), max(1, g["time_down_minimum"])
        for t in range(T):
            # transition linking
            if t == 0:
                m.add_row([(u[gi, 0], 1.0), (v[gi, 0], -1.0), (w[gi, 0], 1.0)], on0, on0)
            else:
                m.add_row([(u[gi, t], 1.0), (u[gi, t - 1], -1.0), (v[gi, t], -1.0), (w[gi, t], 1.0)], 0, 0)
            m.add_row([(v[gi, t], 1.0), (w[gi, t], 1.0)], -INF, 1)
            if g["must_run"]:
                m.lb[u[gi, t]] = 1
            # joint production + reserve within capability; startup capability in start period
            sd_next = opts["enforce_shutdown_capability"] and t + 1 < T
            if sd_next and UT >= 2:
                # start at t and stop at t+1 cannot both happen, so one tighter row covers both
                m.add_row([(p[gi, t], 1.0), (r[gi, t], 1.0), (u[gi, t], -cap), (v[gi, t], su_red),
                           (w[gi, t + 1], sd_red)], -INF, 0)
            else:
                m.add_row([(p[gi, t], 1.0), (r[gi, t], 1.0), (u[gi, t], -cap), (v[gi, t], su_red)], -INF, 0)
                # shutdown capability: output+reserve before a shutdown at t+1 limited to ramp_shutdown_limit
                if sd_next:
                    m.add_row([(p[gi, t], 1.0), (r[gi, t], 1.0), (u[gi, t], -cap), (w[gi, t + 1], sd_red)], -INF, 0)
            # ramping on above-minimum output; reserve must be deliverable within ramp-up
            if t == 0:
                m.add_row([(p[gi, 0], 1.0), (r[gi, 0], 1.0)], -INF, g["ramp_up_limit"] + prev_above)
                m.add_row([(p[gi, 0], -1.0)], -INF, g["ramp_down_limit"] - prev_above)
            else:
                m.add_row([(p[gi, t], 1.0), (r[gi, t], 1.0), (p[gi, t - 1], -1.0)], -INF, g["ramp_up_limit"])
                m.add_row([(p[gi, t - 1], 1.0), (p[gi, t], -1.0)], -INF, g["ramp_down_limit"])
            # minimum up/down windows (truncated at horizon end)
            m.add_row([(v[gi, k], 1.0) for k in range(max(0, t - UT + 1), t + 1)] + [(u[gi, t], -1.0)], -INF, 0)
            m.add_row([(w[gi, k], 1.0) for k in range(max(0, t - DT + 1), t + 1)] + [(u[gi, t], 1.0)], -INF, 1)
            if opts["post_horizon_min_updown"]:
                if t > T - UT:
                    m.ub[v[gi, t]] = 0
                if t > T - DT:
                    m.ub[w[gi, t]] = 0
        # shutdown in the first period only if power_output_t0 is within shutdown capability
        if opts["enforce_shutdown_capability"] and on0 == 1 and p0 > g["ramp_shutdown_limit"] + 1e-9:
            m.ub[w[gi, 0]] = 0
        # initial minimum up/down obligations
        if on0 == 1:
            for t in range(min(T, max(0, g["time_up_minimum"] - g["time_up_t0"]))):
                m.lb[u[gi, t]] = 1
        else:
            for t in range(min(T, max(0, g["time_down_minimum"] - g["time_down_t0"]))):
                m.ub[u[gi, t]] = 0

    pw = m.alloc((R, T)) if R else np.zeros((0, T), dtype=int)
    rr = m.alloc((R, T)) if (R and opts["renewable_reserve_allowed"]) else None
    for ri, rec in enumerate(rn):
        for t in range(T):
            lo, hi = rec["min"][t], rec["max"][t]
            if opts["renewables_must_use_max"]:
                lo = hi
            m.lb[pw[ri, t]] = lo
            m.ub[pw[ri, t]] = hi
            if rr is not None:
                m.add_row([(pw[ri, t], 1.0), (rr[ri, t], 1.0)], -INF, rec["max"][t])

    for t in range(T):
        terms = [(u[gi, t], th[gi]["power_output_minimum"]) for gi in range(G)]
        terms += [(p[gi, t], 1.0) for gi in range(G)] + [(pw[ri, t], 1.0) for ri in range(R)]
        m.add_row(terms, case["demand"][t], case["demand"][t])
        terms = [(r[gi, t], 1.0) for gi in range(G)]
        if rr is not None:
            terms += [(rr[ri, t], 1.0) for ri in range(R)]
        m.add_row(terms, case["reserves"][t], INF)

    A = coo_matrix((m.vals, (m.rows, m.cols)), shape=(m.r, m.n)).tocsr()
    t0 = time.time()
    res = milp(
        c=np.array(m.c),
        integrality=np.array(m.integ),
        bounds=Bounds(np.array(m.lb, dtype=float), np.array(m.ub, dtype=float)),
        constraints=LinearConstraint(A, np.array(m.rlo), np.array(m.rhi)),
        options={"time_limit": float(opts["time_limit_s"]), "mip_rel_gap": float(opts["mip_rel_gap"]), "disp": False},
    )
    runtime = time.time() - t0
    info = {
        "status_code": int(res.status), "message": str(res.message), "runtime_s": round(runtime, 2),
        "n_vars": m.n, "n_rows": m.r, "n_binary": int(sum(m.integ)),
        "objective": None if res.x is None else float(res.fun),
        "mip_gap": getattr(res, "mip_gap", None), "dual_bound": getattr(res, "mip_dual_bound", None),
    }
    for k in ("mip_gap", "dual_bound"):
        val = info[k]
        info[k] = float(val) if val is not None and np.isfinite(val) else None
    if res.x is None:
        return None, info
    x = res.x
    ints = [x[u], x[v], x[w]]
    worst = max(float(np.max(np.abs(a - np.round(a)))) if a.size else 0.0 for a in ints)
    info["max_binary_deviation"] = worst
    U = np.round(x[u]).astype(int)
    V = np.round(x[v]).astype(int)
    W = np.round(x[w]).astype(int)
    P = np.where(U == 1, np.maximum(x[p], 0.0), 0.0)
    Rv = np.where(U == 1, np.maximum(x[r], 0.0), 0.0)
    pmin = np.array([g["power_output_minimum"] for g in th])[:, None]
    actual = pmin * U + P
    PW = x[pw] if R else np.zeros((0, T))
    RR = x[rr] if rr is not None else None
    return {"U": U, "V": V, "W": W, "actual": actual, "reserve": Rv, "pw": PW, "rr": RR}, info


def main():
    state = read_stdin(sys.stdin)
    opts = {
        "time_limit_s": state.get("time_limit_s", 600.0),
        "mip_rel_gap": state.get("mip_rel_gap", 0.01),
        "post_horizon_min_updown": bool(state.get("post_horizon_min_updown", False)),
        "renewable_reserve_allowed": bool(state.get("renewable_reserve_allowed", False)),
        "renewables_must_use_max": bool(state.get("renewables_must_use_max", False)),
        "enforce_shutdown_capability": bool(state.get("enforce_shutdown_capability", True)),
    }
    case, errors, _ = load_case(state["data_path"])
    if case is None or errors:
        print(json.dumps({"solve_status": "data_error", "solve_info": {"errors": errors[:20]}}))
        return
    sol, info = build_and_solve(case, opts)
    if sol is None:
        status = "infeasible" if info["status_code"] == 2 else "no_incumbent"
        print(json.dumps({"solve_status": status, "solve_info": info}))
        return
    if info.get("max_binary_deviation", 0.0) > 1e-4:
        status = "non_integral"     # binaries not near 0/1: do not round and report
    elif info["status_code"] == 0:
        status = "optimal"          # within mip_rel_gap
    else:
        status = "feasible_limit"   # time/node limit with an incumbent
    th, rn, T = case["thermal"], case["renewable"], case["T"]
    names = [g["name"] for g in th]
    rnames = [x["name"] for x in rn]
    doc = {
        "data_path": os.path.abspath(state["data_path"]),
        "time_periods": T,
        "conventions": {
            "period_index": "0-based arrays in source period order; label t+1 if the report is 1-based",
            "dispatch": "actual MW (pmin*u + output above minimum)",
            "options": opts,
        },
        "thermal_names": names,
        "renewable_names": rnames,
        "commitment": {n: sol["U"][i].tolist() for i, n in enumerate(names)},
        "startup": {n: sol["V"][i].tolist() for i, n in enumerate(names)},
        "shutdown": {n: sol["W"][i].tolist() for i, n in enumerate(names)},
        "thermal_dispatch_mw": {n: sol["actual"][i].tolist() for i, n in enumerate(names)},
        "thermal_reserve_mw": {n: sol["reserve"][i].tolist() for i, n in enumerate(names)},
        "renewable_dispatch_mw": {n: sol["pw"][i].tolist() for i, n in enumerate(rnames)},
        "solver": dict(info, status=status, solver="HiGHS via scipy.optimize.milp"),
    }
    if sol["rr"] is not None:
        doc["renewable_reserve_mw"] = {n: sol["rr"][i].tolist() for i, n in enumerate(rnames)}
    if status == "non_integral":
        print(json.dumps({"solve_status": status, "solve_info": info}))
        return
    out_path = state["solution_path"]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    print(json.dumps({
        "solve_status": status,
        "solution_path": out_path,
        "solve_info": {k: info[k] for k in ("objective", "mip_gap", "dual_bound", "runtime_s", "message", "max_binary_deviation", "n_vars", "n_rows")},
    }))


if __name__ == "__main__":
    main()
