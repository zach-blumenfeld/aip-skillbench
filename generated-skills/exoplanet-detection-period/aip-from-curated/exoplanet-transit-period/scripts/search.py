"""search-period: broad TLS search on the flattened light curve, astropy BLS
cross-check, and the diagnostics the vetting decision needs (SDE/SNR tiers,
odd-even depths, dip at phase 0.5, power at P/2 and 2P, top peaks, empty transits).

Optional state overrides: period_min / period_max (0 = auto), bls_objective.
"""
import json
import os

import numpy as np

from common import emit, load_lc, opt, plot_safe, quiet, read_request, red_noise_beta


def tls_attr(res, *names, default=None):
    for n in names:
        v = getattr(res, n, None)
        if v is not None:
            return v
    return default


def run_tls(t, f, e, pmin, pmax, oversampling, dgs):
    from transitleastsquares import transitleastsquares
    kw = dict(show_progress_bar=False, verbose=False, oversampling_factor=oversampling,
              duration_grid_step=dgs, use_threads=os.cpu_count() or 1)
    if pmin and pmin > 0:
        kw["period_min"] = float(pmin)
    if pmax and pmax > 0:
        kw["period_max"] = float(pmax)
    with quiet() as buf:
        model = transitleastsquares(t, f, e)
        res = model.power(**kw)
    text = buf.getvalue()
    warns = [ln.strip() for ln in text.splitlines()
             if "transit" in ln.lower() and ("without data" in ln.lower() or "warning" in ln.lower())]
    return res, warns


def tls_summary(res, t, cfg_v):
    period = float(res.period)
    depth_flux = float(tls_attr(res, "depth", default=np.nan))
    sde = float(tls_attr(res, "SDE", default=np.nan))
    snr = float(tls_attr(res, "snr", default=np.nan))
    per_tr = tls_attr(res, "per_transit_count", default=None)
    transit_times = tls_attr(res, "transit_times", default=[])
    n_with_data = int(np.sum(np.asarray(per_tr) > 0)) if per_tr is not None else None
    tier = "very_strong" if sde >= cfg_v["sde_very_strong"] else ("strong" if sde >= cfg_v["sde_strong"] else "weak")
    return {
        "period": period,
        "period_uncertainty": float(tls_attr(res, "period_uncertainty", default=np.nan)),
        "T0": float(tls_attr(res, "T0", default=np.nan)),
        "duration_days": float(tls_attr(res, "duration", default=np.nan)),
        "depth_fraction": 1.0 - depth_flux if np.isfinite(depth_flux) else None,
        "SDE": sde, "snr": snr,
        "odd_even_mismatch_sigma": float(tls_attr(res, "odd_even_mismatch", default=np.nan)),
        "depth_mean_odd": _pair0(tls_attr(res, "depth_mean_odd")),
        "depth_mean_even": _pair0(tls_attr(res, "depth_mean_even")),
        "transit_count": int(tls_attr(res, "transit_count", default=0) or 0),
        "distinct_transit_count": int(tls_attr(res, "distinct_transit_count", default=0) or 0),
        "empty_transit_count": int(tls_attr(res, "empty_transit_count", default=0) or 0),
        "transits_with_data": n_with_data,
        "transit_times": [float(x) for x in list(transit_times)[:60]],
        "sde_tier": tier,
        "snr_reliable": bool(snr > cfg_v["snr_reliable"]),
    }


def _pair0(v):
    if v is None:
        return None
    try:
        return float(np.asarray(v).ravel()[0])
    except Exception:
        return None


def power_near(periods, power, p, tol):
    if periods is None or len(periods) == 0:
        return None
    periods = np.asarray(periods)
    m = np.abs(periods - p) <= tol * p
    if not m.any():
        return None
    return float(np.nanmax(np.asarray(power)[m]))


def top_peaks(periods, power, n, tol, best):
    periods, power = np.asarray(periods), np.asarray(power)
    order = np.argsort(power)[::-1]
    picked = []
    for i in order:
        p = periods[i]
        if any(abs(p - q) <= 2 * tol * q for q, _ in picked):
            continue
        picked.append((p, power[i]))
        if len(picked) >= n:
            break
    out = []
    for p, s in picked:
        r = p / best
        rel = None
        for name, val in (("P", 1), ("2P", 2), ("P/2", 0.5), ("3P", 3), ("P/3", 1 / 3), ("3P/2", 1.5), ("2P/3", 2 / 3)):
            if abs(r - val) <= tol * val * 2:
                rel = name
                break
        out.append({"period": float(p), "SDE": float(s), "relation_to_best": rel})
    return out


