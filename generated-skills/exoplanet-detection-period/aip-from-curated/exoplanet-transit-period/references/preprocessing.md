# Light-curve preprocessing: by-hand recipes and parameter guidance

Load this when re-running preprocessing with different settings (weak or suspicious
signal, results that change with preprocessing) or when doing a step by hand.

## Order matters

1. Quality flags first.
2. Outlier removal (flares, cosmic rays) before detrending: outliers bias the trend fit.
3. Trend removal (stellar rotation, instrumental drift).
4. Optional second outlier pass after detrending (gentler: sigma 5).

## Quality flags: conventions vary by source

```python
good = flag == 0      # standard TESS: flag 0 is GOOD
good = flag != 0      # some exported files: flag 0 is BAD
```
Always verify; check which gives cleaner results (lower point-to-point scatter).
`scripts/prepare.py` does this automatically; force a convention with state key
`quality_convention`: `flag0_good`, `flag0_bad`, or `ignore`.

## Outliers

```python
lc_clean, mask = lc.remove_outliers(sigma=3, return_mask=True)   # lightkurve
outliers = lc[mask]
# manual
good = np.abs(flux - np.median(flux)) < 3 * np.std(flux)
```
- sigma 3 standard (removes ~0.3%), sigma 5 conservative, sigma 2 aggressive.
- Lower sigma (2-3) is aggressive, higher (5-7) conservative.
- Symmetric clipping removes transit bottoms (transits are negative outliers, a 1-3%
  hot-Jupiter dip is 10-30 sigma on a quiet star). The pack clips upward only
  (`sigma_upper`), and removes downward points only when they are isolated
  single-cadence glitches. Keep that if you clip by hand:
  `lc.remove_outliers(sigma_upper=3, sigma_lower=float('inf'))`.

## Flattening (Savitzky-Golay, lightkurve)

```python
lc_flat = lc_clean.flatten(window_length=501)          # window in CADENCES, must be odd
lc_flat = lc_clean.flatten(window_length=501, mask=in_transit)  # protect known transits
```
- 100-200 cadences: short-term trends; 300-500: medium (typical TESS 2-min); 500-1000: long-term.
- Window must be longer than the transit duration and shorter than the stellar rotation
  period. Too short leaves trends or eats the transit; too long leaves rotation in.
- Convert from days: `window_length = odd(round(window_days / cadence_days))`; the same
  cadence count means very different times at 2-min vs 30-min cadence.
- Override in the pack with state key `flatten_window_days`; a longer window is the
  "less aggressive flattening" fix for a weak signal.

## Iterative sine fitting (fast rotation / pulsation)

```python
def sine_fitting(lc):
    """Remove dominant periodic signal by fitting sine wave."""
    pg = lc.to_periodogram()
    model = pg.model(time=lc.time, frequency=pg.frequency_at_max_power)
    lc_new = lc.copy()
    lc_new.flux = lc_new.flux / model.flux
    return lc_new, model

lc_processed = lc_clean.copy()
for i in range(50):              # number of iterations
    lc_processed, model = sine_fitting(lc_processed)
```
Warning: this removes periodic signals, including a transit whose Lomb-Scargle peak is
dominant. The pack only prewhitens when variability is strong, faster than the
smallest safe flatten window (0.25 d), and not transit-shaped, and stops once peaks
fall below 0.5x the noise. Force with state key `prewhiten`: `on` / `off`.

## Visual checks

Plot before and after each major step (`lc.plot()`; the pack writes `prepare.png`,
`search.png`, `refine.png` in its work dir). Make sure each step improves the data
and does not remove real dips. More preprocessing is not always better.
