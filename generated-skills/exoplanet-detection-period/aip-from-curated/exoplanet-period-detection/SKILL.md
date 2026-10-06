---
name: exoplanet-period-detection
description: Detect the orbital period of a transiting exoplanet from a photometric light curve. Load a TESS-style ASCII light curve (time, flux, quality flag, flux error), apply quality cuts, sigma-clip and flatten with a Savitzky-Golay window chosen from the cadence, run a broad Transit Least Squares (TLS) search, classify the candidate strength from SDE/SNR, and refine the period in a narrow TLS pass. Use when the input is a single-target light curve file and the goal is a period measurement with uncertainty and detection-strength metrics (SDE, SNR, depth, duration, T0).
compatibility: Scripts require numpy, scipy, astropy, lightkurve, and transitleastsquares in the executing Python. See source Dockerfile for a known-good set (python 3.12, numpy 1.26, astropy 6.0, lightkurve 2.4, transitleastsquares 1.32).
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
  Measure the orbital period of a transiting exoplanet in a single-target
  photometric light curve. The pipeline is: load the ASCII light curve and
  apply quality-flag + finite-value cuts, sigma-clip and Savitzky-Golay
  flatten the result, run a broad TLS period search over a cadence- and
  baseline-aware window, classify the detection strength from SDE and SNR,
  and (for anything stronger than a weak detection) refine the period with
  a dense TLS pass in a +/-5% window around the candidate.

trigger_when:
  - A user hands you a single-target light-curve file and asks for the orbital period of a transiting exoplanet.
  - You need the period, T0, depth, duration, SDE, and SNR of the dominant transit signal in a photometric time series.
  - Downstream work (phase-folding, transit masking, model fitting) needs a precise period from a broad period search.

do_not_use_when:
  - The signal of interest is not transit-shaped (stellar rotation, pulsation, radial-velocity sinusoid). Use Lomb-Scargle instead; see `references/method-selection.md`.
  - The file has no flux-uncertainty column and you have no way to synthesise one. TLS requires `flux_err`.
  - The task is multi-planet discovery requiring iterative transit masking. This skill reports the single dominant period; mask with `transitleastsquares.transit_mask` and re-run for the next planet.
  - The input is multiple light curves to be stacked or compared. Run this skill once per curve.

steps:
  - name: load-qc
    kind: execution
    description: Parse the ASCII light curve, drop flagged / non-finite / zero-error cadences, sort by time, and cache cleaned arrays to disk.
    inputs:
      - name: lightcurve_path
        type: string
        description: Absolute path to a whitespace-separated ASCII light curve with 4 columns (time, flux, quality flag, flux error) and `#`-prefixed comment lines.
    script: scripts/load_qc.py
    inputs_to: preprocess

  - name: preprocess
    kind: execution
    description: Sigma-clip at 3-sigma, flatten with a cadence-chosen Savitzky-Golay window, sigma-clip residuals at 5-sigma, and cache the flattened arrays.
    inputs:
      - name: cleaned_cache
        type: string
        description: Path to the npz file written by load-qc.
    script: scripts/preprocess.py
    inputs_to: tls-search

  - name: tls-search
    kind: execution
    description: Broad Transit Least Squares search over the full cadence/baseline-aware period window; reports the best candidate's period, T0, depth, duration, SDE and SNR.
    inputs:
      - name: flattened_cache
        type: string
        description: Path to the npz file written by preprocess.
    script: scripts/tls_search.py
    inputs_to: classify

  - name: classify
    kind: decision
    description: Judge how strong the broad-search candidate is, so the router can decide whether refinement is worth running.
    inputs:
      - name: period
        type: float
        description: Best candidate period from the broad TLS search, in days.
      - name: sde
        type: float
        description: TLS Signal Detection Efficiency of the best candidate.
      - name: snr
        type: float
        description: TLS signal-to-noise ratio of the best candidate.
      - name: transit_count
        type: integer
        description: Number of in-data transits TLS counted at the candidate period.
    questions:
      strength:
        type: choice
        instructions: >
          Classify the detection using the TLS SDE/SNR rubric from the source
          skills. Prefer `strong` when SDE > 9 AND SNR > 7 AND transit_count >= 3;
          `moderate` when SDE in (6, 9] OR SNR in (5, 7]; `weak` otherwise.
          A `weak` answer skips refinement so we don't spend compute polishing
          a false positive.
        criteria:
          strong: SDE > 9 and SNR > 7 with at least 3 transits in-data; a very likely real transit signal.
          moderate: SDE in (6, 9] or SNR in (5, 7]; a plausible candidate worth refining but needing follow-up validation.
          weak: SDE <= 6 and SNR <= 5, or fewer than 2 transits in-data; probably a false positive.
    thresholds:
      strength: 0.6
    inputs_to: refine-router

  - name: refine-router
    kind: router
    description: Strong and moderate candidates are refined; weak candidates skip refinement to save compute.
    branch_on: strength
    branches:
      strong: refine
      moderate: refine
      weak: end

  - name: refine
    kind: execution
    description: Dense TLS pass in a +/-5% window around the candidate period; overwrites period/sde/snr/T0/depth/duration if the refined SDE is at least as high.
    inputs:
      - name: flattened_cache
        type: string
      - name: period
        type: float
      - name: sde
        type: float
    script: scripts/refine.py
    inputs_to: end

  - name: end
    kind: end
    description: Final period measurement plus the detection-quality metrics an analyst needs to judge it.
    inputs:
      - name: period
        type: float
        description: Best-estimate orbital period in days (refined if the refinement improved SDE, otherwise the broad-search value).
      - name: period_uncertainty
        type: float
        description: TLS period uncertainty in days.
      - name: sde
        type: float
        description: TLS Signal Detection Efficiency; >9 very strong, >6 strong, <6 weak.
      - name: snr
        type: float
        description: TLS signal-to-noise ratio of the best candidate.
      - name: t0
        type: float
        description: Mid-transit epoch in the input time system.
      - name: depth
        type: float
        description: Transit depth as a fraction of out-of-transit flux.
      - name: duration
        type: float
        description: Transit duration in days.
      - name: strength
        type: string
        description: Classification label from the classify step (`strong`, `moderate`, `weak`).

anti_patterns:
  - Searching a period window wider than baseline/2. Fewer than two transits in-data cannot be refined and almost always aliases.
  - Flattening with a window shorter than the expected transit duration. The Savitzky-Golay filter will absorb the dip and the transit will vanish.
  - Reporting the broad-search period without refinement when the detection is strong. The broad grid is coarse by design; refinement typically reduces period error by 10-50x.
  - Dropping flux_err or passing zeros to TLS. TLS requires finite positive weights and will raise.
  - Trusting a period with transit_count < 2 or a visible odd/even depth mismatch; both are classic eclipsing-binary / aliasing signatures. See `references/troubleshooting.md`.
```
