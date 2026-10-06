"""Load a TESS-style ASCII light curve, apply quality flags, and cache the arrays.

Input file format (per the TESS text export convention this skill was built for):
  # column1: time (mjd|bjd|btjd)
  # column2: flux (relative)
  # column3: flag  (0 = good; any other value = bad cadence)
  # column4: flux error
  <space-separated numeric rows>

Any line starting with `#` is treated as a comment. The four columns are
whitespace-separated. Rows with a non-zero quality flag, non-finite flux, or
non-positive flux error are dropped before anything downstream runs.
"""
import json
import os
import sys
import tempfile

import numpy as np


def _load_columns(path):
    data = np.loadtxt(path, comments="#", dtype=np.float64)
    if data.ndim != 2 or data.shape[1] < 4:
        raise ValueError(
            f"expected >=4 whitespace-separated columns (time, flux, flag, flux_err); "
            f"got shape {data.shape}"
        )
    time = data[:, 0]
    flux = data[:, 1]
    flag = data[:, 2]
    flux_err = data[:, 3]
    return time, flux, flag, flux_err


def main():
    state_in = json.load(sys.stdin)
    state = state_in.get("currentState", {})
    path = state["lightcurve_path"]

    if not os.path.isfile(path):
        raise FileNotFoundError(f"lightcurve_path does not exist: {path}")

    time, flux, flag, flux_err = _load_columns(path)
    n_raw = int(time.size)

    # TESS convention: flag == 0 means a good cadence. Flagged cadences are
    # dropped. Non-finite flux/flux_err and non-positive flux_err are also
    # dropped because downstream TLS requires finite, positive weights.
    good = (flag == 0) & np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err) & (flux_err > 0)
    time, flux, flux_err = time[good], flux[good], flux_err[good]
    n_good = int(time.size)
    if n_good < 100:
        raise ValueError(
            f"too few surviving cadences after quality cuts: {n_good} (need >=100)"
        )

    # Sort by time so downstream flattening / phase-folding behaves.
    order = np.argsort(time)
    time, flux, flux_err = time[order], flux[order], flux_err[order]

    time_span_days = float(time[-1] - time[0])
    # Cadence estimated from the median diff: robust to a few gaps.
    cadence_minutes = float(np.median(np.diff(time)) * 24.0 * 60.0)

    work_dir = tempfile.mkdtemp(prefix="exoplanet_period_")
    cleaned_cache = os.path.join(work_dir, "cleaned.npz")
    np.savez(cleaned_cache, time=time, flux=flux, flux_err=flux_err)

    out = {
        "cleaned_cache": cleaned_cache,
        "work_dir": work_dir,
        "n_raw": n_raw,
        "n_cadences": n_good,
        "time_span_days": time_span_days,
        "cadence_minutes": cadence_minutes,
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
