---
name: mars-cloud-dbscan-pareto
description: Grid-search DBSCAN hyperparameters (min_samples, epsilon, shape_weight) with an anisotropic custom distance d=sqrt((w*dx)^2+((2-w)*dy)^2) to cluster citizen-science point annotations (e.g. Mars cloud arch peaks), greedily match cluster centroids to expert points per image, score mean F1 and mean Euclidean delta, filter F1>0.5, and write the Pareto frontier (max F1, min delta) to CSV. Use for multi-objective DBSCAN tuning of crowd-sourced vs expert annotations, joblib-parallel grid search with a custom metric, or paretoset frontiers.
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
  Tune DBSCAN on crowd-sourced point annotations against expert labels as a two-objective
  problem and write the Pareto frontier. Encodes the exact evaluation contract (per-image
  DBSCAN with the shape-weighted metric, mean-of-members centroids, greedy closest-first
  centroid-to-expert matching on plain Euclidean distance with a 100 px cap, F1 and delta
  per image, averages over every expert image with F1 zeros kept and NaN deltas skipped,
  F1 > 0.5 filter, non-dominated set with ties kept, rounding) in scripts that run the
  847-combination grid in parallel in seconds (exact sklearn DBSCAN labels, cached
  scoring, resumable checkpoints).

trigger_when:
  - A task asks to optimize DBSCAN hyperparameters (min_samples, epsilon, shape_weight) for citizen-science / crowd-sourced annotations of Mars clouds against expert annotations.
  - A task asks for a Pareto frontier of clustering settings that maximize F1 and minimize centroid-to-expert distance (delta), written as F1,delta,min_samples,epsilon,shape_weight.
  - Any grid search over DBSCAN with a custom weighted distance d(a,b)=sqrt((w*dx)^2+((2-w)*dy)^2), parallelized with joblib, scored per image by matching cluster centroids to reference points.

do_not_use_when:
  - The clustering is not scored against reference points per image (no expert labels), or the task wants a single best setting rather than a frontier and specifies a different scoring.
  - The objectives are not F1 (maximize) and mean matched distance (minimize).

requires:
  interpreter:
    name: python
    version: "3.10"
  packages:
    - numpy
    - scipy
    - pandas
    - scikit-learn>=1.0
    - joblib
    - paretoset

