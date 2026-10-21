# Methods reference (load for ad-hoc diagnostics or debugging)

Condensed from the five source skills in `source/`. The APIs below match the task container's versions (astropy 6.0.1, lightkurve 2.4.2, transitleastsquares 1.32).

## Pipeline stages (order matters)

1. Load: know your format, columns and time system.
2. Quality control: filter by quality flags. Check the convention first (flag = 0 is good for standard TESS; some exports use flag = 0 = bad). Check which convention gives the cleaner light curve.
3. Outlier removal: before detrending, because outliers distort the trend fit. sigma = 3 is standard (~0.3% removed), 5 is conservative, 2 is aggressive; 3 for the first pass, 5 after flattening. For transits, clip the high side (flares, cosmic rays) and keep the low side loose.
4. Detrend: remove rotation and instrumental drift while preserving transit shapes. Don't over-process: too much smoothing removes shallow transits.
5. Optional second outlier pass after detrending.
6. Period search: broad first, then refine.
7. Validate (SDE, SNR, odd/even, phase fold, number of transits), then refine the period.
8. Plot before and after each step when working interactively, and document the workflow.

## Detrending

```python
import lightkurve as lk
lc = lk.LightCurve(time=t, flux=f, flux_err=e)
lc_clean, mask = lc.remove_outliers(sigma=3, return_mask=True)   # lc[mask] = removed points
lc_flat = lc_clean.flatten(window_length=501)                     # cadences, odd; Savitzky-Golay
```

Typical TESS 2-min windows: 100–200 cadences removes short-term trends, 300–500 medium-term (typical for TESS), 500–1000 long-term. The window must be longer than the transit and shorter than the rotation period: too short eats transits, too long leaves trends.

Manual sigma clip: `good = np.abs(flux - np.median(flux)) < 3*np.std(flux)`.

Iterative sine fitting removes rotation and pulsation, but it removes periodic signals generally, so use it carefully:

```python
def sine_fitting(lc):
    pg = lc.to_periodogram()
    model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)
    out = lc.copy(); out.flux = out.flux / model.flux
    return out, model
for i in range(50):
    lc, model = sine_fitting(lc)
```
(`scripts/find_period.py --detrend sine` does the same with astropy LombScargle, which is faster.)

## Lomb-Scargle (rotation and general periodicity)

```python
pg = lc.to_periodogram(minimum_period=0.1, maximum_period=15)   # lightkurve
pg.period_at_max_power, pg.max_power, pg.frequency_at_max_power
pg.plot(view='period')         # default view is frequency
model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)
```
Period ranges: rotation 0.1–100 d, transits 0.5–50 d, eclipsing binaries 0.1–100 d, pulsations 0.001–1 d. Multiple peaks can be harmonics (P/2, 2P) or aliases. Lomb-Scargle is fast but less sensitive to shallow transits and confuses harmonics, so use it for exploration and rotation, then run TLS.

## Transit Least Squares (preferred transit search)

```python
from transitleastsquares import transitleastsquares, transit_mask
model = transitleastsquares(t, f, flux_err)          # flux_err REQUIRED for proper weighting
r = model.power(period_min=0.5, period_max=13, oversampling_factor=3,
                duration_grid_step=1.1, T0_fit_margin=5, use_threads=4,
                show_progress_bar=False, verbose=False)
r.period, r.period_uncertainty, r.T0, r.depth (min flux, 1-depth = fractional), r.duration,
r.snr, r.SDE, r.odd_even_mismatch, r.transit_depths, r.distinct_transit_count,
r.empty_transit_count, r.periods, r.power,
r.folded_phase, r.folded_y, r.model_folded_phase, r.model_folded_model,
r.model_lightcurve_time, r.model_lightcurve_model
```
- Refinement: rerun `power()` over ±2–10% of the candidate (±5% typical, e.g. 3.0–3.4 d around 3.2 d). The narrower range gives a finer grid and better precision. A higher `oversampling_factor` gives a finer period grid (slower). `duration_grid_step` 1.01 = 1% duration steps. `T0_fit_margin=0` is faster.
- Thresholds: SDE > 9 very strong, > 6 strong, < 6 weak / possible false positive. SNR > 7 reliable, < 7 needs validation.
- Multi-planet: find the best candidate, `mask = transit_mask(t, P, 2*duration, T0)`, search `t[~mask]` again, and repeat until nothing significant is left.
- Strengths: most sensitive for transits, handles grazing transits, robust automatic grid. Weaknesses: slower than Lomb-Scargle and BLS on long series, detects transits only.

## Box Least Squares (astropy cross-check)

```python
from astropy.timeseries import BoxLeastSquares
bls = BoxLeastSquares(t, f, dy=e)
pg = bls.autopower([0.05, 0.1, 0.15, 0.2], objective='likelihood')   # or objective='snr' (more robust to correlated noise)
periods = bls.autoperiod(durations, minimum_period=1, maximum_period=10)   # conservative grid
pg = bls.power(periods, durations)        # custom grid; too coarse a grid misses the peak
i = np.argmax(pg.power); P, D, T0 = pg.period[i], pg.duration[i], pg.transit_time[i]
st = bls.compute_stats(P, D, T0)
st['depth'], st['depth_odd'], st['depth_even']       # (value, err) tuples
st['transit_times'], st['per_transit_count'], st['per_transit_log_likelihood']
# NOTE: no 'transit_count' key in astropy 6; use len(st['transit_times'])
```
- Validation: depth SNR > 7, |odd − even| < 3·err (otherwise not planetary: an eclipsing binary or an artefact), several transits, and a duration that is reasonable for the period.
- Compare candidates: sort `pg.power` descending and print period, power, duration, SNR and transit count for the top 5.
- BLS uses a box model and is fast, built in and has good statistics, but it's less sensitive to grazing transits and needs a careful grid. Use a finer grid around promising peaks. Grid quality matters more for BLS than for Lomb-Scargle. Try both TLS and BLS and compare.

## Validation and troubleshooting

- Phase fold: `phase = ((t - T0) % P) / P` and look for a clean dip. Fold at P/2 and 2P as well.
- Period is 2× or 0.5× the truth (aliasing from gaps, missing alternate transits): check both periods manually, compare odd/even depths and both folds, and compare the SDE at both.
- No clear peak or low SDE: transits too shallow, wrong duration range, period outside the searched range, over-aggressive preprocessing (outlier clipping or a short flatten window), or transits falling in data gaps. Widen the duration and period ranges, use a gentler flatten, and look for dips in the raw data.
- Results change with preprocessing: compare the variants, plot each step, and make sure you're not over-smoothing.
- High odd/even mismatch: eclipsing binary or instrumental artefact; probably not a planet.

## Context values

- Transit depths: hot Jupiter 0.01–0.03, super-Earth 0.001–0.003, Earth-size 0.0001–0.001. Smaller planets are much harder to detect.
- Period ranges: hot Jupiters 0.5–10 d, warm planets 10–100 d, habitable zone 200–400 d (Sun-like) or 10–50 d (M dwarf). Wider ranges are more complete but slower. Adjust to the mission duration (TESS sectors are ~27 d, so P ≤ ~13 d for two transits).
