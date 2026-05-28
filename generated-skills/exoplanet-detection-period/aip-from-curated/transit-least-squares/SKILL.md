---
name: transit-least-squares
description: Transit Least Squares (TLS) algorithm for detecting exoplanet transits in light curves. Use when searching for transiting exoplanets specifically, as TLS is more sensitive than Lomb-Scargle for transit-shaped signals. Based on the transitleastsquares Python package.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Run the Transit Least Squares (TLS) algorithm to search a light
  curve for periodic transit-shaped dips: build the TLS object with
  flux uncertainties, run the power search over an appropriate
  period range, extract and interpret the candidate (period, T0,
  depth, SDE, SNR), refine narrow grids around strong candidates,
  phase-fold and overlay the model for visual validation, and mask
  found transits to iterate for multi-planet systems. Scope is the
  TLS-specific procedure on a preprocessed light curve, not raw-data
  cleaning or general algorithm selection.

trigger_when:
  - Searching a preprocessed light curve for exoplanet transits.
  - User mentions transitleastsquares, TLS, transit search, or transit-shaped signals.
  - Signal is expected to be a box-like dip (transit) rather than a sinusoid (rotation, pulsation).
  - Refining a known transit candidate for higher-precision period and epoch.
  - Searching for additional planets in a system where one transit has already been found.
  - Interpreting TLS output fields (SDE, SNR, period_uncertainty, depth, T0, folded data, model light curve).
  - Diagnosing TLS issues — flux_err errors, low SDE, 2x/0.5x period aliasing, "X of Y transits without data" warnings.

do_not_use_when:
  - The signal of interest is non-transit periodic (stellar rotation, pulsation, eclipsing-binary continuous variation) — use Lomb-Scargle instead.
  - The light curve is unprocessed and still contains bad-quality cadences, large outliers, or stellar-rotation trends — clean it first; TLS expects a flattened, outlier-removed light curve.
  - Flux uncertainties are unavailable and cannot be estimated — TLS requires them.

scope_and_approval: >
  Read-only on the input light curve — TLS operates on copies and
  produces a results object. No external network calls. Long
  searches (wide period ranges, large oversampling_factor) can take
  minutes to hours; surface a runtime estimate before kicking off
  expensive searches and prefer a broad-then-narrow strategy over a
  single dense sweep.

steps:
  - name: install
    description: >
      Ensure `transitleastsquares` is installed alongside the usual
      light-curve stack (`lightkurve`, `numpy`, `matplotlib`). If
      missing, install via `pip install transitleastsquares lightkurve
      numpy matplotlib`.
  - name: build-tls-object
    description: >
      Construct the TLS object with three arrays — time, flux, and
      flux_err — in that order. Flux uncertainties are mandatory, not
      optional; omitting them errors out and degrades weighting even
      when defaulted. Use `tls.transitleastsquares(time, flux,
      flux_err)`.
  - name: run-power-search
    description: >
      Call `.power(...)` to search for transits. Default range is
      acceptable for broad exploration; pass `period_min` and
      `period_max` (days) when the target's star type implies a
      narrower window. `show_progress_bar` and `verbose` control
      logging; leave them off in batch runs.
  - name: extract-results
    description: >
      Pull the candidate parameters from the returned results object —
      `period`, `period_uncertainty`, `T0`, `depth`, `snr`, `SDE`.
      Capture these before any further plotting or analysis so the
      candidate is recorded even if downstream visualization fails.
  - name: interpret-strength
    description: >
      Compare SDE and SNR to thresholds before treating the candidate
      as real. SDE > 9 is very strong, SDE > 6 is a strong candidate,
      SDE < 6 is weak and likely a false positive without other
      confirmation. SNR > 7 is generally considered reliable.
  - name: refine-period
    description: >
      If the candidate is strong, rerun `.power(...)` over a narrow
      window around the candidate period (typically ±2–10%) for a
      higher-precision final measurement. Narrow ranges sample the
      grid more densely without slowing the full sweep.
  - name: phase-fold-results
    description: >
      Inspect the phase-folded data and model overlay from the results
      object — `folded_phase`, `folded_y`, `model_folded_phase`,
      `model_folded_model`. A clean U or V dip aligned with the model
      validates the candidate; a noisy or asymmetric fold weakens it.
  - name: inspect-model
    description: >
      Optionally plot the full-time-range model — `model_lightcurve_time`,
      `model_lightcurve_model` — against the original light curve to
      see how the transits land relative to the data. Useful for
      catching missed-transit warnings and gap effects.
  - name: mask-and-iterate
    description: >
      For multi-planet searches, mask the detected transits with
      `transitleastsquares.transit_mask(time, period, duration, t0)`
      and rerun TLS on the residual light curve. Repeat until no
      further significant signal (SDE above threshold) appears.

