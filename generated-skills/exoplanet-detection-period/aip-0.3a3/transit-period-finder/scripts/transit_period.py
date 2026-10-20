#!/usr/bin/env python3
"""Find a transiting planet's orbital period in a light curve dominated by stellar variability.

Subcommands (run in order; each prints a JSON report to stdout and, with --out, to a file):

  inspect  Load the light curve, report columns, flag counts and the scatter of each flag
           subset, cadence, gaps, the Lomb-Scargle stellar-variability period, and the
           recommended flatten window.
  search   Quality-filter, clip outliers against the local trend, flatten (Savitzky-Golay),
           run a broad TLS search plus a BLS cross-check at three flatten windows, and report
           the candidate with validation statistics (SDE, SNR, odd/even, per-transit depths,
           P/2 and 2P alias tests, relation to the rotation period).
  refine   Re-flatten with the candidate's transits masked, fit a limb-darkened transit model
           (batman) for P and T0, cross-check with a dense BLS grid, and write the period
           rounded to --decimals places to --write.

Light-curve format: whitespace text, '#' comments, columns time, flux, flag, flux_err
(override with --cols "t,f,q,e" zero-based indices; use -1 for a missing flag or error column).
"""
import argparse
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONWARNINGS", "ignore")

import numpy as np

MAD = 1.4826


def log(msg):
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- loading / cleaning
def load(path, cols="0,1,2,3"):
    idx = [int(c) for c in cols.split(",")]
    if len(idx) != 4:
        sys.exit("--cols needs 4 comma-separated indices: time,flux,flag,flux_err (-1 = absent)")
    data = np.genfromtxt(path, comments="#", invalid_raise=False)
    if data.ndim != 2 or data.shape[1] < 2:
        sys.exit(f"could not parse a numeric table from {path}")
    t = data[:, idx[0]]
    f = data[:, idx[1]]
    q = data[:, idx[2]] if idx[2] >= 0 else np.zeros_like(t)
    e = data[:, idx[3]] if idx[3] >= 0 else np.full_like(t, np.nan)
    order = np.argsort(t)
    return t[order], f[order], q[order], e[order]


def quality_mask(q, flag_good):
    return (q == 0) if flag_good == "zero" else (q != 0)


def basic_clean(t, f, q, e, flag_good):
    """Apply the quality flag, drop non-finite rows, repair bad errors, normalise flux to median 1."""
    good = quality_mask(q, flag_good) & np.isfinite(t) & np.isfinite(f)
    t, f, e = t[good], f[good], e[good]
    med = np.nanmedian(f)
    f = f / med
    e = e / med
    bad_e = ~np.isfinite(e) | (e <= 0)
    if bad_e.all():
        d = np.diff(f)
        e = np.full_like(f, MAD * np.median(np.abs(d - np.median(d))) / np.sqrt(2))
    elif bad_e.any():
        e[bad_e] = np.median(e[~bad_e])
    return t, f, e


def cadence(t):
    return float(np.median(np.diff(t)))


def window_cadences(window_days, t):
    n = int(round(window_days / cadence(t)))
    n = max(n, 5)
    return n if n % 2 == 1 else n + 1


def flatten(t, f, e, window_days, mask=None):
    import lightkurve as lk

    lc = lk.LightCurve(time=t, flux=f, flux_err=e)
    fl = lc.flatten(window_length=window_cadences(window_days, t), mask=mask)
    return np.asarray(fl.flux.value, float)


def clip_outliers(t, f, e, window_days, sigma_upper=3.0, sigma_lower=10.0, mask=None):
    """Clip against the local trend, not the raw flux: upper outliers (flares, cosmic rays) at
    sigma_upper; low points only when they are >sigma_lower AND isolated (their neighbours are
    not low), so multi-cadence transit dips always survive."""
    ff = flatten(t, f, e, window_days, mask=mask)
    r = ff - 1.0
    s = MAD * np.median(np.abs(r - np.median(r)))
    hi = r > sigma_upper * s
    lo = r < -sigma_lower * s
    if lo.any():
        pad = np.pad(r, 3, mode="edge")
        neigh = np.array([np.median(np.r_[pad[i:i + 3], pad[i + 4:i + 7]]) for i in range(len(r))])
        lo &= neigh > -2.0 * s
    keep = ~(hi | lo)
    return keep, int(hi.sum()), int(lo.sum())


