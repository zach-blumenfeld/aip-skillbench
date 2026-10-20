The automated transit search did not produce a credible planet period. Find the
period by hand, then answer with it.

Search result (window scan, TLS/BLS periods, vetting statistics):
{candidate}

Data preparation summary:
{prep_summary}

Files (numpy .npz with arrays `time`, `flux`, `flux_err`):
- cleaned, not detrended: {clean_file}
- flattened with the candidate's transits masked: {flat_file}
- scratch directory for anything you write: {work_dir}

Work through these in order and stop at the first that yields a credible signal
(TLS broad-search SDE >= 6 and SNR >= 7, >= 2 transits with data, odd/even depths
within 3 sigma, period not the rotation period or a harmonic of it):

1. Re-flatten the cleaned curve with windows outside the scanned set (see
   `window_scan`): longer if transits look shrunk, shorter if rotation residuals remain.
   Keep the window above ~3x the transit duration.
2. Widen the search: durations up to ~0.3 d, period range from 0.2 d to baseline/2.
3. If the strongest peak is the rotation period or a harmonic, mask it out and
   pre-whiten the rotation (iterative sine fitting), then search again.
4. Compare TLS and BLS. Phase-fold at P, P/2 and 2P.
5. Refine the winner with TLS at +/-5% and fit a trapezoid model for the final P
   (`fit_ephemeris` in the skill's `scripts/lc_common.py`).

If nothing reaches the threshold, report the best-supported period anyway (the task
needs a number) and say in the notes how weak it is.

Answer with `rescue_period_days` (float, days, unrounded) and `rescue_notes` (what you
tried, the metrics of the chosen signal, and why it wins).