def phase_dip(t, f, e, period, t0, dur, phase_center, beta=1.0):
    """Weighted mean depth (1 - flux) in a window of width dur at the given phase,
    against the out-of-window median; returns depth and its significance."""
    ph = ((t - t0) / period - phase_center + 0.5) % 1.0 - 0.5
    w = np.abs(ph * period) < 0.5 * dur
    if w.sum() < 3:
        return {"depth": None, "sigma": None, "n_points": int(w.sum())}
    base = np.median(f[~w]) if (~w).sum() > 10 else 1.0
    wt = 1.0 / e[w] ** 2
    d = base - np.sum(f[w] * wt) / np.sum(wt)
    err = beta / np.sqrt(np.sum(wt))
    return {"depth": float(d), "sigma": float(d / err), "n_points": int(w.sum())}


def odd_even(t, f, e, period, t0, dur, beta=None):
    """Odd vs even transit depths from per-transit depths (transits with >=50% of the
    expected in-transit cadences). Each parity's error is the larger of the
    red-noise-inflated white error and the empirical per-transit scatter / sqrt(n),
    so detrending residuals do not masquerade as an odd-even mismatch."""
    if beta is None:
        from transitleastsquares import transit_mask
        beta = red_noise_beta(t, f, e, dur, exclude=transit_mask(t, period, 2 * dur, t0))
    n = np.round((t - t0) / period).astype(int)
    w = np.abs((t - t0) - n * period) < 0.5 * dur
    base = np.median(f[~w])
    cad = np.median(np.diff(t))
    expected = max(dur / cad, 1.0)
    per = []
    for k in np.unique(n[w]):
        m = w & (n == k)
        if m.sum() < max(2, 0.5 * expected):
            continue
        wt = 1.0 / e[m] ** 2
        per.append((int(k), float(base - np.sum(f[m] * wt) / np.sum(wt)), float(beta / np.sqrt(np.sum(wt)))))
    out = {"per_transit_depths": [{"epoch": k, "depth": d, "err": s} for k, d, s in per],
           "red_noise_beta": beta, "depth_odd": None, "depth_even": None, "mismatch_sigma": None}
    if len(per) < 2:
        return out
    depths = np.array([d for _, d, _ in per])
    scatter = float(np.std(depths, ddof=1)) if len(per) >= 3 else 0.0
    out["per_transit_scatter"] = scatter
    res = {}
    for name, par in (("odd", 1), ("even", 0)):
        sel = [(d, s) for k, d, s in per if (k % 2) == par]
        if not sel:
            return out
        d = np.array([x[0] for x in sel]); s_ = np.array([x[1] for x in sel])
        wt = 1.0 / s_ ** 2
        mean = float(np.sum(d * wt) / np.sum(wt))
        err = max(float(1.0 / np.sqrt(np.sum(wt))), scatter / np.sqrt(len(sel)))
        res[name] = (mean, err)
    (d1, s1), (d2, s2) = res["odd"], res["even"]
    out.update(depth_odd=d1, depth_even=d2, mismatch_sigma=float(abs(d1 - d2) / np.hypot(s1, s2)))
    return out


def run_bls(t, f, e, pmin, pmax, durations, objective):
    from astropy.timeseries import BoxLeastSquares
    durations = np.array([d for d in durations if d < 0.5 * pmin]) if pmin else np.array(durations)
    if durations.size == 0:
        durations = np.array([0.25 * pmin])
    bls = BoxLeastSquares(t, f, dy=e)
    pg = bls.autopower(durations, minimum_period=pmin, maximum_period=pmax, objective=objective,
                       frequency_factor=1.0)
    i = int(np.argmax(pg.power))
    P, D, T0 = float(pg.period[i]), float(pg.duration[i]), float(pg.transit_time[i])
    st = bls.compute_stats(P, D, T0)
    depth_err = float(np.asarray(st["depth"]).ravel()[1])
    d_odd = np.asarray(st["depth_odd"]).ravel()
    d_even = np.asarray(st["depth_even"]).ravel()
    return {
        "period": P, "duration_days": D, "T0": T0, "power": float(pg.power[i]),
        "depth": float(np.asarray(st["depth"]).ravel()[0]), "depth_err": depth_err,
        # astropy's compute_stats has no 'depth_snr' key: SNR = depth / depth_err
        "depth_snr": float(np.asarray(st["depth"]).ravel()[0]) / depth_err if depth_err > 0 else None,
        "depth_at_phase_0p5": float(np.asarray(st["depth_phased"]).ravel()[0]),
        "harmonic_delta_log_likelihood": float(st["harmonic_delta_log_likelihood"]),
        "depth_odd": float(d_odd[0]), "depth_even": float(d_even[0]),
        "odd_even_mismatch_sigma": float(abs(d_odd[0] - d_even[0]) / np.hypot(d_odd[1], d_even[1])),
        "transit_count": int(np.sum(np.asarray(st["per_transit_count"]) > 0)),
        "n_periods_searched": int(len(pg.period)),
    }, pg


