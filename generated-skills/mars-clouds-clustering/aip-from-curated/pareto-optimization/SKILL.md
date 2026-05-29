---
name: pareto-optimization
description: Multi-objective optimization with Pareto frontiers. Use when optimizing multiple conflicting objectives simultaneously, finding trade-off solutions, computing Pareto-optimal points, pruning grid-search results to non-dominated solutions, or surfacing accuracy-vs-cost trade-offs (e.g., F1 vs delta, accuracy vs latency, recall vs precision).
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a2
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a2/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Extract the Pareto frontier from a candidate set with two or more
  conflicting objectives. A point belongs to the frontier when no other
  candidate is at least as good on every objective and strictly better on
  at least one. Use this skill to prune grid-search results, model-selection
  sweeps, or any multi-objective comparison down to the non-dominated
  solutions that represent genuine trade-offs.

trigger_when:
  - User asks to compute a Pareto frontier, find Pareto-optimal points, or identify non-dominated solutions.
  - Optimizing two or more conflicting objectives simultaneously (e.g., maximize F1 while minimizing delta; maximize accuracy while minimizing latency or model size).
  - A hyperparameter or grid search produced many candidates and only the trade-off surface is needed.
  - User asks "which models are worth considering" or "show me the trade-off curve" between competing metrics.

do_not_use_when:
  - Optimizing a single objective — use ordinary `argmax`/`argmin` or scalar optimization instead.
  - Objectives are not conflicting (e.g., highly correlated and same sense) — Pareto adds no value over a single-metric ranking.
  - The decision requires a weighted scalarization with known weights — compute the weighted sum directly rather than the full frontier.

scope_and_approval: >
  Read-only on inputs. The only write action is the output CSV produced by
  `compute-frontier`. Safe to run without confirmation when the output path
  is fresh; ask before overwriting an existing file.

steps:
  - name: define-objectives
    description: >
      Identify the objective columns and the sense (`max` / `min`) for each.
      The sense vector is mandatory — forgetting direction is the most common
      Pareto bug. If concepts are unclear, read `references/pareto-concepts.md`.
    outputs:
      - name: objectives
        type: list[string]
        description: Column names to optimize over.
      - name: sense
        type: list[string]
        description: Same length as `objectives`; each entry is `"max"` or `"min"`.

  - name: prefilter
    description: >
      Apply quality thresholds BEFORE Pareto computation so noisy or
      below-spec candidates do not pollute the frontier (e.g., drop rows
      with `F1 <= 0.5`, or `accuracy < 0.85`). Pass a pandas `.query()`
      expression to `compute_pareto.py --prefilter`. Skip the step if no
      threshold applies.
    inputs:
      - name: objectives
        type: list[string]
      - name: sense
        type: list[string]
    outputs:
      - name: prefilter_expr
        type: string
        nullable: true
        description: Pandas query string, or null if no pre-filter applies.

  - name: compute-frontier
    description: >
      Run the script to compute the Pareto mask, optionally sort, optionally
      round, and write the frontier CSV. The script uses the `paretoset`
      library when available and falls back to a numpy implementation
      otherwise.
    script: scripts/compute_pareto.py
    inputs:
      - name: input_csv
        type: string
        description: Path to the candidate set.
      - name: objectives
        type: list[string]
      - name: sense
        type: list[string]
      - name: prefilter_expr
        type: string
        nullable: true
      - name: sort_by
        type: string
        nullable: true
        description: Column to sort the frontier by (often the primary objective).
      - name: round_map
        type: object
        nullable: true
        description: 'Map of column → decimal places, e.g. {"F1": 5, "delta": 5, "shape_weight": 1}.'
      - name: output_csv
        type: string
    outputs:
      - name: frontier_csv
        type: string
        description: Path written by the script.
      - name: frontier_size
        type: integer
        description: Number of rows on the frontier (printed to stdout by the script).

  - name: visualize
    description: >
      Optional. When the user asks for a plot, follow the pattern in
      `references/visualization.md`. Skip otherwise — visualization is not
      part of the default delivery.
    depends_on: [compute-frontier]
    inputs:
      - name: frontier_csv
        type: string

scenarios:
  - need: Prune a DBSCAN hyperparameter grid search to trade-off-optimal settings.
    context: >
      Grid search over (min_samples, epsilon, shape_weight) produced ~770
      rows with `F1` and `delta` per combination. Objective: maximize F1,
      minimize delta. Only meaningful clusterings (F1 > 0.5) should be kept,
      and outputs must be rounded for downstream comparison.
    action: >
      Invoke `scripts/compute_pareto.py --input results.csv
      --objectives F1,delta --sense max,min --prefilter "F1 > 0.5"
      --sort-by F1 --sort-desc --round F1:5,delta:5,shape_weight:1
      --output pareto_frontier.csv`.
    outcome: >
      CSV containing only the Pareto-optimal `(F1, delta, min_samples,
      epsilon, shape_weight)` tuples, sorted high-F1 first, with the
      requested precision applied.

  - need: Surface non-dominated models from a training sweep.
    context: >
      DataFrame `results` with columns `accuracy, inference_time,
      batch_size, hidden_units`. Goal: keep only models with accuracy ≥
      0.85, then return the accuracy/inference-time trade-off surface.
    action: >
      Call `compute_pareto_frontier(results, objectives=["accuracy",
      "inference_time"], sense=["max", "min"],
      prefilter="accuracy >= 0.85", sort_by="accuracy",
      sort_ascending=False)` from a Python session.
    outcome: >
      DataFrame of Pareto-optimal models retaining all parameter columns,
      ready to present to the user as the candidate shortlist.

anti_patterns:
  - Forgetting the `sense` vector or assuming a default direction — `paretoset` defaults to max, which silently inverts minimization objectives.
  - Computing the frontier on raw, unfiltered results — low-quality candidates can dominate corners of objective space and crowd out genuinely useful trade-offs. Apply a quality pre-filter first.
  - Collapsing the frontier to a single "best" point without the user asking — the frontier IS the answer to a multi-objective question; pick a single point only when the user supplies a preference rule.
  - Using a strict `>` everywhere (or `≥` everywhere) when checking dominance — correct dominance is weak (`≥`) on all objectives AND strict (`>`) on at least one. The script handles this; do not re-derive it inline.
  - Mixing the distance metric used during a clustering / model-training step with the metric used to evaluate Pareto trade-offs. The evaluation metric (e.g., standard Euclidean delta) is what the frontier ranks on, not the internal training-time distance.
  - Dropping non-objective columns from the output — keep all parameter columns so the user can see which configuration produced each frontier point.
```