def ls_rotation(t, f, e, pmax=None):
    from astropy.timeseries import LombScargle

    base = t.max() - t.min()
    pmax = pmax or base / 2
    freq = np.linspace(1 / pmax, 1 / (6 * cadence(t)), 200000)
    freq = freq[freq < 1 / 0.05]
    p = LombScargle(t, f, e).power(freq)
    i = int(np.argmax(p))
    amp = float(np.percentile(f, 95) - np.percentile(f, 5))
    return float(1 / freq[i]), float(p[i]), amp


def prewhiten(t, f, e, nmax, pmin=0.1):
    """Iterative sine fitting: divide out the strongest Lomb-Scargle sinusoid, repeat up to nmax
    times, stop once the fitted semi-amplitude drops below the median flux error. Removes coherent
    rotation/pulsation (and its harmonics) that a short Savitzky-Golay window cannot follow; a
    low-duty-cycle transit carries almost no power in any single sinusoid, so it survives."""
    from astropy.timeseries import LombScargle

    base = t.max() - t.min()
    freq = np.linspace(1 / (base / 2), 1 / pmin, 100000)
    g = f.copy()
    terms = []
    floor = np.median(e)
    for _ in range(nmax):
        ls = LombScargle(t, g, e)
        p = ls.power(freq)
        fr = freq[int(np.argmax(p))]
        mdl = ls.model(t, fr)
        amp = 0.5 * (mdl.max() - mdl.min())
        if amp < floor:
            break
        g = g / (mdl / np.median(mdl))
        terms.append({"period_days": round(float(1 / fr), 5), "semi_amplitude": round(float(amp), 6)})
    return g, terms


def default_window(prot):
    """Savitzky-Golay window: well under the variability period (so it follows the spots) but
    several transit durations long (so it does not eat the transit). P_rot/4 clamped to
    [0.25, 0.75] d."""
    return float(np.clip(prot / 4.0, 0.25, 0.75))


def gaps(t, factor=10):
    dt = np.diff(t)
    c = cadence(t)
    i = np.where(dt > factor * c)[0]
    return [[round(float(t[k]), 5), round(float(t[k + 1]), 5), round(float(dt[k]), 4)] for k in i]


# ---------------------------------------------------------------- search helpers
def run_tls(t, f, e, pmin, pmax, **kw):
    from transitleastsquares import transitleastsquares

    model = transitleastsquares(t, f, e)
    return model.power(period_min=pmin, period_max=pmax, show_progress_bar=False,
                       verbose=False, **kw)


def bls_search(t, f, e, pmin, pmax, durations):
    from astropy.timeseries import BoxLeastSquares

    m = BoxLeastSquares(t, f, dy=e)
    base = t.max() - t.min()
    # frequency grid fine enough that the transit phase drifts < duration/3 over the baseline
    df = min(durations) / 3 / base ** 2
    nf = int((1 / pmin - 1 / pmax) / df) + 1
    nf = min(nf, 400000)
    per = 1 / np.linspace(1 / pmax, 1 / pmin, nf)
    pg = m.power(per, durations, objective="snr")
    i = int(np.argmax(pg.power))
    return m, pg, i


def bls_stats(m, period, duration, t0):
    s = m.compute_stats(period, duration, t0)
    d, de = s["depth"]
    do, doe = s["depth_odd"]
    dv, dve = s["depth_even"]
    dh, dhe = s["depth_half"]
    return {
        "depth": float(d), "depth_err": float(de), "depth_snr": float(d / de) if de > 0 else None,
        "odd_even_sigma": float(abs(do - dv) / np.hypot(doe, dve)) if np.hypot(doe, dve) > 0 else None,
        "depth_half_period": float(dh), "depth_half_period_snr": float(dh / dhe) if dhe > 0 else None,
        "transits_with_data": int((s["per_transit_count"] > 0).sum()),
        "transits_predicted": int(len(s["transit_times"])),
    }