steps:
  - name: inspect-data
    kind: execution
    description: Load both CSVs (image key file_rad kept as a string, x/y numeric), resolve the search space, and report anomalies; hard problems exit non-zero.
    inputs:
      - name: citsci_csv
        type: string
        description: Path to the citizen-science annotations CSV (columns file_rad, x, y; others ignored), e.g. /root/data/citsci_train.csv.
      - name: expert_csv
        type: string
        description: Path to the expert annotations CSV (columns file_rad, x, y), e.g. /root/data/expert_train.csv.
      - name: search_space
        type: object
        description: >
          Grid to search as lists, keys min_samples, epsilon, shape_weight. Pass {} to use the
          standard grid (min_samples 3..9, epsilon 4..24 step 2, shape_weight 0.9..1.9 step 0.1 = 847
          combinations); pass explicit lists only when the task states a different grid.
      - name: output_csv
        type: string
        description: Where the frontier CSV goes, e.g. /root/pareto_frontier.csv.
      - name: work_dir
        type: string
        description: Scratch folder for the full grid results and the chunk checkpoints, e.g. /tmp/mars-cloud-dbscan-pareto.
    script: scripts/inspect_data.py
    assets:
      - assets/config.json
    outputs:
      - name: data_report
        type: object
        description: Row and image counts, unmatched images in each direction, points per image, x/y ranges of each file, combination count, and the warnings list.
      - name: resolved_search_space
        type: object
        description: The grid actually searched, as sorted lists (shape_weight rounded to 1 decimal so 1.2000000000000002 never appears).
      - name: data_status
        type: string
        description: clean when there are no warnings, otherwise warnings.
    inputs_to: data-gate

  - name: data-gate
    kind: router
    description: Clean data goes straight to the grid search; any warning is reviewed first.
    branch_on: data_status
    branches:
      clean: grid-search
      warnings: review-warnings

  - name: review-warnings
    kind: client_task
    description: Judge each data warning as benign under the task rules or as a sign of wrong inputs, before spending the grid search.
    inputs:
      - name: data_report
        type: object
    template: assets/review_warnings.md
    references:
      - path: references/method.md
        description: The full evaluation contract and its gotchas. Load if unsure how a warning's rows are treated by the scoring.
    outputs:
      - name: data_review
        type: string
        description: One line per warning, benign or blocking with reason, and the verdict (proceed / stopped and why).
    inputs_to: grid-search

  - name: grid-search
    kind: execution
    description: Run DBSCAN for every (min_samples, epsilon, shape_weight) over every expert image, in parallel joblib chunks of images checkpointed under work_dir, and write all averaged F1/delta results. If it times out, resume; finished chunks are reused.
    inputs:
      - name: citsci_csv
        type: string
      - name: expert_csv
        type: string
      - name: resolved_search_space
        type: object
      - name: work_dir
        type: string
    script: scripts/grid_search.py
    assets:
      - assets/config.json
    outputs:
      - name: grid_results_csv
        type: string
        description: Path of the CSV with every combination's unrounded F1, delta, parameters, and images_with_matches.
      - name: grid_summary
        type: object
        description: Combination and image counts, workers, chunks (and how many came from checkpoints), how many pass F1 > 0.5, best F1 and its parameters, elapsed seconds.
    inputs_to: pareto-frontier

  - name: pareto-frontier
    kind: execution
    description: Keep results with F1 > 0.5, take the non-dominated set (max F1, min delta; paretoset cross-checked by a manual dominance test), round, sort by F1 descending, and write output_csv.
    inputs:
      - name: grid_results_csv
        type: string
      - name: output_csv
        type: string
    script: scripts/pareto_frontier.py
    assets:
      - assets/config.json
    outputs:
      - name: n_frontier
        type: integer
        description: Rows written to output_csv.
      - name: n_passing_min_f1
        type: integer
        description: Combinations with mean F1 > 0.5 that entered the Pareto computation.
      - name: frontier_rows
        type: list[*]
        description: The written rows as objects with F1, delta, min_samples, epsilon, shape_weight.
      - name: frontier_status
        type: string
        description: found when at least one row was written, otherwise empty (header-only CSV).
    inputs_to: frontier-gate

  - name: frontier-gate
    kind: router
    description: A non-empty frontier finishes; an empty one is diagnosed before reporting.
    branch_on: frontier_status
    branches:
      found: end
      empty: diagnose-empty

  - name: diagnose-empty
    kind: client_task
    description: Explain why no combination reached F1 > 0.5 and confirm the header-only CSV is a true result, not a pipeline bug.
    inputs:
      - name: grid_summary
        type: object
      - name: data_report
        type: object
      - name: output_csv
        type: string
    template: assets/diagnose_empty.md
    references:
      - path: references/method.md
        description: The evaluation contract and gotchas. Load to check each scoring rule against the observed best F1.
    outputs:
      - name: empty_diagnosis
        type: string
        description: The likely cause, the checks run and their results, and confirmation that output_csv holds only the header.
    inputs_to: end

  - name: end
    kind: end
    description: The Pareto frontier CSV on disk plus the rows written and the grid summary.
    inputs:
      - name: output_csv
        type: string
      - name: n_frontier
        type: integer
      - name: frontier_rows
        type: list[*]
      - name: grid_summary
        type: object

anti_patterns:
  - Averaging F1 only over images that have citizen-science points or matches. Every expert image counts; missing points, no clusters, or no matches give F1 0.0 and those zeros stay in the F1 mean.
  - Including NaN deltas as 0 in the delta mean. Delta averages only images with at least one match.
  - Matching or measuring delta with the shape-weighted metric. The custom metric is for DBSCAN only; matching and delta use plain Euclidean distance, closest pairs first, each centroid and expert point used once, max 100 px.
  - Counting DBSCAN noise (label -1) as a cluster, or using a cluster medoid instead of the mean of its members as the centroid.
  - Reading file_rad as a number or stripping it; it is a path-like string (e.g. 080109120000/080110120000_A3.png) and is the only join key between the files.
  - Building shape_weight with float steps (0.9 + 0.1*i) and writing 1.2000000000000002; round to 1 decimal.
  - Calling DBSCAN with a Python callable metric over the full grid, or even DBSCAN(metric="precomputed") once per combination. Both give the same labels, but they are too slow for the client's 60-second script limit (the callable takes about 20 s per combination). The script builds the formula's matrix once per (image, shape_weight) and runs sklearn's own DBSCAN core loop only once per distinct core set.
  - Computing the frontier on rounded values, using F1 >= 0.5 instead of F1 > 0.5, or dropping exact ties (paretoset's default distinct=True keeps only one of identical points).
  - Lowering the F1 threshold or inventing rows when the frontier is empty; a header-only CSV is the correct output then.
  - Hardcoding a frontier from an earlier run; the result must be recomputed from the files given.
  - Re-implementing the grid by hand after a grid-search timeout. Resume the run instead; the step reloads its finished chunks from work_dir/chunks and computes only the rest.
```