def main():
    state, cfg = read_request()
    scfg, vcfg = cfg["search"], cfg["validation"]
    t, f, e = load_lc(state["clean_lc_path"])
    baseline = float(t[-1] - t[0])
    pmin = float(opt(state, "period_min", 0) or 0)
    pmax = float(opt(state, "period_max", 0) or 0)
    if pmax <= 0:
        pmax_eff = baseline / 2.0  # at least two transits
    else:
        pmax_eff = pmax
    if pmin > 0 and pmax_eff <= pmin:
        pmax_eff = pmin * 2

    res, warns = run_tls(t, f, e, pmin, pmax_eff, scfg["tls_oversampling_factor"], scfg["tls_duration_grid_step"])
    tls = tls_summary(res, t, vcfg)
    P, T0, D = tls["period"], tls["T0"], tls["duration_days"]
    periods, power = tls_attr(res, "periods"), tls_attr(res, "power")
    tol = scfg["harmonic_tolerance"]

    from transitleastsquares import transit_mask
    beta = red_noise_beta(t, f, e, D, exclude=transit_mask(t, P, 2 * D, T0))
    alias = {
        "red_noise_beta": beta,
        "sde_at_half_period": power_near(periods, power, P / 2, tol),
        "sde_at_double_period": power_near(periods, power, 2 * P, tol),
        "dip_at_phase_0": phase_dip(t, f, e, P, T0, D, 0.0, beta),
        "dip_at_phase_0p5": phase_dip(t, f, e, P, T0, D, 0.5, beta),
        "odd_even": odd_even(t, f, e, P, T0, D, beta),
        "tls_warnings": warns,
        "searched_period_min": float(np.min(periods)) if periods is not None else pmin,
        "searched_period_max": float(np.max(periods)) if periods is not None else pmax_eff,
    }
    d0, dh = alias["dip_at_phase_0"]["depth"], alias["dip_at_phase_0p5"]["depth"]
    alias["phase_0p5_to_phase_0_depth_ratio"] = (dh / d0) if (d0 and dh is not None and d0 != 0) else None
    peaks = top_peaks(periods, power, scfg["n_top_peaks"], tol, P) if periods is not None else []

    bmin = pmin if pmin > 0 else max(alias["searched_period_min"], 0.3)
    try:
        bls, _ = run_bls(t, f, e, bmin, pmax_eff, scfg["bls_durations_days"],
                         opt(state, "bls_objective", scfg["bls_objective"]))
        r = bls["period"] / P
        rel = None
        for name, val in (("same", 1.0), ("2x", 2.0), ("0.5x", 0.5), ("3x", 3.0), ("1/3x", 1 / 3)):
            if abs(r - val) <= tol * val:
                rel = name
        bls["relation_to_tls"] = rel or "unrelated"
    except Exception as ex:
        bls = {"error": str(ex)}

    vet_flags = []
    if tls["sde_tier"] == "weak":
        vet_flags.append(f"SDE {tls['SDE']:.2f} < {vcfg['sde_strong']}: weak, may be a false positive")
    if not tls["snr_reliable"]:
        vet_flags.append(f"SNR {tls['snr']:.2f} <= {vcfg['snr_reliable']}: needs extra validation")
    oe = alias["odd_even"]["mismatch_sigma"]
    if oe is not None and oe > vcfg["odd_even_sigma"]:
        vet_flags.append(f"odd-even depth mismatch {oe:.1f} sigma (red-noise inflated): eclipsing binary or true period 2P")
    if tls["transits_with_data"] is not None and tls["transits_with_data"] < vcfg["min_transits_with_data"]:
        vet_flags.append("fewer than 2 transits with data")
    if tls["empty_transit_count"]:
        both = alias["odd_even"]["depth_odd"] is not None and alias["odd_even"]["depth_even"] is not None
        vet_flags.append(f"{tls['empty_transit_count']} transit epochs fall in gaps: true period may be 2P"
                         + (" (but odd and even epochs both have data; compare their depths)" if both else
                            " (only one parity has data: 2P cannot be excluded)"))
    sh = alias["dip_at_phase_0p5"]["sigma"]
    if sh is not None and sh > 3 and alias["phase_0p5_to_phase_0_depth_ratio"] and alias["phase_0p5_to_phase_0_depth_ratio"] > 0.5:
        vet_flags.append(f"dip at phase 0.5 ({sh:.1f} sigma, depth ratio {alias['phase_0p5_to_phase_0_depth_ratio']:.2f}): true period may be P/2, or a secondary eclipse")
    # "reasonable duration for the orbit": central transit of a Sun-like star lasts
    # ~13 h * (P / 365 d)^(1/3); far longer suggests a giant host, a blend or a non-transit
    d_sun = 13.0 / 24.0 * (P / 365.25) ** (1.0 / 3.0)
    alias["duration_to_sunlike_ratio"] = D / d_sun if d_sun > 0 else None
    if d_sun > 0 and D > vcfg["max_duration_ratio"] * d_sun:
        vet_flags.append(f"duration {D*24:.1f} h is {D/d_sun:.1f}x a Sun-like central transit at this period: "
                         "check for a giant host, an eclipsing binary or a non-transit dip")
    prep = state.get("prep_summary")
    if not prep:
        ps = os.path.join(os.path.dirname(state["clean_lc_path"]), "prep_summary.json")
        if os.path.exists(ps):
            with open(ps) as fh:
                prep = json.load(fh)
    var = (prep or {}).get("variability") or {}
    prot = var.get("dominant_period_days")
    if prot and var.get("strong") and not (var.get("transit_like_shape") or {}).get("transit_like"):
        for k in (0.5, 1, 2, 3):
            if abs(P - k * prot) <= 0.02 * k * prot:
                vet_flags.append(f"candidate period matches {k} x the stellar variability period ({prot:.4f} d): "
                                 "likely residual rotation/pulsation, not a transit")
                break
    if isinstance(bls, dict) and bls.get("relation_to_tls") not in (None, "same"):
        vet_flags.append(f"BLS best period relation to TLS: {bls.get('relation_to_tls')}")

    wd = state.get("work_dir") or os.path.dirname(state["clean_lc_path"])

    def _plot():
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 2, figsize=(13, 8))
        ax[0, 0].plot(periods, power, "-k", lw=0.6)
        ax[0, 0].axvline(P, color="r", alpha=0.4)
        ax[0, 0].set_xlabel("period [d]"); ax[0, 0].set_ylabel("TLS SDE")
        for a, per, lab in ((ax[0, 1], P, "P"), (ax[1, 0], 2 * P, "2P (odd/even)"), (ax[1, 1], P / 2, "P/2")):
            ph = ((t - T0) / per + 0.25) % 1.0 - 0.25
            a.plot(ph, f, ",k", alpha=0.5)
            nb = 200
            bins = np.linspace(-0.25, 0.75, nb + 1)
            idx = np.digitize(ph, bins)
            bm = [np.median(f[idx == k]) if np.any(idx == k) else np.nan for k in range(1, nb + 1)]
            a.plot(0.5 * (bins[1:] + bins[:-1]), bm, "-r", lw=1)
            a.set_title(f"fold at {lab} = {per:.5f} d"); a.set_xlabel("phase")
            lo = 1 - 3 * max(tls["depth_fraction"] or 0.001, 0.001)
            a.set_ylim(lo, 1 + 1.5 * max(tls["depth_fraction"] or 0.001, 0.001))
        p = os.path.join(wd, "search.png")
        fig.tight_layout(); fig.savefig(p, dpi=90); plt.close(fig)
        return p

    plot = plot_safe(_plot)
    tls["note"] = ("depth/duration here come from the unmasked flatten and are usually underestimated; "
                   "refine-period re-flattens with the transits masked")
    summary = {"tls": tls, "alias_checks": alias, "top_peaks": peaks, "bls": bls,
               "vet_flags": vet_flags, "baseline_days": baseline}
    emit({"candidate_period": P, "search_summary": summary,
          "plots": list(state.get("plots") or []) + ([plot] if isinstance(plot, str) and plot.endswith(".png") else [])})


if __name__ == "__main__":
    main()
