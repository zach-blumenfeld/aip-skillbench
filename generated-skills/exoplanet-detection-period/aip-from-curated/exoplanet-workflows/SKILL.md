---
name: exoplanet-workflows
description: General workflows and best practices for exoplanet detection and characterization from light curve data. Use when planning an exoplanet analysis pipeline, understanding when to use different methods, or troubleshooting detection issues.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  General guidance for exoplanet detection from light curve data:
  choose the right period-search algorithm for the signal, design
  preprocessing that strips noise without erasing planetary
  transits, validate candidates against signal-strength and
  consistency checks, and iterate on multi-planet systems. Scope is
  the end-to-end pipeline shape — data loading, quality control,
  preprocessing, period search, validation, refinement — not any
  single mission or instrument.

trigger_when:
  - Planning an exoplanet analysis pipeline from raw or reduced light curves.
  - Deciding which period-search algorithm (TLS, BLS, Lomb-Scargle) fits the signal.
  - Choosing a period range to search given target star type and expected planet types.
  - Troubleshooting weak, missing, or aliased detections (low SDE, 2x/0.5x periods, flux_err errors).
  - Validating a candidate (SDE/SNR thresholds, odd-even consistency, phase-folded inspection).
  - Searching for additional planets in a system after a first candidate is found.
  - User mentions Lightkurve, transit least squares (TLS), BLS, Lomb-Scargle, or transit detection.

steps:
  - name: load-data
    description: >
      Load the light curve and understand its format — columns,
      time system, flux units, and quality flag convention. Verify
      whether quality flag == 0 means "good" or "bad" for this
      dataset before filtering.
  - name: quality-control
    description: >
      Filter out bad cadences using the data's quality flags. Use
      the documented convention for this mission/source; do not
      assume flag == 0 is universally good.
  - name: preprocess
    description: >
      Remove instrumental and stellar noise while preserving
      planetary signals. Sigma-clip outliers (3-sigma initially,
      5-sigma after flattening) and detrend stellar-rotation trends
      that would otherwise mask transits. Visualize each step to
      confirm the data quality is improving, not over-smoothed.
  - name: choose-algorithm
    description: >
      Pick the period-search algorithm based on the expected signal
      shape and exploration goal. Transit-shaped (box-like) dips
      with flux uncertainties → TLS. Quick exploration or any
      periodic signal (rotation, pulsation) → Lomb-Scargle. BLS as
      an Astropy-native alternative to TLS, though TLS generally
      performs better for exoplanet detection.
    one_of:
      - TLS (Transit Least Squares)
      - Lomb-Scargle Periodogram
      - BLS (Box Least Squares)
  - name: choose-period-range
    description: >
      Set the search period range from target star type and
      expected planet types. Hot Jupiters 0.5-10 days; warm planets
      10-100 days; habitable zone 200-400 days around Sun-like
      stars, 10-50 days around M-dwarfs. Wider ranges are more
      complete but slower; adjust to mission duration and science
      goals.
  - name: period-search
    description: >
      Run the chosen algorithm over the chosen range. For TLS pass
      flux uncertainties as the third argument — they are required,
      not optional — and capture the candidate period, SDE, SNR,
      and transit parameters.
  - name: validate-candidate
    description: >
      Check the candidate against signal-strength and consistency
      criteria before treating it as real. Compare SDE/SNR to
      thresholds (SDE > 9 very strong, SDE > 6 strong, SNR > 7
      reliable). Phase-fold at the candidate period and inspect
      visually. Compare odd vs even transit depths for eclipsing-
      binary contamination. More transits → more confidence.
  - name: refine-period
    description: >
      If the candidate is strong, rerun the period search over a
      narrow window around the candidate period to improve
      precision for the final measurement.
  - name: iterate-for-multi-planet
    description: >
      For multi-planet systems, mask the first candidate's transits
      (see transitleastsquares.transit_mask) and rerun the period
      search on the residual light curve. Repeat until no further
      significant signals appear.

