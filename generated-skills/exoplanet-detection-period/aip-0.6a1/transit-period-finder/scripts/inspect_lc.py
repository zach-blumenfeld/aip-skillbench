"""Step inspect-light-curve: describe the file so the flag convention and detrending can be chosen.

stdin state: lc_path (plus the other start inputs, unused here)
stdout: {"data_summary": {...}}
"""
import numpy as np

from lcio import (cadence_days, emit, fail, interpret_columns, load_table, read_payload,
                  robust_p2p)


def subset_stats(t, f, sel):
    n = int(np.sum(sel))
    if n < 10:
        return {"count": n}
    ff = f[sel]
    med = float(np.nanmedian(ff))
    return {
        "count": n,
        "median_flux": med,
        "p2p_scatter": robust_p2p(ff / med if med else ff),
        "std": float(np.nanstd(ff / med if med else ff)),
        "n_nonfinite_flux": int(np.sum(~np.isfinite(ff))),
    }


def rotation(t, f):
    """Lomb-Scargle on the light curve: the dominant stellar-activity period."""
    from astropy.timeseries import LombScargle
    ok = np.isfinite(f)
    t, f = t[ok], f[ok] / np.median(f[ok])
    base = t.max() - t.min()
    ls = LombScargle(t, f)
    freq, power = ls.autopower(minimum_frequency=1.0 / max(base / 2.0, 0.2),
                               maximum_frequency=1.0 / 0.05, samples_per_peak=10)
    i = int(np.argmax(power))
    lo, hi = np.percentile(f, [5, 95])
    noise = robust_p2p(f)
    amp = float(hi - lo)
    return {
        "period_days": float(1.0 / freq[i]),
        "ls_power": float(power[i]),
        "amplitude_5_95": amp,
        "amplitude_over_noise": float(amp / noise) if noise > 0 else None,
        "significant": bool(power[i] > 0.1 and noise > 0 and amp > 3 * noise),
    }


def main():
    state = read_payload()
    path = state.get("lc_path")
    if not path:
        fail("state.lc_path is required")
    data, header = load_table(path)
    t, f, flag, err, names = interpret_columns(data)
    finite = np.isfinite(t) & np.isfinite(f)
    order = np.argsort(t)
    ts = t[order]
    dt = np.diff(ts)
    cad = cadence_days(ts)
    gaps = [{"start": float(ts[i]), "length_days": float(dt[i])}
            for i in np.where(dt > max(0.5, 20 * cad))[0]]

    summary = {
        "path": path,
        "n_rows": int(len(t)),
        "columns_interpreted": names,
        "header_lines": header[:10],
        "time_start": float(np.nanmin(t)),
        "time_end": float(np.nanmax(t)),
        "baseline_days": float(np.nanmax(t) - np.nanmin(t)),
        "cadence_minutes": cad * 1440.0,
        "gaps_over_half_day": gaps,
        "n_nonfinite_time_or_flux": int(np.sum(~finite)),
        "flux_err_present": err is not None,
        "median_flux_err": float(np.nanmedian(err)) if err is not None else None,
    }

    if flag is not None:
        vals, counts = np.unique(flag[np.isfinite(flag)], return_counts=True)
        top = np.argsort(counts)[::-1][:10]
        summary["flag_value_counts"] = {str(int(vals[i])) if vals[i] == int(vals[i]) else str(vals[i]): int(counts[i]) for i in top}
        summary["flag_zero_subset"] = subset_stats(t[order], f[order], (flag[order] == 0))
        summary["flag_nonzero_subset"] = subset_stats(t[order], f[order], (flag[order] != 0))
        z = flag == 0
        rot_sel = z if z.sum() >= 0.5 * len(z) else (flag != 0)
    else:
        summary["flag_value_counts"] = None
        rot_sel = np.ones(len(t), bool)

    sel = rot_sel & finite
    summary["stellar_variability"] = rotation(t[sel], f[sel]) if sel.sum() > 50 else None
    emit({"data_summary": summary})


if __name__ == "__main__":
    main()
