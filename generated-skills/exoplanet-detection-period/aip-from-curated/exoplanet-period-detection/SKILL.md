---
name: exoplanet-period-detection
description: Detect a transiting exoplanet's orbital period from a plain-text TESS light curve. Loads a time/flux/flag/flux_err file, applies quality flags, sigma-clips outliers, flattens stellar/instrumental trends while preserving transit depth, runs a broad Transit Least Squares (TLS) search, then refines the best candidate in a narrow period window for a precise period. Use when the input is one single-target light curve and the goal is to report the orbital period (and transit depth, T0, duration, SDE, SNR). Keywords - TESS, Kepler, K2, light curve, transit, exoplanet, period search, TLS, transitleastsquares, Lomb-Scargle, BLS, phase fold.
compatibility: Needs Python 3.10+ with numpy, scipy, and the transitleastsquares package. The curated task container already provides these (see source/README.md).
metadata:
  aip-version: "0.5a1"
  source-skills: "exoplanet-workflows, light-curve-preprocessing, lomb-scargle-periodogram, box-least-squares, transit-least-squares"
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
  Compute the orbital period of a transiting exoplanet from a single TESS-style
  plain-text light curve. The pipeline preprocesses the data (quality flags,
  outlier clipping, Savitzky-Golay flattening), runs a broad Transit Least
  Squares (TLS) period search, classifies the candidate's signal strength from
  its SDE, and - when the candidate is strong - refines the period with a
  narrow TLS re-search for a tight final uncertainty. TLS is chosen over
  Lomb-Scargle (not transit-shaped) and BLS (less sensitive, simpler box
  model); see source/README.md for the full method comparison.

trigger_when:
  - The task hands you a single light-curve file (TESS, Kepler, K2, or any
    plain-text time/flux/flag/flux_err series) and asks for an orbital period.
  - You need to detect a transit, measure its depth, or phase-fold at the
    recovered period for one target.

do_not_use_when:
  - The data is radial-velocity, imaging, or any non-photometric time series.
  - The target shows obvious eclipsing-binary variability (deep V-shaped dips,
    secondary eclipses) rather than planet-shaped transits - use a dedicated
    EB analysis instead.
  - You already know the planet period precisely and only need characterization
    (transit modeling with batman, limb darkening, stellar parameters).
  - The task is multi-planet discovery requiring iterative masking of multiple
    candidates - this pipeline reports the single strongest candidate.

steps:
  - name: preprocess
    kind: execution
    description: Load the light curve, drop quality-flagged rows, 5-sigma clip, and flatten with Savitzky-Golay.
    inputs:
      - name: light_curve_path
        type: string
        description: Absolute or relative path to a whitespace-delimited text file. Columns in order - time (MJD), flux (relative), quality flag, flux error. Lines starting with `#` are comments. Flag convention is standard TESS - 0 means GOOD.
    script: scripts/preprocess.py
    inputs_to: broad-search

  - name: broad-search
    kind: execution
    description: Broad-range TLS period search; classifies the candidate as very_strong, strong, or weak from its SDE.
    inputs:
      - name: clean_data_path
        type: string
        description: Path to the cleaned-light-curve .npz produced by preprocess.
    script: scripts/broad_search.py
    inputs_to: by-strength

  - name: by-strength
    kind: router
    description: Refine the period only when the broad search produced a strong candidate; weak signals skip refinement because tighter uncertainty on noise is meaningless.
    branch_on: strength
    branches:
      very_strong: refine-search
      strong: refine-search
      weak: end

  - name: refine-search
    kind: execution
    description: Narrow TLS re-search in a +/-5% window around the candidate for a precise period and uncertainty.
    inputs:
      - name: clean_data_path
        type: string
      - name: candidate_period
        type: float
        description: Best period from the broad search; the refined grid is centred here.
    script: scripts/refine_search.py
    inputs_to: end

  - name: end
    kind: end
    description: Final orbital period with uncertainty, signal metrics, and the broad-search transit parameters needed for a follow-up characterization.
    inputs:
      - name: period_days
        type: float
        description: Best orbital period in days (refined if the broad candidate was strong, else the broad-search candidate).
      - name: period_uncertainty_days
        type: float
      - name: strength
        type: string
        description: One of very_strong, strong, weak - derived from the broad-search SDE.
      - name: final_sde
        type: float
      - name: final_snr
        type: float
      - name: candidate_t0
        type: float
        description: Mid-transit epoch of the first transit, in the input time system.
      - name: candidate_duration
        type: float
        description: Transit duration in days.
      - name: candidate_depth
        type: float
        description: Fractional transit depth (1 - min(model_flux)).

anti_patterns:
  - Running TLS without passing flux_err - it is required, not optional, and omitting it degrades every weight in the search.
  - Choosing a flattening window shorter than the transit duration; a too-short Savitzky-Golay window erases shallow dips.
  - Trusting a weak-branch result (SDE < 6) as a confirmed detection; report it as a candidate pending more data.
  - Picking Lomb-Scargle over TLS for transit detection - LS is less sensitive to box-shaped dips and may lock onto a harmonic.
  - Reporting a period that is exactly half or double a plausible one without checking the phase-folded transit for odd-even depth consistency.
  - Over-aggressive sigma clipping (sigma 2-3) that removes in-transit points along with the outliers.
  - Searching a period range larger than baseline / 2 - any longer period gives at most one transit and cannot be verified.
```