def per_transit(t, f, period, t0, duration):
    """Mean depth (ppm) and point count of each individual transit epoch."""
    n0 = int(np.floor((t.min() - t0) / period))
    n1 = int(np.ceil((t.max() - t0) / period))
    s = MAD * np.median(np.abs(f - np.median(f)))
    out = []
    for n in range(n0, n1 + 1):
        tc = t0 + n * period
        if tc < t.min() - duration or tc > t.max() + duration:
            continue
        inn = np.abs(t - tc) < 0.35 * duration
        k = int(inn.sum())
        dep = float((1 - np.mean(f[inn])) * 1e6) if k else None
        snr = float((1 - np.mean(f[inn])) / (s / np.sqrt(k))) if k else None
        out.append({"epoch": n, "tc": round(float(tc), 5), "n_points": k,
                    "depth_ppm": None if dep is None else round(dep, 1),
                    "snr": None if snr is None else round(snr, 1)})
    return out


def transit_mask(t, period, t0, duration):
    return np.abs(((t - t0 + 0.5 * period) % period) - 0.5 * period) < 0.5 * duration


def prepare(args):
    t, f, q, e = load(args.lc, args.cols)
    n_raw = len(t)
    t, f, e = basic_clean(t, f, q, e, args.flag_good)
    n_q = len(t)
    if n_q < 100:
        sys.exit(f"only {n_q} points survive the quality filter with --flag-good {args.flag_good}; "
                 "check the flag convention with `inspect`")
    prot, ls_pow, amp = ls_rotation(t, f, e)
    w = args.window_days or default_window(prot)
    terms = []
    if args.prewhiten > 0:
        f, terms = prewhiten(t, f, e, args.prewhiten)
    keep, nhi, nlo = clip_outliers(t, f, e, w)
    info = {"n_raw": n_raw, "n_after_quality": n_q, "n_clipped_high": nhi, "n_clipped_low": nlo,
            "n_used": int(keep.sum()), "variability_period_days": round(prot, 4),
            "variability_ls_power": round(ls_pow, 3), "variability_p5_p95_amplitude": round(amp, 5),
            "prewhitened_sinusoids": terms,
            "window_days": round(w, 4), "window_cadences": window_cadences(w, t)}
    return t[keep], f[keep], e[keep], info


# ---------------------------------------------------------------- subcommands
def cmd_inspect(args):
    t, f, q, e = load(args.lc, args.cols)
    rep = {"file": args.lc, "n_rows": int(len(t)),
           "time_range": [round(float(np.nanmin(t)), 5), round(float(np.nanmax(t)), 5)],
           "baseline_days": round(float(np.nanmax(t) - np.nanmin(t)), 4),
           "n_nonfinite_flux": int((~np.isfinite(f)).sum()),
           "n_nonfinite_or_nonpositive_err": int((~np.isfinite(e) | (e <= 0)).sum())}
    vals, cnt = np.unique(q[np.isfinite(q)], return_counts=True)
    rep["flag_values"] = {str(int(v)) if float(v).is_integer() else str(v): int(c) for v, c in zip(vals, cnt)}

    def scatter(sel):
        x = f[sel & np.isfinite(f)]
        if len(x) < 10:
            return None
        d = np.diff(x)
        return {"n": int(len(x)), "median": round(float(np.median(x)), 6),
                "point_to_point_scatter": round(float(MAD * np.median(np.abs(d - np.median(d))) / np.sqrt(2)), 7)}

    rep["flag_zero_subset"] = scatter(q == 0)
    rep["flag_nonzero_subset"] = scatter(q != 0)
    tc, fc, ec = basic_clean(t, f, q, e, args.flag_good)
    rep["cadence_minutes"] = round(cadence(tc) * 1440, 3)
    rep["gaps_gt_10_cadences"] = gaps(tc)
    rep["median_flux_err"] = round(float(np.median(ec)), 7)
    prot, pw, amp = ls_rotation(tc, fc, ec)
    rep["variability_period_days"] = round(prot, 4)
    rep["variability_ls_power"] = round(pw, 3)
    rep["variability_p5_p95_amplitude"] = round(amp, 5)
    rep["recommended_window_days"] = round(default_window(prot), 4)
    rep["recommended_period_max_days"] = round(float((tc.max() - tc.min()) / 2), 3)
    emit(rep, args.out)


