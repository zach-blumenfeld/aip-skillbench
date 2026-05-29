---
name: transit-least-squares
description: Transit Least Squares (TLS) algorithm for detecting exoplanet transits in light curves. Use when searching for transiting exoplanets specifically, as TLS is more sensitive than Lomb-Scargle for transit-shaped signals. Based on the transitleastsquares Python package.
compatibility: Requires Python with `transitleastsquares`, `numpy`, and (optionally) `lightkurve` and `matplotlib` installed.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Detect transiting exoplanets in a preprocessed light curve using the Transit
  Least Squares (TLS) algorithm. TLS fits actual transit-shaped models at
  every trial period, duration, and epoch — more sensitive than Lomb-Scargle
  for box-shaped transit signals. Returns the best-fit orbital period (with
  uncertainty), transit epoch, depth, duration, SNR, and SDE. Handles both
  broad initial search and ±5% refinement around a candidate, and supports
  masking a found transit to search for additional planets.

trigger_when:
  - Searching for transiting exoplanets in a stellar light curve.
  - Identifying the orbital period of a known or suspected transit signal.
  - Refining a candidate period (from Lomb-Scargle, BLS, or a coarse TLS run) to higher precision.
  - Looking for additional planets in a system where one has already been found.
  - User mentions "TLS", "transit least squares", or asks for a transit period.

do_not_use_when:
  - The science goal is a general periodic signal (rotation, pulsation, eclipsing binary) — use Lomb-Scargle.
  - The light curve has not been quality-filtered, outlier-cleaned, and detrended/flattened — run `light-curve-preprocessing` first, otherwise stellar activity will swamp the transit.
  - Flux uncertainties (`flux_err`) are completely unavailable — TLS weights points by their uncertainties and is materially less reliable without them; consider BLS or revisit the data source.

steps:
  - name: verify-preprocessing
    description: >
      Confirm the light curve has been quality-filtered (flag == 0 for TESS / Kepler),
      outlier-cleaned (e.g., 3σ clip), and detrended/flattened. TLS is a search,
      not a cleanup — stellar variability left in the curve will dominate the
      best-fit model. Delegate cleanup to `light-curve-preprocessing` if not done.
    inputs:
      - name: data_path
        type: string
        description: Path to the cleaned light-curve file (time, flux, flux_err columns).
    outputs:
      - name: lc_ready
        type: boolean
        description: True once preprocessing is confirmed; gates the broad search.

  - name: run-broad-search
    description: >
      Run TLS over its default period range to find a candidate transit signal.
      ALWAYS pass `flux_err` — the script defaults to column index 2; override
      with `--err-col` if your data has a different layout. `--no-err` is the
      explicit (and discouraged) opt-out.
    script: scripts/run_tls.py
    inputs:
      - name: data_path
        type: string
      - name: time_col
        type: integer
        nullable: true
      - name: flux_col
        type: integer
        nullable: true
      - name: err_col
        type: integer
        nullable: true
      - name: flag_col
        type: integer
        nullable: true
        description: Quality-flag column; rows with flag != 0 are dropped.
    outputs:
      - name: broad_result
        type: object
        description: JSON dict with period_days, period_uncertainty_days, T0_days, duration_days, depth, snr, sde, transits_observed, transits_in_data_gaps.

  - name: assess-candidate
    description: >
      Inspect SDE, SNR, and transit-gap warnings to decide whether the broad-search
      result is real before committing compute to refinement.

      Thresholds: SDE > 9 = very strong candidate; SDE > 6 = candidate worth
      refining; SDE < 6 = likely noise. SNR > 7 = generally reliable; SNR < 7 =
      needs additional validation. If `transits_in_data_gaps > 0`, the true
      period may be 2× the reported value — re-run the broad search with
      `--min-period` set to 1.9 × period and `--max-period` set to 2.1 × period
      and compare SDE. A low SDE can also indicate over-aggressive flattening
      that smoothed out the transit; revisit `light-curve-preprocessing` rather
      than tuning TLS in that case.
    inputs:
      - name: broad_result
        type: object
    outputs:
      - name: candidate_period_days
        type: float
        description: The period to refine; null if no candidate survived assessment.
        nullable: true
      - name: candidate_notes
        type: string
        description: Brief rationale (SDE, SNR, aliasing check outcome).
    one_of:
      - Strong candidate (SDE > 9 OR (SDE > 6 AND SNR > 7)) → proceed to refine-period
      - Aliasing suspected (transits_in_data_gaps > 0) → re-run broad-search at 2× period before refining
      - Weak signal → revisit `light-curve-preprocessing` or report no detection

  - name: refine-period
    description: >
      Re-run TLS in a narrow window around the candidate to improve period precision.
      Default refinement is ±5% (matches the canonical pattern from the curated
      SKILL.md). Widen to ±10% when the broad-search SDE was borderline; tighten
      to ±2% when the broad-search SDE was very strong.
    script: scripts/run_tls.py
    inputs:
      - name: data_path
        type: string
      - name: candidate_period_days
        type: float
      - name: refine_pct
        type: float
        nullable: true
        description: Half-width as a fraction; defaults to 0.05 (±5%).
    outputs:
      - name: refined_result
        type: object
        description: Same shape as broad_result; `period_days` is the refined value.

  - name: report-period
    description: >
      Report `refined_result.period_days`. Round per the user's contract
      (e.g., 5 decimal places). Include `period_uncertainty_days`, SDE, and
      SNR alongside when summarizing a detection.
    inputs:
      - name: refined_result
        type: object
    outputs:
      - name: reported_period_days
        type: float

  - name: mask-and-search-next
    description: >
      Optional. Mask the in-transit points of the confirmed detection and
      re-run TLS on the masked light curve to look for additional planets in
      the system. Skip this step if the task only asks for a single period.
    script: scripts/mask_transit.py
    depends_on: [report-period]
    inputs:
      - name: data_path
        type: string
      - name: refined_result
        type: object
        description: Provides period, T0, and duration for the mask.
      - name: masked_output_path
        type: string
    outputs:
      - name: masked_light_curve_path
        type: string
        description: Pass back into `run-broad-search` to search for the next planet.

