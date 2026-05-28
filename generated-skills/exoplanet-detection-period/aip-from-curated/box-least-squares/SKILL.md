---
name: box-least-squares
description: Box Least Squares (BLS) periodogram for detecting transiting exoplanets and eclipsing binaries. Use when searching for periodic box-shaped dips in light curves. Alternative to Transit Least Squares, available in astropy.timeseries. Based on Kovács et al. (2002).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Run the Box Least Squares (BLS) periodogram from
  `astropy.timeseries` to search a light curve for periodic
  box-shaped dips (transits, eclipsing binaries): prepare time /
  flux / flux_err arrays with units, build the `BoxLeastSquares`
  object, pick between automatic and custom period grids, choose
  the likelihood or SNR objective, extract the best (period,
  duration, transit_time, power), validate the candidate with
  `compute_stats()` (depth SNR, odd-even mismatch, transit count),
  and phase-fold to visualize. Scope is the BLS-specific procedure
  on a preprocessed light curve, not raw-data cleaning or general
  algorithm selection.

trigger_when:
  - Searching a preprocessed light curve for transiting exoplanets or eclipsing binaries.
  - User mentions BLS, BoxLeastSquares, `astropy.timeseries`, or box-shaped periodic dips.
  - Signal is expected to be a box-like dip (transit) rather than a sinusoid (rotation, pulsation).
  - Comparing BLS against Transit Least Squares (TLS) for a specific dataset.
  - Validating a transit candidate with depth SNR, odd-even mismatch, or transit count.
  - Refining a known transit candidate with a finer custom period grid around an autopower peak.
  - Diagnosing BLS issues — no clear peak, 2x/0.5x period aliasing, high odd-even mismatch.

do_not_use_when:
  - The signal of interest is non-transit periodic (stellar rotation, pulsation, smoothly varying eclipsing binaries) — use Lomb-Scargle instead.
  - The light curve is unprocessed and still contains bad-quality cadences, large outliers, or strong stellar-rotation trends — clean and detrend first (gently, to preserve transit shapes).
  - Maximum sensitivity to grazing or partial transits is the priority — prefer TLS, which uses a more sophisticated transit model.

scope_and_approval: >
  Read-only on the input light curve — BLS operates on copies and
  returns a periodogram object. No external network calls. A wide
  period range combined with many durations and a fine custom grid
  can take a long time on long time series; prefer a broad
  `autopower()` first, then a narrow `power()` rerun around
  promising candidates rather than one ultra-dense sweep. Surface a
  runtime estimate before kicking off expensive searches.

steps:
  - name: install
    description: >
      Ensure `astropy` is available (BLS lives in
      `astropy.timeseries.BoxLeastSquares`). Also have `numpy` and
      `matplotlib` for analysis and plotting. If missing, install
      via `pip install astropy numpy matplotlib`. Optionally install
      `lightkurve` for upstream preprocessing.
  - name: prepare-data
    description: >
      Build three arrays — time, flux, and flux_err — and attach
      time units (`time * u.day`). Passing `dy=flux_err` is optional
      but strongly recommended; without it BLS cannot weight points
      and validation statistics are degraded. Ensure upstream
      preprocessing (quality filtering, outlier removal, gentle
      detrending) has preserved transit shapes.
  - name: build-bls-object
    description: >
      Construct the model with `model =
      BoxLeastSquares(t, y, dy=dy)`. The object holds the data; the
      grid and objective are picked at search time.
  - name: choose-grid-method
    description: >
      Pick `autopower(duration)` for initial broad searches (Astropy
      builds a conservative period grid for you) or `power(periods,
      duration)` when you need a custom grid. Period grid quality
      matters for BLS — too coarse and the true period is missed.
    one_of:
      - autopower
      - power
  - name: pick-objective
    description: >
      Choose the objective function. Default is `likelihood`
      (maximizes statistical likelihood of the model fit). Switch to
      `objective='snr'` (signal-to-noise of the depth) when
      correlated noise is suspected — SNR tends to be more reliable
      in that regime.
    one_of:
      - likelihood
      - snr
  - name: run-search
    description: >
      Run the periodogram. For autopower, pass a single duration
      (`0.2 * u.day`) or an array of candidate durations
      (`np.linspace(0.05, 0.3, 10) * u.day`) so BLS tries multiple
      transit widths. For power, supply both the period grid and
      duration(s).
  - name: extract-peak
    description: >
      Find the maximum power index with `np.argmax(periodogram.power)`
      and pull `period`, `duration`, `transit_time`, and `power`
      from that index. Capture these before plotting so the
      candidate is recorded even if downstream visualization fails.
  - name: compute-stats
    description: >
      Call `model.compute_stats(period, duration, transit_time)` for
      the candidate to retrieve `depth`, `depth_err`, `depth_snr`,
      `depth_odd`, `depth_even`, and `transit_count`. These are the
      validation metrics — don't skip this on borderline peaks.
  - name: validate-candidate
    description: >
      Apply the validation criteria. Treat depth SNR > 7 as a strong
      signal, multiple observed transits as more reliable, and
      transit duration as plausible for the period. Flag the
      candidate when `abs(depth_odd - depth_even) > 3 * depth_err` —
      a significant odd-even mismatch usually means an eclipsing
      binary or instrumental artifact, not a planet.
  - name: refine-grid
    description: >
      For a promising candidate, rerun BLS with a finer custom
      period grid around it using `model.autoperiod(durations,
      minimum_period=..., maximum_period=...)` to get a conservative
      grid, then `model.power(periods, durations)`. Narrow ranges
      sample more densely without slowing the full sweep.
  - name: phase-fold-results
    description: >
      Phase-fold the light curve at the best period
      (`phase = ((time.value - t0.value) % period.value) /
      period.value`) and plot flux vs phase. A clean box-shaped dip
      aligned with the expected duration validates the candidate; a
      noisy or asymmetric fold weakens it.

