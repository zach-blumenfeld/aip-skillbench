"""Box Least Squares (astropy) period search with two-stage refinement.

Stage 1: autopower over a duration grid of 0.05 - 0.30 days.
Stage 2: dense linear grid over [0.95 * P, 1.05 * P] with the same duration grid.

Reads: currentState.preprocessed_path — .npz with time/flux/flux_err.
Writes: {period, power, depth, snr, t0, method_used}.

Notes:
- BLS depth_snr and odd/even depth mismatch are the standard validation stats
  from astropy compute_stats.
- Use BLS when TLS is not available or when the transit is a clean box shape;
  for grazing transits prefer TLS.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import astropy.units as u
from astropy.timeseries import BoxLeastSquares


def _search(t, y, dy, periods=None, durations=None):
    model = BoxLeastSquares(t * u.day, y, dy=dy)
    if durations is None:
        durations = np.linspace(0.05, 0.30, 10) * u.day
    if periods is None:
        pg = model.autopower(durations, objective="likelihood")
    else:
        pg = model.power(periods, durations, objective="likelihood")
    return model, pg


def main() -> None:
    payload = json.loads(sys.stdin.read())
    state = payload["currentState"]
    npz = np.load(state["preprocessed_path"])
    t, y, dy = npz["time"], npz["flux"], npz["flux_err"]

    _, pg = _search(t, y, dy)
    idx = int(np.argmax(pg.power))
    p0 = float(pg.period[idx].to_value(u.day))

    periods = np.linspace(0.95 * p0, 1.05 * p0, 4000) * u.day
    model, pg2 = _search(t, y, dy, periods=periods)
    idx2 = int(np.argmax(pg2.power))
    period = float(pg2.period[idx2].to_value(u.day))
    duration = pg2.duration[idx2]
    t0 = float(pg2.transit_time[idx2].to_value(u.day))
    stats = model.compute_stats(pg2.period[idx2], duration, pg2.transit_time[idx2])
    depth_value, depth_err = stats["depth"]
    depth_snr = float(depth_value) / float(depth_err) if depth_err else float("nan")

    print(json.dumps({
        "period": period,
        "power": float(pg2.power[idx2]),
        "depth": float(depth_value),
        "snr": depth_snr,
        "t0": t0,
        "method_used": "bls",
    }))


if __name__ == "__main__":
    main()
