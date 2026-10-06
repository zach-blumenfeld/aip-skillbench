#!/usr/bin/env python
"""Run a broad-range Transit Least Squares search on the cleaned light curve.

TLS fits transit-shaped box dips and is more sensitive than Lomb-Scargle or BLS for
exoplanet transits. flux_err is always passed — TLS requires it for proper weighting.

Picks period_min = 0.5 d and period_max = min(15 d, baseline / 2) so every candidate
period gets at least two expected transits inside the observing baseline.

Classifies the candidate's `strength` from the Signal Detection Efficiency (SDE):
  SDE >= 9  -> very_strong
  SDE >= 6  -> strong
  SDE <  6  -> weak      (routed to end; the candidate period is still returned)
"""
import json
import sys
from pathlib import Path

import numpy as np


def _read_state():
    return json.load(sys.stdin)["currentState"]


def _classify(sde):
    if sde >= 9.0:
        return "very_strong"
    if sde >= 6.0:
        return "strong"
    return "weak"


def main():
    import transitleastsquares as tls

    state = _read_state()
    data = np.load(state["clean_data_path"])
    t = np.asarray(data["time"], dtype=float)
    y = np.asarray(data["flux"], dtype=float)
    e = np.asarray(data["flux_err"], dtype=float)

    baseline = float(t.max() - t.min())
    period_max = max(1.5, min(15.0, baseline / 2.0))
    period_min = 0.5

    model = tls.transitleastsquares(t, y, e)
    result = model.power(
        period_min=period_min,
        period_max=period_max,
        show_progress_bar=False,
        verbose=False,
    )

    candidate_period = float(result.period)
    period_unc = float(result.period_uncertainty)
    sde = float(result.SDE)
    snr = float(result.snr)
    strength = _classify(sde)

    out = {
        "candidate_period": candidate_period,
        "candidate_sde": sde,
        "candidate_snr": snr,
        "candidate_t0": float(result.T0),
        "candidate_duration": float(result.duration),
        # TLS returns `depth` as the minimum of the model light curve
        # (e.g. 0.99 for a 1% dip). Convert to a fractional dip so the
        # value lines up with the "0.01-0.03 = 1-3% dip" convention the
        # source skills use.
        "candidate_depth": float(1.0 - result.depth),
        "search_period_min": period_min,
        "search_period_max": period_max,
        "strength": strength,
        # Pre-populate the final period fields so the "weak" branch, which skips
        # refinement, still carries a complete answer to the end step.
        "period_days": candidate_period,
        "period_uncertainty_days": period_unc,
        "final_sde": sde,
        "final_snr": snr,
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
