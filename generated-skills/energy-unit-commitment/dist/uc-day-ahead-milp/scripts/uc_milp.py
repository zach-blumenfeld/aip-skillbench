#!/usr/bin/env python3
"""Day-ahead thermal unit commitment (single zone, no network) as a MILP with SciPy/HiGHS.

Requires: Python >= 3.9, numpy >= 1.22, scipy >= 1.9 (scipy.optimize.milp, HiGHS). No other packages.

Subcommands (run from anywhere; paths are arguments):
  inspect  CASE.json                       schema + parser-level checks, case summary (exit 2 = schema problem,
                                           exit 3 = data inconsistency)
  solve    CASE.json --out REPORT.json      build + solve + extract + independent validation; the report is
                                           written only if every validation family passes (exit 1 otherwise)
  validate CASE.json REPORT.json            independent re-check of an existing report against the case

Input schema (pglib-uc style JSON; see references/data-format.md):
  time_periods:int, demand:[T], reserves:[T],
  thermal_generators:{name:{must_run, power_output_minimum, power_output_maximum, ramp_up_limit,
      ramp_down_limit, ramp_startup_limit, ramp_shutdown_limit, time_up_minimum, time_down_minimum,
      power_output_t0, unit_on_t0, time_up_t0, time_down_t0, startup:[{lag,cost}],
      piecewise_production:[{mw,cost}]}},
  renewable_generators:{name:{power_output_minimum:[T], power_output_maximum:[T]}}

Internal convention: p = output ABOVE minimum, actual MW = pmin*u + p. Ramping and reserve
deliverability are applied to above-minimum quantities; reports carry actual MW.
"""
import argparse
import json
import math
import sys
import time

import numpy as np

THERMAL_FIELDS = [
    "must_run", "power_output_minimum", "power_output_maximum", "ramp_up_limit", "ramp_down_limit",
    "ramp_startup_limit", "ramp_shutdown_limit", "time_up_minimum", "time_down_minimum",
    "power_output_t0", "unit_on_t0", "time_up_t0", "time_down_t0", "startup", "piecewise_production",
]
RENEW_FIELDS = ["power_output_minimum", "power_output_maximum"]
CHECK_KEYS = [
    "demand_balance", "spinning_reserve", "reserve_deliverability", "generator_limits", "must_run",
    "ramping", "minimum_up_down", "startup_shutdown_logic", "initial_conditions", "renewable_limits",
    "cost_consistency",
]
TOL = 1e-4  # MW tolerance for validation


# ----------------------------------------------------------------------------- parsing
def load_case(path):
    with open(path) as f:
        data = json.load(f)
    missing = []
    for key in ["time_periods", "demand", "reserves", "thermal_generators", "renewable_generators"]:
        if key not in data:
            missing.append(key)
    if missing:
        return None, [f"top-level key missing: {k}" for k in missing]
    for name, g in data["thermal_generators"].items():
        for k in THERMAL_FIELDS:
            if k not in g:
                missing.append(f"thermal {name}: missing {k}")
    for name, r in data["renewable_generators"].items():
        for k in RENEW_FIELDS:
            if k not in r:
                missing.append(f"renewable {name}: missing {k}")
    if missing:
        return None, missing

    T = int(data["time_periods"])
    th_names = list(data["thermal_generators"].keys())     # source order preserved
    rn_names = list(data["renewable_generators"].keys())
    gens = []
    for name in th_names:
        g = data["thermal_generators"][name]
        curve = sorted((float(p["mw"]), float(p["cost"])) for p in g["piecewise_production"])
        tiers = sorted((int(s["lag"]), float(s["cost"])) for s in g["startup"])
        gens.append(dict(
            name=name, must_run=int(g["must_run"]),
            pmin=float(g["power_output_minimum"]), pmax=float(g["power_output_maximum"]),
            ru=float(g["ramp_up_limit"]), rd=float(g["ramp_down_limit"]),
            rsu=float(g["ramp_startup_limit"]), rsd=float(g["ramp_shutdown_limit"]),
            ut=int(g["time_up_minimum"]), dt=int(g["time_down_minimum"]),
            p0=float(g["power_output_t0"]), on0=int(g["unit_on_t0"]),
            up0=int(g["time_up_t0"]), down0=int(g["time_down_t0"]),
            tiers=tiers, curve=curve,
        ))
    rmin = np.array([[float(x) for x in data["renewable_generators"][n]["power_output_minimum"]] for n in rn_names]).reshape(len(rn_names), -1) if rn_names else np.zeros((0, T))
    rmax = np.array([[float(x) for x in data["renewable_generators"][n]["power_output_maximum"]] for n in rn_names]).reshape(len(rn_names), -1) if rn_names else np.zeros((0, T))
    case = dict(T=T, demand=np.array(data["demand"], float), reserve=np.array(data["reserves"], float),
                gens=gens, th_names=th_names, rn_names=rn_names, rmin=rmin, rmax=rmax)
    return case, []


