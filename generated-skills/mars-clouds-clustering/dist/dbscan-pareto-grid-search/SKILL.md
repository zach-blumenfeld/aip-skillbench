---
name: dbscan-pareto-grid-search
description: Grid-search DBSCAN hyperparameters (min_samples, epsilon, an anisotropic shape_weight distance) to cluster crowd-sourced point annotations (e.g. Mars cloud arch-peak markers from citizen scientists), score each setting against expert points with greedy centroid matching (F1 and mean distance delta), and write the F1-max / delta-min Pareto frontier CSV. Use for custom-distance-metric DBSCAN tuning, joblib-parallel grid searches, and Pareto frontier extraction with paretoset.
compatibility: Python >= 3.9 with numpy, pandas, scikit-learn, joblib, paretoset (task container pins numpy 1.26.4, pandas 2.2.2, scikit-learn 1.3.2, joblib 1.3.2, paretoset 1.2.3). No network needed.
---

# DBSCAN Pareto Grid Search

## Trigger When

1. A task asks to optimize/grid-search DBSCAN hyperparameters and output a Pareto frontier (e.g. `/root/pareto_frontier.csv` with `F1,delta,min_samples,epsilon,shape_weight`).
2. Citizen-science (crowd) point annotations must be clustered and compared to expert annotations per image (`file_rad`-style image key, `x`, `y` columns).
3. DBSCAN needs a custom or weighted distance metric such as `d = sqrt((w*dx)^2 + ((2-w)*dy)^2)`.
4. Broader: any multi-objective hyperparameter sweep (maximize one score, minimize another) that should run in parallel with joblib and be reduced to Pareto-optimal points.

## Purpose

