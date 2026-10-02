"""Preprocess a TESS-format light curve for period search.

Reads: currentState.data_path — 4-column text file (time in MJD, flux, quality flag, flux error).
Writes: {preprocessed_path} — path to an .npz with cleaned time/flux/flux_err arrays.

Pipeline (order matters):
1. Quality filter: keep rows where flag == 0 (standard TESS convention: 0 = good).
2. Outlier removal: lightkurve remove_outliers(sigma=3).
3. Flatten: lightkurve flatten() (Savitzky-Golay) to remove stellar variability while
   preserving short-duration transit dips.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import lightkurve as lk


def main() -> None:
    payload = json.loads(sys.stdin.read())
    state = payload["currentState"]
    data_path = state["data_path"]

    data = np.loadtxt(data_path)
    time = data[:, 0]
    flux = data[:, 1]
    flag = data[:, 2]
    error = data[:, 3]

    good = flag == 0
    time, flux, error = time[good], flux[good], error[good]

    lc = lk.LightCurve(time=time, flux=flux, flux_err=error)
    lc_clean = lc.remove_outliers(sigma=3)
    lc_flat = lc_clean.flatten()

    out_path = os.environ.get("AIP_PREPROCESSED_PATH") or os.path.join(
        tempfile.gettempdir(), "exoplanet_preprocessed_lc.npz"
    )
    np.savez(
        out_path,
        time=np.asarray(lc_flat.time.value, dtype=float),
        flux=np.asarray(lc_flat.flux.value, dtype=float),
        flux_err=np.asarray(lc_flat.flux_err.value, dtype=float),
    )

    print(json.dumps({
        "preprocessed_path": out_path,
        "n_points": int(good.sum()),
    }))


if __name__ == "__main__":
    main()