def cmd_search(args):
    t, f, e, info = prepare(args)
    base = t.max() - t.min()
    pmin = args.period_min
    pmax = args.period_max or base / 2
    for spec in args.mask or []:
        P, T0, D = (float(x) for x in spec.split(","))
        m = transit_mask(t, P, T0, D)
        t, f, e = t[~m], f[~m], e[~m]
        info.setdefault("masked_signals", []).append({"period": P, "t0": T0, "duration": D,
                                                      "n_removed": int(m.sum())})
    w = info["window_days"]
    ff = flatten(t, f, e, w)
    log(f"TLS search {pmin:.3f}-{pmax:.3f} d on {len(t)} points (window {w:.3f} d) ...")
    r = run_tls(t, ff, e, pmin, pmax, use_threads=args.threads or os.cpu_count())
    P, T0, D = float(r.period), float(r.T0), float(r.duration)
    tls = {"period": round(P, 6), "period_uncertainty": round(float(r.period_uncertainty), 6),
           "t0": round(T0, 5), "duration_days": round(D, 5),
           "depth_ppm": round((1 - float(r.depth)) * 1e6, 1), "SDE": round(float(r.SDE), 2),
           "snr": round(float(r.snr), 2), "odd_even_mismatch_sigma": round(float(r.odd_even_mismatch), 2),
           "distinct_transit_count": int(r.distinct_transit_count),
           "empty_transit_count": int(r.empty_transit_count), "transit_count": int(r.transit_count)}
    # top independent TLS peaks (not harmonics of the best)
    peaks = []
    order = np.argsort(r.power)[::-1]
    for k in order:
        p = float(r.periods[k])
        if all(min(abs(p / q - round(p / q)), abs(q / p - round(q / p))) > 0.02 for q, _ in peaks):
            peaks.append((p, float(r.power[k])))
        if len(peaks) >= 5:
            break
    tls["top_independent_peaks"] = [{"period": round(p, 5), "SDE": round(s, 2)} for p, s in peaks]

    # BLS cross-check at three windows
    durations = np.array(sorted({max(0.02, 0.5 * D), 0.75 * D, D, 1.5 * D, 2.0 * D, 0.04, 0.08, 0.12, 0.2}))
    durations = durations[durations < 0.3 * pmin + 0.25]
    bls = []
    for fac in (0.6, 1.0, 1.6):
        wf = w * fac
        fb = flatten(t, f, e, wf)
        m, pg, i = bls_search(t, fb, e, pmin, pmax, durations)
        bls.append({"window_days": round(wf, 4), "period": round(float(pg.period[i]), 5),
                    "duration_days": round(float(pg.duration[i]), 4), "snr_power": round(float(pg.power[i]), 2),
                    "agrees_with_tls": bool(abs(pg.period[i] / P - 1) < 0.01)})

    # validation at the TLS candidate, on the default-window flattened curve
    from astropy.timeseries import BoxLeastSquares
    mb = BoxLeastSquares(t, ff, dy=e)
    val = {"at_P": bls_stats(mb, P, D, T0),
           "at_2P": bls_stats(mb, 2 * P, D, T0),
           "at_P_over_2": bls_stats(mb, P / 2, D, T0) if P / 2 > D * 2 else None,
           "per_transit_at_P": per_transit(t, ff, P, T0, D)}
    prot = info["variability_period_days"]
    ratio = P / prot
    val["period_over_variability_period"] = round(ratio, 4)
    near = [n for n in (0.25, 1 / 3, 0.5, 1, 2, 3, 4) if abs(ratio / n - 1) < 0.02]
    flags = []
    if tls["SDE"] < 6:
        flags.append("SDE<6: weak, may be a false positive")
    elif tls["SDE"] < 9:
        flags.append("6<=SDE<9: candidate, not a very strong detection")
    if tls["snr"] < 7:
        flags.append("SNR<7: needs extra validation")
    if tls["odd_even_mismatch_sigma"] > 3:
        flags.append("odd/even depths differ >3 sigma: true period may be 2P or an eclipsing binary")
    if near:
        flags.append(f"period is within 2% of {near} x the variability period: may be residual stellar signal")
    if tls["distinct_transit_count"] < 2:
        flags.append("fewer than 2 transits with data: period not constrained")
    if tls["empty_transit_count"] > 0:
        flags.append(f"{tls['empty_transit_count']} predicted transit(s) fall in gaps; check 2P (at_2P) is worse")
    h = val["at_P_over_2"]
    if h and h["depth"] > 0.7 * val["at_P"]["depth"] and (h["odd_even_sigma"] or 0) < 3:
        flags.append("folding at P/2 keeps the depth with consistent odd/even: true period may be P/2")
    if not all(b["agrees_with_tls"] for b in bls):
        flags.append("BLS does not agree with TLS at every window: detrending-sensitive result")
    val["flags"] = flags
    rep = {"preprocessing": info, "period_range": [round(pmin, 4), round(pmax, 4)], "tls": tls,
           "bls_crosscheck": bls, "validation": val,
           "candidate": {"period": round(P, 6), "t0": round(T0, 5), "duration_days": round(D, 5)}}
    emit(rep, args.out)