integrations:
  - partner: light-curve-preprocessing
    body: >
      Runs *before* this skill. Drops bad-quality flags, removes outliers (3σ
      clip), and flattens stellar variability. Without this step TLS will fit
      the activity envelope instead of the transit.
  - partner: lomb-scargle-periodogram
    body: >
      Often runs *before* TLS for exoplanet work. LS gives a fast first-pass
      period (typically the stellar rotation period); flatten removes that
      modulation, then TLS finds the buried planetary transit.
  - partner: box-least-squares
    body: >
      Older alternative to TLS — same problem shape but less sensitive for
      realistic transit profiles. Reach for BLS only when TLS is unavailable
      or the legacy pipeline requires it.
  - partner: exoplanet-workflows
    body: >
      The umbrella playbook orchestrating preprocessing → (optional LS) →
      flatten → TLS broad search → refine → (optional mask + next planet) for
      end-to-end exoplanet period detection from a raw light curve.

scenarios:
  - need: Find the orbital period of an exoplanet from a TESS light curve dominated by starspot variability.
    context: >
      Raw data at `/root/data/tess_lc.txt` with columns time, flux, quality flag,
      flux_err. Quality flag == 0 means good data.
    action: >
      1) Preprocess with `light-curve-preprocessing` (drop flag != 0, 3σ outlier
      removal, flatten). 2) `python scripts/run_tls.py --data cleaned.csv
      --time-col 0 --flux-col 1 --err-col 2`. 3) Assess SDE and SNR. 4)
      `python scripts/run_tls.py --data cleaned.csv --refine-around <broad period>
      --refine-pct 0.05`. 5) Write the refined `period_days` rounded to 5 decimals
      to the reporting path.
    outcome: Refined orbital period to ~5-decimal precision, with SDE/SNR justifying the detection.

  - need: Search for a second planet in a confirmed transiting system.
    context: First planet found with period P1, T0=T0_1, duration=D1.
    action: >
      `python scripts/mask_transit.py --data cleaned.csv --period P1 --t0 T0_1
      --duration D1 --output masked.csv` then re-run `run_tls.py --data masked.csv`
      over the same broad range.
    outcome: Second-planet candidate identified if the masked-search SDE > 6.

  - need: Disambiguate a TLS result that might be at half the true period.
    context: Broad-search result has `transits_in_data_gaps > 0` — TLS warns transits fell into data gaps.
    action: >
      Re-run the broad search bounded to `--min-period 1.9 * P` and
      `--max-period 2.1 * P`; compare SDE between the original and the
      doubled-period result. Refine around whichever has the higher SDE.
    outcome: True period selected with explicit aliasing check.

anti_patterns:
  - Running TLS without `flux_err` — the search cannot weight points by their uncertainties, and SDE/SNR become unreliable. Use `--err-col`; reserve `--no-err` for diagnostics only.
  - Reporting the broad-search period without refining — refinement typically improves precision by an order of magnitude at low marginal compute cost.
  - Ignoring `transits_in_data_gaps > 0` — silently accepting a period that may be half the true value. Always do the 2× aliasing check when this fires.
  - Confusing a low SDE for a weak signal when the cause is over-aggressive flattening that smoothed out the transit. Re-run preprocessing with a longer flatten window before discarding the candidate.
  - Running TLS on raw, unflattened data — stellar variability dominates and produces a non-physical fit.
  - Using TLS for non-transit periodic signals (rotation, pulsation, eclipsing binaries) — reach for Lomb-Scargle.
  - Hand-tuning `oversampling_factor`, `duration_grid_step`, or `T0_fit_margin` before the basic search has converged on a candidate — these are precision dials, not detection dials.
```
