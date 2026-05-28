---
name: light-curve-preprocessing
description: Preprocessing and cleaning techniques for astronomical light curves. Use when preparing light curve data for period analysis, including outlier removal, trend removal, flattening, and handling data quality flags. Works with lightkurve and general time series data.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Prepare raw astronomical light curves for period analysis by
  removing the noise sources that mask or fake periodic signals —
  bad-quality cadences, outliers, instrumental and stellar trends —
  while preserving the short-duration transit-shaped dips that
  exoplanet searches depend on. Scope is the preprocessing stage of
  the light-curve pipeline (quality-flag filtering, sigma clipping,
  flattening / sine-fitting, visual verification), not the period
  search itself.

trigger_when:
  - Preparing a raw or reduced light curve for period analysis or transit detection.
  - Cleaning outliers (flares, cosmic rays) from time-series flux data.
  - Removing long-term trends (stellar rotation, instrumental drift) before periodogram or TLS/BLS.
  - Applying or interpreting data-quality flags on TESS, Kepler, or exported light-curve files.
  - User mentions lightkurve, sigma clipping, flatten, Savitzky-Golay, quality flags, or detrending.
  - Tuning preprocessing parameters (sigma threshold, flatten window_length) for a specific target.

scope_and_approval: >
  Read-only on the raw data — preprocessing operates on copies of
  the light curve. No external API calls or writes outside the
  working directory. Visualize before/after each major step;
  parameter changes that materially alter the cleaned light curve
  (e.g., switching flag convention, dropping below 3-sigma) should
  be flagged to the user with the trade-off rather than applied
  silently.

steps:
  - name: inspect-format
    description: >
      Inspect the light curve's format before touching it — columns,
      time system, flux units, presence and meaning of the quality
      flag column. Quality-flag conventions are not universal, so
      determine which value means "good" for this specific dataset
      before any filtering.
  - name: quality-control
    description: >
      Apply quality-flag filtering first, before outlier removal or
      detrending. For standard TESS files, flag == 0 means good; for
      some exported files the convention is inverted. Use the
      convention verified in inspect-format and filter time, flux,
      and flux_err together.
  - name: outlier-removal
    description: >
      Sigma-clip outliers (flares, cosmic rays, single-cadence
      glitches) after quality filtering. Default to 3-sigma; use 5+
      sigma when worried about clipping shallow transits, 2-sigma
      only when the data is unusually clean. Prefer lightkurve's
      `lc.remove_outliers(sigma=3, return_mask=True)` so the removed
      points are inspectable; fall back to a manual median/std mask
      when not using lightkurve.
  - name: detrend
    description: >
      Remove long-term variability (stellar rotation, instrumental
      drift) while preserving transit-shaped dips. Default to
      lightkurve's `lc.flatten(window_length=...)` (Savitzky-Golay)
      because it preserves short-duration features. Pick window_length
      from the data — longer than the expected transit duration,
      shorter than the stellar rotation period. Iterative sine
      fitting is an alternative for removing high-frequency stellar
      variability, but it removes periodic signals and must not be
      used when searching for periodic transits.
  - name: second-pass-outliers
    description: >
      Optional. After detrending, residual outliers often become
      visible that were hidden in the trend. Apply a second sigma
      clip (typically 5-sigma) to remove them. Skip this pass if the
      first clip and flatten left the light curve visibly clean.
  - name: verify-visually
    description: >
      Plot before and after each major step. The agent must inspect
      the plots (or surface them to the user) to confirm the
      preprocessing is improving the signal, not erasing real
      features. Use `lc.plot()` on LightCurve objects.
  - name: handoff
    description: >
      Hand off the cleaned light curve to the period-search stage
      with flux_err preserved — downstream algorithms (TLS in
      particular) require flux uncertainties and treat them as
      mandatory, not optional.

