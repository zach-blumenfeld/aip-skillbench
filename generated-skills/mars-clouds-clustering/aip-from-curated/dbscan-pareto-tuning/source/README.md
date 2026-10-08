# Source and provenance: dbscan-pareto-tuning

## Provenance

Compiled 2026-10-08 from three curated Agent Skills, copied verbatim here:

| Folder | Original | Contribution |
|---|---|---|
| `custom-distance-metrics/SKILL.md` | `inputs/skills/custom-distance-metrics/` | Callable / closure distance metrics for sklearn DBSCAN and scipy; performance caveats |
| `parallel-processing/SKILL.md` | `inputs/skills/parallel-processing/` | joblib `Parallel`/`delayed` grid search, shared pre-computed data, overhead tips |
| `pareto-optimization/SKILL.md` | `inputs/skills/pareto-optimization/` | Dominance, frontier, `paretoset` with `sense`, threshold-then-frontier, CSV output, manual fallback |

The sources contain no scripts, references, or assets beyond their SKILL.md files.

Domain context came from the task environment (`inputs/environment/`): the Dockerfile
(python 3.12, numpy 1.26.4, scipy 1.13.1, pandas 2.2.2, scikit-learn 1.3.2,
paretoset 1.2.3, joblib 1.3.2, no matplotlib) and the two data files
`citsci_train.csv` (25,856 crowd "Arch peak marker" marks, 1,413 images, ~1,441 users)
and `expert_train.csv` (1,940 expert marks, 778 images, one expert per image). Both
files share the same 54-column Zooniverse export layout. `frame_file` is the per-image
key: `file_rad` equals `frame_file` only for frame 0 of each 4-frame subject. 777
images appear in both files.

## Intent

The three sources together describe one workflow: sweep DBSCAN hyperparameters with
a parameterized custom distance, run the sweep in parallel, and keep the Pareto-optimal
trade-offs. The pack makes it executable end to end for "cluster crowd marks, match to
expert marks, report the (F1, delta) Pareto frontier" tasks, keeping every
task-specific number in a config so the agent maps the task's own wording onto it.

## Step-kind choices

| Step | Kind | Why |
|---|---|---|
| `configure` | client_task | The output is generated: turning free-text task rules (ranges, formula, cutoff, aggregation, output path/columns) into a config. Defaults plus a key-by-key guide in `assets/configure.md` keep it narrow. |
| `profile-data` | execution | Deterministic: merge defaults, expand inclusive grids, check columns, options, and paths, count frames and overlap. Supplies the evidence `review-config` needs, so that judgment does not rely on guesses. |
| `review-config` | decision (noul, threshold 0.2) | Whether the config faithfully reflects the task is a judgment with a yes/no answer space; a false positive wastes the sweep or yields a wrong answer, hence the wide review margin. |
| `route-config` | router | Branches on `config_ready`; `false` loops back to `configure` with `config_problems`/`profile` in the state. |
| `grid-search` | execution | Clustering, matching, metrics, filtering, Pareto, and CSV writing are pure computation. One script keeps the sweep, frontier, and output consistent. |
| `review-result` | decision (noul, threshold 0.2) | A last sanity gate (non-empty, monotone trade-off, floor respected, verification clean) before declaring the answer; `false` loops back with `result_notes`. |
| `end` | end | Output path, frontier rows, summary. |

Script design notes:
- `scripts/clustertune.py` is the shared library; `profile_data.py` and `grid_search.py`
  are the two entry points (stdin JSON for `aip run`, `--config` for manual runs).
- The custom metric is applied as a vectorized scaled-coordinate distance matrix per
  (image, w), reused across all (eps, min_samples). DBSCAN is re-implemented on that
  matrix with sklearn's exact semantics, and each run spot-checks it against
  `sklearn.cluster.DBSCAN(metric=<callable closure>)`, the source skill's own pattern,
  aborting on any mismatch. This follows the source's "custom Python functions are
  slower / vectorize / pre-compute distance matrices" advice. The full real-data sweep
  (847 combinations × 777 images) takes about 25 s.
