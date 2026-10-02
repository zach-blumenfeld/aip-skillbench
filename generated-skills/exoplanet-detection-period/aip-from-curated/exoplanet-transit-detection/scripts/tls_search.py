"""Transit Least Squares period search with two-stage refinement.

Stage 1: broad search on the default TLS period grid.
Stage 2: narrow search over [0.95 * P, 1.05 * P] around the stage-1 winner for
sub-percent precision.

Reads: currentState.preprocessed_path — .npz with time/flux/flux_err.
Writes: {period, sde, snr, t0, depth, method_used}.

Notes:
- flux_err is REQUIRED by TLS — do not pass equal weights.
- SDE >= 9 = very strong candidate, 6-9 = strong, < 6 = weak/likely false positive.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import transitleastsquares as tls


def _run(t, y, dy, **kwargs):
    model = tls.transitleastsquares(t, y, dy)
    return model.power(show_progress_bar=False, verbose=False, **kwargs)


def main() -> None:
    payload = json.loads(sys.stdin.read())
    state = payload["currentState"]
    npz = np.load(state["preprocessed_path"])
    t, y, dy = npz["time"], npz["flux"], npz["flux_err"]

    broad = _run(t, y, dy)
    p0 = float(broad.period)

    refined = _run(t, y, dy, period_min=0.95 * p0, period_max=1.05 * p0)

    print(json.dumps({
        "period": float(refined.period),
        "sde": float(refined.SDE),
        "snr": float(refined.snr),
        "t0": float(refined.T0),
        "depth": float(refined.depth),
        "method_used": "tls",
    }))


if __name__ == "__main__":
    main()
