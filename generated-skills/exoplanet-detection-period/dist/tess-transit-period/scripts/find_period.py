#!/usr/bin/env python3
"""Find the orbital period of a transiting exoplanet hidden under stellar variability.

Pipeline: load -> quality-flag filter -> flare/outlier clip -> Lomb-Scargle rotation
period -> detrend (Savitzky-Golay flatten or iterative sine fitting) -> second clip ->
TLS broad search -> TLS refinement (+-5%, dense grid) -> BLS alias check (P/2, P, 2P,
odd/even depths) -> batman model-fit cross-check -> flags -> write period.

Requires: Python >= 3.10, numpy, scipy, astropy, lightkurve, transitleastsquares
(all present in the task container: numpy 1.26, astropy 6.0, lightkurve 2.4,
transitleastsquares 1.32). Optional: batman-package (model-fit cross-check; skipped if absent).

Usage:
    python scripts/find_period.py LIGHTCURVE [--out PERIOD_TXT] [--json REPORT_JSON]
        [--flag-good zero|nonzero|all] [--detrend flatten|sine] [--window-days W]
        [--period-min PMIN] [--period-max PMAX] [--force-factor 0.5|1|2]
        [--mask P,T0,DUR ...]
"""
import argparse
import json
import sys
import time as _time
import warnings

import numpy as np

warnings.filterwarnings("ignore")

try:
    import lightkurve as lk
    from astropy.timeseries import BoxLeastSquares, LombScargle
    from transitleastsquares import transitleastsquares, transit_mask
