---
name: exoplanet-period-detection
description: End-to-end exoplanet orbital-period detection from a single-star light curve. Loads a time/flux/flux_err series (CSV, TXT, or FITS), preprocesses it transit-safely, routes to the right period search (Transit Least Squares, Box Least Squares, or Lomb-Scargle), validates the candidate against SDE/SNR/odd-even thresholds, and refines the period for strong candidates. Use when the task is "find the orbital period" or "search this light curve for transits" on Kepler/K2/TESS or similar photometric time series.
compatibility: Python 3.12 with numpy, scipy, astropy, transitleastsquares. The reference container (see source/README.md) installs the pinned stack; locally install the same packages with `pip install astropy transitleastsquares`.
metadata:
  aip-version: "0.5a1"
  author: aip-skillbench
  version: "1.0"
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
  Detect the orbital period of a transiting exoplanet (or the dominant
  periodicity, when the task is general variability) from a single-star
  light curve. The procedure loads a photometric file, applies a
  transit-safe preprocessing pipeline, picks a search algorithm (TLS,
  BLS, or Lomb-Scargle), judges candidate strength against literature
  thresholds, and refines the period for strong candidates.

trigger_when:
  - A user supplies a light-curve file (CSV, TXT, FITS) and asks for the
    orbital period of a transiting planet.
  - A user asks to search a Kepler/K2/TESS light curve for a transit
    signal.
  - A user asks to find the dominant periodicity of a star (rotation,
    pulsation) from photometric time series.

do_not_use_when:
  - The task is radial-velocity planet detection, not photometric
    transits.
  - The input is a raw target pixel file that still needs aperture
    photometry; run a photometry pipeline (e.g. lightkurve `search_targetpixelfile`)
    before this skill.
  - The task is multi-planet injection/recovery or mass characterisation
    rather than period discovery.

