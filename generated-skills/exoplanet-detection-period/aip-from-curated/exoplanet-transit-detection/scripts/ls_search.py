"""Lomb-Scargle periodogram — for general periodicity, not transit-shaped signals.

Use this branch when the target is stellar rotation, pulsation, or an eclipsing
binary. For hidden planet transits under stellar activity, choose TLS or BLS instead.

Reads: currentState.preprocessed_path — .npz with time/flux/flux_err.
Writes: {period, power, method_used}.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import lightkurve as lk


def main() -> None:
    payload = json.loads(sys.stdin.read())
    state = payload["currentState"]
    npz = np.load(state["preprocessed_path"])
    lc = lk.LightCurve(time=npz["time"], flux=npz["flux"], flux_err=npz["flux_err"])

    pg = lc.to_periodogram(minimum_period=0.5, maximum_period=50)
    p0 = float(pg.period_at_max_power.value)

    pg2 = lc.to_periodogram(minimum_period=0.95 * p0, maximum_period=1.05 * p0)
    period = float(pg2.period_at_max_power.value)

    print(json.dumps({
        "period": period,
        "power": float(pg2.max_power.value),
        "method_used": "ls",
    }))


if __name__ == "__main__":
    main()
