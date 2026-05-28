---
name: lomb-scargle-periodogram
description: Lomb-Scargle periodogram for finding periodic signals in unevenly sampled time series data. Use when analyzing light curves, radial velocity data, or any astronomical time series to detect periodic variations. Works for stellar rotation, pulsation, eclipsing binaries, and general periodic phenomena. Based on lightkurve library.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute and interpret a Lomb-Scargle periodogram on an unevenly
  sampled time series — typically an astronomical light curve from
  Kepler, K2, or TESS — to detect periodic signals: build a
  LightCurve, run `to_periodogram(...)` over an appropriate period
  range, plot it in period view, identify the dominant peak and
  inspect for harmonics or aliases, and optionally fit a model
  light curve at the recovered frequency. Scope is the
  Lomb-Scargle-specific procedure on a prepared light curve, not
  raw-data cleaning or transit-specific detection.

trigger_when:
  - Searching unevenly sampled astronomical time series for periodic signals.
  - Analyzing Kepler, K2, or TESS light curves for stellar rotation, pulsation, or eclipsing-binary periods.
  - User mentions Lomb-Scargle, periodogram, lightkurve `to_periodogram`, or "find the period."
  - Initial period reconnaissance before a transit-specific search (Lomb-Scargle then TLS/BLS).
  - Plotting a periodogram and unsure whether to use period or frequency view.
  - Picking a search range (`minimum_period`, `maximum_period`) for a specific science case (rotation, transit, pulsation, eclipsing binary).
  - Interpreting multiple peaks — distinguishing harmonics, aliases, and the fundamental period.
  - Building a model light curve from the recovered frequency for visual validation.

do_not_use_when:
  - Searching specifically for exoplanet transit-shaped (box-like) dips — use Transit Least Squares (TLS) or Box Least Squares (BLS) instead; they are more sensitive to transit shapes.
  - The signal of interest is non-periodic (single flare, secular trend, instrumental drift) — periodograms assume a periodic component.

scope_and_approval: >
  Read-only on the input light curve — `to_periodogram(...)` returns
  a periodogram object without mutating the source. No external
  network calls. Very wide period ranges or oversampled grids can be
  slow on long time series; prefer a science-case-bounded range over
  an unrestricted default sweep.

steps:
  - name: install
    description: >
      Ensure `lightkurve`, `numpy`, and `matplotlib` are installed.
      If missing, install via `pip install lightkurve numpy matplotlib`.
  - name: build-light-curve
    description: >
      Construct a `lightkurve.LightCurve` from time, flux, and flux
      errors — `lk.LightCurve(time=time, flux=flux, flux_err=error)`.
      Use a prepared time series; raw cadences with large outliers or
      strong trends should be cleaned upstream before period search.
  - name: choose-period-range
    description: >
      Pick `minimum_period` and `maximum_period` based on the science
      case (stellar rotation, transit, eclipsing binary, pulsation) —
      see the period-range search shortcut. A bounded range is faster
      and reduces aliasing from extreme periods.
  - name: compute-periodogram
    description: >
      Call `lc.to_periodogram(...)`. Pass `maximum_period=` and
      optionally `minimum_period=` for the chosen range. The returned
      periodogram exposes `period_at_max_power`, `max_power`, and
      `frequency_at_max_power` as the primary candidates.
  - name: extract-strongest-period
    description: >
      Read the candidate period and power from the periodogram —
      `pg.period_at_max_power` and `pg.max_power`. Record these
      before any further visualization so the candidate is captured
      even if plotting fails.
  - name: plot-periodogram
    description: >
      Plot in period view, not frequency — `pg.plot(view='period')`,
      then label the period axis. The default `view='frequency'`
      shows 1/period and is easy to misread. Period view makes the
      dominant peak human-readable in days.
  - name: inspect-peaks
    description: >
      Look for a single dominant peak vs. multiple competing peaks.
      Check whether peaks at period/2 and period*2 are present
      (likely harmonics of the fundamental) and whether very short
      periods could be aliases of longer ones. The strongest peak
      is not always the true period.
  - name: fit-model
    description: >
      Optionally build a model light curve at the recovered
      frequency — `pg.model(time=lc.time, frequency=pg.frequency_at_max_power)`
      — and overlay it on the data for visual validation. A clean
      sinusoidal match strengthens the candidate; a poor fit
      suggests the wrong peak, a harmonic, or a non-sinusoidal
      signal that wants a different method.

decisions:
  - signal: A single strong, isolated peak well above the surrounding power.
    action: Treat as the likely true period. Proceed to optional model fitting for visual validation.
  - signal: Multiple peaks at period, period/2, and period*2.
    action: Suspect harmonics; the longest of the three is typically the fundamental. Phase-fold at each candidate before committing.
  - signal: A very short period dominates but seems implausible for the science case.
    action: Suspect aliasing — check whether period*N (N small integer) lands on a more physically plausible value, and inspect the phase-folded data at each.
  - signal: Plot is hard to read or peaks appear at unexpectedly high frequencies.
    action: Switch to `pg.plot(view='period')` — the frequency-view default flips the axis and is easy to misinterpret.
  - signal: Signal of interest is a transit-shaped dip rather than a sinusoid.
    action: Switch to Transit Least Squares (TLS) or Box Least Squares (BLS); Lomb-Scargle is optimized for sinusoidal variability, not box-shaped transits.
  - signal: Periodogram is dominated by long-period power with no clear peak.
    action: Suspect a residual trend or slow systematic in the light curve. Detrend or flatten upstream and recompute.
  - signal: User has not yet narrowed the period range and the default sweep is slow.
    action: Pick `minimum_period`/`maximum_period` from the science-case shortcut (rotation, transit, eclipsing binary, pulsation) before rerunning.