decisions:
  - signal: TLS errors with "flux_err is required" or similar.
    action: Pass flux uncertainties as the third argument to `tls.transitleastsquares` — they are mandatory, not optional.
  - signal: SDE > 9 on the candidate.
    action: Treat as a very strong candidate; proceed to refinement and validation.
  - signal: SDE between 6 and 9.
    action: Treat as a strong candidate worth refining and validating, but flag remaining uncertainty.
  - signal: SDE below 6.
    action: Treat as weak / likely false positive. Reconsider preprocessing (may be over-smoothing), check for data gaps during transits, and consider whether the signal is simply too shallow to detect.
  - signal: SNR below 7.
    action: Flag the candidate as needing additional validation; do not report as a confirmed detection on TLS output alone.
  - signal: TLS warns "X of Y transits without data. The true period may be twice the given period."
    action: Suspect period aliasing from data gaps. Rerun the search at `period * 2` and inspect the phase-folded light curve at each candidate period before accepting one.
  - signal: Recovered period is exactly 2x or 0.5x the expected value.
    action: Check both periods, inspect phase-folded light curves at each, and look for odd-even depth mismatch (likely eclipsing binary) before committing.
  - signal: A strong candidate has been found and needs higher precision.
    action: Refine by rerunning `.power(...)` over ±2–10% around the candidate period for a denser grid in a smaller range.
  - signal: System may host additional transiting planets.
    action: After validating the first candidate, mask its transits with `transit_mask` and rerun TLS on the residual; repeat until no significant signals remain.
  - signal: Signal of interest is non-transit periodic (stellar rotation, pulsation).
    action: Switch to Lomb-Scargle — TLS is optimized for transit-shaped signals and is the wrong tool for sinusoidal variability.

search_shortcuts:
  - category: TLS results-object fields
    body: |
      period — best-fit period (days).
      period_uncertainty — uncertainty on the best-fit period.
      T0 — mid-transit epoch.
      depth — fractional transit depth.
      snr — signal-to-noise ratio.
      SDE — Signal Detection Efficiency (TLS-specific strength metric).
      folded_phase / folded_y — phase-folded data (0–1 phase).
      model_folded_phase / model_folded_model — folded best-fit model.
      model_lightcurve_time / model_lightcurve_model — model over full time range.
  - category: Signal-strength thresholds
    body: |
      SDE > 9 — very strong candidate.
      SDE > 6 — strong candidate.
      SDE < 6 — weak / likely false positive without further confirmation.
      SNR > 7 — generally considered reliable.
      SNR < 7 — needs additional validation.
  - category: Refinement window
    body: |
      Typical narrow rerun: ±2% to ±10% around the candidate period.
      Narrower range with the default grid = denser sampling = better precision.
  - category: Advanced .power() knobs
    body: |
      oversampling_factor — finer period grid (default 1; higher = slower but more precise).
      duration_grid_step — transit-duration sampling step (default 1.1; e.g., 1.01 = 1% steps).
      T0_fit_margin — mid-transit fitting margin (default 5; 0 = no margin, faster).
  - category: Typical parameter ranges (pipeline context)
    body: |
      Outlier removal (upstream): sigma=3–5 (lower = more aggressive).
      Period search range: match expected orbital periods for the target.
      Refinement window: ±2–10% around the candidate period.
      SDE threshold: >6 for candidates, >9 for strong detections.
  - category: Dependencies
    body: |
      pip install transitleastsquares lightkurve numpy matplotlib
  - category: Official documentation
    body: |
      TLS GitHub — https://github.com/hippke/tls
      TLS Tutorials — https://github.com/hippke/tls/tree/master/tutorials
      Lightkurve Tutorials — https://lightkurve.github.io/lightkurve/tutorials/index.html
      Lightkurve Exoplanet Examples — https://lightkurve.github.io/lightkurve/tutorials/3.1-identifying-transiting-exoplanets.html

