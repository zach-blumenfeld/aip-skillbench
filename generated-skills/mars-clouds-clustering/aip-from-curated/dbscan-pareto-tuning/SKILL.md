---
name: dbscan-pareto-tuning
description: Tune DBSCAN hyperparameters (min_samples, epsilon, shape weight of a custom weighted distance metric) by clustering crowd-sourced point annotations per image, Hungarian-matching cluster centroids to expert annotations, scoring F1 and mean match distance (delta), and writing the Pareto frontier (max F1, min delta) to CSV with paretoset, running the grid in parallel with joblib. Use for Mars cloud-arch citizen-science vs expert marks (citsci_train.csv / expert_train.csv), or any task that asks for a DBSCAN grid search with a custom distance, multi-objective trade-off, or Pareto-optimal parameter sets.
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
  Find the Pareto-optimal DBSCAN settings for turning many noisy crowd point marks per
  image into consensus points that agree with expert marks. Each (min_samples, epsilon,
  shape_weight) combination clusters every image's crowd marks under a weighted distance
  d = sqrt((w*dx)^2 + ((2-w)*dy)^2) by default, takes cluster centroids, matches them to
  the expert points with the Hungarian algorithm under a pixel cutoff, and scores mean
  F1 and mean matched distance (delta). Combinations passing the F1 floor are reduced to
  the (max F1, min delta) frontier and written to CSV. The scripts carry the exact
  DBSCAN semantics, a vectorized metric that replaces the slow Python callable, a
  joblib-parallel sweep, and a self-check against sklearn.

trigger_when:
  - A task asks to optimize or grid-search DBSCAN hyperparameters (min_samples, epsilon/eps, a shape or axis weight) against expert or ground-truth points.
  - Citizen-science / Zooniverse point annotations (e.g. Mars cloud-arch peak markers in citsci_train.csv and expert_train.csv) must be clustered per image and compared to expert marks.
  - A task asks for a Pareto frontier / Pareto-optimal set trading off F1 (or accuracy) against a distance or error metric.
  - A clustering task requires a custom or anisotropic distance metric with sklearn DBSCAN or scipy cdist/pdist.

do_not_use_when:
  - The task is a single DBSCAN fit with given parameters and no ground truth to score against.
  - The objectives are not cluster-vs-reference matching quality (e.g. model accuracy vs latency only); use paretoset directly.
  - The data are not 2-D point coordinates grouped by image or frame.

