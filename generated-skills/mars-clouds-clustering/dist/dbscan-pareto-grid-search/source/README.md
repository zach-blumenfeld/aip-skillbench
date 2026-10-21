# Source and provenance: dbscan-pareto-grid-search

## Sources (copied verbatim)

| File | Origin | Used for |
|---|---|---|
| `custom-distance-metrics/SKILL.md` | curated input skill | the shape-weighted DBSCAN metric, closure/factory pattern, precomputed-matrix and performance advice |
| `parallel-processing/SKILL.md` | curated input skill | joblib `Parallel`/`delayed` grid search, n_jobs, shared data, overhead and memory tips |
| `pareto-optimization/SKILL.md` | curated input skill | dominance definition, `paretoset(..., sense=["max","min"])`, filter-then-frontier pattern, CSV output |
| `task-instruction.md` | the task statement the downstream agent receives (Mars cloud clustering) | evaluation rules, grid, filter, rounding, output path |

The three skills describe one workflow: cluster crowd annotations with a custom DBSCAN metric, sweep hyperparameters in parallel, reduce to a Pareto frontier. The compiled skill joins them into one script plus a short decision layer.

## Component-kind choices

| Component | Kind | Why |
|---|---|---|
| Environment check (step 1) | execution (one-line import) | deterministic |
| Map task statement to flags (step 2) | client_task | the agent has to read free-form task text and fill flags; the flag table gives the defaults and meanings |
| `spec_matches_script` | decision (noul) | judging whether the task's prose rules equal the implemented ones; the answer is yes/no and picks the branch |
| `keep_tied_combos` | decision (noul) | whether to keep duplicate frontier combos depends on task wording; the answer maps to `--keep-ties` |
| Adapt a copy of the script when `spec_matches_script` is false | client_task | code has to be written for a rule the skill cannot anticipate |
| Grid search, metric, DBSCAN, centroids, greedy matching, F1/delta, NaN rules, averaging, F1 filter, Pareto, rounding, CSV (step 4) | execution `scripts/dbscan_pareto.py` | all deterministic rules, numbers and thresholds over structured inputs |
| Output validation (step 5) | execution (built into the script: `validate()`) | fixed format and dominance rules |

There is a single script because every piece shares the same data and loop; splitting it would only add I/O.

## Design notes (verified in the authoring session)

- The custom metric is computed exactly as the formula into a precomputed distance matrix per (image, w). On a 25-image sample (21k fits) and on 15 images over the full grid, labels and all-results are identical to `DBSCAN(metric=<python callable>)`.
- The fast path feeds sklearn's own `_dbscan_inner` with the same ascending-index eps-neighbourhoods that `DBSCAN(metric="precomputed")` builds, so labels are identical (0 mismatches in 21,175 fits) and it runs ~35x faster. The script falls back to the public class if that private module moves.
- The full real grid (847 combos x 369 images) takes about 10-20 s on a multi-core laptop. A separately written naive reference (Euclidean DBSCAN on scaled coordinates, list-sort greedy matching, O(n^2) dominance loop) takes 77 s and gives the same 20-row frontier exactly.
- joblib `backend="multiprocessing"` avoids the loky `ResourceTracker` traceback noise on Python 3.12. The script has a `__main__` guard, which spawn start methods need.
- Float grids are built by index and then rounded, so values like 1.2000000000000002 never appear.

## Deliberate-drop log

| Source content | Decision | Rationale |
|---|---|---|
| custom-distance-metrics: generic `my_distance` callable example | dropped | it is superseded by the concrete metric; a callable is still available through `--metric callable` |
| custom-distance-metrics: `create_weighted_distance(weight_x, weight_y)` factory | absorbed | it is the `dist(a, b, w=w)` closure in `eval_image` with weight_x=w, weight_y=2-w |
| custom-distance-metrics: Manhattan distance example | dropped | the source labels it "just one example"; this task's metric is fixed. If a task names an L1 metric, `spec_matches_script` is false and the agent adapts `eval_image` |
| custom-distance-metrics: scipy `cdist`/`pdist`/`squareform` | absorbed | the pairwise matrix is built with numpy broadcasting (same result, no Python callback) for both the metric and the matching distances |
| custom-distance-metrics: performance considerations (callables slow, vectorize, precompute) | kept | they are the reason for the precomputed and `_dbscan_inner` design and are listed as a Gotcha |
| parallel-processing: basic usage, `n_jobs` semantics | kept | `--n-jobs` flag (-1 = all cores) |
| parallel-processing: `verbose` parameter | dropped | the script prints its own summary, and progress bars would add stderr noise for an unattended agent |
| parallel-processing: `backend` loky vs threading | adapted | multiprocessing backend (CPU-bound; avoids loky exit noise), noted in Gotchas |
| parallel-processing: grid-search example, filtering None, best by max score | absorbed | the grid is `itertools.product` and the results are filtered by the F1 threshold. "Best single" is replaced by the Pareto set, as the task requires |
| parallel-processing: pre-compute shared data | kept | groups are pre-built once. Each worker gets only its image chunk ("watch memory" tip), noted in Gotchas |
| parallel-processing: ">0.1 s per item" overhead tip | applied | work is chunked into about 4 x n_jobs chunks of images, not per-combo tasks |
| pareto-optimization: dominance and frontier definitions | kept | listed in Gotchas, implemented by paretoset, and checked by `validate()` |
| pareto-optimization: paretoset usage with `sense` | kept | `paretoset(kept[["F1","delta"]], sense=["max","min"])` |
| pareto-optimization: manual `is_dominated` implementation | dropped | paretoset is installed in the container. The manual loop survives as the independent reference used during testing (not shipped) |
| pareto-optimization: filter by threshold, then frontier, sort, to_csv | kept | F1 > threshold, then paretoset, then sort by F1 descending, then CSV |
| pareto-optimization: matplotlib visualization | dropped | matplotlib is not in the container and no plot is required. The task output is a CSV |
| pareto-optimization: properties (trade-off curve, no single best, preference) | dropped | background. The monotone trade-off property is enforced by `validate()` |
| task-instruction: all rules (grid, metric, per-image loop over expert images, centroid, greedy matching <= 100 px Euclidean, F1/delta, NaN cases, averaging, F1 > 0.5, Pareto, rounding, output path and columns) | kept | script defaults, docstring, and the `spec_matches_script` rule list |
| task-instruction: "file_rad contains base filenames without variant suffixes" | kept | `--image-col file_rad` is used as-is, with no suffix stripping |