scenarios:
  - need: Run TLS on a Lightkurve LightCurve with no prior period hypothesis.
    context: >
      Light curve has been outlier-clipped (`lc.remove_outliers(sigma=3)`)
      and flattened (`lc.flatten()`). flux_err is preserved.
    action: >
      Build TLS with `tls.transitleastsquares(lc_flat.time.value,
      lc_flat.flux.value, lc_flat.flux_err.value)` and call
      `.power(show_progress_bar=False, verbose=False)` with the default
      period range. Extract `period`, `period_uncertainty`, `T0`,
      `depth`, `snr`, `SDE` from the results object.
    outcome: >
      A candidate with TLS strength metrics, ready for SDE/SNR
      interpretation and phase-folded inspection.
  - need: Restrict the search to a known plausible period band.
    action: >
      Pass `period_min` and `period_max` (days) to `.power(...)`,
      e.g., `period_min=2.0, period_max=7.0`, and turn on progress
      logging if interactive.
    outcome: >
      Faster search bounded by the physical prior; useful when target
      star type implies a planet class.
  - need: Improve precision on a strong candidate from a broad search.
    context: >
      Initial broad sweep returned a candidate at ~3.2 days with SDE > 9.
    action: >
      Rerun `.power(period_min=3.0, period_max=3.4)` (≈±5%) on the
      same TLS object to sample more densely in the narrow window.
    outcome: >
      Smaller period_uncertainty and tighter T0 without paying the
      cost of a dense full-range sweep.
  - need: Visually validate a candidate by overlaying the model on the phase-folded data.
    action: >
      Plot `out_tls.folded_phase` vs `out_tls.folded_y` as points and
      `out_tls.model_folded_phase` vs `out_tls.model_folded_model` as
      a line; label and inspect.
    outcome: >
      Clean U/V dip aligned with the model strengthens confidence;
      noisy or asymmetric folds weaken it.
  - need: Search for a second planet after the first has been found.
    action: >
      Build a transit mask with `from transitleastsquares import
      transit_mask; mask = transit_mask(time, period, duration, t0)`,
      drop the masked cadences (`lc[~mask]`), build a new TLS object on
      the residual light curve, and rerun `.power(...)`.
    outcome: >
      A residual-light-curve search that surfaces additional
      transiting planets; repeat until no significant SDE remains.

anti_patterns:
  - Omitting flux uncertainties when constructing the TLS object — they are required, not optional, and the call will error.
  - Treating an SDE < 6 detection as confirmed without further validation.
  - Reporting the first peak without checking 2x and 0.5x harmonics for aliasing, especially when TLS warns about transits without data.
  - Ignoring the "X of Y transits without data" warning — it is the main aliasing signal TLS surfaces.
  - Running a single ultra-dense sweep across a wide period range instead of broad-then-narrow refinement (slow with no precision gain).
  - Skipping phase-folded visual inspection on borderline candidates — strength metrics alone miss obvious shape problems.
  - Stopping at the first candidate in a system that may host multiple transiting planets.
  - Using TLS for non-transit periodic signals (stellar rotation, pulsation) where Lomb-Scargle is the appropriate tool.
  - Over-aggressive upstream preprocessing that flattens the transit along with the noise, leading to low SDE on a real planet.
```
