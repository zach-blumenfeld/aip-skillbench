# Transit period search: methods reference

Load this when the scripted pipeline did not produce a convincing detection and you must
search by hand, or when you need a method detail (TLS, BLS, Lomb-Scargle, flattening,
validation thresholds) that the scripts do not expose.

## Pipeline order (order matters)

1. Load: know the columns, the time system and the flag convention.
2. Quality filter with the flags. Conventions vary: in standard TESS files `flag == 0` is good;
   some exports use `flag != 0` for good. Check which gives the cleaner (lower point-to-point
   scatter) light curve if the task statement does not say.
3. Remove outliers. With strong stellar variability, sigma-clip the *flattened* flux, not the
   raw flux: a raw 3-sigma clip cuts the peaks and troughs of the rotation signal. Clip upward
   outliers (flares, cosmic rays) only; transits are downward.
4. Remove stellar variability (rotation, pulsation, drift): flatten.
5. Optional second outlier pass after flattening (sigma 5 is conservative; never clip low).
6. Period search (BLS or TLS), then validation, then refinement.

Sigma guide: 2 aggressive, 3 standard (~0.3% of Gaussian data), 5-7 conservative.
"Use sigma 3 for initial outliers, 5 after flattening." Always keep `flux_err`.

## Flattening (lightkurve)

```python
import lightkurve as lk
lc = lk.LightCurve(time=t, flux=f, flux_err=e)
flat = lc.flatten(window_length=w)          # Savitzky-Golay, w in cadences (odd)
flat = lc.flatten(window_length=w, mask=in_transit)   # protect known transits
clean, out = flat.remove_outliers(sigma_upper=3, sigma_lower=float("inf"), return_mask=True)
```

- Window must be longer than the transit duration (>= ~3x) and shorter than the rotation
  period. Too short eats the transit; too long leaves rotation residuals that BLS/TLS pick up.
- Rough windows for 2-min TESS: 100-200 cadences short trends, 300-500 typical, 500-1000
  long-term. Use ~P_rot/4 (0.25-0.75 d) so the window follows the rotation signal and its
  P_rot/2 harmonic; longer windows let the harmonic through as long, shallow "transits".
- After a first detection, mask the transits and re-flatten: unmasked flattening depresses
  the depth and biases the period.
- Iterative sine fitting (`pg = lc.to_periodogram(); model = pg.model(time=lc.time,
  frequency=pg.frequency_at_max_power); lc.flux /= model.flux`, repeated) removes rotation /
  pulsation harmonics, but it also removes periodic signals: do not use it blindly before a
  transit search.

## Lomb-Scargle (stellar variability, not transits)

```python
pg = lc.to_periodogram(minimum_period=0.1, maximum_period=15)
pg.period_at_max_power; pg.max_power; pg.plot(view="period")   # default view is frequency
```
Ranges: rotation 0.1-100 d, transits 0.5-50 d, eclipsing binaries 0.1-100 d, pulsation
0.001-1 d. Peaks at P/2 and 2P are harmonics; very short periods may be aliases. LS is fast
but insensitive to shallow transits; use it to characterise the star, then BLS/TLS for the
planet.

## Box Least Squares (astropy)

```python
from astropy.timeseries import BoxLeastSquares
bls = BoxLeastSquares(t, f, dy=e)
pg = bls.autopower([0.05, 0.1, 0.15, 0.2])                      # automatic grid
periods = bls.autoperiod(durations, minimum_period=0.5, maximum_period=baseline / 2)
pg = bls.power(periods, durations, objective="likelihood")       # or objective="snr"
i = pg.power.argmax(); P, D, T0 = pg.period[i], pg.duration[i], pg.transit_time[i]
st = bls.compute_stats(P, D, T0)  # depth, depth_odd, depth_even, depth_half, depth_phased,
                                  # transit_times, per_transit_count, ...
mask = bls.transit_mask(t, P, D, T0)
```
- Grid quality matters more for BLS than Lomb-Scargle: too coarse misses the period. Refine
  with a dense `np.linspace` grid around the candidate.
- `objective="snr"` can help with correlated noise.
- Every trial duration must be shorter than the minimum trial period.

## Transit Least Squares (transitleastsquares)

```python
from transitleastsquares import transitleastsquares, transit_mask
model = transitleastsquares(t, f, e)          # flux_err is required for proper weighting
r = model.power(period_min=2.0, period_max=7.0, oversampling_factor=3,
                duration_grid_step=1.1, T0_fit_margin=5, use_threads=8,
                show_progress_bar=False, verbose=False)
r.period, r.period_uncertainty, r.T0, r.depth, r.duration, r.SDE, r.snr
r.transit_count, r.distinct_transit_count, r.odd_even_mismatch
r.folded_phase, r.folded_y, r.model_folded_phase, r.model_folded_model
r.model_lightcurve_time, r.model_lightcurve_model
```
- More sensitive than BLS for small/grazing planets (limb-darkened transit model) but much
  slower: a full-grid search on ~16k 2-min points can take many minutes. Bin to 6-10 min or
  restrict `period_min`/`period_max` first.
- TLS prints to stdout; redirect it if stdout must stay clean.
- Refinement: broad search first, then a narrow search (+-2% to +-10% of the candidate) with
  a higher `oversampling_factor` (finer period grid) and smaller `duration_grid_step`
  (e.g. 1.05; 1.01 = 1% steps). `T0_fit_margin=0` is faster.
- Warning "X of Y transits without data. The true period may be twice the given period."
  means gaps hide transits: test 2P.
- Multi-planet: `mask = transit_mask(t, P, 2 * duration, T0)`, search `t[~mask]` again,
  repeat until no significant signal.

## Validation thresholds

| Metric | Threshold |
|---|---|
| TLS SDE (BLS SDE is analogous) | > 9 very strong, > 6 strong candidate, < 6 weak / possible false positive |
| Depth SNR | > 7 reliable, < 7 needs more validation |
| Odd/even depth mismatch | > 3 sigma: not a consistent transit at this period (EB, artifact, or the true period is 2P) |
| Transits observed | >= 2 needed for a period; more = more confidence |
| Duration | Must be plausible for the period (hours for days-long orbits; duration/period ~0.5-10%) |

Aliases: if the period is 2x or 0.5x the true one, check both by phase folding, odd/even
depths (at P: one of odd/even ~0 means the truth is 2P), and the depth at phase 0.5 (equal to
the primary depth means the truth is P/2). Gaps cause aliasing.

## Context

- Expected depths: hot Jupiters 0.01-0.03; super-Earths 0.001-0.003; Earth-sized
  0.0001-0.001. Smaller planets are much harder.
- Period ranges: hot Jupiters 0.5-10 d; warm planets 10-100 d; habitable zone ~200-400 d
  (Sun-like) or 10-50 d (M dwarf). A single TESS sector (~27 d) needs P <= baseline/2 for two
  transits.

## Common issues

- No clear peak / low SDE: the transit may be too shallow, the duration range wrong, the
  period outside the range, or preprocessing too aggressive (lengthen the window, relax
  clipping), or transits fell in gaps. Inspect the raw data around candidate times.
- Results change with preprocessing: compare windows; a real signal is stable.
- High odd/even mismatch: eclipsing binary or instrumental artifact, or wrong period.
