#!/usr/bin/env python3
"""Narrow period search around a candidate to tighten precision.

Dispatches by `method`:
  - tls: re-run TLS with period_min/period_max = period * [0.95, 1.05]
         (if the broad run gave a period_uncertainty, use that to pick
         a tighter window).
  - bls: re-run BoxLeastSquares on a dense custom period grid around
         the candidate (±2 %), reporting the refined period and depth.
  - ls:  re-run LombScargle on a dense frequency grid around the
         candidate (±2 %) and pick the peak.

Writes `detection_refined` into the state. The original `detection`
is preserved.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _preprocess import preprocess  # noqa: E402


def _refine_tls(time, flux, flux_err, candidate, pmin, pmax):
    from transitleastsquares import transitleastsquares

    model = transitleastsquares(time, flux, flux_err)
    result = model.power(
        period_min=pmin,
        period_max=pmax,
        oversampling_factor=5,
        show_progress_bar=False,
        use_threads=1,
        verbose=False,
    )
    return {
        "method": "tls",
        "period": float(result.period),
        "period_uncertainty": float(getattr(result, "period_uncertainty", float("nan"))),
        "T0": float(result.T0),
        "depth": float(getattr(result, "depth", float("nan"))),
        "duration": float(getattr(result, "duration", float("nan"))),
        "SDE": float(getattr(result, "SDE", float("nan"))),
        "SNR": float(getattr(result, "snr", float("nan"))),
        "transit_count": int(getattr(result, "transit_count", 0) or 0),
        "search_window_days": [float(pmin), float(pmax)],
    }


def _refine_bls(time, flux, flux_err, candidate, pmin, pmax):
    import astropy.units as u
    from astropy.timeseries import BoxLeastSquares

    model = BoxLeastSquares(time * u.day, flux, dy=flux_err)
    periods = np.linspace(pmin, pmax, 4000) * u.day
    duration = float(candidate.get("duration", 0.1))
    if not np.isfinite(duration) or duration <= 0:
        duration = 0.1
    pg = model.power(periods, [duration] * u.day)
    power = np.asarray(pg.power)
    idx = int(np.argmax(power))
    best_period = float(pg.period[idx].to_value(u.day))
    stats = model.compute_stats(
        pg.period[idx], pg.duration[idx], pg.transit_time[idx]
    )
    depth = float(stats["depth"][0])
    depth_err = float(stats["depth"][1])
    return {
        "method": "bls",
        "period": best_period,
        "period_uncertainty": float(np.std(pg.period.to_value(u.day))),
        "T0": float(pg.transit_time[idx].to_value(u.day)),
        "depth": depth,
        "duration": float(pg.duration[idx].to_value(u.day)),
        "SNR": float(depth / depth_err) if depth_err > 0 else float("nan"),
        "search_window_days": [float(pmin), float(pmax)],
    }


def _refine_ls(time, flux, flux_err, candidate, pmin, pmax):
    from astropy.timeseries import LombScargle

    ls = LombScargle(time, flux, flux_err)
    frequency = np.linspace(1.0 / pmax, 1.0 / pmin, 20000)
    power = ls.power(frequency)
    idx = int(np.argmax(power))
    best_period = 1.0 / float(frequency[idx])
    return {
        "method": "ls",
        "period": best_period,
        "power": float(power[idx]),
        "search_window_days": [float(pmin), float(pmax)],
    }


def main() -> int:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    method = state["method"]
    detection = state["detection"]
    lc = state["lightcurve"]

    candidate_period = float(detection["period"])
    unc = detection.get("period_uncertainty")
    if unc and np.isfinite(unc) and unc > 0:
        half_window = max(5 * unc, 0.01 * candidate_period)
    else:
        half_window = 0.05 * candidate_period
    pmin = max(0.1, candidate_period - half_window)
    pmax = candidate_period + half_window

    time, flux, flux_err = preprocess(
        np.asarray(lc["time"]),
        np.asarray(lc["flux"]),
        np.asarray(lc["flux_err"]),
    )

    if method == "tls":
        refined = _refine_tls(time, flux, flux_err, detection, pmin, pmax)
    elif method == "bls":
        refined = _refine_bls(time, flux, flux_err, detection, pmin, pmax)
    elif method == "ls":
        refined = _refine_ls(time, flux, flux_err, detection, pmin, pmax)
    else:
        raise ValueError(f"Unknown method: {method!r}")

    json.dump({"detection_refined": refined}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