steps:
  - name: load-lightcurve
    kind: execution
    description: Parse the light curve file, apply quality flags, median-normalise flux, and expose arrays plus derived period bounds.
    inputs:
      - name: lightcurve_path
        type: string
        description: Absolute path to the light curve file (CSV, TSV, whitespace-delimited TXT, or FITS).
      - name: period_min
        type: float
        description: Shortest orbital period to search, in days. Clamped against the time baseline.
      - name: period_max
        type: float
        description: Longest orbital period to search, in days. Clamped to half the baseline so at least two cycles fit.
      - name: quality_good_is_zero
        type: boolean
        description: True for TESS/Kepler default (QUALITY == 0 is good). Set false for exports that flipped the convention.
    script: scripts/load_lightcurve.py
    inputs_to: pick-method

  - name: pick-method
    kind: decision
    description: Choose the primary period-search algorithm for this task.
    inputs:
      - name: lightcurve
        type: object
        description: Loaded light curve {time, flux, flux_err}.
      - name: lightcurve_meta
        type: object
        description: Summary stats (n_points, span, median flux, quality column present).
      - name: task_description
        type: string
        description: One-line summary of the user's task (planet transit, stellar rotation, etc.) used to break method ties.
    questions:
      method:
        type: choice
        instructions: Pick the search algorithm that matches the task. Default to tls when the task is "find a transiting planet" and the baseline supports it; pick bls only when the user asks for astropy-native BLS or needs fine period-grid control; pick ls when the task is general variability (rotation, pulsation, eclipsing-binary period) rather than a transit search.
        criteria:
          tls: Transit detection with maximum sensitivity. Fits a limb-darkened transit template; reports SDE, SNR, depth, duration, transit count. Preferred for exoplanet transit search.
          bls: Box Least Squares (astropy). Faster than TLS; useful when the user wants astropy-only, when the time series is very long and TLS is slow, or when the user needs explicit period-grid control. Reports depth, SNR, odd-even depth.
          ls: Lomb-Scargle periodogram. General-purpose periodicity for sinusoidal signals (stellar rotation, pulsation, eclipsing binaries). Use when the goal is not specifically a transit; no transit depth or duration is reported.
    thresholds:
      method: 0.5
    inputs_to: route-method

  - name: route-method
    kind: router
    description: Dispatch to the chosen search script.
    branch_on: method
    branches:
      tls: search-tls
      bls: search-bls
      ls: search-ls

  - name: search-tls
    kind: execution
    description: Preprocess (sigma-clip + Savitzky-Golay flatten) and run Transit Least Squares across [period_min, period_max].
    inputs:
      - name: lightcurve
        type: object
      - name: period_min
        type: float
      - name: period_max
        type: float
    script: scripts/search_tls.py
    timeout: 600
    inputs_to: validate-detection

  - name: search-bls
    kind: execution
    description: Preprocess and run astropy BoxLeastSquares with `autopower` over the period window; compute depth, SNR, and odd/even stats.
    inputs:
      - name: lightcurve
        type: object
      - name: period_min
        type: float
      - name: period_max
        type: float
    script: scripts/search_bls.py
    timeout: 600
    inputs_to: validate-detection

  - name: search-ls
    kind: execution
    description: Preprocess and run astropy LombScargle over the period window; report best period, power, and false-alarm probability.
    inputs:
      - name: lightcurve
        type: object
      - name: period_min
        type: float
      - name: period_max
        type: float
    script: scripts/search_ls.py
    timeout: 300
    inputs_to: validate-detection

  - name: validate-detection
    kind: decision
    description: Grade the candidate against SDE/SNR/power thresholds and flag likely period aliasing.
    inputs:
      - name: method
        type: string
        description: The algorithm that produced `detection` (tls/bls/ls).
      - name: detection
        type: object
        description: Candidate parameters from the search script (period, SDE, SNR, depth, odd_even_mismatch_sigma, etc.).
    questions:
      strength:
        type: choice
        instructions: >
          Rate the detection against literature thresholds. TLS: strong SDE > 9 and SNR > 7, moderate SDE 6-9, weak SDE < 6.
          BLS: strong SNR > 7 and pseudo-SDE > 7, moderate SNR 5-7, weak SNR < 5. LS: strong FAP < 1e-4, moderate FAP 1e-4 to 1e-2,
          weak FAP > 1e-2. Downgrade one level if odd_even_mismatch_sigma > 3 (likely eclipsing binary rather than planet).
        criteria:
          strong: Clear detection; SDE/SNR well above threshold, multiple transits, consistent odd-even depths.
          moderate: Plausible candidate; metrics near threshold or only a few transits captured. Worth refining but validate externally.
          weak: Below thresholds, few transits, or large odd-even mismatch. Report as non-detection or false-positive risk.
      aliasing_suspected:
        type: noul
        instructions: Is the reported period likely an alias (half or double the true period)?
        criteria:
          true: The detection shows many "transits without data" warnings, a very small transit count (<=3), or a clean fold at 2*period in a quick check.
          false: Transit count comfortably matches baseline / period, no gap warnings, and odd-even depths agree.
    thresholds:
      strength: 0.6
      aliasing_suspected: 0.2
    inputs_to: route-strength

  - name: route-strength
    kind: router
    description: Refine the period for moderate/strong candidates; skip refinement for weak detections.
    branch_on: strength
    branches:
      strong: refine-period
      moderate: refine-period
      weak: end

  - name: refine-period
    kind: execution
    description: Re-run the chosen algorithm on a narrow period window around the candidate for better precision.
    inputs:
      - name: method
        type: string
      - name: detection
        type: object
      - name: lightcurve
        type: object
    script: scripts/refine_period.py
    timeout: 600
    inputs_to: end

  - name: end
    kind: end
    description: Final state carrying the method, the initial detection, the strength rating, the aliasing flag, and (when refinement ran) the refined detection.
    inputs:
      - name: method
        type: string
      - name: detection
        type: object
      - name: strength
        type: string
      - name: aliasing_suspected
        type: boolean

anti_patterns:
  - Running TLS or BLS without flux uncertainties - weighting breaks and SDE/SNR become meaningless. `load_lightcurve.py` fabricates them from the MAD when the file lacks a column; do not override that fallback with zeros.
  - Flattening with a Savitzky-Golay window shorter than the transit duration; this erases the signal before the search even starts.
  - Accepting a "detection" at the first-pass period without checking odd-even depth or the aliasing flag. A 3-sigma odd-even mismatch usually means an eclipsing binary, not a planet.
  - Treating LS power as transit evidence. LS finds sinusoids, not boxes; use TLS or BLS when the user asks about a planet.
  - Refining a weak detection "just in case". Refinement sharpens a real period; if the broad search did not clear SDE/SNR thresholds, refining will not rescue it.
```