decisions:
  - signal: Quality-flag convention is unknown or undocumented for the dataset.
    action: Try both conventions (flag == 0 good vs flag != 0 good) and pick the one that produces a visibly cleaner light curve; record the choice.
  - signal: Standard TESS or Kepler file.
    action: Filter on flag == 0 (good); drop everything else.
  - signal: Exported light curve where flag == 0 means bad.
    action: Filter on flag != 0; verify against a known-clean section before trusting it.
  - signal: Looking for shallow transits (super-Earth or Earth-sized) and worried about clipping the transit.
    action: Use sigma=5 (conservative) on outlier removal and rely on detrending to handle smaller deviations.
  - signal: Data is unusually clean and only a few obvious outliers need removing.
    action: Use sigma=3 (standard) — going to sigma=2 risks clipping real variability.
  - signal: Choosing flatten window_length for TESS short-cadence data.
    action: Start at 300-500 cadences (typical TESS detrending); shorten if long-term trends remain, lengthen if shallow transits are being smoothed.
  - signal: Stellar rotation or pulsation periods are masking the signal of interest.
    action: Consider iterative sine fitting to remove the dominant periodic component — but only if the signal of interest is non-periodic. Never sine-fit when searching for periodic transits.
  - signal: First-pass clip plus flatten left residual outliers visible against a flat baseline.
    action: Run a second sigma clip (5-sigma) on the flattened light curve. Skip if the baseline already looks clean.
  - signal: A preprocessing change materially alters the recovered period or candidate strength.
    action: Compare results across preprocessing variants, plot each step, and surface the sensitivity to the user rather than picking silently.

search_shortcuts:
  - category: Outlier-removal sigma reference
    body: |
      sigma=2 — aggressive; removes more points, risk of clipping shallow transits.
      sigma=3 — standard; removes ~0.3% of data on Gaussian noise.
      sigma=5 — conservative; for shallow-transit searches.
      sigma=7 — very conservative; rarely needed.
  - category: Flatten window_length reference (cadences)
    body: |
      100-200 — remove short-term trends.
      300-500 — remove medium-term trends; typical for TESS short-cadence.
      500-1000 — remove long-term trends.
      Always: longer than expected transit duration, shorter than stellar rotation period.
  - category: Quality-flag conventions
    body: |
      Standard TESS / Kepler files — flag == 0 means GOOD; filter `flag == 0`.
      Some exported files — flag == 0 means BAD; filter `flag != 0`.
      Always verify against a known-clean section before trusting either convention.
  - category: Lightkurve API references
    body: |
      lc.remove_outliers(sigma=3, return_mask=True) — sigma-clip outliers and inspect what was removed.
      lc.flatten(window_length=500) — Savitzky-Golay detrend; preserves transit shapes.
      lc.to_periodogram() / pg.model(...) — used inside iterative sine-fitting loops.
      lc.plot() — quick visualization for before/after comparison.
  - category: Dependencies
    body: |
      pip install lightkurve numpy matplotlib
  - category: Official documentation
    body: |
      Lightkurve Preprocessing Tutorials — https://lightkurve.github.io/lightkurve/tutorials/index.html
      Removing Instrumental Noise — https://lightkurve.github.io/lightkurve/tutorials/2.3-removing-noise.html

anti_patterns:
  - Skipping the quality-flag check and assuming flag == 0 is good — the convention is inverted in some exported files.
  - Detrending before quality-flag filtering or outlier removal, so the trend fit is corrupted by bad cadences.
  - Aggressive outlier clipping (sigma=2 or lower) on a shallow-transit target — the transit gets removed with the noise.
  - Picking flatten window_length shorter than the transit duration, smoothing the transit out.
  - Picking flatten window_length longer than the stellar rotation period, leaving the trend behind.
  - Using iterative sine fitting on a search for periodic transits — it erases the very signal the period search is looking for.
  - Dropping flux_err during preprocessing; downstream algorithms (TLS in particular) require it.
  - Treating preprocessing as fire-and-forget — not plotting before/after each step means over-smoothing goes undetected.
  - Over-processing the light curve "to be safe" — more preprocessing is not always better; it removes real signals.
```
