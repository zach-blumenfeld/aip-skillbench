# Method reference: weighted-distance DBSCAN sweep → Pareto frontier

Load when a task phrase does not obviously map to a config key, when you need to run
or change the scripts by hand, or when a result looks wrong.

## 1. Custom distance metric (from custom-distance-metrics)

sklearn's `DBSCAN` accepts a callable `metric(a, b)` on two 1-D points. Parameterize it
with a closure / factory:

```python
def create_weighted_distance(weight_x, weight_y):
    def distance(a, b):
        dx = a[0] - b[0]; dy = a[1] - b[1]
        return np.sqrt((weight_x * dx)**2 + (weight_y * dy)**2)
    return distance
db = DBSCAN(eps=10, min_samples=3, metric=create_weighted_distance(2.0, 0.5))
```

Manhattan is the same idea with `scale * (|dx| + |dy|)` (config `minkowski_p: 1`,
scales folded into `x_scale`/`y_scale`). `scipy.spatial.distance.cdist / pdist /
squareform` accept the same callable for distance matrices.

Performance: a Python callable is evaluated once per point pair per fit, which is far
slower than built-in metrics. The scripts therefore:

- pre-compute one scaled distance matrix per (image, shape weight), vectorized in
  numpy: a weighted Euclidean/Minkowski metric is just the plain metric on
  (sx·x, sy·y);
- reuse it for every (epsilon, min_samples) pair, with DBSCAN rebuilt from the
  eps-neighbourhood matrix under sklearn's exact semantics: neighbourhood is
  `d <= eps` and includes the point itself, a point is core when its count is
  `>= min_samples`, clusters are connected core points, a border point joins the
  first cluster (in index order) that reaches it, and noise is `-1`;
- spot-check that against `sklearn.cluster.DBSCAN(metric=<callable>)` on
  `verify_samples` random (image, w, eps, min_samples) draws before the sweep, and
  abort on any centroid mismatch.

## 2. Parallel grid search (from parallel-processing)

`joblib.Parallel(n_jobs=-1)(delayed(f)(args) for ...)` with
- `n_jobs`: `-1` all cores, `1` sequential, or a specific number;
- `verbose`: `0` silent, `10` progress, `50` detailed;
- `backend`: `'loky'` (CPU-bound, default) or `'threading'` (I/O-bound).

Grid pattern: build `itertools.product(...)` of parameters, evaluate each in parallel,
return dicts, drop `None` results, then select. Pre-compute shared data once (load and
group the CSVs once) and pass it to each task. Parallelism only pays off for tasks over
~0.1 s each, and every worker gets a copy of the data, so watch memory. The script
parallelizes over shape weights (one task = every eps × min_samples for one w); set
config `n_jobs: 1` if the container is memory-tight. With joblib 1.3.2 on Python 3.12,
loky workers may print `ResourceTracker ... ChildProcessError` tracebacks to stderr at
exit. They are harmless (stdout JSON and the CSV are unaffected). If they bother you,
`n_jobs: 1` runs the full sweep sequentially in about 25 s.

## 3. Pareto frontier (from pareto-optimization)

A dominates B when A is at least as good in every objective and strictly better in at
least one. The frontier is the set of non-dominated points: improving one objective
along it worsens the other, no single point is "best", and the final choice depends on
preference between objectives.

```python
from paretoset import paretoset
mask = paretoset(df[["F1", "delta"]], sense=["max", "min"])   # max F1, min delta
front = df[mask].sort_values("F1", ascending=False)
front.to_csv(path, index=False)
```

Filter by threshold first (e.g. keep `F1 > 0.5`), then compute the mask; the frontier
of the filtered set is what the task asks for. paretoset's default `distinct=True` keeps
one row per identical objective pair (config `pareto_distinct: false` keeps all). If
paretoset is missing, the script falls back to the manual O(n²) dominance check.

Optional plot: scatter all points (delta on x, F1 on y), overlay frontier in red squares.
Only produce it if the task asks for a figure (matplotlib is not in the container).

## 4. Matching and metrics

Per image: cluster the crowd marks, take each cluster's centroid (mean of its member
points, unweighted coordinates), compute the plain Euclidean cost matrix centroid ×
expert point, solve with `scipy.optimize.linear_sum_assignment`, and keep pairs with
cost `<= match_max_distance`.

- TP = kept pairs, FP = centroids − TP, FN = expert points − TP,
  F1 = 2TP / (2TP + FP + FN) (an image with expert points and no clusters scores 0).
- delta = mean distance of kept pairs. `per_image_mean` averages each image's mean over
  images with ≥1 match; `global_pairs` averages over all pairs. A combination with no
  matches at all has no delta and is dropped.
- F1 `per_image_mean` averages per-image F1 over the evaluated images; `global` pools
  TP/FP/FN first.

Phrase → key: "average F1 across images" → `per_image_mean`; "micro / overall F1" →
`global`; "average distance of matched pairs" with no per-image wording → ambiguous,
keep `per_image_mean` unless the task pools pairs; "images annotated by experts" →
`frames: expert`; "images with both" → `intersection`; "F1 at least X" →
`f1_min_inclusive: true`; "match with the Hungarian algorithm, matches over X px
don't count / are discarded" or just "within X px" → `assign_then_filter` (default:
solve on the raw cost matrix, then drop over-limit pairs); "only pairs closer than X
may be assigned" / "infeasible beyond X" → `mask_then_assign`.

## 5. Running by hand

Both scripts also accept `--config cfg.json` (a partial config, merged over
`assets/default_config.json`):

```bash
python scripts/profile_data.py --config cfg.json   # validates columns, prints a profile
python scripts/grid_search.py  --config cfg.json   # writes output_csv, prints summary JSON
```

A full 847-combination sweep on ~26k crowd marks / ~800 images takes well under a
minute on a few cores.