except ImportError as exc:  # pragma: no cover
    sys.exit(f"Missing package: {exc.name}. Needs numpy, scipy, astropy, lightkurve, "
             f"transitleastsquares.")


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- loading
def load(path, cols):
    """Whitespace- or comma-separated text, '#' comments; returns t, f, q, e."""
    with open(path) as fh:
        first = next((ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")), "")
    delim = "," if "," in first else None
    try:
        data = np.genfromtxt(path, comments="#", delimiter=delim)
    except Exception:  # header line without '#'
        data = np.genfromtxt(path, comments="#", delimiter=delim, skip_header=1)
    data = np.atleast_2d(data)
    data = data[~np.all(np.isnan(data), axis=1)]
    ncol = data.shape[1]
    ti, fi, qi, ei = cols
    t = data[:, ti]
    f = data[:, fi]
    q = data[:, qi] if qi is not None and qi < ncol else np.zeros_like(t)
    e = data[:, ei] if ei is not None and ei < ncol else np.full_like(t, np.nan)
    return t, f, q, e


def quality_filter(t, f, q, e, mode):
    finite = np.isfinite(t) & np.isfinite(f)
    if mode == "zero":
        good = q == 0
    elif mode == "nonzero":
        good = q != 0
    else:
        good = np.ones_like(t, bool)
    keep = finite & good
    def p2p(x):
        return float(1.4826 * np.median(np.abs(np.diff(x)))) if x.size > 10 else float("nan")
    info = {"p2p_scatter_flag_zero": p2p(f[finite & (q == 0)]),
            "p2p_scatter_flag_nonzero": p2p(f[finite & (q != 0)]),
            "n_rows": int(t.size), "n_flag_zero": int(np.sum(q == 0)),
            "n_flag_nonzero": int(np.sum(q != 0)), "n_nonfinite": int(np.sum(~finite)),
            "flag_mode": mode, "n_after_quality": int(keep.sum())}
    t, f, q, e = t[keep], f[keep], q[keep], e[keep]
    o = np.argsort(t)
    t, f, e = t[o], f[o], e[o]
    med = np.nanmedian(f)
    f = f / med
    e = e / med
    bad_e = ~np.isfinite(e) | (e <= 0)
    if bad_e.any():  # TLS needs uncertainties: fill from point-to-point scatter
        p2p = 1.4826 * np.median(np.abs(np.diff(f))) / np.sqrt(2)
        e[bad_e] = p2p
        info["n_flux_err_filled"] = int(bad_e.sum())
    return t, f, e, info


def clip(lc, upper, lower):
    """Asymmetric sigma clip: flares are positive, transits are negative."""
    out, mask = lc.remove_outliers(sigma_upper=upper, sigma_lower=lower, return_mask=True)
    return out, int(mask.sum())


# ---------------------------------------------------------------- variability
def rotation(t, f, span):
    fmin = 1.0 / max(min(span / 2.0, 30.0), 0.2)
    freq, power = LombScargle(t, f).autopower(minimum_frequency=fmin,
                                              maximum_frequency=1 / 0.04,
                                              samples_per_peak=10)
    i = int(np.argmax(power))
    p_rot = float(1 / freq[i])
    amp = float(np.percentile(f, 95) - np.percentile(f, 5)) / 2
    return p_rot, float(power[i]), amp


def odd(n):
    n = int(round(n))
    return n if n % 2 else n + 1


def flatten(lc, window_days, cadence, mask=None):
    wl = max(odd(window_days / cadence), 5)
    return lc.flatten(window_length=wl, polyorder=2, break_tolerance=10, mask=mask), wl


def sine_detrend(lc, n_iter, min_period):
    """Iteratively divide out the strongest Lomb-Scargle sinusoid (periods > min_period)."""
    t = lc.time.value
    y = lc.flux.value.copy()
    span = t.max() - t.min()
    removed = []
    for _ in range(n_iter):
        ls = LombScargle(t, y)
        freq, power = ls.autopower(minimum_frequency=1 / span,
                                   maximum_frequency=1 / min_period, samples_per_peak=10)
        fbest = freq[np.argmax(power)]
        model = ls.model(t, fbest)
        y = y / model
        removed.append(float(1 / fbest))
    out = lc.copy()
    out.flux = y
    return out, removed


# ---------------------------------------------------------------- searches
def tls_search(t, f, e, pmin, pmax, oversampling, threads):
    model = transitleastsquares(t, f, e, verbose=False)
    return model.power(period_min=pmin, period_max=pmax, oversampling_factor=oversampling,
                       duration_grid_step=1.1, use_threads=threads,
                       show_progress_bar=False, verbose=False)


def bls_fine(t, f, e, period, rel=0.01, durations=None, n=4000):
    bls = BoxLeastSquares(t, f, dy=e)
    periods = np.linspace(period * (1 - rel), period * (1 + rel), n)
    r = bls.power(periods, durations, objective="snr")
    j = int(np.argmax(r.power))
    p, d, t0 = r.period[j], r.duration[j], r.transit_time[j]
    s = bls.compute_stats(p, d, t0)
    depth, depth_err = s["depth"]
    do, do_err = s["depth_odd"]
    de, de_err = s["depth_even"]
    counts = np.asarray(s["per_transit_count"])
    oe_sigma = abs(do - de) / np.hypot(do_err, de_err) if np.isfinite(do_err * de_err) else np.nan
    return {"period": float(p), "duration": float(d), "t0": float(t0),
            "snr_power": float(r.power[j]), "depth": float(depth),
            "depth_snr": float(depth / depth_err) if depth_err > 0 else 0.0,
            "depth_odd": float(do), "depth_odd_snr": float(do / do_err) if do_err > 0 else 0.0,
            "depth_even": float(de), "depth_even_snr": float(de / de_err) if de_err > 0 else 0.0,
            "odd_even_sigma": float(oe_sigma),
            "transits_with_data": int(np.sum(counts > 0)), "transit_windows": int(counts.size)}


def model_fit(t, f, e, period, t0, duration, depth, cadence):
    """Least-squares batman fit of P, T0, Rp/Rs, a/Rs, b to points near transit."""
    try:
        import batman
        from scipy.optimize import least_squares
    except ImportError:
        return None
    phase = np.abs(((t - t0 + period / 2) % period) - period / 2)
    sel = phase < max(3 * duration, 0.1)
    if sel.sum() < 20:
        return None
    x, y, w = t[sel], f[sel], e[sel]
    pm = batman.TransitParams()
    pm.t0, pm.per, pm.rp = t0, period, np.sqrt(max(depth, 1e-5))
    a0 = max(period / (np.pi * max(duration, 1e-3)), 2.5)
    pm.a, pm.inc, pm.ecc, pm.w, pm.u, pm.limb_dark = a0, 89.0, 0.0, 90.0, [0.4, 0.2], "quadratic"
    mdl = batman.TransitModel(pm, x, supersample_factor=3, exp_time=cadence)

    def res(p):
        pm.t0, pm.per, pm.rp, pm.a, b = p
        pm.inc = float(np.degrees(np.arccos(min(b / pm.a, 1.0))))
        return (mdl.light_curve(pm) - y) / w

    dp = 0.02 * period / 5
    lo = [t0 - duration, period - dp, 0.003, 1.5, 0.0]
    hi = [t0 + duration, period + dp, 0.5, 300.0, 1.0]
    p0 = np.clip([t0, period, pm.rp, a0, 0.3], np.array(lo) + 1e-9, np.array(hi) - 1e-9)
    try:
        s = least_squares(res, p0, bounds=(lo, hi))
        cov = np.linalg.inv(s.jac.T @ s.jac) * np.sum(s.fun ** 2) / max(len(y) - 5, 1)
        return {"period": float(s.x[1]), "period_err": float(np.sqrt(cov[1, 1])),
                "t0": float(s.x[0]), "rp_rs": float(s.x[2]), "a_rs": float(s.x[3]),
                "b": float(s.x[4])}
    except Exception:
        return None


def near_harmonic(p, p_rot, tol=0.01):
    """Return the rotation harmonic (P_rot/k or k*P_rot/2) within tol of p, else None."""
    cands = [p_rot / k for k in (1, 2, 3, 4)] + [k * p_rot / 2 for k in range(1, 41)]
    for h in cands:
        if abs(p - h) / h < tol:
            return round(h, 5)
    return None


def distinct_peaks(periods, power, n=8, sep=0.01):
    order = np.argsort(power)[::-1]
    out = []
    for j in order:
        if all(abs(periods[j] - q) / q > sep for q, _ in out):
            out.append((float(periods[j]), float(power[j])))
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lightcurve")
    ap.add_argument("--out", help="write the final period (5 decimals) to this file")
    ap.add_argument("--json", help="write the full diagnostic report to this file")
    ap.add_argument("--cols", default="0,1,2,3",
                    help="column indices time,flux,flag,flux_err (use -1 for absent)")
    ap.add_argument("--flag-good", choices=["zero", "nonzero", "all"], default="zero")
    ap.add_argument("--detrend", choices=["flatten", "sine"], default="flatten")
    ap.add_argument("--window-days", type=float, default=None,
                    help="flatten window in days (default: min(0.5, P_rot/3), floor 0.25)")
    ap.add_argument("--sine-iter", type=int, default=50)
    ap.add_argument("--period-min", type=float, default=0.5)
    ap.add_argument("--period-max", type=float, default=None,
                    help="default: half the time span (>= 2 transits)")
    ap.add_argument("--force-factor", type=float, choices=[0.5, 1.0, 2.0], default=1.0,
                    help="multiply the refined period by this alias factor before writing")
    ap.add_argument("--mask", action="append", default=[], metavar="P,T0,DUR",
                    help="mask an already-found signal (period,T0,duration in days) before "
                         "searching; repeatable")
    ap.add_argument("--keep-harmonics", action="store_true",
                    help="do not skip TLS peaks that sit on rotation harmonics")
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    t_start = _time.time()

    cols = [None if int(c) < 0 else int(c) for c in a.cols.split(",")]
    t, f, q, e = load(a.lightcurve, cols)
    t, f, e, rep_q = quality_filter(t, f, q, e, a.flag_good)
    if t.size < 100:
        sys.exit(f"Only {t.size} points left after quality filtering (mode={a.flag_good}); "
                 f"check the flag convention with --flag-good.")
    report = {"quality": rep_q}
    conv_flags = []
    frac_kept = rep_q["n_after_quality"] / max(rep_q["n_rows"], 1)
    if frac_kept < 0.5:
        conv_flags.append(f"quality filter (mode={a.flag_good}) kept only {frac_kept:.0%} of rows: "
                          f"flag convention may be inverted (scatter flag==0: "
                          f"{rep_q['p2p_scatter_flag_zero']:.2e}, flag!=0: "
                          f"{rep_q['p2p_scatter_flag_nonzero']:.2e})")
        log("[quality] WARNING " + conv_flags[-1])
    span = float(t.max() - t.min())
    cadence = float(np.median(np.diff(t)))
    gaps = [[round(float(t[i]), 4), round(float(np.diff(t)[i]), 3)]
            for i in np.where(np.diff(t) > 0.5)[0]]
    report["data"] = {"span_days": round(span, 4), "cadence_min": round(cadence * 1440, 3),
                      "gaps_gt_0.5d": gaps}

    lc = lk.LightCurve(time=t, flux=f, flux_err=e)
    lc, n_clip1 = clip(lc, upper=3, lower=10)
    p_rot, rot_power, amp = rotation(lc.time.value, lc.flux.value, span)
    report["variability"] = {"p_rot_days": round(p_rot, 5), "ls_power": round(rot_power, 4),
                             "semi_amplitude": round(amp, 6), "n_clipped_pass1": n_clip1}
    log(f"[load] {rep_q['n_after_quality']} pts, span {span:.2f} d, cadence {cadence*1440:.2f} min; "
        f"rotation P={p_rot:.4f} d (LS power {rot_power:.2f}), semi-amp {amp:.5f}")

    window = a.window_days if a.window_days else min(0.5, max(p_rot / 3.0, 0.25))
    if a.detrend == "flatten":
        flat, wl = flatten(lc, window, cadence)
        report["detrend"] = {"method": "flatten", "window_days": round(window, 4),
                             "window_cadences": wl}
    else:
        flat, removed = sine_detrend(lc, a.sine_iter, min_period=max(0.25, 4 * cadence))
        report["detrend"] = {"method": "sine", "iterations": a.sine_iter,
                             "first_periods_removed": [round(x, 4) for x in removed[:10]]}
    flat, n_clip2 = clip(flat, upper=3, lower=20)
    if a.detrend == "flatten" and not a.window_days and window > 0.15 and \
            np.std(flat.flux.value) > 1.5 * np.median(flat.flux_err.value):
        # rotation left in the residuals (fast rotator): retry with the shortest safe window
        flat_b, wl_b = flatten(lc, 0.15, cadence)
        flat_b, n_clip_b = clip(flat_b, upper=3, lower=20)
        if np.std(flat_b.flux.value) < 0.8 * np.std(flat.flux.value):
            report["detrend"].update({"window_days": 0.15, "window_cadences": wl_b,
                                      "retried_from_window_days": round(window, 4)})
            flat, n_clip2 = flat_b, n_clip_b
    tt, ff, ee = flat.time.value, flat.flux.value, flat.flux_err.value
    resid = float(np.std(ff))
    # inflate uncertainties to the real residual scatter (red noise, residual variability)
    inflate = max(1.0, resid / float(np.median(ee)))
    ee = ee * inflate
    report["detrend"].update({"n_clipped_pass2": n_clip2, "residual_std": round(resid, 6),
                              "flux_err_inflation": round(inflate, 3)})
    log(f"[detrend] {report['detrend']}")

    for spec in a.mask:
        mp, mt0, mdur = (float(x) for x in spec.split(","))
        keep = ~transit_mask(tt, mp, 2 * mdur, mt0)
        tt, ff, ee = tt[keep], ff[keep], ee[keep]
        report.setdefault("masked", []).append({"period": mp, "t0": mt0, "duration": mdur,
                                                "n_masked": int((~keep).sum())})
        log(f"[mask] removed {(~keep).sum()} points around P={mp} T0={mt0}")

    pmax = a.period_max if a.period_max else span / 2.0
    r1 = tls_search(tt, ff, ee, a.period_min, pmax, 3, a.threads)
    p1 = float(r1.period)
    peaks = distinct_peaks(np.asarray(r1.periods), np.asarray(r1.power), n=30)
    report["tls_top_peaks"] = [[round(q, 5), round(w, 2)] for q, w in peaks[:8]]
    skipped, all_harmonic = [], False
    if not a.keep_harmonics and near_harmonic(p1, p_rot):
        # top peak is residual stellar variability: take the best non-harmonic peak
        for q, w in peaks:
            if near_harmonic(q, p_rot):
                skipped.append(round(q, 5))
            else:
                p1 = q
                break
        else:
            all_harmonic, skipped = True, []
    report["rotation_harmonic_peaks_skipped"] = skipped
    log(f"[tls peaks] {report['tls_top_peaks']}" + (f"; skipped harmonics {skipped}" if skipped else ""))
    report["tls_broad"] = {"period": round(p1, 6), "SDE": round(float(r1.SDE), 2),
                           "snr": round(float(r1.snr), 2), "duration": round(float(r1.duration), 5),
                           "depth": round(1 - float(r1.depth), 6), "T0": round(float(r1.T0), 5),
                           "distinct_transits": int(r1.distinct_transit_count),
                           "empty_transits": int(r1.empty_transit_count)}
    log(f"[tls broad] {report['tls_broad']}")

    lo, hi = max(p1 * 0.95, a.period_min * 0.95), p1 * 1.05
    r2 = tls_search(tt, ff, ee, lo, hi, 10, a.threads)
    p2 = float(r2.period)
    report["tls_refined"] = {"period": round(p2, 6),
                             "period_uncertainty": round(float(r2.period_uncertainty), 6),
                             "snr": round(float(r2.snr), 2),
                             "T0": round(float(r2.T0), 5), "duration": round(float(r2.duration), 5),
                             "depth": round(1 - float(r2.depth), 6),
                             "odd_even_mismatch_sigma": round(float(r2.odd_even_mismatch), 2),
                             "distinct_transits": int(r2.distinct_transit_count),
                             "empty_transits": int(r2.empty_transit_count)}
    log(f"[tls refined] {report['tls_refined']}")

    d0 = float(r2.duration)
    durs = np.unique(np.clip(np.array([0.5, 0.75, 1.0, 1.5, 2.0]) * d0, 2 * cadence, None))
    alias = {}
    for fac in (0.5, 1.0, 2.0):
        if fac * p2 > span:  # fewer than one full cycle: no information
            continue
        alias[str(fac)] = bls_fine(tt, ff, ee, fac * p2, durations=durs)
    report["bls_alias_check"] = alias
    for k, v in alias.items():
        log(f"[bls x{k}] P={v['period']:.5f} depth_snr={v['depth_snr']:.1f} "
            f"odd={v['depth_odd']*1e6:.0f}ppm({v['depth_odd_snr']:.1f}s) "
            f"even={v['depth_even']*1e6:.0f}ppm({v['depth_even_snr']:.1f}s) "
            f"odd-even={v['odd_even_sigma']:.1f}s transits={v['transits_with_data']}/{v['transit_windows']}")

    # ------------------------------------------------ flags (deterministic rules)
    flags = list(conv_flags)
    # SDE is only meaningful from the broad search (it is normalised over the searched range)
    sde, snr = float(r1.SDE), float(r2.snr)
    if sde < 6:
        flags.append(f"weak: broad-search SDE {sde:.2f} < 6")
    elif sde < 9:
        flags.append(f"moderate: broad-search SDE {sde:.2f} < 9 (strong is > 9)")
    if snr < 7:
        flags.append(f"weak: SNR {snr:.1f} < 7")
    base = alias["1.0"]
    if base["transits_with_data"] < 2:
        flags.append("only one transit with data at this period")
    if base["odd_even_sigma"] > 3:
        dbl = alias.get("2.0")
        at2 = f"{dbl['odd_even_sigma']:.1f} sigma at 2P" if dbl else "2P not testable"
        flags.append(f"odd/even depth mismatch {base['odd_even_sigma']:.1f} sigma at P ({at2}): "
                     f"true period may be 2P, or an eclipsing binary")
    half = alias.get("0.5")
    half_ok = bool(half and half["odd_even_sigma"] < 3 and min(half["depth_odd_snr"],
                   half["depth_even_snr"]) > 3 and half["depth_snr"] > 7)
    if half_ok:
        flags.append("P/2 has significant, consistent odd and even transits: true period may be P/2")
    if all_harmonic:
        flags.append("all top-30 TLS peaks sit on rotation harmonics: variability not removed")
    if skipped:
        flags.append(f"top TLS peak(s) {skipped} were rotation harmonics and were skipped; "
                     f"refined the next peak (SDE {dict(peaks).get(p1, float('nan')):.1f})")
    harm = near_harmonic(p2, p_rot)
    if harm:
        flags.append(f"period within 1% of a rotation harmonic ({harm} d): may be residual variability")
    if abs(float(base["period"]) - p2) / p2 > 0.002:
        flags.append(f"BLS ({base['period']:.5f}) and TLS ({p2:.5f}) disagree by > 0.2%")
    if r2.empty_transit_count > 0:
        flags.append(f"{r2.empty_transit_count} transit epoch(s) fall in data gaps")

    fit = model_fit(tt, ff, ee, p2, float(r2.T0), float(r2.duration), 1 - float(r2.depth), cadence)
    report["model_fit"] = fit
    if fit:
        log(f"[batman fit] P={fit['period']:.5f} +- {fit['period_err']:.5f}")
        if abs(fit["period"] - p2) > max(3 * fit["period_err"], float(r2.period_uncertainty)):
            flags.append(f"batman fit period {fit['period']:.5f} disagrees with TLS {p2:.5f} "
                         f"beyond 3 sigma and the TLS uncertainty")

    final = p2 * a.force_factor
    report["flags"] = flags
    report["final_period"] = round(final, 5)
    report["force_factor"] = a.force_factor
    report["runtime_s"] = round(_time.time() - t_start, 1)

    if a.out:
        with open(a.out, "w") as fh:
            fh.write(f"{final:.5f}\n")
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(report, fh, indent=2)
    log("[flags] " + ("none" if not flags else "\n        ".join(flags)))
    print(json.dumps({"final_period": round(final, 5), "flags": flags,
                      "tls_refined": report["tls_refined"], "p_rot_days": report["variability"]["p_rot_days"],
                      "detrend": report["detrend"]}, indent=1))


if __name__ == "__main__":
    main()
