"""Sigma-clip and flatten a cleaned light curve.

Two-pass pipeline adapted from `source/light-curve-preprocessing` with one
critical fix: the first clip is **upper-sigma-only**, not symmetric. A
symmetric sigma=3 clip on raw data wipes out deep (hot-Jupiter-class)
transits because the raw-flux standard deviation is dominated by the
transit depth itself, so in-transit points sit outside the 3-sigma band
and get thrown away before flattening ever runs. Positive outliers
(flares, cosmic rays) are the only ones that must come out pre-flatten;
negative excursions are left for the post-flatten clip to judge against a
properly detrended noise estimate.

  1. Clip positive outliers only (sigma_upper=3, sigma_lower=inf) on the
     raw curve. Preserves transits of any depth.
  2. Flatten with a Savitzky-Golay filter via lightkurve to remove stellar
     variability and instrumental drift while preserving transit shapes.
  3. Upper-only second-pass sigma=5 clip on the flattened curve to remove
     residual positive outliers against a trend-corrected noise level.
     Low-side clipping is intentionally disabled on both passes: in a
     transit search the thing we are looking for IS a negative outlier,
     and a 2% transit easily sits 20+ sigma below the median of the
     flattened residuals.

The flatten `window_length` is chosen from the cadence so it is long enough
to span typical transit durations (hours) but shorter than typical stellar
rotation periods. For TESS 2-minute cadence this is ~500 cadences; for
30-minute cadence it is ~51. The window must be odd and >=5.
"""
import json
import os
import sys

import numpy as np


def _choose_window(time):
    cadence_days = float(np.median(np.diff(time)))
    cadence_minutes = cadence_days * 24.0 * 60.0 if cadence_days > 0 else 2.0
    # Target ~16 hours of coverage per window: long enough to span transits
    # (a few hours) with margin, short enough to track stellar rotation.
    target_hours = 16.0
    window = int(round(target_hours * 60.0 / max(cadence_minutes, 0.1)))
    if window % 2 == 0:
        window += 1
    return max(window, 51)


def main():
    state = json.load(sys.stdin).get("currentState", {})
    cleaned_cache = state["cleaned_cache"]
    work_dir = state.get("work_dir") or os.path.dirname(cleaned_cache)

    arrays = np.load(cleaned_cache)
    time = arrays["time"]
    flux = arrays["flux"]
    flux_err = arrays["flux_err"]
    n_before = int(time.size)

    import lightkurve as lk

    lc = lk.LightCurve(time=time, flux=flux, flux_err=flux_err)
    # Pass 1: upper-only clip removes flares / cosmic rays without touching
    # transits. sigma_lower=np.inf disables the low-side clip.
    lc = lc.remove_outliers(sigma_upper=3, sigma_lower=np.inf)
    n_after_pass1 = int(lc.flux.size)

    window = _choose_window(np.asarray(lc.time.value))
    lc_flat = lc.flatten(window_length=window)
    # Pass 2: upper-only clip on flattened residuals; keeps the (negative)
    # transit dips, drops residual flares the first pass may have missed.
    lc_flat = lc_flat.remove_outliers(sigma_upper=5, sigma_lower=np.inf)
    n_after = int(lc_flat.flux.size)

    time_out = np.asarray(lc_flat.time.value, dtype=np.float64)
    flux_out = np.asarray(lc_flat.flux.value, dtype=np.float64)
    err_out = np.asarray(lc_flat.flux_err.value, dtype=np.float64)
    # Guard: TLS requires finite positive errors.
    good = np.isfinite(time_out) & np.isfinite(flux_out) & np.isfinite(err_out) & (err_out > 0)
    time_out, flux_out, err_out = time_out[good], flux_out[good], err_out[good]

    flattened_cache = os.path.join(work_dir, "flattened.npz")
    np.savez(flattened_cache, time=time_out, flux=flux_out, flux_err=err_out)

    out = {
        "flattened_cache": flattened_cache,
        "work_dir": work_dir,
        "flatten_window_cadences": int(window),
        "n_before_preprocess": n_before,
        "n_after_sigma_clip": n_after_pass1,
        "n_after_preprocess": int(time_out.size),
    }
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