def cmd_refine(args):
    t, f, e, info = prepare(args)
    cand = {}
    if args.search:
        cand = json.load(open(args.search))["candidate"]
    P0 = args.period or cand.get("period")
    T00 = args.t0 or cand.get("t0")
    D0 = args.duration or cand.get("duration_days")
    if not (P0 and T00 and D0):
        sys.exit("refine needs --search search.json or all of --period --t0 --duration")
    # 1. re-detrend with the transits masked so the filter cannot shallow/shift them,
    #    and re-clip outliers with the transits protected
    w = info["window_days"]
    msk = transit_mask(t, P0, T00, 3 * D0)
    keep, _, _ = clip_outliers(t, f, e, w, mask=msk)
    keep |= msk
    t, f, e = t[keep], f[keep], e[keep]
    msk = transit_mask(t, P0, T00, 3 * D0)
    ff = flatten(t, f, e, w, mask=msk)

    # 2. batman fit over windows around each transit (falls back to dense BLS on any failure)
    half = max(0.3, 3 * D0)
    sel = np.abs(((t - T00 + 0.5 * P0) % P0) - 0.5 * P0) < half
    ts, fs, es = t[sel], ff[sel], e[sel]
    # put T0 near the middle of the data to decorrelate P and T0
    nmid = int(round((np.median(ts) - T00) / P0)) if len(ts) else 0
    Tm = T00 + nmid * P0
    dP = max(0.02 * P0, 3 * D0 / max(abs(nmid), 1))
    fit = {"success": False}
    try:
        import batman
        from scipy.optimize import least_squares

        pr = batman.TransitParams()
        pr.t0, pr.per, pr.rp, pr.a, pr.inc = Tm, P0, 0.05, 15.0, 89.0
        pr.ecc, pr.w, pr.u, pr.limb_dark = 0.0, 90.0, [0.4, 0.2], "quadratic"
        cad = cadence(t)
        bm = batman.TransitModel(pr, ts, supersample_factor=3 if cad > 0.0035 else 1, exp_time=cad)
        depth0 = max(1 - np.median(ff[transit_mask(t, P0, T00, 0.5 * D0)]), 1e-4)
        a0 = max(2.5, P0 / (np.pi * D0))

        def model(x):
            pr.t0, pr.per, pr.rp, pr.a, b = x
            pr.inc = float(np.degrees(np.arccos(min(abs(b), 0.999) / pr.a)))
            return bm.light_curve(pr)

        def resid(x):
            return (model(x) - fs) / es

        x0 = [Tm, P0, float(np.sqrt(depth0)), a0, 0.3]
        lo = [Tm - D0, P0 - dP, 0.003, 1.5, 0.0]
        hi = [Tm + D0, P0 + dP, 0.5, 300.0, 1.0]
        x0 = list(np.clip(x0, np.array(lo) + 1e-9, np.array(hi) - 1e-9))
        r = least_squares(resid, x0, bounds=(lo, hi), x_scale=[1e-3, 1e-4, 1e-2, 1.0, 0.1])
        dof = max(len(fs) - 5, 1)
        chi2r = float(np.sum(r.fun ** 2) / dof)
        cov = np.linalg.pinv(r.jac.T @ r.jac) * chi2r
        err = np.sqrt(np.clip(np.diag(cov), 0, None))
        at_bound = bool(abs(r.x[1] - lo[1]) < 1e-6 or abs(r.x[1] - hi[1]) < 1e-6)
        fit = {"success": bool(r.success) and not at_bound and bool(np.isfinite(err[1])) and err[1] > 0,
               "period": float(r.x[1]), "period_err": float(err[1]), "t0": float(r.x[0]),
               "t0_err": float(err[0]), "rp_rs": float(r.x[2]), "a_rs": float(r.x[3]),
               "b": float(r.x[4]), "depth_ppm": float((1 - model(r.x).min()) * 1e6),
               "chi2_reduced": chi2r, "period_at_bound": at_bound}
    except Exception as exc:  # noqa: BLE001
        fit["error"] = repr(exc)

    # 3. dense BLS cross-check around P0
    from astropy.timeseries import BoxLeastSquares

    mb = BoxLeastSquares(t, ff, dy=e)
    per = np.linspace(P0 - dP, P0 + dP, 40001)
    durs = np.unique(np.clip(D0 * np.array([0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0]), 0.01, None))
    pg = mb.power(per, durs, objective="likelihood")
    i = int(np.argmax(pg.power))
    bls = {"period": float(pg.period[i]), "duration_days": float(pg.duration[i]),
           "t0": float(pg.transit_time[i])}

    if fit.get("success"):
        chosen, method = fit["period"], "batman_fit"
        tol = max(5 * fit["period_err"], 0.002 * P0)
        agree = bool(abs(fit["period"] - bls["period"]) < tol)
        t0c, dc = fit["t0"], bls["duration_days"]
    else:
        chosen, method, agree = bls["period"], "dense_bls (model fit failed)", None
        t0c, dc = bls["t0"], bls["duration_days"]

    # 4. reliability gate at the chosen ephemeris
    st = bls_stats(mb, chosen, dc, t0c)
    reasons = []
    if agree is False:
        reasons.append("model fit and dense BLS disagree")
    if not st["depth_snr"] or st["depth_snr"] < 7:
        reasons.append(f"depth SNR {st['depth_snr'] and round(st['depth_snr'], 1)} < 7")
    if st["transits_with_data"] < 2:
        reasons.append("fewer than 2 transits with data")
    if fit.get("success") and fit["chi2_reduced"] > 5:
        reasons.append(f"reduced chi2 {fit['chi2_reduced']:.1f} > 5: detrending/flag problem")
    rep = {"preprocessing": info, "start": {"period": P0, "t0": T00, "duration_days": D0},
           "model_fit": {k: (round(v, 7) if isinstance(v, float) else v) for k, v in fit.items()},
           "dense_bls": {k: round(v, 7) for k, v in bls.items()},
           "fit_and_bls_agree": agree, "method": method,
           "check_at_chosen": {k: (round(v, 7) if isinstance(v, float) else v) for k, v in st.items()},
           "reliable": not reasons, "unreliable_reasons": reasons,
           "period": round(chosen, 7), "period_rounded": f"{chosen:.{args.decimals}f}"}
    if args.write:
        with open(args.write, "w") as fh:
            fh.write(f"{chosen:.{args.decimals}f}\n")
        rep["written_to"] = args.write
    emit(rep, args.out)


