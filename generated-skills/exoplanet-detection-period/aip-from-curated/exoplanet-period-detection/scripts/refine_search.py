#!/usr/bin/env python
"""Narrow TLS re-search in a ±5% window around the broad-search candidate.

Refinement runs TLS over a dense period grid in a tight range so the reported
period and its uncertainty are tighter than the broad search can give. Returns the
refined period and uncertainty, plus the refined SDE/SNR for the final report.
"""
import json
import sys

import numpy as np


def _read_state():
    return json.load(sys.stdin)["currentState"]


def main():
    import transitleastsquares as tls

    state = _read_state()
    candidate = float(state["candidate_period"])

    data = np.load(state["clean_data_path"])
    t = np.asarray(data["time"], dtype=float)
    y = np.asarray(data["flux"], dtype=float)
    e = np.asarray(data["flux_err"], dtype=float)

    period_min = candidate * 0.95
    period_max = candidate * 1.05

    model = tls.transitleastsquares(t, y, e)
    result = model.power(
        period_min=period_min,
        period_max=period_max,
        oversampling_factor=5,
        show_progress_bar=False,
        verbose=False,
    )

    # Do NOT overwrite `final_sde` / `final_snr` here: TLS's SDE is
    # normalised against the full searched power spectrum, so a narrow
    # refine window artificially compresses it. The broad search's SDE
    # is the correct signal-strength metric; refinement only tightens
    # the period.
    out = {
        "period_days": float(result.period),
        "period_uncertainty_days": float(result.period_uncertainty),
        "refine_period_min": period_min,
        "refine_period_max": period_max,
        "refine_sde": float(result.SDE),
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