search_shortcuts:
  - category: Periodogram-object fields
    body: |
      period_at_max_power — best-fit period (days, with units).
      max_power — power at the dominant peak.
      frequency_at_max_power — corresponding frequency (1/period).
      period — full array of sampled periods.
      power — full array of sampled powers.
      model(time=..., frequency=...) — synthesizes a model light curve at the chosen frequency.
      plot(view='period' | 'frequency') — render the periodogram.
  - category: Period ranges by science case
    body: |
      Stellar rotation — 0.1 to 100 days.
      Exoplanet transits — 0.5 to 50 days (most common).
      Eclipsing binaries — 0.1 to 100 days.
      Stellar pulsations — 0.001 to 1 day.
  - category: Plotting conventions
    body: |
      Always pass `view='period'` for period-axis plots; default `view='frequency'` shows 1/period and misleads.
      Label the period axis explicitly ("Period [days]") and the power axis ("Power").
  - category: Interpretation heuristics
    body: |
      Single dominant peak — likely the true period.
      Peaks at period/2 and period*2 — likely harmonics; the longest is usually fundamental.
      Implausibly short period dominating — suspect aliasing; check period*N for plausible N.
      High power alone is not proof — confirm via phase-fold or model overlay.
  - category: Dependencies
    body: |
      pip install lightkurve numpy matplotlib
  - category: Official documentation
    body: |
      Lightkurve Tutorials — https://lightkurve.github.io/lightkurve/tutorials/index.html
      Lightkurve Periodogram Documentation — https://docs.lightkurve.org/

integrations:
  - partner: Transit Least Squares (TLS)
    body: |
      Lomb-Scargle is a general periodic-signal finder; TLS is specialized
      for exoplanet transit shapes and is more sensitive to box-like dips.
      Common pattern — run Lomb-Scargle first for a broad period
      reconnaissance, then run TLS for transit-specific refinement and
      candidate detection.
  - partner: Box Least Squares (BLS)
    body: |
      Alternative transit-detection method. Like TLS, prefer over
      Lomb-Scargle when the target signal is a transit-shaped dip rather
      than a sinusoidal variation.

scenarios:
  - need: Find the dominant period in a TESS light curve with no prior period hypothesis.
    action: >
      Build a LightCurve, call
      `pg = lc.to_periodogram(maximum_period=15)`, read
      `pg.period_at_max_power` and `pg.max_power`, then
      `pg.plot(view='period')` to confirm a clean dominant peak.
    outcome: >
      A candidate period in days with associated power, ready for
      harmonic/alias checks and optional model overlay.
  - need: Restrict the search to plausible exoplanet transit periods.
    action: >
      Pass `pg = lc.to_periodogram(minimum_period=0.5, maximum_period=50)`
      to bound the sweep, then inspect the periodogram and dominant peak.
    outcome: >
      Faster, science-case-appropriate search that avoids spurious
      ultra-short or ultra-long peaks.
  - need: Validate a candidate period visually with a model overlay.
    action: >
      Take `frequency = pg.frequency_at_max_power`, build
      `model = pg.model(time=lc.time, frequency=frequency)`, then
      plot `lc` and `model` together with `matplotlib`.
    outcome: >
      Side-by-side data vs. model plot; a clean phase match strengthens
      confidence, a poor fit signals a harmonic, alias, or non-sinusoidal
      signal.
  - need: Use Lomb-Scargle as the first stage of an exoplanet-period workflow.
    action: >
      Run Lomb-Scargle over the broad transit range
      (`minimum_period=0.5, maximum_period=50`) to reconnoiter periodic
      power, then hand the candidate window to TLS for transit-specific
      refinement.
    outcome: >
      A two-stage period search — broad sinusoidal scan followed by
      transit-shaped detection — that combines Lomb-Scargle's generality
      with TLS's transit sensitivity.

anti_patterns:
  - Plotting with the default `view='frequency'` and reading peak locations as periods — always use `view='period'` for period-axis plots.
  - Reporting `period_at_max_power` without checking for harmonics at period/2 and period*2.
  - Accepting an implausibly short dominant period without checking whether it is an alias of a longer one.
  - Using Lomb-Scargle as the primary tool for transit-shaped (box-like) signals where TLS or BLS is more sensitive.
  - Running an unbounded full-range default sweep when the science case implies a narrow plausible band.
  - Treating high power alone as proof of a real signal without phase-folded or model-overlay validation.
  - Computing a periodogram on a light curve that still contains large outliers or strong trends, which dominate the power spectrum at long periods.
```