def emit(rep, out):
    s = json.dumps(rep, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    if out:
        with open(out, "w") as fh:
            fh.write(s + "\n")
    print(s, flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--lc", required=True, help="light-curve text file")
        p.add_argument("--cols", default="0,1,2,3", help="time,flux,flag,flux_err column indices")
        p.add_argument("--flag-good", choices=["zero", "nonzero"], default="zero",
                       help="which flag value marks GOOD data (default: zero = TESS convention)")
        p.add_argument("--out", help="also write the JSON report here")

    p = sub.add_parser("inspect"); common(p)
    p = sub.add_parser("search"); common(p)
    p.add_argument("--window-days", type=float, help="flatten window in days (default from variability period)")
    p.add_argument("--period-min", type=float, default=0.5)
    p.add_argument("--period-max", type=float, help="default: baseline/2 (>=2 transits)")
    p.add_argument("--mask", action="append", metavar="P,T0,DUR",
                   help="remove a known signal's transits before searching (repeatable)")
    p.add_argument("--threads", type=int)
    p.add_argument("--prewhiten", type=int, default=10,
                   help="max sinusoids removed by iterative sine fitting before flattening (0 = off)")
    p = sub.add_parser("refine"); common(p)
    p.add_argument("--search", help="search JSON (supplies the candidate)")
    p.add_argument("--period", type=float); p.add_argument("--t0", type=float)
    p.add_argument("--duration", type=float)
    p.add_argument("--window-days", type=float)
    p.add_argument("--prewhiten", type=int, default=10, help="must match the value used in search")
    p.add_argument("--decimals", type=int, default=5)
    p.add_argument("--write", help="write the rounded period (single line) to this file")
    args = ap.parse_args()
    {"inspect": cmd_inspect, "search": cmd_search, "refine": cmd_refine}[args.cmd](args)


if __name__ == "__main__":
    main()
