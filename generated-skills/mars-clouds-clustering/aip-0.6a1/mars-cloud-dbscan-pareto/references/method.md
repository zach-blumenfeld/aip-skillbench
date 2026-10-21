# Evaluation contract and gotchas (mars-cloud-dbscan-pareto)

The scripts implement this contract. Read it to judge a warning or an odd result, or if
you have to reproduce a step by hand in a debugging session. Never use it to replace a
failed script step during a run.

## Data
- Two CSVs with many Zooniverse columns. Only `file_rad`, `x`, and `y` matter. `file_rad`
  is a path-like base filename (`080109120000/080110120000_A3.png`) with no variant suffix.
  It is the only join key between the files, and it must be read as a string.
- Loop over the unique `file_rad` values of the expert file. Citizen-science images missing
  from the expert file are ignored.
- Coordinates can be negative or beyond the image size. Keep them; nothing in the task
  filters them.

## Per hyperparameter combination (min_samples, epsilon, shape_weight = w)
1. For each expert image, take its citizen-science points. If there are none, the image
   scores F1 = 0.0 and delta = NaN.
2. Run DBSCAN(eps=epsilon, min_samples=min_samples) with
   `d(a,b) = sqrt((w*dx)^2 + ((2-w)*dy)^2)`. When w = 1 this is Euclidean distance; w > 1
   attenuates y distances (it weights x by w and y by 2-w), and w < 1 does the reverse. In
   sklearn, min_samples counts the point itself, and a neighbour at a distance of exactly
   eps counts.
   - The source skill's pattern (a factory returning `distance(a, b)` passed as
     `metric=`) is correct but slow. A precomputed matrix with the same formula
     (`metric="precomputed"`) gives identical labels. Build it once per (image, w) and reuse
     it across every (eps, min_samples) pair.
3. Centroid = mean x, y of each cluster's members. Label -1 is noise, not a cluster. No
   clusters means F1 = 0.0 and delta = NaN.
4. Greedy matching on standard Euclidean distance: compute every centroid-to-expert
   distance, sort ascending, and accept a pair when neither its centroid nor its expert
   point is used yet and the distance is <= 100. Stop at the first distance over 100. No
   matches means F1 = 0.0 and delta = NaN.
5. TP = number of matches, precision = TP / number of clusters, recall = TP / number of
   expert points, F1 = 2PR / (P + R). delta = mean distance of the matched pairs.
6. Average F1 over all expert images (zeros included). Average delta over the images
   whose delta is not NaN.

## Selection and output
- Keep combinations with mean F1 > 0.5 (strictly greater).
- Pareto-optimal: A dominates B when A is at least as good on both objectives (F1 higher
  is better, delta lower is better) and strictly better on one. Keep every non-dominated
  point. Exact ties dominate each other in neither direction, so keep all of them
  (`paretoset(..., sense=["max","min"], distinct=False)`).
- Compute dominance on unrounded values. Round only when writing: F1 and delta to 5
  decimals, shape_weight to 1 decimal; min_samples and epsilon are integers. The columns,
  in order, are `F1,delta,min_samples,epsilon,shape_weight`.

## Performance (what scripts/grid_search.py does and why)
- Speed: DBSCAN labels depend only on the adjacency `D <= eps` and the core set
  `#neighbours >= min_samples`, with the point itself counted. Per (image, w), the script
  builds D once and sorts its rows. Per eps it counts neighbours. It runs DBSCAN only when
  the core set changes, using sklearn's own core loop (`sklearn.cluster._dbscan_inner`),
  which gives exactly the labels of `DBSCAN(metric="precomputed")`. Scores are cached per
  distinct labelling of an image. A connected-components fallback (clusters seeded by
  their lowest core index, and each border point given to the earliest-seeded cluster that
  reaches it) reproduces the same labels if the private helper is missing.
- Parallelism: joblib runs image chunks balanced by n² work, at least 24 chunks with
  `n_jobs = cpu_count`. It uses `backend="multiprocessing"` because joblib 1.3.2's loky
  workers print ResourceTracker errors at exit on Python 3.12. Workers return small arrays.
  Each chunk's work is far above joblib's roughly 0.1 s overhead.
- Checkpoints: each chunk is saved under `<work_dir>/chunks/<hash>.npz`. The hash covers
  the grid, the chunk's images, and the input files' size and mtime. If the step hits the
  client's script timeout, resuming re-runs it and only the missing chunks are computed.
- Reference timing: 847 combinations × 369 images takes about 10 s of wall time on an
  overloaded 18-core machine.
- Verified: identical F1/delta for all 847 combinations under Python 3.12, sklearn 1.3.2,
  and numpy 1.26.4, and under Python 3.14 with sklearn 1.9. The 20-row frontier also
  matched a naive callable-metric implementation.
