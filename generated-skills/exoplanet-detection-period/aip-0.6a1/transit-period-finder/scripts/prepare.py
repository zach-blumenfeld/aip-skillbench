"""Load and clean a light curve, then measure the stellar-activity timescale.

Order matters: quality flags -> non-finite rows -> outliers (before any detrending).
Outlier clipping is asymmetric: positive outliers (flares, cosmic rays) at 3 sigma,
negative points only when isolated single cadences beyond 5 sigma, because transits
are multi-cadence dips and must survive cleaning.
"""
import os

import numpy as np

from lc_common import (emit, fail, load_lightcurve, mad_std, read_state,
                       running_median, save_arrays, window_cadences)

UPPER_SIGMA = 3.0          # initial outlier pass (flares, cosmic rays)
LOWER_ISOLATED_SIGMA = 5.0  # single-cadence negative glitches only
ROT_MIN_PERIOD = 0.1       # days; stellar rotation search range lower bound
ROT_MAX_PERIOD = 100.0     # days; capped at half the baseline below


def main():
    state = read_state()
    path = state["lc_path"]
    convention = str(state.get("flag_convention", "zero_is_good")).strip().lower()
    work_dir = state["work_dir"]

    lc = load_lightcurve(path)
    t, f, q, e = lc["time"], lc["flux"], lc["flag"], lc["flux_err"]
    n_raw = len(t)

    # 1. quality flags -----------------------------------------------------
    n_flagged = 0
    if q is not None:
        if convention in ("zero_is_good", "0_is_good", "zero"):
            good = q == 0
        elif convention in ("nonzero_is_good", "zero_is_bad"):
            good = q != 0
        else:
            fail(f"flag_convention must be zero_is_good or nonzero_is_good, got {convention!r}")
        n_flagged = int((~good).sum())
        if good.sum() == 0:
            fail(f"flag convention {convention} leaves 0 of {n_raw} points; the file probably "
                 "uses the opposite convention - re-run with the other flag_convention")
        t, f = t[good], f[good]
        e = e[good] if e is not None else None

    # 2. non-finite rows, sort, duplicate timestamps ------------------------
    fin = np.isfinite(t) & np.isfinite(f)
    if e is not None:
        fin &= np.isfinite(e)
    n_nonfinite = int((~fin).sum())
    t, f = t[fin], f[fin]
    e = e[fin] if e is not None else None
    order = np.argsort(t, kind="stable")
    t, f = t[order], f[order]
    e = e[order] if e is not None else None
    uniq = np.concatenate([[True], np.diff(t) > 0])
    t, f = t[uniq], f[uniq]
    e = e[uniq] if e is not None else None
    if len(t) < 100:
        fail(f"only {len(t)} usable points after quality filtering")

    # normalize if the flux is not already relative
    med = np.median(f)
    normalized = False
    if med <= 0:
        fail("median flux is not positive; expected flux, not magnitudes")
    if abs(med - 1.0) > 0.05:
        f = f / med
        e = e / med if e is not None else None
        normalized = True

    # flux uncertainties are mandatory for TLS weighting
    err_estimated = False
    if e is None or not np.any(e > 0):
        e = np.full_like(f, mad_std(np.diff(f)) / np.sqrt(2))
        err_estimated = True
    else:
        bad = ~(e > 0)
        if bad.any():
            e = e.copy()
            e[bad] = np.median(e[~bad])

    cadence = float(np.median(np.diff(t)))
    baseline = float(t[-1] - t[0])

    # 3. stellar variability timescale (Lomb-Scargle on the filtered flux) ---
    from astropy.timeseries import LombScargle
    pmax = min(ROT_MAX_PERIOD, baseline / 2.0)
    ls = LombScargle(t, f, e)
    freq, power = ls.autopower(minimum_frequency=1.0 / pmax,
                               maximum_frequency=1.0 / ROT_MIN_PERIOD,
                               samples_per_peak=10)
    i = int(np.argmax(power))
    p_rot = float(1.0 / freq[i])
    rot_power = float(power[i])

    # 4. outliers relative to a running median (short enough to follow rotation)
    med_window_days = min(0.5, p_rot / 6.0)
    trend = running_median(f, window_cadences(med_window_days, cadence))
    resid = f - trend
    s = mad_std(resid)
    upper = resid > UPPER_SIGMA * s
    low = resid < -LOWER_ISOLATED_SIGMA * s
    prev_low = np.concatenate([[False], resid[:-1] < -2.0 * s])
    next_low = np.concatenate([resid[1:] < -2.0 * s, [False]])
    lower = low & ~prev_low & ~next_low
    keep = ~(upper | lower)
    t, f, e = t[keep], f[keep], e[keep]

    gaps = np.where(np.diff(t) > 10 * cadence)[0]
    gap_list = [[round(float(t[g]), 5), round(float(t[g + 1]), 5)] for g in gaps]

    clean_file = save_arrays(os.path.join(work_dir, "clean.npz"), time=t, flux=f, flux_err=e)

    emit({
        "clean_file": clean_file,
        "rotation_period_days": round(p_rot, 5),
        "rotation_power": round(rot_power, 4),
        "prep_summary": {
            "column_map": lc["column_map"],
            "n_raw": n_raw,
            "n_flagged_removed": n_flagged,
            "n_nonfinite_removed": n_nonfinite,
            "n_upper_outliers_removed": int(upper.sum()),
            "n_isolated_low_outliers_removed": int(lower.sum()),
            "n_final": int(len(t)),
            "cadence_days": round(cadence, 6),
            "baseline_days": round(baseline, 4),
            "gaps": gap_list,
            "flux_normalized_by_median": normalized,
            "flux_err_estimated": err_estimated,
            "variability_rms_ppt": round(float(np.std(f)) * 1e3, 3),
            "white_noise_ppt": round(float(np.median(e)) * 1e3, 3),
        },
    })


if __name__ == "__main__":
    main()
