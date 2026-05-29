---
name: exoplanet-workflows
description: General workflows and best practices for exoplanet detection and characterization from light curve data. Use when planning an exoplanet analysis pipeline, understanding when to use different methods (TLS, Lomb-Scargle, BLS), choosing period search ranges, validating candidates against SDE/SNR thresholds, or troubleshooting detection issues such as low SDE, period aliasing, or odd-even depth mismatch.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
compatibility: Requires Python 3.10+ with lightkurve, transitleastsquares, numpy, astropy.
---

```yaml
purpose: >
  Orchestrate exoplanet detection from a light curve: load, filter on
  quality flags, preprocess (outlier removal + flattening), search for a
  periodic transit signal, validate the candidate against signal-strength
  thresholds, and refine the period for final reporting. The procedure
  encodes the canonical TLS recipe (sigma=3 outlier removal, default
  flatten, +/-5% refinement window) and the validation thresholds (SDE>6
  strong, >9 very strong; SNR>=7 reliable; 3-sigma odd-even mismatch
  flags eclipsing binaries) so they apply consistently across runs.

trigger_when:
  - User asks to find an exoplanet's orbital period from a light curve.
  - User provides a TESS / Kepler / K2 light curve and wants transit detection.
  - User mentions TLS, BLS, or Lomb-Scargle in the context of planet hunting.
  - Planning or troubleshooting an exoplanet analysis pipeline.
  - A previous detection returned low SDE, an unexpected period, or
    suspected aliasing.

do_not_use_when:
  - The user wants to detect non-transit signatures (radial velocity,
    astrometry, direct imaging) — those need different methods entirely.
  - The user only needs stellar rotation or pulsation analysis with no
    planet involved — go straight to Lomb-Scargle without the transit
    pipeline.

scope_and_approval: >
  Read-only against the input light curve. Writes a single result file
  (the period) only at the path the user specifies. No network calls.
  Scripts pin numeric parameters (sigma, refine window, thresholds) from
  the workflow doc; if the user requests different values, pass them via
  the documented CLI flags rather than editing the scripts.

steps:
  - name: load-and-inspect
    description: >
      Load the light curve file and confirm the column layout
      (time, flux, quality flag, flux uncertainty). Note the time system
      (MJD/BJD/BKJD) and flag convention (TESS: 0 = good). If columns
      differ from the TESS default, pass the corresponding --time-col /
      --flux-col / --flag-col / --err-col flags to detect_period.py.
    outputs:
      - name: lc-path
        type: string
      - name: column-map
        type: object
      - name: flag-good-value
        type: float
        description: Value of the quality flag that means "keep this row".

  - name: choose-search-strategy
    description: >
      Decide whether the default TLS recipe is appropriate. The default
      fits transit-shaped dips with flux uncertainties — use it for
      exoplanet detection. Switch to Lomb-Scargle for general periodic
      signals or BLS when Astropy-only / odd-even diagnostics are needed.
      If the user has not specified, default to TLS. Load
      references/method-selection.md if you need to justify the pick.
    inputs:
      - name: column-map
        type: object
    outputs:
      - name: method
        type: string
        description: One of tls, lomb-scargle, bls.
    one_of:
      - tls
      - lomb-scargle
      - bls

  - name: pick-period-range
    description: >
      Resolve the period search range from the planet/target type. Use
      this only when the user gives a hint (hot Jupiter, habitable zone,
      etc.); otherwise let TLS auto-pick. The script returns explicit
      (period_min, period_max) in days that can be passed straight to
      detect_period.py.
    script: scripts/period_range_guide.py
    inputs:
      - name: planet-type
        type: string
        nullable: true
      - name: star-type
        type: string
        nullable: true
    outputs:
      - name: period-range
        type: object
        description: "{period_min_days, period_max_days}; null if auto-pick."
        nullable: true

  - name: run-detection-pipeline
    description: >
      Execute the canonical pipeline: quality-flag filter, sigma=3 outlier
      removal, lightkurve.flatten(), TLS broad search, then a refined TLS
      pass over +/-5% around the candidate period. This single script
      pins the numeric choices that the workflow doc recommends so they
      do not drift between runs.
    script: scripts/detect_period.py
    inputs:
      - name: lc-path
        type: string
      - name: column-map
        type: object
      - name: flag-good-value
        type: float
      - name: period-range
        type: object
        nullable: true
    outputs:
      - name: detection
        type: object
        description: >
          {period, period_rounded_5dp, period_uncertainty, sde, snr, depth,
           t0, n_points_after_filter, refined}.

  - name: validate-candidate
    description: >
      Apply the workflow's signal-strength thresholds (SDE>6 / >9, SNR>=7)
      and false-positive checks (odd-even depth mismatch > 3*depth_err,
      missing-transit aliasing warning). The script returns a classification
      and a list of issues / recommendations.
    script: scripts/validate_candidate.py
    inputs:
      - name: detection
        type: object
    outputs:
      - name: verdict
        type: object
        description: "{classification, ok_to_report, issues, recommendations}."

  - name: triage-or-report
    description: >
      If verdict.ok_to_report is true, write the period rounded to 5
      decimal places to the output path the user specified (one numeric
      value, no header). If not, read references/troubleshooting.md and
      try the suggested remediations (less aggressive sigma, longer
      flatten window, test period*2 and period/2 for aliasing) before
      reporting. Never silently report a weak (SDE<6) candidate as the
      answer.
    inputs:
      - name: verdict
        type: object
      - name: detection
        type: object
    outputs:
      - name: output-path
        type: string
        nullable: true

search_shortcuts:
  - category: Sibling skills
    body: >
      light-curve-preprocessing — outlier removal, flattening, quality
      flags. transit-least-squares — TLS algorithm details and advanced
      parameters. lomb-scargle-periodogram — fast generic periodicity.
      box-least-squares — Astropy BLS with compute_stats() validation.
  - category: Official docs
    body: >
      Lightkurve tutorials (https://lightkurve.github.io/lightkurve/tutorials/index.html);
      TLS GitHub (https://github.com/hippke/tls);
      Lightkurve section 3.1 "Identifying transiting exoplanet signals";
      section 2.3 "Removing instrumental noise";
      section 3.2 "Creating periodograms".
  - category: Key papers
    body: >
      Hippke & Heller (2019) — TLS algorithm.
      Kovacs et al. (2002) — BLS algorithm.
  - category: Dependencies
    body: "pip install lightkurve transitleastsquares numpy matplotlib scipy"
  - category: On-demand references
    body: >
      references/method-selection.md — load when justifying TLS vs LS vs BLS.
      references/troubleshooting.md — load on low SDE, odd period, no clear peak,
      or odd-even mismatch.

integrations:
  - partner: light-curve-preprocessing
    body: >
      detect_period.py inlines the canonical preprocessing recipe
      (quality filter, sigma=3 outliers, flatten). When the user needs a
      non-default sigma, window length, or iterative sine fitting, hand
      off to light-curve-preprocessing and pass its cleaned light curve
      back into the TLS step.
  - partner: transit-least-squares
    body: >
      detect_period.py wraps transitleastsquares.transitleastsquares().
      For advanced knobs (oversampling_factor, duration_grid_step,
      T0_fit_margin, transit_mask for multi-planet systems), defer to
      the transit-least-squares skill.
  - partner: box-least-squares
    body: >
      Use BLS when SDE looks fine but you want odd-even depth diagnostics
      via compute_stats(). Run BLS as a cross-check, not a replacement.
  - partner: lomb-scargle-periodogram
    body: >
      Use Lomb-Scargle as a first pass when stellar rotation dominates
      the light curve and you want to characterise it before flattening.

scenarios:
  - need: TESS light curve with stellar activity hiding a transit.
    context: >
      File at /root/data/tess_lc.txt with columns time/flux/flag/err.
      User wants the period in days, rounded to 5 dp, written to
      /root/period.txt.
    action: >
      Run scripts/detect_period.py /root/data/tess_lc.txt
      --out /root/period.txt with defaults. Pipeline filters flag==0,
      removes sigma=3 outliers, flattens, runs TLS, refines +/-5%, writes
      the rounded period. Validate the detection JSON with
      scripts/validate_candidate.py before accepting.
    outcome: >
      /root/period.txt contains a single numeric value matching the
      refined TLS period.
  - need: TLS returns SDE = 3.4 — weak detection.
    context: >
      verdict.classification = "weak"; recommendations include "longer
      flatten window" and "check data gaps".
    action: >
      Read references/troubleshooting.md. Re-run the pipeline with
      --outlier-sigma 5; if still weak, try a sibling pipeline that
      uses a longer flatten window or iterative sine fitting from
      light-curve-preprocessing. Do not write the result until SDE > 6.
    outcome: >
      Either a stronger detection or an explicit "no significant signal"
      report — never a silent low-confidence answer.
  - need: TLS warns "5 of 10 transits without data".
    context: Period may be aliased to half the true period.
    action: >
      Re-run scripts/detect_period.py with --period-min and --period-max
      bracketing 2x the candidate. Compare SDE and the phase-folded
      light curves; trust the period with the cleaner fold and lower
      odd-even mismatch.
    outcome: >
      Reported period reflects the true orbital period, not the alias.

anti_patterns:
  - Calling TLS without flux uncertainties — TLS requires flux_err as the
    third positional argument; passing None or skipping the err column
    produces wrong results, not an error.
  - Reporting a weak (SDE < 6) candidate as the final answer without
    re-checking preprocessing or aliasing.
  - Over-aggressive preprocessing (very low sigma or very short flatten
    window) that removes the transit signal along with the noise.
  - Skipping the refinement pass and reporting the broad-search period —
    the +/-5% refined pass is what brings precision to the 5-dp output.
  - Assuming flag == 0 means "bad" — for standard TESS files 0 means
    good. Verify the convention if you are not on TESS-standard data.
  - Trusting a period with high odd-even depth mismatch
    (|odd-even| > 3 * depth_err) — that signature points to an
    eclipsing binary at twice the period, not a planet.
  - Inventing period ranges from memory when the user names a planet
    type — use scripts/period_range_guide.py so the lookup is consistent.
```
