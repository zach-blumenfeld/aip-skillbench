"""Step detrend-and-search: quality filter, flatten stellar variability, BLS transit search.

stdin state: lc_path, flag_convention, data_summary, period_min, period_max
stdout: {"candidates": [...], "search_summary": {...}}

Run by hand (e.g. from the weak-signal fallback) with extra state keys to override:
  window_days (float), min_duration / max_duration (days).
"""
import numpy as np

from lcio import (bin_lc, cadence_days, choose_window_days, duration_grid, emit, fail,
                  flatten, load_clean, read_payload, robust_p2p)

N_CANDIDATES = 5
DISTINCT_FRAC = 0.02          # peaks within 2% of a kept peak are the same peak
ROT_HARMONIC_TOL = 0.03       # P/P_rot within 3% of n or 1/n flags a rotation harmonic
SEARCH_BIN_DAYS = 10.0 / 1440 # broad search runs on 10-min bins (transits >= 43 min stay resolved)


def bls_search(t, f, e, durations, pmin, pmax):
    """Broad BLS on binned data; returns (BLS on the unbinned data for stats, periodogram)."""
    from astropy.timeseries import BoxLeastSquares
    if cadence_days(t) < 0.8 * SEARCH_BIN_DAYS:
        bt, bf, be = bin_lc(t, f, e, SEARCH_BIN_DAYS)
    else:
        bt, bf, be = t, f, e
    coarse = BoxLeastSquares(bt, bf, dy=be)
    periods = coarse.autoperiod(durations, minimum_period=pmin, maximum_period=pmax,
                                frequency_factor=1.0)
    pg = coarse.power(periods, durations, objective="likelihood", oversample=5)
    return BoxLeastSquares(t, f, dy=e), pg


def sde(power):
    p = np.asarray(power, float)
    s = np.std(p)
    return (p - np.mean(p)) / s if s > 0 else np.zeros_like(p)


def ratio_flag(p, prot):
    if not prot:
        return None
    for n in range(1, 6):
        if abs(p / prot - n) / n < ROT_HARMONIC_TOL:
            return f"P = {n} x P_rot"
        if abs(prot / p - n) / n < ROT_HARMONIC_TOL:
            return f"P = P_rot / {n}"
    return None


def local_refine(bls, P, D, base):
    """Polish a coarse peak on the unbinned data so odd/even and phase-0.5 stats are not
    smeared by period error accumulated over many transits."""
    half_width = max(3 * D / base * P, 1e-4 * P)       # ~3 transit durations of drift
    periods = np.linspace(P - half_width, P + half_width, 201)
    durs = np.unique(np.clip(D * np.array([0.6, 0.75, 0.9, 1.0, 1.15, 1.3, 1.5]), 0.01,
                            min(0.3, 0.9 * periods[0])))
    pg = bls.power(periods, durs, objective="likelihood")
    j = int(np.argmax(pg.power))
    return float(pg.period[j]), float(pg.duration[j]), float(pg.transit_time[j])


def describe(bls, pg, i, sde_arr, prot, rank, base, top_period=None):
    P, D, T0 = local_refine(bls, float(pg.period[i]), float(pg.duration[i]), base)
    st = bls.compute_stats(P, D, T0)
    depth, derr = float(st["depth"][0]), float(st["depth"][1])
    do, doe = float(st["depth_odd"][0]), float(st["depth_odd"][1])
    de, dee = float(st["depth_even"][0]), float(st["depth_even"][1])
    dh = float(st["depth_half"][0])
    dp, dpe = float(st["depth_phased"][0]), float(st["depth_phased"][1])
    counts = np.asarray(st["per_transit_count"])
    oe_err = np.hypot(doe, dee)
    c = {
        "rank": rank,
        "period": P,
        "duration_days": D,
        "t0": T0,
        "depth": depth,
        "depth_err": derr,
        "depth_snr": depth / derr if derr > 0 else None,
        "bls_power": float(pg.power[i]),
        "sde": float(sde_arr[i]),
        "n_transits_with_data": int(np.sum(counts > 0)),
        "n_transit_epochs_in_baseline": int(len(counts)),
        "points_per_transit": [int(x) for x in counts],
        "depth_odd": do,
        "depth_even": de,
        "odd_even_mismatch_sigma": abs(do - de) / oe_err if oe_err > 0 else None,
        "odd_even_depth_ratio": (min(do, de) / max(do, de)) if max(do, de) > 0 else None,
        "secondary_depth_at_phase_0p5": dp,
        "secondary_snr": dp / dpe if dpe > 0 else None,
        "depth_when_folded_at_half_period_over_depth": dh / depth if depth > 0 else None,
        "duration_over_period": D / P,
        "rotation_relation": ratio_flag(P, prot),
    }
    if top_period:
        c["period_over_top_period"] = P / top_period
    return c


