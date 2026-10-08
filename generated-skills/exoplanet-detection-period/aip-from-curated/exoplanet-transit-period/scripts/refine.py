"""refine-period: adopt the vetted candidate (x1, x2 or x0.5), re-flatten the
pre-flatten light curve with its transits masked (so the trend cannot eat the
dips), run a narrow dense TLS (+/-window_fraction), polish period and T0 with a
bounded trapezoid least-squares fit, validate against SDE/SNR/odd-even
thresholds, and optionally mask the planet and search for another.

Optional state overrides: refine_window_fraction, search_additional_planets (bool).
"""
import os

import numpy as np

from common import emit, fail, load_lc, opt, plot_safe, ptp_sigma, quiet, read_request, save_lc
from prepare import clip_upper, isolated_low_glitches
from search import odd_even, run_tls, tls_summary

FACTORS = {"as_found": 1.0, "double": 2.0, "half": 0.5}


def reflatten(prefl_path, prep, period, t0, dur, cfg):
    import lightkurve as lk
    from transitleastsquares import transit_mask
    t, f, e = load_lc(prefl_path)
    d = cfg["detrend"]
    mask = transit_mask(t, period, 2.0 * dur, t0)
    wl = int(prep.get("flatten_window_cadences") or 361)
    lc = lk.LightCurve(time=t, flux=f, flux_err=e)
    with quiet():
        flat = lc.flatten(window_length=wl, polyorder=d["polyorder"], break_tolerance=d["break_tolerance"],
                          niters=d["flatten_niters"], sigma=d["flatten_sigma"], mask=mask)
    tf = np.asarray(flat.time.value, float)
    ff = np.asarray(flat.flux.value, float)
    ef = np.asarray(flat.flux_err.value, float)
    ok = np.isfinite(ff) & np.isfinite(ef) & (ef > 0)
    tf, ff, ef = tf[ok], ff[ok], ef[ok]
    o = cfg["outliers"]
    k = clip_upper(ff, o["pass2_sigma_upper"]) & ~isolated_low_glitches(ff, o["glitch_sigma_lower"], o["glitch_neighbor_sigma"])
    return tf[k], ff[k], ef[k], float(mask.mean())


def trapezoid(t, P, T0, depth, dur, ing):
    ph = ((t - T0 + 0.5 * P) % P) - 0.5 * P
    x = np.abs(ph)
    half = 0.5 * dur
    ti = np.clip(ing, 1e-3, 0.5) * dur
    m = np.where(x <= half - ti, 1.0, np.clip((half - x) / ti, 0.0, 1.0))
    return 1.0 - depth * m


def polish(t, f, e, P, T0, dur, depth):
    """Bounded least squares of a trapezoid; T0 moved to the epoch nearest the data
    middle so P and T0 decorrelate. Returns dict or None."""
    from scipy.optimize import least_squares
    tmid = 0.5 * (t[0] + t[-1])
    T0m = T0 + np.round((tmid - T0) / P) * P
    ph = ((t - T0m + 0.5 * P) % P) - 0.5 * P
    near = np.abs(ph) < 2.0 * dur
    if near.sum() < 20:
        return None
    tt, ff, ee = t[near], f[near], e[near]
    x0 = [P, T0m, max(depth, 1e-5), dur, 0.2]
    dP = max(0.01 * P, 5 * dur / max((t[-1] - t[0]) / P, 1))
    lo = [P - dP, T0m - 0.5 * dur, 0.0, 0.3 * dur, 0.01]
    hi = [P + dP, T0m + 0.5 * dur, 0.5, 3.0 * dur, 0.5]
    x0 = np.clip(x0, np.array(lo) + 1e-12, np.array(hi) - 1e-12)
    r = least_squares(lambda p: (ff - trapezoid(tt, *p)) / ee, x0, bounds=(lo, hi),
                      x_scale=[dur / 50, dur / 50, max(depth, 1e-4), dur / 5, 0.05])
    if not r.success:
        return None
    dof = max(tt.size - 5, 1)
    chi2 = float(np.sum(r.fun ** 2))
    try:
        cov = np.linalg.inv(r.jac.T @ r.jac) * max(chi2 / dof, 1.0)
        perr = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        perr = np.full(5, np.nan)
    chi2_0 = float(np.sum(((ff - trapezoid(tt, *x0)) / ee) ** 2))
    P1, T01, dep1, dur1, ing1 = r.x
    return {"period": float(P1), "period_err": float(perr[0]), "T0_mid": float(T01), "T0_err": float(perr[1]),
            "depth": float(dep1), "depth_err": float(perr[2]), "duration_days": float(dur1),
            "ingress_fraction": float(ing1), "chi2": chi2, "chi2_start": chi2_0, "n_points": int(tt.size),
            "at_bound": bool(np.any(np.isclose(r.x, lo)) or np.any(np.isclose(r.x, hi)))}


