"""Narrow-window TLS refit around a candidate period for better precision.

Follows the refinement strategy in `source/transit-least-squares`:
  * broad search finds a candidate (coarse grid, fast),
  * narrow search around +/-5% of the candidate (dense grid, precise).

Overwrites the broad-search period/sde/snr/t0/depth with the refined values
so downstream the state carries the best estimate. If the refined SDE is
not better than the broad one, the broad numbers are kept (refinement
should never make the detection weaker).
"""
import json
import sys
import warnings

import numpy as np


def main():
    state = json.load(sys.stdin).get("currentState", {})
    cache = state["flattened_cache"]
    candidate = float(state["period"])

    arrays = np.load(cache)
    time = np.asarray(arrays["time"], dtype=np.float64)
    flux = np.asarray(arrays["flux"], dtype=np.float64)
    flux_err = np.asarray(arrays["flux_err"], dtype=np.float64)

    period_min = max(1e-3, candidate * 0.95)
    period_max = candidate * 1.05

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from transitleastsquares import transitleastsquares

        model = transitleastsquares(time, flux, flux_err)
        result = model.power(
            period_min=period_min,
            period_max=period_max,
            oversampling_factor=3,
            show_progress_bar=False,
            verbose=False,
        )

    refined_sde = float(result.SDE)
    broad_sde = float(state.get("sde", 0.0))

    if refined_sde >= broad_sde:
        out = {
            "period": float(result.period),
            "period_uncertainty": float(getattr(result, "period_uncertainty", 0.0) or 0.0),
            "sde": refined_sde,
            "snr": float(result.snr),
            "t0": float(result.T0),
            "depth": float(result.depth),
            "duration": float(result.duration),
            "refinement_applied": True,
            "refine_window_min": period_min,
            "refine_window_max": period_max,
        }
    else:
        # Refinement regressed - keep broad values, record that we tried.
        out = {
            "refinement_applied": False,
            "refine_window_min": period_min,
            "refine_window_max": period_max,
        }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
