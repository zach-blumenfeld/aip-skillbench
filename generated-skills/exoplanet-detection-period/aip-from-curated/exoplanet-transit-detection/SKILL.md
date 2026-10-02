---
name: exoplanet-transit-detection
description: Find an exoplanet's orbital period from a TESS/Kepler/K2 light curve when the transit is hidden by stellar activity (rotation, spots, pulsation). Filters quality flags, removes outliers, flattens stellar variability, and runs a period search (Transit Least Squares by default; Box Least Squares or Lomb-Scargle for alternate signal types) with a two-stage refinement to sub-percent precision. Use when the user hands you a photometric time series and asks for the transiting planet's period.
metadata:
  aip-version: "0.4a0"
  source: "compiled from vendor/skillsbench/tasks/exoplanet-detection-period/environment/skills"
compatibility: "Requires Python packages: lightkurve, transitleastsquares, astropy, numpy, scipy. The SkillsBench container ships these preinstalled."
---

# AIP runtime — format 0.4a0

You are executing an (Agent Instruction Protocol) AIP procedure: the fenced YAML block in this skill's `SKILL.md`. AIP is a protocol for cheaply, quickly, and accurately executing multi-step tasks using a graph-based workflow. AIP is portable, so while designed for execution with an AIP client and server, you, the agent can play both roles instead. 

## Running

If the `aip` command is available (`aip --help` succeeds), use it: run `aip run <this skill's folder> --input <start.json>` with the start step's inputs as JSON. When the run needs you it prints a JSON pause and exits with code 3. `paused` says why: `decision` — answer the listed questions; `review` — confirm or override the flagged answers; `client_task` — do the task and produce the keys in `expects`. Put your answer in a JSON file and run the `resume` command the pause printed. Repeat until the output has `"done": true`; `state` is the result. If `aip` is not available, execute the procedure yourself, following the semantics below.

Critical terminology:

- **Client**: whoever drives the run: posts each step's input, reviews uncertain decisions, performs client tasks, and makes the final call at every step. As a plain Agent Skill, it is the agent that activated the skill.
- **Server**: runs each step and validates its input against the step's `inputs`. Without one, the activating agent does this itself: runs scripts, answers decision questions by its own judgment, and follows routers.
- **State**: the JSON object a step receives. Each step declares its required keys as `inputs`; extra keys pass through.
- **Step kinds**: `execution` runs a script, `decision` asks typed questions about the state, `client_task` hands work to the client, `router` branches on a value in the state, `end` declares the final state's shape.

## Execution

The state is one JSON object. It starts as the start step's `inputs` and flows along `inputs_to`; each step's output is merged over it, so keys accumulate and extra keys pass through untouched. A step runs only if the state holds every key it declares in `inputs`, with the declared types. The client may change the state before any step runs; it has the final say at every step.

- **`execution`**: run `script` with one JSON object on stdin, `{"currentState": <state>, "assets": {<file stem>: <content>}, "expects": <the next step's inputs>}`. The script writes one JSON object to stdout; it is merged over the state.
- **`decision`**: answer each question against the state. Each answer collapses to one value under its question name and is merged over the state: a noul to `true`/`false`, a choice to its label, a score to its level number. With a decision model, an answer under its threshold is sent to the client to confirm or override before continuing; without one, the client answers the questions.
- **`client_task`**: render `template` with `{key}` from the state, `{assets[stem]}` for its assets, and `{meta.name}` for the skill name. The client performs the task, loading `references` if their descriptions apply, and returns the next step's `inputs`; they are merged over the state.
- **`router`**: read the state's `branch_on` key and continue at `branches[value]`. A value with no branch is an error.
- **`end`**: the state must hold `end`'s `inputs`. That state is the procedure's result.

