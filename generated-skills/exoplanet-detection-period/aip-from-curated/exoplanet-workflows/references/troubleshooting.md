# Troubleshooting an exoplanet detection run

Load when a detection looks wrong: low SDE, odd period, or no clear peak.

## Low SDE (<6)

Likely causes:
- Preprocessing removed the transit. Try a longer flatten window or skip
  iterative sine fitting if you used it.
- Outlier removal was too aggressive. Try sigma=5 instead of sigma=3.
- Transits fall in data gaps. Check the time array vs the expected transit
  cadence at the candidate period.
- Signal genuinely too shallow.

## Period is 2× or 0.5× expected

Likely causes:
- Missing alternating transits (true period is double, every-other transit
  was masked by a gap).
- Period aliasing from gaps in the cadence.

What to do:
- Run TLS or BLS at the doubled and halved periods explicitly.
- Phase-fold at each candidate; the wrong period leaves a "second dip"
  visible at phase 0.5.
- If TLS warned "X of Y transits without data", trust the warning.

## "flux_err is required" error

TLS needs flux uncertainties as the third positional argument — they are
not optional. Pass `lc_flat.flux_err.value`, never `None`.

## Results vary wildly with preprocessing

Diagnosis:
- Plot the light curve after each preprocessing step. Compare quality.
- Compare TLS output at different `flatten(window_length=)` values.
- Too short a window flattens transits out; too long leaves rotation in.

## Odd-even mismatch

A real planetary transit has consistent depth on odd and even orbits. If
`|depth_odd - depth_even| > 3 * depth_err`, the candidate is more likely an
eclipsing binary at twice the period. Try the doubled period and check.

## Multi-planet systems

After confirming a candidate, mask the transits with
`transitleastsquares.transit_mask(time, period, duration, t0)` and rerun
TLS on the remaining data. Repeat until no significant signal remains.
