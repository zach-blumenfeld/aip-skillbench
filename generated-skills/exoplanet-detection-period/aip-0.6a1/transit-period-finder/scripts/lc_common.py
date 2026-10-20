"""Shared helpers for the transit-period-finder scripts.

Every step script reads one JSON object from stdin ({"state", "assets", "expects"})
and prints one JSON object holding exactly its declared outputs.
"""
import json
import os
import re
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")


def read_state():
    payload = json.load(sys.stdin)
    return payload.get("state", {})


def emit(outputs):
    json.dump(outputs, sys.stdout, default=_jsonable)
    sys.stdout.write("\n")


def fail(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(1)


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(f"not JSON serializable: {type(o)}")


# ---------------------------------------------------------------- loading

_ROLE_PATTERNS = [
    ("flux_err", re.compile(r"(err|uncert|sigma)", re.I)),
    ("flag", re.compile(r"(flag|quality|qual)", re.I)),
    ("time", re.compile(r"(time|mjd|bjd|btjd|jd)", re.I)),
    ("flux", re.compile(r"(flux|mag|bright)", re.I)),
]


def _header_roles(header_lines, ncol):
    """Map column index -> role from '# columnN: name' or a '# a b c d' header."""
    roles = {}
    for line in header_lines:
        m = re.match(r"#\s*col(?:umn)?\s*(\d+)\s*[:=]\s*(.+)", line, re.I)
        if m:
            idx = int(m.group(1)) - 1
            for role, pat in _ROLE_PATTERNS:
                if pat.search(m.group(2)) and role not in roles.values():
                    roles[idx] = role
                    break
    if len(roles) < 2:
        for line in header_lines:
            toks = re.split(r"[,\s]+", line.lstrip("#").strip())
            if len(toks) == ncol:
                cand = {}
                for i, tok in enumerate(toks):
                    for role, pat in _ROLE_PATTERNS:
                        if pat.search(tok) and role not in cand.values():
                            cand[i] = role
                            break
                if len(cand) >= 2:
                    roles = cand
                    break
    return roles


def load_lightcurve(path):
    """Return dict(time, flux, flag|None, flux_err|None, column_map)."""
    if not os.path.isfile(path):
        fail(f"light curve file not found: {path}")
    header = []
    first_data = None
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#") or not re.match(r"^[-+0-9.]", s):
                header.append(s if s.startswith("#") else "#" + s)
                continue
            first_data = s
            break
    if first_data is None:
        fail(f"no numeric rows in {path}")
    delim = "," if "," in first_data else None
    data = np.genfromtxt(path, comments="#", delimiter=delim, invalid_raise=False)
    if data.ndim == 1:
        data = data[None, :]
    # drop any non-numeric header rows genfromtxt turned into NaN rows
    data = data[~np.all(np.isnan(data), axis=1)]
    ncol = data.shape[1]
    roles = _header_roles(header, ncol)
    if len(set(roles.values())) < 2:
        # default order from the task statement: time, flux, quality flag, flux error
        default = ["time", "flux", "flag", "flux_err"] if ncol >= 4 else ["time", "flux", "flux_err"]
        roles = {i: r for i, r in enumerate(default[:ncol])}
    inv = {r: i for i, r in roles.items()}
    if "time" not in inv or "flux" not in inv:
        fail(f"could not identify time/flux columns in {path}; header={header}")
    out = {
        "time": data[:, inv["time"]],
        "flux": data[:, inv["flux"]],
        "flag": data[:, inv["flag"]] if "flag" in inv else None,
        "flux_err": data[:, inv["flux_err"]] if "flux_err" in inv else None,
        "column_map": {r: int(i) + 1 for r, i in inv.items()},
    }
    return out


# ---------------------------------------------------------------- numerics

def mad_std(x):
    x = np.asarray(x)
    return 1.4826 * np.nanmedian(np.abs(x - np.nanmedian(x)))


def running_median(y, window_cadences_n):
    """Running median over a window given in cadences (y must be time-sorted)."""
    from scipy.ndimage import median_filter
    return median_filter(y, size=max(int(window_cadences_n), 3), mode="nearest")


def window_cadences(window_days, cadence_days):
    wl = int(round(window_days / cadence_days))
    if wl % 2 == 0:
        wl += 1
    return max(wl, 5)


def flatten(time, flux, flux_err, window_days, cadence_days, mask=None):
    """Savitzky-Golay flatten via lightkurve (preserves short dips); mask=True points
    (e.g. in-transit) are excluded from the trend fit."""
    import lightkurve as lk
    lc = lk.LightCurve(time=time, flux=flux, flux_err=flux_err)
    wl = window_cadences(window_days, cadence_days)
    wl = min(wl, len(time) - (1 - len(time) % 2))
    kw = {"window_length": wl}
    if mask is not None:
        kw["mask"] = mask
    flat = lc.flatten(**kw)
    return (np.asarray(flat.time.value, float), np.asarray(flat.flux.value, float),
            np.asarray(flat.flux_err.value, float))


def clip_upper(time, flux, flux_err, sigma):
    """Remove positive outliers only; transits are dips and must survive."""
    resid = flux - np.nanmedian(flux)
    keep = resid < sigma * mad_std(flux)
    return time[keep], flux[keep], flux_err[keep], int((~keep).sum())


def save_arrays(path, **arrays):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    np.savez(path, **arrays)
    return os.path.abspath(path)


def load_arrays(path):
    if not os.path.isfile(path):
        fail(f"intermediate file missing: {path}")
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def write_period(path, period):
    text = f"{float(period):.5f}"
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text + "\n")
    return text


