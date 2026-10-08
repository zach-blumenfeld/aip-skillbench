---
name: exoplanet-transit-period
description: Find a transiting exoplanet's orbital period from a light curve (TESS/Kepler text file with time, flux, quality flag, flux error). Quality-flag filtering, transit-safe outlier removal, stellar-variability detrending (Lomb-Scargle diagnosis, lightkurve flatten, sine prewhitening), Transit Least Squares search with a BLS cross-check, alias (P/2, 2P) and odd-even vetting, narrow-window refinement with masked re-detrending, and reporting the period in the requested format. Use for exoplanet detection, transit period finding, TLS/BLS/Lomb-Scargle period searches on light curves.
compatibility: Python 3 with numpy, scipy, astropy, lightkurve, transitleastsquares and matplotlib (the task container ships them).
metadata:
  aip-version: "0.5a1"
---

# AIP runtime — format 0.5a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. You may change the state before any step runs; you have the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; merge it over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the next step's `inputs`; merge them over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Measure the orbital period of a transiting exoplanet from a photometric light curve
  and deliver it in the format the task asks for. Scripts carry the pipeline the
  curated exoplanet skills describe (quality flags -> outliers -> detrend -> TLS search
  -> refine -> validate) with transit-safe defaults: upward-only outlier clipping, a
  flatten window sized between transit duration and rotation period, a guard that stops
  a deep transit from being fitted away as stellar variability, a BLS cross-check,
  alias and odd-even diagnostics with red-noise-aware errors, re-detrending with the
  transits masked, a narrow dense TLS plus trapezoid polish for precision, and SDE/SNR
  validation on the broad-search statistics.

trigger_when:
  - A task asks for the orbital period of an exoplanet, transit, or periodic dip in a light curve file (TESS, Kepler, K2, ground-based).
  - A light curve has stellar variability (rotation, pulsation) that must be removed before a transit search.
  - Someone asks to run Transit Least Squares, Box Least Squares, or a Lomb-Scargle period search on photometry to find a planet.
  - A transit period must be refined to high precision, or a candidate period must be checked for P/2 or 2P aliasing.

do_not_use_when:
  - The goal is the stellar rotation or pulsation period itself, not a transit; use a Lomb-Scargle periodogram directly.
  - The data are radial velocities or astrometry rather than photometric flux.
  - Only a target name is given and the light curve must first be downloaded (fetch it, then start here with the file path).

