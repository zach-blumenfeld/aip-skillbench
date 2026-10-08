"""Shared helpers for the exoplanet-transit-period scripts.

Protocol (aip execution step): one JSON object on stdin
{"currentState", "assets", "expects"}; one JSON object on stdout.
Libraries used are the ones the task container ships: numpy, scipy, astropy,
lightkurve, transitleastsquares, matplotlib.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import warnings

import numpy as np

warnings.filterwarnings("ignore")


def read_request():
    req = json.load(sys.stdin)
    state = req.get("currentState") or {}
    assets = req.get("assets") or {}
    raw = assets.get("config")
    if isinstance(raw, str):
        cfg = json.loads(raw)
    elif isinstance(raw, dict):
        cfg = raw
    else:  # run by hand without assets: read the file next to this script
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "config.json")) as fh:
            cfg = json.load(fh)
    return state, cfg


def _jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, np.ndarray):
        return [_jsonable(x) for x in o.tolist()]
    if isinstance(o, float):
        return o if np.isfinite(o) else None
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(x) for x in o]
    return o


def emit(obj):
    sys.stdout.write(json.dumps(_jsonable(obj)))
    sys.stdout.write("\n")
    sys.stdout.flush()


def fail(msg, **extra):
    emit({"error": msg, **extra})
    sys.exit(1)


def opt(state, key, default):
    """Optional override carried in the state (extra keys pass through)."""
    v = state.get(key)
    return default if v is None or v == "" else v


@contextlib.contextmanager
def quiet():
    """TLS and lightkurve print to stdout; keep stdout pure JSON and keep the text."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield buf


def work_dir(lc_path, tag=None):
    base = os.environ.get("EXO_WORKDIR") or os.path.join(tempfile.gettempdir(), "exoplanet-transit-period")
    key = hashlib.sha1(os.path.abspath(lc_path).encode()).hexdigest()[:10]
    d = os.path.join(base, f"{os.path.splitext(os.path.basename(lc_path))[0]}-{key}")
    if tag:  # separate folder per by-hand variant so runs do not overwrite each other
        d = os.path.join(d, str(tag))
    os.makedirs(d, exist_ok=True)
    return d


ROLE_PATTERNS = [
    ("flux_err", re.compile(r"err|sigma|uncert", re.I)),
    ("flag", re.compile(r"flag|quality|qual", re.I)),
    ("time", re.compile(r"time|mjd|bjd|jd|btjd", re.I)),
    ("flux", re.compile(r"flux|mag|brightness|sap|pdc", re.I)),
]


def _role(label):
    for role, pat in ROLE_PATTERNS:
        if pat.search(label):
            return role
    return None


def load_lightcurve(path):
    """Load a whitespace/comma text light curve.

    Column roles come from '# columnN: name' comment lines or a text header row when
    present, else by position: 4 cols = time, flux, flag, flux_err (the TESS export
    format); 3 cols = time, flux, flux_err; 2 cols = time, flux.
    """
    if not os.path.exists(path):
        fail(f"light curve not found: {path}")
    comments, header_row, rows = [], None, []
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#") or s.startswith("%"):
                comments.append(s.lstrip("#% ").strip())
                continue
            parts = re.split(r"[,\s;]+", s)
            try:
                rows.append([float(p) for p in parts if p != ""])
            except ValueError:
                if not rows and header_row is None:
                    header_row = [p for p in parts if p]
                continue
    if not rows:
        fail(f"no numeric rows in {path}")
    ncol = min(len(r) for r in rows)
    data = np.array([r[:ncol] for r in rows], dtype=float)

    roles = {}
    numbered = {}
    for c in comments:
        m = re.match(r"col(?:umn)?\s*(\d+)\s*[:=]\s*(.+)", c, re.I)
        if m:
            numbered[int(m.group(1)) - 1] = m.group(2)
    labels = numbered if numbered else ({i: h for i, h in enumerate(header_row)} if header_row else {})
    for i, lab in labels.items():
        r = _role(lab)
        if r and r not in roles and i < ncol:
            roles[r] = i
    source = "header" if ("time" in roles and "flux" in roles) else "position"
    if source == "position":
        roles = {"time": 0, "flux": 1}
        if ncol >= 4:
            roles.update(flag=2, flux_err=3)
        elif ncol == 3:
            roles.update(flux_err=2)
    out = {
        "time": data[:, roles["time"]],
        "flux": data[:, roles["flux"]],
        "flag": data[:, roles["flag"]] if "flag" in roles else None,
        "flux_err": data[:, roles["flux_err"]] if "flux_err" in roles else None,
    }
    info = {"n_columns": ncol, "column_roles": roles, "role_source": source,
            "header_comments": comments[:10]}
    return out, info


def ptp_sigma(flux):
    """White-noise per-point scatter from point-to-point differences (robust)."""
    d = np.diff(flux)
    d = d[np.isfinite(d)]
    if d.size < 3:
        return float(np.nanstd(flux))
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2))


def red_noise_beta(time, flux, flux_err, timescale, exclude=None):
    """Time-averaging beta (Pont et al. 2006 style): ratio of the scatter of flux
    binned on `timescale` to the white-noise expectation; >= 1. Used to inflate
    depth errors so odd-even and phase-0.5 significances are not overstated."""
    m = np.ones(time.size, bool) if exclude is None else ~exclude
    t, f, e = time[m], flux[m], flux_err[m]
    if t.size < 50 or timescale <= 0:
        return 1.0
    idx = np.floor((t - t[0]) / timescale).astype(int)
    counts = np.bincount(idx)
    sums = np.bincount(idx, weights=f)
    good = counts >= max(3, 0.5 * np.median(counts[counts > 0]))
    if good.sum() < 10:
        return 1.0
    means = sums[good] / counts[good]
    expected = np.median(e) / np.sqrt(np.median(counts[good]))
    return float(max(1.0, np.std(means) / expected))


def save_lc(path, time, flux, flux_err):
    np.savez(path, time=time, flux=flux, flux_err=flux_err)


def load_lc(path):
    if not os.path.exists(path):
        fail(f"cleaned light curve not found: {path} (re-run prepare-light-curve)")
    z = np.load(path)
    return z["time"], z["flux"], z["flux_err"]


def plot_safe(fn, *a, **k):
    try:
        import matplotlib
        matplotlib.use("Agg")
        return fn(*a, **k)
    except Exception as e:  # plots are diagnostics, never fatal
        return f"plot failed: {e}"
