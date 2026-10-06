#!/usr/bin/env python3
"""Preprocess the light curve and run a Lomb-Scargle periodogram
(astropy.timeseries.LombScargle). Reports the strongest period and
its false-alarm probability.

The LS periodogram is a general periodicity detector (rotation,
pulsation, EB) — not transit-shaped — so the output does not include
transit depth or duration.
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

    from astropy.timeseries import LombScargle

    ls = LombScargle(time, flux, flux_err)
    f_min = 1.0 / period_max
    f_max = 1.0 / period_min
    frequency, power = ls.autopower(
        minimum_frequency=f_min,
        maximum_frequency=f_max,
        samples_per_peak=10,
    )
    idx = int(np.argmax(power))
    best_freq = float(frequency[idx])
    best_period = 1.0 / best_freq if best_freq > 0 else float("nan")
    try:
        fap = float(ls.false_alarm_probability(power[idx]))
    except Exception:
        fap = float("nan")

    med_p = float(np.median(power))
    std_p = float(np.std(power))
    sde_like = (power[idx] - med_p) / std_p if std_p > 0 else float("nan")

    detection = {
        "method": "ls",
        "period": best_period,
        "period_uncertainty": float("nan"),
        "T0": float("nan"),
        "power": float(power[idx]),
        "false_alarm_probability": fap,
        "SDE": float(sde_like),
        "SNR": float(sde_like),
        "transit_count": 0,
        "odd_even_mismatch_sigma": None,
    }
    out = {"method": "ls", "detection": detection}
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