steps:
  - name: configure
    kind: client_task
    description: Map the task's paths, grids, distance formula, matching and scoring rules onto a partial config over the defaults.
    inputs:
      - name: task_instructions
        type: string
        description: The task statement verbatim, including file paths, parameter ranges, formulas, thresholds, and the required output file and columns.
    template: assets/configure.md
    assets:
      - assets/default_config.json
    references:
      - path: references/method.md
        description: Custom-metric, joblib, and Pareto techniques; matching and metric definitions; phrase-to-config-key mapping; how to run the scripts by hand. Load when a task phrase does not obviously map to a config key.
    inputs_to: profile-data

  - name: profile-data
    kind: execution
    description: Merge the config over the defaults, expand the grids, check columns/paths/options, and profile both CSVs (rows, frames, overlap, value counts, coordinate ranges).
    inputs:
      - name: config
        type: object
        description: Partial config; only the keys that differ from assets/default_config.json.
    script: scripts/profile_data.py
    assets:
      - assets/default_config.json
    timeout: 300
    inputs_to: review-config

  - name: review-config
    kind: decision
    description: Confirm the resolved config implements the task exactly and fits the data before spending the sweep.
    inputs:
      - name: task_instructions
        type: string
      - name: config
        type: object
        description: The fully resolved config returned by profile-data.
      - name: profile
        type: object
        description: Data profile and expanded grid values.
      - name: config_problems
        type: list[*]
        description: Hard problems found by the script; any entry means not ready.
    questions:
      config_ready:
        type: noul
        instructions: >
          Is the resolved config ready to run? Yes only if config_problems is empty AND
          every rule the task states is reflected: input/output paths; grid values
          (compare profile.grid_values with the task's ranges, endpoints inclusive);
          the distance formula (x_scale, y_scale, minkowski_p); the match cutoff and
          matching rule; F1/delta aggregation and which images count; the F1 floor and
          whether it is strict; output columns, order, rounding. Also check the profile:
          frame_col must split the data into single images (for the Mars cloud CSVs,
          frame_file, not file_rad or subject_ids), the frame overlap must be
          substantial, and value_counts must show only the mark type being clustered
          (otherwise add a filter). Defaults kept where the task is silent count as yes.
        criteria:
          true: No script problems, every stated task rule maps to the config, and the profile shows sensible per-image grouping.
          false: A script problem, a mismatch with any stated rule, or a grouping/filter issue visible in the profile.
    thresholds:
      config_ready: 0.2
    inputs_to: route-config

  - name: route-config
    kind: router
    description: Ready configs go to the sweep; anything else goes back to configure with the problems in the state.
    branch_on: config_ready
    branches:
      "true": grid-search
      "false": configure

  - name: grid-search
    kind: execution
    description: Spot-check fast DBSCAN against sklearn, sweep every combination in parallel, filter by F1, compute the Pareto frontier, and write output_csv.
    inputs:
      - name: config
        type: object
        description: The resolved config.
    script: scripts/grid_search.py
    assets:
      - assets/default_config.json
    timeout: 3600
    inputs_to: review-result

  - name: review-result
    kind: decision
    description: Sanity-check the written frontier before finishing.
    inputs:
      - name: task_instructions
        type: string
      - name: pareto_rows
        type: list[*]
        description: The rows written to output_csv.
      - name: summary
        type: string
      - name: n_after_f1_filter
        type: integer
      - name: best_f1_row
        type: object
      - name: verification
        type: object
    questions:
      result_ok:
        type: noul
        instructions: >
          Is the frontier a credible final answer? Yes when verification.mismatches is 0,
          pareto_rows is non-empty with the columns the task asked for, F1
          and delta both decrease down the F1-sorted rows (equal only for kept ties; the
          trade-off shape), every row satisfies the F1 floor, and parameters lie inside
          the task's grid. An empty frontier is only acceptable if best_f1_row shows no
          combination can reach the floor. No when any check fails; then write the
          reason into result_notes before routing back.
        criteria:
          true: Non-empty, monotone trade-off, all rows pass the floor and grid, no verification mismatches.
          false: Empty without justification, non-monotone, wrong columns, or a verification mismatch.
    thresholds:
      result_ok: 0.2
    inputs_to: route-result

  - name: route-result
    kind: router
    description: A credible frontier ends the run; otherwise reconfigure with result_notes.
    branch_on: result_ok
    branches:
      "true": end
      "false": configure

  - name: end
    kind: end
    description: The Pareto frontier CSV written at output_csv, plus its rows and the sweep summary.
    inputs:
      - name: output_csv
        type: string
        description: Path of the written Pareto-frontier CSV.
      - name: pareto_rows
        type: list[*]
        description: Frontier rows (F1, delta, min_samples, epsilon, shape_weight by default), sorted by F1 descending.
      - name: summary
        type: string

anti_patterns:
  - Grouping marks by subject (file_rad, subject_ids, base+channel) instead of the single-image key (frame_file); a subject has four frames and mixing them merges unrelated arches.
  - Passing the Python distance callable straight to DBSCAN for the whole sweep; it is evaluated per point pair per fit and can blow the time budget. The weighted metric equals Euclidean on scaled coordinates, so precompute it once per image and weight.
  - Using the weighted (shape) distance for matching or delta; matching and delta use plain Euclidean pixel distance.
  - Treating range end points as exclusive (np.arange(4, 24, 2) drops 24); task ranges are inclusive.
  - Computing the Pareto frontier before applying the F1 floor, or maximizing delta; sense is F1 max, delta min.
  - Hardcoding a frontier or parameter set instead of computing it from the files given.
  - Letting float drift into shape weights (1.2000000000000002); the scripts round grid values.
```
