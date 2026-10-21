---
name: transit-period-finder
description: Find a transiting exoplanet's orbital period in a TESS/Kepler/K2 light curve dominated by stellar variability (starspot rotation, flares). Quality-flag filtering, flare clipping, rotation-aware Savitzky-Golay flattening (lightkurve), Box Least Squares search with SDE/SNR/odd-even/alias vetting, transit-masked refit, and writing the period rounded to 5 decimals. Use for "find the exoplanet period", detrending light curves before BLS/TLS, or transit-search troubleshooting.
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
  Find the orbital period of a transiting exoplanet hidden under strong stellar variability
  (starspot rotation, pulsation, drift) in a space-telescope light curve (TESS/Kepler/K2 text
  table of time, flux, quality flag, flux error), and write it to a file rounded as the task
  asks. Scripts do the deterministic work: read and summarise the file, quality-filter,
  flatten the variability with a rotation-aware Savitzky-Golay window, clip flares, run a Box
  Least Squares search with alias and robustness diagnostics, then mask the transits,
  re-flatten, and refine the period with a trapezoid fit cross-checked by transit timing.
  Decisions settle the flag convention and whether the top peak is a real transit at its
  true period (not a rotation harmonic or a 2x / 0.5x alias).

trigger_when:
  - A task asks for the period of a transiting exoplanet from a light curve file.
  - A light curve shows rotational modulation or other stellar activity that hides transits and must be detrended before a transit search.
  - Planning or debugging a quality-filter, outlier, detrend, BLS/TLS period-search pipeline on TESS, Kepler, or K2 photometry.

do_not_use_when:
  - The goal is the stellar rotation or pulsation period itself (use a Lomb-Scargle periodogram on the undetrended flux instead).
  - The data are radial velocities or astrometry rather than photometry.
  - Several planets must be characterised; this procedure reports one period (mask it and rerun for more).

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - numpy
    - scipy
    - astropy
    - lightkurve

