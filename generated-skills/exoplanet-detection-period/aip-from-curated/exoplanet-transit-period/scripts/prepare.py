"""prepare-light-curve: load -> quality flags -> outliers (pass 1) -> stellar
variability diagnosis -> [sine prewhitening] -> flatten -> outliers (pass 2).

Order matters (source: light-curve-preprocessing): quality flags first, outliers
before flattening (they bias the trend), flatten, then a second gentler pass.
Optional state overrides: run_tag (separate output folder), quality_convention ('auto'|'flag0_good'|'flag0_bad'|'ignore'),
flatten_window_days, pass1_sigma_upper, pass2_sigma_upper, prewhiten ('auto'|'on'|'off').
"""
import json
import os

import numpy as np

from common import (emit, fail, load_lightcurve, opt, plot_safe, ptp_sigma,
                    quiet, read_request, save_lc, work_dir)


def choose_quality(flag, flux, cfg, override):
    """Return (mask_of_good, convention_used, diagnostics)."""
    n = flux.size
    diag = {}
    if flag is None:
        return np.ones(n, bool), "no_flag_column", diag
    flag = np.nan_to_num(flag, nan=-1)
    z = flag == 0
    diag = {"n_flag0": int(z.sum()), "n_flag_nonzero": int((~z).sum()),
            "flag_values": {str(int(v)): int(c) for v, c in zip(*np.unique(flag, return_counts=True))}}
    if override == "ignore":
        return np.ones(n, bool), "ignore", diag
    if override == "flag0_good":
        return z, "flag0_good", diag
    if override == "flag0_bad":
        return ~z, "flag0_bad", diag
    if z.all():
        return z, "flag0_good (all flags are 0)", diag
    if not z.any():
        return np.ones(n, bool), "all flags nonzero: kept all (flag likely not a quality mask)", diag
    # "Check which approach gives cleaner results": compare white-noise scatter.
    s0, s1 = ptp_sigma(flux[z]), ptp_sigma(flux[~z])
    diag.update(scatter_flag0=s0, scatter_flag_nonzero=s1)
    frac1 = (~z).mean()
    if s1 < cfg["cleaner_scatter_ratio"] * s0 and frac1 >= cfg["min_subset_fraction"]:
        return ~z, "flag0_bad (flag!=0 subset is clearly cleaner)", diag
    return z, "flag0_good (standard TESS)", diag


def clip_upper(flux, sigma, iters=5):
    """Iterative median/std clip of upward outliers only (lightkurve remove_outliers semantics)."""
    keep = np.isfinite(flux)
    for _ in range(iters):
        med, std = np.median(flux[keep]), np.std(flux[keep])
        new = keep & (flux - med < sigma * std)
        if new.sum() == keep.sum():
            break
        keep = new
    return keep


def isolated_low_glitches(flux, sigma_low, sigma_nb):
    """Single-cadence negative glitches: far below and both neighbours normal.
    A transit spans many consecutive cadences, so it is never flagged."""
    med = np.median(flux)
    s = ptp_sigma(flux)
    dev = (flux - med) / s
    bad = dev < -sigma_low
    nb_ok = np.ones_like(bad)
    nb_ok[1:-1] = (np.abs(dev[:-2]) < sigma_nb) & (np.abs(dev[2:]) < sigma_nb)
    return bad & nb_ok


def ls_peak(t, f, e, pmin, pmax):
    from astropy.timeseries import LombScargle
    ls = LombScargle(t, f, e)
    freq, power = ls.autopower(minimum_frequency=1.0 / pmax, maximum_frequency=1.0 / pmin,
                               samples_per_peak=10)
    i = int(np.argmax(power))
    fbest = freq[i]
    model = ls.model(t, fbest)
    amp = 0.5 * (np.max(model) - np.min(model))
    try:
        fap = float(ls.false_alarm_probability(power[i], minimum_frequency=1.0 / pmax,
                                               maximum_frequency=1.0 / pmin))
    except Exception:
        fap = None
    return {"period": float(1.0 / fbest), "power": float(power[i]), "amplitude": float(amp),
            "fap": fap}, model


def transit_like(t, f, period, max_duty, nbins=100):
    """Fold at the LS period and bin. Rotation/pulsation spends about half the cycle
    below mid-range; a transit is a flat top with a narrow dip, so the fraction of
    bins below mid-range (~ the duty cycle) is small."""
    ph = (t % period) / period
    idx = np.minimum((ph * nbins).astype(int), nbins - 1)
    b = np.array([np.median(f[idx == k]) for k in range(nbins) if np.any(idx == k)])
    mid = 0.5 * (b.max() + b.min())
    duty = float(np.mean(b < mid))
    return {"transit_like": bool(duty < max_duty), "low_bin_fraction": duty}


def odd(n):
    n = int(round(n))
    return n if n % 2 == 1 else n + 1


