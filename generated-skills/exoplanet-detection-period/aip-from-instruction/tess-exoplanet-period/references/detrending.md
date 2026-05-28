# Detrending fallbacks

Load this reference only when the default Savitzky-Golay detrend in
`scripts/detect_period.py` fails — typically when the phase-folded
light curve at the recovered period shows no coherent dip, or the BLS
spectrum is dominated by stellar-rotation harmonics rather than a
narrow transit peak.

## Symptom → fix

### Transits are being smoothed away

If the BLS spectrum is flat / noisy and you can see by eye that the
detrended flux has no dips left:

- The window is too small. Increase `--window-days` to ~2× the
  suspected stellar rotation period.
- Switch to a biweight filter (preserves narrow features better than
  Savitzky-Golay's polynomial fit). Use `wotan.flatten(..., method='biweight', window_length=...)`
  if `wotan` is available; otherwise replace `savgol_filter` with a
  rolling biweight via `astropy.stats.biweight_location` over a sliding
  window.

### Stellar rotation leaks through

If the BLS spectrum is dominated by peaks at the stellar rotation
period (typically a few days, with strong harmonics):

1. Run Lomb–Scargle (`astropy.timeseries.LombScargle`) on the
   *un-detrended* flux to identify the rotation period `P_rot`.
2. Choose the Savitzky-Golay window to be `< P_rot / 2` so the filter
   tracks the rotation; or fit and subtract a sum of sinusoids at
   `P_rot, P_rot/2, P_rot/3`.

### Both: iterative transit-masking

The most reliable fallback when single-pass detrending fights the
transits:

```python
from scripts.detect_period import (
    load_lightcurve, quality_filter, detrend_savgol,
    asymmetric_clip, bls_search, refine_peak,
)
import numpy as np

t, f, q, e = load_lightcurve(path)
t, f, e = quality_filter(t, f, q, e)

# Pass 1: rough detrend + BLS to locate transits.
f1 = detrend_savgol(t, f, window_days=1.0)
t1, f1, e1 = asymmetric_clip(t, f1, e)
bls1, p1, _ = bls_search(t1, f1, e1)
stats = bls1.compute_stats(p1, 0.1, 0.0)  # depth, duration, transit time

# Pass 2: mask in-transit points, refit trend on clean points, re-divide.
phase = ((t - stats["transit_time"][0].value) % p1) / p1
in_transit = (phase < 0.05) | (phase > 0.95)
trend = np.interp(t, t[~in_transit],
                  detrend_savgol(t[~in_transit], f[~in_transit], window_days=1.0))
f_clean = f / trend

# Pass 3: BLS on the cleaner flux, then refine.
_, _, _ = asymmetric_clip(t, f_clean, e)
bls2, p2, _ = bls_search(t, f_clean, e)
refined = refine_peak(bls2, p2)
```

### Period-doubling artifact

If BLS reports peaks at `P` and `2P` of comparable power and folding at
`P` shows two unequal dips per cycle (one transit + one secondary
eclipse, or one transit + one starspot-crossing remnant): the true
period is `2P`. Always fold at both candidates and pick the one with a
single coherent dip.

## When to give up on detrending

If after two passes the BLS spectrum is still featureless, the light
curve may genuinely lack a detectable transit. Inspect the raw flux —
if the only dips are at the rotation period with sinusoidal shape, no
transit is present. The skill cannot manufacture a signal that isn't
there.