decisions:
  - signal: Signal is transit-shaped (box-like dip) and flux uncertainties are available.
    action: Use TLS — most sensitive for transits, handles grazing transits, returns transit parameters.
  - signal: Goal is fast exploration or signal is non-transit periodic (stellar rotation, pulsation).
    action: Use Lomb-Scargle — fast and general, but watch for harmonic confusion and reduced sensitivity to shallow transits.
  - signal: Need an Astropy-native transit search.
    action: Use BLS as an alternative to TLS, noting that TLS generally outperforms it for exoplanet detection.
  - signal: TLS raises a flux_err required error.
    action: Pass flux uncertainties as the third argument to TLS — they are mandatory, not optional.
  - signal: SDE is below ~6 (weak signal).
    action: Treat as low-confidence; reconsider preprocessing (may be over-smoothing), check for data gaps during transits, and accept that the signal may simply be too shallow to detect.
  - signal: Recovered period is exactly 2x or 0.5x the expected value.
    action: Suspect aliasing from data gaps or missed alternate transits. Check both periods manually, inspect phase-folded light curves at each, and look for odd-even depth mismatch.
  - signal: Odd and even transits have noticeably different depths.
    action: Flag as a likely eclipsing-binary contaminant rather than a planetary transit.
  - signal: Results vary noticeably with preprocessing choices.
    action: Compare results across preprocessing variants, plot each step, and confirm that smoothing is not erasing the signal.
  - signal: A strong candidate has been found.
    action: Refine by narrowing the search window around the candidate period for a higher-precision final measurement.
  - signal: System may host multiple transiting planets.
    action: After validating the first candidate, mask its transits with transit_mask and rerun the search on the residual; repeat until no significant signals remain.

search_shortcuts:
  - category: Expected transit depths (for sanity-checking candidates)
    body: |
      Hot Jupiters: 0.01-0.03 (1-3% dip).
      Super-Earths: 0.001-0.003 (0.1-0.3% dip).
      Earth-sized: 0.0001-0.001 (0.01-0.1% dip).
      Detection difficulty increases dramatically for smaller planets.
  - category: Period range guidelines (by target characteristics)
    body: |
      Hot Jupiters: 0.5-10 days.
      Warm planets: 10-100 days.
      Habitable zone — Sun-like star: 200-400 days.
      Habitable zone — M-dwarf: 10-50 days.
      Adjust search ranges to mission duration and expected planet types.
  - category: TLS signal-strength thresholds
    body: |
      SDE > 9: very strong candidate.
      SDE > 6: strong candidate.
      SNR > 7: reliable signal.
      SDE < 6: weak — likely false positive without other confirmation.
  - category: Official documentation
    body: |
      Lightkurve Tutorials — https://lightkurve.github.io/lightkurve/tutorials/index.html
      TLS GitHub — https://github.com/hippke/tls
      TLS Tutorials — https://github.com/hippke/tls/tree/master/tutorials
  - category: Key papers
    body: |
      Hippke & Heller (2019) — Transit Least Squares paper.
      Kovács et al. (2002) — BLS algorithm.
  - category: Lightkurve tutorial sections
    body: |
      Section 2.3: Removing instrumental noise.
      Section 3.1: Identifying transiting exoplanet signals.
      Section 3.2: Creating periodograms.
  - category: Dependencies
    body: |
      pip install lightkurve transitleastsquares numpy matplotlib scipy

anti_patterns:
  - Omitting flux uncertainties when calling TLS — they are required, not optional, and the call will error.
  - Aggressive outlier removal that erases the transit along with the noise.
  - Skipping detrending so stellar rotation masks shallow transits.
  - Assuming quality flag == 0 means "good" without checking the mission's convention.
  - Treating an SDE < 6 detection as confirmed without further validation.
  - Reporting the first peak without checking 2x and 0.5x harmonics for aliasing.
  - Ignoring odd-even depth mismatch — strong indicator of an eclipsing binary, not a planet.
  - Searching a period range that excludes the planet class implied by the host star (e.g., 0.5-10 day window on a habitable-zone Sun-like target).
  - Skipping refinement on a strong candidate and reporting the coarse-grid period.
  - Stopping at the first candidate in a system that may host multiple transiting planets.
  - Not visualizing preprocessing steps — over-smoothing goes undetected.
  - Failing to document the workflow so results are not reproducible.
```
