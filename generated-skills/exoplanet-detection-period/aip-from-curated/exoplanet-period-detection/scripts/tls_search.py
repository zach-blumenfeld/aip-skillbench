"""Broad Transit Least Squares (TLS) search for a transiting-exoplanet period.

TLS is the primary method per `source/transit-least-squares` and
`source/exoplanet-workflows`: more sensitive than Lomb-Scargle for
transit-shaped signals, and fits actual transit models (odd/even, limb
darkening). flux_err is mandatory for proper weighting.

Default search window: period_min = max(0.5, 3*cadence_days), period_max =
min(baseline/2, 50 days). The baseline/2 cap guarantees at least two
transits land in the data; 50 days caps runtime for typical TESS sectors.
Callers may override via `period_min` / `period_max` in the input state.
"""
import json
import sys
import warnings

import numpy as np


def main():
    state = json.load(sys.stdin).get("currentState", {})
    cache = state["flattened_cache"]

    arrays = np.load(cache)
    time = np.asarray(arrays["time"], dtype=np.float64)
    flux = np.asarray(arrays["flux"], dtype=np.float64)
    flux_err = np.asarray(arrays["flux_err"], dtype=np.float64)

    baseline = float(time[-1] - time[0])
    cadence_days = float(np.median(np.diff(time))) if time.size > 1 else 2.0 / (24 * 60)

    # Need >=2 transits for a credible detection, so cap at baseline/2.
    default_pmax = max(1.0, min(50.0, baseline / 2.0))
    default_pmin = max(0.5, 3.0 * cadence_days)
    period_min = float(state.get("period_min", default_pmin))
    period_max = float(state.get("period_max", default_pmax))
    if period_max <= period_min:
        period_max = period_min * 2.0

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from transitleastsquares import transitleastsquares

        model = transitleastsquares(time, flux, flux_err)
        result = model.power(
            period_min=period_min,
            period_max=period_max,
            show_progress_bar=False,
            verbose=False,
        )

    out = {
        "period": float(result.period),
        "period_uncertainty": float(getattr(result, "period_uncertainty", 0.0) or 0.0),
        "sde": float(result.SDE),
        "snr": float(result.snr),
        "t0": float(result.T0),
        "depth": float(result.depth),
        "duration": float(result.duration),
        "transit_count": int(getattr(result, "transit_count", 0) or 0),
        "search_period_min": period_min,
        "search_period_max": period_max,
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
