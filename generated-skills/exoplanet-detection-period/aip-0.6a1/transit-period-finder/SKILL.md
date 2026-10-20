---
name: transit-period-finder
description: Find a transiting exoplanet's orbital period in a TESS/Kepler light curve dominated by stellar activity (starspot rotation, flares). Filters quality flags and outliers, detrends with a rotation-aware Savitzky-Golay flatten, searches with Transit Least Squares (BLS and Lomb-Scargle cross-checks), vets SDE/SNR/odd-even/aliases, refines by transit-model fit, and writes the period in days rounded to 5 decimals. Use for "find the exoplanet period" tasks on a time/flux/flag/flux_err text file.
metadata:
  aip-version: "0.6a1"
---

# AIP runtime — format 0.6a1

You are executing an Agent Instruction Protocol (AIP) procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks as a graph of typed steps. You drive the run and execute every step yourself, following the semantics below.

Critical terminology:

- **Client**: you, the agent running this procedure; the `client_task` step kind is named for it. You supply each step's input, run its script, answer its questions by your own judgment, perform its task, follow its router, and make the final call at every step.
- **State**: the one JSON object a run carries. Each step declares the keys it reads as `inputs`; `execution` and `client_task` steps declare the keys they add as `outputs`, and a `decision` adds one key per question.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to you, `router` branches on a value in the state, `end` declares the procedure's result.

## Execution

The state starts as the start step's `inputs` and flows along `inputs_to`; each step adds its outputs to it. Every key is produced by exactly one step, so keys accumulate and nothing is overwritten. A step runs only if the state holds every key it declares in `inputs`, with the declared types; check that before each step. A step sees only those keys: give it its declared `inputs` and nothing else from the state. You have the final say at every step.

- **`execution`**: before the first one, check that this machine has everything `requires` names (the interpreter at its minimum version, the packages, the tools); if anything is missing, stop and name all of it. Run `script` from its folder, launched with the step's `command` when it has one and `python <script>` otherwise, with one JSON object on stdin, `{"state": <the step's inputs>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout holding exactly the step's `outputs`; add them to the state. A non-zero exit, or output missing a declared key, fails the step: stop there and report it rather than doing the step by hand.
- **`decision`**: answer each question from the step's inputs, and from the run so far only when the step sets `history: true`. Each answer collapses to one value under its question name and is added to the state: a noul to `true`/`false`, a choice to its label, a score to its level number. `thresholds` name the questions where an uncertain answer matters most; when your answer to one is a close call, reconsider it before continuing.
- **`client_task`**: render `template` with `{key}` from the step's inputs, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. Perform the task, loading `references` if their descriptions apply, and produce the step's `outputs`; add them to the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. Those keys are the procedure's result.