def parser_checks(case):
    """Return (errors, warnings)."""
    T, errs, warns = case["T"], [], []
    if len(case["demand"]) != T:
        errs.append(f"demand length {len(case['demand'])} != T={T}")
    if len(case["reserve"]) != T:
        errs.append(f"reserves length {len(case['reserve'])} != T={T}")
    if not np.all(np.isfinite(case["demand"])) or not np.all(np.isfinite(case["reserve"])):
        errs.append("non-finite demand/reserve")
    if case["rmin"].shape[1:] != (T,) and len(case["rn_names"]):
        errs.append("renewable series length != T")
    elif len(case["rn_names"]) and np.any(case["rmin"] > case["rmax"] + 1e-9):
        errs.append("renewable min > max somewhere")
    if len(set(case["th_names"]) & set(case["rn_names"])):
        errs.append("a name appears in both thermal and renewable sets")
    for g in case["gens"]:
        n = g["name"]
        if g["pmin"] > g["pmax"] or g["pmin"] < 0:
            errs.append(f"{n}: bad pmin/pmax")
        if len(g["curve"]) < 2:
            errs.append(f"{n}: production curve needs >= 2 points")
        else:
            xs = [x for x, _ in g["curve"]]
            if len(set(xs)) != len(xs):
                errs.append(f"{n}: repeated cost-curve mw points")
            if abs(xs[0] - g["pmin"]) > 1e-6 or abs(xs[-1] - g["pmax"]) > 1e-6:
                errs.append(f"{n}: curve does not span [pmin, pmax] ({xs[0]}..{xs[-1]})")
        if len(g["tiers"]) < 1:
            errs.append(f"{n}: no startup tiers")
        lags = [l for l, _ in g["tiers"]]
        if len(set(lags)) != len(lags):
            errs.append(f"{n}: duplicate startup lags")
        costs = [c for _, c in g["tiers"]]
        if any(b < a for a, b in zip(costs, costs[1:])):
            warns.append(f"{n}: startup cost decreases with lag (model still exact; tier choice is cost-driven)")
        if g["on0"] == 1:
            if not (g["pmin"] - 1e-6 <= g["p0"] <= g["pmax"] + 1e-6):
                errs.append(f"{n}: on at t0 but power_output_t0 outside [pmin,pmax]")
            if g["up0"] <= 0:
                warns.append(f"{n}: on at t0 but time_up_t0 <= 0")
        else:
            if abs(g["p0"]) > 1e-6:
                errs.append(f"{n}: off at t0 but power_output_t0 != 0")
            if g["down0"] <= 0:
                warns.append(f"{n}: off at t0 but time_down_t0 <= 0")
        if g["must_run"] and g["on0"] == 0 and g["dt"] - g["down0"] > 0:
            errs.append(f"{n}: must-run conflicts with initial minimum-down obligation")
        if g["on0"] == 1 and g["p0"] - g["pmin"] > g["rd"] + 1e-6 and g["p0"] > g["rsd"] + 1e-6:
            pass  # must stay on in period 1; handled by constraints
        slopes = [(y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(g["curve"], g["curve"][1:]) if x1 > x0]
        g["convex"] = all(b >= a - 1e-9 for a, b in zip(slopes, slopes[1:]))
    return errs, warns


# ----------------------------------------------------------------------------- shared math
def curve_cost(curve, mw):
    if mw <= curve[0][0]:
        return curve[0][1]
    if mw >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= mw <= x1:
            return y0 + (mw - x0) * (y1 - y0) / (x1 - x0)
    raise ValueError("output outside curve")


def startup_tier_cost(tiers, offline_duration):
    """Largest lag not exceeding the prior offline duration; first tier if none qualifies."""
    chosen = tiers[0]
    for tier in tiers:
        if tier[0] <= offline_duration:
            chosen = tier
        else:
            break
    return chosen[1]


def offline_durations(g, u):
    """For each period t (0-based) with a startup: number of periods offline before t."""
    out = {}
    last_on = None if g["on0"] == 0 else -1  # index of last online period (-1 = t0)
    for t in range(len(u)):
        prev = g["on0"] if t == 0 else u[t - 1]
        if u[t] == 1 and prev == 0:
            out[t] = (g["down0"] + t) if last_on is None else (t - last_on - 1)
        if u[t] == 1:
            last_on = t
    return out


def recompute_cost(case, u, prod):
    total = 0.0
    for i, g in enumerate(case["gens"]):
        for t in range(case["T"]):
            if u[i][t]:
                total += curve_cost(g["curve"], prod[i][t])
        for t, dur in offline_durations(g, u[i]).items():
            total += startup_tier_cost(g["tiers"], dur)
    return total


# ----------------------------------------------------------------------------- model
class Model:
    def __init__(self):
        self.n = 0
        self.lb, self.ub, self.integ, self.c = [], [], [], []
        self.rows, self.cols, self.vals, self.rlo, self.rhi = [], [], [], [], []
        self.nrow = 0

    def var(self, lb, ub, integer=False, cost=0.0):
        j = self.n
        self.n += 1
        self.lb.append(lb); self.ub.append(ub); self.integ.append(1 if integer else 0); self.c.append(cost)
        return j

    def row(self, terms, lo, hi):
        for j, a in terms:
            if a != 0:
                self.rows.append(self.nrow); self.cols.append(j); self.vals.append(float(a))
        self.rlo.append(lo); self.rhi.append(hi)
        self.nrow += 1


def build_and_solve(case, time_limit, mip_gap, curtail, verbose, diagnose=False):
    from scipy.optimize import Bounds, LinearConstraint, milp
    from scipy.sparse import coo_matrix

    T, gens, INF = case["T"], case["gens"], np.inf
    m = Model()
    U, V, W, P, R, SEG, SLK = [], [], [], [], [], [], []
    const = 0.0
    for g in gens:
        cap = g["pmax"] - g["pmin"]
        c0 = g["curve"][0][1]
        u = [m.var(0, 1, True, c0) for _ in range(T)]
        v = [m.var(0, 1, True) for _ in range(T)]
        w = [m.var(0, 1, True) for _ in range(T)]
        p = [m.var(0, cap) for _ in range(T)]
        r = [m.var(0, cap) for _ in range(T)]
        U.append(u); V.append(v); W.append(w); P.append(p); R.append(r)

        # --- production cost: incremental segments over the total-cost breakpoints
        segs = []
        pts = g["curve"]
        widths = [pts[k + 1][0] - pts[k][0] for k in range(len(pts) - 1)]
        slopes = [(pts[k + 1][1] - pts[k][1]) / widths[k] for k in range(len(pts) - 1)]
        for t in range(T):
            s_t = [m.var(0, widths[k], False, slopes[k]) for k in range(len(widths))]
            m.row([(p[t], 1.0)] + [(s, -1.0) for s in s_t], 0, 0)             # p = sum segments
            if g["convex"]:
                for k, s in enumerate(s_t):
                    m.row([(s, 1.0), (u[t], -widths[k])], -INF, 0)          # seg <= width*u
            else:  # nonconvex curve: fill segments in order with binaries
                z = [m.var(0, 1, True) for _ in widths]
                for k, s in enumerate(s_t):
                    m.row([(s, 1.0), (z[k], -widths[k])], -INF, 0)
                    if k + 1 < len(widths):
                        m.row([(s, 1.0), (z[k + 1], -widths[k])], 0, INF)
                        m.row([(z[k + 1], 1.0), (z[k], -1.0)], -INF, 0)
                m.row([(z[0], 1.0), (u[t], -1.0)], -INF, 0)
            segs.append(s_t)
        SEG.append(segs)

        # --- startup tiers
        tiers = g["tiers"]
        S = len(tiers)
        for t in range(T):
            if S == 1:
                m.c[v[t]] += tiers[0][1]
                continue
            d = [m.var(0, 1, True, tiers[s][1]) for s in range(S)]
            m.row([(v[t], 1.0)] + [(x, -1.0) for x in d], 0, 0)               # v = sum delta
            t1 = t + 1                                                        # 1-based period
            for s in range(S - 1):
                lag_s, lag_n = tiers[s][0], tiers[s + 1][0]
                # initially-off unit: offline duration down0 + t1 - 1 >= lag_n forbids tier s
                if max(1, lag_n - g["down0"] + 1) <= t1 <= lag_n - 1:
                    m.ub[d[s]] = 0
                if t1 >= lag_n:  # tier s needs a shutdown lag_s..lag_n-1 periods earlier
                    terms = [(d[s], 1.0)]
                    for i in range(lag_s, lag_n):
                        if t1 - i >= 1:
                            terms.append((w[t1 - i - 1], -1.0))
                    m.row(terms, -INF, 0)

        # --- initial conditions
        ut0 = min(T, max(0, g["ut"] - g["up0"]) * g["on0"])
        dt0 = min(T, max(0, g["dt"] - g["down0"]) * (1 - g["on0"]))
        for t in range(ut0):
            m.lb[u[t]] = 1
        for t in range(dt0):
            m.ub[u[t]] = 0
        if g["must_run"]:
            for t in range(T):
                m.lb[u[t]] = 1
        p0a = (g["p0"] - g["pmin"]) * g["on0"]
        m.row([(p[0], 1.0), (r[0], 1.0)], -INF, g["ru"] + p0a)                 # ramp up from t0
        m.row([(p[0], -1.0)], -INF, g["rd"] - p0a)                             # ramp down from t0
        m.row([(w[0], max(0.0, g["pmax"] - g["rsd"]))], -INF, cap * g["on0"] - p0a)  # shutdown cap at t0

        for t in range(T):
            prev = [] if t == 0 else [(u[t - 1], -1.0)]
            m.row([(u[t], 1.0), (v[t], -1.0), (w[t], 1.0)] + prev, g["on0"] if t == 0 else 0, g["on0"] if t == 0 else 0)
            m.row([(v[t], 1.0), (w[t], 1.0)], -INF, 1)
            # minimum up / down windows (truncated at horizon end)
            m.row([(v[k], 1.0) for k in range(max(0, t - g["ut"] + 1), t + 1)] + [(u[t], -1.0)], -INF, 0)
            m.row([(w[k], 1.0) for k in range(max(0, t - g["dt"] + 1), t + 1)] + [(u[t], 1.0)], -INF, 1)
            # joint production + reserve capability, startup / shutdown capability
            su_red = max(0.0, g["pmax"] - g["rsu"])
            sd_red = max(0.0, g["pmax"] - g["rsd"])
            base = [(p[t], 1.0), (r[t], 1.0), (u[t], -cap)]
            if t + 1 < T and g["ut"] > 1:
                m.row(base + [(v[t], su_red), (w[t + 1], sd_red)], -INF, 0)
            else:
                m.row(base + [(v[t], su_red)], -INF, 0)
                if t + 1 < T:
                    m.row(base + [(w[t + 1], sd_red)], -INF, 0)
            if t > 0:
                m.row([(p[t], 1.0), (r[t], 1.0), (p[t - 1], -1.0)], -INF, g["ru"])
                m.row([(p[t - 1], 1.0), (p[t], -1.0)], -INF, g["rd"])

    # --- renewables
    Q = []
    for k in range(len(case["rn_names"])):
        lo = case["rmin"][k] if curtail else case["rmax"][k]
        Q.append([m.var(float(lo[t]), float(case["rmax"][k][t])) for t in range(T)])

    # --- system balance and reserve
    for t in range(T):
        terms = [(P[i][t], 1.0) for i in range(len(gens))] + [(U[i][t], gens[i]["pmin"]) for i in range(len(gens))]
        terms += [(Q[k][t], 1.0) for k in range(len(Q))]
        rterms = [(R[i][t], 1.0) for i in range(len(gens))]
        if diagnose:  # priced slacks show where the hard model cannot be satisfied
            short, surplus, rshort = m.var(0, INF, cost=1e6), m.var(0, INF, cost=1e6), m.var(0, INF, cost=1e5)
            SLK.append((short, surplus, rshort))
            terms += [(short, 1.0), (surplus, -1.0)]
            rterms += [(rshort, 1.0)]
        m.row(terms, case["demand"][t], case["demand"][t])
        m.row(rterms, case["reserve"][t], INF)

    A = coo_matrix((m.vals, (m.rows, m.cols)), shape=(m.nrow, m.n)).tocsr()
    if verbose:
        print(f"model: {m.n} vars ({sum(m.integ)} integer), {m.nrow} rows, {len(m.vals)} nonzeros", file=sys.stderr)
    t0 = time.time()
    res = milp(c=np.array(m.c), integrality=np.array(m.integ), bounds=Bounds(np.array(m.lb, float), np.array(m.ub, float)),
               constraints=LinearConstraint(A, np.array(m.rlo, float), np.array(m.rhi, float)),
               options={"time_limit": float(time_limit), "mip_rel_gap": float(mip_gap), "disp": bool(verbose)})
    elapsed = time.time() - t0
    if res.x is None:
        raise SystemExit(f"ERROR: no incumbent (status={res.status}: {res.message}). Infeasible model or time limit "
                         "hit before any feasible point; rerun with --diagnose, see references/formulation.md.")
    x = res.x
    if diagnose:
        print("diagnose: hour(1-based)  generation_shortfall_MW  generation_surplus_MW  reserve_shortfall_MW")
        found = False
        for t, (a, b, c) in enumerate(SLK):
            if x[a] > 1e-6 or x[b] > 1e-6 or x[c] > 1e-6:
                found = True
                print(f"  {t + 1:4d}  {max(0.0, x[a]):12.3f}  {max(0.0, x[b]):12.3f}  {max(0.0, x[c]):12.3f}")
        if not found:
            print("  no balance/reserve slack used: the conflict is in unit-level rules (initial conditions, "
                  "must-run vs min-down, ramps); relax families one at a time per references/formulation.md")
        raise SystemExit(0)
    def binv(j):
        val = x[j]
        if abs(val - round(val)) > 1e-4:
            raise SystemExit(f"ERROR: binary not integral ({val}); do not round, re-solve with tighter tolerances")
        return int(round(val))
    G = len(gens)
    u = [[binv(U[i][t]) for t in range(T)] for i in range(G)]
    prod, resv = [], []
    for i, g in enumerate(gens):
        cap = g["pmax"] - g["pmin"]
        prod.append([g["pmin"] * u[i][t] + min(max(x[P[i][t]], 0.0), cap) * u[i][t] for t in range(T)])
        resv.append([min(max(x[R[i][t]], 0.0), cap) * u[i][t] for t in range(T)])
    ren = [[float(x[Q[k][t]]) for t in range(T)] for k in range(len(Q))]

    gap = getattr(res, "mip_gap", None)
    if gap is None or not np.isfinite(gap):
        bound = getattr(res, "mip_dual_bound", None)
        gap = abs(res.fun - bound) / max(abs(res.fun), 1e-9) if bound is not None and np.isfinite(bound) else None
    if gap is not None:
        gap = max(0.0, float(gap))
    status = "optimal" if res.status == 0 else ("time_limit_feasible" if res.status == 1 else "suboptimal_feasible")
    info = dict(status=status, solver_objective=float(res.fun) + const, gap=gap, seconds=round(elapsed, 1),
                scipy_status=int(res.status), message=str(res.message))
    return u, prod, resv, ren, info


# ----------------------------------------------------------------------------- report + validation
def transitions(g, u_row):
    st, sd, prev = [], [], g["on0"]
    for val in u_row:
        st.append(int(val == 1 and prev == 0)); sd.append(int(val == 0 and prev == 1)); prev = val
    return st, sd


def make_report(case, u, prod, resv, ren, info, hour_start, convention):
    T, gens = case["T"], case["gens"]
    th = []
    for i, g in enumerate(gens):
        st, sd = transitions(g, u[i])
        out = prod[i] if convention == "actual" else [prod[i][t] - g["pmin"] * u[i][t] for t in range(T)]
        th.append(dict(name=g["name"], commitment=list(map(int, u[i])), production_MW=[float(v) for v in out],
                       reserve_MW=[float(v) for v in resv[i]], startup=st, shutdown=sd))
    rn = [dict(name=n, production_MW=[float(v) for v in ren[k]]) for k, n in enumerate(case["rn_names"])]
    hourly = []
    for t in range(T):
        hourly.append({"hour": t + hour_start, "demand_MW": float(case["demand"][t]),
                       "thermal_generation_MW": float(sum(prod[i][t] for i in range(len(gens)))),
                       "renewable_generation_MW": float(sum(ren[k][t] for k in range(len(ren)))),
                       "reserve_requirement_MW": float(case["reserve"][t]),
                       "scheduled_spinning_reserve_MW": float(sum(resv[i][t] for i in range(len(gens))))})
    bal = max(abs(h["thermal_generation_MW"] + h["renewable_generation_MW"] - h["demand_MW"]) for h in hourly)
    short = max(max(0.0, h["reserve_requirement_MW"] - h["scheduled_spinning_reserve_MW"]) for h in hourly)
    return {
        "case_name": "unit_commitment_schedule",
        "summary": {
            "solver_status": info["status"],
            "objective_cost": float(recompute_cost(case, u, prod)),
            "reported_mip_gap": info["gap"],
            "time_periods": T,
            "num_thermal_generators": len(gens),
            "num_renewable_generators": len(case["rn_names"]),
            "total_startups": int(sum(sum(r["startup"]) for r in th)),
            "total_shutdowns": int(sum(sum(r["shutdown"]) for r in th)),
            "max_demand_balance_violation_MW": float(bal),
            "max_reserve_shortfall_MW": float(short),
        },
        "thermal_generators": th,
        "renewable_generators": rn,
        "hourly_summary": hourly,
        "constraint_check": {k: "pending" for k in CHECK_KEYS},
    }


def validate(case, rep, convention="actual", solver_objective=None):
    """Independent checks reading only the case and the report arrays. Returns {family: [violations]}."""
    T, gens = case["T"], case["gens"]
    fails = {k: [] for k in CHECK_KEYS}
    fails["structure"] = []
    th = {r["name"]: r for r in rep.get("thermal_generators", [])}
    rn = {r["name"]: r for r in rep.get("renewable_generators", [])}
    if sorted(th) != sorted(case["th_names"]) or len(th) != len(rep["thermal_generators"]):
        fails["structure"].append("thermal names do not match the input exactly once each")
    if sorted(rn) != sorted(case["rn_names"]) or len(rn) != len(rep["renewable_generators"]):
        fails["structure"].append("renewable names do not match the input exactly once each")
    if fails["structure"]:
        return fails
    U, PR, RS = [], [], []
    for g in gens:
        r = th[g["name"]]
        for key in ["commitment", "production_MW", "reserve_MW", "startup", "shutdown"]:
            if len(r[key]) != T:
                fails["structure"].append(f"{g['name']}.{key} length != T")
        u = [int(round(x)) for x in r["commitment"]]
        if any(x not in (0, 1) for x in r["commitment"] + r["startup"] + r["shutdown"]):
            fails["startup_shutdown_logic"].append(f"{g['name']}: non-binary status/transition")
        prod = list(map(float, r["production_MW"]))
        if convention != "actual":
            prod = [prod[t] + g["pmin"] * u[t] for t in range(T)]
        U.append(u); PR.append(prod); RS.append(list(map(float, r["reserve_MW"])))
    for k, n in enumerate(case["rn_names"]):
        if len(rn[n]["production_MW"]) != T:
            fails["structure"].append(f"{n} length != T")
    if fails["structure"]:
        return fails

    for i, g in enumerate(gens):
        n, u, p, r = g["name"], U[i], PR[i], RS[i]
        rec = th[n]
        st, sd = transitions(g, u)
        if st != list(rec["startup"]) or sd != list(rec["shutdown"]):
            fails["startup_shutdown_logic"].append(f"{n}: startup/shutdown do not match commitment transitions")
        cap = g["pmax"] - g["pmin"]
        pa = [p[t] - g["pmin"] * u[t] for t in range(T)]           # above-minimum output
        for t in range(T):
            if u[t] == 0 and (abs(p[t]) > TOL or abs(r[t]) > TOL):
                fails["generator_limits"].append(f"{n} t{t}: offline but production/reserve nonzero")
            if u[t] == 1 and not (g["pmin"] - TOL <= p[t] <= g["pmax"] + TOL):
                fails["generator_limits"].append(f"{n} t{t}: output {p[t]} outside [{g['pmin']},{g['pmax']}]")
            if r[t] < -TOL:
                fails["generator_limits"].append(f"{n} t{t}: negative reserve")
            if g["must_run"] and u[t] != 1:
                fails["must_run"].append(f"{n} t{t}: must-run unit offline")
            if p[t] + r[t] > g["pmax"] * u[t] + TOL:
                fails["reserve_deliverability"].append(f"{n} t{t}: production+reserve above pmax")
            if st[t] and pa[t] + r[t] > cap - max(0.0, g["pmax"] - g["rsu"]) + TOL:
                fails["reserve_deliverability"].append(f"{n} t{t}: startup-period production+reserve above startup limit")
            if t + 1 < T and sd[t + 1] and pa[t] + r[t] > cap - max(0.0, g["pmax"] - g["rsd"]) + TOL:
                fails["reserve_deliverability"].append(f"{n} t{t}: pre-shutdown production+reserve above shutdown limit")
            prev = (g["p0"] - g["pmin"]) * g["on0"] if t == 0 else pa[t - 1]
            fam = "initial_conditions" if t == 0 else "ramping"
            if pa[t] + r[t] - prev > g["ru"] + TOL:
                fails[fam].append(f"{n} t{t}: ramp-up (incl. reserve) exceeded")
                fails["reserve_deliverability"].append(f"{n} t{t}: reserve not deliverable within ramp-up")
            if prev - pa[t] > g["rd"] + TOL:
                fails[fam].append(f"{n} t{t}: ramp-down exceeded")
        if g["on0"] and sd[0] and g["p0"] > g["rsd"] + TOL:
            fails["initial_conditions"].append(f"{n}: shut down in period 1 from output above shutdown limit")
        ut0 = min(T, max(0, g["ut"] - g["up0"]) * g["on0"])
        dt0 = min(T, max(0, g["dt"] - g["down0"]) * (1 - g["on0"]))
        if any(u[t] != 1 for t in range(ut0)):
            fails["initial_conditions"].append(f"{n}: initial minimum-up obligation ({ut0} periods) violated")
        if any(u[t] != 0 for t in range(dt0)):
            fails["initial_conditions"].append(f"{n}: initial minimum-down obligation ({dt0} periods) violated")
        for t in range(T):
            if st[t] and any(u[k] != 1 for k in range(t, min(T, t + g["ut"]))):
                fails["minimum_up_down"].append(f"{n}: started t{t} but off within {g['ut']} periods")
            if sd[t] and any(u[k] != 0 for k in range(t, min(T, t + g["dt"]))):
                fails["minimum_up_down"].append(f"{n}: stopped t{t} but on within {g['dt']} periods")

    for k, n in enumerate(case["rn_names"]):
        q = rn[n]["production_MW"]
        for t in range(T):
            if not (case["rmin"][k][t] - TOL <= q[t] <= case["rmax"][k][t] + TOL):
                fails["renewable_limits"].append(f"{n} t{t}: {q[t]} outside [{case['rmin'][k][t]},{case['rmax'][k][t]}]")
    for t in range(T):
        gen = sum(PR[i][t] for i in range(len(gens))) + sum(rn[n]["production_MW"][t] for n in case["rn_names"])
        if abs(gen - case["demand"][t]) > TOL * 10:
            fails["demand_balance"].append(f"t{t}: generation {gen:.4f} vs demand {case['demand'][t]:.4f}")
        if sum(RS[i][t] for i in range(len(gens))) < case["reserve"][t] - TOL:
            fails["spinning_reserve"].append(f"t{t}: reserve shortfall")
    cost = recompute_cost(case, U, PR)
    rep_cost = rep["summary"]["objective_cost"]
    if abs(cost - rep_cost) > 1e-6 * max(1.0, abs(cost)):
        fails["cost_consistency"].append(f"reported objective {rep_cost} != recomputed {cost}")
    if solver_objective is not None and abs(cost - solver_objective) > 1e-4 * max(1.0, abs(cost)):
        fails["cost_consistency"].append(f"solver objective {solver_objective} != recomputed {cost} (cost model mismatch)")
    s = rep["summary"]
    expect = dict(time_periods=T, num_thermal_generators=len(gens), num_renewable_generators=len(case["rn_names"]),
                  total_startups=sum(sum(th[g["name"]]["startup"]) for g in gens),
                  total_shutdowns=sum(sum(th[g["name"]]["shutdown"]) for g in gens))
    for k2, v in expect.items():
        if s.get(k2) != v:
            fails["structure"].append(f"summary.{k2}={s.get(k2)} expected {v}")
    return fails


def print_fails(fails):
    bad = False
    for k, v in fails.items():
        print(f"  {k:24s} {'pass' if not v else 'FAIL (%d)' % len(v)}")
        for msg in v[:5]:
            print(f"      - {msg}")
        bad |= bool(v)
    return not bad


# ----------------------------------------------------------------------------- CLI
def cmd_inspect(a):
    case, missing = load_case(a.case)
    if case is None:
        print("SCHEMA MISMATCH: the loader expects pglib-uc style fields (references/data-format.md).")
        for msg in missing[:40]:
            print("  -", msg)
        return 2
    errs, warns = parser_checks(case)
    if errs:
        for e in errs:
            print("ERROR:", e)
        return 3
    T, gens = case["T"], case["gens"]
    print(f"T={T}  thermal={len(gens)}  renewable={len(case['rn_names'])}")
    print(f"demand  min={case['demand'].min():.2f} max={case['demand'].max():.2f}   reserve max={case['reserve'].max():.2f}")
    print(f"thermal pmax total={sum(g['pmax'] for g in gens):.2f}  on at t0={sum(g['on0'] for g in gens)}  "
          f"must_run={[g['name'] for g in gens if g['must_run']]}")
    if len(case["rn_names"]):
        print(f"renewable max total: peak={case['rmax'].sum(0).max():.2f}  periods with min<max (curtailable) "
              f"cells={int((case['rmin'] < case['rmax']).sum())}")
        net = case["demand"] + case["reserve"] - case["rmin"].sum(0)
        print(f"peak demand+reserve-renewable_min={net.max():.2f}")
    print(f"nonconvex production curves: {[g['name'] for g in gens if not g['convex']] or 'none'}")
    print(f"startup tiers per unit: {sorted(set(len(g['tiers']) for g in gens))}")
    for w in warns:
        print("WARN:", w)
    return 0


def cmd_solve(a):
    case, missing = load_case(a.case)
    if case is None:
        print("SCHEMA MISMATCH; run `inspect` and convert the case first.", file=sys.stderr)
        return 2
    errs, warns = parser_checks(case)
    if errs:
        for e in errs:
            print("ERROR:", e, file=sys.stderr)
        return 3
    u, prod, resv, ren, info = build_and_solve(case, a.time_limit, a.mip_gap, not a.no_curtail, a.verbose,
                                              a.diagnose)
    rep = make_report(case, u, prod, resv, ren, info, a.hour_start, a.production_convention)
    fails = validate(case, rep, a.production_convention, info["solver_objective"])
    print(f"solver: status={info['status']} (scipy {info['scipy_status']}: {info['message']}) "
          f"time={info['seconds']}s gap={info['gap']}")
    print(f"objective (recomputed from arrays) = {rep['summary']['objective_cost']:.4f}; solver objective = {info['solver_objective']:.4f}")
    print("validation:")
    ok = print_fails(fails)
    if not ok:
        bad = a.out + ".FAILED.json"
        with open(bad, "w") as f:
            json.dump(rep, f, indent=1)
        print(f"VALIDATION FAILED: report NOT written to {a.out}; diagnostic copy at {bad}")
        return 1
    rep["constraint_check"] = {k: "pass" for k in CHECK_KEYS}
    with open(a.out, "w") as f:
        json.dump(rep, f, indent=2)
    s = rep["summary"]
    print(f"wrote {a.out}: startups={s['total_startups']} shutdowns={s['total_shutdowns']} "
          f"max_balance_violation={s['max_demand_balance_violation_MW']:.2e} max_reserve_shortfall={s['max_reserve_shortfall_MW']:.2e}")
    return 0


def cmd_validate(a):
    case, missing = load_case(a.case)
    if case is None:
        print("SCHEMA MISMATCH", file=sys.stderr)
        return 2
    parser_checks(case)
    try:
        f = open(a.report)
    except OSError as e:
        print(f"ERROR: cannot read report: {e}", file=sys.stderr)
        return 2
    with f:
        rep = json.load(f)
    fails = validate(case, rep, a.production_convention)
    print("validation:")
    return 0 if print_fails(fails) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inspect"); p.add_argument("case")
    p = sub.add_parser("solve"); p.add_argument("case"); p.add_argument("--out", required=True)
    p.add_argument("--time-limit", type=float, default=300.0, help="HiGHS wall-clock limit, seconds (default 300)")
    p.add_argument("--mip-gap", type=float, default=1e-3, help="relative MIP gap target (default 1e-3)")
    p.add_argument("--hour-start", type=int, default=1, help="label of the first hour in hourly_summary")
    p.add_argument("--production-convention", choices=["actual", "above_min"], default="actual")
    p.add_argument("--no-curtail", action="store_true", help="fix renewables at their hourly maximum")
    p.add_argument("--verbose", action="store_true", help="print HiGHS log")
    p.add_argument("--diagnose", action="store_true",
                   help="debug only: add priced balance/reserve slacks, print hours that need them, write no report")
    p = sub.add_parser("validate"); p.add_argument("case"); p.add_argument("report")
    p.add_argument("--production-convention", choices=["actual", "above_min"], default="actual")
    a = ap.parse_args()
    return {"inspect": cmd_inspect, "solve": cmd_solve, "validate": cmd_validate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
