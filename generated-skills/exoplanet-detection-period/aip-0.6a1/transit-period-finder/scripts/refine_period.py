"""Step refine-and-write: sharpen the chosen period and write it to the output file.

stdin state: lc_path, flag_convention, search_summary, candidates, candidate_rank,
             alias_factor, output_path
stdout: {"period_days": float, "period_text": str, "refine_summary": {...}}

1. Mask the candidate's transits and re-flatten, so the detrending no longer eats the dips.
2. Fine BLS grid (+-1% of the starting period, dense durations).
3. Least-squares trapezoid fit of all in-transit windows (P, T0, depth, T14, ingress),
   plus a linear ephemeris fit to the individual transit times as a cross-check.
4. Write the period rounded to 5 decimals.
"""
import os

import numpy as np

from lcio import emit, fail, flatten, load_clean, read_payload

ALIAS_FACTOR = {"as_found": 1.0, "double": 2.0, "half": 0.5}


def trapezoid(t, P, T0, depth, T14, T12):
    T14 = abs(T14)
    T12 = float(np.clip(abs(T12), 1e-4, T14 / 2.0))
    ph = np.abs((t - T0 + 0.5 * P) % P - 0.5 * P)
    m = np.ones_like(t)
    full = ph <= T14 / 2.0 - T12
    ing = (ph > T14 / 2.0 - T12) & (ph < T14 / 2.0)
    m[full] = 1.0 - depth
    m[ing] = 1.0 - depth * (T14 / 2.0 - ph[ing]) / T12
    return m


def fit_trapezoid(t, f, e, P, T0, depth, dur):
    from scipy.optimize import least_squares
    p0 = [P, T0, max(depth, 1e-5), dur, dur / 5.0]
    res = least_squares(lambda p: (f - trapezoid(t, *p)) / e, p0,
                        x_scale=[1e-3, 1e-3, max(depth, 1e-5) / 10, dur / 10, dur / 50])
    dof = max(len(f) - 5, 1)
    chi2r = float(np.sum(res.fun ** 2) / dof)
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * max(chi2r, 1.0)
        perr = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        perr = np.full(5, np.nan)
    return res, perr, chi2r


def transit_timing(t, f, e, P, T0, depth, T14, T12):
    """Fit each transit's mid-time and depth with the global shape fixed; linear fit gives P."""
    from scipy.optimize import least_squares
    n = np.round((t - T0) / P)
    rows = []
    for k in np.unique(n):
        s = (n == k) & (np.abs(t - (T0 + k * P)) < 1.5 * T14)
        if s.sum() < 10:
            continue
        r = least_squares(lambda p: (f[s] - trapezoid(t[s], 1e6, p[0], p[1], T14, T12)) / e[s],
                          [T0 + k * P, depth], x_scale=[1e-3, depth / 10])
        cov = np.linalg.pinv(r.jac.T @ r.jac)
        rows.append((int(k), float(r.x[0]), float(np.sqrt(cov[0, 0])),
                     float(r.x[1]), float(np.sqrt(cov[1, 1]))))
    if len(rows) < 2:
        return None
    k = np.array([r[0] for r in rows], float)
    tc = np.array([r[1] for r in rows])
    sig = np.array([r[2] for r in rows])
    w = 1.0 / np.maximum(sig, 1e-6) ** 2
    A = np.vstack([np.ones_like(k), k]).T
    cov = np.linalg.inv(A.T @ (A * w[:, None]))
    coef = cov @ (A.T @ (w * tc))
    oc = tc - (coef[0] + coef[1] * k)
    return {"period": float(coef[1]), "period_err": float(np.sqrt(cov[1, 1])),
            "epochs": [int(x) for x in k], "transit_times": tc.tolist(),
            "o_minus_c_minutes": (oc * 1440).tolist(),
            "per_transit_depth": [r[3] for r in rows],
            "per_transit_depth_err": [r[4] for r in rows]}


