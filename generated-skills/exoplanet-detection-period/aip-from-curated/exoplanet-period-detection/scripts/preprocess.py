#!/usr/bin/env python
"""Load a plain-text TESS light curve, quality-filter, outlier-clip, and flatten.

Reads a 4-column whitespace-delimited file (time MJD, flux relative, flag, flux_err)
with `#` comment lines. Keeps rows with flag == 0 (standard TESS convention — flag 0
is GOOD). Sigma-clips flux outliers at 5 sigma around the median, then detrends with
a Savitzky-Golay filter (window ~ 501 cadences) that preserves transit-depth dips.

Writes a .npz holding the cleaned arrays and emits the path plus summary stats.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter


def _read_state():
    payload = json.load(sys.stdin)
    return payload["currentState"]


def _load_light_curve(path):
    arr = np.loadtxt(path, comments="#")
    if arr.ndim != 2 or arr.shape[1] < 4:
        raise ValueError(
            f"Expected a 4-column file (time, flux, flag, flux_err); got shape {arr.shape}"
        )
    return arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]


def _filter_quality(time, flux, flag, flux_err):
    good = flag == 0
    return time[good], flux[good], flux_err[good]


def _sigma_clip(time, flux, flux_err, sigma=5.0):
    median = np.median(flux)
    std = np.std(flux)
    keep = np.abs(flux - median) < sigma * std
    return time[keep], flux[keep], flux_err[keep]


def _flatten(flux, window_length=501, polyorder=3):
    n = len(flux)
    if window_length >= n:
        window_length = max(5, (n // 2) * 2 - 1)
    if window_length % 2 == 0:
        window_length += 1
    trend = savgol_filter(flux, window_length=window_length, polyorder=polyorder)
    return flux / trend


def main():
    state = _read_state()
    src = Path(state["light_curve_path"]).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"light_curve_path does not exist: {src}")

    time, flux, flag, flux_err = _load_light_curve(src)
    n_raw = len(time)

    time, flux, flux_err = _filter_quality(time, flux, flag, flux_err)
    n_quality = len(time)

    time, flux, flux_err = _sigma_clip(time, flux, flux_err, sigma=5.0)
    n_clipped = len(time)

    # Choose a flattening window that is longer than any expected transit
    # (hours) but shorter than slow stellar/instrumental drift.
    flux = _flatten(flux, window_length=501, polyorder=3)

    out_dir = src.parent
    out_path = out_dir / f"{src.stem}.clean.npz"
    np.savez(out_path, time=time, flux=flux, flux_err=flux_err)

    result = {
        "clean_data_path": str(out_path),
        "n_raw": int(n_raw),
        "n_quality_good": int(n_quality),
        "n_after_clip": int(n_clipped),
        "baseline_days": float(time.max() - time.min()),
    }
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