```yaml
purpose: >
  Recover the orbital period of a transiting exoplanet hidden under strong stellar
  variability in a space-telescope light curve, and write it to a file as days rounded
  to 5 decimals. Scripts do the deterministic work: column/flag-aware loading, upper-side
  outlier clipping that cannot delete transits, a Lomb-Scargle rotation measurement that
  sets the flatten windows (longer than a transit, shorter than the rotation), a BLS
  window scan, a TLS broad search, a transit-masked re-flatten, TLS refinement, a
  trapezoid ephemeris fit for the final digits, and alias/odd-even statistics. The agent
  judges whether the signal is a credible transit and which alias is the true period;
  a non-credible result goes to a guided manual rescue.

trigger_when:
  - A task asks for the period of an exoplanet, transit, or planet candidate from a light curve (TESS, Kepler, K2).
  - A light curve shows rotational modulation, starspots, or other stellar activity hiding transits.
  - The input is a text/CSV table of time, flux, quality flag, and flux uncertainty, and the output is a single period value.

do_not_use_when:
  - The goal is the stellar rotation or pulsation period itself, not a transiting planet (use a plain Lomb-Scargle periodogram).
  - The data are radial velocities or astrometry rather than photometry.
  - Full planet characterization (radius, inclination, MCMC posteriors) is required beyond the period.

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - numpy
    - scipy
    - astropy
    - lightkurve
    - transitleastsquares

steps:
  - name: prepare
    kind: execution
    description: Load the light curve, apply quality flags, drop non-finite rows, clip outliers (upper 3 sigma; lower only isolated >5 sigma single cadences), and measure the stellar rotation period with Lomb-Scargle.
    inputs:
      - name: lc_path
        type: string
        description: >
          Absolute path of the light-curve file as given by the task (e.g. /root/data/tess_lc.txt).
          Whitespace or comma separated with '#' comments; '# columnN: name' headers map the
          columns, otherwise the order is time, flux, quality flag, flux error.
      - name: flag_convention
        type: string
        description: zero_is_good (TESS standard, and what the task statement says when it reads "0 means good data") or nonzero_is_good for exports where flag 0 marks bad data. Take it from the task statement; if it is silent use zero_is_good, and switch only if the script reports that the convention leaves no data.
      - name: work_dir
        type: string
        description: Writable scratch directory for intermediate .npz files, outside the skill folder (e.g. /root/transit_work).
      - name: output_path
        type: string
        description: Where the task wants the period written (e.g. /root/period.txt). Not used by this step; carried to the writing step.
    script: scripts/prepare.py
    timeout: 300
    outputs:
      - name: clean_file
        type: string
        description: .npz of the cleaned, not detrended light curve (time, flux, flux_err).
      - name: rotation_period_days
        type: float
        description: Strongest Lomb-Scargle period in 0.1 d to min(100 d, baseline/2), taken as the stellar activity timescale.
      - name: rotation_power
        type: float
        description: Normalized Lomb-Scargle power of that peak (>=0.1 means clear rotational modulation).
      - name: prep_summary
        type: object
        description: Column map, points removed per stage, cadence, baseline, gaps, whether flux was median-normalized or errors estimated, variability and white-noise levels in ppt.
    inputs_to: search

  - name: search
    kind: execution
    description: Flatten with windows tied to the rotation period and pick the best by BLS SDE, TLS broad search, transit-masked re-flatten, TLS +/-5% refinement, BLS cross-check, trapezoid ephemeris fit, and vetting statistics for P, P/2 and 2P.
    inputs:
      - name: clean_file
        type: string
      - name: rotation_period_days
        type: float
      - name: rotation_power
        type: float
      - name: work_dir
        type: string
    script: scripts/search.py
    timeout: 1500
    outputs:
      - name: candidate
        type: object
        description: >
          period_days (fitted, unrounded), period_uncertainty_days, period_source
          (trapezoid_fit or tls_refined), tls_refined_period_days, bls_crosscheck_period_days,
          broad_search_period_days, t0, duration_hours, depth_ppt, tls_sde_broad, tls_snr,
          tls_odd_even_mismatch_sigma, transit_count, distinct_transit_count,
          empty_transit_count, rotation period/power, period_matches_rotation_harmonic,
          flatten/refine window, windows_agreeing_with_period, window_scan (per-window BLS
          period, depth, SDE) and aliases {reported, half, double} each with depth_ppt,
          depth_snr, odd/even depths, odd_even_mismatch_sigma, depth_at_phase_0p5 (ppt, snr),
          transits_with_data and transits_expected.
      - name: flat_file
        type: string
        description: .npz of the transit-masked flattened light curve used for refinement.
      - name: candidate_period_days
        type: float
        description: The search's period before alias adjudication.
    inputs_to: vet

  - name: vet
    kind: decision
    description: Judge whether the candidate is a credible transit signal and whether the true period is the reported one or its half/double alias.
    inputs:
      - name: candidate
        type: object
        description: The search result with its vetting statistics.
      - name: prep_summary
        type: object
        description: Data-preparation summary (baseline, gaps, noise levels).
    questions:
      signal_credible:
        type: noul
        instructions: >
          Is there a credible periodic transit signal at the candidate period (or its
          alias)? Weigh tls_sde_broad (>9 very strong, >6 strong, <6 weak/possible false
          positive), tls_snr or aliases.reported.depth_snr (>7 reliable), at least 2
          transits with data (distinct_transit_count / transits_with_data), a duration
          that is hours rather than a large fraction of the period, a depth that is
          plausible (planets ~0.01-3%), windows_agreeing_with_period (most windows
          finding P, P/2 or 2P means the signal survives preprocessing), and
          period_matches_rotation_harmonic (a candidate at the rotation period or a
          harmonic is residual activity unless the depth/shape is clearly transit-like).
          An odd/even mismatch alone does not make it non-credible: that is an alias
          question below.
        criteria:
          true: SDE >= 6 and SNR >= 7 with >= 2 transits, and not explained by rotation residuals or a single artifact.
          false: SDE < 6, SNR < 7, fewer than 2 transits with data, the period equals a rotation harmonic with no transit-like dip, or windows disagree so the period depends on preprocessing.
      period_choice:
        type: choice
        instructions: >
          Which period is the planet's true orbital period? Use the aliases block:
          aliases.reported.depth_at_phase_0p5 is the dip halfway between reported
          transits; aliases.double.depth_at_phase_0p5 is the depth of the in-between
          transits if the period were 2P; odd/even depths compare alternating transits.
          Default to reported when evidence is absent (for example the in-between epochs
          fall in data gaps; empty_transit_count > 0 alone is not evidence for 2P).
          If signal_credible is false, answer reported.
        criteria:
          reported: Alternate transits have equal depths (odd_even_mismatch_sigma < 3), the 2P alias's phase-0.5 dip equals the reported depth (the in-between transits are real), and there is no equal dip halfway between reported transits.
          double: Alternate transits differ (reported odd_even_mismatch_sigma >= 3, e.g. an eclipsing binary's primary/secondary), or the in-between epochs have data and show no dip (aliases.double.depth_at_phase_0p5_snr < 3 while aliases.double.depth_snr is high).
          half: An equally deep dip sits halfway between reported transits (aliases.reported.depth_at_phase_0p5 comparable to depth_ppt with snr >= 7) and the half alias's odd/even depths agree.
    thresholds:
      signal_credible: 0.2
      period_choice: 0.7
    inputs_to: route-credible

  - name: route-credible
    kind: router
    description: Credible signals are finalized by script; non-credible ones go to a manual rescue.
    branch_on: signal_credible
    branches:
      "true": finalize
      "false": rescue

  - name: finalize
    kind: execution
    description: Take the reported period or re-fit the chosen alias (2P or P/2), then write it rounded to 5 decimals as a single number.
    inputs:
      - name: period_choice
        type: string
      - name: candidate
        type: object
      - name: flat_file
        type: string
      - name: output_path
        type: string
    script: scripts/finalize.py
    timeout: 300
    outputs:
      - name: final_period_days
        type: float
        description: The final period in days (unrounded).
      - name: period_text
        type: string
        description: Exactly what was written to output_path, e.g. "2.44535".
      - name: final_basis
        type: string
        description: How the period was obtained (fit, alias re-fit, or fallback).
    inputs_to: end

  - name: rescue
    kind: client_task
    description: Find the period by hand with alternative detrending and search settings when the automated result is not credible.
    inputs:
      - name: candidate
        type: object
      - name: prep_summary
        type: object
      - name: clean_file
        type: string
      - name: flat_file
        type: string
      - name: work_dir
        type: string
    template: assets/rescue.md
    references:
      - path: references/transit-search-methods.md
        description: Lightkurve/TLS/BLS/Lomb-Scargle code, preprocessing parameters (sigma, flatten windows, masking, sine pre-whitening), validation thresholds, alias diagnosis, expected depths and period ranges, multi-planet masking. Load before trying alternatives.
    outputs:
      - name: rescue_period_days
        type: float
        description: Best-supported period in days, unrounded.
      - name: rescue_notes
        type: string
        description: What was tried, the chosen signal's SDE/SNR/transit count/odd-even, and why it wins.
    inputs_to: write-rescue

  - name: write-rescue
    kind: execution
    description: Write the rescue period rounded to 5 decimals as a single number.
    inputs:
      - name: rescue_period_days
        type: float
      - name: output_path
        type: string
    script: scripts/write_period.py
    timeout: 60
    outputs:
      - name: rescue_period_text
        type: string
        description: Exactly what was written to output_path.
    inputs_to: end

  - name: end
    kind: end
    description: The period file is written at output_path; the candidate carries the search evidence.
    inputs:
      - name: output_path
        type: string
      - name: candidate
        type: object

anti_patterns:
  - Symmetric sigma clipping on the raw or flattened flux; transits are dips and get deleted. Clip the upper side (flares, cosmic rays) only.
  - A flatten window near or above the rotation period (it leaves rotation residuals that TLS then reports as a false period), or shorter than ~3x the transit duration (it erases the transit).
  - Calling TLS without flux_err, or detrending without carrying flux_err through.
  - Writing the TLS or BLS grid period straight to the answer; grid periods are only good to a fraction of the peak width, and the trapezoid fit over all transits is ~10x more precise.
  - Judging significance from the SDE of a narrow refinement search; use the broad-search SDE.
  - Switching to 2P because TLS warns about transits without data, when the in-between epochs simply fall in gaps.
  - Hardcoding a period or expected answer; every run must compute it from the given file.
  - Writing anything but a single number rounded to 5 decimals (no units, no labels) to the output file.
  - Putting intermediate files or test inputs inside the skill folder; use work_dir.
```