def main():
    state = read_payload()
    for key in ("lc_path", "flag_convention", "search_summary", "candidates",
                "candidate_rank", "alias_factor", "output_path"):
        if key not in state:
            fail(f"state.{key} is required")
    rank_label, alias = state["candidate_rank"], state["alias_factor"]
    if alias not in ALIAS_FACTOR:
        fail(f"alias_factor {alias!r} not one of {list(ALIAS_FACTOR)}")
    factor = ALIAS_FACTOR[alias]
    try:
        rank = int(str(rank_label).replace("rank", ""))
    except ValueError:
        fail(f"candidate_rank {rank_label!r} is not rank1..rank5")
    by_rank = {int(c["rank"]): c for c in state["candidates"]}
    if rank not in by_rank:
        fail(f"candidate_rank {rank_label!r} not among the {len(by_rank)} candidates")
    c = by_rank[rank]
    P0 = float(c["period"]) * factor
    T0 = float(c["t0"])
    D = float(c["duration_days"])
    summ = state["search_summary"]
    window = float(summ["flatten_window_days"])

    d = load_clean(state["lc_path"], state["flag_convention"])
    t, f, e = d["time"], d["flux"], d["flux_err"]

    from astropy.timeseries import BoxLeastSquares
    # 1. Mask transits (2.5x duration covers T0/duration slop) and re-flatten.
    mask = BoxLeastSquares(t, f).transit_mask(t, P0, 2.5 * D, T0)
    ft, ff, fe, nclip = flatten(t, f, e, window, mask=mask)

    # 2. Fine BLS around P0.
    bls = BoxLeastSquares(ft, ff, dy=fe)
    periods = np.linspace(P0 * 0.99, P0 * 1.01, 6001)
    durs = np.linspace(max(0.5 * D, 0.01), min(2.0 * D, 0.9 * P0 * 0.99), 31)
    pg = bls.power(periods, durs, objective="likelihood")
    i = int(np.argmax(pg.power))
    Pb, Tb, Db, depb = (float(pg.period[i]), float(pg.transit_time[i]),
                        float(pg.duration[i]), float(pg.depth[i]))
    stats = bls.compute_stats(Pb, Db, Tb)
    depth_snr = float(stats["depth"][0] / stats["depth"][1]) if stats["depth"][1] > 0 else None

    # 3. Trapezoid fit on the in-transit neighbourhoods.
    near = bls.transit_mask(ft, Pb, 5.0 * Db, Tb)
    res, perr, chi2r = fit_trapezoid(ft[near], ff[near], fe[near], Pb, Tb, depb, Db)
    Pf, Tf, depf, T14, T12 = [float(x) for x in res.x]
    fit_ok = (res.success and np.isfinite(perr[0]) and abs(Pf / Pb - 1) < 0.005
              and depf > 0 and 0 < abs(T14) < 0.5 * Pb)
    timing = transit_timing(ft[near], ff[near], fe[near], Pf, Tf, depf, abs(T14), abs(T12)) if fit_ok else None

    if fit_ok:
        period, perr0, method = Pf, float(perr[0]), "trapezoid least-squares fit (transit-masked flatten)"
    else:
        grid_step = float(periods[1] - periods[0])
        period, perr0, method = Pb, grid_step, "fine BLS grid peak (trapezoid fit rejected)"

    text = f"{period:.5f}"
    out = state["output_path"]
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w") as fh:
        fh.write(text + "\n")

    agree = [abs(period - Pb)]
    if timing:
        agree.append(abs(period - timing["period"]))
    emit({
        "period_days": period,
        "period_text": text,
        "refine_summary": {
            "candidate_rank": rank,
            "alias_factor": alias,
            "start_period": P0,
            "method": method,
            "period": period,
            "period_uncertainty": perr0,
            "fine_bls_period": Pb,
            "fine_bls_depth_snr": depth_snr,
            "fine_bls_duration_days": Db,
            "fit_period": Pf,
            "fit_t0": Tf,
            "fit_depth": depf,
            "fit_t14_days": abs(T14),
            "fit_reduced_chi2": chi2r,
            "fit_accepted": bool(fit_ok),
            "timing": timing,
            "max_disagreement_between_estimates_days": float(max(agree)),
            "n_points_after_masked_flatten": int(len(ft)),
            "n_upward_outliers_clipped": nclip,
            "output_path": out,
            "written": text,
        },
    })


if __name__ == "__main__":
    main()
