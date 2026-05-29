---
name: box-least-squares
description: Box Least Squares (BLS) periodogram for detecting transiting exoplanets and eclipsing binaries. Use when searching for periodic box-shaped dips in light curves. Alternative to Transit Least Squares, available in astropy.timeseries. Based on Kovács et al. (2002).
compatibility: Requires Python with `astropy`, `numpy`, and (optionally) `matplotlib` installed.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Detect transiting exoplanets and eclipsing binaries in a photometric time
  series by fitting a periodic box-shaped dip and finding the (period, duration,
  depth, mid-transit time) tuple that best explains the data. Wraps
  `astropy.timeseries.BoxLeastSquares` so the agent always returns: the
  strongest peak, the top-N peaks (for harmonic / alias inspection), and the
  `compute_stats()` validation block (depth SNR, odd/even depths,
  transit_count) in one JSON payload. Encodes the conventional validation
  thresholds (depth_snr > 7, |odd − even| < 3·depth_err) as prose so the
  agent can apply them with judgement.

trigger_when:
  - Searching for a periodic transit signal in a preprocessed light curve.
  - User mentions "BLS", "Box Least Squares", or "transit periodogram".
  - Working inside the Astropy ecosystem without `transitleastsquares` installed.
  - Cross-checking a TLS candidate against an independent transit search with built-in odd/even diagnostics.
  - Eclipsing-binary or grazing-transit search where shape modelling is unnecessary.

do_not_use_when:
  - Searching for general (non-box-shaped) periodic signals such as stellar rotation or pulsation — use `lomb-scargle-periodogram` instead.
  - Maximum sensitivity to subtle or grazing transits is critical and `transitleastsquares` is available — TLS uses a physical transit shape and is generally more sensitive.
  - The light curve is dominated by stellar activity / instrumental trends — first preprocess with `light-curve-preprocessing` (quality cut, sigma clip, gentle flatten); BLS on raw data will lock onto activity, not the transit.
  - The data are evenly sampled and the user only needs a quick FFT — BLS is overkill for that.

scope_and_approval: >
  Read-only against the input light curve. The script emits JSON to stdout
  and never writes files; the calling workflow decides where to persist
  results. No network calls. Numeric defaults (duration sweep, top-N peaks,
  default `likelihood` objective) come straight from the source skill; pass
  CLI flags to override rather than editing the script.