steps:
  - name: prepare-light-curve
    kind: execution
    description: Load the file, apply the quality-flag convention, clip flares, diagnose stellar variability, flatten (sine-prewhiten if needed), clip again.
    inputs:
      - name: task_request
        type: string
        description: The task's instructions verbatim (output file, precision, any period range or target hints).
      - name: lc_path
        type: string
        description: Absolute path to the light-curve text file (columns from '# columnN:' headers, else time, flux, flag, flux_err).
      - name: period_min
        type: float
        description: Minimum search period in days; 0 for auto. Set only when the task or target type implies a range.
      - name: period_max
        type: float
        description: Maximum search period in days; 0 for auto (baseline/2, so at least two transits).
    script: scripts/prepare.py
    assets:
      - assets/config.json
    timeout: 600
    inputs_to: search-period

  - name: search-period
    kind: execution
    description: Broad TLS search with flux_err, BLS cross-check, top peaks, SDE at P/2 and 2P, phase-0.5 dip, odd-even depths, vet flags, diagnostic folds.
    inputs:
      - name: clean_lc_path
        type: string
        description: Flattened, cleaned light curve (.npz) written by prepare-light-curve.
      - name: period_min
        type: float
      - name: period_max
        type: float
    script: scripts/search.py
    assets:
      - assets/config.json
    timeout: 1800
    inputs_to: vet-candidate

  - name: vet-candidate
    kind: decision
    description: Judge whether the TLS candidate is a credible transit and whether the true period is P, 2P or P/2.
    inputs:
      - name: candidate_period
        type: float
        description: Best broad-search TLS period in days.
      - name: search_summary
        type: object
        description: tls (SDE, snr, depth, duration, odd-even, transit counts), alias_checks, top_peaks, bls, vet_flags. View search.png in plots when available.
      - name: prep_summary
        type: object
        description: Preprocessing diagnostics (flag convention, gaps, variability, flatten window, notes).
    questions:
      period_choice:
        type: choice
        instructions: >
          Which multiple of the TLS candidate is the true orbital period? Use
          alias_checks (odd_even.mismatch_sigma, dip_at_phase_0p5, its depth ratio to
          phase 0, sde_at_half_period, sde_at_double_period), tls.empty_transit_count,
          the BLS relation_to_tls and top_peaks, and the folds at P, 2P and P/2 in
          search.png. A higher SDE at P than at P/2 or 2P is normal and not by itself a
          reason to switch.
        criteria:
          as_found: Odd and even depths agree (mismatch at most ~3 sigma), no comparable dip at phase 0.5, and the fold at P shows one clean transit; the default.
          double: Odd and even depths differ significantly (more than 3 sigma), or the fold at 2P shows the alternate events absent or clearly different (eclipsing-binary primary/secondary, or every other dip missing in gaps).
          half: A dip of comparable depth (ratio above ~0.7, more than 3 sigma) sits at phase 0.5 of the fold at P, and the fold at P/2 shows one clean transit with every event present.
      signal_credible:
        type: noul
        instructions: >
          Is the candidate a credible periodic transit worth refining? Weigh the TLS SDE
          (above 6 strong, above 9 very strong, below 6 weak), SNR (above 7 reliable),
          at least 2 transits with data, a transit-shaped dip in the fold, a duration
          reasonable for the period (vet_flags warns when it is not), and whether BLS
          finds the same period or a harmonic.
        criteria:
          true: SDE at least 6; SNR above 7 from TLS, or from BLS depth_snr when BLS finds the same period; two or more transits with data; a transit-shaped dip; not at gap edges, not a single event, not the stellar variability period.
          false: SDE below 6; or neither TLS SNR nor a same-period BLS depth_snr exceeds 7; or a single event; or the dip sits at data-gap edges or is not transit-shaped; or the period matches the stellar variability period or a harmonic of it (compare with prep_summary.variability.dominant_period_days; vet_flags also says so).
    thresholds:
      period_choice: 0.75
      signal_credible: 0.2
    inputs_to: credible-router

  - name: credible-router
    kind: router
    description: Credible candidates go straight to refinement; weak or suspicious ones are investigated first.
    branch_on: signal_credible
    branches:
      "true": refine-period
      "false": investigate-signal

  - name: investigate-signal
    kind: client_task
    description: Diagnose a weak or suspicious candidate by re-running preprocessing and search with targeted overrides, then pick the best candidate.
    inputs:
      - name: task_request
        type: string
      - name: lc_path
        type: string
      - name: candidate_period
        type: float
      - name: search_summary
        type: object
      - name: prep_summary
        type: object
    template: assets/investigate.md
    references:
      - path: references/validation-troubleshooting.md
        description: Thresholds, alias and odd-even rules, and fixes for low SDE, 2x/0.5x periods, preprocessing-dependent results. Load first.
      - path: references/preprocessing.md
        description: Flag conventions, outlier sigma choices, flatten window rules, sine prewhitening code and caveats. Load when changing preprocessing.
      - path: references/period-search-methods.md
        description: TLS/BLS/Lomb-Scargle APIs, period-range guidelines, refinement and multi-planet masking. Load when changing the search.
    inputs_to: refine-period

  - name: refine-period
    kind: execution
    description: Adopt P, 2P or P/2, re-flatten with transits masked, run a narrow dense TLS (+/-5%), polish with a trapezoid fit, and validate.
    inputs:
      - name: clean_lc_path
        type: string
      - name: candidate_period
        type: float
      - name: period_choice
        type: string
        description: as_found, double or half.
      - name: search_summary
        type: object
    script: scripts/refine.py
    assets:
      - assets/config.json
    timeout: 1800
    inputs_to: report-answer

  - name: report-answer
    kind: client_task
    description: Deliver the period exactly as the task asks (file, units, decimals) with a short validation report.
    inputs:
      - name: task_request
        type: string
      - name: final_period
        type: float
        description: Refined orbital period in days.
      - name: period_uncertainty
        type: float
      - name: refine_summary
        type: object
        description: Refined TLS, trapezoid polish, final_method, validation checks, notes, optional second-planet search.
    template: assets/report.md
    references:
      - path: references/validation-troubleshooting.md
        description: Load when refine_summary.validation.validated is false, to explain which check failed.
    inputs_to: end

  - name: end
    kind: end
    description: The orbital period delivered in the requested format, with uncertainty and a validation report.
    inputs:
      - name: final_period
        type: float
      - name: period_uncertainty
        type: float
      - name: answer
        type: string
        description: The answer exactly as delivered (e.g. the text written to the requested output file).
      - name: report
        type: string

anti_patterns:
  - Running TLS without flux_err. TLS needs uncertainties to weight points; if the file has none, use the point-to-point scatter as a constant error.
  - Assuming flag 0 means bad (or good) without checking. Standard TESS uses flag 0 = good; some exports invert it. Compare the scatter of both subsets.
  - Symmetric sigma clipping of the raw light curve. Transits are negative outliers; clip upward (flares, cosmic rays) only, and remove downward points only when they are isolated single-cadence glitches.
  - Flattening before removing outliers, or with a window shorter than about three transit durations or longer than the rotation period. Set the window in days and convert to an odd cadence count.
  - Sine-prewhitening (iterative sine fitting) when the dominant Lomb-Scargle peak is the transit itself; it deletes the planet.
  - Using Lomb-Scargle to measure a transit period; it is less sensitive to shallow transits and confuses harmonics. Use TLS, with BLS as a cross-check.
  - Comparing a narrow refine-window SDE with the 6/9 thresholds. SDE is normalised over the searched range; use the broad-search SDE.
  - Reporting the broad-search period as final. Its grid is coarse; refine within +/-2-10% (5% default) for precision.
  - Accepting a period without checking P/2 and 2P when the TLS output warns that transits fall in data gaps or odd and even depths differ.
  - Hardcoding a period, epoch or range from memory of a named target; compute it from the file you are given.
  - Rounding or reformatting the answer differently from what the task specifies, or writing extra text into an output file meant to hold only the number.
```
