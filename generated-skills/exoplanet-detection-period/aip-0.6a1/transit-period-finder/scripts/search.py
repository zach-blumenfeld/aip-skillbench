"""Detrend stellar activity and search for the transit period.

1. Flatten (Savitzky-Golay, lightkurve) with several windows tied to the stellar
   variability timescale: the window must be longer than a transit but shorter than
   the rotation period. Pick the window whose BLS periodogram has the highest SDE.
2. TLS broad search on that flattened curve (flux_err always passed).
3. Mask the found transits, re-flatten the cleaned (un-flattened) curve with the mask
   so the trend fit cannot eat the transit depth, then refine with TLS over +/-5%
   with a dense grid. BLS on the same curve is the cross-check.
4. Trapezoid least-squares ephemeris fit seeded by TLS: the final period. TLS/BLS grid
   periods are only good to a fraction of their peak width; the fit uses every transit's
   timing and is ~10x more precise. Falls back to TLS if the fit fails or wanders.
5. Vetting statistics for the candidate and its P/2 and 2P aliases.
"""
import os

import numpy as np

from lc_common import (clip_upper, emit, fit_ephemeris, flatten, load_arrays,
                       read_state, save_arrays)

POST_FLATTEN_UPPER_SIGMA = 5.0
WINDOW_FRACTIONS_OF_ROT = [0.1, 0.15, 0.2, 0.3, 0.4]   # used when rotation is clear
FALLBACK_WINDOWS_DAYS = [0.25, 0.4, 0.6, 0.8, 1.0]     # weak / no rotation signal
MIN_WINDOW_DAYS = 0.12     # ~3x a short transit; shorter windows erase transits
MAX_WINDOW_DAYS = 1.5
ROT_POWER_CLEAR = 0.1
PERIOD_MIN_DAYS = 0.3
BLS_DURATIONS = [0.02, 0.03, 0.045, 0.065, 0.09, 0.12, 0.16, 0.22]
REFINE_FRACTION = 0.05
REFINE_OVERSAMPLING = 10


def candidate_windows(p_rot, rot_power):
    if rot_power >= ROT_POWER_CLEAR and p_rot > 0:
        ws = [p_rot * fr for fr in WINDOW_FRACTIONS_OF_ROT]
    else:
        ws = list(FALLBACK_WINDOWS_DAYS)
    ws = sorted({round(min(max(w, MIN_WINDOW_DAYS), MAX_WINDOW_DAYS), 3) for w in ws})
    return ws


def sde(power):
    power = np.asarray(power, float)
    sd = np.std(power)
    return float((power.max() - np.mean(power)) / sd) if sd > 0 else 0.0


def bls_scan(t, f, e, pmin, pmax):
    from astropy.timeseries import BoxLeastSquares
    durs = [d for d in BLS_DURATIONS if d < pmin]
    bls = BoxLeastSquares(t, f, e)
    periods = bls.autoperiod(durs, minimum_period=pmin, maximum_period=pmax,
                             frequency_factor=1.0)
    pg = bls.power(periods, durs, objective="snr")
    i = int(np.argmax(pg.power))
    return {
        "period": float(pg.period[i]),
        "duration": float(pg.duration[i]),
        "depth": float(pg.depth[i]),
        "t0": float(pg.transit_time[i]),
        "sde": sde(pg.power),
    }


def run_tls(t, f, e, **kw):
    from transitleastsquares import transitleastsquares
    model = transitleastsquares(t, f, e)
    return model.power(show_progress_bar=False, verbose=False,
                       use_threads=os.cpu_count() or 1, **kw)


def bls_stats(t, f, e, period, duration, t0):
    from astropy.timeseries import BoxLeastSquares
    bls = BoxLeastSquares(t, f, e)
    duration = min(duration, 0.9 * period)
    s = bls.compute_stats(period, duration, t0)
    depth, derr = float(s["depth"][0]), float(s["depth"][1])
    odd, oerr = float(s["depth_odd"][0]), float(s["depth_odd"][1])
    even, eerr = float(s["depth_even"][0]), float(s["depth_even"][1])
    oe_err = np.hypot(oerr, eerr)
    if not np.isfinite(oe_err):   # one parity has no transits with data
        oe_err = 0.0
    ptc = np.asarray(s["per_transit_count"])
    return {
        "period": round(float(period), 6),
        "depth_ppt": round(depth * 1e3, 4),
        "depth_snr": round(depth / derr, 2) if derr > 0 else None,
        "depth_odd_ppt": round(odd * 1e3, 4),
        "depth_even_ppt": round(even * 1e3, 4),
        "odd_even_mismatch_sigma": round(abs(odd - even) / oe_err, 2) if oe_err > 0 else None,
        "depth_at_phase_0p5_ppt": round(float(s["depth_phased"][0]) * 1e3, 4),
        "depth_at_phase_0p5_snr": (round(float(s["depth_phased"][0] / s["depth_phased"][1]), 2)
                                   if s["depth_phased"][1] > 0 else None),
        "transits_with_data": int((ptc > 0).sum()),
        "transits_expected": int(len(ptc)),
    }


def harmonic_of(p, p_rot, tol=0.02):
    for k in (1, 2, 3, 4):
        for ratio, label in ((k, f"{k}x"), (1.0 / k, f"1/{k}x")):
            if abs(p / (p_rot * ratio) - 1) < tol:
                return f"{label} rotation period"
    return None