steps:
  - name: preprocess-first
    description: >
      Verify the light curve has already been cleaned (quality-flag filter,
      sigma-clip outliers, gentle flatten). BLS hates trends and outliers —
      they create spurious peaks and inflate odd/even mismatch. If the input
      is raw, hand off to `light-curve-preprocessing` *before* running BLS.
      Preprocessing must preserve transit shape — overly aggressive flattening
      (very short window) will erase the signal.
    outputs:
      - name: clean-data-path
        type: string
        description: Path to the preprocessed light curve (whitespace-delimited columns).
      - name: column-map
        type: object
        description: Zero-based column indices for time, flux, flag, err.

  - name: select-search-config
    description: >
      Pick `--min-period` / `--max-period` (days) and the `--durations` sweep
      (days) from the science case. Defaults — `autopower` for the period grid,
      durations `0.05,0.075,0.1,0.15,0.2,0.25,0.3` — work for most hot-Jupiter
      and short-period searches. Narrow the period range when prior knowledge
      exists (refining a candidate, restricted habitable-zone search).
      Choose `--objective snr` instead of the default `likelihood` if the data
      have visible correlated noise. See `search_shortcuts` for typical ranges.
    inputs:
      - name: science_case
        type: string
        description: One of hot-jupiter, short-period, habitable-zone, eclipsing-binary, candidate-refinement, other.
    outputs:
      - name: min_period
        type: float
        nullable: true
      - name: max_period
        type: float
        nullable: true
      - name: durations_csv
        type: string
        nullable: true
        description: Comma-separated transit durations in days.
      - name: objective
        type: string
        description: "'likelihood' (default) or 'snr' (under correlated noise)."

  - name: compute-bls
    description: >
      Run BLS via `astropy.timeseries.BoxLeastSquares.autopower(durations)`,
      identify the strongest peak, run `compute_stats()` on it, and return the
      top-N peaks for harmonic/alias inspection. The script always returns
      depth, depth_err, depth_snr, odd/even depths and their mismatch in
      sigmas, and the transit count in one JSON blob.
    script: scripts/run_bls.py
    inputs:
      - name: data_path
        type: string
        description: Path to the preprocessed light curve.
      - name: column-map
        type: object
      - name: min_period
        type: float
        nullable: true
      - name: max_period
        type: float
        nullable: true
      - name: durations_csv
        type: string
        nullable: true
      - name: objective
        type: string
        nullable: true
    outputs:
      - name: strongest_period_days
        type: float
      - name: strongest_duration_days
        type: float
      - name: strongest_t0_days
        type: float
      - name: max_power
        type: float
      - name: stats
        type: object
        description: depth, depth_err, depth_snr, depth_odd, depth_even, odd_even_mismatch, odd_even_mismatch_sigma, transit_count.
      - name: top_peaks
        type: list[object]
        description: Up to N (period, duration, t0, power) tuples at local periodogram maxima, strongest first.

  - name: interpret-candidate
    description: >
      Apply the conventional BLS validation rules with judgement, not a
      blanket pass/fail. A strong candidate satisfies all of:
      `depth_snr > 7` (strong signal), `odd_even_mismatch_sigma < 3` (consistent
      transit depth — high mismatch points to an eclipsing binary at half the
      reported period), `transit_count >= 3` (more transits → more reliable),
      and a duration that is physically reasonable for the orbital period
      (a transit lasting a sizeable fraction of the period is suspicious).
      When two `top_peaks` sit at integer ratios (P and 2P, P and P/2), the
      fundamental is often the *longer* one — check the phase-folded shape
      and the odd/even mismatch at both before committing.
    inputs:
      - name: stats
        type: object
      - name: top_peaks
        type: list[object]
    outputs:
      - name: confirmed_period_days
        type: float
      - name: classification
        type: string
        description: One of strong-candidate, weak-candidate, alias, eclipsing-binary, no-signal.

  - name: phase-fold-visualize
    description: >
      Optional. Fold the cleaned light curve at the confirmed period using
      `phase = ((time - t0) % P) / P` and plot phase vs flux. A clean,
      symmetric box-shaped dip near phase 0 (and only there) confirms a
      single transiting body; two equal dips half a phase apart point to an
      eclipsing binary at twice the period.
    inputs:
      - name: data_path
        type: string
      - name: confirmed_period_days
        type: float
      - name: strongest_t0_days
        type: float

modes:
  - name: quick-search
    body: >
      Single broad `autopower` call with default durations. Use when scanning
      a fresh light curve with no prior period knowledge — the cheapest first
      pass and what `scripts/run_bls.py` does by default.
  - name: refine
    body: >
      Tight `--min-period` / `--max-period` (e.g. ±5% around a candidate from
      Lomb-Scargle or TLS) with a narrower `--durations` sweep. Use to nail
      the period precisely before reporting.
  - name: snr-objective
    body: >
      Pass `--objective snr`. Use when the light curve has visible correlated
      noise (red noise, residual trends) and the default likelihood objective
      is reporting spurious high-power peaks.

search_shortcuts:
  - category: Hot Jupiters / short-period transits
    body: "Period 0.5 – 10 days; durations 0.05 – 0.3 day. Default config covers this."
  - category: Warm / habitable-zone candidates
    body: "Period 10 – 100 days; durations 0.1 – 0.5 day. Watch the transit_count — fewer transits per baseline."
  - category: Eclipsing binaries
    body: "Period 0.1 – 30 days; expect high odd_even_mismatch if BLS locks onto half the true period."
  - category: Candidate refinement
    body: "Narrow window ±5 % around a TLS / LS candidate; durations bracketing the candidate duration."
  - category: Dependencies
    body: "pip install astropy numpy matplotlib"
  - category: Official docs
    body: "https://docs.astropy.org/en/stable/timeseries/bls.html"
  - category: Key paper
    body: "Kovács, Zucker & Mazeh (2002) — original BLS, A&A 391, 369."

