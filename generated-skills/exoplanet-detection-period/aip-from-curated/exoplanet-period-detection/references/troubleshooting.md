# Troubleshooting

## Script failures

### `transitleastsquares` complains about `flux_err`
`load_lightcurve.py` fabricates a MAD-based `flux_err` when the file
does not supply one. If TLS still raises, verify the lightcurve has
enough finite points (≥50) and non-zero scatter.

### `BoxLeastSquares` returns a single-element periodogram
The time span is too short relative to `period_min`/`period_max`.
`load_lightcurve.py` clamps `period_max` to half the baseline, but
very short datasets still produce a degenerate grid. Shorten
`period_min` or provide more cadences.

### `LombScargle.false_alarm_probability` raises
Astropy requires an approximation method on some code paths. The
`search_ls.py` wraps the call in a try/except and reports NaN; treat a
NaN FAP as "unknown" and lean on the sde-like statistic.

## Detection anomalies

### Period is twice or half of expected
Classic aliasing from data gaps. Phase-fold at both candidates:
- odd-even mismatch → the true period is twice (half of them were empty)
- clean fold at the shorter period → the shorter period is real

Re-run with `period_min`/`period_max` bracketing the alternative to
confirm.

### High odd-even mismatch (> 3σ)
Not a planet: likely an eclipsing binary with primary/secondary
eclipses of different depth. Flag in the final report; do not refine.

### Low SDE despite obvious dips
Over-aggressive flattening is the usual cause. The default Savitzky–
Golay window is 101 cadences — if a transit is longer than that, the
flattener erases it. Raise `window_length` (edit `_preprocess.py` or
pass a custom override) and re-search.

### Many TLS "transits without data" warnings
Data gaps. Consider: (a) widening the search to `2 * period`, (b)
masking the first transit and searching the remaining data (TLS
`transit_mask`) for multi-planet systems.

## Over-restriction

- The `validate-detection` decision collapses the signal strength to
  a three-level score. If the real detection sits awkwardly between
  levels (e.g. SDE = 6.1 with 4 transits), consider the thresholds
  advisory and surface both the raw SDE and the collapsed level to the
  user.
- The `pick-method` decision defaults to TLS. For general stellar
  variability work the agent should still override to LS even if the
  task description does not say "planet".
