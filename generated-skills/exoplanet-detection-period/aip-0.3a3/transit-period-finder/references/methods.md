# Transit search methods: API notes and thresholds

Load this file when you need to go past `scripts/transit_period.py`: hand-tuning a search,
writing custom code, interpreting a statistic the script reports, or debugging a failed run.
Versions match the task container: astropy 6.0.1, lightkurve 2.4.2, transitleastsquares 1.32,
batman-package 2.5.2, numpy 1.26.4, scipy 1.13.1.

## Choosing a method

| Method | Use for | Notes |
|---|---|---|
| TLS (`transitleastsquares`) | Transiting planets. The default search | Fits limb-darkened transit shapes; most sensitive to shallow and grazing transits; robust automatic period grid; slower on long series; needs a separate package |
| BLS (`astropy.timeseries.BoxLeastSquares`) | Fast, built-in transit search; cross-check for TLS; `compute_stats` validation | Box model; you control the period grid, and grid quality matters more than for Lomb-Scargle; may miss grazing transits |
| Lomb-Scargle (`lc.to_periodogram()`, `astropy.timeseries.LombScargle`) | Stellar rotation, pulsation, eclipsing binaries, first exploration of any periodicity | Less sensitive to shallow transits and confuses harmonics with the fundamental. Use it to measure the *variability* period, not the planet's |

TLS usually beats BLS for exoplanets. Running both and comparing them is the cross-check.

## Lightkurve preprocessing

```python
import lightkurve as lk
lc = lk.LightCurve(time=t, flux=f, flux_err=e)
lc_clean, outlier_mask = lc.remove_outliers(sigma=3, return_mask=True)  # removed = lc[outlier_mask]
lc_flat = lc_clean.flatten(window_length=501)   # Savitzky-Golay; window in CADENCES, must be odd
lc_flat = lc_clean.flatten(window_length=501, mask=transit_mask)  # masked points ignored by the trend fit
pg = lc.to_periodogram(minimum_period=0.1, maximum_period=15)     # Lomb-Scargle
pg.period_at_max_power; pg.max_power; pg.frequency_at_max_power
model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)  # sinusoid for sine fitting
lc.plot(); pg.plot(view='period')   # view='period' shows period on the x axis; the default view is frequency
```

- `remove_outliers` sigma: 2 is aggressive, 3 standard (~0.3% of points), 5 to 7 conservative.
  The source workflow uses 3 for the first pass and 5 after flattening. Accepts
  `sigma_upper`/`sigma_lower` separately.
- `flatten` window, as a rule of thumb at 2-min cadence: 100 to 200 cadences remove short-term
  trends, 300 to 500 medium-term (typical for TESS), 500 to 1000 long-term. A short window does
  not remove the trend; a long one eats transits. The window must be longer than the transit
  and shorter than the rotation period.
- Iterative sine fitting divides out `pg.model(...)` at the peak frequency repeatedly (the source
  used up to 50 iterations). It removes periodic signals, so never run it on the flattened
  series you search for transits. `transit_period.py` stops once the fitted amplitude is below
  the flux error.

## TLS

```python
from transitleastsquares import transitleastsquares, transit_mask
model = transitleastsquares(t, flux, flux_err)        # pass flux_err: TLS needs it for weighting
res = model.power(period_min=0.5, period_max=12.7,    # omit both to use the default grid
                  oversampling_factor=3,               # finer period grid (default 3; higher is slower)
                  duration_grid_step=1.1,              # 1.01 = 1% duration steps
                  T0_fit_margin=0.01,                  # 0 = no margin (faster)
                  use_threads=os.cpu_count(), show_progress_bar=False, verbose=False)
res.period, res.period_uncertainty, res.T0, res.duration, res.depth   # depth is a flux RATIO (0.998), not 1 - ratio
res.SDE, res.snr, res.odd_even_mismatch, res.transit_count, res.distinct_transit_count, res.empty_transit_count
res.periods, res.power                                # the SDE spectrum
res.folded_phase, res.folded_y, res.model_folded_phase, res.model_folded_model
res.model_lightcurve_time, res.model_lightcurve_model
in_transit = transit_mask(t, res.period, 2 * res.duration, res.T0)   # boolean, True = in transit
```

- The defaults shown above (oversampling 3, duration step 1.1, T0 margin 0.01, which is a
  fraction of the duration and capped at 0.1) are the real values in 1.32. Older notes that list
  defaults of 1 and 5 are wrong.
- Run TLS from a script with an `if __name__ == "__main__":` guard. TLS uses multiprocessing,
  and on spawn-based platforms an unguarded script re-executes itself in every worker.
- The warning "X of Y transits without data. The true period may be twice the given period"
  means data gaps fall on predicted transits. Check 2P.