decisions:
  - signal: First exploratory search with no period prior.
    action: Use `autopower(durations)` with an array of candidate transit durations and the default `likelihood` objective. Refine later with `power()` once a peak emerges.
  - signal: Correlated noise is suspected in the light curve.
    action: Switch to `objective='snr'` — SNR-based selection tends to be more reliable than likelihood when noise is correlated.
  - signal: A strong candidate is found and needs higher precision.
    action: Rerun with `model.autoperiod(...)` over a narrow window around the candidate period, then `model.power(periods, durations)` — denser sampling in a small range without paying for a full-range fine sweep.
  - signal: depth SNR > 7 on the candidate.
    action: Treat as a strong signal; proceed to phase-fold validation and odd-even check.
  - signal: depth SNR < 7 on the candidate.
    action: Flag as needing additional validation — do not report as a confirmed detection on BLS output alone. Reconsider whether the transit is too shallow or preprocessing too aggressive.
  - signal: abs(depth_odd - depth_even) > 3 * depth_err.
    action: Warn that the candidate is likely not planetary — most often an eclipsing binary or instrumental artifact. Do not commit without independent confirmation.
  - signal: No clear peak in the periodogram.
    action: Try a wider range of durations, extend the period search range, check whether preprocessing has flattened the transit, and look at the raw data for visible dips before concluding nothing is there.
  - signal: Recovered period is exactly 2x or 0.5x the expected value.
    action: Suspect period aliasing from data gaps or missing alternating transits. Check both candidate periods, inspect phase-folded plots at each, and use odd-even depth comparison to disambiguate.
  - signal: Need detailed validation statistics for a transit candidate.
    action: Use BLS over TLS for this step — `compute_stats()` gives a richer per-candidate validation block (depth, depth_err, depth_snr, depth_odd, depth_even, transit_count) than the TLS results object.
  - signal: Maximum sensitivity to grazing or partial transits is required.
    action: Prefer TLS — its transit model handles grazing transits better than BLS's box. BLS remains a fast cross-check.
  - signal: Signal of interest is general periodic variability (stellar rotation, pulsation), not transits.
    action: Switch to Lomb-Scargle — BLS is optimized for box-shaped dips and is the wrong tool for sinusoidal variability.

search_shortcuts:
  - category: BLS periodogram fields
    body: |
      period — array of trial periods searched.
      power — periodogram power at each (period, duration) pair.
      duration — best transit duration at each grid point (when multiple durations searched).
      transit_time — best mid-transit time (T0) at each grid point.
  - category: compute_stats() fields
    body: |
      depth — fractional transit depth.
      depth_err — uncertainty on the depth.
      depth_snr — signal-to-noise of the depth (validation threshold > 7).
      depth_odd — depth measured on odd-numbered transits.
      depth_even — depth measured on even-numbered transits.
      transit_count — number of transits observed in the data.
  - category: autopower vs power
    body: |
      autopower(duration) — Astropy picks a conservative period grid; good for initial broad searches.
      power(periods, duration) — caller-supplied period grid; use for refinement or full control.
      autoperiod(durations, minimum_period=..., maximum_period=...) — conservative grid generator you can feed into power().
  - category: Objective functions
    body: |
      likelihood (default) — maximizes statistical likelihood of the model fit; default first choice.
      snr — uses the SNR with which transit depth is measured; more robust under correlated noise.
  - category: Validation thresholds
    body: |
      depth_snr > 7 — strong signal.
      abs(depth_odd - depth_even) < 3 * depth_err — consistent transit depth (passes odd-even check).
      transit_count multiple — more reliable than a single observed transit.
      duration plausible for orbital period — sanity check on transit width.
  - category: Typical parameter ranges (pipeline context)
    body: |
      Transit duration scan: ~0.05 to 0.3 day (10 steps) for general searches.
      Period search range: match expected orbital periods for the target.
      Refinement window: narrow `autoperiod()` around the candidate period.
      Outlier removal (upstream): use gentle methods (e.g., lightkurve `flatten()`) so transits survive.
  - category: Dependencies
    body: |
      pip install astropy numpy matplotlib
      Optional upstream preprocessing: pip install lightkurve
  - category: Official documentation
    body: |
      Astropy BLS — https://docs.astropy.org/en/stable/timeseries/bls.html
      Astropy Time Series Guide — https://docs.astropy.org/en/stable/timeseries/
  - category: Key papers
    body: |
      Kovács, Zucker, & Mazeh (2002) — original BLS paper, A&A 391, 369. https://arxiv.org/abs/astro-ph/0206099
      Hartman & Bakos (2016) — VARTOOLS implementation, A&C 17, 1. https://arxiv.org/abs/1605.06811
  - category: Related resources
    body: |
      Lightkurve Tutorials — https://lightkurve.github.io/lightkurve/tutorials/
      TLS GitHub — https://github.com/hippke/tls (alternative transit detection method)