integrations:
  - partner: light-curve-preprocessing
    body: >
      Runs *before* this skill. Drops bad quality flags, removes 3σ outliers,
      and flattens the light curve so BLS sees a flat baseline with transits
      on top. Skipping this step on activity-dominated data sends BLS chasing
      the stellar variability period, not the transit.
  - partner: transit-least-squares
    body: >
      Complementary, not redundant. TLS uses a physical transit shape and is
      generally more sensitive, especially to grazing transits; BLS is faster
      and ships with Astropy's `compute_stats()` validation. A common cross-
      check: run both, agree → confidence; disagree → investigate (which one
      is correct depends on data quality and transit shape).
  - partner: lomb-scargle-periodogram
    body: >
      Runs *before* this skill when the period is completely unknown — LS is
      faster for a first broad scan. Take the LS peak (or its harmonic) as a
      starting candidate, then run BLS in `refine` mode over a narrow range.
  - partner: exoplanet-workflows
    body: >
      The umbrella playbook that orchestrates preprocessing → period search
      (TLS, LS, or BLS) → validation → report. Calls this skill when the
      user explicitly asks for BLS or when the pipeline needs Astropy's
      built-in odd/even diagnostics as a cross-check.

scenarios:
  - need: First-pass transit search on a TESS light curve with no prior period guess.
    context: Light curve already preprocessed (quality cut, sigma clip, flatten).
    action: >
      Run `scripts/run_bls.py --data <path> --flag-col 2 --err-col 3`.
      Inspect `strongest_period_days`, `stats.depth_snr`, and
      `stats.odd_even_mismatch_sigma`.
    outcome: >
      JSON with the strongest peak plus top-5 peaks and full validation
      stats. Move to `interpret-candidate` to classify.
  - need: TLS reports period P; cross-check with BLS.
    context: Want an independent confirmation and the odd/even diagnostic.
    action: >
      Run `scripts/run_bls.py --data <path> --min-period <0.95·P>
      --max-period <1.05·P> --durations <bracket-around-TLS-duration>`.
      Compare BLS period to TLS period and inspect odd/even mismatch.
    outcome: >
      Periods agree within tolerance → confidence high. Disagree or BLS
      mismatch_sigma > 3 → flag for investigation.
  - need: BLS returns period P but `odd_even_mismatch_sigma` is 5.
    context: Strong signal, but odd and even transits have different depths.
    action: >
      Treat as a likely eclipsing binary at 2P. Re-run BLS with `--min-period`
      and `--max-period` bracketing `2*P` and compare. The phase-fold at 2P
      should show two distinct dips of unequal depth — classic EB signature.
    outcome: >
      Classification = eclipsing-binary; do not report as a planet.
  - need: BLS shows no clear peak.
    context: Light curve looks clean but `max_power` is low and no peak dominates.
    action: >
      First widen `--durations` (try 0.025 to 0.5 day) and `--max-period` (extend
      to half the baseline). If still flat, the preprocessing may have removed
      the transit — re-run with a longer flatten window upstream and try again.
      As a last resort, switch to `transit-least-squares` for higher sensitivity.
    outcome: >
      Either a peak surfaces under broader settings, or the run is reported as
      "no significant transit" with explicit search bounds.

anti_patterns:
  - Running BLS on raw, activity-dominated data — it will lock onto the stellar variability period, not the transit. Preprocess first.
  - Reporting the strongest peak without inspecting `top_peaks` for integer-ratio harmonics or 1-day / 1-year aliases.
  - Trusting a period with `odd_even_mismatch_sigma > 3` — that signature points to an eclipsing binary at twice the reported period, not a planet.
  - Reporting a period with `transit_count < 2` — single-transit "candidates" need a different validation pipeline entirely.
  - Calling BLS without flux uncertainties (`--err-col` unset) when the file provides them — BLS weights by 1/dy² and ignoring uncertainties degrades the fit.
  - Picking a `--durations` sweep narrower than the true transit duration — BLS will miss the signal because the box width does not match the dip.
  - Over-aggressive preprocessing (very short flatten window, very low sigma clip) that erases the transit alongside the noise — verify by overplotting raw vs cleaned before BLS.
  - Using BLS as the primary tool for non-transit periodicity (stellar rotation, pulsation) — prefer `lomb-scargle-periodogram`.
```