```yaml
purpose: >
  Detect a transiting exoplanet's orbital period from a TESS/Kepler/K2 light curve
  even when the transit is masked by stellar activity. The pipeline quality-filters
  the raw photometry, removes outliers, flattens stellar variability with a
  Savitzky-Golay filter, then runs a period search. The default branch is Transit
  Least Squares (TLS) with a two-stage refinement (broad → ±5% around the
  candidate) which is the most sensitive method for transit-shaped signals. Box
  Least Squares (BLS) and Lomb-Scargle (LS) branches are provided for alternate
  signal types.

trigger_when:
  - A TESS, Kepler, or K2 light curve is provided and a transiting planet's period is required.
  - The user says the target has strong rotational or pulsational variability hiding a transit.
  - A photometric time series with time / flux / quality flag / flux error columns needs a period search.
  - Reproducing or extending an exoplanet detection pipeline that combines preprocessing with TLS/BLS/LS.

do_not_use_when:
  - The input is radial-velocity data or spectroscopy — this skill is for photometric time series.
  - The goal is transit modeling (limb darkening, planet radius fitting) rather than period detection.
  - The signal is already known to be a stellar oscillation with no transit component (use lomb-scargle-periodogram directly).

steps:
  - name: preprocess
    kind: execution
    description: Load the light curve, quality-filter, remove outliers, and flatten stellar variability.
    inputs:
      - name: data_path
        type: string
        description: Absolute path to a 4-column text light curve (time_MJD, flux, quality_flag, flux_err).
    script: scripts/preprocess.py
    inputs_to: pick-method

  - name: pick-method
    kind: decision
    description: Choose the period search algorithm best matched to the signal type.
    inputs:
      - name: signal_description
        type: string
        description: One-line description of what the analyst expects to find (e.g. "transiting planet under rotational variability").
    questions:
      method:
        type: choice
        instructions: >
          Which period-search algorithm best fits this signal? Transit Least Squares
          (tls) fits an actual transit model and is most sensitive to shallow,
          transit-shaped dips including grazing transits — the default for exoplanet
          detection. Box Least Squares (bls) is astropy's built-in transit search;
          use it when TLS is unavailable or when the transit is a clean deep box.
          Lomb-Scargle (ls) detects general periodic signals (stellar rotation,
          pulsation, eclipsing binaries) but is less sensitive to shallow transits.
        criteria:
          tls: Transit-shaped dips (planets), possibly shallow or grazing; stellar-activity masked signals. Preferred default.
          bls: Deep box-shaped transits, or environments without transitleastsquares installed.
          ls: General periodicity — stellar rotation, pulsation, eclipsing binary with non-box shape.
    thresholds:
      method: 0.4
    inputs_to: route-method

  - name: route-method
    kind: router
    description: Route to the search branch the method decision selected.
    branch_on: method
    branches:
      tls: tls-search
      bls: bls-search
      ls: ls-search

  - name: tls-search
    kind: execution
    description: Transit Least Squares two-stage search (broad, then ±5% refinement) — the sensitive default for transits.
    inputs:
      - name: preprocessed_path
        type: string
        description: Path to the .npz saved by preprocess.
    script: scripts/tls_search.py
    timeout: 900
    inputs_to: write-output

  - name: bls-search
    kind: execution
    description: Astropy Box Least Squares two-stage search with a 0.05-0.30 d duration grid.
    inputs:
      - name: preprocessed_path
        type: string
    script: scripts/bls_search.py
    timeout: 900
    inputs_to: write-output

  - name: ls-search
    kind: execution
    description: Lomb-Scargle periodogram two-stage search (0.5-50 d, then ±5% refinement).
    inputs:
      - name: preprocessed_path
        type: string
    script: scripts/ls_search.py
    timeout: 300
    inputs_to: write-output

  - name: write-output
    kind: execution
    description: Write the final period to output_path formatted to 5 decimal places.
    inputs:
      - name: period
        type: float
        description: Best-fit orbital period in days.
      - name: output_path
        type: string
        description: File to write the numeric period into.
    script: scripts/write_period.py
    inputs_to: end

  - name: end
    kind: end
    description: Final state — the period in days and where it was written.
    inputs:
      - name: period
        type: float
      - name: output_path
        type: string

anti_patterns:
  - Skipping the quality-flag filter — bad-cadence data injects false periodic structure.
  - Passing flux with equal weights to TLS; flux_err is required for correct weighting.
  - Flattening with an overly short window that eats the transit dip along with the stellar variability.
  - Reporting the stage-1 broad-grid period as the final answer; refinement over ±5% is what pins sub-percent precision.
  - Accepting the first strong peak without checking for period aliasing (½× or 2× the true period, especially with data gaps).
  - Choosing Lomb-Scargle for a hidden transit — it will lock onto stellar rotation and miss the planet.
```