Turns the "cluster crowd annotations, match to experts, sweep hyperparameters, keep the Pareto set" workflow into one tested script. It carries the exact evaluation rules (per-image F1/delta, which images count, NaN handling, greedy matching on plain Euclidean distance, F1 filter, rounding), a fast exact DBSCAN path (precomputed custom-metric matrix + sklearn's own inner loop, ~30x faster than a Python callable metric, verified label-identical), joblib parallelism, and paretoset frontier extraction, so the full 847-combo grid over ~370 images finishes in seconds instead of hours.

## Procedure

Progress:
- [ ] 1. Check the environment
- [ ] 2. Read the task statement and map it to flags (client task)
- [ ] 3. Spec-conformance decision
- [ ] 4. Smoke run, then full run (script)
- [ ] 5. Validate the output

### 1. Check the environment

Run `python -c "import numpy, pandas, sklearn, joblib, paretoset"`. If it fails, name every missing package and `pip install` them (the task container already has all five). Python >= 3.9.

### 2. Map the task statement to flags (client task)

Read the task's instruction file. Fill each flag below from it; keep the default when the task matches it. Range flags take `start:stop:step` (inclusive both ends) or a comma list.

| Flag | Default (Mars clouds task) | Meaning |
|---|---|---|
| `--citsci` | `/root/data/citsci_train.csv` | crowd points, columns image-key, `x`, `y` |
| `--expert` | `/root/data/expert_train.csv` | expert points, same columns |
| `--out` | `/root/pareto_frontier.csv` | frontier CSV |
| `--image-col` | `file_rad` | column matching images across both files (use as-is; no suffix stripping needed) |
| `--min-samples` | `3:9:1` | integer grid |
| `--eps` | `4:24:2` | epsilon grid (integers in output when all integral) |
| `--shape-weight` | `0.9:1.9:0.1` | w grid; values rounded to avoid float drift |
| `--f1-threshold` | `0.5` | keep mean F1 **strictly greater** |
| `--max-match-dist` | `100` | greedy match cutoff, plain Euclidean pixels (pairs with distance <= cutoff match) |
| `--keep-ties` | off | see decision `keep_tied_combos` |
| `--n-jobs` | `-1` (all cores) | joblib workers |
| `--all-results` | none | optional CSV of all combos, for inspection |
| `--max-images` | none | first N expert images only (smoke tests) |
| `--metric` | `precomputed` | `callable` = literal Python metric, slow, cross-check only |

### 3. Spec-conformance decision

Answer both questions against the task statement before running.

```yaml
spec_matches_script:
  type: noul
  instructions: >
    Does the task's evaluation match what scripts/dbscan_pareto.py implements?
    Script rules: DBSCAN distance sqrt((w*dx)^2 + ((2-w)*dy)^2) with eps <= inclusive;
    centroid = mean x,y of each non-noise cluster in original coordinates; greedy
    one-to-one matching of centroids to expert points by plain Euclidean distance,
    closest pair first, cutoff --max-match-dist; per-image F1 = 2PR/(P+R) with
    P = matches/clusters, R = matches/expert points; delta = mean matched Euclidean
    distance; loop over every image in the EXPERT file; image with no crowd points,
    no clusters, or no matches -> F1 0.0 (counted) and delta NaN (skipped in the
    delta mean); keep combos with mean F1 > threshold; Pareto with F1 max, delta min;
    round F1/delta to 5 dp, shape_weight to 1 dp, min_samples/epsilon as integers.
  criteria:
    true: Every rule the task states is one of the above or is set by a flag in step 2.
    false: The task states a different metric, matching rule, averaging rule, objective, filter, or output column set.
  costly_mistake: A false "true" silently produces a wrong frontier; reconsider any close call that leans true.
keep_tied_combos:
  type: noul
  instructions: >
    Should every hyperparameter combo that shares an identical frontier (F1, delta)
    value be written, rather than one representative per value?
  criteria:
    true: The task explicitly asks for every parameter combination achieving each optimal trade-off, or says not to deduplicate.
    false: The task just asks for the Pareto-optimal points / frontier, including "identify all Pareto-optimal points" (the paretoset default, distinct=True, keeps one per value).
  costly_mistake: Either; default false. The script prints how many tied combos were collapsed; if that is 0 the answer does not change the output.
```

- `spec_matches_script` = true → step 4 as is.
- `spec_matches_script` = false → (client task) copy `scripts/dbscan_pareto.py` into the working directory, change only the differing rule (`eval_image` for metric/centroids/F1, `greedy_match` for matching, `main` for averaging/filter/Pareto/rounding), and run the copy in step 4.
- `keep_tied_combos` = true → add `--keep-ties`.

### 4. Run (script)

Smoke run first (seconds), then the full grid (about 10-30 s on the real data with several cores):

```bash
python scripts/dbscan_pareto.py --max-images 10 --out /tmp/smoke.csv
python scripts/dbscan_pareto.py --out /root/pareto_frontier.csv --all-results /tmp/all_results.csv
```

Add the step-2/3 flags to both. Paths are relative to this skill folder; use the absolute path of the script if running from elsewhere. Stdout reports image counts, grid size, how many combos passed the F1 filter, collapsed ties, and the frontier table.

### 5. Validate the output

- The script re-reads its CSV and prints `VALIDATION OK` (header exactly `F1,delta,min_samples,epsilon,shape_weight`, no NaN, every F1 > threshold, delta strictly falling as F1 falls so no row is dominated). On `VALIDATION FAILED`, fix the cause and rerun; do not hand-edit the CSV.
- `images (expert)` equals the number of unique image keys in the expert file; "without citizen points" images are still counted in F1.
- If the script warns that no combo passed the F1 filter, it writes a header-only CSV; recheck the flags (column names, ranges, cutoff) before accepting that.
- If the result looks implausible, rerun a few images with `--metric callable --max-images 5 --all-results /tmp/b.csv` and the same with the default metric; the two `--all-results` files must be identical.

## Gotchas

- Do not pass a Python callable metric to DBSCAN for the full grid: ~300k DBSCAN fits with a Python metric take hours. The custom metric is computed exactly as written into a precomputed matrix instead; this is label-identical to the callable (verified).
- Match centroids with **plain** Euclidean distance, not the shape-weighted one; the custom metric is only for clustering. Centroids use original (unscaled) coordinates.
- Iterate images from the expert file, not the crowd file; images missing crowd points contribute F1 = 0.
- Average delta only over images with matches (NaN-skipping), but average F1 over all images.
- Generate float grids by index (`start + i*step`, rounded), not `np.arange` accumulation, or 1.2000000000000002 leaks into lookups/output.
- joblib's default loky backend prints `ResourceTracker` tracebacks at exit on Python 3.12; the script uses `backend="multiprocessing"` to keep stderr clean. Each worker receives only its image chunk, not the whole dataset.
- paretoset `sense` is `["max", "min"]` for `(F1, delta)`. Pareto dominance: A dominates B if A is no worse on both objectives and strictly better on one.
