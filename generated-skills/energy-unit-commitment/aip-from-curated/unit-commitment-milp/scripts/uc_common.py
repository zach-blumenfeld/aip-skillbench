"""Shared loader, parser-level checks, and cost rules for the unit-commitment-milp scripts.

Canonical case schema (pglib-uc / UnitCommitment.jl style JSON):
  time_periods: int T
  demand: [T] MW;  reserves: [T] MW (system spinning reserve requirement)
  thermal_generators: {name: {must_run, power_output_minimum, power_output_maximum,
      ramp_up_limit, ramp_down_limit, ramp_startup_limit, ramp_shutdown_limit,
      time_up_minimum, time_down_minimum, power_output_t0, unit_on_t0,
      time_up_t0, time_down_t0, startup: [{lag, cost}], piecewise_production: [{mw, cost}]}}
  renewable_generators: {name: {power_output_minimum: [T], power_output_maximum: [T]}}
A list of objects carrying "name" is accepted in place of either name-keyed dict.
Source order of resources is preserved everywhere.
"""
import json
import math

THERMAL_KEYS = [
    "must_run", "power_output_minimum", "power_output_maximum",
    "ramp_up_limit", "ramp_down_limit", "ramp_startup_limit", "ramp_shutdown_limit",
    "time_up_minimum", "time_down_minimum", "power_output_t0", "unit_on_t0",
    "time_up_t0", "time_down_t0", "startup", "piecewise_production",
]
TOP_KEYS = ["time_periods", "demand", "reserves", "thermal_generators"]
TOL = 1e-4


def read_stdin(stream):
    raw = stream.read()
    payload = json.loads(raw) if raw.strip() else {}
    return payload.get("currentState", payload)