def main():
    state, cfg = read_request()
    lc_path = state.get("lc_path")
    if not lc_path:
        fail("state has no lc_path")
    qcfg, ocfg, dcfg = cfg["quality"], cfg["outliers"], cfg["detrend"]
    notes = []

    raw, info = load_lightcurve(lc_path)
    t, f, flag, e = raw["time"], raw["flux"], raw["flag"], raw["flux_err"]
    n_raw = t.size

    good, conv, qdiag = choose_quality(flag, f, qcfg, opt(state, "quality_convention", qcfg["convention"]))
    finite = np.isfinite(t) & np.isfinite(f)
    if e is not None:
        finite &= np.isfinite(e)
    good &= finite
    t, f = t[good], f[good]
    e = e[good] if e is not None else None
    order = np.argsort(t)
    t, f = t[order], f[order]
    e = e[order] if e is not None else None
    if t.size < 100:
        fail(f"only {t.size} usable points after quality filtering ({conv})")

    # normalise (relative flux around 1); magnitudes are not handled
    med = np.median(f)
    if med <= 0:
        fail("median flux <= 0: input looks like magnitudes or differential flux; convert to relative flux first")
    f = f / med
    if e is None or not np.all(e > 0):
        est = ptp_sigma(f)
        if e is None:
            e = np.full_like(f, est)
            notes.append("no flux_err column: using point-to-point scatter as uniform flux_err (TLS needs flux_err)")
        else:
            e = e / med
            bad = ~(e > 0)
            e[bad] = est
            notes.append(f"{int(bad.sum())} non-positive flux_err replaced by scatter estimate")
    else:
        e = e / med

    dt = np.diff(t)
    cadence = float(np.median(dt))
    baseline = float(t[-1] - t[0])
    gap_idx = np.where(dt > 10 * cadence)[0]
    gaps = [{"start": float(t[i]), "end": float(t[i + 1]), "length_days": float(dt[i])} for i in gap_idx]

    # pass 1: upward outliers only (flares, cosmic rays)
    s1 = float(opt(state, "pass1_sigma_upper", ocfg["pass1_sigma_upper"]))
    k1 = clip_upper(f, s1)
    k1 &= ~isolated_low_glitches(f, ocfg["glitch_sigma_lower"], ocfg["glitch_neighbor_sigma"])
    n_out1 = int((~k1).sum())
    t, f, e = t[k1], f[k1], e[k1]

    # stellar variability diagnosis (Lomb-Scargle)
    noise = ptp_sigma(f)
    pmax_ls = min(dcfg["ls_max_period_days"], max(baseline / 2, 1.0))
    pmin_ls = max(dcfg["ls_min_period_days"], 5 * cadence)
    peak, _ = ls_peak(t, f, e, pmin_ls, pmax_ls)
    ratio = peak["amplitude"] / noise if noise > 0 else 0.0
    strong = ratio >= dcfg["variability_amp_ratio"] and (peak["fap"] is None or peak["fap"] < dcfg["variability_fap"])
    tlike = transit_like(t, f, peak["period"], dcfg["transit_like_max_duty"])
    variability = {"dominant_period_days": peak["period"], "semi_amplitude": peak["amplitude"],
                   "amp_to_noise": ratio, "fap": peak["fap"], "strong": bool(strong),
                   "transit_like_shape": tlike}
    if strong and tlike["transit_like"]:
        # the LS peak is the transit itself (deep planet on a quiet star): never fit it away
        notes.append(f"dominant LS peak at {peak['period']:.4f} d has a narrow-dip shape: treated as the transit, not stellar variability")
        strong = False

    # flatten window: longer than a transit, shorter than the rotation period
    wdays_override = state.get("flatten_window_days")
    if wdays_override:
        wdays = float(wdays_override)
        wreason = "override"
    elif strong:
        wdays = min(dcfg["default_window_days"], dcfg["rotation_window_fraction"] * peak["period"])
        wreason = f"strong variability P~{peak['period']:.3f} d: window = min(default, {dcfg['rotation_window_fraction']} x P)"
    else:
        wdays = dcfg["default_window_days"]
        wreason = "default (no strong variability)"
    prewhiten_mode = opt(state, "prewhiten", "auto")
    # prewhitening depends on the variability, not on the window the caller picked
    rot_window = dcfg["rotation_window_fraction"] * peak["period"]
    do_sine = prewhiten_mode == "on" or (prewhiten_mode == "auto" and strong and rot_window < dcfg["min_window_days"])
    if do_sine:
        wreason += f"; sine prewhitening (mode {prewhiten_mode}): variability faster than the safe window"
    if wdays < dcfg["min_window_days"] and not wdays_override:
        wdays = dcfg["min_window_days"]
        wreason += f"; floored at {dcfg['min_window_days']} d to protect transits"

    sine_log = []
    if do_sine:
        # iterative sine fitting for variability faster than the window can follow.
        # Warning (source): this removes periodic signals; stop once peaks are weak.
        for _ in range(int(dcfg["sine_max_iterations"])):
            pk, model = ls_peak(t, f, e, pmin_ls, pmax_ls)
            if pk["amplitude"] / noise < dcfg["sine_stop_amp_ratio"]:
                break
            f = f / model
            sine_log.append({"period": pk["period"], "amplitude": pk["amplitude"]})
        notes.append(f"sine prewhitening removed {len(sine_log)} components")
        if not wdays_override:
            # the fast variability is gone: a short window would now only eat transits
            wdays = dcfg["default_window_days"]
            wreason += f"; after prewhitening reset to default {wdays} d"

    wl = odd(max(wdays / cadence, 5))
    wd = work_dir(lc_path, state.get("run_tag"))
    prefl_path = os.path.join(wd, "prefl_lc.npz")
    save_lc(prefl_path, t, f, e)  # refine re-flattens this with the transits masked
    import lightkurve as lk
    lc = lk.LightCurve(time=t, flux=f, flux_err=e)
    flat = None
    for attempt in range(4):
        try:
            with quiet():
                flat, trend = lc.flatten(window_length=wl, polyorder=dcfg["polyorder"],
                                         break_tolerance=dcfg["break_tolerance"],
                                         niters=dcfg["flatten_niters"], sigma=dcfg["flatten_sigma"],
                                         return_trend=True)
            break
        except Exception as ex:
            notes.append(f"flatten window {wl} failed ({ex}); halving")
            wl = odd(max(wl // 2, 5))
    if flat is None:
        fail("flatten failed for all window lengths")
    tf = np.asarray(flat.time.value, float)
    ff = np.asarray(flat.flux.value, float)
    ef = np.asarray(flat.flux_err.value, float)
    trend_f = np.asarray(trend.flux.value, float)
    ok = np.isfinite(ff) & np.isfinite(ef) & (ef > 0)
    tf, ff, ef, trend_f = tf[ok], ff[ok], ef[ok], trend_f[ok]
    tf_all = tf.copy()

    # pass 2 (after flattening): gentler, upward only
    s2 = float(opt(state, "pass2_sigma_upper", ocfg["pass2_sigma_upper"]))
    k2 = clip_upper(ff, s2)
    k2 &= ~isolated_low_glitches(ff, ocfg["glitch_sigma_lower"], ocfg["glitch_neighbor_sigma"])
    n_out2 = int((~k2).sum())
    tf, ff, ef = tf[k2], ff[k2], ef[k2]

    resid_peak, _ = ls_peak(tf, ff, ef, max(pmin_ls, 2 * wl * cadence), pmax_ls)
    resid_noise = ptp_sigma(ff)
    if resid_peak["amplitude"] / resid_noise > dcfg["variability_amp_ratio"]:
        notes.append(f"residual variability after flattening at P~{resid_peak['period']:.3f} d "
                     f"(amp/noise {resid_peak['amplitude']/resid_noise:.2f}); if this matches the transit period it is the transit itself")

    clean_path = os.path.join(wd, "clean_lc.npz")
    save_lc(clean_path, tf, ff, ef)

    def _plot():
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
        ax[0].plot(t, f, ",k")
        ax[0].plot(tf_all, trend_f, "-r", lw=0.8)
        ax[0].set_ylabel("flux + trend (pre-flatten)")
        ax[1].plot(tf, ff, ",k")
        ax[1].set_ylabel("flattened flux")
        ax[1].set_xlabel("time [d]")
        p = os.path.join(wd, "prepare.png")
        fig.savefig(p, dpi=90)
        plt.close(fig)
        return p

    plot = plot_safe(_plot)
    summary = {
        "lc_path": lc_path, "load": info, "n_raw": n_raw,
        "quality_convention": conv, "quality": qdiag,
        "n_after_quality": int(good.sum()), "n_outliers_pass1": n_out1, "n_outliers_pass2": n_out2,
        "n_final": int(tf.size), "cadence_days": cadence, "baseline_days": baseline, "gaps": gaps,
        "noise_ptp": float(resid_noise), "variability": variability,
        "flatten_window_cadences": wl, "flatten_window_days": wl * cadence, "window_reason": wreason,
        "sine_prewhitening": sine_log, "residual_ls_peak": resid_peak, "notes": notes,
    }
    with open(os.path.join(wd, "prep_summary.json"), "w") as fh:  # search.py reads it on by-hand runs
        json.dump(summary, fh, default=float)
    emit({"clean_lc_path": clean_path, "prefl_lc_path": prefl_path, "prep_summary": summary, "work_dir": wd,
          "plots": [plot] if isinstance(plot, str) and plot.endswith(".png") else []})


if __name__ == "__main__":
    main()