- joblib parallelizes over shape weights (11 tasks of about 2 s each, above the
  source's 0.1 s overhead floor). Data are loaded once and shared.
- `paretoset(..., sense=["max","min"])` is used as in the source, with the manual
  dominance check as a fallback when the package is missing.

## Completeness check (source → pack)

custom-distance-metrics
- Callable `metric` for DBSCAN → `clustertune.make_weighted_metric` (used in verification); method.md §1.
- Parameterized closure / factory → `make_weighted_metric`, config `x_scale`/`y_scale` expressions in `w`; method.md §1.
- Weighted distance example (`weight_x`, `weight_y`) → default metric `w`, `2 - w`; configure.md "Distance".
- Manhattan with scale → `minkowski_p: 1` + scale expressions; method.md §1.
- scipy `cdist`/`pdist`/`squareform` → `cdist` used for matching cost; mentioned in method.md §1.
- Performance considerations (slow callables, vectorize, pre-compute matrices) → script design; anti_pattern 2; method.md §1.

parallel-processing
- `Parallel(n_jobs=-1)(delayed(f)(x) ...)` → `grid_search.py`; method.md §2.
- Key parameters n_jobs / verbose / backend → method.md §2; config `n_jobs`.
- Grid search over `product(...)`, filter `None`, pick best → `evaluate_weight` grid, deterministic product ordering, `best_f1_row`; method.md §2.
- Pre-computing shared data → data loaded/grouped once and passed to workers; method.md §2.
- Performance tips (>0.1 s per item, memory copies, verbose=10) → method.md §2 and the design notes above.

pareto-optimization
- Dominance definition, frontier definition → method.md §3; `pareto_mask` fallback.
- `paretoset` with `sense` max/min → `clustertune.pareto_mask`.
- Manual implementation → `pareto_mask` ImportError fallback (vectorized version of the same rule).
- Model-selection example: threshold filter → frontier → sort desc → CSV → `grid_search.py` (`f1_min`, `sort_by`, `output_csv`); review-result checks.
- Properties (trade-off curve, no single best, choice depends on preference) → method.md §3; the monotone check in `review-result`.
- Visualization → method.md §3 (optional, only when asked).

## Deliberate drops

- **Toy example data** (accuracy/latency/model_size tables, `learning_rate`, `batch_size`, `hidden_units` values): illustrative only. The pattern is kept, the numbers are not.
- **`process_item(x) = x**2` and sequential-vs-parallel demo**: illustrative only; the real parallel call is in `grid_search.py`.
- **Matplotlib plotting code verbatim**: matplotlib is not installed in the task container and no output figure is required by the workflow. A one-line description stays in method.md §3 for tasks that ask for a plot.
- **The source's manual `is_dominated` loop as written**: replaced by an equivalent vectorized dominance check (same rule: ≥ in all objectives, strictly better in one) to keep the fallback fast.

## Functional test log (2026-10-08)

- `aip run` on synthetic full-length copies of both CSVs (same 54-column layout, 95% of rows, x/y jittered by σ = 3 px; test inputs kept in the workspace `scratch/`, not in the pack). The run went configure → profile-data → review-config(true) → grid-search → review-result(true) → end. Both `false` branches were also exercised: an unknown `frame_col` is reported in `config_problems` and loops back to configure, and `result_ok: false` loops back too. No script errors; sklearn spot-check showed 0/300 mismatches.
- The same sweep run on the real `inputs/environment/data` files under the container's pinned stack (py3.12, numpy 1.26.4, pandas 2.2.2, sklearn 1.3.2, joblib 1.3.2, paretoset 1.2.3) gave results identical to the py3.14 run. joblib 1.3.2's loky printed harmless ResourceTracker tracebacks on macOS, which is documented in method.md §2.
- One fresh agent ran the procedure from a trigger-style prompt and reproduced the same frontier. Its feedback led to three fixes: match_mode phrase mapping added (method.md §4, configure.md), a note that the expert file's mixed `workflow_name` values are not a reason to filter, and the column lists removed from the profile output to cut verbosity.
