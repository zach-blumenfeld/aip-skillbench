"""Shared unit-commitment logic: parse, build/solve the MILP, extract, validate, cost.

Conventions (kept in one place so model, validation and report never mix them):
- Internal thermal variable `pg` is output ABOVE minimum; reports use ACTUAL MW
  (actual = pmin * u + pg).
- Period index t is 0-based internally; report hour labels are t + 1.
- Resource order is the source order; names are opaque strings.
"""
import json
import math
import sys
import time

import numpy as np

TOL = 1e-5
FULL_MILP_SHARE = 0.25  # share of the time limit for the full MILP (dual bound)
LNS_STEP_SHARE = 0.08   # time cap per neighborhood sub-MILP, as a share of the time limit

# Concept -> accepted source keys (map by meaning, not one benchmark's names).
ALIASES = {
    "periods": ["time_periods", "periods", "num_periods", "T", "horizon"],
    "demand": ["demand", "load", "system_demand", "net_load"],
    "reserves": ["reserves", "reserve", "spinning_reserve", "reserve_requirement", "reserve_requirements"],
    "thermal": ["thermal_generators", "thermal", "generators", "thermal_units"],
    "renewable": ["renewable_generators", "renewables", "renewable", "renewable_units"],
}
GEN_ALIASES = {
    "must_run": ["must_run", "mustrun"],
    "pmin": ["power_output_minimum", "pmin", "min_output", "p_min"],
    "pmax": ["power_output_maximum", "pmax", "max_output", "p_max"],
    "ru": ["ramp_up_limit", "ramp_up", "ramp_up_rate"],
    "rd": ["ramp_down_limit", "ramp_down", "ramp_down_rate"],
    "su": ["ramp_startup_limit", "startup_limit", "startup_ramp"],
    "sd": ["ramp_shutdown_limit", "shutdown_limit", "shutdown_ramp"],
    "ut": ["time_up_minimum", "min_up", "min_up_time"],
    "dt": ["time_down_minimum", "min_down", "min_down_time"],
    "p0": ["power_output_t0", "initial_output", "p0"],
    "on0": ["unit_on_t0", "initial_status", "status_t0"],
    "up0": ["time_up_t0", "initial_time_up"],
    "down0": ["time_down_t0", "initial_time_down"],
    "startup": ["startup", "startup_costs", "startup_tiers"],
    "curve": ["piecewise_production", "production_cost_curve", "cost_curve"],
}


def log(*a):
    print(*a, file=sys.stderr)


def _pick(d, names, what, required=True):
    for n in names:
        if n in d:
            return d[n]
    if required:
        raise KeyError(f"missing field for {what}; looked for {names}; available keys: {sorted(d)[:40]}")
    return None


def _as_named_list(obj, what):
    """Resources may be a dict keyed by name or a list of objects with a name."""
    if isinstance(obj, dict):
        out = []
        for k, v in obj.items():
            v = dict(v)
            v.setdefault("name", k)
            out.append((str(k), v))
        return out
    if isinstance(obj, list):
        out = []
        for i, v in enumerate(obj):
            nm = v.get("name", v.get("id", f"{what}_{i}"))
            out.append((str(nm), v))
        return out
    raise TypeError(f"{what} must be a dict or list, got {type(obj).__name__}")


def _series(v, T, what):
    if isinstance(v, (int, float)):
        return np.full(T, float(v))
    a = np.asarray(v, dtype=float)
    if a.shape != (T,):
        raise ValueError(f"{what}: expected length {T}, got shape {a.shape}")
    return a