steps:
  - name: inspect-light-curve
    kind: execution
    description: Read the table and summarise columns, flag values, scatter per flag subset, cadence, gaps, and the dominant stellar-variability period (Lomb-Scargle).
    inputs:
      - name: lc_path
        type: string
        description: Path to the light-curve text file (task container path, e.g. /root/data/tess_lc.txt). Columns time, flux, quality flag, flux error; '#' lines are headers.
      - name: output_path
        type: string
        description: Where the period must be written (e.g. /root/period.txt).
      - name: task_statement
        type: string
        description: The task text verbatim, including what it says about columns, flag meaning, and output format.
      - name: period_min
        type: float
        description: Shortest trial period in days; 0 means the default 0.5 d.
      - name: period_max
        type: float
        description: Longest trial period in days; 0 means half the baseline (two transits needed).
    script: scripts/inspect_lc.py
    outputs:
      - name: data_summary
        type: object
        description: Columns, flag_value_counts, flag_zero_subset / flag_nonzero_subset (count, p2p_scatter, std), baseline, cadence, gaps, stellar_variability (period_days, amplitude, significant).
    inputs_to: choose-flag-convention

  - name: choose-flag-convention
    kind: decision
    description: Decide which rows the quality flag marks as good.
    inputs:
      - name: data_summary
        type: object
      - name: task_statement
        type: string
    questions:
      flag_convention:
        type: choice
        instructions: >
          Which rows does the quality-flag column mark as good data? Conventions vary by source,
          so verify rather than assume. An explicit statement in the task ("0 means good data")
          decides it. Otherwise standard TESS/Kepler files use 0 = good; confirm with the subset
          statistics: the good subset normally holds most rows and has the lower p2p_scatter.
          If there is no flag column (flag_value_counts is null), answer ignore_flags.
        criteria:
          zero_is_good: Rows with flag 0 are good; drop every non-zero flag (standard TESS/Kepler).
          nonzero_is_good: Rows with a non-zero flag are good; drop flag 0 (some exported files).
          ignore_flags: No usable flag column, or the flags carry no quality meaning; keep all finite rows.
    thresholds:
      flag_convention: 0.8
    inputs_to: detrend-and-search

  - name: detrend-and-search
    kind: execution
    description: Quality-filter, flatten stellar variability (window P_rot/4 clipped to 0.25-0.75 d), clip upward outliers, run BLS on 10-min bins over the period range, and report the top 5 distinct peaks with vetting statistics plus a two-window robustness check.
    inputs:
      - name: lc_path
        type: string
      - name: flag_convention
        type: string
      - name: data_summary
        type: object
      - name: period_min
        type: float
      - name: period_max
        type: float
    script: scripts/search_transits.py
    outputs:
      - name: candidates
        type: list[*]
        description: Ranked BLS peaks (rank 1 = highest power), each polished on unbinned data, with period, t0, duration, depth, depth_snr, sde, n_transits_with_data, odd/even depths, mismatch sigma and depth ratio, secondary depth at phase 0.5, rotation_relation, period_over_top_period.
      - name: search_summary
        type: object
        description: Points kept/removed, flatten window, residual scatter, period and duration grids, and robustness (top period under a 0.6x and 1.5x window).
    inputs_to: vet-candidates

  - name: vet-candidates
    kind: decision
    description: Judge whether a real transit was found, which candidate it is, and whether its true period is the peak period or an alias.
    inputs:
      - name: candidates
        type: list[*]
      - name: search_summary
        type: object
    questions:
      transit_detected:
        type: noul
        instructions: >
          Does at least one candidate show a credible periodic transit? Credible means SDE > 6
          (SDE > 9 is very strong), depth_snr > 7, at least 2 transits with data, a duration that
          is a small fraction of the period (duration_over_period below ~0.1), and a period that is
          not simply a rotation harmonic (rotation_relation set) unless its transit statistics are
          far stronger than residual variability would give. A top period that survives both
          robustness windows supports detection; a top period that jumps between windows to
          rotation-scale values argues against it.
        criteria:
          true: Some candidate meets the SDE, SNR and transit-count thresholds with a transit-like duration.
          false: No candidate does, or the only strong peaks are rotation harmonics or unstable across windows.
      candidate_rank:
        type: choice
        instructions: >
          Which candidate is the planet? Default to rank1. Pass over a higher-ranked peak only if
          it is a rotation harmonic, has inconsistent odd/even depths (odd_even_depth_ratio below
          ~0.3) that a 2x alias does not explain, has a long box duration matching residual
          variability, or is an alias of a better
          candidate (period_over_top_period near 0.5, 1.5, 2, or 3 of the real one). Peaks at
          2x / 0.5x / 1.5x of the planet period are aliases of it, not separate planets. If
          transit_detected is false, answer rank1.
        criteria:
          rank1: The highest-power peak.
          rank2: Second peak.
          rank3: Third peak.
          rank4: Fourth peak.
          rank5: Fifth peak.
      alias_factor:
        type: choice
        instructions: >
          Is the chosen candidate's period the true orbital period, or an alias? Use its own
          statistics. If odd_even_depth_ratio is below ~0.3 (one of depth_odd / depth_even near
          zero, usually with odd_even_mismatch_sigma > 3), alternate "transits" are empty, so the
          true period is double. A high mismatch sigma with both depths substantial (ratio above
          ~0.6) at high SNR comes from detrending distortion under fast rotation, not an alias.
          If secondary_depth_at_phase_0p5 is comparable to depth (large secondary_snr, similar
          depth), the transits recur at half the period, so the true period is half. Otherwise
          the period is as found. Epochs lost in data gaps (n_transits_with_data below
          n_transit_epochs_in_baseline, zero entries in points_per_transit) do not by themselves
          make it an alias; decide on the odd/even and phase-0.5 evidence. If transit_detected is
          false, answer as_found.
        criteria:
          as_found: Odd and even depths agree within 3 sigma and there is no comparable dip at phase 0.5.
          double: Alternate events are missing (odd_even_depth_ratio below ~0.3); true period is 2x.
          half: An equal dip sits at phase 0.5; true period is 0.5x.
    thresholds:
      transit_detected: 0.2
      candidate_rank: 0.7
      alias_factor: 0.7
    inputs_to: route-on-detection

  - name: route-on-detection
    kind: router
    description: A vetted transit goes to refinement; a weak or ambiguous search goes to a hand investigation.
    branch_on: transit_detected
    branches:
      "true": refine-and-write
      "false": investigate-weak-signal

  - name: refine-and-write
    kind: execution
    description: Mask the chosen transits, re-flatten, refine with a dense BLS grid and a trapezoid least-squares fit cross-checked by a linear transit-timing ephemeris, then write the period rounded to 5 decimals to output_path.
    inputs:
      - name: lc_path
        type: string
      - name: flag_convention
        type: string
      - name: search_summary
        type: object
      - name: candidates
        type: list[*]
      - name: candidate_rank
        type: string
      - name: alias_factor
        type: string
      - name: output_path
        type: string
    script: scripts/refine_period.py
    outputs:
      - name: period_days
        type: float
        description: Refined orbital period in days (unrounded).
      - name: period_text
        type: string
        description: Exactly what was written to output_path, the period rounded to 5 decimals.
      - name: refine_summary
        type: object
        description: Method used, uncertainty, fine-BLS / fit / timing periods and their disagreement, fitted depth and T14, per-transit times, O-C and depths.
    inputs_to: end

  - name: investigate-weak-signal
    kind: client_task
    description: Search by hand (other flag convention, windows, durations, TLS, aliases), then write the best-supported period rounded to 5 decimals.
    inputs:
      - name: lc_path
        type: string
      - name: output_path
        type: string
      - name: task_statement
        type: string
      - name: data_summary
        type: object
      - name: search_summary
        type: object
      - name: candidates
        type: list[*]
    template: assets/investigate.md
    references:
      - path: references/methods.md
        description: Flattening, Lomb-Scargle, BLS and TLS call patterns and parameters, validation thresholds (SDE, SNR, odd/even), alias checks, expected depths and period ranges, common failure causes. Load before any manual search.
    outputs:
      - name: fallback_period_text
        type: string
        description: Exactly what was written to output_path.
      - name: investigation_notes
        type: string
        description: What was tried, which candidate won and why, with its SDE, SNR and transit count; flags low confidence.
    inputs_to: end

  - name: end
    kind: end
    description: The period file has been written; the result points at it with the search record.
    inputs:
      - name: output_path
        type: string
      - name: candidates
        type: list[*]
      - name: search_summary
        type: object

anti_patterns:
  - Sigma-clipping the raw flux before flattening when the star is variable; it cuts the rotation peaks and troughs. Flatten first, then clip only upward outliers.
  - Clipping low outliers at 3-5 sigma after flattening; transits are low outliers and deep ones get erased.
  - A flatten window too long to follow the rotation signal and its P_rot/2 harmonic (residual spots masquerade as long, shallow box transits near P_rot/2 or P_rot) or shorter than ~3x the transit duration (the transit is flattened away).
  - Taking the period from a flatten that did not mask the transits; the depth is suppressed and the period biased. Refine on a transit-masked re-flatten.
  - Reporting the stellar rotation period (the strongest Lomb-Scargle peak) as the planet period.
  - Accepting the top peak without checking 2x / 0.5x aliases via odd/even depths and the phase-0.5 depth.
  - Dropping flux_err; BLS and TLS weight points by it (TLS needs it).
  - Assuming the flag convention instead of checking it against the task text and the subset scatter.
  - Running a full-range TLS search on unbinned 2-minute data inside a time budget; it can take many minutes. BLS first, TLS only on a narrow window or binned data.
  - Writing a hardcoded or remembered period; the value must come from the file at hand.
  - Writing anything but the single rounded number (no units, no label) to the output file.
```