scenarios:
  - need: Minimal BLS run on a preprocessed light curve with one candidate duration.
    context: >
      Time array in days with units attached, flux and flux_err
      available, no prior period hypothesis.
    action: >
      `model = BoxLeastSquares(t, y, dy=dy)`; `periodogram =
      model.autopower(0.2 * u.day)`; `best_period =
      periodogram.period[np.argmax(periodogram.power)]`.
    outcome: >
      A best-period candidate ready for `compute_stats()`
      validation and phase-folded inspection.
  - need: Search multiple plausible transit durations in one pass.
    action: >
      Build a duration array (`durations = np.linspace(0.05, 0.3,
      10) * u.day`), call `model.autopower(durations,
      objective='likelihood')`, and `argmax` over `periodogram.power`
      — `duration` and `transit_time` arrays carry the best width
      and T0 at each grid point.
    outcome: >
      A best (period, duration, transit_time, power) tuple from a
      single broad sweep.
  - need: Validate a candidate with depth SNR and odd-even mismatch.
    action: >
      `stats = model.compute_stats(period, duration, transit_time)`;
      check `stats['depth_snr']`, compare `stats['depth_odd']` vs
      `stats['depth_even']` against `3 * stats['depth_err']`, and
      record `stats['transit_count']`.
    outcome: >
      A validated candidate (or a flagged false-positive when the
      odd-even mismatch exceeds the threshold).
  - need: Refine a strong autopower candidate with a custom grid.
    context: >
      Broad `autopower()` sweep returned a peak near a known
      plausible period; want denser sampling around it.
    action: >
      `periods = model.autoperiod(durations, minimum_period=p_lo *
      u.day, maximum_period=p_hi * u.day)`; `periodogram =
      model.power(periods, durations)`.
    outcome: >
      A higher-resolution periodogram around the candidate without
      paying the cost of a dense full-range search.
  - need: Rank the top 5 candidate periods and validate each.
    action: >
      `sorted_idx = np.argsort(periodogram.power)[::-1][:5]`; loop
      over the indices, pull each (period, duration, transit_time),
      run `compute_stats(...)`, and print depth_snr / transit_count
      for comparison.
    outcome: >
      A ranked candidate list with per-candidate validation —
      useful for picking the real signal when multiple peaks
      compete.
  - need: Phase-fold and plot to visually validate a candidate.
    action: >
      `phase = ((time.value - t0.value) % period.value) /
      period.value`; `plt.plot(phase, flux, '.')`. Optionally
      sort-by-phase before plotting for a cleaner line.
    outcome: >
      A phase-folded scatter — a clean box-shaped dip aligned with
      the expected duration validates the candidate.

anti_patterns:
  - Skipping `dy=flux_err` when building the BoxLeastSquares object — without it BLS cannot weight points and validation statistics are degraded.
  - Running BLS on raw, untrended data and concluding the planet is missing — stellar variability and outliers can drown the transit.
  - Over-aggressive preprocessing (large-window detrending, harsh sigma-clipping) that flattens the transit along with the noise, leading to no peak on a real planet.
  - Trusting a peak from a single duration when the true transit width is unknown — pass an array of durations to `autopower()` instead.
  - Reporting the first peak without checking 2x and 0.5x harmonics for aliasing, especially when data has large gaps.
  - Skipping `compute_stats()` and treating raw periodogram power as the only candidate metric — depth_snr and the odd-even check catch many false positives.
  - Ignoring a significant odd-even depth mismatch — that signal usually means eclipsing binary or instrumental artifact, not a planet.
  - Using a too-coarse custom period grid with `power()` and missing the true period — BLS is more grid-sensitive than Lomb-Scargle.
  - Using BLS for non-transit periodic signals (stellar rotation, pulsation) where Lomb-Scargle is the appropriate tool.
```
