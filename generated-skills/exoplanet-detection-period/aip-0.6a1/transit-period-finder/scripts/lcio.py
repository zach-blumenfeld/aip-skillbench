"""Shared helpers for the transit-period-finder scripts.

Every entry script reads one JSON object on stdin ({"state", "assets", "expects"}) and
prints one JSON object holding exactly its declared outputs. Library chatter (lightkurve
import warnings, numba notices) is pushed to stderr so stdout stays a single JSON object.
"""
import contextlib
import json
import math
import os
import re
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")

FLAG_CONVENTIONS = ("zero_is_good", "nonzero_is_good", "ignore_flags")


def read_payload():
    raw = sys.stdin.read()
    if not raw.strip():
        fail("expected one JSON object on stdin: {\"state\": {...}}")
    payload = json.loads(raw)
    return payload.get("state", payload)


def emit(obj):
    sys.stdout.write(json.dumps(clean_json(obj)) + "\n")
    sys.stdout.flush()


def fail(msg):
    sys.stderr.write("ERROR: " + msg + "\n")
    sys.exit(1)


def clean_json(x):
    """Make numpy / astropy values JSON-safe (NaN and inf become null)."""
    if isinstance(x, dict):
        return {str(k): clean_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean_json(v) for v in x]
    if hasattr(x, "unit") and hasattr(x, "value"):
        x = x.value
    if isinstance(x, np.ndarray):
        return [clean_json(v) for v in x.tolist()]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return None if not math.isfinite(x) else x
    return x