def load_case(path):
    with open(path) as f:
        raw = json.load(f)
    issues = []
    per = _pick(raw, ALIASES["periods"], "time periods")
    T = int(per) if not isinstance(per, list) else len(per)
    demand = _series(_pick(raw, ALIASES["demand"], "demand"), T, "demand")
    res_raw = _pick(raw, ALIASES["reserves"], "reserve requirement", required=False)
    if res_raw is None:
        issues.append("no reserve requirement field found; using zero reserve")
        res_raw = 0.0
    reserves = _series(res_raw, T, "reserves")

    therm = []
    for name, g in _as_named_list(_pick(raw, ALIASES["thermal"], "thermal generators"), "thermal"):
        p = {k: _pick(g, GEN_ALIASES[k], f"{name}.{k}", required=k in ("pmin", "pmax", "curve")) for k in GEN_ALIASES}
        pmin, pmax = float(p["pmin"]), float(p["pmax"])
        big = pmax  # missing ramp/startup limits -> unrestrictive
        on0 = int(round(float(p["on0"] if p["on0"] is not None else 0)))
        gen = {
            "name": name,
            "must_run": int(p["must_run"] or 0),
            "pmin": pmin, "pmax": pmax,
            "ru": float(p["ru"] if p["ru"] is not None else big),
            "rd": float(p["rd"] if p["rd"] is not None else big),
            "su": float(p["su"] if p["su"] is not None else big),
            "sd": float(p["sd"] if p["sd"] is not None else big),
            "ut": max(1, int(p["ut"] or 1)), "dt": max(1, int(p["dt"] or 1)),
            "on0": on0,
            "p0": float(p["p0"] if p["p0"] is not None else (pmin if on0 else 0.0)),
            "up0": int(p["up0"] or 0), "down0": int(p["down0"] or 0),
        }
        st = p["startup"] or [{"lag": 1, "cost": 0.0}]
        if isinstance(st, (int, float)):
            st = [{"lag": 1, "cost": float(st)}]
        gen["startup"] = sorted(({"lag": int(s["lag"]), "cost": float(s["cost"])} for s in st), key=lambda s: s["lag"])
        pts = sorted((float(c["mw"]), float(c["cost"])) for c in p["curve"])
        gen["curve"] = pts
        # parser-level checks
        if pmin > pmax + TOL:
            raise ValueError(f"{name}: pmin {pmin} > pmax {pmax}")
        if len(pts) < 1:
            raise ValueError(f"{name}: empty production cost curve")
        if len({x for x, _ in pts}) != len(pts):
            issues.append(f"{name}: repeated cost-curve MW points")
        if abs(pts[0][0] - pmin) > 1e-6 or abs(pts[-1][0] - pmax) > 1e-6:
            issues.append(f"{name}: cost curve spans [{pts[0][0]},{pts[-1][0]}] not [pmin,pmax]=[{pmin},{pmax}]; interpolating/extrapolating")
        if len({s['lag'] for s in gen['startup']}) != len(gen['startup']):
            issues.append(f"{name}: duplicate startup lags")
        if on0 and not (pmin - TOL <= gen["p0"] <= pmax + TOL):
            issues.append(f"{name}: initial output {gen['p0']} outside [pmin,pmax] while on")
        if not on0 and gen["p0"] > TOL:
            issues.append(f"{name}: initial output {gen['p0']} > 0 while off")
        if on0 and gen["up0"] <= 0:
            issues.append(f"{name}: on at t0 but time_up_t0 = {gen['up0']}")
        if not on0 and gen["down0"] <= 0:
            issues.append(f"{name}: off at t0 but time_down_t0 = {gen['down0']}; treating as long offline")
            gen["down0"] = max(gen["down0"], max(s["lag"] for s in gen["startup"]))
        therm.append(gen)

    ren = []
    ren_raw = _pick(raw, ALIASES["renewable"], "renewable generators", required=False) or {}
    for name, r in _as_named_list(ren_raw, "renewable"):
        rmin = _series(_pick(r, GEN_ALIASES["pmin"], f"{name}.min"), T, f"{name}.min")
        rmax = _series(_pick(r, GEN_ALIASES["pmax"], f"{name}.max"), T, f"{name}.max")
        if np.any(rmin > rmax + TOL):
            raise ValueError(f"{name}: renewable min > max in some period")
        ren.append({"name": name, "min": rmin, "max": rmax})

    names = [g["name"] for g in therm] + [r["name"] for r in ren]
    if len(set(names)) != len(names):
        raise ValueError("duplicate resource names across thermal/renewable sets")
    if not (np.all(np.isfinite(demand)) and np.all(np.isfinite(reserves))):
        raise ValueError("non-finite demand or reserve values")
    return {"T": T, "demand": demand, "reserves": reserves, "thermal": therm, "renewable": ren}, issues


# ---------------- cost curve helpers ----------------

def curve_on_range(g):
    """Breakpoints covering exactly [pmin, pmax] (interpolate inside, extend last slope)."""
    pts = g["curve"]
    pmin, pmax = g["pmin"], g["pmax"]
    xs = [x for x, _ in pts]
    if len(pts) == 1:
        return [(pmin, pts[0][1])] if pmax - pmin <= TOL else [(pmin, pts[0][1]), (pmax, pts[0][1])]

    def f(x):
        if x <= xs[0]:
            (x0, y0), (x1, y1) = pts[0], pts[1]
        elif x >= xs[-1]:
            (x0, y0), (x1, y1) = pts[-2], pts[-1]
        else:
            k = max(i for i in range(len(xs)) if xs[i] <= x)
            k = min(k, len(pts) - 2)
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        return y0 + (x - x0) * (y1 - y0) / (x1 - x0) if x1 > x0 else y0

    inner = [(x, y) for x, y in pts if pmin + 1e-9 < x < pmax - 1e-9]
    out = [(pmin, f(pmin))] + inner
    if pmax > pmin + 1e-9:
        out.append((pmax, f(pmax)))
    return out


