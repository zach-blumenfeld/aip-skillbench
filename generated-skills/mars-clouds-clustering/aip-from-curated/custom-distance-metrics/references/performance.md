# Performance notes for custom distance metrics

Python-callable metrics in sklearn / scipy are evaluated one pair at a time
through the Python interpreter. They are correct but slow relative to the
built-in C-backed metrics. The cost compounds when DBSCAN is invoked inside an
outer grid search or per-image loop.

## When the Python callable is fine
- Datasets under a few thousand points per call.
- Outer loops dominated by other work (I/O, plotting, matching).
- Prototyping a new metric before optimising it.

## Speedups, in order of effort
1. **Vectorise inside the closure.** Operate on numpy arrays directly; avoid
   Python-level branching and per-element loops.
2. **Pre-compute distance matrices** when the same points are clustered or
   queried many times. `scipy.spatial.distance.cdist(points, points, metric=fn)`
   produces a dense matrix; pass `metric="precomputed"` to DBSCAN with that
   matrix.
3. **Recast as a built-in.** Many "custom" metrics are linear reweightings of
   the input axes (e.g. `d = sqrt((w*dx)**2 + ((2-w)*dy)**2)`). Scale the input
   coordinates once and call the built-in Euclidean metric — orders of
   magnitude faster than a Python callable.
4. **Parallelise the outer loop.** When the metric stays a Python callable,
   parallelise across hyperparameter combinations or across images rather than
   fighting the GIL inside the metric.

## Equivalence trick: shape-weighted Euclidean as a coordinate scale
Given `d(a, b) = sqrt((w*dx)**2 + ((2-w)*dy)**2)`, rescale `x' = w*x` and
`y' = (2-w)*y` once, then run `DBSCAN(metric="euclidean")` on the rescaled
points. Cluster identity is preserved; runtime drops to the C path.

`eps` interpretation does not change — it is still measured in the same
units as the weighted distance, because the rescaling absorbs the weights.