def main():
    state = read_state()
    clean = load_arrays(state["clean_file"])
    p_rot = float(state["rotation_period_days"])
    rot_power = float(state["rotation_power"])
    work_dir = state["work_dir"]
    t, f, e = clean["time"], clean["flux"], clean["flux_err"]
    cadence = float(np.median(np.diff(t)))
    baseline = float(t[-1] - t[0])
    pmin, pmax = PERIOD_MIN_DAYS, baseline / 2.0   # >= 2 transits inside the baseline

    # 1. window scan ---------------------------------------------------------
    scan = []
    for w in candidate_windows(p_rot, rot_power):
        ft, ff, fe = flatten(t, f, e, w, cadence)
        ft, ff, fe, _ = clip_upper(ft, ff, fe, POST_FLATTEN_UPPER_SIGMA)
        r = bls_scan(ft, ff, fe, pmin, pmax)
        r["window_days"] = w
        scan.append(r)
    best = max(scan, key=lambda r: r["sde"])
    w_best = best["window_days"]

    # 2. TLS broad search ----------------------------------------------------
    ft, ff, fe = flatten(t, f, e, w_best, cadence)
    ft, ff, fe, _ = clip_upper(ft, ff, fe, POST_FLATTEN_UPPER_SIGMA)
    broad = run_tls(ft, ff, fe, period_min=pmin, period_max=pmax)
    p0, dur0, t00 = float(broad.period), float(broad.duration), float(broad.T0)

    # 3. masked re-flatten + refinement -------------------------------------
    from transitleastsquares import transit_mask
    in_tr = transit_mask(t, p0, 2.5 * dur0, t00)
    w_ref = max(w_best, 4.0 * dur0)
    rt, rf, re_ = flatten(t, f, e, w_ref, cadence, mask=in_tr)
    rt, rf, re_, _ = clip_upper(rt, rf, re_, POST_FLATTEN_UPPER_SIGMA)
    flat_file = save_arrays(os.path.join(work_dir, "flat.npz"), time=rt, flux=rf, flux_err=re_,
                            window_days=np.array(w_ref))
    lo, hi = p0 * (1 - REFINE_FRACTION), min(p0 * (1 + REFINE_FRACTION), baseline)
    ref = run_tls(rt, rf, re_, period_min=lo, period_max=hi,
                  oversampling_factor=REFINE_OVERSAMPLING)
    p, dur, t0 = float(ref.period), float(ref.duration), float(ref.T0)

    from astropy.timeseries import BoxLeastSquares
    bls = BoxLeastSquares(rt, rf, re_)
    fine = np.linspace(p * 0.99, p * 1.01, 20001)
    durs = sorted({round(dur * k, 4) for k in (0.7, 0.85, 1.0, 1.2)})
    pg = bls.power(fine, [d for d in durs if d < fine[0]], objective="likelihood")
    p_bls = float(pg.period[int(np.argmax(pg.power))])

    # 4. ephemeris fit -------------------------------------------------------
    p_tls = p
    halfwidth = max(float(ref.period_uncertainty), 1e-3 * p)
    fit = fit_ephemeris(rt, rf, re_, p, t0, dur, 1 - float(ref.depth), halfwidth)
    if fit and not fit["at_bound"] and abs(fit["period"] - p) <= halfwidth:
        p, t0, p_err, source = fit["period"], fit["t0"], fit["period_err"], "trapezoid_fit"
    else:
        p_err, source = float(ref.period_uncertainty), "tls_refined"

    # 5. vetting -------------------------------------------------------------
    aliases = {
        "reported": bls_stats(rt, rf, re_, p, dur, t0),
        "half": bls_stats(rt, rf, re_, p / 2, dur, t0) if p / 2 >= pmin else None,
        "double": bls_stats(rt, rf, re_, 2 * p, dur, t0) if 2 * p <= baseline else None,
    }
    n_agree = sum(1 for r in scan if any(abs(r["period"] / p - k) < 0.01 * k for k in (0.5, 1, 2)))
    empty = int(getattr(ref, "empty_transit_count", 0) or 0)

    candidate = {
        "period_days": round(p, 6),
        "period_uncertainty_days": round(p_err, 6),
        "period_source": source,
        "tls_refined_period_days": round(p_tls, 6),
        "tls_period_uncertainty_days": round(float(ref.period_uncertainty), 6),
        "bls_crosscheck_period_days": round(p_bls, 6),
        "fit_chi2_reduced": round(fit["chi2_reduced"], 3) if fit else None,
        "broad_search_period_days": round(p0, 6),
        "t0": round(t0, 5),
        "duration_hours": round(dur * 24, 3),
        "depth_ppt": round((1 - float(ref.depth)) * 1e3, 4),
        "tls_sde_broad": round(float(broad.SDE), 2),
        "tls_snr": round(float(ref.snr), 2),
        "tls_odd_even_mismatch_sigma": round(float(ref.odd_even_mismatch), 2),
        "transit_count": int(ref.transit_count),
        "distinct_transit_count": int(ref.distinct_transit_count),
        "empty_transit_count": empty,
        "rotation_period_days": p_rot,
        "rotation_power": rot_power,
        "period_matches_rotation_harmonic": harmonic_of(p, p_rot),
        "flatten_window_days": w_best,
        "refine_window_days": round(w_ref, 4),
        "windows_agreeing_with_period": f"{n_agree}/{len(scan)}",
        "window_scan": [{k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()}
                        for r in scan],
        "aliases": aliases,
    }
    emit({"candidate": candidate, "flat_file": flat_file, "candidate_period_days": round(p, 6)})


if __name__ == "__main__":
    main()