def is_convex(g):
    c = curve_on_range(g)
    sl = [(y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(c, c[1:])]
    return all(a <= b + 1e-9 for a, b in zip(sl, sl[1:]))


def production_cost(g, mw):
    c = curve_on_range(g)
    if mw <= c[0][0]:
        return c[0][1]
    for (x0, y0), (x1, y1) in zip(c, c[1:]):
        if x0 - 1e-9 <= mw <= x1 + 1e-9:
            return y0 + (min(mw, x1) - x0) * (y1 - y0) / (x1 - x0)
    return c[-1][1]


def startup_cost(g, offline_duration):
    """Largest tier lag not exceeding prior offline duration; first tier if none."""
    chosen = g["startup"][0]
    for tier in g["startup"]:
        if tier["lag"] <= offline_duration:
            chosen = tier
        else:
            break
    return chosen["cost"]


def startup_windows(g):
    """Offline-duration window [lo, hi] (inclusive) for each tier except the last (unbounded)."""
    lags = [s["lag"] for s in g["startup"]]
    wins = []
    for s in range(len(lags) - 1):
        lo = 1 if s == 0 else lags[s]
        wins.append((lo, lags[s + 1] - 1))
    return wins


# ---------------- MILP ----------------

class Model:
    def __init__(self):
        self.n = 0
        self.owner = []  # thermal unit index owning each variable (-1 for system/renewable)
        self.period = []  # period index of each variable (last axis of every allocation is time)
        self.lb, self.ub, self.integ, self.c = [], [], [], []
        self.rows, self.cols, self.vals, self.rlo, self.rhi = [], [], [], [], []
        self.nrow = 0

    def alloc(self, shape, lb=0.0, ub=math.inf, integer=False, cost=0.0, owner=None):
        size = int(np.prod(shape))
        self.period += list(range(shape[-1])) * (size // shape[-1])
        if owner is None and len(shape) == 2:
            self.owner += [i for i in range(shape[0]) for _ in range(shape[1])]
        else:
            self.owner += [-1 if owner is None else owner] * size
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
                self.rows.append(self.nrow)
                self.cols.append(int(j))
                self.vals.append(float(a))
        self.rlo.append(float(lo))
        self.rhi.append(float(hi))
        self.nrow += 1


def build_and_solve(case, opts, time_limit, gap):
    from scipy.optimize import milp, LinearConstraint, Bounds
    from scipy.sparse import csr_matrix

    T, G, R = case["T"], len(case["thermal"]), len(case["renewable"])
    INF = math.inf
    m = Model()
    u = m.alloc((G, T), 0, 1, True)
    v = m.alloc((G, T), 0, 1, True)
    w = m.alloc((G, T), 0, 1, True)
    pg = m.alloc((G, T))            # output above minimum
    rg = m.alloc((G, T))            # spinning reserve
    rn = m.alloc((R, T), owner=-1) if R else np.zeros((0, T), dtype=int)
    segs, cats, zs = [], [], []
    for gi, g in enumerate(case["thermal"]):
        curve = curve_on_range(g)
        widths = [x1 - x0 for (x0, _), (x1, _) in zip(curve, curve[1:])]
        slopes = [(y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(curve, curve[1:])]
        s_idx = [m.alloc((T,), 0, wd, False, sl, owner=gi) for wd, sl in zip(widths, slopes)]
        segs.append((s_idx, widths))
        for t in range(T):
            m.c[u[gi, t]] = curve[0][1]                 # cost at pmin when online
        cats.append([m.alloc((T,), 0, 1, True, s["cost"], owner=gi) for s in g["startup"]])
        z = []
        if not is_convex(g):                                   # enforce fill order with binaries
            z = [m.alloc((T,), 0, 1, True, owner=gi) for _ in range(len(widths) - 1)]
        zs.append(z)

    # renewables bounds
    for ri, r in enumerate(case["renewable"]):
        for t in range(T):
            hi = r["max"][t]
            lo = r["min"][t] if opts["renewables_curtailable"] else hi
            m.lb[rn[ri, t]], m.ub[rn[ri, t]] = lo, hi

    for gi, g in enumerate(case["thermal"]):
        pmin, pmax = g["pmin"], g["pmax"]
        span = pmax - pmin
        su_red = max(0.0, pmax - g["su"])
        sd_red = max(0.0, pmax - g["sd"])
        u0 = g["on0"]
        pg0 = u0 * max(0.0, g["p0"] - pmin)
        # initial min up/down obligations and must-run (variable bounds)
        if u0:
            for t in range(min(T, max(0, g["ut"] - g["up0"]))):
                m.lb[u[gi, t]] = 1
        else:
            for t in range(min(T, max(0, g["dt"] - g["down0"]))):
                m.ub[u[gi, t]] = 0
        if g["must_run"]:
            for t in range(T):
                m.lb[u[gi, t]] = 1
        if u0 and g["p0"] > g["sd"] + TOL:                # cannot shut down from above SD
            m.ub[w[gi, 0]] = 0
        if opts["enforce_post_horizon"]:
            for t in range(T):
                if t + g["ut"] > T:
                    m.ub[v[gi, t]] = 0
                if t + g["dt"] > T:
                    m.ub[w[gi, t]] = 0
        s_idx, widths = segs[gi]
        wins = startup_windows(g)
        for t in range(T):
            # transition logic: u[t] - u[t-1] = v[t] - w[t]
            if t == 0:
                m.add_row([(u[gi, 0], 1), (v[gi, 0], -1), (w[gi, 0], 1)], u0, u0)
            else:
                m.add_row([(u[gi, t], 1), (u[gi, t - 1], -1), (v[gi, t], -1), (w[gi, t], 1)], 0, 0)
            m.add_row([(v[gi, t], 1), (w[gi, t], 1)], -INF, 1)
            # minimum up / down (windows truncated at horizon start)
            m.add_row([(v[gi, i], 1) for i in range(max(0, t - g["ut"] + 1), t + 1)] + [(u[gi, t], -1)], -INF, 0)
            m.add_row([(w[gi, i], 1) for i in range(max(0, t - g["dt"] + 1), t + 1)] + [(u[gi, t], 1)], -INF, 1)
            # startup category selection
            m.add_row([(cats[gi][s][t], 1) for s in range(len(cats[gi]))] + [(v[gi, t], -1)], 0, 0)
            for s, (lo, hi) in enumerate(wins):
                terms, const = [(cats[gi][s][t], 1)], 0.0
                for i in range(lo, hi + 1):
                    k = t - i
                    if k >= 0:
                        terms.append((w[gi, k], -1))
                    elif not u0 and k == -g["down0"]:
                        const += 1.0
                m.add_row(terms, -INF, const)
            # production segments: pg = sum seg, seg <= width * u
            m.add_row([(s_idx[k][t], 1) for k in range(len(widths))] + [(pg[gi, t], -1)], 0, 0)
            for k, wd in enumerate(widths):
                m.add_row([(s_idx[k][t], 1), (u[gi, t], -wd)], -INF, 0)
            for k, zk in enumerate(zs[gi]):
                m.add_row([(s_idx[k][t], 1), (zk[t], -widths[k])], 0, INF)
                m.add_row([(s_idx[k + 1][t], 1), (zk[t], -widths[k + 1])], -INF, 0)
            # joint capacity incl. startup/shutdown capability (production + reserve)
            if t < T - 1 and g["ut"] > 1:
                m.add_row([(pg[gi, t], 1), (rg[gi, t], 1), (u[gi, t], -span), (v[gi, t], su_red), (w[gi, t + 1], sd_red)], -INF, 0)
            else:
                m.add_row([(pg[gi, t], 1), (rg[gi, t], 1), (u[gi, t], -span), (v[gi, t], su_red)], -INF, 0)
                if t < T - 1:
                    m.add_row([(pg[gi, t], 1), (rg[gi, t], 1), (u[gi, t], -span), (w[gi, t + 1], sd_red)], -INF, 0)
            # reserve only from online units, and deployable within one ramp
            m.add_row([(rg[gi, t], 1), (u[gi, t], -g["ru"])], -INF, 0)
            # ramping on above-minimum output; reserve counts toward ramp-up. Tightened with
            # v/w (same integer points): a starting unit moves at most min(RU, SUcap-pmin),
            # a stopping unit drops at most min(RD, SDcap-pmin).
            su_ramp = max(0.0, min(g["ru"], min(pmax, g["su"]) - pmin))
            sd_ramp = max(0.0, min(g["rd"], min(pmax, g["sd"]) - pmin))
            if t == 0:
                m.add_row([(pg[gi, 0], 1), (rg[gi, 0], 1), (u[gi, 0], -g["ru"]), (v[gi, 0], g["ru"] - su_ramp)], -INF, pg0)
                m.add_row([(pg[gi, 0], -1), (u[gi, 0], -g["rd"]), (w[gi, 0], -sd_ramp)], -INF, -pg0)
            else:
                m.add_row([(pg[gi, t], 1), (rg[gi, t], 1), (pg[gi, t - 1], -1), (u[gi, t], -g["ru"]),
                           (v[gi, t], g["ru"] - su_ramp)], -INF, 0)
                m.add_row([(pg[gi, t - 1], 1), (pg[gi, t], -1), (u[gi, t], -g["rd"]), (w[gi, t], -sd_ramp)], -INF, 0)

    for t in range(T):
        terms = [(pg[gi, t], 1) for gi in range(G)] + [(u[gi, t], g["pmin"]) for gi, g in enumerate(case["thermal"])]
        terms += [(rn[ri, t], 1) for ri in range(R)]
        m.add_row(terms, case["demand"][t], case["demand"][t])
        rterms = [(rg[gi, t], 1) for gi in range(G)]
        const = 0.0
        if opts["renewable_reserve_allowed"]:
            rterms += [(rn[ri, t], -1) for ri in range(R)]
            const = -sum(r["max"][t] for r in case["renewable"])
        m.add_row(rterms, case["reserves"][t] + const, INF)

    A = csr_matrix((m.vals, (m.rows, m.cols)), shape=(m.nrow, m.n))
    cons = LinearConstraint(A, m.rlo, m.rhi)
    c = np.array(m.c)
    lb, ub = np.array(m.lb, float), np.array(m.ub, float)
    integ = np.array(m.integ)
    ib = integ == 1
    log(f"model: {m.n} vars ({int(ib.sum())} integer), {m.nrow} rows")
    t_start = time.time()

    def remaining():
        return float(time_limit) - (time.time() - t_start)

    def run_milp(lo, hi, tl, gp, relax=False):
        return milp(c=c, integrality=np.zeros_like(integ) if relax else integ, bounds=Bounds(lo, hi),
                    constraints=cons, options={"time_limit": max(1.0, tl), "mip_rel_gap": gp, "disp": False})

    info = {"variables": int(m.n), "integer_variables": int(ib.sum()), "rows": int(m.nrow), "phases": []}
    # Phase 0: LP relaxation (bound fallback and RINS reference).
    lp = run_milp(lb, ub, remaining(), gap, relax=True)
    x_lp = lp.x
    info["lp_relaxation_objective"] = None if x_lp is None else float(lp.fun)
    if x_lp is None:
        info.update(milp_status=int(lp.status), milp_message=f"LP relaxation: {lp.message}",
                    mip_objective=None, mip_gap=None, mip_dual_bound=None)
        return None, info
    best_x, best_obj = None, math.inf

    def consider(x, obj):
        nonlocal best_x, best_obj
        if x is not None and obj < best_obj - 1e-7 * max(1.0, abs(obj)):
            best_x, best_obj = x, obj
            return True
        return False

    def sub_milp(name, fix, ref, tl):
        lo2, hi2 = lb.copy(), ub.copy()
        lo2[fix] = ref[fix]
        hi2[fix] = ref[fix]
        sub = run_milp(lo2, hi2, min(remaining(), tl), gap / 10)
        obj = None if sub.x is None else float(sub.fun)
        info["phases"].append({"phase": name, "fixed_binaries": int(fix.sum()), "status": int(sub.status),
                               "objective": obj, "seconds_left": round(remaining(), 1)})
        return consider(sub.x, obj if obj is not None else math.inf)

    budget = float(time_limit)
    # Phase 1: LP-guided start -- fix binaries that are integral in the LP relaxation.
    lp_ref = np.round(x_lp)
    sub_milp("lp_fix", ib & (np.abs(x_lp - lp_ref) < 1e-6), lp_ref, max(15.0, 0.15 * budget))
    # Phase 2: full MILP, mainly for a valid dual bound (and possibly a better incumbent).
    res = run_milp(lb, ub, FULL_MILP_SHARE * budget, gap)
    info["phases"].append({"phase": "full_milp", "status": int(res.status),
                           "objective": None if res.x is None else float(res.fun),
                           "seconds_left": round(remaining(), 1)})
    consider(res.x, math.inf if res.x is None else float(res.fun))
    bound = getattr(res, "mip_dual_bound", None)
    if bound is None or not np.isfinite(bound):
        bound = float(lp.fun)
    proven = res.status == 0
    # Phase 3: large-neighborhood search. Fix most binaries to the incumbent and re-solve the
    # small sub-MILP: overlapping time windows (most productive in tests), RINS (fix where
    # incumbent and LP agree), and unit groups (units sorted by min up time and capacity,
    # ~6 chunks). Sub-solutions are feasible for the full model; the full model's dual bound
    # stays valid for the gap.
    owner, period = np.array(m.owner), np.array(m.period)
    order = sorted(range(G), key=lambda i: (case["thermal"][i]["ut"], case["thermal"][i]["pmax"]))
    n_chunks = min(6, G)
    chunks = [order[k * G // n_chunks:(k + 1) * G // n_chunks] for k in range(n_chunks)]
    W = max(4, T // 4)
    windows = [(a, min(T, a + W)) for a in range(0, max(1, T - W // 2), max(1, W // 2))]
    hoods = [(f"hours_{a + 1}_{b}", (a, b)) for a, b in windows] + [("rins", None)] + \
            [(f"units_{k}", ch) for k, ch in enumerate(chunks)]
    k, misses = 0, 0
    while best_x is not None and not proven and remaining() > 5.0 and misses < len(hoods):
        name, arg = hoods[k % len(hoods)]
        k += 1
        ref = np.round(best_x)
        if name == "rins":
            fix = ib & (np.abs(x_lp - ref) < 1e-6)
        elif name.startswith("units_"):
            fix = ib & ~np.isin(owner, arg)
        else:
            fix = ib & ~((period >= arg[0]) & (period < arg[1]))
        improved = sub_milp(name, fix, ref, max(15.0, LNS_STEP_SHARE * budget))
        misses = 0 if improved else misses + 1
    gap_now = None if best_x is None else max(0.0, (best_obj - bound) / max(1e-9, abs(best_obj)))
    proven = proven or (gap_now is not None and gap_now <= gap + 1e-12)
    info.update(milp_status=0 if proven else int(res.status if best_x is not None else 1),
                milp_message=str(res.message), mip_objective=None if best_x is None else best_obj,
                mip_gap=gap_now, mip_dual_bound=float(bound))
    if best_x is None:
        return None, info
    x = best_x
    frac = float(np.max(np.abs(x[ib] - np.round(x[ib])))) if ib.any() else 0.0
    info["max_binary_fractionality"] = frac
    if frac > 1e-4:
        info["milp_message"] += f" | binaries not integral (max frac {frac:.2e})"
        return None, info
    # Fixed-commitment polish LP: same model (every family), binaries fixed -> clean continuous values.
    lb2, ub2 = lb.copy(), ub.copy()
    xi = np.round(x[ib])
    lb2[ib] = xi
    ub2[ib] = xi
    res2 = run_milp(lb2, ub2, 120.0, gap, relax=True)
    if res2.x is not None and res2.status == 0:
        x = res2.x
        x[ib] = xi
        info["polish_lp"] = "applied"
    else:
        x[ib] = xi
        info["polish_lp"] = f"skipped ({res2.message})"
    info["model_objective"] = float(c @ x)

    sched = {"thermal": [], "renewable": []}
    for gi, g in enumerate(case["thermal"]):
        uu = np.round(x[u[gi]]).astype(int)
        prod = g["pmin"] * uu + np.maximum(x[pg[gi]], 0.0) * uu
        rr = np.maximum(x[rg[gi]], 0.0) * uu
        sched["thermal"].append({"name": g["name"], "commitment": uu.tolist(),
                                 "production_MW": [round(float(a), 6) for a in prod],
                                 "reserve_MW": [round(float(a), 6) for a in rr],
                                 "startup": np.round(x[v[gi]]).astype(int).tolist(),
                                 "shutdown": np.round(x[w[gi]]).astype(int).tolist()})
    for ri, r in enumerate(case["renewable"]):
        sched["renewable"].append({"name": r["name"],
                                   "production_MW": [round(float(np.clip(x[rn[ri, t]], r["min"][t], r["max"][t])), 6) for t in range(T)]})
    return sched, info


def status_label(info):
    st = info["milp_status"]
    if st == 0:
        return "optimal"
    if info.get("mip_objective") is not None:
        return "time_limit_feasible" if st == 1 else "suboptimal_feasible"
    return "infeasible" if st == 2 else "no_incumbent"


def reported_gap(info):
    g = info.get("mip_gap")
    if g is not None and np.isfinite(g) and g >= 0:
        return float(g)
    ob, db = info.get("mip_objective"), info.get("mip_dual_bound")
    if ob is not None and db is not None and np.isfinite(db):
        return max(0.0, (ob - db) / max(1e-9, abs(ob)))
    return None


# ---------------- independent validation (input data + arrays only) ----------------

def validate(case, sched, opts, model_objective=None):
    T = case["T"]
    th = {g["name"]: g for g in case["thermal"]}
    rn = {r["name"]: r for r in case["renewable"]}
    fails = {k: [] for k in ["demand_balance", "spinning_reserve", "reserve_deliverability", "generator_limits",
                             "must_run", "ramping", "minimum_up_down", "startup_shutdown_logic",
                             "initial_conditions", "renewable_limits", "cost_consistency"]}
    tol = 1e-4

    def bad(k, msg):
        if len(fails[k]) < 20:
            fails[k].append(msg)

    names_t = [s["name"] for s in sched["thermal"]]
    names_r = [s["name"] for s in sched["renewable"]]
    if sorted(names_t) != sorted(th) or len(set(names_t)) != len(names_t):
        bad("generator_limits", "thermal name set mismatch with input")
    if sorted(names_r) != sorted(rn) or len(set(names_r)) != len(names_r):
        bad("renewable_limits", "renewable name set mismatch with input")

    tot_th, tot_rn, tot_res = np.zeros(T), np.zeros(T), np.zeros(T)
    total_cost, starts, stops = 0.0, 0, 0
    for s in sched["thermal"]:
        g = th[s["name"]]
        u = np.array(s["commitment"]); p = np.array(s["production_MW"], float); r = np.array(s["reserve_MW"], float)
        v = np.array(s["startup"]); w = np.array(s["shutdown"])
        for arr, nm in ((u, "commitment"), (p, "production"), (r, "reserve"), (v, "startup"), (w, "shutdown")):
            if len(arr) != T:
                bad("generator_limits", f"{g['name']}: {nm} length {len(arr)} != {T}")
                return {"ok": False, "checks": {k: "fail" for k in fails}, "failures": fails}
        if not all(x in (0, 1) for x in list(u) + list(v) + list(w)):
            bad("startup_shutdown_logic", f"{g['name']}: non-binary status/transition")
        tot_th += p; tot_res += r
        starts += int(v.sum()); stops += int(w.sum())
        prev = g["on0"]
        off_run = g["down0"] if not g["on0"] else 0
        for t in range(T):
            if v[t] != int(u[t] == 1 and prev == 0) or w[t] != int(u[t] == 0 and prev == 1):
                bad("startup_shutdown_logic", f"{g['name']} h{t+1}: transition flags do not match commitment")
            if u[t] == 0:
                if abs(p[t]) > tol or abs(r[t]) > tol:
                    bad("generator_limits", f"{g['name']} h{t+1}: offline but p={p[t]} r={r[t]}")
            else:
                if p[t] < g["pmin"] - tol or p[t] > g["pmax"] + tol:
                    bad("generator_limits", f"{g['name']} h{t+1}: p={p[t]} outside [{g['pmin']},{g['pmax']}]")
                if r[t] < -tol or p[t] + r[t] > g["pmax"] + tol:
                    bad("reserve_deliverability", f"{g['name']} h{t+1}: p+r={p[t]+r[t]} > pmax")
                if r[t] > g["ru"] + tol:
                    bad("reserve_deliverability", f"{g['name']} h{t+1}: r={r[t]} > ramp_up {g['ru']}")
                if v[t] == 1 and p[t] + r[t] > min(g["pmax"], g["su"]) + tol:
                    bad("reserve_deliverability", f"{g['name']} h{t+1}: startup p+r={p[t]+r[t]} > startup limit {g['su']}")
                if t + 1 < T and u[t + 1] == 0 and p[t] + r[t] > min(g["pmax"], g["sd"]) + tol:
                    bad("reserve_deliverability", f"{g['name']} h{t+1}: pre-shutdown p+r={p[t]+r[t]} > shutdown limit {g['sd']}")
            if g["must_run"] and u[t] != 1:
                bad("must_run", f"{g['name']} h{t+1}: must-run unit offline")
            # ramping on above-minimum output (reserve counts toward ramp-up)
            a_prev = (g["p0"] - g["pmin"]) * g["on0"] if t == 0 else (p[t - 1] - g["pmin"]) * u[t - 1]
            a_now = (p[t] - g["pmin"]) * u[t]
            key = "initial_conditions" if t == 0 else "ramping"
            if a_now + r[t] * u[t] - a_prev > g["ru"] + tol:
                bad(key, f"{g['name']} h{t+1}: ramp up {a_now + r[t] - a_prev:.3f} > {g['ru']}")
            if a_prev - a_now > g["rd"] + tol:
                bad(key, f"{g['name']} h{t+1}: ramp down {a_prev - a_now:.3f} > {g['rd']}")
            if t == 0 and w[0] == 1 and g["p0"] > g["sd"] + tol:
                bad("initial_conditions", f"{g['name']}: shut down at h1 from p0={g['p0']} > SD {g['sd']}")
            # minimum up/down windows (truncated at horizon end)
            if v[t] == 1:
                if not np.all(u[t:min(T, t + g["ut"])] == 1):
                    bad("minimum_up_down", f"{g['name']} h{t+1}: started but off within min up {g['ut']}")
                total_cost += startup_cost(g, off_run)
            if w[t] == 1 and not np.all(u[t:min(T, t + g["dt"])] == 0):
                bad("minimum_up_down", f"{g['name']} h{t+1}: stopped but on within min down {g['dt']}")
            if opts.get("enforce_post_horizon"):
                if v[t] == 1 and t + g["ut"] > T:
                    bad("minimum_up_down", f"{g['name']} h{t+1}: start leaves min-up obligation past horizon")
                if w[t] == 1 and t + g["dt"] > T:
                    bad("minimum_up_down", f"{g['name']} h{t+1}: stop leaves min-down obligation past horizon")
            if u[t] == 1:
                total_cost += production_cost(g, p[t])
            off_run = 0 if u[t] == 1 else off_run + 1
            prev = u[t]
        # initial obligations
        if g["on0"]:
            n = min(T, max(0, g["ut"] - g["up0"]))
            if not np.all(u[:n] == 1):
                bad("initial_conditions", f"{g['name']}: initial min-up obligation ({n} h) violated")
        else:
            n = min(T, max(0, g["dt"] - g["down0"]))
            if not np.all(u[:n] == 0):
                bad("initial_conditions", f"{g['name']}: initial min-down obligation ({n} h) violated")

    for s in sched["renewable"]:
        r = rn[s["name"]]
        p = np.array(s["production_MW"], float)
        if len(p) != T:
            bad("renewable_limits", f"{r['name']}: length {len(p)}")
            continue
        lo = r["min"] if opts["renewables_curtailable"] else r["max"]
        if np.any(p < lo - tol) or np.any(p > r["max"] + tol):
            bad("renewable_limits", f"{r['name']}: output outside hourly bounds")
        tot_rn += p
    res_avail = tot_res.copy()
    if opts.get("renewable_reserve_allowed"):
        res_avail += sum(r["max"] for r in case["renewable"]) - tot_rn
    bal = np.abs(tot_th + tot_rn - case["demand"])
    short = np.maximum(case["reserves"] - res_avail, 0.0)
    for t in range(T):
        if bal[t] > 1e-3:
            bad("demand_balance", f"h{t+1}: |gen - demand| = {bal[t]:.6f}")
        if short[t] > 1e-3:
            bad("spinning_reserve", f"h{t+1}: reserve shortfall {short[t]:.6f}")
    if model_objective is not None and abs(model_objective - total_cost) > 1e-4 * max(1.0, abs(total_cost)):
        bad("cost_consistency", f"recomputed cost {total_cost:.4f} != model objective {model_objective:.4f}")
    checks = {k: ("pass" if not v else "fail") for k, v in fails.items()}
    return {
        "ok": all(c == "pass" for c in checks.values()),
        "checks": checks,
        "failures": {k: v for k, v in fails.items() if v},
        "recomputed_cost": round(total_cost, 6),
        "total_startups": starts, "total_shutdowns": stops,
        "max_demand_balance_violation_MW": float(bal.max()) if T else 0.0,
        "max_reserve_shortfall_MW": float(short.max()) if T else 0.0,
        "hourly": {"thermal": tot_th.tolist(), "renewable": tot_rn.tolist(), "reserve": tot_res.tolist()},
    }


def read_stdin():
    payload = json.load(sys.stdin)
    return payload.get("state", {})


def emit(obj):
    json.dump(obj, sys.stdout)
    sys.stdout.write("\n")
