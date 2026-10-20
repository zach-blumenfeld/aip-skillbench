"""Settle the period (reported value or the chosen alias) and write the answer file.

For an alias the ephemeris fit is re-run seeded at 2P or P/2, so the written value is
fitted, not a multiplied grid value.
"""
import numpy as np

from lc_common import emit, fail, fit_ephemeris, load_arrays, read_state, write_period

FACTORS = {"reported": 1.0, "double": 2.0, "half": 0.5}


def main():
    state = read_state()
    choice = str(state["period_choice"]).strip().lower()
    if choice not in FACTORS:
        fail(f"period_choice must be one of {sorted(FACTORS)}, got {choice!r}")
    cand = state["candidate"]
    p = float(cand["period_days"])
    basis = f"{cand.get('period_source', 'search')} period"
    if choice != "reported":
        k = FACTORS[choice]
        seed = p * k
        flat = load_arrays(state["flat_file"])
        t, f, e = flat["time"], flat["flux"], flat["flux_err"]
        if seed > (t[-1] - t[0]):
            fail(f"alias {seed:.5f} d exceeds the {t[-1] - t[0]:.2f} d baseline; cannot be the period")
        dur = float(cand["duration_hours"]) / 24.0
        depth = float(cand["depth_ppt"]) / 1e3
        hw = max(float(cand.get("period_uncertainty_days", 0)) * 2 * k, 1e-3 * seed)
        fit = fit_ephemeris(t, f, e, seed, float(cand["t0"]), dur, depth, hw)
        if fit and not fit["at_bound"]:
            p, basis = fit["period"], f"trapezoid fit seeded at {choice} alias"
        else:
            p, basis = seed, f"{choice} alias of the search period (fit did not converge)"
    if not (np.isfinite(p) and p > 0):
        fail(f"non-physical period {p}")
    text = write_period(state["output_path"], p)
    emit({"final_period_days": round(p, 6), "period_text": text, "final_basis": basis})


if __name__ == "__main__":
    main()
