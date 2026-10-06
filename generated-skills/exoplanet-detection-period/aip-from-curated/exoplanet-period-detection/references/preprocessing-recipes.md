# Preprocessing recipes

The three search scripts (`search_tls.py`, `search_bls.py`, `search_ls.py`)
all call the same `_preprocess.preprocess()` helper, which is a transit-safe
Savitzky–Golay flattener bracketed by two upper-only sigma clips:

| Stage | What | Default |
| --- | --- | --- |
| 1 | Drop non-finite rows | — |
| 2 | Upper-only sigma clip (drops flares/cosmics; keeps dips) | σ = 5 |
| 3 | Savitzky–Golay flatten (window 101 cadences, polyorder 2) | window ≈ 2 days at 30-min cadence |
| 4 | Upper-only sigma clip on the detrended flux | σ = 5 |

Both clips are **one-sided** on purpose: a symmetric clip at σ = 3–5 happily
removes a 1 % transit dip in a star with 2 ppt stellar variability, because
the dip is 5σ below the mean. Clipping only the bright wing keeps every
transit intact.

## When to override `_preprocess.preprocess` defaults

- **Short-cadence (≤2 min) data**: raise the window to ≥501 so the
  rolling trend stays longer than the transit duration.
- **Rapidly rotating active stars** (variability < 1 d): fit and divide
  out the dominant Lomb–Scargle sinusoid first (iterated sine fitting);
  then flatten; then search. See `source/light-curve-preprocessing/SKILL.md`
  for the sine-fit recipe. Beware: iterated sine fitting removes any
  periodic signal, so skip it when the transit period itself is in that
  frequency range.
- **Suspected flares or cosmic rays**: tighten sigma1 to 3 and run twice.

## Quality flag conventions

The default is TESS/Kepler: `QUALITY == 0` is good. Some exported CSVs
flip the convention so `QUALITY != 0` is good — set
`quality_good_is_zero: false` in the start input when that is the case.
`load_lightcurve.py` only applies the mask when a quality column is
actually present.

## When flux_err is missing

TLS and BLS both require per-point uncertainties for proper weighting.
`load_lightcurve.py` fabricates one when the input file does not carry
`flux_err`: it uses the median absolute deviation of the residual flux
after subtracting the median, scaled to Gaussian σ. This is good enough
for a first pass; for publication-quality numbers, provide real
uncertainties.

## Order matters

1. Quality filter first (`load_lightcurve.py`): bad cadences poison
   every later statistic.
2. Outlier clip before flattening: outliers warp the Savitzky–Golay
   trend.
3. Flatten before searching: TLS and BLS both assume the baseline is
   near 1.
4. A second gentler clip on the detrended flux catches residuals the
   first pass missed; we clip upward only, so transit dips survive.