- TLS's reported period sits on its own grid. Re-running it on a narrow window
  (±2 to ±10% of the candidate) with a higher `oversampling_factor` helps somewhat, but a
  transit-model fit of P and T0 (what `refine` does) is more precise than any grid.
  `period_uncertainty` is the grid half-width, not a fit error.

## BLS

```python
import astropy.units as u
from astropy.timeseries import BoxLeastSquares
m = BoxLeastSquares(t * u.day, flux, dy=flux_err)      # units optional; be consistent
pg = m.autopower(0.2 * u.day)                           # automatic grid, one duration
pg = m.autopower([0.05, 0.1, 0.15, 0.2] * u.day, objective="likelihood")   # or objective="snr"
periods = m.autoperiod(durations, minimum_period=1, maximum_period=10)      # conservative grid
pg = m.power(periods, durations)                        # custom grid
i = np.argmax(pg.power); pg.period[i], pg.duration[i], pg.transit_time[i], pg.depth[i]
top5 = np.argsort(pg.power)[::-1][:5]
stats = m.compute_stats(pg.period[i], pg.duration[i], pg.transit_time[i])
```

- The default objective is `likelihood`. `snr` can be more reliable with correlated noise.
- `compute_stats` keys in astropy 6.0.1: `depth`, `depth_odd`, `depth_even`, `depth_half`,
  `depth_phased` (each a `(value, uncertainty)` tuple), `transit_times`, `per_transit_count`,
  `per_transit_log_likelihood`, `harmonic_amplitude`, `harmonic_delta_log_likelihood`.
  The keys `depth_snr`, `depth_err` and `transit_count` used in some tutorials do not exist.
  Compute them instead: depth SNR = `depth[0]/depth[1]`;
  odd/even sigma = `|odd[0]-even[0]| / hypot(odd[1], even[1])`;
  transits with data = `(per_transit_count > 0).sum()`.
- `depth_half` is the depth at half the period. `depth_phased` is the depth at phase 0.5
  (a secondary eclipse).
- Fold: `phase = ((t - t0) % P) / P`. A period grid that is too coarse misses the true period:
  the frequency step must keep the transit phase drift over the baseline under about a third
  of the duration.

## Validation thresholds

- TLS SDE: > 9 very strong, > 6 strong candidate, < 6 weak (possible false positive).
- SNR (TLS `snr`, BLS depth SNR): > 7 reliable, < 7 needs extra validation.
- Odd/even depths differing by more than 3σ points to an eclipsing binary or a true period of 2P.
- Each additional transit adds confidence. Fewer than 2 transits with data leaves the period unconstrained.
- The duration must be plausible for the orbit: roughly `P/(π·a/R*)`, and hours for P of a few days.
- Expected depths: hot Jupiter 0.01 to 0.03; super-Earth 0.001 to 0.003; Earth-size 0.0001 to 0.001.
- Typical periods: hot Jupiters 0.5 to 10 d; warm planets 10 to 100 d; habitable zone 200 to
  400 d (Sun-like star) or 10 to 50 d (M dwarf). Lomb-Scargle ranges by phenomenon: rotation
  0.1 to 100 d, transits 0.5 to 50 d, eclipsing binaries 0.1 to 100 d, pulsation 0.001 to 1 d.
  A single TESS sector (~27 d) caps a ≥2-transit search at about 13 d.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No clear peak / SDE < 6 | Over-aggressive flattening or clipping, wrong duration or period range, transits in gaps, signal too shallow | Lengthen the window (still below P_rot/3), use a gentler clip, widen the duration and period ranges, look at the raw data around predicted transits |
| P is 2× or 0.5× expected | Missing alternate transits, gaps, aliasing | Compare both: odd/even at P, depth at P/2, phase folds at both |
| High odd/even mismatch | Eclipsing binary or instrumental artifact | Not a planet at this period. Try 2P or the next peak |
| Peak at P_rot or a harmonic | Residual stellar variability | Pre-whiten more sinusoids or shorten the window |
| Results change with preprocessing | Over-smoothing or a marginal signal | Compare windows and plot each step. Trust only what survives all of them |
| "flux_err required" / poor weighting | Errors omitted | Always pass flux_err. If the file has no error column, estimate it from point-to-point scatter |

## Multi-planet systems

Find the strongest candidate, mask its transits (`transit_mask`, or
`transit_period.py search --mask P,T0,DUR`), search again, and repeat until nothing
significant is left. Report the strongest signal unless the task specifies another.

## Further reading

Astropy BLS docs (docs.astropy.org/en/stable/timeseries/bls.html); TLS (github.com/hippke/tls,
tutorials folder); Lightkurve tutorials 2.3 (removing noise), 3.1 (identifying transiting
exoplanets), 3.2 (periodograms). Papers: Kovács, Zucker & Mazeh 2002 (BLS, A&A 391, 369);
Hippke & Heller 2019 (TLS); Hartman & Bakos 2016 (VARTOOLS BLS).
