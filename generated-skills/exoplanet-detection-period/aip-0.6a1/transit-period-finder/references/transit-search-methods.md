# Transit search methods: working notes

Load this when the automated search failed or was judged not credible, or when you must
hand-run an alternative. Packages in the task container: numpy, scipy, astropy,
lightkurve, transitleastsquares (TLS), batman-package, matplotlib. No wotan.

## Pipeline order (order matters)

1. Quality flags first. TESS standard: flag == 0 is GOOD. Some exported files invert it
   (flag == 0 is BAD); if one convention leaves almost nothing, or a much noisier curve,
   try the other and keep the one that gives cleaner data.
2. Outliers before detrending (outliers distort the trend fit). Initial pass sigma=3;
   after flattening sigma=5. Lower sigma (2) is aggressive, higher (5-7) conservative.
   Clip the upper side only (flares, cosmic rays): a symmetric clip on raw flux can delete
   transits, especially deep ones.
3. Remove stellar variability: `lc.flatten(window_length=N)` (Savitzky-Golay, in cadences).
   The window must be longer than the transit duration and shorter than the rotation
   period. Too short erases/shrinks transits; too long leaves rotation residuals that
   become false periods. Rough guide: 100-200 cadences removes short-term trends,
   300-500 medium (typical TESS 2-min), 500-1000 long-term. Pass `mask=` (True =
   in-transit) to keep known transits out of the trend fit.
4. Optional second outlier pass after detrending (upper side, sigma=5).
5. Period search, then refine, then validate.

Always carry flux_err through every step; TLS needs it as the third argument.

## Lomb-Scargle (stellar rotation / any periodicity)

```python
import lightkurve as lk
lc = lk.LightCurve(time=time, flux=flux, flux_err=error)
pg = lc.to_periodogram(minimum_period=0.1, maximum_period=15)
pg.period_at_max_power, pg.max_power      # plot with pg.plot(view='period')
model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)
```

Ranges: rotation 0.1-100 d, transits 0.5-50 d, eclipsing binaries 0.1-100 d, pulsation
0.001-1 d. Peaks at P/2 or 2P are harmonics; check both. LS is weak on shallow transits.

Iterative sine fitting (pre-whitening) removes rotation/pulsation harmonics, but it also
removes periodic signals, so mask known transits first and inspect the result:

```python
def sine_fitting(lc):
    pg = lc.to_periodogram()
    model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)
    lc_new = lc.copy(); lc_new.flux = lc_new.flux / model.flux
    return lc_new, model
for i in range(50):
    lc_processed, model = sine_fitting(lc_processed)
```

## Transit Least Squares (default transit search)

```python
from transitleastsquares import transitleastsquares, transit_mask
model = transitleastsquares(t, f, f_err)                    # flux_err REQUIRED
res = model.power(period_min=0.3, period_max=baseline/2,
                  show_progress_bar=False, verbose=False, use_threads=os.cpu_count())
res.period, res.period_uncertainty, res.T0, res.depth, res.duration
res.SDE, res.snr, res.odd_even_mismatch, res.transit_count, res.distinct_transit_count
res.folded_phase, res.folded_y, res.model_folded_phase, res.model_folded_model
res.model_lightcurve_time, res.model_lightcurve_model
```

Wrap TLS calls in `if __name__ == "__main__":` (it uses multiprocessing).

- Refine: broad search first, then re-run with period_min/max at +/-2-10% (typ. 5%) of the
  candidate. Narrower range = finer grid. Advanced knobs: `oversampling_factor` (finer
  period grid, slower), `duration_grid_step` (default 1.1; 1.01 = 1% steps),
  `T0_fit_margin` (default 5; 0 = faster).
- SDE inside a narrow refinement window is not meaningful; judge SDE on the broad search.
- Warning "X of Y transits without data. The true period may be twice the given period"
  means gaps may alias the period; check 2P.
- Grid periods are good to a fraction of the peak width (`period_uncertainty`). For the
  final number, fit a transit model (trapezoid or batman) to all transits for P and T0.

## Box Least Squares (astropy, cross-check)

```python
from astropy.timeseries import BoxLeastSquares
bls = BoxLeastSquares(t, f, dy=f_err)
durations = [0.05, 0.08, 0.12, 0.2]                # days; each must be < minimum period
periods = bls.autoperiod(durations, minimum_period=0.5, maximum_period=baseline/2)
pg = bls.power(periods, durations, objective='snr')   # or 'likelihood' (default)
i = pg.power.argmax(); P, dur, t0 = pg.period[i], pg.duration[i], pg.transit_time[i]
s = bls.compute_stats(P, dur, t0)   # depth, depth_odd, depth_even, depth_half,
                                    # depth_phased, transit_count, per_transit_count
```

To compare competing peaks, take the top 5 by power (`np.argsort(pg.power)[::-1][:5]`)
and run `compute_stats` on each: period, power, duration, depth SNR, transit count.

`autopower(duration)` picks a grid automatically (good for a first pass; then use finer
grids around promising candidates). Grid spacing matters more for BLS than
for LS; too coarse misses the period. The SNR objective is more robust to correlated
noise. BLS is a box model (less sensitive to grazing transits); TLS is generally more
sensitive. Try both and compare.

## Validation

| Metric | Threshold |
|---|---|
| TLS SDE (broad search) | >9 very strong, >6 strong, <6 weak / possible false positive |
| SNR (TLS snr or BLS depth_snr) | >7 reliable |
| Odd-even depth difference | > 3 x depth_err: not a consistent planet transit (EB or artifact; true period may be 2P) |
| Transits with data | >= 2 required; more = more confidence |
| Duration | plausible for the period (hours for days-long orbits) |

Also phase-fold at the candidate (and at P/2, 2P) and look.

## Expected transit depths and period ranges

- Hot Jupiters 1-3% (0.01-0.03), periods 0.5-10 d.
- Super-Earths 0.1-0.3%; Earth-sized 0.01-0.1%.
- Warm planets 10-100 d; habitable zone: Sun-like 200-400 d, M-dwarf 10-50 d.
- Search no longer than baseline/2 (need >= 2 transits).

## Common problems

- No clear peak / low SDE: transits too shallow, wrong duration range, period outside the
  range, or over-aggressive preprocessing. Widen durations and period range, use a less
  aggressive (longer) flatten window or less aggressive outlier removal, check gaps
  during transits, look at the raw data for dips.
- Period is 2x or 0.5x: missing alternate transits, gaps, aliasing. Fold at both; check
  odd-even; compare SDE at both.
- Results change with preprocessing: compare several settings, plot each step, avoid
  over-smoothing. A period that survives several windows is the robust one.
- Candidate equals the rotation period or a harmonic: residual activity, not a planet.
  Shorten the window or mask and pre-whiten the rotation.

## Multi-planet systems

Find the strongest candidate, mask its transits (`transit_mask(t, P, 2*duration, T0)`),
re-run TLS on the rest, repeat until SDE < 6. The planet the task asks for is normally
the strongest signal.