# ---------------------------------------------------------------- ephemeris fit

def trapezoid(params, t):
    """Periodic trapezoid transit: params = (P, t0, depth, total_duration, ingress_frac)."""
    P, t0, depth, dur, fi = params
    a = np.abs((t - t0 + 0.5 * P) % P - 0.5 * P)
    ti = max(dur * fi, 1e-6)
    m = np.ones_like(t)
    m[a <= dur / 2 - ti] -= depth
    ing = (a > dur / 2 - ti) & (a < dur / 2)
    m[ing] -= depth * (dur / 2 - a[ing]) / ti
    return m


def fit_ephemeris(t, f, e, period, t0, duration, depth, period_halfwidth):
    """Least-squares trapezoid fit of period and mid-transit time.

    A grid over (P, t0) inside +/-period_halfwidth seeds the fit so the local optimizer
    cannot lock onto a neighbouring phase solution. t0 is referenced to the epoch nearest
    the middle of the data, which decorrelates it from P. Returns a dict or None.
    """
    from scipy.optimize import least_squares
    cadence = float(np.median(np.diff(t)))
    n_mid = np.round((np.median(t) - t0) / period)
    tc = t0 + n_mid * period
    n_ep = max(1.0, (t[-1] - t[0]) / period)
    sel = np.abs((t - tc + 0.5 * period) % period - 0.5 * period) < 2.5 * duration + period_halfwidth * n_ep
    if sel.sum() < 20:
        return None
    ts, fs, es = t[sel], f[sel], e[sel]

    def resid(p):
        return (fs - trapezoid(p, ts)) / es

    lo = [period - period_halfwidth, tc - duration, 0.0, 0.3 * duration, 0.01]
    hi = [period + period_halfwidth, tc + duration, 0.5, 3.0 * duration, 0.5]
    shape = least_squares(resid, [period, tc, max(depth, 1e-5), duration, 0.2],
                          bounds=(lo, hi), x_scale=[1e-3, 1e-3, 1e-4, 1e-3, 0.05],
                          diff_step=1e-6).x
    dP = max(cadence / 4.0 / n_ep, 1e-6)
    Ps = np.arange(period - period_halfwidth, period + period_halfwidth + dP, dP)
    T0s = np.arange(tc - duration / 2, tc + duration / 2 + cadence / 4, cadence / 4)
    dep_s, dur_s, fi_s = shape[2], shape[3], shape[4]
    ti = max(dur_s * fi_s, 1e-6)
    w = 1.0 / es ** 2
    best = (np.inf, period, tc)
    for P in Ps:   # vectorized over t0 for each trial period
        a = np.abs((ts[:, None] - T0s[None, :] + 0.5 * P) % P - 0.5 * P)
        drop = np.where(a <= dur_s / 2 - ti, dep_s,
                        np.where(a < dur_s / 2, dep_s * (dur_s / 2 - a) / ti, 0.0))
        c2 = np.sum(w[:, None] * (fs[:, None] - 1.0 + drop) ** 2, axis=0)
        j = int(np.argmin(c2))
        if c2[j] < best[0]:
            best = (float(c2[j]), float(P), float(T0s[j]))
    x0 = np.clip([best[1], best[2], shape[2], shape[3], shape[4]], lo, hi)
    r = least_squares(resid, x0, bounds=(lo, hi), x_scale=[1e-4, 1e-4, 1e-4, 1e-3, 0.05],
                      diff_step=1e-6)
    dof = max(len(fs) - 5, 1)
    chi2r = float(np.sum(r.fun ** 2) / dof)
    try:
        cov = np.linalg.inv(r.jac.T @ r.jac) * max(chi2r, 1.0)
        perr = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        perr = np.full(5, np.nan)
    if not np.isfinite(perr[0]):
        return None
    return {
        "period": float(r.x[0]),
        "period_err": float(perr[0]),
        "t0": float(r.x[1]),
        "depth": float(r.x[2]),
        "duration": float(r.x[3]),
        "chi2_reduced": chi2r,
        "at_bound": bool(np.any(np.isclose(r.x[:2], [lo[0], lo[1]])) or
                         np.any(np.isclose(r.x[:2], [hi[0], hi[1]]))),
    }