def main():
    state, cfg = read_request()
    rcfg, vcfg = cfg["refine"], cfg["validation"]
    choice = str(state.get("period_choice", "as_found"))
    if choice not in FACTORS:
        fail(f"period_choice must be one of {list(FACTORS)}, got {choice!r}")
    cand = float(state["candidate_period"]) * FACTORS[choice]
    s = state.get("search_summary") or {}
    tls0 = s.get("tls", {})
    t0 = tls0.get("T0")
    dur = tls0.get("duration_days") or 0.1
    notes = []

    t, f, e = load_lc(state["clean_lc_path"])
    prefl = state.get("prefl_lc_path")
    if prefl and os.path.exists(prefl) and t0 is not None:
        try:
            # mask every dip seen in the search: for 'double' the search period still marks all events
            mask_p = min(cand, float(state["candidate_period"]))
            t, f, e, mfrac = reflatten(prefl, state.get("prep_summary") or {}, mask_p, t0, dur, cfg)
            notes.append(f"re-flattened with candidate transits masked ({100*mfrac:.1f}% of cadences)")
            wd = state.get("work_dir") or os.path.dirname(state["clean_lc_path"])
            save_lc(os.path.join(wd, "refined_lc.npz"), t, f, e)
        except Exception as ex:
            notes.append(f"masked re-flatten failed ({ex}); using the unmasked flattened curve")
    else:
        notes.append("no pre-flatten curve/T0: refining on the unmasked flattened curve")

    w = float(opt(state, "refine_window_fraction", rcfg["window_fraction"]))
    res, warns = run_tls(t, f, e, cand * (1 - w), cand * (1 + w), rcfg["tls_oversampling_factor"],
                         rcfg["tls_duration_grid_step"])
    tls = tls_summary(res, t, vcfg)
    P, T0, D = tls["period"], tls["T0"], tls["duration_days"]
    if abs(P - cand) > 0.98 * w * cand:
        notes.append("refined peak sits at the edge of the refine window: candidate may be wrong; widen the window")

    final_P, final_unc, method = P, tls["period_uncertainty"], "tls_refined"
    pol = None
    if rcfg.get("polish", True):
        pol = polish(t, f, e, P, T0, D, tls["depth_fraction"] or 1e-3)
        if pol and not pol["at_bound"] and np.isfinite(pol["period_err"]) and pol["chi2"] <= pol["chi2_start"]:
            lim = rcfg["polish_max_shift_sigma"] * max(tls["period_uncertainty"] or 0, pol["period_err"])
            if abs(pol["period"] - P) <= lim:
                final_P, final_unc, method = pol["period"], pol["period_err"], "trapezoid_polish"
            else:
                notes.append("polish moved the period beyond the allowed shift; kept the TLS value")
        elif pol:
            notes.append("polish did not converge cleanly; kept the TLS value")

    oe = odd_even(t, f, e, final_P, pol["T0_mid"] if method == "trapezoid_polish" else T0, D)
    # SDE is normalised over the searched range, so a narrow refine window deflates it:
    # judge strength on the broad-search SDE at the adopted period.
    alias = s.get("alias_checks", {})
    broad_sde = {"as_found": tls0.get("SDE"), "double": alias.get("sde_at_double_period"),
                 "half": alias.get("sde_at_half_period")}[choice]
    broad_sde = float(broad_sde) if broad_sde is not None else float("nan")
    tier = ("very_strong" if broad_sde >= vcfg["sde_very_strong"] else
            "strong" if broad_sde >= vcfg["sde_strong"] else "weak" if np.isfinite(broad_sde) else "unknown")
    checks = {
        "broad_search_SDE": broad_sde, "sde_tier": tier, "refine_window_SDE": tls["SDE"],
        "snr": tls["snr"], "snr_reliable": tls["snr_reliable"],
        "odd_even_mismatch_sigma": oe["mismatch_sigma"],
        "odd_even_consistent": (oe["mismatch_sigma"] is None) or (oe["mismatch_sigma"] <= vcfg["odd_even_sigma"]),
        "transits_with_data": tls["transits_with_data"],
        "enough_transits": (tls["transits_with_data"] or 0) >= vcfg["min_transits_with_data"],
        "tls_warnings": warns,
    }
    checks["red_noise_beta"] = oe.get("red_noise_beta")
    checks["validated"] = bool(checks["sde_tier"] in ("strong", "very_strong") and checks["snr_reliable"]
                               and checks["odd_even_consistent"] and checks["enough_transits"])

    extra = None
    if bool(state.get("search_additional_planets", False)):
        from transitleastsquares import transit_mask
        m = transit_mask(t, final_P, 2.0 * D, T0)
        r2, w2 = run_tls(t[~m], f[~m], e[~m], 0, (t[-1] - t[0]) / 2, cfg["search"]["tls_oversampling_factor"],
                         cfg["search"]["tls_duration_grid_step"])
        s2 = tls_summary(r2, t[~m], vcfg)
        s2.pop("transit_times", None)
        r = s2["period"] / final_P
        harmonic = any(abs(r - k) < 0.02 * k or abs(1 / r - k) < 0.02 * k for k in (1, 2, 3, 4))
        extra = {"second_candidate": s2, "harmonic_of_first": bool(harmonic),
                 "significant": bool(s2["sde_tier"] != "weak" and not harmonic), "warnings": w2}

    wd = state.get("work_dir") or os.path.dirname(state["clean_lc_path"])

    def _plot():
        import matplotlib.pyplot as plt
        T0p = pol["T0_mid"] if method == "trapezoid_polish" else T0
        ph = ((t - T0p + 0.5 * final_P) % final_P) - 0.5 * final_P
        sel = np.abs(ph) < 3 * D
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.plot(ph[sel] * 24, f[sel], ".k", ms=1, alpha=0.4)
        if pol:
            xs = np.linspace(-3 * D, 3 * D, 600)
            ax.plot(xs * 24, trapezoid(xs + T0p, final_P, T0p, pol["depth"], pol["duration_days"], pol["ingress_fraction"]), "-r")
        ax.set_xlabel("hours from mid-transit"); ax.set_ylabel("flux")
        ax.set_title(f"P = {final_P:.6f} +/- {final_unc:.6f} d ({method})")
        p = os.path.join(wd, "refine.png")
        fig.savefig(p, dpi=90); plt.close(fig)
        return p

    plot = plot_safe(_plot)
    tls.pop("transit_times", None)
    tls.pop("sde_tier", None)  # narrow-window SDE tier is meaningless; see validation.sde_tier
    for k in ("odd_even_mismatch_sigma", "depth_mean_odd", "depth_mean_even"):
        tls.pop(k, None)  # TLS's white-noise odd-even; validation holds the red-noise-aware one
    summary = {"candidate_in": float(state["candidate_period"]), "period_choice": choice, "center": cand,
               "window": [cand * (1 - w), cand * (1 + w)], "tls_refined": tls, "polish": pol,
               "final_method": method, "validation": checks, "additional_planet_search": extra,
               "noise_ptp": ptp_sigma(f), "notes": notes}
    emit({"final_period": float(final_P), "period_uncertainty": float(final_unc), "refine_summary": summary,
          "plots": list(state.get("plots") or []) + ([plot] if isinstance(plot, str) and plot.endswith(".png") else [])})


if __name__ == "__main__":
    main()
