---
name: pareto-optimization
description: Compute the Pareto frontier from multi-objective optimization results — the set of non-dominated points where improving one objective requires sacrificing another. Use when optimizing multiple conflicting objectives simultaneously (accuracy vs latency, F1 vs centroid error, cost vs quality), finding trade-off solutions across a hyperparameter sweep, or computing Pareto-optimal points from a DataFrame / CSV of results.
metadata:
  aip:
    spec: https://github.com/zach-blumenfeld/aip/tree/v0.3a3
    schemaId: https://raw.githubusercontent.com/zach-blumenfeld/aip/v0.3a3/assets/aip-schemas/procedure.schema.json
---

```yaml
purpose: >
  Compute the Pareto frontier from a table of multi-objective results —
  the set of rows where no other row is at least as good on every
  objective and strictly better on at least one. Covers framing the
  objectives (which columns, max vs min), applying any quality
  prefilters, running the frontier computation, and writing the result
  in the format the consuming task expects.

trigger_when:
  - Optimizing multiple conflicting objectives simultaneously (e.g. accuracy vs latency, F1 vs centroid error, cost vs quality).
  - The user asks for "trade-off" or "Pareto-optimal" solutions across a hyperparameter sweep.
  - You have a DataFrame / CSV of candidate results with two or more objective columns and need the non-dominated subset.
  - Reporting a frontier of model / configuration choices rather than a single best one.

do_not_use_when:
  - There is only one objective — pick the row with max/min on that column and skip the frontier logic entirely.
  - The user has already collapsed the objectives into a single weighted score and accepts that score as the criterion.
  - The candidate set is empty — return an empty result without invoking the frontier computation.

steps:
  - name: frame-objectives
    description: >
      Identify each objective column and its sense (maximize vs minimize)
      from the task. The frontier is meaningless without this — getting
      the sense backwards produces the *anti*-frontier (the worst
      trade-offs).

      Distinguish three column kinds in the input table:

      • **Objectives** — what the frontier balances (e.g. `F1` to
        maximize, `delta` to minimize). At least one of each direction
        is typical; two objectives is the common case.

      • **Hyperparameters / metadata** — `min_samples`, `epsilon`,
        `shape_weight`, model id, etc. These are carried through
        unchanged for downstream reporting but do not participate in
        dominance.

      • **Quality gates** — columns that must clear a threshold before a
        row is eligible (e.g. "F1 > 0.5 means meaningful clustering").
        Handle these in the next step, not as objectives.

      Output an explicit list of maximize columns and minimize columns;
      those drive every subsequent step.
    outputs:
      - name: objective-spec
        type: object
        description: "{ maximize: list[string], minimize: list[string], passthrough: list[string] }."

  - name: prefilter-results
    description: >
      Apply any quality-gate thresholds the task specifies *before*
      computing the frontier. The frontier respects only the rows you
      hand it — dropping a row at this step keeps it off the frontier
      regardless of its trade-off shape.

      Typical filters: minimum F1, maximum cost, valid status. Compose
      multiple filters with logical AND (each one narrows the candidate
      set).

      When the task says "only keep results with average F1 > 0.5" or
      similar, this step is where it goes. If the task has no gate, pass
      the table through unchanged.
    inputs:
      - name: candidate-results
        type: object
        description: DataFrame / CSV with one row per evaluated configuration.
      - name: objective-spec
        type: object
    outputs:
      - name: filtered-candidates
        type: object
        description: Eligible rows that cleared every gate.

  - name: compute-pareto-frontier
    description: >
      Run scripts/compute_pareto.py over the filtered candidates with
      the maximize/minimize columns from objective-spec. The script
      prefers the `paretoset` library (handles ties cleanly) and falls
      back to a vectorized numpy implementation if paretoset is not
      installed. CLI form is the typical entrypoint:

      ```
      python scripts/compute_pareto.py \
          --input filtered.csv --output frontier.csv \
          --maximize F1 --minimize delta \
          --filter "F1 > 0.5"
      ```

      The `--filter` flag can absorb the prior step's gates when the
      candidate set lives on disk and you want a one-shot invocation.
      The script can also be imported: `from compute_pareto import
      pareto_frontier`.
    script: scripts/compute_pareto.py
    inputs:
      - name: filtered-candidates
        type: object
      - name: objective-spec
        type: object
    outputs:
      - name: pareto-frontier
        type: object
        description: Rows of filtered-candidates that are Pareto-optimal on the declared objectives.

  - name: format-output
    description: >
      Render the frontier in the exact shape the task expects. Three
      knobs matter and each is easy to miss:

      • **Column order and selection.** Many tasks specify a header line
        (e.g. `F1,delta,min_samples,epsilon,shape_weight`). Reorder /
        subset before writing — `compute_pareto.py --columns` does this
        in one shot.

      • **Per-column rounding.** Decimal precision often varies by
        column (e.g. `F1` and `delta` to 5 places, `shape_weight` to 1
        place, integer hyperparameters left alone). Use the script's
        `--round COL:DECIMALS` (repeatable) or a pandas
        `df[col].round(n)` per column.

      • **Sort order.** When the task asks for a sorted frontier (most
        often descending on the primary "maximize" objective), apply it
        last — the dominance test is order-insensitive but the output
        consumers may not be.

      Write to the path the task specifies.
    inputs:
      - name: pareto-frontier
        type: object
    outputs:
      - name: output-path
        type: string
        description: Filesystem path of the written result.

scenarios:
  - need: >
      Hyperparameter sweep over DBSCAN with three knobs
      (`min_samples`, `epsilon`, `shape_weight`); each combination
      yields an `F1` (maximize) and a `delta` (minimize). Task asks for
      the Pareto frontier among rows with average F1 > 0.5, written to
      `/root/pareto_frontier.csv` with header `F1,delta,min_samples,
      epsilon,shape_weight`, F1/delta rounded to 5 places, shape_weight
      to 1 place.
    context: >
      Sweep is precomputed into a DataFrame `results` with one row per
      `(min_samples, epsilon, shape_weight)` combination.
    action: >
      Filter `results = results[results['F1'] > 0.5]`, then call
      `pareto_frontier(results, maximize=['F1'], minimize=['delta'])`.
      Reorder columns to `['F1','delta','min_samples','epsilon',
      'shape_weight']`, round `F1`/`delta` to 5 and `shape_weight` to 1,
      and write to `/root/pareto_frontier.csv` with `index=False`.
    outcome: >
      Output CSV contains exactly the non-dominated configurations the
      grader expects, in the declared column order and precision.

  - need: >
      Model selection — choose a small set of models that span the
      accuracy / inference-time trade-off, filtered by a minimum
      accuracy of 0.85.
    action: >
      Drop rows with `accuracy < 0.85`, then take the frontier with
      `maximize=['accuracy']`, `minimize=['inference_time']`. Sort
      descending by accuracy and write to `pareto_models.csv`.
    outcome: >
      A short list of models where each one is the best at *some*
      accuracy / latency trade-off — no candidate is strictly worse than
      another on both axes.

  - need: >
      Visualize the frontier against the full candidate set.
    action: >
      Run `scripts/visualize_pareto.py --all results.csv --frontier
      pareto.csv --x-col delta --y-col F1` to produce a scatter plot
      with the frontier highlighted.
    outcome: >
      Two-objective tradeoff curve plotted; useful for sanity-checking
      the dominance logic and for stakeholder reporting.

anti_patterns:
  - Computing the frontier on the raw sweep output without applying the task's quality gates first — gated-out rows can sit on the convex front and silently appear in the result.
  - Confusing the sense of an objective (passing `sense=["max", "max"]` when one column is "lower is better"). The output then maximizes both, which is the anti-frontier — looks plausible, is wrong.
  - Treating the "best F1" row as the Pareto-optimal answer. There is no single best; the frontier is a *set* of equally-good trade-offs.
  - Rounding objective values *before* the dominance test — rounding can collapse strictly-dominated rows into ties and pull dominated points onto the frontier. Round only on output.
  - Hand-rolling the O(N²) Python-loop check in a tight inner loop for thousands of points. Use `paretoset` or the vectorized numpy fallback in `scripts/compute_pareto.py`.
  - Writing the frontier in source column order when the task specifies a header — the grader's parser may key on column index, not name.
```