def main():
    state = read_payload()
    for k in ("lc_path", "flag_convention", "data_summary"):
        if k not in state:
            fail(f"state.{k} is required")
    summ = state["data_summary"] or {}
    d = load_clean(state["lc_path"], state["flag_convention"])
    t, f, e = d["time"], d["flux"], d["flux_err"]
    base = float(t.max() - t.min())
    cad = cadence_days(t)

    var = summ.get("stellar_variability") or {}
    prot = var.get("period_days")
    window = float(state.get("window_days") or choose_window_days(prot, var.get("significant")))

    pmin = float(state.get("period_min") or 0) or 0.5
    pmax = float(state.get("period_max") or 0) or base / 2.0   # >= 2 transits in the baseline
    pmax = min(pmax, base)
    if pmin >= pmax:
        fail(f"period range empty: period_min={pmin} >= period_max={pmax} (baseline {base:.2f} d)")

    durations = duration_grid(window, cad)
    if state.get("min_duration") or state.get("max_duration"):
        lo = float(state.get("min_duration") or durations[0])
        hi = float(state.get("max_duration") or durations[-1])
        durations = np.geomspace(lo, hi, 6)
    durations = durations[durations < pmin]  # BLS requires duration < period
    if durations.size == 0:
        fail("all trial durations exceed period_min; lower min_duration or raise period_min")

    ft, ff, fe, nclip = flatten(t, f, e, window)
    bls, pg = bls_search(ft, ff, fe, durations, pmin, pmax)
    s = sde(pg.power)

    order = np.argsort(np.asarray(pg.power))[::-1]
    kept = []
    for i in order:
        P = pg.period[i]
        if pg.depth[i] <= 0:
            continue
        if all(abs(P / pg.period[j] - 1) > DISTINCT_FRAC for j in kept):
            kept.append(i)
        if len(kept) == N_CANDIDATES:
            break
    if not kept:
        fail("BLS found no dip-shaped signal at any trial period")
    top_P = float(pg.period[kept[0]])
    cands = [describe(bls, pg, i, s, prot, r + 1, base, top_P) for r, i in enumerate(kept)]

    # Robustness: does the top period survive a shorter and a longer flatten window?
    robust = []
    for fac in (0.6, 1.5):
        w2 = float(np.clip(window * fac, 0.15, 1.2))
        t2, f2, e2, _ = flatten(t, f, e, w2)
        dur2 = duration_grid(w2, cad)
        dur2 = dur2[dur2 < pmin]
        if dur2.size == 0:
            continue
        _, pg2 = bls_search(t2, f2, e2, dur2, pmin, pmax)
        j = int(np.argmax(pg2.power))
        P2 = float(pg2.period[j])
        robust.append({"window_days": w2, "top_period": P2,
                       "top_duration_days": float(pg2.duration[j]),
                       "agrees_with_top_within_1pct": abs(P2 / top_P - 1) < 0.01,
                       "ratio_to_top": P2 / top_P})

    search_summary = {
        "flag_convention": state["flag_convention"],
        "n_rows_in_file": d["n_rows"],
        "n_removed_by_flag": d["n_flag_removed"],
        "n_removed_nonfinite": d["n_nonfinite_removed"],
        "n_upward_outliers_clipped": nclip,
        "n_points_searched": int(len(ft)),
        "flux_err_source": d["flux_err_source"],
        "baseline_days": base,
        "rotation_period_days": prot,
        "rotation_significant": var.get("significant"),
        "flatten_window_days": window,
        "flatten_method": "lightkurve flatten (Savitzky-Golay, polyorder 2, split at gaps) then 3-sigma upward clip",
        "bls_search_bin_minutes": SEARCH_BIN_DAYS * 1440 if cadence_days(t) < 0.8 * SEARCH_BIN_DAYS else None,
        "residual_p2p_scatter": robust_p2p(ff),
        "residual_std": float(np.std(ff)),
        "period_min": pmin,
        "period_max": pmax,
        "durations_days": [float(x) for x in durations],
        "n_trial_periods": int(len(pg.period)),
        "robustness": robust,
    }
    emit({"candidates": cands, "search_summary": search_summary})


if __name__ == "__main__":
    main()
