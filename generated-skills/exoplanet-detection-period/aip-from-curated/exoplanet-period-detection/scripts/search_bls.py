#!/usr/bin/env python3
"""Preprocess the light curve and run astropy BoxLeastSquares.

Writes a `detection` object analogous to search_tls.py:
  period, T0, depth, depth_snr (as SNR), duration, power (as "SDE"-like),
  transit_count, odd_even_mismatch_sigma.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _preprocess import preprocess  # noqa: E402


def main() -> int:
    payload = json.load(sys.stdin)
    state = payload.get("currentState", {})
    lc = state["lightcurve"]
    period_min = float(state["period_min"])
    period_max = float(state["period_max"])

    time, flux, flux_err = preprocess(
        np.asarray(lc["time"]),
        np.asarray(lc["flux"]),
        np.asarray(lc["flux_err"]),
    )

    import astropy.units as u
    from astropy.timeseries import BoxLeastSquares

    model = BoxLeastSquares(time * u.day, flux, dy=flux_err)
    durations = np.linspace(0.05, 0.3, 8) * u.day
    pg = model.autopower(
        durations,
        minimum_period=period_min * u.day,
        maximum_period=period_max * u.day,
        objective="likelihood",
    )
    power = np.asarray(pg.power)
    idx = int(np.argmax(power))
    best_period = float(pg.period[idx].to_value(u.day))
    best_duration = float(pg.duration[idx].to_value(u.day))
    best_t0 = float(pg.transit_time[idx].to_value(u.day))

    stats = model.compute_stats(
        pg.period[idx], pg.duration[idx], pg.transit_time[idx]
    )
    depth = float(stats["depth"][0])
    depth_err = float(stats["depth"][1])
    depth_odd = float(stats["depth_odd"][0])
    depth_odd_err = float(stats["depth_odd"][1])
    depth_even = float(stats["depth_even"][0])
    depth_even_err = float(stats["depth_even"][1])
    denom = np.sqrt(max(depth_odd_err, 0) ** 2 + max(depth_even_err, 0) ** 2)
    mismatch_sigma = abs(depth_odd - depth_even) / denom if denom > 0 else float("nan")

    # Pseudo-SDE: (peak power - mean) / std, same spirit as TLS SDE.
    med_p = float(np.median(power))
    std_p = float(np.std(power))
    sde_like = (power[idx] - med_p) / std_p if std_p > 0 else float("nan")

    detection = {
        "method": "bls",
        "period": best_period,
        "period_uncertainty": float(np.nan),
        "T0": best_t0,
        "depth": depth,
        "depth_err": depth_err,
        "duration": best_duration,
        "power": float(power[idx]),
        "SDE": float(sde_like),
        "SNR": float(depth / depth_err) if depth_err > 0 else float("nan"),
        "transit_count": int(stats["transit_times"].size),
        "odd_even_mismatch_sigma": float(mismatch_sigma) if np.isfinite(mismatch_sigma) else None,
    }
    out = {"method": "bls", "detection": detection}
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
