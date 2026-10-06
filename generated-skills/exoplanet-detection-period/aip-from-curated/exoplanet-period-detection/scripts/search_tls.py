#!/usr/bin/env python3
"""Preprocess the light curve and run Transit Least Squares.

Reads one JSON object on stdin and writes one JSON object on stdout.

TLS output written to the state under `detection`:
  period, period_uncertainty, T0, depth, duration, SDE, SNR,
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

    from transitleastsquares import transitleastsquares

    model = transitleastsquares(time, flux, flux_err)
    result = model.power(
        period_min=period_min,
        period_max=period_max,
        show_progress_bar=False,
        use_threads=1,
        verbose=False,
    )

    depth_odd = float(getattr(result, "depth_mean_odd", (np.nan,))[0]) if hasattr(result, "depth_mean_odd") else float("nan")
    depth_even = float(getattr(result, "depth_mean_even", (np.nan,))[0]) if hasattr(result, "depth_mean_even") else float("nan")
    depth_odd_err = float(getattr(result, "depth_mean_odd", (np.nan, np.nan))[1]) if hasattr(result, "depth_mean_odd") else float("nan")
    depth_even_err = float(getattr(result, "depth_mean_even", (np.nan, np.nan))[1]) if hasattr(result, "depth_mean_even") else float("nan")
    if np.isfinite(depth_odd) and np.isfinite(depth_even):
        denom = np.sqrt(max(depth_odd_err, 0) ** 2 + max(depth_even_err, 0) ** 2)
        mismatch_sigma = abs(depth_odd - depth_even) / denom if denom > 0 else float("nan")
    else:
        mismatch_sigma = float("nan")

    detection = {
        "method": "tls",
        "period": float(result.period),
        "period_uncertainty": float(getattr(result, "period_uncertainty", float("nan"))),
        "T0": float(result.T0),
        "depth": float(getattr(result, "depth", float("nan"))),
        "duration": float(getattr(result, "duration", float("nan"))),
        "SDE": float(getattr(result, "SDE", float("nan"))),
        "SNR": float(getattr(result, "snr", float("nan"))),
        "transit_count": int(getattr(result, "transit_count", 0) or 0),
        "distinct_transit_count": int(getattr(result, "distinct_transit_count", 0) or 0),
        "empty_transit_count": int(getattr(result, "empty_transit_count", 0) or 0),
        "odd_even_mismatch_sigma": float(mismatch_sigma) if np.isfinite(mismatch_sigma) else None,
    }
    out = {"method": "tls", "detection": detection}
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