@contextlib.contextmanager
def quiet():
    """Send anything a library prints to stdout over to stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


# --------------------------------------------------------------------------- loading

_SPLIT = re.compile(r"[,\s;]+")


def load_table(path):
    """Read a whitespace/comma separated numeric table, skipping comments and headers.

    Returns (rows ndarray, header_lines list[str]).
    """
    if not os.path.isfile(path):
        fail(f"light curve file not found: {path}")
    rows, header = [], []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            if s[0] in "#%!/":
                header.append(s)
                continue
            parts = [p for p in _SPLIT.split(s) if p]
            try:
                vals = [float(p) for p in parts]
            except ValueError:
                header.append(s)
                continue
            rows.append(vals)
    if not rows:
        fail(f"no numeric rows in {path}")
    width = max(set(len(r) for r in rows), key=[len(r) for r in rows].count)
    data = np.array([r for r in rows if len(r) == width], dtype=float)
    return data, header


def interpret_columns(data):
    """Map table columns to time, flux, flag, flux_err.

    The task format is: time, normalized flux, quality flag, flux uncertainty.
    3-column files are time, flux, and either a flag (all integers) or an error.
    """
    ncol = data.shape[1]
    t = data[:, 0]
    f = data[:, 1] if ncol > 1 else None
    if f is None:
        fail("need at least two columns (time, flux)")
    flag = err = None
    if ncol >= 4:
        flag, err = data[:, 2], data[:, 3]
        names = ["time", "flux", "flag", "flux_err"] + [f"extra{i}" for i in range(ncol - 4)]
    elif ncol == 3:
        c = data[:, 2]
        finite = c[np.isfinite(c)]
        if finite.size and np.all(finite == np.round(finite)):
            flag = c
            names = ["time", "flux", "flag"]
        else:
            err = c
            names = ["time", "flux", "flux_err"]
    else:
        names = ["time", "flux"]
    return t, f, flag, err, names


def robust_p2p(flux):
    """Point-to-point scatter (robust white-noise estimate unaffected by slow variability)."""
    d = np.diff(flux[np.isfinite(flux)])
    if d.size < 3:
        return float("nan")
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / math.sqrt(2.0))


def quality_mask(flag, convention):
    if flag is None or convention == "ignore_flags":
        return None
    if convention == "zero_is_good":
        return flag == 0
    if convention == "nonzero_is_good":
        return flag != 0
    fail(f"unknown flag_convention {convention!r}; expected one of {FLAG_CONVENTIONS}")


def load_clean(path, convention):
    """Load, apply the quality convention, drop non-finite rows, normalise flux to median 1.

    Returns dict with time, flux, flux_err arrays and bookkeeping counts.
    """
    data, _ = load_table(path)
    t, f, flag, err, names = interpret_columns(data)
    n0 = len(t)
    keep = np.ones(n0, bool)
    qm = quality_mask(flag, convention)
    n_flag_removed = 0
    if qm is not None:
        n_flag_removed = int(np.sum(~qm))
        keep &= qm
    finite = np.isfinite(t) & np.isfinite(f)
    if err is not None:
        finite &= np.isfinite(err) & (err > 0)
    n_nonfinite = int(np.sum(keep & ~finite))
    keep &= finite
    if keep.sum() < 100:
        fail(f"only {int(keep.sum())} usable points after quality filtering "
             f"with convention {convention!r}; check the flag convention")
    t, f = t[keep], f[keep]
    order = np.argsort(t)
    t, f = t[order], f[order]
    med = np.median(f)
    f = f / med
    if err is not None:
        e = err[keep][order] / med
        err_source = "file"
    else:
        e = np.full_like(f, robust_p2p(f))
        err_source = "estimated_point_to_point"
    return {
        "time": t, "flux": f, "flux_err": e, "columns": names,
        "n_rows": n0, "n_flag_removed": n_flag_removed, "n_nonfinite_removed": n_nonfinite,
        "flux_median_divided": float(med), "flux_err_source": err_source,
    }


# --------------------------------------------------------------------------- detrending

def cadence_days(t):
    return float(np.median(np.diff(t)))


def window_cadences(window_days, cad):
    w = int(round(window_days / cad))
    w = max(w, 5)
    return w if w % 2 == 1 else w + 1


def flatten(t, f, e, window_days, mask=None):
    """Savitzky-Golay flatten via lightkurve (splits at gaps), then clip upward outliers.

    Only *upward* points are clipped (flares, cosmic rays): transits are downward and a
    lower clip at 3-5 sigma would eat deep transits. Returns (t, f, e, n_clipped).
    """
    with quiet():
        import lightkurve as lk
    lc = lk.LightCurve(time=t, flux=f, flux_err=e)
    w = window_cadences(window_days, cadence_days(t))
    with quiet():
        flat = lc.flatten(window_length=w, polyorder=2, break_tolerance=10,
                          niters=3, sigma=3, mask=mask)
        flat, out = flat.remove_outliers(sigma_upper=3, sigma_lower=float("inf"),
                                         return_mask=True)
    ft = np.asarray(flat.time.value, float)
    ff = np.asarray(flat.flux.value, float)
    fe = np.asarray(flat.flux_err.value, float)
    ok = np.isfinite(ff) & np.isfinite(fe)
    return ft[ok], ff[ok], fe[ok], int(np.sum(out))


def choose_window_days(rotation_period, rotation_significant):
    """Flatten window: short enough to follow the rotation signal *and its first harmonic*
    (P_rot/2), long enough to keep transits.

    A quarter of the rotation period follows both; the 0.25-day floor keeps the window
    >= ~3x a 2-hour transit; 0.75 day is the ceiling (longer windows let the P_rot/2 harmonic
    leak through as long, shallow "transits").
    """
    if rotation_significant and rotation_period and rotation_period > 0:
        return float(np.clip(rotation_period / 4.0, 0.25, 0.75))
    return 0.75


def duration_grid(window_days, cad):
    """Trial transit durations: 0.03 d (43 min) up to a third of the flatten window, max 0.25 d."""
    lo = max(0.03, 3 * cad)
    hi = min(0.25, window_days / 3.0)
    if hi <= lo:
        hi = lo * 1.5
    return np.geomspace(lo, hi, 6)


def bin_lc(t, f, e, bin_days):
    """Inverse-variance bin onto a regular grid (drops empty bins). Speeds BLS ~5x on 2-min data."""
    k = np.floor((t - t[0]) / bin_days).astype(int)
    _, inv, cnt = np.unique(k, return_inverse=True, return_counts=True)
    w = 1.0 / e ** 2
    sw = np.bincount(inv, w)
    return np.bincount(inv, t) / cnt, np.bincount(inv, f * w) / sw, 1.0 / np.sqrt(sw)