def _as_named(obj, kind, errors):
    """Return an ordered list of (name, record); dict keys or record['name'] are the IDs."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append((str(k), v))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if not isinstance(v, dict) or "name" not in v:
                errors.append(f"{kind}[{i}] has no 'name'")
                continue
            out.append((str(v["name"]), v))
    else:
        errors.append(f"{kind} is neither an object nor a list")
    names = [n for n, _ in out]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        errors.append(f"duplicate {kind} IDs: {dup[:10]}")
    return out


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def load_case(path):
    """Load and check a case. Returns (case, errors, warnings); case is None when unrecognized."""
    errors, warnings = [], []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None, ["top level is not a JSON object"], warnings
    missing = [k for k in TOP_KEYS if k not in data]
    if missing:
        return None, [f"missing top-level keys {missing}; found {sorted(data.keys())}"], warnings

    T = data["time_periods"]
    if not isinstance(T, int) or T <= 0:
        errors.append(f"time_periods must be a positive int, got {T!r}")
        return None, errors, warnings
    demand = [float(x) for x in data["demand"]]
    reserves = [float(x) for x in data["reserves"]]
    for label, arr in (("demand", demand), ("reserves", reserves)):
        if len(arr) != T:
            errors.append(f"{label} length {len(arr)} != time_periods {T}")
        if not all(math.isfinite(x) for x in arr):
            errors.append(f"{label} has non-finite values")
        if any(x < 0 for x in arr):
            errors.append(f"{label} has negative values")

    thermal = []
    for name, g in _as_named(data["thermal_generators"], "thermal_generators", errors):
        miss = [k for k in THERMAL_KEYS if k not in g]
        if miss:
            errors.append(f"thermal {name} missing {miss}")
            continue
        rec = {"name": name}
        for k in THERMAL_KEYS[:13]:
            if not _finite(g[k]):
                errors.append(f"thermal {name}.{k} not a finite number: {g[k]!r}")
            rec[k] = float(g[k]) if _finite(g[k]) else 0.0
        for k in ("must_run", "unit_on_t0", "time_up_minimum", "time_down_minimum", "time_up_t0", "time_down_t0"):
            rec[k] = int(round(rec[k]))
        pmin, pmax = rec["power_output_minimum"], rec["power_output_maximum"]
        if pmin < 0 or pmin > pmax:
            errors.append(f"thermal {name}: need 0 <= pmin ({pmin}) <= pmax ({pmax})")
        for k in ("ramp_up_limit", "ramp_down_limit", "ramp_startup_limit", "ramp_shutdown_limit"):
            if rec[k] < 0:
                errors.append(f"thermal {name}.{k} negative")
        if rec["ramp_startup_limit"] < pmin - TOL:
            warnings.append(f"thermal {name}: ramp_startup_limit < pmin; unit can never start")
        if rec["ramp_shutdown_limit"] < pmin - TOL:
            warnings.append(f"thermal {name}: ramp_shutdown_limit < pmin; unit can never shut down")
        # initial condition consistency
        on0, p0 = rec["unit_on_t0"], rec["power_output_t0"]
        if on0 not in (0, 1):
            errors.append(f"thermal {name}: unit_on_t0 must be 0/1")
        if on0 == 1 and not (pmin - TOL <= p0 <= pmax + TOL):
            errors.append(f"thermal {name}: on at t0 but power_output_t0 {p0} outside [{pmin},{pmax}]")
        if on0 == 0 and abs(p0) > TOL:
            errors.append(f"thermal {name}: off at t0 but power_output_t0 = {p0}")
        if on0 == 1 and rec["time_up_t0"] <= 0:
            warnings.append(f"thermal {name}: on at t0 but time_up_t0 = {rec['time_up_t0']}")
        if on0 == 0 and rec["time_down_t0"] <= 0:
            warnings.append(f"thermal {name}: off at t0 but time_down_t0 = {rec['time_down_t0']}")
        if rec["must_run"] and on0 == 0 and rec["time_down_t0"] < rec["time_down_minimum"]:
            errors.append(f"thermal {name}: must-run but initial min-down obligation keeps it off")
        # startup tiers: parse without assuming order
        tiers = []
        for s in g["startup"]:
            if not (_finite(s.get("lag")) and _finite(s.get("cost"))):
                errors.append(f"thermal {name}: bad startup tier {s}")
                continue
            tiers.append((int(round(s["lag"])), float(s["cost"])))
        if not tiers:
            errors.append(f"thermal {name}: no startup tiers")
        if tiers != sorted(tiers):
            warnings.append(f"thermal {name}: startup tiers not sorted by lag; sorted")
        tiers.sort()
        lags = [l for l, _ in tiers]
        if len(set(lags)) != len(lags):
            errors.append(f"thermal {name}: repeated startup lags {lags}")
        if any(b[1] < a[1] - 1e-9 for a, b in zip(tiers, tiers[1:])):
            warnings.append(f"thermal {name}: startup cost decreases with lag (unusual)")
        rec["startup"] = tiers
        # production curve: total cost ($/period) at output breakpoints (MW)
        pts = []
        for p in g["piecewise_production"]:
            if not (_finite(p.get("mw")) and _finite(p.get("cost"))):
                errors.append(f"thermal {name}: bad cost point {p}")
                continue
            pts.append((float(p["mw"]), float(p["cost"])))
        pts.sort()
        if len(pts) < 2 and pmax - pmin > TOL:
            errors.append(f"thermal {name}: production curve needs >= 2 points")
        if any(abs(b[0] - a[0]) < 1e-9 for a, b in zip(pts, pts[1:])):
            errors.append(f"thermal {name}: repeated cost-curve MW points")
        if pts and abs(pts[0][0] - pmin) > TOL:
            errors.append(f"thermal {name}: first cost point {pts[0][0]} MW != pmin {pmin}")
        if pts and abs(pts[-1][0] - pmax) > TOL:
            errors.append(f"thermal {name}: last cost point {pts[-1][0]} MW != pmax {pmax}")
        slopes = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(pts, pts[1:]) if b[0] - a[0] > 1e-9]
        rec["convex"] = all(s2 >= s1 - 1e-7 for s1, s2 in zip(slopes, slopes[1:]))
        if not rec["convex"]:
            warnings.append(f"thermal {name}: non-convex cost curve; segment model needs ordering binaries")
        rec["curve"] = pts
        thermal.append(rec)

    renewable = []
    if "renewable_generators" in data:
        for name, r in _as_named(data["renewable_generators"], "renewable_generators", errors):
            lo = r.get("power_output_minimum")
            hi = r.get("power_output_maximum")
            if not (isinstance(lo, list) and isinstance(hi, list)):
                errors.append(f"renewable {name}: min/max must be per-period lists")
                continue
            if len(lo) != T or len(hi) != T:
                errors.append(f"renewable {name}: series length != {T}")
                continue
            lo = [float(x) for x in lo]
            hi = [float(x) for x in hi]
            if not all(math.isfinite(x) for x in lo + hi):
                errors.append(f"renewable {name}: non-finite values")
            if any(a > b + TOL for a, b in zip(lo, hi)):
                errors.append(f"renewable {name}: min > max in some period")
            renewable.append({"name": name, "min": lo, "max": hi})

    extra = sorted(set(data.keys()) - set(TOP_KEYS) - {"renewable_generators"})
    if extra:
        warnings.append(f"unmodeled top-level keys present (check the task needs them): {extra}")
    case = {"T": T, "demand": demand, "reserves": reserves, "thermal": thermal, "renewable": renewable}
    return case, errors, warnings


def curve_cost(pts, mw):
    """Total cost at actual output by linear interpolation of total-cost breakpoints."""
    if mw <= pts[0][0]:
        return pts[0][1]
    if mw >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= mw <= x1:
            return y0 + (mw - x0) * (y1 - y0) / (x1 - x0)
    raise ValueError("output outside curve")


def startup_tier_index(tiers, offline_duration):
    """Largest lag not exceeding prior offline duration; hottest tier if none qualifies."""
    chosen = 0
    for i, (lag, _) in enumerate(tiers):
        if lag <= offline_duration:
            chosen = i
        else:
            break
    return chosen


def offline_durations_at_starts(g, u):
    """For each period, the number of periods offline before it (only meaningful at starts)."""
    T = len(u)
    out = [0] * T
    off = 0 if g["unit_on_t0"] else g["time_down_t0"]
    prev = g["unit_on_t0"]
    for t in range(T):
        out[t] = off
        if u[t] == 1:
            off = 0
        else:
            off = off + 1 if prev == 0 else 1
        prev = u[t]
    return out
